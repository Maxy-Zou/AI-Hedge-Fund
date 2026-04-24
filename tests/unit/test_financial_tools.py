"""Tests for XBRL financial extraction client and financial summary tools.

Tests XbrlClient tag fallback, cents conversion, filed_date filtering,
and the get_financial_summary tool function with @enforce_as_of_date decorator.
All edgartools calls are mocked -- no real SEC API calls.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings

# ---------------------------------------------------------------------------
# Mock CompanyFacts helpers
#
# The production XbrlClient consumes
# ``edgar.EntityFacts.to_dataframe(pit_mode=True)`` which has columns:
#
#   concept, label, value, numeric_value, unit, period_type,
#   period_start, period_end, fiscal_year, fiscal_period,
#   filing_date, form_type
#
# ``filing_date`` and ``period_end`` are native ``datetime.date``; ``concept``
# is taxonomy-prefixed (e.g. ``'us-gaap:Revenues'``). These helpers build a
# mock ``EntityFacts`` whose ``.to_dataframe(pit_mode=True)`` returns a
# DataFrame with that schema. Tests keep using the pre-migration call
# signatures (``_make_fact_row(val=..., fiscal_year=..., filed=...)``) —
# the fixture does the translation.
# ---------------------------------------------------------------------------


def _make_fact_row(
    *,
    val: float,
    unit: str = "USD",
    fiscal_period: str = "FY",
    fiscal_year: int = 2024,
    filed: str = "2024-02-01",
) -> dict[str, Any]:
    """Create a single fact row dict for ``_make_company_facts``.

    The returned dict is consumed internally by ``_make_company_facts``; it
    is not itself a DataFrame row. Dates are parsed to ``datetime.date`` at
    DataFrame-construction time to match the edgartools runtime shape.
    """
    return {
        "val": val,
        "units": unit,
        "fp": fiscal_period,
        "fy": fiscal_year,
        "filed": filed,
        "form": "10-K",
        "taxonomy": "us-gaap",
    }


def _make_company_facts(
    concept_data: dict[str, list[dict[str, Any]]],
    cik: str = "0000320193",
) -> SimpleNamespace:
    """Create a mock ``EntityFacts`` object.

    The returned object exposes ``.to_dataframe(pit_mode=True)`` which
    yields a DataFrame matching the schema produced by edgartools >= 5.28.

    Args:
        concept_data: Maps XBRL tag name (unprefixed, e.g. ``"Revenues"``)
            to a list of fact row dicts built by ``_make_fact_row``.
        cik: CIK number for the company.
    """
    import pandas as pd

    facts = SimpleNamespace()
    facts.cik = cik

    def _to_date(value: Any) -> date:
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    all_rows: list[dict[str, Any]] = []
    for tag_name, rows in concept_data.items():
        concept_key = f"us-gaap:{tag_name}"
        for row in rows:
            fiscal_year = int(row.get("fy", 2024))
            fiscal_period = str(row.get("fp", "FY"))
            filing_date = _to_date(row.get("filed", "2024-02-01"))

            # Default period_end derived from fiscal year for FY facts;
            # interim periods (Q1/Q2/Q3) get an approximate quarter-end.
            if "end" in row:
                period_end = _to_date(row["end"])
            elif fiscal_period == "FY":
                period_end = date(fiscal_year, 12, 31)
            else:
                quarter_month = {"Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12}.get(fiscal_period, 12)
                quarter_day = 31 if quarter_month in (3, 12) else 30
                period_end = date(fiscal_year, quarter_month, quarter_day)

            period_start = (
                _to_date(row["start"]) if "start" in row else date(fiscal_year - 1, 1, 1)
            )

            numeric = float(row["val"])
            all_rows.append(
                {
                    "concept": concept_key,
                    "label": tag_name,
                    "value": numeric,
                    "numeric_value": numeric,
                    "unit": row.get("units", "USD"),
                    "period_type": "duration",
                    "period_start": period_start,
                    "period_end": period_end,
                    "fiscal_year": fiscal_year,
                    "fiscal_period": fiscal_period,
                    "filing_date": filing_date,
                    "form_type": row.get("form", "10-K"),
                }
            )

    columns = [
        "concept",
        "label",
        "value",
        "numeric_value",
        "unit",
        "period_type",
        "period_start",
        "period_end",
        "fiscal_year",
        "fiscal_period",
        "filing_date",
        "form_type",
    ]
    facts_df = pd.DataFrame(all_rows, columns=columns)

    def to_dataframe(*args: Any, **kwargs: Any) -> Any:
        # pit_mode flag is accepted but ignored — the fixture always
        # returns the PIT-mode schema.
        return facts_df

    facts.to_dataframe = to_dataframe
    return facts


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


# ---------------------------------------------------------------------------
# XbrlClient tests
# ---------------------------------------------------------------------------


class TestXbrlClient:
    """Tests for the XbrlClient wrapper around edgartools CompanyFacts."""

    def test_xbrl_tag_groups_has_12_concepts(self) -> None:
        """XBRL_TAG_GROUPS contains at least 12 financial concepts."""
        from ai_hedge_fund.data.clients.xbrl_client import XBRL_TAG_GROUPS

        assert len(XBRL_TAG_GROUPS) >= 12
        expected_concepts = {
            "revenue",
            "net_income",
            "operating_income",
            "eps_diluted",
            "total_assets",
            "total_liabilities",
            "cash_and_equivalents",
            "operating_cash_flow",
            "capex",
            "rd_expense",
            "shares_outstanding",
            "gross_profit",
        }
        assert expected_concepts.issubset(set(XBRL_TAG_GROUPS.keys()))

    def test_resolves_tags_with_fallback(self) -> None:
        """XbrlClient tries primary tag first, falls to secondary if not found."""
        # Only provide the secondary tag for revenue (Revenues, not the primary)
        concept_data = {
            "Revenues": [
                _make_fact_row(val=394_328_000_000.0, fiscal_year=2024, filed="2024-11-01"),
            ],
        }
        facts = _make_company_facts(concept_data)

        with patch("ai_hedge_fund.data.clients.xbrl_client.edgar") as mock_edgar:
            mock_company = MagicMock()
            mock_company.get_facts.return_value = facts
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.clients.xbrl_client import XbrlClient

            client = XbrlClient(edgar_identity="TestCo test@example.com")
            result = client.get_facts("AAPL", concepts=["revenue"])

        assert "revenue" in result
        assert len(result["revenue"]) == 1
        assert result["revenue"][0]["value"] == 394_328_000_000.0

    def test_converts_monetary_values_to_cents(self) -> None:
        """Monetary concepts are converted to cents (int) in get_financial_metrics."""
        concept_data = {
            "Revenues": [
                _make_fact_row(val=394_328_000_000.0, fiscal_year=2024, filed="2024-02-01"),
                _make_fact_row(val=383_285_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "NetIncomeLoss": [
                _make_fact_row(val=96_995_000_000.0, fiscal_year=2024, filed="2024-02-01"),
                _make_fact_row(val=94_680_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "OperatingIncomeLoss": [
                _make_fact_row(val=118_658_000_000.0, fiscal_year=2024, filed="2024-02-01"),
                _make_fact_row(val=114_301_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "EarningsPerShareDiluted": [
                _make_fact_row(
                    val=6.42, unit="USD/shares", fiscal_year=2024, filed="2024-02-01"
                ),
                _make_fact_row(
                    val=6.16, unit="USD/shares", fiscal_year=2023, filed="2023-02-01"
                ),
            ],
            "Assets": [
                _make_fact_row(val=352_583_000_000.0, fiscal_year=2024, filed="2024-02-01"),
            ],
            "Liabilities": [
                _make_fact_row(val=290_437_000_000.0, fiscal_year=2024, filed="2024-02-01"),
            ],
            "CashAndCashEquivalentsAtCarryingValue": [
                _make_fact_row(val=29_965_000_000.0, fiscal_year=2024, filed="2024-02-01"),
            ],
            "NetCashProvidedByUsedInOperatingActivities": [
                _make_fact_row(val=118_254_000_000.0, fiscal_year=2024, filed="2024-02-01"),
            ],
            "PaymentsToAcquirePropertyPlantAndEquipment": [
                _make_fact_row(val=10_959_000_000.0, fiscal_year=2024, filed="2024-02-01"),
            ],
            "ResearchAndDevelopmentExpense": [
                _make_fact_row(val=29_915_000_000.0, fiscal_year=2024, filed="2024-02-01"),
            ],
            "CommonStockSharesOutstanding": [
                _make_fact_row(
                    val=15_115_785_000, unit="shares", fiscal_year=2024, filed="2024-02-01"
                ),
            ],
            "GrossProfit": [
                _make_fact_row(val=180_683_000_000.0, fiscal_year=2024, filed="2024-02-01"),
            ],
        }
        facts = _make_company_facts(concept_data)

        with patch("ai_hedge_fund.data.clients.xbrl_client.edgar") as mock_edgar:
            mock_company = MagicMock()
            mock_company.get_facts.return_value = facts
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.clients.xbrl_client import XbrlClient

            client = XbrlClient(edgar_identity="TestCo test@example.com")
            result = client.get_financial_metrics("AAPL", as_of_date=date(2024, 12, 31))

        metrics = result["metrics"]
        # Revenue should be in cents
        assert metrics["revenue"]["current"] == int(394_328_000_000.0 * 100)
        assert metrics["revenue"]["prior"] == int(383_285_000_000.0 * 100)

    def test_filters_by_filed_date(self) -> None:
        """Facts with filed_date > as_of_date are excluded."""
        concept_data = {
            "Revenues": [
                # This one is visible (filed before cutoff)
                _make_fact_row(val=383_285_000_000.0, fiscal_year=2023, filed="2023-02-01"),
                # This one is NOT visible (filed after cutoff)
                _make_fact_row(val=394_328_000_000.0, fiscal_year=2024, filed="2024-11-01"),
            ],
        }
        facts = _make_company_facts(concept_data)

        with patch("ai_hedge_fund.data.clients.xbrl_client.edgar") as mock_edgar:
            mock_company = MagicMock()
            mock_company.get_facts.return_value = facts
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.clients.xbrl_client import XbrlClient

            client = XbrlClient(edgar_identity="TestCo test@example.com")
            result = client.get_financial_metrics("AAPL", as_of_date=date(2024, 6, 1))

        metrics = result["metrics"]
        # Only 2023 data should be present (current), no prior
        assert metrics["revenue"]["current"] == int(383_285_000_000.0 * 100)
        assert metrics["revenue"]["prior"] is None


# ---------------------------------------------------------------------------
# get_financial_summary tool function tests
# ---------------------------------------------------------------------------


class TestGetFinancialSummary:
    """Tests for the get_financial_summary tool function."""

    def test_raises_on_none_as_of_date(self) -> None:
        """get_financial_summary raises ValueError when as_of_date is None."""
        from ai_hedge_fund.data.tools.financial_tools import get_financial_summary

        with pytest.raises(ValueError, match="as_of_date is required"):
            get_financial_summary("AAPL", as_of_date=None)  # type: ignore[arg-type]

    def test_returns_financial_summary_result(self, _mock_settings: AppSettings) -> None:
        """Returns dict with ticker, fiscal_period, fiscal_year, metrics, summary_text."""
        concept_data = {
            "Revenues": [
                _make_fact_row(val=394_328_000_000.0, fiscal_year=2024, filed="2024-02-01"),
                _make_fact_row(val=383_285_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "NetIncomeLoss": [
                _make_fact_row(val=96_995_000_000.0, fiscal_year=2024, filed="2024-02-01"),
                _make_fact_row(val=94_680_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "OperatingIncomeLoss": [
                _make_fact_row(val=118_658_000_000.0, fiscal_year=2024, filed="2024-02-01"),
                _make_fact_row(val=114_301_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "EarningsPerShareDiluted": [
                _make_fact_row(
                    val=6.42, unit="USD/shares", fiscal_year=2024, filed="2024-02-01"
                ),
                _make_fact_row(
                    val=6.16, unit="USD/shares", fiscal_year=2023, filed="2023-02-01"
                ),
            ],
        }
        facts = _make_company_facts(concept_data)

        with (
            patch("ai_hedge_fund.data.clients.xbrl_client.edgar") as mock_edgar,
            patch(
                "ai_hedge_fund.data.tools.financial_tools.get_settings",
                return_value=_mock_settings,
            ),
        ):
            mock_company = MagicMock()
            mock_company.get_facts.return_value = facts
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.tools.financial_tools import get_financial_summary

            result = get_financial_summary(
                "AAPL",
                as_of_date=date(2024, 12, 31),
            )

        assert result["ticker"] == "AAPL"
        assert result["fiscal_year"] == 2024
        assert "metrics" in result
        assert "summary_text" in result
        assert isinstance(result["summary_text"], str)
        assert len(result["summary_text"]) > 0

    def test_summary_calls_format_financial_summary(
        self, _mock_settings: AppSettings
    ) -> None:
        """Financial summary calls format_financial_summary to produce NL text."""
        concept_data = {
            "Revenues": [
                _make_fact_row(val=100_000_000.0, fiscal_year=2024, filed="2024-02-01"),
                _make_fact_row(val=90_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "NetIncomeLoss": [
                _make_fact_row(val=20_000_000.0, fiscal_year=2024, filed="2024-02-01"),
                _make_fact_row(val=18_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "OperatingIncomeLoss": [
                _make_fact_row(val=25_000_000.0, fiscal_year=2024, filed="2024-02-01"),
                _make_fact_row(val=22_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "EarningsPerShareDiluted": [
                _make_fact_row(
                    val=2.50, unit="USD/shares", fiscal_year=2024, filed="2024-02-01"
                ),
                _make_fact_row(
                    val=2.25, unit="USD/shares", fiscal_year=2023, filed="2023-02-01"
                ),
            ],
        }
        facts = _make_company_facts(concept_data)

        with (
            patch("ai_hedge_fund.data.clients.xbrl_client.edgar") as mock_edgar,
            patch(
                "ai_hedge_fund.data.tools.financial_tools.get_settings",
                return_value=_mock_settings,
            ),
        ):
            mock_company = MagicMock()
            mock_company.get_facts.return_value = facts
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.tools.financial_tools import get_financial_summary

            result = get_financial_summary("TEST", as_of_date=date(2024, 12, 31))

        # Should contain ticker and YoY text from format_financial_summary
        summary = result["summary_text"]
        assert "TEST" in summary
        assert "YoY" in summary

    def test_yoy_comparison_with_prior_year(self, _mock_settings: AppSettings) -> None:
        """Financial summary includes YoY comparison when prior year data available."""
        concept_data = {
            "Revenues": [
                _make_fact_row(val=200_000_000.0, fiscal_year=2024, filed="2024-02-01"),
                _make_fact_row(val=180_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "NetIncomeLoss": [
                _make_fact_row(val=40_000_000.0, fiscal_year=2024, filed="2024-02-01"),
                _make_fact_row(val=35_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "OperatingIncomeLoss": [
                _make_fact_row(val=50_000_000.0, fiscal_year=2024, filed="2024-02-01"),
                _make_fact_row(val=45_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "EarningsPerShareDiluted": [
                _make_fact_row(
                    val=4.00, unit="USD/shares", fiscal_year=2024, filed="2024-02-01"
                ),
                _make_fact_row(
                    val=3.50, unit="USD/shares", fiscal_year=2023, filed="2023-02-01"
                ),
            ],
        }
        facts = _make_company_facts(concept_data)

        with (
            patch("ai_hedge_fund.data.clients.xbrl_client.edgar") as mock_edgar,
            patch(
                "ai_hedge_fund.data.tools.financial_tools.get_settings",
                return_value=_mock_settings,
            ),
        ):
            mock_company = MagicMock()
            mock_company.get_facts.return_value = facts
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.tools.financial_tools import get_financial_summary

            result = get_financial_summary("AAPL", as_of_date=date(2024, 12, 31))

        summary = result["summary_text"]
        # YoY comparisons should be present
        assert "YoY" in summary
        assert "Revenue" in summary or "revenue" in summary.lower()

    def test_caches_to_xbrl_fact_model(
        self, _mock_settings: AppSettings, db_session: Session
    ) -> None:
        """Results are cached to XbrlFact model when db_session is provided."""
        concept_data = {
            "Revenues": [
                _make_fact_row(val=100_000_000.0, fiscal_year=2024, filed="2024-02-01"),
            ],
            "NetIncomeLoss": [
                _make_fact_row(val=20_000_000.0, fiscal_year=2024, filed="2024-02-01"),
            ],
            "OperatingIncomeLoss": [
                _make_fact_row(val=25_000_000.0, fiscal_year=2024, filed="2024-02-01"),
            ],
            "EarningsPerShareDiluted": [
                _make_fact_row(
                    val=2.50, unit="USD/shares", fiscal_year=2024, filed="2024-02-01"
                ),
            ],
        }
        facts = _make_company_facts(concept_data)

        with (
            patch("ai_hedge_fund.data.clients.xbrl_client.edgar") as mock_edgar,
            patch(
                "ai_hedge_fund.data.tools.financial_tools.get_settings",
                return_value=_mock_settings,
            ),
        ):
            mock_company = MagicMock()
            mock_company.get_facts.return_value = facts
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.tools.financial_tools import get_financial_summary

            get_financial_summary(
                "AAPL",
                as_of_date=date(2024, 12, 31),
                db_session=db_session,
            )

        from ai_hedge_fund.db.models import XbrlFact

        rows = db_session.query(XbrlFact).all()
        assert len(rows) > 0
        assert all(r.ticker == "AAPL" for r in rows)
        # At least one monetary concept should be in cents
        revenue_row = next((r for r in rows if r.concept == "revenue"), None)
        assert revenue_row is not None
        assert revenue_row.value_cents == int(100_000_000.0 * 100)

    def test_filters_facts_by_filed_date(self, _mock_settings: AppSettings) -> None:
        """Facts filed after as_of_date are excluded from results."""
        concept_data = {
            "Revenues": [
                _make_fact_row(val=100_000_000.0, fiscal_year=2023, filed="2023-02-01"),
                _make_fact_row(val=120_000_000.0, fiscal_year=2024, filed="2024-11-01"),
            ],
            "NetIncomeLoss": [
                _make_fact_row(val=20_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "OperatingIncomeLoss": [
                _make_fact_row(val=25_000_000.0, fiscal_year=2023, filed="2023-02-01"),
            ],
            "EarningsPerShareDiluted": [
                _make_fact_row(
                    val=2.50, unit="USD/shares", fiscal_year=2023, filed="2023-02-01"
                ),
            ],
        }
        facts = _make_company_facts(concept_data)

        with (
            patch("ai_hedge_fund.data.clients.xbrl_client.edgar") as mock_edgar,
            patch(
                "ai_hedge_fund.data.tools.financial_tools.get_settings",
                return_value=_mock_settings,
            ),
        ):
            mock_company = MagicMock()
            mock_company.get_facts.return_value = facts
            mock_edgar.Company.return_value = mock_company

            from ai_hedge_fund.data.tools.financial_tools import get_financial_summary

            result = get_financial_summary("AAPL", as_of_date=date(2024, 6, 1))

        # Only 2023 revenue should be visible
        metrics = result["metrics"]
        assert metrics["revenue"]["current"] == int(100_000_000.0 * 100)
        # No 2024 data should have leaked in
        assert result["fiscal_year"] == 2023
