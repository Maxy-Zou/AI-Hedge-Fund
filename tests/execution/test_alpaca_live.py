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
from ai_hedge_fund.execution.errors import DuplicateClientOrderId

pytestmark = pytest.mark.slow


def _broker_or_skip():
    if not os.environ.get("ALPACA_PAPER_API_KEY") or not os.environ.get("ALPACA_PAPER_SECRET"):
        pytest.skip("ALPACA_PAPER_API_KEY/_SECRET not set; live paper smoke skipped")
    settings = get_settings()
    if "paper-api" not in settings.alpaca_paper_host:
        pytest.skip("host is not a paper endpoint")
    from ai_hedge_fund.execution.alpaca import AlpacaPaperBroker

    return AlpacaPaperBroker.from_settings(settings)


def _far_below_market(coid: str) -> BrokerOrderRequest:
    return BrokerOrderRequest(
        client_order_id=coid,
        symbol="SPY",
        side="buy",
        qty=1,
        order_type="limit",
        limit_price_cents=100,  # $1.00, far below market -> stays open
    )


def test_paper_roundtrip() -> None:
    broker = _broker_or_skip()
    coid = f"smoke-{uuid.uuid4().hex[:12]}"
    result = broker.submit_order(_far_below_market(coid))
    try:
        assert result.broker_order_id
        assert result.raw.get("client_order_id") == coid
    finally:
        broker.cancel_order(result.broker_order_id)


def test_duplicate_is_classified_and_lookup_finds_the_order() -> None:
    """Review R3/R5 against the real API: a resent client_order_id is classified
    as a duplicate (by message; its code is shared with other 422s), and lookup
    by client_order_id returns the held order that submit_signal would adopt."""
    broker = _broker_or_skip()
    coid = f"smoke-{uuid.uuid4().hex[:12]}"
    first = broker.submit_order(_far_below_market(coid))
    try:
        with pytest.raises(DuplicateClientOrderId):
            broker.submit_order(_far_below_market(coid))
        held = broker.get_order_by_client_order_id(coid)
        assert held is not None and held.broker_order_id == first.broker_order_id
        assert (held.symbol, held.side, held.qty) == ("SPY", "buy", 1)
        # adoption records these from the real Order object (enum/decimal-string mapping)
        assert (held.order_type, held.limit_price_cents, held.filled_qty) == ("limit", 100, 0)
        assert broker.get_order_by_client_order_id(f"smoke-missing-{uuid.uuid4().hex[:8]}") is None
    finally:
        broker.cancel_order(first.broker_order_id)


def test_list_activities_roundtrip() -> None:
    """Phase 11 (11-PREMORTEM #30/#31) against the real API: read-only.

    Proves the SDK-client path (auth, paper host, /account/activities, paging
    params) returns typed activities. On 2026-09-25 the paper account had none,
    so an empty list is a pass; any item returned must parse to the typed shape.
    """
    from datetime import UTC, datetime, timedelta

    from ai_hedge_fund.db.dates import trading_date
    from ai_hedge_fund.mtm.ingest import ACTIVITY_TYPES

    broker = _broker_or_skip()
    since = trading_date(datetime.now(UTC)) - timedelta(days=90)
    activities = broker.list_activities(ACTIVITY_TYPES, since)
    assert isinstance(activities, list)
    for act in activities:
        assert act.activity_type in ACTIVITY_TYPES
        assert trading_date(act.occurred_at) >= since
        if act.activity_type == "FILL":
            assert isinstance(act.qty, int) and isinstance(act.price_cents, int)
        else:
            assert isinstance(act.net_amount_cents, int)
