---
phase: 02-price-data-pipeline
plan: 02
subsystem: price-data
tags: [yfinance, tenacity, retry, downloader, validator, anomaly-detection, gap-detection, coverage, tdd]

# Dependency graph
requires:
  - phase: 02-price-data-pipeline
    plan: 01
    provides: PriceAnomalyRecord, CoverageReport, PriceSettings from price/types.py

provides:
  - download_in_chunks() in price/downloader.py — chunked yfinance download with sleep between batches
  - _download_batch() with tenacity retry on YFRateLimitError/HTTPError (max 5, exponential backoff)
  - get_failed_tickers() detecting missing columns and all-NaN Close
  - detect_return_anomalies() returning PriceAnomalyRecord list for |return| > threshold
  - detect_gaps() flagging gaps >3 business days using bdate_range
  - compute_coverage() delegating to CoverageReport.from_counts()

affects:
  - 02-03-repository (will call download_in_chunks and pass results to builder/inserter)
  - 02-04-builder (uses per-ticker DataFrames from download_in_chunks output)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "tenacity @retry on module-level function: retry.wait patched to 0 in tests to avoid sleeping"
    - "YFRateLimitError() takes no constructor args — instantiate as YFRateLimitError() not YFRateLimitError('msg')"
    - "pd.bdate_range(inclusive='neither') counts business days strictly between two dates"
    - "pct_change().dropna() on anomaly series skips first bar's NaN automatically"
    - "Patch yf.download via patch.object(yf, 'download') for cleaner isolation"

key-files:
  created:
    - backtest/src/fund_backtest/price/downloader.py
    - backtest/src/fund_backtest/price/validator.py
    - backtest/tests/unit/test_downloader.py
    - backtest/tests/unit/test_validator.py
  modified: []

key-decisions:
  - "Patch tenacity wait via dl_mod._download_batch.retry.wait = lambda: 0 — avoids sleep in tests while testing real retry logic through the decorated function"
  - "YFRateLimitError takes no args — constructor is YFRateLimitError() (no message string)"
  - "detect_gaps uses bdate_range(inclusive='neither'): counts only the missing business days between two dates, not the endpoints themselves"
  - "compute_coverage is a thin wrapper over CoverageReport.from_counts() — keeps logic in one place (types.py)"

# Metrics
duration: 3min
completed: 2026-03-29
---

# Phase 2 Plan 02: Downloader and Validator Summary

**Chunked yfinance downloader with tenacity retry (5 attempts, exp backoff) and price validator with ±50% anomaly detection, >3-business-day gap flagging, and coverage threshold — 24 unit tests all passing**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-29T08:17:18Z
- **Completed:** 2026-03-29T08:20:18Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- downloader.py: `download_in_chunks()` splits ticker lists into batch_size=80 chunks, sleeps between batches (not after last), and returns (ticker, DataFrame) tuples for all tickers with valid Close data
- downloader.py: `_download_batch()` decorated with tenacity `@retry` — retries on both `YFRateLimitError` and `requests.HTTPError`, max 5 attempts, exponential backoff 5-60s
- downloader.py: `get_failed_tickers()` handles two failure modes: ticker absent from MultiIndex columns, and ticker present but Close column is entirely NaN
- validator.py: `detect_return_anomalies()` uses `pct_change().dropna()` — first bar's NaN is skipped automatically; returns typed `PriceAnomalyRecord` list
- validator.py: `detect_gaps()` uses `pd.bdate_range(inclusive="neither")` to count strictly missing business days; only gaps >3 are flagged
- validator.py: `compute_coverage()` delegates entirely to `CoverageReport.from_counts()` for single-source-of-truth coverage logic
- Full test suite: 66 unit tests passing (42 from Plan 01 + 7 downloader + 17 validator)

## Task Commits

Each task was committed atomically:

1. **Task 1: downloader.py + test_downloader.py** — `e3c20e3` (feat)
2. **Task 2: validator.py + test_validator.py** — `b7146a4` (feat)

_Note: Both tasks used TDD — tests written first (RED), then implementation (GREEN)_

## Files Created/Modified

- `backtest/src/fund_backtest/price/downloader.py` — `download_in_chunks()`, `_download_batch()` with tenacity, `get_failed_tickers()`
- `backtest/src/fund_backtest/price/validator.py` — `detect_return_anomalies()`, `detect_gaps()`, `compute_coverage()`
- `backtest/tests/unit/test_downloader.py` — 7 unit tests (chunking, retry, failed ticker detection, sleep behavior)
- `backtest/tests/unit/test_validator.py` — 17 unit tests (spike anomalies, gap threshold, coverage threshold)

## Decisions Made

- **Tenacity wait patching in tests:** The retry test patches `dl_mod._download_batch.retry.wait = lambda retry_state: 0` to avoid sleeping, then restores it. This tests real retry behavior through the live decorator rather than bypassing it with `__wrapped__`.
- **YFRateLimitError constructor:** Takes no arguments — `YFRateLimitError()` not `YFRateLimitError("msg")`. Discovered during RED phase when `__init__() takes 1 positional argument but 2 were given`.
- **bdate_range inclusive="neither":** Counts business days strictly between two dates (excludes endpoints), which is exactly the number of "missing" trading bars between two consecutive data points.
- **compute_coverage is a thin wrapper:** All logic lives in `CoverageReport.from_counts()` from Plan 01 — compute_coverage just forwards arguments to keep the validator API consistent.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] YFRateLimitError constructor takes no args**
- **Found during:** Task 1 (RED phase test run)
- **Issue:** Test raised `TypeError: YFRateLimitError.__init__() takes 1 positional argument but 2 were given` when calling `YFRateLimitError("rate limited")`
- **Fix:** Changed to `YFRateLimitError()` (no message string). The retry test was also simplified to remove duplicated logic and use a cleaner pattern with wait patching.
- **Files modified:** `backtest/tests/unit/test_downloader.py`
- **Commit:** `e3c20e3`

## Known Stubs

None — all functions are fully implemented with real logic.

## Next Phase Readiness

- Both downloader and validator are pure functions with no DB access — ready for the repository plan (02-03) to wire them into the persistence layer
- The (ticker, DataFrame) tuples from `download_in_chunks()` are the exact input format expected by `PriceBar.from_yfinance_row()` from Plan 01
- All 66 unit tests passing

---
*Phase: 02-price-data-pipeline*
*Completed: 2026-03-29*

## Self-Check: PASSED

- FOUND: backtest/src/fund_backtest/price/downloader.py
- FOUND: backtest/src/fund_backtest/price/validator.py
- FOUND: backtest/tests/unit/test_downloader.py
- FOUND: backtest/tests/unit/test_validator.py
- FOUND: .planning/phases/02-price-data-pipeline/02-02-SUMMARY.md
- FOUND: commit e3c20e3 (feat: downloader + tests)
- FOUND: commit b7146a4 (feat: validator + tests)
- All 66 unit tests passing
