"""Tests for the Bear Advocate agent, system prompt, limits, and format helper.

These tests verify the bear_agent's wiring without making real LLM calls:
- bear_agent is an Agent[None, BearCase] on ModelTier.REASONING with retries=2
  and zero registered tools.
- BEAR_SYSTEM_PROMPT contains the DEBATE-02 enforcement language --
  specifically both "addressed_bull_claims" AND "at least 2".
- get_bear_limits() returns REASONING-tier UsageLimits (Opus budget).
- format_bull_case_for_bear() emits bull claims as a numbered list so the
  bear agent can quote them verbatim into addressed_bull_claims.
"""

from __future__ import annotations

import os

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.agents.bear import (
    BEAR_SYSTEM_PROMPT,
    bear_agent,
    format_bull_case_for_bear,
    get_bear_limits,
)
from ai_hedge_fund.agents.manager import manager_agent
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.debate import BearCase


class TestBearAgent:
    """Tests for the bear_agent Agent instance."""

    def test_agent_exists(self) -> None:
        """bear_agent is a PydanticAI Agent instance."""
        assert isinstance(bear_agent, Agent)

    def test_agent_uses_reasoning_tier(self) -> None:
        """bear_agent uses the same REASONING-tier model as manager_agent."""
        assert bear_agent.model.model_name == manager_agent.model.model_name

    def test_agent_output_type(self) -> None:
        """bear_agent produces BearCase."""
        assert bear_agent._output_type is BearCase

    def test_agent_has_retries(self) -> None:
        """bear_agent is configured with retries=2 for output validation."""
        assert bear_agent._max_result_retries == 2

    def test_agent_no_tools(self) -> None:
        """bear_agent has zero registered tools (pure synthesis agent)."""
        tools = bear_agent._function_toolset.tools
        assert len(tools) == 0


class TestBearSystemPrompt:
    """Tests for BEAR_SYSTEM_PROMPT content requirements (DEBATE-02)."""

    def test_prompt_requires_addressing_two_bull_claims(self) -> None:
        """System prompt must contain BOTH 'addressed_bull_claims' AND 'at least 2'.

        This is the textual enforcement of DEBATE-02 -- the bear must be told
        (at the prompt level) that the field exists and the minimum count it
        has to carry, so Pydantic's min_length=2 schema rejection has a chance
        to self-correct during the retries=2 loop.
        """
        assert "addressed_bull_claims" in BEAR_SYSTEM_PROMPT
        assert "at least 2" in BEAR_SYSTEM_PROMPT.lower()

    def test_prompt_requires_source_analyst_citation(self) -> None:
        """System prompt must require source_analyst citations on every claim."""
        assert "source_analyst" in BEAR_SYSTEM_PROMPT

    def test_prompt_forbids_vague_claims(self) -> None:
        """System prompt must require specific data or forbid vague claims."""
        prompt_lower = BEAR_SYSTEM_PROMPT.lower()
        assert "vague" in prompt_lower or "specific" in prompt_lower

    def test_prompt_names_advocate_role(self) -> None:
        """System prompt describes the agent as an advocate (not a synthesizer)."""
        prompt_lower = BEAR_SYSTEM_PROMPT.lower()
        assert "advocate" in prompt_lower or "advocating" in prompt_lower


class TestBearLimits:
    """Tests for get_bear_limits()."""

    def test_returns_usage_limits_instance(self) -> None:
        """get_bear_limits returns a UsageLimits instance."""
        limits = get_bear_limits()
        assert isinstance(limits, UsageLimits)

    def test_total_limit_matches_reasoning_tier(self) -> None:
        """Bear limits match REASONING-tier defaults across all three caps."""
        limits = get_bear_limits()
        reasoning_default = get_usage_limits(ModelTier.REASONING)
        assert limits.total_tokens_limit == reasoning_default.total_tokens_limit
        assert limits.input_tokens_limit == reasoning_default.input_tokens_limit
        assert limits.output_tokens_limit == reasoning_default.output_tokens_limit


class TestFormatBullCaseForBear:
    """Tests for format_bull_case_for_bear() helper."""

    def test_empty_claims(self) -> None:
        """Bull case with empty claims list returns the no-case message."""
        bull_case = {"ticker": "AAPL", "claims": [], "headline": "h"}
        result = format_bull_case_for_bear(bull_case)
        assert result == "No bull case provided."

    def test_none_input(self) -> None:
        """None input returns the no-case message."""
        result = format_bull_case_for_bear(None)
        assert result == "No bull case provided."

    def test_numbered_list_format(self) -> None:
        """Claims are emitted as a numbered list starting at 1."""
        bull_case = {
            "ticker": "AAPL",
            "claims": [
                {
                    "claim": "Revenue growing",
                    "evidence": "FY23 10-K",
                    "source_analyst": "fundamental",
                },
                {
                    "claim": "Momentum positive",
                    "evidence": "RSI 65",
                    "source_analyst": "technical",
                },
            ],
            "headline": "Apple is a buy",
        }
        result = format_bull_case_for_bear(bull_case)
        assert "1. " in result
        assert "2. " in result

    def test_includes_source_analyst(self) -> None:
        """Claims include source_analyst in a bracketed prefix."""
        bull_case = {
            "ticker": "AAPL",
            "claims": [
                {
                    "claim": "Revenue growing",
                    "evidence": "FY23 10-K",
                    "source_analyst": "fundamental",
                }
            ],
            "headline": "h",
        }
        result = format_bull_case_for_bear(bull_case)
        assert "[fundamental]" in result

    def test_includes_headline_line(self) -> None:
        """Output contains a 'HEADLINE:' line for the bull headline."""
        bull_case = {
            "ticker": "AAPL",
            "claims": [
                {
                    "claim": "c",
                    "evidence": "e",
                    "source_analyst": "fundamental",
                }
            ],
            "headline": "Apple is a buy",
        }
        result = format_bull_case_for_bear(bull_case)
        assert "HEADLINE:" in result
        assert "Apple is a buy" in result

    def test_includes_bull_case_label(self) -> None:
        """Output begins with 'BULL CASE TO REBUT:'."""
        bull_case = {
            "ticker": "AAPL",
            "claims": [
                {
                    "claim": "c",
                    "evidence": "e",
                    "source_analyst": "fundamental",
                }
            ],
            "headline": "h",
        }
        result = format_bull_case_for_bear(bull_case)
        assert result.startswith("BULL CASE TO REBUT:")

    def test_claim_text_and_evidence_in_output(self) -> None:
        """Both claim text and evidence text appear in formatted output."""
        bull_case = {
            "ticker": "AAPL",
            "claims": [
                {
                    "claim": "Revenue grew 20% YoY",
                    "evidence": "FY23 10-K income statement",
                    "source_analyst": "fundamental",
                }
            ],
            "headline": "h",
        }
        result = format_bull_case_for_bear(bull_case)
        assert "Revenue grew 20% YoY" in result
        assert "FY23 10-K income statement" in result
