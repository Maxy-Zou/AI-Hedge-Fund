"""Fixtures for the execution suite: build analysis + review rows the way the
Phase 8 pipeline stores them, so submit orchestration is tested against the real
payload shapes (09-PREMORTEM #23), not hand-invented keys.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import DailyPrice, EpisodicMemory

RISK_SHA = "1" * 64
REVIEW_SHA = "2" * 64


def make_analysis(
    db_session: Session,
    *,
    ticker: str = "AAPL",
    as_of: str = "2026-04-18",
    risk_status: str = "APPROVED",
    direction: str = "long",
    conviction: int = 80,
) -> int:
    """Insert a record_type='analysis' row (mirrors episodic_store_node payload)."""
    row = EpisodicMemory(
        ticker=ticker,
        sector="Technology",
        record_type="analysis",
        signal_direction=direction,
        confidence=conviction,
        policy_sha=RISK_SHA,
        as_of_date=normalise_as_of(as_of),
        payload={
            "schema_version": 1,
            "thesis": {"confidence": conviction},
            "signal": {"direction": direction},
            "risk_assessment": {"status": risk_status, "policy_sha": RISK_SHA},
        },
    )
    db_session.add(row)
    db_session.commit()
    return row.id


def add_review(
    db_session: Session,
    analysis_id: int,
    *,
    ticker: str = "AAPL",
    as_of: str = "2026-04-18",
    review_status: str = "NOT_REQUIRED",
    direction: str = "long",
    conviction: int = 80,
) -> int:
    """Insert a record_type='review' row (mirrors review_store_node payload)."""
    final_signal = {
        "ticker": ticker,
        "as_of_date": as_of,
        "direction": direction,
        "conviction": conviction,
        "thesis_summary": "t",
        "risk_score": 20,
        "thesis_link": f"episodic://{analysis_id}",
        "policy_sha": RISK_SHA,
        "review_policy_sha": REVIEW_SHA,
        "episodic_id": analysis_id,
        "review_status": review_status,
    }
    row = EpisodicMemory(
        ticker=ticker,
        sector="Technology",
        record_type="review",
        signal_direction=direction,
        confidence=conviction,
        linked_analysis_id=analysis_id,
        policy_sha=RISK_SHA,
        as_of_date=normalise_as_of(as_of),
        payload={
            "schema_version": 1,
            "review_status": review_status,
            "review_decision": {"status": review_status, "review_policy_sha": REVIEW_SHA},
            "review_policy_sha": REVIEW_SHA,
            "linked_analysis_id": analysis_id,
            "final_signal": final_signal,
        },
    )
    db_session.add(row)
    db_session.commit()
    return row.id


def add_price(
    db_session: Session, ticker: str = "AAPL", d: str = "2026-04-17", adj: int = 10_000
) -> None:
    db_session.add(
        DailyPrice(
            ticker=ticker,
            trade_date=date.fromisoformat(d),
            open_cents=adj,
            high_cents=adj,
            low_cents=adj,
            close_cents=adj,
            adj_close_cents=adj,
            volume=1_000,
            source="test",
            as_of_date=datetime.fromisoformat(d + "T00:00:00+00:00"),
        )
    )
    db_session.commit()


@pytest.fixture()
def reviewed_signal(db_session: Session) -> int:
    """An APPROVED-risk, reviewed (NOT_REQUIRED), long signal with a cheap price."""
    aid = make_analysis(db_session)
    add_review(db_session, aid)
    add_price(db_session)
    return aid
