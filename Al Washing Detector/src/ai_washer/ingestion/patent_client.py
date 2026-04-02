"""PatentSearch API client for USPTO patent data.

Queries the PatentSearch API (search.patentsview.org/api/v1) for AI-related
patents by assignee organization, with CPC code filtering, cursor-based
pagination, and tenacity-based retry logic for rate limits.

Usage::

    client = PatentSearchClient(api_key="your-key")
    patents = client.search_by_assignee("Acme Corp")
    for p in patents:
        print(p.patent_id, p.patent_title, p.cpc_codes)
"""

from __future__ import annotations

import json
from datetime import date

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ai_washer.ingestion.patent_types import CPC_AI_PREFIXES, PatentRecord

logger = structlog.get_logger(__name__)

# Maximum number of pages to fetch in a single search (safety cap).
_MAX_PAGES = 10

# Default page size for the PatentSearch API.
_PAGE_SIZE = 100

# URL to request a PatentsView API key.
_KEY_REQUEST_URL = (
    "https://patentsview-support.atlassian.net"
    "/servicedesk/customer/portal/1/group/1/create/18"
)

# Fields to request from the PatentSearch API.
_RESPONSE_FIELDS = [
    "patent_id",
    "patent_title",
    "patent_date",
    "assignees.assignee_organization",
    "cpc_current.cpc_group_id",
]


class PatentClientError(Exception):
    """Raised when the PatentSearch API client encounters an error."""


