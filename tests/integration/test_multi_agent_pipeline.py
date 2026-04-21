"""Integration tests for the Phase-4 multi-agent pipeline.

Three test categories:

A. **Pipeline compilation and topology tests** (always run, no API key,
   no DB). Verify that ``build_multi_agent_pipeline`` returns a
   ``CompiledStateGraph`` with the expected 5 nodes and fan-out / fan-in
   edge structure, and that Phase-1 / Phase-3 pipelines still compile
   (no regression).

B. **TestModel-based end-to-end flow** (always run, no real LLM, no
   network). Overrides every agent (3 analysts + manager + signal) with
   PydanticAI's ``TestModel``, invokes the compiled pipeline, and
   verifies the state after ``ainvoke`` contains exactly 3 analyst
   reports, a thesis dict, a signal dict, and no error.

   ``call_tools=[]`` is required on the three analyst agents because
   their tools hit SEC EDGAR / yfinance / Finnhub and would cause real
   network side effects during unit testing.

C. No real-LLM tests in this file -- the Phase-4 pipeline exercises
   four agents and would cost roughly $1-3 per run, so we gate real-LLM
   evaluation behind phase-level UAT scripts rather than pytest.

Expected timings:
    - Compilation / topology tests: sub-second.
    - TestModel flow test: <1 second.
"""

from __future__ import annotations

import asyncio
import os

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.graph.state import CompiledStateGraph  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402

from ai_hedge_fund.agents.fundamental import fundamental_agent  # noqa: E402
from ai_hedge_fund.agents.manager import manager_agent  # noqa: E402
from ai_hedge_fund.agents.sentiment import sentiment_agent  # noqa: E402
from ai_hedge_fund.agents.signal import signal_agent  # noqa: E402
from ai_hedge_fund.agents.technical import technical_agent  # noqa: E402
from ai_hedge_fund.graph.pipeline import (  # noqa: E402
    build_multi_agent_pipeline,
    build_pipeline,
    build_research_pipeline,
)

# ---------------------------------------------------------------------------
# A. Pipeline compilation and topology tests
# ---------------------------------------------------------------------------


def test_multi_agent_pipeline_compiles() -> None:
    """build_multi_agent_pipeline() returns a CompiledStateGraph."""
    graph = build_multi_agent_pipeline()
    assert graph is not None
    assert isinstance(graph, CompiledStateGraph)
    assert hasattr(graph, "ainvoke")


def test_multi_agent_pipeline_with_checkpointer() -> None:
    """build_multi_agent_pipeline(checkpointer=...) compiles cleanly."""
    checkpointer = MemorySaver()
    graph = build_multi_agent_pipeline(checkpointer=checkpointer)
    assert graph is not None
    assert isinstance(graph, CompiledStateGraph)


def test_multi_agent_pipeline_has_all_five_nodes() -> None:
    """Compiled graph has fundamental, sentiment, technical, manager, signal."""
    graph = build_multi_agent_pipeline()
    node_ids = {node.id for node in graph.get_graph().nodes.values()}
    assert "fundamental" in node_ids
    assert "sentiment" in node_ids
    assert "technical" in node_ids
    assert "manager" in node_ids
    assert "signal" in node_ids


def test_multi_agent_pipeline_has_start_and_end() -> None:
    """Compiled graph includes __start__ and __end__ markers."""
    graph = build_multi_agent_pipeline()
    node_ids = {node.id for node in graph.get_graph().nodes.values()}
    assert "__start__" in node_ids
    assert "__end__" in node_ids


def test_multi_agent_pipeline_fan_out_edges() -> None:
    """START fans out to all three analyst nodes."""
    graph = build_multi_agent_pipeline()
    edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
    assert ("__start__", "fundamental") in edge_pairs
    assert ("__start__", "sentiment") in edge_pairs
    assert ("__start__", "technical") in edge_pairs


def test_multi_agent_pipeline_fan_in_edges() -> None:
    """All three analysts feed into the manager (fan-in)."""
    graph = build_multi_agent_pipeline()
    edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
    assert ("fundamental", "manager") in edge_pairs
    assert ("sentiment", "manager") in edge_pairs
    assert ("technical", "manager") in edge_pairs


