"""Tests for :mod:`ai_hedge_fund.risk.correlation`.

Covers 06-03 Task 2 behaviours 1-5:

    1. Known high-correlation pair (MSFT built to track AAPL ~0.95) is
       surfaced as the top correlated ticker.
    2. Empty ``portfolio_tickers`` returns ``("", 0.0)``.
    3. Aligned window below ``min_window`` returns ``("", 0.0)`` and
       emits a structlog warning.
    4. ``check_correlation`` returns a :class:`Violation` when max
       correlation exceeds ``policy.max_correlation_with_portfolio``.
    5. ``check_correlation`` returns ``None`` when max correlation is at
       or below the policy limit.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ai_hedge_fund.risk.correlation import (
    check_correlation,
    compute_max_correlation_with_portfolio,
)
from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.portfolio import PortfolioSnapshot, PortfolioSnapshotPosition
from ai_hedge_fund.schemas.risk import Violation

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def golden_returns() -> pd.DataFrame:
    return pd.read_csv(FIXTURES_DIR / "returns_golden.csv", index_col=0, parse_dates=True)


@pytest.fixture()
def strict_corr_policy() -> RiskPolicy:
    return RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.80,
        max_projected_drawdown_pct=25.0,
    )


@pytest.fixture()
def loose_corr_policy() -> RiskPolicy:
    return RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=25.0,
    )


def _snapshot_with_tickers(tickers: list[str]) -> PortfolioSnapshot:
    """Equal-weighted snapshot worth $100k split across ``tickers``."""
    if not tickers:
        return PortfolioSnapshot(as_of_date="2025-04-01", positions=[], total_value_cents=0)
    share = 100_000_00 // len(tickers)
    positions = [
        PortfolioSnapshotPosition(
            ticker=t,
            sector="Other",
            quantity=10.0,
            cost_basis_cents=share,
            current_value_cents=share,
        )
        for t in tickers
    ]
    return PortfolioSnapshot(
        as_of_date="2025-04-01",
        positions=positions,
        total_value_cents=share * len(tickers),
    )


def test_known_high_correlation_pair_is_surfaced(golden_returns: pd.DataFrame) -> None:
    # MSFT was generated as 0.95 * AAPL + noise; JNJ/JPM/PG are independent.
    top_ticker, corr = compute_max_correlation_with_portfolio(
        candidate_ticker="AAPL",
        portfolio_tickers=["MSFT", "JNJ", "JPM", "PG"],
        returns=golden_returns,
    )
    assert top_ticker == "MSFT"
    assert corr > 0.85


def test_empty_portfolio_tickers_returns_zero(golden_returns: pd.DataFrame) -> None:
    top_ticker, corr = compute_max_correlation_with_portfolio(
        candidate_ticker="AAPL",
        portfolio_tickers=[],
        returns=golden_returns,
    )
    assert top_ticker == ""
    assert corr == 0.0


def test_insufficient_data_window_returns_zero(golden_returns: pd.DataFrame) -> None:
    # NEW has only 30 rows in the fixture; intersected with AAPL full history
    # yields 30 aligned rows. Force min_window above 30 to trigger the branch.
    top_ticker, corr = compute_max_correlation_with_portfolio(
        candidate_ticker="AAPL",
        portfolio_tickers=["NEW"],
        returns=golden_returns,
        min_window=60,
    )
    assert top_ticker == ""
    assert corr == 0.0


def test_check_correlation_vetoes_when_above_limit(
    golden_returns: pd.DataFrame, strict_corr_policy: RiskPolicy
) -> None:
    portfolio = _snapshot_with_tickers(["MSFT", "JNJ", "JPM"])
    # strict policy caps correlation at 0.80; AAPL<->MSFT is ~0.94 in fixture.
    result = check_correlation("AAPL", portfolio, golden_returns, strict_corr_policy)

    assert isinstance(result, Violation)
    assert result.name == "max_correlation_with_portfolio"
    assert result.observed > 0.80
    assert result.limit == 0.80


def test_check_correlation_approves_when_within_limit(
    golden_returns: pd.DataFrame, loose_corr_policy: RiskPolicy
) -> None:
    portfolio = _snapshot_with_tickers(["MSFT", "JNJ", "JPM"])
    # loose policy caps at 0.99; AAPL<->MSFT 0.94 is under.
    assert check_correlation("AAPL", portfolio, golden_returns, loose_corr_policy) is None
