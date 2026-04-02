"""Unit tests for EFTS full-text search client.

Tests pagination, truncation detection, User-Agent compliance,
retry logic, date range filtering, and error handling.
"""

from __future__ import annotations

import httpx
import pytest

from ai_washer.ingestion.efts_client import EFTS_BASE_URL, EFTS_MAX_OFFSET, EFTSClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EDGAR_IDENTITY = "TestCorp test@example.com"


def _make_efts_hit(
    accession_no: str = "0001234567-26-000123",
    entity_name: str = "ACME CORP",
    cik: str = "0001234567",
    form_type: str = "10-K",
    file_date: str = "2026-02-15",
    period_of_report: str = "2025-12-31",
) -> dict:
    """Build a single EFTS hit in the raw API response format."""
    return {
        "_source": {
            "accession_no": accession_no,
            "form_type": form_type,
            "file_date": file_date,
            "entity_name": entity_name,
            "ciks": [cik],
            "period_of_report": period_of_report,
            "display_names": [f"{entity_name} (CIK {cik})"],
        }
    }


def _make_efts_response(
    hits: list[dict],
    total: int,
    relation: str = "eq",
) -> dict:
    """Build the nested EFTS JSON response structure."""
    return {
        "hits": {
            "total": {"value": total, "relation": relation},
            "hits": hits,
        }
    }


# ---------------------------------------------------------------------------
# Tests: Basic search
# ---------------------------------------------------------------------------


class TestSearchFilings:
    """Tests for EFTSClient.search_filings basic behavior."""

    def test_single_page_returns_hits(self, httpx_mock):
        """search_filings returns EFTSHit objects parsed from EFTS JSON."""
        raw_hits = [
            _make_efts_hit(accession_no="0001-26-001", entity_name="FOO INC"),
            _make_efts_hit(accession_no="0002-26-002", entity_name="BAR CORP"),
        ]
        httpx_mock.add_response(
            url=httpx.URL(EFTS_BASE_URL, params={
                "q": "artificial intelligence",
                "forms": "10-K",
                "from": "0",
                "size": "50",
            }),
            json=_make_efts_response(raw_hits, total=2),
        )

        with EFTSClient(edgar_identity=EDGAR_IDENTITY) as client:
            results = client.search_filings("artificial intelligence", forms="10-K")

        assert len(results) == 2
        assert results[0].accession_no == "0001-26-001"
        assert results[0].entity_name == "FOO INC"
        assert results[1].accession_no == "0002-26-002"

    def test_empty_response(self, httpx_mock):
        """Empty EFTS response returns empty list without error."""
        httpx_mock.add_response(
            url=httpx.URL(EFTS_BASE_URL, params={
                "q": "nonexistent term",
                "forms": "10-K",
                "from": "0",
                "size": "50",
            }),
            json=_make_efts_response([], total=0),
        )

        with EFTSClient(edgar_identity=EDGAR_IDENTITY) as client:
            results = client.search_filings("nonexistent term")

        assert results == []


# ---------------------------------------------------------------------------
# Tests: Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    """Tests for automatic pagination through EFTS results."""

    def test_pagination_sends_multiple_requests(self, httpx_mock):
        """Client paginates when first page returns PAGE_SIZE results."""
        page_size = 2  # Use small page for testing
        page1_hits = [
            _make_efts_hit(accession_no="0001-26-001"),
            _make_efts_hit(accession_no="0002-26-002"),
        ]
        page2_hits = [
            _make_efts_hit(accession_no="0003-26-003"),
        ]

        # First page -- full, triggers pagination
        httpx_mock.add_response(
            url=httpx.URL(EFTS_BASE_URL, params={
                "q": "machine learning",
                "forms": "10-K",
                "from": "0",
                "size": "2",
            }),
            json=_make_efts_response(page1_hits, total=3),
        )
        # Second page -- partial, stops pagination
        httpx_mock.add_response(
            url=httpx.URL(EFTS_BASE_URL, params={
                "q": "machine learning",
                "forms": "10-K",
                "from": "2",
                "size": "2",
            }),
            json=_make_efts_response(page2_hits, total=3),
        )

        with EFTSClient(edgar_identity=EDGAR_IDENTITY, page_size=page_size) as client:
            results = client.search_filings("machine learning")

        assert len(results) == 3
        assert results[2].accession_no == "0003-26-003"

    def test_pagination_stops_when_fewer_than_page_size(self, httpx_mock):
        """Client stops paginating when page returns fewer than PAGE_SIZE."""
        page_size = 5
        hits = [_make_efts_hit(accession_no=f"000{i}-26-000{i}") for i in range(3)]

        httpx_mock.add_response(
            url=httpx.URL(EFTS_BASE_URL, params={
                "q": "ai",
                "forms": "10-K",
                "from": "0",
                "size": "5",
            }),
            json=_make_efts_response(hits, total=3),
        )

        with EFTSClient(edgar_identity=EDGAR_IDENTITY, page_size=page_size) as client:
            results = client.search_filings("ai")

        assert len(results) == 3
        # Only one request should have been made
        assert len(httpx_mock.get_requests()) == 1

    def test_pagination_stops_at_max_offset(self, httpx_mock):
        """Client stops paginating when offset reaches EFTS_MAX_OFFSET (10,000)."""
        page_size = 50
        hits = [_make_efts_hit() for _ in range(page_size)]

        # Mock enough responses to reach the offset cap
        # We need 10000/50 = 200 pages, but we'll verify it stops
        for offset in range(0, EFTS_MAX_OFFSET, page_size):
            httpx_mock.add_response(
                json=_make_efts_response(hits, total=20000, relation="gte"),
            )

        with EFTSClient(edgar_identity=EDGAR_IDENTITY, page_size=page_size) as client:
            results = client.search_filings("artificial intelligence")

        # Should have exactly 10000/50 = 200 pages * 50 = 10000 results
        assert len(results) == EFTS_MAX_OFFSET
        requests = httpx_mock.get_requests()
        assert len(requests) == EFTS_MAX_OFFSET // page_size


