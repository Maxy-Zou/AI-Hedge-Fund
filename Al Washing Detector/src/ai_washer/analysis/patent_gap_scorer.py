"""Patent gap scorer: compares AI claim intensity trend to patent filing trend.

Pure function engine -- no DB access, no side effects. Follows the same pattern
as sec_filing_scorer.py and compute_spending_scorer.py.

High score = lots of AI claims, few patents (washing signal).
Low score = patent activity matches or exceeds claims (genuine).
"""

from __future__ import annotations

from ai_washer.analysis.growth import compute_cagr
from ai_washer.analysis.normalization import sigmoid_normalize
from ai_washer.analysis.types import SignalResult

_SIGNAL_VERSION = "0.5.0"
_MIN_YEARS = 2


def compute_patent_gap_score(
    patent_counts_by_year: dict[int, int],
    ai_claim_intensity_by_year: dict[int, float],
    scoring_year: int,
    window_years: int = 3,
    sigmoid_midpoint: float = 1.0,
    sigmoid_steepness: float = 2.0,
) -> SignalResult | None:
    """Compute patent gap: AI claim intensity trend vs patent filing trend.

    Args:
        patent_counts_by_year: {year: count} of AI-related patents granted.
        ai_claim_intensity_by_year: {year: weighted_keyword_count} from SEC filings.
        scoring_year: The year to score (end of window).
        window_years: Number of years to look back (default 3).
        sigmoid_midpoint: Ratio value mapping to ~50 score.
        sigmoid_steepness: Controls curve sharpness.

    Returns:
        SignalResult with signal_type="patent_gap" and score 0-100,
        or None if insufficient overlapping data.
    """
    end_year = scoring_year
    start_year = end_year - window_years

    # Check for sufficient overlapping data
    claim_years = {y for y in ai_claim_intensity_by_year if start_year <= y <= end_year}
    patent_years = {y for y in patent_counts_by_year if start_year <= y <= end_year}
    overlapping = claim_years & patent_years
    if len(overlapping) < _MIN_YEARS:
        return None

    # Get start and end values for CAGR
    start_claims = ai_claim_intensity_by_year.get(start_year)
    end_claims = ai_claim_intensity_by_year.get(end_year)
    if start_claims is None or end_claims is None:
        return None

    start_patents = patent_counts_by_year.get(start_year, 0)
    end_patents = patent_counts_by_year.get(end_year, 0)

    # CAGR with floor values to prevent division by zero
    claim_growth = compute_cagr(max(start_claims, 0.1), end_claims, window_years)
    patent_growth = compute_cagr(max(start_patents, 1), end_patents, window_years)

    # Build ratio: high claim growth / low patent growth = high score (washing)
    claim_factor = 1.0 + (claim_growth if claim_growth is not None else 0.0)
    patent_factor = 1.0 + (patent_growth if patent_growth is not None else 0.0)

    # Clamp patent_factor to prevent division by zero
    if patent_factor <= 0:
        patent_factor = 0.01

    ratio = claim_factor / patent_factor
    score = sigmoid_normalize(ratio, midpoint=sigmoid_midpoint, steepness=sigmoid_steepness)

    evidence = {
        "signal_version": _SIGNAL_VERSION,
        "claim_growth_cagr": claim_growth,
        "patent_growth_cagr": patent_growth,
        "gap_ratio": round(ratio, 4),
        "patent_counts": patent_counts_by_year,
        "ai_claim_intensity": {str(k): round(v, 2) for k, v in ai_claim_intensity_by_year.items()},
        "window": {"start": start_year, "end": end_year},
        "overlapping_years": sorted(overlapping),
    }

    return SignalResult(signal_type="patent_gap", score=score, evidence=evidence)
