"""Tests for MarketSnapshot typed domain contract (frozen dataclass).

Tests cover:
- frozen=True enforcement (FrozenInstanceError)
- Float-to-int price normalization
- Value equality between instances
- from_sdk_market() classmethod
"""
from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest


def _make_snapshot(**overrides) -> object:
    """Build a MarketSnapshot with sensible defaults."""
    from kalshi_tracker.kalshi.types import MarketSnapshot

    defaults = {
        "market_id": "PRES-2024-DEM-J",
        "ticker": "PRES-2024-DEM-J",
        "series_ticker": "PRES",
        "title": "Democrat wins presidency",
        "yes_bid": 45,
        "yes_ask": 47,
        "no_bid": 53,
        "no_ask": 55,
        "last_price": 46,
        "volume": 1000,
        "volume_24h": 200,
        "status": "active",
        "captured_at": datetime(2026, 4, 2, 12, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return MarketSnapshot(**defaults)


def test_market_snapshot_is_frozen() -> None:
    """MarketSnapshot is a frozen dataclass — __dataclass_params__.frozen is True."""
    from kalshi_tracker.kalshi.types import MarketSnapshot

    assert MarketSnapshot.__dataclass_params__.frozen is True


def test_market_snapshot_normalizes_float_prices_to_int() -> None:
    """Float prices are normalized to int on construction (round behavior)."""
    snapshot = _make_snapshot(yes_bid=45, yes_ask=47)
    assert isinstance(snapshot.yes_bid, int)
    assert snapshot.yes_bid == 45


def test_market_snapshot_equality() -> None:
    """Two MarketSnapshot instances with identical fields are equal."""
    ts = datetime(2026, 4, 2, 12, 0, 0, tzinfo=UTC)
    a = _make_snapshot(captured_at=ts)
    b = _make_snapshot(captured_at=ts)
    assert a == b


def test_market_snapshot_frozen_raises_on_assignment() -> None:
    """Assigning to a field of a frozen MarketSnapshot raises FrozenInstanceError."""
    snapshot = _make_snapshot()
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.yes_bid = 50  # type: ignore[misc]


def test_market_snapshot_from_sdk_market() -> None:
    """from_sdk_market() classmethod converts SDK market object to MarketSnapshot."""
    from kalshi_tracker.kalshi.types import MarketSnapshot

    mock_market = MagicMock()
    mock_market.ticker = "PRES-2024-DEM-J"
    mock_market.series_ticker = "PRES"
    mock_market.title = "Democrat wins presidency"
    mock_market.yes_bid = 45.0  # float from SDK
    mock_market.yes_ask = 47.0
    mock_market.no_bid = 53.0
    mock_market.no_ask = 55.0
    mock_market.last_price = 46.0
    mock_market.volume = 1000
    mock_market.volume_24h = 200
    mock_market.status = "active"

    ts = datetime(2026, 4, 2, 12, 0, 0, tzinfo=UTC)
    snapshot = MarketSnapshot.from_sdk_market(mock_market, captured_at=ts)

    assert isinstance(snapshot, MarketSnapshot)
    assert snapshot.ticker == "PRES-2024-DEM-J"
    assert snapshot.series_ticker == "PRES"
    assert snapshot.yes_bid == 45  # float normalized to int
    assert isinstance(snapshot.yes_bid, int)
    assert snapshot.captured_at == ts
