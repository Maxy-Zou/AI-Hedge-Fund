---
phase: 01-data-foundation
plan: "03"
subsystem: ingestion
tags: [api-client, kalshi, historical-tier, live-tier, cutoff-routing, tenacity, httpx]
dependency_graph:
  requires: [01-01, 01-02]
  provides: [ingestion-client-layer]
  affects: [01-04-pipeline]
tech_stack:
  added: [cryptography>=46.0.0]
  patterns: [dual-client-router, token-bucket-rate-limit, in-process-cache, cursor-pagination, TDD]
key_files:
  created:
    - kalshi-backtest/src/kalshi_backtest/ingestion/cutoff.py
    - kalshi-backtest/src/kalshi_backtest/ingestion/client.py
    - kalshi-backtest/src/kalshi_backtest/ingestion/fetcher.py
  modified:
    - kalshi-backtest/src/kalshi_backtest/ingestion/__init__.py
    - kalshi-backtest/tests/test_ingest.py
    - kalshi-backtest/tests/conftest.py
    - kalshi-backtest/pyproject.toml
decisions:
  - "Use cryptography as explicit dependency — kalshi-python 2.1.4 requires it but omits it from its own deps"
  - "load_fixture() converted to @pytest.fixture factory returning a callable — original was a plain function unusable as fixture arg"
  - "KalshiHistoricalClient._build_auth_headers() stubbed with TODO — RSA-PSS signing for httpx not wired until live API testing in plan 04"
metrics:
  duration: "~20 minutes"
  completed: "2026-04-04"
  tasks_completed: 2
  files_changed: 7
---

# Phase 1 Plan 3: API Client Layer Summary

**One-liner:** Dual-tier Kalshi API client layer with live SDK wrapper, historical httpx client, runtime cutoff resolver, and cursor-paginated fetchers — all tested against fixture JSON.

## What Was Built

### cutoff.py — HistoricalCutoffResolver
- `CutoffResult` frozen dataclass: `cutoff_ts` (Unix epoch int) + `cutoff_dt` (naive UTC datetime)
- `HistoricalCutoffResolver`: calls `GET /historical/cutoff`, caches in-process, exposes `is_historical(close_time, cutoff)` comparison
- Tenacity retry (3 attempts, exponential backoff 1–10s) on `httpx.HTTPStatusError` and `httpx.TimeoutException`
- Never hardcodes a cutoff date — always resolved at runtime from the API

### client.py — Three client classes
- `_TokenBucket`: simple rate limiter; `consume()` sleeps until the next request slot (configurable RPM from settings)
- `KalshiLiveClient`: wraps `kalshi_python.api.MarketsApi`; correctly passes `series_ticker` as `ticker=` kwarg (not `market_ticker`) to `get_market_candlesticks()`
- `KalshiHistoricalClient`: direct httpx calls to `/trade-api/v2/historical/markets/{ticker}/candlesticks` and `/historical/markets`; parses OHLCV fields into `CandlestickRecord` and `MarketRecord`
- `KalshiClientRouter`: resolves cutoff, routes `get_candlesticks()` to historical or live client based on `market_close_time`; accepts injected clients for testing

### fetcher.py — Two high-level fetchers
- `MarketFetcher.fetch_all(start_dt, end_dt)`: cursor-paginated loop over `KalshiHistoricalClient.get_markets()`, deduplicates by ticker, logs each page
- `CandlestickFetcher.fetch_for_market(market, lookback_start, last_ingested_ts)`: supports incremental sync via `last_ingested_ts`; caps end at `market.close_time`

### ingestion/__init__.py
- Exports all 9 public symbols: `KalshiClientRouter`, `KalshiHistoricalClient`, `KalshiLiveClient`, `HistoricalCutoffResolver`, `CutoffResult`, `MarketFetcher`, `CandlestickFetcher`, `CandlestickRecord`, `MarketRecord`

## Tests

All 5 tests in `tests/test_ingest.py` pass (previously 4 were skipped stubs):

| Test | Coverage |
|------|----------|
| `test_live_candlestick_fetch` | DATA-01: fixture candlesticks.json → 2 `CandlestickRecord` objects, naive UTC ts, valid price range |
| `test_cutoff_routing_historical` | DATA-02: `is_historical()` returns True for close_time before cutoff |
| `test_cutoff_routing_live` | DATA-02: `is_historical()` returns False for close_time after cutoff |
| `test_cutoff_resolve_caches_result` | DATA-02: second `resolve()` call returns cached result, no HTTP call |
| `test_idempotent_ingest` | DATA-04: inserting same 2 candles twice yields exactly 2 rows (ON CONFLICT DO NOTHING) |

Full suite: **36 passed, 5 skipped** (up from 31 passed, 9 skipped before this plan).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `load_fixture` was a plain function, not a pytest fixture**
- **Found during:** Task 2 (test stub filling)
- **Issue:** `conftest.py` defined `load_fixture()` without `@pytest.fixture`, making it unusable as a pytest fixture argument in test function signatures
- **Fix:** Converted to `@pytest.fixture()` factory returning an inner `_load()` callable — preserves the same call interface (`load_fixture("name.json")`) but now injectable
- **Files modified:** `kalshi-backtest/tests/conftest.py`
- **Commit:** 669d54a

**2. [Rule 3 - Blocking] Missing `cryptography` transitive dependency**
- **Found during:** Task 1 (import verification)
- **Issue:** `kalshi-python>=2.1.4` requires `cryptography` for RSA-PSS signing but does not declare it as a dependency; `kalshi_python` import failed with `ModuleNotFoundError: No module named 'cryptography'`
- **Fix:** Added `cryptography` to project dependencies via `uv add cryptography`
- **Files modified:** `kalshi-backtest/pyproject.toml`, `kalshi-backtest/uv.lock`
- **Commit:** 669d54a

## Known Stubs

**1. `KalshiHistoricalClient._build_auth_headers()` — returns `{}`**
- **File:** `src/kalshi_backtest/ingestion/client.py`, method `_build_auth_headers()`
- **Reason:** RSA-PSS signing for direct httpx calls requires inspecting the `kalshi_python.ApiClient` signing hook at runtime. The TODO comment documents the two paths: (a) extract from SDK's `api_client` signing infrastructure, or (b) port `sign_request()` from `Kalshi Insider Tracker/src/kalshi_tracker/kalshi/client.py`. This stub does not block tests (all tests mock the client) but will cause 401 errors against the live historical API until wired.
- **Resolution plan:** Plan 04 (pipeline integration) will test against the live API and wire the signing header at that point.

## Self-Check: PASSED

All created files exist on disk. Commits 669d54a and a5a4f4c confirmed in git log. 36 tests pass.
