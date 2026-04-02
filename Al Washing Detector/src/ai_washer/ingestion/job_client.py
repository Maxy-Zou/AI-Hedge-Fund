"""Thin wrapper around python-jobspy for job posting search.

Provides a typed interface that converts raw DataFrames from jobspy's
scrape_jobs() into validated JobRecord objects with role classification
and dedup hashing. Includes tenacity-based retry logic for transient
scraping failures.

Usage::

    client = JobClient()
    records = client.search_company_jobs("Apple Inc")
    for r in records:
        print(r.title, r.role_classification, r.dedup_hash)
"""

from __future__ import annotations

import math

import structlog
from jobspy import scrape_jobs
from tenacity import retry, stop_after_attempt, wait_exponential

from ai_washer.ingestion.job_types import JobRecord, classify_role, compute_job_hash

logger = structlog.get_logger(__name__)


class JobClientError(Exception):
    """Raised when the job scraping client encounters an error."""


class JobClient:
    """Client for searching job postings via python-jobspy.

    Wraps scrape_jobs() to return typed JobRecord objects with role
    classification and dedup hashing applied. Defaults to Indeed and
    Google (not LinkedIn, due to rate limit risk).

    Parameters
    ----------
    sites:
        Job board sites to search. Defaults to ``["indeed", "google"]``.
    results_wanted:
        Maximum number of results per search. Defaults to 50.
    """

    def __init__(
        self,
        sites: list[str] | None = None,
        results_wanted: int = 50,
    ) -> None:
        self._sites = sites or ["indeed", "google"]
        self._results_wanted = results_wanted
        self._log = logger.bind(client="job")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=0.1, max=10),
        reraise=True,
    )
    def search_company_jobs(
        self,
        company_name: str,
        search_term: str | None = None,
    ) -> list[JobRecord]:
        """Search for job postings at a company.

        Builds a search query combining the company name with AI/ML
        keywords, calls jobspy scrape_jobs(), and converts each result
        row into a validated JobRecord with role classification and
        dedup hash.

        Parameters
        ----------
        company_name:
            Company name to search for.
        search_term:
            Custom search term. If None, builds default query with
            AI/ML keywords.

        Returns
        -------
        list[JobRecord]
            Validated job records with classification and hashing.

        Raises
        ------
        JobClientError
            On any scraping failure after retries.
        """
        if search_term is None:
            search_term = f'"{company_name}" AI OR "machine learning"'

        self._log.info(
            "job_search_started",
            company_name=company_name,
            sites=self._sites,
            results_wanted=self._results_wanted,
        )

        try:
            df = scrape_jobs(
                site_name=self._sites,
                search_term=search_term,
                results_wanted=self._results_wanted,
                country_indeed="USA",
            )
        except Exception as exc:
            raise JobClientError(
                f"Job scraping failed for '{company_name}': {exc}"
            ) from exc

        if df is None or df.empty:
            self._log.info("job_search_empty", company_name=company_name)
            return []

        records: list[JobRecord] = []
        for _, row in df.iterrows():
            title = str(row.get("title", ""))
            company_raw = str(row.get("company", company_name))
            location = _nan_to_none(row.get("location"))
            description = _nan_to_none(row.get("description"))
            job_url = _nan_to_none(row.get("job_url"))
            site = str(row.get("site", "unknown"))

            role = classify_role(title, description or "")
            dedup = compute_job_hash(company_raw, title, location or "")

            record = JobRecord(
                title=title,
                company_name_raw=company_raw,
                location=location,
                description=description,
                job_url=job_url,
                source_site=site,
                role_classification=role,
                dedup_hash=dedup,
            )
            records.append(record)

        self._log.info(
            "job_search_complete",
            company_name=company_name,
            jobs_found=len(records),
        )

        return records


def _nan_to_none(value: object) -> str | None:
    """Convert NaN or None to None, otherwise return string.

    pandas DataFrames may contain float NaN for missing string columns.
    This normalizes them to None for Pydantic validation.

    Args:
        value: Raw value from DataFrame row.

    Returns:
        String value or None.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value)
    return s if s else None
