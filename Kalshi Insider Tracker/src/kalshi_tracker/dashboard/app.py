"""Streamlit monitoring dashboard for Kalshi Insider Tracker.

Displays 4 panels (Markets, Signals, Positions, P&L) in a tab layout.
Auto-refreshes every 10 seconds via time.sleep(10) + st.rerun().

Launch via CLI:
    kalshi-tracker dashboard

Or directly:
    streamlit run src/kalshi_tracker/dashboard/app.py
"""

from __future__ import annotations

import time

import pandas as pd
import streamlit as st
import structlog

from kalshi_tracker.config import load_app_settings
from kalshi_tracker.dashboard.queries import (
    get_markets,
    get_open_positions,
    get_pnl_summary,
    get_recent_signals,
)
from kalshi_tracker.db.session import create_engine_from_settings, get_session_factory
from kalshi_tracker.logging import configure_logging

configure_logging("INFO")
logger = structlog.get_logger(__name__)

# Must be the first Streamlit call in the module — called once at import time
st.set_page_config(page_title="Kalshi Insider Tracker", layout="wide")


@st.cache_resource
def _get_session_factory():
    """Create engine and session factory as a singleton (survives reruns).

    st.cache_resource caches across all sessions — the engine is created
    once and reused on every auto-refresh, avoiding connection churn.

    Returns:
        SQLAlchemy sessionmaker bound to the configured database engine.
    """
    settings = load_app_settings()
    engine = create_engine_from_settings(settings)
    return get_session_factory(engine)


@st.cache_data(ttl=10)
def _load_markets() -> list[dict]:
    """Load active markets with latest snapshot data (cached 10s).

    Returns:
        List of market dicts. Empty list on error.
    """
    try:
        factory = _get_session_factory()
        with factory() as session:
            return get_markets(session)
    except Exception:
        logger.warning("dashboard_load_markets_failed", exc_info=True)
        return []


@st.cache_data(ttl=10)
def _load_signals() -> list[dict]:
    """Load recent anomaly signals (cached 10s).

    Returns:
        List of signal dicts ordered by detected_at DESC. Empty list on error.
    """
    try:
        factory = _get_session_factory()
        with factory() as session:
            return get_recent_signals(session)
    except Exception:
        logger.warning("dashboard_load_signals_failed", exc_info=True)
        return []


@st.cache_data(ttl=10)
def _load_positions() -> list[dict]:
    """Load open (pending/filled) positions (cached 10s).

    Returns:
        List of trade dicts. Empty list on error.
    """
    try:
        factory = _get_session_factory()
        with factory() as session:
            return get_open_positions(session)
    except Exception:
        logger.warning("dashboard_load_positions_failed", exc_info=True)
        return []


@st.cache_data(ttl=10)
def _load_pnl() -> dict:
    """Load aggregate P&L statistics (cached 10s).

    Returns:
        Dict with trade_count, total_contracts, total_cost_cents, realized_pnl_cents.
        Zeroed dict on error.
    """
    try:
        factory = _get_session_factory()
        with factory() as session:
            return get_pnl_summary(session)
    except Exception:
        logger.warning("dashboard_load_pnl_failed", exc_info=True)
        return {
            "trade_count": 0,
            "total_contracts": 0,
            "total_cost_cents": 0,
            "realized_pnl_cents": 0,
        }


def _render_markets_tab(tab) -> None:
    """Render the Markets panel (DASH-01).

    Shows active markets with latest price and volume from the most
    recent snapshot for each market.

    Args:
        tab: Streamlit tab context.
    """
    with tab:
        markets = _load_markets()
        st.metric("Active Markets", len(markets))

        if not markets:
            st.info("No active markets — daemon may not be running yet.")
            return

        df = pd.DataFrame(markets)

        # Format price as percentage probability (Kalshi prices are 0-99 cents)
        if "last_price" in df.columns:
            df["last_price"] = df["last_price"].apply(
                lambda v: f"{v / 100:.0%}" if v is not None else "—"
            )

        # Select and reorder display columns
        display_cols = [c for c in ["ticker", "title", "last_price", "volume", "captured_at"] if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True)


def _render_signals_tab(tab) -> None:
    """Render the Signals panel (DASH-02).

    Shows recent anomaly signals with type, confidence, and timestamp.

    Args:
        tab: Streamlit tab context.
    """
    with tab:
        signals = _load_signals()
        st.metric("Recent Signals (last 50)", len(signals))

        if not signals:
            st.info("No signals detected yet.")
            return

        df = pd.DataFrame(signals)

        # Format confidence as percentage
        if "confidence" in df.columns:
            df["confidence"] = df["confidence"].apply(
                lambda v: f"{v:.0%}" if v is not None else "—"
            )

        # Select and reorder display columns
        display_cols = [c for c in ["ticker", "signal_type", "confidence", "detected_at"] if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True)


def _render_positions_tab(tab) -> None:
    """Render the Positions panel (DASH-03).

    Shows all open (pending/filled) positions.

    Args:
        tab: Streamlit tab context.
    """
    with tab:
        positions = _load_positions()
        st.metric("Open Positions", len(positions))

        if not positions:
            st.info("No open positions.")
            return

        df = pd.DataFrame(positions)

        # Format price_cents as cents display
        if "price_cents" in df.columns:
            df["price_cents"] = df["price_cents"].apply(
                lambda v: f"{v}¢" if v is not None else "—"
            )

        # Select and reorder display columns
        display_cols = [
            c for c in ["ticker", "side", "contracts", "price_cents", "mode", "status", "placed_at"]
            if c in df.columns
        ]
        st.dataframe(df[display_cols], use_container_width=True)


def _render_pnl_tab(tab) -> None:
    """Render the P&L panel (DASH-04).

    Shows running totals: trade count, total contracts, total cost,
    and realized P&L (always $0 in v1 — settled prices not yet stored).

    Args:
        tab: Streamlit tab context.
    """
    with tab:
        pnl = _load_pnl()

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Trades", pnl.get("trade_count", 0))

        with col2:
            st.metric("Total Contracts", pnl.get("total_contracts", 0))

        with col3:
            total_cost = pnl.get("total_cost_cents", 0)
            # Convert cents to dollars for display
            st.metric("Total Cost", f"${total_cost / 100:.2f}")

        with col4:
            realized = pnl.get("realized_pnl_cents", 0)
            st.metric("Realized P&L", f"${realized / 100:.2f}")

        st.info("Realized P&L shows $0 in v1 — settled prices not yet stored.")


def main() -> None:
    """Main dashboard layout: title, 4-panel tabs, auto-refresh."""
    st.title("Kalshi Insider Tracker — Live Dashboard")
    st.caption("Auto-refreshes every 10 seconds")

    tab_markets, tab_signals, tab_positions, tab_pnl = st.tabs(
        ["Markets", "Signals", "Positions", "P&L"]
    )

    _render_markets_tab(tab_markets)
    _render_signals_tab(tab_signals)
    _render_positions_tab(tab_positions)
    _render_pnl_tab(tab_pnl)

    # Auto-refresh: sleep then rerun so the dashboard stays live without manual reload
    time.sleep(10)
    st.rerun()


if __name__ == "__main__":
    main()
