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
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Constants — no inline magic values.
_DRAWDOWN_EPISODE_THRESHOLD: float = -0.05
_STRATEGY_COLOUR: str = "#1f77b4"
_DRAWDOWN_FILL_COLOUR: str = "rgba(220,50,50,0.3)"
_DRAWDOWN_LINE_COLOUR: str = "rgba(220,50,50,0.8)"
_MONTH_LABELS: list[str] = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def _annotate_drawdown_episodes(
    fig: go.Figure,
    drawdown: pd.Series,
    threshold: float = _DRAWDOWN_EPISODE_THRESHOLD,
    row: int = 2,
) -> None:
    """Annotate major drawdown episodes on a figure subplot.

    Finds contiguous segments where drawdown < threshold and adds a text
    annotation at each episode's maximum-depth point showing depth and
    duration in trading days.

    Handles episodes that extend to the last row of the series (no closing
    transition before the end of data).

    Args:
        fig: Plotly Figure to add annotations to (mutated in-place).
        drawdown: Drawdown Series (values <= 0) with DatetimeIndex.
        threshold: Depth threshold below which an episode is annotated.
                   Default is -0.05 (5% drawdown).
        row: Subplot row number for the annotation.
    """
    in_episode = drawdown < threshold
    episode_start: int | None = None

    for i in range(len(drawdown)):
        if in_episode.iloc[i] and episode_start is None:
            episode_start = i
        elif not in_episode.iloc[i] and episode_start is not None:
            episode_slice = drawdown.iloc[episode_start:i]
            min_idx = episode_slice.idxmin()
            min_val = episode_slice.min()
            duration = i - episode_start
            fig.add_annotation(
                x=min_idx,
                y=min_val,
                text=f"{min_val:.1%} ({duration}d)",
                showarrow=True,
                arrowhead=2,
                row=row,
                col=1,
            )
            episode_start = None

    # Handle episode that extends to end of series.
    if episode_start is not None:
        episode_slice = drawdown.iloc[episode_start:]
        min_idx = episode_slice.idxmin()
        min_val = episode_slice.min()
        duration = len(drawdown) - episode_start
        fig.add_annotation(
            x=min_idx,
            y=min_val,
            text=f"{min_val:.1%} ({duration}d)",
            showarrow=True,
            arrowhead=2,
            row=row,
            col=1,
        )


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
    """
    if net_returns is None or len(net_returns) < 2:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="Insufficient data", showarrow=False,
        )
        return fig

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.65, 0.35],
        vertical_spacing=0.03,
    )

    # Equity curve trace in row 1.
    equity = (1 + net_returns).cumprod() - 1
    fig.add_trace(
        go.Scatter(
            x=equity.index,
            y=equity.values,
            name="Strategy",
            line={"color": _STRATEGY_COLOUR, "width": 2},
        ),
        row=1,
        col=1,
    )

    # Benchmark overlays (dashed) in row 1.
    for name, bm_ret in (benchmark_returns or {}).items():
        bm_eq = (1 + bm_ret).cumprod() - 1
        fig.add_trace(
            go.Scatter(
                x=bm_eq.index,
                y=bm_eq.values,
                name=name,
                line={"dash": "dash"},
            ),
            row=1,
            col=1,
        )

    # Drawdown fill in row 2.
    fig.add_trace(
        go.Scatter(
            x=drawdown.index,
            y=drawdown.values,
            fill="tozeroy",
            fillcolor=_DRAWDOWN_FILL_COLOUR,
            line={"color": _DRAWDOWN_LINE_COLOUR, "width": 1},
            name="Drawdown",
        ),
        row=2,
        col=1,
    )

    # Annotate major drawdown episodes.
    _annotate_drawdown_episodes(fig, drawdown, _DRAWDOWN_EPISODE_THRESHOLD, row=2)

    fig.update_layout(
        title="Equity Curve & Drawdown",
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
    )
    fig.update_yaxes(tickformat=".1%", row=1, col=1, title_text="Cumulative Return")
    fig.update_yaxes(tickformat=".1%", row=2, col=1, title_text="Drawdown")

    return fig


def build_monthly_heatmap(net_returns: pd.Series) -> go.Figure:
    """Build a year x month heatmap of monthly returns.

    Each cell shows the compounded monthly return for that calendar month,
    colour-coded red (negative) to green (positive) with zero as the midpoint.

    CRITICAL: color_continuous_midpoint=0.0 must be applied so zero anchors
    the red/green split — not the data mean.

    Uses "ME" (month-end) resampling for pandas 3.x compatibility.

    Args:
        net_returns: Daily net return Series with DatetimeIndex.

    Returns:
        Plotly Figure with RdYlGn heatmap. (RPT-02)
    """
    if net_returns is None or len(net_returns) < 2:
        fig = go.Figure()
        fig.add_annotation(
            x=0.5, y=0.5, xref="paper", yref="paper",
            text="Insufficient data", showarrow=False,
        )
        return fig

    # CRITICAL: "ME" not "M" — pandas 3.x uses month-end alias "ME".
    monthly = (1 + net_returns).resample("ME").prod() - 1
    pivot = monthly.groupby([monthly.index.year, monthly.index.month]).first().unstack(level=1)
    pivot.columns = [_MONTH_LABELS[m - 1] for m in pivot.columns]
    pivot.index = pivot.index.astype(str)

    fig = px.imshow(
        pivot,
        labels={"x": "Month", "y": "Year", "color": "Return"},
        color_continuous_scale="RdYlGn",
        color_continuous_midpoint=0.0,
        text_auto=".1%",
        aspect="auto",
    )
    fig.update_layout(title="Monthly Returns Heatmap")
    fig.update_coloraxes(colorbar_tickformat=".0%")

    return fig


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
    """
    sector_map = pd.Series(ticker_sectors)
    valid = positions.columns.intersection(sector_map.index)
    sector_weights = (
        positions[valid].abs().mean()
        .groupby(sector_map[valid]).sum()
        .sort_values(ascending=True)
    )

    fig = go.Figure(
        go.Bar(
            x=sector_weights.values,
            y=sector_weights.index,
            orientation="h",
            marker_color=_STRATEGY_COLOUR,
            text=[f"{v:.1%}" for v in sector_weights.values],
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Sector Exposure (Mean Absolute Weight)",
        xaxis_tickformat=".0%",
        xaxis_title="Portfolio Weight",
        yaxis_title="GICS Sector",
        margin={"l": 200},
    )

    return fig
