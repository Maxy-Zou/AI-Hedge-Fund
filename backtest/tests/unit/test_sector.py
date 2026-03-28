"""Unit tests for yfinance enricher and UniverseBuilder.

Tests cover:
- fetch_ticker_info: market cap cents conversion, None handling
- build_universe_entry: sector source precedence (Wikipedia > yfinance > None)
- UniverseBuilder._upsert_ticker: insert new, update existing
- UniverseBuilder._deactivate_ticker: soft-delete (is_active=False, no row delete)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from fund_backtest.db.base import Base
from fund_backtest.db.models import UniverseTicker
from fund_backtest.universe.builder import UniverseBuilder
from fund_backtest.universe.enricher import build_universe_entry, fetch_ticker_info
from fund_backtest.universe.types import SeedRow, UniverseEntry


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def make_mock_ticker(market_cap: int | None, sector: str | None) -> MagicMock:
    """Create a mock yfinance Ticker with specific info values."""
    mock = MagicMock()
    mock.info = {"marketCap": market_cap, "sector": sector}
    return mock


@pytest.fixture
def sqlite_session() -> Session:
    """In-memory SQLite session for builder unit tests.

    Creates only the universe_tickers table (not universe_snapshots which uses
    PostgreSQL-only JSONB). Builder unit tests only exercise _upsert_ticker and
    _deactivate_ticker which only touch universe_tickers.
    """
    engine = create_engine("sqlite:///:memory:")
    # Create only universe_tickers — universe_snapshots uses JSONB (PostgreSQL-only)
    UniverseTicker.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    yield session
    session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# fetch_ticker_info tests
# ---------------------------------------------------------------------------


def test_enricher_converts_market_cap_to_cents() -> None:
    """fetch_ticker_info converts marketCap $5B to 500_000_000_000 cents."""
    with patch("fund_backtest.universe.enricher.yf.Ticker") as mock_yf:
        mock_yf.return_value = make_mock_ticker(5_000_000_000, "Technology")
        result = fetch_ticker_info("MTSI")
    assert result["market_cap_cents"] == 500_000_000_000


def test_enricher_none_market_cap_returns_none() -> None:
    """fetch_ticker_info returns market_cap_cents=None when yfinance has no data."""
    with patch("fund_backtest.universe.enricher.yf.Ticker") as mock_yf:
        mock_yf.return_value = make_mock_ticker(None, "Technology")
        result = fetch_ticker_info("MTSI")
    assert result["market_cap_cents"] is None


# ---------------------------------------------------------------------------
# build_universe_entry sector precedence tests
# ---------------------------------------------------------------------------


def test_sector_precedence_wikipedia_wins() -> None:
    """Wikipedia sector takes precedence over yfinance sector."""
    seed_row = SeedRow(
        ticker="MTSI",
        name="MACOM Technology Solutions",
        gics_sector="Information Technology",
        gics_sub_industry="Semiconductors",
    )
    yf_data = {"market_cap_cents": 500_000_000_000, "yfinance_sector": "Technology"}

    entry = build_universe_entry(seed_row, yf_data)

    assert entry.gics_sector == "Information Technology"
    assert entry.sector_source == "wikipedia_sp400"


def test_sector_precedence_yfinance_fallback() -> None:
    """yfinance sector used when Wikipedia sector is None."""
    seed_row = SeedRow(
        ticker="MTSI",
        name="MACOM Technology Solutions",
        gics_sector=None,
        gics_sub_industry=None,
    )
    yf_data = {"market_cap_cents": 500_000_000_000, "yfinance_sector": "Industrials"}

    entry = build_universe_entry(seed_row, yf_data)

    assert entry.gics_sector == "Industrials"
    assert entry.sector_source == "yfinance"


def test_sector_precedence_both_none() -> None:
    """build_universe_entry handles both sector sources being None gracefully."""
    seed_row = SeedRow(
        ticker="MTSI",
        name="MACOM Technology Solutions",
        gics_sector=None,
        gics_sub_industry=None,
    )
    yf_data = {"market_cap_cents": None, "yfinance_sector": None}

    entry = build_universe_entry(seed_row, yf_data)

    assert entry.gics_sector is None
    assert entry.sector_source is None


# ---------------------------------------------------------------------------
# UniverseBuilder._upsert_ticker tests
# ---------------------------------------------------------------------------


def _make_entry(ticker: str = "MTSI", market_cap_cents: int = 500_000_000_000) -> UniverseEntry:
    """Factory for test UniverseEntry instances."""
    return UniverseEntry(
        ticker=ticker,
        name="MACOM Technology Solutions",
        gics_sector="Information Technology",
        gics_sub_industry="Semiconductors",
        market_cap_cents=market_cap_cents,
        sector_source="wikipedia_sp400",
    )


def test_builder_upsert_new_ticker(sqlite_session: Session) -> None:
    """_upsert_ticker inserts a new row with is_active=True and returns True."""
    builder = UniverseBuilder(session=sqlite_session)
    entry = _make_entry("MTSI")

    is_new = builder._upsert_ticker(entry)
    sqlite_session.flush()

    assert is_new is True
    row = sqlite_session.query(UniverseTicker).filter_by(ticker="MTSI").first()
    assert row is not None
    assert row.is_active is True
    assert row.market_cap_cents == 500_000_000_000


def test_builder_upsert_existing_ticker_updates(sqlite_session: Session) -> None:
    """_upsert_ticker updates market_cap_cents on existing ticker without creating a duplicate."""
    builder = UniverseBuilder(session=sqlite_session)

    # Insert initial row
    first_entry = _make_entry("MTSI", market_cap_cents=400_000_000_000)
    builder._upsert_ticker(first_entry)
    sqlite_session.flush()

    # Upsert again with updated cap
    updated_entry = _make_entry("MTSI", market_cap_cents=600_000_000_000)
    is_new = builder._upsert_ticker(updated_entry)
    sqlite_session.flush()

    assert is_new is False
    rows = sqlite_session.query(UniverseTicker).filter_by(ticker="MTSI").all()
    assert len(rows) == 1  # No duplicate created
    assert rows[0].market_cap_cents == 600_000_000_000


# ---------------------------------------------------------------------------
# UniverseBuilder._deactivate_ticker tests
# ---------------------------------------------------------------------------


def test_enrich_universe_success(sqlite_session: Session) -> None:
    """enrich_universe returns a list of UniverseEntry objects with mocked yfinance."""
    from fund_backtest.universe.enricher import enrich_universe

    seed_rows = [
        SeedRow(
            ticker="MTSI",
            name="MACOM Technology Solutions",
            gics_sector="Information Technology",
            gics_sub_industry="Semiconductors",
        )
    ]
    with patch("fund_backtest.universe.enricher.yf.Ticker") as mock_yf:
        mock_yf.return_value = make_mock_ticker(5_000_000_000, "Technology")
        with patch("fund_backtest.universe.enricher.time.sleep"):  # skip delay
            entries = enrich_universe(seed_rows, delay_secs=0.0)

    assert len(entries) == 1
    assert entries[0].ticker == "MTSI"
    assert entries[0].market_cap_cents == 500_000_000_000


def test_enrich_universe_graceful_degradation() -> None:
    """enrich_universe continues when yfinance raises an exception for a ticker."""
    from fund_backtest.universe.enricher import enrich_universe

    seed_rows = [
        SeedRow(
            ticker="MTSI",
            name="MACOM Technology Solutions",
            gics_sector="Information Technology",
            gics_sub_industry="Semiconductors",
        )
    ]
    with patch("fund_backtest.universe.enricher.yf.Ticker") as mock_yf:
        mock_yf.side_effect = RuntimeError("yfinance unavailable")
        with patch("fund_backtest.universe.enricher.time.sleep"):
            entries = enrich_universe(seed_rows, delay_secs=0.0)

    assert len(entries) == 1
    assert entries[0].market_cap_cents is None


def test_builder_deactivate_ticker(sqlite_session: Session) -> None:
    """_deactivate_ticker sets is_active=False and sets deactivation_reason, never deletes."""
    builder = UniverseBuilder(session=sqlite_session)

    # Insert initial row
    entry = _make_entry("MTSI")
    builder._upsert_ticker(entry)
    sqlite_session.flush()

    # Deactivate
    builder._deactivate_ticker("MTSI", reason="exited_midcap_range")
    sqlite_session.flush()

    # Row still exists — not deleted
    row = sqlite_session.query(UniverseTicker).filter_by(ticker="MTSI").first()
    assert row is not None
    assert row.is_active is False
    assert row.deactivation_reason == "exited_midcap_range"
