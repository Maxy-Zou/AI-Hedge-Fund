"""Unit tests for JobCollector orchestrator.

Tests cover lifecycle tracking: new posting insertion, last_seen update
for existing postings, stale posting deactivation, empty scrape results,
collect_all iteration with delay, and error handling.
All tests use mocked JobClient and mock database sessions.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from ai_washer.ingestion.job_types import JobCollectionResult, JobRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COMPANY_ID = uuid.uuid4()
COMPANY_NAME = "Acme Corp"
COMPANY_CIK = "0001234567"


def _make_job_record(
    title: str = "ML Engineer",
    company: str = "Acme Corp",
    location: str = "Cupertino, CA",
    description: str = "Build ML models with pytorch",
    source_site: str = "indeed",
    role_classification: str = "engineering",
    dedup_hash: str | None = None,
) -> JobRecord:
    if dedup_hash is None:
        from ai_washer.ingestion.job_types import compute_job_hash

        dedup_hash = compute_job_hash(company, title, location)
    return JobRecord(
        title=title,
        company_name_raw=company,
        location=location,
        description=description,
        job_url="https://indeed.com/job/1",
        source_site=source_site,
        role_classification=role_classification,
        dedup_hash=dedup_hash,
    )


@pytest.fixture()
def mock_job_client():
    """Create a mocked JobClient."""
    client = MagicMock()
    client.search_company_jobs.return_value = [_make_job_record()]
    return client


@pytest.fixture()
def mock_session_factory():
    """Create a mocked session factory returning a mock session."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    mock_factory = MagicMock(return_value=mock_session)
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    return mock_factory


@pytest.fixture()
def collector(mock_job_client, mock_session_factory):
    """Create a JobCollector with mocked dependencies."""
    from ai_washer.ingestion.job_collector import JobCollector

    c = JobCollector.__new__(JobCollector)
    c._log = MagicMock()
    c._client = mock_job_client
    c._session_factory = mock_session_factory
    return c


# ---------------------------------------------------------------------------
# Test 1: New posting insertion
# ---------------------------------------------------------------------------


class TestNewPostingInsertion:
    """Test collect_for_company inserts new postings when dedup_hash not in DB."""

    def test_inserts_new_posting(
        self, collector, mock_job_client, mock_session_factory
    ) -> None:
        """New dedup_hash results in a DB add call."""
        mock_session = mock_session_factory.return_value.__enter__.return_value
        # No existing posting (dedup_hash not found)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        # scalars().all() returns empty (no stale postings to deactivate)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            cik=COMPANY_CIK,
            collection_date=date(2026, 3, 29),
        )

        assert result.jobs_new >= 1
        assert mock_session.add.call_count >= 1
        mock_session.commit.assert_called()


# ---------------------------------------------------------------------------
# Test 2: Existing posting last_seen update
# ---------------------------------------------------------------------------


class TestExistingPostingUpdate:
    """Test collect_for_company updates last_seen when dedup_hash exists."""

    def test_updates_last_seen(
        self, collector, mock_job_client, mock_session_factory
    ) -> None:
        """Existing dedup_hash triggers last_seen update, not insert."""
        mock_session = mock_session_factory.return_value.__enter__.return_value

        # Simulate existing posting found by dedup_hash
        existing_posting = MagicMock()
        existing_posting.last_seen = date(2026, 3, 28)
        existing_posting.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_posting
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            cik=COMPANY_CIK,
            collection_date=date(2026, 3, 29),
        )

        assert result.jobs_updated >= 1
        # last_seen should be updated to collection_date
        assert existing_posting.last_seen == date(2026, 3, 29)
        assert existing_posting.is_active is True


# ---------------------------------------------------------------------------
# Test 3: Stale postings marked inactive
# ---------------------------------------------------------------------------


class TestStalePostingDeactivation:
    """Test collect_for_company sets is_active=False on stale postings."""

    def test_deactivates_stale_postings(
        self, collector, mock_job_client, mock_session_factory
    ) -> None:
        """Postings not seen in current scrape get is_active=False."""
        mock_session = mock_session_factory.return_value.__enter__.return_value

        # First call: dedup_hash lookup returns None (new posting)
        # Second call: stale postings query returns one stale posting
        stale_posting = MagicMock()
        stale_posting.is_active = True
        stale_posting.last_seen = date(2026, 3, 27)

        call_count = 0

        def execute_side_effect(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Dedup hash lookup: not found
                result.scalar_one_or_none.return_value = None
            else:
                # Stale postings query
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = [stale_posting]
                result.scalars = MagicMock(return_value=mock_scalars)
            return result

        mock_session.execute.side_effect = execute_side_effect

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            cik=COMPANY_CIK,
            collection_date=date(2026, 3, 29),
        )

        # Stale posting should be deactivated
        assert stale_posting.is_active is False


