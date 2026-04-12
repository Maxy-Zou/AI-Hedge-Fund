"""RED tests for TradeExecutor — EXEC-01, EXEC-02, LOG-02.

These tests will FAIL with ImportError until Plan 02 implements executor.py.
That is the expected RED state for Plan 01.

Coverage:
  EXEC-01: Paper trade mode — write Trade row, no external API call
  EXEC-02: Live trade mode — call portfolio_api.create_order() once
  LOG-02: Blocked trade — write Trade(status='rejected') to DB
  Threshold gate: Below confidence_threshold → return None, no Trade row
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from kalshi_tracker.execution.types import ApprovalResult

# This import WILL FAIL until Plan 02 creates executor.py.
# That failure IS the RED state for Plan 01.
from kalshi_tracker.execution.executor import TradeExecutor  # noqa: E402


class TestPaperTradeMode:
    """EXEC-01: In paper mode (portfolio_api=None), write Trade(mode='paper', status='filled')."""

    def test_paper_trade_writes_row(
        self, mock_session_factory: tuple, signal_factory
    ) -> None:
        """paper mode → Trade(mode='paper', status='filled') added to session; no external API call.

        Args:
            mock_session_factory: (factory, session) fixture tuple.
            signal_factory: Signal MagicMock factory.
        """
        factory, session = mock_session_factory
        signal = signal_factory(confidence=0.8, current_price=45, contracts=10)

        mock_risk_guard = MagicMock()
        mock_risk_guard.approve.return_value = ApprovalResult(
            approved=True, reason="approved", trade_cost_cents=450
        )

        executor = TradeExecutor(
            session_factory=factory,
            risk_guard=mock_risk_guard,
            portfolio_api=None,  # paper mode
            confidence_threshold=0.5,
        )
        result = executor.execute(signal)

        # Trade must have been added to session
        assert session.add.call_count == 1
        added_trade = session.add.call_args[0][0]
        assert added_trade.mode == "paper"
        assert added_trade.status == "filled"


class TestLiveTradeMode:
    """EXEC-02: In live mode, call portfolio_api.create_order() with correct ticker."""

    def test_live_trade_calls_api(
        self, mock_session_factory: tuple, signal_factory
    ) -> None:
        """live mode → portfolio_api.create_order() called exactly once with signal.ticker.

        Args:
            mock_session_factory: (factory, session) fixture tuple.
            signal_factory: Signal MagicMock factory.
        """
        factory, session = mock_session_factory
        signal = signal_factory(ticker="PRES-2024-R", confidence=0.8, current_price=45, contracts=10)

        mock_risk_guard = MagicMock()
        mock_risk_guard.approve.return_value = ApprovalResult(
            approved=True, reason="approved", trade_cost_cents=450
        )

        mock_portfolio_api = MagicMock()

        executor = TradeExecutor(
            session_factory=factory,
            risk_guard=mock_risk_guard,
            portfolio_api=mock_portfolio_api,
            confidence_threshold=0.5,
        )
        result = executor.execute(signal)

        # portfolio_api.create_order must be called exactly once
        assert mock_portfolio_api.create_order.called is True
        assert mock_portfolio_api.create_order.call_count == 1


class TestBlockedTradeLogging:
    """LOG-02: When RiskGuard blocks, persist Trade(status='rejected') to DB."""

    def test_blocked_trade_logged(
        self, mock_session_factory: tuple, signal_factory
    ) -> None:
        """RiskGuard blocks → Trade(status='rejected') added to session.

        Args:
            mock_session_factory: (factory, session) fixture tuple.
            signal_factory: Signal MagicMock factory.
        """
        factory, session = mock_session_factory
        signal = signal_factory(confidence=0.8, current_price=45, contracts=10)

        mock_risk_guard = MagicMock()
        mock_risk_guard.approve.return_value = ApprovalResult(
            approved=False, reason="per_trade_cap", trade_cost_cents=0
        )

        executor = TradeExecutor(
            session_factory=factory,
            risk_guard=mock_risk_guard,
            portfolio_api=None,
            confidence_threshold=0.5,
        )
        result = executor.execute(signal)

        # A rejected Trade row must be added to the session
        assert session.add.call_count == 1
        added_trade = session.add.call_args[0][0]
        assert added_trade.status == "rejected"


class TestBelowThresholdGate:
    """Threshold gate: signals below confidence_threshold return None without any DB write."""

    def test_below_threshold_returns_none(
        self, mock_session_factory: tuple, signal_factory
    ) -> None:
        """signal.confidence=0.3 with threshold=0.6 → execute() returns None, no Trade persisted.

        Args:
            mock_session_factory: (factory, session) fixture tuple.
            signal_factory: Signal MagicMock factory.
        """
        factory, session = mock_session_factory
        # confidence below threshold — should be skipped, not blocked
        signal = signal_factory(confidence=0.3)

        mock_risk_guard = MagicMock()

        executor = TradeExecutor(
            session_factory=factory,
            risk_guard=mock_risk_guard,
            portfolio_api=None,
            confidence_threshold=0.6,  # signal is below this
        )
        result = executor.execute(signal)

        # Must return None — not a rejected Trade, just skipped
        assert result is None
        # No Trade row written to DB
        assert session.add.call_count == 0
        # RiskGuard was NOT consulted (threshold check is a pre-guard gate)
        assert mock_risk_guard.approve.call_count == 0
