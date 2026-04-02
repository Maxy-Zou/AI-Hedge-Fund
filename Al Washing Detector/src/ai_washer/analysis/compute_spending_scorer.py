"""Compute spending gap scorer.

Detects flat CapEx/cloud spending despite growing AI narrative, producing
a 0-100 gap score. Pure functions only -- no database access, no side effects.

Three public functions:
- count_cloud_mentions_by_year: Cloud keyword detection in filing sections
- compute_capex_keyword_gap: CapEx vs AI keyword growth divergence
- compute_compute_spending_score: Full signal scoring pipeline

Implements COMP-01 (CapEx from XBRL), COMP-02 (cloud partnership mentions
in filing text per Pitfall 6 -- not transcripts until Phase 7), and
COMP-03 (compute spending gap score).

Per D-05: YoY CapEx growth vs keyword growth comparison with cloud mention
detection as supplementary factor (70% CapEx weight, 30% cloud mentions).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from ai_washer.analysis.growth import build_yearly_series, compute_cagr
from ai_washer.analysis.keywords import (
    CLOUD_COMPUTE_KEYWORDS,
    compile_lexicon,
    count_keywords_in_text,
)
from ai_washer.analysis.normalization import sigmoid_normalize
from ai_washer.analysis.types import FilingForScoring, SignalResult

_SIGNAL_VERSION = "0.4.0"

# Sections to search for cloud/compute keywords
_CLOUD_SEARCH_SECTIONS = ("mda", "risk_factors", "business")


def count_cloud_mentions_by_year(
    filings: Sequence[FilingForScoring],
    cloud_patterns: list[tuple[re.Pattern[str], str, str]] | None = None,
) -> dict[int, int]:
    """Count cloud/compute keyword occurrences in filing sections by year.

    Searches across mda, risk_factors, and business sections. Skips None
    sections without error.

    Args:
        filings: Sequence of FilingForScoring with year and sections.
        cloud_patterns: Pre-compiled patterns. If None, compiled from
                        CLOUD_COMPUTE_KEYWORDS using compile_lexicon.

    Returns:
        Sorted dict mapping year to total cloud keyword count.
        Years with zero mentions are included if filings exist.
    """
    if not filings:
        return {}

    if cloud_patterns is None:
        cloud_patterns = compile_lexicon(CLOUD_COMPUTE_KEYWORDS, [])

    result: dict[int, int] = {}
    for filing in filings:
        total_count = 0
        for section_name in _CLOUD_SEARCH_SECTIONS:
            text = filing.sections.get(section_name)
            if text is None:
                continue
            matches = count_keywords_in_text(text, cloud_patterns)
            total_count += sum(m.count for m in matches)
        result[filing.year] = result.get(filing.year, 0) + total_count

    return dict(sorted(result.items()))


def compute_capex_keyword_gap(
    ai_keyword_counts_by_year: dict[int, float],
    capex_by_year: dict[int, int],
    cloud_mentions_by_year: dict[int, int],
    window_years: int = 3,
    scoring_year: int | None = None,
    capex_weight: float = 0.70,
    cloud_mention_weight: float = 0.30,
) -> tuple[float | None, dict]:
    """Compute the gap between AI keyword growth and investment growth.

    Investment growth is a weighted combination of CapEx growth (70%)
    and cloud mention growth (30%) per D-05.

    Args:
        ai_keyword_counts_by_year: Year -> total weighted AI keyword count.
        capex_by_year: Year -> CapEx in cents.
        cloud_mentions_by_year: Year -> cloud keyword count from filings.
        window_years: Number of years for growth window (default 3).
        scoring_year: End year. If None, uses max year from CapEx data.
        capex_weight: Weight for CapEx growth factor (default 0.70).
        cloud_mention_weight: Weight for cloud mention growth (default 0.30).

    Returns:
        Tuple of (gap_ratio, evidence_dict). gap_ratio is None if
        insufficient CapEx data. evidence_dict always has audit fields.
    """
    if not capex_by_year:
        return (None, {"error": "insufficient_capex_data"})

    sorted_capex_years = sorted(capex_by_year.keys())
    if len(sorted_capex_years) < 2:
        return (None, {"error": "insufficient_capex_data"})

    end_year = scoring_year if scoring_year is not None else sorted_capex_years[-1]
    start_year = end_year - window_years + 1

    # Validate we have data for start and end years
    if start_year not in capex_by_year or end_year not in capex_by_year:
        # Fall back to earliest and latest available years
        start_year = sorted_capex_years[0]
        end_year = sorted_capex_years[-1]

    years_span = end_year - start_year
    if years_span <= 0:
        return (None, {"error": "insufficient_capex_data"})

    # CapEx CAGR
    capex_start = capex_by_year[start_year]
    capex_end = capex_by_year[end_year]
    capex_cagr = compute_cagr(float(capex_start), float(capex_end), years_span)
    if capex_cagr is None:
        capex_cagr = 0.0

    # AI keyword CAGR
    kw_start = ai_keyword_counts_by_year.get(start_year)
    kw_end = ai_keyword_counts_by_year.get(end_year)
    if kw_start is not None and kw_end is not None and kw_start > 0:
        keyword_cagr = compute_cagr(kw_start, kw_end, years_span)
        if keyword_cagr is None:
            keyword_cagr = 0.0
    else:
        keyword_cagr = 0.0

    # Cloud mention CAGR
    cloud_start = cloud_mentions_by_year.get(start_year)
    cloud_end = cloud_mentions_by_year.get(end_year)
    if (
        cloud_start is not None
        and cloud_end is not None
        and cloud_start > 0
    ):
        cloud_cagr = compute_cagr(float(cloud_start), float(cloud_end), years_span)
        if cloud_cagr is None:
            cloud_cagr = 0.0
    else:
        cloud_cagr = 0.0

    # Combined investment growth factor
    capex_growth_factor = 1.0 + capex_cagr
    cloud_growth_factor = 1.0 + cloud_cagr
    investment_growth = (
        capex_weight * capex_growth_factor
        + cloud_mention_weight * cloud_growth_factor
    )

    # Clamp to prevent division by zero or negative
    if investment_growth <= 0:
        investment_growth = 0.01

    # Gap ratio: how much AI narrative outpaces investment
    ai_narrative_growth = 1.0 + keyword_cagr
    gap_ratio = ai_narrative_growth / investment_growth

    evidence = {
        "capex_growth_cagr": capex_cagr,
        "cloud_mention_growth": cloud_cagr,
        "keyword_growth_cagr": keyword_cagr,
        "combined_gap_ratio": gap_ratio,
        "capex_weight": capex_weight,
        "cloud_mention_weight": cloud_mention_weight,
        "window_start_year": start_year,
        "window_end_year": end_year,
        "window_years_actual": years_span,
    }

    return (gap_ratio, evidence)


def compute_compute_spending_score(
    filings: Sequence[FilingForScoring],
    capex_facts: Sequence[tuple[int, str, int]],
    ai_keyword_counts_by_year: dict[int, float],
    scoring_year: int | None = None,
    window_years: int = 3,
    capex_weight: float = 0.70,
    cloud_mention_weight: float = 0.30,
    sigmoid_midpoint: float = 1.0,
    sigmoid_steepness: float = 2.0,
) -> SignalResult | None:
    """Compute the compute spending gap score (0-100).

    Detects flat CapEx/cloud spending despite growing AI narrative.
    Companies with flat CapEx and growing AI keywords score high (70+).
    Companies with growing CapEx matching narrative growth score neutral (~50).

    Args:
        filings: Sequence of FilingForScoring for cloud mention detection.
        capex_facts: Sequence of (fiscal_year, fiscal_period, value_cents).
        ai_keyword_counts_by_year: Year -> total weighted AI keyword count
                                   (passed from SEC scoring pipeline).
        scoring_year: End year for scoring window. If None, auto-detected.
        window_years: Growth window size (default 3).
        capex_weight: Weight for CapEx in gap metric (default 0.70).
        cloud_mention_weight: Weight for cloud mentions (default 0.30).
        sigmoid_midpoint: Sigmoid midpoint for normalization (default 1.0).
        sigmoid_steepness: Sigmoid steepness for normalization (default 2.0).

    Returns:
        SignalResult with signal_type="compute_spending" and 0-100 score,
        or None if insufficient data.
    """
    # Build CapEx yearly series from XBRL facts
    capex_series = build_yearly_series(capex_facts)

    # Require at least 2 years of CapEx data
    if len(capex_series) < 2:
        return None

    # Require at least 2 years of keyword data
    if len(ai_keyword_counts_by_year) < 2:
        return None

    # Count cloud mentions by year from filing text
    cloud_mentions = count_cloud_mentions_by_year(filings)

    # Collect all unique cloud keywords found across all filings
    cloud_patterns = compile_lexicon(CLOUD_COMPUTE_KEYWORDS, [])
    all_cloud_keywords_found: set[str] = set()
    filings_with_any_mention = 0
    for filing in filings:
        filing_has_mention = False
        for section_name in _CLOUD_SEARCH_SECTIONS:
            text = filing.sections.get(section_name)
            if text is None:
                continue
            matches = count_keywords_in_text(text, cloud_patterns)
            for m in matches:
                all_cloud_keywords_found.add(m.keyword)
                filing_has_mention = True
        if filing_has_mention:
            filings_with_any_mention += 1

    # Compute the gap
    gap_ratio, gap_evidence = compute_capex_keyword_gap(
        ai_keyword_counts_by_year=ai_keyword_counts_by_year,
        capex_by_year=capex_series,
        cloud_mentions_by_year=cloud_mentions,
        window_years=window_years,
        scoring_year=scoring_year,
        capex_weight=capex_weight,
        cloud_mention_weight=cloud_mention_weight,
    )

    if gap_ratio is None:
        return None

    # Normalize to 0-100 via sigmoid
    score = sigmoid_normalize(gap_ratio, sigmoid_midpoint, sigmoid_steepness)

    # Build evidence
    evidence = {
        "signal_version": _SIGNAL_VERSION,
        "window_start_year": gap_evidence.get("window_start_year"),
        "window_end_year": gap_evidence.get("window_end_year"),
        "capex_data": {
            "by_year_cents": capex_series,
            "capex_growth_cagr": gap_evidence.get("capex_growth_cagr"),
            "xbrl_concept_used": "capex",
        },
        "cloud_mentions": {
            "by_year": cloud_mentions,
            "keywords_found": sorted(all_cloud_keywords_found),
            "data_source": "filing_text",  # NOT transcripts (Phase 7 enhancement)
        },
        "keyword_growth_cagr": gap_evidence.get("keyword_growth_cagr"),
        "scoring": {
            "capex_vs_keyword_ratio": gap_ratio,
            "capex_weight": capex_weight,
            "cloud_mention_weight": cloud_mention_weight,
            "combined_gap_score": score,
            "normalization_params": {
                "midpoint": sigmoid_midpoint,
                "steepness": sigmoid_steepness,
            },
        },
        "data_quality": {
            "capex_years_available": sorted(capex_series.keys()),
            "filings_with_cloud_mentions": filings_with_any_mention,
        },
    }

    return SignalResult(
        signal_type="compute_spending",
        score=score,
        evidence=evidence,
    )
