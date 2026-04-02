"""Unit tests for XBRL financial fact extraction.

Tests tag fallback logic, deduplication by fiscal period,
dollar-to-cents conversion, form filtering, and the XBRLExtractor
class that fetches from the EDGAR companyfacts API.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import httpx
import pytest

from ai_washer.ingestion.edgar_client import XBRL_FACTS_URL
from ai_washer.ingestion.types import XBRLFactRecord
from ai_washer.ingestion.xbrl_extractor import (
    XBRLExtractor,
    deduplicate_by_period,
    extract_all_facts,
    extract_facts_for_concept,
)


# ---------------------------------------------------------------------------
# Fixtures: XBRL company facts JSON structures
# ---------------------------------------------------------------------------

EDGAR_IDENTITY = "TestCorp test@example.com"


def _make_us_gaap_facts(tag: str, usd_entries: list[dict]) -> dict:
    """Build companyfacts JSON with a single us-gaap tag."""
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                tag: {
                    "label": tag,
                    "units": {
                        "USD": usd_entries,
                    },
                },
            },
        },
    }


def _make_multi_tag_facts(tags: dict[str, list[dict]]) -> dict:
    """Build companyfacts JSON with multiple us-gaap tags."""
    us_gaap = {}
    for tag, entries in tags.items():
        us_gaap[tag] = {
            "label": tag,
            "units": {
                "USD": entries,
            },
        }
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": us_gaap,
        },
    }


def _make_entry(
    val: float,
    end: str = "2024-12-31",
    filed: str = "2025-02-15",
    form: str = "10-K",
    fy: int = 2024,
    fp: str = "FY",
    accn: str = "0000320193-25-000001",
) -> dict:
    """Build a single XBRL fact entry."""
    return {
        "end": end,
        "val": val,
        "accn": accn,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }


# ---------------------------------------------------------------------------
# Tests: extract_facts_for_concept
# ---------------------------------------------------------------------------


class TestExtractFactsForConcept:
    """Tests for extracting XBRL facts with tag fallback logic."""

    def test_extracts_with_primary_tag(self) -> None:
        """Test 1: Uses first matching tag 'ResearchAndDevelopmentExpense'."""
        facts_json = _make_us_gaap_facts(
            "ResearchAndDevelopmentExpense",
            [_make_entry(val=31_370_000_000.0)],
        )

        result = extract_facts_for_concept("rd_expense", facts_json)

        assert len(result) == 1
        assert result[0].tag == "ResearchAndDevelopmentExpense"
        assert result[0].concept == "rd_expense"

    def test_falls_back_to_secondary_tag(self) -> None:
        """Test 2: Falls back to second tag when first is not present."""
        fallback_tag = (
            "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"
        )
        facts_json = _make_us_gaap_facts(
            fallback_tag,
            [_make_entry(val=5_000_000_000.0)],
        )

        result = extract_facts_for_concept("rd_expense", facts_json)

        assert len(result) == 1
        assert result[0].tag == fallback_tag

    def test_returns_empty_when_no_tags_match(self) -> None:
        """Test 3: Returns empty list when no known tags present."""
        facts_json = {
            "cik": 320193,
            "entityName": "Apple Inc.",
            "facts": {
                "us-gaap": {
                    "SomeUnrelatedTag": {
                        "units": {"USD": [_make_entry(val=100.0)]},
                    },
                },
            },
        }

        result = extract_facts_for_concept("rd_expense", facts_json)

        assert result == []

    def test_dollar_to_cents_conversion(self) -> None:
        """Test 4: Dollar value 31370000000 -> value_cents 3137000000000."""
        facts_json = _make_us_gaap_facts(
            "ResearchAndDevelopmentExpense",
            [_make_entry(val=31_370_000_000)],
        )

        result = extract_facts_for_concept("rd_expense", facts_json)

        assert result[0].value_cents == 3_137_000_000_000
        assert isinstance(result[0].value_cents, int)

    def test_form_filter_exact_match(self) -> None:
        """Test 6: Only '10-K' entries returned, not '10-K/A'."""
        facts_json = _make_us_gaap_facts(
            "ResearchAndDevelopmentExpense",
            [
                _make_entry(val=1_000_000.0, form="10-K", end="2024-12-31",
                            filed="2025-02-15", accn="0000320193-25-000001"),
                _make_entry(val=1_100_000.0, form="10-K/A", end="2024-12-31",
                            filed="2025-04-01", accn="0000320193-25-000002"),
                _make_entry(val=500_000.0, form="10-Q", end="2024-09-30",
                            filed="2024-11-15", accn="0000320193-24-000003"),
            ],
        )

        result = extract_facts_for_concept(
            "rd_expense", facts_json, form_filter="10-K",
        )

        forms = [r.form_type for r in result]
        assert all(f == "10-K" for f in forms)
        assert "10-K/A" not in forms
        assert "10-Q" not in forms

    def test_fiscal_period_parsing(self) -> None:
        """Test 11: Fiscal period FY vs Q1/Q2/Q3/Q4 correctly parsed."""
        facts_json = _make_us_gaap_facts(
            "Revenues",
            [
                _make_entry(val=100_000.0, fp="FY", end="2024-12-31",
                            fy=2024, accn="accn-fy"),
                _make_entry(val=25_000.0, fp="Q1", end="2024-03-31",
                            fy=2024, accn="accn-q1"),
                _make_entry(val=26_000.0, fp="Q2", end="2024-06-30",
                            fy=2024, accn="accn-q2"),
                _make_entry(val=27_000.0, fp="Q3", end="2024-09-30",
                            fy=2024, accn="accn-q3"),
                _make_entry(val=22_000.0, fp="Q4", end="2024-12-31",
                            fy=2024, accn="accn-q4"),
            ],
        )

        result = extract_facts_for_concept(
            "revenue", facts_json, form_filter=None,
        )

        fps = {r.fiscal_period for r in result}
        assert fps == {"FY", "Q1", "Q2", "Q3", "Q4"}

    def test_returns_xbrl_fact_records(self) -> None:
        """Extracted records are proper XBRLFactRecord instances."""
        facts_json = _make_us_gaap_facts(
            "ResearchAndDevelopmentExpense",
            [_make_entry(
                val=5_000_000_000.0,
                end="2024-12-31",
                filed="2025-02-15",
                fy=2024,
                fp="FY",
                accn="0000320193-25-000001",
            )],
        )

        result = extract_facts_for_concept("rd_expense", facts_json)

        assert len(result) == 1
        rec = result[0]
        assert isinstance(rec, XBRLFactRecord)
        assert rec.end_date == date(2024, 12, 31)
        assert rec.filed_date == date(2025, 2, 15)
        assert rec.fiscal_year == 2024
        assert rec.fiscal_period == "FY"
        assert rec.accession_no == "0000320193-25-000001"

    def test_no_form_filter(self) -> None:
        """When form_filter=None, all forms are included."""
        facts_json = _make_us_gaap_facts(
            "ResearchAndDevelopmentExpense",
            [
                _make_entry(val=1_000_000.0, form="10-K", accn="accn-1"),
                _make_entry(val=500_000.0, form="10-Q", end="2024-09-30",
                            accn="accn-2"),
            ],
        )

        result = extract_facts_for_concept(
            "rd_expense", facts_json, form_filter=None,
        )

        forms = {r.form_type for r in result}
        assert "10-K" in forms
        assert "10-Q" in forms

    def test_missing_us_gaap_section(self) -> None:
        """Returns empty when facts JSON has no us-gaap section."""
        facts_json = {"cik": 320193, "facts": {}}

        result = extract_facts_for_concept("rd_expense", facts_json)

        assert result == []


# ---------------------------------------------------------------------------
# Tests: deduplicate_by_period
# ---------------------------------------------------------------------------


class TestDeduplicateByPeriod:
    """Tests for deduplication of XBRL entries by fiscal period."""

    def test_keeps_latest_filed_date(self) -> None:
        """Test 5: Removes duplicates for same (end, fp), keeping latest filed."""
        entries = [
            _make_entry(val=1_000_000.0, end="2024-12-31", fp="FY",
                        filed="2025-02-15"),
            _make_entry(val=1_050_000.0, end="2024-12-31", fp="FY",
                        filed="2025-04-20"),
        ]

        result = deduplicate_by_period(entries)

        assert len(result) == 1
        assert result[0]["filed"] == "2025-04-20"
        assert result[0]["val"] == 1_050_000.0

    def test_keeps_different_periods(self) -> None:
        """Different (end, fp) pairs are all kept."""
        entries = [
            _make_entry(val=100.0, end="2024-12-31", fp="FY"),
            _make_entry(val=25.0, end="2024-03-31", fp="Q1"),
            _make_entry(val=26.0, end="2024-06-30", fp="Q2"),
        ]

        result = deduplicate_by_period(entries)

        assert len(result) == 3

    def test_empty_input(self) -> None:
        """Empty list returns empty list."""
        result = deduplicate_by_period([])

        assert result == []

    def test_single_entry(self) -> None:
        """Single entry is returned unchanged."""
        entries = [_make_entry(val=999.0)]

        result = deduplicate_by_period(entries)

        assert len(result) == 1
        assert result[0]["val"] == 999.0


# ---------------------------------------------------------------------------
# Tests: extract_all_facts
# ---------------------------------------------------------------------------


class TestExtractAllFacts:
    """Tests for extracting all concept facts from company data."""

    def test_returns_dict_with_all_concepts(self) -> None:
        """Test 7: Returns dict with keys rd_expense, capex, revenue."""
        facts_json = _make_multi_tag_facts({
            "ResearchAndDevelopmentExpense": [
                _make_entry(val=5_000_000.0, accn="accn-rd"),
            ],
            "PaymentsToAcquirePropertyPlantAndEquipment": [
                _make_entry(val=10_000_000.0, accn="accn-capex"),
            ],
            "Revenues": [
                _make_entry(val=50_000_000.0, accn="accn-rev"),
            ],
        })

        result = extract_all_facts(facts_json)

        assert set(result.keys()) == {"rd_expense", "capex", "revenue"}
        assert len(result["rd_expense"]) == 1
        assert len(result["capex"]) == 1
        assert len(result["revenue"]) == 1

    def test_empty_concepts_when_no_data(self) -> None:
        """Missing concepts result in empty lists."""
        facts_json = {"cik": 320193, "facts": {"us-gaap": {}}}

        result = extract_all_facts(facts_json)

        assert set(result.keys()) == {"rd_expense", "capex", "revenue"}
        assert all(len(v) == 0 for v in result.values())


# ---------------------------------------------------------------------------
# Tests: XBRLExtractor class
# ---------------------------------------------------------------------------


class TestXBRLExtractor:
    """Tests for the XBRLExtractor HTTP client class."""

    def test_get_company_facts_fetches_with_padded_cik(
        self, httpx_mock,
    ) -> None:
        """Test 8: get_company_facts fetches from XBRL_FACTS_URL with padded CIK."""
        padded = "0000320193"
        url = XBRL_FACTS_URL.format(cik=padded)
        facts = _make_us_gaap_facts(
            "ResearchAndDevelopmentExpense",
            [_make_entry(val=1_000_000.0)],
        )
        httpx_mock.add_response(url=url, json=facts)

        with XBRLExtractor(edgar_identity=EDGAR_IDENTITY) as extractor:
            result = extractor.get_company_facts("320193")

        assert result is not None
        assert result["cik"] == 320193
        request = httpx_mock.get_requests()[0]
        assert padded in str(request.url)

    def test_get_company_facts_returns_none_on_404(
        self, httpx_mock,
    ) -> None:
        """Test 9: get_company_facts returns None for 404 (CIK not found)."""
        padded = "0000999999"
        url = XBRL_FACTS_URL.format(cik=padded)
        httpx_mock.add_response(url=url, status_code=404)

        with XBRLExtractor(edgar_identity=EDGAR_IDENTITY) as extractor:
            result = extractor.get_company_facts("999999")

        assert result is None

    def test_extract_company_xbrl_returns_flat_list(
        self, httpx_mock,
    ) -> None:
        """Test 10: extract_company_xbrl returns flat list of XBRLFactRecord."""
        padded = "0000320193"
        url = XBRL_FACTS_URL.format(cik=padded)
        facts = _make_multi_tag_facts({
            "ResearchAndDevelopmentExpense": [
                _make_entry(val=5_000_000.0, end="2024-12-31",
                            accn="accn-rd"),
            ],
            "PaymentsToAcquirePropertyPlantAndEquipment": [
                _make_entry(val=10_000_000.0, end="2023-12-31",
                            accn="accn-capex"),
            ],
            "Revenues": [
                _make_entry(val=50_000_000.0, end="2022-12-31",
                            accn="accn-rev"),
            ],
        })
        httpx_mock.add_response(url=url, json=facts)

        with XBRLExtractor(edgar_identity=EDGAR_IDENTITY) as extractor:
            result = extractor.extract_company_xbrl("320193")

        assert isinstance(result, list)
        assert len(result) == 3
        assert all(isinstance(r, XBRLFactRecord) for r in result)
        # Sorted by end_date descending
        dates = [r.end_date for r in result]
        assert dates == sorted(dates, reverse=True)

    def test_extract_company_xbrl_returns_empty_on_404(
        self, httpx_mock,
    ) -> None:
        """extract_company_xbrl returns empty list when CIK not found."""
        padded = "0000999999"
        url = XBRL_FACTS_URL.format(cik=padded)
        httpx_mock.add_response(url=url, status_code=404)

        with XBRLExtractor(edgar_identity=EDGAR_IDENTITY) as extractor:
            result = extractor.extract_company_xbrl("999999")

        assert result == []

    def test_rate_limiting_delay(self, httpx_mock) -> None:
        """Test 12: Rate limiting delay between consecutive API calls."""
        padded_1 = "0000320193"
        padded_2 = "0000789019"
        url_1 = XBRL_FACTS_URL.format(cik=padded_1)
        url_2 = XBRL_FACTS_URL.format(cik=padded_2)
        facts = _make_us_gaap_facts(
            "ResearchAndDevelopmentExpense",
            [_make_entry(val=1_000_000.0)],
        )
        httpx_mock.add_response(url=url_1, json=facts)
        httpx_mock.add_response(url=url_2, json=facts)

        with (
            patch("ai_washer.ingestion.xbrl_extractor.time.sleep") as mock_sleep,
            XBRLExtractor(edgar_identity=EDGAR_IDENTITY) as extractor,
        ):
            extractor.get_company_facts("320193")
            extractor.get_company_facts("789019")

        mock_sleep.assert_called_once()

    def test_user_agent_header(self, httpx_mock) -> None:
        """User-Agent header is set to edgar_identity."""
        padded = "0000320193"
        url = XBRL_FACTS_URL.format(cik=padded)
        httpx_mock.add_response(url=url, json={"facts": {"us-gaap": {}}})

        with XBRLExtractor(edgar_identity=EDGAR_IDENTITY) as extractor:
            extractor.get_company_facts("320193")

        request = httpx_mock.get_requests()[0]
        assert request.headers["user-agent"] == EDGAR_IDENTITY

    def test_retries_on_429(self, httpx_mock) -> None:
        """Client retries on 429 Too Many Requests."""
        padded = "0000320193"
        url = XBRL_FACTS_URL.format(cik=padded)
        facts = _make_us_gaap_facts(
            "ResearchAndDevelopmentExpense",
            [_make_entry(val=1_000_000.0)],
        )
        httpx_mock.add_response(url=url, status_code=429)
        httpx_mock.add_response(url=url, json=facts)

        with XBRLExtractor(edgar_identity=EDGAR_IDENTITY) as extractor:
            result = extractor.get_company_facts("320193")

        assert result is not None
        assert len(httpx_mock.get_requests()) == 2

    def test_context_manager(self) -> None:
        """XBRLExtractor works as context manager."""
        with XBRLExtractor(edgar_identity=EDGAR_IDENTITY) as extractor:
            assert extractor is not None
