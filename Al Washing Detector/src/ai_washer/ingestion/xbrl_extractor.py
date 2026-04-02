"""XBRL financial fact extraction from the EDGAR companyfacts API.

Extracts R&D spending, CapEx, and revenue from structured XBRL data using
fallback tag lists, deduplication by fiscal period, and dollar-to-cents
conversion.  Companion module to ``edgar_client.py``.

Usage::

    # Pure functions (no HTTP)
    facts_by_concept = extract_all_facts(company_facts_json)

    # Class with HTTP (rate-limited, retried)
    with XBRLExtractor(edgar_identity="YourCo you@example.com") as ext:
        records = ext.extract_company_xbrl("320193")
"""

from __future__ import annotations

import logging
import time
from datetime import date as date_type

import httpx
import structlog
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ai_washer.ingestion.edgar_client import (
    XBRL_FACTS_URL,
    _is_retryable_error,
    pad_cik,
)
from ai_washer.ingestion.types import XBRL_TAG_GROUPS, XBRLFactRecord

logger = structlog.get_logger(__name__)

# SEC rate limit: 10 req/sec. Match EdgarFactsClient's conservative delay.
_SEC_RATE_LIMIT_DELAY = 0.1


# ---------------------------------------------------------------------------
# Pure functions (no HTTP, no class needed)
# ---------------------------------------------------------------------------


def deduplicate_by_period(entries: list[dict]) -> list[dict]:
    """Keep only the latest-filed entry for each (end, fp) pair.

    When a company amends a filing (10-K/A), both original and amended
    values appear in the companyfacts response.  This keeps the most
    recently filed value for each fiscal period.

    Parameters
    ----------
    entries:
        Raw XBRL fact entries from the companyfacts JSON.

    Returns
    -------
    list[dict]
        Deduplicated entries, one per unique (end, fp) combination.
    """
    best: dict[tuple[str, str], dict] = {}

    for entry in entries:
        key = (entry.get("end", ""), entry.get("fp", ""))
        existing = best.get(key)

        if existing is None or entry.get("filed", "") > existing.get("filed", ""):
            best[key] = entry

    return list(best.values())


def extract_facts_for_concept(
    concept: str,
    facts_json: dict,
    form_filter: str | None = "10-K",
) -> list[XBRLFactRecord]:
    """Extract XBRL facts for a financial concept using fallback tags.

    Looks up the tag list from ``XBRL_TAG_GROUPS[concept]``, navigates
    ``facts_json["facts"]["us-gaap"]``, and tries each tag in order --
    using the first one that has USD entries.

    Parameters
    ----------
    concept:
        Normalized concept name (e.g. ``"rd_expense"``, ``"capex"``,
        ``"revenue"``).  Must be a key in ``XBRL_TAG_GROUPS``.
    facts_json:
        Raw companyfacts JSON response from the EDGAR API.
    form_filter:
        If set, only entries whose ``form`` field exactly matches this
        value are included.  ``"10-K"`` excludes ``"10-K/A"``.
        Pass ``None`` to include all form types.

    Returns
    -------
    list[XBRLFactRecord]
        Extracted and deduplicated fact records, or empty list if no
        matching tag is found.
    """
    tag_list = XBRL_TAG_GROUPS.get(concept, [])
    us_gaap = facts_json.get("facts", {}).get("us-gaap", {})

    for tag in tag_list:
        tag_data = us_gaap.get(tag, {})
        usd_entries = tag_data.get("units", {}).get("USD", [])

        if not usd_entries:
            continue

        # Filter by form type (exact match)
        if form_filter is not None:
            usd_entries = [
                e for e in usd_entries
                if e.get("form") == form_filter
            ]

        if not usd_entries:
            continue

        # Deduplicate: for each (end, fp) pair, keep latest filed date
        deduped = deduplicate_by_period(usd_entries)

        # Convert to XBRLFactRecord
        records = []
        for entry in deduped:
            record = XBRLFactRecord(
                tag=tag,
                concept=concept,
                end_date=date_type.fromisoformat(entry["end"]),
                value_cents=int(entry["val"] * 100),
                fiscal_year=entry["fy"],
                fiscal_period=entry["fp"],
                form_type=entry["form"],
                filed_date=date_type.fromisoformat(entry["filed"]),
                accession_no=entry["accn"],
            )
            records.append(record)

        logger.info(
            "xbrl_facts_extracted",
            concept=concept,
            tag=tag,
            count=len(records),
        )
        return records

    logger.debug(
        "xbrl_no_matching_tag",
        concept=concept,
        tags_tried=[t for t in tag_list],
    )
    return []


