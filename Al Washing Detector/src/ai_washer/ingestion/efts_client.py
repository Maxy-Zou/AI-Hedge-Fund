"""Paginated EFTS full-text search client for SEC filings.

Wraps the efts.sec.gov/LATEST/search-index API with automatic
offset-based pagination (up to 10,000 results), truncation detection,
SEC-compliant User-Agent headers, and tenacity retry on transient errors.

Usage::

    with EFTSClient(edgar_identity="YourCo you@example.com") as client:
        hits = client.search_filings("artificial intelligence", forms="10-K")
        for hit in hits:
            print(hit.entity_name, hit.ciks)
"""

from __future__ import annotations

import logging

import httpx
import structlog
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ai_washer.universe.types import EFTSHit, EFTSResponse

logger = structlog.get_logger(__name__)

EFTS_BASE_URL = "https://efts.sec.gov/LATEST/search-index"
EFTS_MAX_OFFSET = 10_000


def _is_retryable_error(exc: BaseException) -> bool:
    """Return True for transient HTTP errors (429, 5xx) that should be retried."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return False


class EFTSClient:
    """Paginated EFTS full-text search client.

    Parameters
    ----------
    edgar_identity:
        SEC-compliant User-Agent string, e.g. "CompanyName email@example.com".
    page_size:
        Number of results per page (1-100). Default 50.
    """

    def __init__(self, edgar_identity: str, page_size: int = 50) -> None:
        if page_size <= 0:
            msg = f"page_size must be positive, got {page_size}"
            raise ValueError(msg)

        self._edgar_identity = edgar_identity
        self._page_size = page_size
        self._client = httpx.Client(
            headers={
                "User-Agent": edgar_identity,
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    # -- Context manager --------------------------------------------------

    def __enter__(self) -> EFTSClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._client.close()

    # -- Public API -------------------------------------------------------

    def search_filings(
        self,
        query: str,
        forms: str = "10-K",
        date_start: str | None = None,
        date_end: str | None = None,
    ) -> list[EFTSHit]:
        """Search EFTS for filings matching *query*, paginating automatically.

        Returns all matching hits up to the EFTS 10,000-result cap.
        When EFTS reports more results than can be retrieved
        (total_relation='gte'), consider splitting the query.

        Parameters
        ----------
        query:
            Full-text search string (e.g. "artificial intelligence").
        forms:
            Filing form type filter (default "10-K").
        date_start:
            Optional start date (YYYY-MM-DD) for date range filter.
        date_end:
            Optional end date (YYYY-MM-DD) for date range filter.
        """
        params: dict[str, str | int] = {
            "q": query,
            "forms": forms,
            "from": 0,
            "size": self._page_size,
        }
        if date_start is not None and date_end is not None:
            params["dateRange"] = "custom"
            params["startdt"] = date_start
            params["enddt"] = date_end

        all_hits: list[EFTSHit] = []
        page_number = 0

        while int(params["from"]) < EFTS_MAX_OFFSET:
            data = self._fetch_page(params)
            response = self._parse_efts_response(data)

            all_hits.extend(response.hits)
            page_number += 1

            log = logger.bind(
                query=query,
                page=page_number,
                page_hits=len(response.hits),
                total=response.total_value,
                accumulated=len(all_hits),
            )
            log.info("efts_page_fetched")

            if response.is_truncated and page_number == 1:
                log.warning(
                    "efts_results_truncated",
                    total_relation=response.total_relation,
                    hint="Consider splitting query into narrower date ranges",
                )

            # Stop if this page returned fewer than page_size (last page)
            if len(response.hits) < self._page_size:
                break

            params = {**params, "from": int(params["from"]) + self._page_size}

        logger.info(
            "efts_search_complete",
            query=query,
            total_results=len(all_hits),
            pages=page_number,
        )
        return all_hits

    def check_truncation(self, query: str, forms: str = "10-K") -> bool:
        """Check if a query produces truncated results (>10K matches).

        Makes a single request with size=1 to inspect total_relation.
        """
        params: dict[str, str | int] = {
            "q": query,
            "forms": forms,
            "from": 0,
            "size": 1,
        }
        data = self._fetch_page(params)
        response = self._parse_efts_response(data)
        return response.is_truncated

    def _parse_efts_response(self, data: dict) -> EFTSResponse:
        """Parse raw EFTS JSON dict into a typed EFTSResponse.

        The search-index API returns _source dicts with 'adsh', 'form',
        and 'period_ending' instead of the legacy 'accession_no', 'form_type',
        'entity_name'. Uses EFTSHit.from_search_index() to map field names.
        """
        hits_wrapper = data.get("hits", {})
        total_info = hits_wrapper.get("total", {})
        raw_hits = hits_wrapper.get("hits", [])

        parsed_hits = [
            EFTSHit.from_search_index(hit["_source"])
            for hit in raw_hits
        ]

        return EFTSResponse(
            total_value=total_info.get("value", 0),
            total_relation=total_info.get("relation", "eq"),
            hits=parsed_hits,
        )

    # -- Private ----------------------------------------------------------

    @retry(
        wait=wait_exponential(multiplier=1, min=0.1, max=30),
        stop=stop_after_attempt(5),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
        reraise=True,
    )
    def _fetch_page(self, params: dict[str, str | int]) -> dict:
        """GET a single EFTS page, raising on non-retryable errors."""
        response = self._client.get(EFTS_BASE_URL, params=params)
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def search_filings(
    edgar_identity: str,
    query: str,
    forms: str = "10-K",
    page_size: int = 50,
    date_start: str | None = None,
    date_end: str | None = None,
) -> list[EFTSHit]:
    """Search EFTS with a one-shot client (convenience wrapper).

    Creates an EFTSClient, runs the search, and returns the results.
    For repeated searches, prefer creating an EFTSClient directly to
    reuse the HTTP connection pool.
    """
    with EFTSClient(edgar_identity=edgar_identity, page_size=page_size) as client:
        return client.search_filings(
            query=query,
            forms=forms,
            date_start=date_start,
            date_end=date_end,
        )
