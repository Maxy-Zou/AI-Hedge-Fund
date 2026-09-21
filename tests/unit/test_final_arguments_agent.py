"""Tests for the Final Arguments agent, system prompt, limits, and format helper.

These tests verify final_arguments_agent wiring without making real LLM calls:
- final_arguments_agent is an Agent[None, FinalArguments] on
  ModelTier.REASONING with retries=2 and zero registered tools.
- FINAL_ARGUMENTS_SYSTEM_PROMPT requires non-empty closings on both sides
  with explicit citation counts (DEBATE-03 Act 4 enforcement).
- get_final_arguments_limits() applies output_override=8_000 per Pitfall 6.
- format_debate_for_final() formats (bull_case, bear_case, rebuttal) into
  the user prompt.
"""

from __future__ import annotations

import os

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.final_arguments import (
    FINAL_ARGUMENTS_SYSTEM_PROMPT,
    final_arguments_agent,
    format_debate_for_final,
    get_final_arguments_limits,
)
from ai_hedge_fund.agents.manager import manager_agent
from ai_hedge_fund.schemas.debate import FinalArguments


class TestFinalArgumentsAgent:
    """Tests for the final_arguments_agent Agent instance."""

    def test_agent_exists(self) -> None:
        """final_arguments_agent is a PydanticAI Agent instance."""
        assert isinstance(final_arguments_agent, Agent)

    def test_agent_uses_reasoning_tier(self) -> None:
        """final_arguments_agent uses the same REASONING-tier model as manager_agent."""
        assert final_arguments_agent.model.model_name == manager_agent.model.model_name

    def test_agent_output_type(self) -> None:
        """final_arguments_agent produces FinalArguments."""
        assert final_arguments_agent._output_type is FinalArguments

    def test_agent_has_retries(self) -> None:
        """final_arguments_agent is configured with retries=2 for output validation."""
        assert final_arguments_agent._max_output_retries == 2

    def test_agent_no_tools(self) -> None:
        """final_arguments_agent has zero registered tools."""
        tools = final_arguments_agent._function_toolset.tools
        assert len(tools) == 0


class TestFinalArgumentsSystemPrompt:
    """Tests for FINAL_ARGUMENTS_SYSTEM_PROMPT content requirements (DEBATE-03 Act 4)."""

    def test_prompt_requires_both_closings(self) -> None:
        """System prompt must name both bull_closing and bear_closing fields."""
        assert "bull_closing" in FINAL_ARGUMENTS_SYSTEM_PROMPT
        assert "bear_closing" in FINAL_ARGUMENTS_SYSTEM_PROMPT

    def test_prompt_requires_citation_counts(self) -> None:
        """System prompt must reference the citation_count fields."""
        assert "citation_count" in FINAL_ARGUMENTS_SYSTEM_PROMPT

    def test_prompt_forbids_new_evidence(self) -> None:
        """System prompt must forbid introducing new evidence in closings."""
        lower = FINAL_ARGUMENTS_SYSTEM_PROMPT.lower()
        assert (
            "not introduce new evidence" in lower
            or "do not introduce" in lower
        )


class TestFinalArgumentsLimits:
    """Tests for get_final_arguments_limits()."""

    def test_returns_usage_limits_instance(self) -> None:
        """get_final_arguments_limits returns a UsageLimits instance."""
        limits = get_final_arguments_limits()
        assert isinstance(limits, UsageLimits)

    def test_uses_output_override_8000(self) -> None:
        """Final arguments output_tokens_limit is overridden to 8_000 per Pitfall 6."""
        limits = get_final_arguments_limits()
        assert limits.output_tokens_limit == 8_000


class TestFormatDebateForFinal:
    """Tests for format_debate_for_final() helper."""

    def test_all_none(self) -> None:
        """All three inputs None yields a string with fallback markers."""
        result = format_debate_for_final(None, None, None)
        assert "BULL CASE" in result
        assert "BEAR CASE" in result
        assert "REBUTTAL" in result
        assert "None available" in result

    def test_partial(self) -> None:
        """Only bull present: bear and rebuttal show fallback."""
        bull_case = {"ticker": "AAPL", "headline": "bull view"}
        result = format_debate_for_final(bull_case, None, None)
        assert "bull view" in result
        assert "BEAR CASE" in result
        assert "REBUTTAL" in result
        assert "None available" in result

    def test_all_present(self) -> None:
        """All three sections present: three section headers and two dividers appear."""
        bull_case = {"ticker": "AAPL"}
        bear_case = {"ticker": "AAPL"}
        rebuttal = {"ticker": "AAPL"}
        result = format_debate_for_final(bull_case, bear_case, rebuttal)
        assert "BULL CASE" in result
        assert "BEAR CASE" in result
        assert "REBUTTAL" in result
        # 3 sections -> 2 dividers between them.
        assert result.count("\n\n---\n\n") == 2
