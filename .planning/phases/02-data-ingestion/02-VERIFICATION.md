---
phase: 02-data-ingestion
verified: 2026-04-12T09:00:00Z
status: human_needed
score: 8/8 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Call get_filing_sections for AAPL with a real EDGAR_IDENTITY env var and as_of_date in the past. Confirm it returns sections and none of the filing dates exceed as_of_date."
    expected: "List of dicts with form_type, filing_date <= as_of_date, and non-empty sections dict"
    why_human: "Requires live SEC EDGAR connection; tenacity retry and rate-limit compliance cannot be verified without real network I/O"
  - test: "Trigger yfinance failure (e.g., pass an invalid ticker with a Tiingo key configured) and confirm the fallback to Tiingo is logged and succeeds."
    expected: "PriceClient.download returns data from source='tiingo'; structlog warning emitted for yfinance failure"
    why_human: "Requires real network calls to both APIs and the ability to simulate one failing; cannot deterministically trigger in unit tests without integration setup"
  - test: "Run get_macro_context with a real FRED_API_KEY and a past as_of_date. Confirm returned indicators dict has no future observations."
    expected: "All series values in indicators are from observations on or before as_of_date; summary_text is non-empty prose"
    why_human: "Requires live FRED API key; temporal filtering of real multi-frequency time series data cannot be verified from a mock"
---

# Phase 02: Data Ingestion Verification Report

