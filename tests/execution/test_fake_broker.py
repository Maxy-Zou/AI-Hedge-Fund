"""Phase 10 T5 -- the FakeBroker itself honours the BrokerClient contract."""

from __future__ import annotations

import pytest

from ai_hedge_fund.execution.broker import BrokerOrderRequest
from ai_hedge_fund.execution.errors import DuplicateClientOrderId, TransientBrokerError
from tests.execution.fakes import FakeBroker


def _req(coid: str = "sig-1-a1") -> BrokerOrderRequest:
    return BrokerOrderRequest(
        client_order_id=coid,
        symbol="AAPL",
        side="buy",
        qty=10,
        order_type="market",
        limit_price_cents=None,
    )


def test_records_requests_and_returns_result() -> None:
    b = FakeBroker()
    r = b.submit_order(_req())
    assert b.calls == 1 and b.requests[0].symbol == "AAPL"
    assert r.broker_order_id == "fake-1" and r.status == "accepted"


def test_duplicate_client_order_id_raises() -> None:
    b = FakeBroker()
    b.submit_order(_req("sig-1-a1"))
    with pytest.raises(DuplicateClientOrderId):
        b.submit_order(_req("sig-1-a1"))
    assert b.calls == 2  # the attempt was recorded even though it was rejected


def test_scripted_failure() -> None:
    b = FakeBroker(fail_with=RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        b.submit_order(_req())


def test_lookup_by_client_order_id() -> None:
    b = FakeBroker()
    r = b.submit_order(_req("sig-1-a1"))
    assert b.get_order_by_client_order_id("sig-1-a1") == r
    assert b.get_order_by_client_order_id("missing") is None


def test_lose_response_once_keeps_the_order() -> None:
    b = FakeBroker(lose_response_once=True)
    with pytest.raises(TransientBrokerError):
        b.submit_order(_req("sig-1-a1"))
    assert b.get_order_by_client_order_id("sig-1-a1") is not None  # accepted at the broker
