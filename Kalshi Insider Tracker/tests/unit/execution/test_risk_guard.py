"""RED tests for RiskGuard — EXEC-03 through EXEC-06.

These tests will FAIL with ImportError until Plan 02 implements risk_guard.py.
That is the expected RED state for Plan 01.

Coverage:
  EXEC-03: Per-trade cap ($50 / 5_000 cents)
  EXEC-04: Total exposure cap ($500 / 50_000 cents)
  EXEC-05: Duplicate signal rejection (same ticker, filled within dedup window)
  EXEC-06: In-flight order rejection (same ticker, pending within 60s)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

# This import WILL FAIL until Plan 02 creates risk_guard.py.
# That failure IS the RED state for Plan 01.
from kalshi_tracker.execution.risk_guard import (  # noqa: E402
    MAX_PER_TRADE_CENTS,
    MAX_TOTAL_EXPOSURE_CENTS,
    RiskGuard,
)


class TestRiskGuardPerTradeCap:
    """EXEC-03: Reject trades exceeding the per-trade cap of $50 (5_000 cents)."""

    def test_per_trade_cap_blocks(
        self, mock_session_factory: tuple, signal_factory, trade_factory
    ) -> None:
        """Signal priced at 51 cents * 100 contracts = 5_100 > 5_000 → blocked.

        Args:
            mock_session_factory: (factory, session) fixture tuple.
            signal_factory: Signal MagicMock factory.
            trade_factory: Trade MagicMock factory.
        """
        factory, session = mock_session_factory
        # 51 cents * 100 contracts = 5_100 > MAX_PER_TRADE_CENTS (5_000)
        signal = signal_factory(current_price=51, contracts=100)

        guard = RiskGuard(session_factory=factory)
        result = guard.approve(signal)

        assert result.approved is False
        assert result.reason == "per_trade_cap"


class TestRiskGuardTotalExposureCap:
    """EXEC-04: Reject trades that would push total live exposure above $500 (50_000 cents)."""

    def test_total_exposure_cap_blocks(
        self, mock_session_factory: tuple, signal_factory, trade_factory
    ) -> None:
        """Existing exposure 49_500 + new trade 600 = 50_100 > 50_000 → blocked.

        Args:
            mock_session_factory: (factory, session) fixture tuple.
            signal_factory: Signal MagicMock factory.
            trade_factory: Trade MagicMock factory.
        """
        factory, session = mock_session_factory

        # Existing live filled trades summing to 49_500 cents exposure
        existing_trade = trade_factory(
            contracts=990,
            price_cents=50,  # 990 * 50 = 49_500
            mode="live",
            status="filled",
        )
        # Session query returns the existing trade for exposure query
        session.query.return_value.filter.return_value.all.return_value = [existing_trade]

        # New signal: 12 cents * 50 contracts = 600 cents → total 50_100 > 50_000
        signal = signal_factory(current_price=12, contracts=50)

        guard = RiskGuard(session_factory=factory)
        result = guard.approve(signal)

        assert result.approved is False
        assert result.reason == "total_exposure_cap"


class TestRiskGuardDuplicateSignal:
    """EXEC-05: Reject duplicate signals (same ticker already filled within dedup window)."""

    def test_duplicate_signal_blocks(
        self, mock_session_factory: tuple, signal_factory, trade_factory
    ) -> None:
        """Trade with status='filled' for same ticker within last 300s → blocked.

        Args:
            mock_session_factory: (factory, session) fixture tuple.
            signal_factory: Signal MagicMock factory.
            trade_factory: Trade MagicMock factory.
        """
        factory, session = mock_session_factory
        now = datetime.now(tz=UTC)

        # Existing filled trade placed 10 seconds ago (within dedup window)
        recent_filled_trade = trade_factory(
            ticker="PRES-2024-R",
            status="filled",
            mode="live",
            placed_at=now - timedelta(seconds=10),
        )
        session.query.return_value.filter.return_value.all.return_value = [recent_filled_trade]

        # Signal for the same ticker
        signal = signal_factory(ticker="PRES-2024-R", current_price=45, contracts=10)

        guard = RiskGuard(session_factory=factory)
        result = guard.approve(signal)

        assert result.approved is False
        assert result.reason == "duplicate"


class TestRiskGuardInFlightRejection:
    """EXEC-06: Reject trades when a pending order for the same ticker is in-flight (within 60s)."""

    def test_in_flight_blocks(
        self, mock_session_factory: tuple, signal_factory, trade_factory
    ) -> None:
        """Trade with status='pending' for same ticker placed within 60s → blocked.

        Args:
            mock_session_factory: (factory, session) fixture tuple.
            signal_factory: Signal MagicMock factory.
            trade_factory: Trade MagicMock factory.
        """
        factory, session = mock_session_factory
        now = datetime.now(tz=UTC)

        # Existing pending trade placed 5 seconds ago (within 60s in-flight window)
        pending_trade = trade_factory(
            ticker="PRES-2024-R",
            status="pending",
            placed_at=now - timedelta(seconds=5),
        )
        session.query.return_value.filter.return_value.all.return_value = [pending_trade]

        # Signal for the same ticker
        signal = signal_factory(ticker="PRES-2024-R", current_price=45, contracts=10)

        guard = RiskGuard(session_factory=factory)
        result = guard.approve(signal)

        assert result.approved is False
        assert result.reason == "in_flight"


class TestRiskGuardApproveClean:
    """Positive path: approve when all risk checks pass."""

    def test_approve_passes_clean(
        self, mock_session_factory: tuple, signal_factory
    ) -> None:
        """No existing trades, cost within cap → approved=True.

        Args:
            mock_session_factory: (factory, session) fixture tuple.
            signal_factory: Signal MagicMock factory.
        """
        factory, session = mock_session_factory
        # Session returns no trades (default from conftest)
        session.query.return_value.filter.return_value.all.return_value = []

        # 45 cents * 10 contracts = 450 < 5_000 per-trade cap
        signal = signal_factory(ticker="PRES-2024-R", current_price=45, contracts=10)

        guard = RiskGuard(session_factory=factory)
        result = guard.approve(signal)

        assert result.approved is True
