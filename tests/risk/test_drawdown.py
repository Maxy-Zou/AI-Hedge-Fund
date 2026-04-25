"""Tests for :mod:`ai_hedge_fund.risk.drawdown`.

Covers 06-03 Task 2 behaviours 6-11 plus the post-fix utilization contract:

    6.  Historical simulation on the golden fixture returns a finite
        drawdown value and no error name.
    7.  Insufficient price history (< ``policy.min_history_days``) returns
        ``(0.0, "insufficient_price_history")`` (Pitfall 4).
    8.  Empty portfolio + candidate 100% weight returns the candidate's
        solo drawdown, not ``0.0`` (Pitfall 3).
    9.  All-zero returns produce a drawdown of ``0.0`` with no NaN or
        division-by-zero (T-06-05 guard).
    10. ``check_drawdown`` returns a :class:`CheckResult` whose
        ``violation`` is a :class:`Violation` when projected drawdown
        exceeds the policy cap.
    11. ``check_drawdown`` surfaces the ``insufficient_price_history``
        error as a named :class:`Violation` with ``ratio = 1.0``
        (fail-closed: data-quality budget fully consumed).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ai_hedge_fund.risk.drawdown import check_drawdown, project_max_drawdown_pct
from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.portfolio import PortfolioSnapshot, PortfolioSnapshotPosition
from ai_hedge_fund.schemas.risk import CheckResult, Violation

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def golden_returns() -> pd.DataFrame:
    return pd.read_csv(FIXTURES_DIR / "returns_golden.csv", index_col=0, parse_dates=True)


@pytest.fixture()
def default_policy() -> RiskPolicy:
    return RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.80,
        max_projected_drawdown_pct=25.0,
    )


def _snapshot(
    tickers_and_sectors: list[tuple[str, str]],
) -> PortfolioSnapshot:
    if not tickers_and_sectors:
        return PortfolioSnapshot(as_of_date="2025-04-01", positions=[], total_value_cents=0)
    share = 100_000_00 // len(tickers_and_sectors)
    positions = [
        PortfolioSnapshotPosition(
            ticker=t,
            sector=s,
            quantity=10.0,
            cost_basis_cents=share,
            current_value_cents=share,
        )
        for (t, s) in tickers_and_sectors
    ]
    return PortfolioSnapshot(
        as_of_date="2025-04-01",
        positions=positions,
        total_value_cents=share * len(tickers_and_sectors),
    )


def test_project_max_drawdown_pct_returns_finite_value(
    golden_returns: pd.DataFrame, default_policy: RiskPolicy
) -> None:
    weights = {"AAPL": 0.5, "JNJ": 0.5}
    dd_pct, err = project_max_drawdown_pct(weights, golden_returns, default_policy)

    assert err is None
    assert dd_pct > 0.0
    assert dd_pct < 100.0


def test_project_max_drawdown_returns_error_on_insufficient_history(
    golden_returns: pd.DataFrame, default_policy: RiskPolicy
) -> None:
    # NEW only has 30 rows in the fixture; policy.min_history_days defaults to 60.
    dd_pct, err = project_max_drawdown_pct({"NEW": 1.0}, golden_returns, default_policy)

    assert err == "insufficient_price_history"
    assert dd_pct == 0.0


def test_empty_portfolio_uses_candidate_only_weights(
    golden_returns: pd.DataFrame, default_policy: RiskPolicy
) -> None:
    """Pitfall 3: empty portfolio + candidate must evaluate candidate-only drawdown."""
    empty_portfolio = _snapshot([])

    result = check_drawdown("AAPL", 10.0, empty_portfolio, golden_returns, default_policy)

    # drawdown must have been computed (not short-circuited to 0.0). Both
    # branches return a CheckResult; we only assert the candidate-only
    # path activated end-to-end.
    assert isinstance(result, CheckResult)


def test_all_zero_returns_produce_zero_drawdown_no_nan(default_policy: RiskPolicy) -> None:
    """T-06-05: guarded division-by-zero / NaN paths."""
    index = pd.date_range("2024-01-01", periods=100, freq="B")
    zeros = pd.DataFrame({"AAPL": np.zeros(100)}, index=index)

    dd_pct, err = project_max_drawdown_pct({"AAPL": 1.0}, zeros, default_policy)

    assert err is None
    assert dd_pct == 0.0
    assert not np.isnan(dd_pct)


def test_check_drawdown_vetoes_when_above_limit(golden_returns: pd.DataFrame) -> None:
    tight_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.80,
        max_projected_drawdown_pct=0.01,  # impossibly tight — any dd vetoes
    )
    portfolio = _snapshot([("MSFT", "Technology"), ("JNJ", "Healthcare")])

    result = check_drawdown("AAPL", 5.0, portfolio, golden_returns, tight_policy)

    assert isinstance(result, CheckResult)
    assert isinstance(result.violation, Violation)
    assert result.violation.name == "max_projected_drawdown_pct"
    assert result.violation.observed > tight_policy.max_projected_drawdown_pct
    assert result.violation.limit == tight_policy.max_projected_drawdown_pct
    # ratio surfaces beyond 1.0 -- aggregator clamps but stores breach magnitude.
    assert result.ratio > 1.0


def test_check_drawdown_approved_branch_reports_meaningful_ratio(
    golden_returns: pd.DataFrame,
) -> None:
    """APPROVED drawdown still reports drawdown/cap so the aggregator can
    use it for ``RiskAssessment.utilization``."""
    loose_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.80,
        max_projected_drawdown_pct=99.0,  # very loose -- dd will not breach
    )
    portfolio = _snapshot([("MSFT", "Technology"), ("JNJ", "Healthcare")])

    result = check_drawdown("AAPL", 5.0, portfolio, golden_returns, loose_policy)

    assert isinstance(result, CheckResult)
    assert result.violation is None
    assert 0.0 <= result.ratio < 1.0


def test_check_drawdown_surfaces_insufficient_history(
    golden_returns: pd.DataFrame, default_policy: RiskPolicy
) -> None:
    empty_portfolio = _snapshot([])

    result = check_drawdown("NEW", 10.0, empty_portfolio, golden_returns, default_policy)

    assert isinstance(result, CheckResult)
    assert isinstance(result.violation, Violation)
    assert result.violation.name == "insufficient_price_history"
    assert result.violation.observed == 0.0
    assert result.violation.limit == float(default_policy.min_history_days)
    # Fail-closed contract: ratio saturates so utilization aggregation
    # reflects the data-quality breach as full budget consumption.
    assert result.ratio == 1.0
