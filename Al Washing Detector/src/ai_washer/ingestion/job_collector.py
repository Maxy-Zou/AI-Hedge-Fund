"""Job posting collection orchestrator with lifecycle tracking.

Coordinates JobClient (scraping) and database persistence into an
idempotent pipeline with lifecycle tracking. For each company, scrapes
job postings, classifies roles, deduplicates by hash, and persists to
the job_postings table. Tracks first_seen, last_seen, and is_active
for ghost job detection.

Usage::

    from ai_washer.ingestion.job_collector import JobCollector
    collector = JobCollector(app_settings=settings)
    result = collector.collect_for_company(company_id, "Acme Corp", "0001234567")
"""

from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timezone

import structlog
from sqlalchemy import select

from ai_washer.config import AppSettings
from ai_washer.db.models import Company, JobPosting
from ai_washer.db.session import create_engine_from_settings, get_session_factory
from ai_washer.ingestion.job_client import JobClient, JobClientError
from ai_washer.ingestion.job_types import (
    JOB_SIGNAL_VERSION,
    JobCollectionResult,
)

logger = structlog.get_logger(__name__)

# Delay between companies in collect_all to respect scraping rate limits.
_INTER_COMPANY_DELAY = 1.0

# Log progress every N companies in collect_all.
_PROGRESS_LOG_INTERVAL = 10


