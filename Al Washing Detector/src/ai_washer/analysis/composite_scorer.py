"""Pure composite scoring with graceful degradation.

Combines up to 6 individual signal scores into a single weighted-average
composite score (0-100). When signals are missing, weights are renormalized
so available signals still produce a valid composite. Confidence reflects
the fraction of total weight covered by available signals.

This module is pure (no database access, no side effects) and fully testable
in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_washer.analysis.types import SignalResult
from ai_washer.config import SignalWeights

# Maps SignalResult.signal_type to the corresponding SignalWeights field name.
# Two mismatches exist by design:
#   - "earnings_vagueness" -> "earnings_call" (signal measures vagueness, weight named for source)
#   - "job_mismatch" -> "job_posting" (signal measures mismatch, weight named for source)
SIGNAL_TYPE_TO_WEIGHT_KEY: dict[str, str] = {
    "sec_filing": "sec_filing",
    "patent_gap": "patent_gap",
    "earnings_vagueness": "earnings_call",
    "job_mismatch": "job_posting",
    "github_activity": "github_activity",
    "compute_spending": "compute_spending",
}

ALL_SIGNAL_TYPES: list[str] = list(SIGNAL_TYPE_TO_WEIGHT_KEY.keys())


@dataclass(frozen=True)
class CompositeResult:
    """Immutable result of composite scoring.

    Attributes:
        score: Weighted average risk score clamped to [0, 100].
        confidence: Sum of original weights for available signals (0.0-1.0).
        risk_band: Classification string based on score thresholds.
        signal_breakdown: Per-signal scores {signal_type: score}.
        weights_used: Renormalized weights actually applied {weight_key: weight}.
        signals_available: Signal types that contributed to the composite.
        signals_missing: Signal types that were unavailable.
    """

    score: int
    confidence: float
    risk_band: str
    signal_breakdown: dict[str, int]
    weights_used: dict[str, float]
    signals_available: list[str]
    signals_missing: list[str]


def classify_risk_band(
    score: int,
    low: int = 30,
    high: int = 60,
    strong: int = 80,
) -> str:
    """Classify a composite score into a risk band.

    Args:
        score: Composite score (0-100).
        low: Upper bound (exclusive) for "genuine" band.
        high: Upper bound (exclusive) for "mixed" band.
        strong: Upper bound (exclusive) for "significant_risk" band.

    Returns:
        One of "genuine", "mixed", "significant_risk", "strong_short".
    """
    if score < low:
        return "genuine"
    if score < high:
        return "mixed"
    if score < strong:
        return "significant_risk"
    return "strong_short"


def compute_composite_score(
    signal_results: list[SignalResult],
    weights: SignalWeights,
    low_risk_threshold: int = 30,
    high_risk_threshold: int = 60,
    strong_short_threshold: int = 80,
) -> CompositeResult | None:
    """Compute weighted-average composite score from individual signal results.

    When signals are missing, the remaining weights are renormalized to sum
    to 1.0 so that partial coverage still produces a valid composite. The
    confidence field reflects what fraction of the total weight was covered.

    Args:
        signal_results: Individual signal scores (may be fewer than 6).
        weights: Signal weight configuration.
        low_risk_threshold: Upper bound for "genuine" band.
        high_risk_threshold: Upper bound for "mixed" band.
        strong_short_threshold: Upper bound for "strong_short" band.

    Returns:
        CompositeResult with weighted score and metadata, or None if no
        signals are available.
    """
    if not signal_results:
        return None

    # Build lookup of available signal scores
    available: dict[str, int] = {}
    for sr in signal_results:
        if sr.signal_type in SIGNAL_TYPE_TO_WEIGHT_KEY:
            available[sr.signal_type] = sr.score

    if not available:
        return None

    # Look up original weights for available signals
    weight_lookup: dict[str, float] = {}
    for signal_type in available:
        weight_key = SIGNAL_TYPE_TO_WEIGHT_KEY[signal_type]
        weight_lookup[signal_type] = getattr(weights, weight_key)

    # Confidence = sum of original weights for available signals
    confidence = sum(weight_lookup.values())

    # Renormalize weights to sum to 1.0
    renormalized: dict[str, float] = {
        st: w / confidence for st, w in weight_lookup.items()
    }

    # Compute weighted average
    raw_score = sum(
        available[st] * renormalized[st] for st in available
    )

    # Clamp to [0, 100] and round
    clamped = max(0.0, min(100.0, raw_score))
    final_score = round(clamped)

    # Build output
    signals_available = sorted(available.keys())
    signals_missing = sorted(
        st for st in ALL_SIGNAL_TYPES if st not in available
    )

    # weights_used keyed by weight field name (not signal type)
    weights_used = {
        SIGNAL_TYPE_TO_WEIGHT_KEY[st]: renormalized[st]
        for st in available
    }

    risk_band = classify_risk_band(
        final_score,
        low=low_risk_threshold,
        high=high_risk_threshold,
        strong=strong_short_threshold,
    )

    return CompositeResult(
        score=final_score,
        confidence=confidence,
        risk_band=risk_band,
        signal_breakdown={st: available[st] for st in signals_available},
        weights_used=weights_used,
        signals_available=signals_available,
        signals_missing=signals_missing,
    )
