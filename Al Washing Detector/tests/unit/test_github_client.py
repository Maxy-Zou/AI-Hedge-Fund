"""Unit tests for GitHub REST API client.

Tests cover org repo listing, language fetching, file content retrieval,
ML framework detection, rate limit tracking, retry logic, authentication
errors, and org snapshot aggregation.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import pytest
from freezegun import freeze_time

from ai_washer.ingestion.github_client import GitHubClient, GitHubClientError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_REPOS = [
    {
        "full_name": "acme/ml-engine",
        "name": "ml-engine",
        "language": "Python",
        "pushed_at": "2026-03-01T12:00:00Z",
        "fork": False,
        "archived": False,
        "stargazers_count": 42,
    },
    {
        "full_name": "acme/web-app",
        "name": "web-app",
        "language": "JavaScript",
        "pushed_at": "2026-02-15T08:30:00Z",
        "fork": False,
        "archived": False,
        "stargazers_count": 10,
    },
]

FORKED_REPO = {
    "full_name": "acme/forked-lib",
    "name": "forked-lib",
    "language": "Python",
    "pushed_at": "2026-01-01T00:00:00Z",
    "fork": True,
    "archived": False,
    "stargazers_count": 0,
}


@pytest.fixture()
def token() -> str:
    return "ghp_test_token_12345"


@pytest.fixture()
def base_url() -> str:
    return "https://api.github.com"


# ---------------------------------------------------------------------------
# Tests: list_org_repos
# ---------------------------------------------------------------------------


class TestListOrgRepos:
    """Tests for list_org_repos method."""

    def test_returns_repo_records(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """Mock 200 with 2 repos, verify GitHubRepoRecord list."""
        httpx_mock.add_response(
            url=httpx.URL(
                f"{base_url}/orgs/acme/repos",
                params={
                    "type": "public",
                    "sort": "pushed",
                    "direction": "desc",
                    "per_page": "100",
                    "page": "1",
                },
            ),
            json=SAMPLE_REPOS,
        )

        client = GitHubClient(token=token, base_url=base_url)
        repos = client.list_org_repos("acme")

        assert len(repos) == 2
        assert repos[0].repo_full_name == "acme/ml-engine"
        assert repos[0].repo_name == "ml-engine"
        assert repos[0].primary_language == "Python"
        assert repos[0].is_fork is False
        assert repos[0].is_archived is False
        assert repos[0].stargazers_count == 42
        assert repos[0].pushed_at == datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_filters_forks(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """Forked repos should be excluded from results."""
        httpx_mock.add_response(
            json=[SAMPLE_REPOS[0], FORKED_REPO, SAMPLE_REPOS[1]],
        )

        client = GitHubClient(token=token, base_url=base_url)
        repos = client.list_org_repos("acme")

        assert len(repos) == 2
        for repo in repos:
            assert repo.is_fork is False

    def test_pagination(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """When first page is full (100 items), fetch next page."""
        # Page 1: 100 repos (full page)
        page1 = [
            {
                "full_name": f"acme/repo-{i}",
                "name": f"repo-{i}",
                "language": "Python",
                "pushed_at": "2026-03-01T00:00:00Z",
                "fork": False,
                "archived": False,
                "stargazers_count": i,
            }
            for i in range(100)
        ]
        # Page 2: 20 repos (partial page, stops)
        page2 = [
            {
                "full_name": f"acme/repo-{100 + i}",
                "name": f"repo-{100 + i}",
                "language": "Python",
                "pushed_at": "2026-03-01T00:00:00Z",
                "fork": False,
                "archived": False,
                "stargazers_count": 100 + i,
            }
            for i in range(20)
        ]

        httpx_mock.add_response(json=page1)
        httpx_mock.add_response(json=page2)

        client = GitHubClient(token=token, base_url=base_url)
        repos = client.list_org_repos("acme", max_repos=200)

        assert len(repos) == 120
        assert len(httpx_mock.get_requests()) == 2

    def test_respects_max_repos(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """max_repos parameter caps the results even from a single page."""
        page1 = [
            {
                "full_name": f"acme/repo-{i}",
                "name": f"repo-{i}",
                "language": "Python",
                "pushed_at": "2026-03-01T00:00:00Z",
                "fork": False,
                "archived": False,
                "stargazers_count": i,
            }
            for i in range(100)
        ]

        httpx_mock.add_response(json=page1)

        client = GitHubClient(token=token, base_url=base_url)
        repos = client.list_org_repos("acme", max_repos=50)

        assert len(repos) == 50


# ---------------------------------------------------------------------------
# Tests: get_repo_languages
# ---------------------------------------------------------------------------


class TestGetRepoLanguages:
    """Tests for get_repo_languages method."""

    def test_returns_language_bytes(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """Mock 200 with language bytes, verify dict returned."""
        httpx_mock.add_response(
            json={"Python": 150000, "C++": 30000, "Shell": 5000},
        )

        client = GitHubClient(token=token, base_url=base_url)
        languages = client.get_repo_languages("acme", "ml-engine")

        assert languages == {"Python": 150000, "C++": 30000, "Shell": 5000}


# ---------------------------------------------------------------------------
# Tests: get_file_content
# ---------------------------------------------------------------------------


class TestGetFileContent:
    """Tests for get_file_content method."""

    def test_returns_file_text(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """Mock 200 with raw file content, verify string returned."""
        httpx_mock.add_response(
            text="tensorflow==2.15.0\nnumpy>=1.24\n",
        )

        client = GitHubClient(token=token, base_url=base_url)
        content = client.get_file_content("acme", "ml-engine", "requirements.txt")

        assert content is not None
        assert "tensorflow" in content

    def test_returns_none_on_404(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """404 for missing file returns None, no exception."""
        httpx_mock.add_response(status_code=404)

        client = GitHubClient(token=token, base_url=base_url)
        content = client.get_file_content("acme", "ml-engine", "nonexistent.txt")

        assert content is None


# ---------------------------------------------------------------------------
# Tests: scan_ml_frameworks
# ---------------------------------------------------------------------------


class TestScanMlFrameworks:
    """Tests for scan_ml_frameworks method."""

    def test_detects_tensorflow(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """Detect tensorflow in requirements.txt content."""
        # requirements.txt found
        httpx_mock.add_response(text="tensorflow==2.15.0\nnumpy>=1.24\n")
        # pyproject.toml not found
        httpx_mock.add_response(status_code=404)
        # setup.py not found
        httpx_mock.add_response(status_code=404)
        # setup.cfg not found
        httpx_mock.add_response(status_code=404)

        client = GitHubClient(token=token, base_url=base_url)
        frameworks = client.scan_ml_frameworks("acme", "ml-engine")

        assert "tensorflow" in frameworks

    def test_detects_pytorch(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """Detect pytorch (torch) in pyproject.toml content."""
        # requirements.txt not found
        httpx_mock.add_response(status_code=404)
        # pyproject.toml found with torch
        httpx_mock.add_response(
            text='[project]\ndependencies = [\n  "torch>=2.0",\n  "numpy",\n]\n'
        )
        # setup.py not found
        httpx_mock.add_response(status_code=404)
        # setup.cfg not found
        httpx_mock.add_response(status_code=404)

        client = GitHubClient(token=token, base_url=base_url)
        frameworks = client.scan_ml_frameworks("acme", "ml-engine")

        assert "pytorch" in frameworks

    def test_returns_empty_on_no_deps(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """All dependency files 404 → empty list."""
        for _ in range(4):
            httpx_mock.add_response(status_code=404)

        client = GitHubClient(token=token, base_url=base_url)
        frameworks = client.scan_ml_frameworks("acme", "ml-engine")

        assert frameworks == []


# ---------------------------------------------------------------------------
# Tests: Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    """Tests for rate limit tracking."""

    def test_updates_rate_limit_from_headers(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """x-ratelimit-remaining header is tracked."""
        httpx_mock.add_response(
            json={"Python": 100000},
            headers={"x-ratelimit-remaining": "4500"},
        )

        client = GitHubClient(token=token, base_url=base_url)
        client.get_repo_languages("acme", "ml-engine")

        assert client.rate_limit_remaining == 4500


# ---------------------------------------------------------------------------
# Tests: Retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    """Tests for tenacity retry on transient errors."""

    def test_retries_on_429(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """429 triggers retry, second request succeeds."""
        httpx_mock.add_response(status_code=429)
        httpx_mock.add_response(json=SAMPLE_REPOS)

        client = GitHubClient(token=token, base_url=base_url)
        repos = client.list_org_repos("acme")

        assert len(repos) == 2
        assert len(httpx_mock.get_requests()) == 2

    def test_retries_on_500(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """500 triggers retry, second request succeeds."""
        httpx_mock.add_response(status_code=500)
        httpx_mock.add_response(json=SAMPLE_REPOS)

        client = GitHubClient(token=token, base_url=base_url)
        repos = client.list_org_repos("acme")

        assert len(repos) == 2
        assert len(httpx_mock.get_requests()) == 2


# ---------------------------------------------------------------------------
# Tests: Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for authentication and client errors."""

    def test_401_raises_client_error(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """401 should raise GitHubClientError, not retry."""
        httpx_mock.add_response(status_code=401)

        client = GitHubClient(token=token, base_url=base_url)
        with pytest.raises(GitHubClientError, match="Authentication failed"):
            client.list_org_repos("acme")

    def test_empty_token_raises_on_request(
        self, base_url: str
    ) -> None:
        """Empty token raises GitHubClientError on first API call."""
        client = GitHubClient(token="", base_url=base_url)
        with pytest.raises(GitHubClientError, match="token"):
            client.list_org_repos("acme")


# ---------------------------------------------------------------------------
# Tests: build_org_snapshot
# ---------------------------------------------------------------------------


class TestBuildOrgSnapshot:
    """Tests for build_org_snapshot aggregation."""

    @freeze_time("2026-03-29", ignore=["torch", "transformers"])
    def test_aggregates_repos(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """Verify snapshot aggregates repos with correct ml_language_ratio and days."""
        # list_org_repos response
        httpx_mock.add_response(json=SAMPLE_REPOS)

        # For acme/ml-engine: get_repo_languages
        httpx_mock.add_response(
            json={"Python": 150000, "C++": 30000},
        )
        # For acme/ml-engine: scan_ml_frameworks (4 dep files)
        httpx_mock.add_response(text="tensorflow==2.15.0\ntorch>=2.0\n")
        httpx_mock.add_response(status_code=404)
        httpx_mock.add_response(status_code=404)
        httpx_mock.add_response(status_code=404)

        # For acme/web-app: get_repo_languages
        httpx_mock.add_response(
            json={"JavaScript": 200000, "Python": 10000},
        )
        # For acme/web-app: scan_ml_frameworks (4 dep files)
        httpx_mock.add_response(status_code=404)
        httpx_mock.add_response(status_code=404)
        httpx_mock.add_response(status_code=404)
        httpx_mock.add_response(status_code=404)

        client = GitHubClient(token=token, base_url=base_url)
        snapshot = client.build_org_snapshot("acme")

        assert snapshot.repo_count == 2
        # Python (150000+10000) + C++ (30000) = 190000 ML bytes
        # Total = Python 160000 + C++ 30000 + JavaScript 200000 = 390000
        assert snapshot.total_ml_language_bytes == 190000
        assert snapshot.total_language_bytes == 390000
        assert snapshot.ml_language_ratio == pytest.approx(190000 / 390000)
        # Most recent push: 2026-03-01T12:00:00Z, reference: 2026-03-29T00:00:00Z → 27 days
        assert snapshot.days_since_last_push == 27
        assert "pytorch" in snapshot.ml_frameworks_found
        assert "tensorflow" in snapshot.ml_frameworks_found

    def test_zero_repos_snapshot(
        self, httpx_mock, token: str, base_url: str
    ) -> None:
        """Zero repos returns snapshot with defaults."""
        httpx_mock.add_response(json=[])

        client = GitHubClient(token=token, base_url=base_url)
        snapshot = client.build_org_snapshot("acme")

        assert snapshot.repo_count == 0
        assert snapshot.ml_language_ratio == 0.0
        assert snapshot.days_since_last_push is None
        assert snapshot.ml_frameworks_found == []
        assert snapshot.repos == []
