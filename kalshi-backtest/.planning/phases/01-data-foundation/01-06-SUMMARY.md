---
phase: 01-data-foundation
plan: 06
subsystem: api
tags: [kalshi, rsa-pss, auth, httpx, kalshi-python]

# Dependency graph
requires:
  - phase: 01-data-foundation/01-03
    provides: KalshiHistoricalClient skeleton with _build_auth_headers() stub
provides:
  - KalshiHistoricalClient with working per-request RSA-PSS signing via KalshiAuth.create_auth_headers()
  - 3 unit tests verifying auth header structure, per-request freshness, and call-site wiring
  - Phase 1 verification score raised from 6/7 to 7/7
affects: [02-backtest-engine, 03-metrics, 04-visualization]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-request auth: _get_auth_headers(method, url) called inline at each httpx.get() — never cached"
    - "SDK delegation: KalshiAuth.create_auth_headers() is the single signing source of truth"

key-files:
  created:
    - kalshi-backtest/.planning/phases/01-data-foundation/01-06-SUMMARY.md
  modified:
    - kalshi-backtest/src/kalshi_backtest/ingestion/client.py
    - kalshi-backtest/tests/test_ingest.py
    - kalshi-backtest/tests/test_coverage_boost.py
    - kalshi-backtest/.planning/phases/01-data-foundation/01-VERIFICATION.md

key-decisions:
  - "Use KalshiAuth.create_auth_headers() directly — no need to port RSA-PSS signing manually; SDK exposes it cleanly"
  - "Per-request signing (not cached at init) — KALSHI-ACCESS-TIMESTAMP must be fresh per request to avoid 401 replay rejection"

patterns-established:
  - "KalshiAuth instantiated once at __init__; _get_auth_headers() called per request — separates key loading from signing"

requirements-completed: [DATA-01, DATA-02]

# Metrics
duration: 16min
completed: 2026-04-05
---

# Phase 1 Plan 06: Gap Closure Summary

**RSA-PSS auth wired into KalshiHistoricalClient via KalshiAuth.create_auth_headers() — empty-dict stub removed, all historical httpx calls now signed per-request**

## Performance

- **Duration:** 16 min
- **Started:** 2026-04-05T23:08:00Z
- **Completed:** 2026-04-05T23:24:50Z
- **Tasks:** 1
- **Files modified:** 3 (+ 1 planning doc updated)

## Accomplishments

- Removed `_build_auth_headers()` stub that returned `{}` — the single blocker preventing live historical-tier ingestion
- Implemented `_get_auth_headers(method, url)` delegating to `KalshiAuth.create_auth_headers()` from the kalshi-python SDK
- Updated both httpx call sites (`get_candlesticks`, `get_markets`) to call `_get_auth_headers()` per request
- Added 3 unit tests verifying: non-empty headers with all 3 Kalshi keys, per-request timestamp freshness, call-site wiring
- Phase 1 verification score advanced from 6/7 to 7/7 — phase is now fully verified

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement RSA-PSS auth in KalshiHistoricalClient and add test** - `639f639` (feat)

**Plan metadata:** (docs commit — see final commit below)

## Files Created/Modified

- `src/kalshi_backtest/ingestion/client.py` — Replaced `_build_auth_headers()` stub with `_get_auth_headers(method, url)`; `KalshiAuth` instantiated at `__init__`; both httpx call sites updated
- `tests/test_ingest.py` — 3 new tests: `test_historical_auth_headers_are_non_empty`, `test_historical_auth_headers_are_per_request`, `test_historical_get_candlesticks_sends_auth_headers`
- `tests/test_coverage_boost.py` — Updated 2 `__new__`-bypass test fixtures from `_auth_headers = {}` to `_kalshi_auth` mock
- `.planning/phases/01-data-foundation/01-VERIFICATION.md` — Status updated from `gaps_found` (6/7) to `verified` (7/7)

## Decisions Made

- Used `KalshiAuth.create_auth_headers()` directly rather than porting RSA-PSS signing manually — the SDK class is already present in `.venv` and exposes exactly the interface needed
- `_kalshi_auth` stored as instance attribute (key loaded once at init); `_get_auth_headers()` called per request to embed live timestamp — clean separation of key loading from signing

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated two test_coverage_boost.py tests that referenced removed `_auth_headers` attribute**

- **Found during:** Task 1 (full suite run after GREEN implementation)
- **Issue:** Two tests in `TestHistoricalClientParsing` used `KalshiHistoricalClient.__new__()` to bypass `__init__` and manually set `client._auth_headers = {}`. After renaming to `_get_auth_headers()`, these tests raised `AttributeError: 'KalshiHistoricalClient' object has no attribute '_kalshi_auth'` when `get_candlesticks()` was called.
- **Fix:** Replaced `client._auth_headers = {}` with a mock `_kalshi_auth` that returns the expected 3-key dict from `create_auth_headers()`
- **Files modified:** `tests/test_coverage_boost.py`
- **Verification:** Full suite 71/71 pass
- **Committed in:** `639f639` (included in task commit)

**2. [Rule 1 - Bug] Moved mid-file imports to top of test_ingest.py**

- **Found during:** Task 1 (ruff lint check after GREEN)
- **Issue:** Following the plan's code block literally placed `import time` and `from unittest.mock import MagicMock, patch` mid-file after the DATA-04 tests — ruff flagged E402 (module level import not at top) and F811 (redefinition of MagicMock already imported at line 5)
- **Fix:** Added `import time` and `patch` to the existing top-of-file imports; removed the duplicate mid-file block
- **Files modified:** `tests/test_ingest.py`
- **Verification:** `uv run ruff check src/ tests/` — "All checks passed!"
- **Committed in:** `639f639` (included in task commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - Bug)
**Impact on plan:** Both fixes necessary for correctness. No scope creep — the implementation changes are exactly as planned.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## Known Stubs

None. The only stub in this plan (`return {}` in `_build_auth_headers()`) has been fully replaced.

## Next Phase Readiness

- Phase 1 Data Foundation is fully verified (7/7 truths, 71 tests, 86% coverage)
- `KalshiHistoricalClient` now produces authenticated requests — historical-tier data ingestion is production-ready pending live credentials
- Phase 2 (Backtest Engine) can consume the historical data store without any auth blockers

---
*Phase: 01-data-foundation*
*Completed: 2026-04-05*
