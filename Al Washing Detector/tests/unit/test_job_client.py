"""Unit tests for JobClient wrapper around python-jobspy.

Tests cover search_company_jobs with mocked scrape_jobs, empty DataFrame
handling, error wrapping in JobClientError, role classification and
dedup hash population, and default site configuration.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from ai_washer.ingestion.job_client import JobClient, JobClientError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_DF = pd.DataFrame(
    [
        {
            "title": "ML Engineer",
            "company": "Apple Inc",
            "location": "Cupertino, CA",
            "description": "Build machine learning models with pytorch and tensorflow",
            "job_url": "https://indeed.com/job/1",
            "site": "indeed",
        },
        {
            "title": "AI Strategy Director",
            "company": "Apple Inc",
            "location": "Austin, TX",
            "description": "Lead AI-powered digital transformation initiatives",
            "job_url": "https://google.com/job/2",
            "site": "google",
        },
        {
            "title": "Software Developer",
            "company": "Apple Inc",
            "location": "Seattle, WA",
            "description": "Build backend services for cloud platform",
            "job_url": "https://indeed.com/job/3",
            "site": "indeed",
        },
    ]
)

EMPTY_DF = pd.DataFrame()


# ---------------------------------------------------------------------------
# Tests: search_company_jobs
# ---------------------------------------------------------------------------


class TestSearchCompanyJobs:
    """Tests for JobClient.search_company_jobs."""

    @patch("ai_washer.ingestion.job_client.scrape_jobs")
    def test_returns_job_records_from_dataframe(self, mock_scrape: MagicMock) -> None:
        """Mock scrape_jobs returning 3-row DataFrame, verify list[JobRecord]."""
        mock_scrape.return_value = SAMPLE_DF.copy()

        client = JobClient()
        records = client.search_company_jobs("Apple Inc")

        assert len(records) == 3
        assert records[0].title == "ML Engineer"
        assert records[0].company_name_raw == "Apple Inc"
        assert records[0].source_site == "indeed"
        assert records[0].location == "Cupertino, CA"

    @patch("ai_washer.ingestion.job_client.scrape_jobs")
    def test_empty_dataframe_returns_empty_list(self, mock_scrape: MagicMock) -> None:
        """Empty DataFrame from jobspy returns empty list, no error."""
        mock_scrape.return_value = EMPTY_DF.copy()

        client = JobClient()
        records = client.search_company_jobs("Apple Inc")

        assert records == []

    @patch("ai_washer.ingestion.job_client.scrape_jobs")
    def test_exception_wraps_in_job_client_error(self, mock_scrape: MagicMock) -> None:
        """Exception from scrape_jobs is wrapped in JobClientError."""
        mock_scrape.side_effect = RuntimeError("Connection refused")

        client = JobClient()
        with pytest.raises(JobClientError, match="Connection refused"):
            client.search_company_jobs("Apple Inc")

    @patch("ai_washer.ingestion.job_client.scrape_jobs")
    def test_role_classification_populated(self, mock_scrape: MagicMock) -> None:
        """Each record has role_classification set by classify_role."""
        mock_scrape.return_value = SAMPLE_DF.copy()

        client = JobClient()
        records = client.search_company_jobs("Apple Inc")

        # ML Engineer + pytorch/tensorflow description -> engineering
        assert records[0].role_classification == "engineering"
        # AI Strategy Director + digital transformation -> marketing
        assert records[1].role_classification == "marketing"
        # Software Developer + generic description -> ambiguous
        assert records[2].role_classification == "ambiguous"

    @patch("ai_washer.ingestion.job_client.scrape_jobs")
    def test_dedup_hash_populated(self, mock_scrape: MagicMock) -> None:
        """Each record has a 64-char hex dedup_hash from compute_job_hash."""
        mock_scrape.return_value = SAMPLE_DF.copy()

        client = JobClient()
        records = client.search_company_jobs("Apple Inc")

        for record in records:
            assert len(record.dedup_hash) == 64
            # All hashes should be unique (different title+location combos)
        hashes = [r.dedup_hash for r in records]
        assert len(set(hashes)) == 3


# ---------------------------------------------------------------------------
# Tests: Default configuration
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    """Tests for JobClient default settings."""

    def test_default_sites(self) -> None:
        """Default sites are indeed and google (no LinkedIn)."""
        client = JobClient()
        assert client._sites == ["indeed", "google"]

    def test_default_results_wanted(self) -> None:
        """Default results_wanted is 50."""
        client = JobClient()
        assert client._results_wanted == 50

    def test_custom_sites(self) -> None:
        """Custom sites override defaults."""
        client = JobClient(sites=["indeed"])
        assert client._sites == ["indeed"]

    @patch("ai_washer.ingestion.job_client.scrape_jobs")
    def test_passes_sites_and_results_wanted(self, mock_scrape: MagicMock) -> None:
        """scrape_jobs called with configured sites and results_wanted."""
        mock_scrape.return_value = EMPTY_DF.copy()

        client = JobClient(sites=["indeed"], results_wanted=25)
        client.search_company_jobs("Apple Inc")

        mock_scrape.assert_called_once()
        call_kwargs = mock_scrape.call_args
        assert call_kwargs.kwargs.get("site_name") == ["indeed"]
        assert call_kwargs.kwargs.get("results_wanted") == 25


# ---------------------------------------------------------------------------
# Tests: NaN handling
# ---------------------------------------------------------------------------


class TestNanHandling:
    """Tests for handling NaN values in DataFrame columns."""

    @patch("ai_washer.ingestion.job_client.scrape_jobs")
    def test_nan_values_become_none(self, mock_scrape: MagicMock) -> None:
        """NaN in optional fields (location, description, job_url) becomes None."""
        df = pd.DataFrame(
            [
                {
                    "title": "ML Engineer",
                    "company": "Apple Inc",
                    "location": float("nan"),
                    "description": float("nan"),
                    "job_url": float("nan"),
                    "site": "indeed",
                },
            ]
        )
        mock_scrape.return_value = df

        client = JobClient()
        records = client.search_company_jobs("Apple Inc")

        assert len(records) == 1
        assert records[0].location is None
        assert records[0].description is None
        assert records[0].job_url is None
