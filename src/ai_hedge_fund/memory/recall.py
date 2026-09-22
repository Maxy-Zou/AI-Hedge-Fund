"""Episodic recall query (MEM-01 read path).

The temporal-filter contract is non-negotiable: every call filters by
``as_of_date <= target`` (07-RESEARCH.md Pitfall 2). Tests seed a row
at ``as_of_date='2099-01-01'`` and assert a query with an earlier target
never returns it.

The recall query is DELIBERATELY not a PydanticAI tool (v1 design per
07-RESEARCH.md §Anti-Patterns): Plan 07-03's ``memory_recall_node`` calls
this function once per run so every downstream agent sees the same
deterministic hit set.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.memory.episodic import EpisodicHit


def _to_hit(row: EpisodicMemory) -> EpisodicHit:
    """Convert a SQLAlchemy row to an immutable :class:`EpisodicHit`."""
    as_of_str = (
        row.as_of_date.isoformat() if hasattr(row.as_of_date, "isoformat") else str(row.as_of_date)
    )
    return EpisodicHit(
        id=row.id,
        ticker=row.ticker,
        sector=row.sector,
        record_type=row.record_type,
        as_of_date=as_of_str,
        signal_direction=row.signal_direction,
        confidence=row.confidence,
        outcome_pct=row.outcome_pct,
        linked_analysis_id=row.linked_analysis_id,
        policy_sha=row.policy_sha,
        payload=dict(row.payload) if row.payload else {},
    )


def query_episodic(
    db_session: Session,
    *,
    as_of_date: str | date | datetime,
    ticker: str | None = None,
    sector: str | None = None,
    limit: int = 10,
) -> list[EpisodicHit]:
    """Return episodic hits visible as of ``as_of_date``.

    At least one of ``ticker`` / ``sector`` MUST be supplied. When both
    are supplied the query returns rows matching EITHER (ticker OR sector)
    so a candidate gets ticker-specific prior analyses AND sector-wide
    context in one pass.

    Always filters by ``as_of_date <= target`` (Pitfall 2). Always orders
    by ``as_of_date DESC`` and bounds by ``limit``.

    Args:
        db_session: Open SQLAlchemy session.
        as_of_date: Analysis cutoff; no row dated AFTER this is returned.
        ticker: Target ticker (e.g. ``"AAPL"``).
        sector: Target sector (e.g. ``"Technology"``).
        limit: Maximum rows to return (DoS cap; Pitfall 8). Defaults to 10.

    Returns:
        List of :class:`EpisodicHit` in ``as_of_date`` DESC order; length
        ``<= limit``.

    Raises:
        ValueError: Neither ``ticker`` nor ``sector`` supplied.
    """
    if ticker is None and sector is None:
        raise ValueError("query_episodic requires ticker or sector (Pitfall 8 DoS guard)")
    target = normalise_as_of(as_of_date)
    predicates: list[Any] = []
    if ticker is not None:
        predicates.append(EpisodicMemory.ticker == ticker)
    if sector is not None:
        predicates.append(EpisodicMemory.sector == sector)

    rows = (
        db_session.query(EpisodicMemory)
        .filter(EpisodicMemory.as_of_date <= target)
        .filter(EpisodicMemory.record_type.in_(("analysis", "outcome")))
        .filter(or_(*predicates))
        .order_by(EpisodicMemory.as_of_date.desc())
        .limit(limit)
        .all()
    )
    return [_to_hit(row) for row in rows]
