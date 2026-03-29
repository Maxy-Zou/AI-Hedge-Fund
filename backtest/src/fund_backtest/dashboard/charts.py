"""Pure Plotly chart factory functions for the backtest dashboard.

This module contains NO streamlit imports. All functions return go.Figure
objects that app.py renders via st.plotly_chart(). Keeping Plotly logic
here makes the charts independently testable without a Streamlit session.

All functions return NEW Figure objects — arguments are never mutated.

Constants:
    _DRAWDOWN_EPISODE_THRESHOLD: Minimum drawdown depth to annotate (-5%).
    _STRATEGY_COLOUR: Hex colour for strategy equity curve line.
    _DRAWDOWN_FILL_COLOUR: RGBA fill colour for drawdown area.
    _MONTH_LABELS: 12-element list of abbreviated month names (Jan..Dec).
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# Constants — no inline magic values.
_DRAWDOWN_EPISODE_THRESHOLD: float = -0.05
_STRATEGY_COLOUR: str = "#1f77b4"
_DRAWDOWN_FILL_COLOUR: str = "rgba(220,50,50,0.3)"
_DRAWDOWN_LINE_COLOUR: str = "rgba(220,50,50,0.8)"
_MONTH_LABELS: list[str] = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def build_equity_drawdown_chart(
    net_returns: pd.Series,
    drawdown: pd.Series,
    benchmark_returns: dict[str, pd.Series] | None = None,
) -> go.Figure:
    """Build a two-panel equity curve + drawdown figure.

    Row 1 (65%): Cumulative return lines for strategy and any benchmarks.
    Row 2 (35%): Drawdown as a filled red area below zero.
    Major drawdown episodes (depth < -5%) are annotated with depth and duration.

    Args:
        net_returns: Daily net return Series with DatetimeIndex.
        drawdown: Drawdown Series (values <= 0) with DatetimeIndex.
        benchmark_returns: Optional dict of name -> daily return Series
                           for benchmark overlay traces.

    Returns:
        Plotly Figure with two subplots sharing the x-axis. (RPT-01)

    Raises:
        NotImplementedError: Implementation pending (Wave 2).
    """
    raise NotImplementedError("build_equity_drawdown_chart — implement in Wave 2")


def build_monthly_heatmap(net_returns: pd.Series) -> go.Figure:
    """Build a year x month heatmap of monthly returns.

    Each cell shows the compounded monthly return for that calendar month,
    colour-coded red (negative) to green (positive) with zero as the midpoint.

    CRITICAL: color_continuous_midpoint=0.0 must be applied so zero anchors
    the red/green split — not the data mean.

    Args:
        net_returns: Daily net return Series with DatetimeIndex.

    Returns:
        Plotly Figure with RdYlGn heatmap. (RPT-02)

    Raises:
        NotImplementedError: Implementation pending (Wave 2).
    """
    raise NotImplementedError("build_monthly_heatmap — implement in Wave 2")


def build_sector_exposure_chart(
    positions: pd.DataFrame,
    ticker_sectors: dict[str, str],
) -> go.Figure:
    """Build a horizontal bar chart of mean absolute sector exposure.

    Sector weights are computed as the time-average of absolute position
    weights per ticker, grouped by GICS sector. Using absolute values means
    both long and short positions contribute positively to sector exposure.

    Args:
        positions: Date x ticker weight DataFrame from PortfolioResult.
        ticker_sectors: Mapping from ticker symbol to GICS sector name.

    Returns:
        Plotly Figure with horizontal bar chart sorted ascending. (RPT-03)

    Raises:
        NotImplementedError: Implementation pending (Wave 2).
    """
    raise NotImplementedError("build_sector_exposure_chart — implement in Wave 2")
