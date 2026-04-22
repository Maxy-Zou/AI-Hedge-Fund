"""Phase-6 ``policy_sha`` audit trail integration tests.

Six scenarios prove the SHA-256 policy fingerprint (``T-06-04`` audit
mitigation) is deterministic, stable across same-policy runs, different
for different policies, sensitive to single-field changes, well-formed
on both APPROVED and VETOED paths, and idempotent under reverts.

Mirrors the stubbing pattern from :mod:`tests.integration.test_phase6_e2e`.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from typing import Any

import pandas as pd
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


# ---------- Fixtures ----------


@pytest.fixture()
def golden_returns_df() -> pd.DataFrame:
    return pd.read_csv(
        FIXTURES_DIR / "returns_golden.csv",
        index_col=0,
        parse_dates=True,
    )


@pytest.fixture()
def seeded_session(db_session: Session) -> Session:
    seed_portfolio_from_csv(db_session, FIXTURES_DIR / "portfolio_sample.csv", "2026-03-01")
    db_session.commit()
    return db_session


def _valid_bear_case() -> dict:
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


def _run_pipeline(*, deps: RiskDeps, initial_state: dict[str, Any]) -> dict[str, Any]:
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
            risk_manager_agent.override(model=TestModel(custom_output_args={"rationale": "r"})),
            signal_agent.override(model=TestModel()),
        ):
            return await graph.ainvoke(initial_state)

    return asyncio.run(_invoke())


SAFE_POLICY_KWARGS: dict[str, float | list[str]] = dict(
    max_single_position_pct=10.0,
    max_sector_pct=90.0,
    max_correlation_with_portfolio=0.99,
    max_projected_drawdown_pct=95.0,
)


def _safe_policy(**overrides: Any) -> RiskPolicy:
    kwargs: dict[str, Any] = {**SAFE_POLICY_KWARGS, **overrides}
    return RiskPolicy(**kwargs)


def _initial_state(ticker: str = "PG", sector: str = "Consumer Staples") -> dict[str, Any]:
    return {
        "ticker": ticker,
        "as_of_date": "2026-03-01",
        "candidate_metadata": CandidateMetadata(sector=sector).model_dump(),
    }


def _run_and_get_sha(policy: RiskPolicy, session: Session, returns: pd.DataFrame) -> str:
    deps = RiskDeps(db_session=session, returns=returns, policy=policy)
    result = _run_pipeline(deps=deps, initial_state=_initial_state())
    assessment = result["risk_assessment"]
    return assessment["policy_sha"]


# ---------- Test 1 — same policy => same sha across runs ----------


def test_same_policy_yields_identical_sha(
    seeded_session: Session, golden_returns_df: pd.DataFrame
) -> None:
    policy = _safe_policy()
    sha_a = _run_and_get_sha(policy, seeded_session, golden_returns_df)
    sha_b = _run_and_get_sha(policy, seeded_session, golden_returns_df)
    assert sha_a == sha_b


# ---------- Test 2 — different policies => different sha ----------


def test_different_policies_yield_different_sha(
    seeded_session: Session, golden_returns_df: pd.DataFrame
) -> None:
    sha_a = _run_and_get_sha(_safe_policy(), seeded_session, golden_returns_df)
    sha_b = _run_and_get_sha(
        _safe_policy(max_single_position_pct=5.0), seeded_session, golden_returns_df
    )
    assert sha_a != sha_b


# ---------- Test 3 — single-field mutation flips the sha ----------


def test_single_field_change_flips_sha(
    seeded_session: Session, golden_returns_df: pd.DataFrame
) -> None:
    sha_a = _run_and_get_sha(
        _safe_policy(max_single_position_pct=10.0), seeded_session, golden_returns_df
    )
    sha_b = _run_and_get_sha(
        _safe_policy(max_single_position_pct=10.1), seeded_session, golden_returns_df
    )
    assert sha_a != sha_b


# ---------- Test 4 — policy_sha is 64 lowercase hex chars on APPROVED ----------


def test_policy_sha_format_on_approved(
    seeded_session: Session, golden_returns_df: pd.DataFrame
) -> None:
    policy = _safe_policy()
    deps = RiskDeps(db_session=seeded_session, returns=golden_returns_df, policy=policy)
    result = _run_pipeline(deps=deps, initial_state=_initial_state())
    assessment = result["risk_assessment"]
    assert assessment["status"] == "APPROVED"
    assert re.fullmatch(r"[0-9a-f]{64}", assessment["policy_sha"])


# ---------- Test 5 — policy_sha is 64 lowercase hex chars on VETOED ----------


def test_policy_sha_format_on_vetoed(
    seeded_session: Session, golden_returns_df: pd.DataFrame
) -> None:
    """Exclusion-based veto to stay deterministic under TestModel stubs."""
    policy = _safe_policy(excluded_sectors=["Consumer Staples"])
    deps = RiskDeps(db_session=seeded_session, returns=golden_returns_df, policy=policy)
    result = _run_pipeline(deps=deps, initial_state=_initial_state())
    assessment = result["risk_assessment"]
    assert assessment["status"] == "VETOED"
    assert re.fullmatch(r"[0-9a-f]{64}", assessment["policy_sha"])


# ---------- Test 6 — field change + revert is idempotent ----------


def test_field_change_and_revert_is_idempotent(
    seeded_session: Session, golden_returns_df: pd.DataFrame
) -> None:
    original = _safe_policy()
    mutated = _safe_policy(max_single_position_pct=5.0)
    reverted = _safe_policy()

    sha_original = _run_and_get_sha(original, seeded_session, golden_returns_df)
    sha_mutated = _run_and_get_sha(mutated, seeded_session, golden_returns_df)
    sha_reverted = _run_and_get_sha(reverted, seeded_session, golden_returns_df)

    assert sha_original != sha_mutated
    assert sha_original == sha_reverted