# ---------------------------------------------------------------------------
# Tests: Truncation detection
# ---------------------------------------------------------------------------


class TestTruncation:
    """Tests for truncation detection (total_relation='gte')."""

    def test_truncated_results_detected(self, httpx_mock):
        """Client detects truncated results when total_relation='gte'."""
        hits = [_make_efts_hit()]
        httpx_mock.add_response(
            url=httpx.URL(EFTS_BASE_URL, params={
                "q": "ai",
                "forms": "10-K",
                "from": "0",
                "size": "1",
            }),
            json=_make_efts_response(hits, total=10000, relation="gte"),
        )

        with EFTSClient(edgar_identity=EDGAR_IDENTITY, page_size=1) as client:
            is_truncated = client.check_truncation("ai")

        assert is_truncated is True

    def test_non_truncated_results(self, httpx_mock):
        """Client reports non-truncated when total_relation='eq'."""
        hits = [_make_efts_hit()]
        httpx_mock.add_response(
            url=httpx.URL(EFTS_BASE_URL, params={
                "q": "specific term",
                "forms": "10-K",
                "from": "0",
                "size": "1",
            }),
            json=_make_efts_response(hits, total=500, relation="eq"),
        )

        with EFTSClient(edgar_identity=EDGAR_IDENTITY, page_size=1) as client:
            is_truncated = client.check_truncation("specific term")

        assert is_truncated is False


# ---------------------------------------------------------------------------
# Tests: User-Agent compliance
# ---------------------------------------------------------------------------


class TestUserAgent:
    """Tests for SEC-compliant User-Agent header on every request."""

    def test_user_agent_header_included(self, httpx_mock):
        """Every HTTP request includes User-Agent matching edgar_identity."""
        httpx_mock.add_response(
            json=_make_efts_response([], total=0),
        )

        with EFTSClient(edgar_identity=EDGAR_IDENTITY) as client:
            client.search_filings("test query")

        request = httpx_mock.get_requests()[0]
        assert request.headers["user-agent"] == EDGAR_IDENTITY


# ---------------------------------------------------------------------------
# Tests: Retry logic
# ---------------------------------------------------------------------------


class TestRetry:
    """Tests for tenacity retry on transient HTTP errors."""

    def test_retries_on_429(self, httpx_mock):
        """Client retries on 429 Too Many Requests."""
        # First call returns 429, second succeeds
        httpx_mock.add_response(status_code=429)
        httpx_mock.add_response(
            json=_make_efts_response([], total=0),
        )

        with EFTSClient(edgar_identity=EDGAR_IDENTITY) as client:
            results = client.search_filings("test")

        assert results == []
        assert len(httpx_mock.get_requests()) == 2

    def test_retries_on_500(self, httpx_mock):
        """Client retries on 500 Internal Server Error."""
        httpx_mock.add_response(status_code=500)
        httpx_mock.add_response(
            json=_make_efts_response([], total=0),
        )

        with EFTSClient(edgar_identity=EDGAR_IDENTITY) as client:
            results = client.search_filings("test")

        assert results == []
        assert len(httpx_mock.get_requests()) == 2


# ---------------------------------------------------------------------------
# Tests: Date range filtering
# ---------------------------------------------------------------------------


class TestDateRange:
    """Tests for date range parameters in search_filings."""

    def test_date_range_sends_custom_params(self, httpx_mock):
        """search_filings with date_start/date_end sends dateRange, startdt, enddt."""
        httpx_mock.add_response(
            url=httpx.URL(EFTS_BASE_URL, params={
                "q": "artificial intelligence",
                "forms": "10-K",
                "from": "0",
                "size": "50",
                "dateRange": "custom",
                "startdt": "2025-01-01",
                "enddt": "2026-01-01",
            }),
            json=_make_efts_response([], total=0),
        )

        with EFTSClient(edgar_identity=EDGAR_IDENTITY) as client:
            results = client.search_filings(
                "artificial intelligence",
                date_start="2025-01-01",
                date_end="2026-01-01",
            )

        assert results == []
        request = httpx_mock.get_requests()[0]
        assert "dateRange" in str(request.url)
        assert "startdt" in str(request.url)
        assert "enddt" in str(request.url)


# ---------------------------------------------------------------------------
# Tests: Input validation
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for input validation."""

    def test_invalid_page_size_zero(self):
        """Client raises ValueError when page_size is 0."""
        with pytest.raises(ValueError, match="page_size must be positive"):
            EFTSClient(edgar_identity=EDGAR_IDENTITY, page_size=0)

    def test_invalid_page_size_negative(self):
        """Client raises ValueError when page_size is negative."""
        with pytest.raises(ValueError, match="page_size must be positive"):
            EFTSClient(edgar_identity=EDGAR_IDENTITY, page_size=-1)
