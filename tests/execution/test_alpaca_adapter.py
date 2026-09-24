"""Phase 10 T5 -- AlpacaPaperBroker adapter (SDK mocked at the client boundary).

Guards: paper-only host (09-PREMORTEM #1), credentials named at construction
(#17), error classification (#2 no retry on rejection). No network.

Error bodies marked PROBED are the real shapes Alpaca's paper API returned on
2026-09-24 (review R5 / round-2 re-review); the rest are illustrative:

    PROBED  duplicate client_order_id   422  code 42210000  "client_order_id must be unique"
    PROBED  unknown symbol              422  code 42210000  'asset "X" not found'
    PROBED  client_order_id too long    422  code 40010001  "client_order_id must be no more ..."
    PROBED  wrong secret                401  (no code)      {"message": "unauthorized."}
    PROBED  insufficient buying power   403  code 40310000  "insufficient buying power"
    PROBED  lookup of unknown order     404  code 40410000  "order not found for ..."
            rate limited / server error 429 / 503           (illustrative bodies)
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
import requests
from alpaca.common.exceptions import APIError

from ai_hedge_fund.execution.alpaca import AlpacaPaperBroker, _classify_api_error
from ai_hedge_fund.execution.broker import BrokerOrderRequest
from ai_hedge_fund.execution.errors import (
    BrokerAuthError,
    BrokerRejected,
    DuplicateClientOrderId,
    LiveEndpointRefused,
    MissingBrokerCredentials,
    TransientBrokerError,
)

PAPER = "https://paper-api.alpaca.markets"

DUPLICATE = (422, '{"code":42210000,"message":"client_order_id must be unique"}')
UNKNOWN_SYMBOL = (422, '{"code":42210000,"message":"asset \\"ZZZZ\\" not found"}')
COID_TOO_LONG = (
    422,
    '{"code":40010001,"message":"client_order_id must be no more than 128 characters"}',
)
UNAUTHORIZED = (401, '{"message": "unauthorized."}\n')
BUYING_POWER = (403, '{"code":40310000,"message":"insufficient buying power"}')
NOT_FOUND = (404, '{"code":40410000,"message":"order not found for sig-1-a1"}')
RATE_LIMITED = (429, '{"code":42910000,"message":"rate limit exceeded"}')
SERVER_ERROR = (503, '{"message":"internal"}')


def _api_error(shape: tuple[int, str]) -> APIError:
    status, body = shape
    http = MagicMock()
    http.response.status_code = status
    return APIError(body, http_error=http)


def _req() -> BrokerOrderRequest:
    return BrokerOrderRequest(
        client_order_id="sig-1-a1",
        symbol="AAPL",
        side="buy",
        qty=5,
        order_type="market",
        limit_price_cents=None,
    )


def _order(order_id: str = "brk-9", symbol: str = "AAPL", side: str = "buy", qty: str = "5"):
    order = MagicMock()
    order.id = order_id
    order.status = "accepted"
    order.symbol = symbol
    order.side = side
    order.qty = qty
    order.order_type = "market"
    order.limit_price = None
    order.filled_qty = "0"  # set explicitly: MagicMock's __float__ would silently be 1.0
    order.client_order_id = "sig-1-a1"
    order.submitted_at = datetime(2026, 4, 18, tzinfo=UTC)
    order.model_dump.return_value = {"id": order_id, "client_order_id": "sig-1-a1"}
    return order


@pytest.fixture()
def no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tenacity's exponential backoff from sleeping in unit tests."""
    monkeypatch.setattr(AlpacaPaperBroker._submit.retry, "sleep", lambda _s: None)


# --------------------------------------------------------------------------- construction guards


@pytest.mark.parametrize(
    "missing", ["ALPACA_PAPER_API_KEY", "ALPACA_PAPER_SECRET", "ALPACA_PAPER_HOST"]
)
def test_missing_credentials_named(missing: str) -> None:
    kw = {"api_key": "PK", "secret": "s", "host": PAPER}
    kw[
        {
            "ALPACA_PAPER_API_KEY": "api_key",
            "ALPACA_PAPER_SECRET": "secret",
            "ALPACA_PAPER_HOST": "host",
        }[missing]
    ] = ""
    with pytest.raises(MissingBrokerCredentials, match=missing):
        AlpacaPaperBroker(**kw)


@pytest.mark.parametrize(
    "host",
    [
        "https://api.alpaca.markets",
        # Review R2: each of these contains "paper-api" but is not the paper host.
        "https://paper-api@api.alpaca.markets",  # userinfo -- real host is live
        "https://paper-api.alpaca.markets.evil.com",  # suffix -- third party gets creds
        "https://api.alpaca.markets/paper-api",  # path
        "https://evil.com/?paper-api.alpaca.markets",  # query
        "http://paper-api.alpaca.markets",  # plaintext
        "https://user:pw@paper-api.alpaca.markets",  # userinfo on the right host
        "https://paper-api.alpaca.markets:8443",  # non-default port
        "paper-api.alpaca.markets",  # no scheme
    ],
)
def test_non_paper_host_refused(host: str) -> None:
    with (
        pytest.raises(LiveEndpointRefused),
        patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc,
    ):
        AlpacaPaperBroker(api_key="PK", secret="s", host=host)
    assert not tc.called  # credentials never handed to a client for a bad host


@pytest.mark.parametrize(
    "host", [PAPER, PAPER + "/", "HTTPS://Paper-API.alpaca.markets", PAPER + ":443"]
)
def test_paper_host_constructs(host: str) -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        AlpacaPaperBroker(api_key="PK", secret="s", host=host)
        assert tc.called


# --------------------------------------------------------------------------- submit mapping


