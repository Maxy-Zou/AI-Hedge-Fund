"""Filing collection orchestrator.

Coordinates FilingClient (filing text retrieval), XBRLExtractor
(financial data extraction), and database persistence into a single
idempotent pipeline. Runs per-company or across the full active universe.

Usage::

    from ai_washer.ingestion.filing_collector import FilingCollector
    collector = FilingCollector(app_settings=settings)
    result = collector.collect_for_company(company_id, cik, ticker)
"""

from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_washer.config import AppSettings, FilingCollectionSettings
from ai_washer.db.models import Company, Filing, XBRLFact
from ai_washer.db.session import create_engine_from_settings, get_session_factory
from ai_washer.ingestion.filing_client import FilingClient
from ai_washer.ingestion.types import CollectionResult, FilingData, XBRLFactRecord
from ai_washer.ingestion.xbrl_extractor import XBRLExtractor

logger = structlog.get_logger(__name__)

# Version string embedded in collection_metadata for traceability.
_COLLECTOR_VERSION = "0.3.0"

# Delay between companies in collect_all to respect SEC rate limits.
_INTER_COMPANY_DELAY = 1.0

# Log progress every N companies in collect_all.
_PROGRESS_LOG_INTERVAL = 10


class FilingCollector:
    """Orchestrates SEC filing retrieval and XBRL extraction for target companies.

    Coordinates FilingClient (filing text) and XBRLExtractor (financial data),
    persisting results to the database with idempotent daily checks.

    Parameters
    ----------
    app_settings:
        Application settings containing database URL and EDGAR identity.
    filing_settings:
        Optional filing collection settings (form types, limits).
    """

    def __init__(
        self,
        app_settings: AppSettings,
        filing_settings: FilingCollectionSettings | None = None,
    ) -> None:
        self._app_settings = app_settings
        self._filing_settings = filing_settings or FilingCollectionSettings()
        self._log = logger.bind(collector="filing_collector")

        engine = create_engine_from_settings(app_settings)
        self._session_factory = get_session_factory(engine)

    # -- Public API -----------------------------------------------------------

    def collect_for_company(
        self,
        company_id: uuid.UUID,
        cik: str,
        ticker: str,
        collection_date: date | None = None,
    ) -> CollectionResult:
        """Collect filings and XBRL facts for a single company.

        Retrieves filings for each configured form type, extracts XBRL
        financial data, and persists both to the database. Skips any
        records that already exist (idempotent).

        Parameters
        ----------
        company_id:
            UUID of the Company row in the database.
        cik:
            SEC CIK number for the company.
        ticker:
            Company ticker symbol (for logging).
        collection_date:
            Date to record as observed_date. Defaults to today (UTC).

        Returns
        -------
        CollectionResult
            Counts of filings collected, XBRL facts extracted, skipped,
            and any errors encountered.
        """
        if collection_date is None:
            collection_date = date.today()

        log = self._log.bind(ticker=ticker, cik=cik, collection_date=str(collection_date))
        log.info("collection_started")

        filing_count = 0
        xbrl_fact_count = 0
        skipped_count = 0
        errors: list[str] = []

        with self._session_factory() as session:
            # -- Filing collection (per form type) ----------------------------
            with FilingClient(
                edgar_identity=self._app_settings.edgar_identity,
                settings=self._filing_settings,
            ) as filing_client:
                for form_type in self._filing_settings.form_types:
                    try:
                        new_filings, new_skipped = self._collect_filings_for_form(
                            session=session,
                            filing_client=filing_client,
                            company_id=company_id,
                            cik=cik,
                            form_type=form_type,
                            collection_date=collection_date,
                        )
                        filing_count += new_filings
                        skipped_count += new_skipped
                    except Exception as exc:
                        err_msg = f"{form_type}: {exc}"
                        errors.append(err_msg)
                        log.warning(
                            "filing_form_type_error",
                            form_type=form_type,
                            error=str(exc),
                        )

            # -- XBRL extraction -----------------------------------------------
            try:
                with XBRLExtractor(
                    edgar_identity=self._app_settings.edgar_identity,
                ) as xbrl_extractor:
                    new_xbrl, xbrl_skipped = self._collect_xbrl_facts(
                        session=session,
                        xbrl_extractor=xbrl_extractor,
                        company_id=company_id,
                        cik=cik,
                        collection_date=collection_date,
                    )
                    xbrl_fact_count += new_xbrl
                    skipped_count += xbrl_skipped
            except Exception as exc:
                err_msg = f"XBRL: {exc}"
                errors.append(err_msg)
                log.warning("xbrl_extraction_error", error=str(exc))

            session.commit()

        log.info(
            "collection_complete",
            filing_count=filing_count,
            xbrl_fact_count=xbrl_fact_count,
            skipped_count=skipped_count,
            error_count=len(errors),
        )

        return CollectionResult(
            company_cik=cik,
            filing_count=filing_count,
            xbrl_fact_count=xbrl_fact_count,
            skipped_count=skipped_count,
            errors=errors,
        )

    def collect_all(
        self,
        collection_date: date | None = None,
    ) -> list[CollectionResult]:
        """Collect filings and XBRL facts for all active companies.

        Queries the database for active companies with a CIK, then
        calls collect_for_company for each. Sleeps between companies
        to respect SEC rate limits.

        Parameters
        ----------
        collection_date:
            Date to record as observed_date. Defaults to today (UTC).

        Returns
        -------
        list[CollectionResult]
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

        self._log.info("collect_all_started", company_count=len(companies))

        results: list[CollectionResult] = []
        for idx, company in enumerate(companies):
            result = self.collect_for_company(
                company_id=company.id,
                cik=company.cik,
                ticker=company.ticker,
                collection_date=collection_date,
            )
            results.append(result)

            # Rate limit between companies
            if idx < len(companies) - 1:
                time.sleep(_INTER_COMPANY_DELAY)

            # Progress logging
            if (idx + 1) % _PROGRESS_LOG_INTERVAL == 0:
                self._log.info(
                    "collect_all_progress",
                    completed=idx + 1,
                    total=len(companies),
                )

        self._log.info(
            "collect_all_complete",
            companies_processed=len(results),
            total_filings=sum(r.filing_count for r in results),
            total_xbrl=sum(r.xbrl_fact_count for r in results),
        )

        return results

    # -- Private helpers ------------------------------------------------------

    def _collect_filings_for_form(
        self,
        session: Session,
        filing_client: FilingClient,
        company_id: uuid.UUID,
        cik: str,
        form_type: str,
        collection_date: date,
    ) -> tuple[int, int]:
        """Fetch and persist filings for a single form type.

        Returns
        -------
        tuple[int, int]
            (inserted_count, skipped_count)
        """
        filings = filing_client.get_latest_filings(form_type=form_type, cik=cik)
        inserted = 0
        skipped = 0

        for filing_data in filings:
            if self._filing_exists(session, company_id, form_type, filing_data.accession_no):
                skipped += 1
                self._log.debug(
                    "filing_skipped_existing",
                    accession_no=filing_data.accession_no,
                    form_type=form_type,
                )
                continue

            filing_row = self._create_filing_row(
                company_id=company_id,
                filing_data=filing_data,
                collection_date=collection_date,
            )
            session.add(filing_row)
            inserted += 1

        return inserted, skipped

    def _collect_xbrl_facts(
        self,
        session: Session,
        xbrl_extractor: XBRLExtractor,
        company_id: uuid.UUID,
        cik: str,
        collection_date: date,
    ) -> tuple[int, int]:
        """Fetch and persist XBRL facts for a company.

        Returns
        -------
        tuple[int, int]
            (inserted_count, skipped_count)
        """
        facts = xbrl_extractor.extract_company_xbrl(cik)
        inserted = 0
        skipped = 0

        for fact in facts:
            if self._xbrl_fact_exists(session, company_id, fact):
                skipped += 1
                self._log.debug(
                    "xbrl_fact_skipped_existing",
                    concept=fact.concept,
                    end_date=str(fact.end_date),
                )
                continue

            xbrl_row = self._create_xbrl_row(
                company_id=company_id,
                fact=fact,
                collection_date=collection_date,
            )
            session.add(xbrl_row)
            inserted += 1

        return inserted, skipped

    def _filing_exists(
        self,
        session: Session,
        company_id: uuid.UUID,
        form_type: str,
        accession_no: str,
    ) -> bool:
        """Check if a filing with the same unique key already exists."""
        stmt = select(Filing).where(
            Filing.company_id == company_id,
            Filing.form_type == form_type,
            Filing.accession_no == accession_no,
        )
        return session.execute(stmt).scalar_one_or_none() is not None

    def _xbrl_fact_exists(
        self,
        session: Session,
        company_id: uuid.UUID,
        fact: XBRLFactRecord,
    ) -> bool:
        """Check if an XBRL fact with the same unique key already exists."""
        stmt = select(XBRLFact).where(
            XBRLFact.company_id == company_id,
            XBRLFact.concept == fact.concept,
            XBRLFact.end_date == fact.end_date,
            XBRLFact.fiscal_period == fact.fiscal_period,
        )
        return session.execute(stmt).scalar_one_or_none() is not None

    def _create_filing_row(
        self,
        company_id: uuid.UUID,
        filing_data: FilingData,
        collection_date: date,
    ) -> Filing:
        """Build a Filing ORM object from a FilingData record."""
        return Filing(
            company_id=company_id,
            form_type=filing_data.form_type,
            accession_no=filing_data.accession_no,
            filing_date=filing_data.filing_date,
            period_of_report=filing_data.period_of_report,
            sections=filing_data.sections.model_dump(),
            content_hash=filing_data.content_hash,
            collection_metadata={
                "collector_version": _COLLECTOR_VERSION,
                "collected_at": datetime.now(tz=timezone.utc).isoformat(),
            },
            as_of_date=filing_data.period_of_report or filing_data.filing_date,
            observed_date=collection_date,
        )

    def _create_xbrl_row(
        self,
        company_id: uuid.UUID,
        fact: XBRLFactRecord,
        collection_date: date,
    ) -> XBRLFact:
        """Build an XBRLFact ORM object from an XBRLFactRecord."""
        return XBRLFact(
            company_id=company_id,
            concept=fact.concept,
            tag=fact.tag,
            value_cents=fact.value_cents,
            fiscal_year=fact.fiscal_year,
            fiscal_period=fact.fiscal_period,
            form_type=fact.form_type,
            filed_date=fact.filed_date,
            end_date=fact.end_date,
            accession_no=fact.accession_no,
            as_of_date=fact.end_date,
            observed_date=collection_date,
        )
