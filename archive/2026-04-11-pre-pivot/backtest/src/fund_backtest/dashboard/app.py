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

import os

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


@st.cache_data
def _load_live_data() -> tuple[PortfolioResult, MetricsBundle, dict[str, str]] | None:
    """Run the backtest pipeline and return real results + sector map.

    Uses lazy imports to avoid Typer/Click initialization from importing cli.py.
    Creates its own engine and session — cannot accept session as argument
    because st.cache_data cannot serialize SQLAlchemy objects.

    Returns:
        Tuple of (PortfolioResult, MetricsBundle, ticker_sectors dict) on success.
        None if DATABASE_URL is not configured or pipeline raises any exception.
    """
    if not os.environ.get("FUND_BACKTEST_DATABASE_URL"):
        return None
    try:
        # Lazy imports — avoids Typer app initialization at module load time.
        from pydantic import ValidationError

        from fund_backtest.config import load_app_settings
        from fund_backtest.db.models import UniverseTicker
        from fund_backtest.db.session import create_engine_from_settings, get_session_factory
        from fund_backtest.metrics.engine import MetricsEngine
        from fund_backtest.price.repository import PriceBarRepository
        from fund_backtest.signal.adapter import SignalAdapter
        from fund_backtest.signal.loaders import AiWashingLoader
        from fund_backtest.simulator.engine import PortfolioSimulator
        import yfinance as yf

        try:
            settings = load_app_settings()
        except ValidationError:
            logger.warning("live_data_load_failed", reason="DATABASE_URL validation failed")
            return None

        engine = create_engine_from_settings(settings)
        session_factory = get_session_factory(engine)

        with session_factory() as session:
            # Stage 1: Load signal
            loader = AiWashingLoader(session)
            signal_frame = loader.load()
            logger.info(
                "live_signal_loaded",
                n_dates=len(signal_frame),
                n_tickers=len(signal_frame.columns),
            )

            # Stage 2: Load price data
            repo = PriceBarRepository(session)
            tickers = list(signal_frame.columns)
            start = signal_frame.index.min().date()
            end = signal_frame.index.max().date()
            bars = repo.get_bars(tickers=tickers, start_date=start, end_date=end)
            records = [
                {"date": b.bar_date, "ticker": b.ticker, "close": b.close_cents / 100}
                for b in bars
            ]
            price_df = pd.DataFrame(records)
            price_frame = price_df.pivot_table(
                index="date", columns="ticker", values="close"
            )
            price_frame.index = pd.DatetimeIndex(pd.to_datetime(price_frame.index))
            price_frame.columns.name = None

            # FIX-02: Intersect dates before adapt() (mirrors cli.py fix)
            common_dates = signal_frame.index.intersection(price_frame.index)
            if len(common_dates) == 0:
                logger.warning("live_data_load_failed", reason="no overlapping dates")
                return None
            signal_frame = signal_frame.loc[common_dates]

            # Stage 3: Adapt
            weight_frame = SignalAdapter().adapt(signal_frame)

            # Stage 4: Simulate
            portfolio_result = PortfolioSimulator().simulate(weight_frame, price_frame)

            # FIX-05: Benchmark fetch (mirrors cli.py fix)
            benchmark_returns: pd.Series | None = None
            try:
                spy_df = yf.download(
                    "SPY",
                    start=str(portfolio_result.net_returns.index[0].date()),
                    end=str(portfolio_result.net_returns.index[-1].date()),
                    progress=False,
                    auto_adjust=True,
                )
                if not spy_df.empty:
                    benchmark_returns = spy_df["Close"].squeeze().pct_change().dropna()
            except Exception:
                logger.warning("benchmark_fetch_failed", ticker="SPY")

            # Stage 5: Metrics
            bundle = MetricsEngine().compute(portfolio_result, benchmark=benchmark_returns)

            # Sector map: query active tickers for real GICS data
            active_tickers = session.query(UniverseTicker).filter_by(is_active=True).all()
            ticker_sectors: dict[str, str] = {
                t.ticker: t.gics_sector
                for t in active_tickers
                if t.gics_sector
            }

        logger.info("live_data_loaded", n_days=len(portfolio_result.net_returns))
        return portfolio_result, bundle, ticker_sectors

    except Exception as exc:
        logger.warning("live_data_load_failed", error=str(exc))
        return None


def _load_data() -> tuple[PortfolioResult, MetricsBundle, dict[str, str], bool]:
    """Load backtest data: live mode if DATABASE_URL is set, demo otherwise.

    Returns:
        Tuple of (PortfolioResult, MetricsBundle, ticker_sectors, is_live).
        is_live=True when real pipeline data was loaded.
    """
    live = _load_live_data()
    if live is not None:
        result, bundle, ticker_sectors = live
        return result, bundle, ticker_sectors, True
    result, bundle = _load_demo_data()
    return result, bundle, DEMO_TICKER_SECTORS, False


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

    result, bundle, ticker_sectors, is_live = _load_data()
    if is_live:
        st.caption("Live mode — AI Washing signal, real SEC filing data")
    else:
        st.caption("Demo mode: showing synthetic 5-year backtest (2021–2025)")
        if os.environ.get("FUND_BACKTEST_DATABASE_URL"):
            st.warning(
                "Database URL is set but pipeline failed to load live data. "
                "Check logs for details."
            )

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
        ticker_sectors=ticker_sectors,
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
