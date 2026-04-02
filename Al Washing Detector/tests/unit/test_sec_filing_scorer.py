"""Unit tests for SEC filing mismatch scorer.

Tests the pure-function scoring engine that computes keyword frequency
growth vs R&D spending growth over a 3-year rolling window, producing
a 0-100 mismatch score per D-04.
"""

from __future__ import annotations

import pytest

from ai_washer.analysis.types import FilingForScoring, KeywordFrequencyResult, SignalResult
from ai_washer.analysis.sec_filing_scorer import (
    compute_filing_mismatch_ratio,
    compute_keyword_counts_by_year,
    compute_sec_filing_score,
)


# ---------------------------------------------------------------------------
# Helpers: build realistic filing fixtures
# ---------------------------------------------------------------------------

# Text with vague buzzwords (> 500 chars for section validation)
_VAGUE_TEXT = (
    "Our company is leveraging ai to transform our operations. "
    "We have deployed ai-powered solutions across all departments. "
    "Our ai-driven platform delivers ai-enabled features that are "
    "cutting-edge ai and revolutionary ai. We are an ai-first company "
    "with state-of-the-art ai capabilities and world-class ai solutions. "
    "Our ai platform powers intelligent automation and cognitive computing "
    "with predictive analytics and smart technology. Next-generation ai "
    "is at the core of our ai transformation and ai strategy. "
    "This ai initiative represents our commitment to powered by ai "
    "industry-leading ai and machine learning capabilities. "
) * 3  # Repeat to exceed 500 chars


# Text with substantive terms (> 500 chars)
_SUBSTANTIVE_TEXT = (
    "We operate a neural network training pipeline for deep learning "
    "models using our gpu cluster for model training and model inference. "
    "Our transformer model processes natural language processing tasks "
    "with fine-tuning on custom training data. The compute infrastructure "
    "supports computer vision and reinforcement learning workloads. "
    "Our mlops platform handles model deployment with feature engineering "
    "and hyperparameter tuning across large language model architectures. "
    "We use vector database for embedding storage and retrieval. "
    "Our training pipeline leverages attention mechanism and tokenization. "
) * 3


# Mixed text with some vague and some substantive
_MIXED_TEXT = (
    "Our ai-powered platform uses neural network and deep learning "
    "for ai-driven solutions. We leverage transformer model training "
    "with gpu cluster compute infrastructure. The ai-enabled system "
    "supports model inference and natural language processing. "
    "Our ai capabilities include fine-tuning and model deployment. "
    "We are leveraging ai alongside compute infrastructure and mlops. "
    "Our ai strategy involves training pipeline and feature engineering. "
) * 4


def _make_filings(
    years: list[int],
    text: str,
    sections: list[str] | None = None,
) -> list[FilingForScoring]:
    """Create FilingForScoring fixtures for given years with same text."""
    section_keys = sections or ["mda", "risk_factors", "business"]
    return [
        FilingForScoring(
            year=year,
            sections={s: text for s in section_keys},
        )
        for year in years
    ]


def _make_rd_facts(
    data: dict[int, int],
) -> list[tuple[int, str, int]]:
    """Create R&D fact tuples from year->value_cents mapping."""
    return [(year, "FY", value) for year, value in sorted(data.items())]


# ---------------------------------------------------------------------------
# Tests: compute_keyword_counts_by_year
# ---------------------------------------------------------------------------


