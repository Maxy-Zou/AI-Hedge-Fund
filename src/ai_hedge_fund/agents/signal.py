"""Signal generation agent -- converts a ThesisOutput dict into a trade signal.

The signal agent is intentionally lighter than the research agent:
    - No tools: it derives direction/conviction/sizing purely from the
      structured thesis passed in the prompt.
    - No dependencies: the thesis already contains every data point it
      needs, so ``deps_type=None`` (the default).
    - Same ANALYSIS tier as the research agent: signal synthesis is
      analytical work, not a simple extraction.

Threat mitigations:
    T-03-07: DoS -- ``UsageLimits`` via ``get_signal_limits`` on every run.
    T-03-08: Tampering -- the node that calls this agent returns new dicts
             and never mutates pipeline state.
    T-03-09: Tampering (thesis injection) -- accepted: thesis content was
             produced by the research agent and validated by Pydantic;
             signal output is also Pydantic-validated.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.agents import SignalOutput

SIGNAL_SYSTEM_PROMPT = (
    "You are a portfolio strategist converting an investment thesis into a trade signal.\n"
    "\n"
    "Given a thesis with bull case, bear case, confidence score, and risk factors, produce:\n"
    "1. direction: 'long' if the bull case dominates, 'short' if the bear case dominates, "
    "'neutral' if the cases are balanced or evidence is weak.\n"
    "2. conviction: 'high' if confidence >= 70, 'medium' if 40-69, 'low' if < 40.\n"
    "3. time_horizon: Estimate based on thesis catalysts (e.g., '3-6 months', "
    "'6-12 months').\n"
    "4. position_size_pct: Suggest allocation 1-10%. Higher conviction = larger position. "
    "Never exceed 10%.\n"
    "5. thesis_summary: One-paragraph summary of the key thesis points.\n"
    "\n"
    "Base your signal ONLY on the thesis data provided. Do not add analysis from outside "
    "the thesis.\n"
)


signal_agent: Agent[None, SignalOutput] = Agent(
    ModelTier.ANALYSIS.value,
    output_type=SignalOutput,
    system_prompt=SIGNAL_SYSTEM_PROMPT,
    retries=2,
)


def get_signal_limits() -> UsageLimits:
    """Return UsageLimits for the signal agent (ANALYSIS tier, Sonnet)."""
    return get_usage_limits(ModelTier.ANALYSIS)
