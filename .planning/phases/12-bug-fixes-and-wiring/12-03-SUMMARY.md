---
phase: 12-bug-fixes-and-wiring
plan: "03"
subsystem: ui
tags: [streamlit, dashboard, live-mode, postgresql, backtest-pipeline]

# Dependency graph
requires:
  - phase: 06-streamlit-dashboard
    provides: dashboard/app.py with demo-only _load_demo_data()
  - phase: 08-ai-washing-detector-integration
    provides: AiWashingLoader, SignalAdapter, PortfolioSimulator, MetricsEngine
  - phase: 12-bug-fixes-and-wiring
    provides: FIX-02 date intersection and FIX-05 SPY benchmark fetch patterns from cli.py
provides:
  - _load_live_data() cached function in dashboard/app.py — runs 5-stage pipeline from FUND_BACKTEST_DATABASE_URL
  - _load_data() dispatcher — routes to live or demo, returns (result, bundle, ticker_sectors, is_live)
  - Live mode banner in main() — caption switches between "Live mode" and "Demo mode"
  - Real GICS sector map from UniverseTicker replaces DEMO_TICKER_SECTORS in live mode
affects:
  - 13-live-demo (consumes live mode dashboard)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Lazy imports inside @st.cache_data to avoid Typer/Click initialization at Streamlit module load
    - Environment-variable-gated live mode with graceful fallback to demo
    - Session created inside cached function (not passed as argument — SQLAlchemy objects not serializable by st.cache_data)

key-files:
  created: []
  modified:
    - backtest/src/fund_backtest/dashboard/app.py

key-decisions:
  - "FIX-04 live mode uses lazy imports inside _load_live_data() — NOT importing from cli.py — to avoid Typer registering commands in Streamlit context"
  - "FUND_BACKTEST_DATABASE_URL env var is the live mode gate; absence → demo mode without warning"
  - "ValidationError from load_app_settings() caught explicitly before broader Exception — gives specific log reason"
  - "ticker_sectors passed dynamically to build_sector_exposure_chart(); DEMO_TICKER_SECTORS remains as fallback in _load_data() only"

patterns-established:
  - "Live mode gate pattern: check os.environ.get('FUND_BACKTEST_DATABASE_URL') at top of cached function, return None if absent"
  - "Lazy import pattern for Streamlit + Typer coexistence: all fund_backtest.* imports inside the function body"

requirements-completed:
  - FIX-04

# Metrics
duration: 4min
completed: 2026-03-30
---

# Phase 12 Plan 03: Dashboard Live Mode Summary

**Live mode wired to dashboard: _load_live_data() runs real 5-stage AI Washing pipeline when FUND_BACKTEST_DATABASE_URL is set, with graceful fallback to demo mode on missing config or any pipeline error**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-30T19:44:33Z
- **Completed:** 2026-03-30T19:48:10Z
- **Tasks:** 2 auto + 1 checkpoint (auto-approved)
- **Files modified:** 1

## Accomplishments

- Added `_load_live_data()` with `@st.cache_data` — runs AiWashingLoader, PriceBarRepository, SignalAdapter, PortfolioSimulator, MetricsEngine using lazy imports (no cli.py import)
- Added `_load_data()` dispatcher returning `(result, bundle, ticker_sectors, is_live)` — live branch when DB available, demo fallback otherwise
- Wired `main()` to call `_load_data()` and display "Live mode" or "Demo mode" caption accordingly; warning toast shown when DATABASE_URL set but pipeline failed
- Real GICS sector map from UniverseTicker replaces hardcoded DEMO_TICKER_SECTORS in live path

## Task Commits

Each task was committed atomically:

1. **Tasks 1+2: Add _load_live_data(), _load_data() dispatcher, wire main()** - `9a67f48` (feat)

**Plan metadata:** (see final commit below)

## Files Created/Modified

- `backtest/src/fund_backtest/dashboard/app.py` - Added `import os`, `_load_live_data()`, `_load_data()`, updated `main()` to use dispatcher and dynamic ticker_sectors

## Decisions Made

- FIX-04 live mode uses lazy imports inside `_load_live_data()` — NOT importing from cli.py — to avoid Typer registering commands in Streamlit context (confirmed from plan interfaces)
- `FUND_BACKTEST_DATABASE_URL` env var is the live mode gate; absence returns `None` immediately
- `ValidationError` from `load_app_settings()` caught explicitly before broader `except Exception` for specific log reason
- `ticker_sectors` passed dynamically to `build_sector_exposure_chart()`; `DEMO_TICKER_SECTORS` kept as fallback in `_load_data()` only — not in `main()`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. Syntax checked and 171 unit tests passed without regressions.

## User Setup Required

To use live mode:
```bash
export FUND_BACKTEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/ai_hedge_fund"
cd backtest
uv run streamlit run src/fund_backtest/dashboard/app.py
```
Dashboard shows "Live mode — AI Washing signal, real SEC filing data" when pipeline loads successfully. If daily_scores table is empty, it falls back to demo mode with a warning toast.

## Next Phase Readiness

- Phase 12 (bug-fixes-and-wiring) is now complete — all 3 plans executed
- Phase 13 live demo can proceed: dashboard live mode is wired and ready
- Prerequisite: Phase 11 Detector must have populated daily_scores rows before live mode shows real data

---

## Self-Check: PASSED

- `/Users/maxzou/Documents/projects/AI Hedgefund/backtest/src/fund_backtest/dashboard/app.py` — FOUND (modified with _load_live_data, _load_data, is_live)
- Commit `9a67f48` — FOUND (verified via git log)

---
*Phase: 12-bug-fixes-and-wiring*
*Completed: 2026-03-30*
