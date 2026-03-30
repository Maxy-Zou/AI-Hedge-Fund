"""Unit tests for the fund-backtest CLI commands.

Tests use Typer's CliRunner and unittest.mock.patch to mock the DB session and
UniverseBuilder. No real DB connections are made in unit tests.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from fund_backtest.cli import app
from fund_backtest.universe.types import RefreshResult

runner = CliRunner()


def _make_refresh_result(active_count: int = 247) -> RefreshResult:
    return RefreshResult(
        snapshot_date="2026-03-28",
        active_count=active_count,
        new_count=5,
        removed_count=2,
        sector_breakdown={"Information Technology": 60, "Health Care": 30},
    )


# ---------------------------------------------------------------------------
# Test 1: universe refresh --dry-run
# ---------------------------------------------------------------------------

def test_refresh_dry_run_exits_zero():
    """refresh --dry-run exits 0 and mentions dry-run without touching DB."""
    from fund_backtest.config import UniverseSettings
    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.load_universe_settings", return_value=UniverseSettings()):
                result = runner.invoke(app, ["universe", "refresh", "--dry-run"])
    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    assert "dry" in result.output.lower(), f"expected 'dry' in output: {result.output}"


def test_refresh_dry_run_does_not_call_builder():
    """refresh --dry-run must NOT call UniverseBuilder.refresh()."""
    with patch("fund_backtest.cli.UniverseBuilder") as mock_cls:
        with patch("fund_backtest.cli.load_app_settings"):
            with patch("fund_backtest.cli.configure_logging"):
                result = runner.invoke(app, ["universe", "refresh", "--dry-run"])
    assert result.exit_code == 0
    mock_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: universe refresh (no --dry-run) calls builder and shows active count
# ---------------------------------------------------------------------------

def test_refresh_calls_builder_and_shows_count():
    """refresh (no --dry-run) calls UniverseBuilder.refresh() and shows active_count."""
    mock_result = _make_refresh_result(active_count=247)

    with patch("fund_backtest.cli.load_app_settings") as mock_settings:
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.load_universe_settings"):
                with patch("fund_backtest.cli.create_engine_from_settings"):
                    with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                        mock_session = MagicMock()
                        mock_session.__enter__ = MagicMock(return_value=mock_session)
                        mock_session.__exit__ = MagicMock(return_value=False)
                        mock_factory.return_value.return_value = mock_session

                        with patch("fund_backtest.cli.UniverseBuilder") as mock_cls:
                            mock_instance = MagicMock()
                            mock_instance.refresh.return_value = mock_result
                            mock_cls.return_value = mock_instance

                            result = runner.invoke(app, ["universe", "refresh"])

    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    assert "247" in result.output, f"expected '247' in output: {result.output}"


# ---------------------------------------------------------------------------
# Test 3: universe status — empty universe (no tickers)
# ---------------------------------------------------------------------------

def test_status_empty_universe():
    """status with an empty DB exits 0 and handles gracefully."""
    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.create_engine_from_settings"):
                with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                    mock_session = MagicMock()
                    mock_session.__enter__ = MagicMock(return_value=mock_session)
                    mock_session.__exit__ = MagicMock(return_value=False)

                    # Active tickers query returns empty list
                    mock_query = MagicMock()
                    mock_query.filter_by.return_value.all.return_value = []
                    mock_session.query.return_value = mock_query

                    mock_factory.return_value.return_value = mock_session

                    result = runner.invoke(app, ["universe", "status"])

    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    # Should show "empty" or "0" to indicate no tickers
    lower = result.output.lower()
    assert "empty" in lower or "0" in lower, f"expected empty/0 in output: {result.output}"


# ---------------------------------------------------------------------------
# Test 4: universe status — with tickers, shows count and sector names
# ---------------------------------------------------------------------------

def test_status_with_tickers():
    """status with tickers shows active count and sector names."""
    # Build 3 mock tickers in 2 sectors
    def make_ticker(t, sector):
        m = MagicMock()
        m.ticker = t
        m.gics_sector = sector
        return m

    tickers = [
        make_ticker("MTSI", "Information Technology"),
        make_ticker("WTS", "Industrials"),
        make_ticker("CALX", "Information Technology"),
    ]

    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.create_engine_from_settings"):
                with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                    mock_session = MagicMock()
                    mock_session.__enter__ = MagicMock(return_value=mock_session)
                    mock_session.__exit__ = MagicMock(return_value=False)

                    # First query (active tickers) returns 3 tickers
                    # Second query (latest snapshot) returns None
                    active_query = MagicMock()
                    active_query.filter_by.return_value.all.return_value = tickers
                    snapshot_query = MagicMock()
                    snapshot_query.order_by.return_value.first.return_value = None

                    mock_session.query.side_effect = [active_query, snapshot_query]

                    mock_factory.return_value.return_value = mock_session

                    result = runner.invoke(app, ["universe", "status"])

    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    assert "3" in result.output, f"expected ticker count (3) in output: {result.output}"
    assert "Information Technology" in result.output, f"expected sector name in output: {result.output}"


# ---------------------------------------------------------------------------
# Test 5: universe refresh — builder raises, exits code 1
# ---------------------------------------------------------------------------

def test_refresh_error_handling_exits_code_1():
    """When builder raises, refresh exits code 1 with error message."""
    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.load_universe_settings"):
                with patch("fund_backtest.cli.create_engine_from_settings"):
                    with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                        mock_session = MagicMock()
                        mock_session.__enter__ = MagicMock(return_value=mock_session)
                        mock_session.__exit__ = MagicMock(return_value=False)
                        mock_factory.return_value.return_value = mock_session

                        with patch("fund_backtest.cli.UniverseBuilder") as mock_cls:
                            mock_instance = MagicMock()
                            mock_instance.refresh.side_effect = RuntimeError("DB connection failed")
                            mock_cls.return_value = mock_instance

                            result = runner.invoke(app, ["universe", "refresh"])

    assert result.exit_code == 1, f"expected exit code 1, got {result.exit_code}: {result.output}"
    assert "DB connection failed" in result.output, (
        f"expected error text in output: {result.output}"
    )


# ---------------------------------------------------------------------------
# Tests for backtest export subgroup (Task 1 + 2 — Phase 07-02)
# Note: matplotlib Agg backend is guarded in tearsheet.py itself, but we set
# it here too as a belt-and-suspenders measure for the test process.
# ---------------------------------------------------------------------------

import matplotlib
if matplotlib.get_backend() != "Agg":
    matplotlib.use("Agg")


def test_export_tearsheet_creates_pdf(tmp_path):
    """backtest export --tearsheet writes tearsheet.pdf to output-dir."""
    result = runner.invoke(app, ["backtest", "export", "--tearsheet", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    assert (tmp_path / "tearsheet.pdf").exists(), f"tearsheet.pdf missing; output: {result.output}"


def test_export_csv_creates_three_files(tmp_path):
    """backtest export --csv writes daily_returns.csv, positions.csv, trade_log.csv."""
    result = runner.invoke(app, ["backtest", "export", "--csv", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    assert (tmp_path / "daily_returns.csv").exists(), "daily_returns.csv missing"
    assert (tmp_path / "positions.csv").exists(), "positions.csv missing"
    assert (tmp_path / "trade_log.csv").exists(), "trade_log.csv missing"


def test_export_json_creates_metrics_file(tmp_path):
    """backtest export --json writes metrics.json to output-dir."""
    result = runner.invoke(app, ["backtest", "export", "--json", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    assert (tmp_path / "metrics.json").exists(), f"metrics.json missing; output: {result.output}"


def test_export_all_creates_all_outputs(tmp_path):
    """backtest export --all creates tearsheet.pdf + 3 CSVs + metrics.json."""
    result = runner.invoke(app, ["backtest", "export", "--all", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    assert (tmp_path / "tearsheet.pdf").exists(), "tearsheet.pdf missing"
    assert (tmp_path / "daily_returns.csv").exists(), "daily_returns.csv missing"
    assert (tmp_path / "positions.csv").exists(), "positions.csv missing"
    assert (tmp_path / "trade_log.csv").exists(), "trade_log.csv missing"
    assert (tmp_path / "metrics.json").exists(), "metrics.json missing"


def test_export_no_flags_exits_nonzero(tmp_path):
    """backtest export without any flags exits with non-zero code."""
    result = runner.invoke(app, ["backtest", "export", "--output-dir", str(tmp_path)])
    assert result.exit_code != 0, f"expected non-zero exit, got {result.exit_code}: {result.output}"


# ---------------------------------------------------------------------------
# Tests for data commands — error paths and dry-run (Rule 2: missing coverage)
# These mirror the pattern from universe command tests.
# ---------------------------------------------------------------------------

def test_data_download_dry_run_exits_zero():
    """data download --dry-run exits 0 and mentions dry-run without touching DB."""
    from fund_backtest.config import PriceSettings
    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.load_price_settings", return_value=PriceSettings()):
                with patch("fund_backtest.cli.create_engine_from_settings"):
                    with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                        mock_session = MagicMock()
                        mock_session.__enter__ = MagicMock(return_value=mock_session)
                        mock_session.__exit__ = MagicMock(return_value=False)
                        mock_factory.return_value.return_value = mock_session
                        with patch("fund_backtest.cli.PriceBuilder") as mock_cls:
                            mock_instance = MagicMock()
                            mock_instance.download.return_value = MagicMock(
                                requested=0, successful=[], failed=[], bars_inserted=0
                            )
                            mock_cls.return_value = mock_instance
                            result = runner.invoke(app, ["data", "download", "--dry-run"])
    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    assert "dry" in result.output.lower(), f"expected 'dry' in output: {result.output}"


def test_data_download_error_exits_code_1():
    """When PriceBuilder.download raises, data download exits code 1."""
    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.load_price_settings"):
                with patch("fund_backtest.cli.create_engine_from_settings"):
                    with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                        mock_session = MagicMock()
                        mock_session.__enter__ = MagicMock(return_value=mock_session)
                        mock_session.__exit__ = MagicMock(return_value=False)
                        mock_factory.return_value.return_value = mock_session
                        with patch("fund_backtest.cli.PriceBuilder") as mock_cls:
                            mock_instance = MagicMock()
                            mock_instance.download.side_effect = RuntimeError("fetch error")
                            mock_cls.return_value = mock_instance
                            result = runner.invoke(app, ["data", "download"])
    assert result.exit_code == 1, f"expected exit 1, got {result.exit_code}: {result.output}"
    assert "fetch error" in result.output


def test_data_update_error_exits_code_1():
    """When PriceBuilder.update raises, data update exits code 1."""
    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.load_price_settings"):
                with patch("fund_backtest.cli.create_engine_from_settings"):
                    with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                        mock_session = MagicMock()
                        mock_session.__enter__ = MagicMock(return_value=mock_session)
                        mock_session.__exit__ = MagicMock(return_value=False)
                        mock_factory.return_value.return_value = mock_session
                        with patch("fund_backtest.cli.PriceBuilder") as mock_cls:
                            mock_instance = MagicMock()
                            mock_instance.update.side_effect = RuntimeError("update error")
                            mock_cls.return_value = mock_instance
                            result = runner.invoke(app, ["data", "update"])
    assert result.exit_code == 1, f"expected exit 1, got {result.exit_code}: {result.output}"
    assert "update error" in result.output


def test_data_coverage_error_exits_code_1():
    """When DB query fails, data coverage exits code 1."""
    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.create_engine_from_settings"):
                with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                    mock_factory.return_value.return_value.__enter__ = MagicMock(
                        side_effect=RuntimeError("coverage error")
                    )
                    mock_factory.return_value.return_value.__exit__ = MagicMock(return_value=False)
                    result = runner.invoke(app, ["data", "coverage"])
    assert result.exit_code == 1, f"expected exit 1, got {result.exit_code}: {result.output}"
    assert "coverage error" in result.output


def test_status_with_latest_snapshot():
    """universe status shows 'Last refreshed' row when snapshot exists."""
    def make_ticker(t, sector):
        m = MagicMock()
        m.ticker = t
        m.gics_sector = sector
        return m

    tickers = [make_ticker("ABC", "Information Technology")]
    mock_snapshot = MagicMock()
    mock_snapshot.snapshot_date = "2026-03-28"

    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.create_engine_from_settings"):
                with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                    mock_session = MagicMock()
                    mock_session.__enter__ = MagicMock(return_value=mock_session)
                    mock_session.__exit__ = MagicMock(return_value=False)
                    active_query = MagicMock()
                    active_query.filter_by.return_value.all.return_value = tickers
                    snapshot_query = MagicMock()
                    snapshot_query.order_by.return_value.first.return_value = mock_snapshot
                    mock_session.query.side_effect = [active_query, snapshot_query]
                    mock_factory.return_value.return_value = mock_session
                    result = runner.invoke(app, ["universe", "status"])
    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    assert "2026-03-28" in result.output


# ---------------------------------------------------------------------------
# Tests for backtest run command (Phase 08-02)
# ---------------------------------------------------------------------------

import numpy as np
import pandas as pd
from datetime import date as _date


def _make_minimal_signal_frame():
    """Build a minimal 10-row x 3-ticker SignalFrame for CLI run tests."""
    dates = pd.date_range("2024-01-02", periods=10, freq="B")
    tickers = ["AAPL", "MSFT", "GOOG"]
    data = np.random.uniform(40, 80, (10, 3))
    return pd.DataFrame(data, index=dates, columns=tickers)


def _make_mock_session():
    """Build a mock SQLAlchemy session context manager."""
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    return mock_session


def test_backtest_run_ai_washing_exits_zero():
    """backtest run --signal ai-washing exits 0 when all pipeline stages complete."""
    signal_frame = _make_minimal_signal_frame()

    # Build mock PriceBarORM objects for the 3 tickers
    mock_bars = []
    for ticker in ["AAPL", "MSFT", "GOOG"]:
        for i in range(10):
            bar = MagicMock()
            bar.ticker = ticker
            bar.bar_date = _date(2024, 1, 2 + i)
            bar.close_cents = 15000
            mock_bars.append(bar)

    mock_session = _make_mock_session()

    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.create_engine_from_settings"):
                with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                    mock_factory.return_value.return_value = mock_session

                    with patch("fund_backtest.cli.AiWashingLoader") as mock_loader_cls:
                        mock_loader = MagicMock()
                        mock_loader.load.return_value = signal_frame
                        mock_loader_cls.return_value = mock_loader

                        with patch("fund_backtest.cli.PriceBarRepository") as mock_repo_cls:
                            mock_repo = MagicMock()
                            mock_repo.get_bars.return_value = mock_bars
                            mock_repo_cls.return_value = mock_repo

                            with patch("fund_backtest.cli.PortfolioSimulator") as mock_sim_cls:
                                mock_sim = MagicMock()
                                mock_portfolio_result = MagicMock()
                                mock_sim.simulate.return_value = mock_portfolio_result
                                mock_sim_cls.return_value = mock_sim

                                with patch("fund_backtest.cli.MetricsEngine") as mock_metrics_cls:
                                    mock_metrics = MagicMock()
                                    mock_bundle = MagicMock()
                                    mock_bundle.sharpe = 1.23
                                    mock_bundle.cagr = 0.15
                                    mock_metrics.compute.return_value = mock_bundle
                                    mock_metrics_cls.return_value = mock_metrics

                                    result = runner.invoke(
                                        app, ["backtest", "run", "--signal", "ai-washing"]
                                    )

    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    assert "complete" in result.output.lower(), f"expected 'complete' in output: {result.output}"


def test_backtest_run_exits_1_on_signal_load_error():
    """backtest run exits 1 with error message when AiWashingLoader raises SignalLoadError."""
    from fund_backtest.signal.loaders import SignalLoadError

    mock_session = _make_mock_session()

    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.create_engine_from_settings"):
                with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                    mock_factory.return_value.return_value = mock_session

                    with patch("fund_backtest.cli.AiWashingLoader") as mock_loader_cls:
                        mock_loader = MagicMock()
                        mock_loader.load.side_effect = SignalLoadError(
                            "scores table is empty"
                        )
                        mock_loader_cls.return_value = mock_loader

                        result = runner.invoke(
                            app, ["backtest", "run", "--signal", "ai-washing"]
                        )

    assert result.exit_code == 1, f"expected exit 1, got {result.exit_code}: {result.output}"
    assert "empty" in result.output.lower(), f"expected 'empty' in output: {result.output}"


def test_backtest_run_unknown_signal_exits_1():
    """backtest run --signal unknown-strategy exits 1 with 'unknown' in output."""
    result = runner.invoke(app, ["backtest", "run", "--signal", "unknown-strategy"])

    assert result.exit_code == 1, f"expected exit 1, got {result.exit_code}: {result.output}"
    assert "unknown" in result.output.lower(), f"expected 'unknown' in output: {result.output}"


# ---------------------------------------------------------------------------
# Tests for FIX-02 (date intersection) and FIX-05 (benchmark alpha/beta)
# ---------------------------------------------------------------------------

def _make_mock_price_bars(dates, tickers=("AAPL", "MSFT", "GOOG"), close_cents=15000):
    """Build mock PriceBarORM objects for the given dates and tickers."""
    bars = []
    for ticker in tickers:
        for d in dates:
            bar = MagicMock()
            bar.ticker = ticker
            bar.bar_date = d.date() if hasattr(d, "date") else d
            bar.close_cents = close_cents
            bars.append(bar)
    return bars


def _make_mock_portfolio_result(n_periods=8):
    """Build a mock PortfolioResult with a net_returns DatetimeIndex."""
    mock_result = MagicMock()
    dates = pd.date_range("2024-01-04", periods=n_periods, freq="B")
    mock_result.net_returns = pd.Series(
        [0.001] * n_periods, index=dates, dtype=float
    )
    return mock_result


def test_run_date_intersection():
    """FIX-02: SignalAdapter.adapt() is called with only common-date rows.

    signal_frame has 10 dates, price_frame has only the last 8 of those dates.
    The intersection must trim signal_frame to 8 rows before adapt() is called.
    """
    signal_dates = pd.date_range("2024-01-02", periods=10, freq="B")
    price_dates = signal_dates[2:]  # 8 dates — first 2 signal dates excluded
    tickers = ["AAPL", "MSFT", "GOOG"]
    data = np.random.uniform(40, 80, (10, 3))
    signal_frame = pd.DataFrame(data, index=signal_dates, columns=tickers)

    mock_bars = _make_mock_price_bars(price_dates, tickers)
    mock_session = _make_mock_session()
    mock_portfolio_result = _make_mock_portfolio_result(n_periods=8)

    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.create_engine_from_settings"):
                with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                    mock_factory.return_value.return_value = mock_session

                    with patch("fund_backtest.cli.AiWashingLoader") as mock_loader_cls:
                        mock_loader = MagicMock()
                        mock_loader.load.return_value = signal_frame
                        mock_loader_cls.return_value = mock_loader

                        with patch("fund_backtest.cli.PriceBarRepository") as mock_repo_cls:
                            mock_repo = MagicMock()
                            mock_repo.get_bars.return_value = mock_bars
                            mock_repo_cls.return_value = mock_repo

                            with patch("fund_backtest.cli.SignalAdapter") as mock_adapter_cls:
                                mock_adapter = MagicMock()
                                mock_adapter_cls.return_value = mock_adapter

                                with patch("fund_backtest.cli.PortfolioSimulator") as mock_sim_cls:
                                    mock_sim = MagicMock()
                                    mock_sim.simulate.return_value = mock_portfolio_result
                                    mock_sim_cls.return_value = mock_sim

                                    with patch("fund_backtest.cli.MetricsEngine") as mock_metrics_cls:
                                        mock_metrics = MagicMock()
                                        mock_bundle = MagicMock()
                                        mock_bundle.sharpe = 1.0
                                        mock_bundle.cagr = 0.10
                                        mock_metrics.compute.return_value = mock_bundle
                                        mock_metrics_cls.return_value = mock_metrics

                                        with patch("fund_backtest.cli.yf") as mock_yf:
                                            mock_yf.download.return_value = pd.DataFrame()

                                            result = runner.invoke(
                                                app,
                                                ["backtest", "run", "--signal", "ai-washing"],
                                            )

    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    # The adapt() call must have received a DataFrame with 8 rows, not 10
    call_args = mock_adapter.adapt.call_args
    assert call_args is not None, "SignalAdapter.adapt() was never called"
    passed_frame = call_args[0][0]
    assert len(passed_frame) == 8, (
        f"Expected adapt() to receive 8-row frame (intersection), got {len(passed_frame)} rows"
    )


def test_run_benchmark_passed():
    """FIX-05: MetricsEngine.compute() receives a non-None benchmark when SPY fetch succeeds."""
    signal_dates = pd.date_range("2024-01-02", periods=10, freq="B")
    tickers = ["AAPL", "MSFT", "GOOG"]
    data = np.random.uniform(40, 80, (10, 3))
    signal_frame = pd.DataFrame(data, index=signal_dates, columns=tickers)

    mock_bars = _make_mock_price_bars(signal_dates, tickers)
    mock_session = _make_mock_session()
    mock_portfolio_result = _make_mock_portfolio_result(n_periods=9)

    # Build a non-empty SPY DataFrame mimicking yfinance output
    spy_dates = pd.date_range("2024-01-03", periods=9, freq="B")
    spy_df = pd.DataFrame({"Close": [450.0 + i for i in range(9)]}, index=spy_dates)

    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.create_engine_from_settings"):
                with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                    mock_factory.return_value.return_value = mock_session

                    with patch("fund_backtest.cli.AiWashingLoader") as mock_loader_cls:
                        mock_loader = MagicMock()
                        mock_loader.load.return_value = signal_frame
                        mock_loader_cls.return_value = mock_loader

                        with patch("fund_backtest.cli.PriceBarRepository") as mock_repo_cls:
                            mock_repo = MagicMock()
                            mock_repo.get_bars.return_value = mock_bars
                            mock_repo_cls.return_value = mock_repo

                        with patch("fund_backtest.cli.PortfolioSimulator") as mock_sim_cls:
                            mock_sim = MagicMock()
                            mock_sim.simulate.return_value = mock_portfolio_result
                            mock_sim_cls.return_value = mock_sim

                            with patch("fund_backtest.cli.MetricsEngine") as mock_metrics_cls:
                                mock_metrics = MagicMock()
                                mock_bundle = MagicMock()
                                mock_bundle.sharpe = 1.5
                                mock_bundle.cagr = 0.20
                                mock_metrics.compute.return_value = mock_bundle
                                mock_metrics_cls.return_value = mock_metrics

                                with patch("fund_backtest.cli.yf") as mock_yf:
                                    mock_yf.download.return_value = spy_df

                                    result = runner.invoke(
                                        app,
                                        ["backtest", "run", "--signal", "ai-washing"],
                                    )

    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    compute_call = mock_metrics.compute.call_args
    assert compute_call is not None, "MetricsEngine.compute() was never called"
    benchmark_arg = compute_call.kwargs.get("benchmark")
    assert benchmark_arg is not None, (
        f"Expected non-None benchmark= in MetricsEngine.compute(), got None. "
        f"Call kwargs: {compute_call.kwargs}"
    )


def test_run_benchmark_fallback():
    """FIX-05: When yfinance raises, run() exits 0 and compute() receives benchmark=None."""
    signal_dates = pd.date_range("2024-01-02", periods=10, freq="B")
    tickers = ["AAPL", "MSFT", "GOOG"]
    data = np.random.uniform(40, 80, (10, 3))
    signal_frame = pd.DataFrame(data, index=signal_dates, columns=tickers)

    mock_bars = _make_mock_price_bars(signal_dates, tickers)
    mock_session = _make_mock_session()
    mock_portfolio_result = _make_mock_portfolio_result(n_periods=9)

    with patch("fund_backtest.cli.load_app_settings"):
        with patch("fund_backtest.cli.configure_logging"):
            with patch("fund_backtest.cli.create_engine_from_settings"):
                with patch("fund_backtest.cli.get_session_factory") as mock_factory:
                    mock_factory.return_value.return_value = mock_session

                    with patch("fund_backtest.cli.AiWashingLoader") as mock_loader_cls:
                        mock_loader = MagicMock()
                        mock_loader.load.return_value = signal_frame
                        mock_loader_cls.return_value = mock_loader

                        with patch("fund_backtest.cli.PriceBarRepository") as mock_repo_cls:
                            mock_repo = MagicMock()
                            mock_repo.get_bars.return_value = mock_bars
                            mock_repo_cls.return_value = mock_repo

                        with patch("fund_backtest.cli.PortfolioSimulator") as mock_sim_cls:
                            mock_sim = MagicMock()
                            mock_sim.simulate.return_value = mock_portfolio_result
                            mock_sim_cls.return_value = mock_sim

                            with patch("fund_backtest.cli.MetricsEngine") as mock_metrics_cls:
                                mock_metrics = MagicMock()
                                mock_bundle = MagicMock()
                                mock_bundle.sharpe = 0.8
                                mock_bundle.cagr = 0.05
                                mock_metrics.compute.return_value = mock_bundle
                                mock_metrics_cls.return_value = mock_metrics

                                with patch("fund_backtest.cli.yf") as mock_yf:
                                    mock_yf.download.side_effect = Exception("network error")

                                    result = runner.invoke(
                                        app,
                                        ["backtest", "run", "--signal", "ai-washing"],
                                    )

    assert result.exit_code == 0, f"exit code {result.exit_code}: {result.output}"
    compute_call = mock_metrics.compute.call_args
    assert compute_call is not None, "MetricsEngine.compute() was never called"
    benchmark_arg = compute_call.kwargs.get("benchmark")
    assert benchmark_arg is None, (
        f"Expected benchmark=None on SPY fetch failure, got: {benchmark_arg}"
    )
