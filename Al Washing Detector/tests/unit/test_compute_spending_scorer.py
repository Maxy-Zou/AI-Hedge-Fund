"""Unit tests for compute spending gap scorer.

Tests the three pure functions:
- count_cloud_mentions_by_year: cloud keyword detection in filing sections
- compute_capex_keyword_gap: CapEx vs AI keyword growth divergence
- compute_compute_spending_score: full signal scoring pipeline

Scenarios cover flat CapEx (high score), growing CapEx (low score),
cloud mention offset, insufficient data (None), and determinism.
"""

from __future__ import annotations

import pytest

from ai_washer.analysis.types import FilingForScoring, SignalResult
from ai_washer.analysis.compute_spending_scorer import (
    compute_capex_keyword_gap,
    compute_compute_spending_score,
    count_cloud_mentions_by_year,
)


# ---------------------------------------------------------------------------
# Fixtures: reusable filing and fact data
# ---------------------------------------------------------------------------

def _make_filing(year: int, sections: dict[str, str | None]) -> FilingForScoring:
    """Helper to create a FilingForScoring."""
    return FilingForScoring(year=year, sections=sections)


def _flat_capex_facts(years: list[int], value_cents: int = 100_000_00) -> list[tuple[int, str, int]]:
    """CapEx facts with identical value across all years (flat spending)."""
    return [(y, "FY", value_cents) for y in years]


def _growing_capex_facts(years: list[int], start_cents: int = 100_000_00, growth_rate: float = 0.30) -> list[tuple[int, str, int]]:
    """CapEx facts with compound growth across years."""
    facts = []
    current = start_cents
    for y in years:
        facts.append((y, "FY", int(current)))
        current = current * (1 + growth_rate)
    return facts


def _growing_keyword_counts(years: list[int], start: float = 10.0, growth_rate: float = 0.30) -> dict[int, float]:
    """AI keyword counts growing by growth_rate per year."""
    result = {}
    current = start
    for y in years:
        result[y] = current
        current = current * (1 + growth_rate)
    return result


def _flat_keyword_counts(years: list[int], value: float = 10.0) -> dict[int, float]:
    """AI keyword counts flat across years."""
    return {y: value for y in years}


# ---------------------------------------------------------------------------
# count_cloud_mentions_by_year
# ---------------------------------------------------------------------------

class TestCountCloudMentionsByYear:
    """Tests for cloud keyword detection in filing sections."""

    def test_finds_aws_in_mda(self) -> None:
        """Cloud mention detection finds 'aws' in filing text."""
        filings = [
            _make_filing(2023, {
                "mda": "Our company uses AWS for cloud computing " * 20,  # pad for length
                "risk_factors": None,
                "business": None,
            }),
        ]
        result = count_cloud_mentions_by_year(filings)
        assert result[2023] > 0

    def test_finds_cloud_infrastructure_in_business(self) -> None:
        """Detection finds 'cloud infrastructure' in business section."""
        filings = [
            _make_filing(2024, {
                "mda": None,
                "risk_factors": None,
                "business": "We invested in cloud infrastructure and data center expansion " * 15,
            }),
        ]
        result = count_cloud_mentions_by_year(filings)
        assert result[2024] > 0

    def test_returns_yearly_mapping(self) -> None:
        """Returns dict[int, int] mapping year to total count."""
        filings = [
            _make_filing(2022, {"mda": "AWS and Azure services " * 25, "risk_factors": None, "business": None}),
            _make_filing(2023, {"mda": "Google Cloud platform " * 25, "risk_factors": None, "business": None}),
        ]
        result = count_cloud_mentions_by_year(filings)
        assert isinstance(result, dict)
        assert 2022 in result
        assert 2023 in result
        assert isinstance(result[2022], int)
        assert isinstance(result[2023], int)

    def test_skips_none_sections_without_error(self) -> None:
        """None sections do not cause errors."""
        filings = [
            _make_filing(2023, {"mda": None, "risk_factors": None, "business": None}),
        ]
        result = count_cloud_mentions_by_year(filings)
        # Should return 0 or not include the year
        assert result.get(2023, 0) == 0

    def test_searches_across_mda_risk_business(self) -> None:
        """Searches mda, risk_factors, and business sections."""
        filings = [
            _make_filing(2023, {
                "mda": "AWS partnership " * 20,
                "risk_factors": "GPU shortage risk " * 20,
                "business": "NVIDIA collaboration " * 20,
            }),
        ]
        result = count_cloud_mentions_by_year(filings)
        # Should find mentions from all three sections
        assert result[2023] >= 3  # at least one from each section

    def test_empty_filings_returns_empty(self) -> None:
        """Empty filing list returns empty dict."""
        result = count_cloud_mentions_by_year([])
        assert result == {}