class JobCollector:
    """Orchestrates job posting collection with lifecycle tracking.

    For each company, scrapes job postings via JobClient, deduplicates
    by hash, inserts new postings, updates last_seen on existing ones,
    and marks stale postings as inactive.

    Parameters
    ----------
    app_settings:
        Application settings containing database URL.
    job_client:
        Optional JobClient for dependency injection in tests.
    session_factory:
        Optional session factory for dependency injection in tests.
    """

    def __init__(
        self,
        app_settings: AppSettings | None = None,
        job_client: JobClient | None = None,
        session_factory=None,
    ) -> None:
        if app_settings is None:
            from ai_washer.config import load_app_settings

            app_settings = load_app_settings()

        self._log = logger.bind(collector="job_collector")
        self._client = job_client or JobClient()

        if session_factory is not None:
            self._session_factory = session_factory
        else:
            engine = create_engine_from_settings(app_settings)
            self._session_factory = get_session_factory(engine)

    # -- Public API -----------------------------------------------------------

    def collect_for_company(
        self,
        company_id: uuid.UUID,
        company_name: str,
        cik: str,
        collection_date: date | None = None,
    ) -> JobCollectionResult:
        """Collect job postings for a single company with lifecycle tracking.

        1. Scrape job postings via JobClient
        2. For each posting: insert if new (by dedup_hash), update last_seen if exists
        3. Mark stale postings (not seen today) as is_active=False
        4. Return counts

        Parameters
        ----------
        company_id:
            UUID of the Company row in the database.
        company_name:
            Company name for job search query.
        cik:
            Company CIK for result tracking.
        collection_date:
            Date to record as first_seen/last_seen. Defaults to today.

        Returns
        -------
        JobCollectionResult
            Counts of jobs found, new, updated, and errors.
        """
        if collection_date is None:
            collection_date = date.today()

        log = self._log.bind(
            company_id=str(company_id),
            company_name=company_name,
        )

        log.info("job_collection_started")

        try:
            records = self._client.search_company_jobs(company_name)
        except (JobClientError, Exception) as exc:
            err_msg = f"Job scraping failed for '{company_name}': {exc}"
            log.warning("job_collection_failed", error=str(exc))
            return JobCollectionResult(
                company_cik=cik,
                jobs_found=0,
                jobs_new=0,
                jobs_updated=0,
                errors=[err_msg],
            )

        jobs_new = 0
        jobs_updated = 0
        seen_hashes: set[str] = set()

        with self._session_factory() as session:
            for record in records:
                seen_hashes.add(record.dedup_hash)

                existing = self._find_by_hash(session, record.dedup_hash)

                if existing is None:
                    # New posting: insert
                    posting = JobPosting(
                        company_id=company_id,
                        title=record.title,
                        company_name_raw=record.company_name_raw,
                        location=record.location,
                        description=record.description,
                        job_url=record.job_url,
                        source_site=record.source_site,
                        role_classification=record.role_classification,
                        dedup_hash=record.dedup_hash,
                        first_seen=collection_date,
                        last_seen=collection_date,
                        is_active=True,
                        collection_metadata={
                            "signal_version": JOB_SIGNAL_VERSION,
                            "collected_at": datetime.now(
                                tz=timezone.utc
                            ).isoformat(),
                        },
                    )
                    session.add(posting)
                    jobs_new += 1
                else:
                    # Existing posting: update last_seen
                    existing.last_seen = collection_date
                    existing.is_active = True
                    jobs_updated += 1

            # Mark stale postings as inactive
            stale_postings = self._find_stale_postings(
                session, company_id, collection_date
            )
            for stale in stale_postings:
                stale.is_active = False

            session.commit()

        log.info(
            "job_collection_complete",
            jobs_found=len(records),
            jobs_new=jobs_new,
            jobs_updated=jobs_updated,
            stale_deactivated=len(stale_postings) if records else 0,
        )

        return JobCollectionResult(
            company_cik=cik,
            jobs_found=len(records),
            jobs_new=jobs_new,
            jobs_updated=jobs_updated,
            errors=[],
        )

    def collect_all(
        self,
        collection_date: date | None = None,
    ) -> list[JobCollectionResult]:
        """Collect job postings for all active companies.

        Queries the database for active companies with a CIK, then
        calls collect_for_company for each. Sleeps between companies
        to respect scraping rate limits.

        Parameters
        ----------
        collection_date:
            Date to record as first_seen/last_seen. Defaults to today.

        Returns
        -------
        list[JobCollectionResult]
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

        self._log.info("job_collect_all_started", company_count=len(companies))

        results: list[JobCollectionResult] = []
        for idx, company in enumerate(companies):
            result = self.collect_for_company(
                company_id=company.id,
                company_name=company.name,
                cik=company.cik or "",
                collection_date=collection_date,
            )
            results.append(result)

            # Rate limit between companies
            if idx < len(companies) - 1:
                time.sleep(_INTER_COMPANY_DELAY)

            # Progress logging
            if (idx + 1) % _PROGRESS_LOG_INTERVAL == 0:
                self._log.info(
                    "job_collect_all_progress",
                    completed=idx + 1,
                    total=len(companies),
                )

        self._log.info(
            "job_collect_all_complete",
            companies_processed=len(results),
            total_jobs_new=sum(r.jobs_new for r in results),
            total_jobs_updated=sum(r.jobs_updated for r in results),
        )

        return results

    # -- Private helpers ------------------------------------------------------

    def _find_by_hash(self, session, dedup_hash: str) -> JobPosting | None:
        """Find an existing job posting by dedup_hash.

        Parameters
        ----------
        session:
            Active SQLAlchemy session.
        dedup_hash:
            SHA-256 dedup hash to search for.

        Returns
        -------
        JobPosting | None
            Existing posting or None if not found.
        """
        stmt = select(JobPosting).where(JobPosting.dedup_hash == dedup_hash)
        return session.execute(stmt).scalar_one_or_none()

    def _find_stale_postings(
        self, session, company_id: uuid.UUID, collection_date: date
    ) -> list[JobPosting]:
        """Find active postings for a company that weren't seen today.

        These postings had is_active=True but their last_seen is before
        the current collection_date, meaning they weren't found in the
        latest scrape.

        Parameters
        ----------
        session:
            Active SQLAlchemy session.
        company_id:
            UUID of the company.
        collection_date:
            Current collection date.

        Returns
        -------
        list[JobPosting]
            Stale postings to deactivate.
        """
        stmt = select(JobPosting).where(
            JobPosting.company_id == company_id,
            JobPosting.is_active == True,  # noqa: E712
            JobPosting.last_seen < collection_date,
        )
        return list(session.execute(stmt).scalars().all())
