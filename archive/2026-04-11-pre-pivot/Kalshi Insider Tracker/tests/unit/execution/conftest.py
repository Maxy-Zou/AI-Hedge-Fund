"""Shared test fixtures for execution layer unit tests.

Provides: mock_session_factory, signal_factory, trade_factory.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_session_factory() -> tuple[MagicMock, MagicMock]:
    """Return (factory, session) tuple following the established project mock_session_factory pattern.

    The factory is a callable that returns a context-manager-compatible session.
    The session supports: .add(), .commit(), .query().filter().order_by().limit().all()

    Returns:
        Tuple of (factory MagicMock, session MagicMock).
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

    # Context manager protocol
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    factory = MagicMock(return_value=session)
    factory.return_value.__enter__ = MagicMock(return_value=session)
    factory.return_value.__exit__ = MagicMock(return_value=False)

    return factory, session


@pytest.fixture
def signal_factory() -> Any:
    """Return a callable that creates Signal-like MagicMock objects.

    The factory returns a MagicMock with Signal ORM field names populated.
    Matches the Signal ORM schema: ticker, signal_type, confidence, details, detected_at, id.

    Returns:
        Callable accepting keyword overrides and returning a Signal MagicMock.
    """

    def _make_signal(
        ticker: str = "PRES-2024-R",
        signal_type: str = "volume_spike",
        confidence: float = 0.8,
        direction: str = "yes",
        current_price: int = 45,
        contracts: int = 100,
        detected_at: datetime | None = None,
    ) -> MagicMock:
        """Build a Signal MagicMock with given parameters.

        Args:
            ticker: Market ticker.
            signal_type: Signal type string.
            confidence: Confidence float (0.0-1.0).
            direction: Trade direction ('yes' or 'no').
            current_price: Current market price in cents.
            contracts: Number of contracts for the trade.
            detected_at: Signal detection datetime (UTC). Defaults to now.

        Returns:
            MagicMock representing a Signal ORM object.
        """
        signal = MagicMock()
        signal.id = uuid.uuid4()
        signal.ticker = ticker
        signal.signal_type = signal_type
        signal.confidence = confidence
        signal.details = {
            "direction": direction,
            "current_price": current_price,
            "contracts": contracts,
        }
        signal.detected_at = detected_at or datetime.now(tz=UTC)
        return signal

    return _make_signal


@pytest.fixture
def trade_factory() -> Any:
    """Return a callable that creates Trade-like MagicMock objects.

    The factory returns a MagicMock with Trade ORM field names populated.
    Matches the Trade ORM schema: ticker, side, contracts, price_cents, mode, status, placed_at.

    Returns:
        Callable accepting keyword overrides and returning a Trade MagicMock.
    """

    def _make_trade(
        ticker: str = "PRES-2024-R",
        side: str = "yes",
        contracts: int = 100,
        price_cents: int = 45,
        mode: str = "live",
        status: str = "filled",
        placed_at: datetime | None = None,
        kalshi_order_id: str | None = None,
    ) -> MagicMock:
        """Build a Trade MagicMock with given parameters.

        Args:
            ticker: Market ticker.
            side: Trade side ('yes' or 'no').
            contracts: Number of contracts.
            price_cents: Trade price in cents (0-99).
            mode: Trade mode ('paper' or 'live').
            status: Trade status ('pending', 'filled', or 'rejected').
            placed_at: Datetime the trade was placed (UTC). Defaults to now.
            kalshi_order_id: Kalshi order ID (None for paper trades).

        Returns:
            MagicMock representing a Trade ORM object.
        """
        trade = MagicMock()
        trade.id = uuid.uuid4()
        trade.ticker = ticker
        trade.side = side
        trade.contracts = contracts
        trade.price_cents = price_cents
        trade.mode = mode
        trade.status = status
        trade.placed_at = placed_at or datetime.now(tz=UTC)
        trade.kalshi_order_id = kalshi_order_id
        return trade

    return _make_trade
