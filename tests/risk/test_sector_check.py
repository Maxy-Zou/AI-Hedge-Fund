"""Tests for :func:`check_sector_concentration` and :func:`check_exclusions`.

Covers 06-03 Task 1 behaviours 4-9:

Sector concentration (pre-trade convention / Pitfall 6):
    4. Portfolio 20% Technology, candidate +7% Technology, max 30% -> None.
    5. Portfolio 25% Technology, candidate +7% Technology, max 30% -> Violation (32 > 30).
    6. Empty portfolio, candidate 10% Healthcare, max 30% -> None.

Exclusions:
    7. ``excluded_instrument_types`` containing the candidate type -> Violation.
    8. ``excluded_sectors`` containing the candidate sector -> Violation.
    9. Neither excluded -> None.
"""

from __future__ import annotations

import pytest

from ai_hedge_fund.risk.checks import check_exclusions, check_sector_concentration
from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.portfolio import PortfolioSnapshot, PortfolioSnapshotPosition
from ai_hedge_fund.schemas.risk import Violation


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
    assert (
        check_sector_concentration("Technology", 7.0, portfolio, policy_sector_30pct) is None
    )


def test_sector_over_cap_is_rejected_pre_trade(policy_sector_30pct: RiskPolicy) -> None:
    portfolio = _snapshot_with_tech_weight(25.0)

    result = check_sector_concentration("Technology", 7.0, portfolio, policy_sector_30pct)

    assert isinstance(result, Violation)
    assert result.name == "max_sector_pct"
    assert result.observed == pytest.approx(32.0)
    assert result.limit == 30.0


def test_empty_portfolio_new_sector_is_approved(policy_sector_30pct: RiskPolicy) -> None:
    empty = PortfolioSnapshot(as_of_date="2025-04-01", positions=[], total_value_cents=0)
    assert check_sector_concentration("Healthcare", 10.0, empty, policy_sector_30pct) is None


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

    assert isinstance(result, Violation)
    assert result.name == "excluded_instrument_type"
    assert result.observed == 1.0
    assert result.limit == 0.0


def test_excluded_sector_rejected(policy_with_spac_excluded: RiskPolicy) -> None:
    result = check_exclusions("Energy", "equity", policy_with_spac_excluded)

    assert isinstance(result, Violation)
    assert result.name == "excluded_sector"


def test_non_excluded_candidate_is_approved(policy_with_spac_excluded: RiskPolicy) -> None:
    assert check_exclusions("Technology", "equity", policy_with_spac_excluded) is None
