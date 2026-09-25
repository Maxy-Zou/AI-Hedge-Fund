"""Parse Alpaca ``/account/activities`` items into :class:`BrokerActivity` (Phase 11, T4).

Validated field by field against what we *use*, not against the SDK's
``TradeActivity`` / ``NonTradeActivity`` models: those require fields
(``account_id``, ``order_status``, ``description``) that Alpaca's documented
examples omit, so a real response would have been rejected wholesale (review H1).

Each item either parses or becomes a :class:`RejectedActivity` with a reason --
one manual short sale or fractional trade on the account must not abort the
ingest of everything else (review H2). Only a malformed *response* (not a list,
an item without an id) raises :class:`UnexpectedBrokerResponse`. Money and
quantity come from the raw decimal strings: exact cents, positive, bounded; a
fractional quantity is refused, never truncated (11-PREMORTEM #19).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal, DecimalException
from typing import Any

from ai_hedge_fund.db.dates import market_midnight_utc
from ai_hedge_fund.execution.broker import BrokerActivity, RejectedActivity
from ai_hedge_fund.execution.errors import UnexpectedBrokerResponse
from ai_hedge_fund.execution.redact import redact

_CENT = Decimal(1)
_MAX_CENTS = 2**63 - 1  # BigInteger
_MAX_QTY = 2**31 - 1  # paper_fills.filled_qty is Integer
_SIDES = frozenset({"buy", "sell"})
_SYMBOL_MAX = 10  # paper_trades.ticker / paper_cash_events.ticker


class _Reject(Exception):
    """Internal: this item cannot be used; the message is the reason."""


def _text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise _Reject(f"{key} missing or not a string")
    return value


def _symbol(item: dict[str, Any]) -> str:
    symbol = _text(item, "symbol")
    if symbol != symbol.upper() or len(symbol) > _SYMBOL_MAX:
        raise _Reject(f"symbol {symbol!r} is not an upper-case ticker of <= {_SYMBOL_MAX} chars")
    return symbol


def _decimal(item: dict[str, Any], key: str) -> Decimal:
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise _Reject(f"{key} is not a number")
    try:
        amount = Decimal(str(value))
    except DecimalException:
        raise _Reject(f"{key} {value!r} is not a number") from None
    if not amount.is_finite():
        raise _Reject(f"{key} {value!r} is not finite")
    return amount


def _cents(item: dict[str, Any], key: str) -> int:
    try:
        cents = int((_decimal(item, key) * 100).quantize(_CENT, rounding=ROUND_HALF_EVEN))
    except DecimalException:
        raise _Reject(f"{key} is out of range") from None
    if abs(cents) > _MAX_CENTS:
        raise _Reject(f"{key} is out of range")
    return cents


def _fill_fields(item: dict[str, Any]) -> tuple[datetime, str, int, int]:
    moment = datetime.fromisoformat(_text(item, "transaction_time"))
    if moment.tzinfo is None:
        raise _Reject("transaction_time has no timezone")
    side = _text(item, "side")
    if side not in _SIDES:
        raise _Reject(f"unsupported side {side!r}")
    qty = _decimal(item, "qty")
    if abs(qty) > _MAX_QTY:
        raise _Reject("qty is out of range")
    if qty != qty.to_integral_value():
        raise _Reject(f"fractional qty {item['qty']}")
    price_cents = _cents(item, "price")
    if qty <= 0 or price_cents <= 0:
        raise _Reject("qty and price must be positive")
    return moment.astimezone(UTC), side, int(qty), price_cents


def _parse_fill(item: dict[str, Any], raw: dict[str, Any]) -> BrokerActivity:
    occurred_at, side, qty, price_cents = _fill_fields(item)
    return BrokerActivity(
        activity_id=item["id"],
        activity_type="FILL",
        symbol=_symbol(item),
        occurred_at=occurred_at,
        broker_order_id=_text(item, "order_id"),
        side=side,  # type: ignore[arg-type]
        qty=qty,
        price_cents=price_cents,
        net_amount_cents=None,
        raw=raw,
    )


def _parse_non_trade(item: dict[str, Any], raw: dict[str, Any]) -> BrokerActivity:
    if item.get("status") == "canceled":
        raise _Reject("activity status is canceled")
    return BrokerActivity(
        activity_id=item["id"],
        activity_type=_text(item, "activity_type"),
        symbol=_symbol(item),
        occurred_at=market_midnight_utc(date.fromisoformat(_text(item, "date"))),
        broker_order_id=None,
        side=None,
        qty=None,
        price_cents=None,
        net_amount_cents=_cents(item, "net_amount"),
        raw=raw,
    )


def parse_activity(item: object, secret_values: list[str]) -> BrokerActivity | RejectedActivity:
    """One raw activity -> a parsed activity or a rejection with its reason.

    Raises:
        UnexpectedBrokerResponse: the item is not an object with a string ``id``.
    """
    if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
        raise UnexpectedBrokerResponse("activity is not an object with an id")
    raw = redact({k: v for k, v in item.items() if k != "account_id"}, secret_values)
    kind = item.get("activity_type")
    try:
        if kind == "FILL":
            return _parse_fill(item, raw)
        return _parse_non_trade(item, raw)
    except (_Reject, ValueError) as exc:  # ValueError: fromisoformat
        return RejectedActivity(
            activity_id=item["id"],
            activity_type=kind if isinstance(kind, str) else None,
            order_id=item.get("order_id") if isinstance(item.get("order_id"), str) else None,
            reason=str(exc),
            raw=raw,
        )
