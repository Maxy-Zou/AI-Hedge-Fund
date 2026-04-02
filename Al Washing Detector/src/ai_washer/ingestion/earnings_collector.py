"""Earnings call transcript collection orchestrator.

Coordinates EarningsClient (earningscall API) and database persistence
into an idempotent pipeline. For each company, fetches transcripts for
the last N quarters and persists EarningsTranscript rows.

Usage::

    from ai_washer.ingestion.earnings_collector import EarningsCollector
    collector = EarningsCollector(app_settings=settings)
    result = collector.collect_for_company(company_id, "AAPL")
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime

import structlog
from sqlalchemy import select

from ai_washer.config import AppSettings
from ai_washer.db.models import Company, EarningsTranscript
from ai_washer.db.session import create_engine_from_settings, get_session_factory
from ai_washer.ingestion.earnings_client import EarningsClient, EarningsClientError
from ai_washer.ingestion.earnings_types import (
    EARNINGS_SIGNAL_VERSION,
    EarningsCollectionResult,
)

logger = structlog.get_logger(__name__)

# Delay between companies in collect_all to respect API rate limits.
_INTER_COMPANY_DELAY = 1.0

# Log progress every N companies in collect_all.
_PROGRESS_LOG_INTERVAL = 10


def _compute_quarter_list(num_quarters: int, ref_date: date) -> list[tuple[int, int]]:
    """Compute the last N (year, quarter) pairs counting back from ref_date.

    Parameters
    ----------
    num_quarters:
        Number of quarters to look back.
    ref_date:
        Reference date (typically today).

    Returns
    -------
    list[tuple[int, int]]
        List of (year, quarter) tuples, most recent first.
    """
    current_quarter = (ref_date.month - 1) // 3 + 1
    current_year = ref_date.year

    quarters: list[tuple[int, int]] = []
    y, q = current_year, current_quarter
    for _ in range(num_quarters):
        quarters.append((y, q))
        q -= 1
        if q < 1:
            q = 4
            y -= 1

    return quarters


class EarningsCollector:
    """Orchestrates earnings transcript collection from the earningscall API.

    For each company, fetches transcripts for the last N quarters and
    persists EarningsTranscript rows with idempotent upsert (skip
    duplicates via unique constraint check).

    Parameters
    ----------
    app_settings:
        Application settings containing database URL and API key.
    """

    def __init__(self, app_settings: AppSettings | None = None) -> None:
        if app_settings is None:
            from ai_washer.config import load_app_settings

            app_settings = load_app_settings()

        self._log = logger.bind(collector="earnings_collector")
        self._client = EarningsClient(api_key=app_settings.earningscall_api_key)
        self._default_quarters = 8

        engine = create_engine_from_settings(app_settings)
        self._session_factory = get_session_factory(engine)

    # -- Public API -----------------------------------------------------------

    def collect_for_company(
        self,
        company_id: uuid.UUID,
        ticker: str,
        num_quarters: int | None = None,
        collection_date: date | None = None,
    ) -> EarningsCollectionResult:
        """Collect earnings transcripts for a single company.

        Fetches transcripts for the last ``num_quarters`` quarters and
        persists them as EarningsTranscript rows. Skips quarters that
        already exist in the database (idempotent).

        Parameters
        ----------
        company_id:
            UUID of the Company row in the database.
        ticker:
            Stock ticker symbol.
        num_quarters:
            Number of quarters to fetch. Defaults to 8 (2 years).
        collection_date:
            Date to record as observed_date. Defaults to today (UTC).

        Returns
        -------
        EarningsCollectionResult
            Counts of transcripts collected, skipped, and errors.
        """
        if collection_date is None:
            collection_date = date.today()
        if num_quarters is None:
            num_quarters = self._default_quarters

        log = self._log.bind(company_id=str(company_id), ticker=ticker)
        log.info("earnings_collection_started", num_quarters=num_quarters)

        quarters = _compute_quarter_list(num_quarters, collection_date)
        transcript_count = 0
        skipped_count = 0
        errors: list[str] = []

        with self._session_factory() as session:
            for year, quarter in quarters:
                # Idempotent: skip if already collected
                if self._transcript_exists(session, company_id, year, quarter):
                    skipped_count += 1
                    continue

                try:
                    record = self._client.get_transcript(ticker, year, quarter)
                except EarningsClientError as exc:
                    err_msg = f"Earnings API error for {ticker} Q{quarter} {year}: {exc}"
                    log.warning("earnings_fetch_failed", error=str(exc))
                    errors.append(err_msg)
                    continue

                if record is None:
                    log.info(
                        "transcript_not_available",
                        ticker=ticker,
                        year=year,
                        quarter=quarter,
                    )
                    continue

                # Build transcript_text JSONB: ONLY string values
                transcript_text: dict[str, str | None] = {
                    "full_text": record.text,
                    "prepared_remarks": None,
                    "qa": None,
                }

                # Build collection_metadata: speakers dict goes here
                now_iso = datetime.now(tz=UTC).isoformat()
                collection_metadata: dict = {
                    "signal_version": EARNINGS_SIGNAL_VERSION,
                    "collected_at": now_iso,
                    "speakers": record.speakers if record.speakers else {},
                }

                # Determine as_of_date from transcript
                as_of_date = record.transcript_date
                if as_of_date is None:
                    # Approximate: last day of the quarter
                    quarter_end_month = quarter * 3
                    as_of_date = date(year, quarter_end_month, 1)

                row = EarningsTranscript(
                    company_id=company_id,
                    fiscal_year=year,
                    fiscal_quarter=quarter,
                    transcript_date=record.transcript_date,
                    transcript_text=transcript_text,
                    source=record.source,
                    collection_metadata=collection_metadata,
                    as_of_date=as_of_date,
                    observed_date=collection_date,
                )
                session.add(row)
                transcript_count += 1

            session.commit()

        log.info(
            "earnings_collection_complete",
            transcript_count=transcript_count,
            skipped_count=skipped_count,
            error_count=len(errors),
        )

        return EarningsCollectionResult(
            company_cik="",
            transcript_count=transcript_count,
            skipped_count=skipped_count,
            errors=errors,
        )

    def collect_all(
        self,
        collection_date: date | None = None,
    ) -> list[EarningsCollectionResult]:
        """Collect earnings transcripts for all active companies.

        Queries the database for active companies with a CIK, then
        calls collect_for_company for each. Sleeps between companies
        to respect API rate limits.

        Parameters
        ----------
        collection_date:
            Date to record as observed_date. Defaults to today (UTC).

        Returns
        -------
        list[EarningsCollectionResult]
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

        self._log.info("earnings_collect_all_started", company_count=len(companies))

        results: list[EarningsCollectionResult] = []
        for idx, company in enumerate(companies):
            result = self.collect_for_company(
                company_id=company.id,
                ticker=company.ticker,
                collection_date=collection_date,
            )

            # Set the CIK on the result (immutable pattern)
            result = EarningsCollectionResult(
                company_cik=company.cik or "",
                transcript_count=result.transcript_count,
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
                    "earnings_collect_all_progress",
                    completed=idx + 1,
                    total=len(companies),
                )

        self._log.info(
            "earnings_collect_all_complete",
            companies_processed=len(results),
            total_transcripts=sum(r.transcript_count for r in results),
        )

        return results

    # -- Private helpers ------------------------------------------------------

    def _transcript_exists(
        self,
        session,
        company_id: uuid.UUID,
        year: int,
        quarter: int,
    ) -> bool:
        """Check if a transcript for the given company/year/quarter exists.

        Mirrors the unique constraint on (company_id, fiscal_year, fiscal_quarter)
        for idempotent collection.
        """
        stmt = select(EarningsTranscript).where(
            EarningsTranscript.company_id == company_id,
            EarningsTranscript.fiscal_year == year,
            EarningsTranscript.fiscal_quarter == quarter,
        )
        return session.execute(stmt).scalar_one_or_none() is not None
