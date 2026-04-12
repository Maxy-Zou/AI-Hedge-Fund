"""Trade executor — paper/live dispatch with append-only trade persistence.

Paper mode (portfolio_api=None) is the safe default (EXEC-01). It writes a
Trade(mode='paper', status='filled') row without touching the Kalshi API.

Live mode calls PortfolioApi.create_order() with client_order_id=str(signal.id)
for idempotency (EXEC-02). A pending row is written BEFORE the API call so the
in-flight guard in RiskGuard can detect crashes (EXEC-06). The outcome row is
appended after the API responds — existing rows are NEVER modified (append-only).

Confidence threshold is a pre-guard gate. Signals below the threshold are silently
skipped (None returned). They are NOT logged as blocked trades (LOG-02 only covers
risk-guard blocks, not sub-threshold skips).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy.orm import Session, sessionmaker

from kalshi_tracker.db.models import Signal, Trade
from kalshi_tracker.execution.risk_guard import MAX_PER_TRADE_CENTS, RiskGuard
from kalshi_tracker.execution.types import ApprovalResult

if TYPE_CHECKING:
    # Avoid hard import of kalshi_python in environments where it may not be installed
    from kalshi_python.api.portfolio_api import PortfolioApi

logger = structlog.get_logger(__name__)


class TradeExecutor:
    """Execute signals through RiskGuard then paper or live trade placement.

    Attributes:
        _session_factory: SQLAlchemy sessionmaker for DB writes.
        _risk_guard: RiskGuard instance for pre-execution checks.
        _portfolio_api: Kalshi PortfolioApi instance (None = paper mode).
        _confidence_threshold: Minimum signal confidence required to proceed.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        risk_guard: RiskGuard,
        portfolio_api: PortfolioApi | None,  # None = paper mode (EXEC-01 safe default)
        confidence_threshold: float = 0.6,
    ) -> None:
        """Initialize TradeExecutor.

        Args:
            session_factory: SQLAlchemy sessionmaker for DB writes.
            risk_guard: RiskGuard instance (checks limits before every trade).
            portfolio_api: Kalshi PortfolioApi for live orders. None enables paper mode.
            confidence_threshold: Minimum signal.confidence to proceed (default 0.6).
        """
        self._session_factory = session_factory
        self._risk_guard = risk_guard
        self._portfolio_api = portfolio_api
        self._confidence_threshold = confidence_threshold
        self._log = logger.bind(executor="trade_executor")

    def execute(self, signal: Signal) -> Trade | None:
        """Execute one signal through RiskGuard then paper or live path.

        Returns:
            Trade row if execution or blocking occurred (logged to DB).
            None if signal is below confidence_threshold (not logged — not a block).
        """
        # Gate: sub-threshold signals are silently skipped — not logged as blocked (PITFALL-4)
        if signal.confidence < self._confidence_threshold:
            self._log.info(
                "signal_below_threshold",
                ticker=signal.ticker,
                confidence=signal.confidence,
                threshold=self._confidence_threshold,
            )
            return None

        approval = self._risk_guard.approve(signal)

        if not approval.approved:
            # LOG-02: every risk-guard block writes a rejected Trade row
            return self._persist_blocked(signal, approval.reason)

        if self._portfolio_api is None:
            # EXEC-01: paper mode — no API call
            return self._execute_paper(signal, approval)

        # EXEC-02: live mode — call Kalshi API
        return self._execute_live(signal, approval)

    def _execute_paper(self, signal: Signal, approval: ApprovalResult) -> Trade:
        """Write a Trade(mode='paper', status='filled') row without any API call.

        Args:
            signal: Approved Signal ORM object.
            approval: ApprovalResult from RiskGuard (approved=True).

        Returns:
            The Trade ORM object added to the session.
        """
        price_cents = signal.details.get("current_price", 0)
        contracts = (
            max(1, MAX_PER_TRADE_CENTS // max(1, price_cents)) if price_cents > 0 else 1
        )
        side = signal.details.get("direction", "yes")

        trade = Trade(
            ticker=signal.ticker,
            signal_id=signal.id,
            side=side,
            contracts=contracts,
            price_cents=price_cents,
            mode="paper",
            status="filled",
            placed_at=datetime.now(UTC),
            kalshi_order_id=None,
        )

        with self._session_factory() as session:
            session.add(trade)
            session.commit()

        self._log.info(
            "paper_trade_executed",
            ticker=signal.ticker,
            contracts=contracts,
            price_cents=price_cents,
        )
        return trade

    def _execute_live(self, signal: Signal, approval: ApprovalResult) -> Trade:
        """Place a live order on Kalshi with pending-before-API pattern.

        Step 1: Write Trade(status='pending') BEFORE API call — so in-flight guard works.
        Step 2: Call PortfolioApi.create_order() with client_order_id=str(signal.id).
        Step 3: Append outcome Trade(status='filled'|'rejected') — never modify pending row.

        Args:
            signal: Approved Signal ORM object.
            approval: ApprovalResult from RiskGuard (approved=True).

        Returns:
            The outcome Trade ORM object (filled or rejected on API error).
        """
        price_cents = signal.details.get("current_price", 0)
        contracts = (
            max(1, MAX_PER_TRADE_CENTS // max(1, price_cents)) if price_cents > 0 else 1
        )
        side = signal.details.get("direction", "yes")
        placed_at = datetime.now(UTC)

        # Step 1: Write pending row BEFORE API call (EXEC-06 — in-flight guard)
        pending = Trade(
            ticker=signal.ticker,
            signal_id=signal.id,
            side=side,
            contracts=contracts,
            price_cents=price_cents,
            mode="live",
            status="pending",
            placed_at=placed_at,
            kalshi_order_id=None,
        )
        with self._session_factory() as session:
            session.add(pending)
            session.commit()

        # Step 2: Call Kalshi API with idempotency key = str(signal.id) (EXEC-02)
        kalshi_order_id: str | None = None
        final_status = "rejected"
        try:
            from kalshi_python.models.create_order_request import CreateOrderRequest

            request = CreateOrderRequest(
                ticker=signal.ticker,
                client_order_id=str(signal.id),
                side=side,
                action="buy",
                count=contracts,
                type="limit",
                yes_price=price_cents if side == "yes" else None,
                no_price=price_cents if side == "no" else None,
            )
            response = self._portfolio_api.create_order(create_order_request=request)
            kalshi_order_id = (
                response.order.order_id if (response and response.order) else None
            )
            final_status = "filled"
            self._log.info(
                "live_trade_placed",
                ticker=signal.ticker,
                order_id=kalshi_order_id,
            )
        except Exception:
            self._log.warning("live_trade_api_error", ticker=signal.ticker, exc_info=True)

        # Step 3: Append outcome row — never update the pending row (AppendOnly invariant)
        outcome = Trade(
            ticker=signal.ticker,
            signal_id=signal.id,
            side=side,
            contracts=contracts,
            price_cents=price_cents,
            mode="live",
            status=final_status,
            placed_at=placed_at,
            kalshi_order_id=kalshi_order_id,
        )
        with self._session_factory() as session:
            session.add(outcome)
            session.commit()

        return outcome

    def _persist_blocked(self, signal: Signal, reason: str) -> Trade:
        """Write a Trade(status='rejected') row for risk-guard blocks (LOG-02).

        Args:
            signal: Signal ORM object that was blocked.
            reason: Block reason from RiskGuard (e.g. 'per_trade_cap').

        Returns:
            The rejected Trade ORM object added to the session.
        """
        price_cents = signal.details.get("current_price", 0)
        mode = "live" if self._portfolio_api else "paper"

        trade = Trade(
            ticker=signal.ticker,
            signal_id=signal.id,
            side=signal.details.get("direction", "yes"),
            contracts=0,
            price_cents=price_cents,
            mode=mode,
            status="rejected",
            placed_at=datetime.now(UTC),
            kalshi_order_id=None,
        )

        with self._session_factory() as session:
            session.add(trade)
            session.commit()

        self._log.info("trade_blocked", ticker=signal.ticker, reason=reason)
        return trade
