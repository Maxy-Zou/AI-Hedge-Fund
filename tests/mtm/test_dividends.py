"""Phase 11 T7 / review H5 -- per-signal dividend credit (11-SPEC s5)."""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from ai_hedge_fund.mtm.dividends import paid_shares, signal_credit


@pytest.mark.parametrize(
    ("amount", "shares", "paid", "expected"),
    [
        (240, 10, "10", 240),
        (240, 10, "20", 120),
        (101, 30, "40", 75),
        (101, 10, "40", 25),
        (-37, 5, "10", -18),  # withholding truncates toward zero
        (5_000, 10, "100", 500),
        (240, 0, "10", 0),
        (100, 1, "3.5", 28),  # fractional account holding
    ],
)
def test_signal_credit_table(amount: int, shares: int, paid: str, expected: int) -> None:
    assert signal_credit(amount, shares, Decimal(paid)) == expected


def test_credits_never_exceed_what_was_paid() -> None:
    """11-PREMORTEM #15 as amended: holders' credits sum to at most the payment."""
    rng = random.Random(11)
    for _ in range(2_000):
        holdings = [rng.randint(0, 500) for _ in range(rng.randint(1, 6))]
        paid = Decimal(sum(holdings) + rng.randint(0, 300)) or Decimal(1)
        amount = rng.randint(-50_000, 500_000)
        total = sum(signal_credit(amount, h, paid) for h in holdings)
        assert abs(total) <= abs(amount)
        assert (
            abs(amount) - abs(total) < len(holdings) + abs(amount) * (1 - sum(holdings) / paid) + 1
        )


@pytest.mark.parametrize(("shares", "paid"), [(-1, "10"), (1, "0"), (1, "-2")])
def test_invalid_inputs_rejected(shares: int, paid: str) -> None:
    with pytest.raises(ValueError):
        signal_credit(100, shares, Decimal(paid))


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"qty": "20"}, Decimal(20)),
        ({"qty": 7}, Decimal(7)),
        ({"qty": "2.5"}, Decimal("2.5")),
        ({}, None),
        ({"qty": "0"}, None),
        ({"qty": "-3"}, None),
        ({"qty": "abc"}, None),
        ({"qty": True}, None),
        ({"qty": "NaN"}, None),
    ],
)
def test_paid_shares_parsing(payload: dict, expected: Decimal | None) -> None:
    assert paid_shares(payload) == expected
