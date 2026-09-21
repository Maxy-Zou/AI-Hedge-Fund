"""Tests for the fundamental analyst agent: tool registration, system prompt, limits.

Verifies:
- fundamental_agent is Agent[ResearchDeps, FundamentalAnalysis] with ANALYSIS tier
- Exactly 3 tools: fetch_filings, get_financials, get_macro_environment
- System prompt requires filing citations and valuation metrics
- get_fundamental_limits returns ANALYSIS tier UsageLimits
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.fundamental import (
    FUNDAMENTAL_SYSTEM_PROMPT_TEMPLATE,
    fundamental_agent,
    get_fundamental_limits,
)
from ai_hedge_fund.schemas.agents import FundamentalAnalysis


class TestFundamentalAgent:
    """Tests for the fundamental_agent Agent instance."""

    def test_agent_exists(self) -> None:
        """fundamental_agent is a PydanticAI Agent instance."""
        assert isinstance(fundamental_agent, Agent)

    def test_agent_model(self) -> None:
        """fundamental_agent uses the ANALYSIS tier model (Sonnet)."""
        assert fundamental_agent.model.model_name == "claude-sonnet-4-6"

    def test_agent_output_type(self) -> None:
        """fundamental_agent produces FundamentalAnalysis."""
        assert fundamental_agent._output_type is FundamentalAnalysis

    def test_agent_has_retries(self) -> None:
        """fundamental_agent is configured with retries=2."""
        assert fundamental_agent._max_output_retries == 2

    def test_tool_count(self) -> None:
        """fundamental_agent has exactly 3 registered tools."""
        tools = fundamental_agent._function_toolset.tools
        assert len(tools) == 3

    def test_tool_names(self) -> None:
        """All 3 expected tool names are registered."""
        expected = {"fetch_filings", "get_financials", "get_macro_environment"}
        actual = set(fundamental_agent._function_toolset.tools.keys())
        assert actual == expected

    def test_no_cross_domain_tools(self) -> None:
        """fundamental_agent does NOT have sentiment or price tools."""
        tool_names = set(fundamental_agent._function_toolset.tools.keys())
        assert "get_sentiment" not in tool_names
        assert "get_insider_activity" not in tool_names
        assert "get_price_data" not in tool_names

    def test_system_prompt_has_ticker_placeholder(self) -> None:
        """System prompt template references {ticker}."""
        assert "{ticker}" in FUNDAMENTAL_SYSTEM_PROMPT_TEMPLATE

    def test_system_prompt_has_as_of_date_placeholder(self) -> None:
        """System prompt template references {as_of_date}."""
        assert "{as_of_date}" in FUNDAMENTAL_SYSTEM_PROMPT_TEMPLATE

    def test_system_prompt_requires_filing_citations(self) -> None:
        """System prompt requires filing citations."""
        prompt_lower = FUNDAMENTAL_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "filing" in prompt_lower

    def test_system_prompt_requires_valuation_metrics(self) -> None:
        """System prompt requires computed valuation metrics."""
        prompt_lower = FUNDAMENTAL_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "valuation" in prompt_lower or "metric" in prompt_lower


class TestFundamentalLimits:
    """Tests for get_fundamental_limits()."""

    def test_returns_usage_limits(self) -> None:
        """get_fundamental_limits returns a UsageLimits instance."""
        limits = get_fundamental_limits()
        assert isinstance(limits, UsageLimits)

    def test_limits_match_analysis_tier(self) -> None:
        """Budget matches the ANALYSIS tier defaults (Sonnet)."""
        limits = get_fundamental_limits()
        assert limits.input_tokens_limit == 50_000
        assert limits.output_tokens_limit == 8_000
        assert limits.total_tokens_limit == 58_000
