"""Broker abstraction for the paper execution surface (Phase 10, D2).

A narrow :class:`BrokerClient` Protocol so the submit orchestration depends on a
seam, not on Alpaca. The real adapter is :class:`~ai_hedge_fund.execution.alpaca.AlpacaPaperBroker`;
tests use ``tests.execution.fakes.FakeBroker``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
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


@dataclass(frozen=True)
class BrokerActivity:
    """One account activity: a fill, a dividend cash movement, or a corporate action.

    FILL rows carry ``broker_order_id`` / ``side`` / ``qty`` / ``price_cents``;
    every other type carries ``net_amount_cents`` (signed). Money is exact cents.
    """

    activity_id: str
    activity_type: str
    symbol: str
    occurred_at: datetime  # aware UTC; non-FILL = 00:00 New York on the activity date
    broker_order_id: str | None
    side: Literal["buy", "sell"] | None
    qty: int | None
    price_cents: int | None
    net_amount_cents: int | None
    raw: dict[str, Any]  # redacted, account_id removed


@dataclass(frozen=True)
class RejectedActivity:
    """An activity the broker reported that cannot be used, and why (review H2)."""

    activity_id: str
    activity_type: str | None
    order_id: str | None  # FILL only -- lets the caller tell our orders from manual ones
    reason: str
    raw: dict[str, Any]  # redacted


@dataclass(frozen=True)
class ActivityBatch:
    activities: list[BrokerActivity]
    rejected: list[RejectedActivity]


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

    def list_activities(self, types: Sequence[str], since: date) -> ActivityBatch:
        """Account activities of ``types`` on or after New York date ``since``, oldest first.

        Unusable items come back in ``rejected``; raises UnexpectedBrokerResponse for a
        malformed response and the typed API errors.
        """
        ...
