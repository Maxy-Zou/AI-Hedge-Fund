"""Broker abstraction for the paper execution surface (Phase 10, D2).

A narrow :class:`BrokerClient` Protocol so the submit orchestration depends on a
seam, not on Alpaca. The real adapter is :class:`~ai_hedge_fund.execution.alpaca.AlpacaPaperBroker`;
tests use ``tests.execution.fakes.FakeBroker``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class BrokerOrderRequest:
    client_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    qty: int
    order_type: Literal["market", "limit"]
    limit_price_cents: int | None
    time_in_force: Literal["day"] = "day"


@dataclass(frozen=True)
class BrokerOrderResult:
    broker_order_id: str
    status: str
    submitted_at: datetime
    # What the broker holds -- compared against our request before an existing
    # order found by client_order_id is adopted as ours.
    client_order_id: str
    symbol: str
    side: str
    qty: int
    order_type: str
    limit_price_cents: int | None
    filled_qty: int  # a canceled order may still have traded (partial fill)
    raw: dict[str, Any]  # already redacted by the adapter


class BrokerClient(Protocol):
    """The seam the submit orchestration depends on."""

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        """Submit one order.

        Raises BrokerRejected / DuplicateClientOrderId / TransientBrokerError /
        BrokerAuthError.
        """
        ...

    def get_order_by_client_order_id(self, client_order_id: str) -> BrokerOrderResult | None:
        """The order the broker holds under ``client_order_id``, or None if none."""
        ...

    def cancel_order(self, broker_order_id: str) -> None:
        """Cancel an open order (used by the live smoke test)."""
        ...
