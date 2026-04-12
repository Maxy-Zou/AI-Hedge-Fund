"""Tests for CLI entry point — CLI-01 and CLI-02."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from kalshi_backtest.cli import app

runner = CliRunner()


def test_ingest_help_exits_zero():
    """CLI-01: `kalshi-backtest ingest --help` exits 0 and shows key options."""
    # With multiple commands, must use the subcommand name to see its options
    result = runner.invoke(app, ["ingest", "--help"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    assert "--lookback-days" in result.output
    assert "--dry-run" in result.output
    assert "--series" in result.output


def test_ingest_dry_run_prints_plan():
    """CLI-01: `kalshi-backtest ingest --dry-run` prints plan without DB writes."""
    mock_settings = MagicMock()
    mock_settings.db_path = "/tmp/test.duckdb"
    mock_settings.api_base_url = "https://demo-api.kalshi.co/trade-api/v2"
    mock_settings.rate_limit_rpm = 60

    with patch("kalshi_backtest.cli.load_settings", return_value=mock_settings):
        result = runner.invoke(app, ["ingest", "--dry-run"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    assert "dry-run" in result.output.lower() or "Dry-run" in result.output


def test_ingest_missing_credentials_exits_one():
    """CLI-01: Missing required env vars produce exit code 1 and clear error message."""
    with patch.dict(os.environ, {}, clear=True):
        result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}"
    assert "Configuration error" in result.output or "error" in result.output.lower()


# ---------------------------------------------------------------------------
# CLI-02: `run` command tests
# ---------------------------------------------------------------------------


def test_run_dry_run_exits_zero():
    """CLI-02: `kalshi-backtest run --dry-run` exits 0 (no credentials needed)."""
    result = runner.invoke(app, ["run", "--dry-run"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"


def test_run_dry_run_shows_date_range():
    """CLI-02: dry-run output contains lookback reference and date range info."""
    result = runner.invoke(app, ["run", "--dry-run"])

    assert result.exit_code == 0
    output_lower = result.output.lower()
    assert "lookback" in output_lower or "days" in output_lower, (
        f"Expected 'lookback' or 'days' in output: {result.output}"
    )


def test_run_missing_credentials_exits_one():
    """CLI-02: Missing credentials exits 1 with error message when not --dry-run."""
    with patch.dict(os.environ, {}, clear=True):
        result = runner.invoke(app, ["run"])

    assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}: {result.output}"
    assert "error" in result.output.lower() or "configuration" in result.output.lower(), (
        f"Expected error message in output: {result.output}"
    )


def test_run_default_lookback_is_365():
    """CLI-02: Default --lookback-days is 365, shown in dry-run output."""
    result = runner.invoke(app, ["run", "--dry-run"])

    assert result.exit_code == 0
    assert "365" in result.output, f"Expected '365' in output: {result.output}"


def test_run_custom_lookback():
    """CLI-02: Custom --lookback-days value appears in dry-run output."""
    result = runner.invoke(app, ["run", "--lookback-days", "90", "--dry-run"])

    assert result.exit_code == 0
    assert "90" in result.output, f"Expected '90' in output: {result.output}"


def test_run_series_filter():
    """CLI-02: --series filter value echoed in dry-run output."""
    result = runner.invoke(app, ["run", "--series", "KXBTC", "--dry-run"])

    assert result.exit_code == 0
    assert "KXBTC" in result.output, f"Expected 'KXBTC' in output: {result.output}"


# ---------------------------------------------------------------------------
# CLI-03: `compare` command tests
# ---------------------------------------------------------------------------


def test_compare_command():
    """CLI-03: `kalshi-backtest compare --dry-run` exits 0 with comparison table."""
    result = runner.invoke(app, ["compare", "--dry-run"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    assert "Strategy Comparison" in result.output, (
        f"Expected 'Strategy Comparison' in output: {result.output}"
    )


def test_compare_dry_run_no_credentials():
    """CLI-03: compare --dry-run exits 0 without any credentials in environment."""
    with patch.dict(os.environ, {}, clear=True):
        result = runner.invoke(app, ["compare", "--dry-run"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"


def test_compare_dry_run_shows_both_strategies():
    """CLI-03: compare --dry-run output includes both strategy column names."""
    result = runner.invoke(app, ["compare", "--dry-run"])

    assert result.exit_code == 0
    assert "StrategyA" in result.output, f"Expected 'StrategyA' in output: {result.output}"
    assert "StrategyB" in result.output, f"Expected 'StrategyB' in output: {result.output}"


# ---------------------------------------------------------------------------
# CLI STRAT-01/02: --strategy flag tests
# ---------------------------------------------------------------------------
# This test will fail RED until Plan 04-03 wires the --strategy flag into the
# `run` command and registers strategy names in the CLI.
# ---------------------------------------------------------------------------


def test_run_strategy_flag_dry_run():
    """CLI STRAT: `run --strategy pass-through --dry-run` exits 0.

    The --strategy flag selects a named strategy to run. 'pass-through' is the
    built-in default strategy. This test will fail RED until Plan 04-03 adds
    the --strategy option to the `run` command.
    """
    result = runner.invoke(app, ["run", "--strategy", "pass-through", "--dry-run"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