# ---------------------------------------------------------------------------
# compute_capex_keyword_gap
# ---------------------------------------------------------------------------

class TestComputeCapexKeywordGap:
    """Tests for CapEx vs AI keyword growth gap computation."""

    def test_flat_capex_growing_keywords_high_ratio(self) -> None:
        """Flat CapEx (0% growth) + growing AI keywords (30%) returns ratio > 1.0."""
        years = [2021, 2022, 2023]
        ai_keywords = _growing_keyword_counts(years, start=10.0, growth_rate=0.30)
        capex = {2021: 100_000_00, 2022: 100_000_00, 2023: 100_000_00}
        cloud_mentions: dict[int, int] = {}

        ratio, evidence = compute_capex_keyword_gap(
            ai_keyword_counts_by_year=ai_keywords,
            capex_by_year=capex,
            cloud_mentions_by_year=cloud_mentions,
            window_years=3,
        )
        assert ratio is not None
        assert ratio > 1.0
        assert "capex_growth_cagr" in evidence

    def test_growing_capex_matching_keywords_neutral_ratio(self) -> None:
        """Growing CapEx matching keyword growth returns ratio near 1.0."""
        years = [2021, 2022, 2023]
        ai_keywords = _growing_keyword_counts(years, start=10.0, growth_rate=0.20)
        capex = {y: int(100_000_00 * (1.20 ** i)) for i, y in enumerate(years)}
        cloud_mentions: dict[int, int] = {}

        ratio, evidence = compute_capex_keyword_gap(
            ai_keyword_counts_by_year=ai_keywords,
            capex_by_year=capex,
            cloud_mentions_by_year=cloud_mentions,
        )
        assert ratio is not None
        # When keyword growth ~ CapEx growth, ratio should be near 1.0
        assert 0.7 <= ratio <= 1.3

    def test_no_capex_data_returns_none(self) -> None:
        """No CapEx data returns (None, evidence with error)."""
        ai_keywords = {2021: 10.0, 2022: 15.0, 2023: 20.0}
        capex: dict[int, int] = {}
        cloud_mentions: dict[int, int] = {}

        ratio, evidence = compute_capex_keyword_gap(
            ai_keyword_counts_by_year=ai_keywords,
            capex_by_year=capex,
            cloud_mentions_by_year=cloud_mentions,
        )
        assert ratio is None
        assert "error" in evidence

    def test_weights_capex_70_cloud_30(self) -> None:
        """Combined gap uses 0.70 CapEx weight and 0.30 cloud mention weight."""
        years = [2021, 2022, 2023]
        ai_keywords = _growing_keyword_counts(years, start=10.0, growth_rate=0.30)
        capex = {2021: 100_000_00, 2022: 100_000_00, 2023: 100_000_00}
        # Cloud mentions growing - should partially offset
        cloud_mentions = {2021: 5, 2022: 8, 2023: 12}

        ratio_with_cloud, ev_cloud = compute_capex_keyword_gap(
            ai_keyword_counts_by_year=ai_keywords,
            capex_by_year=capex,
            cloud_mentions_by_year=cloud_mentions,
            capex_weight=0.70,
            cloud_mention_weight=0.30,
        )

        ratio_without_cloud, _ = compute_capex_keyword_gap(
            ai_keyword_counts_by_year=ai_keywords,
            capex_by_year=capex,
            cloud_mentions_by_year={},
            capex_weight=0.70,
            cloud_mention_weight=0.30,
        )

        assert ratio_with_cloud is not None
        assert ratio_without_cloud is not None
        # Cloud mentions growing should reduce the gap ratio
        assert ratio_with_cloud < ratio_without_cloud

    def test_evidence_contains_required_fields(self) -> None:
        """Evidence dict contains capex_growth_cagr, cloud_mention_growth, keyword_growth_cagr."""
        years = [2021, 2022, 2023]
        ai_keywords = _growing_keyword_counts(years)
        capex = {y: 100_000_00 for y in years}

        _, evidence = compute_capex_keyword_gap(
            ai_keyword_counts_by_year=ai_keywords,
            capex_by_year=capex,
            cloud_mentions_by_year={},
        )
        assert "capex_growth_cagr" in evidence
        assert "cloud_mention_growth" in evidence
        assert "keyword_growth_cagr" in evidence
        assert "combined_gap_ratio" in evidence


# ---------------------------------------------------------------------------
# compute_compute_spending_score
# ---------------------------------------------------------------------------

