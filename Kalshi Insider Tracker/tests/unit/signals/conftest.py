"""Shared test fixtures for signal detection unit tests.

Provides: snapshot_factory, mock_session, warmed_warmup, cold_warmup.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from kalshi_tracker.daemon.warmup import WarmupTracker


def snapshot_factory(
    ticker: str,
    volumes: list[int],
    prices: list[int],
    base_time: datetime | None = None,
) -> list[Any]:
    """Build a list of ORM-like MarketSnapshot objects with sequential timestamps.

    Args:
        ticker: Market ticker string.
        volumes: List of volume_24h values (one per snapshot).
        prices: List of last_price values in cents (one per snapshot).
        base_time: Base datetime for timestamps (UTC). Defaults to a fixed UTC time.

    Returns:
        List of MagicMock objects with .ticker, .volume_24h, .last_price, .captured_at.

    Raises:
        ValueError: If volumes and prices have different lengths.
    """
    if len(volumes) != len(prices):
        msg = "volumes and prices must have the same length"
        raise ValueError(msg)

    if base_time is None:
        base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

    snapshots = []
    for i, (vol, price) in enumerate(zip(volumes, prices)):
        snap = MagicMock()
        snap.ticker = ticker
        snap.volume_24h = vol
        snap.last_price = price
        snap.captured_at = base_time + timedelta(seconds=i * 10)
        snapshots.append(snap)

    return snapshots


@pytest.fixture
def mock_session() -> MagicMock:
    """Return a MagicMock session with standard ORM method mocks.

    The session's query chain is set up to be further configured per test:
      session.query(...).filter(...).order_by(...).limit(...).all() returns []
    """
    session = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()

    # Default query chain returns empty list
    query_mock = MagicMock()
    query_mock.filter.return_value = query_mock
    query_mock.order_by.return_value = query_mock
    query_mock.limit.return_value = query_mock
    query_mock.all.return_value = []
    session.query.return_value = query_mock

    return session


@pytest.fixture
def warmed_warmup() -> WarmupTracker:
    """Return a WarmupTracker with threshold=1 that has already warmed up 'TEST-1'.

    Use this fixture when tests need a market that passes the warmup gate.
    """
    tracker = WarmupTracker(threshold=1)
    tracker.record("TEST-1")
    return tracker


@pytest.fixture
def cold_warmup() -> WarmupTracker:
    """Return a WarmupTracker with threshold=100 (never warmed up for any ticker).

    Use this fixture when tests need to verify the warmup gate blocks execution.
    """
    return WarmupTracker(threshold=100)
