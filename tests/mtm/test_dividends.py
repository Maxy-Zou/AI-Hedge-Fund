"""Phase 11 T7 -- pro-rata dividend apportionment across signals (11-SPEC s5)."""

from __future__ import annotations

import random

import pytest

from ai_hedge_fund.mtm.dividends import apportion


@pytest.mark.parametrize(
    ("amount", "weights", "expected"),
    [
        (100, {1: 30, 2: 10}, {1: 75, 2: 25}),
        (101, {1: 30, 2: 10}, {1: 76, 2: 25}),  # leftover cent -> lowest signal id
        (101, {2: 30, 1: 10}, {1: 26, 2: 75}),
        (-36, {1: 5, 2: 5}, {1: -18, 2: -18}),  # withholding
        (-37, {1: 5, 2: 5}, {1: -18, 2: -19}),
        (240, {9: 10}, {9: 240}),
    ],
)
def test_apportion_table(amount: int, weights: dict[int, int], expected: dict[int, int]) -> None:
    assert apportion(amount, weights) == expected


def test_no_holders_means_nothing_allocated() -> None:
    assert apportion(240, {}) == {}
    assert apportion(240, {1: 0, 2: 0}) == {}


def test_zero_weight_holders_get_nothing() -> None:
    assert apportion(100, {1: 0, 2: 4}) == {2: 100}


def test_negative_weight_rejected() -> None:
    with pytest.raises(ValueError, match="weight"):
        apportion(100, {1: -1, 2: 3})


def test_always_sums_exactly() -> None:
    """11-PREMORTEM #15: every cent the broker paid is credited exactly once."""
    rng = random.Random(11)
    for _ in range(2_000):
        weights = {sid: rng.randint(0, 500) for sid in range(1, rng.randint(2, 6))}
        amount = rng.randint(-50_000, 500_000)
        out = apportion(amount, weights)
        if any(weights.values()):
            assert sum(out.values()) == amount
        else:
            assert out == {}
