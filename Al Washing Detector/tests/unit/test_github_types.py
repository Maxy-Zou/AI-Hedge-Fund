"""Unit tests for GitHub signal type contracts and scoring config."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


def test_github_repo_record_valid():
    """Test 1: GitHubRepoRecord validates a well-formed repo dict."""
    from ai_washer.ingestion.github_types import GitHubRepoRecord

    record = GitHubRepoRecord(
        repo_full_name="org/repo",
        repo_name="repo",
        primary_language="Python",
        language_bytes={"Python": 50000, "JavaScript": 2000},
        pushed_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        is_fork=False,
        is_archived=False,
        stargazers_count=42,
        ml_frameworks=["pytorch", "transformers"],
    )
    assert record.repo_full_name == "org/repo"
    assert record.repo_name == "repo"
    assert record.primary_language == "Python"
    assert record.language_bytes == {"Python": 50000, "JavaScript": 2000}
    assert record.is_fork is False
    assert record.is_archived is False
    assert record.stargazers_count == 42
    assert record.ml_frameworks == ["pytorch", "transformers"]


def test_github_repo_record_rejects_empty_name():
    """Test 2: GitHubRepoRecord rejects missing required fields (empty repo_full_name)."""
    from ai_washer.ingestion.github_types import GitHubRepoRecord

    with pytest.raises(ValidationError, match="repo_full_name"):
        GitHubRepoRecord(
            repo_full_name="",
            repo_name="repo",
            primary_language=None,
            language_bytes={},
            pushed_at=None,
            is_fork=False,
            is_archived=False,
            stargazers_count=0,
            ml_frameworks=[],
        )


def test_github_org_snapshot_valid():
    """Test 3: GitHubOrgSnapshot validates with all required fields."""
    from ai_washer.ingestion.github_types import GitHubOrgSnapshot

    snapshot = GitHubOrgSnapshot(
        repo_count=5,
        total_ml_language_bytes=100_000,
        total_language_bytes=500_000,
        ml_language_ratio=0.2,
        days_since_last_push=30,
        ml_frameworks_found=["pytorch"],
        repos=[],
    )
    assert snapshot.repo_count == 5
    assert snapshot.total_ml_language_bytes == 100_000
    assert snapshot.total_language_bytes == 500_000
    assert snapshot.ml_language_ratio == 0.2
    assert snapshot.days_since_last_push == 30
    assert snapshot.ml_frameworks_found == ["pytorch"]
    assert snapshot.repos == []


def test_github_collection_result_fields():
    """Test 4: GitHubCollectionResult has company_cik, repo_count, skipped_count, errors."""
    from ai_washer.ingestion.github_types import GitHubCollectionResult

    result = GitHubCollectionResult(company_cik="0001234567")
    assert result.company_cik == "0001234567"
    assert result.repo_count == 0
    assert result.skipped_count == 0
    assert result.errors == []


def test_ml_framework_patterns_keys():
    """Test 5: ML_FRAMEWORK_PATTERNS contains expected keys with list[str] values."""
    from ai_washer.ingestion.github_types import ML_FRAMEWORK_PATTERNS

    expected_keys = {
        "tensorflow",
        "pytorch",
        "scikit-learn",
        "jax",
        "huggingface",
        "xgboost",
        "lightgbm",
    }
    assert set(ML_FRAMEWORK_PATTERNS.keys()) == expected_keys
    for key, value in ML_FRAMEWORK_PATTERNS.items():
        assert isinstance(value, list), f"{key} should map to list[str]"
        assert all(isinstance(v, str) for v in value), f"{key} values should be strings"


def test_ml_languages_tuple():
    """Test 6: ML_LANGUAGES tuple contains expected languages."""
    from ai_washer.ingestion.github_types import ML_LANGUAGES

    assert isinstance(ML_LANGUAGES, tuple)
    expected = ("Python", "R", "Julia", "C++", "Rust", "Jupyter Notebook")
    assert ML_LANGUAGES == expected


def test_github_signal_version():
    """Test 7: GITHUB_SIGNAL_VERSION equals '0.6.0'."""
    from ai_washer.ingestion.github_types import GITHUB_SIGNAL_VERSION

    assert GITHUB_SIGNAL_VERSION == "0.6.0"


def test_github_activity_scoring_config_defaults():
    """Test 8: GitHubActivityScoringConfig has correct defaults."""
    from ai_washer.config import GitHubActivityScoringConfig

    config = GitHubActivityScoringConfig()
    assert config.max_repos_per_org == 100
    assert config.recency_decay_days == 365
    assert config.sigmoid_midpoint == 1.0
    assert config.sigmoid_steepness == 2.0


def test_github_activity_scoring_config_in_scoring_config():
    """GitHubActivityScoringConfig is accessible via ScoringConfig."""
    from ai_washer.config import ScoringConfig

    scoring = ScoringConfig()
    assert hasattr(scoring, "github_activity")
    assert scoring.github_activity.max_repos_per_org == 100
