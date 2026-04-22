"""Tests for ``build_debate_pipeline(with_memory=True, memory_deps=...)``.

Verifies four topology variants of the builder:

    (1) with_memory=False, with_risk=False   -> Phase-5 backcompat
    (2) with_memory=True,  with_risk=False   -> memory only
    (3) with_memory=False, with_risk=True    -> Phase-6 unchanged
    (4) with_memory=True,  with_risk=True    -> composed, this plan

Compile-time tests inspect ``graph.get_graph().nodes`` and
``graph.get_graph().edges``; end-to-end tests stub all 11 LLM agents via
:class:`TestModel` and assert episodic_hits / beliefs_consulted /
episodic_stored_id are populated.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from langgraph.graph.state import CompiledStateGraph  # noqa: E402
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
from ai_hedge_fund.agents.sentiment import sentiment_agent  # noqa: E402
from ai_hedge_fund.agents.signal import signal_agent  # noqa: E402
from ai_hedge_fund.agents.technical import technical_agent  # noqa: E402
from ai_hedge_fund.db.models import EpisodicMemory  # noqa: E402
from ai_hedge_fund.graph.memory_deps import MemoryDeps  # noqa: E402
from ai_hedge_fund.graph.pipeline import build_debate_pipeline  # noqa: E402
from ai_hedge_fund.graph.risk_deps import RiskDeps  # noqa: E402
from ai_hedge_fund.memory.episodic import seed_episodic_from_csv  # noqa: E402
from ai_hedge_fund.risk.policy import RiskPolicy  # noqa: E402


# ---------------------------------------------------------------------------
# Structural tests (tests 16-19) -- compile-time inspection only
# ---------------------------------------------------------------------------


def test_builder_no_kwargs_backcompat() -> None:
    """Test 16: the no-kwargs builder still compiles (Phase-5 topology).

    Node list MUST NOT include memory_recall or episodic_store (those
    only appear when with_memory=True).
    """
    graph = build_debate_pipeline()
    assert isinstance(graph, CompiledStateGraph)
    nodes = set(graph.get_graph().nodes)
    assert "memory_recall" not in nodes
    assert "episodic_store" not in nodes
    assert "risk_manager" not in nodes


def test_with_memory_requires_memory_deps() -> None:
    """Test 17: with_memory=True and memory_deps=None -> ValueError."""
    with pytest.raises(ValueError, match="memory_deps"):
        build_debate_pipeline(with_memory=True)


def test_with_memory_nodes_registered(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """Test 18: with_memory=True registers both memory nodes (no risk)."""
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    graph = build_debate_pipeline(with_memory=True, memory_deps=deps)
    nodes = set(graph.get_graph().nodes)
    assert "memory_recall" in nodes
    assert "episodic_store" in nodes
    assert "risk_manager" not in nodes  # memory-only topology


def test_with_memory_and_with_risk_compose(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    seeded_portfolio_session: Session,
    golden_returns_df: pd.DataFrame,
    safe_policy: RiskPolicy,
) -> None:
    """Test 19: combined topology registers memory + risk nodes."""
    # seeded_portfolio_session and memory_db_session both alias the same
    # root db_session fixture in the current test runner, so the
    # portfolio rows and future episodic inserts share one SQLite DB.
    risk_deps = RiskDeps(
        db_session=seeded_portfolio_session,
        returns=golden_returns_df,
        policy=safe_policy,
    )
    memory_deps = MemoryDeps(
        db_session=seeded_portfolio_session, beliefs_path=beliefs_tmp_dir
    )
    graph = build_debate_pipeline(
        with_risk=True,
        risk_deps=risk_deps,
        with_memory=True,
        memory_deps=memory_deps,
    )
    nodes = set(graph.get_graph().nodes)
    assert {"memory_recall", "risk_manager", "episodic_store"}.issubset(nodes)


def test_with_memory_start_fan_out_goes_through_memory_recall(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """Start fans out to memory_recall, which fans to the three analysts."""
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    graph = build_debate_pipeline(with_memory=True, memory_deps=deps)
    edges = {(e.source, e.target) for e in graph.get_graph().edges}

    assert ("__start__", "memory_recall") in edges
    assert ("memory_recall", "fundamental") in edges
    assert ("memory_recall", "sentiment") in edges
    assert ("memory_recall", "technical") in edges
    # Direct START -> analyst edges must NOT exist when memory is active.
    assert ("__start__", "fundamental") not in edges


def test_with_memory_only_signal_feeds_episodic_store(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    """When memory+no-risk: signal -> episodic_store -> END (not signal -> END)."""
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    graph = build_debate_pipeline(with_memory=True, memory_deps=deps)
    edges = {(e.source, e.target) for e in graph.get_graph().edges}

    assert ("signal", "episodic_store") in edges
    assert ("episodic_store", "__end__") in edges
    assert ("signal", "__end__") not in edges


# ---------------------------------------------------------------------------
# Pipeline-runner helper (tests 20-22) -- stubs all 11 agents
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


def _run_pipeline(
    graph: CompiledStateGraph,
    *,
    initial_state: dict[str, Any],
    rationale: str = "stubbed risk rationale",
) -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# End-to-end tests (tests 20-22) -- stub agents + assert memory artefacts
# ---------------------------------------------------------------------------


def test_end_to_end_memory_only_populates_state(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """Test 20: seeded DB + default belief -> episodic_hits non-empty,
    beliefs_consulted non-empty, episodic_stored_id is an int.
    """
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    graph = build_debate_pipeline(with_memory=True, memory_deps=deps)

    initial = {
        "ticker": "AAPL",
        "as_of_date": "2026-04-20",
        "candidate_metadata": {"sector": "Technology", "instrument_type": "equity"},
    }
    result = _run_pipeline(graph, initial_state=initial)

    assert result.get("error") is None, f"Pipeline errored: {result.get('error')}"
    assert result["episodic_hits"], "expected non-empty episodic_hits"
    assert result["beliefs_consulted"], "expected non-empty beliefs_consulted"
    assert isinstance(result["episodic_stored_id"], int)


def test_end_to_end_mem03_human_edit_reaches_state(
    memory_db_session: Session,
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
) -> None:
    """Test 21: MEM-03 end-to-end -- human-edited belief reaches state."""
    # Replace the plain AAPL.yaml with the human-edited variant BEFORE the run.
    shutil.copy2(
        beliefs_tmp_dir / "tickers" / "AAPL_human.yaml",
        beliefs_tmp_dir / "tickers" / "AAPL.yaml",
    )
    seed_episodic_from_csv(memory_db_session, sample_episodic_csv_path)
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    graph = build_debate_pipeline(with_memory=True, memory_deps=deps)

    initial = {
        "ticker": "AAPL",
        "as_of_date": "2026-04-20",
        "candidate_metadata": {"sector": "Technology", "instrument_type": "equity"},
    }
    result = _run_pipeline(graph, initial_state=initial)

    assert result.get("error") is None
    aapl_beliefs = [b for b in result["beliefs_consulted"] if b["ticker"] == "AAPL"]
    assert len(aapl_beliefs) == 1
    assert aapl_beliefs[0]["human_edited"] is True
    assert aapl_beliefs[0]["confidence"] == 20  # human override


def test_end_to_end_policy_sha_links_phase6_to_phase7(
    beliefs_tmp_dir: Path,
    sample_episodic_csv_path: Path,
    seeded_portfolio_session: Session,
    golden_returns_df: pd.DataFrame,
    safe_policy: RiskPolicy,
) -> None:
    """Test 22: with_risk=True + with_memory=True -> the stored episodic row's
    policy_sha equals the policy_sha on state['risk_assessment'] (the Phase 6
    risk_manager_node computes both).
    """
    seed_episodic_from_csv(seeded_portfolio_session, sample_episodic_csv_path)
    risk_deps = RiskDeps(
        db_session=seeded_portfolio_session,
        returns=golden_returns_df,
        policy=safe_policy,
    )
    memory_deps = MemoryDeps(
        db_session=seeded_portfolio_session, beliefs_path=beliefs_tmp_dir
    )
    graph = build_debate_pipeline(
        with_risk=True,
        risk_deps=risk_deps,
        with_memory=True,
        memory_deps=memory_deps,
    )

    # Use PG (Consumer Staples) + safe_policy -> APPROVED path so signal + store fire.
    initial = {
        "ticker": "PG",
        "as_of_date": "2026-03-01",
        "candidate_metadata": {"sector": "Consumer Staples", "instrument_type": "equity"},
    }
    result = _run_pipeline(graph, initial_state=initial)

    assert result.get("error") is None, f"Pipeline errored: {result.get('error')}"
    # Phase-6 produces a policy_sha on the risk_assessment.
    assert result["risk_assessment"]["policy_sha"]
    expected_sha = result["risk_assessment"]["policy_sha"]
    assert isinstance(result["episodic_stored_id"], int)

    row = (
        seeded_portfolio_session.query(EpisodicMemory)
        .filter_by(id=result["episodic_stored_id"])
        .one()
    )
    assert row.policy_sha == expected_sha
    assert row.payload["risk_assessment"]["policy_sha"] == expected_sha
