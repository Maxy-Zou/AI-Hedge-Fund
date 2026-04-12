"""Tests for EDGAR filing client and filing retrieval tools.

Tests EdgarClient section extraction, filing_date filtering, identity setup,
and the get_filing_sections tool function with @enforce_as_of_date decorator.
All edgartools calls are mocked -- no real SEC API calls.
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings

# ---------------------------------------------------------------------------
# Mock filing class (supports bracket notation via __getitem__)
# ---------------------------------------------------------------------------


class MockFiling:
    """Mock edgartools filing with bracket-notation section access."""

    def __init__(
        self,
        *,
        accession_no: str,
        filing_date: date,
        form_type: str = "10-K",
        company: str = "Apple Inc.",
        sections: dict[str, str | None] | None = None,
        full_text: str = "Full filing text for fallback testing " * 100,
    ) -> None:
        self.accession_no = accession_no
        self.filing_date = filing_date
        self.form_type = form_type
        self.company = company
        self._sections = sections or {}
        self._full_text = full_text

    def __getitem__(self, key: str) -> str | None:
        return self._sections.get(key)

    def text(self) -> str:
        return self._full_text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _mock_settings(monkeypatch: pytest.MonkeyPatch) -> AppSettings:
    """AppSettings with edgar_identity configured."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return AppSettings(
        _env_file=None,
        edgar_identity="TestCo test@example.com",
    )


def _make_filing(
    *,
    accession_no: str,
    filing_date: date,
    form_type: str = "10-K",
    company_name: str = "Apple Inc.",
    sections: dict[str, str | None] | None = None,
    full_text: str = "Full filing text for fallback testing " * 100,
) -> MockFiling:
    """Create a mock edgartools filing object."""
    return MockFiling(
        accession_no=accession_no,
        filing_date=filing_date,
        form_type=form_type,
        company=company_name,
        sections=sections,
        full_text=full_text,
    )


def _make_filings_list(filings: list[Any]) -> SimpleNamespace:
    """Wrap a list of filings in a namespace that mimics edgartools Filings."""
    obj = SimpleNamespace()
    obj.head = lambda n: filings[:n]
    return obj


# ---------------------------------------------------------------------------
# EdgarClient tests
# ---------------------------------------------------------------------------


