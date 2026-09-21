"""Tests for the Debate Synthesis agent, system prompt, limits, and format helper.

These tests verify debate_synthesis_agent wiring without making real LLM calls:
- debate_synthesis_agent is an Agent[None, DebateSynthesis] on
  ModelTier.REASONING with retries=2 and zero registered tools.
- DEBATE_SYNTHESIS_SYSTEM_PROMPT contains the Pitfall-3 re-evaluation
  mandate (DEBATE-04 success criterion 4 mitigation).
- get_debate_synthesis_limits() returns the DEFAULT REASONING-tier
  UsageLimits (no output_override) -- synthesis needs full output budget
  for revised_thesis + sub-scores + notes.
- format_debate_for_synthesis() formats all prior acts + pre_debate_confidence
  into the user prompt.
"""

from __future__ import annotations

import os

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.agents.debate_synthesis import (
    DEBATE_SYNTHESIS_SYSTEM_PROMPT,
    debate_synthesis_agent,
    format_debate_for_synthesis,
    get_debate_synthesis_limits,
)
from ai_hedge_fund.agents.manager import manager_agent
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.debate import DebateSynthesis


class TestDebateSynthesisAgent:
    """Tests for the debate_synthesis_agent Agent instance."""

    def test_agent_exists(self) -> None:
        """debate_synthesis_agent is a PydanticAI Agent instance."""
        assert isinstance(debate_synthesis_agent, Agent)

    def test_agent_uses_reasoning_tier(self) -> None:
        """debate_synthesis_agent uses the same REASONING-tier model as manager_agent."""
        assert debate_synthesis_agent.model.model_name == manager_agent.model.model_name

    def test_agent_output_type(self) -> None:
        """debate_synthesis_agent produces DebateSynthesis."""
        assert debate_synthesis_agent._output_type is DebateSynthesis

    def test_agent_has_retries(self) -> None:
        """debate_synthesis_agent is configured with retries=2 for output validation."""
        assert debate_synthesis_agent._max_output_retries == 2

    def test_agent_no_tools(self) -> None:
        """debate_synthesis_agent has zero registered tools."""
        tools = debate_synthesis_agent._function_toolset.tools
        assert len(tools) == 0


class TestDebateSynthesisSystemPrompt:
    """Tests for DEBATE_SYNTHESIS_SYSTEM_PROMPT content requirements."""

    def test_prompt_requires_reevaluation(self) -> None:
        """Prompt must contain the Pitfall-3 re-evaluation mandate.

        DEBATE-04 success criterion 4 depends on post_debate_confidence
        differing from pre_debate_confidence in at least 30% of runs --
        the prompt must explicitly forbid defaulting the post value to
        the pre value.
        """
        lower = DEBATE_SYNTHESIS_SYSTEM_PROMPT.lower()
        assert "re-evaluate" in lower or "do not default" in lower

    def test_prompt_names_sub_scores(self) -> None:
        """Prompt must reference all three sub-score fields by name."""
        assert "evidence_strength" in DEBATE_SYNTHESIS_SYSTEM_PROMPT
        assert "logical_consistency" in DEBATE_SYNTHESIS_SYSTEM_PROMPT
        assert "risk_coverage" in DEBATE_SYNTHESIS_SYSTEM_PROMPT

    def test_prompt_documents_placeholder_fields(self) -> None:
        """Prompt must tell the LLM that pre_debate_confidence / quality_score get overwritten.

        This stops the LLM from fighting the pipeline by treating the
        overwritten fields as authoritative.
        """
        assert "overwritten" in DEBATE_SYNTHESIS_SYSTEM_PROMPT.lower()

    def test_prompt_requires_revised_thesis(self) -> None:
        """Prompt must reference the revised_thesis field."""
        assert "revised_thesis" in DEBATE_SYNTHESIS_SYSTEM_PROMPT


class TestDebateSynthesisLimits:
    """Tests for get_debate_synthesis_limits()."""

    def test_returns_usage_limits_instance(self) -> None:
        """get_debate_synthesis_limits returns a UsageLimits instance."""
        limits = get_debate_synthesis_limits()
        assert isinstance(limits, UsageLimits)

    def test_uses_default_reasoning_cap(self) -> None:
        """Synthesis uses the REASONING-tier defaults -- no output_override.

        Synthesis emits a full ThesisOutput + three sub-scores + notes; it
        needs the default 16k output cap. Checking BOTH total_tokens_limit
        AND output_tokens_limit defends against an accidental
        output_override being applied to synthesis.
        """
        limits = get_debate_synthesis_limits()
        default = get_usage_limits(ModelTier.REASONING)
        assert limits.total_tokens_limit == default.total_tokens_limit
        assert limits.output_tokens_limit == default.output_tokens_limit


class TestFormatDebateForSynthesis:
    """Tests for format_debate_for_synthesis() helper."""

    def test_empty_state(self) -> None:
        """Empty state + pre=0: returns a string with 'None available' for each missing section."""
        result = format_debate_for_synthesis({}, 0)
        assert isinstance(result, str)
        assert result
        # Every section header appears, every body is the fallback.
        assert "PRE-DEBATE CONFIDENCE" in result
        assert "PRE-DEBATE THESIS" in result
        assert "BULL CASE" in result
        assert "BEAR CASE" in result
        assert "REBUTTAL" in result
        assert "FINAL ARGUMENTS" in result
        assert "None available" in result

    def test_full_state(self) -> None:
        """Full state + pre_debate_confidence=75: all 5 bodies present and 5 dividers."""
        state = {
            "thesis": {"ticker": "AAPL", "confidence": 70},
            "bull_case": {"ticker": "AAPL", "headline": "bull view"},
            "bear_case": {"ticker": "AAPL", "headline": "bear view"},
            "rebuttal": {"ticker": "AAPL"},
            "final_arguments": {"ticker": "AAPL"},
        }
        result = format_debate_for_synthesis(state, 75)
        # Section headers all present.
        for header in (
            "PRE-DEBATE CONFIDENCE",
            "PRE-DEBATE THESIS",
            "BULL CASE",
            "BEAR CASE",
            "REBUTTAL",
            "FINAL ARGUMENTS",
        ):
            assert header in result
        # 6 sections -> 5 dividers between them.
        assert result.count("\n\n---\n\n") == 5
        # The pre_debate_confidence integer must appear.
        assert "75" in result
        # Non-fallback content appears.
        assert "bull view" in result
        assert "bear view" in result

    def test_pre_confidence_appears_in_output(self) -> None:
        """Passing pre_debate_confidence=42 causes '42' to appear in the prompt."""
        result = format_debate_for_synthesis({}, 42)
        assert "42" in result

    def test_missing_key_in_state(self) -> None:
        """State with only thesis present: other sections show fallback."""
        state = {"thesis": {"ticker": "AAPL", "confidence": 60}}
        result = format_debate_for_synthesis(state, 60)
        # thesis content present
        assert "AAPL" in result
        # missing sections show the fallback
        assert "None available" in result
