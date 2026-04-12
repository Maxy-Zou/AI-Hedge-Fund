"""Tests for research_node, signal_node, and build_research_pipeline.

These tests verify pipeline wiring without making real LLM calls:
- research_node and signal_node exist as async callables.
- signal_node short-circuits (empty dict) when an upstream error is set.
- signal_node returns an error dict when no thesis is present.
- build_research_pipeline compiles a graph with research + signal nodes and
  a START -> research -> signal -> END edge structure.
- The existing build_pipeline is untouched (no regression).
"""

from __future__ import annotations

import asyncio
import inspect
import os

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from ai_hedge_fund.graph.nodes import (
    analyze_node,
    extract_node,
    research_node,
    signal_node,
)
from ai_hedge_fund.graph.pipeline import build_pipeline, build_research_pipeline


class TestNodesExist:
    """Verify the new nodes are async callables and existing nodes still exist."""

    def test_research_node_is_async(self) -> None:
        """research_node is an async coroutine function."""
        assert inspect.iscoroutinefunction(research_node)

    def test_signal_node_is_async(self) -> None:
        """signal_node is an async coroutine function."""
        assert inspect.iscoroutinefunction(signal_node)

    def test_extract_node_still_exists(self) -> None:
        """Existing extract_node is preserved (no regression)."""
        assert inspect.iscoroutinefunction(extract_node)

    def test_analyze_node_still_exists(self) -> None:
        """Existing analyze_node is preserved (no regression)."""
        assert inspect.iscoroutinefunction(analyze_node)


class TestSignalNodeShortCircuits:
    """signal_node must skip work when upstream errored or thesis is missing."""

    def test_skips_when_error_in_state(self) -> None:
        """signal_node returns an empty dict (no new state) if ``error`` is set."""
        state = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-01",
            "error": "Research budget exceeded",
        }
        result = asyncio.run(signal_node(state))
        assert result == {}

    def test_errors_when_thesis_missing(self) -> None:
        """signal_node returns an error dict if no thesis is present in state."""
        state = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-01",
        }
        result = asyncio.run(signal_node(state))
        assert "error" in result
        assert "thesis" in result["error"].lower()

    def test_errors_when_thesis_is_none(self) -> None:
        """signal_node treats thesis=None as missing (still returns error)."""
        state = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-01",
            "thesis": None,
        }
        result = asyncio.run(signal_node(state))
        assert "error" in result
        assert "thesis" in result["error"].lower()


class TestResearchPipeline:
    """Tests for the compiled research pipeline graph structure."""

    def test_build_research_pipeline_compiles(self) -> None:
        """build_research_pipeline() returns a compiled graph with ainvoke."""
        graph = build_research_pipeline()
        assert graph is not None
        assert hasattr(graph, "ainvoke")

    def test_pipeline_has_research_node(self) -> None:
        """Compiled graph contains the 'research' node."""
        graph = build_research_pipeline()
        node_ids = {node.id for node in graph.get_graph().nodes.values()}
        assert "research" in node_ids

    def test_pipeline_has_signal_node(self) -> None:
        """Compiled graph contains the 'signal' node."""
        graph = build_research_pipeline()
        node_ids = {node.id for node in graph.get_graph().nodes.values()}
        assert "signal" in node_ids

    def test_pipeline_has_start_and_end(self) -> None:
        """Compiled graph contains the __start__ and __end__ markers."""
        graph = build_research_pipeline()
        node_ids = {node.id for node in graph.get_graph().nodes.values()}
        assert "__start__" in node_ids
        assert "__end__" in node_ids

    def test_pipeline_edge_structure(self) -> None:
        """Edges form START -> research -> signal -> END."""
        graph = build_research_pipeline()
        edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
        assert ("__start__", "research") in edge_pairs
        assert ("research", "signal") in edge_pairs
        assert ("signal", "__end__") in edge_pairs

    def test_pipeline_node_count(self) -> None:
        """Graph should have exactly 4 nodes: __start__, research, signal, __end__."""
        graph = build_research_pipeline()
        assert len(graph.get_graph().nodes) == 4


class TestExistingPipeline:
    """Ensure the legacy Phase-1 pipeline still compiles (no regression)."""

    def test_build_pipeline_still_compiles(self) -> None:
        """Legacy build_pipeline still returns a compiled graph."""
        graph = build_pipeline()
        assert graph is not None
        assert hasattr(graph, "ainvoke")

    def test_legacy_pipeline_has_extract_and_analyze(self) -> None:
        """Legacy graph still contains extract + analyze nodes."""
        graph = build_pipeline()
        node_ids = {node.id for node in graph.get_graph().nodes.values()}
        assert "extract" in node_ids
        assert "analyze" in node_ids
