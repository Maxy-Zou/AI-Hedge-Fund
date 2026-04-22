"""Tests for ``build_debate_pipeline(with_risk=True, risk_deps=...)``.

Verifies the Phase-6 topology:

    ... -> debate_synthesis -> risk_manager -[conditional]-> {signal, END}

The tests do NOT invoke the agents end-to-end (that's in the Phase-6
integration suite 06-06); they only compile the graph and inspect the
node set + edge set, plus sanity-check the builder contract (ValueError
when risk_deps is missing).
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pytest
from langgraph.graph.state import CompiledStateGraph

from ai_hedge_fund.graph.pipeline import build_debate_pipeline
from ai_hedge_fund.graph.risk_deps import RiskDeps


def test_builder_returns_compiled_state_graph(risk_deps: RiskDeps) -> None:
    graph = build_debate_pipeline(with_risk=True, risk_deps=risk_deps)
    assert isinstance(graph, CompiledStateGraph)


def test_pipeline_includes_risk_manager_node(risk_deps: RiskDeps) -> None:
    graph = build_debate_pipeline(with_risk=True, risk_deps=risk_deps)
    nodes = set(graph.get_graph().nodes)
    assert "risk_manager" in nodes


def test_debate_synthesis_connects_to_risk_manager(risk_deps: RiskDeps) -> None:
    """When with_risk=True, debate_synthesis feeds risk_manager, NOT signal."""
    graph = build_debate_pipeline(with_risk=True, risk_deps=risk_deps)
    edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}

    assert ("debate_synthesis", "risk_manager") in edge_pairs
    # Direct debate_synthesis -> signal must be absent when risk is active.
    assert ("debate_synthesis", "signal") not in edge_pairs


def test_risk_manager_has_conditional_edges_to_signal_and_end(
    risk_deps: RiskDeps,
) -> None:
    """Approved path goes to signal; vetoed path ends the graph."""
    graph = build_debate_pipeline(with_risk=True, risk_deps=risk_deps)
    edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}

    assert ("risk_manager", "signal") in edge_pairs
    assert ("risk_manager", "__end__") in edge_pairs


def test_signal_still_terminates_the_graph(risk_deps: RiskDeps) -> None:
    graph = build_debate_pipeline(with_risk=True, risk_deps=risk_deps)
    edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
    assert ("signal", "__end__") in edge_pairs


def test_builder_rejects_missing_risk_deps() -> None:
    with pytest.raises(ValueError, match="risk_deps"):
        build_debate_pipeline(with_risk=True, risk_deps=None)


def test_no_diamond_from_debate_synthesis(risk_deps: RiskDeps) -> None:
    """Pitfall 4 regression: exactly one outgoing edge from debate_synthesis."""
    graph = build_debate_pipeline(with_risk=True, risk_deps=risk_deps)
    edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
    outgoing = [t for (s, t) in edge_pairs if s == "debate_synthesis"]
    assert outgoing == ["risk_manager"]
