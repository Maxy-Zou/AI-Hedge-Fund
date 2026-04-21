"""Tests for the Phase-4 multi-agent LangGraph nodes.

These tests verify node wiring and return-shape contracts without making
real LLM calls. They rely on PydanticAI's ``agent.override(model=TestModel)``
pattern to short-circuit the actual model call while still exercising the
node's success and error paths.

Coverage:
    - MultiAgentPipelineState exists and has the ``operator.add`` reducer
      annotation on ``analyst_reports``.
    - All five new nodes (fundamental / sentiment / technical / manager /
      multi_agent_signal) are async callables.
    - Each analyst node wraps its output in a single-element list so the
      reducer merges parallel outputs correctly.
    - manager_node short-circuits cleanly when no analyst reports are
      available (returns ``{"error": ...}`` instead of crashing).
    - multi_agent_signal_node preserves the Phase-3 short-circuit semantics
      (skip-on-upstream-error, error-when-no-thesis).
    - Existing Phase-3 nodes (research_node, signal_node, extract_node,
      analyze_node) still exist and are async (no regression).
"""

from __future__ import annotations

import asyncio
import inspect
import operator
import os
import typing

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai.models.test import TestModel  # noqa: E402

from ai_hedge_fund.agents.fundamental import fundamental_agent  # noqa: E402
from ai_hedge_fund.agents.manager import manager_agent  # noqa: E402
from ai_hedge_fund.agents.sentiment import sentiment_agent  # noqa: E402
from ai_hedge_fund.agents.technical import technical_agent  # noqa: E402
from ai_hedge_fund.graph.nodes import (  # noqa: E402
    analyze_node,
    extract_node,
    fundamental_node,
    manager_node,
    multi_agent_signal_node,
    research_node,
    sentiment_node,
    signal_node,
    technical_node,
)
from ai_hedge_fund.schemas.state import MultiAgentPipelineState  # noqa: E402


class TestMultiAgentPipelineStateSchema:
    """MultiAgentPipelineState TypedDict carries the operator.add reducer."""

    def test_state_class_exists(self) -> None:
        """MultiAgentPipelineState is importable from schemas.state."""
        assert MultiAgentPipelineState is not None

    def test_state_has_required_keys(self) -> None:
        """ticker and as_of_date are declared (via Required[str])."""
        hints = typing.get_type_hints(MultiAgentPipelineState, include_extras=True)
        assert "ticker" in hints
        assert "as_of_date" in hints

    def test_state_has_analyst_reports_field(self) -> None:
        """analyst_reports is present in the TypedDict annotations."""
        hints = typing.get_type_hints(MultiAgentPipelineState, include_extras=True)
        assert "analyst_reports" in hints

    def test_analyst_reports_uses_operator_add_reducer(self) -> None:
        """analyst_reports carries Annotated[list, operator.add] metadata.

        The reducer is what lets LangGraph merge parallel analyst outputs
        instead of overwriting them. This test fails loudly if a future
        refactor accidentally drops the annotation.
        """
        hints = typing.get_type_hints(MultiAgentPipelineState, include_extras=True)
        ar_hint = hints["analyst_reports"]
        metadata = typing.get_args(ar_hint)
        # Expect Annotated[list[dict], operator.add] -> args are (list[dict], operator.add)
        assert len(metadata) >= 2
        assert operator.add in metadata, (
            "analyst_reports must carry operator.add as its Annotated reducer"
        )

    def test_state_has_thesis_signal_error_keys(self) -> None:
        """Optional thesis / signal / error keys are declared."""
        hints = typing.get_type_hints(MultiAgentPipelineState, include_extras=True)
        assert "thesis" in hints
        assert "signal" in hints
        assert "error" in hints


class TestNewNodesAreAsync:
    """All four new analyst/manager nodes and the signal adapter are coroutines."""

    def test_fundamental_node_is_async(self) -> None:
        assert inspect.iscoroutinefunction(fundamental_node)

    def test_sentiment_node_is_async(self) -> None:
        assert inspect.iscoroutinefunction(sentiment_node)

    def test_technical_node_is_async(self) -> None:
        assert inspect.iscoroutinefunction(technical_node)

    def test_manager_node_is_async(self) -> None:
        assert inspect.iscoroutinefunction(manager_node)

    def test_multi_agent_signal_node_is_async(self) -> None:
        assert inspect.iscoroutinefunction(multi_agent_signal_node)


class TestExistingNodesUnchanged:
    """Phase-1/3 nodes must keep their existing signatures (no regression)."""

    def test_extract_node_exists(self) -> None:
        assert inspect.iscoroutinefunction(extract_node)

    def test_analyze_node_exists(self) -> None:
        assert inspect.iscoroutinefunction(analyze_node)

    def test_research_node_exists(self) -> None:
        assert inspect.iscoroutinefunction(research_node)

    def test_signal_node_exists(self) -> None:
        assert inspect.iscoroutinefunction(signal_node)


