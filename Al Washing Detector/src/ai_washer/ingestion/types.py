"""Pydantic type contracts for SEC filing collection.

Defines schemas for filing data, XBRL facts, tag groups, and collection results.
These types form the contract between the ingestion layer and the database layer.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# XBRL tag fallback lists per financial concept
# ---------------------------------------------------------------------------

XBRL_TAG_GROUPS: dict[str, list[str]] = {
    "rd_expense": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "CapitalExpenditureDiscontinuedOperations",
    ],
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
}


class XBRLTagGroup(BaseModel):
    """Ordered fallback list of XBRL tags for a single financial concept.

    The extractor tries tags in order and uses the first one that has data
    for a given company. This handles the variability in XBRL tag usage
    across different companies (Pitfall 10 from research).
    """

    concept: str
    tags: list[str]


class FilingSections(BaseModel):
    """Section text excerpts from an SEC filing.

    Maps to standard 10-K/10-Q section identifiers. All fields are optional
    because not every filing type has every section (e.g., 8-K has none of
    these standard sections).
    """

    business: str | None = None  # Item 1
    risk_factors: str | None = None  # Item 1A
    mda: str | None = None  # Item 7 -- Management Discussion & Analysis
    financial_statements: str | None = None  # Item 8
    full_text_excerpt: str | None = None  # Fallback when section parsing fails


class FilingData(BaseModel):
    """Parsed filing data from edgartools.

    Represents a single SEC filing (10-K, 10-Q, or 8-K) with metadata
    and extracted section text. Validated at the ingestion boundary before
    storage.
    """

    accession_no: str
    form_type: Literal["10-K", "10-Q", "8-K"]
    filing_date: date
    period_of_report: date | None = None
    sections: FilingSections = Field(default_factory=FilingSections)
    content_hash: str | None = None
    entity_name: str | None = None


class XBRLFactRecord(BaseModel):
    """Single extracted XBRL fact from the companyfacts API.

    Represents one financial data point (e.g., R&D expense for FY2025).
    Monetary values are stored in cents to avoid floating point issues
    per project constraint D-09.
    """

    tag: str  # Actual XBRL tag matched (e.g., "ResearchAndDevelopmentExpense")
    concept: str  # Normalized concept name (e.g., "rd_expense")
    end_date: date
    value_cents: int  # Value in cents -- converted from dollars
    fiscal_year: int
    fiscal_period: str  # "FY", "Q1", "Q2", "Q3", "Q4"
    form_type: str
    filed_date: date
    accession_no: str


class CollectionResult(BaseModel):
    """Result of collecting filings for one company.

    Tracks counts of filings and XBRL facts collected, plus any errors
    encountered during collection. Used for operational monitoring.
    """

    company_cik: str
    filing_count: int = 0
    xbrl_fact_count: int = 0
    skipped_count: int = 0
    errors: list[str] = Field(default_factory=list)
