"""GitHub activity scorer: compares AI claim intensity to GitHub ML activity.

Pure function engine -- no DB access, no side effects. Follows the same pattern
as patent_gap_scorer.py and sec_filing_scorer.py.

High score = lots of AI claims, little GitHub ML activity (washing signal).
Low score = GitHub activity matches claims (genuine AI development).

Sub-factors (each 0.0-1.0):
  - repo_factor: raw repo count, capped at 20 repos for full credit
  - language_factor: ratio of ML-language repos (Python, Julia, R, etc.)
  - recency_factor: how recently code was pushed, decaying over time
  - framework_factor: number of ML frameworks detected (TensorFlow, PyTorch, etc.)

These combine into a weighted github_factor, which is compared against
a normalized claim_factor to produce the gap_ratio fed into sigmoid_normalize.
"""

from __future__ import annotations

from ai_washer.analysis.normalization import sigmoid_normalize
from ai_washer.analysis.types import SignalResult

_SIGNAL_VERSION = "0.6.0"


def compute_github_activity_score(
    repo_count: int,
    ml_language_ratio: float,
    days_since_last_push: int | None,
    ml_frameworks_found: list[str],
    ai_claim_intensity: float,
    scoring_year: int,
    recency_decay_days: int = 365,
    sigmoid_midpoint: float = 1.0,
    sigmoid_steepness: float = 2.0,
) -> SignalResult | None:
    """Compute GitHub activity gap score relative to AI claim intensity.

    Args:
        repo_count: Number of non-archived public repos in the org.
        ml_language_ratio: Fraction of repos using ML languages (0.0-1.0).
        days_since_last_push: Days since most recent push, or None if no repos.
        ml_frameworks_found: List of detected ML framework names.
        ai_claim_intensity: Weighted keyword count from SEC filings.
        scoring_year: The year being scored.
        recency_decay_days: Days until recency_factor decays to 0 (default 365).
        sigmoid_midpoint: Ratio value mapping to ~50 score.
        sigmoid_steepness: Controls curve sharpness.

    Returns:
        SignalResult with signal_type="github_activity" and score 0-100,
        or None if insufficient data to compare.
    """
    # No claims = nothing to measure a gap against
    if ai_claim_intensity <= 0:
        return None

    # Zero repos + claims = near-max washing signal
    if repo_count == 0:
        evidence = {
            "signal_version": _SIGNAL_VERSION,
            "repo_count": 0,
            "ml_language_ratio": 0.0,
            "days_since_last_push": None,
            "ml_frameworks_found": [],
            "ai_claim_intensity": round(ai_claim_intensity, 2),
            "sub_factors": {
                "repo_factor": 0.0,
                "language_factor": 0.0,
                "recency_factor": 0.0,
                "framework_factor": 0.0,
            },
            "github_factor": 0.0,
            "claim_factor": round(min(ai_claim_intensity / 50.0, 2.0), 4),
            "gap_ratio": None,
            "scoring_year": scoring_year,
        }
        return SignalResult(
            signal_type="github_activity",
            score=95,
            evidence=evidence,
        )

    # Compute four sub-factors, each 0.0-1.0
    repo_factor = min(repo_count / 20.0, 1.0)
    language_factor = ml_language_ratio
    recency_factor = (
        max(0.0, 1.0 - (days_since_last_push / recency_decay_days))
        if days_since_last_push is not None
        else 0.0
    )
    framework_factor = min(len(ml_frameworks_found) / 3.0, 1.0)

    # Weighted average of sub-factors
    github_factor = (
        repo_factor * 0.2
        + language_factor * 0.3
        + recency_factor * 0.3
        + framework_factor * 0.2
    )

    # Clamp minimum to prevent division by zero
    github_factor_clamped = max(github_factor, 0.01)

    # Normalize claims to ~1.0 range, cap at 2.0
    claim_factor = min(ai_claim_intensity / 50.0, 2.0)

    gap_ratio = claim_factor / github_factor_clamped
    score = sigmoid_normalize(
        gap_ratio, midpoint=sigmoid_midpoint, steepness=sigmoid_steepness
    )

    evidence = {
        "signal_version": _SIGNAL_VERSION,
        "repo_count": repo_count,
        "ml_language_ratio": ml_language_ratio,
        "days_since_last_push": days_since_last_push,
        "ml_frameworks_found": list(ml_frameworks_found),
        "ai_claim_intensity": round(ai_claim_intensity, 2),
        "sub_factors": {
            "repo_factor": round(repo_factor, 4),
            "language_factor": round(language_factor, 4),
            "recency_factor": round(recency_factor, 4),
            "framework_factor": round(framework_factor, 4),
        },
        "github_factor": round(github_factor, 4),
        "claim_factor": round(claim_factor, 4),
        "gap_ratio": round(gap_ratio, 4),
        "scoring_year": scoring_year,
    }

    return SignalResult(
        signal_type="github_activity",
        score=score,
        evidence=evidence,
    )
