"""Pydantic type contracts and shared dataclasses for scoring inputs/outputs.

Defines the canonical types consumed by both the SEC filing scorer (Plan 02)
and compute spending scorer (Plan 03). FilingForScoring is defined here as the
single shared type to eliminate parallel-wave type ownership ambiguity.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class FilingForScoring:
    """Immutable input for scoring functions. Shared by both SEC and compute scorers.

    year: from period_of_report.year (not filing_date) per Pitfall 5
    sections: dict with keys "mda", "risk_factors", "business", etc. Values may be None.
    """

    year: int
    sections: dict[str, str | None]


class KeywordLexicon(BaseModel):
    """Two-tier keyword classification per D-02.

    vague: Tier 1 buzzwords that indicate marketing speak
    substantive: Tier 2 technical terms that indicate real AI work
    """

    vague: list[str]
    substantive: list[str]


class SectionKeywordCounts(BaseModel):
    """Per-section keyword count breakdown."""

    vague_count: int = 0
    substantive_count: int = 0
    total: int = 0


class KeywordFrequencyResult(BaseModel):
    """Result of section-weighted keyword frequency analysis.

    total_weighted_count: weighted sum across sections
    by_section: per-section breakdown of vague/substantive counts
    by_tier: aggregate counts across all sections {"vague": N, "substantive": M}
    sections_available: sections that had valid text (>= 500 chars)
    sections_missing: sections that were None or too short
    """

    total_weighted_count: float
    by_section: dict[str, SectionKeywordCounts]
    by_tier: dict[str, int]
    sections_available: list[str]
    sections_missing: list[str]


class GrowthRateResult(BaseModel):
    """Result of growth rate computation.

    keyword_growth: CAGR of keyword frequency over time (None if insufficient data)
    spending_growth: CAGR of financial spending over time (None if insufficient data)
    window_years: number of years in the growth window
    start_year: first year in window
    end_year: last year in window
    """

    keyword_growth: float | None
    spending_growth: float | None
    window_years: int
    start_year: int
    end_year: int


class SignalResult(BaseModel):
    """Output of a signal scoring function.

    signal_type: "sec_filing" or "compute_spending"
    score: 0-100 integer risk score
    evidence: full JSONB evidence dict for auditability per D-07
    """

    signal_type: str
    score: int
    evidence: dict
