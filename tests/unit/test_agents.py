"""Tests for agent factory creation and configuration.

Tests verify:
- create_agent returns PydanticAI Agent with correct model tier
- create_agent sets output_type to provided BaseModel subclass
- create_agent sets system_prompt on returned Agent
- get_usage_limits returns correct UsageLimits per tier
- get_usage_limits supports custom overrides
"""

from __future__ import annotations

import os

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

# Set dummy API key before importing agents (PydanticAI validates at construction)
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from ai_hedge_fund.agents.base import create_agent, get_usage_limits
from ai_hedge_fund.models import ModelTier


class _TestOutput(BaseModel):
    """Minimal output schema for factory tests."""

    name: str


class TestCreateAgentExtraction:
    """Test create_agent with EXTRACTION tier."""

    def test_returns_agent_instance(self) -> None:
        agent = create_agent(
            model_tier=ModelTier.EXTRACTION,
            output_type=_TestOutput,
            system_prompt="Test prompt",
        )
        assert isinstance(agent, Agent)

    def test_model_string_matches_extraction_tier(self) -> None:
        agent = create_agent(
            model_tier=ModelTier.EXTRACTION,
            output_type=_TestOutput,
            system_prompt="Test prompt",
        )
        assert agent.model.model_name == "claude-haiku-4-5"

    def test_output_type_is_set(self) -> None:
        agent = create_agent(
            model_tier=ModelTier.EXTRACTION,
            output_type=_TestOutput,
            system_prompt="Test prompt",
        )
        assert agent._output_type is _TestOutput


class TestCreateAgentAnalysis:
    """Test create_agent with ANALYSIS tier."""

    def test_returns_agent_instance(self) -> None:
        agent = create_agent(
            model_tier=ModelTier.ANALYSIS,
            output_type=_TestOutput,
            system_prompt="Analyze this",
        )
        assert isinstance(agent, Agent)

    def test_model_string_matches_analysis_tier(self) -> None:
        agent = create_agent(
            model_tier=ModelTier.ANALYSIS,
            output_type=_TestOutput,
            system_prompt="Analyze this",
        )
        assert agent.model.model_name == "claude-sonnet-4-6"


class TestCreateAgentSystemPrompt:
    """Test create_agent sets system_prompt on the Agent."""

    def test_system_prompt_is_set(self) -> None:
        prompt = "You are a financial extraction specialist."
        agent = create_agent(
            model_tier=ModelTier.EXTRACTION,
            output_type=_TestOutput,
            system_prompt=prompt,
        )
        assert prompt in agent._system_prompts


class TestGetUsageLimitsExtraction:
    """Test get_usage_limits for EXTRACTION tier."""

    def test_returns_usage_limits_instance(self) -> None:
        limits = get_usage_limits(ModelTier.EXTRACTION)
        assert isinstance(limits, UsageLimits)

    def test_extraction_input_tokens(self) -> None:
        limits = get_usage_limits(ModelTier.EXTRACTION)
        assert limits.input_tokens_limit == 20_000

    def test_extraction_output_tokens(self) -> None:
        limits = get_usage_limits(ModelTier.EXTRACTION)
        assert limits.output_tokens_limit == 2_000


class TestGetUsageLimitsAnalysis:
    """Test get_usage_limits for ANALYSIS tier."""

    def test_analysis_input_tokens(self) -> None:
        limits = get_usage_limits(ModelTier.ANALYSIS)
        assert limits.input_tokens_limit == 50_000

    def test_analysis_output_tokens(self) -> None:
        limits = get_usage_limits(ModelTier.ANALYSIS)
        assert limits.output_tokens_limit == 8_000


class TestGetUsageLimitsOverrides:
    """Test get_usage_limits with custom overrides."""

    def test_input_override(self) -> None:
        limits = get_usage_limits(ModelTier.EXTRACTION, input_override=30_000)
        assert limits.input_tokens_limit == 30_000
        # Other fields still default
        assert limits.output_tokens_limit == 2_000

    def test_output_override(self) -> None:
        limits = get_usage_limits(ModelTier.EXTRACTION, output_override=5_000)
        assert limits.output_tokens_limit == 5_000
        assert limits.input_tokens_limit == 20_000

    def test_total_override(self) -> None:
        limits = get_usage_limits(ModelTier.EXTRACTION, total_override=99_999)
        assert limits.total_tokens_limit == 99_999
