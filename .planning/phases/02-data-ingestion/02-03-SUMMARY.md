---
phase: 02-data-ingestion
plan: 03
subsystem: equity-prices-insider-trades
tags: [yfinance, tiingo, form4, insider-clusters, cache-first, temporal-enforcement]
dependency_graph:
  requires: [02-01]
  provides: [price-client, form4-client, price-tools, insider-tools]
  affects: [02-04, 03-agents]
tech_stack:
  added: []
  patterns: [cache-first-pattern, yfinance-tiingo-fallback, sliding-window-cluster-detection, cents-as-int]
key_files:
  created:
    - src/ai_hedge_fund/data/clients/__init__.py
    - src/ai_hedge_fund/data/clients/price_client.py
    - src/ai_hedge_fund/data/clients/form4_client.py
    - src/ai_hedge_fund/data/tools/__init__.py
    - src/ai_hedge_fund/data/tools/price_tools.py
    - src/ai_hedge_fund/data/tools/insider_tools.py
    - tests/unit/test_price_tools.py
    - tests/unit/test_insider_tools.py
  modified: []
decisions:
  - Used check-before-insert pattern instead of SQL ON CONFLICT for SQLite test compatibility
  - Used datetime.UTC alias per ruff UP017 (Python 3.11+ style)
  - Import datetime module as dt to avoid collision with date/datetime type names in form4_client
metrics:
  duration: 14m
  completed: "2026-04-12T08:09:45Z"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 42
  files_created: 8
  files_modified: 0
---

# Phase 02 Plan 03: Equity Prices and Insider Trade Cluster Detection Summary

PriceClient with yfinance primary and Tiingo automatic fallback, cache-first DailyPrice pattern, Form4Client with edgartools for SEC insider trade parsing, and sliding-window cluster detection algorithm (3+ insiders in 14 days).

## Completed Tasks

| # | Name | Commit | Tests |
|---|------|--------|-------|
| 1 | Price client (yfinance + Tiingo fallback) and price retrieval tools | 0335283 | 24 |
| 2 | Form 4 insider trade client and cluster detection tools | pending | 18 |

## Key Artifacts

### PriceClient (`src/ai_hedge_fund/data/clients/price_client.py`)
- `PriceClient(tiingo_api_key="")` -- downloads OHLCV from yfinance, falls back to Tiingo on failure
- `download_yfinance()` -- tenacity retry (3 attempts, exponential backoff), converts DataFrame to cents dicts
- `download_tiingo()` -- TiingoClient wrapper, raises PriceDownloadError if no API key
- `download()` -- tries yfinance first, logs warning and falls back to Tiingo, raises PriceDownloadError if both fail
- `PriceDownloadError` -- custom exception for both-sources-failed case
- `_dollars_to_cents()` -- `int(round(value * 100))` conversion for financial precision

### Price Tools (`src/ai_hedge_fund/data/tools/price_tools.py`)
- `@enforce_as_of_date get_price_history(ticker, as_of_date, lookback_days=252, db_session, settings)` -- cache-first pattern
- Cache check: queries DailyPrice table, uses cached data if >80% of expected trading days present
- Cache miss: downloads via PriceClient, stores to DailyPrice with check-before-insert (emulates ON CONFLICT DO NOTHING)
- Computes: period return %, annualized volatility (log returns * sqrt(252)), 52w high/low, avg volume
- Returns: `{ticker, prices: list[dict], summary_text: str, stats: dict}`
- Summary generated via `format_price_summary()` from Plan 01

### Form4Client (`src/ai_hedge_fund/data/clients/form4_client.py`)
- `Form4Client(edgar_identity)` -- parses Form 4 filings via edgartools `Company(ticker).get_filings(form="4")`
- `get_insider_trades(ticker, max_filings=50)` -- extracts purchase transactions, converts to cents
- Handles edge cases: missing prices (None), non-standard transaction codes, parse failures (logged, skipped)
- `detect_purchase_clusters(purchases, window_days=14, min_insiders=3)` -- sliding window algorithm
- `InsiderCluster` -- frozen dataclass with tuple insiders (immutable per CLAUDE.md)
- `_deduplicate_clusters()` -- keeps largest cluster when overlapping, tracks used insiders

### Insider Tools (`src/ai_hedge_fund/data/tools/insider_tools.py`)
- `@enforce_as_of_date get_insider_clusters(ticker, as_of_date, lookback_days=90, window_days=14, min_insiders=3, db_session, settings)`
- Filters by `filing_date <= as_of_date` (T-02-12 threat mitigation -- temporal correctness)
- Filters by `trade_date >= as_of_date - lookback_days`
- Returns "No significant insider activity" when no clusters found
- Caches trades to InsiderTrade table when db_session provided
- Returns: `{ticker, clusters: list[dict], summary_text: str}`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DualTimestampMixin as_of_date NOT NULL constraint**
- **Found during:** Task 1, TDD GREEN
- **Issue:** DailyPrice model inherits DualTimestampMixin which requires as_of_date (NOT NULL). Test fixtures and _store_prices omitted this field.
- **Fix:** Set as_of_date to UTC datetime of trade_date in both test fixtures and _store_prices implementation
- **Files modified:** tests/unit/test_price_tools.py, src/ai_hedge_fund/data/tools/price_tools.py

**2. [Rule 1 - Bug] Cache threshold math -- insufficient test data**
- **Found during:** Task 1, TDD GREEN
- **Issue:** Test seeded 200 calendar days but expected_trading_days threshold was 144 (80% of 180). With weekend filtering, only ~142 trading days were generated, falling below threshold.
- **Fix:** Increased test data range to 252 calendar days (~180 trading days) to reliably exceed cache threshold
- **Files modified:** tests/unit/test_price_tools.py

**3. [Rule 1 - Bug] Unique constraint collision in temporal filter test**
- **Found during:** Task 1, TDD GREEN
- **Issue:** Test seeded 260 calendar days extending past as_of_date, creating a Jan 13 row that conflicted with the explicit future_price fixture for Jan 13
- **Fix:** Added `if d > as_of: break` guard to stop seeding at the as_of_date boundary
- **Files modified:** tests/unit/test_price_tools.py

## Verification Results

- 42 unit tests passing (24 price + 18 insider)
- ruff check clean on all source and test files
- All tools use `@enforce_as_of_date` decorator
- All monetary values stored as integer cents
- Filing date filtering (not trade date) for temporal correctness

## Self-Check: PASSED
