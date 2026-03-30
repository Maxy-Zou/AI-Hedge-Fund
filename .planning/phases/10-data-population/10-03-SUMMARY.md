---
phase: 10-data-population
plan: 03
subsystem: database, infra
tags: [yfinance, price_bars, ohlcv, postgresql, coverage]

# Dependency graph
requires:
  - phase: "10-02"
    provides: "universe_tickers populated with 274 active S&P 400 mid-cap tickers"
  - phase: "10-01"
    provides: "price.yaml config created with batch_sleep_secs=3.0 and CLI patched"
provides:
  - "price_bars table populated with 337,866 daily OHLCV bars for 273 tickers"
  - "5-year history: 2021-03-31 to 2026-03-30 (1,825 day span)"
  - "Coverage at 99.6% (273/274 tickers) — POP-02 and POP-03 requirements satisfied"
  - "9 anomalies flagged in price_anomalies (all return spikes, normal for 5yr data)"
  - "POP-04 overlap SQL verified structurally correct; overlap-verification.md created"
  - "Phase 11 (Detector Execution) and Phase 13 (Backtest) can now proceed"
affects: [phase-11, phase-12, phase-13]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PostgreSQL 65535 bind-parameter limit: chunk bulk INSERTs at floor(65535/N_cols) rows; _INSERT_CHUNK_SIZE=8191 for 8-col rows"

key-files:
  created:
    - .planning/phases/10-data-population/overlap-verification.md
  modified:
    - backtest/src/fund_backtest/price/repository.py

key-decisions:
  - "PostgreSQL hard-caps bind parameters at 65,535 per statement: insert_bars() must chunk at 8191 rows (65535//8); single mega-INSERT with 274 tickers * 1257 days * 8 cols = ~2.75M params fails at runtime"
  - "CMC yfinance TypeError NoneType failure is acceptable: 1/274 = 0.4% failure rate, within 10% SLA; do not retry or special-case single tickers"

requirements-completed: [POP-02, POP-03, POP-04]

# Metrics
duration: ~6min (excluding first failed attempt before bug fix)
completed: 2026-03-30
---

# Phase 10 Plan 03: Price Data Download Summary

**337,866 daily OHLCV bars for 273/274 S&P 400 mid-cap tickers (99.6% coverage, 2021-03-31 to 2026-03-30) inserted into price_bars after fixing a PostgreSQL 65,535 bind-parameter overflow in insert_bars()**

## Performance

- **Duration:** ~6 min (active execution after bug fix; ~45 min total including first failed attempt)
- **Started:** 2026-03-30T15:57:04Z
- **Completed:** 2026-03-30T16:38:48Z
- **Tasks:** 2 auto + 1 checkpoint (auto-approved)
- **Files modified:** 1 source file + 1 planning artifact

## Accomplishments

