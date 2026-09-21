"""Phase 8 review_policy_sha linkage tests.

Six scenarios prove the review_policy_sha audit contract across the state,
the persisted row, and the recomputed policy SHA -- mirror of
tests/integration/test_phase7_policy_sha_linkage.py for the Phase-6 risk
policy_sha, now applied to the Phase-8 review policy.

Scenarios:
    1. Same policy -> same review_policy_sha across runs
    2. Different policy -> different review_policy_sha (drift detection)
    3. Idempotent revert: A, B, A -> runs 1 and 3 identical SHAs
    4. SHA format on APPROVED row (64-char lowercase hex)
    5. SHA format on REJECTED row
    6. Three-way equality: state['review_decision']['review_policy_sha'] ==
       row.payload['review_policy_sha'] == compute_review_policy_sha(policy)

All 12 agents stubbed via TestModel. Zero real LLM calls. Tests resume the
interrupt with APPROVED/REJECTED decisions to drive the review_store_node;
the ``compute_review_policy_sha`` equality chain locks the T-08-02 drift
mitigation + T-08-22 runtime-mutation defense.
"""

from __future__ import annotations

import asyncio
import os
import re
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pandas as pd  # noqa: E402
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
from ai_hedge_fund.db.models import EpisodicMemory  # noqa: E402
from ai_hedge_fund.graph.memory_deps import MemoryDeps  # noqa: E402
from ai_hedge_fund.graph.pipeline import build_debate_pipeline  # noqa: E402
from ai_hedge_fund.graph.review_deps import ReviewDeps  # noqa: E402
from ai_hedge_fund.graph.risk_deps import RiskDeps  # noqa: E402
from ai_hedge_fund.review.policy import ReviewPolicy, compute_review_policy_sha  # noqa: E402
from ai_hedge_fund.risk.policy import RiskPolicy  # noqa: E402

RISK_FIXTURES = Path(__file__).parent.parent / "risk" / "fixtures"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
AS_OF_IN_WINDOW = "2024-06-03"


# ---------------------------------------------------------------------------
# Stubbing helpers (duplicated minimally from test_phase8_e2e.py per the
# Phase-7 Plan-05 precedent -- shared extraction to conftest deferred)
# ---------------------------------------------------------------------------


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


def _debate_synth_stub(confidence: int = 85) -> dict:
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
        "confidence": confidence,
        "risk_factors": ["r1", "r2"],
    }
    return {
        "ticker": "PG",
        "revised_thesis": thesis,
        "pre_debate_confidence": confidence,
        "post_debate_confidence": confidence,
        "evidence_strength": 70,
        "logical_consistency": 70,
        "risk_coverage": 70,
        "quality_score": 70,
        "synthesis_notes": "ok",
    }