**Phase Goal:** Agents can query any of the fund's data sources and receive pre-processed, temporally-correct financial data -- so research agents never touch raw APIs and never see future data
**Verified:** 2026-04-12T09:00:00Z
**Status:** human_needed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | Calling any data tool function without as_of_date raises ValueError | VERIFIED | `normalize_as_of_date` raises ValueError when `as_of_date is None`; `@enforce_as_of_date` wraps all 6 tool functions. 13 temporal unit tests pass. |
| 2  | as_of_date in the future raises ValueError | VERIFIED | `normalize_as_of_date` checks `as_of_date > date.today()` and raises ValueError with descriptive message. |
| 3  | datetime as_of_date is converted to date | VERIFIED | `normalize_as_of_date` detects `isinstance(as_of_date, datetime)` and calls `.date()`. Test passes confirming conversion. |
| 4  | Structured financial data can be formatted to natural language prose | VERIFIED | 5 formatter functions exist in `summary.py` and are tested (12 summary tests pass). All produce readable sentences. |
| 5  | Database tables exist for filings, XBRL facts, prices, insider trades, news, macro data | VERIFIED | 6 SQLAlchemy model classes present in `models.py`, all inheriting `DualTimestampMixin`. Alembic migration `001_create_data_ingestion_tables.py` creates all 6 tables. 25 model tests pass. |
| 6  | All data tables use append-only pattern with dual timestamps | VERIFIED | Every model class inherits `Base, DualTimestampMixin` providing `as_of_date` and `observed_date`. Unique constraints prevent overwrite. |
| 7  | Filings with filing_date after as_of_date are excluded from results | VERIFIED | `EdgarClient.get_filing_sections` filters `filing_date > filing_date_cutoff` with `continue`; `Form4Client.get_insider_trades` + tool filter `filing_date <= as_of_date`. Test confirms exclusion. |
| 8  | Equity price data is served from PostgreSQL cache first; yfinance is fallback | VERIFIED | `get_price_history` queries `DailyPrice` table; uses external API only when cache returns <80% of expected trading days. `PriceClient.download` tries yfinance then Tiingo. 24 price tests pass. |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/ai_hedge_fund/data/temporal.py` | enforce_as_of_date decorator, normalize_as_of_date | VERIFIED | Both functions exist; sync+async wrapper; 74 lines; substantive |
| `src/ai_hedge_fund/data/summary.py` | 5 NL formatters for financial data | VERIFIED | All 5 formatters exist (`format_financial_summary`, `format_price_summary`, `format_insider_summary`, `format_news_summary`, `format_macro_summary`) plus `_format_dollars` helper; 302 lines |
| `src/ai_hedge_fund/db/models.py` | 6 SQLAlchemy models with DualTimestampMixin | VERIFIED | SecFiling, XbrlFact, DailyPrice, InsiderTrade, NewsArticle, MacroIndicator -- all 6 present with UniqueConstraints |
| `alembic/versions/001_create_data_ingestion_tables.py` | Initial migration for all 6 tables | VERIFIED | Hand-written migration creates all 6 tables with matching columns and constraints; `downgrade()` implemented |
| `src/ai_hedge_fund/data/clients/edgar_client.py` | EdgarClient with section extraction | VERIFIED | `EdgarClient`, `get_filings`, `get_filing_sections`, `_safe_section`; tenacity retry; filing_date filtering present |
| `src/ai_hedge_fund/data/clients/xbrl_client.py` | XbrlClient with 12-concept tag fallback | VERIFIED | `XbrlClient`, `XBRL_TAG_GROUPS` (12 concepts confirmed), `MONETARY_CONCEPTS` (frozenset), filed_date filtering |
| `src/ai_hedge_fund/data/tools/filing_tools.py` | get_filing_sections with as_of_date enforcement | VERIFIED | `@enforce_as_of_date` applied; edgar_identity validation; SecFiling caching present |
| `src/ai_hedge_fund/data/tools/financial_tools.py` | get_financial_summary with NL output | VERIFIED | `@enforce_as_of_date` applied; calls `format_financial_summary`; XbrlFact caching present |
| `src/ai_hedge_fund/data/clients/price_client.py` | PriceClient with yfinance+Tiingo fallback | VERIFIED | `PriceClient`, `download_yfinance` (tenacity retry), `download_tiingo`, `PriceDownloadError`; `_dollars_to_cents` helper |
| `src/ai_hedge_fund/data/clients/form4_client.py` | Form4Client with InsiderCluster detection | VERIFIED | `Form4Client`, `detect_purchase_clusters`, `InsiderCluster` frozen dataclass (tuple insiders), `_deduplicate_clusters` |
| `src/ai_hedge_fund/data/tools/price_tools.py` | get_price_history with cache-first pattern | VERIFIED | `@enforce_as_of_date`; DailyPrice cache check; 80% threshold logic; `format_price_summary` called |
| `src/ai_hedge_fund/data/tools/insider_tools.py` | get_insider_clusters with as_of_date filter | VERIFIED | `@enforce_as_of_date`; filing_date filter; `format_insider_summary` called; InsiderTrade caching |
| `src/ai_hedge_fund/data/clients/finnhub_client.py` | FinnhubClient with news and sentiment | VERIFIED | `FinnhubClient`, `get_company_news` (tenacity retry, empty list on error), `get_news_sentiment`; api_key validation on init |
| `src/ai_hedge_fund/data/clients/fred_client.py` | FredClient with 7 FRED series | VERIFIED | `FredClient`, `FRED_SERIES` (7 entries confirmed), `get_series`, `get_latest_values`, `compute_cpi_yoy`, `compute_gdp_growth` |
| `src/ai_hedge_fund/data/tools/sentiment_tools.py` | get_news_sentiment with temporal filter | VERIFIED | `@enforce_as_of_date`; published_date cutoff filter; None-sentinel replacement before formatter; NewsArticle caching |
| `src/ai_hedge_fund/data/tools/macro_tools.py` | get_macro_context with FRED integration | VERIFIED | `@enforce_as_of_date`; FredClient instantiated; `format_macro_summary` called; MacroIndicator caching |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----| ----|--------|---------|
| `filing_tools.py` | `edgar_client.py` | `EdgarClient` instance | WIRED | `EdgarClient(resolved_settings.edgar_identity)` instantiated; `.get_filing_sections()` called |
| `filing_tools.py` | `temporal.py` | `@enforce_as_of_date` | WIRED | Decorator applied at function definition |
| `financial_tools.py` | `summary.py` | `format_financial_summary` | WIRED | Imported and called in `_build_summary_text` |
| `financial_tools.py` | `xbrl_client.py` | `XbrlClient` instance | WIRED | `XbrlClient(resolved_settings.edgar_identity)` instantiated; `.get_financial_metrics()` called |
| `price_tools.py` | `price_client.py` | `PriceClient` instance | WIRED | `PriceClient(tiingo_api_key=settings.tiingo_api_key)` instantiated; `.download()` called on cache miss |
| `price_tools.py` | `models.py` (DailyPrice) | DailyPrice cache read/write | WIRED | `_query_cached_prices` queries `DailyPrice`; `_store_prices` writes to it |
| `insider_tools.py` | `form4_client.py` | `Form4Client` + `detect_purchase_clusters` | WIRED | Both imported; `Form4Client.get_insider_trades()` called; `detect_purchase_clusters()` called on filtered trades |
| `sentiment_tools.py` | `finnhub_client.py` | `FinnhubClient` instance | WIRED | `FinnhubClient(api_key=resolved_settings.finnhub_api_key)` instantiated; `.get_company_news()` called |
| `sentiment_tools.py` | `summary.py` | `format_news_summary` | WIRED | Imported and called with None-sentinel replacement |
| `macro_tools.py` | `fred_client.py` | `FredClient` instance | WIRED | `FredClient(api_key=resolved_settings.fred_api_key)` instantiated; all compute methods called |
| `macro_tools.py` | `summary.py` | `format_macro_summary` | WIRED | Imported and called in `_build_summary` |
| `data/tools/__init__.py` | all 6 tool functions | re-exports | WIRED | All 6 tools exported in `__all__` |

### Data-Flow Trace (Level 4)

All tool functions return data derived from external API calls (mocked in tests) through the following chains. The tools do not render to a UI -- they return dicts for agent consumption.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `get_filing_sections` | `results` | `EdgarClient.get_filing_sections()` → edgartools | Yes (mocked in tests, real API path wired) | VERIFIED |
| `get_financial_summary` | `metrics` | `XbrlClient.get_financial_metrics()` → XBRL CompanyFacts | Yes (filed_date filtered, cents converted) | VERIFIED |
| `get_price_history` | `prices` | DailyPrice cache OR `PriceClient.download()` → yfinance/Tiingo | Yes (cache-first, adj_close_cents computed) | VERIFIED |
| `get_insider_clusters` | `clusters` | `Form4Client.get_insider_trades()` + `detect_purchase_clusters()` | Yes (filing_date filtered, cluster algo run) | VERIFIED |
| `get_news_sentiment` | `filtered_articles` | `FinnhubClient.get_company_news()` → Finnhub | Yes (published_date filtered post-retrieval) | VERIFIED |
| `get_macro_context` | `indicators` | `FredClient.get_latest_values()` → FRED API | Yes (observation_end=as_of_date passed) | VERIFIED |

### Behavioral Spot-Checks

The codebase has no runnable HTTP server or standalone CLI entry points at Phase 2. All behaviors are exercised via pytest with mocked APIs.

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Temporal enforcement raises on None | `uv run pytest tests/unit/test_temporal.py -q` | 13 passed | PASS |
| NL formatter produces prose | `uv run pytest tests/unit/test_summary.py -q` | 12 passed | PASS |
| DB models create via SQLite | `uv run pytest tests/unit/test_data_models.py -q` | 25 passed | PASS |
| Filing tools with mocked EDGAR | `uv run pytest tests/unit/test_filing_tools.py -q` | 12 passed | PASS |
| Financial tools with mocked XBRL | `uv run pytest tests/unit/test_financial_tools.py -q` | 10 passed | PASS |
| Price tools with cache-first | `uv run pytest tests/unit/test_price_tools.py -q` | 24 passed | PASS |
| Insider cluster detection | `uv run pytest tests/unit/test_insider_tools.py -q` | 18 passed | PASS |
| News sentiment with date filter | `uv run pytest tests/unit/test_sentiment_tools.py -q` | 17 passed | PASS |
| Macro context from FRED | `uv run pytest tests/unit/test_macro_tools.py -q` | 19 passed | PASS |
| **Full unit suite** | `uv run pytest tests/unit/ -q` | **150 passed** | PASS |
| Ruff lint clean | `uv run ruff check src/ai_hedge_fund/data/ src/ai_hedge_fund/db/models.py` | All checks passed | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| DATA-01 | 02-02 | SEC EDGAR integration for 10-K, 10-Q, 8-K filings with section-level chunking | SATISFIED | `EdgarClient.get_filing_sections` extracts Item 1/1A/7 (10-K) and part1item2 (10-Q); fallback to 50k-char truncated full text |
| DATA-02 | 02-02 | XBRL financial data extraction via CompanyFacts API with pre-computed metric summaries | SATISFIED | `XbrlClient` with 12-concept `XBRL_TAG_GROUPS`, tag fallback, cents conversion, `get_financial_summary` produces NL output |
| DATA-03 | 02-03 | Equity price data ingestion (yfinance with PostgreSQL caching, Tiingo fallback) | SATISFIED | `PriceClient` downloads yfinance → Tiingo; `DailyPrice` cache-first in `get_price_history`; `adj_close_cents` used for returns |
| DATA-04 | 02-03 | Insider trade detection from SEC Form 4 filings with cluster buy identification | SATISFIED | `Form4Client` parses Form 4; `detect_purchase_clusters` sliding window algorithm (3+ insiders, 14-day window, dedup) |
| DATA-05 | 02-04 | News and sentiment aggregation from Finnhub with daily per-ticker summaries | SATISFIED | `FinnhubClient.get_company_news`; `get_news_sentiment` filters by `published_date <= as_of_date`; NL digest via `format_news_summary` |
| DATA-06 | 02-04 | Macro context from FRED (interest rates, CPI, GDP, yield curve) | SATISFIED | `FredClient` with 7 FRED series (FEDFUNDS, CPIAUCSL, GDP, GDPC1, T10Y2Y, DGS10, DGS2); CPI YoY and GDP growth computed |
| DATA-07 | 02-01 | Strict temporal controls -- every data input timestamped, RAG filtered by "available as of" date | SATISFIED | `enforce_as_of_date` decorator on all 6 tool functions; `normalize_as_of_date` validates and converts; filing_date/published_date filtering in each client |
| DATA-08 | 02-01, 02-02, 02-03, 02-04 | Natural language summaries generated from structured data before LLM consumption | SATISFIED | All 5 formatters in `summary.py`; every tool function returns `summary_text` as NL prose; raw XBRL/JSON never returned directly to agents |

**All 8 required DATA requirements satisfied.**

No orphaned requirements -- REQUIREMENTS.md maps DATA-01 through DATA-08 to Phase 2, and all 8 appear in plans 02-01 through 02-04.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `financial_tools.py:203` | `cik: ""` hardcoded in `XbrlFact` record on cache write | Info | CIK is not available from the metrics dict returned by `get_financial_metrics`; the code includes a comment acknowledging this. CIK is populated in the full pipeline. Does not affect agent consumption of the summary. |
| `sentiment_tools.py:136` | `as_of_date=date.today()` in `NewsArticle` record instead of the tool's `as_of_date` | Warning | The cached record stores today's date as `as_of_date` rather than the tool's temporal parameter. This is a minor inconsistency -- the article content is still correct, but the model's `as_of_date` field will not match the tool call's temporal context for historical queries. |

Neither anti-pattern prevents the phase goal. The second is a low-severity data quality concern for the caching path.

### Human Verification Required

The following cannot be verified programmatically (require live API connections or real-time behavior):

#### 1. SEC EDGAR Live Temporal Filtering

**Test:** With `EDGAR_IDENTITY` configured, call `get_filing_sections("AAPL", as_of_date=date(2023, 6, 30))` against real SEC EDGAR. Inspect all returned `filing_date` values.
**Expected:** Every filing in the result has `filing_date <= 2023-06-30`. No future filings appear. At least one 10-K with sections (business, risk_factors, mda) is returned.
**Why human:** Requires a live EDGAR connection with a valid identity string. Tenacity rate-limit compliance and actual SEC 10 req/sec behavior cannot be verified in unit tests.

#### 2. yfinance Failure → Tiingo Fallback

**Test:** Configure a valid `TIINGO_API_KEY`. Force yfinance to fail (e.g., pass a valid ticker but set `start_date` to a date where yfinance returns an empty DataFrame). Call `PriceClient.download(ticker, start_date, end_date)`.
**Expected:** A warning is logged (`"yfinance returned empty data for ... trying Tiingo"` or `"yfinance failed for ... trying Tiingo"`). Data is returned with `source="tiingo"`.
**Why human:** Requires real API keys for both sources and the ability to reproducibly trigger yfinance failure in a live environment. Unit tests mock both clients independently.

#### 3. FRED API Temporal Boundary

**Test:** With `FRED_API_KEY` configured, call `get_macro_context(as_of_date=date(2022, 1, 1))`. Examine all values in `indicators`.
**Expected:** All indicator values are from FRED observations on or before 2022-01-01. For example, `fed_funds_rate` should reflect the rate as of early 2022 (~0.08%), not a recent value.
**Why human:** Requires a live FRED API key. The temporal filtering logic (`observation_end=as_of_date` + belt-and-suspenders `series[series.index <= cutoff]`) needs verification against real multi-frequency Federal Reserve data.

---

## Summary

Phase 2 goal is **effectively achieved** -- the full data ingestion pipeline is implemented and tested:

- All 6 tool functions enforce `as_of_date` via `@enforce_as_of_date` (DATA-07)
- All 6 clients filter data by filing_date/published_date/observation_date to prevent look-ahead bias
- All 5 NL formatters convert structured data to prose for LLM consumption (DATA-08)
- All 6 SQLAlchemy models with dual timestamps and unique constraints support append-only caching
- 150 unit tests pass across the full module; ruff lint is clean

The 3 human verification items are required to confirm live API temporal correctness and the yfinance→Tiingo fallback under real network conditions. One warning-level anti-pattern exists in `sentiment_tools.py` (caching `date.today()` as `as_of_date` instead of the tool parameter) that should be addressed before the caching path is relied upon for historical analysis.

---

_Verified: 2026-04-12T09:00:00Z_
_Verifier: Claude (gsd-verifier)_
