"""Interactive Plotly dashboard for Kalshi backtest results.

Provides:
    compute_category_breakdown: Groups trade log rows by ticker prefix (category).
    build_dashboard: Builds a 4-panel Plotly Figure from BacktestMetrics + trade log.
    DashboardBuilder: Convenience class that writes an HTML dashboard to disk.

The generated HTML is self-contained and uses CDN Plotly JS to keep file size small.
Open the output file in any browser — no server required.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import quantstats as qs
from plotly.subplots import make_subplots

from kalshi_backtest.metrics.calculator import BacktestMetrics

# Maximum number of trade scatter markers to include on the equity curve.
# Limits HTML file size for large backtests.
_MAX_TRADE_MARKERS = 200


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_category(ticker: str) -> str:
    """Extract the series/category prefix from a Kalshi ticker.

    Splits on '-' and returns the first segment.  For example:
        'KXBTC-A' -> 'KXBTC'
        'KXETH-2024-01' -> 'KXETH'

    Args:
        ticker: A Kalshi market ticker string.

    Returns:
        The first dash-delimited segment of the ticker.
    """
    return ticker.split("-")[0]


# ---------------------------------------------------------------------------
# Public API — category breakdown
# ---------------------------------------------------------------------------


def compute_category_breakdown(trade_log: pd.DataFrame) -> pd.DataFrame:
    """Group trade log rows by ticker category prefix and compute performance stats.

    Category is the first '-'-delimited segment of each ticker
    (e.g. 'KXBTC-A' -> 'KXBTC').

    Args:
        trade_log: DataFrame with at least 'ticker' and 'pnl_cents' columns.
                   The input is not mutated.

    Returns:
        DataFrame with columns ['category', 'trades', 'win_rate_pct', 'net_pnl_cents'].
        Returns an empty DataFrame with those columns if trade_log is empty.
    """
    empty_result = pd.DataFrame(
        columns=["category", "trades", "win_rate_pct", "net_pnl_cents"]
    )

    if trade_log.empty:
        return empty_result

    # Work on a copy — never mutate input
    df = trade_log.copy()
    df["category"] = df["ticker"].map(_extract_category)
    df["win"] = df["pnl_cents"] > 0

    breakdown = (
        df.groupby("category")
        .agg(
            trades=("pnl_cents", "count"),
            win_rate_pct=("win", lambda s: round(s.mean() * 100, 1)),
            net_pnl_cents=("pnl_cents", "sum"),
        )
        .reset_index()
    )

    return breakdown


# ---------------------------------------------------------------------------
# Public API — dashboard builder
# ---------------------------------------------------------------------------


def build_dashboard(metrics: BacktestMetrics, trade_log: pd.DataFrame) -> go.Figure:
    """Build a 4-panel interactive Plotly Figure for a backtest result.

    Layout (3 rows × 2 columns):
        (1,1) Equity curve
        (1,2) Drawdown
        (2,1) Monthly P&L bar chart
        (2,2) Per-category net P&L bar chart
        (3,1) Per-category win rate bar chart
        (3,2) Empty

    A sample-size warning annotation is added to the figure when
    metrics.sample_size_warning is True.

    Trade markers on the equity curve are limited to the top
    _MAX_TRADE_MARKERS trades by abs(pnl_cents) to keep HTML size small.

    Args:
        metrics: Computed BacktestMetrics for the backtest run.
        trade_log: Trade log DataFrame from PositionTracker.to_trade_log().

    Returns:
        A populated plotly.graph_objects.Figure ready to render or export.
    """
    fig = make_subplots(
        rows=3,
        cols=2,
        subplot_titles=(
            "Equity Curve",
            "Drawdown",
            "Monthly P&L ($)",
            "Category Net P&L (cents)",
            "Category Win Rate (%)",
            "",
        ),
        row_heights=[0.4, 0.3, 0.3],
        vertical_spacing=0.10,
    )

    # ------------------------------------------------------------------
    # Panel (1,1): Equity curve
    # ------------------------------------------------------------------
    if not metrics.equity_curve.empty:
        fig.add_trace(
            go.Scatter(
                x=metrics.equity_curve.index,
                y=metrics.equity_curve.values,
                name="Equity",
                mode="lines",
                line=dict(color="#1f77b4", width=2),
            ),
            row=1,
            col=1,
        )

        # Optional: top trade markers on the equity curve
        if not trade_log.empty and "pnl_cents" in trade_log.columns:
            marker_df = trade_log.copy()
            # Select top by abs(pnl_cents) to limit marker count
            marker_df = marker_df.reindex(
                marker_df["pnl_cents"].abs().nlargest(_MAX_TRADE_MARKERS).index
            )
            if "entry_ts" in marker_df.columns:
                colors = marker_df["pnl_cents"].apply(
                    lambda v: "#2ca02c" if v > 0 else "#d62728"
                )
                eq = metrics.equity_curve
                has_asof = hasattr(eq, "asof")
                y_vals = [
                    eq.asof(pd.Timestamp(ts)) if has_asof else 0
                    for ts in marker_df["entry_ts"]
                ]
                fig.add_trace(
                    go.Scatter(
                        x=pd.to_datetime(marker_df["entry_ts"]),
                        y=y_vals,
                        mode="markers",
                        name="Trades",
                        marker=dict(color=colors, size=6, symbol="circle"),
                        showlegend=True,
                    ),
                    row=1,
                    col=1,
                )
    else:
        # Provide an empty placeholder so the subplot still renders
        fig.add_trace(
            go.Scatter(x=[], y=[], name="Equity", mode="lines"),
            row=1,
            col=1,
        )

    # ------------------------------------------------------------------
    # Panel (1,2): Drawdown
    # ------------------------------------------------------------------
    try:
        if not metrics.daily_returns.empty:
            drawdown = qs.stats.to_drawdown_series(metrics.daily_returns)
            fig.add_trace(
                go.Scatter(
                    x=drawdown.index,
                    y=(drawdown * 100).values,
                    name="Drawdown %",
                    mode="lines",
                    fill="tozeroy",
                    line=dict(color="#d62728", width=1),
                ),
                row=1,
                col=2,
            )
        else:
            fig.add_trace(
                go.Scatter(x=[], y=[], name="Drawdown %", mode="lines"),
                row=1,
                col=2,
            )
    except Exception:
        fig.add_trace(
            go.Scatter(x=[], y=[], name="Drawdown %", mode="lines"),
            row=1,
            col=2,
        )

    # ------------------------------------------------------------------
    # Panel (2,1): Monthly P&L bar chart
    # ------------------------------------------------------------------
    try:
        if not metrics.equity_curve.empty:
            # Convert cumulative equity to daily pnl, then resample to month-end
            # Use 'ME' (month-end) — pandas 3.x deprecates 'M'
            daily_pnl_dollars = metrics.equity_curve.diff().fillna(metrics.equity_curve.iloc[0])
            monthly_pnl = daily_pnl_dollars.resample("ME").sum()
            fig.add_trace(
                go.Bar(
                    x=monthly_pnl.index,
                    y=monthly_pnl.values,
                    name="Monthly P&L",
                    marker_color=[
                        "#2ca02c" if v >= 0 else "#d62728" for v in monthly_pnl.values
                    ],
                ),
                row=2,
                col=1,
            )
        else:
            fig.add_trace(
                go.Bar(x=[], y=[], name="Monthly P&L"),
                row=2,
                col=1,
            )
    except Exception:
        fig.add_trace(
            go.Bar(x=[], y=[], name="Monthly P&L"),
            row=2,
            col=1,
        )

    # ------------------------------------------------------------------
    # Panel (2,2): Per-category net P&L and Panel (3,1): win rate
    # ------------------------------------------------------------------
    breakdown = compute_category_breakdown(trade_log)

    if not breakdown.empty:
        fig.add_trace(
            go.Bar(
                x=breakdown["category"],
                y=breakdown["net_pnl_cents"],
                name="Net P&L (cents)",
                marker_color=[
                    "#2ca02c" if v >= 0 else "#d62728"
                    for v in breakdown["net_pnl_cents"]
                ],
            ),
            row=2,
            col=2,
        )
        fig.add_trace(
            go.Bar(
                x=breakdown["category"],
                y=breakdown["win_rate_pct"],
                name="Win Rate %",
                marker_color="#1f77b4",
            ),
            row=3,
            col=1,
        )
    else:
        fig.add_trace(go.Bar(x=[], y=[], name="Net P&L (cents)"), row=2, col=2)
        fig.add_trace(go.Bar(x=[], y=[], name="Win Rate %"), row=3, col=1)

    # Panel (3,2): intentionally empty

    # ------------------------------------------------------------------
    # Sample size warning annotation
    # ------------------------------------------------------------------
    if metrics.sample_size_warning:
        settled = getattr(metrics, "settled_markets", 0)
        fig.add_annotation(
            text=(
                f"Warning: N={settled} settled markets — "
                "results may be unreliable (N<30)"
            ),
            xref="paper",
            yref="paper",
            x=0.5,
            y=1.05,
            showarrow=False,
            font=dict(color="orange", size=13),
        )

    fig.update_layout(
        title_text=f"Backtest Dashboard — {getattr(metrics, 'strategy_name', '')}",
        height=900,
        showlegend=True,
    )

    return fig


# ---------------------------------------------------------------------------
# DashboardBuilder — convenience wrapper
# ---------------------------------------------------------------------------


class DashboardBuilder:
    """Builds and exports an interactive Plotly dashboard to an HTML file.

    Usage:
        builder = DashboardBuilder(metrics, trade_log)
        builder.write_html("output/dashboard.html")

    The generated HTML file is self-contained (CDN Plotly JS) and opens
    in any browser without a server.
    """

    def __init__(self, metrics: BacktestMetrics, trade_log: pd.DataFrame) -> None:
        """Initialise the builder with computed metrics and trade log.

        Args:
            metrics: BacktestMetrics from MetricsCalculator.compute().
            trade_log: Trade log DataFrame from PositionTracker.to_trade_log().
        """
        self._metrics = metrics
        self._trade_log = trade_log

    def write_html(self, output_path: str | Path) -> None:
        """Build the dashboard and write it as a self-contained HTML file.

        Uses include_plotlyjs="cdn" so the file is small — the browser fetches
        Plotly JS from cdn.plot.ly at render time.

        Args:
            output_path: Destination path for the HTML file (str or Path).
        """
        fig = build_dashboard(self._metrics, self._trade_log)
        fig.write_html(str(output_path), full_html=True, include_plotlyjs="cdn")
