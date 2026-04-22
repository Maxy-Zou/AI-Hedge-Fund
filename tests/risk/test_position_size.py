"""Tests for :func:`ai_hedge_fund.risk.checks.check_position_size`.

Covers the RISK-02 hard-limit rejection contract (06-03 Task 1, behaviours 1-3):

- Approval when candidate size is below the policy cap.
- Rejection (NOT silent capping) when candidate exceeds the cap.
- Approval when candidate is exactly at the cap (inclusive boundary).
"""

from __future__ import annotations

import pytest

from ai_hedge_fund.risk.checks import check_position_size
from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.schemas.risk import Violation


@pytest.fixture()
def policy_10pct() -> RiskPolicy:
    return RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.80,
        max_projected_drawdown_pct=25.0,
    )


def test_candidate_below_limit_is_approved(policy_10pct: RiskPolicy) -> None:
    assert check_position_size(5.0, policy_10pct) is None


def test_candidate_above_limit_is_rejected_not_capped(policy_10pct: RiskPolicy) -> None:
    result = check_position_size(15.0, policy_10pct)

    assert isinstance(result, Violation)
    assert result.name == "max_single_position_pct"
    assert result.observed == 15.0
    assert result.limit == 10.0


def test_candidate_exactly_at_limit_is_inclusive(policy_10pct: RiskPolicy) -> None:
    assert check_position_size(10.0, policy_10pct) is None
