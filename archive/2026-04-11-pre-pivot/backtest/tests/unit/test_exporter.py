"""RED tests for reports/exporter.py ExportBuilder.

All tests in this file are in the RED state: the ExportBuilder class does
not exist yet. Tests will turn GREEN in Plan 07-01 Task 2.

Test coverage targets (from PLAN.md must_haves):
  - RPT-05: ExportBuilder.export_csv() writes 3 CSV files with cost comments and ISO 8601 dates
  - RPT-06: ExportBuilder.export_json() writes metrics.json with cost_assumptions key
"""
from __future__ import annotations

import json

import pytest

from fund_backtest.dashboard.demo_data import make_demo_bundle, make_demo_result
from fund_backtest.reports import ExportBuilder
from fund_backtest.simulator.types import CostConfig


@pytest.fixture
def demo_result():
    """Synthetic PortfolioResult with 1260 days and 5 tickers."""
    return make_demo_result(seed=42)


@pytest.fixture
def demo_bundle(demo_result):
    """Synthetic MetricsBundle aligned to demo_result."""
    return make_demo_bundle(demo_result)


@pytest.fixture
def cost_config():
    """Standard cost config used across exporter tests."""
    return CostConfig(slippage_bps=10.0, commission_bps=5.0, borrow_cost_bps_annual=50.0)


class TestExportBuilderCSV:
    """Tests for ExportBuilder.export_csv() (RPT-05)."""

    def test_export_csv_creates_three_files(self, demo_result, cost_config, tmp_path):
        """export_csv() must write daily_returns.csv, positions.csv, trade_log.csv."""
        builder = ExportBuilder()
        builder.export_csv(demo_result, cost_config, tmp_path)
        assert (tmp_path / "daily_returns.csv").exists(), "daily_returns.csv not created"
        assert (tmp_path / "positions.csv").exists(), "positions.csv not created"
        assert (tmp_path / "trade_log.csv").exists(), "trade_log.csv not created"

    def test_csv_dates_are_iso8601(self, demo_result, cost_config, tmp_path):
        """daily_returns.csv second line (after comment) must start with '20' (ISO 8601)."""
        builder = ExportBuilder()
        builder.export_csv(demo_result, cost_config, tmp_path)
        lines = (tmp_path / "daily_returns.csv").read_text().splitlines()
        # lines[0] is the cost comment, lines[1] is the header, lines[2] is first data row
        data_line = lines[2]
        assert data_line.startswith("20"), (
            f"Expected ISO 8601 date (starting with '20'), got: {data_line!r}"
        )
        # Must not contain timestamp (e.g. "2021-01-04 00:00:00" fails)
        assert " 00:00:00" not in data_line, (
            f"Date must be ISO 8601 (YYYY-MM-DD), not datetime: {data_line!r}"
        )

    def test_csv_has_cost_comment(self, demo_result, cost_config, tmp_path):
        """First line of each CSV must start with '# cost_assumptions:'."""
        builder = ExportBuilder()
        builder.export_csv(demo_result, cost_config, tmp_path)
        for filename in ("daily_returns.csv", "positions.csv", "trade_log.csv"):
            first_line = (tmp_path / filename).read_text().splitlines()[0]
            assert first_line.startswith("# cost_assumptions:"), (
                f"{filename} first line must be cost comment, got: {first_line!r}"
            )

    def test_csv_cost_values_match_config(self, demo_result, cost_config, tmp_path):
        """Cost comment must include the exact slippage, commission, borrow values."""
        builder = ExportBuilder()
        builder.export_csv(demo_result, cost_config, tmp_path)
        comment_line = (tmp_path / "daily_returns.csv").read_text().splitlines()[0]
        assert str(cost_config.slippage_bps) in comment_line, (
            f"slippage_bps={cost_config.slippage_bps} not found in comment: {comment_line!r}"
        )
        assert str(cost_config.commission_bps) in comment_line, (
            f"commission_bps={cost_config.commission_bps} not found in comment: {comment_line!r}"
        )
        assert str(cost_config.borrow_cost_bps_annual) in comment_line, (
            f"borrow_cost_bps_annual={cost_config.borrow_cost_bps_annual} not found in comment: {comment_line!r}"
        )

    def test_export_csv_returns_three_paths(self, demo_result, cost_config, tmp_path):
        """export_csv() must return a list of exactly 3 Path objects."""
        from pathlib import Path
        builder = ExportBuilder()
        result = builder.export_csv(demo_result, cost_config, tmp_path)
        assert isinstance(result, list), f"Expected list, got {type(result)}"
        assert len(result) == 3, f"Expected 3 paths, got {len(result)}"
        for p in result:
            assert isinstance(p, Path), f"Expected Path objects, got {type(p)}"


