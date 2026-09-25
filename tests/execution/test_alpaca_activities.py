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
from ai_hedge_fund.execution.errors import BrokerAuthError, UnexpectedBrokerResponse
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
    [act] = broker.list_activities(["FILL"], since=date(2026, 9, 1)).activities
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
    acts = broker.list_activities(["FILL"], since=date(2026, 9, 1)).activities
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
    acts = broker.list_activities(["FILL"], since=date(2026, 9, 1)).activities
    assert [a.activity_id.rsplit("-", 1)[1] for a in acts] == ["3"]


@pytest.mark.parametrize("qty", ["0.5", "5.25"])
def test_fractional_qty_is_rejected_not_truncated(qty: str) -> None:
    """11-PREMORTEM #19: whole shares only; never truncated (a rejection since review H2)."""
    broker, _ = _broker([[_fill(qty=qty)]])
    batch = broker.list_activities(["FILL"], since=date(2026, 9, 1))
    assert batch.activities == []
    assert qty in batch.rejected[0].reason


def test_dividend_net_amount_in_cents() -> None:
    broker, _ = _broker([[_div()]])
    [act] = broker.list_activities(["DIV"], since=date(2026, 9, 1)).activities
    assert act.activity_type == "DIV"
    assert act.net_amount_cents == 240
    assert act.occurred_at == datetime(2026, 9, 15, 4, 0, tzinfo=UTC)  # 00:00 ET
    assert act.broker_order_id is None and act.qty is None and act.price_cents is None


def test_withholding_is_negative_cents() -> None:
    """11-PREMORTEM #20: the sign survives."""
    broker, _ = _broker([[_div("DIVWH", net="-0.36")]])
    [act] = broker.list_activities(["DIVWH"], since=date(2026, 9, 1)).activities
    assert act.net_amount_cents == -36


def test_sub_cent_amount_rounds_half_even() -> None:
    broker, _ = _broker([[_div(net="0.125")]])
    [act] = broker.list_activities(["DIV"], since=date(2026, 9, 1)).activities
    assert act.net_amount_cents == 12


@pytest.mark.parametrize(
    "body",
    [{"message": "not a list"}, None, [["not", "an", "object"]], [{"activity_type": "FILL"}]],
    ids=["dict-body", "null-body", "non-object-item", "item-without-id"],
)
def test_unexpected_response_shape_raises(body: object) -> None:
    """11-PREMORTEM #30: vendor drift in the response fails loudly, never an empty list."""
    broker, _ = _broker([body])
    with pytest.raises(UnexpectedBrokerResponse):
        broker.list_activities(["FILL", "DIV"], since=date(2026, 9, 1))


@pytest.mark.parametrize(
    "item",
    [{"id": "x", "activity_type": "FILL"}, _fill(price="abc"), _div(net_amount=None)],
    ids=["missing-fields", "bad-price", "null-net"],
)
def test_unusable_item_is_rejected_with_reason(item: dict) -> None:
    """Item-level drift is reported per item (review H2), never silently dropped."""
    broker, _ = _broker([[item]])
    batch = broker.list_activities(["FILL", "DIV"], since=date(2026, 9, 1))
    assert batch.activities == [] and batch.rejected[0].reason


def test_api_error_is_classified_and_scrubbed() -> None:
    broker, _ = _broker(_api_error(UNAUTHORIZED))
    with pytest.raises(BrokerAuthError) as exc:
        broker.list_activities(["FILL"], since=date(2026, 9, 1))
    assert "secret-456" not in str(exc.value)


# --------------------------------------------------------------------------- review round (T10)

