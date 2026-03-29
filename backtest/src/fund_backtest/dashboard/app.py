"""Streamlit dashboard entry point for fund-backtest.

Renders an interactive investor-facing backtest dashboard with:
  - KPI metrics row (Sharpe, Sortino, Max DD, CAGR, Calmar)
  - Equity curve + drawdown chart with SPY and Russell 2000 overlays (RPT-01)
  - Monthly returns heatmap (RPT-02)
  - Sector exposure breakdown by GICS sector (RPT-03)

Launch command:
    streamlit run backtest/src/fund_backtest/dashboard/app.py

Demo mode (default when no DATABASE_URL is set):
    Uses synthetic 5-year backtest data from dashboard/demo_data.py.
    Set FUND_BACKTEST_DATABASE_URL to connect to a real database.

Note: Do NOT add Typer CLI commands to launch this file — Streamlit starts
its own server and conflicts with Typer's event loop.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
import structlog
import yfinance as yf

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
from fund_backtest.metrics.types import MetricsBundle
from fund_backtest.simulator.types import PortfolioResult

logger = structlog.get_logger(__name__)

st.set_page_config(
    page_title="AI Hedge Fund — Backtest Dashboard",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


@st.cache_data
def _fetch_benchmark_returns(start: str, end: str) -> dict[str, pd.Series]:
    """Fetch SPY and IWM (Russell 2000 proxy) daily returns via yfinance.

    Cached with st.cache_data so repeated Streamlit reruns do not re-download.
    Returns an empty dict if any fetch fails — the equity chart renders
    without benchmark lines rather than crashing.

    Args:
        start: ISO 8601 start date string (e.g. "2021-01-04").
        end: ISO 8601 end date string (e.g. "2025-12-31").

    Returns:
        Dict mapping benchmark display name to daily return Series.
    """
    tickers: dict[str, str] = {"SPY": "SPY", "Russell 2000": "IWM"}
    result: dict[str, pd.Series] = {}
    for name, ticker in tickers.items():
        try:
            df = yf.download(
                ticker,
                start=start,
                end=end,
                progress=False,
                auto_adjust=True,
            )
            if not df.empty:
                series = df["Close"].squeeze().pct_change().dropna()
                if not series.empty:
                    result[name] = series
        except Exception:
            logger.warning("benchmark_fetch_failed", ticker=ticker)
    return result


def _compute_drawdown(net_returns: pd.Series) -> pd.Series:
    """Compute drawdown Series from daily net returns.

    Args:
        net_returns: Daily return Series with DatetimeIndex.

    Returns:
        Drawdown Series with values <= 0 representing percentage below peak.
    """
    cumulative = (1 + net_returns).cumprod()
    rolling_max = cumulative.cummax()
    return (cumulative / rolling_max) - 1


def render_kpi_row(bundle: MetricsBundle) -> None:
    """Render a row of five key performance metric cards.

    Uses st.metric for consistent Streamlit styling. All values are scalar
    floats from MetricsBundle — no mutable state.

    Args:
        bundle: Computed MetricsBundle from MetricsEngine.
    """
    cols = st.columns(5)
    cols[0].metric("Sharpe", f"{bundle.sharpe:.2f}")
    cols[1].metric("Sortino", f"{bundle.sortino:.2f}")
    cols[2].metric("Max DD", f"{bundle.max_drawdown:.1%}")
    cols[3].metric("CAGR", f"{bundle.cagr:.1%}")
    cols[4].metric("Calmar", f"{bundle.calmar:.2f}")


@st.cache_data
def _load_demo_data() -> tuple[PortfolioResult, MetricsBundle]:
    """Load synthetic demo backtest data.

    Cached so repeated Streamlit reruns do not regenerate random data.

    Returns:
        Tuple of (PortfolioResult, MetricsBundle) with synthetic 5-year data.
    """
    result = make_demo_result(seed=42)
    bundle = make_demo_bundle(result)
    logger.info("demo_data_loaded", n_days=len(result.net_returns))
    return result, bundle


# ---------------------------------------------------------------------------
# Main dashboard layout
# ---------------------------------------------------------------------------


def main() -> None:
    """Render the full backtest dashboard.

    Layout:
        1. Header (title + mode banner)
        2. KPI metrics row
        3. Tabs: Performance | Monthly Returns | Sector Exposure
    """
    st.title("AI Hedge Fund — Backtest Dashboard")
    st.caption("Demo mode: showing synthetic 5-year backtest (2021–2025)")

    # Load data (demo mode for Phase 6 — Phase 8 will wire real DB data).
    result, bundle = _load_demo_data()

    # Fetch benchmark returns for equity chart overlay.
    start_date = str(result.net_returns.index[0].date())
    end_date = str(result.net_returns.index[-1].date())
    benchmark_returns = _fetch_benchmark_returns(start_date, end_date)

    if not benchmark_returns:
        st.warning(
            "Benchmark data (SPY, IWM) could not be fetched. "
            "Equity chart will display strategy only."
        )

    # KPI row — scalar metrics at a glance.
    st.subheader("Key Performance Indicators")
    render_kpi_row(bundle)

    st.divider()

    # Drawdown computed once for both the equity chart and sidebar.
    drawdown = _compute_drawdown(result.net_returns)

    # Build figures from pure chart factories.
    equity_fig = build_equity_drawdown_chart(
        net_returns=result.net_returns,
        drawdown=drawdown,
        benchmark_returns=benchmark_returns if benchmark_returns else None,
    )
    heatmap_fig = build_monthly_heatmap(result.net_returns)
    sector_fig = build_sector_exposure_chart(
        positions=result.positions,
        ticker_sectors=DEMO_TICKER_SECTORS,
    )

    # Tab layout — each tab shows one chart.
    tab_perf, tab_returns, tab_sector = st.tabs(
        [
            "Performance",
            "Monthly Returns",
            "Sector Exposure",
        ]
    )

    with tab_perf:
        st.plotly_chart(equity_fig, width="stretch")

    with tab_returns:
        st.plotly_chart(heatmap_fig, width="stretch")

    with tab_sector:
        st.plotly_chart(sector_fig, width="stretch")


if __name__ == "__main__":
    main()
