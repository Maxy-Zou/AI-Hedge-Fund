"""EDGAR company facts client for EntityPublicFloat and CIK-ticker mapping.

Wraps the data.sec.gov XBRL company facts API and SEC company_tickers.json
with SEC-compliant User-Agent headers, tenacity retry on transient errors,
and CIK normalization utilities.

Usage::

    with EdgarFactsClient(edgar_identity="YourCo you@example.com") as client:
        float_cents = client.get_entity_public_float("320193")
        mapping = client.get_cik_ticker_mapping()
"""

from __future__ import annotations

import logging
import time

import httpx
import structlog
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)

XBRL_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# SEC rate limit: 10 req/sec. We stay conservative.
_SEC_RATE_LIMIT_DELAY = 0.1


# ---------------------------------------------------------------------------
# CIK normalization
# ---------------------------------------------------------------------------


def pad_cik(cik: str) -> str:
    """Pad CIK to 10 digits with leading zeros.

    Examples::

        pad_cik("320193")      -> "0000320193"
        pad_cik("0000320193")  -> "0000320193"
    """
    return cik.lstrip("0").zfill(10)


def strip_cik(cik: str) -> str:
    """Remove leading zeros from CIK.

    Examples::

        strip_cik("0000320193") -> "320193"
        strip_cik("0")          -> "0"
    """
    return cik.lstrip("0") or "0"


# ---------------------------------------------------------------------------
# Retry predicate
# ---------------------------------------------------------------------------


def _is_retryable_error(exc: BaseException) -> bool:
    """Return True for transient HTTP errors (429, 5xx) that should be retried."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return False


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class EdgarFactsClient:
    """EDGAR company facts client for XBRL data and CIK-ticker mapping.

    Parameters
    ----------
    edgar_identity:
        SEC-compliant User-Agent string, e.g. "CompanyName email@example.com".
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

    # -- Context manager --------------------------------------------------

    def __enter__(self) -> EdgarFactsClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._client.close()

    # -- Public API -------------------------------------------------------

    def get_entity_public_float(self, cik: str) -> int | None:
        """Fetch EntityPublicFloat from XBRL company facts, returned in cents.

        Selects the most recent entry by ``end`` date. Returns ``None``
        when the CIK is not found (404) or the EntityPublicFloat tag
        is absent from the response.

        Parameters
        ----------
        cik:
            CIK number (any format -- will be padded to 10 digits).
        """
        padded = pad_cik(cik)
        url = XBRL_FACTS_URL.format(cik=padded)

        try:
            data = self._fetch_json(url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.info("edgar_cik_not_found", cik=cik, padded=padded)
                return None
            raise

        # Navigate: facts -> dei -> EntityPublicFloat -> units -> USD
        dei = data.get("facts", {}).get("dei", {})
        float_data = dei.get("EntityPublicFloat", {})
        usd_entries = float_data.get("units", {}).get("USD", [])

        if not usd_entries:
            logger.info(
                "edgar_entity_public_float_missing",
                cik=cik,
                padded=padded,
            )
            return None

        # Select the most recent entry by end date
        latest = max(usd_entries, key=lambda x: x.get("end", ""))
        value_dollars = latest["val"]
        value_cents = int(value_dollars * 100)

        logger.info(
            "edgar_entity_public_float_fetched",
            cik=cik,
            end_date=latest.get("end"),
            value_cents=value_cents,
        )
        return value_cents

    def get_cik_ticker_mapping(self) -> dict[str, tuple[str, str]]:
        """Load CIK-to-ticker mapping from SEC company_tickers.json.

        Returns a dict mapping stripped CIK strings to (ticker, title)
        tuples.
        """
        data = self._fetch_json(COMPANY_TICKERS_URL)

        mapping: dict[str, tuple[str, str]] = {}
        for entry in data.values():
            cik_str = strip_cik(str(entry["cik_str"]))
            ticker = entry["ticker"]
            title = entry["title"]
            mapping[cik_str] = (ticker, title)

        logger.info("edgar_ticker_mapping_loaded", count=len(mapping))
        return mapping

    def get_entity_public_float_batch(
        self,
        ciks: list[str],
    ) -> dict[str, int | None]:
        """Fetch EntityPublicFloat for multiple CIKs, respecting rate limits.

        Returns a dict mapping each CIK to its public float in cents
        (or None if not found).
        """
        results: dict[str, int | None] = {}

        for idx, cik in enumerate(ciks):
            results[cik] = self.get_entity_public_float(cik)

            if (idx + 1) % 50 == 0:
                logger.info(
                    "edgar_batch_progress",
                    completed=idx + 1,
                    total=len(ciks),
                )

            # Respect SEC 10 req/sec rate limit
            if idx < len(ciks) - 1:
                time.sleep(_SEC_RATE_LIMIT_DELAY)

        logger.info(
            "edgar_batch_complete",
            total=len(ciks),
            found=sum(1 for v in results.values() if v is not None),
        )
        return results

    # -- Private ----------------------------------------------------------

    @retry(
        wait=wait_exponential(multiplier=1, min=0.1, max=30),
        stop=stop_after_attempt(5),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
        reraise=True,
    )
    def _fetch_json(self, url: str) -> dict:
        """GET a URL and return parsed JSON, raising on non-retryable errors."""
        response = self._client.get(url)
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def get_entity_public_float(edgar_identity: str, cik: str) -> int | None:
    """Fetch EntityPublicFloat in cents (one-shot convenience wrapper)."""
    with EdgarFactsClient(edgar_identity=edgar_identity) as client:
        return client.get_entity_public_float(cik)


def get_cik_ticker_mapping(edgar_identity: str) -> dict[str, tuple[str, str]]:
    """Load CIK-ticker mapping from SEC (one-shot convenience wrapper)."""
    with EdgarFactsClient(edgar_identity=edgar_identity) as client:
        return client.get_cik_ticker_mapping()