# Shaped like Alpaca's documented examples (docs.alpaca.markets account-activities, read
# 2026-09-25): no account_id, no order_status on FILL, no description/status on DIV.
DOC_FILL = {
    "activity_type": "FILL",
    "cum_qty": "1",
    "id": "20190524113406977::8efc7b9a-8b2b-4000-9955-d36e7db0df74",
    "leaves_qty": "0",
    "price": "1.63",
    "qty": "1",
    "side": "buy",
    "symbol": "LPCN",
    "transaction_time": "2019-05-24T15:34:06.977Z",
    "order_id": "904837e3-3b76-47ec-b432-046db621571b",
    "type": "fill",
}
DOC_DIV = {
    "activity_type": "DIV",
    "id": "20190801011955195::5f596936-6f23-4cef-bdf1-3806aae57dbf",
    "date": "2019-08-01",
    "net_amount": "1.02",
    "symbol": "T",
    "qty": "2",
    "per_share_amount": "0.51",
}


def test_documented_fill_shape_parses() -> None:
    """Review H1: the SDK model's extra required fields must not reject the documented shape."""
    broker, _ = _broker([[DOC_FILL]])
    [act] = broker.list_activities(["FILL"], since=date(2019, 5, 1)).activities
    assert (act.qty, act.price_cents, act.side, act.symbol) == (1, 163, "buy", "LPCN")


def test_documented_div_shape_parses() -> None:
    broker, _ = _broker([[DOC_DIV]])
    [act] = broker.list_activities(["DIV"], since=date(2019, 7, 1)).activities
    assert (act.net_amount_cents, act.symbol) == (102, "T")


def test_one_bad_activity_does_not_abort_the_batch() -> None:
    """Review H2: a manual short or fractional trade is reported, not fatal."""
    short = _fill(2, side="sell_short", order_id="manual-short")
    frac = _fill(3, qty="0.5", order_id="manual-frac")
    broker, _ = _broker([[_fill(1), short, frac]])
    batch = broker.list_activities(["FILL"], since=date(2026, 9, 1))
    assert [a.activity_id for a in batch.activities] == ["20260902143000000::fill-1"]
    rejected = {r.order_id: r.reason for r in batch.rejected}
    assert set(rejected) == {"manual-short", "manual-frac"}
    assert "sell_short" in rejected["manual-short"] and "fractional" in rejected["manual-frac"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"qty": "0"},
        {"qty": "-3"},
        {"price": "0"},
        {"price": "-1"},
        {"price": "1e999999999"},
        {"transaction_time": "2026-09-02T14:30:00"},  # naive
        {"symbol": "aapl"},
    ],
    ids=["qty-0", "qty-neg", "price-0", "price-neg", "overflow", "naive-time", "lowercase"],
)
def test_invalid_fill_values_are_rejected(overrides: dict) -> None:
    broker, _ = _broker([[_fill(1, **overrides)]])
    batch = broker.list_activities(["FILL"], since=date(2026, 9, 1))
    assert batch.activities == [] and len(batch.rejected) == 1


def test_canceled_cash_activity_is_rejected() -> None:
    broker, _ = _broker([[_div(status="canceled")]])
    batch = broker.list_activities(["DIV"], since=date(2026, 9, 1))
    assert batch.activities == [] and "canceled" in batch.rejected[0].reason


def test_non_json_body_is_typed() -> None:
    import requests as _requests

    broker, _ = _broker(_requests.exceptions.JSONDecodeError("x", "<html>", 0))
    with pytest.raises(UnexpectedBrokerResponse):
        broker.list_activities(["FILL"], since=date(2026, 9, 1))


def test_page_token_cycle_raises() -> None:
    page_a = [_fill(n) for n in range(100)]
    page_b = [_fill(n) for n in range(100, 200)]
    broker, _ = _broker([page_a, page_b, page_a, page_b])
    with pytest.raises(UnexpectedBrokerResponse, match="repeated"):
        broker.list_activities(["FILL"], since=date(2026, 9, 1))


def test_secrets_in_raw_are_scrubbed() -> None:
    """Review M2 (#32 strengthened): scrubbing happens in the adapter, not upstream."""
    broker, _ = _broker([[_fill(1, description="key-123 secret-456")]])
    [act] = broker.list_activities(["FILL"], since=date(2026, 9, 1)).activities
    dumped = str(act.raw)
    assert "key-123" not in dumped and "secret-456" not in dumped
