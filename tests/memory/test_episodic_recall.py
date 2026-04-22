"""Plan 07-01 Task 2: EpisodicHit + seed_episodic_from_csv + query_episodic tests.

Covers the MEM-01 read path contract — including the Pitfall-2 temporal
leakage regression (FUTUREX row at 2099-01-01 must NEVER be returned by
a query with an earlier target).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ai_hedge_fund.memory import (
    EpisodicHit,
    query_episodic,
    seed_episodic_from_csv,
)


def test_episodic_hit_validates_schema() -> None:
    """Test 1: EpisodicHit accepts a well-formed payload; rejects extras."""
    data = {
        "id": 1,
        "ticker": "AAPL",
        "sector": "Technology",
        "record_type": "analysis",
        "as_of_date": "2026-01-10T00:00:00+00:00",
        "signal_direction": "long",
        "confidence": 70,
        "outcome_pct": None,
        "linked_analysis_id": None,
        "policy_sha": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "payload": {"nested": {"key": "value"}},
    }
    hit = EpisodicHit(**data)
    assert hit.ticker == "AAPL"
    assert hit.confidence == 70
    assert hit.record_type == "analysis"

    # extra="forbid" — unknown key rejected (Shared Pattern B)
    bad = dict(data)
    bad["unknown_field"] = "nope"
    with pytest.raises(ValidationError):
        EpisodicHit(**bad)


def test_seed_episodic_from_csv_loads_10_rows(
    memory_db_session: Session, sample_episodic_csv_path: Path
) -> None:
    """Test 2: CSV seeder inserts exactly 10 rows; blank outcome_pct -> None."""
    from ai_hedge_fund.db.models import EpisodicMemory

    count = seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    assert count == 10

    rows = memory_db_session.query(EpisodicMemory).all()
    assert len(rows) == 10

    # Analysis rows: outcome_pct is None, not 0.0.
    analysis_rows = [r for r in rows if r.record_type == "analysis"]
    for r in analysis_rows:
        assert r.outcome_pct is None, (
            f"Blank CSV outcome_pct must round-trip as None; got {r.outcome_pct!r}"
        )


def test_recall_by_ticker_returns_ordered_hits(
    memory_db_session: Session, sample_episodic_csv_path: Path
) -> None:
    """Test 3: Recall by ticker returns all AAPL hits in as_of_date DESC order."""
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    hits = query_episodic(
        memory_db_session,
        ticker="AAPL",
        as_of_date="2026-06-01",
        limit=10,
    )
    assert len(hits) >= 2  # AAPL analysis (2026-01-10) + AAPL outcome (2026-03-15)
    for h in hits:
        assert h.ticker == "AAPL"
    # DESC order on as_of_date
    dates = [h.as_of_date for h in hits]
    assert dates == sorted(dates, reverse=True)


def test_recall_excludes_future_rows(
    memory_db_session: Session, sample_episodic_csv_path: Path
) -> None:
    """Test 4 (Pitfall-2 regression): FUTUREX row (2099-01-01) MUST NOT leak."""
    count = seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    assert count == 10
    hits = query_episodic(
        memory_db_session,
        ticker="FUTUREX",
        as_of_date="2030-01-01",
        limit=10,
    )
    assert hits == []  # future-dated FUTUREX row MUST NOT leak into an earlier query


def test_recall_by_sector_returns_multi_ticker_hits(
    memory_db_session: Session, sample_episodic_csv_path: Path
) -> None:
    """Test 5: Recall by sector returns Technology rows across AAPL + MSFT."""
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    hits = query_episodic(
        memory_db_session,
        sector="Technology",
        as_of_date="2026-06-01",
        limit=10,
    )
    # Seed has AAPL analysis, AAPL outcome, MSFT analysis, MSFT outcome in Tech;
    # FUTUREX is also Technology but dated 2099 and must be excluded.
    assert len(hits) >= 3
    for h in hits:
        assert h.sector == "Technology"
    assert not any(h.ticker == "FUTUREX" for h in hits)


def test_recall_limit_is_enforced(
    memory_db_session: Session, sample_episodic_csv_path: Path
) -> None:
    """Test 6: limit=1 returns exactly one row."""
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    hits = query_episodic(
        memory_db_session,
        ticker="AAPL",
        as_of_date="2026-06-01",
        limit=1,
    )
    assert len(hits) == 1


def test_recall_requires_ticker_or_sector(memory_db_session: Session) -> None:
    """Test 7: Pitfall-8 DoS guard — neither ticker nor sector raises ValueError."""
    with pytest.raises(ValueError):
        query_episodic(
            memory_db_session,
            as_of_date="2026-06-01",
            limit=10,
        )


def test_policy_sha_round_trips(memory_db_session: Session, sample_episodic_csv_path: Path) -> None:
    """Test 8: policy_sha from CSV survives round-trip to EpisodicHit."""
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    hits = query_episodic(
        memory_db_session,
        ticker="AAPL",
        as_of_date="2026-06-01",
        limit=10,
    )
    # Oldest hit (AAPL analysis on 2026-01-10) — Phase-6 audit linkage.
    analysis_hits = [h for h in hits if h.record_type == "analysis"]
    assert analysis_hits, "Expected at least one AAPL analysis row"
    oldest_analysis = analysis_hits[-1]
    assert oldest_analysis.policy_sha is not None
    assert oldest_analysis.policy_sha.startswith("e3b0c4")
