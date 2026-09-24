"""Alpaca paper-trading adapter (Phase 10, D2/D8).

Wraps the official ``alpaca-py`` TradingClient behind the :class:`BrokerClient`
seam. Two fail-closed guards: the host must be a paper endpoint (a live URL is a
construction error, never a live order), and every credential must be present
and named if missing. Broker errors are classified by driver code -- duplicate
client_order_id and outright rejections are terminal (never retried); only
transient transport/5xx failures retry. Stored ``raw`` is redacted so a broker
response can never carry a credential into an audit payload.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ai_hedge_fund.execution.broker import BrokerOrderRequest, BrokerOrderResult
from ai_hedge_fund.execution.errors import (
    BrokerRejected,
    DuplicateClientOrderId,
    LiveEndpointRefused,
    MissingBrokerCredentials,
    TransientBrokerError,
)
from ai_hedge_fund.execution.redact import redact

logger = structlog.get_logger(__name__)

_PAPER_MARKER = "paper-api"
_DUP_CODE = 40010001


def _classify_api_error(exc: APIError) -> Exception:
    """Map an Alpaca APIError to a typed execution error by driver code, not message text."""
    try:
        status = exc.status_code
    except Exception:  # noqa: BLE001 - status_code parsing can raise without an http_error
        status = None
    if status is not None and status >= 500:
        return TransientBrokerError(str(exc))

    code: Any = None
    message = ""
    try:
        code = exc.code
        message = exc.message or ""
    except Exception:  # noqa: BLE001 - defensive: fall back to the raw string
        message = str(exc)

    if code == _DUP_CODE or "client_order_id" in message.lower():
        return DuplicateClientOrderId(message or str(exc))
    return BrokerRejected(message or str(exc))


class AlpacaPaperBroker:
    """BrokerClient backed by Alpaca's paper trading API."""

    def __init__(self, api_key: str, secret: str, host: str) -> None:
        if not api_key:
            raise MissingBrokerCredentials("ALPACA_PAPER_API_KEY is not set")
        if not secret:
            raise MissingBrokerCredentials("ALPACA_PAPER_SECRET is not set")
        if not host:
            raise MissingBrokerCredentials("ALPACA_PAPER_HOST is not set")
        if _PAPER_MARKER not in host:
            raise LiveEndpointRefused(
                f"refusing non-paper host {host!r}: must contain {_PAPER_MARKER!r}"
            )
        self._secret_values = [api_key, secret]
        self._client = TradingClient(api_key, secret, paper=True, url_override=host)

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

    @retry(
        retry=retry_if_exception_type(TransientBrokerError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    def _submit(self, order_data: Any) -> Any:
        try:
            return self._client.submit_order(order_data=order_data)
        except APIError as exc:
            raise _classify_api_error(exc) from exc

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        order = self._submit(self._build_request(req))
        raw = redact(_as_dict(order), secret_values=self._secret_values)
        logger.info(
            "paper_order_submitted",
            client_order_id=req.client_order_id,
            symbol=req.symbol,
            qty=req.qty,
            broker_order_id=str(order.id),
        )
        return BrokerOrderResult(
            broker_order_id=str(order.id),
            status=str(order.status),
            submitted_at=order.submitted_at,
            raw=raw,
        )

    def cancel_order(self, broker_order_id: str) -> None:
        self._client.cancel_order_by_id(broker_order_id)


def _as_dict(order: Any) -> dict[str, Any]:
    """Best-effort dict view of an Alpaca Order for the audit payload."""
    dump = getattr(order, "model_dump", None)
    if callable(dump):
        return json.loads(json.dumps(dump(mode="json"), default=str))
    return {"repr": str(order)}
