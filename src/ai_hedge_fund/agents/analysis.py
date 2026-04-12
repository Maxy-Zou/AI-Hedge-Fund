"""Sonnet-routed analysis agent for financial data analysis.

Uses ModelTier.ANALYSIS (Claude Sonnet) for deep analytical review of
extracted financial data. Output is validated against AnalysisOutput schema.

The system prompt enforces tool-first rules: the agent references numbers
from provided data and never generates financial numbers independently.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import create_agent, get_usage_limits
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.agents import AnalysisOutput

ANALYSIS_SYSTEM_PROMPT = (
    "You are a senior financial analyst. "
    "Analyze the provided financial data and produce an investment assessment. "
    "Identify key findings, risks, and opportunities. "
    "Support every claim with specific data points from the input. "
    "Never generate financial numbers -- only reference numbers from the provided data."
)

analysis_agent: Agent = create_agent(
    model_tier=ModelTier.ANALYSIS,
    output_type=AnalysisOutput,
    system_prompt=ANALYSIS_SYSTEM_PROMPT,
)


def get_analysis_limits() -> UsageLimits:
    """Return UsageLimits for the analysis tier (Sonnet defaults)."""
    return get_usage_limits(ModelTier.ANALYSIS)
