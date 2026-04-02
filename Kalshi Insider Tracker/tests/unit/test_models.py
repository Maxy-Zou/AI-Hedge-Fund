"""Tests for ORM models — LOG-03 (append-only enforcement)."""

from __future__ import annotations

from kalshi_tracker.db.models import Market, MarketSnapshot, Signal, Trade


def test_signal_is_append_only() -> None:
    """LOG-03: Signal model has no update() or delete() class-level methods."""
    assert not hasattr(Signal, "update"), "Signal must not have update() — append-only"
    assert not hasattr(Signal, "delete"), "Signal must not have delete() — append-only"


def test_trade_is_append_only() -> None:
    """LOG-03: Trade model has no update() or delete() class-level methods."""
    assert not hasattr(Trade, "update"), "Trade must not have update() — append-only"
    assert not hasattr(Trade, "delete"), "Trade must not have delete() — append-only"


def test_market_snapshot_is_append_only() -> None:
    """LOG-03: MarketSnapshot model has no update() or delete() class-level methods."""
    assert not hasattr(MarketSnapshot, "update")
    assert not hasattr(MarketSnapshot, "delete")


def test_market_entity_is_mutable() -> None:
    """Market entity table (metadata) is NOT append-only — it is updated on upsert."""
    # Market should NOT inherit from AppendOnlyMixin
    from kalshi_tracker.db.base import AppendOnlyMixin
    assert not isinstance(Market, type) or not issubclass(Market, AppendOnlyMixin)
    # Verify Market has standard mutable columns (last_updated with onupdate)
    assert hasattr(Market, "last_updated")


def test_market_snapshot_tablename() -> None:
    """MarketSnapshot table name is 'market_snapshots'."""
    assert MarketSnapshot.__tablename__ == "market_snapshots"


def test_market_snapshot_prices_are_small_integer() -> None:
    """Prices stored as SmallInteger (0-99 cents), not Float."""
    from sqlalchemy import SmallInteger
    assert isinstance(MarketSnapshot.yes_bid.type, SmallInteger)
    assert isinstance(MarketSnapshot.last_price.type, SmallInteger)


def test_all_datetime_columns_are_timezone_aware() -> None:
    """All DateTime columns must use timezone=True (UTC everywhere)."""
    for col in [MarketSnapshot.captured_at, Signal.detected_at, Trade.placed_at]:
        assert col.type.timezone is True, f"{col} must have timezone=True"
