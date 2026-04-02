"""Tests for GitHub activity scorer pure function.

Validates the gap between AI claim intensity and GitHub ML activity,
normalized to 0-100 via sigmoid. High score = claims without GitHub
activity (washing signal). Low score = genuine ML development.
"""

from __future__ import annotations

import pytest

from ai_washer.analysis.github_activity_scorer import compute_github_activity_score
from ai_washer.analysis.types import SignalResult


class TestNoneReturns:
    """Cases where scorer returns None (insufficient data)."""

    def test_zero_repos_zero_claims_returns_none(self):
        """No repos + no claims = nothing to score."""
        result = compute_github_activity_score(
            repo_count=0,
            ml_language_ratio=0.0,
            days_since_last_push=None,
            ml_frameworks_found=[],
            ai_claim_intensity=0.0,
            scoring_year=2025,
        )
        assert result is None

    def test_active_repos_zero_claims_returns_none(self):
        """Active ML repos but zero claims = no gap to measure."""
        result = compute_github_activity_score(
            repo_count=10,
            ml_language_ratio=0.8,
            days_since_last_push=5,
            ml_frameworks_found=["tensorflow", "pytorch"],
            ai_claim_intensity=0.0,
            scoring_year=2025,
        )
        assert result is None

    def test_negative_claims_returns_none(self):
        """Negative claim intensity treated as no claims."""
        result = compute_github_activity_score(
            repo_count=5,
            ml_language_ratio=0.5,
            days_since_last_push=10,
            ml_frameworks_found=["pytorch"],
            ai_claim_intensity=-1.0,
            scoring_year=2025,
        )
        assert result is None


class TestZeroReposWithClaims:
    """Zero GitHub presence + nonzero AI claims = near-max washing."""

    def test_zero_repos_high_claims_returns_95(self):
        """No repos + high claims = 95 (near-max washing signal)."""
        result = compute_github_activity_score(
            repo_count=0,
            ml_language_ratio=0.0,
            days_since_last_push=None,
            ml_frameworks_found=[],
            ai_claim_intensity=50.0,
            scoring_year=2025,
        )
        assert result is not None
        assert result.score == 95
        assert result.signal_type == "github_activity"

    def test_zero_repos_low_claims_returns_95(self):
        """No repos + even small claims = 95."""
        result = compute_github_activity_score(
            repo_count=0,
            ml_language_ratio=0.0,
            days_since_last_push=None,
            ml_frameworks_found=[],
            ai_claim_intensity=1.0,
            scoring_year=2025,
        )
        assert result is not None
        assert result.score == 95


class TestActiveMLRepos:
    """Active ML repos + claims = low score (genuine)."""

    def test_active_ml_repos_high_claims_low_score(self):
        """High ML activity + high claims = low score (genuine AI)."""
        result = compute_github_activity_score(
            repo_count=25,
            ml_language_ratio=0.9,
            days_since_last_push=3,
            ml_frameworks_found=["tensorflow", "pytorch", "jax"],
            ai_claim_intensity=40.0,
            scoring_year=2025,
        )
        assert result is not None
        assert result.score <= 45

    def test_moderate_ml_repos_moderate_claims(self):
        """Moderate activity + moderate claims = moderate score."""
        result = compute_github_activity_score(
            repo_count=10,
            ml_language_ratio=0.5,
            days_since_last_push=30,
            ml_frameworks_found=["tensorflow"],
            ai_claim_intensity=25.0,
            scoring_year=2025,
        )
        assert result is not None
        assert 30 <= result.score <= 70


class TestNoMLLanguages:
    """Repos exist but no ML languages or frameworks = high score."""

    def test_many_repos_no_ml_high_claims(self):
        """Many repos but zero ML languages + zero ML frameworks + high claims = high score."""
        result = compute_github_activity_score(
            repo_count=15,
            ml_language_ratio=0.0,
            days_since_last_push=10,
            ml_frameworks_found=[],
            ai_claim_intensity=50.0,
            scoring_year=2025,
        )
        assert result is not None
        assert result.score >= 60


class TestDormantRepos:
    """Dormant repos (old last push) + claims = moderately high score."""

    def test_dormant_repos_high_claims(self):
        """days_since_last_push > 365 + high claims = moderately high score."""
        result = compute_github_activity_score(
            repo_count=10,
            ml_language_ratio=0.5,
            days_since_last_push=500,
            ml_frameworks_found=["tensorflow"],
            ai_claim_intensity=40.0,
            scoring_year=2025,
        )
        assert result is not None
        assert result.score >= 55


class TestArchivedRepos:
    """All archived (effective repo_count=0 after filtering) + claims = high score."""

    def test_archived_repos_zero_effective_count(self):
        """If repo_count=0 (already filtered to exclude archived) + claims = 95."""
        result = compute_github_activity_score(
            repo_count=0,
            ml_language_ratio=0.0,
            days_since_last_push=None,
            ml_frameworks_found=[],
            ai_claim_intensity=30.0,
            scoring_year=2025,
        )
        assert result is not None
        assert result.score == 95


