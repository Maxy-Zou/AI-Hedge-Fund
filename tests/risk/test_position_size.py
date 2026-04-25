"""Tests for :func:`ai_hedge_fund.risk.checks.check_position_size`.

Covers the RISK-02 hard-limit rejection contract (06-03 Task 1, behaviours 1-3)
plus the post-fix utilization contract (08-RESEARCH.md A9):

- Approval when candidate size is below the policy cap.
- Rejection (NOT silent capping) when candidate exceeds the cap.
- Approval when candidate is exactly at the cap (inclusive boundary).
- ``CheckResult.ratio`` is always ``observed / limit`` regardless of
  approval -- the node aggregates this into ``RiskAssessment.utilization``.
"""

from __future__ import annotations

import pytest

from ai_hedge_fund.risk.checks import check_position_size
from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.schemas.risk import CheckResult, Violation


@pytest.fixture()
def policy_10pct() -> RiskPolicy:
    return RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.80,
        max_projected_drawdown_pct=25.0,
    )


def test_candidate_below_limit_is_approved(policy_10pct: RiskPolicy) -> None:
    result = check_position_size(5.0, policy_10pct)

    assert isinstance(result, CheckResult)
    assert result.violation is None
    # 5/10 == 0.5; ratio surfaces utilization for the aggregator.
    assert result.ratio == pytest.approx(0.5)


def test_candidate_above_limit_is_rejected_not_capped(policy_10pct: RiskPolicy) -> None:
    result = check_position_size(15.0, policy_10pct)

    assert isinstance(result, CheckResult)
    assert isinstance(result.violation, Violation)
    assert result.violation.name == "max_single_position_pct"
    assert result.violation.observed == 15.0
    assert result.violation.limit == 10.0
    # 15/10 == 1.5 -- exceeds 1.0; node clamps to 1.0 in utilization.
    assert result.ratio == pytest.approx(1.5)


def test_candidate_exactly_at_limit_is_inclusive(policy_10pct: RiskPolicy) -> None:
    result = check_position_size(10.0, policy_10pct)

    assert isinstance(result, CheckResult)
    assert result.violation is None
    assert result.ratio == pytest.approx(1.0)


def test_zero_candidate_size_yields_zero_ratio(policy_10pct: RiskPolicy) -> None:
    """Zero-sized candidate consumes no policy budget."""
    result = check_position_size(0.0, policy_10pct)

    assert result.violation is None
    assert result.ratio == 0.0
