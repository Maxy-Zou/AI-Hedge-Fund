"""Research Manager agent -- synthesizes analyst reports into a unified thesis.

The manager is a pure synthesis agent (no tools). It receives structured
analyst reports as part of its user prompt and produces a unified
ThesisOutput by identifying agreements, conflicts, and applying weighted
resolution. Uses REASONING tier (Opus) for complex multi-source synthesis.

Threat mitigations:
    T-04-06: Tampering (concatenation) -- system prompt explicitly requires
             conflict identification and resolution rationale; not a merge.
    T-04-07: DoS -- UsageLimits via get_manager_limits() on every run.
"""

from __future__ import annotations

import json

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.agents import ThesisOutput

MANAGER_SYSTEM_PROMPT = (
    "You are a Research Manager synthesizing analyst reports into a unified "
    "investment thesis.\n"
    "\n"
    "You will receive reports from three specialist analysts:\n"
    "1. Fundamental Analyst: valuation, financial metrics, SEC filing evidence\n"
    "2. Sentiment Analyst: news sentiment, insider activity, market mood\n"
    "3. Technical/Quant Analyst: momentum, volatility, price patterns\n"
    "\n"
    "YOUR TASK:\n"
    "1. Identify where analysts AGREE -- convergent signals strengthen confidence.\n"
    "2. Identify where analysts CONFLICT -- e.g., bullish fundamentals vs bearish "
    "sentiment.\n"
    "3. For each conflict, explain which signal you weight more heavily and WHY. "
    "Resolve disagreements with explicit rationale, not by ignoring them.\n"
    "4. Produce a unified thesis with explicit citations to each analyst's evidence.\n"
    "5. In bull_case and bear_case ThesisPoints, set source_tool to the analyst name "
    "that provided the evidence (e.g., 'fundamental_analyst', 'sentiment_analyst', "
    "'technical_analyst').\n"
    "6. Confidence score should reflect evidence quality and the agreement/conflict "
    "ratio -- not just vote-counting across analysts.\n"
    "7. risk_factors should include risks identified by ANY analyst, plus any "
    "cross-analyst contradictions that represent uncertainty.\n"
    "\n"
    "IMPORTANT: You are a SYNTHESIZER, not a concatenator. Do not simply list each "
    "analyst's findings sequentially. Identify patterns, weigh conflicting evidence, "
    "and produce a coherent investment thesis with clear resolution of disagreements.\n"
)


manager_agent: Agent[None, ThesisOutput] = Agent(
    ModelTier.REASONING.value,
    output_type=ThesisOutput,
    system_prompt=MANAGER_SYSTEM_PROMPT,
    retries=2,
)


def get_manager_limits() -> UsageLimits:
    """Return UsageLimits for the manager agent (REASONING tier, Opus)."""
    return get_usage_limits(ModelTier.REASONING)


def format_analyst_reports(reports: list[dict]) -> str:
    """Format analyst report dicts into a human-readable string for the manager prompt.

    Each report dict has keys:
        - "analyst" (str): analyst name (e.g., "fundamental", "sentiment", "technical")
        - "analysis" (dict): the analyst's output (model_dump of specialist schema)
        - "tokens_used" (int): tokens consumed by the analyst
        - "error" (str, optional): error message if the analyst failed

    Args:
        reports: List of analyst report dicts from the pipeline state.

    Returns:
        Formatted string with all analyst reports separated by dividers.
        Returns a descriptive message if no reports are available.
    """
    if not reports:
        return "No analyst reports available."

    formatted_sections: list[str] = []
    for report in reports:
        analyst = report.get("analyst", "unknown")
        error = report.get("error")

        if error:
            section = f"{analyst}: UNAVAILABLE -- {error}"
        else:
            analysis = report.get("analysis", {})
            section = f"{analyst}:\n{json.dumps(analysis, indent=2)}"

        formatted_sections.append(section)

    return "\n\n---\n\n".join(formatted_sections)