class TestExportBuilderJSON:
    """Tests for ExportBuilder.export_json() (RPT-06)."""

    def test_export_json_creates_metrics_file(self, demo_bundle, cost_config, tmp_path):
        """export_json() must write metrics.json in output_dir."""
        builder = ExportBuilder()
        builder.export_json(demo_bundle, cost_config, tmp_path)
        assert (tmp_path / "metrics.json").exists(), "metrics.json not created"

    def test_json_has_cost_assumptions_key(self, demo_bundle, cost_config, tmp_path):
        """Parsed JSON must contain 'cost_assumptions' dict with all 3 cost fields."""
        builder = ExportBuilder()
        builder.export_json(demo_bundle, cost_config, tmp_path)
        data = json.loads((tmp_path / "metrics.json").read_text())
        assert "cost_assumptions" in data, "JSON missing 'cost_assumptions' key"
        ca = data["cost_assumptions"]
        assert "slippage_bps" in ca, "cost_assumptions missing 'slippage_bps'"
        assert "commission_bps" in ca, "cost_assumptions missing 'commission_bps'"
        assert "borrow_cost_bps_annual" in ca, "cost_assumptions missing 'borrow_cost_bps_annual'"

    def test_json_excludes_rolling_series(self, demo_bundle, cost_config, tmp_path):
        """Parsed JSON must NOT contain 'rolling_sharpe' or 'rolling_drawdown' keys."""
        builder = ExportBuilder()
        builder.export_json(demo_bundle, cost_config, tmp_path)
        data = json.loads((tmp_path / "metrics.json").read_text())
        assert "rolling_sharpe" not in data, "JSON must not contain 'rolling_sharpe'"
        assert "rolling_drawdown" not in data, "JSON must not contain 'rolling_drawdown'"

    def test_json_scalar_values_match_bundle(self, demo_bundle, cost_config, tmp_path):
        """Scalar metrics in JSON must match MetricsBundle values."""
        builder = ExportBuilder()
        builder.export_json(demo_bundle, cost_config, tmp_path)
        data = json.loads((tmp_path / "metrics.json").read_text())
        assert data["sharpe"] == demo_bundle.sharpe, "sharpe mismatch"
        assert data["sortino"] == demo_bundle.sortino, "sortino mismatch"
        assert data["calmar"] == demo_bundle.calmar, "calmar mismatch"
        assert data["max_drawdown"] == demo_bundle.max_drawdown, "max_drawdown mismatch"
        assert data["cagr"] == demo_bundle.cagr, "cagr mismatch"
        assert data["hit_rate"] == demo_bundle.hit_rate, "hit_rate mismatch"
        assert data["win_loss_ratio"] == demo_bundle.win_loss_ratio, "win_loss_ratio mismatch"
        assert data["annual_turnover"] == demo_bundle.annual_turnover, "annual_turnover mismatch"
        assert data["alpha"] == demo_bundle.alpha, "alpha mismatch"
        assert data["beta"] == demo_bundle.beta, "beta mismatch"

    def test_export_json_returns_path(self, demo_bundle, cost_config, tmp_path):
        """export_json() must return a single Path object."""
        from pathlib import Path
        builder = ExportBuilder()
        result = builder.export_json(demo_bundle, cost_config, tmp_path)
        assert isinstance(result, Path), f"Expected Path, got {type(result)}"
        assert result == tmp_path / "metrics.json", f"Expected metrics.json path, got {result}"
