"""Tests for CLI entry point — CLI-01."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from kalshi_backtest.cli import app


runner = CliRunner()


def test_ingest_help_exits_zero():
    """CLI-01: `kalshi-backtest ingest --help` exits 0 and shows key options."""
    result = runner.invoke(app, ["--help"])

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
        result = runner.invoke(app, ["--dry-run"])

    assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}: {result.output}"
    assert "dry-run" in result.output.lower() or "Dry-run" in result.output


def test_ingest_missing_credentials_exits_one():
    """CLI-01: Missing required env vars produce exit code 1 and clear error message."""
    with patch.dict(os.environ, {}, clear=True):
        result = runner.invoke(app, [])

    assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}"
    assert "Configuration error" in result.output or "error" in result.output.lower()
