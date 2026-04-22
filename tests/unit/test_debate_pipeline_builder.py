"""Tests for the Phase-5 build_debate_pipeline builder (pipeline topology).

Asserts the compiled graph's node set and edge set match the documented
debate topology:

    START -> [fundamental, sentiment, technical] (parallel fan-out)
          -> manager
          -> bull -> bear -> rebuttal -> final_arguments -> debate_synthesis
          -> signal
          -> END

Critical invariants enforced at the topology layer:

    - build_debate_pipeline exists alongside build_multi_agent_pipeline;
      neither replaces the other.
    - (manager, signal) direct edge is ABSENT in the debate pipeline
      (Pitfall-4: otherwise a diamond forms with the debate chain).
    - Phase-4's build_multi_agent_pipeline is byte-for-byte unchanged --
      still compiles, still has the direct (manager, signal) edge, still
      has NO debate nodes.

These tests do NOT invoke any agent -- they only compile the graph and
inspect the StateGraph edge list.
"""

from __future__ import annotations

import os

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from langgraph.graph.state import CompiledStateGraph  # noqa: E402

from ai_hedge_fund.graph.pipeline import (  # noqa: E402
    build_debate_pipeline,
    build_multi_agent_pipeline,
)


class TestBuildDebatePipelineCompiles:
    """build_debate_pipeline() returns a CompiledStateGraph."""

    def test_returns_compiled_state_graph(self) -> None:
        graph = build_debate_pipeline()
        assert isinstance(graph, CompiledStateGraph)

    def test_has_ainvoke_method(self) -> None:
        graph = build_debate_pipeline()
        assert hasattr(graph, "ainvoke")


class TestDebatePipelineTopology:
    """Node set + edge set match the documented sequential-debate topology."""

    def test_has_all_agent_nodes(self) -> None:
        graph = build_debate_pipeline()
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
        assert expected.issubset(nodes), f"Missing nodes: {expected - nodes}"

    def test_preserves_phase4_fanout_edges(self) -> None:
        graph = build_debate_pipeline()
        edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
        assert ("__start__", "fundamental") in edge_pairs
        assert ("__start__", "sentiment") in edge_pairs
        assert ("__start__", "technical") in edge_pairs

    def test_preserves_phase4_fanin_edges(self) -> None:
        graph = build_debate_pipeline()
        edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
        assert ("fundamental", "manager") in edge_pairs
        assert ("sentiment", "manager") in edge_pairs
        assert ("technical", "manager") in edge_pairs

    def test_has_sequential_debate_chain(self) -> None:
        graph = build_debate_pipeline()
        edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
        assert ("manager", "bull") in edge_pairs
        assert ("bull", "bear") in edge_pairs
        assert ("bear", "rebuttal") in edge_pairs
        assert ("rebuttal", "final_arguments") in edge_pairs
        assert ("final_arguments", "debate_synthesis") in edge_pairs
        assert ("debate_synthesis", "signal") in edge_pairs
        assert ("signal", "__end__") in edge_pairs

    def test_no_manager_to_signal_diamond(self) -> None:
        """Pitfall-4 enforcement: (manager, signal) MUST NOT be a direct edge.

        A direct manager->signal edge forms a diamond with the debate chain
        (manager->bull->...->debate_synthesis->signal), causing the signal
        node to fire twice or receive inconsistent state.
        """
        graph = build_debate_pipeline()
        edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
        assert ("manager", "signal") not in edge_pairs, (
            "Direct manager->signal edge creates a diamond with the debate "
            "chain. See 05-RESEARCH.md Pitfall 4."
        )


class TestPhase4PipelineStillWorks:
    """Option B: build_multi_agent_pipeline is byte-for-byte unchanged."""

    def test_build_multi_agent_pipeline_still_compiles(self) -> None:
        graph = build_multi_agent_pipeline()
        assert isinstance(graph, CompiledStateGraph)

    def test_build_multi_agent_pipeline_has_direct_manager_signal_edge(self) -> None:
        """Phase-4 pipeline has manager->signal edge; Phase-5 does NOT.

        Confirms the two pipelines have DISTINCT topologies -- the debate
        pipeline is a new builder, not a modification of the Phase-4 builder.
        """
        graph = build_multi_agent_pipeline()
        edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
        assert ("manager", "signal") in edge_pairs

    def test_build_multi_agent_pipeline_has_no_debate_nodes(self) -> None:
        graph = build_multi_agent_pipeline()
        nodes = set(graph.get_graph().nodes)
        for debate_node in (
            "bull",
            "bear",
            "rebuttal",
            "final_arguments",
            "debate_synthesis",
        ):
            assert debate_node not in nodes, (
                f"Phase-4 pipeline must NOT contain {debate_node}; "
                "that is Phase-5 only."
            )
