"""Job mismatch scorer: compares AI claim intensity to actual AI hiring activity.

Pure function engine -- no DB access, no side effects. Follows the same pattern
as github_activity_scorer.py and patent_gap_scorer.py.

High score = lots of AI claims, few genuine AI hires (washing signal).
Low score = hiring activity matches claims (genuine AI development).

Sub-factors (each 0.0-1.0):
  - hiring_intensity: raw AI role count, capped at 20 for full credit
  - specificity: ratio of AI roles to total roles
  - marketing_ratio: fraction of marketing/fluff roles
  - ghost_penalty: ghost_ratio scaled by weight, reduces job_factor

These combine into a weighted job_factor, which is compared against
a normalized claim_factor to produce the gap_ratio fed into sigmoid_normalize.
"""

from __future__ import annotations

from ai_washer.analysis.normalization import sigmoid_normalize
from ai_washer.analysis.types import SignalResult

_SIGNAL_VERSION = "0.8.0"


def compute_job_mismatch_score(
    ai_role_count: int,
    marketing_role_count: int,
    total_role_count: int,
    ghost_ratio: float,
    ai_claim_intensity: float,
    scoring_year: int,
    ghost_penalty_weight: float = 0.20,
    engineering_weight: float = 0.40,
    hiring_intensity_weight: float = 0.40,
    sigmoid_midpoint: float = 1.0,
    sigmoid_steepness: float = 2.0,
) -> SignalResult | None:
    """Compute job mismatch gap score relative to AI claim intensity.

    Args:
        ai_role_count: Number of genuine AI/ML engineering roles found.
        marketing_role_count: Number of marketing/fluff AI-titled roles.
        total_role_count: Total AI-related job postings (engineering + marketing).
        ghost_ratio: Fraction of postings detected as ghost jobs (0.0-1.0).
        ai_claim_intensity: Weighted keyword count from SEC filings.
        scoring_year: The year being scored.
        ghost_penalty_weight: How much ghost_ratio penalizes job_factor (default 0.20).
        engineering_weight: Weight for specificity sub-factor (default 0.40).
        hiring_intensity_weight: Weight for hiring_intensity sub-factor (default 0.40).
        sigmoid_midpoint: Ratio value mapping to ~50 score.
        sigmoid_steepness: Controls curve sharpness.

    Returns:
        SignalResult with signal_type="job_mismatch" and score 0-100,
        or None if no AI claims to compare against.
    """
    # No claims = nothing to measure a gap against
    if ai_claim_intensity <= 0:
        return None

    # Normalize claims to ~1.0 range, cap at 2.0 (same as github scorer)
    claim_factor = min(ai_claim_intensity / 50.0, 2.0)

    # Zero roles + claims = near-max washing signal
    if total_role_count == 0:
        evidence = _build_evidence(
            ai_role_count=0,
            marketing_role_count=0,
            total_role_count=0,
            ghost_ratio=ghost_ratio,
            ai_claim_intensity=ai_claim_intensity,
            sub_factors={
                "hiring_intensity": 0.0,
                "specificity": 0.0,
                "marketing_ratio": 0.0,
                "ghost_penalty": 0.0,
            },
            job_factor=0.0,
            claim_factor=claim_factor,
            gap_ratio=None,
            scoring_year=scoring_year,
        )
        return SignalResult(
            signal_type="job_mismatch",
            score=95,
            evidence=evidence,
        )

    # Compute sub-factors, each 0.0-1.0
    hiring_intensity = min(ai_role_count / 20.0, 1.0)
    specificity = ai_role_count / max(total_role_count, 1)
    marketing_ratio = marketing_role_count / max(total_role_count, 1)
    ghost_penalty = ghost_ratio * ghost_penalty_weight

    # Weighted combination, penalized by ghosts
    job_factor = (
        hiring_intensity * hiring_intensity_weight + specificity * engineering_weight
    ) * (1.0 - ghost_penalty)

    # Clamp minimum to prevent division by zero (same as patent scorer)
    job_factor_clamped = max(job_factor, 0.01)

    gap_ratio = claim_factor / job_factor_clamped
    score = sigmoid_normalize(
        gap_ratio, midpoint=sigmoid_midpoint, steepness=sigmoid_steepness
    )

    evidence = _build_evidence(
        ai_role_count=ai_role_count,
        marketing_role_count=marketing_role_count,
        total_role_count=total_role_count,
        ghost_ratio=ghost_ratio,
        ai_claim_intensity=ai_claim_intensity,
        sub_factors={
            "hiring_intensity": round(hiring_intensity, 4),
            "specificity": round(specificity, 4),
            "marketing_ratio": round(marketing_ratio, 4),
            "ghost_penalty": round(ghost_penalty, 4),
        },
        job_factor=round(job_factor, 4),
        claim_factor=round(claim_factor, 4),
        gap_ratio=round(gap_ratio, 4),
        scoring_year=scoring_year,
    )

    return SignalResult(
        signal_type="job_mismatch",
        score=score,
        evidence=evidence,
    )


def _build_evidence(
    *,
    ai_role_count: int,
    marketing_role_count: int,
    total_role_count: int,
    ghost_ratio: float,
    ai_claim_intensity: float,
    sub_factors: dict[str, float],
    job_factor: float,
    claim_factor: float,
    gap_ratio: float | None,
    scoring_year: int,
) -> dict:
    """Build the evidence dict for auditability.

    Separated into a helper to keep the main function focused on scoring logic
    and avoid duplicating evidence construction between the zero-roles and
    normal code paths.
    """
    return {
        "signal_version": _SIGNAL_VERSION,
        "ai_role_count": ai_role_count,
        "marketing_role_count": marketing_role_count,
        "total_role_count": total_role_count,
        "ghost_ratio": round(ghost_ratio, 4),
        "ai_claim_intensity": round(ai_claim_intensity, 2),
        "sub_factors": sub_factors,
        "job_factor": round(job_factor, 4),
        "claim_factor": round(claim_factor, 4),
        "gap_ratio": gap_ratio,
        "scoring_year": scoring_year,
    }
