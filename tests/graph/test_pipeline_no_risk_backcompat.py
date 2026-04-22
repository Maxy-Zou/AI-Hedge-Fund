"""Phase-5 backcompat tests for ``build_debate_pipeline(with_risk=False)``.

The default ``build_debate_pipeline()`` call -- used throughout the
Phase-5 test suite -- MUST produce the pre-Phase-6 topology so existing
tests do not regress. The risk_manager node is absent; the direct
``debate_synthesis -> signal`` edge is present exactly as it was in
Phase 5.
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from langgraph.graph.state import CompiledStateGraph

from ai_hedge_fund.graph.pipeline import build_debate_pipeline


def test_default_build_is_phase5_backcompat() -> None:
    """No args -> with_risk defaults to False -> Phase-5 topology."""
    graph = build_debate_pipeline()
    assert isinstance(graph, CompiledStateGraph)


def test_backcompat_has_no_risk_manager_node() -> None:
    graph = build_debate_pipeline(with_risk=False)
    nodes = set(graph.get_graph().nodes)
    assert "risk_manager" not in nodes


def test_backcompat_has_direct_debate_synthesis_to_signal_edge() -> None:
    graph = build_debate_pipeline(with_risk=False)
    edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
    assert ("debate_synthesis", "signal") in edge_pairs
    assert ("signal", "__end__") in edge_pairs


def test_backcompat_preserves_phase5_node_set() -> None:
    graph = build_debate_pipeline(with_risk=False)
    nodes = set(graph.get_graph().nodes)
    expected = {
        "fundamental",
        "sentiment",
        "technical",
        "manager",
        "bull",
        "bear",
        "rebuttal",
        "final_arguments",
        "debate_synthesis",
        "signal",
        "__start__",
        "__end__",
    }
    assert expected.issubset(nodes)


def test_backcompat_allows_missing_risk_deps() -> None:
    """Unlike with_risk=True, the backcompat path does NOT require risk_deps."""
    # No risk_deps argument -- this must not raise.
    graph = build_debate_pipeline(with_risk=False, risk_deps=None)
    assert isinstance(graph, CompiledStateGraph)
