"""Tests for :func:`check_sector_concentration` and :func:`check_exclusions`.

Covers 06-03 Task 1 behaviours 4-9 plus the post-fix utilization contract:

Sector concentration (pre-trade convention / Pitfall 6):
    4. Portfolio 20% Technology, candidate +7% Technology, max 30% -> None
       (ratio = 27/30).
    5. Portfolio 25% Technology, candidate +7% Technology, max 30% ->
       Violation (32 > 30) with ratio = 32/30.
    6. Empty portfolio, candidate 10% Healthcare, max 30% -> None
       (ratio = 10/30).

Exclusions:
    7. ``excluded_instrument_types`` containing the candidate type ->
       Violation, ratio = 1.0.
    8. ``excluded_sectors`` containing the candidate sector -> Violation,
       ratio = 1.0.
    9. Neither excluded -> None, ratio = 0.0.
"""

from __future__ import annotations

import pytest

from ai_hedge_fund.risk.checks import check_exclusions, check_sector_concentration
from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.portfolio import PortfolioSnapshot, PortfolioSnapshotPosition
from ai_hedge_fund.schemas.risk import CheckResult, Violation


@pytest.fixture()
def policy_sector_30pct() -> RiskPolicy:
    return RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.80,
        max_projected_drawdown_pct=25.0,
    )


def _snapshot_with_tech_weight(tech_pct: float) -> PortfolioSnapshot:
    """Portfolio worth $100k where ``tech_pct`` percent is Technology."""
    tech_cents = int(100_000_00 * tech_pct / 100)
    other_cents = 100_000_00 - tech_cents
    positions: list[PortfolioSnapshotPosition] = []
    if tech_cents > 0:
        positions.append(
            PortfolioSnapshotPosition(
                ticker="AAPL",
                sector="Technology",
                quantity=10.0,
                cost_basis_cents=tech_cents,
                current_value_cents=tech_cents,
            )
        )
    if other_cents > 0:
        positions.append(
            PortfolioSnapshotPosition(
                ticker="JNJ",
                sector="Healthcare",
                quantity=10.0,
                cost_basis_cents=other_cents,
                current_value_cents=other_cents,
            )
        )
    return PortfolioSnapshot(
        as_of_date="2025-04-01",
        positions=positions,
        total_value_cents=100_000_00,
    )


def test_sector_within_cap_is_approved(policy_sector_30pct: RiskPolicy) -> None:
    portfolio = _snapshot_with_tech_weight(20.0)
    result = check_sector_concentration("Technology", 7.0, portfolio, policy_sector_30pct)

    assert isinstance(result, CheckResult)
    assert result.violation is None
    # post-trade weight 27% / cap 30% = 0.9.
    assert result.ratio == pytest.approx(27.0 / 30.0)


def test_sector_over_cap_is_rejected_pre_trade(policy_sector_30pct: RiskPolicy) -> None:
    portfolio = _snapshot_with_tech_weight(25.0)

    result = check_sector_concentration("Technology", 7.0, portfolio, policy_sector_30pct)

    assert isinstance(result, CheckResult)
    assert isinstance(result.violation, Violation)
    assert result.violation.name == "max_sector_pct"
    assert result.violation.observed == pytest.approx(32.0)
    assert result.violation.limit == 30.0
    # ratio surfaces beyond 1.0 so the aggregator clamps; verifies math.
    assert result.ratio == pytest.approx(32.0 / 30.0)


def test_empty_portfolio_new_sector_is_approved(policy_sector_30pct: RiskPolicy) -> None:
    empty = PortfolioSnapshot(as_of_date="2025-04-01", positions=[], total_value_cents=0)
    result = check_sector_concentration("Healthcare", 10.0, empty, policy_sector_30pct)

    assert isinstance(result, CheckResult)
    assert result.violation is None
    assert result.ratio == pytest.approx(10.0 / 30.0)


# ---------- Exclusion tests ----------


@pytest.fixture()
def policy_with_spac_excluded() -> RiskPolicy:
    return RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.80,
        max_projected_drawdown_pct=25.0,
        excluded_instrument_types=["SPAC"],
        excluded_sectors=["Energy"],
    )


def test_excluded_instrument_type_rejected(policy_with_spac_excluded: RiskPolicy) -> None:
    result = check_exclusions("Technology", "SPAC", policy_with_spac_excluded)

    assert isinstance(result, CheckResult)
    assert isinstance(result.violation, Violation)
    assert result.violation.name == "excluded_instrument_type"
    assert result.violation.observed == 1.0
    assert result.violation.limit == 0.0
    # Hard-veto: ratio saturates so the aggregator clamps to 1.0.
    assert result.ratio == 1.0


def test_excluded_sector_rejected(policy_with_spac_excluded: RiskPolicy) -> None:
    result = check_exclusions("Energy", "equity", policy_with_spac_excluded)

    assert isinstance(result, CheckResult)
    assert isinstance(result.violation, Violation)
    assert result.violation.name == "excluded_sector"
    assert result.ratio == 1.0


def test_non_excluded_candidate_is_approved(policy_with_spac_excluded: RiskPolicy) -> None:
    result = check_exclusions("Technology", "equity", policy_with_spac_excluded)

    assert isinstance(result, CheckResult)
    assert result.violation is None
    # Clean miss should not inflate utilization for the aggregator.
    assert result.ratio == 0.0
