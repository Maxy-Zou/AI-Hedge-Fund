"""Phase 10 T4 -- deterministic order sizing (D5; pure, integer, 09-PREMORTEM #9/#10)."""

from __future__ import annotations

from fractions import Fraction

import pytest

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


def _policy(pct: str, lo: int, hi: int) -> ExecutionPolicy:
    return POLICY.model_copy(
        update={"max_position_pct": float(pct), "min_conviction": lo, "full_conviction": hi}
    )


def _exact_budget(pct: str, lo: int, hi: int, conviction: int) -> Fraction:
    """Reference: the budget in exact rational arithmetic, from the decimal as written."""
    if conviction < lo:
        return Fraction(0)
    scale = Fraction(1) if conviction >= hi else Fraction(conviction - lo, hi - lo)
    return POLICY.nav_cents * Fraction(pct) * scale


def test_boundary_budget_is_exact_not_float() -> None:
    """Review R4 counterexample: 10_000_000 * 0.01 * 29/50 is exactly 58_000 cents,
    but float math gives 57999.999... and truncates a whole share away."""
    assert (
        size_order(conviction=79, price_cents=58_000, policy=_policy("0.01", 50, 100)).shares == 1
    )


@pytest.mark.parametrize("pct", ["0.01", "0.02", "0.03", "0.05", "0.07", "0.1", "0.15", "0.3"])
@pytest.mark.parametrize("lo,hi", [(50, 100), (55, 90), (60, 85), (40, 95), (70, 71)])
def test_size_matches_exact_rational_reference(pct: str, lo: int, hi: int) -> None:
    """09-PREMORTEM #10: integer arithmetic only. At every exact-cent budget, a share
    priced at the budget must fit; at every other price the share count is the
    exact floor."""
    policy = _policy(pct, lo, hi)
    for conviction in range(lo - 1, hi + 2):
        exact = _exact_budget(pct, lo, hi, conviction)
        prices = [1_234, 9_999, 58_000]
        if exact.denominator == 1 and exact > 0:
            prices.append(int(exact))  # the boundary: exactly one share
        for price in prices:
            got = size_order(conviction=conviction, price_cents=price, policy=policy)
            assert got.shares == exact // price, (pct, lo, hi, conviction, price)
            assert isinstance(got.shares, int) and isinstance(got.notional_cents, int)
