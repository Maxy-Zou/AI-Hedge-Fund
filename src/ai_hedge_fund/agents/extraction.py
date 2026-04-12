"""Haiku-routed extraction agent for financial data extraction.

Uses ModelTier.EXTRACTION (Claude Haiku) for fast, cheap extraction of
structured financial metrics from filing text. Output is validated against
ExtractionOutput schema.

The system prompt enforces tool-first rules: the agent extracts exact values
from source text and never estimates or calculates numbers.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import create_agent, get_usage_limits
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.agents import ExtractionOutput

EXTRACTION_SYSTEM_PROMPT = (
    "You are a financial data extraction specialist. "
    "Extract key financial metrics from the provided text. "
    "Return structured data with metric names and values. "
    "Focus on: revenue, net income, EPS, margins, growth rates, and debt levels. "
    "Always report the exact values from the source -- never estimate or calculate."
)

extraction_agent: Agent = create_agent(
    model_tier=ModelTier.EXTRACTION,
    output_type=ExtractionOutput,
    system_prompt=EXTRACTION_SYSTEM_PROMPT,
)


def get_extraction_limits() -> UsageLimits:
    """Return UsageLimits for the extraction tier (Haiku defaults)."""
    return get_usage_limits(ModelTier.EXTRACTION)
