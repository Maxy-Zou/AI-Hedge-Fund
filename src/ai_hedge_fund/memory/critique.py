"""Deterministic self-critique math (MEM-04 Pattern 2).

The LLM does NOT author the confidence update. A pure function here
computes the new value from ``(old_confidence, outcome_pct,
signal_direction)`` and the self_critique_agent writes a rationale
only. Same contract as Phase 6's ``risk_manager_agent``: deterministic
Python decides the number, LLM explains.

Pitfall 5 (confidence drift): the raw algorithm can push confidence by
``k * |outcome| * 10`` per event, which an extreme outcome can saturate
at 100 in a single step. We cap the per-event delta at ``10`` so the
rule is bounded-linear and aligns with human-reviewable behavior.
07-RESEARCH.md Pattern 6 flags the raw numbers (``k=0.3``, cap=10) as
placeholders (A2 in the Assumptions Log) -- revisit after 50
calibration events.

Threat mitigations:
    T-07-30 (LLM authors the number): the writer-facing API here
            accepts only numeric inputs and returns an int; there is no
            path for LLM text to influence the returned value. Belt-
            and-braces for the ``RationaleOnly`` schema guard in
            ``ai_hedge_fund.agents.self_critique``.
    T-07-36 (confidence drift saturating on extreme outcomes):
            ``_PER_EVENT_DELTA_CAP = 10`` bounds a single update.
"""

from __future__ import annotations

import json
from typing import Any

from ai_hedge_fund.schemas.memory import Belief

# Allowed signal directions. Kept as a tuple (not a Literal type alias) so
# the ValueError message can list them verbatim without relying on typing
# runtime introspection.
_ALLOWED_DIRECTIONS: tuple[str, ...] = ("long", "short", "neutral")

# Pitfall 5 mitigation: cap |new_confidence - old_confidence| per event.
# A 10-point cap on a 0-100 scale means a belief cannot flip from high
# to low in a single outcome; operators always see a smooth drift that
# is human-reviewable. Documented in 07-RESEARCH.md Pattern 6.
_PER_EVENT_DELTA_CAP: int = 10


def compute_new_confidence(
    old_confidence: int,
    outcome_pct: float,
    signal_direction: str,
    k: float = 0.3,
) -> int:
    """Return the new confidence after a trade outcome.

    Args:
        old_confidence: Prior confidence in ``[0, 100]``.
        outcome_pct: Realised P&L as percent (positive = up, negative =
            down). A 4.2% winning trade is ``4.2``.
        signal_direction: One of ``"long"``, ``"short"``, ``"neutral"``.
        k: Adjustment coefficient (default ``0.3``). Placeholder pending
            calibration per 07-RESEARCH.md A2.

    Returns:
        New confidence, int in ``[0, 100]``. Per-event ``|delta| <= 10``.

    Raises:
        ValueError: ``signal_direction`` is not in
            ``{"long", "short", "neutral"}``.
    """
    if signal_direction not in _ALLOWED_DIRECTIONS:
        raise ValueError(
            f"Unknown signal_direction {signal_direction!r}; expected one of {_ALLOWED_DIRECTIONS}"
        )

    agreed = (signal_direction == "long" and outcome_pct > 0) or (
        signal_direction == "short" and outcome_pct < 0
    )
    raw_adjustment = k * abs(outcome_pct) * 10
    capped_adjustment = min(raw_adjustment, float(_PER_EVENT_DELTA_CAP))

    if signal_direction == "neutral":
        # Any significant move penalises a neutral call.
        delta = -capped_adjustment
    elif agreed:
        delta = +capped_adjustment
    else:
        delta = -capped_adjustment

    new = max(0.0, min(100.0, old_confidence + delta))
    return int(round(new))


def format_critique_context(
    belief: Belief,
    outcome_pct: float,
    new_confidence: int,
    linked_analysis_payload: dict[str, Any] | None = None,
) -> str:
    """Build the deterministic 5-section prompt consumed by self_critique_agent.

    Sections are separated by ``\\n\\n---\\n\\n`` and labelled
    ``BELIEF``, ``OUTCOME``, ``OLD_CONFIDENCE``,
    ``NEW_CONFIDENCE (DETERMINISTIC)``, ``LINKED_ANALYSIS``. Pure
    function; no I/O; deterministic across runs for audit.

    Args:
        belief: The prior belief (YAML projection) being critiqued.
        outcome_pct: Realised outcome percent.
        new_confidence: The value returned by :func:`compute_new_confidence`.
            The agent is told this number is authoritative (it does NOT
            author the number; it explains it).
        linked_analysis_payload: Optional JSON-serialisable snapshot of
            the analysis row whose signal this outcome grades. ``None``
            renders as an empty object.

    Returns:
        A deterministic prompt string ready for ``self_critique_agent.run``.
    """
    belief_section = f"BELIEF:\n{json.dumps(belief.model_dump(mode='json'), indent=2, default=str)}"
    outcome_section = f"OUTCOME:\n  outcome_pct: {outcome_pct}"
    old_section = f"OLD_CONFIDENCE: {belief.confidence}"
    new_section = f"NEW_CONFIDENCE (DETERMINISTIC): {new_confidence}"
    linked = linked_analysis_payload or {}
    linked_section = f"LINKED_ANALYSIS:\n{json.dumps(linked, indent=2, default=str)}"
    return "\n\n---\n\n".join(
        [
            belief_section,
            outcome_section,
            old_section,
            new_section,
            linked_section,
        ]
    )
