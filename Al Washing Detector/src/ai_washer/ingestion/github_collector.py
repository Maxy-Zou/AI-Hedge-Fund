"""GitHub repository collection orchestrator.

Coordinates GitHubClient (API queries) and database persistence
into an idempotent pipeline. For each company with a github_org alias,
builds an org snapshot via the GitHub REST API and persists repo records
to the github_repos table.

Usage::

    from ai_washer.ingestion.github_collector import GitHubCollector
    collector = GitHubCollector(app_settings=settings)
    result = collector.collect_for_company(company_id, "acme-corp")
"""

from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timezone

import structlog
from sqlalchemy import select

from ai_washer.config import AppSettings
from ai_washer.db.models import Company, GitHubRepo
from ai_washer.db.session import create_engine_from_settings, get_session_factory
from ai_washer.ingestion.github_client import GitHubClient, GitHubClientError
from ai_washer.ingestion.github_types import (
    GITHUB_SIGNAL_VERSION,
    GitHubCollectionResult,
    GitHubRepoRecord,
)

logger = structlog.get_logger(__name__)

# Delay between companies in collect_all to respect API rate limits.
_INTER_COMPANY_DELAY = 1.0

# Log progress every N companies in collect_all.
_PROGRESS_LOG_INTERVAL = 10


