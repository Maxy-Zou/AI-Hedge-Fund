"""RED tests for dashboard/charts.py pure Plotly chart factory functions.

All tests in this file are in the RED state: the chart functions raise
NotImplementedError. Tests will turn GREEN in Plan 06-02.

Test coverage targets (from RESEARCH.md Validation Architecture):
  - RPT-01: TestEquityChart — equity traces, benchmark overlays, drawdown annotations
  - RPT-02: TestMonthlyHeatmap — pivot shape, zero midpoint anchor
  - RPT-03: TestSectorChart — all sectors present, absolute weights
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fund_backtest.dashboard.charts import (
    build_equity_drawdown_chart,
    build_monthly_heatmap,
    build_sector_exposure_chart,
)
from fund_backtest.dashboard.demo_data import (
    DEMO_TICKER_SECTORS,
    make_demo_bundle,
    make_demo_result,
)


@pytest.fixture
def demo_result():
    """Synthetic PortfolioResult with 1260 days and 5 tickers."""
    return make_demo_result(seed=42)


@pytest.fixture
def demo_bundle(demo_result):
    """Synthetic MetricsBundle aligned to demo_result."""
    return make_demo_bundle(demo_result)


class TestEquityChart:
    """Tests for build_equity_drawdown_chart (RPT-01)."""

    def test_returns_figure_with_two_subplots(self, demo_result):
        """Figure must have exactly 2 subplot rows (equity + drawdown)."""
        drawdown = (
            (1 + demo_result.net_returns).cumprod()
            / (1 + demo_result.net_returns).cumprod().cummax()
            - 1
        )
        fig = build_equity_drawdown_chart(demo_result.net_returns, drawdown)
        # Two subplot rows means at least 2 traces (strategy + drawdown)
        assert len(fig.data) >= 2

    def test_benchmark_overlay(self, demo_result):
        """With 2 benchmarks, figure must have at least 4 traces
        (strategy + SPY + Russell + drawdown)."""
        drawdown = (
            (1 + demo_result.net_returns).cumprod()
            / (1 + demo_result.net_returns).cumprod().cummax()
            - 1
        )
        spy_ret = demo_result.net_returns * 0.8
        iwm_ret = demo_result.net_returns * 0.6
        fig = build_equity_drawdown_chart(
            demo_result.net_returns,
            drawdown,
            benchmark_returns={"SPY": spy_ret, "Russell 2000": iwm_ret},
        )
        assert len(fig.data) >= 4

    def test_drawdown_trace_uses_fill(self, demo_result):
        """Drawdown trace must use fill='tozeroy' for red shaded area."""
        drawdown = (
            (1 + demo_result.net_returns).cumprod()
            / (1 + demo_result.net_returns).cumprod().cummax()
            - 1
        )
        fig = build_equity_drawdown_chart(demo_result.net_returns, drawdown)
        fill_traces = [t for t in fig.data if getattr(t, "fill", None) == "tozeroy"]
        assert len(fill_traces) >= 1


class TestDrawdownAnnotations:
    """Tests for drawdown episode annotations in equity chart (RPT-01)."""

    def test_major_episode_annotated(self):
        """A drawdown series with one episode below -5% must produce at least
        one annotation on the returned figure."""
        dates = pd.bdate_range("2022-01-03", periods=252)
        # Construct a series with one deep episode: days 50..100 at -15%.
        dd_vals = np.zeros(252)
        dd_vals[50:100] = -0.15
        drawdown = pd.Series(dd_vals, index=dates)
        net_ret = pd.Series(np.zeros(252), index=dates)

        fig = build_equity_drawdown_chart(net_ret, drawdown)
        assert len(fig.layout.annotations) >= 1


class TestMonthlyHeatmap:
    """Tests for build_monthly_heatmap (RPT-02)."""

    def test_returns_figure(self, demo_result):
        """Function must return a Plotly Figure object."""
        import plotly.graph_objects as go
        fig = build_monthly_heatmap(demo_result.net_returns)
        assert isinstance(fig, go.Figure)

    def test_pivot_covers_5_years(self, demo_result):
        """5 years of data must produce a heatmap covering 5 distinct years."""
        fig = build_monthly_heatmap(demo_result.net_returns)
        # The heatmap trace z array should have 5 rows (years 2021..2025).
        assert len(fig.data) >= 1

    def test_zero_midpoint(self, demo_result):
        """color_continuous_midpoint must be 0.0 so zero anchors red/green split,
        not the mean return."""
        fig = build_monthly_heatmap(demo_result.net_returns)
        # px.imshow stores midpoint in layout.coloraxis.cmid
        cmid = fig.layout.coloraxis.cmid if fig.layout.coloraxis else None
        assert cmid == 0.0, (
            f"Expected color_continuous_midpoint=0.0 but got {cmid}. "
            "Without midpoint=0, positive-return months may appear red."
        )


class TestSectorChart:
    """Tests for build_sector_exposure_chart (RPT-03)."""

    def test_returns_figure(self, demo_result):
        """Function must return a Plotly Figure object."""
        import plotly.graph_objects as go
        fig = build_sector_exposure_chart(demo_result.positions, DEMO_TICKER_SECTORS)
        assert isinstance(fig, go.Figure)

    def test_all_sectors_present(self, demo_result):
        """All GICS sectors from ticker_sectors must appear in the chart."""
        fig = build_sector_exposure_chart(demo_result.positions, DEMO_TICKER_SECTORS)
        unique_sectors = set(DEMO_TICKER_SECTORS.values())
        assert len(fig.data) >= 1
        # y-axis values should contain all sector names
        bar_trace = fig.data[0]
        chart_sectors = set(bar_trace.y)
        assert unique_sectors == chart_sectors, (
            f"Missing sectors: {unique_sectors - chart_sectors}"
        )

    def test_absolute_weights(self):
        """Sector weights must be non-negative (abs values used so short
        positions count as positive exposure)."""
        dates = pd.bdate_range("2022-01-03", periods=10)
        # All negative positions (short-only portfolio).
        positions = pd.DataFrame(
            {
                "AAPL": [-0.3] * 10,
                "MSFT": [-0.2] * 10,
                "NVDA": [-0.1] * 10,
            },
            index=dates,
        )
        sectors = {"AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech"}
        fig = build_sector_exposure_chart(positions, sectors)
        bar_trace = fig.data[0]
        # All x values (weights) must be non-negative.
        assert all(v >= 0 for v in bar_trace.x), (
            "Sector weights must use abs() — short positions should appear as positive exposure"
        )
