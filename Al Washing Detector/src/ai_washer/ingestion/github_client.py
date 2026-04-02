"""GitHub REST API v3 client for organization repository analysis.

Enumerates public repositories for a GitHub organization, fetches language
byte breakdowns, retrieves raw dependency file content, and detects ML
framework usage. Rate-limit-aware with tenacity-based retry logic for
429 and 5xx responses.

Usage::

    client = GitHubClient(token="ghp_...")
    snapshot = client.build_org_snapshot("acme-corp")
    print(snapshot.ml_language_ratio, snapshot.ml_frameworks_found)
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ai_washer.ingestion.github_types import (
    GitHubOrgSnapshot,
    GitHubRepoRecord,
    ML_FRAMEWORK_PATTERNS,
    ML_LANGUAGES,
)

logger = structlog.get_logger(__name__)

# Dependency files to scan for ML framework imports.
_DEPENDENCY_FILES: tuple[str, ...] = (
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
)


class GitHubClientError(Exception):
    """Raised when the GitHub API client encounters an error."""


def _is_retryable(exc: BaseException) -> bool:
    """Determine if an HTTP error should trigger a retry.

    Retries on 429 (rate limit) and 5xx (server errors).
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


class GitHubClient:
    """Client for the GitHub REST API v3.

    Lists organization repos, fetches language breakdowns, reads raw file
    content, and detects ML framework usage in dependency files.

    Parameters
    ----------
    token:
        GitHub personal access token. Empty string is accepted at
        construction time (lazy validation) but will raise
        GitHubClientError on first API call.
    base_url:
        Base URL for the GitHub API.
    client:
        Optional httpx.Client for dependency injection in tests.
    """

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.github.com",
        client: httpx.Client | None = None,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._log = logger.bind(client="github")
        self._rate_limit_remaining: int | None = None

        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            self._owns_client = True

    # -- Rate limit tracking --------------------------------------------------

    def _update_rate_limit(self, response: httpx.Response) -> None:
        """Read x-ratelimit-remaining from response headers."""
        remaining = response.headers.get("x-ratelimit-remaining")
        if remaining is not None:
            try:
                self._rate_limit_remaining = int(remaining)
            except ValueError:
                pass

    @property
    def rate_limit_remaining(self) -> int | None:
        """Expose the last-seen rate limit remaining value."""
        return self._rate_limit_remaining

    # -- HTTP layer -----------------------------------------------------------

    @retry(
        wait=wait_exponential(min=0.1, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    def _get(
        self,
        path: str,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        """Execute a GET request against the GitHub API.

        Parameters
        ----------
        path:
            URL path relative to base_url (e.g. ``/orgs/acme/repos``).
        params:
            Query parameters.
        headers:
            Additional headers to merge with defaults.

        Returns
        -------
        httpx.Response

        Raises
        ------
        GitHubClientError
            On empty token, 401, or 403.
        """
        if not self._token:
            raise GitHubClientError(
                "GitHub token is required. Set AI_WASHER_GITHUB_TOKEN "
                "environment variable or pass token to GitHubClient."
            )

        url = f"{self._base_url}{path}"
        merged_headers = {}
        if headers:
            merged_headers.update(headers)

        response = self._client.get(url, params=params, headers=merged_headers)
        self._update_rate_limit(response)

        if response.status_code in (401, 403):
            raise GitHubClientError(
                f"Authentication failed (HTTP {response.status_code}). "
                f"Check your GitHub token."
            )

        response.raise_for_status()
        return response

    # -- Public API -----------------------------------------------------------

    def list_org_repos(
        self, org: str, max_repos: int = 100
    ) -> list[GitHubRepoRecord]:
        """List public repositories for an organization.

        Paginates through the GitHub API, filtering out forked repos.

        Parameters
        ----------
        org:
            GitHub organization login name.
        max_repos:
            Maximum number of repos to return.

        Returns
        -------
        list[GitHubRepoRecord]
            Non-fork repos, ordered by most recently pushed.
        """
        all_repos: list[GitHubRepoRecord] = []
        page = 1

        while len(all_repos) < max_repos:
            response = self._get(
                f"/orgs/{org}/repos",
                params={
                    "type": "public",
                    "sort": "pushed",
                    "direction": "desc",
                    "per_page": "100",
                    "page": str(page),
                },
            )
            repos_data: list[dict] = response.json()

            if not repos_data:
                break

            for repo_dict in repos_data:
                if repo_dict.get("fork", False):
                    continue

                pushed_at_str = repo_dict.get("pushed_at")
                pushed_at_val: datetime | None = None
                if pushed_at_str:
                    pushed_at_val = datetime.fromisoformat(
                        pushed_at_str.replace("Z", "+00:00")
                    )

                record = GitHubRepoRecord(
                    repo_full_name=repo_dict["full_name"],
                    repo_name=repo_dict["name"],
                    primary_language=repo_dict.get("language"),
                    pushed_at=pushed_at_val,
                    is_fork=False,
                    is_archived=repo_dict.get("archived", False),
                    stargazers_count=repo_dict.get("stargazers_count", 0),
                )
                all_repos.append(record)

            if len(repos_data) < 100:
                break

            page += 1

        return all_repos[:max_repos]

    def get_repo_languages(self, owner: str, repo: str) -> dict[str, int]:
        """Fetch language byte breakdown for a repository.

        Parameters
        ----------
        owner:
            Repository owner (org or user).
        repo:
            Repository name.

        Returns
        -------
        dict[str, int]
            Language name to byte count mapping.
        """
        response = self._get(f"/repos/{owner}/{repo}/languages")
        return response.json()

    def get_file_content(
        self, owner: str, repo: str, path: str
    ) -> str | None:
        """Fetch raw file content from a repository.

        Parameters
        ----------
        owner:
            Repository owner.
        repo:
            Repository name.
        path:
            File path within the repository.

        Returns
        -------
        str | None
            File content as text, or None if file not found (404).
        """
        try:
            response = self._get(
                f"/repos/{owner}/{repo}/contents/{path}",
                headers={"Accept": "application/vnd.github.raw+json"},
            )
            return response.text
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    def scan_ml_frameworks(self, owner: str, repo: str) -> list[str]:
        """Detect ML frameworks from repository dependency files.

        Scans requirements.txt, pyproject.toml, setup.py, and setup.cfg
        for ML framework package names.

        Parameters
        ----------
        owner:
            Repository owner.
        repo:
            Repository name.

        Returns
        -------
        list[str]
            Sorted, deduplicated list of ML framework family keys.
        """
        detected: set[str] = set()

        for dep_file in _DEPENDENCY_FILES:
            content = self.get_file_content(owner, repo, dep_file)
            if content is None:
                continue

            content_lower = content.lower()
            for framework_key, package_names in ML_FRAMEWORK_PATTERNS.items():
                for pkg in package_names:
                    if pkg in content_lower:
                        detected.add(framework_key)
                        break

        return sorted(detected)

    def build_org_snapshot(
        self,
        org: str,
        max_repos: int = 100,
        reference_date: date | None = None,
    ) -> GitHubOrgSnapshot:
        """Build an aggregated snapshot of an organization's GitHub activity.

        Enumerates repos, fetches language breakdowns and dependency files
        for non-archived repos, and aggregates into an org-level snapshot.

        Parameters
        ----------
        org:
            GitHub organization login name.
        max_repos:
            Maximum repos to enumerate.
        reference_date:
            Date to compute days_since_last_push against. Defaults to today.

        Returns
        -------
        GitHubOrgSnapshot
        """
        if reference_date is None:
            reference_date = date.today()

        repos = self.list_org_repos(org, max_repos=max_repos)

        if not repos:
            return GitHubOrgSnapshot(
                repo_count=0,
                total_ml_language_bytes=0,
                total_language_bytes=0,
                ml_language_ratio=0.0,
                days_since_last_push=None,
                ml_frameworks_found=[],
                repos=[],
            )

        all_ml_frameworks: set[str] = set()
        total_language_bytes = 0
        total_ml_language_bytes = 0
        most_recent_push: datetime | None = None

        for repo in repos:
            if repo.is_archived:
                continue

            # Split owner/repo from full_name
            owner, repo_name = repo.repo_full_name.split("/", 1)

            # Fetch language breakdown
            lang_bytes = self.get_repo_languages(owner, repo_name)
            # Update the repo record with language bytes (create new record)
            repo.language_bytes = lang_bytes

            # Scan for ML frameworks
            frameworks = self.scan_ml_frameworks(owner, repo_name)
            repo.ml_frameworks = frameworks
            all_ml_frameworks.update(frameworks)

            # Aggregate language bytes
            for lang, byte_count in lang_bytes.items():
                total_language_bytes += byte_count
                if lang in ML_LANGUAGES:
                    total_ml_language_bytes += byte_count

            # Track most recent push
            if repo.pushed_at is not None:
                if most_recent_push is None or repo.pushed_at > most_recent_push:
                    most_recent_push = repo.pushed_at

        ml_language_ratio = (
            total_ml_language_bytes / total_language_bytes
            if total_language_bytes > 0
            else 0.0
        )

        days_since_last_push: int | None = None
        if most_recent_push is not None:
            ref_dt = datetime(
                reference_date.year,
                reference_date.month,
                reference_date.day,
                tzinfo=timezone.utc,
            )
            delta = ref_dt - most_recent_push
            days_since_last_push = delta.days

        self._log.info(
            "org_snapshot_complete",
            org=org,
            repo_count=len(repos),
            ml_frameworks=sorted(all_ml_frameworks),
            ml_language_ratio=round(ml_language_ratio, 4),
        )

        return GitHubOrgSnapshot(
            repo_count=len(repos),
            total_ml_language_bytes=total_ml_language_bytes,
            total_language_bytes=total_language_bytes,
            ml_language_ratio=ml_language_ratio,
            days_since_last_push=days_since_last_push,
            ml_frameworks_found=sorted(all_ml_frameworks),
            repos=repos,
        )

    # -- Lifecycle ------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client if owned by this instance."""
        if self._owns_client:
            self._client.close()
