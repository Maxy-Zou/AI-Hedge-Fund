"""Parse Alpaca ``/account/activities`` items into :class:`BrokerActivity` (Phase 11, T4).

Shape is validated with the SDK's own ``TradeActivity`` / ``NonTradeActivity``
models, so vendor drift raises :class:`UnexpectedBrokerResponse` instead of
quietly yielding nothing (11-PREMORTEM #30). Money and quantity are then read
from the *raw* decimal strings -- the SDK models hold them as floats -- so cents
are exact (half-even to the cent) and a fractional quantity is refused, never
truncated (#19).
"""

from __future__ import annotations

from datetime import UTC
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

from alpaca.trading.models import NonTradeActivity, TradeActivity
from pydantic import ValidationError

from ai_hedge_fund.db.dates import market_midnight_utc
from ai_hedge_fund.execution.broker import BrokerActivity
from ai_hedge_fund.execution.errors import FractionalQuantity, UnexpectedBrokerResponse
from ai_hedge_fund.execution.redact import redact

_CENT = Decimal(1)
_SIDES = {"buy": "buy", "sell": "sell"}


def _decimal(item: dict[str, Any], key: str) -> Decimal:
    value = item.get(key)
    try:
        return Decimal(str(value)) if value is not None else Decimal("NaN")
    except InvalidOperation:
        return Decimal("NaN")


def _cents(item: dict[str, Any], key: str) -> int:
    amount = _decimal(item, key)
    if not amount.is_finite():
        raise UnexpectedBrokerResponse(f"activity {item.get('id')!r}: {key} is not a number")
    return int((amount * 100).quantize(_CENT, rounding=ROUND_HALF_EVEN))


def _whole_shares(item: dict[str, Any]) -> int:
    qty = _decimal(item, "qty")
    if not qty.is_finite():
        raise UnexpectedBrokerResponse(f"activity {item.get('id')!r}: qty is not a number")
    if qty != qty.to_integral_value():
        raise FractionalQuantity(f"activity {item.get('id')!r}: fractional qty {item['qty']}")
    return int(qty)


def _raw(item: dict[str, Any], secret_values: list[str]) -> dict[str, Any]:
    return redact({k: v for k, v in item.items() if k != "account_id"}, secret_values)


def _parse_fill(item: dict[str, Any], secret_values: list[str]) -> BrokerActivity:
    model = TradeActivity.model_validate(item)
    side = _SIDES.get(str(getattr(model.side, "value", model.side)))
    if side is None:
        raise UnexpectedBrokerResponse(f"activity {model.id!r}: unsupported side {model.side!r}")
    return BrokerActivity(
        activity_id=model.id,
        activity_type="FILL",
        symbol=model.symbol,
        occurred_at=model.transaction_time.astimezone(UTC),
        broker_order_id=str(model.order_id),
        side=side,  # type: ignore[arg-type]
        qty=_whole_shares(item),
        price_cents=_cents(item, "price"),
        net_amount_cents=None,
        raw=_raw(item, secret_values),
    )


def _parse_non_trade(item: dict[str, Any], secret_values: list[str]) -> BrokerActivity:
    model = NonTradeActivity.model_validate(item)
    if not model.symbol:
        raise UnexpectedBrokerResponse(f"activity {model.id!r}: no symbol")
    return BrokerActivity(
        activity_id=model.id,
        activity_type=str(getattr(model.activity_type, "value", model.activity_type)),
        symbol=model.symbol,
        occurred_at=market_midnight_utc(model.date),
        broker_order_id=None,
        side=None,
        qty=None,
        price_cents=None,
        net_amount_cents=_cents(item, "net_amount"),
        raw=_raw(item, secret_values),
    )


def parse_activity(item: object, secret_values: list[str]) -> BrokerActivity:
    """One raw activity -> :class:`BrokerActivity`, or a typed error."""
    if not isinstance(item, dict):
        raise UnexpectedBrokerResponse(f"activity is {type(item).__name__}, expected an object")
    try:
        if item.get("activity_type") == "FILL":
            return _parse_fill(item, secret_values)
        return _parse_non_trade(item, secret_values)
    except ValidationError as exc:
        raise UnexpectedBrokerResponse(
            f"activity {item.get('id')!r} does not match the documented shape: "
            f"{exc.error_count()} error(s)"
        ) from None
