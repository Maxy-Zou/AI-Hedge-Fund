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
