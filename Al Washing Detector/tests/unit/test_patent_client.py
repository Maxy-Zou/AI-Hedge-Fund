"""Unit tests for PatentSearch API client.

Tests cover query construction, pagination, rate limiting retries,
error handling, and empty API key validation.
"""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from ai_washer.ingestion.patent_client import PatentClientError, PatentSearchClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PATENT_RESPONSE = {
    "patents": [
        {
            "patent_id": "US-11234567-B2",
            "patent_title": "Neural network optimization method",
            "patent_date": "2025-06-15",
            "assignees": [
                {"assignee_organization": "Acme Corp"}
            ],
            "cpc_current": [
                {"cpc_group_id": "G06N3/08"},
                {"cpc_group_id": "G06F18/24"},
            ],
        },
        {
            "patent_id": "US-11345678-B1",
            "patent_title": "Machine learning data pipeline",
            "patent_date": "2025-07-20",
            "assignees": [
                {"assignee_organization": "Acme Corp"}
            ],
            "cpc_current": [
                {"cpc_group_id": "G06N20/00"},
            ],
        },
    ],
    "total_patent_count": 2,
}

EMPTY_RESPONSE = {"patents": [], "total_patent_count": 0}


@pytest.fixture()
def api_key() -> str:
    return "test-api-key-12345"


@pytest.fixture()
def base_url() -> str:
    return "https://search.patentsview.org/api/v1"


# ---------------------------------------------------------------------------
# Tests: Query construction
# ---------------------------------------------------------------------------


class TestBuildQuery:
    """Tests for _build_query method."""

    def test_query_includes_cpc_begins(self, api_key: str, base_url: str) -> None:
        """Verify _build_query produces correct _begins structure for CPC codes."""
        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        query = client._build_query(
            assignee_name="Acme Corp",
            cpc_prefixes=("G06N", "G06F18"),
            after_date=None,
        )

        # Should have _and at top level
        assert "_and" in query
        conditions = query["_and"]

        # Should include assignee _contains filter
        assignee_filter = conditions[0]
        assert "_contains" in assignee_filter
        assert assignee_filter["_contains"]["assignees.assignee_organization"] == "Acme Corp"

        # Should include CPC _or with _begins
        cpc_filter = conditions[1]
        assert "_or" in cpc_filter
        begins_filters = cpc_filter["_or"]
        assert len(begins_filters) == 2
        assert {"_begins": {"cpc_current.cpc_group_id": "G06N"}} in begins_filters
        assert {"_begins": {"cpc_current.cpc_group_id": "G06F18"}} in begins_filters

    def test_after_date_filter(self, api_key: str, base_url: str) -> None:
        """Verify _gte added when after_date provided."""
        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        query = client._build_query(
            assignee_name="Acme Corp",
            cpc_prefixes=("G06N",),
            after_date=date(2024, 1, 1),
        )

        conditions = query["_and"]
        # Should have 3 conditions: assignee, CPC, and date
        assert len(conditions) == 3
        date_filter = conditions[2]
        assert "_gte" in date_filter
        assert date_filter["_gte"]["patent_date"] == "2024-01-01"

    def test_no_date_filter_when_none(self, api_key: str, base_url: str) -> None:
        """Verify no _gte when after_date is None."""
        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        query = client._build_query(
            assignee_name="Acme Corp",
            cpc_prefixes=("G06N",),
            after_date=None,
        )

        conditions = query["_and"]
        # Should have only 2 conditions: assignee and CPC
        assert len(conditions) == 2


# ---------------------------------------------------------------------------
# Tests: Search and parsing
# ---------------------------------------------------------------------------


class TestSearchByAssignee:
    """Tests for search_by_assignee method."""

    def test_search_returns_patents(
        self, httpx_mock, api_key: str, base_url: str
    ) -> None:
        """Mock 200 with sample patent JSON, verify PatentRecord list."""
        httpx_mock.add_response(
            url=httpx.URL(f"{base_url}/patent/", params={
                "q": json.dumps({"_and": [
                    {"_contains": {"assignees.assignee_organization": "Acme Corp"}},
                    {"_or": [
                        {"_begins": {"cpc_current.cpc_group_id": "G06N"}},
                        {"_begins": {"cpc_current.cpc_group_id": "G06F18"}},
                    ]},
                ]}),
                "f": json.dumps([
                    "patent_id", "patent_title", "patent_date",
                    "assignees.assignee_organization",
                    "cpc_current.cpc_group_id",
                ]),
                "o": json.dumps({"size": 100}),
            }),
            json=SAMPLE_PATENT_RESPONSE,
        )

        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        results = client.search_by_assignee("Acme Corp")

        assert len(results) == 2
        assert results[0].patent_id == "US-11234567-B2"
        assert results[0].patent_title == "Neural network optimization method"
        assert results[0].patent_date == date(2025, 6, 15)
        assert results[0].assignee_organization == "Acme Corp"
        assert "G06N3/08" in results[0].cpc_codes
        assert "G06F18/24" in results[0].cpc_codes

    def test_empty_response_returns_empty(
        self, httpx_mock, api_key: str, base_url: str
    ) -> None:
        """Mock 200 with no patents, verify empty list."""
        httpx_mock.add_response(json=EMPTY_RESPONSE)

        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        results = client.search_by_assignee("Unknown Corp")

        assert results == []

    def test_response_missing_patents_key_returns_empty(
        self, httpx_mock, api_key: str, base_url: str
    ) -> None:
        """When response has no 'patents' field, return empty list."""
        httpx_mock.add_response(json={"total_patent_count": 0})

        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        results = client.search_by_assignee("Unknown Corp")

        assert results == []

    def test_deduplicates_by_patent_id(
        self, httpx_mock, api_key: str, base_url: str
    ) -> None:
        """Same patent_id appearing twice should be deduplicated."""
        duplicate_response = {
            "patents": [
                {
                    "patent_id": "US-11234567-B2",
                    "patent_title": "Neural network optimization method",
                    "patent_date": "2025-06-15",
                    "assignees": [{"assignee_organization": "Acme Corp"}],
                    "cpc_current": [{"cpc_group_id": "G06N3/08"}],
                },
                {
                    "patent_id": "US-11234567-B2",
                    "patent_title": "Neural network optimization method",
                    "patent_date": "2025-06-15",
                    "assignees": [{"assignee_organization": "Acme Corp"}],
                    "cpc_current": [{"cpc_group_id": "G06N3/08"}],
                },
            ],
            "total_patent_count": 2,
        }
        httpx_mock.add_response(json=duplicate_response)

        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        results = client.search_by_assignee("Acme Corp")

        assert len(results) == 1


