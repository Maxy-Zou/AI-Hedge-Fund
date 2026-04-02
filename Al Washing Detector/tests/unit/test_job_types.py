"""Tests for job posting type contracts, role classifier, and dedup hash."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestClassifyRole:
    """Tests for the classify_role function."""

    def test_engineering_role_with_ml_keywords(self):
        from ai_washer.ingestion.job_types import classify_role

        result = classify_role("ML Engineer", "Build PyTorch models for NLP pipeline")
        assert result == "engineering"

    def test_marketing_role_with_strategy_keywords(self):
        from ai_washer.ingestion.job_types import classify_role

        result = classify_role(
            "AI Strategy Director", "Lead digital transformation AI initiatives"
        )
        assert result == "marketing"

    def test_ambiguous_role_no_signal_keywords(self):
        from ai_washer.ingestion.job_types import classify_role

        result = classify_role("Software Engineer", "Build web applications")
        assert result == "ambiguous"

    def test_engineering_wins_ties(self):
        from ai_washer.ingestion.job_types import classify_role

        # One engineering keyword (ml engineer) and one marketing keyword (ai strategy)
        result = classify_role("ML Engineer", "Lead ai strategy initiatives")
        assert result == "engineering"

    def test_case_insensitive(self):
        from ai_washer.ingestion.job_types import classify_role

        result = classify_role("MACHINE LEARNING ENGINEER", "BUILD PYTORCH MODELS")
        assert result == "engineering"


class TestComputeJobHash:
    """Tests for the compute_job_hash function."""

    def test_deterministic_output(self):
        from ai_washer.ingestion.job_types import compute_job_hash

        h1 = compute_job_hash("Apple Inc", "ML Engineer", "Cupertino, CA")
        h2 = compute_job_hash("Apple Inc", "ML Engineer", "Cupertino, CA")
        assert h1 == h2

    def test_case_and_whitespace_insensitive(self):
        from ai_washer.ingestion.job_types import compute_job_hash

        h1 = compute_job_hash("Apple Inc", "ML Engineer", "Cupertino, CA")
        h2 = compute_job_hash("apple inc", " ML Engineer ", "cupertino, ca")
        assert h1 == h2

    def test_different_company_different_hash(self):
        from ai_washer.ingestion.job_types import compute_job_hash

        h1 = compute_job_hash("Apple", "ML Engineer", "Cupertino")
        h2 = compute_job_hash("Google", "ML Engineer", "Cupertino")
        assert h1 != h2

    def test_returns_64_char_hex_digest(self):
        from ai_washer.ingestion.job_types import compute_job_hash

        h = compute_job_hash("Test Co", "Engineer", "NYC")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestJobRecord:
    """Tests for JobRecord Pydantic model."""

    def test_valid_job_record(self):
        from ai_washer.ingestion.job_types import JobRecord

        record = JobRecord(
            title="ML Engineer",
            company_name_raw="Apple Inc",
            location="Cupertino, CA",
            description="Build ML models",
            job_url="https://example.com/job/123",
            source_site="indeed",
            role_classification="engineering",
            dedup_hash="a" * 64,
        )
        assert record.title == "ML Engineer"
        assert record.source_site == "indeed"

    def test_rejects_empty_title(self):
        from ai_washer.ingestion.job_types import JobRecord

        with pytest.raises(ValidationError):
            JobRecord(
                title="",
                company_name_raw="Apple",
                source_site="indeed",
                role_classification="engineering",
                dedup_hash="a" * 64,
            )

    def test_rejects_wrong_hash_length(self):
        from ai_washer.ingestion.job_types import JobRecord

        with pytest.raises(ValidationError):
            JobRecord(
                title="ML Engineer",
                company_name_raw="Apple",
                source_site="indeed",
                role_classification="engineering",
                dedup_hash="tooshort",
            )

    def test_optional_fields_default_none(self):
        from ai_washer.ingestion.job_types import JobRecord

        record = JobRecord(
            title="Engineer",
            company_name_raw="Acme",
            source_site="linkedin",
            role_classification="ambiguous",
            dedup_hash="b" * 64,
        )
        assert record.location is None
        assert record.description is None
        assert record.job_url is None


class TestJobCollectionResult:
    """Tests for JobCollectionResult Pydantic model."""

    def test_defaults(self):
        from ai_washer.ingestion.job_types import JobCollectionResult

        result = JobCollectionResult(company_cik="0001234567")
        assert result.jobs_found == 0
        assert result.jobs_new == 0
        assert result.jobs_updated == 0
        assert result.errors == []

    def test_with_values(self):
        from ai_washer.ingestion.job_types import JobCollectionResult

        result = JobCollectionResult(
            company_cik="0001234567",
            jobs_found=10,
            jobs_new=5,
            jobs_updated=3,
            errors=["timeout on page 3"],
        )
        assert result.jobs_found == 10
        assert result.errors == ["timeout on page 3"]


class TestConstants:
    """Tests for module constants."""

    def test_signal_version(self):
        from ai_washer.ingestion.job_types import JOB_SIGNAL_VERSION

        assert JOB_SIGNAL_VERSION == "0.8.0"

    def test_engineering_keywords_not_empty(self):
        from ai_washer.ingestion.job_types import ENGINEERING_KEYWORDS

        assert len(ENGINEERING_KEYWORDS) >= 10

    def test_marketing_keywords_not_empty(self):
        from ai_washer.ingestion.job_types import MARKETING_KEYWORDS

        assert len(MARKETING_KEYWORDS) >= 5
