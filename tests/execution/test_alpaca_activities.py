"""Phase 11 T4 -- AlpacaPaperBroker.list_activities (11-SPEC s4; SDK mocked, no network).

alpaca-py 0.44.0 has activity *models* but no TradingClient method for
``/account/activities``, so the adapter calls the SDK's own ``RESTClient.get``
(same auth and paper-host guard). Probed live 2026-09-25: the endpoint returns a
JSON list; the paper account had no FILL/DIV activity yet, so item bodies below
follow Alpaca's documented shape (strings for money and quantity).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest

from ai_hedge_fund.execution.alpaca import AlpacaPaperBroker
from ai_hedge_fund.execution.errors import (
    BrokerAuthError,
    FractionalQuantity,
    UnexpectedBrokerResponse,
)
from tests.execution.test_alpaca_adapter import PAPER, UNAUTHORIZED, _api_error

ACCOUNT = "904837e3-3b76-47ec-b432-046db621571b"


def _fill(n: int = 1, **overrides: object) -> dict:
    item = {
        "id": f"20260902143000000::fill-{n}",
        "account_id": ACCOUNT,
        "activity_type": "FILL",
        "transaction_time": "2026-09-02T14:30:00.123Z",
        "type": "fill",
        "price": "187.25",
        "qty": "5",
        "side": "buy",
        "symbol": "AAPL",
        "leaves_qty": "0",
        "order_id": "61e69015-8549-4bfd-b9c3-01e75843f47d",
        "cum_qty": "5",
        "order_status": "filled",
    }
    return {**item, **overrides}


def _div(activity_type: str = "DIV", net: str = "2.40", **overrides: object) -> dict:
    item = {
        "id": f"20260915000000000::{activity_type.lower()}-1",
        "account_id": ACCOUNT,
        "activity_type": activity_type,
        "date": "2026-09-15",
        "net_amount": net,
        "description": "",
        "symbol": "AAPL",
        "qty": "10",
        "per_share_amount": "0.24",
    }
    return {**item, **overrides}


def _broker(get_side_effect) -> tuple[AlpacaPaperBroker, MagicMock]:
    with patch("ai_hedge_fund.execution.alpaca.TradingClient") as tc:
        broker = AlpacaPaperBroker("key-123", "secret-456", PAPER)
    client = tc.return_value
    client.get.side_effect = get_side_effect
    return broker, client


def test_fill_is_mapped_exactly() -> None:
    broker, client = _broker([[_fill()]])
    [act] = broker.list_activities(["FILL"], since=date(2026, 9, 1))
    assert act.activity_id == "20260902143000000::fill-1"
    assert act.activity_type == "FILL"
    assert act.symbol == "AAPL"
    assert act.broker_order_id == "61e69015-8549-4bfd-b9c3-01e75843f47d"
    assert act.side == "buy"
    assert act.qty == 5 and isinstance(act.qty, int)
    assert act.price_cents == 18_725 and isinstance(act.price_cents, int)
    assert act.occurred_at == datetime(2026, 9, 2, 14, 30, 0, 123000, tzinfo=UTC)
    assert act.net_amount_cents is None
    assert "account_id" not in act.raw


def test_request_goes_through_the_guarded_sdk_client() -> None:
    """11-PREMORTEM #31: no hand-built URL; the adapter's TradingClient makes the call."""
    broker, client = _broker([[]])
    with patch("requests.get") as raw_get, patch("requests.request") as raw_request:
        broker.list_activities(["FILL", "DIV"], since=date(2026, 9, 1))
    raw_get.assert_not_called()
    raw_request.assert_not_called()
    path, params = client.get.call_args.args
    assert path == "/account/activities"
    assert params["activity_types"] == "FILL,DIV"
    assert params["direction"] == "asc"
    assert params["page_size"] == 100


def test_follows_page_token_until_short_page() -> None:
    """11-PREMORTEM #29: every page is read, not just the first 100."""
    page1 = [_fill(n) for n in range(100)]
    page2 = [_fill(100)]
    broker, client = _broker([page1, page2])
    acts = broker.list_activities(["FILL"], since=date(2026, 9, 1))
    assert len(acts) == 101
    assert client.get.call_count == 2
    assert "page_token" not in client.get.call_args_list[0].args[1]
    assert client.get.call_args_list[1].args[1]["page_token"] == page1[-1]["id"]


def test_activities_before_since_are_dropped() -> None:
    """``after`` is requested a day early (timezone slack) and filtered to the NY date."""
    early = _fill(1, transaction_time="2026-08-31T19:00:00Z")  # 15:00 ET on Aug 31
    late_evening = _fill(2, transaction_time="2026-09-01T01:00:00Z")  # 21:00 ET Aug 31
    on_day = _fill(3, transaction_time="2026-09-01T14:00:00Z")
    broker, _ = _broker([[early, late_evening, on_day]])
    acts = broker.list_activities(["FILL"], since=date(2026, 9, 1))
    assert [a.activity_id.rsplit("-", 1)[1] for a in acts] == ["3"]


@pytest.mark.parametrize("qty", ["0.5", "5.25"])
def test_fractional_qty_raises(qty: str) -> None:
    """11-PREMORTEM #19: whole shares only; never truncated."""
    broker, _ = _broker([[_fill(qty=qty)]])
    with pytest.raises(FractionalQuantity, match=qty):
        broker.list_activities(["FILL"], since=date(2026, 9, 1))


def test_dividend_net_amount_in_cents() -> None:
    broker, _ = _broker([[_div()]])
    [act] = broker.list_activities(["DIV"], since=date(2026, 9, 1))
    assert act.activity_type == "DIV"
    assert act.net_amount_cents == 240
    assert act.occurred_at == datetime(2026, 9, 15, 4, 0, tzinfo=UTC)  # 00:00 ET
    assert act.broker_order_id is None and act.qty is None and act.price_cents is None


def test_withholding_is_negative_cents() -> None:
    """11-PREMORTEM #20: the sign survives."""
    broker, _ = _broker([[_div("DIVWH", net="-0.36")]])
    [act] = broker.list_activities(["DIVWH"], since=date(2026, 9, 1))
    assert act.net_amount_cents == -36


def test_sub_cent_amount_rounds_half_even() -> None:
    broker, _ = _broker([[_div(net="0.125")]])
    [act] = broker.list_activities(["DIV"], since=date(2026, 9, 1))
    assert act.net_amount_cents == 12


@pytest.mark.parametrize(
    "body",
    [
        {"message": "not a list"},
        [{"id": "x", "activity_type": "FILL"}],  # missing required fields
        [_fill(price="abc")],
        [_div(net_amount=None)],
    ],
    ids=["dict-body", "missing-fields", "bad-price", "null-net"],
)
def test_unexpected_shape_raises(body: object) -> None:
    """11-PREMORTEM #30: vendor drift fails loudly, never returns an empty list."""
    broker, _ = _broker([body])
    with pytest.raises(UnexpectedBrokerResponse):
        broker.list_activities(["FILL", "DIV"], since=date(2026, 9, 1))


def test_api_error_is_classified_and_scrubbed() -> None:
    broker, _ = _broker(_api_error(UNAUTHORIZED))
    with pytest.raises(BrokerAuthError) as exc:
        broker.list_activities(["FILL"], since=date(2026, 9, 1))
    assert "secret-456" not in str(exc.value)