def _stubbed_stack(confidence: int = 85) -> ExitStack:
    stack = ExitStack()
    for agent in (fundamental_agent, sentiment_agent, technical_agent):
        stack.enter_context(agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(manager_agent.override(model=TestModel()))
    stack.enter_context(bull_agent.override(model=TestModel()))
    stack.enter_context(bear_agent.override(model=TestModel(custom_output_args=_valid_bear_case())))
    stack.enter_context(rebuttal_agent.override(model=TestModel()))
    stack.enter_context(final_arguments_agent.override(model=TestModel()))
    stack.enter_context(
        debate_synthesis_agent.override(
            model=TestModel(custom_output_args=_debate_synth_stub(confidence))
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


def _build(session: Session, beliefs: Path, review_policy: ReviewPolicy) -> CompiledStateGraph:
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
        review_deps=ReviewDeps(db_session=session, policy=review_policy),
    )


def _decision_for(policy: ReviewPolicy, *, status: str = "APPROVED") -> dict:
    return {
        "status": status,
        "reviewer_id": "t",
        "reviewer_note": "ok",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "review_policy_sha": compute_review_policy_sha(policy),
    }


def _run_with_decision(
    graph: CompiledStateGraph, threshold: int, decision: dict, thread_id: str
) -> dict:
    cfg = {"configurable": {"thread_id": thread_id}}
    asyncio.run(
        graph.ainvoke(
            {
                "ticker": "PG",
                "as_of_date": AS_OF_IN_WINDOW,
                "candidate_metadata": {
                    "sector": "Consumer Staples",
                    "instrument_type": "equity",
                },
                "_review_threshold": threshold,
            },
            config=cfg,
        )
    )
    return asyncio.run(graph.ainvoke(Command(resume=decision), config=cfg))


# =====================================================================
# Test 1 -- same policy => identical review_policy_sha on review rows
# =====================================================================


def test_same_policy_same_review_sha(memory_db_session: Session, beliefs_tmp_dir: Path) -> None:
    policy = ReviewPolicy(conviction_threshold=70, reviewer_id_default="test")
    with _stubbed_stack():
        g1 = _build(memory_db_session, beliefs_tmp_dir, policy)
        _run_with_decision(g1, 70, _decision_for(policy), "sha-same-1")
        g2 = _build(memory_db_session, beliefs_tmp_dir, policy)
        _run_with_decision(g2, 70, _decision_for(policy), "sha-same-2")

    rows = memory_db_session.query(EpisodicMemory).filter_by(record_type="review").all()
    assert len(rows) == 2
    sha = compute_review_policy_sha(policy)
    for row in rows:
        assert row.payload["review_policy_sha"] == sha


# =====================================================================
# Test 2 -- different policies => different review_policy_sha
# =====================================================================


def test_different_policy_different_review_sha(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    p_a = ReviewPolicy(conviction_threshold=70, reviewer_id_default="test")
    p_b = ReviewPolicy(conviction_threshold=71, reviewer_id_default="test")
    assert compute_review_policy_sha(p_a) != compute_review_policy_sha(p_b)

    with _stubbed_stack():
        g_a = _build(memory_db_session, beliefs_tmp_dir, p_a)
        _run_with_decision(g_a, 70, _decision_for(p_a), "sha-diff-a")
        g_b = _build(memory_db_session, beliefs_tmp_dir, p_b)
        _run_with_decision(g_b, 71, _decision_for(p_b), "sha-diff-b")

    rows = (
        memory_db_session.query(EpisodicMemory)
        .filter_by(record_type="review")
        .order_by(EpisodicMemory.id)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].payload["review_policy_sha"] != rows[1].payload["review_policy_sha"]


# =====================================================================
# Test 3 -- idempotence under revert: A, B, A => rows 1 and 3 identical
# =====================================================================


def test_idempotent_revert(memory_db_session: Session, beliefs_tmp_dir: Path) -> None:
    """Run A, B, A -> review rows 1 and 3 share a SHA; row 2 differs."""
    p_a = ReviewPolicy(conviction_threshold=70, reviewer_id_default="test")
    p_b = ReviewPolicy(conviction_threshold=71, reviewer_id_default="test")

    with _stubbed_stack():
        _run_with_decision(
            _build(memory_db_session, beliefs_tmp_dir, p_a),
            70,
            _decision_for(p_a),
            "sha-rev-1",
        )
        _run_with_decision(
            _build(memory_db_session, beliefs_tmp_dir, p_b),
            71,
            _decision_for(p_b),
            "sha-rev-2",
        )
        _run_with_decision(
            _build(memory_db_session, beliefs_tmp_dir, p_a),
            70,
            _decision_for(p_a),
            "sha-rev-3",
        )

    rows = (
        memory_db_session.query(EpisodicMemory)
        .filter_by(record_type="review")
        .order_by(EpisodicMemory.id)
        .all()
    )
    assert len(rows) == 3
    assert rows[0].payload["review_policy_sha"] == rows[2].payload["review_policy_sha"]
    assert rows[1].payload["review_policy_sha"] != rows[0].payload["review_policy_sha"]


# =====================================================================
# Test 4 -- review_policy_sha on APPROVED row is 64-char lowercase hex
# =====================================================================


def test_sha_format_on_approved(memory_db_session: Session, beliefs_tmp_dir: Path) -> None:
    policy = ReviewPolicy(conviction_threshold=70, reviewer_id_default="test")
    with _stubbed_stack():
        _run_with_decision(
            _build(memory_db_session, beliefs_tmp_dir, policy),
            70,
            _decision_for(policy, status="APPROVED"),
            "sha-fmt-a",
        )

    row = memory_db_session.query(EpisodicMemory).filter_by(record_type="review").one()
    sha = row.payload["review_policy_sha"]
    assert SHA_RE.fullmatch(sha)
    # Defense-in-depth: pure lowercase hex
    assert sha == sha.lower()
    assert row.payload["review_status"] == "APPROVED"


# =====================================================================
# Test 5 -- review_policy_sha on REJECTED row is also well-formed
# =====================================================================


def test_sha_format_on_rejected(memory_db_session: Session, beliefs_tmp_dir: Path) -> None:
    policy = ReviewPolicy(conviction_threshold=70, reviewer_id_default="test")
    with _stubbed_stack():
        _run_with_decision(
            _build(memory_db_session, beliefs_tmp_dir, policy),
            70,
            _decision_for(policy, status="REJECTED"),
            "sha-fmt-r",
        )

    row = memory_db_session.query(EpisodicMemory).filter_by(record_type="review").one()
    sha = row.payload["review_policy_sha"]
    assert SHA_RE.fullmatch(sha)
    assert row.payload["review_status"] == "REJECTED"


# =====================================================================
# Test 6 -- three-way equality: state, row.payload, recomputed
# =====================================================================


def test_three_way_sha_equality(memory_db_session: Session, beliefs_tmp_dir: Path) -> None:
    """T-08-02 / T-08-22: state -> row -> recomputed SHAs all agree.

    Any silent rewriting layer between the resume decision, the persistence
    layer, and the policy object would break this equality. Locks the
    cross-phase review audit contract end-to-end.
    """
    policy = ReviewPolicy(conviction_threshold=70, reviewer_id_default="test")
    graph = _build(memory_db_session, beliefs_tmp_dir, policy)
    cfg = {"configurable": {"thread_id": "sha-three-way"}}
    expected_sha = compute_review_policy_sha(policy)
    decision = _decision_for(policy, status="APPROVED")

    with _stubbed_stack():
        asyncio.run(
            graph.ainvoke(
                {
                    "ticker": "PG",
                    "as_of_date": AS_OF_IN_WINDOW,
                    "candidate_metadata": {
                        "sector": "Consumer Staples",
                        "instrument_type": "equity",
                    },
                    "_review_threshold": 70,
                },
                config=cfg,
            )
        )
        final = asyncio.run(graph.ainvoke(Command(resume=decision), config=cfg))

    # Leg 1: state-side (what the pipeline emits)
    assert final["review_decision"]["review_policy_sha"] == expected_sha
    # Leg 2: row-payload side (what actually lands in episodic_memory)
    row = memory_db_session.query(EpisodicMemory).filter_by(record_type="review").one()
    assert row.payload["review_policy_sha"] == expected_sha
    # Leg 3: recomputed from policy (attribution from first principles)
    assert compute_review_policy_sha(policy) == expected_sha
