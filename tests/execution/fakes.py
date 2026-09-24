"""Test doubles for the execution broker (Phase 10).

FakeBroker records every request, enforces client_order_id uniqueness the way
Alpaca does, and can be scripted to raise. No network, no SDK import.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ai_hedge_fund.execution.broker import BrokerOrderRequest, BrokerOrderResult
from ai_hedge_fund.execution.errors import DuplicateClientOrderId


class FakeBroker:
    """In-memory BrokerClient stand-in.

    Args:
        fail_with: if set, submit_order raises this exception instead of accepting.
    """

    def __init__(self, fail_with: Exception | None = None) -> None:
        self.requests: list[BrokerOrderRequest] = []
        self.cancelled: list[str] = []
        self._seen_client_ids: set[str] = set()
        self._fail_with = fail_with
        self._counter = 0

    @property
    def calls(self) -> int:
        return len(self.requests)

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        self.requests.append(req)
        if self._fail_with is not None:
            raise self._fail_with
        if req.client_order_id in self._seen_client_ids:
            raise DuplicateClientOrderId(f"duplicate client_order_id {req.client_order_id}")
        self._seen_client_ids.add(req.client_order_id)
        self._counter += 1
        return BrokerOrderResult(
            broker_order_id=f"fake-{self._counter}",
            status="accepted",
            submitted_at=datetime(2026, 4, 18, 14, 30, tzinfo=UTC),
            raw={"client_order_id": req.client_order_id, "symbol": req.symbol, "qty": req.qty},
        )

    def cancel_order(self, broker_order_id: str) -> None:
        self.cancelled.append(broker_order_id)
