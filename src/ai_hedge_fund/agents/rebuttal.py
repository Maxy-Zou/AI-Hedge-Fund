"""Rebuttal agent -- produces balanced bidirectional rebuttals for Act 3 of the 5-act debate.

The Rebuttal agent is a pure synthesis agent (no tools). It reads the Bull
Advocate's full case and the Bear Advocate's full case from state and
produces a RebuttalAct with at least 2 bull-side rebuttals of bear claims
AND at least 2 bear-side rebuttals of bull claims. Uses REASONING tier
(Opus), matching manager_agent / bull_agent / bear_agent.

Threat mitigations:
    T-05-08: Tampering (unbalanced rebuttals) -- RebuttalAct schema enforces
             dual ``min_length=2`` on both ``bull_rebuttals`` and
             ``bear_rebuttals`` so one-sided rebuttal outputs fail validation.
             REBUTTAL_SYSTEM_PROMPT explicitly demands the minimum on each
             side; retries=2 lets PydanticAI self-correct when the LLM
             under-fills a side.
    T-05-09: DoS (cost blowout) -- ``get_rebuttal_limits()`` returns
             REASONING tier with ``output_override=8_000`` per Pitfall 6.
             Rebuttals are structurally small; the full 16k output budget
             would let runaway LLM output blow the per-debate cost target.
"""

from __future__ import annotations

import json

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.debate import RebuttalAct

REBUTTAL_SYSTEM_PROMPT = (
    "You are the Debate Rebuttal agent. You have read the Bull Advocate's "
    "case and the Bear Advocate's case; produce cross-side rebuttals.\n"
    "\n"
    "STRICT RULES:\n"
    "1. Produce AT LEAST 2 bull_rebuttals -- arguments the Bull side makes "
    "against specific Bear claims.\n"
    "2. Produce AT LEAST 2 bear_rebuttals -- arguments the Bear side makes "
    "against specific Bull claims.\n"
    "3. Each RebuttalPoint MUST have a targets_claim field containing the "
    "verbatim (or near-verbatim) text of the opposing claim being rebutted.\n"
    "4. Every rebuttal MUST cite source_analyst (fundamental|sentiment|"
    "technical|manager).\n"
    "5. Brevity: cap each rebuttal at 2 sentences. Cap total rebuttals at 3 "
    "per side.\n"
    "6. Do NOT soften. If one side has weaker rebuttals than the other, "
    "still produce the minimum 2 -- the schema requires balance.\n"
)


rebuttal_agent: Agent[None, RebuttalAct] = Agent(
    ModelTier.REASONING.value,
    output_type=RebuttalAct,
    system_prompt=REBUTTAL_SYSTEM_PROMPT,
    retries=2,
)


def get_rebuttal_limits() -> UsageLimits:
    """Return UsageLimits for the Rebuttal agent.

    REASONING tier with ``output_override=8_000`` per the Pitfall-6 cost
    guardrail documented in ``05-RESEARCH.md``. Rebuttals are structurally
    small (max 3 per side × 2 sentences); the default 16k output cap
    would allow runaway generation that blows the per-debate cost target.
    """
    return get_usage_limits(ModelTier.REASONING, output_override=8_000)


def format_debate_for_rebuttal(bull_case: dict | None, bear_case: dict | None) -> str:
    """Format the (bull_case, bear_case) pair for the rebuttal agent's user prompt.

    Produces a two-section string separated by ``"\\n\\n---\\n\\n"``:

        1. ``BULL CASE:`` followed by ``json.dumps(bull_case, indent=2)``,
           or the fallback ``"BULL CASE: None available"`` when ``bull_case``
           is ``None`` or an empty dict.
        2. ``BEAR CASE:`` followed by ``json.dumps(bear_case, indent=2)``,
           or the fallback ``"BEAR CASE: None available"`` when missing.

    Args:
        bull_case: A ``BullCase.model_dump()`` dict, or ``None`` / empty dict.
        bear_case: A ``BearCase.model_dump()`` dict, or ``None`` / empty dict.

    Returns:
        Formatted two-section string suitable for the rebuttal agent's
        user prompt. Pure function -- no I/O, no logging.
    """
    if not bull_case:
        bull_section = "BULL CASE: None available"
    else:
        bull_section = "BULL CASE:\n" + json.dumps(bull_case, indent=2)

    if not bear_case:
        bear_section = "BEAR CASE: None available"
    else:
        bear_section = "BEAR CASE:\n" + json.dumps(bear_case, indent=2)

    return f"{bull_section}\n\n---\n\n{bear_section}"
