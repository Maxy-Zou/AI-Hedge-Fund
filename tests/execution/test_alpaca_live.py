"""Phase 10 T8 -- live paper smoke test (EXEC-01/05, 10.5).

Credential-gated and @slow: skips unless ALPACA_PAPER_API_KEY / _SECRET are set.
Refuses any non-paper host. Places a far-below-market limit buy of 1 share so
the order stays open (no fill, no position) regardless of market hours, asserts
the broker accepted it and the client_order_id round-trips, then cancels it.
Spends nothing.
"""

from __future__ import annotations

import os
import uuid

import pytest

from ai_hedge_fund.config import get_settings
from ai_hedge_fund.execution.broker import BrokerOrderRequest

pytestmark = pytest.mark.slow


def _broker_or_skip():
    if not os.environ.get("ALPACA_PAPER_API_KEY") or not os.environ.get("ALPACA_PAPER_SECRET"):
        pytest.skip("ALPACA_PAPER_API_KEY/_SECRET not set; live paper smoke skipped")
    settings = get_settings()
    if "paper-api" not in settings.alpaca_paper_host:
        pytest.skip("host is not a paper endpoint")
    from ai_hedge_fund.execution.alpaca import AlpacaPaperBroker

    return AlpacaPaperBroker.from_settings(settings)


def test_paper_roundtrip() -> None:
    broker = _broker_or_skip()
    coid = f"smoke-{uuid.uuid4().hex[:12]}"
    req = BrokerOrderRequest(
        client_order_id=coid,
        symbol="SPY",
        side="buy",
        qty=1,
        order_type="limit",
        limit_price_cents=100,  # $1.00, far below market -> stays open
    )
    result = broker.submit_order(req)
    try:
        assert result.broker_order_id
        assert result.raw.get("client_order_id") == coid
    finally:
        broker.cancel_order(result.broker_order_id)
