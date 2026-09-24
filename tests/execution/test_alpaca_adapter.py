"""Phase 10 T5 -- AlpacaPaperBroker adapter (SDK mocked at the client boundary).

Guards: paper-only host (09-PREMORTEM #1), credentials named at construction
(#17), error classification (#2 no retry on rejection). No network.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from alpaca.common.exceptions import APIError

from ai_hedge_fund.execution.alpaca import AlpacaPaperBroker, _classify_api_error
from ai_hedge_fund.execution.broker import BrokerOrderRequest
from ai_hedge_fund.execution.errors import (
    BrokerRejected,
    DuplicateClientOrderId,
    LiveEndpointRefused,
    MissingBrokerCredentials,
    TransientBrokerError,
)

PAPER = "https://paper-api.alpaca.markets"


def _req() -> BrokerOrderRequest:
    return BrokerOrderRequest(
        client_order_id="sig-1-a1",
        symbol="AAPL",
        side="buy",
        qty=5,
        order_type="market",
        limit_price_cents=None,
    )


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


def test_live_host_refused() -> None:
    with (
        pytest.raises(LiveEndpointRefused),
        patch("ai_hedge_fund.execution.alpaca.TradingClient"),
    ):
        AlpacaPaperBroker(api_key="PK", secret="s", host="https://api.alpaca.markets")


def test_paper_host_constructs() -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        assert tc.called


# --------------------------------------------------------------------------- submit mapping


def test_submit_passes_client_order_id_and_maps_result() -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        order = MagicMock()
        order.id = "brk-9"
        order.status = "accepted"
        order.submitted_at = __import__("datetime").datetime(
            2026, 4, 18, tzinfo=__import__("datetime").UTC
        )
        order.model_dump.return_value = {"id": "brk-9", "client_order_id": "sig-1-a1"}
        tc.return_value.submit_order.return_value = order

        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        res = broker.submit_order(_req())

        sent = tc.return_value.submit_order.call_args.kwargs["order_data"]
        assert sent.client_order_id == "sig-1-a1"
        assert res.broker_order_id == "brk-9"


def test_duplicate_client_order_id_maps_to_typed_error() -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        tc.return_value.submit_order.side_effect = APIError(
            '{"code":40010001,"message":"client_order_id must be unique"}'
        )
        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        with pytest.raises(DuplicateClientOrderId):
            broker.submit_order(_req())


def test_other_api_error_maps_to_broker_rejected() -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        tc.return_value.submit_order.side_effect = APIError(
            '{"code":40010000,"message":"insufficient buying power"}'
        )
        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        with pytest.raises(BrokerRejected):
            broker.submit_order(_req())


# --------------------------------------------------------------------------- error classification


def test_classify_duplicate() -> None:
    exc = APIError('{"code":40010001,"message":"client_order_id must be unique"}')
    assert isinstance(_classify_api_error(exc), DuplicateClientOrderId)


def test_classify_generic_rejection() -> None:
    exc = APIError('{"code":40010000,"message":"insufficient buying power"}')
    out = _classify_api_error(exc)
    assert isinstance(out, BrokerRejected) and not isinstance(out, DuplicateClientOrderId)


def test_classify_server_error_is_transient() -> None:
    exc = APIError('{"message":"internal"}')
    exc.__dict__["_http_error"] = None
    with patch.object(type(exc), "status_code", 503):
        assert isinstance(_classify_api_error(exc), TransientBrokerError)


def test_cancel_delegates() -> None:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        broker = AlpacaPaperBroker(api_key="PK", secret="s", host=PAPER)
        broker.cancel_order("brk-9")
        tc.return_value.cancel_order_by_id.assert_called_once_with("brk-9")