def test_submit_passes_client_order_id_and_maps_result() -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        tc.return_value.submit_order.return_value = _order()

        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        res = broker.submit_order(_req())

        sent = tc.return_value.submit_order.call_args.kwargs["order_data"]
        assert sent.client_order_id == "sig-1-a1"
        assert res.broker_order_id == "brk-9"
        assert (res.client_order_id, res.symbol, res.side, res.qty) == (
            "sig-1-a1",
            "AAPL",
            "buy",
            5,
        )


def test_duplicate_client_order_id_maps_to_typed_error() -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        tc.return_value.submit_order.side_effect = _api_error(DUPLICATE)
        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        with pytest.raises(DuplicateClientOrderId):
            broker.submit_order(_req())


def test_other_api_error_maps_to_broker_rejected() -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        tc.return_value.submit_order.side_effect = _api_error(UNKNOWN_SYMBOL)
        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        with pytest.raises(BrokerRejected) as exc:
            broker.submit_order(_req())
        assert not isinstance(exc.value, DuplicateClientOrderId)
        assert tc.return_value.submit_order.call_count == 1  # 09-PREMORTEM #2: never retried


@pytest.mark.parametrize(
    "transport_error",
    [requests.exceptions.ReadTimeout("read timed out"), requests.exceptions.ConnectionError("x")],
)
def test_transport_error_is_retried_then_transient(transport_error, no_retry_sleep) -> None:
    """Review R3: a timeout may hide an accepted order; retry with the same
    client_order_id (idempotent) and surface TransientBrokerError, never a raw
    requests exception."""
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        tc.return_value.submit_order.side_effect = transport_error
        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        with pytest.raises(TransientBrokerError):
            broker.submit_order(_req())
        calls = tc.return_value.submit_order.call_args_list
        assert len(calls) == 3
        assert {c.kwargs["order_data"].client_order_id for c in calls} == {"sig-1-a1"}


def test_transient_then_success_returns_result(no_retry_sleep) -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        tc.return_value.submit_order.side_effect = [
            requests.exceptions.ReadTimeout("read timed out"),
            _order(),
        ]
        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        assert broker.submit_order(_req()).broker_order_id == "brk-9"


def test_error_message_scrubbed_of_credentials() -> None:
    """Review R9: an error body echoing a credential must not leave the adapter."""
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        tc.return_value.submit_order.side_effect = _api_error(
            (422, '{"code":42210000,"message":"bad header APCA-API-SECRET-KEY: s3cr3t-value"}')
        )
        broker = AlpacaPaperBroker(api_key="PKLIVE123", secret="s3cr3t-value", host=PAPER)
        with pytest.raises(BrokerRejected) as exc:
            broker.submit_order(_req())
        assert "s3cr3t-value" not in str(exc.value)


# --------------------------------------------------------------------------- lookup by client id


def test_get_order_by_client_order_id_maps_result() -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        tc.return_value.get_order_by_client_id.return_value = _order()
        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        res = broker.get_order_by_client_order_id("sig-1-a1")
        tc.return_value.get_order_by_client_id.assert_called_once_with("sig-1-a1")
        assert res is not None and res.broker_order_id == "brk-9" and res.qty == 5


def test_get_order_by_client_order_id_none_when_absent() -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        tc.return_value.get_order_by_client_id.side_effect = _api_error(NOT_FOUND)
        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        assert broker.get_order_by_client_order_id("sig-1-a1") is None


# --------------------------------------------------------------------------- error classification


def test_classify_duplicate() -> None:
    assert isinstance(_classify_api_error(_api_error(DUPLICATE)), DuplicateClientOrderId)


@pytest.mark.parametrize("shape", [UNKNOWN_SYMBOL, COID_TOO_LONG], ids=["symbol", "coid-length"])
def test_classify_other_422_is_plain_rejection(shape) -> None:
    """Review R5: 42210000 also means 'unknown symbol', and a message merely
    *mentioning* client_order_id (too long) is a validation error, not a duplicate."""
    out = _classify_api_error(_api_error(shape))
    assert isinstance(out, BrokerRejected) and not isinstance(out, DuplicateClientOrderId)


def test_classify_401_is_an_auth_failure_not_an_order_rejection() -> None:
    """Review R5: bad credentials are not a broker verdict on the order -- they
    must not be recorded as 'rejected' and burn an attempt."""
    out = _classify_api_error(_api_error(UNAUTHORIZED))
    assert isinstance(out, BrokerAuthError) and not isinstance(out, BrokerRejected)


def test_classify_403_buying_power_is_an_order_rejection() -> None:
    """Round-2 re-review: Alpaca uses 403 for 'insufficient buying power' (probed).
    That *is* the broker's verdict on the order -- record it, don't treat it as auth."""
    out = _classify_api_error(_api_error(BUYING_POWER))
    assert isinstance(out, BrokerRejected) and not isinstance(out, DuplicateClientOrderId)


@pytest.mark.parametrize("shape", [SERVER_ERROR, RATE_LIMITED], ids=["503", "429"])
def test_classify_server_and_rate_limit_are_transient(shape) -> None:
    assert isinstance(_classify_api_error(_api_error(shape)), TransientBrokerError)


def test_cancel_delegates() -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        broker.cancel_order("brk-9")
        tc.return_value.cancel_order_by_id.assert_called_once_with("brk-9")


def test_result_maps_order_type_and_limit_price_cents() -> None:
    """Adoption records the broker's own order type and limit price (round-2 re-review)."""
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        held = _order()
        held.order_type, held.limit_price = "limit", "187.25"
        tc.return_value.get_order_by_client_id.return_value = held
        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        res = broker.get_order_by_client_order_id("sig-1-a1")
        assert res is not None and (res.order_type, res.limit_price_cents) == ("limit", 18_725)
