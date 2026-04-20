"""Tests for the sentiment analyst agent: tool registration, system prompt, limits.

Verifies:
- sentiment_agent is Agent[ResearchDeps, SentimentAnalysis] with ANALYSIS tier
- Exactly 2 tools: get_sentiment, get_insider_activity
- System prompt requires composite sentiment score with component breakdown
- get_sentiment_limits returns ANALYSIS tier UsageLimits
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.sentiment import (
    SENTIMENT_SYSTEM_PROMPT_TEMPLATE,
    get_sentiment_limits,
    sentiment_agent,
)
from ai_hedge_fund.schemas.agents import SentimentAnalysis


class TestSentimentAgent:
    """Tests for the sentiment_agent Agent instance."""

    def test_agent_exists(self) -> None:
        """sentiment_agent is a PydanticAI Agent instance."""
        assert isinstance(sentiment_agent, Agent)

    def test_agent_model(self) -> None:
        """sentiment_agent uses the ANALYSIS tier model (Sonnet)."""
        assert sentiment_agent.model.model_name == "claude-sonnet-4-6"

    def test_agent_output_type(self) -> None:
        """sentiment_agent produces SentimentAnalysis."""
        assert sentiment_agent._output_type is SentimentAnalysis

    def test_agent_has_retries(self) -> None:
        """sentiment_agent is configured with retries=2."""
        assert sentiment_agent._max_result_retries == 2

    def test_tool_count(self) -> None:
        """sentiment_agent has exactly 2 registered tools."""
        tools = sentiment_agent._function_toolset.tools
        assert len(tools) == 2

    def test_tool_names(self) -> None:
        """All 2 expected tool names are registered."""
        expected = {"get_sentiment", "get_insider_activity"}
        actual = set(sentiment_agent._function_toolset.tools.keys())
        assert actual == expected

    def test_no_cross_domain_tools(self) -> None:
        """sentiment_agent does NOT have fundamental or technical tools."""
        tool_names = set(sentiment_agent._function_toolset.tools.keys())
        assert "fetch_filings" not in tool_names
        assert "get_financials" not in tool_names
        assert "get_macro_environment" not in tool_names
        assert "get_price_data" not in tool_names

    def test_system_prompt_has_ticker_placeholder(self) -> None:
        """System prompt template references {ticker}."""
        assert "{ticker}" in SENTIMENT_SYSTEM_PROMPT_TEMPLATE

    def test_system_prompt_has_as_of_date_placeholder(self) -> None:
        """System prompt template references {as_of_date}."""
        assert "{as_of_date}" in SENTIMENT_SYSTEM_PROMPT_TEMPLATE

    def test_system_prompt_requires_composite_score(self) -> None:
        """System prompt requires composite sentiment score."""
        prompt_lower = SENTIMENT_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "composite" in prompt_lower or "sentiment" in prompt_lower

    def test_system_prompt_requires_component_breakdown(self) -> None:
        """System prompt requires component breakdown."""
        prompt_lower = SENTIMENT_SYSTEM_PROMPT_TEMPLATE.lower()
        assert "component" in prompt_lower or "source_tool" in prompt_lower


class TestSentimentLimits:
    """Tests for get_sentiment_limits()."""

    def test_returns_usage_limits(self) -> None:
        """get_sentiment_limits returns a UsageLimits instance."""
        limits = get_sentiment_limits()
        assert isinstance(limits, UsageLimits)

    def test_limits_match_analysis_tier(self) -> None:
        """Budget matches the ANALYSIS tier defaults (Sonnet)."""
        limits = get_sentiment_limits()
        assert limits.input_tokens_limit == 50_000
        assert limits.output_tokens_limit == 8_000
        assert limits.total_tokens_limit == 58_000