class TestComputeKeywordCountsByYear:
    """Tests for compute_keyword_counts_by_year function."""

    def test_four_years_returns_dict_mapping_year_to_result(self) -> None:
        """4 years of filing data returns dict[int, KeywordFrequencyResult]."""
        filings = _make_filings([2020, 2021, 2022, 2023], _VAGUE_TEXT)
        result = compute_keyword_counts_by_year(filings)
        assert isinstance(result, dict)
        assert set(result.keys()) == {2020, 2021, 2022, 2023}
        for year, kfr in result.items():
            assert isinstance(kfr, KeywordFrequencyResult)
            assert kfr.total_weighted_count > 0

    def test_groups_by_period_of_report_year(self) -> None:
        """Filings grouped by year field (from period_of_report, not filing_date)."""
        # Two filings in 2022, one in 2023 -- verify grouping
        filings = [
            FilingForScoring(year=2022, sections={"mda": _VAGUE_TEXT, "risk_factors": _VAGUE_TEXT, "business": _VAGUE_TEXT}),
            FilingForScoring(year=2022, sections={"mda": _VAGUE_TEXT, "risk_factors": _VAGUE_TEXT, "business": _VAGUE_TEXT}),
            FilingForScoring(year=2023, sections={"mda": _VAGUE_TEXT, "risk_factors": _VAGUE_TEXT, "business": _VAGUE_TEXT}),
        ]
        result = compute_keyword_counts_by_year(filings)
        assert set(result.keys()) == {2022, 2023}
        # 2022 should have higher weighted count (two filings combined)
        assert result[2022].total_weighted_count > result[2023].total_weighted_count

    def test_multiple_filings_per_year_combines_counts(self) -> None:
        """Multiple filings in same year have their weighted counts combined."""
        single_filing = _make_filings([2023], _VAGUE_TEXT)
        double_filing = _make_filings([2023, 2023], _VAGUE_TEXT)

        single_result = compute_keyword_counts_by_year(single_filing)
        double_result = compute_keyword_counts_by_year(double_filing)

        # Double should have roughly 2x the weighted count
        assert double_result[2023].total_weighted_count > single_result[2023].total_weighted_count

    def test_none_sections_skipped(self) -> None:
        """Filings with None sections skip those sections gracefully."""
        filings = [
            FilingForScoring(
                year=2023,
                sections={"mda": _VAGUE_TEXT, "risk_factors": None, "business": None},
            ),
        ]
        result = compute_keyword_counts_by_year(filings)
        assert 2023 in result
        kfr = result[2023]
        assert "mda" in kfr.sections_available
        assert "risk_factors" in kfr.sections_missing
        assert "business" in kfr.sections_missing

    def test_empty_filings_returns_empty_dict(self) -> None:
        """No filings returns empty dict."""
        result = compute_keyword_counts_by_year([])
        assert result == {}


# ---------------------------------------------------------------------------
# Tests: compute_filing_mismatch_ratio
# ---------------------------------------------------------------------------


class TestComputeFilingMismatchRatio:
    """Tests for compute_filing_mismatch_ratio function."""

    def test_high_keyword_growth_low_rd_returns_ratio_above_one(self) -> None:
        """keyword_growth=0.36, rd_growth=0.02 -> ratio > 1.0."""
        # Build data that yields these approximate CAGRs
        # keyword: 100 -> ~251 over 3 years (CAGR ~0.36)
        # R&D: 100 -> ~106 over 3 years (CAGR ~0.02)
        kw = {2020: 100.0, 2021: 136.0, 2022: 185.0, 2023: 251.0}
        rd = {2020: 10000, 2021: 10200, 2022: 10404, 2023: 10612}

        ratio, evidence = compute_filing_mismatch_ratio(kw, rd, window_years=3, scoring_year=2023)
        assert ratio is not None
        assert ratio > 1.0
        assert evidence.get("mismatch_ratio") == ratio

    def test_proportional_growth_returns_ratio_near_one(self) -> None:
        """keyword_growth=0.10, rd_growth=0.10 -> ratio ~1.0."""
        kw = {2020: 100.0, 2021: 110.0, 2022: 121.0, 2023: 133.1}
        rd = {2020: 10000, 2021: 11000, 2022: 12100, 2023: 13310}

        ratio, evidence = compute_filing_mismatch_ratio(kw, rd, window_years=3, scoring_year=2023)
        assert ratio is not None
        assert 0.9 < ratio < 1.1  # Close to 1.0

    def test_no_rd_data_returns_none_with_error(self) -> None:
        """Missing R&D data for window years returns (None, evidence_with_error)."""
        kw = {2020: 100.0, 2021: 110.0, 2022: 121.0, 2023: 133.1}
        rd: dict[int, int] = {}

        ratio, evidence = compute_filing_mismatch_ratio(kw, rd, window_years=3, scoring_year=2023)
        assert ratio is None
        assert "error" in evidence
        assert "rd" in evidence["error"].lower()

    def test_no_keyword_data_returns_none_with_error(self) -> None:
        """Missing keyword data for window years returns (None, evidence_with_error)."""
        kw: dict[int, float] = {}
        rd = {2020: 10000, 2021: 11000, 2022: 12100, 2023: 13310}

        ratio, evidence = compute_filing_mismatch_ratio(kw, rd, window_years=3, scoring_year=2023)
        assert ratio is None
        assert "error" in evidence
        assert "keyword" in evidence["error"].lower()

    def test_uses_growth_factor_formula(self) -> None:
        """Ratio = (1 + keyword_growth) / (1 + rd_growth) per research."""
        # Known: kw CAGR ~0.20, rd CAGR ~0.05
        # Expected ratio: 1.20 / 1.05 ~= 1.143
        kw = {2020: 100.0, 2023: 172.8}  # (172.8/100)^(1/3) - 1 = 0.20
        rd = {2020: 10000, 2023: 11576}  # (11576/10000)^(1/3) - 1 ~= 0.05

        ratio, evidence = compute_filing_mismatch_ratio(kw, rd, window_years=3, scoring_year=2023)
        assert ratio is not None
        # (1 + 0.20) / (1 + 0.05) ~= 1.143
        assert 1.10 < ratio < 1.20

    def test_evidence_contains_required_fields(self) -> None:
        """Evidence dict contains keyword_growth_cagr, rd_growth_cagr, etc."""
        kw = {2020: 100.0, 2023: 150.0}
        rd = {2020: 10000, 2023: 12000}

        ratio, evidence = compute_filing_mismatch_ratio(kw, rd, window_years=3, scoring_year=2023)
        assert "keyword_growth_cagr" in evidence
        assert "rd_growth_cagr" in evidence
        assert "mismatch_ratio" in evidence
        assert "window_start_year" in evidence
        assert "window_end_year" in evidence


