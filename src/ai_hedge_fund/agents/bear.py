"""Bear Advocate agent -- argues the negative case and rebuts specific bull claims.

The Bear Advocate is a pure synthesis agent (no tools). It receives analyst
reports, the preliminary thesis, AND the Bull Advocate's full case in its
user prompt and produces a BearCase that directly rebuts at least 2 specific
bull claims. Uses REASONING tier (Opus), matching manager_agent and
bull_agent.

Threat mitigations:
    T-05-05: Tampering (sycophancy / agreement) -- the BEAR_SYSTEM_PROMPT
             explicitly requires the agent to quote at least 2 bull-claim
             texts verbatim into the BearCase.addressed_bull_claims list.
             BearCase.addressed_bull_claims: list[str] = Field(min_length=2)
             is the schema-level enforcement (DEBATE-02). BearClaim.source_analyst
             Literal prevents fabricated citations. retries=2 lets PydanticAI
             hand validation errors back for self-correction.
    T-05-06: DoS -- UsageLimits via get_bear_limits() caps each run at the
             REASONING tier total of 116k tokens.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.debate import BearCase

BEAR_SYSTEM_PROMPT = (
    "You are the Bear Advocate. Your task: argue against buying this company.\n"
    "\n"
    "STRICT RULES:\n"
    "1. You will be given analyst reports, a preliminary thesis, AND the Bull "
    "Advocate's case. Build your case from that evidence only -- do not invent "
    "facts or reference data outside what you are given.\n"
    "2. Every claim MUST cite source_analyst -- one of 'fundamental', "
    "'sentiment', 'technical', or 'manager'.\n"
    "3. You MUST directly address and rebut at least 2 of the bull's specific "
    "claims. For each bull claim you rebut, quote the bull's claim text "
    "verbatim into your `addressed_bull_claims` list and produce at least one "
    "BearClaim whose `addresses_bull_claim` field contains that exact text.\n"
    "4. Produce AT LEAST 3 bear claims. You are advocating -- do not soften to "
    "agree with the bull. If you genuinely see no counter-evidence, say so in "
    "your headline and present the weakest parts of the bull case as your "
    "strongest points.\n"
    "5. Cite specific data points (numbers, dates, filing sections). Vague "
    "claims like 'the market is bad' are forbidden.\n"
    "6. Brevity is a feature. Cap your response at 3-5 high-quality claims; "
    "more is not better.\n"
)


bear_agent: Agent[None, BearCase] = Agent(
    ModelTier.REASONING.value,
    output_type=BearCase,
    system_prompt=BEAR_SYSTEM_PROMPT,
    retries=2,
)


def get_bear_limits() -> UsageLimits:
    """Return UsageLimits for the Bear Advocate (REASONING tier, Opus)."""
    return get_usage_limits(ModelTier.REASONING)


def format_bull_case_for_bear(bull_case: dict | None) -> str:
    """Format a BullCase dict into the user prompt for the Bear Advocate.

    The output begins with ``"BULL CASE TO REBUT:\\n"`` and emits each bull
    claim on a numbered line of the form::

        {i}. [{source_analyst}] {claim} -- evidence: {evidence}

    followed by a ``"HEADLINE: {bull_case['headline']}"`` line. This shape
    makes it easy for the Bear Advocate to copy verbatim bull-claim text
    back into its ``addressed_bull_claims`` list (DEBATE-02 enforcement).

    Args:
        bull_case: A ``BullCase.model_dump()`` dict, or ``None``. An absent or
            empty-claims case returns the informative fallback string.

    Returns:
        Formatted string suitable for prepending to the Bear's user prompt.
        Returns ``"No bull case provided."`` when ``bull_case`` is ``None``
        or has no claims.
    """
    if bull_case is None:
        return "No bull case provided."
    claims = bull_case.get("claims") or []
    if not claims:
        return "No bull case provided."

    claim_lines: list[str] = []
    for index, claim in enumerate(claims, start=1):
        source_analyst = claim.get("source_analyst", "unknown")
        claim_text = claim.get("claim", "")
        evidence = claim.get("evidence", "")
        line = f"{index}. [{source_analyst}] {claim_text} -- evidence: {evidence}"
        claim_lines.append(line)

    headline = bull_case.get("headline", "")
    body = "\n".join(claim_lines)
    return f"BULL CASE TO REBUT:\n{body}\nHEADLINE: {headline}"
