"""Public Python API for the AI Washing Detector.

Returns frozen dataclasses -- no ORM models leak to consumers.
Downstream modules (portfolio management, trade execution) import these
functions to retrieve composite scores without knowing about database
internals or SQLAlchemy models.

Usage::

    from ai_washer import get_score, get_latest_scores, get_score_history

    score = get_score("AAPL")
    all_scores = get_latest_scores()
    history = get_score_history("AAPL", date(2026, 1, 1), date(2026, 3, 31))
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_washer.analysis.composite_scorer import ALL_SIGNAL_TYPES, classify_risk_band
from ai_washer.api_types import CompanyScore
from ai_washer.db.models import Company, DailyScore, SignalDetail
from ai_washer.db.session import get_session_factory

logger = structlog.get_logger(__name__)


def _build_signal_freshness(
    company_id: uuid.UUID,
    session: Session,
) -> dict[str, date]:
    """Query the most recent as_of_date per signal type for a company.

    Args:
        company_id: UUID of the company to look up.
        session: Active SQLAlchemy session.

    Returns:
        Dict mapping signal_type -> latest as_of_date.  Empty dict if no
        SignalDetail rows exist for the company.
    """
    stmt = (
        select(
            SignalDetail.signal_type,
            func.max(SignalDetail.as_of_date).label("latest_date"),
        )
        .where(SignalDetail.company_id == company_id)
        .group_by(SignalDetail.signal_type)
    )
    rows = session.execute(stmt).all()
    return {signal_type: latest_date for signal_type, latest_date in rows}


def _row_to_company_score(
    row: DailyScore,
    company: Company,
    session: Session,
) -> CompanyScore:
    """Convert an ORM DailyScore + Company into a frozen CompanyScore.

    Args:
        row: DailyScore ORM instance.
        company: Company ORM instance.
        session: Active session (used for signal freshness lookup).

    Returns:
        Frozen CompanyScore dataclass.
    """
    breakdown = row.signal_breakdown or {}
    signals_available = sorted(breakdown.keys())
    signals_missing = sorted(
        st for st in ALL_SIGNAL_TYPES if st not in breakdown
    )
    signal_freshness = _build_signal_freshness(row.company_id, session)

    risk_band = classify_risk_band(row.composite_score)

    return CompanyScore(
        ticker=company.ticker,
        company_name=company.name,
        scored_at=row.scored_at,
        composite_score=row.composite_score,
        risk_band=risk_band,
        confidence=row.confidence,
        signal_breakdown=dict(breakdown),
        weights_used=dict(row.weights_used or {}),
        signals_available=signals_available,
        signals_missing=signals_missing,
        run_id=row.run_id,
        signal_freshness=signal_freshness if signal_freshness else None,
    )


def get_score(
    ticker: str,
    score_date: date | None = None,
    *,
    session: Session | None = None,
) -> CompanyScore | None:
    """Retrieve the composite score for a single company.

    Args:
        ticker: Stock ticker symbol (case-insensitive).
        score_date: Optional date to query.  If None, returns the most
            recent score.
        session: Optional SQLAlchemy session.  If None, one is created
            automatically via ``get_session_factory()``.

    Returns:
        CompanyScore frozen dataclass, or None if the ticker is not found
        or no score exists for the requested date.
    """
    own_session = session is None
    if own_session:
        factory = get_session_factory()
        session = factory()

    try:
        # Look up company (case-insensitive)
        company_stmt = select(Company).where(
            func.upper(Company.ticker) == ticker.upper()
        )
        company = session.execute(company_stmt).scalar_one_or_none()
        if company is None:
            logger.info("company_not_found", ticker=ticker)
            return None

        # Query score
        if score_date is None:
            score_stmt = (
                select(DailyScore)
                .where(DailyScore.company_id == company.id)
                .order_by(DailyScore.scored_at.desc())
                .limit(1)
            )
        else:
            score_stmt = (
                select(DailyScore)
                .where(
                    DailyScore.company_id == company.id,
                    func.date(DailyScore.scored_at) == score_date,
                )
                .order_by(DailyScore.scored_at.desc())
                .limit(1)
            )

        row = session.execute(score_stmt).scalar_one_or_none()
        if row is None:
            logger.info("score_not_found", ticker=ticker, score_date=score_date)
            return None

        return _row_to_company_score(row, company, session)
    finally:
        if own_session:
            session.close()


def get_latest_scores(
    *,
    session: Session | None = None,
) -> list[CompanyScore]:
    """Retrieve the most recent score for every scored company.

    Scores are sorted by composite_score descending (highest risk first).

    Args:
        session: Optional SQLAlchemy session.

    Returns:
        List of CompanyScore frozen dataclasses, or empty list if no
        scores exist.
    """
    own_session = session is None
    if own_session:
        factory = get_session_factory()
        session = factory()

    try:
        # Subquery: max scored_at per company
        latest_subq = (
            select(
                DailyScore.company_id,
                func.max(DailyScore.scored_at).label("max_scored_at"),
            )
            .group_by(DailyScore.company_id)
            .subquery()
        )

        stmt = (
            select(DailyScore, Company)
            .join(Company, DailyScore.company_id == Company.id)
            .join(
                latest_subq,
                (DailyScore.company_id == latest_subq.c.company_id)
                & (DailyScore.scored_at == latest_subq.c.max_scored_at),
            )
            .order_by(DailyScore.composite_score.desc())
        )

        rows = session.execute(stmt).all()
        if not rows:
            return []

        results: list[CompanyScore] = []
        for daily_score, company in rows:
            results.append(_row_to_company_score(daily_score, company, session))
        return results
    finally:
        if own_session:
            session.close()


def get_score_history(
    ticker: str,
    start_date: date,
    end_date: date,
    *,
    session: Session | None = None,
) -> list[CompanyScore]:
    """Retrieve score history for a company over a date range.

    Scores are sorted by scored_at ascending (chronological order).

    Args:
        ticker: Stock ticker symbol (case-insensitive).
        start_date: Inclusive start of date range.
        end_date: Inclusive end of date range.
        session: Optional SQLAlchemy session.

    Returns:
        List of CompanyScore frozen dataclasses sorted by scored_at ASC,
        or empty list if ticker not found or no scores in range.
    """
    own_session = session is None
    if own_session:
        factory = get_session_factory()
        session = factory()

    try:
        # Look up company (case-insensitive)
        company_stmt = select(Company).where(
            func.upper(Company.ticker) == ticker.upper()
        )
        company = session.execute(company_stmt).scalar_one_or_none()
        if company is None:
            logger.info("company_not_found", ticker=ticker)
            return []

        stmt = (
            select(DailyScore)
            .where(
                DailyScore.company_id == company.id,
                func.date(DailyScore.scored_at) >= start_date,
                func.date(DailyScore.scored_at) <= end_date,
            )
            .order_by(DailyScore.scored_at.asc())
        )

        rows = session.execute(stmt).scalars().all()
        return [_row_to_company_score(r, company, session) for r in rows]
    finally:
        if own_session:
            session.close()
