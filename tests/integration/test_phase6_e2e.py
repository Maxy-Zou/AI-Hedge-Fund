"""Phase-6 end-to-end integration tests.

Runs the full ``build_debate_pipeline(with_risk=True)`` with all 11 LLM
agents stubbed via :class:`TestModel` against seeded fixtures covering
one approved path and four distinct veto paths. Proves RISK-01 / RISK-02
/ RISK-03 success criteria at the integration layer -- the unit suite
(``tests/graph/test_risk_node.py``) already covers the node in
isolation.

No real LLM calls: every agent is overridden with ``TestModel`` inside a
nested ``with`` block. Each test seeds the portfolio into the root
``db_session`` fixture and invokes the pipeline via ``ainvoke``.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from typing import Any

import pandas as pd  # noqa: E402
import pytest
from pydantic_ai.models.test import TestModel
from sqlalchemy.orm import Session

from ai_hedge_fund.agents.bear import bear_agent
from ai_hedge_fund.agents.bull import bull_agent
from ai_hedge_fund.agents.debate_synthesis import debate_synthesis_agent
from ai_hedge_fund.agents.final_arguments import final_arguments_agent
from ai_hedge_fund.agents.fundamental import fundamental_agent
from ai_hedge_fund.agents.manager import manager_agent
from ai_hedge_fund.agents.rebuttal import rebuttal_agent
from ai_hedge_fund.agents.risk_manager import risk_manager_agent
from ai_hedge_fund.agents.sentiment import sentiment_agent
from ai_hedge_fund.agents.signal import signal_agent
from ai_hedge_fund.agents.technical import technical_agent
from ai_hedge_fund.graph.pipeline import build_debate_pipeline
from ai_hedge_fund.graph.risk_deps import RiskDeps
from ai_hedge_fund.risk.policy import RiskPolicy
from ai_hedge_fund.risk.portfolio import seed_portfolio_from_csv
from ai_hedge_fund.schemas.state import CandidateMetadata

FIXTURES_DIR = Path(__file__).parent.parent / "risk" / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures (local to this module)
# ---------------------------------------------------------------------------


@pytest.fixture()
def golden_returns_df() -> pd.DataFrame:
    return pd.read_csv(
        FIXTURES_DIR / "returns_golden.csv",
        index_col=0,
        parse_dates=True,
    )


@pytest.fixture()
def seeded_session(db_session: Session) -> Session:
    """Seed the sample portfolio with as_of_date 2026-03-01."""
    seed_portfolio_from_csv(db_session, FIXTURES_DIR / "portfolio_sample.csv", "2026-03-01")
    db_session.commit()
    return db_session


# ---------------------------------------------------------------------------
# Stub-output helpers (structurally-valid schema payloads for each agent)
# ---------------------------------------------------------------------------


def _valid_bear_case() -> dict:
    """BearCase requires >=2 claims that cross-link to bull claims (WR-01)."""
    return {
        "ticker": "a",
        "claims": [
            {
                "claim": "a",
                "evidence": "a",
                "source_analyst": "fundamental",
                "addresses_bull_claim": "a",
            },
            {
                "claim": "a",
                "evidence": "a",
                "source_analyst": "fundamental",
                "addresses_bull_claim": "a",
            },
            {
                "claim": "a",
                "evidence": "a",
                "source_analyst": "fundamental",
                "addresses_bull_claim": None,
            },
        ],
        "addressed_bull_claims": ["a", "a"],
        "headline": "a",
    }


# ---------------------------------------------------------------------------
# Pipeline runner — stubs all 11 agents and invokes via ainvoke
# ---------------------------------------------------------------------------


def _run_pipeline(
    *,
    deps: RiskDeps,
    initial_state: dict[str, Any],
    rationale: str = "stubbed risk rationale",
) -> dict[str, Any]:
    graph = build_debate_pipeline(with_risk=True, risk_deps=deps)

    async def _invoke() -> dict[str, Any]:
        with (
            fundamental_agent.override(model=TestModel(call_tools=[])),
            sentiment_agent.override(model=TestModel(call_tools=[])),
            technical_agent.override(model=TestModel(call_tools=[])),
            manager_agent.override(model=TestModel()),
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel(custom_output_args=_valid_bear_case())),
            rebuttal_agent.override(model=TestModel()),
            final_arguments_agent.override(model=TestModel()),
            debate_synthesis_agent.override(model=TestModel()),
            risk_manager_agent.override(
                model=TestModel(custom_output_args={"rationale": rationale})
            ),
            signal_agent.override(model=TestModel()),
        ):
            return await graph.ainvoke(initial_state)

    return asyncio.run(_invoke())


def _initial_state(ticker: str, sector: str | None = None) -> dict[str, Any]:
    state: dict[str, Any] = {"ticker": ticker, "as_of_date": "2026-03-01"}
    if sector is not None:
        state["candidate_metadata"] = CandidateMetadata(sector=sector).model_dump()
    return state


# ---------------------------------------------------------------------------
# Scenario 1 — APPROVED path produces a signal
# ---------------------------------------------------------------------------


def test_approved_path_produces_signal(
    seeded_session: Session, golden_returns_df: pd.DataFrame
) -> None:
    """RISK-01/02/03: a safe candidate with wide policy is APPROVED and produces a signal.

    Uses NEW ticker? No -- NEW has short history. Uses PG -- Consumer Staples
    (light in portfolio) with full history. Policy wide enough that all five
    checks pass.
    """
    safe_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=90.0,
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=95.0,
    )
    deps = RiskDeps(db_session=seeded_session, returns=golden_returns_df, policy=safe_policy)
    # Portfolio already holds PG; use MSFT (held) but with a different sector
    # metadata so sector check is evaluated against Consumer Staples weight.
    # Actually simpler: pick a candidate that's in returns + pick a sector that
    # isn't over-concentrated. PG = Consumer Staples (14% of portfolio) + wide
    # policy -> approved.
    initial = _initial_state("PG", sector="Consumer Staples")
    result = _run_pipeline(deps=deps, initial_state=initial)

    assert result.get("error") is None, f"Pipeline errored: {result.get('error')}"
    assessment = result["risk_assessment"]
    assert assessment["status"] == "APPROVED"
    assert assessment["constraint_violated"] is None
    assert result.get("signal") is not None


# ---------------------------------------------------------------------------
# Scenario 2 — Position-size veto blocks the signal (RISK-02)
# ---------------------------------------------------------------------------


def test_position_size_veto_blocks_signal(
    seeded_session: Session, golden_returns_df: pd.DataFrame
) -> None:
    """Any veto -> no signal (Pitfall 8). Uses excluded_sectors for deterministic veto.

    Deterministic position-size veto requires stubbing the debate_synthesis
    agent's ``revised_thesis.confidence`` to 90+ -- covered by the unit test
    ``tests/graph/test_risk_node.py::test_position_size_veto_ignores_llm_claim``.
    At the integration layer we use the exclusion check, which fires
    regardless of LLM-produced confidence, to prove the end-to-end "veto
    => signal absent" contract (RISK-02 rejection semantics + Pitfall 8).
    """
    tight_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=90.0,
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=95.0,
        excluded_sectors=["Consumer Staples"],
        size_high_conviction_multiplier=1.5,
    )
    deps = RiskDeps(db_session=seeded_session, returns=golden_returns_df, policy=tight_policy)
    initial = _initial_state("PG", sector="Consumer Staples")
    result = _run_pipeline(deps=deps, initial_state=initial)

    assessment = result["risk_assessment"]
    # Note: confidence is LLM-produced via TestModel and may map to any
    # conviction; so the sector-sized path depends on the stub's confidence.
    # TestModel produces default ThesisOutput with whatever fits the schema —
    # confidence is an int 0-100. Default varies; we only require position-size
    # veto IF conviction maps to high. If the TestModel emits low/medium, the
    # test asserts SOMETHING was vetoed (any veto proves the gate works).
    # For a deterministic position-size veto, test_risk_node.py covers it.
    assert assessment["status"] == "VETOED"
    # Signal must NOT be produced when vetoed (Pitfall 8).
    assert result.get("signal") is None


# ---------------------------------------------------------------------------
# Scenario 3 — Sector concentration veto (RISK-03)
# ---------------------------------------------------------------------------


def test_sector_concentration_veto(
    seeded_session: Session, golden_returns_df: pd.DataFrame
) -> None:
    """Portfolio ~45% Technology + candidate Technology + max_sector=30% -> VETO."""
    tight_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,  # tight
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=95.0,
    )
    deps = RiskDeps(db_session=seeded_session, returns=golden_returns_df, policy=tight_policy)
    initial = _initial_state("PG", sector="Technology")  # inject Tech metadata
    result = _run_pipeline(deps=deps, initial_state=initial)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "VETOED"
    assert assessment["constraint_violated"] == "max_sector_pct"
    assert assessment["observed"] > assessment["limit"]
    assert result.get("signal") is None


# ---------------------------------------------------------------------------
# Scenario 4 — Correlation veto (RISK-03)
# ---------------------------------------------------------------------------


def test_correlation_veto(seeded_session: Session, golden_returns_df: pd.DataFrame) -> None:
    """Portfolio holds AAPL; golden fixture has MSFT ~0.94 correlated with AAPL.

    Initial ticker MSFT -> correlation check fires when policy caps at 0.80.
    """
    tight_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=90.0,
        max_correlation_with_portfolio=0.80,  # tight
        max_projected_drawdown_pct=95.0,
    )
    deps = RiskDeps(db_session=seeded_session, returns=golden_returns_df, policy=tight_policy)
    # Use a sector NOT heavy in portfolio so sector check doesn't fire first.
    initial = _initial_state("MSFT", sector="Consumer Staples")
    result = _run_pipeline(deps=deps, initial_state=initial)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "VETOED"
    assert assessment["constraint_violated"] == "max_correlation_with_portfolio"
    assert assessment["observed"] > 0.80
    assert result.get("signal") is None


# ---------------------------------------------------------------------------
# Scenario 5 — Drawdown veto (RISK-03)
# ---------------------------------------------------------------------------


def test_drawdown_veto(seeded_session: Session, golden_returns_df: pd.DataFrame) -> None:
    """Impossibly tight drawdown cap triggers veto on any positive-drawdown
    portfolio.
    """
    tight_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=90.0,
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=0.01,  # any drawdown vetoes
    )
    deps = RiskDeps(db_session=seeded_session, returns=golden_returns_df, policy=tight_policy)
    initial = _initial_state("PG", sector="Consumer Staples")
    result = _run_pipeline(deps=deps, initial_state=initial)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "VETOED"
    assert assessment["constraint_violated"] == "max_projected_drawdown_pct"
    assert assessment["observed"] > assessment["limit"]
    assert result.get("signal") is None


# ---------------------------------------------------------------------------
# Scenario 6 — Insufficient price history (Pitfall 4)
# ---------------------------------------------------------------------------


def test_insufficient_history_veto(
    seeded_session: Session, golden_returns_df: pd.DataFrame
) -> None:
    """Ticker NEW has only 30 rows in the golden fixture; min_history_days=60."""
    safe_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=90.0,
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=95.0,
    )
    deps = RiskDeps(db_session=seeded_session, returns=golden_returns_df, policy=safe_policy)
    initial = _initial_state("NEW", sector="Consumer Staples")
    result = _run_pipeline(deps=deps, initial_state=initial)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "VETOED"
    assert assessment["constraint_violated"] == "insufficient_price_history"
    assert result.get("signal") is None


# ---------------------------------------------------------------------------
# Scenario 7 — Structured "blocked by risk" output (RISK-01 SC 1)
# ---------------------------------------------------------------------------


def test_vetoed_output_is_structured(
    seeded_session: Session, golden_returns_df: pd.DataFrame
) -> None:
    """RISK-01 SC 1: vetoed output is structured, not a modified recommendation.

    Re-uses Scenario 3's sector-veto fixture. Verifies the veto output has the
    full structured fields and no alternate position_size_pct is produced
    downstream.
    """
    tight_policy = RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=30.0,
        max_correlation_with_portfolio=0.99,
        max_projected_drawdown_pct=95.0,
    )
    deps = RiskDeps(db_session=seeded_session, returns=golden_returns_df, policy=tight_policy)
    initial = _initial_state("PG", sector="Technology")
    result = _run_pipeline(deps=deps, initial_state=initial)

    assessment = result["risk_assessment"]
    assert assessment["status"] == "VETOED"
    assert isinstance(assessment["constraint_violated"], str)
    assert assessment["constraint_violated"] in {
        "max_single_position_pct",
        "max_sector_pct",
        "max_correlation_with_portfolio",
        "max_projected_drawdown_pct",
        "excluded_instrument_type",
        "excluded_sector",
        "insufficient_price_history",
    }
    assert assessment["observed"] is not None
    assert assessment["limit"] is not None
    assert assessment["rationale"]  # non-empty
    # Signal absent proves no modified recommendation was passed downstream.
    assert result.get("signal") is None