class TestEdgarClient:
    """Tests for the EdgarClient wrapper around edgartools."""

    def test_sets_identity_from_config(self) -> None:
        """EdgarClient sets edgar identity on init."""
        with patch("ai_hedge_fund.data.clients.edgar_client.edgar") as mock_edgar:
            from ai_hedge_fund.data.clients.edgar_client import EdgarClient

            client = EdgarClient(edgar_identity="TestCo test@example.com")
            mock_edgar.set_identity.assert_called_once_with("TestCo test@example.com")
            assert client._identity == "TestCo test@example.com"

    def test_get_filings_returns_metadata_sorted_by_date_desc(self) -> None:
        """get_filings returns filing metadata sorted by filing_date descending."""
        filings = [
            _make_filing(
                accession_no="0001-24-000001",
                filing_date=date(2024, 2, 1),
                form_type="10-K",
            ),
            _make_filing(
                accession_no="0001-23-000001",
                filing_date=date(2023, 2, 1),
                form_type="10-K",
            ),
        ]

        with patch("ai_hedge_fund.data.clients.edgar_client.edgar") as mock_edgar:
            mock_company = MagicMock()
            mock_company.get_filings.return_value = _make_filings_list(filings)
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.clients.edgar_client import EdgarClient

            client = EdgarClient(edgar_identity="TestCo test@example.com")
            result = client.get_filings("AAPL", form_type="10-K", max_filings=5)

        assert len(result) == 2
        assert result[0]["accession_no"] == "0001-24-000001"
        assert result[0]["filing_date"] == date(2024, 2, 1)
        assert result[1]["filing_date"] == date(2023, 2, 1)
        # Verify descending order
        assert result[0]["filing_date"] >= result[1]["filing_date"]

    def test_get_filing_sections_extracts_10k_sections(self) -> None:
        """get_filing_sections extracts business, risk_factors, mda from 10-K."""
        filing = _make_filing(
            accession_no="0001-24-000001",
            filing_date=date(2024, 2, 1),
            form_type="10-K",
            sections={
                "Item 1": "Business description text",
                "Item 1A": "Risk factors text",
                "Item 7": "MD&A analysis text",
            },
        )

        with patch("ai_hedge_fund.data.clients.edgar_client.edgar") as mock_edgar:
            mock_company = MagicMock()
            mock_company.get_filings.return_value = _make_filings_list([filing])
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.clients.edgar_client import EdgarClient

            client = EdgarClient(edgar_identity="TestCo test@example.com")
            result = client.get_filing_sections(
                "AAPL", form_type="10-K", filing_date_cutoff=date(2024, 12, 31)
            )

        assert len(result) == 1
        sections = result[0]["sections"]
        assert sections["business"] == "Business description text"
        assert sections["risk_factors"] == "Risk factors text"
        assert sections["mda"] == "MD&A analysis text"

    def test_get_filing_sections_extracts_10q_sections(self) -> None:
        """get_filing_sections extracts mda from 10-Q (part1item2)."""
        filing = _make_filing(
            accession_no="0001-24-Q1",
            filing_date=date(2024, 5, 1),
            form_type="10-Q",
            sections={"part1item2": "Q1 MD&A text"},
        )

        with patch("ai_hedge_fund.data.clients.edgar_client.edgar") as mock_edgar:
            mock_company = MagicMock()
            mock_company.get_filings.return_value = _make_filings_list([filing])
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.clients.edgar_client import EdgarClient

            client = EdgarClient(edgar_identity="TestCo test@example.com")
            result = client.get_filing_sections(
                "AAPL", form_type="10-Q", filing_date_cutoff=date(2024, 12, 31)
            )

        assert len(result) == 1
        assert result[0]["sections"]["mda"] == "Q1 MD&A text"

    def test_get_filing_sections_filters_by_cutoff(self) -> None:
        """Filings with filing_date > filing_date_cutoff are excluded."""
        old_filing = _make_filing(
            accession_no="0001-23-000001",
            filing_date=date(2023, 2, 1),
            form_type="10-K",
            sections={"Item 1": "Old business"},
        )
        new_filing = _make_filing(
            accession_no="0001-24-000001",
            filing_date=date(2024, 2, 1),
            form_type="10-K",
            sections={"Item 1": "New business"},
        )

        with patch("ai_hedge_fund.data.clients.edgar_client.edgar") as mock_edgar:
            mock_company = MagicMock()
            mock_company.get_filings.return_value = _make_filings_list([new_filing, old_filing])
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.clients.edgar_client import EdgarClient

            client = EdgarClient(edgar_identity="TestCo test@example.com")
            result = client.get_filing_sections(
                "AAPL",
                form_type="10-K",
                filing_date_cutoff=date(2023, 12, 31),  # Before new_filing
            )

        assert len(result) == 1
        assert result[0]["accession_no"] == "0001-23-000001"

    def test_fallback_to_full_text_when_sections_none(self) -> None:
        """When all sections return None, falls back to truncated full text."""
        full_text = "A" * 60000  # Longer than 50000 char limit
        filing = _make_filing(
            accession_no="0001-24-000001",
            filing_date=date(2024, 2, 1),
            form_type="10-K",
            sections={},  # All sections will return None
            full_text=full_text,
        )

        with patch("ai_hedge_fund.data.clients.edgar_client.edgar") as mock_edgar:
            mock_company = MagicMock()
            mock_company.get_filings.return_value = _make_filings_list([filing])
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.clients.edgar_client import EdgarClient

            client = EdgarClient(edgar_identity="TestCo test@example.com")
            result = client.get_filing_sections(
                "AAPL", form_type="10-K", filing_date_cutoff=date(2024, 12, 31)
            )

        assert len(result) == 1
        assert result[0]["sections"]["full_text"] is not None
        assert len(result[0]["sections"]["full_text"]) <= 50000

    def test_safe_section_returns_none_on_missing(self) -> None:
        """_safe_section returns None when section key is not found."""
        from ai_hedge_fund.data.clients.edgar_client import EdgarClient

        with patch("ai_hedge_fund.data.clients.edgar_client.edgar"):
            client = EdgarClient(edgar_identity="TestCo test@example.com")

        filing = _make_filing(
            accession_no="0001-24-000001",
            filing_date=date(2024, 2, 1),
            sections={"Item 1": "Business"},
        )
        assert client._safe_section(filing, "Item 1") == "Business"
        assert client._safe_section(filing, "Item 99") is None


# ---------------------------------------------------------------------------
# get_filing_sections tool function tests
# ---------------------------------------------------------------------------


