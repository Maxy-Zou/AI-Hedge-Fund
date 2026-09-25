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

from collections.abc import Sequence
from typing import Any, Literal

from ai_hedge_fund.mtm.policy import MtmPolicy

Analyst = Literal["fundamental", "sentiment", "technical"]
Stance = Literal["bull", "bear", "neutral", "absent"]

ANALYSTS: tuple[Analyst, ...] = ("fundamental", "sentiment", "technical")
_DEBATE_FIELDS = ("pre_debate_confidence", "post_debate_confidence", "quality_score")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _factor_stance(analysis: dict[str, Any]) -> Stance:
    bull, bear = analysis.get("bull_factors"), analysis.get("bear_factors")
    if not isinstance(bull, list) or not isinstance(bear, list):
        return "absent"
    if len(bull) > len(bear):
        return "bull"
    if len(bull) < len(bear):
        return "bear"
    return "neutral"


def _sentiment_stance(analysis: dict[str, Any], threshold: float) -> Stance:
    score = analysis.get("composite_score")
    if not _is_number(score):
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
