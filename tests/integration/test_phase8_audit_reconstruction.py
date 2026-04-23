"""Phase 8 audit reconstruction integration tests (SIG-04, Pitfall G).

Four scenarios prove reconstruct_audit_trail can rebuild the full
compliance trail for any finalized analysis after a live pipeline run:

    1. APPROVED run -> trail contains analysis row + review row (APPROVED)
       + Langfuse thread hint.
    2. NOT_REQUIRED (below-threshold) run -> trail contains analysis row +
       review row with status='NOT_REQUIRED' + thread hint.
    3. Both policy_sha fields present: risk policy_sha on analysis row +
       review_policy_sha on review row (T-08-19 repudiation mitigation).
    4. Wrong / missing episodic_id -> ValueError (fail-closed).

All 12 agents stubbed via TestModel. Zero real LLM calls. Pipeline is
wired with_memory + with_risk + with_output + with_review +
InMemorySaver -- the full Phase 5+6+7+8 stack.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.graph.state import CompiledStateGraph  # noqa: E402
from langgraph.types import Command  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ai_hedge_fund.agents.bear import bear_agent  # noqa: E402
from ai_hedge_fund.agents.bull import bull_agent  # noqa: E402
from ai_hedge_fund.agents.debate_synthesis import debate_synthesis_agent  # noqa: E402
from ai_hedge_fund.agents.final_arguments import final_arguments_agent  # noqa: E402
from ai_hedge_fund.agents.fundamental import fundamental_agent  # noqa: E402
from ai_hedge_fund.agents.manager import manager_agent  # noqa: E402
from ai_hedge_fund.agents.rebuttal import rebuttal_agent  # noqa: E402
from ai_hedge_fund.agents.risk_manager import risk_manager_agent  # noqa: E402
from ai_hedge_fund.agents.self_critique import self_critique_agent  # noqa: E402
from ai_hedge_fund.agents.sentiment import sentiment_agent  # noqa: E402
from ai_hedge_fund.agents.signal import signal_agent  # noqa: E402
from ai_hedge_fund.agents.technical import technical_agent  # noqa: E402
from ai_hedge_fund.graph.memory_deps import MemoryDeps  # noqa: E402
from ai_hedge_fund.graph.pipeline import build_debate_pipeline  # noqa: E402
from ai_hedge_fund.graph.review_deps import ReviewDeps  # noqa: E402
from ai_hedge_fund.graph.risk_deps import RiskDeps  # noqa: E402
from ai_hedge_fund.review.policy import ReviewPolicy, compute_review_policy_sha  # noqa: E402
from ai_hedge_fund.risk.policy import RiskPolicy  # noqa: E402
from ai_hedge_fund.scripts.audit_reconstruct import reconstruct_audit_trail  # noqa: E402

RISK_FIXTURES = Path(__file__).parent.parent / "risk" / "fixtures"
AS_OF_IN_WINDOW = "2024-06-03"


def _bear() -> dict:
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


def _synth(conf: int) -> dict:
    thesis = {
        "ticker": "PG",
        "bull_case": [
            {"claim": "c", "evidence": "e", "source_tool": "t"},
            {"claim": "c", "evidence": "e", "source_tool": "t"},
            {"claim": "c", "evidence": "e", "source_tool": "t"},
        ],
        "bear_case": [
            {"claim": "c", "evidence": "e", "source_tool": "t"},
            {"claim": "c", "evidence": "e", "source_tool": "t"},
            {"claim": "c", "evidence": "e", "source_tool": "t"},
        ],
        "confidence": conf,
        "risk_factors": ["r1", "r2"],
    }
    return {
        "ticker": "PG",
        "revised_thesis": thesis,
        "pre_debate_confidence": conf,
        "post_debate_confidence": conf,
        "evidence_strength": 70,
        "logical_consistency": 70,
        "risk_coverage": 70,
        "quality_score": 70,
        "synthesis_notes": "ok",
    }


def _stack(conf: int = 85) -> ExitStack:
    stack = ExitStack()
    for agent in (fundamental_agent, sentiment_agent, technical_agent):
        stack.enter_context(agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(manager_agent.override(model=TestModel()))
    stack.enter_context(bull_agent.override(model=TestModel()))
    stack.enter_context(
        bear_agent.override(model=TestModel(custom_output_args=_bear()))
    )
    stack.enter_context(rebuttal_agent.override(model=TestModel()))
    stack.enter_context(final_arguments_agent.override(model=TestModel()))
    stack.enter_context(
        debate_synthesis_agent.override(
            model=TestModel(custom_output_args=_synth(conf))
        )
    )
    stack.enter_context(
        risk_manager_agent.override(model=TestModel(custom_output_args={"rationale": "r"}))
    )
    stack.enter_context(signal_agent.override(model=TestModel()))
    stack.enter_context(
        self_critique_agent.override(model=TestModel(custom_output_args={"rationale": "r"}))
    )
    return stack


def _golden_returns() -> pd.DataFrame:
    return pd.read_csv(
        RISK_FIXTURES / "returns_golden.csv",
        index_col=0,
        parse_dates=True,
    )


def _wide_open_risk_policy() -> RiskPolicy:
    return RiskPolicy(
        max_single_position_pct=10.0,
        max_sector_pct=50.0,
        max_total_exposure_pct=100.0,
        max_correlation_with_portfolio=0.99,
        correlation_window_days=60,
        max_projected_drawdown_pct=99.0,
        drawdown_window_days=60,
        min_history_days=60,
        excluded_instrument_types=["OTC", "SPAC"],
        excluded_sectors=[],
        size_high_conviction_multiplier=1.0,
        size_medium_conviction_multiplier=0.5,
        size_low_conviction_multiplier=0.25,
    )


def _build(
    session: Session, beliefs: Path, policy: ReviewPolicy
) -> CompiledStateGraph:
    return build_debate_pipeline(
        checkpointer=InMemorySaver(),
        with_memory=True,
        memory_deps=MemoryDeps(db_session=session, beliefs_path=beliefs),
        with_risk=True,
        risk_deps=RiskDeps(
            db_session=session, returns=_golden_returns(), policy=_wide_open_risk_policy()
        ),
        with_output=True,
        with_review=True,
        review_deps=ReviewDeps(db_session=session, policy=policy),
    )


def _decision(policy: ReviewPolicy, status: str = "APPROVED") -> dict:
    return {
        "status": status,
        "reviewer_id": "t",
        "reviewer_note": "ok",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "review_policy_sha": compute_review_policy_sha(policy),
    }


def _initial(threshold: int = 70) -> dict:
    return {
        "ticker": "PG",
        "as_of_date": AS_OF_IN_WINDOW,
        "candidate_metadata": {"sector": "Consumer Staples", "instrument_type": "equity"},
        "_review_threshold": threshold,
    }


# =====================================================================
# Test 1 -- reconstruct after APPROVED run
# =====================================================================


def test_reconstruct_after_approved_run(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """SIG-04: compliance reviewer can rebuild the trail for any finalized signal."""
    policy = ReviewPolicy(conviction_threshold=70, reviewer_id_default="test")
    graph = _build(memory_db_session, beliefs_tmp_dir, policy)
    cfg = {"configurable": {"thread_id": "recon-1"}}

    with _stack(85):
        asyncio.run(graph.ainvoke(_initial(threshold=70), config=cfg))
        final = asyncio.run(
            graph.ainvoke(Command(resume=_decision(policy)), config=cfg)
        )

    episodic_id = final["episodic_stored_id"]
    trail = reconstruct_audit_trail(memory_db_session, episodic_id)

    # Analysis row
    assert trail["analysis_row"]["id"] == episodic_id
    assert trail["analysis_row"]["ticker"] == "PG"
    assert trail["analysis_row"]["record_type"] == "analysis"
    assert trail["analysis_row"]["policy_sha"]

    # Review row
    assert trail["review_row"] is not None
    assert trail["review_row"]["status"] == "APPROVED"
    assert trail["review_row"]["review_policy_sha"] == compute_review_policy_sha(policy)

    # Langfuse hint
    assert "thread_id" in trail["langfuse_trace_hint"]
    assert "PG" in trail["langfuse_trace_hint"]["thread_id"]


# =====================================================================
# Test 2 -- reconstruct after NOT_REQUIRED (below-threshold) run
# =====================================================================


def test_reconstruct_after_not_required_run(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """NOT_REQUIRED runs still produce a full auditable trail (uniform audit)."""
    policy = ReviewPolicy(conviction_threshold=70, reviewer_id_default="test")
    graph = _build(memory_db_session, beliefs_tmp_dir, policy)
    cfg = {"configurable": {"thread_id": "recon-2"}}
    with _stack(50):
        final = asyncio.run(graph.ainvoke(_initial(threshold=70), config=cfg))

    trail = reconstruct_audit_trail(memory_db_session, final["episodic_stored_id"])
    assert trail["review_row"] is not None
    assert trail["review_row"]["status"] == "NOT_REQUIRED"
    assert trail["analysis_row"]["ticker"] == "PG"


# =====================================================================
# Test 3 -- BOTH policy_sha fields present (risk + review)
# =====================================================================


def test_reconstruct_shows_both_policy_shas(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """T-08-19: SIG-04 trail includes BOTH risk policy_sha and review_policy_sha."""
    policy = ReviewPolicy(conviction_threshold=70, reviewer_id_default="test")
    graph = _build(memory_db_session, beliefs_tmp_dir, policy)
    cfg = {"configurable": {"thread_id": "recon-3"}}

    with _stack(85):
        asyncio.run(graph.ainvoke(_initial(threshold=70), config=cfg))
        final = asyncio.run(
            graph.ainvoke(Command(resume=_decision(policy)), config=cfg)
        )

    trail = reconstruct_audit_trail(memory_db_session, final["episodic_stored_id"])
    # Risk policy_sha on the analysis row (Phase 6 -> 7 audit linkage)
    assert trail["analysis_row"]["policy_sha"]
    # Review policy_sha on the review row (Phase 8 audit)
    assert trail["review_row"]["review_policy_sha"] == compute_review_policy_sha(policy)


# =====================================================================
# Test 4 -- wrong / missing id => ValueError
# =====================================================================


def test_reconstruct_raises_on_wrong_id(memory_db_session: Session) -> None:
    """Fail-closed: unknown id raises ValueError (T-08-19 repudiation guard)."""
    with pytest.raises(ValueError, match="No analysis row"):
        reconstruct_audit_trail(memory_db_session, 999999)
