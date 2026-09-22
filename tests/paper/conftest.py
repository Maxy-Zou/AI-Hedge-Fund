"""Shared fixtures for the Phase 9 paper-trading test suite.

Inherits ``db_session`` / ``sqlite_engine`` from the root tests/conftest.py.
Seed data is self-contained under tests/paper/fixtures/ so this suite cannot
break when another suite's fixtures change:

- seeded_signals.csv     9 episodic rows: 6 usable analysis signals incl. the
                         FUTUREX @ 2099-01-01 temporal-leak seed (PT-05); a
                         deliberate duplicate pair (DUPX) for AmbiguousSignal;
                         two record_type='review' rows that must never resolve.
- seeded_paper_trades.csv 6 order intents: market + limit, a rejection and its
                         attempt-2 retry, a VETOED refusal, and FUTUREX.
- seeded_paper_fills.csv 5 fills incl. two partial fills for one order and a
                         FUTUREX fill @ 2099-01-01.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.memory.episodic import seed_episodic_from_csv

FIXTURES_DIR = Path(__file__).parent / "fixtures"
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


@pytest.fixture()
def signals_csv_path() -> Path:
    return FIXTURES_DIR / "seeded_signals.csv"


@pytest.fixture()
def paper_trades_csv_path() -> Path:
    return FIXTURES_DIR / "seeded_paper_trades.csv"


@pytest.fixture()
def paper_fills_csv_path() -> Path:
    return FIXTURES_DIR / "seeded_paper_fills.csv"


@pytest.fixture()
def seeded_signals(db_session: Session, signals_csv_path: Path) -> int:
    """Seed the episodic signals; returns the row count (9)."""
    return seed_episodic_from_csv(db_session, signals_csv_path)


@pytest.fixture()
def seeded_ledger(
    db_session: Session,
    seeded_signals: int,
    paper_trades_csv_path: Path,
    paper_fills_csv_path: Path,
) -> tuple[int, int]:
    """Signals + trades + fills all seeded. Returns (trade_count, fill_count)."""
    from ai_hedge_fund.paper.seed import seed_paper_fills_from_csv, seed_paper_trades_from_csv

    trades = seed_paper_trades_from_csv(db_session, paper_trades_csv_path)
    fills = seed_paper_fills_from_csv(db_session, paper_fills_csv_path)
    return trades, fills
