"""Final Arguments agent -- produces each side's closing argument for Act 4 of the 5-act debate.

The Final Arguments agent is a pure synthesis agent (no tools). It reads the
Bull case, Bear case, and the cross-side Rebuttal act from state and
produces a FinalArguments output: a non-empty closing statement per side
plus an integer citation count per side. Uses REASONING tier (Opus),
matching manager_agent / bull_agent / bear_agent / rebuttal_agent.

Threat mitigations:
    T-05-10: Tampering (empty closing) -- FinalArguments schema enforces
             ``min_length=1`` on both ``bull_closing`` and ``bear_closing``
             so blank-closing outputs fail validation. The prompt forbids
             introducing new evidence; closings must reflect what survived
             the rebuttal act.
    T-05-11: DoS (cost blowout) -- ``get_final_arguments_limits()`` returns
             REASONING tier with ``output_override=8_000`` per Pitfall 6.
             Closings are structurally small (1-2 paragraphs per side);
             the full 16k budget would permit runaway generation.
"""

from __future__ import annotations

import json

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.debate import FinalArguments

FINAL_ARGUMENTS_SYSTEM_PROMPT = (
    "You are the Final Arguments agent. You have read the Bull case, Bear "
    "case, and the Rebuttal cross-exchange. Produce each side's closing "
    "argument.\n"
    "\n"
    "STRICT RULES:\n"
    "1. bull_closing: a single closing statement (1-2 paragraphs) summarizing "
    "the Bull side's strongest remaining case AFTER the rebuttal. Must be "
    "non-empty.\n"
    "2. bear_closing: same format for the Bear side. Must be non-empty.\n"
    "3. bull_citation_count: count the distinct evidence references in "
    "bull_closing (e.g., if the closing cites 3 different analyst data "
    "points, set to 3). Integer, 0 or greater.\n"
    "4. bear_citation_count: same for bear_closing.\n"
    "5. Closings should reflect what SURVIVED the rebuttal. If a bull claim "
    "was effectively rebutted, do not re-assert it; focus on the strongest "
    "remaining points.\n"
    "6. Do NOT introduce new evidence not present in earlier acts. Closings "
    "are syntheses, not new arguments.\n"
)


final_arguments_agent: Agent[None, FinalArguments] = Agent(
    ModelTier.REASONING.value,
    output_type=FinalArguments,
    system_prompt=FINAL_ARGUMENTS_SYSTEM_PROMPT,
    retries=2,
)


def get_final_arguments_limits() -> UsageLimits:
    """Return UsageLimits for Final Arguments.

    REASONING tier with ``output_override=8_000`` per the Pitfall-6 cost
    guardrail. Closings are structurally small (1-2 paragraphs per side);
    the default 16k output cap would allow runaway generation that blows
    the per-debate cost target.
    """
    return get_usage_limits(ModelTier.REASONING, output_override=8_000)


def format_debate_for_final(
    bull_case: dict | None,
    bear_case: dict | None,
    rebuttal: dict | None,
) -> str:
    """Format (bull_case, bear_case, rebuttal) into the final-arguments prompt.

    Produces a three-section string separated by ``"\\n\\n---\\n\\n"``:

        1. ``BULL CASE:`` followed by ``json.dumps(bull_case, indent=2)``,
           or ``"BULL CASE: None available"`` when ``bull_case`` is ``None``
           or an empty dict.
        2. ``BEAR CASE:`` same pattern.
        3. ``REBUTTAL:`` same pattern.

    Args:
        bull_case: A ``BullCase.model_dump()`` dict, or ``None`` / empty dict.
        bear_case: A ``BearCase.model_dump()`` dict, or ``None`` / empty dict.
        rebuttal: A ``RebuttalAct.model_dump()`` dict, or ``None`` / empty dict.

    Returns:
        Formatted three-section string suitable for the final-arguments
        agent's user prompt. Pure function -- no I/O, no logging.
    """
    if not bull_case:
        bull_section = "BULL CASE: None available"
    else:
        bull_section = "BULL CASE:\n" + json.dumps(bull_case, indent=2)

    if not bear_case:
        bear_section = "BEAR CASE: None available"
    else:
        bear_section = "BEAR CASE:\n" + json.dumps(bear_case, indent=2)

    if not rebuttal:
        rebuttal_section = "REBUTTAL: None available"
    else:
        rebuttal_section = "REBUTTAL:\n" + json.dumps(rebuttal, indent=2)

    return (
        f"{bull_section}\n\n---\n\n"
        f"{bear_section}\n\n---\n\n"
        f"{rebuttal_section}"
    )
