"""Phase 10 T6 -- the pure decision function (EXEC-04, D5, D7; 09-PREMORTEM #5/#6/#16)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_hedge_fund.execution.decide import OrderPlan, Refusal, decide
from ai_hedge_fund.execution.policy import ExecutionPolicy

POLICY = ExecutionPolicy(
    nav_cents=10_000_000,
    max_position_pct=0.05,
    min_conviction=55,
    full_conviction=90,
    long_only=True,
    max_attempts=3,
    order_type="market",
    limit_offset_bps=25,
)
SHORT_OK = POLICY.model_copy(update={"long_only": False})


def _sig(direction: str = "long", conviction: int = 80) -> dict:
    return {"ticker": "AAPL", "direction": direction, "conviction": conviction}


def test_vetoed_refuses_before_anything_else() -> None:
    # even with a fine signal and price, a veto wins
    d = decide(
        _sig(), risk_status="VETOED", review_status="APPROVED", price_cents=10_000, policy=POLICY
    )
    assert isinstance(d, Refusal) and d.status == "refused_veto" and d.reason == "risk_vetoed"


def test_vetoed_without_final_signal_still_refuses() -> None:
    d = decide(None, risk_status="VETOED", review_status=None, price_cents=None, policy=POLICY)
    assert isinstance(d, Refusal) and d.status == "refused_veto"


def test_review_rejected_refuses() -> None:
    d = decide(
        _sig(), risk_status="APPROVED", review_status="REJECTED", price_cents=10_000, policy=POLICY
    )
    assert isinstance(d, Refusal) and d.status == "refused_review" and d.reason == "review_rejected"


def test_neutral_direction_refuses() -> None:
    d = decide(
        _sig("neutral"),
        risk_status="APPROVED",
        review_status="NOT_REQUIRED",
        price_cents=10_000,
        policy=POLICY,
    )
    assert isinstance(d, Refusal) and d.reason == "neutral_direction"


def test_short_refused_when_long_only() -> None:
    d = decide(
        _sig("short"),
        risk_status="APPROVED",
        review_status="APPROVED",
        price_cents=10_000,
        policy=POLICY,
    )
    assert isinstance(d, Refusal) and d.status == "refused_policy" and d.reason == "long_only"


def test_short_becomes_sell_when_shorts_enabled() -> None:
    d = decide(
        _sig("short"),
        risk_status="APPROVED",
        review_status="APPROVED",
        price_cents=10_000,
        policy=SHORT_OK,
    )
    assert isinstance(d, OrderPlan) and d.side == "sell" and d.quantity > 0


def test_no_price_refuses() -> None:
    d = decide(
        _sig(),
        risk_status="APPROVED",
        review_status="NOT_REQUIRED",
        price_cents=None,
        policy=POLICY,
    )
    assert isinstance(d, Refusal) and d.reason == "no_price"


def test_below_min_size_refuses() -> None:
    # conviction below min -> scale 0 -> 0 shares -> refuse
    d = decide(
        _sig(conviction=40),
        risk_status="APPROVED",
        review_status="NOT_REQUIRED",
        price_cents=10_000,
        policy=POLICY,
    )
    assert isinstance(d, Refusal) and d.reason == "below_min_size"


def test_expensive_share_refuses_below_min_size() -> None:
    d = decide(
        _sig(conviction=90),
        risk_status="APPROVED",
        review_status="APPROVED",
        price_cents=900_000_00,
        policy=POLICY,
    )
    assert isinstance(d, Refusal) and d.reason == "below_min_size"


def test_approved_long_produces_buy_order() -> None:
    d = decide(
        _sig(), risk_status="APPROVED", review_status="APPROVED", price_cents=10_000, policy=POLICY
    )
    assert isinstance(d, OrderPlan) and d.side == "buy" and d.order_type == "market"
    assert d.quantity > 0 and d.size.price_cents == 10_000


def test_not_required_long_produces_order() -> None:
    d = decide(
        _sig(),
        risk_status="APPROVED",
        review_status="NOT_REQUIRED",
        price_cents=10_000,
        policy=POLICY,
    )
    assert isinstance(d, OrderPlan)


def test_limit_order_carries_price() -> None:
    policy_limit = POLICY.model_copy(update={"order_type": "limit"})
    d = decide(
        _sig(),
        risk_status="APPROVED",
        review_status="APPROVED",
        price_cents=10_000,
        policy=policy_limit,
    )
    assert isinstance(d, OrderPlan) and d.order_type == "limit" and d.limit_price_cents is not None


def test_veto_precedence_over_review_rejected() -> None:
    d = decide(
        _sig(), risk_status="VETOED", review_status="REJECTED", price_cents=10_000, policy=POLICY
    )
    assert isinstance(d, Refusal) and d.status == "refused_veto"


def test_decision_types_are_frozen() -> None:
    r = Refusal(status="refused_veto", reason="risk_vetoed")
    with pytest.raises(ValidationError):
        r.status = "x"  # type: ignore[misc]
