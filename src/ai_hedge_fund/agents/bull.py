"""Bull Advocate agent -- argues the positive investment case from analyst evidence.

The Bull Advocate is a pure synthesis agent (no tools). It receives analyst
reports + the preliminary thesis in its user prompt and produces a BullCase
by making at least 3 claims, each citing a specific analyst's evidence. Uses
REASONING tier (Opus) because high-quality adversarial argument is high-
reasoning work, the same justification used for manager_agent.

Threat mitigations:
    T-05-03: Tampering (unsupported claim) -- BullCase.BullClaim.source_analyst
             is a Literal over {fundamental, sentiment, technical, manager};
             the system prompt forbids claims without analyst evidence;
             retries=2 lets PydanticAI hand validation errors back to the
             model for self-correction when it fabricates a non-existent
             source or emits fewer than 3 claims.
    T-05-04: DoS -- UsageLimits via get_bull_limits() caps each run at the
             REASONING tier total of 116k tokens.
"""

from __future__ import annotations

import json

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.debate import BullCase

BULL_SYSTEM_PROMPT = (
    "You are the Bull Advocate. Your task: argue for this company as a buy.\n"
    "\n"
    "STRICT RULES:\n"
    "1. You are given analyst reports AND a preliminary thesis. Build your case "
    "ONLY from evidence in those inputs. Do not invent facts or reference data "
    "outside what you are given.\n"
    "2. Every claim you make MUST cite its source_analyst -- one of "
    "'fundamental', 'sentiment', 'technical', or 'manager'. Claims without a "
    "valid source_analyst will be rejected by schema validation.\n"
    "3. Cite specific data points (numbers, dates, filing sections). Vague "
    "claims like 'strong fundamentals' are forbidden.\n"
    "4. Produce AT LEAST 3 bull claims. Outputs with fewer than 3 claims will "
    "be rejected.\n"
    "5. You are advocating, not synthesizing -- present the strongest possible "
    "buy case. The Bear Advocate will counter you.\n"
    "6. Brevity is a feature. Cap your response at 3-5 high-quality claims; "
    "more is not better.\n"
)


bull_agent: Agent[None, BullCase] = Agent(
    ModelTier.REASONING.value,
    output_type=BullCase,
    system_prompt=BULL_SYSTEM_PROMPT,
    retries=2,
)


def get_bull_limits() -> UsageLimits:
    """Return UsageLimits for the Bull Advocate (REASONING tier, Opus)."""
    return get_usage_limits(ModelTier.REASONING)


def format_analyst_evidence(reports: list[dict], thesis: dict | None) -> str:
    """Format the (analyst_reports, preliminary_thesis) pair for the bull prompt.

    Produces a two-section string separated by ``"\\n\\n---\\n\\n"``:
        1. ``PRELIMINARY THESIS:`` followed by ``json.dumps(thesis, indent=2)``,
           or the ``"No preliminary thesis available."`` fallback when
           ``thesis`` is ``None``.
        2. ``ANALYST EVIDENCE:`` followed by the analyst reports formatted as
           per-analyst sections, or the ``"No analyst evidence available."``
           fallback when ``reports`` is empty.

    Each report dict has keys:
        - ``analyst`` (str): analyst name (e.g., ``"fundamental"``).
        - ``analysis`` (dict): the analyst's output (model_dump of specialist
          schema).
        - ``tokens_used`` (int): tokens consumed by the analyst.
        - ``error`` (str, optional): error message if the analyst failed.

    Args:
        reports: List of analyst report dicts from pipeline state. May be empty.
        thesis: The manager's preliminary thesis dict, or None if unavailable.

    Returns:
        Formatted two-section string suitable for the bull agent's user prompt.
    """
    if thesis is None:
        thesis_section = "PRELIMINARY THESIS:\nNo preliminary thesis available."
    else:
        thesis_section = "PRELIMINARY THESIS:\n" + json.dumps(thesis, indent=2)

    if not reports:
        evidence_section = "ANALYST EVIDENCE:\nNo analyst evidence available."
    else:
        analyst_sections: list[str] = []
        for report in reports:
            analyst = report.get("analyst", "unknown")
            error = report.get("error")
            if error:
                section = f"{analyst}: UNAVAILABLE -- {error}"
            else:
                analysis = report.get("analysis", {})
                section = f"{analyst}:\n{json.dumps(analysis, indent=2)}"
            analyst_sections.append(section)
        evidence_body = "\n\n".join(analyst_sections)
        evidence_section = f"ANALYST EVIDENCE:\n{evidence_body}"

    return f"{thesis_section}\n\n---\n\n{evidence_section}"
