"""Test doubles for the execution broker (Phase 10).

FakeBroker records every request, enforces client_order_id uniqueness the way
Alpaca does, supports lookup by client_order_id, and can be scripted to raise
or to lose the response of an order it accepted. No network, no SDK import.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

from ai_hedge_fund.db.dates import trading_date
from ai_hedge_fund.execution.broker import BrokerActivity, BrokerOrderRequest, BrokerOrderResult
from ai_hedge_fund.execution.errors import DuplicateClientOrderId, TransientBrokerError


class FakeBroker:
    """In-memory BrokerClient stand-in.

    Args:
        fail_with: if set, submit_order raises this exception instead of accepting.
        lose_response_once: accept the first order, then raise TransientBrokerError
            as if the response timed out -- the order exists at the broker but the
            caller never learned its id (review R3).
    """

    def __init__(
        self, fail_with: Exception | None = None, *, lose_response_once: bool = False
    ) -> None:
        self.requests: list[BrokerOrderRequest] = []
        self.cancelled: list[str] = []
        self.orders: dict[str, BrokerOrderResult] = {}
        self.activities: list[BrokerActivity] = []  # Phase 11: scripted account activity
        self._fail_with = fail_with
        self._lose_next_response = lose_response_once
        self._counter = 0

    @property
    def calls(self) -> int:
        return len(self.requests)

    def seed_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        qty: int,
        *,
        order_type: str = "market",
        limit_price_cents: int | None = None,
        status: str = "accepted",
        filled_qty: int = 0,
    ) -> None:
        """Pre-place an order under ``client_order_id`` (a lost response, or a foreign order)."""
        self.orders[client_order_id] = self._result(
            client_order_id, symbol, side, qty, order_type, limit_price_cents, status, filled_qty
        )

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        self.requests.append(req)
        if self._fail_with is not None:
            raise self._fail_with
        if req.client_order_id in self.orders:
            raise DuplicateClientOrderId("client_order_id must be unique")
        result = self._result(
            req.client_order_id,
            req.symbol,
            req.side,
            req.qty,
            req.order_type,
            req.limit_price_cents,
        )
        self.orders[req.client_order_id] = result
        if self._lose_next_response:
            self._lose_next_response = False
            raise TransientBrokerError("read timed out")
        return result

    def get_order_by_client_order_id(self, client_order_id: str) -> BrokerOrderResult | None:
        return self.orders.get(client_order_id)

    def cancel_order(self, broker_order_id: str) -> None:
        self.cancelled.append(broker_order_id)

    def list_activities(self, types: Sequence[str], since: date) -> list[BrokerActivity]:
        """Scripted activities of ``types`` on or after New York date ``since``, oldest first."""
        wanted = set(types)
        return sorted(
            (
                a
                for a in self.activities
                if a.activity_type in wanted and trading_date(a.occurred_at) >= since
            ),
            key=lambda a: (a.occurred_at, a.activity_id),
        )

    def _result(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        qty: int,
        order_type: str = "market",
        limit_price_cents: int | None = None,
        status: str = "accepted",
        filled_qty: int = 0,
    ) -> BrokerOrderResult:
        self._counter += 1
        return BrokerOrderResult(
            broker_order_id=f"fake-{self._counter}",
            status=status,
            submitted_at=datetime(2026, 4, 18, 14, 30, tzinfo=UTC),
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            limit_price_cents=limit_price_cents,
            filled_qty=filled_qty,
            raw={"client_order_id": client_order_id, "symbol": symbol, "qty": qty},
        )
