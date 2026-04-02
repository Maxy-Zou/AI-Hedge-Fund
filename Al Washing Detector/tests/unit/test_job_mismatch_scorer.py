"""Tests for the job mismatch scorer pure function.

Verifies that compute_job_mismatch_score correctly compares AI claim intensity
to actual hiring activity (role count, role quality, ghost ratio) and produces
a 0-100 score following the same pattern as github_activity_scorer and patent_gap_scorer.
"""

from __future__ import annotations

import pytest

from ai_washer.analysis.job_mismatch_scorer import compute_job_mismatch_score


class TestJobMismatchScorerNone:
    """Cases where the scorer should return None."""

    def test_zero_claim_intensity_returns_none(self) -> None:
        result = compute_job_mismatch_score(
            ai_role_count=5,
            marketing_role_count=2,
            total_role_count=10,
            ghost_ratio=0.0,
            ai_claim_intensity=0.0,
            scoring_year=2025,
        )
        assert result is None

    def test_negative_claim_intensity_returns_none(self) -> None:
        result = compute_job_mismatch_score(
            ai_role_count=5,
            marketing_role_count=2,
            total_role_count=10,
            ghost_ratio=0.0,
            ai_claim_intensity=-1.0,
            scoring_year=2025,
        )
        assert result is None


class TestJobMismatchScorerHighScore:
    """Cases producing high washing scores."""

    def test_no_roles_with_claims_returns_high_score(self) -> None:
        """total_role_count=0 with positive claims = near-max washing."""
        result = compute_job_mismatch_score(
            ai_role_count=0,
            marketing_role_count=0,
            total_role_count=0,
            ghost_ratio=0.0,
            ai_claim_intensity=30.0,
            scoring_year=2025,
        )
        assert result is not None
        assert result.score > 80
        assert result.score <= 100

    def test_all_marketing_roles_returns_high_score(self) -> None:
        """0 engineering, 10 marketing = fluff, high score."""
        result = compute_job_mismatch_score(
            ai_role_count=0,
            marketing_role_count=10,
            total_role_count=10,
            ghost_ratio=0.0,
            ai_claim_intensity=30.0,
            scoring_year=2025,
        )
        assert result is not None
        assert result.score > 60


class TestJobMismatchScorerLowScore:
    """Cases producing low (genuine) scores."""

    def test_strong_engineering_hiring_returns_low_score(self) -> None:
        """20 engineering roles, 0 marketing, 0 ghosts = genuine hiring."""
        result = compute_job_mismatch_score(
            ai_role_count=20,
            marketing_role_count=0,
            total_role_count=20,
            ghost_ratio=0.0,
            ai_claim_intensity=30.0,
            scoring_year=2025,
        )
        assert result is not None
        assert result.score < 40


class TestJobMismatchScorerGhostPenalty:
    """Ghost ratio should increase the score (more washing signal)."""

    def test_ghost_ratio_increases_score(self) -> None:
        base_kwargs = {
            "ai_role_count": 5,
            "marketing_role_count": 2,
            "total_role_count": 10,
            "ai_claim_intensity": 30.0,
            "scoring_year": 2025,
        }
        result_no_ghosts = compute_job_mismatch_score(ghost_ratio=0.0, **base_kwargs)
        result_with_ghosts = compute_job_mismatch_score(ghost_ratio=0.5, **base_kwargs)

        assert result_no_ghosts is not None
        assert result_with_ghosts is not None
        assert result_with_ghosts.score > result_no_ghosts.score


class TestJobMismatchScorerOutput:
    """Verify output structure and invariants."""

    def test_score_is_int_between_0_and_100(self) -> None:
        result = compute_job_mismatch_score(
            ai_role_count=3,
            marketing_role_count=2,
            total_role_count=8,
            ghost_ratio=0.1,
            ai_claim_intensity=25.0,
            scoring_year=2025,
        )
        assert result is not None
        assert isinstance(result.score, int)
        assert 0 <= result.score <= 100

    def test_signal_type_is_job_mismatch(self) -> None:
        result = compute_job_mismatch_score(
            ai_role_count=3,
            marketing_role_count=2,
            total_role_count=8,
            ghost_ratio=0.1,
            ai_claim_intensity=25.0,
            scoring_year=2025,
        )
        assert result is not None
        assert result.signal_type == "job_mismatch"

    def test_evidence_contains_required_keys(self) -> None:
        result = compute_job_mismatch_score(
            ai_role_count=3,
            marketing_role_count=2,
            total_role_count=8,
            ghost_ratio=0.1,
            ai_claim_intensity=25.0,
            scoring_year=2025,
        )
        assert result is not None
        ev = result.evidence
        assert ev["signal_version"] == "0.8.0"
        assert "ai_role_count" in ev
        assert "marketing_role_count" in ev
        assert "total_role_count" in ev
        assert "ghost_ratio" in ev
        assert "ai_claim_intensity" in ev
        assert "sub_factors" in ev
        assert "job_factor" in ev
        assert "claim_factor" in ev
        assert "gap_ratio" in ev
        assert "scoring_year" in ev
        assert ev["scoring_year"] == 2025

    def test_evidence_sub_factors_complete(self) -> None:
        result = compute_job_mismatch_score(
            ai_role_count=3,
            marketing_role_count=2,
            total_role_count=8,
            ghost_ratio=0.1,
            ai_claim_intensity=25.0,
            scoring_year=2025,
        )
        assert result is not None
        sf = result.evidence["sub_factors"]
        assert "hiring_intensity" in sf
        assert "specificity" in sf
        assert "marketing_ratio" in sf
        assert "ghost_penalty" in sf
