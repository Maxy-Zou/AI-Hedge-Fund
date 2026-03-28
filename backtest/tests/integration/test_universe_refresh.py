"""Integration tests for the full universe refresh cycle.

These tests use a real PostgreSQL container (testcontainers).
Run with: uv run pytest tests/integration/ -v -m integration

Excluded from fast unit test runs by default:
    uv run pytest tests/unit/ -v          # fast, no Docker
    uv run pytest tests/ -m integration   # integration only
    uv run pytest tests/                  # full suite
"""
from __future__ import annotations

import contextlib
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from fund_backtest.config import UniverseSettings
from fund_backtest.db.models import UniverseSnapshot, UniverseTicker
from fund_backtest.universe.builder import UniverseBuilder
from fund_backtest.universe.types import RefreshResult

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

# Three tickers with different market cap scenarios:
#   MTSI  — $5B   — in range ($2B-$10B) -> should be active
#   GRBK  — $1B   — below $2B minimum -> should be excluded
#   NVDA  — $500B — above $10B maximum -> should be excluded
TEST_TICKERS = [
    ("MTSI", "Information Technology", 5_000_000_000),
    ("GRBK", "Consumer Discretionary", 1_000_000_000),
    ("NVDA", "Information Technology", 500_000_000_000),
]


def _make_mock_wiki_df(tickers: list[tuple[str, str, int | None]]) -> pd.DataFrame:
    """Build a mock Wikipedia DataFrame with expected columns before rename.

    Args:
        tickers: List of (ticker, sector, market_cap_dollars) tuples.
    """
    return pd.DataFrame(
        {
            "Symbol": [t[0] for t in tickers],
            "Security": [f"{t[0]} Inc." for t in tickers],
            "GICS Sector": [t[1] for t in tickers],
            "GICS Sub-Industry": ["Software" for _ in tickers],
        }
    )


def _make_mock_yf_ticker(market_cap_dollars: int | None, sector: str | None) -> MagicMock:
    mock = MagicMock()
    mock.info = {
        "marketCap": market_cap_dollars,
        "sector": sector,
    }
    return mock


@contextlib.contextmanager
def _patch_external(tickers: list[tuple[str, str, int | None]]):
    """Patch Wikipedia and yfinance with controlled test data.

    Args:
        tickers: List of (ticker, sector, market_cap_dollars) tuples.
                 market_cap_dollars=None means unavailable cap.
    """
    wiki_df = _make_mock_wiki_df(tickers)

    def yf_ticker_factory(ticker: str) -> MagicMock:
        match = next((t for t in tickers if t[0] == ticker), None)
        if match:
            return _make_mock_yf_ticker(match[2], match[1])
        return _make_mock_yf_ticker(None, None)

    with patch("fund_backtest.universe.seeder.pd.read_html", return_value=[wiki_df]):
        with patch("fund_backtest.universe.enricher.yf.Ticker", side_effect=yf_ticker_factory):
            yield


@pytest.fixture
def universe_settings() -> UniverseSettings:
    """Universe settings with tight bounds and no yfinance delay for fast tests."""
    return UniverseSettings(
        market_cap_min_cents=200_000_000_000,    # $2B
        market_cap_max_cents=1_000_000_000_000,  # $10B
        seed_url="https://example.com/fake",
        yfinance_delay_secs=0.0,                 # no delay in tests
    )


# ---------------------------------------------------------------------------
# Integration test class
# ---------------------------------------------------------------------------


