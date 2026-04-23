# Phase 2: Data Ingestion - Research

**Researched:** 2026-04-12
**Domain:** Financial data ingestion (SEC EDGAR, equity prices, insider trades, news sentiment, macro indicators)
**Confidence:** HIGH

## Summary

Phase 2 builds the complete data layer: six data sources (SEC filings via edgartools, XBRL financials via CompanyFacts API, equity prices via yfinance with Tiingo fallback, insider trades from Form 4, news/sentiment from Finnhub, macro data from FRED) all unified behind tool functions with mandatory `as_of_date` temporal controls. Every tool enforces look-ahead bias prevention by filtering on filing date (not period end date) and rejecting requests without an `as_of_date` parameter.

The project already has substantial prior art: the archived AI Washing Detector contains a working EDGAR client, XBRL extractor, and filing client using edgartools, plus SQLAlchemy models with AppendOnlyMixin and DualTimestampMixin patterns. Phase 1 established the foundation (config, db session, schemas, models, graph pipeline) that this phase extends. The key technical challenge is not any single data source but the consistency guarantee: every retrieval path must enforce temporal controls, cache to PostgreSQL, and return natural-language summaries (not raw JSON) for LLM consumption.

**Primary recommendation:** Build a repository-pattern data layer with one client module per data source, one SQLAlchemy model per data table, and one tool function per agent-callable operation -- all sharing a common `as_of_date` enforcement decorator and natural-language summary formatter.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion -- infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints from PROJECT.md and CLAUDE.md:
- Every data input must have a timestamp; RAG retrieval filtered by "available as of analysis date"
- Always use filing date (not period end date) for SEC data -- prevents look-ahead bias
- Always use adjusted close prices for return calculations
- Pre-process structured data into natural language summaries before LLM consumption
- Raw data cached locally (PostgreSQL) to avoid redundant API calls
- Append-only for financial time-series data (never overwrite historical observations)
- Dual timestamps where relevant: business date (as_of_date) vs. collection date (observed_date)
- Free data stack for v1: SEC EDGAR, yfinance, Finnhub (60 req/min), FMP (250 calls/day), FRED

