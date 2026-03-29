"""RED tests for reports/tearsheet.py TearsheetBuilder.

All tests in this file are in the RED state: the TearsheetBuilder class does
not exist yet. Tests will turn GREEN in Plan 07-01 Task 2.

Test coverage targets (from PLAN.md must_haves):
  - RPT-04: TearsheetBuilder.build() writes a valid PDF with cost assumptions
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

import pytest

from fund_backtest.dashboard.demo_data import make_demo_bundle, make_demo_result
from fund_backtest.reports import TearsheetBuilder
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
    """Standard cost config used across tearsheet tests."""
    return CostConfig(slippage_bps=10.0, commission_bps=5.0, borrow_cost_bps_annual=50.0)


class TestTearsheetBuilder:
    """Tests for TearsheetBuilder.build() (RPT-04)."""

    def test_build_creates_pdf_file(self, demo_result, demo_bundle, cost_config, tmp_path):
        """TearsheetBuilder.build() must create a file that exists with size > 0."""
        output_path = tmp_path / "out.pdf"
        builder = TearsheetBuilder()
        builder.build(demo_result, demo_bundle, cost_config, output_path)
        assert output_path.exists(), "PDF file was not created"
        assert output_path.stat().st_size > 0, "PDF file is empty"

    def test_pdf_is_valid_pdf(self, demo_result, demo_bundle, cost_config, tmp_path):
        """PDF file content must start with %PDF magic bytes."""
        output_path = tmp_path / "out.pdf"
        builder = TearsheetBuilder()
        builder.build(demo_result, demo_bundle, cost_config, output_path)
        with open(output_path, "rb") as f:
            header = f.read(4)
        assert header == b"%PDF", f"Expected b'%PDF' header, got {header!r}"

    def test_build_returns_path(self, demo_result, demo_bundle, cost_config, tmp_path):
        """build() must return the output_path argument."""
        output_path = tmp_path / "out.pdf"
        builder = TearsheetBuilder()
        result = builder.build(demo_result, demo_bundle, cost_config, output_path)
        assert result == output_path, f"Expected {output_path}, got {result}"
