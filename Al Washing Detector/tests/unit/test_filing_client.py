"""Unit tests for FilingClient with mocked edgartools.

Tests filing retrieval (10-K, 10-Q, 8-K), section extraction,
truncation, validation, content hashing, error handling, and
identity initialization.
"""

from __future__ import annotations

import hashlib
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from ai_washer.config import FilingCollectionSettings
from ai_washer.ingestion.types import FilingData, FilingSections


# ---------------------------------------------------------------------------
# Helpers: build mock edgartools objects
# ---------------------------------------------------------------------------


def _make_mock_filing(
    *,
    accession_no: str = "0001234567-25-000001",
    form: str = "10-K",
    filing_date: str = "2025-03-15",
    report_date: str = "2024-12-31",
    company: str = "TestCorp Inc",
    cik: int = 123456,
) -> MagicMock:
    """Create a mock CompanyFiling with expected attributes."""
    filing = MagicMock()
    filing.accession_no = accession_no
    filing.accession_number = accession_no
    filing.form = form
    filing.filing_date = filing_date
    filing.report_date = report_date
    filing.company = company
    filing.cik = cik
    return filing


def _make_mock_tenk(
    business: str = "We are a technology company." * 50,
    risk_factors: str = "Risk factor content here." * 50,
    mda: str = "Management discussion and analysis." * 50,
) -> MagicMock:
    """Create a mock TenK object with section bracket access."""
    tenk = MagicMock()

    def bracket_access(_self: object, key: str) -> str | None:
        mapping = {
            "Item 1": business,
            "Item 1A": risk_factors,
            "Item 7": mda,
        }
        return mapping.get(key)

    tenk.__getitem__ = bracket_access
    return tenk


def _make_mock_tenq(
    mda: str = "Quarterly management discussion." * 50,
) -> MagicMock:
    """Create a mock TenQ object with section bracket access."""
    tenq = MagicMock()

    def bracket_access(_self: object, key: str) -> str | None:
        mapping = {
            "part1item2": mda,
        }
        return mapping.get(key)

    tenq.__getitem__ = bracket_access
    return tenq


def _make_mock_company(filings_list: list[MagicMock]) -> MagicMock:
    """Create a mock Company object that returns filings."""
    company = MagicMock()
    filings_collection = MagicMock()

    def latest_func(count: int) -> list[MagicMock] | MagicMock | None:
        items = filings_list[:count]
        if not items:
            return None
        if len(items) == 1:
            return items[0]
        # Return iterable for count > 1
        result = MagicMock()
        result.__iter__ = MagicMock(return_value=iter(items))
        result.__len__ = MagicMock(return_value=len(items))
        return result

    filings_collection.latest = latest_func
    company.get_filings.return_value = filings_collection
    return company


# ---------------------------------------------------------------------------
# Test 1: FilingClient.__init__ calls edgar.set_identity
# ---------------------------------------------------------------------------


