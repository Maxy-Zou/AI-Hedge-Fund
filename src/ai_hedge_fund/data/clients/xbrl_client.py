"""XBRL financial fact extraction client via edgartools CompanyFacts API.

Retrieves structured financial data from SEC EDGAR XBRL filings.
Resolves tag variability across companies using fallback tag lists
per concept. Monetary values are converted to cents at ingestion.

Implementation notes
--------------------
Targets edgartools >= 5.28 (installed: 5.28.5). Uses
``EntityFacts.to_dataframe(pit_mode=True)`` which returns a DataFrame with
columns::

    concept, label, value, numeric_value, unit, period_type,
    period_start, period_end, fiscal_year, fiscal_period,
    filing_date, form_type

``filing_date`` is a native ``datetime.date``. ``concept`` is a taxonomy-
prefixed string (e.g. ``'us-gaap:Revenues'``). PIT mode is mandatory for
look-ahead-bias control — it preserves every restatement so we can filter
``filing_date <= as_of_date`` and then pick the latest filing per period.
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
MONETARY_CONCEPTS: frozenset[str] = frozenset(
    {
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
    }
)

# Default taxonomy for our fallback-tag lookups. All tags in XBRL_TAG_GROUPS
# are US GAAP concepts; edgartools prefixes concepts as ``'us-gaap:<Tag>'``.
_DEFAULT_TAXONOMY = "us-gaap"

# Annual report form (FY facts arrive via 10-K/10-K/A filings). We key
# "latest fiscal year" off period_end rather than the fiscal_year column
# because in pit_mode fiscal_year can reflect the filing's FY rather than
# the fact's FY.
_ANNUAL_FORMS: frozenset[str] = frozenset({"10-K", "10-K/A"})


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
            keys: value, unit, fiscal_period, fiscal_year, filed_date,
            period_end, form.
        """
        log.info("xbrl_client.get_facts", ticker=ticker)
        company = edgar.Company(ticker)
        company_facts = company.get_facts()
        facts_df = company_facts.to_dataframe(pit_mode=True)

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

        Filters facts by ``filing_date <= as_of_date`` to prevent look-ahead
        bias. For each ``(concept, period_end)`` pair the latest filing
        visible as of ``as_of_date`` is kept (handles restatements). Facts
        are then narrowed to annual reports, and current/prior are the two
        most recent fiscal years. Monetary values are converted to cents.

        Args:
            ticker: Stock ticker symbol.
            as_of_date: Maximum filing_date to include (inclusive).

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

        metrics: dict[str, dict[str, int | float | None]] = {}
        latest_fiscal_year = 0
        latest_fiscal_period = "FY"

        for concept, facts_list in raw_facts.items():
            # Temporal filter: drop anything filed after as_of_date.
            visible = [f for f in facts_list if f["filed_date"] <= as_of_date]
            if not visible:
                continue

            # Dedupe restatements: for each period_end, keep the row with
            # the latest filing_date visible as of as_of_date.
            by_period: dict[date, dict[str, Any]] = {}
            for fact in visible:
                pe = fact.get("period_end")
                if pe is None:
                    continue
                prior = by_period.get(pe)
                if prior is None or fact["filed_date"] > prior["filed_date"]:
                    by_period[pe] = fact

            # Prefer annual-report facts (10-K / 10-K/A) when available;
            # fall back to whatever remains (covers tags that only appear
            # on 10-Q, e.g. shares_outstanding).
            period_facts = list(by_period.values())
            annual_facts = [f for f in period_facts if f.get("form") in _ANNUAL_FORMS]
            candidate_facts = annual_facts or period_facts

            # Sort by period_end descending -> [current, prior, ...]
            candidate_facts.sort(key=lambda f: f["period_end"], reverse=True)

            current_fact = candidate_facts[0]
            prior_fact = candidate_facts[1] if len(candidate_facts) > 1 else None

            # Track latest fiscal year across concepts using period_end.year
            # (fiscal_year column is unreliable in pit_mode).
            current_year = current_fact["period_end"].year
            if current_year > latest_fiscal_year:
                latest_fiscal_year = current_year
                latest_fiscal_period = current_fact.get("fiscal_period") or "FY"

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

    Matches against edgartools' taxonomy-prefixed ``concept`` column
    (e.g. ``'us-gaap:Revenues'``). Returns the first tag that has data.

    Args:
        facts_df: DataFrame from ``EntityFacts.to_dataframe(pit_mode=True)``.
        tags: List of XBRL tag names to try, in priority order.

    Returns:
        List of fact dicts for the first tag that has data, or empty list.
    """
    if facts_df is None or len(facts_df) == 0:
        return []

    for tag in tags:
        concept_key = f"{_DEFAULT_TAXONOMY}:{tag}"
        matching = facts_df[facts_df["concept"] == concept_key]

        if len(matching) == 0:
            continue

        results: list[dict[str, Any]] = []
        for _, row in matching.iterrows():
            numeric = row.get("numeric_value")
            raw_value = row["value"] if numeric is None or _is_nan(numeric) else numeric
            if raw_value is None or _is_nan(raw_value):
                continue

            filed = row.get("filing_date")
            period_end = row.get("period_end")
            if filed is None or period_end is None:
                # Can't enforce temporal invariant without both dates.
                continue

            results.append(
                {
                    "value": float(raw_value),
                    "unit": str(row.get("unit", "")),
                    "fiscal_period": str(row.get("fiscal_period", "")),
                    "fiscal_year": int(row["fiscal_year"]) if row.get("fiscal_year") else 0,
                    "filed_date": filed,
                    "period_end": period_end,
                    "form": str(row.get("form_type", "")),
                }
            )

        if results:
            return results

    return []


def _is_nan(value: Any) -> bool:
    """Return True if ``value`` is a NaN float (incl. numpy.float64 NaN)."""
    try:
        return value != value  # NaN != NaN
    except Exception:
        return False