### Claude's Discretion
All implementation choices are at Claude's discretion -- infrastructure phase.

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase, no discussion occurred.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | SEC EDGAR integration for 10-K, 10-Q, 8-K filings via edgartools with section-level chunking | edgartools v5.28.5 verified on PyPI; TenK/TenQ objects support bracket-notation section access (`tenk["Item 1"]`); archived FilingClient provides proven pattern |
| DATA-02 | XBRL financial data extraction via CompanyFacts API with pre-computed metric summaries | CompanyFacts API at `data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` verified; edgartools `Company.get_facts()` wraps this; archived XBRLExtractor provides tag-fallback pattern; must expand to ~12 financial concepts |
| DATA-03 | Equity price data ingestion (yfinance with PostgreSQL caching, Tiingo fallback) | yfinance v1.2.1 on PyPI; tiingo v0.16.1 on PyPI; yfinance is fragile (unofficial, Yahoo changes break it); cache-once-to-PostgreSQL pattern mitigates; Tiingo free tier: 50 symbols/hour, 100 requests/day |
| DATA-04 | Insider trade detection from SEC Form 4 filings with cluster buy identification | edgartools supports Form 4 via `company.get_filings(form="4")`; `.obj()` returns structured transactions; cluster detection (3+ insiders buying within 14 days) is custom logic on top of stored Form 4 data |
| DATA-05 | News and sentiment aggregation from Finnhub with daily per-ticker summaries | finnhub-python v2.4.27 on PyPI; free tier 60 req/min; provides company_news and news_sentiment endpoints; daily summaries require aggregation + natural language formatting |
| DATA-06 | Macro context from FRED (interest rates, CPI, GDP, yield curve) | fredapi v0.5.2 on PyPI; verified series IDs: FEDFUNDS, CPIAUCSL, GDP, T10Y2Y, DGS10, DGS2; free with API key |
| DATA-07 | Strict temporal controls -- every data input timestamped, RAG filtered by "available as of" date | Cross-cutting concern: decorator pattern on all tool functions enforcing mandatory `as_of_date`; all queries filter `WHERE as_of_date <= :cutoff`; raise error on missing parameter |
| DATA-08 | Natural language summaries generated from structured data before LLM consumption | Template-based formatters per data type: XBRL metrics to prose (revenue, margins, YoY/QoQ changes), news to daily digest, insider trades to cluster narrative |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Language/runtime:** Python 3.11+ (3.12 recommended), uv for packages
- **Database:** PostgreSQL 16+ via Docker Compose (already running)
- **ORM:** SQLAlchemy 2.0+ with mapped_column, AppendOnlyMixin, DualTimestampMixin
- **Config:** pydantic-settings AppSettings (extend, don't replace)
- **Logging:** structlog throughout
- **HTTP client:** httpx (already in stack) for non-edgartools API calls
- **Retry:** tenacity for all external API calls
- **Formatting:** ruff (line-length=100, target-version=py312)
- **Testing:** pytest, TDD workflow, 80%+ coverage target
- **Immutability:** Return new objects, never mutate in place
- **Files:** Functions under 50 lines, files under 800 lines
- **Type hints:** Required on all function params and return values
- **Monetary values:** Store as integers (cents) to avoid floating point
- **Timestamps:** All UTC
- **Financial data:** Preserve source precision, never round prematurely

## Standard Stack

### Core (New Dependencies for Phase 2)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| edgartools | >=5.28.0 | SEC EDGAR filings, Form 4 insider trades, XBRL via get_facts() | [VERIFIED: PyPI 5.28.5] Free, no API key, typed Python objects, section extraction, Form 4 support, actively maintained (weekly releases) |
| yfinance | >=1.2.0 | Equity price download (OHLCV) for PostgreSQL caching | [VERIFIED: PyPI 1.2.1] Unofficial but ubiquitous; cache once then serve from DB; fragile but free |
| tiingo | >=0.16.0 | Fallback equity price source when yfinance fails | [VERIFIED: PyPI 0.16.1] Free tier: 50 symbols/hr, 100 req/day, 30+ years history; reliable API |
| fredapi | >=0.5.0 | FRED macro data (rates, CPI, GDP, yield curve) | [VERIFIED: PyPI 0.5.2] Official Python wrapper, returns pandas Series, supports ALFRED revisions |
| finnhub-python | >=2.4.0 | News + sentiment + market data | [VERIFIED: PyPI 2.4.27] Free tier 60 req/min; company_news, news_sentiment endpoints |

### Already in Stack (Phase 1)

| Library | Version | Purpose |
|---------|---------|---------|
| sqlalchemy | >=2.0.49 | ORM, models, append-only tables |
| psycopg[binary,pool] | >=3.3.0 | PostgreSQL driver |
| alembic | >=1.18.0 | Database migrations |
| httpx | >=0.28.0 | HTTP client for direct API calls |
| tenacity | >=9.0.0 | Retry with exponential backoff |
| structlog | >=25.0.0 | Structured logging |
| pydantic | >=2.12.0 | Data validation, schemas |
| pydantic-settings | >=2.13.0 | Environment config |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| edgartools | sec-api | sec-api requires paid API key; edgartools is free with better Python objects |
| edgartools | Direct EDGAR HTTP + httpx | Months of parsing work for 20+ form types; edgartools handles this |
| yfinance | Polygon.io | Polygon is $29/mo; yfinance is free; cache mitigates fragility |
| tiingo (fallback) | Alpha Vantage | Alpha Vantage has stricter rate limits (25/day free); Tiingo is more generous |
| fredapi | pystlouisfed | fredapi is simpler, returns pandas directly, well-established |
| finnhub-python | Direct Finnhub REST + httpx | The SDK handles auth and pagination; minimal overhead |

**Installation:**
```bash
uv add edgartools yfinance tiingo fredapi finnhub-python
```

## Architecture Patterns

### Recommended Project Structure

```
src/ai_hedge_fund/
  data/                        # NEW: Phase 2 data layer
    __init__.py
    temporal.py                # as_of_date enforcement decorator + utilities
    summary.py                 # Natural language summary formatters (DATA-08)
    clients/                   # External API client wrappers
      __init__.py
      edgar_client.py          # SEC EDGAR filings (10-K, 10-Q, 8-K)
      xbrl_client.py           # XBRL CompanyFacts extraction
      form4_client.py          # Form 4 insider trade parsing
      price_client.py          # yfinance + Tiingo fallback
      finnhub_client.py        # News + sentiment
      fred_client.py           # Macro indicators
    tools/                     # Agent-callable tool functions (PydanticAI tools)
      __init__.py
      filing_tools.py          # get_filing_sections(ticker, as_of_date)
      financial_tools.py       # get_financial_summary(ticker, as_of_date)
      price_tools.py           # get_price_history(ticker, as_of_date, lookback)
      insider_tools.py         # get_insider_clusters(ticker, as_of_date)
      sentiment_tools.py       # get_news_sentiment(ticker, as_of_date)
      macro_tools.py           # get_macro_context(as_of_date)
  db/
    base.py                    # (existing) Base, AppendOnlyMixin, DualTimestampMixin
    session.py                 # (existing) Engine + session factory
    models.py                  # NEW: SQLAlchemy models for data tables
    migrations/                # NEW: Alembic migration directory
      env.py
      versions/
```

### Pattern 1: Temporal Enforcement Decorator

**What:** A decorator that enforces mandatory `as_of_date` on every data retrieval tool, validates the parameter type, and ensures no downstream query returns data after the cutoff.

**When to use:** Every tool function in `data/tools/`.

**Example:**
```python
# Source: Project convention (CLAUDE.md temporal controls)
from __future__ import annotations

import functools
from datetime import date, datetime


def enforce_as_of_date(func):
    """Decorator ensuring as_of_date is provided and valid.

    Raises ValueError if as_of_date is missing or in the future.
    Converts datetime to date if needed.
    """
    @functools.wraps(func)
    def wrapper(*args, as_of_date: date | datetime | None = None, **kwargs):
        if as_of_date is None:
            raise ValueError(
                f"{func.__name__} requires as_of_date parameter. "
                "Calling without it risks look-ahead bias."
            )
        if isinstance(as_of_date, datetime):
            as_of_date = as_of_date.date()
        if as_of_date > date.today():
            raise ValueError(
                f"as_of_date ({as_of_date}) is in the future. "
                "Cannot retrieve data that does not yet exist."
            )
        return func(*args, as_of_date=as_of_date, **kwargs)
    return wrapper
```

### Pattern 2: Repository Pattern for Cached Data Access

**What:** Each data source has a client (fetches from external API) and a repository (reads/writes PostgreSQL cache). Tools compose both: check cache first, fetch if missing, cache result, return.

**When to use:** All data sources that cache to PostgreSQL (prices, filings, XBRL, insider trades, news, macro).

**Example:**
```python
# Source: Project convention (repository pattern from CLAUDE.md rules)
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session


class PriceRepository:
    """Read/write equity price data from PostgreSQL cache."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[DailyPrice]:
        """Fetch cached prices for a ticker within a date range.

        Filters by as_of_date <= end_date to prevent look-ahead bias.
        Returns empty list if no cached data exists.
        """
        return (
            self._session.query(DailyPrice)
            .filter(
                DailyPrice.ticker == ticker,
                DailyPrice.trade_date >= start_date,
                DailyPrice.trade_date <= end_date,
            )
            .order_by(DailyPrice.trade_date)
            .all()
        )

    def upsert_prices(self, prices: list[DailyPrice]) -> int:
        """Insert prices, skip duplicates (append-only)."""
        # Use INSERT ... ON CONFLICT DO NOTHING for idempotency
        ...
```

### Pattern 3: Natural Language Summary Formatter

**What:** Template-based formatters that convert structured financial data into natural language paragraphs for LLM consumption. LLMs process prose better than raw JSON/tables.

**When to use:** DATA-08 requirement -- every structured data result gets summarized before being passed to agents.

**Example:**
```python
# Source: CLAUDE.md convention (pre-process structured data into NL summaries)
from __future__ import annotations


def format_financial_summary(
    ticker: str,
    revenue_current: int,  # cents
    revenue_prior: int,    # cents
    net_income_current: int,
    net_income_prior: int,
    operating_margin_current: float,
    operating_margin_prior: float,
    fiscal_period: str,
) -> str:
    """Format XBRL financials into a natural language summary.

    Returns a paragraph describing key metrics with YoY changes.
    All monetary values are in cents, converted to display format.
    """
    rev_change = (revenue_current - revenue_prior) / max(revenue_prior, 1) * 100
    ni_change = (net_income_current - net_income_prior) / max(abs(net_income_prior), 1) * 100

    return (
        f"{ticker} {fiscal_period}: Revenue was ${revenue_current / 100:,.0f} "
        f"({'up' if rev_change > 0 else 'down'} {abs(rev_change):.1f}% YoY). "
        f"Net income was ${net_income_current / 100:,.0f} "
        f"({'up' if ni_change > 0 else 'down'} {abs(ni_change):.1f}% YoY). "
        f"Operating margin was {operating_margin_current:.1f}% "
        f"(vs {operating_margin_prior:.1f}% prior year)."
    )
```

### Anti-Patterns to Avoid

- **Returning raw JSON/XBRL to agents:** Violates DATA-08. Always format to natural language summaries first.
- **Using period_of_report instead of filing_date for SEC data:** Causes look-ahead bias. A 10-K with period ending Dec 31 may not be filed until Feb 28 -- filter on `filing_date` (or `accepted_date` in EDGAR terms).
- **Mutating cached price records:** Financial time-series is append-only. If a stock splits, store the new adjusted prices as new rows with the observed_date of when you detected the split; never overwrite historical rows.
- **Calling external APIs without tenacity retry:** SEC EDGAR rate-limits at 10 req/sec, yfinance randomly blocks, Finnhub at 60 req/min. Every HTTP call must have retry + exponential backoff.
- **Making as_of_date optional in tool signatures:** The whole point of DATA-07 is that this is mandatory. No default value, no optional parameter.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SEC filing parsing | Custom EDGAR HTML parser | edgartools TenK/TenQ objects | 20+ form types, section extraction, HTML cleanup handled by library |
| XBRL tag resolution | Manual tag name mapping | edgartools `Company.get_facts()` + archived fallback lists | Companies use different XBRL tags for the same concept; edgartools normalizes this |
| CIK-ticker mapping | Custom SEC scraper | edgartools `Company("AAPL")` or archived `get_cik_ticker_mapping()` | SEC provides company_tickers.json; edgartools wraps it |
| Stock split adjustment | Custom adjustment logic | yfinance `auto_adjust=True` (default) | Split/dividend adjustment is complex; yfinance handles via Yahoo Finance adjusted prices |
| FRED data retrieval | Raw HTTP to FRED API | fredapi `Fred.get_series()` | Returns pandas Series directly, handles pagination and date filtering |
| SEC rate limiting | Custom rate limiter | tenacity + `time.sleep(0.1)` pattern | Archived code shows the exact pattern; SEC allows 10 req/sec |

**Key insight:** The data ingestion layer is deceptively complex not because any single API is hard, but because temporal correctness and caching consistency across six sources simultaneously is where bugs hide. Use proven clients wherever possible; focus engineering effort on the temporal enforcement and summary generation layers.

## Common Pitfalls

### Pitfall 1: Look-Ahead Bias from Filing Date vs Period End Date
**What goes wrong:** Using `period_of_report` (e.g., Dec 31, 2025) instead of `filing_date` (e.g., Feb 28, 2026) when filtering SEC data. This makes data "available" months before it was actually public.
**Why it happens:** XBRL data has both `end` (period end) and `filed` dates. The natural instinct is to use `end` because it represents the fiscal period.
**How to avoid:** All SEC data queries filter on `filing_date <= as_of_date` (for filings) or `filed_date <= as_of_date` (for XBRL facts). The archived XBRLExtractor already stores `filed_date` separately -- use it.
**Warning signs:** Backtests showing unrealistically good performance on earnings dates.

### Pitfall 2: edgartools Section Extraction Returns None for Combined Sections
**What goes wrong:** Some companies file 10-Ks with combined section headings (e.g., "Items 1 and 2" instead of separate "Item 1" and "Item 2"). edgartools returns `None` for the individual items.
**Why it happens:** SEC filing formatting is not standardized -- companies have latitude in how they structure their documents.
**How to avoid:** Always check for `None` sections and fall back to `filing.text()` truncated to a maximum character limit (the archived FilingClient's `_fallback_sections` pattern handles this). Log short/missing sections for monitoring.
**Warning signs:** Many `None` sections in a batch collection run.

### Pitfall 3: yfinance Random Failures and Rate Limiting
**What goes wrong:** yfinance calls fail silently or return empty DataFrames. Yahoo changes endpoints without notice.
**Why it happens:** yfinance is an unofficial scraper, not an official API. Yahoo actively tries to prevent automated access.
**How to avoid:** Cache-once-to-PostgreSQL pattern. Download historical data in bulk once, then serve from cache. Only call yfinance for net-new dates. Implement Tiingo as automatic fallback. Use tenacity retry with exponential backoff.
**Warning signs:** Empty DataFrames, HTTP 429 errors, sudden data gaps.

### Pitfall 4: XBRL Tag Variability Across Companies
**What goes wrong:** Querying for "Revenues" returns empty because a company uses "RevenueFromContractWithCustomerExcludingAssessedTax" instead.
**Why it happens:** The US-GAAP taxonomy allows multiple tags for the same financial concept. Companies choose different ones.
**How to avoid:** Use fallback tag lists per concept (the archived `XBRL_TAG_GROUPS` pattern). Try tags in priority order, use first match. Expand the tag groups from the archive's 3 concepts to cover all required financial metrics (~12 concepts).
**Warning signs:** Many companies returning zero facts for a concept.

### Pitfall 5: Finnhub Rate Limit Exhaustion
**What goes wrong:** Hitting 60 req/min limit during batch collection, getting 429 errors or empty responses.
**Why it happens:** Collecting news for many tickers without rate awareness.
**How to avoid:** Implement a rate limiter (token bucket or simple sleep-based) for Finnhub calls. Cache news to PostgreSQL. Consider FMP as supplementary source for fundamentals if Finnhub budget is tight.
**Warning signs:** 429 HTTP status codes, increasing latency in responses.

### Pitfall 6: Monetary Value Floating Point Errors
**What goes wrong:** Revenue of $1,234,567,890.12 becomes $1,234,567,890.1199... due to IEEE 754 floating point.
**Why it happens:** Storing dollars as floats. XBRL data comes as float dollars.
**How to avoid:** Convert all monetary values to integer cents immediately at the ingestion boundary (`int(value * 100)`). Store as BigInteger in PostgreSQL. Only convert back to dollars for display/summary formatting.
**Warning signs:** Numbers not matching source within rounding tolerance.

### Pitfall 7: Duplicate Records on Re-Ingestion
**What goes wrong:** Running the data collection pipeline twice inserts duplicate rows.
**Why it happens:** Append-only tables without idempotency guards.
**How to avoid:** Use unique constraints (e.g., `(ticker, trade_date)` for prices, `(ticker, accession_no)` for filings) and `INSERT ... ON CONFLICT DO NOTHING`. The archived models show this pattern with `uq_sec_filings_company_form_accession`.
**Warning signs:** Row counts growing unexpectedly, duplicate entries in query results.

## Code Examples

### SEC Filing Section Retrieval (edgartools)
```python
# Source: edgartools docs + archived FilingClient pattern
# [VERIFIED: edgartools GitHub README, PyPI 5.28.5]
import edgar
from edgar import Company

def get_filing_sections(
    ticker: str,
    form_type: str,
    edgar_identity: str,
    max_filings: int = 5,
) -> list[dict]:
    """Retrieve SEC filing sections using edgartools.

    Returns list of dicts with filing metadata and section text.
    Uses bracket-notation access for section extraction.
    """
    edgar.set_identity(edgar_identity)
    company = Company(ticker)
    filings = company.get_filings(form=form_type).head(max_filings)

    results = []
    for filing in filings:
        obj = filing.obj()
        sections = {}

        if form_type == "10-K":
            sections["business"] = _safe_section(obj, "Item 1")
            sections["risk_factors"] = _safe_section(obj, "Item 1A")
            sections["mda"] = _safe_section(obj, "Item 7")
        elif form_type == "10-Q":
            sections["mda"] = _safe_section(obj, "part1item2")

        # Fallback for missing sections
        if all(v is None for v in sections.values()):
            try:
                sections["full_text"] = filing.text()[:50000]
            except Exception:
                pass

        results.append({
            "accession_no": filing.accession_no,
            "filing_date": str(filing.filing_date),
            "form_type": form_type,
            "sections": sections,
        })

    return results


def _safe_section(obj: object, key: str) -> str | None:
    """Safely extract a section, returning None on failure."""
    try:
        text = obj[key]
        return str(text) if text is not None else None
    except (KeyError, IndexError, TypeError, Exception):
        return None
```

### XBRL Financial Data Extraction (CompanyFacts API)
```python
# Source: Archived xbrl_extractor.py + SEC CompanyFacts API docs
# [VERIFIED: data.sec.gov API, archived code]

# Expanded tag groups for fund-relevant financial concepts
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
```

### Form 4 Insider Trade Cluster Detection
```python
# Source: edgartools Form 4 docs + project requirement (DATA-04)
# [VERIFIED: edgartools README, search results for Form 4 API]
from __future__ import annotations

from datetime import date, timedelta
from dataclasses import dataclass


@dataclass(frozen=True)
class InsiderCluster:
    """A cluster of insider purchases within a time window."""
    ticker: str
    insiders: list[str]
    total_shares: int
    total_value_cents: int
    start_date: date
    end_date: date
    cluster_size: int


def detect_purchase_clusters(
    purchases: list[dict],
    window_days: int = 14,
    min_insiders: int = 3,
) -> list[InsiderCluster]:
    """Detect clusters of insider purchases within a rolling window.

    A cluster is defined as min_insiders or more distinct insiders
    making purchases within window_days of each other.
    """
    # Sort by date
    sorted_purchases = sorted(purchases, key=lambda p: p["trade_date"])

    clusters = []
    for i, anchor in enumerate(sorted_purchases):
        window_end = anchor["trade_date"] + timedelta(days=window_days)
        window_purchases = [
            p for p in sorted_purchases[i:]
            if p["trade_date"] <= window_end
        ]
        unique_insiders = {p["insider_name"] for p in window_purchases}

        if len(unique_insiders) >= min_insiders:
            clusters.append(InsiderCluster(
                ticker=anchor["ticker"],
                insiders=list(unique_insiders),
                total_shares=sum(p["shares"] for p in window_purchases),
                total_value_cents=sum(p["value_cents"] for p in window_purchases),
                start_date=anchor["trade_date"],
                end_date=max(p["trade_date"] for p in window_purchases),
                cluster_size=len(unique_insiders),
            ))

    # Deduplicate overlapping clusters (keep largest)
    return _deduplicate_clusters(clusters)
```

### FRED Macro Data Retrieval
```python
# Source: fredapi docs + FRED series ID verification
# [VERIFIED: fredapi PyPI, FRED series pages]

# Key FRED series for macro context
FRED_SERIES: dict[str, dict[str, str]] = {
    "fed_funds_rate": {
        "series_id": "FEDFUNDS",
        "description": "Federal Funds Effective Rate",
        "frequency": "monthly",
    },
    "cpi": {
        "series_id": "CPIAUCSL",
        "description": "Consumer Price Index for All Urban Consumers",
        "frequency": "monthly",
    },
    "gdp": {
        "series_id": "GDP",
        "description": "Gross Domestic Product (nominal)",
        "frequency": "quarterly",
    },
    "real_gdp": {
        "series_id": "GDPC1",
        "description": "Real Gross Domestic Product",
        "frequency": "quarterly",
    },
    "yield_curve_spread": {
        "series_id": "T10Y2Y",
        "description": "10-Year minus 2-Year Treasury Spread",
        "frequency": "daily",
    },
    "treasury_10y": {
        "series_id": "DGS10",
        "description": "10-Year Treasury Constant Maturity",
        "frequency": "daily",
    },
    "treasury_2y": {
        "series_id": "DGS2",
        "description": "2-Year Treasury Constant Maturity",
        "frequency": "daily",
    },
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| edgartools 4.x | edgartools 5.x (5.28.5) | 2025 | Breaking API changes in 5.0; `Company.get_financials()` and `Company.get_facts()` are new; MCP server for AI integration |
| yfinance 0.2.x | yfinance 1.2.x | 2024 | Major version bump; improved caching, new Ticker API; still unofficial and fragile |
| SEC EDGAR submissions.json | data.sec.gov CompanyFacts + Frames API | 2023+ | Structured XBRL data via REST; real-time updates; 10 req/sec limit |
| fredapi + raw HTTP | fredapi 0.5.x | Stable since 2022 | Minimal changes; well-established API; ALFRED support for historical revisions |

**Deprecated/outdated:**
- **sec-edgar-downloader:** Superseded by edgartools for structured data access
- **EDGAR full-text search API (EFTS):** Still works but edgartools wraps it
- **yfinance `data_reader`:** Use `yf.download()` or `Ticker.history()` instead

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Tiingo free tier allows 50 symbols/hour and 100 requests/day | Standard Stack | If limits are lower, fallback may not cover yfinance failures for large ticker universes; would need to batch over multiple hours |
| A2 | edgartools 5.28.x `Company.get_facts()` returns CompanyFacts with `to_pandas()` for any us-gaap concept | Code Examples (XBRL) | If API changed, may need to fall back to direct CompanyFacts HTTP client (archived pattern still works) |
| A3 | edgartools Form 4 `.obj().transactions` provides structured insider trade data with shares and value | Code Examples (Form 4) | If Form 4 parsing is less structured, may need to parse Form 4 XML directly via EDGAR |
| A4 | FMP free tier (250 calls/day) is adequate as supplementary data source | Standard Stack | Not critical -- FMP is supplementary, not primary; all primary sources are verified |
| A5 | finnhub-python SDK handles auth header injection automatically | Standard Stack | If not, simple httpx client with API key header works (trivial fix) |

## Open Questions

1. **Tiingo API key availability**
   - What we know: Tiingo requires a free API key for access; free tier is limited
   - What's unclear: Whether the user has already signed up for a Tiingo API key
   - Recommendation: Add `TIINGO_API_KEY` to AppSettings; if not configured, log warning and disable Tiingo fallback (yfinance-only mode)

2. **Ticker universe size for initial data collection**
   - What we know: yfinance and Finnhub have rate limits; bulk collection is needed
   - What's unclear: How many tickers the system needs to support in v1
   - Recommendation: Design for configurable universe (default: S&P 500 or a smaller watchlist); batch collection with progress tracking

3. **Alembic migration strategy**
   - What we know: Phase 1 db/ has no migrations directory yet; db/base.py has Base
   - What's unclear: Whether to `alembic init` in Phase 2 or assume it was done in Phase 1
   - Recommendation: Phase 2 should initialize Alembic if not present and create the first migration for all data tables

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.12.11 | -- |
| uv | Package management | Yes | 0.11.2 | -- |
| Docker | PostgreSQL | Yes | 29.0.1 | -- |
| PostgreSQL (via Docker) | Data caching | Yes (docker-compose.yml) | 16-alpine | -- |
| SEC EDGAR API | DATA-01, DATA-02, DATA-04 | Yes (public, no key) | -- | -- |
| FRED API key | DATA-06 | Unknown (needs .env) | -- | Data source disabled with warning |
| Finnhub API key | DATA-05 | Unknown (needs .env) | -- | Data source disabled with warning |
| Tiingo API key | DATA-03 fallback | Unknown (needs .env) | -- | yfinance only (no fallback) |
| EDGAR_IDENTITY | DATA-01 | Unknown (needs .env) | -- | SEC blocks requests without User-Agent |

**Missing dependencies with no fallback:**
- `EDGAR_IDENTITY` -- SEC requires User-Agent string for all requests. Without it, all EDGAR calls fail. Must be configured before any data collection.

**Missing dependencies with fallback:**
- `FRED_API_KEY` -- Without it, macro data (DATA-06) is unavailable but other sources work fine
- `FINNHUB_API_KEY` -- Without it, news/sentiment (DATA-05) is unavailable but other sources work fine
- `TIINGO_API_KEY` -- Without it, price fallback (DATA-03) degrades to yfinance-only

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 9.0 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/ -x -q` |
| Full suite command | `uv run pytest tests/ -x --cov=ai_hedge_fund --cov-report=term-missing` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Filing sections retrieved by ticker + as_of_date, filtered by filing_date | unit | `uv run pytest tests/unit/test_filing_tools.py -x` | Wave 0 |
| DATA-02 | XBRL facts extracted + formatted as NL summary with YoY/QoQ | unit | `uv run pytest tests/unit/test_financial_tools.py -x` | Wave 0 |
| DATA-03 | Price data served from PostgreSQL cache; Tiingo fallback tested | unit + integration | `uv run pytest tests/unit/test_price_tools.py tests/integration/test_price_cache.py -x` | Wave 0 |
| DATA-04 | Insider cluster detection (3+ insiders, 14-day window) | unit | `uv run pytest tests/unit/test_insider_tools.py -x` | Wave 0 |
| DATA-05 | Daily news sentiment summary per ticker with as_of_date filter | unit | `uv run pytest tests/unit/test_sentiment_tools.py -x` | Wave 0 |
| DATA-06 | Macro indicators (Fed Funds, CPI, GDP, yield curve) retrievable | unit | `uv run pytest tests/unit/test_macro_tools.py -x` | Wave 0 |
| DATA-07 | Calling any tool without as_of_date raises ValueError | unit | `uv run pytest tests/unit/test_temporal.py -x` | Wave 0 |
| DATA-08 | Structured data converted to NL summaries (not raw JSON) | unit | `uv run pytest tests/unit/test_summary.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -x --cov=ai_hedge_fund --cov-report=term-missing`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_filing_tools.py` -- covers DATA-01
- [ ] `tests/unit/test_financial_tools.py` -- covers DATA-02
- [ ] `tests/unit/test_price_tools.py` -- covers DATA-03
- [ ] `tests/unit/test_insider_tools.py` -- covers DATA-04
- [ ] `tests/unit/test_sentiment_tools.py` -- covers DATA-05
- [ ] `tests/unit/test_macro_tools.py` -- covers DATA-06
- [ ] `tests/unit/test_temporal.py` -- covers DATA-07 (as_of_date enforcement)
- [ ] `tests/unit/test_summary.py` -- covers DATA-08 (NL formatting)
- [ ] `tests/unit/test_data_models.py` -- covers DB models
- [ ] `tests/integration/test_price_cache.py` -- covers DATA-03 cache + fallback
- [ ] `tests/conftest.py` update -- add fixtures for mock data, db session
- [ ] Framework install: `uv add pytest-httpx` -- mock external API calls in tests

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A (no user auth in data layer) |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A (internal tool layer, no user-facing endpoints) |
| V5 Input Validation | Yes | Pydantic schemas for all data inputs; `as_of_date` type validation; ticker format validation |
| V6 Cryptography | No | N/A (no encryption needed for public financial data) |

### Known Threat Patterns for Data Ingestion

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key exposure in logs | Information Disclosure | structlog processor to redact API keys; keys in .env only |
| SEC rate limit violation | Denial of Service (self-inflicted) | tenacity + sleep(0.1) for 10 req/sec SEC limit |
| Look-ahead bias in data | Tampering (data integrity) | Mandatory as_of_date enforcement; filing_date filtering |
| SQL injection via ticker input | Tampering | SQLAlchemy parameterized queries (never raw SQL strings) |
| yfinance returning stale/incorrect data | Tampering (data integrity) | Cross-validate with Tiingo fallback; content hash for dedup |

## Sources

### Primary (HIGH confidence)
- [edgartools PyPI](https://pypi.org/project/edgartools/) -- v5.28.5 verified, section extraction API confirmed
- [edgartools GitHub](https://github.com/dgunning/edgartools) -- Form 4 support, Company.get_facts(), bracket-notation sections
- [edgartools Form 4 guide](https://edgartools.readthedocs.io/en/stable/guides/track-form4/) -- insider trade parsing patterns
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) -- CompanyFacts API, 10 req/sec rate limit
- [yfinance PyPI](https://pypi.org/project/yfinance/) -- v1.2.1 verified
- [fredapi PyPI](https://pypi.org/project/fredapi/) -- v0.5.2 verified
- [FRED API docs](https://fred.stlouisfed.org/docs/api/fred/) -- series IDs verified
- [finnhub-python PyPI](https://pypi.org/project/finnhub-python/) -- v2.4.27 verified
- [tiingo PyPI](https://pypi.org/project/tiingo/) -- v0.16.1 verified

### Secondary (MEDIUM confidence)
- [Tiingo pricing page](https://www.tiingo.com/pricing) -- free tier limits (50 symbols/hr, 100 req/day)
- [Finnhub rate limits](https://finnhub.io/docs/api/rate-limit) -- 60 req/min free tier confirmed
- [FMP pricing](https://site.financialmodelingprep.com/pricing-plans) -- 250 calls/day free tier

### Tertiary (LOW confidence)
- [yfinance reliability concerns](https://medium.com/@trading.dude/why-yfinance-keeps-getting-blocked-and-what-to-use-instead-92d84bb2cc01) -- community reports of blocking and breakage (general sentiment, not specific to current version)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all library versions verified on PyPI, APIs confirmed via official docs
- Architecture: HIGH -- patterns derived from archived working code + project conventions in CLAUDE.md
- Pitfalls: HIGH -- identified from archived code experience + known yfinance fragility + SEC XBRL tag variability
- XBRL tag groups: MEDIUM -- expanded from 3 concepts to 12 based on common us-gaap tags; tag names verified against SEC taxonomy but actual availability varies by company

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (stable APIs with well-established patterns; edgartools is the fast-moving piece with weekly releases)
