"""Read-only database query functions for the monitoring dashboard.

All functions accept a SQLAlchemy Session and return plain dicts/lists.
Never write to the database — dashboard is strictly read-only.

Four query functions:
  - get_markets(session): active markets with latest snapshot data
  - get_recent_signals(session, limit): most recent anomaly signals
  - get_open_positions(session): pending and filled trades
  - get_pnl_summary(session): aggregate trade statistics
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.orm import Session

from kalshi_tracker.db.models import Market, MarketSnapshot, Signal, Trade

logger = structlog.get_logger(__name__)


def get_markets(session: Session) -> list[dict[str, Any]]:
    """Return active markets with their most recent snapshot data.

    Uses a subquery to find the max(captured_at) per ticker from
    market_snapshots, then joins to retrieve the latest snapshot for each
    active market.

    Args:
        session: SQLAlchemy Session (read-only — no writes).

    Returns:
        List of dicts with keys: ticker, title, status, last_price,
        volume, captured_at. One entry per active market. Empty list
        when no data or on error.
    """
    try:
        from sqlalchemy import func

        # Subquery: max(captured_at) per ticker to identify the latest snapshot
        latest_sq = (
            session.query(
                MarketSnapshot.ticker.label("ticker"),
                func.max(MarketSnapshot.captured_at).label("max_captured_at"),
            )
            .group_by(MarketSnapshot.ticker)
            .subquery()
        )

        # Join Market + MarketSnapshot + latest_sq to retrieve the latest snapshot
        # for each active market in a single query
        rows = (
            session.query(Market, MarketSnapshot)
            .join(
                latest_sq,
                (MarketSnapshot.ticker == latest_sq.c.ticker)
                & (MarketSnapshot.captured_at == latest_sq.c.max_captured_at),
            )
            .join(Market, Market.ticker == MarketSnapshot.ticker)
            .filter(Market.status == "active")
            .all()
        )

        return [
            {
                "ticker": market.ticker,
                "title": market.title,
                "status": market.status,
                "last_price": snapshot.last_price,
                "volume": snapshot.volume,
                "captured_at": snapshot.captured_at,
            }
            for market, snapshot in rows
        ]
    except Exception:
        logger.warning("get_markets_failed", exc_info=True)
        return []


def get_recent_signals(session: Session, limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent anomaly signals ordered by detection time.

    Args:
        session: SQLAlchemy Session (read-only — no writes).
        limit: Maximum number of signals to return. Defaults to 50.

    Returns:
        List of dicts with keys: ticker, signal_type, confidence,
        detected_at, details. Ordered by detected_at DESC. Empty list
        when no data or on error.
    """
    try:
        signals = (
            session.query(Signal)
            .order_by(Signal.detected_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "ticker": s.ticker,
                "signal_type": s.signal_type,
                "confidence": s.confidence,
                "detected_at": s.detected_at,
                "details": s.details,
            }
            for s in signals
        ]
    except Exception:
        logger.warning("get_recent_signals_failed", exc_info=True)
        return []


def get_open_positions(session: Session) -> list[dict[str, Any]]:
    """Return all pending and filled trades (open positions).

    Filters to trades with status IN ('pending', 'filled'). Rejected
    trades are excluded. Ordered by placed_at DESC.

    Args:
        session: SQLAlchemy Session (read-only — no writes).

    Returns:
        List of dicts with keys: ticker, side, contracts, price_cents,
        mode, status, placed_at. Empty list when no data or on error.
    """
    try:
        trades = (
            session.query(Trade)
            .filter(Trade.status.in_(["pending", "filled"]))
            .order_by(Trade.placed_at.desc())
            .all()
        )
        return [
            {
                "ticker": t.ticker,
                "side": t.side,
                "contracts": t.contracts,
                "price_cents": t.price_cents,
                "mode": t.mode,
                "status": t.status,
                "placed_at": t.placed_at,
            }
            for t in trades
        ]
    except Exception:
        logger.warning("get_open_positions_failed", exc_info=True)
        return []


def get_pnl_summary(session: Session) -> dict[str, int]:
    """Return aggregate P&L statistics across all trades.

    Computes total contracts, total cost, and trade count from all
    trade records (any status). realized_pnl_cents is always 0 in v1
    because Kalshi settled prices are not yet stored in the database.

    Args:
        session: SQLAlchemy Session (read-only — no writes).

    Returns:
        Dict with keys:
          - trade_count (int): total number of trades placed
          - total_contracts (int): sum of contracts across all trades
          - total_cost_cents (int): sum of contracts * price_cents
          - realized_pnl_cents (int): always 0 in v1 — see TODO below

    TODO: Compute realized_pnl_cents from settled trades once Kalshi
          provides settled prices in the DB (post-v1 schema update).
    """
    _empty: dict[str, int] = {
        "trade_count": 0,
        "total_contracts": 0,
        "total_cost_cents": 0,
        "realized_pnl_cents": 0,
    }
    try:
        trades = session.query(Trade).all()
        return {
            "trade_count": len(trades),
            "total_contracts": sum(t.contracts for t in trades),
            "total_cost_cents": sum(t.contracts * t.price_cents for t in trades),
            "realized_pnl_cents": 0,  # TODO: compute from settled trades when available
        }
    except Exception:
        logger.warning("get_pnl_summary_failed", exc_info=True)
        return _empty
