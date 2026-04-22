"""Plan 07-01 Task 1: EpisodicMemory SQLAlchemy model tests.

Proves the append-only contract (duplicates allowed by design — NO
UniqueConstraint unlike PortfolioPosition), the hot-path column set,
composite index registration, JSONB payload round-trip, and nullable
analysis/outcome fields.

Fixtures: memory_db_session (alias for the project-wide db_session;
bound to an in-memory SQLite engine with Base.metadata.create_all).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory


_AS_OF_JAN10 = datetime(2026, 1, 10, tzinfo=UTC)
_AS_OF_FEB01 = datetime(2026, 2, 1, tzinfo=UTC)
_AS_OF_MAR15 = datetime(2026, 3, 15, tzinfo=UTC)


def test_episodic_round_trip(memory_db_session: Session) -> None:
    """Test 1: Insert + read back an analysis row with all hot-path fields."""
    row = EpisodicMemory(
        ticker="AAPL",
        sector="Technology",
        record_type="analysis",
        signal_direction="long",
        confidence=70,
        payload={"thesis": {"confidence": 70}},
        as_of_date=_AS_OF_JAN10,
    )
    memory_db_session.add(row)
    memory_db_session.commit()

    read_back = memory_db_session.query(EpisodicMemory).filter_by(ticker="AAPL").one()
    assert read_back.ticker == "AAPL"
    assert read_back.sector == "Technology"
    assert read_back.record_type == "analysis"
    assert read_back.signal_direction == "long"
    assert read_back.confidence == 70
    assert read_back.payload == {"thesis": {"confidence": 70}}


def test_append_only_duplicates_allowed(memory_db_session: Session) -> None:
    """Test 2: Two analysis rows for the same (ticker, as_of_date) BOTH succeed.

    Contrast with PortfolioPosition which has UniqueConstraint("ticker",
    "as_of_date"). Episodic memory deliberately lifts that guard per
    07-PATTERNS.md — duplicate analyses are a valid operational signal.
    """
    row1 = EpisodicMemory(
        ticker="AAPL",
        sector="Technology",
        record_type="analysis",
        signal_direction="long",
        confidence=70,
        payload={"schema_version": 1},
        as_of_date=_AS_OF_JAN10,
    )
    row2 = EpisodicMemory(
        ticker="AAPL",
        sector="Technology",
        record_type="analysis",
        signal_direction="long",
        confidence=72,
        payload={"schema_version": 1},
        as_of_date=_AS_OF_JAN10,
    )
    memory_db_session.add_all([row1, row2])
    memory_db_session.commit()

    hits = memory_db_session.query(EpisodicMemory).filter_by(ticker="AAPL").all()
    assert len(hits) == 2  # no UniqueConstraint — duplicates by design


def test_episodic_has_all_required_columns() -> None:
    """Test 3: The table has all hot-path columns + audit fields + timestamps."""
    cols = {c.name for c in EpisodicMemory.__table__.columns}
    required = {
        "id",
        "ticker",
        "sector",
        "record_type",
        "signal_direction",
        "confidence",
        "outcome_pct",
        "linked_analysis_id",
        "policy_sha",
        "payload",
        "as_of_date",
        "observed_date",
    }
    missing = required - cols
    assert not missing, f"EpisodicMemory is missing columns: {missing}"
    # Sanity: at least 12 columns.
    assert len(cols) >= 12


def test_payload_round_trips_nested_dict(memory_db_session: Session) -> None:
    """Test 4: JSONB/JSON payload preserves nested dicts on round-trip."""
    payload = {
        "nested": {"key": "value"},
        "list": [1, 2, 3],
        "number": 42,
        "schema_version": 1,
    }
    row = EpisodicMemory(
        ticker="MSFT",
        sector="Technology",
        record_type="analysis",
        signal_direction="long",
        confidence=60,
        payload=payload,
        as_of_date=_AS_OF_FEB01,
    )
    memory_db_session.add(row)
    memory_db_session.commit()

    read_back = memory_db_session.query(EpisodicMemory).filter_by(ticker="MSFT").one()
    assert read_back.payload["nested"]["key"] == "value"
    assert read_back.payload["list"] == [1, 2, 3]
    assert read_back.payload["number"] == 42


def test_outcome_and_linked_fields_are_nullable(memory_db_session: Session) -> None:
    """Test 5: analysis rows omit outcome_pct + linked_analysis_id (None)."""
    analysis = EpisodicMemory(
        ticker="AAPL",
        sector="Technology",
        record_type="analysis",
        signal_direction="long",
        confidence=70,
        payload={"schema_version": 1},
        as_of_date=_AS_OF_JAN10,
    )
    memory_db_session.add(analysis)
    memory_db_session.commit()
    memory_db_session.refresh(analysis)

    assert analysis.outcome_pct is None
    assert analysis.linked_analysis_id is None

    # Outcome row references the analysis row's id.
    outcome = EpisodicMemory(
        ticker="AAPL",
        sector="Technology",
        record_type="outcome",
        signal_direction="long",
        confidence=70,
        outcome_pct=4.2,
        linked_analysis_id=analysis.id,
        payload={"schema_version": 1},
        as_of_date=_AS_OF_MAR15,
    )
    memory_db_session.add(outcome)
    memory_db_session.commit()

    read_back = memory_db_session.query(EpisodicMemory).filter_by(record_type="outcome").one()
    assert read_back.outcome_pct == 4.2
    assert read_back.linked_analysis_id == analysis.id


def test_composite_indexes_registered() -> None:
    """Test 6: ix_episodic_ticker_asof + ix_episodic_sector_asof exist."""
    names = {idx.name for idx in EpisodicMemory.__table__.indexes}
    assert "ix_episodic_ticker_asof" in names
    assert "ix_episodic_sector_asof" in names
