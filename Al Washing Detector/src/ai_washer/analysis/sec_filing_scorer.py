"""SEC filing mismatch scorer.

Pure-function engine that computes keyword frequency growth vs R&D spending
growth over a 3-year rolling window, producing a 0-100 mismatch score per D-04.

Functions:
- compute_keyword_counts_by_year: Aggregate keyword frequency per fiscal year
- compute_filing_mismatch_ratio: Compute divergence ratio between keyword and R&D growth
- compute_sec_filing_score: Orchestrate full scoring pipeline to produce SignalResult

All functions are pure: typed inputs in, typed outputs out. No database access,
no side effects. Evidence dict follows the JSONB schema from research.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence

from ai_washer.analysis.growth import build_yearly_series, compute_cagr
from ai_washer.analysis.keywords import (
    DEFAULT_SECTION_WEIGHTS,
    SUBSTANTIVE_TERMS,
    VAGUE_BUZZWORDS,
    compile_lexicon,
    compute_section_weighted_frequency,
)
from ai_washer.analysis.normalization import sigmoid_normalize
from ai_washer.analysis.types import (
    FilingForScoring,
    KeywordFrequencyResult,
    SectionKeywordCounts,
    SignalResult,
)

_SIGNAL_VERSION = "0.4.0"

# Minimum years of overlapping data required to produce a score
_MIN_YEARS = 2


def compute_keyword_counts_by_year(
    filings: Sequence[FilingForScoring],
    lexicon_patterns: list[tuple[re.Pattern[str], str, str]] | None = None,
    section_weights: dict[str, float] | None = None,
) -> dict[int, KeywordFrequencyResult]:
    """Aggregate keyword frequency per fiscal year from filing data.

    Groups filings by `year` field (from period_of_report per Pitfall 5).
    For each year, calls `compute_section_weighted_frequency` on each filing,
    then combines results for that year (sum weighted counts, merge section counts).

    Args:
        filings: Sequence of FilingForScoring (immutable, year from period_of_report).
        lexicon_patterns: Pre-compiled patterns. If None, compiled from defaults.
        section_weights: Custom section weights. If None, uses DEFAULT_SECTION_WEIGHTS.

    Returns:
        Sorted dict mapping fiscal_year to KeywordFrequencyResult.
    """
    if not filings:
        return {}

    patterns = (
        lexicon_patterns
        if lexicon_patterns is not None
        else compile_lexicon(VAGUE_BUZZWORDS, SUBSTANTIVE_TERMS)
    )
    weights = section_weights if section_weights is not None else DEFAULT_SECTION_WEIGHTS

    # Group filings by year
    by_year: dict[int, list[FilingForScoring]] = defaultdict(list)
    for filing in filings:
        by_year[filing.year].append(filing)

    result: dict[int, KeywordFrequencyResult] = {}
    for year in sorted(by_year.keys()):
        year_filings = by_year[year]
        combined = _combine_filing_results(year_filings, patterns, weights)
        result[year] = combined

    return result


def _combine_filing_results(
    filings: list[FilingForScoring],
    patterns: list[tuple[re.Pattern[str], str, str]],
    section_weights: dict[str, float],
) -> KeywordFrequencyResult:
    """Combine keyword frequency results across multiple filings for one year.

    Each filing is scored independently, then results are merged:
    - total_weighted_count: sum across all filings
    - by_section: per-section counts summed
    - by_tier: aggregate counts summed
    - sections_available/missing: union across all filings
    """
    total_weighted = 0.0
    merged_sections: dict[str, SectionKeywordCounts] = {}
    merged_vague = 0
    merged_substantive = 0
    all_available: set[str] = set()
    all_missing: set[str] = set()

    for filing in filings:
        kfr = compute_section_weighted_frequency(
            filing.sections, patterns, section_weights
        )
        total_weighted += kfr.total_weighted_count
        merged_vague += kfr.by_tier.get("vague", 0)
        merged_substantive += kfr.by_tier.get("substantive", 0)

        for section_name, counts in kfr.by_section.items():
            if section_name in merged_sections:
                existing = merged_sections[section_name]
                merged_sections[section_name] = SectionKeywordCounts(
                    vague_count=existing.vague_count + counts.vague_count,
                    substantive_count=existing.substantive_count + counts.substantive_count,
                    total=existing.total + counts.total,
                )
            else:
                merged_sections[section_name] = SectionKeywordCounts(
                    vague_count=counts.vague_count,
                    substantive_count=counts.substantive_count,
                    total=counts.total,
                )

        all_available.update(kfr.sections_available)
        all_missing.update(kfr.sections_missing)

    # Sections that appear in both available and missing across filings
    # are considered available (at least one filing had the section)
    final_missing = all_missing - all_available

    return KeywordFrequencyResult(
        total_weighted_count=total_weighted,
        by_section=merged_sections,
        by_tier={"vague": merged_vague, "substantive": merged_substantive},
        sections_available=sorted(all_available),
        sections_missing=sorted(final_missing),
    )


def compute_filing_mismatch_ratio(
    keyword_counts_by_year: dict[int, float],
    rd_spend_by_year: dict[int, int],
    window_years: int = 3,
    scoring_year: int | None = None,
) -> tuple[float | None, dict]:
    """Compute the divergence ratio between keyword growth and R&D spending growth.

    Per D-03: 3-year rolling window. Per D-04: ratio = (1 + kw_cagr) / (1 + rd_cagr).

    Args:
        keyword_counts_by_year: Mapping of year to total_weighted_count (float).
        rd_spend_by_year: Mapping of year to R&D spending in cents (int).
        window_years: Rolling window size (default 3).
        scoring_year: Year to score. Defaults to max year in keyword data.

    Returns:
        Tuple of (ratio_or_none, evidence_dict). Evidence always populated.
    """
    if not keyword_counts_by_year:
        return None, {"error": "insufficient_keyword_data"}

    if not rd_spend_by_year:
        return None, {"error": "insufficient_rd_data"}

    end_year = scoring_year if scoring_year is not None else max(keyword_counts_by_year.keys())
    start_year = end_year - window_years

    # Look up start and end values for keywords
    start_kw = keyword_counts_by_year.get(start_year)
    end_kw = keyword_counts_by_year.get(end_year)
    if start_kw is None or end_kw is None:
        return None, {
            "error": "insufficient_keyword_data",
            "window_start_year": start_year,
            "window_end_year": end_year,
            "available_years": sorted(keyword_counts_by_year.keys()),
        }

    # Look up start and end values for R&D spending
    start_rd = rd_spend_by_year.get(start_year)
    end_rd = rd_spend_by_year.get(end_year)
    if start_rd is None or end_rd is None:
        return None, {
            "error": "insufficient_rd_data",
            "window_start_year": start_year,
            "window_end_year": end_year,
            "available_years": sorted(rd_spend_by_year.keys()),
        }

    # Compute CAGRs with floors to prevent zero-start issues
    kw_growth = compute_cagr(max(start_kw, 0.1), end_kw, window_years)
    rd_growth = compute_cagr(max(start_rd, 1), end_rd, window_years)

    # Compute ratio: (1 + kw_growth) / (1 + rd_growth)
    kw_factor = 1.0 + (kw_growth if kw_growth is not None else 0.0)
    rd_factor = 1.0 + (rd_growth if rd_growth is not None else 0.0)

    # Clamp rd_factor to prevent division by zero or negative
    if rd_factor <= 0:
        rd_factor = 0.01

    ratio = kw_factor / rd_factor

    evidence = {
        "keyword_growth_cagr": kw_growth,
        "rd_growth_cagr": rd_growth,
        "mismatch_ratio": ratio,
        "window_start_year": start_year,
        "window_end_year": end_year,
    }

    return ratio, evidence


def compute_sec_filing_score(
    filings: Sequence[FilingForScoring],
    rd_facts: Sequence[tuple[int, str, int]],
    scoring_year: int | None = None,
    window_years: int = 3,
    section_weights: dict[str, float] | None = None,
    sigmoid_midpoint: float = 1.0,
    sigmoid_steepness: float = 2.0,
) -> SignalResult | None:
    """Orchestrate the full SEC filing mismatch scoring pipeline.

    Pipeline: keyword counting -> yearly aggregation -> growth rate computation
    -> ratio -> sigmoid normalization -> SignalResult.

    Args:
        filings: Sequence of FilingForScoring (year from period_of_report).
        rd_facts: Sequence of (fiscal_year, fiscal_period, value_cents) tuples
                  from XBRLFact rows with concept="rd_expense".
        scoring_year: Year to produce score for. Defaults to max year in filings.
        window_years: Rolling window size (default 3).
        section_weights: Custom section weights. Defaults to DEFAULT_SECTION_WEIGHTS.
        sigmoid_midpoint: Midpoint for sigmoid normalization (default 1.0).
        sigmoid_steepness: Steepness for sigmoid curve (default 2.0).

    Returns:
        SignalResult with signal_type="sec_filing" and 0-100 score, or None
        if insufficient data (< 2 years of keyword or R&D data).
    """
    weights = section_weights if section_weights is not None else DEFAULT_SECTION_WEIGHTS

    # Step 1: Compute keyword counts by year
    kw_by_year = compute_keyword_counts_by_year(filings, section_weights=weights)
    if not kw_by_year:
        return None

    # Step 2: Build R&D yearly series
    rd_by_year = build_yearly_series(rd_facts)
    if not rd_by_year:
        return None

    # Determine scoring year
    end_year = scoring_year if scoring_year is not None else max(kw_by_year.keys())
    start_year = end_year - window_years

    # Step 3: Check minimum data requirement
    # Need at least _MIN_YEARS of keyword data and _MIN_YEARS of R&D data
    # overlapping with the window [start_year, end_year]
    kw_years_in_window = [
        y for y in kw_by_year if start_year <= y <= end_year
    ]
    rd_years_in_window = [
        y for y in rd_by_year if start_year <= y <= end_year
    ]

    if len(kw_years_in_window) < _MIN_YEARS or len(rd_years_in_window) < _MIN_YEARS:
        return None

    # Step 4: Extract total_weighted_count per year for mismatch ratio
    kw_totals: dict[int, float] = {
        year: kfr.total_weighted_count for year, kfr in kw_by_year.items()
    }

    # Step 5: Compute mismatch ratio
    ratio, ratio_evidence = compute_filing_mismatch_ratio(
        kw_totals, rd_by_year, window_years=window_years, scoring_year=end_year
    )

    if ratio is None:
        return None

    # Step 6: Normalize via sigmoid
    score = sigmoid_normalize(ratio, midpoint=sigmoid_midpoint, steepness=sigmoid_steepness)

    # Step 7: Build evidence dict per research JSONB schema
    # Aggregate by_section across all years for evidence
    aggregated_by_section: dict[str, dict[str, int]] = {}
    all_missing_sections: set[str] = set()
    total_filing_count = len(filings)

    for _year, kfr in kw_by_year.items():
        for section_name, counts in kfr.by_section.items():
            if section_name not in aggregated_by_section:
                aggregated_by_section[section_name] = {"vague": 0, "substantive": 0}
            aggregated_by_section[section_name]["vague"] += counts.vague_count
            aggregated_by_section[section_name]["substantive"] += counts.substantive_count
        all_missing_sections.update(kfr.sections_missing)

    # Build by_year evidence with per-year breakdown
    by_year_evidence: dict[str, dict[str, float | int]] = {}
    for year, kfr in kw_by_year.items():
        by_year_evidence[str(year)] = {
            "vague": kfr.by_tier.get("vague", 0),
            "substantive": kfr.by_tier.get("substantive", 0),
            "total_weighted": kfr.total_weighted_count,
        }

    # Build R&D spend evidence
    rd_spend_evidence: dict[str, int] = {
        str(year): value for year, value in sorted(rd_by_year.items())
    }

    evidence = {
        "signal_version": _SIGNAL_VERSION,
        "window_start_year": start_year,
        "window_end_year": end_year,
        "keyword_counts": {
            "by_year": by_year_evidence,
            "by_section": aggregated_by_section,
            "section_weights_used": weights,
        },
        "financial_data": {
            "rd_spend_cents": rd_spend_evidence,
            "rd_growth_cagr": ratio_evidence.get("rd_growth_cagr"),
        },
        "scoring": {
            "keyword_growth_cagr": ratio_evidence.get("keyword_growth_cagr"),
            "mismatch_ratio": ratio,
            "raw_sigmoid_output": score,
            "normalization_params": {
                "midpoint": sigmoid_midpoint,
                "steepness": sigmoid_steepness,
            },
        },
        "data_quality": {
            "filings_analyzed": total_filing_count,
            "years_with_data": sorted(kw_by_year.keys()),
            "missing_sections": sorted(all_missing_sections),
        },
    }

    return SignalResult(
        signal_type="sec_filing",
        score=score,
        evidence=evidence,
    )
