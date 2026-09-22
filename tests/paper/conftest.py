"""Shared fixtures for the Phase 9 paper-trading test suite.

Inherits ``db_session`` / ``sqlite_engine`` from the root tests/conftest.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import EpisodicMemory

SHA = "d" * 64


def seed_signal(
    db_session: Session,
    *,
    ticker: str = "AAPL",
    as_of: str = "2026-04-18",
    record_type: str = "analysis",
) -> int:
    """Insert one episodic row and return its id (the FK target for paper_trades)."""
    row = EpisodicMemory(
        ticker=ticker,
        sector="Technology",
        record_type=record_type,
        signal_direction="long",
        confidence=70,
        policy_sha=SHA,
        as_of_date=normalise_as_of(as_of),
        payload={"schema_version": 1},
    )
    db_session.add(row)
    db_session.commit()
    return row.id


@pytest.fixture()
def signal_id(db_session: Session) -> int:
    """One AAPL record_type='analysis' row dated 2026-04-18."""
    return seed_signal(db_session)
