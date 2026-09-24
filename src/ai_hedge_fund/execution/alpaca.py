"""Alpaca paper-trading adapter (Phase 10, D2/D8).

Wraps the official ``alpaca-py`` TradingClient behind the :class:`BrokerClient`
seam. Two fail-closed guards: the host must be exactly Alpaca's paper endpoint
(parsed, allow-listed -- a live or look-alike URL is a construction error, never
an order), and every credential must be present and named if missing.

Broker errors are classified from shapes observed on the real paper API
(review R5): a duplicate client_order_id is identified by its message, because
its code (42210000) is shared with other 422s such as an unknown symbol; 401 is
a credential failure, not an order rejection -- but 403 is (Alpaca returns
"insufficient buying power" as 403/40310000); 429, 5xx, timeouts and
connection errors are transient and retried with the *same* client_order_id,
which makes the retry idempotent. Every message leaving the adapter -- and the
stored ``raw`` -- is scrubbed of the configured credentials.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

import requests
import structlog
from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ai_hedge_fund.execution.broker import BrokerOrderRequest, BrokerOrderResult
from ai_hedge_fund.execution.errors import (
    BrokerAuthError,
    BrokerRejected,
    DuplicateClientOrderId,
    ExecutionError,
    LiveEndpointRefused,
    MissingBrokerCredentials,
    TransientBrokerError,
)
from ai_hedge_fund.execution.redact import redact

logger = structlog.get_logger(__name__)

_PAPER_HOSTNAMES = frozenset({"paper-api.alpaca.markets"})
_DUPLICATE_MESSAGE = "client_order_id must be unique"
_TRANSPORT_ERRORS = (requests.exceptions.Timeout, requests.exceptions.ConnectionError)


def _paper_base_url(host: str) -> str:
    """Canonical ``https://<paper hostname>`` for ``host``, or LiveEndpointRefused.

    Parsed, not substring-matched (review R2): ``https://paper-api@api.alpaca.markets``
    contains "paper-api" but its hostname is the live API. The message names only
    scheme and hostname, never the raw value, which may carry userinfo credentials.
    """
    parts = urlsplit(host.strip())
    try:
        port = parts.port
    except ValueError:
        port = -1
    hostname = parts.hostname or ""
    if (
        parts.scheme.lower() != "https"
        or hostname not in _PAPER_HOSTNAMES
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        allowed = ", ".join(f"https://{h}" for h in sorted(_PAPER_HOSTNAMES))
        raise LiveEndpointRefused(
            f"refusing broker host (scheme={parts.scheme!r}, hostname={hostname!r}); "
            f"only {allowed} is allowed"
        )
    return f"https://{hostname}"


def _status(exc: APIError) -> int | None:
    try:
        return exc.status_code
    except Exception:  # noqa: BLE001 - status_code parsing can raise without an http_error
        return None


def _message(exc: APIError) -> str:
    try:
        return str(exc.message or "") or str(exc)
    except Exception:  # noqa: BLE001 - body may not be JSON or may lack "message"
        return str(exc)


def _classify_api_error(exc: APIError, secret_values: list[str] | None = None) -> ExecutionError:
    """Map an Alpaca APIError to a typed execution error (shapes probed live, review R5)."""
    status = _status(exc)
    raw_message = _message(exc)
    # Classify on the raw text; only the scrubbed text leaves the adapter.
    message = f"HTTP {status}: {redact(raw_message, secret_values)}"
    if status == 401:  # 403 is an order verdict at Alpaca (e.g. buying power)
        return BrokerAuthError(message)
    if status == 429 or (status is not None and status >= 500):
        return TransientBrokerError(message)
    if _DUPLICATE_MESSAGE in raw_message.lower():
        return DuplicateClientOrderId(message)
    return BrokerRejected(message)


class AlpacaPaperBroker:
    """BrokerClient backed by Alpaca's paper trading API."""

    def __init__(self, api_key: str, secret: str, host: str) -> None:
        if not api_key:
            raise MissingBrokerCredentials("ALPACA_PAPER_API_KEY is not set")
        if not secret:
            raise MissingBrokerCredentials("ALPACA_PAPER_SECRET is not set")
        if not host:
            raise MissingBrokerCredentials("ALPACA_PAPER_HOST is not set")
        base_url = _paper_base_url(host)
        self._secret_values = [api_key, secret]
        self._client = TradingClient(api_key, secret, paper=True, url_override=base_url)

    @classmethod
    def from_settings(cls, settings: Any) -> AlpacaPaperBroker:
        return cls(
            api_key=settings.alpaca_paper_api_key,
            secret=settings.alpaca_paper_secret,
            host=settings.alpaca_paper_host,
        )

    def _build_request(self, req: BrokerOrderRequest) -> Any:
        side = OrderSide.BUY if req.side == "buy" else OrderSide.SELL
        common = {
            "symbol": req.symbol,
            "qty": req.qty,
            "side": side,
            "time_in_force": TimeInForce.DAY,
            "client_order_id": req.client_order_id,
        }
        if req.order_type == "limit":
            limit = (req.limit_price_cents or 0) / 100
            return LimitOrderRequest(limit_price=limit, **common)
        return MarketOrderRequest(**common)

    def _translate(self, exc: Exception) -> ExecutionError:
        """Typed, credential-scrubbed error. Raised ``from None`` by callers so the
        unscrubbed SDK exception never rides along as ``__cause__``."""
        if isinstance(exc, APIError):
            return _classify_api_error(exc, self._secret_values)
        detail = redact(str(exc), self._secret_values)
        return TransientBrokerError(f"{type(exc).__name__}: {detail}")

    @retry(
        retry=retry_if_exception_type(TransientBrokerError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    def _submit(self, order_data: Any) -> Any:
        try:
            return self._client.submit_order(order_data=order_data)
        except (APIError, *_TRANSPORT_ERRORS) as exc:
            raise self._translate(exc) from None

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        order = self._submit(self._build_request(req))
        result = self._to_result(order)
        logger.info(
            "paper_order_submitted",
            client_order_id=req.client_order_id,
            symbol=req.symbol,
            qty=req.qty,
            broker_order_id=result.broker_order_id,
        )
        return result

    def get_order_by_client_order_id(self, client_order_id: str) -> BrokerOrderResult | None:
        try:
            order = self._client.get_order_by_client_id(client_order_id)
        except APIError as exc:
            if _status(exc) == 404:
                return None
            raise self._translate(exc) from None
        except _TRANSPORT_ERRORS as exc:
            raise self._translate(exc) from None
        return self._to_result(order)

    def cancel_order(self, broker_order_id: str) -> None:
        self._client.cancel_order_by_id(broker_order_id)

    def _to_result(self, order: Any) -> BrokerOrderResult:
        return BrokerOrderResult(
            broker_order_id=str(order.id),
            status=_enum_value(order.status),
            submitted_at=order.submitted_at,
            client_order_id=str(order.client_order_id),
            symbol=str(order.symbol),
            side=_enum_value(order.side),
            qty=int(float(order.qty)),
            order_type=_enum_value(order.order_type),
            limit_price_cents=_dollars_to_cents(order.limit_price),
            filled_qty=int(float(order.filled_qty or 0)),
            raw=redact(_as_dict(order), secret_values=self._secret_values),
        )


def _enum_value(value: Any) -> str:
    """alpaca-py returns enums (``OrderSide.BUY``); store their wire value (``buy``)."""
    return str(getattr(value, "value", value))


def _dollars_to_cents(value: Any) -> int | None:
    """Alpaca reports prices as decimal-dollar strings; convert exactly, no float."""
    if value is None:
        return None
    return int((Decimal(str(value)) * 100).to_integral_value())


def _as_dict(order: Any) -> dict[str, Any]:
    """Best-effort dict view of an Alpaca Order for the audit payload."""
    dump = getattr(order, "model_dump", None)
    if callable(dump):
        return json.loads(json.dumps(dump(mode="json"), default=str))
    return {"repr": str(order)}
