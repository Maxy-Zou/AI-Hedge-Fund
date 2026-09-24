"""Test doubles for the execution broker (Phase 10).

FakeBroker records every request, enforces client_order_id uniqueness the way
Alpaca does, supports lookup by client_order_id, and can be scripted to raise
or to lose the response of an order it accepted. No network, no SDK import.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ai_hedge_fund.execution.broker import BrokerOrderRequest, BrokerOrderResult
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
        self._fail_with = fail_with
        self._lose_next_response = lose_response_once
        self._counter = 0

    @property
    def calls(self) -> int:
        return len(self.requests)

    def seed_order(self, client_order_id: str, symbol: str, side: str, qty: int) -> None:
        """Pre-place an order under ``client_order_id`` (e.g. from another database)."""
        self.orders[client_order_id] = self._result(client_order_id, symbol, side, qty)

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        self.requests.append(req)
        if self._fail_with is not None:
            raise self._fail_with
        if req.client_order_id in self.orders:
            raise DuplicateClientOrderId("client_order_id must be unique")
        result = self._result(req.client_order_id, req.symbol, req.side, req.qty)
        self.orders[req.client_order_id] = result
        if self._lose_next_response:
            self._lose_next_response = False
            raise TransientBrokerError("read timed out")
        return result

    def get_order_by_client_order_id(self, client_order_id: str) -> BrokerOrderResult | None:
        return self.orders.get(client_order_id)

    def cancel_order(self, broker_order_id: str) -> None:
        self.cancelled.append(broker_order_id)

    def _result(self, client_order_id: str, symbol: str, side: str, qty: int) -> BrokerOrderResult:
        self._counter += 1
        return BrokerOrderResult(
            broker_order_id=f"fake-{self._counter}",
            status="accepted",
            submitted_at=datetime(2026, 4, 18, 14, 30, tzinfo=UTC),
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            raw={"client_order_id": client_order_id, "symbol": symbol, "qty": qty},
        )