# ---------------------------------------------------------------------------
# Tests: Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    """Tests for cursor-based pagination."""

    def test_pagination_follows_cursor(
        self, httpx_mock, api_key: str, base_url: str
    ) -> None:
        """Mock two pages, verify all patents collected."""
        # Page 1: 100 patents (full page) with a cursor for next
        page1_patents = [
            {
                "patent_id": f"US-{10000000 + i}-B2",
                "patent_title": f"Patent {i}",
                "patent_date": "2025-01-01",
                "assignees": [{"assignee_organization": "Big Corp"}],
                "cpc_current": [{"cpc_group_id": "G06N3/00"}],
            }
            for i in range(100)
        ]
        page1_response = {
            "patents": page1_patents,
            "total_patent_count": 150,
        }

        # Page 2: 50 patents (partial page, no more)
        page2_patents = [
            {
                "patent_id": f"US-{10000100 + i}-B2",
                "patent_title": f"Patent {100 + i}",
                "patent_date": "2025-01-01",
                "assignees": [{"assignee_organization": "Big Corp"}],
                "cpc_current": [{"cpc_group_id": "G06N3/00"}],
            }
            for i in range(50)
        ]
        page2_response = {
            "patents": page2_patents,
            "total_patent_count": 150,
        }

        httpx_mock.add_response(json=page1_response)
        httpx_mock.add_response(json=page2_response)

        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        results = client.search_by_assignee("Big Corp")

        assert len(results) == 150
        # Verify it made 2 requests
        assert len(httpx_mock.get_requests()) == 2


# ---------------------------------------------------------------------------
# Tests: Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for API error handling."""

    def test_empty_api_key_raises(self, base_url: str) -> None:
        """Verify PatentClientError on search with empty key."""
        client = PatentSearchClient(api_key="", base_url=base_url)
        with pytest.raises(PatentClientError, match="API key"):
            client.search_by_assignee("Acme Corp")

    def test_401_raises_auth_error(
        self, httpx_mock, api_key: str, base_url: str
    ) -> None:
        """Mock 401, verify PatentClientError."""
        httpx_mock.add_response(status_code=401)

        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        with pytest.raises(PatentClientError, match="Authentication failed"):
            client.search_by_assignee("Acme Corp")

    def test_403_raises_auth_error(
        self, httpx_mock, api_key: str, base_url: str
    ) -> None:
        """Mock 403, verify PatentClientError."""
        httpx_mock.add_response(status_code=403)

        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        with pytest.raises(PatentClientError, match="Authentication failed"):
            client.search_by_assignee("Acme Corp")

    def test_400_raises_invalid_query(
        self, httpx_mock, api_key: str, base_url: str
    ) -> None:
        """Mock 400, verify PatentClientError with invalid query message."""
        httpx_mock.add_response(status_code=400)

        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        with pytest.raises(PatentClientError, match="Invalid query"):
            client.search_by_assignee("Acme Corp")

    def test_429_retries(
        self, httpx_mock, api_key: str, base_url: str
    ) -> None:
        """Mock 429 then 200, verify retry succeeds."""
        # First call: 429
        httpx_mock.add_response(status_code=429)
        # Second call: success
        httpx_mock.add_response(json=SAMPLE_PATENT_RESPONSE)

        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        results = client.search_by_assignee("Acme Corp")

        assert len(results) == 2
        assert len(httpx_mock.get_requests()) == 2

    def test_500_retries_then_raises(
        self, httpx_mock, api_key: str, base_url: str
    ) -> None:
        """Mock persistent 500s, verify retry exhaustion raises."""
        for _ in range(5):
            httpx_mock.add_response(status_code=500)

        client = PatentSearchClient(api_key=api_key, base_url=base_url)
        with pytest.raises(Exception):
            client.search_by_assignee("Acme Corp")


# ---------------------------------------------------------------------------
# Tests: Client construction
# ---------------------------------------------------------------------------


class TestClientConstruction:
    """Tests for client initialization."""

    def test_client_stores_api_key(self, api_key: str, base_url: str) -> None:
        """Client can be constructed with empty key (lazy validation)."""
        client = PatentSearchClient(api_key="", base_url=base_url)
        # Should not raise on construction
        assert client._api_key == ""

    def test_custom_client_injection(self, api_key: str, base_url: str) -> None:
        """Custom httpx.Client can be injected for testing."""
        custom_client = httpx.Client(timeout=5.0)
        client = PatentSearchClient(
            api_key=api_key, base_url=base_url, client=custom_client
        )
        assert client._client is custom_client
        custom_client.close()
