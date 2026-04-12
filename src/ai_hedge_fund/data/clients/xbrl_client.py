"""XBRL financial fact extraction client via edgartools CompanyFacts API.

Retrieves structured financial data from SEC EDGAR XBRL filings.
Resolves tag variability across companies using fallback tag lists
per concept. Monetary values are converted to cents at ingestion.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import edgar
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# XBRL tag groups: fallback lists per financial concept
# Companies use different XBRL tags for the same concept. We try in order.
# Source: archived XBRL extractor + SEC CompanyFacts API research
# ---------------------------------------------------------------------------

XBRL_TAG_GROUPS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "net_income": [
        "NetIncomeLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "ProfitLoss",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ],
    "eps_diluted": [
        "EarningsPerShareDiluted",
        "EarningsPerShareBasicAndDiluted",
    ],
    "total_assets": [
        "Assets",
    ],
    "total_liabilities": [
        "Liabilities",
        "LiabilitiesAndStockholdersEquity",
    ],
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "rd_expense": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
    ],
    "shares_outstanding": [
        "CommonStockSharesOutstanding",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    ],
    "gross_profit": [
        "GrossProfit",
    ],
}

# Concepts where values represent monetary amounts (convert to cents)
MONETARY_CONCEPTS: frozenset[str] = frozenset({
    "revenue",
    "net_income",
    "operating_income",
    "total_assets",
    "total_liabilities",
    "cash_and_equivalents",
    "operating_cash_flow",
    "capex",
    "rd_expense",
    "gross_profit",
})


class XbrlClient:
    """Wrapper around edgartools for XBRL financial fact extraction.

    Uses CompanyFacts API to retrieve structured financial data.
    Resolves XBRL tag variability by trying tags in priority order
    from XBRL_TAG_GROUPS.

    Args:
        edgar_identity: Identity string for SEC EDGAR.
    """

    def __init__(self, edgar_identity: str) -> None:
        self._identity = edgar_identity
        edgar.set_identity(edgar_identity)
        log.info("xbrl_client.init", identity=edgar_identity)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def get_facts(
        self,
        ticker: str,
        concepts: list[str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Retrieve XBRL facts for specified financial concepts.

        Tries XBRL tags in priority order from XBRL_TAG_GROUPS for each
        concept. Returns the first tag that has data.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL").
            concepts: List of concept names to retrieve. Defaults to all
                XBRL_TAG_GROUPS keys.

        Returns:
            Dict mapping concept name to list of fact dicts. Each fact has
            keys: value, unit, fiscal_period, fiscal_year, filed_date.
        """
        log.info("xbrl_client.get_facts", ticker=ticker)
        company = edgar.Company(ticker)
        company_facts = company.get_facts()
        facts_df = company_facts.to_pandas()

        target_concepts = concepts or list(XBRL_TAG_GROUPS.keys())
        result: dict[str, list[dict[str, Any]]] = {}

        for concept in target_concepts:
            tags = XBRL_TAG_GROUPS.get(concept, [])
            concept_facts = _resolve_concept_facts(facts_df, tags)
            if concept_facts:
                result[concept] = concept_facts

        return result

    def get_financial_metrics(
        self,
        ticker: str,
        as_of_date: date,
    ) -> dict[str, Any]:
        """Retrieve financial metrics with temporal filtering and cents conversion.

        Filters facts by filed_date <= as_of_date to prevent look-ahead bias.
        Groups by fiscal_year and returns the latest year (current) plus the
        prior year. Converts monetary values to cents.

        Args:
            ticker: Stock ticker symbol.
            as_of_date: Maximum filed_date to include (inclusive).

        Returns:
            Dict with keys: ticker, fiscal_period, fiscal_year, metrics.
            metrics maps concept to {current, prior} values.
        """
        log.info(
            "xbrl_client.get_financial_metrics",
            ticker=ticker,
            as_of_date=as_of_date.isoformat(),
        )

        raw_facts = self.get_facts(ticker)

        # Filter by filed_date and organize by fiscal_year
        metrics: dict[str, dict[str, int | float | None]] = {}
        latest_fiscal_year = 0
        latest_fiscal_period = "FY"

        for concept, facts_list in raw_facts.items():
            # Filter by filed_date
            visible_facts = [
                f for f in facts_list if date.fromisoformat(f["filed_date"]) <= as_of_date
            ]

            if not visible_facts:
                continue

            # Sort by fiscal_year descending to get latest and prior
            visible_facts.sort(key=lambda f: f["fiscal_year"], reverse=True)

            current_fact = visible_facts[0]
            prior_fact = visible_facts[1] if len(visible_facts) > 1 else None

            # Track latest fiscal year across all concepts
            if current_fact["fiscal_year"] > latest_fiscal_year:
                latest_fiscal_year = current_fact["fiscal_year"]
                latest_fiscal_period = current_fact.get("fiscal_period", "FY")

            # Convert to cents for monetary concepts
            current_val = current_fact["value"]
            prior_val = prior_fact["value"] if prior_fact else None

            if concept in MONETARY_CONCEPTS:
                current_val = int(current_val * 100)
                prior_val = int(prior_val * 100) if prior_val is not None else None

            metrics[concept] = {
                "current": current_val,
                "prior": prior_val,
            }

        return {
            "ticker": ticker,
            "fiscal_period": latest_fiscal_period,
            "fiscal_year": latest_fiscal_year,
            "metrics": metrics,
        }


def _resolve_concept_facts(
    facts_df: Any,
    tags: list[str],
) -> list[dict[str, Any]]:
    """Resolve a financial concept by trying tags in priority order.

    Args:
        facts_df: Pandas DataFrame of all CompanyFacts data.
        tags: List of XBRL tag names to try, in priority order.

    Returns:
        List of fact dicts for the first tag that has data, or empty list.
    """
    if facts_df is None or len(facts_df) == 0:
        return []

    for tag in tags:
        # Filter by tag name and us-gaap namespace
        mask = (facts_df["fact"] == tag) & (facts_df["namespace"] == "us-gaap")
        matching = facts_df[mask]

        if len(matching) > 0:
            results = []
            for _, row in matching.iterrows():
                results.append({
                    "value": float(row["val"]),
                    "unit": str(row["units"]),
                    "fiscal_period": str(row["fp"]),
                    "fiscal_year": int(row["fy"]),
                    "filed_date": str(row["filed"]),
                    "form": str(row["form"]),
                })
            return results

    return []