def extract_all_facts(
    facts_json: dict,
    form_filter: str | None = "10-K",
) -> dict[str, list[XBRLFactRecord]]:
    """Extract facts for all concepts in ``XBRL_TAG_GROUPS``.

    Parameters
    ----------
    facts_json:
        Raw companyfacts JSON response from the EDGAR API.
    form_filter:
        Optional form type filter passed to
        ``extract_facts_for_concept``.

    Returns
    -------
    dict[str, list[XBRLFactRecord]]
        Mapping of concept name to list of extracted records.
    """
    return {
        concept: extract_facts_for_concept(concept, facts_json, form_filter)
        for concept in XBRL_TAG_GROUPS
    }


# ---------------------------------------------------------------------------
# XBRLExtractor class (HTTP client with rate limiting)
# ---------------------------------------------------------------------------


class XBRLExtractor:
    """EDGAR companyfacts API client for XBRL financial data extraction.

    Fetches structured XBRL data and extracts R&D, CapEx, and revenue
    facts using fallback tag lists.  Respects SEC rate limits and
    retries on transient errors.

    Parameters
    ----------
    edgar_identity:
        SEC-compliant User-Agent string, e.g.
        ``"CompanyName email@example.com"``.
    """

    def __init__(self, edgar_identity: str) -> None:
        self._edgar_identity = edgar_identity
        self._client = httpx.Client(
            headers={
                "User-Agent": edgar_identity,
                "Accept": "application/json",
            },
            timeout=30.0,
        )
        self._last_request_time: float | None = None

    # -- Context manager --------------------------------------------------

    def __enter__(self) -> XBRLExtractor:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._client.close()

    # -- Public API -------------------------------------------------------

    def get_company_facts(self, cik: str) -> dict | None:
        """Fetch all XBRL company facts for a CIK.

        Parameters
        ----------
        cik:
            CIK number (any format -- will be padded to 10 digits).

        Returns
        -------
        dict | None
            Parsed companyfacts JSON, or ``None`` if the CIK is not
            found (404).
        """
        self._enforce_rate_limit()
        padded = pad_cik(cik)
        url = XBRL_FACTS_URL.format(cik=padded)

        try:
            data = self._fetch_json(url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.info("xbrl_cik_not_found", cik=cik, padded=padded)
                return None
            raise

        logger.info("xbrl_company_facts_fetched", cik=cik, padded=padded)
        return data

    def extract_company_xbrl(self, cik: str) -> list[XBRLFactRecord]:
        """Fetch and extract all XBRL facts for a company.

        Calls ``get_company_facts`` then ``extract_all_facts``, and
        returns a flat list of all records sorted by ``end_date`` descending.

        Parameters
        ----------
        cik:
            CIK number (any format).

        Returns
        -------
        list[XBRLFactRecord]
            All extracted facts across all concepts, sorted by end_date
            descending.  Empty list if CIK not found.
        """
        facts_json = self.get_company_facts(cik)
        if facts_json is None:
            return []

        all_facts = extract_all_facts(facts_json)

        # Flatten into a single list
        flat: list[XBRLFactRecord] = []
        for records in all_facts.values():
            flat.extend(records)

        # Sort by end_date descending (most recent first)
        flat.sort(key=lambda r: r.end_date, reverse=True)

        logger.info(
            "xbrl_company_extracted",
            cik=cik,
            total_facts=len(flat),
        )
        return flat

    # -- Private ----------------------------------------------------------

    def _enforce_rate_limit(self) -> None:
        """Sleep to respect SEC 10 req/sec rate limit."""
        if self._last_request_time is not None:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < _SEC_RATE_LIMIT_DELAY:
                time.sleep(_SEC_RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.monotonic()

    @retry(
        wait=wait_exponential(multiplier=1, min=0.1, max=30),
        stop=stop_after_attempt(5),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(
            logging.getLogger(__name__), logging.WARNING,
        ),
        reraise=True,
    )
    def _fetch_json(self, url: str) -> dict:
        """GET a URL and return parsed JSON, raising on non-retryable errors."""
        response = self._client.get(url)
        response.raise_for_status()
        return response.json()
