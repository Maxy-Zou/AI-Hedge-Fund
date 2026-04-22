"""Tests for :func:`ai_hedge_fund.risk.sizing.derive_candidate_size_pct`.

Covers the A4 conviction-to-size mapping (06-03 Task 1, behaviours 10-13):

    high   -> max_single_position_pct * size_high_conviction_multiplier
    medium -> max_single_position_pct * size_medium_conviction_multiplier
    low    -> max_single_position_pct * size_low_conviction_multiplier
    other  -> ValueError
"""

from __future__ import annotations

import pytest

from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.sizing import derive_candidate_size_pct


@pytest.fixture()
def default_policy() -> RiskPolicy:
    return RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.80,
        max_projected_drawdown_pct=25.0,
    )


def test_high_conviction_uses_full_multiplier(default_policy: RiskPolicy) -> None:
    assert derive_candidate_size_pct("high", default_policy) == pytest.approx(10.0)


def test_medium_conviction_uses_half_multiplier(default_policy: RiskPolicy) -> None:
    assert derive_candidate_size_pct("medium", default_policy) == pytest.approx(5.0)


def test_low_conviction_uses_quarter_multiplier(default_policy: RiskPolicy) -> None:
    assert derive_candidate_size_pct("low", default_policy) == pytest.approx(2.5)


def test_unknown_conviction_raises_value_error(default_policy: RiskPolicy) -> None:
    with pytest.raises(ValueError, match="conviction"):
        derive_candidate_size_pct("reckless", default_policy)  # type: ignore[arg-type]
