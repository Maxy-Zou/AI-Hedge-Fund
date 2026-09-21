"""Tests for the technical analyst agent: tool registration, system prompt, limits.

Verifies:
- technical_agent is Agent[ResearchDeps, TechnicalAnalysis] with ANALYSIS tier
- Exactly 1 tool: get_price_data
- System prompt forbids unsourced price pattern descriptions (T-04-02)
- get_technical_limits returns ANALYSIS tier UsageLimits
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.technical import (
    TECHNICAL_SYSTEM_PROMPT_TEMPLATE,
    get_technical_limits,
    technical_agent,
)
from ai_hedge_fund.schemas.agents import TechnicalAnalysis


class TestTechnicalAgent:
    """Tests for the technical_agent Agent instance."""

    def test_agent_exists(self) -> None:
        """technical_agent is a PydanticAI Agent instance."""
        assert isinstance(technical_agent, Agent)

    def test_agent_model(self) -> None:
        """technical_agent uses the ANALYSIS tier model (Sonnet)."""
        assert technical_agent.model.model_name == "claude-sonnet-4-6"

    def test_agent_output_type(self) -> None:
        """technical_agent produces TechnicalAnalysis."""
        assert technical_agent._output_type is TechnicalAnalysis

    def test_agent_has_retries(self) -> None:
        """technical_agent is configured with retries=2."""
        assert technical_agent._max_output_retries == 2

    def test_tool_count(self) -> None:
        """technical_agent has exactly 1 registered tool."""
        tools = technical_agent._function_toolset.tools
        assert len(tools) == 1

    def test_tool_names(self) -> None:
        """The only registered tool is get_price_data."""
        expected = {"get_price_data"}
        actual = set(technical_agent._function_toolset.tools.keys())
        assert actual == expected

    def test_no_cross_domain_tools(self) -> None:
        """technical_agent does NOT have fundamental or sentiment tools."""
        tool_names = set(technical_agent._function_toolset.tools.keys())
        assert "fetch_filings" not in tool_names
        assert "get_financials" not in tool_names
        assert "get_macro_environment" not in tool_names
        assert "get_sentiment" not in tool_names
        assert "get_insider_activity" not in tool_names

    def test_system_prompt_has_ticker_placeholder(self) -> None:
        """System prompt template references {ticker}."""
        assert "{ticker}" in TECHNICAL_SYSTEM_PROMPT_TEMPLATE

    def test_system_prompt_has_as_of_date_placeholder(self) -> None:
        """System prompt template references {as_of_date}."""
        assert "{as_of_date}" in TECHNICAL_SYSTEM_PROMPT_TEMPLATE

    def test_system_prompt_forbids_unsourced_price_patterns(self) -> None:
        """System prompt contains directive forbidding unsourced price patterns (T-04-02)."""
        assert "NEVER" in TECHNICAL_SYSTEM_PROMPT_TEMPLATE
        prompt_lower = TECHNICAL_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "price pattern" in prompt_lower or "chart formation" in prompt_lower

    def test_system_prompt_requires_source_tool_citation(self) -> None:
        """System prompt requires every metric to cite source_tool."""
        prompt_lower = TECHNICAL_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "source_tool" in prompt_lower


class TestTechnicalLimits:
    """Tests for get_technical_limits()."""

    def test_returns_usage_limits(self) -> None:
        """get_technical_limits returns a UsageLimits instance."""
        limits = get_technical_limits()
        assert isinstance(limits, UsageLimits)

    def test_limits_match_analysis_tier(self) -> None:
        """Budget matches the ANALYSIS tier defaults (Sonnet)."""
        limits = get_technical_limits()
        assert limits.input_tokens_limit == 50_000
        assert limits.output_tokens_limit == 8_000
        assert limits.total_tokens_limit == 58_000
