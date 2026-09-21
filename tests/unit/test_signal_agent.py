"""Tests for the signal agent, its usage limits, and ResearchPipelineState.

These tests verify the signal agent wiring without making real LLM calls:
- signal_agent is an Agent[None, SignalOutput] on ModelTier.ANALYSIS with
  retries=2 and no registered tools (derives signal from the provided thesis,
  not from external data).
- get_signal_limits() returns ANALYSIS-tier UsageLimits (same budget as the
  research agent since signal generation is a similar synthesis task).
- ResearchPipelineState is a TypedDict with the required ticker/as_of_date
  fields plus optional thesis/signal/error slots.
"""

from __future__ import annotations

import os
from typing import get_type_hints

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.signal import (
    SIGNAL_SYSTEM_PROMPT,
    get_signal_limits,
    signal_agent,
)
from ai_hedge_fund.schemas.agents import SignalOutput
from ai_hedge_fund.schemas.state import ResearchPipelineState


class TestSignalAgent:
    """Tests for the signal_agent Agent instance."""

    def test_agent_exists(self) -> None:
        """signal_agent is a PydanticAI Agent instance."""
        assert isinstance(signal_agent, Agent)

    def test_agent_model(self) -> None:
        """signal_agent uses the ANALYSIS tier model (Sonnet)."""
        assert signal_agent.model.model_name == "claude-sonnet-4-6"

    def test_agent_output_type(self) -> None:
        """signal_agent produces SignalOutput."""
        assert signal_agent._output_type is SignalOutput

    def test_agent_has_retries(self) -> None:
        """signal_agent is configured with retries=2 for output validation."""
        assert signal_agent._max_output_retries == 2

    def test_agent_no_tools(self) -> None:
        """signal_agent has zero registered tools (derives signal from thesis only)."""
        tools = signal_agent._function_toolset.tools
        assert len(tools) == 0

    def test_system_prompt_mentions_direction_options(self) -> None:
        """System prompt lists the allowed signal directions."""
        assert "long" in SIGNAL_SYSTEM_PROMPT
        assert "short" in SIGNAL_SYSTEM_PROMPT
        assert "neutral" in SIGNAL_SYSTEM_PROMPT

    def test_system_prompt_mentions_conviction_levels(self) -> None:
        """System prompt lists the allowed conviction levels."""
        assert "high" in SIGNAL_SYSTEM_PROMPT
        assert "medium" in SIGNAL_SYSTEM_PROMPT
        assert "low" in SIGNAL_SYSTEM_PROMPT

    def test_system_prompt_forbids_outside_analysis(self) -> None:
        """System prompt restricts the agent to the thesis data provided."""
        # Slight normalization: allow any casing that conveys "only"/"only the thesis".
        prompt_lower = SIGNAL_SYSTEM_PROMPT.lower()
        assert "only" in prompt_lower and "thesis" in prompt_lower


class TestSignalLimits:
    """Tests for get_signal_limits()."""

    def test_returns_usage_limits(self) -> None:
        """get_signal_limits returns a UsageLimits instance."""
        limits = get_signal_limits()
        assert isinstance(limits, UsageLimits)

    def test_limits_match_analysis_tier(self) -> None:
        """Budget matches the ANALYSIS tier defaults (Sonnet)."""
        limits = get_signal_limits()
        assert limits.input_tokens_limit == 50_000
        assert limits.output_tokens_limit == 8_000
        assert limits.total_tokens_limit == 58_000


class TestResearchPipelineState:
    """Tests for the ResearchPipelineState TypedDict."""

    def test_instantiate_minimal(self) -> None:
        """ResearchPipelineState accepts the required ticker + as_of_date."""
        state: ResearchPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-01",
        }
        assert state["ticker"] == "AAPL"
        assert state["as_of_date"] == "2024-01-01"

    def test_instantiate_full(self) -> None:
        """ResearchPipelineState accepts every documented field."""
        thesis_dict: dict = {
            "ticker": "AAPL",
            "bull_case": [],
            "bear_case": [],
            "confidence": 50,
            "risk_factors": [],
        }
        signal_dict: dict = {
            "ticker": "AAPL",
            "direction": "long",
            "conviction": "medium",
            "time_horizon": "3-6 months",
            "position_size_pct": 5.0,
            "thesis_summary": "...",
        }
        state: ResearchPipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-01",
            "thesis": thesis_dict,
            "signal": signal_dict,
            "error": None,
        }
        assert state["thesis"] == thesis_dict
        assert state["signal"] == signal_dict
        assert state["error"] is None

    def test_thesis_defaults_to_absent(self) -> None:
        """Only ticker + as_of_date are required; other keys can be missing (total=False)."""
        state: ResearchPipelineState = {
            "ticker": "MSFT",
            "as_of_date": "2024-06-30",
        }
        # Missing keys should not raise; TypedDict w/ total=False permits absence.
        assert "thesis" not in state
        assert "signal" not in state
        assert "error" not in state

    def test_has_expected_keys(self) -> None:
        """Type hints expose the expected field set on ResearchPipelineState."""
        hints = get_type_hints(ResearchPipelineState, include_extras=False)
        expected = {"ticker", "as_of_date", "thesis", "signal", "error"}
        assert expected.issubset(hints.keys())

    def test_does_not_have_raw_text(self) -> None:
        """ResearchPipelineState must NOT inherit the legacy raw_text field."""
        hints = get_type_hints(ResearchPipelineState, include_extras=False)
        assert "raw_text" not in hints
