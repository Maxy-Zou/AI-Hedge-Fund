"""Plan 08-03 Task 2: build_debate_pipeline with_output + with_review tests.

Covers:
    Tests 1-5:  ValueError guards (4 new + Phase-7 topology preservation).
    Tests 6-8:  Backcompat -- prior 4 kwarg combos byte-for-byte unchanged.
    Tests 9-13: Phase-8 topology -- node registration + new edges.

Threat mitigations:
    T-08-21 (with_review without checkpointer silently drops interrupt):
        explicit ValueError guard tested in
        :func:`test_with_review_requires_checkpointer`.
    T-08-23 (with_output without with_memory -- no episodic_id for
        thesis_link): explicit ValueError guard tested in
        :func:`test_with_output_requires_with_memory`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from ai_hedge_fund.graph.memory_deps import MemoryDeps
from ai_hedge_fund.graph.pipeline import build_debate_pipeline
from ai_hedge_fund.graph.review_deps import ReviewDeps
from ai_hedge_fund.graph.risk_deps import RiskDeps
from ai_hedge_fund.review.policy import ReviewPolicy
from ai_hedge_fund.risk.policy import load_policy

RISK_POLICY_PATH = Path("config/risk_policy.yaml")


# ============================================================
# ValueError guards (Tests 1-5)
# ============================================================


def test_with_review_requires_checkpointer(
    portfolio_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    mdeps = MemoryDeps(db_session=portfolio_db_session, beliefs_path=beliefs_tmp_dir)
    rdeps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    with pytest.raises(ValueError, match="checkpointer"):
        build_debate_pipeline(
            with_memory=True,
            memory_deps=mdeps,
            with_output=True,
            with_review=True,
            review_deps=rdeps,
        )


def test_with_output_requires_with_memory(portfolio_db_session: Session) -> None:
    rdeps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    with pytest.raises(ValueError, match="with_memory"):
        build_debate_pipeline(with_output=True, review_deps=rdeps)


def test_with_output_requires_review_deps(
    portfolio_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    mdeps = MemoryDeps(db_session=portfolio_db_session, beliefs_path=beliefs_tmp_dir)
    with pytest.raises(ValueError, match="review_deps"):
        build_debate_pipeline(with_memory=True, memory_deps=mdeps, with_output=True)


def test_with_review_requires_with_output(
    portfolio_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    mdeps = MemoryDeps(db_session=portfolio_db_session, beliefs_path=beliefs_tmp_dir)
    rdeps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    with pytest.raises(ValueError, match="with_output"):
        build_debate_pipeline(
            checkpointer=InMemorySaver(),
            with_memory=True,
            memory_deps=mdeps,
            with_review=True,
            review_deps=rdeps,
        )


def test_no_phase8_flags_phase7_topology_unchanged(
    portfolio_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    mdeps = MemoryDeps(db_session=portfolio_db_session, beliefs_path=beliefs_tmp_dir)
    rdeps = RiskDeps(
        db_session=portfolio_db_session,
        returns=__import__("pandas").DataFrame(),
        policy=load_policy(RISK_POLICY_PATH),
    )

    graph = build_debate_pipeline(
        with_memory=True,
        memory_deps=mdeps,
        with_risk=True,
        risk_deps=rdeps,
    )
    nodes = set(graph.get_graph().nodes)
    for phase8_node in ("output", "human_review", "review_store"):
        assert phase8_node not in nodes


# ============================================================
# Backcompat topology (Tests 6-8)
# ============================================================


def test_no_kwargs_phase5_topology_unchanged() -> None:
    graph = build_debate_pipeline()
    assert isinstance(graph, CompiledStateGraph)
    nodes = set(graph.get_graph().nodes)
    for phase8 in ("output", "human_review", "review_store"):
        assert phase8 not in nodes
    for phase7 in ("memory_recall", "episodic_store"):
        assert phase7 not in nodes


def test_with_memory_only_no_phase8_nodes(
    portfolio_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    mdeps = MemoryDeps(db_session=portfolio_db_session, beliefs_path=beliefs_tmp_dir)
    graph = build_debate_pipeline(with_memory=True, memory_deps=mdeps)
    nodes = set(graph.get_graph().nodes)
    assert "memory_recall" in nodes and "episodic_store" in nodes
    for phase8 in ("output", "human_review", "review_store"):
        assert phase8 not in nodes


def test_with_memory_and_risk_no_phase8(
    portfolio_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    mdeps = MemoryDeps(db_session=portfolio_db_session, beliefs_path=beliefs_tmp_dir)
    rdeps = RiskDeps(
        db_session=portfolio_db_session,
        returns=__import__("pandas").DataFrame(),
        policy=load_policy(RISK_POLICY_PATH),
    )
    graph = build_debate_pipeline(
        with_memory=True,
        memory_deps=mdeps,
        with_risk=True,
        risk_deps=rdeps,
    )
    nodes = set(graph.get_graph().nodes)
    assert "risk_manager" in nodes
    for phase8 in ("output", "human_review", "review_store"):
        assert phase8 not in nodes


# ============================================================
# Phase-8 topology (Tests 9-13)
# ============================================================


def test_with_output_no_review_registers_output_and_review_store(
    portfolio_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    mdeps = MemoryDeps(db_session=portfolio_db_session, beliefs_path=beliefs_tmp_dir)
    rdeps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    graph = build_debate_pipeline(
        with_memory=True,
        memory_deps=mdeps,
        with_output=True,
        review_deps=rdeps,
    )
    nodes = set(graph.get_graph().nodes)
    assert "output" in nodes and "review_store" in nodes
    assert "human_review" not in nodes  # not wired without with_review


def test_with_review_registers_all_three_phase8_nodes(
    portfolio_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    mdeps = MemoryDeps(db_session=portfolio_db_session, beliefs_path=beliefs_tmp_dir)
    rdeps_risk = RiskDeps(
        db_session=portfolio_db_session,
        returns=__import__("pandas").DataFrame(),
        policy=load_policy(RISK_POLICY_PATH),
    )
    rdeps_rev = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    graph = build_debate_pipeline(
        checkpointer=InMemorySaver(),
        with_memory=True,
        memory_deps=mdeps,
        with_risk=True,
        risk_deps=rdeps_risk,
        with_output=True,
        with_review=True,
        review_deps=rdeps_rev,
    )
    nodes = set(graph.get_graph().nodes)
    for phase8 in ("output", "human_review", "review_store"):
        assert phase8 in nodes


def test_edge_from_episodic_store_to_output(
    portfolio_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    mdeps = MemoryDeps(db_session=portfolio_db_session, beliefs_path=beliefs_tmp_dir)
    rdeps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    graph = build_debate_pipeline(
        with_memory=True,
        memory_deps=mdeps,
        with_output=True,
        review_deps=rdeps,
    )
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert ("episodic_store", "output") in edges


def test_conditional_edges_from_output_when_review_enabled(
    portfolio_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    mdeps = MemoryDeps(db_session=portfolio_db_session, beliefs_path=beliefs_tmp_dir)
    rdeps_rev = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    graph = build_debate_pipeline(
        checkpointer=InMemorySaver(),
        with_memory=True,
        memory_deps=mdeps,
        with_output=True,
        with_review=True,
        review_deps=rdeps_rev,
    )
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    # Both branches present
    assert ("output", "human_review") in edges
    assert ("output", "review_store") in edges
    # Review converges into review_store
    assert ("human_review", "review_store") in edges


def test_review_store_terminates_graph(
    portfolio_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    mdeps = MemoryDeps(db_session=portfolio_db_session, beliefs_path=beliefs_tmp_dir)
    rdeps = ReviewDeps(db_session=portfolio_db_session, policy=ReviewPolicy())
    graph = build_debate_pipeline(
        with_memory=True,
        memory_deps=mdeps,
        with_output=True,
        review_deps=rdeps,
    )
    edges = {(e.source, e.target) for e in graph.get_graph().edges}
    assert any(
        src == "review_store" and tgt in {END, "__end__"} for src, tgt in edges
    )
