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


# ------------------------------------------------------------------ fail closed (review R6)


def _decide(sig=None, *, risk="APPROVED", review="NOT_REQUIRED", policy=POLICY):
    return decide(
        _sig() if sig is None else sig,
        risk_status=risk,
        review_status=review,
        price_cents=10_000,
        policy=policy,
    )


@pytest.mark.parametrize("direction", ["LONG", "Short", "bullish", "", None, 1])
@pytest.mark.parametrize("policy", [POLICY, SHORT_OK], ids=["long_only", "shorts_ok"])
def test_unknown_direction_is_refused_never_a_sell(direction, policy) -> None:
    """Review R6: anything but exactly long/short/neutral used to become side='sell'."""
    d = _decide({"ticker": "AAPL", "direction": direction, "conviction": 90}, policy=policy)
    assert isinstance(d, Refusal) and d.reason == "invalid_signal", d


@pytest.mark.parametrize("risk", ["UNKNOWN", "approved", "", "PENDING"])
def test_unknown_risk_status_is_refused(risk) -> None:
    """Review R6: only an explicit APPROVED may trade; VETOED is the veto path."""
    d = _decide(risk=risk)
    assert isinstance(d, Refusal) and d.reason == "invalid_signal", d


@pytest.mark.parametrize("review", [None, "rejected", "MAYBE", ""])
def test_unknown_review_status_is_refused(review) -> None:
    """Review R6: only APPROVED or NOT_REQUIRED (below the review threshold) may trade."""
    d = _decide(review=review)
    assert isinstance(d, Refusal) and d.reason == "invalid_signal", d


@pytest.mark.parametrize("conviction", [None, "90", 101, -1, True, 80.5])
def test_invalid_conviction_is_refused(conviction) -> None:
    d = _decide({"ticker": "AAPL", "direction": "long", "conviction": conviction})
    assert isinstance(d, Refusal) and d.reason == "invalid_signal", d


def test_missing_final_signal_on_approved_path_is_invalid_not_neutral() -> None:
    d = decide(
        None, risk_status="APPROVED", review_status="APPROVED", price_cents=10_000, policy=POLICY
    )
    assert isinstance(d, Refusal) and d.reason == "invalid_signal"


@pytest.mark.parametrize("review", ["APPROVED", "NOT_REQUIRED"])
def test_valid_go_statuses_still_trade(review) -> None:
    assert isinstance(_decide(review=review), OrderPlan)