class TestGetFilingSections:
    """Tests for the get_filing_sections tool function."""

    def test_raises_on_none_as_of_date(self) -> None:
        """get_filing_sections raises ValueError when as_of_date is None."""
        from ai_hedge_fund.data.tools.filing_tools import get_filing_sections

        with pytest.raises(ValueError, match="as_of_date is required"):
            get_filing_sections("AAPL", as_of_date=None)  # type: ignore[arg-type]

    def test_returns_filing_section_results(self, _mock_settings: AppSettings) -> None:
        """Returns list of dicts with accession_no, filing_date, form_type, sections."""
        filing = _make_filing(
            accession_no="0001-24-000001",
            filing_date=date(2024, 2, 1),
            form_type="10-K",
            sections={
                "Item 1": "Business",
                "Item 1A": "Risks",
                "Item 7": "MDA",
            },
        )

        with (
            patch("ai_hedge_fund.data.clients.edgar_client.edgar") as mock_edgar,
            patch(
                "ai_hedge_fund.data.tools.filing_tools.get_settings",
                return_value=_mock_settings,
            ),
        ):
            mock_company = MagicMock()
            mock_company.get_filings.return_value = _make_filings_list([filing])
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.tools.filing_tools import get_filing_sections

            result = get_filing_sections(
                "AAPL",
                as_of_date=date(2024, 12, 31),
                form_type="10-K",
            )

        assert len(result) == 1
        r = result[0]
        assert r["accession_no"] == "0001-24-000001"
        assert r["filing_date"] == date(2024, 2, 1)
        assert r["form_type"] == "10-K"
        assert "business" in r["sections"]

    def test_excludes_future_filings(self, _mock_settings: AppSettings) -> None:
        """Filings filed after as_of_date are excluded from results."""
        old = _make_filing(
            accession_no="OLD-001",
            filing_date=date(2023, 2, 1),
            sections={"Item 1": "Old"},
        )
        new = _make_filing(
            accession_no="NEW-001",
            filing_date=date(2025, 2, 1),
            sections={"Item 1": "New"},
        )

        with (
            patch("ai_hedge_fund.data.clients.edgar_client.edgar") as mock_edgar,
            patch(
                "ai_hedge_fund.data.tools.filing_tools.get_settings",
                return_value=_mock_settings,
            ),
        ):
            mock_company = MagicMock()
            mock_company.get_filings.return_value = _make_filings_list([new, old])
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.tools.filing_tools import get_filing_sections

            result = get_filing_sections(
                "AAPL",
                as_of_date=date(2024, 6, 1),
                form_type="10-K",
            )

        assert len(result) == 1
        assert result[0]["accession_no"] == "OLD-001"

    def test_raises_on_empty_edgar_identity(self) -> None:
        """Raises ValueError if edgar_identity is not configured."""
        empty_settings = AppSettings(
            _env_file=None,
            edgar_identity="",
        )

        with patch(
            "ai_hedge_fund.data.tools.filing_tools.get_settings",
            return_value=empty_settings,
        ):
            from ai_hedge_fund.data.tools.filing_tools import get_filing_sections

            with pytest.raises(ValueError, match="edgar_identity"):
                get_filing_sections(
                    "AAPL",
                    as_of_date=date(2024, 6, 1),
                )

    def test_caches_to_sec_filing_model(
        self, _mock_settings: AppSettings, db_session: Session
    ) -> None:
        """Results are cached to SecFiling model when db_session is provided."""
        filing = _make_filing(
            accession_no="0001-24-CACHE",
            filing_date=date(2024, 2, 1),
            form_type="10-K",
            sections={"Item 1": "Business text for caching"},
        )

        with (
            patch("ai_hedge_fund.data.clients.edgar_client.edgar") as mock_edgar,
            patch(
                "ai_hedge_fund.data.tools.filing_tools.get_settings",
                return_value=_mock_settings,
            ),
        ):
            mock_company = MagicMock()
            mock_company.get_filings.return_value = _make_filings_list([filing])
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.tools.filing_tools import get_filing_sections

            get_filing_sections(
                "AAPL",
                as_of_date=date(2024, 12, 31),
                form_type="10-K",
                db_session=db_session,
            )

        from ai_hedge_fund.db.models import SecFiling

        rows = db_session.query(SecFiling).all()
        assert len(rows) == 1
        assert rows[0].ticker == "AAPL"
        assert rows[0].accession_no == "0001-24-CACHE"
        stored_sections = json.loads(rows[0].sections_json)
        assert "business" in stored_sections