class GitHubCollector:
    """Orchestrates GitHub repository collection from the REST API.

    For each company with a github_org alias, fetches the org snapshot
    (repos, languages, ML frameworks) and persists GitHubRepo rows.
    Follows the PatentCollector pattern from Phase 5.

    Parameters
    ----------
    app_settings:
        Application settings containing database URL and GitHub token.
    """

    def __init__(self, app_settings: AppSettings | None = None) -> None:
        if app_settings is None:
            from ai_washer.config import load_app_settings

            app_settings = load_app_settings()

        self._log = logger.bind(collector="github_collector")

        self._github_client = GitHubClient(
            token=app_settings.github_token,
        )

        engine = create_engine_from_settings(app_settings)
        self._session_factory = get_session_factory(engine)
        self._max_repos_per_org = 100

    # -- Public API -----------------------------------------------------------

    def collect_for_company(
        self,
        company_id: uuid.UUID,
        github_org: str | None,
        collection_date: date | None = None,
    ) -> GitHubCollectionResult:
        """Collect GitHub repository data for a single company.

        If github_org is None or empty, logs a skip and returns an empty
        result. Otherwise, builds an org snapshot via the GitHub API and
        persists new GitHubRepo rows (idempotent -- skips repos already
        collected for the same observed_date).

        Parameters
        ----------
        company_id:
            UUID of the Company row in the database.
        github_org:
            GitHub organization login name (from Company.aliases).
        collection_date:
            Date to record as observed_date. Defaults to today (UTC).

        Returns
        -------
        GitHubCollectionResult
            Counts of repos collected, skipped, and errors.
        """
        if collection_date is None:
            collection_date = date.today()

        log = self._log.bind(
            company_id=str(company_id),
            github_org=github_org or "(none)",
        )

        if not github_org:
            log.info("github_collection_skipped", reason="no_github_org")
            return GitHubCollectionResult(
                company_cik="",
                repo_count=0,
                skipped_count=0,
                errors=[],
            )

        log.info("github_collection_started")

        try:
            snapshot = self._github_client.build_org_snapshot(
                github_org, max_repos=self._max_repos_per_org
            )
        except GitHubClientError as exc:
            err_msg = f"GitHub API error for '{github_org}': {exc}"
            log.warning("github_collection_failed", error=str(exc))
            return GitHubCollectionResult(
                company_cik="",
                repo_count=0,
                skipped_count=0,
                errors=[err_msg],
            )

        repo_count = 0
        skipped_count = 0

        with self._session_factory() as session:
            for repo_record in snapshot.repos:
                if self._repo_exists(
                    session, company_id, repo_record.repo_full_name, collection_date
                ):
                    skipped_count += 1
                    continue

                row = self._create_github_repo_row(
                    company_id=company_id,
                    repo_record=repo_record,
                    collection_date=collection_date,
                )
                session.add(row)
                repo_count += 1

            session.commit()

        log.info(
            "github_collection_complete",
            repo_count=repo_count,
            skipped_count=skipped_count,
        )

        return GitHubCollectionResult(
            company_cik="",
            repo_count=repo_count,
            skipped_count=skipped_count,
            errors=[],
        )

    def collect_all(
        self,
        collection_date: date | None = None,
    ) -> list[GitHubCollectionResult]:
        """Collect GitHub data for all active companies.

        Queries the database for active companies with a CIK, then
        calls collect_for_company for each that has a github_org alias.
        Sleeps between companies to respect API rate limits.

        Parameters
        ----------
        collection_date:
            Date to record as observed_date. Defaults to today (UTC).

        Returns
        -------
        list[GitHubCollectionResult]
            One result per company processed.
        """
        if collection_date is None:
            collection_date = date.today()

        with self._session_factory() as session:
            companies = (
                session.execute(
                    select(Company).where(
                        Company.is_active == True,  # noqa: E712
                        Company.cik.isnot(None),
                    )
                )
                .scalars()
                .all()
            )

        self._log.info("github_collect_all_started", company_count=len(companies))

        results: list[GitHubCollectionResult] = []
        for idx, company in enumerate(companies):
            github_org = (company.aliases or {}).get("github_org")

            result = self.collect_for_company(
                company_id=company.id,
                github_org=github_org,
                collection_date=collection_date,
            )

            # Set the CIK on the result (immutable pattern)
            result = GitHubCollectionResult(
                company_cik=company.cik or "",
                repo_count=result.repo_count,
                skipped_count=result.skipped_count,
                errors=result.errors,
            )
            results.append(result)

            # Rate limit between companies
            if idx < len(companies) - 1:
                time.sleep(_INTER_COMPANY_DELAY)

            # Progress logging
            if (idx + 1) % _PROGRESS_LOG_INTERVAL == 0:
                self._log.info(
                    "github_collect_all_progress",
                    completed=idx + 1,
                    total=len(companies),
                )

        self._log.info(
            "github_collect_all_complete",
            companies_processed=len(results),
            total_repos=sum(r.repo_count for r in results),
        )

        return results

    # -- Private helpers ------------------------------------------------------

    def _repo_exists(
        self,
        session,
        company_id: uuid.UUID,
        repo_full_name: str,
        observed_date: date,
    ) -> bool:
        """Check if a repo with the same unique key already exists.

        Mirrors the unique constraint on (company_id, repo_full_name,
        observed_date) for idempotent daily collection.
        """
        stmt = select(GitHubRepo).where(
            GitHubRepo.company_id == company_id,
            GitHubRepo.repo_full_name == repo_full_name,
            GitHubRepo.observed_date == observed_date,
        )
        return session.execute(stmt).scalar_one_or_none() is not None

    def _create_github_repo_row(
        self,
        company_id: uuid.UUID,
        repo_record: GitHubRepoRecord,
        collection_date: date,
    ) -> GitHubRepo:
        """Build a GitHubRepo ORM object from a GitHubRepoRecord.

        Parameters
        ----------
        company_id:
            UUID of the company.
        repo_record:
            Validated repo data from the GitHub API.
        collection_date:
            Date to use as both as_of_date and observed_date.
        """
        return GitHubRepo(
            company_id=company_id,
            repo_full_name=repo_record.repo_full_name,
            repo_name=repo_record.repo_name,
            primary_language=repo_record.primary_language,
            language_bytes=repo_record.language_bytes,
            pushed_at=repo_record.pushed_at,
            is_fork=repo_record.is_fork,
            is_archived=repo_record.is_archived,
            stargazers_count=repo_record.stargazers_count,
            ml_frameworks=repo_record.ml_frameworks,
            collection_metadata={
                "signal_version": GITHUB_SIGNAL_VERSION,
                "collected_at": datetime.now(tz=timezone.utc).isoformat(),
            },
            as_of_date=collection_date,
            observed_date=collection_date,
        )
