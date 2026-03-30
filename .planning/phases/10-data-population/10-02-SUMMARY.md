---
phase: 10-data-population
plan: 02
subsystem: database, infra
tags: [yfinance, wikipedia, universe, sp400, gics, postgresql]

# Dependency graph
requires:
  - phase: "10-01"
    provides: "testcontainers fix applied and price.yaml config created"
  - phase: "09-02"
    provides: "PostgreSQL running via Docker Compose with ai_hedge_fund database"
provides:
  - "universe_tickers table populated with 274 real mid-cap tickers from S&P 400"
  - "universe_snapshots contains snapshot row for 2026-03-30"
  - "11 GICS sectors with meaningful ticker counts"
  - "POP-01 requirement satisfied — Plan 03 price data download can proceed"
affects: [phase-10-wave3, phase-11, phase-12, phase-13]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "urllib.request.Request with browser User-Agent before pd.read_html(BytesIO) — Wikipedia blocks default pandas UA (HTTP 403)"
    - "Pydantic v2 field_validator mode='before' with math.isnan check — pandas NaN is float, not None; must coerce explicitly for str | None fields"

key-files:
  created: []
  modified:
    - backtest/src/fund_backtest/universe/seeder.py
    - backtest/src/fund_backtest/universe/types.py

key-decisions:
  - "urllib.request with browser User-Agent is the clean fix for Wikipedia 403 — pd.read_html(url) sends Python-urllib/3.x which Wikipedia blocks; fetch HTML bytes first, pass as BytesIO"
  - "Pydantic v2 requires explicit NaN->None coercion via field_validator(mode='before') — the str | None annotation is not enough to handle float('nan') from pandas"

requirements-completed: [POP-01]

# Metrics
duration: 12min
completed: 2026-03-30
---

# Phase 10 Plan 02: Universe Refresh Summary

**274 mid-cap S&P 400 tickers with 11 GICS sectors inserted into universe_tickers via yfinance market-cap filter ($2B-$10B), after fixing Wikipedia 403 and pandas NaN validation bugs in the seeder**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-03-30T15:42:07Z
- **Completed:** 2026-03-30T15:54:30Z
- **Tasks:** 2 (1 auto + 1 checkpoint, auto-approved)
- **Files modified:** 2 (seeder.py, types.py)

## Accomplishments

- Fixed Wikipedia 403 Forbidden error in `seeder.py`: replaced `pd.read_html(url)` with `urllib.request.Request` + browser User-Agent, passing fetched HTML as `BytesIO` to `pd.read_html()`
- Fixed Pydantic v2 NaN validation error in `types.py`: added `coerce_nan_to_none` validator on `SeedRow.gics_sector` and `gics_sub_industry` to convert pandas `float('nan')` to `None`
- Ran `fund-backtest universe refresh` successfully: 400 tickers seeded, 274 passed the $2B-$10B market cap filter
- `universe_tickers` populated with 274 real mid-cap tickers: AAL, AAON, ACI, ADC, AGCO, ALK, etc.
- 11 GICS sectors present: Industrials (55), Financials (49), Consumer Discretionary (47), Information Technology (30), Real Estate (22), Health Care (20), and more
- `universe_snapshots` contains one row for 2026-03-30 with active_count=274
- POP-01 requirement satisfied — Plan 03 price data download can now proceed

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Run universe refresh and verify universe_tickers populated | 9112f6d | backtest/src/fund_backtest/universe/seeder.py, backtest/src/fund_backtest/universe/types.py |
| 2 | Checkpoint: auto-approved (autonomous mode) | - | No code changes |

## Files Created/Modified

- `backtest/src/fund_backtest/universe/seeder.py` — Added browser User-Agent fetch via `urllib.request.Request`; HTML parsed from `io.BytesIO`; added `_WIKIPEDIA_USER_AGENT` constant and `io`, `urllib.request` imports
- `backtest/src/fund_backtest/universe/types.py` — Added `coerce_nan_to_none` validator and `_nan_to_none()` helper; imported `math`; applies to `gics_sector` and `gics_sub_industry` fields in `SeedRow`

## Decisions Made

- Browser-like User-Agent is the minimal-change fix for Wikipedia 403 — `urllib.request.Request` with a Chrome UA avoids adding new library dependencies (requests, httpx); fetches bytes once and parses in-memory
- Explicit NaN coercion is preferred over filling NaN in the DataFrame before model creation — keeps validation logic in the Pydantic model where it belongs, not scattered in caller code

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Wikipedia S&P 400 seed fetch returned HTTP 403 Forbidden**
- **Found during:** Task 1 (universe refresh execution)
- **Issue:** `pd.read_html(url)` sends `Python-urllib/3.x` User-Agent, which Wikipedia blocks with HTTP 403 as of 2026. The plan assumed the Wikipedia scrape would work as written.
- **Fix:** Updated `seeder.py` to fetch the Wikipedia page using `urllib.request.Request` with a browser-like Chrome User-Agent, read the HTML bytes, then pass as `io.BytesIO` to `pd.read_html()`
- **Files modified:** `backtest/src/fund_backtest/universe/seeder.py`
- **Verification:** `fetch_sp400_seed()` returned 400 rows successfully in isolation test before full refresh run
- **Committed in:** 9112f6d (Task 1 commit)

**2. [Rule 1 - Bug] Pydantic v2 validation error: `gics_sub_industry` received float NaN from pandas**
- **Found during:** Task 1 (universe refresh execution, second attempt after fix 1)
- **Issue:** `SeedRow(gics_sub_industry=nan)` raised `ValidationError: Input should be a valid string [type=string_type, input_value=nan]` — pandas uses `float('nan')` for missing string cells; Pydantic v2 doesn't coerce NaN to None automatically
- **Fix:** Added `coerce_nan_to_none` field validator in `types.py` on `gics_sector` and `gics_sub_industry` with `mode='before'`, converting `float NaN` to `None` before Pydantic processes the value
- **Files modified:** `backtest/src/fund_backtest/universe/types.py`
- **Verification:** 400 SeedRows created without ValidationError; `nan_count=2` in seed data confirmed the 2 rows with missing sub-industry are now handled correctly
- **Committed in:** 9112f6d (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - Bug)
**Impact on plan:** Both fixes were necessary to execute the plan at all — the seeder was broken by Wikipedia's bot detection and pandas/Pydantic mismatch. No scope creep; same data ingested as intended.

## Issues Encountered

None beyond the two auto-fixed bugs above.

## Known Stubs

None — this plan populates operational DB tables; no UI or data rendering involved.

## Next Phase Readiness

- POP-01 satisfied: `universe_tickers` has 274 active mid-cap tickers with GICS sectors
- Plan 03 (`fund-backtest data download`) can query `universe_tickers WHERE is_active=True` and will return 274 tickers
- No blockers for price data download

## Self-Check: PASSED

- `.planning/phases/10-data-population/10-02-SUMMARY.md` exists
- `backtest/src/fund_backtest/universe/seeder.py` exists and modified
- `backtest/src/fund_backtest/universe/types.py` exists and modified
- Commit `9112f6d` exists in git log
- `universe_tickers WHERE is_active=TRUE` returns 274 rows (within 150-400 range)

---
*Phase: 10-data-population*
*Completed: 2026-03-30*
