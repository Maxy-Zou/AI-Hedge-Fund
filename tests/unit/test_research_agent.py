"""Tests for the research agent: ResearchDeps, tool registration, usage limits.

These tests verify the agent wiring without making real LLM calls. They
validate that:
- ResearchDeps is an immutable (frozen) dataclass with the required fields.
- research_agent is an ``Agent[ResearchDeps, ThesisOutput]`` configured for
  ModelTier.ANALYSIS with retries=2.
- All 6 data tool wrappers are registered on the agent.
- The system prompt enforces temporal controls and tool-first rules.
- get_research_limits returns UsageLimits matching the ANALYSIS budget.
"""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError
from datetime import date

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pytest
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.research import (
    RESEARCH_SYSTEM_PROMPT_TEMPLATE,
    ResearchDeps,
    get_research_limits,
    research_agent,
)
from ai_hedge_fund.schemas.agents import ThesisOutput


class TestResearchDeps:
    """Tests for the immutable ResearchDeps dataclass."""

    def test_frozen(self) -> None:
        """ResearchDeps instances cannot be mutated (frozen dataclass)."""
        deps = ResearchDeps(ticker="AAPL", as_of_date=date(2024, 1, 1))
        with pytest.raises(FrozenInstanceError):
            deps.ticker = "MSFT"  # type: ignore[misc]

    def test_defaults(self) -> None:
        """db_session and settings default to None when not supplied."""
        deps = ResearchDeps(ticker="AAPL", as_of_date=date(2024, 1, 1))
        assert deps.db_session is None
        assert deps.settings is None

    def test_required_fields(self) -> None:
        """ticker and as_of_date are required positional/keyword fields."""
        # Positional construction works
        deps = ResearchDeps("AAPL", date(2024, 1, 1))
        assert deps.ticker == "AAPL"
        assert deps.as_of_date == date(2024, 1, 1)

        # Missing ticker raises TypeError
        with pytest.raises(TypeError):
            ResearchDeps(as_of_date=date(2024, 1, 1))  # type: ignore[call-arg]

        # Missing as_of_date raises TypeError
        with pytest.raises(TypeError):
            ResearchDeps(ticker="AAPL")  # type: ignore[call-arg]


class TestResearchAgent:
    """Tests for the research_agent Agent instance."""

    def test_agent_exists(self) -> None:
        """research_agent is a PydanticAI Agent instance."""
        assert isinstance(research_agent, Agent)

    def test_agent_model(self) -> None:
        """research_agent uses the ANALYSIS tier model (Sonnet)."""
        assert research_agent.model.model_name == "claude-sonnet-4-6"

    def test_agent_output_type(self) -> None:
        """research_agent produces ThesisOutput."""
        assert research_agent._output_type is ThesisOutput

    def test_agent_has_retries(self) -> None:
        """research_agent is configured with retries=2 for output validation."""
        # PydanticAI applies the `retries` constructor kwarg to both
        # _max_output_retries and _max_tool_retries.
        assert research_agent._max_output_retries == 2

    def test_tool_count(self) -> None:
        """research_agent has exactly 6 registered tools."""
        tools = research_agent._function_toolset.tools
        assert len(tools) == 6

    def test_tool_names(self) -> None:
        """All 6 expected tool names are registered."""
        expected = {
            "fetch_filings",
            "get_financials",
            "get_price_data",
            "get_insider_activity",
            "get_sentiment",
            "get_macro_environment",
        }
        actual = set(research_agent._function_toolset.tools.keys())
        assert actual == expected

    def test_system_prompt_forbids_financial_figures(self) -> None:
        """System prompt template forbids LLM-generated financial numbers."""
        assert "NEVER state a financial figure" in RESEARCH_SYSTEM_PROMPT_TEMPLATE

    def test_system_prompt_injects_as_of_date(self) -> None:
        """System prompt template references the as_of_date placeholder."""
        assert "{as_of_date}" in RESEARCH_SYSTEM_PROMPT_TEMPLATE

    def test_system_prompt_references_required_tools(self) -> None:
        """System prompt mentions the mandatory data tools."""
        assert "get_financials" in RESEARCH_SYSTEM_PROMPT_TEMPLATE
        assert "get_price_data" in RESEARCH_SYSTEM_PROMPT_TEMPLATE


class TestResearchLimits:
    """Tests for get_research_limits()."""

    def test_returns_usage_limits(self) -> None:
        """get_research_limits returns a UsageLimits instance."""
        limits = get_research_limits()
        assert isinstance(limits, UsageLimits)

    def test_limits_match_analysis_tier(self) -> None:
        """Budget matches the ANALYSIS tier defaults (Sonnet)."""
        limits = get_research_limits()
        assert limits.input_tokens_limit == 50_000
        assert limits.output_tokens_limit == 8_000
        assert limits.total_tokens_limit == 58_000
