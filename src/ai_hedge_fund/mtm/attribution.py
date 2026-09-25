"""Attribution inputs and rules for mark-to-market (Phase 11, 11-SPEC A2 / s2 / s5).

Pure functions, no I/O, no LLM. ``derive_stances`` runs at *store* time
(``episodic_store_node``) so an analyst's stance is frozen with the analysis it
belongs to; a later rule change bumps ``stance_rule_version`` (and therefore
``mtm_policy_sha``) instead of rewriting history (11-PREMORTEM #23).

The analyst output schemas carry no direction field (A2), so a stance is
derived: fundamental / technical compare bull vs bear factor counts; sentiment
compares ``composite_score`` against ``MtmPolicy.sentiment_threshold``. Anything
the rule cannot read honestly -- an errored, missing, malformed, or duplicated
report -- is ``absent``, never ``neutral`` (11-PREMORTEM #24).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ai_hedge_fund.mtm.policy import UNKNOWN_BUCKET, MtmPolicy

Analyst = Literal["fundamental", "sentiment", "technical"]
Stance = Literal["bull", "bear", "neutral", "absent"]
Side = Literal["buy", "sell"]
DebateWinner = Literal["bull", "bear", "draw", "unattributed"]

ANALYSTS: tuple[Analyst, ...] = ("fundamental", "sentiment", "technical")
_DEBATE_FIELDS = ("pre_debate_confidence", "post_debate_confidence", "quality_score")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_factor_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) and v for v in value)


def _factor_stance(analysis: dict[str, Any]) -> Stance:
    bull, bear = analysis.get("bull_factors"), analysis.get("bear_factors")
    if not _is_factor_list(bull) or not _is_factor_list(bear):
        return "absent"
    if len(bull) > len(bear):
        return "bull"
    if len(bull) < len(bear):
        return "bear"
    return "neutral"


def _sentiment_stance(analysis: dict[str, Any], threshold: float) -> Stance:
    score = analysis.get("composite_score")
    if not _is_number(score) or not math.isfinite(score):
        return "absent"
    if score >= threshold:
        return "bull"
    if score <= -threshold:
        return "bear"
    return "neutral"


def _stance_of(report: dict[str, Any], policy: MtmPolicy) -> Stance:
    analysis = report.get("analysis")
    if report.get("error") or not isinstance(analysis, dict):
        return "absent"
    if report.get("analyst") == "sentiment":
        return _sentiment_stance(analysis, policy.sentiment_threshold)
    return _factor_stance(analysis)


def derive_stances(
    analyst_reports: Sequence[dict[str, Any]], policy: MtmPolicy
) -> dict[str, Stance]:
    """Map each of the three analysts to a stance (A2); always returns all three keys."""
    by_analyst: dict[str, list[dict[str, Any]]] = {name: [] for name in ANALYSTS}
    for report in analyst_reports:
        name = report.get("analyst")
        if name in by_analyst:
            by_analyst[name].append(report)
    # Two reports for one analyst have no single honest stance -> absent.
    return {
        name: _stance_of(reports[0], policy) if len(reports) == 1 else "absent"
        for name, reports in by_analyst.items()
    }


def debate_snapshot(debate_synthesis: dict[str, Any] | None) -> dict[str, int] | None:
    """The three debate numbers attribution needs, or None if there was no usable debate."""
    if not debate_synthesis:
        return None
    values = {field: debate_synthesis.get(field) for field in _DEBATE_FIELDS}
    if not all(_is_int(v) for v in values.values()):
        return None
    return values  # type: ignore[return-value]


# --------------------------------------------------------------------------- per-signal labels (T6)

_SIDE_STANCE: dict[str, Stance] = {"buy": "bull", "sell": "bear"}
_OPPOSITE: dict[str, Stance] = {"bull": "bear", "bear": "bull"}


class Attribution(BaseModel):
    """A signal's frozen attribution labels, stored verbatim on every P&L row.

    ``attribution_schema`` separates "no analyst agreed" (``v2`` with no credited
    analysts -> ``none_aligned``) from "we never recorded stances" (``unattributed``,
    pre-Phase-11 analyses) -- 11-PREMORTEM #22. No float fields, so the stored JSON
    is deterministic (#5).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    attribution_schema: Literal["v2", "unattributed"]
    credited_analysts: tuple[Analyst, ...]
    debate_winner: DebateWinner
    conviction_bucket: str


def debate_winner(debate: dict[str, Any] | None, side: Side) -> DebateWinner:
    """D3: the side the debate moved confidence toward, relative to the traded side."""
    snapshot = debate_snapshot(debate)
    if snapshot is None:
        return "unattributed"
    delta = snapshot["post_debate_confidence"] - snapshot["pre_debate_confidence"]
    aligned = _SIDE_STANCE[side]
    if delta > 0:
        return aligned  # type: ignore[return-value]
    if delta < 0:
        return _OPPOSITE[aligned]  # type: ignore[return-value]
    return "draw"


def _stored_stances(payload: dict[str, Any]) -> dict[str, Any] | None:
    stances = payload.get("analyst_stances")
    version = payload.get("schema_version")
    if type(version) is not int or version < 2 or not isinstance(stances, dict):
        return None
    return stances


def attribution_for(
    analysis_payload: dict[str, Any],
    confidence: int | None,
    side: Side,
    policy: MtmPolicy,
) -> Attribution:
    """Attribution labels for one executed signal, read from its stored analysis row.

    Uses the stances frozen at store time -- never re-derives them (11-PREMORTEM #23).
    """
    bucket = UNKNOWN_BUCKET if confidence is None else policy.bucket_for(confidence)
    stances = _stored_stances(analysis_payload)
    if stances is None:
        return Attribution(
            attribution_schema="unattributed",
            credited_analysts=(),
            debate_winner="unattributed",
            conviction_bucket=bucket,
        )
    wanted = _SIDE_STANCE[side]
    return Attribution(
        attribution_schema="v2",
        credited_analysts=tuple(a for a in ANALYSTS if stances.get(a) == wanted),
        debate_winner=debate_winner(analysis_payload.get("debate"), side),
        conviction_bucket=bucket,
    )


def split_cents(total: int, parts: int) -> tuple[int, ...]:
    """Split ``total`` into ``parts`` integers that sum to it exactly (criterion 11.3).

    Pieces differ by at most one cent; the extra cents go to the leading parts, so
    with analysts in fixed order (fundamental, sentiment, technical) the split is
    reproducible.
    """
    if parts < 1:
        raise ValueError(f"parts must be >= 1, got {parts}")
    base, remainder = divmod(total, parts)
    return tuple(base + 1 if i < remainder else base for i in range(parts))
