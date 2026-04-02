"""Patent collection orchestrator.

Coordinates PatentSearchClient (API queries) and database persistence
into an idempotent pipeline. Searches all patent_assignee aliases for
each company, deduplicates across name variations, and persists new
patent records incrementally.

Usage::

    from ai_washer.ingestion.patent_collector import PatentCollector
    collector = PatentCollector(app_settings=settings)
    result = collector.collect_for_company(company_id, "Acme Corp", aliases)
"""

from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_washer.config import AppSettings
from ai_washer.db.models import Company, Patent
from ai_washer.db.session import create_engine_from_settings, get_session_factory
from ai_washer.ingestion.patent_client import PatentClientError, PatentSearchClient
from ai_washer.ingestion.patent_types import (
    PATENT_SIGNAL_VERSION,
    PatentCollectionResult,
    PatentRecord,
)

logger = structlog.get_logger(__name__)

# Delay between companies in collect_all to respect API rate limits.
_INTER_COMPANY_DELAY = 1.0

# Log progress every N companies in collect_all.
_PROGRESS_LOG_INTERVAL = 10


class PatentCollector:
    """Orchestrates patent collection from the PatentSearch API.

    Searches all assignee name aliases per company, deduplicates results
    across name variations, and persists new patents incrementally.
    Follows the FilingCollector pattern from Phase 3.

    Parameters
    ----------
    app_settings:
        Application settings containing database URL and PatentsView API key.
    """

    def __init__(self, app_settings: AppSettings | None = None) -> None:
        if app_settings is None:
            from ai_washer.config import load_app_settings

            app_settings = load_app_settings()

        self._log = logger.bind(collector="patent_collector")

        self._patent_client = PatentSearchClient(
            api_key=app_settings.patentsview_api_key,
            base_url=app_settings.patentsview_base_url,
        )

        engine = create_engine_from_settings(app_settings)
        self._session_factory = get_session_factory(engine)

    # -- Public API -----------------------------------------------------------

    def collect_for_company(
        self,
        company_id: uuid.UUID,
        company_name: str,
        aliases: dict,
        collection_date: date | None = None,
    ) -> PatentCollectionResult:
        """Collect patents for a single company.

        Searches all patent_assignee aliases (or falls back to company_name),
        deduplicates by patent_id across searches, and persists new patents.

        Parameters
        ----------
        company_id:
            UUID of the Company row in the database.
        company_name:
            Company display name (fallback if no aliases).
        aliases:
            Company.aliases dict containing optional patent_assignee list.
        collection_date:
            Date to record as observed_date. Defaults to today (UTC).

        Returns
        -------
        PatentCollectionResult
            Counts of patents collected, skipped, and errors.
        """
        if collection_date is None:
            collection_date = date.today()

        log = self._log.bind(
            company_name=company_name,
            company_id=str(company_id),
        )
        log.info("patent_collection_started")

        assignee_names = self._get_assignee_names(company_name, aliases)
        errors: list[str] = []
        api_query_count = 0

        with self._session_factory() as session:
            # Get last patent date for incremental collection
            last_patent_date = self._get_last_patent_date(session, company_id)

            if last_patent_date is not None:
                log.info(
                    "patent_incremental_collection",
                    after_date=str(last_patent_date),
                )

            # Search all assignee names and collect unique patents
            all_patents: dict[str, PatentRecord] = {}

            for name in assignee_names:
                try:
                    patents = self._patent_client.search_by_assignee(
                        name, after_date=last_patent_date
                    )
                    api_query_count += 1

                    for patent in patents:
                        if patent.patent_id not in all_patents:
                            all_patents[patent.patent_id] = patent

                except PatentClientError as exc:
                    err_msg = f"Search for '{name}': {exc}"
                    errors.append(err_msg)
                    log.warning(
                        "patent_search_failed",
                        assignee_name=name,
                        error=str(exc),
                    )

            # Persist new patents
            patent_count = 0
            skipped_count = 0

            for patent_record in all_patents.values():
                if self._patent_exists(session, company_id, patent_record.patent_id):
                    skipped_count += 1
                    continue

                patent_row = self._create_patent_row(
                    company_id=company_id,
                    patent_record=patent_record,
                    collection_date=collection_date,
                    assignee_names_searched=assignee_names,
                    api_query_count=api_query_count,
                )
                session.add(patent_row)
                patent_count += 1

            session.commit()

        log.info(
            "patent_collection_complete",
            patent_count=patent_count,
            skipped_count=skipped_count,
            error_count=len(errors),
            assignee_names_searched=assignee_names,
        )

        return PatentCollectionResult(
            company_cik="",
            patent_count=patent_count,
            skipped_count=skipped_count,
            errors=errors,
        )

    def collect_all(
        self,
        collection_date: date | None = None,
    ) -> list[PatentCollectionResult]:
        """Collect patents for all active companies.

        Queries the database for active companies with a CIK, then
        calls collect_for_company for each. Sleeps between companies
        to respect API rate limits.

        Parameters
        ----------
        collection_date:
            Date to record as observed_date. Defaults to today (UTC).

        Returns
        -------
        list[PatentCollectionResult]
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

        self._log.info("patent_collect_all_started", company_count=len(companies))

        results: list[PatentCollectionResult] = []
        for idx, company in enumerate(companies):
            result = self.collect_for_company(
                company_id=company.id,
                company_name=company.name,
                aliases=company.aliases or {},
                collection_date=collection_date,
            )
            # Set the CIK on the result
            result = PatentCollectionResult(
                company_cik=company.cik or "",
                patent_count=result.patent_count,
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
                    "patent_collect_all_progress",
                    completed=idx + 1,
                    total=len(companies),
                )

        self._log.info(
            "patent_collect_all_complete",
            companies_processed=len(results),
            total_patents=sum(r.patent_count for r in results),
        )

        return results

    # -- Private helpers ------------------------------------------------------

    def _get_assignee_names(self, company_name: str, aliases: dict) -> list[str]:
        """Extract patent_assignee names from aliases, falling back to company name.

        Parameters
        ----------
        company_name:
            Company display name (fallback).
        aliases:
            Company.aliases dict with optional patent_assignee key.

        Returns
        -------
        list[str]
            Deduplicated list of assignee names to search.
        """
        patent_assignees = aliases.get("patent_assignee", [])

        if not patent_assignees:
            return [company_name]

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for name in patent_assignees:
            if name not in seen:
                seen.add(name)
                unique.append(name)

        return unique

    def _get_last_patent_date(
        self, session: Session, company_id: uuid.UUID
    ) -> date | None:
        """Query MAX(patent_date) for a company.

        Returns None if no patents exist (first collection).
        """
        stmt = select(func.max(Patent.patent_date)).where(
            Patent.company_id == company_id
        )
        return session.execute(stmt).scalar_one_or_none()

    def _patent_exists(
        self,
        session: Session,
        company_id: uuid.UUID,
        patent_id: str,
    ) -> bool:
        """Check if a patent with the same unique key already exists."""
        stmt = select(Patent).where(
            Patent.company_id == company_id,
            Patent.patent_id == patent_id,
        )
        return session.execute(stmt).scalar_one_or_none() is not None

    def _create_patent_row(
        self,
        company_id: uuid.UUID,
        patent_record: PatentRecord,
        collection_date: date,
        assignee_names_searched: list[str],
        api_query_count: int,
    ) -> Patent:
        """Build a Patent ORM object from a PatentRecord.

        Parameters
        ----------
        company_id:
            UUID of the company.
        patent_record:
            Validated patent data from the API.
        collection_date:
            Date to use as observed_date.
        assignee_names_searched:
            List of assignee names that were searched.
        api_query_count:
            Number of API queries made for this collection run.
        """
        return Patent(
            company_id=company_id,
            patent_id=patent_record.patent_id,
            patent_title=patent_record.patent_title,
            patent_date=patent_record.patent_date,
            assignee_organization=patent_record.assignee_organization,
            cpc_codes=patent_record.cpc_codes,
            collection_metadata={
                "signal_version": PATENT_SIGNAL_VERSION,
                "assignee_names_searched": assignee_names_searched,
                "api_query_count": api_query_count,
                "collected_at": datetime.now(tz=timezone.utc).isoformat(),
            },
            as_of_date=patent_record.patent_date,
            observed_date=collection_date,
        )
