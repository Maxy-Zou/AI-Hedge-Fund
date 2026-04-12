"""Integration tests for LangGraph pipeline compilation and execution.

Tests are split into two categories:
1. Compilation tests -- verify graph structure, run without API keys or DB.
2. LLM integration tests -- marked with requires_api_key, skip without
   a real ANTHROPIC_API_KEY (dummy test keys don't count).
"""

from __future__ import annotations

import os

import pytest

from ai_hedge_fund.graph.pipeline import build_pipeline

# A dummy API key used for agent construction in tests -- not valid for LLM calls.
_DUMMY_KEY_PREFIX = "test-key"


def _has_real_api_key() -> bool:
    """Check if ANTHROPIC_API_KEY is set to a real key (not a dummy test key)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return bool(key) and not key.startswith(_DUMMY_KEY_PREFIX)


# ---------------------------------------------------------------------------
# Compilation tests (no API key or DB required)
# ---------------------------------------------------------------------------


def test_build_pipeline_compiles_without_checkpointer():
    """build_pipeline() returns a compiled graph without a checkpointer."""
    graph = build_pipeline()
    assert graph is not None
    # CompiledStateGraph has an ainvoke method
    assert hasattr(graph, "ainvoke")


def test_compiled_graph_has_expected_nodes():
    """Compiled graph contains 'extract' and 'analyze' nodes."""
    graph = build_pipeline()
    graph_repr = graph.get_graph()
    node_ids = {node.id for node in graph_repr.nodes.values()}
    assert "extract" in node_ids
    assert "analyze" in node_ids


def test_compiled_graph_has_start_and_end():
    """Compiled graph contains __start__ and __end__ nodes."""
    graph = build_pipeline()
    graph_repr = graph.get_graph()
    node_ids = {node.id for node in graph_repr.nodes.values()}
    assert "__start__" in node_ids
    assert "__end__" in node_ids


def test_compiled_graph_node_count():
    """Graph should have exactly 4 nodes: __start__, extract, analyze, __end__."""
    graph = build_pipeline()
    graph_repr = graph.get_graph()
    assert len(graph_repr.nodes) == 4


def test_compiled_graph_edge_structure():
    """Graph edges should form: __start__ -> extract -> analyze -> __end__."""
    graph = build_pipeline()
    graph_repr = graph.get_graph()
    edge_pairs = {(e.source, e.target) for e in graph_repr.edges}
    assert ("__start__", "extract") in edge_pairs
    assert ("extract", "analyze") in edge_pairs
    assert ("analyze", "__end__") in edge_pairs


# ---------------------------------------------------------------------------
# LLM integration tests (require real ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------

requires_api_key = pytest.mark.skipif(
    not _has_real_api_key(),
    reason="Real ANTHROPIC_API_KEY not set -- skipping LLM integration test",
)


@requires_api_key
@pytest.mark.asyncio
async def test_requires_api_key_graph_invoke():
    """Full pipeline invocation returns state with extraction and analysis."""
    graph = build_pipeline()
    state = await graph.ainvoke(
        {
            "ticker": "AAPL",
            "raw_text": "Revenue: $394B, Net Income: $97B, EPS: $6.42",
        },
    )
    assert "extraction" in state
    assert "analysis" in state
    assert isinstance(state["extraction"], dict)
    assert isinstance(state["analysis"], dict)


@requires_api_key
@pytest.mark.asyncio
async def test_requires_api_key_extraction_has_key_metrics():
    """Extraction result contains key_metrics list and data_quality float."""
    graph = build_pipeline()
    state = await graph.ainvoke(
        {
            "ticker": "AAPL",
            "raw_text": "Revenue: $394B, Net Income: $97B, EPS: $6.42",
        },
    )
    extraction = state["extraction"]
    assert "key_metrics" in extraction
    assert isinstance(extraction["key_metrics"], list)
    assert "data_quality" in extraction
    assert isinstance(extraction["data_quality"], (int, float))


@requires_api_key
@pytest.mark.asyncio
async def test_requires_api_key_analysis_has_expected_fields():
    """Analysis result contains summary, confidence, and key_findings."""
    graph = build_pipeline()
    state = await graph.ainvoke(
        {
            "ticker": "AAPL",
            "raw_text": "Revenue: $394B, Net Income: $97B, EPS: $6.42",
        },
    )
    analysis = state["analysis"]
    assert "summary" in analysis
    assert isinstance(analysis["summary"], str)
    assert "confidence" in analysis
    assert isinstance(analysis["confidence"], (int, float))
    assert "key_findings" in analysis
    assert isinstance(analysis["key_findings"], list)