def _is_retryable(exc: BaseException) -> bool:
    """Determine if an HTTP error should trigger a retry.

    Retries on 429 (rate limit) and 5xx (server errors).
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


class PatentSearchClient:
    """Client for the USPTO PatentSearch API.

    Searches for patents by assignee organization with CPC code filters.
    Handles cursor-based pagination and rate limit retries via tenacity.

    Parameters
    ----------
    api_key:
        PatentsView API key. Empty string is accepted at construction
        time (lazy validation) but will raise PatentClientError on search.
    base_url:
        Base URL for the PatentSearch API.
    client:
        Optional httpx.Client for dependency injection in tests.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://search.patentsview.org/api/v1",
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._log = logger.bind(client="patent_search")

        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(
                timeout=30.0,
                headers={"X-Api-Key": api_key},
            )
            self._owns_client = True

    # -- Public API -----------------------------------------------------------

    def search_by_assignee(
        self,
        assignee_name: str,
        cpc_prefixes: tuple[str, ...] = CPC_AI_PREFIXES,
        after_date: date | None = None,
    ) -> list[PatentRecord]:
        """Search for AI-related patents by assignee organization name.

        Parameters
        ----------
        assignee_name:
            Organization name to search (uses _contains filter).
        cpc_prefixes:
            CPC code prefixes to filter (uses _begins filter).
            Defaults to CPC_AI_PREFIXES (G06N, G06F18).
        after_date:
            If provided, only return patents with patent_date >= this date
            (for incremental collection).

        Returns
        -------
        list[PatentRecord]
            Deduplicated list of matching patents.

        Raises
        ------
        PatentClientError
            If API key is empty, authentication fails, or query is invalid.
        """
        if not self._api_key:
            raise PatentClientError(
                f"PatentsView API key is required. "
                f"Request a free key at {_KEY_REQUEST_URL}"
            )

        query = self._build_query(assignee_name, cpc_prefixes, after_date)
        self._log.info(
            "patent_search_started",
            assignee=assignee_name,
            cpc_prefixes=cpc_prefixes,
            after_date=str(after_date) if after_date else None,
        )

        all_patents: list[PatentRecord] = []
        seen_ids: set[str] = set()
        after_cursor: str | None = None

        for page_num in range(_MAX_PAGES):
            response_data = self._fetch_page(
                query=query, size=_PAGE_SIZE, after=after_cursor
            )

            patents_data = response_data.get("patents", [])
            if not patents_data:
                break

            for patent_dict in patents_data:
                record = self._parse_patent(patent_dict)
                if record is not None and record.patent_id not in seen_ids:
                    all_patents.append(record)
                    seen_ids.add(record.patent_id)

            # Pagination: if we got a full page, use the last patent_id as cursor
            if len(patents_data) < _PAGE_SIZE:
                break

            # Use the last patent_id as the cursor for the next page
            last_patent = patents_data[-1]
            after_cursor = last_patent.get("patent_id")
            if not after_cursor:
                break

        self._log.info(
            "patent_search_complete",
            assignee=assignee_name,
            total_patents=len(all_patents),
            pages_fetched=page_num + 1,
        )

        return all_patents

    # -- Query construction ---------------------------------------------------

    def _build_query(
        self,
        assignee_name: str,
        cpc_prefixes: tuple[str, ...],
        after_date: date | None,
    ) -> dict:
        """Build the PatentSearch API query dict.

        Structure::

            {"_and": [
                {"_contains": {"assignees.assignee_organization": name}},
                {"_or": [{"_begins": {"cpc_current.cpc_group_id": prefix}} ...]},
                # Optional: {"_gte": {"patent_date": "YYYY-MM-DD"}}
            ]}
        """
        conditions: list[dict] = [
            {"_contains": {"assignees.assignee_organization": assignee_name}},
            {
                "_or": [
                    {"_begins": {"cpc_current.cpc_group_id": prefix}}
                    for prefix in cpc_prefixes
                ]
            },
        ]

        if after_date is not None:
            conditions.append({"_gte": {"patent_date": after_date.isoformat()}})

        return {"_and": conditions}

    # -- HTTP layer -----------------------------------------------------------

    @retry(
        wait=wait_exponential(min=0.1, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    def _fetch_page(
        self,
        query: dict,
        size: int = _PAGE_SIZE,
        after: str | None = None,
    ) -> dict:
        """Execute a single API call to the PatentSearch endpoint.

        Parameters
        ----------
        query:
            Query dict to serialize as JSON.
        size:
            Number of results per page.
        after:
            Cursor for pagination (last patent_id from previous page).

        Returns
        -------
        dict
            Parsed JSON response.

        Raises
        ------
        PatentClientError
            On 400 (invalid query) or 401/403 (authentication failure).
        """
        options: dict = {"size": size}
        if after is not None:
            options["after"] = after

        params = {
            "q": json.dumps(query),
            "f": json.dumps(_RESPONSE_FIELDS),
            "o": json.dumps(options),
        }

        response = self._client.get(
            f"{self._base_url}/patent/",
            params=params,
            headers={"X-Api-Key": self._api_key},
        )

        if response.status_code in (401, 403):
            raise PatentClientError(
                f"Authentication failed (HTTP {response.status_code}). "
                f"Check your API key or request one at {_KEY_REQUEST_URL}"
            )

        if response.status_code == 400:
            raise PatentClientError(
                f"Invalid query (HTTP 400): {response.text[:200]}"
            )

        # Raise for 429/5xx so tenacity can retry
        response.raise_for_status()

        return response.json()

    # -- Response parsing -----------------------------------------------------

    def _parse_patent(self, patent_dict: dict) -> PatentRecord | None:
        """Parse a single patent dict from the API response into a PatentRecord.

        Returns None if parsing fails (logs warning, does not raise).
        """
        try:
            patent_id = patent_dict.get("patent_id", "")
            patent_title = patent_dict.get("patent_title", "")
            patent_date_str = patent_dict.get("patent_date", "")

            # Extract first assignee organization
            assignees = patent_dict.get("assignees", [])
            assignee_org = ""
            if assignees and isinstance(assignees, list):
                first_assignee = assignees[0]
                if isinstance(first_assignee, dict):
                    assignee_org = first_assignee.get("assignee_organization", "")

            # Collect all CPC group IDs
            cpc_current = patent_dict.get("cpc_current", [])
            cpc_codes: list[str] = []
            if isinstance(cpc_current, list):
                for cpc_entry in cpc_current:
                    if isinstance(cpc_entry, dict):
                        group_id = cpc_entry.get("cpc_group_id", "")
                        if group_id:
                            cpc_codes.append(group_id)

            patent_date_val = date.fromisoformat(patent_date_str)

            return PatentRecord(
                patent_id=patent_id,
                patent_title=patent_title,
                patent_date=patent_date_val,
                assignee_organization=assignee_org,
                cpc_codes=cpc_codes,
            )
        except Exception:
            self._log.warning(
                "patent_parse_failed",
                patent_dict=patent_dict,
                exc_info=True,
            )
            return None
