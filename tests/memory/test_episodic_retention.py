"""Plan 07-01 Task 3: 90-day retention sweep tests.

Covers idempotent deletion of rows older than ``retention_days`` via an
ORM-only ``delete()`` statement. Seed CSV has rows dated 2026-01-10 ..
2026-04-01 plus one FUTUREX row at 2099-01-01.

With today=2026-05-01 and retention_days=90, cutoff is 2026-01-31.
Rows strictly older than the cutoff (as_of_date < cutoff):
    - AAPL 2026-01-10 (analysis)
    - JPM  2026-01-20 (analysis)
Total = 2 rows deleted.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.memory.episodic import seed_episodic_from_csv
from ai_hedge_fund.scripts.purge_expired_episodic import purge_expired


def test_purge_respects_cutoff(memory_db_session: Session, sample_episodic_csv_path: Path) -> None:
    """Test 1: purge deletes rows with as_of_date < today - retention_days."""
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    deleted = purge_expired(memory_db_session, retention_days=90, today=date(2026, 5, 1))
    assert deleted == 2
    remaining = memory_db_session.query(EpisodicMemory).count()
    assert remaining == 10 - 2


def test_purge_preserves_in_window_rows(
    memory_db_session: Session, sample_episodic_csv_path: Path
) -> None:
    """Test 2: Rows with as_of_date >= cutoff survive; older rows are gone."""
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    purge_expired(memory_db_session, retention_days=90, today=date(2026, 5, 1))

    # AAPL analysis (2026-01-10) should be gone.
    gone = (
        memory_db_session.query(EpisodicMemory)
        .filter_by(ticker="AAPL", record_type="analysis")
        .count()
    )
    assert gone == 0

    # AAPL outcome (2026-03-15) should survive (>= 2026-01-31 cutoff).
    survived = (
        memory_db_session.query(EpisodicMemory)
        .filter_by(ticker="AAPL", record_type="outcome")
        .count()
    )
    assert survived == 1

    # FUTUREX 2099-01-01 must still be there.
    future = memory_db_session.query(EpisodicMemory).filter_by(ticker="FUTUREX").count()
    assert future == 1


def test_purge_is_idempotent(memory_db_session: Session, sample_episodic_csv_path: Path) -> None:
    """Test 3: Running purge twice returns 0 on the second call."""
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    first = purge_expired(memory_db_session, retention_days=90, today=date(2026, 5, 1))
    second = purge_expired(memory_db_session, retention_days=90, today=date(2026, 5, 1))
    assert first == 2
    assert second == 0


def test_purge_retention_zero_purges_everything_before_today(
    memory_db_session: Session, sample_episodic_csv_path: Path
) -> None:
    """Test 4: retention_days=0 with today=2099-01-02 keeps only 2099-01-01 row."""
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    # cutoff = today = 2099-01-02; rows < 2099-01-02 are purged.
    # Only the FUTUREX row dated 2099-01-01 survives — wait, 2099-01-01 < 2099-01-02.
    # So the FUTUREX row is ALSO purged. Only rows >= 2099-01-02 survive.
    deleted = purge_expired(memory_db_session, retention_days=0, today=date(2099, 1, 2))
    assert deleted == 10  # all 10 rows are strictly before 2099-01-02
    remaining = memory_db_session.query(EpisodicMemory).count()
    assert remaining == 0


def test_purge_rejects_negative_retention(memory_db_session: Session) -> None:
    """Test 5 (input validation — CLAUDE.md): negative retention is rejected."""
    with pytest.raises(ValueError):
        purge_expired(memory_db_session, retention_days=-1)


def test_purge_defaults_are_usable(memory_db_session: Session) -> None:
    """Test 5b: purge_expired(session) uses default retention_days=90 and today=today()."""
    # Empty DB — purge is a no-op but signature must accept bare-session call.
    deleted = purge_expired(memory_db_session)
    assert deleted == 0