def test_multi_agent_pipeline_tail_edges() -> None:
    """Manager -> signal -> END completes the pipeline."""
    graph = build_multi_agent_pipeline()
    edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
    assert ("manager", "signal") in edge_pairs
    assert ("signal", "__end__") in edge_pairs


def test_multi_agent_pipeline_node_count() -> None:
    """Graph has exactly 7 nodes: __start__, 3 analysts, manager, signal, __end__."""
    graph = build_multi_agent_pipeline()
    assert len(graph.get_graph().nodes) == 7


# ---------------------------------------------------------------------------
# No regression -- Phase-1 and Phase-3 pipelines still compile
# ---------------------------------------------------------------------------


def test_phase3_research_pipeline_still_compiles() -> None:
    """build_research_pipeline() still returns a CompiledStateGraph (no regression)."""
    graph = build_research_pipeline()
    assert graph is not None
    assert isinstance(graph, CompiledStateGraph)
    node_ids = {node.id for node in graph.get_graph().nodes.values()}
    assert "research" in node_ids
    assert "signal" in node_ids


def test_phase1_pipeline_still_compiles() -> None:
    """build_pipeline() still returns a CompiledStateGraph (no regression)."""
    graph = build_pipeline()
    assert graph is not None
    assert isinstance(graph, CompiledStateGraph)
    node_ids = {node.id for node in graph.get_graph().nodes.values()}
    assert "extract" in node_ids
    assert "analyze" in node_ids


# ---------------------------------------------------------------------------
# B. TestModel-based end-to-end flow
# ---------------------------------------------------------------------------


def test_full_multi_agent_pipeline_with_test_model() -> None:
    """Full fan-out/fan-in flow completes with TestModel on every agent.

    Overrides all 5 agents with ``TestModel``, then invokes the compiled
    pipeline with a minimal starting state. Verifies:
      - analyst_reports has exactly 3 entries (one per parallel analyst).
      - Each analyst_reports entry has the expected shape (analyst name,
        analysis dict, tokens_used).
      - thesis is a dict (set by manager_node).
      - signal is a dict (set by multi_agent_signal_node).
      - No top-level error was set.

    ``call_tools=[]`` is set for the 3 analyst agents so TestModel does
    not invoke their real tool wrappers (which would hit SEC EDGAR /
    yfinance / Finnhub). TestModel auto-fills the schema-valid output
    from the declared ``output_type`` of each agent.

    Note: Uses ``asyncio.run`` rather than an ``async def`` test to stay
    compatible with the current pytest configuration, which does not
    have ``pytest-asyncio`` available. This mirrors the sync-wrapper
    pattern used in ``tests/unit/test_research_node.py``.
    """
    graph = build_multi_agent_pipeline()
    initial_state = {"ticker": "AAPL", "as_of_date": "2024-01-02"}

    async def _invoke() -> dict:
        with (
            fundamental_agent.override(model=TestModel(call_tools=[])),
            sentiment_agent.override(model=TestModel(call_tools=[])),
            technical_agent.override(model=TestModel(call_tools=[])),
            manager_agent.override(model=TestModel()),
            signal_agent.override(model=TestModel()),
        ):
            return await graph.ainvoke(initial_state)

    final_state = asyncio.run(_invoke())

    # No top-level error.
    assert final_state.get("error") is None, f"Unexpected error: {final_state.get('error')}"

    # All three analyst reports made it through the reducer.
    reports = final_state.get("analyst_reports", [])
    assert len(reports) == 3, f"Expected 3 analyst reports, got {len(reports)}"

    analyst_names = {r["analyst"] for r in reports}
    assert analyst_names == {"fundamental", "sentiment", "technical"}

    for report in reports:
        assert "analysis" in report
        assert isinstance(report["analysis"], dict)
        assert "tokens_used" in report
        assert isinstance(report["tokens_used"], int)
        assert report["tokens_used"] >= 0

    # Manager produced a thesis dict.
    assert "thesis" in final_state
    assert isinstance(final_state["thesis"], dict)

    # Signal node produced a signal dict.
    assert "signal" in final_state
    assert isinstance(final_state["signal"], dict)