class TestFrameworkDetection:
    """Framework count affects score."""

    def test_single_framework_vs_multiple(self):
        """Multiple frameworks = lower score than single framework."""
        single = compute_github_activity_score(
            repo_count=15,
            ml_language_ratio=0.6,
            days_since_last_push=10,
            ml_frameworks_found=["tensorflow"],
            ai_claim_intensity=30.0,
            scoring_year=2025,
        )
        multiple = compute_github_activity_score(
            repo_count=15,
            ml_language_ratio=0.6,
            days_since_last_push=10,
            ml_frameworks_found=["tensorflow", "pytorch", "jax"],
            ai_claim_intensity=30.0,
            scoring_year=2025,
        )
        assert single is not None
        assert multiple is not None
        assert multiple.score < single.score


class TestScoreBounds:
    """Score is always 0-100 integer."""

    @pytest.mark.parametrize(
        "repo_count,ml_ratio,days,frameworks,claims",
        [
            (1, 0.01, 364, [], 100.0),
            (100, 1.0, 0, ["tf", "pt", "jax", "keras"], 0.1),
            (50, 0.5, 180, ["pytorch"], 50.0),
            (1, 0.0, 1000, [], 200.0),
        ],
    )
    def test_score_always_0_100_integer(
        self, repo_count, ml_ratio, days, frameworks, claims
    ):
        result = compute_github_activity_score(
            repo_count=repo_count,
            ml_language_ratio=ml_ratio,
            days_since_last_push=days,
            ml_frameworks_found=frameworks,
            ai_claim_intensity=claims,
            scoring_year=2025,
        )
        assert result is not None
        assert isinstance(result.score, int)
        assert 0 <= result.score <= 100


class TestEvidence:
    """Evidence dict contains all required fields."""

    def test_evidence_fields(self):
        result = compute_github_activity_score(
            repo_count=10,
            ml_language_ratio=0.6,
            days_since_last_push=15,
            ml_frameworks_found=["tensorflow", "pytorch"],
            ai_claim_intensity=30.0,
            scoring_year=2025,
        )
        assert result is not None
        ev = result.evidence

        assert ev["signal_version"] == "0.6.0"
        assert ev["repo_count"] == 10
        assert ev["ml_language_ratio"] == 0.6
        assert ev["days_since_last_push"] == 15
        assert ev["ml_frameworks_found"] == ["tensorflow", "pytorch"]
        assert isinstance(ev["ai_claim_intensity"], float)
        assert "sub_factors" in ev
        sub = ev["sub_factors"]
        assert "repo_factor" in sub
        assert "language_factor" in sub
        assert "recency_factor" in sub
        assert "framework_factor" in sub
        assert "github_factor" in ev
        assert "claim_factor" in ev
        assert "gap_ratio" in ev
        assert ev["scoring_year"] == 2025

    def test_evidence_signal_type(self):
        result = compute_github_activity_score(
            repo_count=5,
            ml_language_ratio=0.3,
            days_since_last_push=50,
            ml_frameworks_found=["pytorch"],
            ai_claim_intensity=20.0,
            scoring_year=2025,
        )
        assert result is not None
        assert result.signal_type == "github_activity"


class TestParameterEffects:
    """sigmoid_midpoint, sigmoid_steepness, and recency_decay_days affect output."""

    def test_sigmoid_midpoint_affects_score(self):
        """Higher midpoint = lower score for same inputs."""
        kwargs = dict(
            repo_count=10,
            ml_language_ratio=0.5,
            days_since_last_push=30,
            ml_frameworks_found=["tensorflow"],
            ai_claim_intensity=30.0,
            scoring_year=2025,
        )
        low_mid = compute_github_activity_score(**kwargs, sigmoid_midpoint=0.5)
        high_mid = compute_github_activity_score(**kwargs, sigmoid_midpoint=3.0)

        assert low_mid is not None
        assert high_mid is not None
        assert low_mid.score > high_mid.score

    def test_sigmoid_steepness_affects_score(self):
        """Higher steepness = more extreme score for above-midpoint ratio."""
        kwargs = dict(
            repo_count=5,
            ml_language_ratio=0.2,
            days_since_last_push=100,
            ml_frameworks_found=[],
            ai_claim_intensity=40.0,
            scoring_year=2025,
        )
        low_steep = compute_github_activity_score(**kwargs, sigmoid_steepness=0.5)
        high_steep = compute_github_activity_score(**kwargs, sigmoid_steepness=5.0)

        assert low_steep is not None
        assert high_steep is not None
        # For a ratio above midpoint, higher steepness pushes score higher
        assert high_steep.score >= low_steep.score

    def test_recency_decay_days_affects_score(self):
        """Longer decay = more forgiving of old pushes."""
        kwargs = dict(
            repo_count=10,
            ml_language_ratio=0.5,
            days_since_last_push=200,
            ml_frameworks_found=["tensorflow"],
            ai_claim_intensity=30.0,
            scoring_year=2025,
        )
        short_decay = compute_github_activity_score(**kwargs, recency_decay_days=100)
        long_decay = compute_github_activity_score(**kwargs, recency_decay_days=730)

        assert short_decay is not None
        assert long_decay is not None
        # Longer decay means higher recency_factor -> higher github_factor -> lower score
        assert long_decay.score < short_decay.score
