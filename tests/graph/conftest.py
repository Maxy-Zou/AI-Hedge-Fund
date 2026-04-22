"""Shared fixtures for the Phase-6 graph test suite.

Provides three primary fixtures consumed by ``test_risk_node.py``,
``test_pipeline_with_risk.py``, and ``test_pipeline_no_risk_backcompat.py``:

    ``golden_returns_df`` -- loads ``tests/risk/fixtures/returns_golden.csv``
    into a wide pandas DataFrame (one column per ticker).

    ``seeded_portfolio_session`` -- depends on the root ``db_session``
    fixture in ``tests/conftest.py`` and seeds the sample portfolio CSV
    with ``as_of_date = "2026-03-01"``. Tests that need a pre-populated
    portfolio depend on this fixture; tests that need an empty portfolio
    use the raw ``db_session`` fixture.

    ``safe_policy`` -- a :class:`RiskPolicy` with defaults wide enough that
    the sample portfolio + a single low-conviction trade does not trigger
    any veto. Narrow policies are constructed in-test.

    ``risk_deps`` -- a :class:`RiskDeps` bundling the seeded session, the
    golden returns DataFrame, and ``safe_policy``.

Phase 7 adds re-exports of the memory fixtures so graph-level tests
(``test_memory_nodes.py``, ``test_pipeline_with_memory.py``) can consume
the same ``memory_db_session`` / ``beliefs_tmp_dir`` / seeded paths that
the memory unit tests do, without duplicating the fixture work.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.graph.risk_deps import RiskDeps
from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.portfolio import seed_portfolio_from_csv

# Phase-7 memory fixtures — re-exported so tests/graph/* can consume them
# without duplicating fixture code.  The noqa: F401 suppresses the unused
# import warning while the name is still picked up by pytest's fixture
# discovery.
from tests.memory.conftest import (  # noqa: F401 -- re-export
    beliefs_tmp_dir,
    memory_db_session,
    sample_belief_field_locked_path,
    sample_belief_human_edited_path,
    sample_belief_yaml_path,
    sample_episodic_csv_path,
    sample_outcomes_yaml_path,
)

RISK_FIXTURES_DIR = Path(__file__).parent.parent / "risk" / "fixtures"


@pytest.fixture()
def golden_returns_df() -> pd.DataFrame:
    """Wide daily-log-returns DataFrame produced by plan 06-03."""
    return pd.read_csv(
        RISK_FIXTURES_DIR / "returns_golden.csv",
        index_col=0,
        parse_dates=True,
    )


@pytest.fixture()
def seeded_portfolio_session(db_session: Session) -> Session:
    """Root ``db_session`` seeded with the sample portfolio as of 2026-03-01."""
    seed_portfolio_from_csv(
        db_session,
        RISK_FIXTURES_DIR / "portfolio_sample.csv",
        "2026-03-01",
    )
    db_session.commit()
    return db_session


@pytest.fixture()
def safe_policy() -> RiskPolicy:
    """Wide policy: low-conviction trade on MSFT sized 2.5% cannot veto."""
    return RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=90.0,
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=90.0,
    )


@pytest.fixture()
def risk_deps(
    seeded_portfolio_session: Session,
    golden_returns_df: pd.DataFrame,
    safe_policy: RiskPolicy,
) -> RiskDeps:
    return RiskDeps(
        db_session=seeded_portfolio_session,
        returns=golden_returns_df,
        policy=safe_policy,
    )