class TestUniverseRefreshIntegration:
    """Full refresh cycle tests against real PostgreSQL (via testcontainers)."""

    def test_refresh_returns_refresh_result(self, db_session, universe_settings):
        """refresh() returns a RefreshResult instance."""
        with _patch_external(TEST_TICKERS):
            builder = UniverseBuilder(session=db_session, settings=universe_settings)
            result = builder.refresh()

        assert isinstance(result, RefreshResult)

    def test_refresh_inserts_only_midcap_tickers(self, db_session, universe_settings):
        """Only MTSI ($5B, in range) should be active; GRBK ($1B) and NVDA ($500B) excluded."""
        with _patch_external(TEST_TICKERS):
            builder = UniverseBuilder(session=db_session, settings=universe_settings)
            result = builder.refresh()

        assert result.active_count == 1

        active = db_session.query(UniverseTicker).filter_by(is_active=True).all()
        assert len(active) == 1
        assert active[0].ticker == "MTSI"

        # Out-of-range tickers must not appear in universe_tickers at all
        all_tickers = {row.ticker for row in db_session.query(UniverseTicker).all()}
        assert "GRBK" not in all_tickers, "GRBK ($1B) below range should not be inserted"
        assert "NVDA" not in all_tickers, "NVDA ($500B) above range should not be inserted"

    def test_refresh_creates_snapshot_row(self, db_session, universe_settings):
        """Each refresh appends exactly one UniverseSnapshot row."""
        # Count snapshots before
        before_count = db_session.query(UniverseSnapshot).count()

        with _patch_external(TEST_TICKERS):
            builder = UniverseBuilder(session=db_session, settings=universe_settings)
            builder.refresh()

        after_count = db_session.query(UniverseSnapshot).count()
        assert after_count == before_count + 1

        snap = (
            db_session.query(UniverseSnapshot)
            .order_by(UniverseSnapshot.snapshot_date.desc())
            .first()
        )
        assert snap is not None
        assert snap.active_count == 1
        assert snap.snapshot_date == date.today()
        assert "Information Technology" in snap.sector_breakdown

    def test_refresh_twice_appends_snapshot_not_overwrites(self, db_session, universe_settings):
        """Running refresh twice produces two new snapshot rows (append-only history)."""
        before_count = db_session.query(UniverseSnapshot).count()

        with _patch_external(TEST_TICKERS):
            builder = UniverseBuilder(session=db_session, settings=universe_settings)
            builder.refresh()
            builder.refresh()

        after_count = db_session.query(UniverseSnapshot).count()
        assert after_count == before_count + 2, (
            f"Expected 2 new snapshot rows, got {after_count - before_count}"
        )

    def test_deactivation_preserves_historical_row(self, db_session, universe_settings):
        """A ticker that was active then exits mid-cap range is marked inactive — not deleted."""
        # First refresh: MTSI is in range ($5B)
        with _patch_external(TEST_TICKERS):
            builder = UniverseBuilder(session=db_session, settings=universe_settings)
            builder.refresh()

        # Confirm MTSI was inserted and is active
        mtsi_before = db_session.query(UniverseTicker).filter_by(ticker="MTSI").first()
        assert mtsi_before is not None
        assert mtsi_before.is_active is True

        # Second refresh: MTSI now has a $50B cap (above the $10B max)
        tickers_v2 = [("MTSI", "Information Technology", 50_000_000_000)]
        with _patch_external(tickers_v2):
            builder.refresh()

        mtsi_after = db_session.query(UniverseTicker).filter_by(ticker="MTSI").first()
        assert mtsi_after is not None, "MTSI row must still exist (never delete)"
        assert mtsi_after.is_active is False, "MTSI should be inactive after exiting range"
        assert mtsi_after.deactivation_reason is not None, (
            "deactivation_reason must be set when marking ticker inactive"
        )

    def test_market_cap_stored_as_cents(self, db_session, universe_settings):
        """Market cap is stored as cents: $5B = 500_000_000_000 cents."""
        with _patch_external(TEST_TICKERS):
            builder = UniverseBuilder(session=db_session, settings=universe_settings)
            builder.refresh()

        mtsi = db_session.query(UniverseTicker).filter_by(ticker="MTSI").first()
        assert mtsi is not None
        # $5B * 100 = 500_000_000_000 cents
        assert mtsi.market_cap_cents == 500_000_000_000, (
            f"Expected 500_000_000_000 cents for $5B, got {mtsi.market_cap_cents}"
        )

    def test_gics_sector_stored_for_active_tickers(self, db_session, universe_settings):
        """Active tickers have gics_sector populated (DATA-07)."""
        with _patch_external(TEST_TICKERS):
            builder = UniverseBuilder(session=db_session, settings=universe_settings)
            builder.refresh()

        active = db_session.query(UniverseTicker).filter_by(is_active=True).all()
        assert len(active) > 0, "Expected at least one active ticker"
        for ticker in active:
            assert ticker.gics_sector is not None, (
                f"{ticker.ticker} missing gics_sector — DATA-07 requires sector for all active tickers"
            )
            assert ticker.sector_source in (
                "wikipedia_sp400",
                "yfinance",
            ), f"{ticker.ticker} has unexpected sector_source: {ticker.sector_source}"
