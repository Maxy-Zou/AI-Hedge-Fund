"""Unit tests for EDGAR company facts client.

Tests XBRL EntityPublicFloat extraction, CIK normalization,
CIK-ticker mapping, User-Agent compliance, and retry logic.
"""

from __future__ import annotations

import httpx
import pytest

from ai_washer.ingestion.edgar_client import (
    COMPANY_TICKERS_URL,
    XBRL_FACTS_URL,
    EdgarFactsClient,
    pad_cik,
    strip_cik,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EDGAR_IDENTITY = "TestCorp test@example.com"


def _make_company_facts_response(
    public_float_usd: float | None = None,
    end_date: str = "2025-06-30",
    form: str = "10-K",
    filed: str = "2025-09-15",
) -> dict:
    """Build the nested XBRL company facts JSON structure."""
    if public_float_usd is None:
        return {"facts": {"dei": {}}}

    return {
        "facts": {
            "dei": {
                "EntityPublicFloat": {
                    "units": {
                        "USD": [
                            {
                                "end": end_date,
                                "val": public_float_usd,
                                "form": form,
                                "filed": filed,
                            }
                        ]
                    }
                }
            }
        }
    }


def _make_multi_filing_facts(entries: list[dict]) -> dict:
    """Build company facts with multiple EntityPublicFloat entries."""
    return {
        "facts": {
            "dei": {
                "EntityPublicFloat": {
                    "units": {
                        "USD": entries,
                    }
                }
            }
        }
    }


def _make_company_tickers_json() -> dict:
    """Build a sample company_tickers.json response."""
    return {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
        "2": {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
    }


# ---------------------------------------------------------------------------
# Tests: CIK normalization
# ---------------------------------------------------------------------------


class TestCIKNormalization:
    """Tests for CIK padding and stripping functions."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("320193", "0000320193"),
            ("0000320193", "0000320193"),
            ("1", "0000000001"),
            ("0001652044", "0001652044"),
            ("1652044", "0001652044"),
        ],
    )
    def test_pad_cik(self, raw: str, expected: str) -> None:
        """pad_cik pads to 10 digits with leading zeros."""
        assert pad_cik(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("0000320193", "320193"),
            ("320193", "320193"),
            ("0000000001", "1"),
            ("0", "0"),
            ("0000000000", "0"),
        ],
    )
    def test_strip_cik(self, raw: str, expected: str) -> None:
        """strip_cik removes leading zeros from CIK."""
        assert strip_cik(raw) == expected


# ---------------------------------------------------------------------------
# Tests: EntityPublicFloat
# ---------------------------------------------------------------------------


class TestEntityPublicFloat:
    """Tests for get_entity_public_float."""

    def test_entity_public_float_returns_cents(self, httpx_mock):
        """get_entity_public_float returns value in cents from XBRL data."""
        padded = "0000320193"
        url = XBRL_FACTS_URL.format(cik=padded)
        httpx_mock.add_response(
            url=url,
            json=_make_company_facts_response(
                public_float_usd=5_000_000_000.0,
                end_date="2025-06-30",
            ),
        )

        with EdgarFactsClient(edgar_identity=EDGAR_IDENTITY) as client:
            result = client.get_entity_public_float("320193")

        assert result == 500_000_000_000  # $5B in cents

    def test_entity_public_float_selects_most_recent(self, httpx_mock):
        """get_entity_public_float picks the most recent entry by end date."""
        padded = "0000320193"
        url = XBRL_FACTS_URL.format(cik=padded)
        entries = [
            {"end": "2024-06-30", "val": 4_000_000_000.0, "form": "10-K", "filed": "2024-09-15"},
            {"end": "2025-06-30", "val": 5_000_000_000.0, "form": "10-K", "filed": "2025-09-15"},
            {"end": "2023-06-30", "val": 3_000_000_000.0, "form": "10-K", "filed": "2023-09-15"},
        ]
        httpx_mock.add_response(
            url=url,
            json=_make_multi_filing_facts(entries),
        )

        with EdgarFactsClient(edgar_identity=EDGAR_IDENTITY) as client:
            result = client.get_entity_public_float("320193")

        # Should pick the 2025 entry: $5B -> 500B cents
        assert result == 500_000_000_000

    def test_entity_public_float_pads_cik(self, httpx_mock):
        """get_entity_public_float pads CIK to 10 digits for URL."""
        padded = "0000320193"
        url = XBRL_FACTS_URL.format(cik=padded)
        httpx_mock.add_response(
            url=url,
            json=_make_company_facts_response(public_float_usd=2_000_000_000.0),
        )

        with EdgarFactsClient(edgar_identity=EDGAR_IDENTITY) as client:
            result = client.get_entity_public_float("320193")

        assert result is not None
        # Verify the request was made with padded CIK
        request = httpx_mock.get_requests()[0]
        assert padded in str(request.url)

    def test_missing_entity_public_float_tag(self, httpx_mock):
        """get_entity_public_float returns None when tag is missing."""
        padded = "0000320193"
        url = XBRL_FACTS_URL.format(cik=padded)
        httpx_mock.add_response(
            url=url,
            json=_make_company_facts_response(public_float_usd=None),
        )

        with EdgarFactsClient(edgar_identity=EDGAR_IDENTITY) as client:
            result = client.get_entity_public_float("320193")

        assert result is None

    def test_not_found_returns_none(self, httpx_mock):
        """get_entity_public_float returns None when API returns 404."""
        padded = "0000999999"
        url = XBRL_FACTS_URL.format(cik=padded)
        httpx_mock.add_response(url=url, status_code=404)

        with EdgarFactsClient(edgar_identity=EDGAR_IDENTITY) as client:
            result = client.get_entity_public_float("999999")

        assert result is None


# ---------------------------------------------------------------------------
# Tests: CIK-ticker mapping
# ---------------------------------------------------------------------------


class TestCIKTickerMapping:
    """Tests for get_cik_ticker_mapping."""

    def test_cik_ticker_mapping(self, httpx_mock):
        """get_cik_ticker_mapping returns dict of CIK -> (ticker, name)."""
        httpx_mock.add_response(
            url=COMPANY_TICKERS_URL,
            json=_make_company_tickers_json(),
        )

        with EdgarFactsClient(edgar_identity=EDGAR_IDENTITY) as client:
            mapping = client.get_cik_ticker_mapping()

        assert mapping["320193"] == ("AAPL", "Apple Inc.")
        assert mapping["789019"] == ("MSFT", "MICROSOFT CORP")
        assert mapping["1652044"] == ("GOOG", "Alphabet Inc.")
        assert len(mapping) == 3


# ---------------------------------------------------------------------------
# Tests: User-Agent compliance
# ---------------------------------------------------------------------------


class TestUserAgent:
    """Tests for SEC-compliant User-Agent header."""

    def test_user_agent_on_facts_request(self, httpx_mock):
        """User-Agent header included on XBRL facts request."""
        padded = "0000320193"
        url = XBRL_FACTS_URL.format(cik=padded)
        httpx_mock.add_response(
            url=url,
            json=_make_company_facts_response(public_float_usd=1_000_000_000.0),
        )

        with EdgarFactsClient(edgar_identity=EDGAR_IDENTITY) as client:
            client.get_entity_public_float("320193")

        request = httpx_mock.get_requests()[0]
        assert request.headers["user-agent"] == EDGAR_IDENTITY

    def test_user_agent_on_tickers_request(self, httpx_mock):
        """User-Agent header included on company tickers request."""
        httpx_mock.add_response(
            url=COMPANY_TICKERS_URL,
            json=_make_company_tickers_json(),
        )

        with EdgarFactsClient(edgar_identity=EDGAR_IDENTITY) as client:
            client.get_cik_ticker_mapping()

        request = httpx_mock.get_requests()[0]
        assert request.headers["user-agent"] == EDGAR_IDENTITY


# ---------------------------------------------------------------------------
# Tests: Retry logic
# ---------------------------------------------------------------------------


class TestRetry:
    """Tests for tenacity retry on transient errors."""

    def test_retries_on_429(self, httpx_mock):
        """Client retries on 429 Too Many Requests."""
        padded = "0000320193"
        url = XBRL_FACTS_URL.format(cik=padded)
        httpx_mock.add_response(url=url, status_code=429)
        httpx_mock.add_response(
            url=url,
            json=_make_company_facts_response(public_float_usd=3_000_000_000.0),
        )

        with EdgarFactsClient(edgar_identity=EDGAR_IDENTITY) as client:
            result = client.get_entity_public_float("320193")

        assert result == 300_000_000_000
        assert len(httpx_mock.get_requests()) == 2

    def test_retries_on_503(self, httpx_mock):
        """Client retries on 503 Service Unavailable."""
        padded = "0000320193"
        url = XBRL_FACTS_URL.format(cik=padded)
        httpx_mock.add_response(url=url, status_code=503)
        httpx_mock.add_response(
            url=url,
            json=_make_company_facts_response(public_float_usd=1_000_000_000.0),
        )

        with EdgarFactsClient(edgar_identity=EDGAR_IDENTITY) as client:
            result = client.get_entity_public_float("320193")

        assert result == 100_000_000_000
        assert len(httpx_mock.get_requests()) == 2