# ---------------------------------------------------------------------------
# Test 4: Empty scrape returns zero counts
# ---------------------------------------------------------------------------


class TestEmptyScrape:
    """Test empty scrape result returns zero counts without error."""

    def test_empty_scrape_returns_zeros(
        self, collector, mock_job_client, mock_session_factory
    ) -> None:
        """No jobs found returns JobCollectionResult with zero counts."""
        mock_job_client.search_company_jobs.return_value = []

        mock_session = mock_session_factory.return_value.__enter__.return_value
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute.return_value = mock_result

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            cik=COMPANY_CIK,
        )

        assert result.jobs_found == 0
        assert result.jobs_new == 0
        assert result.jobs_updated == 0
        assert result.errors == []


# ---------------------------------------------------------------------------
# Test 5: collect_all iterates active companies
# ---------------------------------------------------------------------------


class TestCollectAll:
    """Test collect_all iterates companies with delay."""

    def test_iterates_active_companies(
        self, collector, mock_job_client, mock_session_factory
    ) -> None:
        """collect_all processes each active company."""
        company1 = MagicMock()
        company1.id = uuid.uuid4()
        company1.name = "Acme Corp"
        company1.cik = "0001234567"
        company1.is_active = True

        company2 = MagicMock()
        company2.id = uuid.uuid4()
        company2.name = "Beta Inc"
        company2.cik = "0009876543"
        company2.is_active = True

        call_count = 0

        def side_effect_factory():
            nonlocal call_count
            call_count += 1
            session = MagicMock()
            session.__enter__ = MagicMock(return_value=session)
            session.__exit__ = MagicMock(return_value=False)
            if call_count == 1:
                # Companies query
                result = MagicMock()
                result.scalars.return_value.all.return_value = [company1, company2]
                session.execute.return_value = result
            else:
                # Per-company operations
                result = MagicMock()
                result.scalar_one_or_none.return_value = None
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = []
                result.scalars = MagicMock(return_value=mock_scalars)
                session.execute.return_value = result
            return session

        mock_session_factory.side_effect = side_effect_factory

        with patch("ai_washer.ingestion.job_collector.time") as mock_time:
            results = collector.collect_all(collection_date=date(2026, 3, 29))

        assert len(results) == 2
        assert mock_job_client.search_company_jobs.call_count == 2

    def test_sleeps_between_companies(
        self, collector, mock_job_client, mock_session_factory
    ) -> None:
        """Verify time.sleep called between companies."""
        company1 = MagicMock()
        company1.id = uuid.uuid4()
        company1.name = "Acme Corp"
        company1.cik = "0001234567"

        company2 = MagicMock()
        company2.id = uuid.uuid4()
        company2.name = "Beta Inc"
        company2.cik = "0009876543"

        call_count = 0

        def side_effect_factory():
            nonlocal call_count
            call_count += 1
            session = MagicMock()
            session.__enter__ = MagicMock(return_value=session)
            session.__exit__ = MagicMock(return_value=False)
            if call_count == 1:
                result = MagicMock()
                result.scalars.return_value.all.return_value = [company1, company2]
                session.execute.return_value = result
            else:
                result = MagicMock()
                result.scalar_one_or_none.return_value = None
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = []
                result.scalars = MagicMock(return_value=mock_scalars)
                session.execute.return_value = result
            return session

        mock_session_factory.side_effect = side_effect_factory

        with patch("ai_washer.ingestion.job_collector.time") as mock_time:
            collector.collect_all(collection_date=date(2026, 3, 29))

        assert mock_time.sleep.call_count >= 1


# ---------------------------------------------------------------------------
# Test 6: Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test graceful error handling for JobClientError."""

    def test_client_error_returns_result_with_error(
        self, collector, mock_job_client, mock_session_factory
    ) -> None:
        """JobClientError does not crash, produces error in result."""
        from ai_washer.ingestion.job_client import JobClientError

        mock_job_client.search_company_jobs.side_effect = JobClientError(
            "Scraping failed"
        )

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            company_name=COMPANY_NAME,
            cik=COMPANY_CIK,
        )

        assert result.jobs_found == 0
        assert len(result.errors) >= 1
        assert "Scraping failed" in result.errors[0]
