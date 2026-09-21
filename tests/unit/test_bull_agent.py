"""Tests for the Bull Advocate agent, system prompt, limits, and format helper.

These tests verify the bull_agent's wiring without making real LLM calls:
- bull_agent is an Agent[None, BullCase] on ModelTier.REASONING with retries=2
  and zero registered tools (pure synthesis from analyst + thesis inputs).
- BULL_SYSTEM_PROMPT contains the DEBATE-01 enforcement language
  ("source_analyst" + "at least 3" / "minimum 3" / similar brevity language).
- get_bull_limits() returns REASONING-tier UsageLimits (Opus budget).
- format_analyst_evidence() formats a (reports, thesis) pair into the
  user prompt for the bull agent.
"""

from __future__ import annotations

import os

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.agents.bull import (
    BULL_SYSTEM_PROMPT,
    bull_agent,
    format_analyst_evidence,
    get_bull_limits,
)
from ai_hedge_fund.agents.manager import manager_agent
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.debate import BullCase


class TestBullAgent:
    """Tests for the bull_agent Agent instance."""

    def test_agent_exists(self) -> None:
        """bull_agent is a PydanticAI Agent instance."""
        assert isinstance(bull_agent, Agent)

    def test_agent_uses_reasoning_tier(self) -> None:
        """bull_agent uses the same REASONING-tier model as manager_agent.

        Robust to model-version bumps: we compare against manager_agent so
        the assertion tracks ModelTier.REASONING without hardcoding a string.
        """
        assert bull_agent.model.model_name == manager_agent.model.model_name

    def test_agent_output_type(self) -> None:
        """bull_agent produces BullCase."""
        assert bull_agent._output_type is BullCase

    def test_agent_has_retries(self) -> None:
        """bull_agent is configured with retries=2 for output validation."""
        assert bull_agent._max_output_retries == 2

    def test_agent_no_tools(self) -> None:
        """bull_agent has zero registered tools (pure synthesis agent)."""
        tools = bull_agent._function_toolset.tools
        assert len(tools) == 0


class TestBullSystemPrompt:
    """Tests for BULL_SYSTEM_PROMPT content requirements (DEBATE-01)."""

    def test_prompt_requires_source_analyst_citation(self) -> None:
        """System prompt must literally mention the 'source_analyst' field."""
        assert "source_analyst" in BULL_SYSTEM_PROMPT

    def test_prompt_forbids_vague_claims(self) -> None:
        """System prompt must require specific data or forbid vague claims."""
        prompt_lower = BULL_SYSTEM_PROMPT.lower()
        assert "vague" in prompt_lower or "specific" in prompt_lower

    def test_prompt_requires_minimum_claims(self) -> None:
        """System prompt must require at least 3 claims."""
        prompt_lower = BULL_SYSTEM_PROMPT.lower()
        assert "at least 3" in prompt_lower or "minimum 3" in prompt_lower

    def test_prompt_names_advocate_role(self) -> None:
        """System prompt must describe the agent as an advocate."""
        prompt_lower = BULL_SYSTEM_PROMPT.lower()
        assert "advocate" in prompt_lower or "advocating" in prompt_lower


class TestBullLimits:
    """Tests for get_bull_limits()."""

    def test_returns_usage_limits_instance(self) -> None:
        """get_bull_limits returns a UsageLimits instance."""
        limits = get_bull_limits()
        assert isinstance(limits, UsageLimits)

    def test_total_limit_matches_reasoning_tier(self) -> None:
        """Bull limits total_tokens_limit equals REASONING-tier default."""
        limits = get_bull_limits()
        reasoning_default = get_usage_limits(ModelTier.REASONING)
        assert limits.total_tokens_limit == reasoning_default.total_tokens_limit
        assert limits.input_tokens_limit == reasoning_default.input_tokens_limit
        assert limits.output_tokens_limit == reasoning_default.output_tokens_limit


class TestFormatAnalystEvidence:
    """Tests for format_analyst_evidence() helper."""

    def test_empty_reports_and_none_thesis(self) -> None:
        """Empty reports + thesis=None returns the 'no evidence' / 'no thesis' messages."""
        result = format_analyst_evidence([], None)
        assert "No analyst evidence" in result
        assert "No preliminary thesis" in result

    def test_empty_reports_with_thesis(self) -> None:
        """Empty reports + valid thesis shows the thesis JSON and the no-evidence msg."""
        thesis = {"ticker": "AAPL", "confidence": 60}
        result = format_analyst_evidence([], thesis)
        assert "AAPL" in result
        assert "60" in result
        assert "No analyst evidence" in result

    def test_single_report(self) -> None:
        """Single report appears with analyst name and analysis JSON."""
        reports = [
            {
                "analyst": "fundamental",
                "analysis": {"ticker": "AAPL", "confidence": 75},
                "tokens_used": 1000,
            }
        ]
        thesis = {"ticker": "AAPL", "confidence": 60}
        result = format_analyst_evidence(reports, thesis)
        assert "fundamental" in result.lower()
        assert "AAPL" in result
        assert "75" in result

    def test_multi_report_separator(self) -> None:
        """Divider '---' appears between preliminary-thesis and analyst-evidence sections."""
        reports = [
            {
                "analyst": "fundamental",
                "analysis": {"ticker": "AAPL"},
                "tokens_used": 1000,
            }
        ]
        thesis = {"ticker": "AAPL", "confidence": 60}
        result = format_analyst_evidence(reports, thesis)
        # Exactly one section divider between the two top-level sections.
        assert result.count("\n\n---\n\n") == 1

    def test_error_report_branch(self) -> None:
        """Report with an error key emits 'UNAVAILABLE' and the error message."""
        reports = [
            {
                "analyst": "technical",
                "error": "Budget exceeded",
                "tokens_used": 0,
            }
        ]
        thesis = {"ticker": "AAPL", "confidence": 60}
        result = format_analyst_evidence(reports, thesis)
        assert "UNAVAILABLE" in result or "unavailable" in result.lower()
        assert "Budget exceeded" in result

    def test_preliminary_thesis_label_present(self) -> None:
        """Output labels the thesis section as 'PRELIMINARY THESIS'."""
        thesis = {"ticker": "AAPL", "confidence": 60}
        result = format_analyst_evidence([], thesis)
        assert "PRELIMINARY THESIS" in result

    def test_analyst_evidence_label_present(self) -> None:
        """Output labels the reports section as 'ANALYST EVIDENCE'."""
        reports = [
            {
                "analyst": "fundamental",
                "analysis": {"ticker": "AAPL"},
                "tokens_used": 100,
            }
        ]
        thesis = {"ticker": "AAPL", "confidence": 60}
        result = format_analyst_evidence(reports, thesis)
        assert "ANALYST EVIDENCE" in result
