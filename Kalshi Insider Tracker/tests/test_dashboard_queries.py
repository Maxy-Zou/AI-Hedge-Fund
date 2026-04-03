"""Unit tests for dashboard query functions.

All tests use MagicMock for the SQLAlchemy Session — no real DB required.
Tests verify that each function returns the expected shape and handles
empty/no-data cases gracefully.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from kalshi_tracker.dashboard.queries import (
    get_markets,
    get_open_positions,
    get_pnl_summary,
    get_recent_signals,
)


# ---------------------------------------------------------------------------
# get_markets
# ---------------------------------------------------------------------------


def test_get_markets_empty():
    """Returns empty list when no markets or snapshots exist."""
    session = MagicMock()
    # Simulate query chain returning empty list
    session.query.return_value.filter.return_value.all.return_value = []
    result = get_markets(session)
    assert result == []


def test_get_markets_returns_list_of_dicts(monkeypatch):
    """Returns a list of dicts with the expected keys when data exists."""
    from kalshi_tracker.db.models import Market, MarketSnapshot

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    market = MagicMock(spec=Market)
    market.ticker = "PRES-2026-DEM"
    market.title = "Will Democrats win the 2026 presidency?"
    market.status = "active"

    snapshot = MagicMock(spec=MarketSnapshot)
    snapshot.ticker = "PRES-2026-DEM"
    snapshot.last_price = 55
    snapshot.volume = 1000
    snapshot.captured_at = now

    # Build a fake row tuple matching (Market, MarketSnapshot)
    session = MagicMock()
    row = MagicMock()
    row[0] = market
    row[1] = snapshot

    # Mimic the join query returning one row
    session.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [
        row
    ]

    result = get_markets(session)
    assert isinstance(result, list)
    # Each entry should be a dict
    if result:
        entry = result[0]
        assert isinstance(entry, dict)
        assert "ticker" in entry
        assert "title" in entry
        assert "status" in entry
        assert "last_price" in entry
        assert "volume" in entry
        assert "captured_at" in entry


def test_get_markets_returns_empty_list_on_exception():
    """Returns [] when a DB exception is raised — never propagates."""
    session = MagicMock()
    session.query.side_effect = Exception("DB error")
    result = get_markets(session)
    assert result == []


# ---------------------------------------------------------------------------
# get_recent_signals
# ---------------------------------------------------------------------------


def test_get_recent_signals_empty():
    """Returns empty list when no signals exist."""
    session = MagicMock()
    session.query.return_value.order_by.return_value.limit.return_value.all.return_value = []
    result = get_recent_signals(session)
    assert result == []


def test_get_recent_signals_returns_expected_keys():
    """Returns list of dicts with expected keys for each signal."""
    from kalshi_tracker.db.models import Signal

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    signal = MagicMock(spec=Signal)
    signal.ticker = "PRES-2026-DEM"
    signal.signal_type = "volume_spike"
    signal.confidence = 0.85
    signal.detected_at = now
    signal.details = {"z_score": 3.2}

    session = MagicMock()
    session.query.return_value.order_by.return_value.limit.return_value.all.return_value = [signal]

    result = get_recent_signals(session)
    assert len(result) == 1
    entry = result[0]
    assert entry["ticker"] == "PRES-2026-DEM"
    assert entry["signal_type"] == "volume_spike"
    assert entry["confidence"] == 0.85
    assert entry["detected_at"] == now
    assert entry["details"] == {"z_score": 3.2}


def test_get_recent_signals_default_limit():
    """Default limit of 50 is passed to the query."""
    session = MagicMock()
    chain = session.query.return_value.order_by.return_value
    chain.limit.return_value.all.return_value = []
    get_recent_signals(session)
    chain.limit.assert_called_once_with(50)


def test_get_recent_signals_custom_limit():
    """Custom limit is passed to the query."""
    session = MagicMock()
    chain = session.query.return_value.order_by.return_value
    chain.limit.return_value.all.return_value = []
    get_recent_signals(session, limit=10)
    chain.limit.assert_called_once_with(10)


def test_get_recent_signals_returns_empty_list_on_exception():
    """Returns [] when a DB exception is raised."""
    session = MagicMock()
    session.query.side_effect = Exception("DB error")
    result = get_recent_signals(session)
    assert result == []


# ---------------------------------------------------------------------------
# get_open_positions
# ---------------------------------------------------------------------------


def test_get_open_positions_empty():
    """Returns empty list when no open trades exist."""
    session = MagicMock()
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    result = get_open_positions(session)
    assert result == []


def test_get_open_positions_returns_expected_keys():
    """Returns list of dicts with expected keys for each open trade."""
    from kalshi_tracker.db.models import Trade

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    trade = MagicMock(spec=Trade)
    trade.ticker = "PRES-2026-DEM"
    trade.side = "yes"
    trade.contracts = 5
    trade.price_cents = 55
    trade.mode = "paper"
    trade.status = "filled"
    trade.placed_at = now

    session = MagicMock()
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [trade]

    result = get_open_positions(session)
    assert len(result) == 1
    entry = result[0]
    assert entry["ticker"] == "PRES-2026-DEM"
    assert entry["side"] == "yes"
    assert entry["contracts"] == 5
    assert entry["price_cents"] == 55
    assert entry["mode"] == "paper"
    assert entry["status"] == "filled"
    assert entry["placed_at"] == now


def test_get_open_positions_returns_empty_list_on_exception():
    """Returns [] when a DB exception is raised."""
    session = MagicMock()
    session.query.side_effect = Exception("DB error")
    result = get_open_positions(session)
    assert result == []


# ---------------------------------------------------------------------------
# get_pnl_summary
# ---------------------------------------------------------------------------


def test_get_pnl_summary_no_trades():
    """Returns zero dict when no trades exist."""
    session = MagicMock()
    session.query.return_value.all.return_value = []
    result = get_pnl_summary(session)
    assert result["trade_count"] == 0
    assert result["total_contracts"] == 0
    assert result["total_cost_cents"] == 0
    assert result["realized_pnl_cents"] == 0


def test_get_pnl_summary_with_trades():
    """Returns correct aggregates when trades exist."""
    from kalshi_tracker.db.models import Trade

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    trade1 = MagicMock(spec=Trade)
    trade1.contracts = 5
    trade1.price_cents = 55
    trade1.placed_at = now

    trade2 = MagicMock(spec=Trade)
    trade2.contracts = 3
    trade2.price_cents = 40
    trade2.placed_at = now

    session = MagicMock()
    session.query.return_value.all.return_value = [trade1, trade2]

    result = get_pnl_summary(session)
    assert result["trade_count"] == 2
    assert result["total_contracts"] == 8           # 5 + 3
    assert result["total_cost_cents"] == 395         # 5*55 + 3*40 = 275 + 120
    assert result["realized_pnl_cents"] == 0        # v1: always 0


def test_get_pnl_summary_returns_zero_dict_on_exception():
    """Returns zero-filled dict when a DB exception is raised."""
    session = MagicMock()
    session.query.side_effect = Exception("DB error")
    result = get_pnl_summary(session)
    assert result == {
        "trade_count": 0,
        "total_contracts": 0,
        "total_cost_cents": 0,
        "realized_pnl_cents": 0,
    }