# ---------------------------------------------------------------------------
# Tests: compute_sec_filing_score
# ---------------------------------------------------------------------------


class TestComputeSecFilingScore:
    """Tests for compute_sec_filing_score orchestrator function."""

    def test_returns_signal_result_with_sec_filing_type(self) -> None:
        """Returns SignalResult with signal_type='sec_filing'."""
        filings = _make_filings([2020, 2021, 2022, 2023], _VAGUE_TEXT)
        rd_facts = _make_rd_facts({2020: 10000, 2021: 10200, 2022: 10404, 2023: 10612})

        result = compute_sec_filing_score(filings, rd_facts)
        assert result is not None
        assert isinstance(result, SignalResult)
        assert result.signal_type == "sec_filing"

    def test_high_mismatch_score_above_70(self) -> None:
        """Growing keywords with flat R&D produces score > 70."""
        # Year-over-year text gets progressively more keyword-dense
        # 2020: minimal keywords, 2023: heavy keywords -> steep CAGR
        filings = (
            _make_filings([2020], _MIXED_TEXT)
            + _make_filings([2021], _VAGUE_TEXT + _VAGUE_TEXT)
            + _make_filings([2022], _VAGUE_TEXT + _VAGUE_TEXT + _VAGUE_TEXT + _VAGUE_TEXT)
            + _make_filings([2023], _VAGUE_TEXT * 8)
        )
        # Flat R&D spending (< 1% growth)
        rd_facts = _make_rd_facts({2020: 100000, 2021: 100500, 2022: 101000, 2023: 101500})

        result = compute_sec_filing_score(filings, rd_facts)
        assert result is not None
        assert result.score > 70, f"Expected > 70 for high mismatch, got {result.score}"

    def test_neutral_proportional_growth_score_around_50(self) -> None:
        """Proportional AI talk and R&D growth produces score ~50."""
        # Same text each year (no keyword growth) with flat R&D
        filings = _make_filings([2020, 2021, 2022, 2023], _MIXED_TEXT)
        # Flat R&D matches flat keywords
        rd_facts = _make_rd_facts({2020: 100000, 2021: 100000, 2022: 100000, 2023: 100000})

        result = compute_sec_filing_score(filings, rd_facts)
        assert result is not None
        assert 40 <= result.score <= 60, f"Expected 40-60 for neutral, got {result.score}"

    def test_genuine_investment_score_below_40(self) -> None:
        """R&D outpaces keyword growth produces score < 40."""
        # Same text (flat keywords) with rapidly growing R&D
        filings = _make_filings([2020, 2021, 2022, 2023], _MIXED_TEXT)
        # R&D growing 50%+ per year
        rd_facts = _make_rd_facts({2020: 100000, 2021: 150000, 2022: 225000, 2023: 337500})

        result = compute_sec_filing_score(filings, rd_facts)
        assert result is not None
        assert result.score < 40, f"Expected < 40 for genuine investment, got {result.score}"

    def test_insufficient_data_less_than_2_years_returns_none(self) -> None:
        """Only 1 year of filings returns None (insufficient data)."""
        filings = _make_filings([2023], _VAGUE_TEXT)
        rd_facts = _make_rd_facts({2023: 100000})

        result = compute_sec_filing_score(filings, rd_facts)
        assert result is None

    def test_missing_rd_facts_returns_none(self) -> None:
        """No R&D data returns None."""
        filings = _make_filings([2020, 2021, 2022, 2023], _VAGUE_TEXT)
        rd_facts: list[tuple[int, str, int]] = []

        result = compute_sec_filing_score(filings, rd_facts)
        assert result is None

    def test_determinism_same_inputs_same_output(self) -> None:
        """Same inputs always produce identical score and evidence."""
        filings = _make_filings([2020, 2021, 2022, 2023], _VAGUE_TEXT)
        rd_facts = _make_rd_facts({2020: 100000, 2021: 110000, 2022: 120000, 2023: 130000})

        result_a = compute_sec_filing_score(filings, rd_facts)
        result_b = compute_sec_filing_score(filings, rd_facts)

        assert result_a is not None and result_b is not None
        assert result_a.score == result_b.score
        assert result_a.evidence == result_b.evidence

    def test_evidence_contains_required_sections(self) -> None:
        """Evidence contains keyword_counts, financial_data, scoring fields."""
        filings = _make_filings([2020, 2021, 2022, 2023], _VAGUE_TEXT)
        rd_facts = _make_rd_facts({2020: 100000, 2021: 110000, 2022: 120000, 2023: 130000})

        result = compute_sec_filing_score(filings, rd_facts)
        assert result is not None

        ev = result.evidence
        # Top-level evidence keys
        assert "signal_version" in ev
        assert ev["signal_version"] == "0.4.0"
        assert "window_start_year" in ev
        assert "window_end_year" in ev
        assert "keyword_counts" in ev
        assert "financial_data" in ev
        assert "scoring" in ev
        assert "data_quality" in ev

        # keyword_counts sub-structure
        kc = ev["keyword_counts"]
        assert "by_year" in kc
        assert "by_section" in kc
        assert "section_weights_used" in kc

        # financial_data sub-structure
        fd = ev["financial_data"]
        assert "rd_spend_cents" in fd
        assert "rd_growth_cagr" in fd

        # scoring sub-structure
        sc = ev["scoring"]
        assert "keyword_growth_cagr" in sc
        assert "mismatch_ratio" in sc
        assert "normalization_params" in sc

        # data_quality sub-structure
        dq = ev["data_quality"]
        assert "filings_analyzed" in dq
        assert "years_with_data" in dq
        assert "missing_sections" in dq

    def test_evidence_signal_version_is_0_4_0(self) -> None:
        """Evidence contains signal_version '0.4.0'."""
        filings = _make_filings([2020, 2021, 2022, 2023], _VAGUE_TEXT)
        rd_facts = _make_rd_facts({2020: 100000, 2021: 110000, 2022: 120000, 2023: 130000})

        result = compute_sec_filing_score(filings, rd_facts)
        assert result is not None
        assert result.evidence["signal_version"] == "0.4.0"

    def test_period_of_report_year_alignment(self) -> None:
        """Keyword counts use FilingForScoring.year (period_of_report, not filing_date)."""
        # Ensure that year field is used for grouping, not any other attribute
        filings = [
            FilingForScoring(year=2021, sections={"mda": _VAGUE_TEXT, "risk_factors": _VAGUE_TEXT, "business": _VAGUE_TEXT}),
            FilingForScoring(year=2022, sections={"mda": _VAGUE_TEXT, "risk_factors": _VAGUE_TEXT, "business": _VAGUE_TEXT}),
            FilingForScoring(year=2023, sections={"mda": _VAGUE_TEXT, "risk_factors": _VAGUE_TEXT, "business": _VAGUE_TEXT}),
        ]
        rd_facts = _make_rd_facts({2021: 100000, 2022: 110000, 2023: 120000})

        result = compute_sec_filing_score(filings, rd_facts, window_years=2)
        assert result is not None
        # Should use years from FilingForScoring.year
        ev = result.evidence
        assert ev["window_end_year"] == 2023
        years_in_data = ev["data_quality"]["years_with_data"]
        assert 2021 in years_in_data
        assert 2022 in years_in_data
        assert 2023 in years_in_data

    def test_score_is_bounded_0_to_100(self) -> None:
        """Score is always within 0-100 range."""
        filings = _make_filings([2020, 2021, 2022, 2023], _VAGUE_TEXT)
        rd_facts = _make_rd_facts({2020: 100000, 2021: 110000, 2022: 120000, 2023: 130000})

        result = compute_sec_filing_score(filings, rd_facts)
        assert result is not None
        assert 0 <= result.score <= 100

    def test_two_years_is_minimum_sufficient_data(self) -> None:
        """Exactly 2 years of data should still produce a score."""
        filings = _make_filings([2022, 2023], _VAGUE_TEXT)
        rd_facts = _make_rd_facts({2022: 100000, 2023: 110000})

        result = compute_sec_filing_score(filings, rd_facts, window_years=1)
        assert result is not None
        assert isinstance(result.score, int)
