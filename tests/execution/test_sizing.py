"""Phase 10 T4 -- deterministic order sizing (D5; pure, integer, 09-PREMORTEM #9/#10)."""

from __future__ import annotations

from ai_hedge_fund.execution.policy import ExecutionPolicy
from ai_hedge_fund.execution.sizing import SizeResult, conviction_scale, size_order

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


def test_scale_is_zero_below_min() -> None:
    assert conviction_scale(54, POLICY) == 0.0
    assert conviction_scale(0, POLICY) == 0.0


def test_scale_is_one_at_or_above_full() -> None:
    assert conviction_scale(90, POLICY) == 1.0
    assert conviction_scale(100, POLICY) == 1.0


def test_scale_is_linear_between() -> None:
    # midpoint of [55, 90] is 72.5; 72 -> (72-55)/(90-55)=17/35
    assert conviction_scale(72, POLICY) == 17 / 35


def test_size_floors_to_whole_shares() -> None:
    # budget = 10_000_000 * 0.05 * 1.0 = 500_000 cents; price 18_500_00 -> 0 shares? no:
    # 500_000 / 1_850_000 = 0.27 -> 0. Use a cheaper price to get a real count.
    r = size_order(conviction=90, price_cents=10_000, policy=POLICY)  # $100.00
    # budget 500_000 cents / 10_000 = 50 shares
    assert isinstance(r, SizeResult) and r.shares == 50
    assert r.notional_cents == 50 * 10_000
    assert r.scale == 1.0 and r.price_cents == 10_000


def test_below_min_conviction_sizes_zero() -> None:
    r = size_order(conviction=40, price_cents=10_000, policy=POLICY)
    assert r.shares == 0


def test_expensive_share_floors_to_zero() -> None:
    r = size_order(conviction=90, price_cents=600_000_00, policy=POLICY)  # $600k share
    assert r.shares == 0


def test_scaled_budget_reduces_shares() -> None:
    full = size_order(conviction=90, price_cents=10_000, policy=POLICY).shares
    half = size_order(conviction=72, price_cents=10_000, policy=POLICY).shares
    assert 0 < half < full


def test_deterministic_same_inputs_same_output() -> None:
    a = size_order(conviction=80, price_cents=12_345, policy=POLICY)
    b = size_order(conviction=80, price_cents=12_345, policy=POLICY)
    assert a == b


def test_integer_arithmetic_no_float_drift() -> None:
    # Pick values where float multiplication would drift: 0.05 * conviction scaling.
    r = size_order(conviction=90, price_cents=3_333, policy=POLICY)
    # exact: floor(500_000 / 3_333) = 150
    assert r.shares == 150
    assert isinstance(r.shares, int) and isinstance(r.notional_cents, int)
