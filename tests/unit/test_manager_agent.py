"""Tests for the Research Manager agent, system prompt, limits, and format helper.

These tests verify manager agent wiring without making real LLM calls:
- manager_agent is an Agent[None, ThesisOutput] on ModelTier.REASONING with
  retries=2 and zero registered tools (pure synthesis from analyst reports).
- MANAGER_SYSTEM_PROMPT requires agreement identification, conflict
  identification, and resolution rationale (not concatenation).
- get_manager_limits() returns REASONING-tier UsageLimits (Opus budget).
- format_analyst_reports() converts analyst report dicts to readable text
  for the manager's user prompt.
"""

from __future__ import annotations

import os

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.manager import (
    MANAGER_SYSTEM_PROMPT,
    format_analyst_reports,
    get_manager_limits,
    manager_agent,
)
from ai_hedge_fund.schemas.agents import ThesisOutput


class TestManagerAgent:
    """Tests for the manager_agent Agent instance."""

    def test_agent_exists(self) -> None:
        """manager_agent is a PydanticAI Agent instance."""
        assert isinstance(manager_agent, Agent)

    def test_agent_model(self) -> None:
        """manager_agent uses the REASONING tier model (Opus)."""
        assert manager_agent.model.model_name == "claude-opus-4-6"

    def test_agent_output_type(self) -> None:
        """manager_agent produces ThesisOutput."""
        assert manager_agent._output_type is ThesisOutput

    def test_agent_has_retries(self) -> None:
        """manager_agent is configured with retries=2 for output validation."""
        assert manager_agent._max_result_retries == 2

    def test_agent_no_tools(self) -> None:
        """manager_agent has zero registered tools (pure synthesis agent)."""
        tools = manager_agent._function_toolset.tools
        assert len(tools) == 0


class TestManagerSystemPrompt:
    """Tests for MANAGER_SYSTEM_PROMPT content requirements."""

    def test_prompt_requires_agreement_identification(self) -> None:
        """System prompt must require identifying where analysts agree."""
        prompt_lower = MANAGER_SYSTEM_PROMPT.lower()
        assert "agree" in prompt_lower

    def test_prompt_requires_conflict_identification(self) -> None:
        """System prompt must require identifying where analysts conflict."""
        prompt_lower = MANAGER_SYSTEM_PROMPT.lower()
        assert "conflict" in prompt_lower

    def test_prompt_requires_resolution_rationale(self) -> None:
        """System prompt must require explaining conflict resolution."""
        prompt_lower = MANAGER_SYSTEM_PROMPT.lower()
        assert "resolv" in prompt_lower or "resolution" in prompt_lower

    def test_prompt_names_fundamental_analyst(self) -> None:
        """System prompt must reference the Fundamental analyst domain."""
        assert "Fundamental" in MANAGER_SYSTEM_PROMPT

    def test_prompt_names_sentiment_analyst(self) -> None:
        """System prompt must reference the Sentiment analyst domain."""
        assert "Sentiment" in MANAGER_SYSTEM_PROMPT

    def test_prompt_names_technical_analyst(self) -> None:
        """System prompt must reference the Technical analyst domain."""
        assert "Technical" in MANAGER_SYSTEM_PROMPT


class TestManagerLimits:
    """Tests for get_manager_limits()."""

    def test_returns_usage_limits(self) -> None:
        """get_manager_limits returns a UsageLimits instance."""
        limits = get_manager_limits()
        assert isinstance(limits, UsageLimits)

    def test_limits_match_reasoning_tier(self) -> None:
        """Budget matches the REASONING tier defaults (Opus)."""
        limits = get_manager_limits()
        assert limits.input_tokens_limit == 100_000
        assert limits.output_tokens_limit == 16_000
        assert limits.total_tokens_limit == 116_000


class TestFormatAnalystReports:
    """Tests for format_analyst_reports() helper."""

    def test_empty_reports(self) -> None:
        """Empty list returns an informative 'no reports' message."""
        result = format_analyst_reports([])
        assert "no" in result.lower() or "No" in result

    def test_single_report_includes_analyst_name(self) -> None:
        """Single report includes the analyst name in the formatted output."""
        reports = [
            {
                "analyst": "fundamental",
                "analysis": {"ticker": "AAPL", "confidence": 75},
                "tokens_used": 1000,
            }
        ]
        result = format_analyst_reports(reports)
        assert "fundamental" in result.lower()

    def test_single_report_includes_analysis_content(self) -> None:
        """Single report includes the analysis dict content in the output."""
        reports = [
            {
                "analyst": "fundamental",
                "analysis": {"ticker": "AAPL", "confidence": 75},
                "tokens_used": 1000,
            }
        ]
        result = format_analyst_reports(reports)
        assert "AAPL" in result
        assert "75" in result

    def test_multiple_reports_separated(self) -> None:
        """Multiple reports are separated by a divider."""
        reports = [
            {
                "analyst": "fundamental",
                "analysis": {"ticker": "AAPL"},
                "tokens_used": 1000,
            },
            {
                "analyst": "sentiment",
                "analysis": {"ticker": "AAPL"},
                "tokens_used": 800,
            },
        ]
        result = format_analyst_reports(reports)
        assert "fundamental" in result.lower()
        assert "sentiment" in result.lower()
        assert "---" in result

    def test_error_report_includes_error_message(self) -> None:
        """Report with an error key formats as unavailable with the error."""
        reports = [
            {
                "analyst": "technical",
                "error": "Budget exceeded: 58000 tokens used",
                "tokens_used": 0,
            }
        ]
        result = format_analyst_reports(reports)
        assert "technical" in result.lower()
        assert "unavailable" in result.lower() or "UNAVAILABLE" in result
        assert "Budget exceeded" in result

    def test_mixed_success_and_error_reports(self) -> None:
        """Mix of successful and error reports formats correctly."""
        reports = [
            {
                "analyst": "fundamental",
                "analysis": {"ticker": "AAPL", "confidence": 80},
                "tokens_used": 2000,
            },
            {
                "analyst": "sentiment",
                "error": "API timeout",
                "tokens_used": 0,
            },
            {
                "analyst": "technical",
                "analysis": {"ticker": "AAPL", "momentum": "bullish"},
                "tokens_used": 1500,
            },
        ]
        result = format_analyst_reports(reports)
        assert "fundamental" in result.lower()
        assert "sentiment" in result.lower()
        assert "technical" in result.lower()
        assert "API timeout" in result
        assert "AAPL" in result
