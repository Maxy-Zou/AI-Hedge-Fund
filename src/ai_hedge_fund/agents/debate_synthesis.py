"""Debate Synthesis agent -- Act 5 of the 5-act debate + deterministic quality_score helper.

The Debate Synthesis agent is a pure synthesis agent (no tools). It reads
all four prior acts (bull case, bear case, rebuttal, final arguments) and
the manager's pre-debate thesis from state, and produces a DebateSynthesis
containing a revised_thesis, a re-evaluated post_debate_confidence, and
three decomposed sub-scores (evidence_strength, logical_consistency,
risk_coverage). Uses REASONING tier (Opus) -- this is the most complex
reasoning step in the pipeline.

``compute_quality_score`` is a PURE PYTHON weighted-mean aggregator that
turns the three LLM-produced sub-scores into a single quality_score.
CLAUDE.md: "Tool-first for quantitative work. LLMs NEVER compute financial
ratios, run backtests, or calculate position sizes directly." Weighted-mean
aggregation is a quantitative computation -- this is the tool the LLM does
not have access to. The ``quality_score`` field on ``DebateSynthesis`` is
overwritten by ``debate_synthesis_node`` (Plan 05-03) with the output of
this function; the LLM-produced ``quality_score`` value is discarded.

Threat mitigations:
    T-05-12: Tampering (fabricated quality_score) -- ``compute_quality_score``
             is Python; Plan 05-03's ``debate_synthesis_node`` overwrites the
             LLM's ``quality_score`` with the Python result via
             ``DebateSynthesis.model_copy(update={'quality_score': ...})``.
             The LLM-produced sub-scores (``evidence_strength``,
             ``logical_consistency``, ``risk_coverage``) are range-checked
             (``ge=0, le=100``) by the Pydantic schema before they reach
             this function.
    T-05-13: Tampering (post_debate_confidence == pre_debate_confidence
             sycophancy) -- ``DEBATE_SYNTHESIS_SYSTEM_PROMPT`` explicitly
             requires re-evaluation from scratch; Plan 05-03's node sources
             ``pre_debate_confidence`` from ``state["thesis"]["confidence"]``
             (not LLM output) so the pre-debate baseline cannot be
             tampered with.
    T-05-14: DoS -- ``get_debate_synthesis_limits()`` caps REASONING tier
             usage at the default (116k total). Not overridden because
             synthesis emits a full ThesisOutput + three sub-scores + notes
             and needs the full 16k output budget.
"""

from __future__ import annotations

import json

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.debate import DebateSynthesis

# Quality-score weights: evidence citations matter most (citations and data
# grounding), logical consistency and risk coverage are equal secondary
# concerns. See 05-RESEARCH.md A1; surfaced as named constants so an
# alternative weighting (e.g. 0.33/0.33/0.33) can be sanity-checked in tests
# and edited without touching the compute function.
EVIDENCE_WEIGHT: float = 0.4
LOGIC_WEIGHT: float = 0.3
RISK_WEIGHT: float = 0.3


def compute_quality_score(
    evidence_strength: int,
    logical_consistency: int,
    risk_coverage: int,
) -> int:
    """Compute debate quality_score as a deterministic weighted mean of three sub-scores.

    Weights (documented in 05-RESEARCH.md A1):
        EVIDENCE_WEIGHT = 0.4  (citations and data grounding)
        LOGIC_WEIGHT    = 0.3  (internal coherence)
        RISK_WEIGHT     = 0.3  (risk-factor completeness)

    All inputs must be integers in [0, 100]; output is rounded to int in [0, 100].

    CLAUDE.md: "Tool-first for quantitative work. LLMs NEVER compute financial
    ratios, run backtests, or calculate position sizes directly." Weighted-mean
    aggregation is a quantitative computation -- this is the tool the LLM does
    not have access to. The ``debate_synthesis`` agent produces the three
    sub-scores (qualitative LLM judgment); this function computes the aggregate
    (arithmetic).

    Args:
        evidence_strength: LLM judgment of evidence quality (0-100).
        logical_consistency: LLM judgment of internal consistency (0-100).
        risk_coverage: LLM judgment of risk-factor completeness (0-100).

    Returns:
        Integer in [0, 100] -- the rounded weighted mean.

    Raises:
        ValueError: if any sub-score is outside [0, 100].
    """
    if not (0 <= evidence_strength <= 100):
        raise ValueError(f"evidence_strength out of range [0,100]: {evidence_strength}")
    if not (0 <= logical_consistency <= 100):
        raise ValueError(f"logical_consistency out of range [0,100]: {logical_consistency}")
    if not (0 <= risk_coverage <= 100):
        raise ValueError(f"risk_coverage out of range [0,100]: {risk_coverage}")
    score = (
        EVIDENCE_WEIGHT * evidence_strength
        + LOGIC_WEIGHT * logical_consistency
        + RISK_WEIGHT * risk_coverage
    )
    return round(score)


