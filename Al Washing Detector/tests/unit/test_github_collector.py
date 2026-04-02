"""Unit tests for GitHubCollector.

Tests cover collect_for_company with/without github_org alias,
idempotent skip for already-collected repos, collect_all iteration,
inter-company delay, and GitHubClientError graceful handling.
All tests use mocked GitHubClient and mock database sessions.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from ai_washer.ingestion.github_client import GitHubClientError
from ai_washer.ingestion.github_types import (
    GITHUB_SIGNAL_VERSION,
    GitHubCollectionResult,
    GitHubOrgSnapshot,
    GitHubRepoRecord,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COMPANY_ID = uuid.uuid4()
COMPANY_NAME = "Acme Corp"


def _make_repo_record(
    full_name: str = "acme/ml-engine",
    name: str = "ml-engine",
    language: str | None = "Python",
    pushed_at: datetime | None = None,
    language_bytes: dict[str, int] | None = None,
    ml_frameworks: list[str] | None = None,
) -> GitHubRepoRecord:
    return GitHubRepoRecord(
        repo_full_name=full_name,
        repo_name=name,
        primary_language=language,
        language_bytes=language_bytes or {"Python": 5000},
        pushed_at=pushed_at or datetime(2025, 6, 1, tzinfo=timezone.utc),
        is_fork=False,
        is_archived=False,
        stargazers_count=10,
        ml_frameworks=ml_frameworks or ["pytorch"],
    )


def _make_snapshot(
    repos: list[GitHubRepoRecord] | None = None,
) -> GitHubOrgSnapshot:
    repos = repos or [_make_repo_record()]
    return GitHubOrgSnapshot(
        repo_count=len(repos),
        total_ml_language_bytes=5000,
        total_language_bytes=10000,
        ml_language_ratio=0.5,
        days_since_last_push=30,
        ml_frameworks_found=["pytorch"],
        repos=repos,
    )


@pytest.fixture()
def mock_github_client():
    """Create a mocked GitHubClient."""
    client = MagicMock()
    client.build_org_snapshot.return_value = _make_snapshot()
    client.close = MagicMock()
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
def collector(mock_github_client, mock_session_factory):
    """Create a GitHubCollector with mocked dependencies."""
    from ai_washer.ingestion.github_collector import GitHubCollector

    c = GitHubCollector.__new__(GitHubCollector)
    c._log = MagicMock()
    c._github_client = mock_github_client
    c._session_factory = mock_session_factory
    c._max_repos_per_org = 100
    return c


# ---------------------------------------------------------------------------
# Test 1: collect_for_company with github_org calls build_org_snapshot
# ---------------------------------------------------------------------------


class TestCollectForCompanyWithOrg:
    """Test collect_for_company with a github_org alias."""

    def test_calls_build_org_snapshot_and_persists(
        self, collector, mock_github_client, mock_session_factory
    ) -> None:
        """Verify build_org_snapshot called and GitHubRepo rows created."""
        mock_session = mock_session_factory.return_value.__enter__.return_value
        # No existing repos (first collection)
        mock_exists = MagicMock()
        mock_exists.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_exists

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            github_org="acme",
            collection_date=date(2025, 7, 1),
        )

        mock_github_client.build_org_snapshot.assert_called_once_with(
            "acme", max_repos=100
        )
        assert result.repo_count == 1
        assert mock_session.add.call_count == 1
        mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: collect_for_company without github_org skips
# ---------------------------------------------------------------------------


class TestCollectForCompanyWithoutOrg:
    """Test collect_for_company without github_org alias."""

    def test_returns_empty_result_for_none(
        self, collector, mock_github_client
    ) -> None:
        """github_org=None returns repo_count=0."""
        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            github_org=None,
        )
        assert result.repo_count == 0
        mock_github_client.build_org_snapshot.assert_not_called()

    def test_returns_empty_result_for_empty_string(
        self, collector, mock_github_client
    ) -> None:
        """github_org='' returns repo_count=0."""
        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            github_org="",
        )
        assert result.repo_count == 0
        mock_github_client.build_org_snapshot.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: Idempotent -- skips already-persisted repos
# ---------------------------------------------------------------------------


class TestIdempotentCollection:
    """Test that re-running on same day skips existing repos."""

    def test_skips_existing_repo(
        self, collector, mock_github_client, mock_session_factory
    ) -> None:
        """Repo already in DB for same observed_date is skipped."""
        mock_session = mock_session_factory.return_value.__enter__.return_value

        # Simulate existing repo found
        mock_exists = MagicMock()
        mock_exists.scalar_one_or_none.return_value = MagicMock()  # exists!
        mock_session.execute.return_value = mock_exists

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            github_org="acme",
            collection_date=date(2025, 7, 1),
        )

        assert result.repo_count == 0
        assert result.skipped_count == 1
        mock_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: collect_all iterates active companies
# ---------------------------------------------------------------------------


class TestCollectAll:
    """Test collect_all iterates companies."""

    def test_iterates_active_companies(
        self, collector, mock_github_client, mock_session_factory
    ) -> None:
        """collect_all processes each company with github_org alias."""
        # Setup: query returns two companies
        company1 = MagicMock()
        company1.id = uuid.uuid4()
        company1.cik = "0001234567"
        company1.aliases = {"github_org": "acme"}
        company1.is_active = True

        company2 = MagicMock()
        company2.id = uuid.uuid4()
        company2.cik = "0009876543"
        company2.aliases = {"github_org": "betacorp"}
        company2.is_active = True

        # First call: companies query
        mock_companies_result = MagicMock()
        mock_companies_result.scalars.return_value.all.return_value = [company1, company2]

        # Subsequent calls: per-company repo existence checks
        mock_no_exist = MagicMock()
        mock_no_exist.scalar_one_or_none.return_value = None

        mock_session = mock_session_factory.return_value.__enter__.return_value

        # First call to session_factory is for companies query (in collect_all)
        # Then for each company, collect_for_company opens its own session
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
                # Per-company repo existence checks
                result = MagicMock()
                result.scalar_one_or_none.return_value = None
                session.execute.return_value = result
            return session

        mock_session_factory.side_effect = side_effect_factory

        with patch("ai_washer.ingestion.github_collector.time") as mock_time:
            results = collector.collect_all(collection_date=date(2025, 7, 1))

        assert len(results) == 2
        assert mock_github_client.build_org_snapshot.call_count == 2


# ---------------------------------------------------------------------------
# Test 5: collect_all sleeps between companies
# ---------------------------------------------------------------------------


class TestCollectAllDelay:
    """Test rate limit delay between companies."""

    def test_sleeps_between_companies(
        self, collector, mock_github_client, mock_session_factory
    ) -> None:
        """Verify time.sleep called between companies."""
        company1 = MagicMock()
        company1.id = uuid.uuid4()
        company1.cik = "0001234567"
        company1.aliases = {"github_org": "acme"}

        company2 = MagicMock()
        company2.id = uuid.uuid4()
        company2.cik = "0009876543"
        company2.aliases = {"github_org": "beta"}

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
                session.execute.return_value = result
            return session

        mock_session_factory.side_effect = side_effect_factory

        with patch("ai_washer.ingestion.github_collector.time") as mock_time:
            results = collector.collect_all(collection_date=date(2025, 7, 1))

        # Should sleep between first and second company (once)
        assert mock_time.sleep.call_count >= 1


# ---------------------------------------------------------------------------
# Test 6: GitHubClientError handled gracefully
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test graceful error handling for GitHubClientError."""

    def test_client_error_returns_result_with_error(
        self, collector, mock_github_client, mock_session_factory
    ) -> None:
        """GitHubClientError does not crash, produces error in result."""
        mock_github_client.build_org_snapshot.side_effect = GitHubClientError(
            "Rate limit exceeded"
        )

        result = collector.collect_for_company(
            company_id=COMPANY_ID,
            github_org="acme",
        )

        assert result.repo_count == 0
        assert len(result.errors) >= 1
        assert "Rate limit exceeded" in result.errors[0]