- Fixed PostgreSQL bind-parameter overflow in `repository.py`: `insert_bars()` now chunks at 8,191 rows per INSERT (65535 // 8 cols), enabling bulk inserts of any size
- Downloaded 5 years of daily OHLCV data for all 274 universe tickers via `fund-backtest data download`
- Inserted 337,866 price bars: coverage 99.6% (273/274 tickers), date range 2021-03-31 to 2026-03-30
- Flagged 9 anomalies (>50% single-day return spikes) stored in price_anomalies for downstream review
- Verified POP-04 overlap SQL executes without error; created overlap-verification.md with Phase 11 post-conditions
- POP-02 (5yr history), POP-03 (>=95% coverage), and POP-04 (SQL verified) all satisfied

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Run data download + coverage verify | 381c08e | backtest/src/fund_backtest/price/repository.py |
| 2 | Document POP-04 overlap query | cb0e3fc | .planning/phases/10-data-population/overlap-verification.md |
| CP | Checkpoint: auto-approved (autonomous mode) | - | No code changes |

## Files Created/Modified

- `backtest/src/fund_backtest/price/repository.py` — Added `_INSERT_CHUNK_SIZE=8191` and `_ANOMALY_CHUNK_SIZE=10922` constants; `insert_bars()` and `insert_anomalies()` now loop over chunks instead of single mega-INSERT
- `.planning/phases/10-data-population/overlap-verification.md` — Phase 11 post-conditions for POP-04 overlap verification; SQL queries documented; current status (active_universe=274, active_companies=0, overlap=0) recorded

## Decisions Made

- **PostgreSQL chunking constant:** `_INSERT_CHUNK_SIZE = 65535 // 8 = 8191` — derived from hard DB limit; constant named and commented to make the constraint obvious to future maintainers
- **CMC failure acceptable:** yfinance raised `TypeError("'NoneType' object is not subscriptable")` for CMC (Commercial Metals Company) — 1 out of 274 = 0.4% failure rate; within 10% SLA; idempotent re-run would retry, but coverage at 99.6% exceeds the 95% threshold without it

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PostgreSQL 65,535 bind-parameter overflow in insert_bars()**
- **Found during:** Task 1 (first data download attempt)
- **Issue:** `insert_bars()` collected all bars from all 4 batches into a single list (274 tickers × ~1,257 bars × 8 columns ≈ 2.75M parameters) and issued one mega-INSERT. PostgreSQL hard-limits bind parameters to 65,535 per statement. The command ran for ~40 minutes processing yfinance data, then failed at the DB insert step with: `psycopg.OperationalError: sending query and params failed: number of parameters must be between 0 and 65535`
- **Fix:** Added `_PG_MAX_PARAMS = 65_535`, `_INSERT_CHUNK_SIZE = 8191` (65535 // 8), `_ANOMALY_CHUNK_SIZE = 10922` (65535 // 6) constants in `repository.py`. `insert_bars()` now iterates over chunks: `for chunk_start in range(0, len(rows), _INSERT_CHUNK_SIZE)`. Same fix applied defensively to `insert_anomalies()`.
- **Files modified:** `backtest/src/fund_backtest/price/repository.py`
- **Verification:** Second download run completed in ~6 min with `insert_bars_complete: requested=337866, inserted=337866`; `SELECT COUNT(*) FROM price_bars` returns 337,866
- **Committed in:** 381c08e (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Fix was required to complete the plan at all — the data download could not insert anything without it. No scope creep; same data inserted as intended. The chunking logic is correct and idempotent.

## Issues Encountered

- First download attempt (PID 77806) ran ~40 minutes consuming CPU before the overflow error surfaced at insert time — yfinance downloads are fast but insert was deferred until all 4 batches were processed in memory
- After fixing repository.py, re-running was safe because ON CONFLICT DO NOTHING prevents double-inserts; the price_bars table was still empty

## Known Stubs

None — this plan populates operational DB tables; no UI or data rendering involved.

## Next Phase Readiness

- POP-02 satisfied: `price_bars` has 5yr OHLCV data (MIN=2021-03-31, MAX=2026-03-30, span=1825 days)
- POP-03 satisfied: 273/274 tickers = 99.6% coverage
- POP-04 structurally verified: overlap SQL executes correctly; full count deferred to post-Phase-11
- Phase 11 (ai-washer universe scan + filing collection) can now begin
- Phase 12 (bug fixes) can run in parallel with Phase 11
- Phase 13 (live backtest) requires both Phase 11 (companies populated) and this phase (price_bars populated)

## Self-Check: PASSED

- `.planning/phases/10-data-population/10-03-SUMMARY.md` exists (this file)
- `backtest/src/fund_backtest/price/repository.py` exists and modified
- `.planning/phases/10-data-population/overlap-verification.md` exists
- Commit `381c08e` exists in git log
- Commit `cb0e3fc` exists in git log
- `SELECT COUNT(*) FROM price_bars` returns 337,866 (> 100,000 required)
- `SELECT MIN(bar_date) FROM price_bars` returns 2021-03-31 (<= 2021-12-31 required)
- Coverage = 99.6% (>= 95% required)

---
*Phase: 10-data-population*
*Completed: 2026-03-30*
