"""Tests for patent gap scorer pure function.

Validates CAGR-based divergence ratio between AI claim intensity
and patent filing trend, normalized to 0-100 via sigmoid.
"""

from __future__ import annotations

import pytest

from ai_washer.analysis.patent_gap_scorer import compute_patent_gap_score
from ai_washer.analysis.types import SignalResult


class TestComputePatentGapScore:
    """Core scoring logic tests."""

    def test_high_claims_low_patents_high_score(self):
        """Growing claims but flat patents -> high score (washing signal)."""
        patent_counts = {2022: 5, 2023: 5, 2024: 5, 2025: 5}
        ai_claims = {2022: 10.0, 2023: 15.0, 2024: 20.0, 2025: 30.0}

        result = compute_patent_gap_score(
            patent_counts_by_year=patent_counts,
            ai_claim_intensity_by_year=ai_claims,
            scoring_year=2025,
            window_years=3,
        )

        assert result is not None
        assert result.score >= 60

    def test_low_claims_high_patents_low_score(self):
        """Flat claims but growing patents -> low score (genuine AI)."""
        patent_counts = {2022: 2, 2023: 4, 2024: 7, 2025: 10}
        ai_claims = {2022: 10.0, 2023: 10.0, 2024: 10.0, 2025: 10.0}

        result = compute_patent_gap_score(
            patent_counts_by_year=patent_counts,
            ai_claim_intensity_by_year=ai_claims,
            scoring_year=2025,
            window_years=3,
        )

        assert result is not None
        assert result.score <= 40

    def test_equal_growth_neutral_score(self):
        """Both grow equally -> neutral score near 50."""
        patent_counts = {2022: 5, 2023: 7, 2024: 9, 2025: 12}
        ai_claims = {2022: 5.0, 2023: 7.0, 2024: 9.0, 2025: 12.0}

        result = compute_patent_gap_score(
            patent_counts_by_year=patent_counts,
            ai_claim_intensity_by_year=ai_claims,
            scoring_year=2025,
            window_years=3,
        )

        assert result is not None
        assert 40 <= result.score <= 60

    def test_insufficient_data_returns_none(self):
        """Only 1 overlapping year -> returns None."""
        patent_counts = {2025: 5}
        ai_claims = {2025: 10.0}

        result = compute_patent_gap_score(
            patent_counts_by_year=patent_counts,
            ai_claim_intensity_by_year=ai_claims,
            scoring_year=2025,
            window_years=3,
        )

        assert result is None

    def test_no_claims_returns_none(self):
        """Missing start_year claims -> returns None."""
        patent_counts = {2022: 5, 2023: 5, 2024: 5, 2025: 5}
        ai_claims = {2024: 10.0, 2025: 20.0}

        result = compute_patent_gap_score(
            patent_counts_by_year=patent_counts,
            ai_claim_intensity_by_year=ai_claims,
            scoring_year=2025,
            window_years=3,
        )

        assert result is None

    def test_zero_start_patents_uses_floor(self):
        """start_patents=0 does not crash, uses 1 as floor."""
        patent_counts = {2022: 0, 2023: 1, 2024: 2, 2025: 3}
        ai_claims = {2022: 10.0, 2023: 12.0, 2024: 15.0, 2025: 20.0}

        result = compute_patent_gap_score(
            patent_counts_by_year=patent_counts,
            ai_claim_intensity_by_year=ai_claims,
            scoring_year=2025,
            window_years=3,
        )

        assert result is not None
        assert 0 <= result.score <= 100

    def test_zero_start_claims_uses_floor(self):
        """start_claims=0 does not crash, uses 0.1 as floor."""
        patent_counts = {2022: 5, 2023: 5, 2024: 5, 2025: 5}
        ai_claims = {2022: 0.0, 2023: 5.0, 2024: 10.0, 2025: 15.0}

        result = compute_patent_gap_score(
            patent_counts_by_year=patent_counts,
            ai_claim_intensity_by_year=ai_claims,
            scoring_year=2025,
            window_years=3,
        )

        assert result is not None
        assert 0 <= result.score <= 100

    def test_evidence_contains_required_fields(self):
        """Verify evidence dict contains all required audit fields."""
        patent_counts = {2022: 5, 2023: 5, 2024: 5, 2025: 5}
        ai_claims = {2022: 10.0, 2023: 12.0, 2024: 15.0, 2025: 20.0}

        result = compute_patent_gap_score(
            patent_counts_by_year=patent_counts,
            ai_claim_intensity_by_year=ai_claims,
            scoring_year=2025,
            window_years=3,
        )

        assert result is not None
        ev = result.evidence
        assert ev["signal_version"] == "0.5.0"
        assert "claim_growth_cagr" in ev
        assert "patent_growth_cagr" in ev
        assert "gap_ratio" in ev
        assert "patent_counts" in ev
        assert "window" in ev
        assert ev["window"]["start"] == 2022
        assert ev["window"]["end"] == 2025
        assert "overlapping_years" in ev

    def test_signal_type_is_patent_gap(self):
        """Result signal_type must be 'patent_gap'."""
        patent_counts = {2022: 5, 2023: 5, 2024: 5, 2025: 5}
        ai_claims = {2022: 10.0, 2023: 12.0, 2024: 15.0, 2025: 20.0}

        result = compute_patent_gap_score(
            patent_counts_by_year=patent_counts,
            ai_claim_intensity_by_year=ai_claims,
            scoring_year=2025,
            window_years=3,
        )

        assert result is not None
        assert result.signal_type == "patent_gap"

    def test_score_bounded_0_100(self):
        """Extreme inputs still produce 0-100 score."""
        # Extreme: massive claim growth, zero patent growth
        patent_counts = {2022: 1, 2023: 1, 2024: 1, 2025: 1}
        ai_claims = {2022: 1.0, 2023: 100.0, 2024: 1000.0, 2025: 10000.0}

        result = compute_patent_gap_score(
            patent_counts_by_year=patent_counts,
            ai_claim_intensity_by_year=ai_claims,
            scoring_year=2025,
            window_years=3,
        )

        assert result is not None
        assert 0 <= result.score <= 100

    def test_custom_window_years(self):
        """window_years=5 uses correct start_year."""
        patent_counts = {2020: 5, 2021: 5, 2022: 5, 2023: 5, 2024: 5, 2025: 5}
        ai_claims = {2020: 10.0, 2021: 12.0, 2022: 14.0, 2023: 16.0, 2024: 18.0, 2025: 20.0}

        result = compute_patent_gap_score(
            patent_counts_by_year=patent_counts,
            ai_claim_intensity_by_year=ai_claims,
            scoring_year=2025,
            window_years=5,
        )

        assert result is not None
        assert result.evidence["window"]["start"] == 2020
        assert result.evidence["window"]["end"] == 2025