class TestFilingClientInit:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_init_calls_set_identity(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        identity = "TestCo test@example.com"
        client = FilingClient(edgar_identity=identity)

        mock_edgar.set_identity.assert_called_once_with(identity)
        assert client is not None


# ---------------------------------------------------------------------------
# Test 2: get_latest_filings("10-K", cik, count=5) returns list[FilingData]
# ---------------------------------------------------------------------------


class TestGetLatestFilings10K:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_returns_filing_data_for_10k(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        # Build mock filing + TenK
        mock_filing = _make_mock_filing(form="10-K")
        tenk = _make_mock_tenk()
        mock_filing.obj.return_value = tenk

        mock_company = _make_mock_company([mock_filing])
        mock_edgar.Company.return_value = mock_company

        client = FilingClient(edgar_identity="Test test@test.com")
        results = client.get_latest_filings("10-K", "123456", count=5)

        assert isinstance(results, list)
        assert len(results) >= 1
        assert isinstance(results[0], FilingData)
        assert results[0].form_type == "10-K"
        assert results[0].accession_no == "0001234567-25-000001"


# ---------------------------------------------------------------------------
# Test 3: get_latest_filings("10-Q", cik, count=8) returns quarterly filings
# ---------------------------------------------------------------------------


class TestGetLatestFilings10Q:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_returns_filing_data_for_10q(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        mock_filing = _make_mock_filing(form="10-Q")
        tenq = _make_mock_tenq()
        mock_filing.obj.return_value = tenq

        mock_company = _make_mock_company([mock_filing])
        mock_edgar.Company.return_value = mock_company

        client = FilingClient(edgar_identity="Test test@test.com")
        results = client.get_latest_filings("10-Q", "123456", count=8)

        assert isinstance(results, list)
        assert len(results) >= 1
        assert results[0].form_type == "10-Q"


# ---------------------------------------------------------------------------
# Test 4: get_latest_filings("8-K", cik, count=10) returns current reports
# ---------------------------------------------------------------------------


class TestGetLatestFilings8K:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_returns_filing_data_for_8k(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        mock_filing = _make_mock_filing(form="8-K")
        mock_filing.text.return_value = "This is an 8-K current report." * 50

        mock_company = _make_mock_company([mock_filing])
        mock_edgar.Company.return_value = mock_company

        client = FilingClient(edgar_identity="Test test@test.com")
        results = client.get_latest_filings("8-K", "123456", count=10)

        assert isinstance(results, list)
        assert len(results) >= 1
        assert results[0].form_type == "8-K"
        # 8-K should have full_text_excerpt populated
        assert results[0].sections.full_text_excerpt is not None


# ---------------------------------------------------------------------------
# Test 5: Section extraction populates business, risk_factors, mda from TenK
# ---------------------------------------------------------------------------


class TestSectionExtraction:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_populates_sections_from_10k(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        business_text = "We are a leading AI company." * 50
        risk_text = "Our business faces significant risks." * 50
        mda_text = "Revenue grew 15% year over year." * 50

        mock_filing = _make_mock_filing(form="10-K")
        tenk = _make_mock_tenk(
            business=business_text,
            risk_factors=risk_text,
            mda=mda_text,
        )
        mock_filing.obj.return_value = tenk

        mock_company = _make_mock_company([mock_filing])
        mock_edgar.Company.return_value = mock_company

        client = FilingClient(edgar_identity="Test test@test.com")
        results = client.get_latest_filings("10-K", "123456", count=1)

        assert len(results) == 1
        sections = results[0].sections
        assert sections.business is not None
        assert "AI company" in sections.business
        assert sections.risk_factors is not None
        assert "risks" in sections.risk_factors
        assert sections.mda is not None
        assert "Revenue" in sections.mda


# ---------------------------------------------------------------------------
# Test 6: Short section text (< 500 chars) triggers warning and fallback
# ---------------------------------------------------------------------------


class TestShortSectionFallback:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_short_section_triggers_full_text_fallback(
        self, mock_edgar: MagicMock
    ) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        # business is suspiciously short (< 500 chars)
        short_business = "Item 1. Business"
        long_risk = "Risk factor content here." * 50
        long_mda = "Management discussion." * 50

        mock_filing = _make_mock_filing(form="10-K")
        tenk = _make_mock_tenk(
            business=short_business,
            risk_factors=long_risk,
            mda=long_mda,
        )
        mock_filing.obj.return_value = tenk
        # Provide full text for fallback
        mock_filing.text.return_value = "Full filing text content here." * 100

        mock_company = _make_mock_company([mock_filing])
        mock_edgar.Company.return_value = mock_company

        client = FilingClient(edgar_identity="Test test@test.com")
        results = client.get_latest_filings("10-K", "123456", count=1)

        assert len(results) == 1
        # full_text_excerpt should be populated as fallback
        assert results[0].sections.full_text_excerpt is not None


# ---------------------------------------------------------------------------
# Test 7: Section text is truncated at section_max_chars limit
# ---------------------------------------------------------------------------


class TestSectionTruncation:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_truncates_at_max_chars(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        # Use a small max to test truncation
        settings = FilingCollectionSettings(section_max_chars=1000)
        very_long_text = "A" * 5000

        mock_filing = _make_mock_filing(form="10-K")
        tenk = _make_mock_tenk(
            business=very_long_text,
            risk_factors=very_long_text,
            mda=very_long_text,
        )
        mock_filing.obj.return_value = tenk

        mock_company = _make_mock_company([mock_filing])
        mock_edgar.Company.return_value = mock_company

        client = FilingClient(
            edgar_identity="Test test@test.com", settings=settings
        )
        results = client.get_latest_filings("10-K", "123456", count=1)

        assert len(results) == 1
        sections = results[0].sections
        assert sections.business is not None
        assert len(sections.business) <= 1000
        assert sections.risk_factors is not None
        assert len(sections.risk_factors) <= 1000
        assert sections.mda is not None
        assert len(sections.mda) <= 1000


# ---------------------------------------------------------------------------
# Test 8: CIK not found returns empty list (no exception)
# ---------------------------------------------------------------------------


class TestCIKNotFound:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_cik_not_found_returns_empty(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        mock_edgar.Company.side_effect = Exception("Company not found")

        client = FilingClient(edgar_identity="Test test@test.com")
        results = client.get_latest_filings("10-K", "999999", count=5)

        assert results == []


# ---------------------------------------------------------------------------
# Test 9: edgartools exception is caught, logged, returns empty list
# ---------------------------------------------------------------------------


class TestEdgartoolsException:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_exception_caught_returns_empty(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        mock_company = MagicMock()
        mock_company.get_filings.side_effect = RuntimeError("EDGAR API down")
        mock_edgar.Company.return_value = mock_company

        client = FilingClient(edgar_identity="Test test@test.com")
        results = client.get_latest_filings("10-K", "123456", count=5)

        assert results == []


# ---------------------------------------------------------------------------
# Test 10: content_hash is SHA-256 of concatenated section text
# ---------------------------------------------------------------------------


class TestContentHash:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_content_hash_is_sha256(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        business = "Business section text." * 50
        risk = "Risk factors text." * 50
        mda = "MDA section text." * 50

        mock_filing = _make_mock_filing(form="10-K")
        tenk = _make_mock_tenk(business=business, risk_factors=risk, mda=mda)
        mock_filing.obj.return_value = tenk

        mock_company = _make_mock_company([mock_filing])
        mock_edgar.Company.return_value = mock_company

        client = FilingClient(edgar_identity="Test test@test.com")
        results = client.get_latest_filings("10-K", "123456", count=1)

        assert len(results) == 1
        result = results[0]
        assert result.content_hash is not None
        # Verify it is a valid SHA-256 hex string (64 chars)
        assert len(result.content_hash) == 64
        assert all(c in "0123456789abcdef" for c in result.content_hash)

        # Verify hash matches concatenated sections
        concat = ""
        for section_val in [
            result.sections.business,
            result.sections.risk_factors,
            result.sections.mda,
            result.sections.financial_statements,
            result.sections.full_text_excerpt,
        ]:
            if section_val is not None:
                concat += section_val
        expected_hash = hashlib.sha256(concat.encode()).hexdigest()
        assert result.content_hash == expected_hash


# ---------------------------------------------------------------------------
# Test 11: period_of_report and filing_date are correctly extracted
# ---------------------------------------------------------------------------


class TestDateExtraction:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_dates_extracted_correctly(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        mock_filing = _make_mock_filing(
            form="10-K",
            filing_date="2025-03-15",
            report_date="2024-12-31",
        )
        tenk = _make_mock_tenk()
        mock_filing.obj.return_value = tenk

        mock_company = _make_mock_company([mock_filing])
        mock_edgar.Company.return_value = mock_company

        client = FilingClient(edgar_identity="Test test@test.com")
        results = client.get_latest_filings("10-K", "123456", count=1)

        assert len(results) == 1
        assert results[0].filing_date == date(2025, 3, 15)
        assert results[0].period_of_report == date(2024, 12, 31)
        assert results[0].entity_name == "TestCorp Inc"


# ---------------------------------------------------------------------------
# Context manager tests
# ---------------------------------------------------------------------------


class TestContextManager:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_context_manager_protocol(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        with FilingClient(edgar_identity="Test test@test.com") as client:
            assert client is not None


# ---------------------------------------------------------------------------
# Default count tests
# ---------------------------------------------------------------------------


class TestDefaultCounts:
    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_default_count_for_10k(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        settings = FilingCollectionSettings(
            max_annual_filings=3,
            max_quarterly_filings=4,
            max_8k_filings=5,
        )

        filings_collection = MagicMock()
        filings_collection.latest.return_value = None
        mock_company = MagicMock()
        mock_company.get_filings.return_value = filings_collection
        mock_edgar.Company.return_value = mock_company

        client = FilingClient(
            edgar_identity="Test test@test.com", settings=settings
        )
        client.get_latest_filings("10-K", "123456")

        # Should have called latest with default max_annual_filings=3
        filings_collection.latest.assert_called_once_with(3)

    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_default_count_for_10q(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        settings = FilingCollectionSettings(
            max_annual_filings=3,
            max_quarterly_filings=4,
            max_8k_filings=5,
        )

        filings_collection = MagicMock()
        filings_collection.latest.return_value = None
        mock_company = MagicMock()
        mock_company.get_filings.return_value = filings_collection
        mock_edgar.Company.return_value = mock_company

        client = FilingClient(
            edgar_identity="Test test@test.com", settings=settings
        )
        client.get_latest_filings("10-Q", "123456")

        filings_collection.latest.assert_called_once_with(4)

    @patch("ai_washer.ingestion.filing_client.edgar")
    def test_default_count_for_8k(self, mock_edgar: MagicMock) -> None:
        from ai_washer.ingestion.filing_client import FilingClient

        settings = FilingCollectionSettings(
            max_annual_filings=3,
            max_quarterly_filings=4,
            max_8k_filings=5,
        )

        filings_collection = MagicMock()
        filings_collection.latest.return_value = None
        mock_company = MagicMock()
        mock_company.get_filings.return_value = filings_collection
        mock_edgar.Company.return_value = mock_company

        client = FilingClient(
            edgar_identity="Test test@test.com", settings=settings
        )
        client.get_latest_filings("8-K", "123456")

        filings_collection.latest.assert_called_once_with(5)
