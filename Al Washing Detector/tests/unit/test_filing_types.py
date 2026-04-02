"""Unit tests for filing-specific Pydantic type contracts and collection settings.

Tests cover:
- FilingData validates required fields and rejects missing ones
- FilingSections validates section text (optional fields)
- XBRLFactRecord validates required fields
- XBRLTagGroup fallback tag iteration order
- XBRL_TAG_GROUPS constant contains expected keys and tag lists
- CollectionResult tracks filing/xbrl/skipped counts
- FilingCollectionSettings defaults and validation
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Test 1: FilingData validates required fields and rejects missing ones
# ---------------------------------------------------------------------------


class TestFilingData:
    """Tests for FilingData Pydantic model."""

    def test_valid_filing_data(self):
        """FilingData accepts valid required fields."""
        from ai_washer.ingestion.types import FilingData

        data = FilingData(
            accession_no="0000320193-25-000106",
            form_type="10-K",
            filing_date=date(2025, 11, 1),
        )
        assert data.accession_no == "0000320193-25-000106"
        assert data.form_type == "10-K"
        assert data.filing_date == date(2025, 11, 1)

    def test_valid_filing_data_all_fields(self):
        """FilingData accepts all optional fields."""
        from ai_washer.ingestion.types import FilingData, FilingSections

        sections = FilingSections(business="AI strategy discussion")
        data = FilingData(
            accession_no="0000320193-25-000106",
            form_type="10-Q",
            filing_date=date(2025, 8, 1),
            period_of_report=date(2025, 6, 30),
            sections=sections,
            content_hash="abc123",
            entity_name="Apple Inc.",
        )
        assert data.period_of_report == date(2025, 6, 30)
        assert data.sections.business == "AI strategy discussion"
        assert data.content_hash == "abc123"
        assert data.entity_name == "Apple Inc."

    def test_rejects_missing_accession_no(self):
        """FilingData rejects missing accession_no."""
        from ai_washer.ingestion.types import FilingData

        with pytest.raises(ValidationError, match="accession_no"):
            FilingData(
                form_type="10-K",
                filing_date=date(2025, 11, 1),
            )

    def test_rejects_missing_form_type(self):
        """FilingData rejects missing form_type."""
        from ai_washer.ingestion.types import FilingData

        with pytest.raises(ValidationError, match="form_type"):
            FilingData(
                accession_no="0000320193-25-000106",
                filing_date=date(2025, 11, 1),
            )

    def test_rejects_missing_filing_date(self):
        """FilingData rejects missing filing_date."""
        from ai_washer.ingestion.types import FilingData

        with pytest.raises(ValidationError, match="filing_date"):
            FilingData(
                accession_no="0000320193-25-000106",
                form_type="10-K",
            )

    def test_rejects_invalid_form_type(self):
        """FilingData rejects form types not in 10-K, 10-Q, 8-K."""
        from ai_washer.ingestion.types import FilingData

        with pytest.raises(ValidationError):
            FilingData(
                accession_no="0000320193-25-000106",
                form_type="20-F",
                filing_date=date(2025, 11, 1),
            )

    def test_default_sections_empty(self):
        """FilingData defaults sections to empty FilingSections."""
        from ai_washer.ingestion.types import FilingData

        data = FilingData(
            accession_no="0000320193-25-000106",
            form_type="10-K",
            filing_date=date(2025, 11, 1),
        )
        assert data.sections.business is None
        assert data.sections.risk_factors is None
        assert data.sections.mda is None

    def test_form_type_8k(self):
        """FilingData accepts 8-K form type."""
        from ai_washer.ingestion.types import FilingData

        data = FilingData(
            accession_no="0000320193-25-000106",
            form_type="8-K",
            filing_date=date(2025, 11, 1),
        )
        assert data.form_type == "8-K"


# ---------------------------------------------------------------------------
# Test 2: FilingSections validates section text
# ---------------------------------------------------------------------------


class TestFilingSections:
    """Tests for FilingSections Pydantic model."""

    def test_all_sections_optional(self):
        """FilingSections allows all fields to be None."""
        from ai_washer.ingestion.types import FilingSections

        sections = FilingSections()
        assert sections.business is None
        assert sections.risk_factors is None
        assert sections.mda is None
        assert sections.financial_statements is None
        assert sections.full_text_excerpt is None

    def test_sections_accept_text(self):
        """FilingSections accepts text for each section."""
        from ai_washer.ingestion.types import FilingSections

        sections = FilingSections(
            business="Our business uses AI.",
            risk_factors="AI investments may fail.",
            mda="Management discusses AI strategy.",
            financial_statements="R&D spending details.",
            full_text_excerpt="Full text fallback.",
        )
        assert sections.business == "Our business uses AI."
        assert sections.risk_factors == "AI investments may fail."
        assert sections.mda == "Management discusses AI strategy."
        assert sections.financial_statements == "R&D spending details."
        assert sections.full_text_excerpt == "Full text fallback."


# ---------------------------------------------------------------------------
# Test 3: XBRLFactRecord validates required fields
# ---------------------------------------------------------------------------


class TestXBRLFactRecord:
    """Tests for XBRLFactRecord Pydantic model."""

    def test_valid_xbrl_fact(self):
        """XBRLFactRecord accepts valid required fields."""
        from ai_washer.ingestion.types import XBRLFactRecord

        fact = XBRLFactRecord(
            tag="ResearchAndDevelopmentExpense",
            concept="rd_expense",
            end_date=date(2025, 9, 27),
            value_cents=3137000000000,
            fiscal_year=2025,
            fiscal_period="FY",
            form_type="10-K",
            filed_date=date(2025, 11, 1),
            accession_no="0000320193-25-000106",
        )
        assert fact.tag == "ResearchAndDevelopmentExpense"
        assert fact.concept == "rd_expense"
        assert fact.value_cents == 3137000000000

    def test_rejects_missing_tag(self):
        """XBRLFactRecord rejects missing tag."""
        from ai_washer.ingestion.types import XBRLFactRecord

        with pytest.raises(ValidationError, match="tag"):
            XBRLFactRecord(
                concept="rd_expense",
                end_date=date(2025, 9, 27),
                value_cents=100,
                fiscal_year=2025,
                fiscal_period="FY",
                form_type="10-K",
                filed_date=date(2025, 11, 1),
                accession_no="0000320193-25-000106",
            )

    def test_rejects_missing_concept(self):
        """XBRLFactRecord rejects missing concept."""
        from ai_washer.ingestion.types import XBRLFactRecord

        with pytest.raises(ValidationError, match="concept"):
            XBRLFactRecord(
                tag="ResearchAndDevelopmentExpense",
                end_date=date(2025, 9, 27),
                value_cents=100,
                fiscal_year=2025,
                fiscal_period="FY",
                form_type="10-K",
                filed_date=date(2025, 11, 1),
                accession_no="0000320193-25-000106",
            )

    def test_rejects_missing_end_date(self):
        """XBRLFactRecord rejects missing end_date."""
        from ai_washer.ingestion.types import XBRLFactRecord

        with pytest.raises(ValidationError, match="end_date"):
            XBRLFactRecord(
                tag="ResearchAndDevelopmentExpense",
                concept="rd_expense",
                value_cents=100,
                fiscal_year=2025,
                fiscal_period="FY",
                form_type="10-K",
                filed_date=date(2025, 11, 1),
                accession_no="0000320193-25-000106",
            )

    def test_rejects_missing_value_cents(self):
        """XBRLFactRecord rejects missing value_cents."""
        from ai_washer.ingestion.types import XBRLFactRecord

        with pytest.raises(ValidationError, match="value_cents"):
            XBRLFactRecord(
                tag="ResearchAndDevelopmentExpense",
                concept="rd_expense",
                end_date=date(2025, 9, 27),
                fiscal_year=2025,
                fiscal_period="FY",
                form_type="10-K",
                filed_date=date(2025, 11, 1),
                accession_no="0000320193-25-000106",
            )

    def test_rejects_missing_fiscal_year(self):
        """XBRLFactRecord rejects missing fiscal_year."""
        from ai_washer.ingestion.types import XBRLFactRecord

        with pytest.raises(ValidationError, match="fiscal_year"):
            XBRLFactRecord(
                tag="ResearchAndDevelopmentExpense",
                concept="rd_expense",
                end_date=date(2025, 9, 27),
                value_cents=100,
                fiscal_period="FY",
                form_type="10-K",
                filed_date=date(2025, 11, 1),
                accession_no="0000320193-25-000106",
            )

    def test_rejects_missing_fiscal_period(self):
        """XBRLFactRecord rejects missing fiscal_period."""
        from ai_washer.ingestion.types import XBRLFactRecord

        with pytest.raises(ValidationError, match="fiscal_period"):
            XBRLFactRecord(
                tag="ResearchAndDevelopmentExpense",
                concept="rd_expense",
                end_date=date(2025, 9, 27),
                value_cents=100,
                fiscal_year=2025,
                form_type="10-K",
                filed_date=date(2025, 11, 1),
                accession_no="0000320193-25-000106",
            )


# ---------------------------------------------------------------------------
# Test 4: XBRLTagGroup iterates fallback tags in order
# ---------------------------------------------------------------------------


class TestXBRLTagGroup:
    """Tests for XBRLTagGroup model."""

    def test_tag_group_preserves_order(self):
        """XBRLTagGroup maintains fallback tag order."""
        from ai_washer.ingestion.types import XBRLTagGroup

        group = XBRLTagGroup(
            concept="rd_expense",
            tags=["TagA", "TagB", "TagC"],
        )
        assert group.concept == "rd_expense"
        assert group.tags == ["TagA", "TagB", "TagC"]
        # Iteration order preserved
        assert list(group.tags) == ["TagA", "TagB", "TagC"]

    def test_tag_group_requires_concept(self):
        """XBRLTagGroup rejects missing concept."""
        from ai_washer.ingestion.types import XBRLTagGroup

        with pytest.raises(ValidationError, match="concept"):
            XBRLTagGroup(tags=["TagA"])

    def test_tag_group_requires_tags(self):
        """XBRLTagGroup rejects missing tags."""
        from ai_washer.ingestion.types import XBRLTagGroup

        with pytest.raises(ValidationError, match="tags"):
            XBRLTagGroup(concept="rd_expense")


# ---------------------------------------------------------------------------
# Test 5: XBRL_TAG_GROUPS constant
# ---------------------------------------------------------------------------


class TestXBRLTagGroups:
    """Tests for XBRL_TAG_GROUPS constant."""

    def test_contains_rd_expense_key(self):
        """XBRL_TAG_GROUPS has rd_expense key."""
        from ai_washer.ingestion.types import XBRL_TAG_GROUPS

        assert "rd_expense" in XBRL_TAG_GROUPS

    def test_contains_capex_key(self):
        """XBRL_TAG_GROUPS has capex key."""
        from ai_washer.ingestion.types import XBRL_TAG_GROUPS

        assert "capex" in XBRL_TAG_GROUPS

    def test_contains_revenue_key(self):
        """XBRL_TAG_GROUPS has revenue key."""
        from ai_washer.ingestion.types import XBRL_TAG_GROUPS

        assert "revenue" in XBRL_TAG_GROUPS

    def test_rd_expense_tags(self):
        """rd_expense contains correct XBRL tags in order."""
        from ai_washer.ingestion.types import XBRL_TAG_GROUPS

        expected = [
            "ResearchAndDevelopmentExpense",
            "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
            "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost",
        ]
        assert XBRL_TAG_GROUPS["rd_expense"] == expected

    def test_capex_tags(self):
        """capex contains correct XBRL tags in order."""
        from ai_washer.ingestion.types import XBRL_TAG_GROUPS

        expected = [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
            "CapitalExpenditureDiscontinuedOperations",
        ]
        assert XBRL_TAG_GROUPS["capex"] == expected

    def test_revenue_tags(self):
        """revenue contains correct XBRL tags in order."""
        from ai_washer.ingestion.types import XBRL_TAG_GROUPS

        expected = [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
            "SalesRevenueGoodsNet",
        ]
        assert XBRL_TAG_GROUPS["revenue"] == expected

    def test_exactly_three_groups(self):
        """XBRL_TAG_GROUPS has exactly 3 concept groups."""
        from ai_washer.ingestion.types import XBRL_TAG_GROUPS

        assert len(XBRL_TAG_GROUPS) == 3


# ---------------------------------------------------------------------------
# Test 6: CollectionResult tracks counts
# ---------------------------------------------------------------------------


class TestCollectionResult:
    """Tests for CollectionResult Pydantic model."""

    def test_default_counts(self):
        """CollectionResult defaults all counts to 0 and errors to empty list."""
        from ai_washer.ingestion.types import CollectionResult

        result = CollectionResult(company_cik="0000320193")
        assert result.filing_count == 0
        assert result.xbrl_fact_count == 0
        assert result.skipped_count == 0
        assert result.errors == []

    def test_custom_counts(self):
        """CollectionResult accepts custom count values."""
        from ai_washer.ingestion.types import CollectionResult

        result = CollectionResult(
            company_cik="0000320193",
            filing_count=5,
            xbrl_fact_count=15,
            skipped_count=2,
            errors=["Rate limited on filing X"],
        )
        assert result.filing_count == 5
        assert result.xbrl_fact_count == 15
        assert result.skipped_count == 2
        assert result.errors == ["Rate limited on filing X"]

    def test_rejects_missing_company_cik(self):
        """CollectionResult rejects missing company_cik."""
        from ai_washer.ingestion.types import CollectionResult

        with pytest.raises(ValidationError, match="company_cik"):
            CollectionResult()


# ---------------------------------------------------------------------------
# Test 7: FilingCollectionSettings defaults
# ---------------------------------------------------------------------------


class TestFilingCollectionSettings:
    """Tests for FilingCollectionSettings in config.py."""

    def test_default_form_types(self):
        """FilingCollectionSettings defaults form_types to 10-K, 10-Q, 8-K."""
        from ai_washer.config import FilingCollectionSettings

        settings = FilingCollectionSettings()
        assert settings.form_types == ["10-K", "10-Q", "8-K"]

    def test_default_section_max_chars(self):
        """FilingCollectionSettings defaults section_max_chars to 50000."""
        from ai_washer.config import FilingCollectionSettings

        settings = FilingCollectionSettings()
        assert settings.section_max_chars == 50_000

    def test_default_max_8k_filings(self):
        """FilingCollectionSettings defaults max_8k_filings to 10."""
        from ai_washer.config import FilingCollectionSettings

        settings = FilingCollectionSettings()
        assert settings.max_8k_filings == 10

    def test_default_max_annual_filings(self):
        """FilingCollectionSettings defaults max_annual_filings to 5."""
        from ai_washer.config import FilingCollectionSettings

        settings = FilingCollectionSettings()
        assert settings.max_annual_filings == 5

    def test_default_max_quarterly_filings(self):
        """FilingCollectionSettings defaults max_quarterly_filings to 8."""
        from ai_washer.config import FilingCollectionSettings

        settings = FilingCollectionSettings()
        assert settings.max_quarterly_filings == 8


# ---------------------------------------------------------------------------
# Test 8: FilingCollectionSettings validation
# ---------------------------------------------------------------------------


class TestFilingCollectionSettingsValidation:
    """Tests for FilingCollectionSettings field validation."""

    def test_section_max_chars_minimum_1000(self):
        """FilingCollectionSettings rejects section_max_chars < 1000."""
        from ai_washer.config import FilingCollectionSettings

        with pytest.raises(ValidationError, match="section_max_chars"):
            FilingCollectionSettings(section_max_chars=999)

    def test_section_max_chars_exactly_1000_valid(self):
        """FilingCollectionSettings accepts section_max_chars == 1000."""
        from ai_washer.config import FilingCollectionSettings

        settings = FilingCollectionSettings(section_max_chars=1000)
        assert settings.section_max_chars == 1000

    def test_max_8k_filings_range(self):
        """FilingCollectionSettings validates max_8k_filings in [1, 50]."""
        from ai_washer.config import FilingCollectionSettings

        with pytest.raises(ValidationError):
            FilingCollectionSettings(max_8k_filings=0)
        with pytest.raises(ValidationError):
            FilingCollectionSettings(max_8k_filings=51)

    def test_max_annual_filings_range(self):
        """FilingCollectionSettings validates max_annual_filings in [1, 20]."""
        from ai_washer.config import FilingCollectionSettings

        with pytest.raises(ValidationError):
            FilingCollectionSettings(max_annual_filings=0)
        with pytest.raises(ValidationError):
            FilingCollectionSettings(max_annual_filings=21)

    def test_max_quarterly_filings_range(self):
        """FilingCollectionSettings validates max_quarterly_filings in [1, 40]."""
        from ai_washer.config import FilingCollectionSettings

        with pytest.raises(ValidationError):
            FilingCollectionSettings(max_quarterly_filings=0)
        with pytest.raises(ValidationError):
            FilingCollectionSettings(max_quarterly_filings=41)

    def test_custom_form_types(self):
        """FilingCollectionSettings accepts custom form_types."""
        from ai_washer.config import FilingCollectionSettings

        settings = FilingCollectionSettings(form_types=["10-K", "10-Q"])
        assert settings.form_types == ["10-K", "10-Q"]
