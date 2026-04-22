"""Shared test fixtures for the Phase 6 risk management test suite.

Fixtures defined here are consumed by plans 06-01 through 06-06:
- ``sample_policy_path`` / ``sample_policy`` -- tighter-than-default RiskPolicy
  that gives integration tests room to both pass and veto against sample data.
- ``sample_portfolio_csv_path`` -- pointer to the sample portfolio CSV file
  authored in plan 06-02. This conftest only exposes the path; the file itself
  is materialised by plan 06-02.
- ``golden_returns_path`` -- pointer to the golden log-returns CSV authored in
  plan 06-03 (used by the drawdown / correlation check tests).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_hedge_fund.risk.policy import RiskPolicy, load_policy

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def sample_policy_path() -> Path:
    """Path to the checked-in sample risk-policy YAML fixture."""
    return FIXTURES_DIR / "risk_policy_sample.yaml"


@pytest.fixture()
def sample_policy(sample_policy_path: Path) -> RiskPolicy:
    """Validated RiskPolicy instance loaded from the sample YAML fixture."""
    return load_policy(sample_policy_path)


@pytest.fixture()
def sample_portfolio_csv_path() -> Path:
    """Path to the sample portfolio CSV fixture (authored in plan 06-02)."""
    return FIXTURES_DIR / "portfolio_sample.csv"


@pytest.fixture()
def golden_returns_path() -> Path:
    """Path to the golden log-returns CSV fixture (authored in plan 06-03)."""
    return FIXTURES_DIR / "returns_golden.csv"
