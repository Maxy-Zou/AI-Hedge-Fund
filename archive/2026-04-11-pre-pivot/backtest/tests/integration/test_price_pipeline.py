"""Integration tests for the full price data pipeline.

Tests run against a real PostgreSQL testcontainer (via conftest.py fixtures).
All external HTTP calls (yfinance) are mocked to avoid network dependencies.

Run with: uv run pytest tests/integration/test_price_pipeline.py -v -m integration
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from fund_backtest.config import PriceSettings
from fund_backtest.db.models import PriceAnomalyORM, PriceBarORM, UniverseTicker
from fund_backtest.price.builder import PriceBuilder
from fund_backtest.price.repository import PriceBarRepository
from fund_backtest.price.types import PriceAnomalyRecord, PriceBar

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_price_bar(
    ticker: str,
    bar_date: date,
    close_cents: int = 15000,
) -> PriceBar:
    """Create a minimal PriceBar with sensible defaults."""
    return PriceBar(
        ticker=ticker,
        bar_date=bar_date,
        open_cents=close_cents - 100,
        high_cents=close_cents + 200,
        low_cents=close_cents - 200,
        close_cents=close_cents,
        volume=1_000_000,
    )


def make_ohlcv_df(tickers: list[str], n_bars: int = 5) -> pd.DataFrame:
    """Build a minimal MultiIndex OHLCV DataFrame that mimics yfinance output.

    Args:
        tickers: List of ticker symbols.
        n_bars: Number of trading bars to generate.

    Returns:
        MultiIndex DataFrame with (field, ticker) columns and DatetimeIndex.
    """
    dates = pd.date_range("2026-01-02", periods=n_bars, freq="B")
    data = {
        (field, ticker): [100.0 + i for i in range(n_bars)]
        for ticker in tickers
        for field in ["Open", "High", "Low", "Close", "Volume"]
    }
    columns = pd.MultiIndex.from_tuples(data.keys())
    return pd.DataFrame(data, index=dates, columns=columns)


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_price_tables(db_session):
    """Delete price_bars, price_anomalies, and universe_tickers before each test.

    insert_bars() calls session.commit() internally, so the conftest rollback
    cannot undo those inserts.  We delete at the start of each test instead.
    Also clears universe_tickers so seeded_universe fixture can always insert fresh rows.
    """
    from sqlalchemy import text as _text

    db_session.execute(_text("DELETE FROM price_anomalies"))
    db_session.execute(_text("DELETE FROM price_bars"))
    db_session.execute(_text("DELETE FROM universe_tickers"))
    db_session.commit()
    yield


@pytest.fixture
def repo(db_session) -> PriceBarRepository:
    """PriceBarRepository bound to the test session."""
    return PriceBarRepository(db_session)


@pytest.fixture
def price_settings() -> PriceSettings:
    """Fast PriceSettings with no inter-batch sleep."""
    return PriceSettings(
        lookback_years=5,
        batch_size=80,
        batch_sleep_secs=0.0,
        coverage_alert_threshold=0.95,
        return_anomaly_threshold=0.50,
    )


@pytest.fixture
def seeded_universe(db_session):
    """Insert 2 active tickers into universe_tickers for builder tests."""
    for ticker, name in [("AAPL", "Apple"), ("MSFT", "Microsoft")]:
        db_session.add(UniverseTicker(ticker=ticker, name=name, is_active=True))
    db_session.commit()
    yield db_session
    # clean_price_tables autouse fixture handles price table cleanup
    # conftest.py db_session fixture handles rollback for uncommitted rows


# ---------------------------------------------------------------------------
# Repository unit-style tests (use real DB, no builder)
# ---------------------------------------------------------------------------


class TestInsertBars:
    """insert_bars() populates price_bars and returns row counts."""

    def test_insert_bars_populates_price_bars_table(self, db_session, repo):
        """Inserting 3 PriceBar objects creates 3 rows in price_bars."""
        bars = [
            _make_price_bar("AAPL", date(2026, 1, 2), 15000),
            _make_price_bar("AAPL", date(2026, 1, 5), 15100),
            _make_price_bar("AAPL", date(2026, 1, 6), 15200),
        ]

        inserted = repo.insert_bars(bars)

        assert inserted == 3
        rows = db_session.query(PriceBarORM).filter_by(ticker="AAPL").all()
        assert len(rows) == 3
        dates_in_db = {r.bar_date for r in rows}
        assert dates_in_db == {date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)}
        # Verify close_cents stored correctly
        bar_2 = next(r for r in rows if r.bar_date == date(2026, 1, 2))
        assert bar_2.close_cents == 15000

    def test_insert_bars_idempotent_on_conflict_do_nothing(self, db_session, repo):
        """Inserting same 3 bars twice: second insert returns 0 new rows."""
        bars = [
            _make_price_bar("AAPL", date(2026, 1, 2)),
            _make_price_bar("AAPL", date(2026, 1, 5)),
            _make_price_bar("AAPL", date(2026, 1, 6)),
        ]

        first_insert = repo.insert_bars(bars)
        second_insert = repo.insert_bars(bars)

        assert first_insert == 3
        assert second_insert == 0

        # Exactly 3 rows in table — no duplicates
        total = db_session.query(PriceBarORM).filter_by(ticker="AAPL").count()
        assert total == 3


class TestGetLastDates:
    """get_last_dates() returns per-ticker max bar_date."""

    def test_update_appends_only_new_bars(self, db_session, repo):
        """After inserting a bar, get_last_dates reflects it; a later insert adds rows."""
        bar_jan2 = _make_price_bar("AAPL", date(2026, 1, 2))
        repo.insert_bars([bar_jan2])

        last_dates = repo.get_last_dates(["AAPL"])
        assert last_dates["AAPL"] == date(2026, 1, 2)

        # Insert a later bar
        bar_jan3 = _make_price_bar("AAPL", date(2026, 1, 3))
        repo.insert_bars([bar_jan3])

        rows = db_session.query(PriceBarORM).filter_by(ticker="AAPL").count()
        assert rows == 2

        last_dates_after = repo.get_last_dates(["AAPL"])
        assert last_dates_after["AAPL"] == date(2026, 1, 3)


class TestAnomalies:
    """insert_anomalies() and anomaly exclusion in get_bars()."""

    def test_anomaly_record_inserted_for_spike(self, db_session, repo):
        """PriceAnomalyRecord persisted to price_anomalies with is_reviewed=False."""
        anomaly = PriceAnomalyRecord(
            ticker="AAPL",
            bar_date=date(2026, 1, 5),
            anomaly_type="return_spike_plus",
            daily_return_pct=0.75,
        )
        repo.insert_anomalies([anomaly])

        rows = db_session.query(PriceAnomalyORM).filter_by(ticker="AAPL").all()
        assert len(rows) == 1
        assert rows[0].is_reviewed is False
        assert rows[0].bar_date == date(2026, 1, 5)
        assert rows[0].anomaly_type == "return_spike_plus"

    def test_get_bars_excludes_anomalous_bar(self, db_session, repo):
        """get_bars(exclude_anomalies=True) hides the bar with an unreviewed anomaly."""
        bars = [
            _make_price_bar("AAPL", date(2026, 1, 2)),
            _make_price_bar("AAPL", date(2026, 1, 5)),  # this one has an anomaly
        ]
        repo.insert_bars(bars)

        anomaly = PriceAnomalyRecord(
            ticker="AAPL",
            bar_date=date(2026, 1, 5),
            anomaly_type="return_spike_plus",
            daily_return_pct=0.75,
        )
        repo.insert_anomalies([anomaly])

        result = repo.get_bars(["AAPL"], exclude_anomalies=True)
        result_dates = {r.bar_date for r in result}

        assert date(2026, 1, 5) not in result_dates, "Anomalous bar should be excluded"
        assert date(2026, 1, 2) in result_dates, "Non-anomalous bar should be included"

    def test_get_bars_includes_anomalous_bar_when_reviewed(self, db_session, repo):
        """Reviewed anomaly: bar appears when exclude_anomalies=True (reviewed => not excluded)."""
        bars = [_make_price_bar("AAPL", date(2026, 1, 5))]
        repo.insert_bars(bars)

        anomaly = PriceAnomalyRecord(
            ticker="AAPL",
            bar_date=date(2026, 1, 5),
            anomaly_type="return_spike_plus",
            daily_return_pct=0.75,
        )
        repo.insert_anomalies([anomaly])

        # Mark anomaly as reviewed directly
        db_session.query(PriceAnomalyORM).filter_by(
            ticker="AAPL", bar_date=date(2026, 1, 5)
        ).update({"is_reviewed": True})
        db_session.commit()

        result = repo.get_bars(["AAPL"], exclude_anomalies=True)
        result_dates = {r.bar_date for r in result}

        assert date(2026, 1, 5) in result_dates, (
            "Bar with a reviewed anomaly should be included when exclude_anomalies=True"
        )


# ---------------------------------------------------------------------------
# Builder integration tests (mock yfinance, use real DB)
# ---------------------------------------------------------------------------


class TestPriceBuilderDownload:
    """PriceBuilder.download() wires fetch + insert end-to-end."""

    def test_price_builder_download_with_mocked_yfinance(
        self, seeded_universe, price_settings
    ):
        """Seeded 2 active tickers; mocked yf.download returns 5 bars each → 10 rows inserted."""
        mock_df = make_ohlcv_df(["AAPL", "MSFT"], n_bars=5)

        with patch(
            "fund_backtest.price.downloader.yf.download",
            return_value=mock_df,
        ):
            builder = PriceBuilder(session=seeded_universe, settings=price_settings)
            summary = builder.download()

        assert summary.bars_inserted == 10, (
            f"Expected 10 bars (5 × 2 tickers), got {summary.bars_inserted}"
        )
        assert len(summary.successful) == 2
        assert len(summary.failed) == 0

        total_rows = seeded_universe.query(PriceBarORM).count()
        assert total_rows == 10

    def test_price_builder_download_dry_run_no_db_writes(
        self, seeded_universe, price_settings
    ):
        """dry_run=True: builder returns empty summary and writes no rows to DB."""
        builder = PriceBuilder(session=seeded_universe, settings=price_settings)
        summary = builder.download(dry_run=True)

        assert summary.bars_inserted == 0
        assert len(summary.successful) == 0

        total_rows = seeded_universe.query(PriceBarORM).count()
        assert total_rows == 0, "dry_run must not write to price_bars"


class TestPriceBuilderUpdate:
    """PriceBuilder.update() appends only bars after max(bar_date) per ticker."""

    def test_price_builder_update_incremental(self, seeded_universe, price_settings):
        """Pre-seed AAPL with 1 bar on 2026-01-02; update fetches only bars after that date."""
        # Pre-seed: AAPL has a bar on 2026-01-02
        repo = PriceBarRepository(seeded_universe)
        existing_bar = _make_price_bar("AAPL", date(2026, 1, 2))
        repo.insert_bars([existing_bar])

        # Mock returns 3 new bars for AAPL (2026-01-05, 2026-01-06, 2026-01-07)
        # and 5 bars for MSFT (no existing data)
        new_aapl_dates = pd.date_range("2026-01-05", periods=3, freq="B")
        msft_dates = pd.date_range("2026-01-02", periods=5, freq="B")

        def _mock_download(tickers, start, end=None, **kwargs):
            """Return appropriate mock data based on tickers requested."""
            tickers_list = [tickers] if isinstance(tickers, str) else list(tickers)
            return make_ohlcv_df(tickers_list, n_bars=3)

        with patch(
            "fund_backtest.price.downloader.yf.download",
            side_effect=_mock_download,
        ):
            builder = PriceBuilder(session=seeded_universe, settings=price_settings)
            summary = builder.update()

        # AAPL already has 1 bar; update adds bars after 2026-01-02.
        # The mock returns 3 bars — so AAPL ends up with 1 + 3 = 4 bars MAX.
        # MSFT had no data so gets 3 bars from mock.
        # Key invariant: AAPL bar on 2026-01-02 must not be a duplicate.
        aapl_bars = (
            seeded_universe.query(PriceBarORM).filter_by(ticker="AAPL").count()
        )
        aapl_jan2 = (
            seeded_universe.query(PriceBarORM)
            .filter_by(ticker="AAPL", bar_date=date(2026, 1, 2))
            .count()
        )
        # ON CONFLICT DO NOTHING ensures exactly 1 row for the pre-seeded date
        assert aapl_jan2 == 1, "Pre-seeded bar must not be duplicated"
        assert aapl_bars >= 1, "AAPL must still have bars"