DEBATE_SYNTHESIS_SYSTEM_PROMPT = (
    "You are the Debate Synthesis agent. You have read all four prior acts "
    "(bull case, bear case, rebuttal, final arguments) and the manager's "
    "pre-debate thesis. Produce a revised_thesis and three decomposed "
    "sub-scores.\n"
    "\n"
    "STRICT RULES:\n"
    "1. revised_thesis: a full ThesisOutput (ticker, bull_case, bear_case, "
    "confidence, risk_factors) reflecting what survived the debate. If the "
    "debate exposed risks, the bear_case list should incorporate them; if it "
    "strengthened the bull, the bull_case list should sharpen. You may keep "
    "the pre-debate thesis unchanged only if the debate was truly balanced "
    "AND you explicitly say so in synthesis_notes.\n"
    "2. post_debate_confidence: YOU MUST re-evaluate confidence FROM SCRATCH "
    "based on the debate. Do NOT default to the pre-debate value. If the "
    "debate strengthened the case, increase; if it exposed risk, decrease; "
    "if it was balanced, you may keep it BUT note that explicitly in "
    "synthesis_notes.\n"
    "3. evidence_strength (0-100): how strong is the evidence backing the "
    "revised thesis? Strong = well-cited, from multiple analysts. Weak = "
    "few citations, single-analyst.\n"
    "4. logical_consistency (0-100): how internally consistent is the "
    "debate? High = rebuttals directly addressed claims; low = sides talked "
    "past each other.\n"
    "5. risk_coverage (0-100): how well are risks identified and covered? "
    "High = bear_case surfaced material risks the manager missed; low = "
    "debate did not expose new risk.\n"
    "6. pre_debate_confidence: this field will be overwritten by the "
    'pipeline from state["thesis"]["confidence"] -- fill with your best '
    "estimate but do not rely on it.\n"
    "7. quality_score: this field will be overwritten by the pipeline's "
    "compute_quality_score() function -- fill with 0 as a placeholder.\n"
    "8. synthesis_notes: 1-3 sentences explaining the delta between pre- "
    "and post-debate confidence and any material thesis revisions.\n"
)


debate_synthesis_agent: Agent[None, DebateSynthesis] = Agent(
    ModelTier.REASONING.value,
    output_type=DebateSynthesis,
    system_prompt=DEBATE_SYNTHESIS_SYSTEM_PROMPT,
    retries=2,
)


def get_debate_synthesis_limits() -> UsageLimits:
    """Return UsageLimits for Debate Synthesis.

    REASONING tier with the DEFAULT output cap (NOT overridden). Synthesis
    emits a full ThesisOutput (bull_case + bear_case ThesisPoints +
    risk_factors) + three sub-scores + synthesis_notes + pre/post
    confidence; it needs the full 16k output budget. This is the
    intentional divergence from rebuttal_agent / final_arguments_agent,
    which DO apply output_override=8_000 because their outputs are
    structurally smaller.
    """
    return get_usage_limits(ModelTier.REASONING)


def format_debate_for_synthesis(state: dict, pre_debate_confidence: int) -> str:
    """Format the full debate state + pre_debate_confidence for the synthesis prompt.

    Produces a six-section string separated by ``"\\n\\n---\\n\\n"``:

        1. ``PRE-DEBATE CONFIDENCE (from manager): <int>``
        2. ``PRE-DEBATE THESIS:`` JSON-dump of ``state['thesis']``
           (or ``None available`` when absent).
        3. ``BULL CASE:`` JSON-dump of ``state['bull_case']``.
        4. ``BEAR CASE:`` JSON-dump of ``state['bear_case']``.
        5. ``REBUTTAL:`` JSON-dump of ``state['rebuttal']``.
        6. ``FINAL ARGUMENTS:`` JSON-dump of ``state['final_arguments']``.

    Missing state keys emit ``None available`` for that section body;
    ``pre_debate_confidence`` is ALWAYS printed (sourced from the pipeline,
    not state) so the LLM sees the baseline it must re-evaluate against.

    Args:
        state: A mapping with keys ``thesis``, ``bull_case``, ``bear_case``,
            ``rebuttal``, ``final_arguments`` (any/all optional).
        pre_debate_confidence: The manager's pre-debate confidence integer
            (0-100). Plan 05-03's node sources this from
            ``state["thesis"]["confidence"]`` so the baseline is not
            tampered with by the LLM.

    Returns:
        Formatted six-section string suitable for the synthesis agent's
        user prompt. Pure function -- no I/O, no logging.
    """

    def _section(label: str, value: dict | None) -> str:
        if not value:
            return f"{label}: None available"
        return f"{label}:\n{json.dumps(value, indent=2)}"

    sections = [
        f"PRE-DEBATE CONFIDENCE (from manager): {pre_debate_confidence}",
        _section("PRE-DEBATE THESIS", state.get("thesis")),
        _section("BULL CASE", state.get("bull_case")),
        _section("BEAR CASE", state.get("bear_case")),
        _section("REBUTTAL", state.get("rebuttal")),
        _section("FINAL ARGUMENTS", state.get("final_arguments")),
    ]
    return "\n\n---\n\n".join(sections)
