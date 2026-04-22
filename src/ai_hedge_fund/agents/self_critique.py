"""Self-critique rationale agent (MEM-04 Pattern 2).

Mirrors :class:`ai_hedge_fund.agents.risk_manager.risk_manager_agent` in
shape: REASONING tier, :class:`RationaleOnly` output, ``retries=2``, system
prompt using the "EXPLAIN" verb exclusively. A deterministic Python
function (:func:`ai_hedge_fund.memory.critique.compute_new_confidence`)
computes the new_confidence BEFORE this agent runs; the agent's ONLY job is
to produce a human-readable rationale.

Threat mitigations:
    T-07-30 (LLM authors the number): :class:`RationaleOnly` has EXACTLY
            ONE field (``rationale: str``); no numeric field is reachable
            via schema. Belt-and-braces: even with a wider output schema,
            ``ingest_outcome`` stamps the Python value into the
            ``CritiqueEvent`` before calling ``write_belief``.
    T-07-31 (Prompt-injected authority shift): system prompt uses EXPLAIN
            exclusively; the Phase-6 forbidden-verb list (see
            ``tests/memory/test_self_critique_agent.py``) is absent --
            word-boundary regex enforces this (analog of T-06-02b).
    T-05-13-analog (Rationale DoS): :class:`RationaleOnly` caps
            ``rationale`` at ``max_length=2000`` AND
            :func:`get_self_critique_limits` applies
            ``output_override=4_000``; two independent bounds.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.models import ModelTier


class RationaleOnly(BaseModel):
    """The self-critique agent's sole output: one human-readable paragraph.

    No number fields by design: a deterministic Python function has
    already computed the new_confidence BEFORE this agent runs. If you
    are tempted to add a ``new_confidence`` field here, stop -- that
    violates MEM-04 Pattern 2.
    """

    rationale: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "One-paragraph human-readable explanation of why the "
            "deterministic new_confidence differs from old_confidence. "
            "Must reference the ticker, old/new confidence, the realised "
            "outcome_pct, and which thesis element the outcome supports "
            "or contradicts. Advisory only -- does not affect the "
            "confidence number already computed."
        ),
    )


SELF_CRITIQUE_SYSTEM_PROMPT = (
    "You are the self-critique rationale writer. A deterministic Python "
    "function has ALREADY computed the new confidence for an investment "
    "thesis given a trade outcome. Your ONLY job is to EXPLAIN the "
    "change in one paragraph.\n"
    "\n"
    "Your input contains:\n"
    "  - BELIEF: the prior ticker/sector belief YAML dump\n"
    "  - OUTCOME: the realised outcome_pct\n"
    "  - OLD_CONFIDENCE: the prior confidence\n"
    "  - NEW_CONFIDENCE (DETERMINISTIC): the computed new confidence\n"
    "  - LINKED_ANALYSIS: snapshot of the signal that is being graded\n"
    "\n"
    "STRICT CONSTRAINTS:\n"
    "1. You DO NOT author the new_confidence number. You EXPLAIN the "
    "change already computed by Python.\n"
    "2. State the direction (raised / lowered / unchanged), the old and "
    "new confidence values, and which evidence from the thesis plus "
    "outcome supports the change.\n"
    "3. Never suggest re-writing the thesis body. Suggesting a rewrite "
    "is a human's responsibility.\n"
    "4. Output a single RationaleOnly object with one 'rationale' field. "
    "Target length: 2-5 sentences. No headings. No bullet lists.\n"
)


self_critique_agent: Agent[None, RationaleOnly] = Agent(
    ModelTier.REASONING.value,
    output_type=RationaleOnly,
    system_prompt=SELF_CRITIQUE_SYSTEM_PROMPT,
    retries=2,
)


def get_self_critique_limits() -> UsageLimits:
    """Return REASONING-tier limits with output capped at 4,000 tokens.

    Mirrors
    :func:`ai_hedge_fund.agents.risk_manager.get_risk_manager_limits` --
    same rationale budget, same dual-bound protection against
    runaway-generation DoS.
    """
    return get_usage_limits(ModelTier.REASONING, output_override=4_000)