class TestFundamentalNodeHappyPath:
    """fundamental_node returns a single-element analyst_reports list on success."""

    def test_returns_analyst_reports_list_of_one(self) -> None:
        """Success path wraps the analyst output in a length-1 list."""
        state: MultiAgentPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
        }
        with fundamental_agent.override(model=TestModel(call_tools=[])):
            result = asyncio.run(fundamental_node(state))

        assert "analyst_reports" in result
        reports = result["analyst_reports"]
        assert isinstance(reports, list)
        assert len(reports) == 1

    def test_report_entry_has_analyst_name(self) -> None:
        """The single entry names 'fundamental' as the analyst."""
        state: MultiAgentPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
        }
        with fundamental_agent.override(model=TestModel(call_tools=[])):
            result = asyncio.run(fundamental_node(state))

        entry = result["analyst_reports"][0]
        assert entry["analyst"] == "fundamental"

    def test_report_entry_has_analysis_dict(self) -> None:
        """Success path includes an ``analysis`` dict from model_dump()."""
        state: MultiAgentPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
        }
        with fundamental_agent.override(model=TestModel(call_tools=[])):
            result = asyncio.run(fundamental_node(state))

        entry = result["analyst_reports"][0]
        assert "analysis" in entry
        assert isinstance(entry["analysis"], dict)

    def test_report_entry_has_tokens_used(self) -> None:
        """Success path records tokens_used as a non-negative int."""
        state: MultiAgentPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
        }
        with fundamental_agent.override(model=TestModel(call_tools=[])):
            result = asyncio.run(fundamental_node(state))

        entry = result["analyst_reports"][0]
        assert "tokens_used" in entry
        assert isinstance(entry["tokens_used"], int)
        assert entry["tokens_used"] >= 0


class TestSentimentNodeHappyPath:
    """sentiment_node has the same shape as fundamental_node with a different name."""

    def test_returns_analyst_reports_list_of_one(self) -> None:
        state: MultiAgentPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
        }
        with sentiment_agent.override(model=TestModel(call_tools=[])):
            result = asyncio.run(sentiment_node(state))

        assert "analyst_reports" in result
        assert len(result["analyst_reports"]) == 1
        assert result["analyst_reports"][0]["analyst"] == "sentiment"


class TestTechnicalNodeHappyPath:
    """technical_node has the same shape as the other analyst nodes."""

    def test_returns_analyst_reports_list_of_one(self) -> None:
        state: MultiAgentPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
        }
        with technical_agent.override(model=TestModel(call_tools=[])):
            result = asyncio.run(technical_node(state))

        assert "analyst_reports" in result
        assert len(result["analyst_reports"]) == 1
        assert result["analyst_reports"][0]["analyst"] == "technical"


class TestManagerNodeErrorPaths:
    """manager_node must not crash on empty analyst_reports."""

    def test_no_reports_returns_error(self) -> None:
        """Empty analyst_reports produces a descriptive error message."""
        state: MultiAgentPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
        }
        result = asyncio.run(manager_node(state))
        assert "error" in result
        assert "analyst report" in result["error"].lower()

    def test_empty_list_returns_error(self) -> None:
        """Explicit empty list triggers the same branch."""
        state: MultiAgentPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "analyst_reports": [],
        }
        result = asyncio.run(manager_node(state))
        assert "error" in result


class TestManagerNodeHappyPath:
    """manager_node with valid reports produces a thesis dict."""

    def test_returns_thesis_dict(self) -> None:
        """Non-empty analyst_reports produces a thesis model_dump."""
        reports = [
            {
                "analyst": "fundamental",
                "analysis": {
                    "ticker": "AAPL",
                    "valuation_assessment": "fair",
                    "confidence": 70,
                },
                "tokens_used": 1000,
            },
            {
                "analyst": "sentiment",
                "analysis": {
                    "ticker": "AAPL",
                    "composite_score": 0.3,
                    "confidence": 60,
                },
                "tokens_used": 800,
            },
            {
                "analyst": "technical",
                "analysis": {
                    "ticker": "AAPL",
                    "momentum_assessment": "positive",
                    "confidence": 65,
                },
                "tokens_used": 700,
            },
        ]
        state: MultiAgentPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "analyst_reports": reports,
        }
        with manager_agent.override(model=TestModel()):
            result = asyncio.run(manager_node(state))

        assert "thesis" in result
        assert isinstance(result["thesis"], dict)


class TestMultiAgentSignalNodeShortCircuits:
    """multi_agent_signal_node preserves short-circuit semantics."""

    def test_skips_when_error_in_state(self) -> None:
        """If a prior node set error, return empty dict (don't overwrite)."""
        state: MultiAgentPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "error": "Manager budget exceeded",
        }
        result = asyncio.run(multi_agent_signal_node(state))
        assert result == {}

    def test_errors_when_thesis_missing(self) -> None:
        """Missing thesis produces an explicit error message."""
        state: MultiAgentPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
        }
        result = asyncio.run(multi_agent_signal_node(state))
        assert "error" in result
        assert "thesis" in result["error"].lower()

    def test_errors_when_thesis_is_none(self) -> None:
        """Thesis=None is treated as missing."""
        state: MultiAgentPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "thesis": None,
        }
        result = asyncio.run(multi_agent_signal_node(state))
        assert "error" in result