class TestComputeComputeSpendingScore:
    """Tests for the full compute spending score pipeline."""

    def test_returns_signal_result_type(self) -> None:
        """Returns SignalResult with signal_type='compute_spending'."""
        years = [2021, 2022, 2023]
        filings = [_make_filing(y, {"mda": "basic text " * 100, "risk_factors": None, "business": None}) for y in years]
        capex_facts = _flat_capex_facts(years)
        ai_keywords = _growing_keyword_counts(years)

        result = compute_compute_spending_score(
            filings=filings,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year=ai_keywords,
        )
        assert result is not None
        assert isinstance(result, SignalResult)
        assert result.signal_type == "compute_spending"

    def test_flat_capex_growing_keywords_high_score(self) -> None:
        """Flat CapEx + no cloud mentions + growing AI keywords -> score > 70."""
        years = [2021, 2022, 2023]
        filings = [_make_filing(y, {"mda": "generic text " * 100, "risk_factors": None, "business": None}) for y in years]
        capex_facts = _flat_capex_facts(years, value_cents=500_000_00)
        ai_keywords = _growing_keyword_counts(years, start=10.0, growth_rate=0.50)

        result = compute_compute_spending_score(
            filings=filings,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year=ai_keywords,
        )
        assert result is not None
        assert result.score > 70

    def test_growing_capex_increasing_cloud_low_score(self) -> None:
        """Growing CapEx + increasing cloud mentions -> score < 40."""
        years = [2021, 2022, 2023]
        # Filings with cloud mentions that grow
        filings = [
            _make_filing(2021, {"mda": "AWS cloud infrastructure " * 50, "risk_factors": None, "business": None}),
            _make_filing(2022, {"mda": "AWS Azure cloud infrastructure GPU cluster " * 50, "risk_factors": None, "business": None}),
            _make_filing(2023, {"mda": "AWS Azure Google Cloud cloud infrastructure GPU NVIDIA data center " * 50, "risk_factors": None, "business": None}),
        ]
        capex_facts = _growing_capex_facts(years, start_cents=500_000_00, growth_rate=0.40)
        ai_keywords = _growing_keyword_counts(years, start=10.0, growth_rate=0.20)

        result = compute_compute_spending_score(
            filings=filings,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year=ai_keywords,
        )
        assert result is not None
        assert result.score < 40

    def test_cloud_mentions_partially_offset_flat_capex(self) -> None:
        """Flat CapEx + growing cloud mentions scores lower than flat CapEx alone."""
        years = [2021, 2022, 2023]
        filings_no_cloud = [_make_filing(y, {"mda": "generic text " * 100, "risk_factors": None, "business": None}) for y in years]
        filings_with_cloud = [
            _make_filing(2021, {"mda": "AWS partnership " * 50, "risk_factors": None, "business": None}),
            _make_filing(2022, {"mda": "AWS Azure partnership " * 50, "risk_factors": None, "business": None}),
            _make_filing(2023, {"mda": "AWS Azure Google Cloud partnership data center " * 50, "risk_factors": None, "business": None}),
        ]
        capex_facts = _flat_capex_facts(years)
        ai_keywords = _growing_keyword_counts(years, start=10.0, growth_rate=0.40)

        score_no_cloud = compute_compute_spending_score(
            filings=filings_no_cloud,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year=ai_keywords,
        )
        score_with_cloud = compute_compute_spending_score(
            filings=filings_with_cloud,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year=ai_keywords,
        )
        assert score_no_cloud is not None
        assert score_with_cloud is not None
        assert score_with_cloud.score <= score_no_cloud.score

    def test_insufficient_capex_data_returns_none(self) -> None:
        """With no CapEx data, returns None."""
        years = [2021, 2022, 2023]
        filings = [_make_filing(y, {"mda": "text " * 100, "risk_factors": None, "business": None}) for y in years]
        ai_keywords = _growing_keyword_counts(years)

        result = compute_compute_spending_score(
            filings=filings,
            capex_facts=[],
            ai_keyword_counts_by_year=ai_keywords,
        )
        assert result is None

    def test_insufficient_keyword_data_returns_none(self) -> None:
        """With no keyword data, returns None."""
        years = [2021, 2022, 2023]
        filings = [_make_filing(y, {"mda": "text " * 100, "risk_factors": None, "business": None}) for y in years]
        capex_facts = _flat_capex_facts(years)

        result = compute_compute_spending_score(
            filings=filings,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year={},
        )
        assert result is None

    def test_single_year_capex_returns_none(self) -> None:
        """Single year of CapEx data is insufficient (need >= 2)."""
        filings = [_make_filing(2023, {"mda": "text " * 100, "risk_factors": None, "business": None})]
        capex_facts = [(2023, "FY", 100_000_00)]
        ai_keywords = {2023: 10.0}

        result = compute_compute_spending_score(
            filings=filings,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year=ai_keywords,
        )
        assert result is None

    def test_evidence_contains_signal_version(self) -> None:
        """Evidence contains signal_version '0.4.0'."""
        years = [2021, 2022, 2023]
        filings = [_make_filing(y, {"mda": "text " * 100, "risk_factors": None, "business": None}) for y in years]
        capex_facts = _flat_capex_facts(years)
        ai_keywords = _growing_keyword_counts(years)

        result = compute_compute_spending_score(
            filings=filings,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year=ai_keywords,
        )
        assert result is not None
        assert result.evidence["signal_version"] == "0.4.0"

    def test_evidence_contains_capex_data(self) -> None:
        """Evidence contains capex_data section."""
        years = [2021, 2022, 2023]
        filings = [_make_filing(y, {"mda": "text " * 100, "risk_factors": None, "business": None}) for y in years]
        capex_facts = _flat_capex_facts(years)
        ai_keywords = _growing_keyword_counts(years)

        result = compute_compute_spending_score(
            filings=filings,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year=ai_keywords,
        )
        assert result is not None
        assert "capex_data" in result.evidence
        assert "by_year_cents" in result.evidence["capex_data"]
        assert "capex_growth_cagr" in result.evidence["capex_data"]
        assert result.evidence["capex_data"]["xbrl_concept_used"] == "capex"

    def test_evidence_contains_cloud_mentions(self) -> None:
        """Evidence contains cloud_mentions section with data_source='filing_text'."""
        years = [2021, 2022, 2023]
        filings = [_make_filing(y, {"mda": "AWS partnership " * 50, "risk_factors": None, "business": None}) for y in years]
        capex_facts = _flat_capex_facts(years)
        ai_keywords = _growing_keyword_counts(years)

        result = compute_compute_spending_score(
            filings=filings,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year=ai_keywords,
        )
        assert result is not None
        assert "cloud_mentions" in result.evidence
        assert result.evidence["cloud_mentions"]["data_source"] == "filing_text"
        assert "by_year" in result.evidence["cloud_mentions"]
        assert "keywords_found" in result.evidence["cloud_mentions"]

    def test_evidence_contains_scoring_section(self) -> None:
        """Evidence contains scoring section with normalization params."""
        years = [2021, 2022, 2023]
        filings = [_make_filing(y, {"mda": "text " * 100, "risk_factors": None, "business": None}) for y in years]
        capex_facts = _flat_capex_facts(years)
        ai_keywords = _growing_keyword_counts(years)

        result = compute_compute_spending_score(
            filings=filings,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year=ai_keywords,
        )
        assert result is not None
        scoring = result.evidence["scoring"]
        assert "capex_vs_keyword_ratio" in scoring
        assert "capex_weight" in scoring
        assert "cloud_mention_weight" in scoring
        assert "combined_gap_score" in scoring
        assert "normalization_params" in scoring

    def test_evidence_contains_data_quality(self) -> None:
        """Evidence contains data_quality section."""
        years = [2021, 2022, 2023]
        filings = [_make_filing(y, {"mda": "text " * 100, "risk_factors": None, "business": None}) for y in years]
        capex_facts = _flat_capex_facts(years)
        ai_keywords = _growing_keyword_counts(years)

        result = compute_compute_spending_score(
            filings=filings,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year=ai_keywords,
        )
        assert result is not None
        assert "data_quality" in result.evidence
        assert "capex_years_available" in result.evidence["data_quality"]

    def test_deterministic_same_inputs_same_output(self) -> None:
        """Same inputs always produce same output (determinism)."""
        years = [2021, 2022, 2023]
        filings = [_make_filing(y, {"mda": "AWS cloud infrastructure text " * 50, "risk_factors": None, "business": None}) for y in years]
        capex_facts = _flat_capex_facts(years)
        ai_keywords = _growing_keyword_counts(years, start=10.0, growth_rate=0.30)

        results = []
        for _ in range(5):
            r = compute_compute_spending_score(
                filings=filings,
                capex_facts=capex_facts,
                ai_keyword_counts_by_year=ai_keywords,
            )
            results.append(r)

        # All runs produce identical scores
        scores = [r.score for r in results if r is not None]
        assert len(scores) == 5
        assert len(set(scores)) == 1, f"Non-deterministic scores: {scores}"

        # Evidence dicts are also identical
        evidences = [r.evidence for r in results if r is not None]
        assert all(e == evidences[0] for e in evidences)

    def test_score_range_0_to_100(self) -> None:
        """Score is always in [0, 100] range."""
        years = [2021, 2022, 2023]
        filings = [_make_filing(y, {"mda": "text " * 100, "risk_factors": None, "business": None}) for y in years]
        capex_facts = _flat_capex_facts(years)
        ai_keywords = _growing_keyword_counts(years)

        result = compute_compute_spending_score(
            filings=filings,
            capex_facts=capex_facts,
            ai_keyword_counts_by_year=ai_keywords,
        )
        assert result is not None
        assert 0 <= result.score <= 100
