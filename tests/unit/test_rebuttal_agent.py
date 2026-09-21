"""Tests for the Rebuttal agent, system prompt, limits, and format helper.

These tests verify rebuttal_agent wiring without making real LLM calls:
- rebuttal_agent is an Agent[None, RebuttalAct] on ModelTier.REASONING with
  retries=2 and zero registered tools.
- REBUTTAL_SYSTEM_PROMPT requires both bull_rebuttals and bear_rebuttals with
  a minimum of 2 per side (DEBATE-03 Act 3 enforcement).
- get_rebuttal_limits() returns REASONING-tier UsageLimits with
  output_override=8_000 (Pitfall-6 cost mitigation).
- format_debate_for_rebuttal() formats (bull_case, bear_case) into the user
  prompt for the rebuttal agent.
"""

from __future__ import annotations

import os

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.manager import manager_agent
from ai_hedge_fund.agents.rebuttal import (
    REBUTTAL_SYSTEM_PROMPT,
    format_debate_for_rebuttal,
    get_rebuttal_limits,
    rebuttal_agent,
)
from ai_hedge_fund.schemas.debate import RebuttalAct


class TestRebuttalAgent:
    """Tests for the rebuttal_agent Agent instance."""

    def test_agent_exists(self) -> None:
        """rebuttal_agent is a PydanticAI Agent instance."""
        assert isinstance(rebuttal_agent, Agent)

    def test_agent_uses_reasoning_tier(self) -> None:
        """rebuttal_agent uses the same REASONING-tier model as manager_agent."""
        assert rebuttal_agent.model.model_name == manager_agent.model.model_name

    def test_agent_output_type(self) -> None:
        """rebuttal_agent produces RebuttalAct."""
        assert rebuttal_agent._output_type is RebuttalAct

    def test_agent_has_retries(self) -> None:
        """rebuttal_agent is configured with retries=2 for output validation."""
        assert rebuttal_agent._max_output_retries == 2

    def test_agent_no_tools(self) -> None:
        """rebuttal_agent has zero registered tools (pure synthesis agent)."""
        tools = rebuttal_agent._function_toolset.tools
        assert len(tools) == 0


class TestRebuttalSystemPrompt:
    """Tests for REBUTTAL_SYSTEM_PROMPT content requirements (DEBATE-03 Act 3)."""

    def test_prompt_requires_both_sides(self) -> None:
        """System prompt must name both bull_rebuttals and bear_rebuttals fields."""
        assert "bull_rebuttals" in REBUTTAL_SYSTEM_PROMPT
        assert "bear_rebuttals" in REBUTTAL_SYSTEM_PROMPT

    def test_prompt_requires_minimum_two_per_side(self) -> None:
        """System prompt must require at least 2 rebuttals per side."""
        assert "at least 2" in REBUTTAL_SYSTEM_PROMPT.lower()

    def test_prompt_requires_source_analyst(self) -> None:
        """System prompt must require source_analyst citation on every rebuttal."""
        assert "source_analyst" in REBUTTAL_SYSTEM_PROMPT

    def test_prompt_requires_targets_claim(self) -> None:
        """System prompt must require the targets_claim field on each rebuttal."""
        assert "targets_claim" in REBUTTAL_SYSTEM_PROMPT


class TestRebuttalLimits:
    """Tests for get_rebuttal_limits()."""

    def test_returns_usage_limits_instance(self) -> None:
        """get_rebuttal_limits returns a UsageLimits instance."""
        limits = get_rebuttal_limits()
        assert isinstance(limits, UsageLimits)

    def test_uses_output_override_8000(self) -> None:
        """Rebuttal output_tokens_limit is overridden to 8_000 per Pitfall-6 cost mitigation."""
        limits = get_rebuttal_limits()
        assert limits.output_tokens_limit == 8_000


class TestFormatDebateForRebuttal:
    """Tests for format_debate_for_rebuttal() helper."""

    def test_both_none(self) -> None:
        """None on both sides yields graceful fallback strings."""
        result = format_debate_for_rebuttal(None, None)
        assert "BULL CASE" in result
        assert "BEAR CASE" in result
        assert "None available" in result

    def test_bull_only(self) -> None:
        """Only bull present: bear section shows fallback."""
        bull_case = {"ticker": "AAPL", "claims": [{"claim": "x"}]}
        result = format_debate_for_rebuttal(bull_case, None)
        assert "AAPL" in result
        assert "BEAR CASE" in result
        assert "None available" in result

    def test_bear_only(self) -> None:
        """Only bear present: bull section shows fallback."""
        bear_case = {"ticker": "AAPL", "claims": [{"claim": "y"}]}
        result = format_debate_for_rebuttal(None, bear_case)
        assert "AAPL" in result
        assert "BULL CASE" in result
        assert "None available" in result

    def test_both_present(self) -> None:
        """Both cases present: both section headers and both contents appear."""
        bull_case = {"ticker": "AAPL", "headline": "bull view"}
        bear_case = {"ticker": "AAPL", "headline": "bear view"}
        result = format_debate_for_rebuttal(bull_case, bear_case)
        assert "BULL CASE" in result
        assert "BEAR CASE" in result
        assert "bull view" in result
        assert "bear view" in result

    def test_separator_appears_once(self) -> None:
        """Divider '---' appears exactly once between the two sections."""
        bull_case = {"ticker": "AAPL"}
        bear_case = {"ticker": "AAPL"}
        result = format_debate_for_rebuttal(bull_case, bear_case)
        assert result.count("\n\n---\n\n") == 1
