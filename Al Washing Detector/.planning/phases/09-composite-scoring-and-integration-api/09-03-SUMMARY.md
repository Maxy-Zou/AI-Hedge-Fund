---
phase: 09-composite-scoring-and-integration-api
plan: 03
subsystem: api
tags: [python-api, frozen-dataclass, sqlalchemy, composite-score]

requires:
  - phase: 09-01
    provides: CompanyScore frozen dataclass, classify_risk_band, ALL_SIGNAL_TYPES, DailyScore/Company ORM models
provides:
  - get_score(ticker, date) -> CompanyScore | None
  - get_latest_scores() -> list[CompanyScore] sorted by composite desc
  - get_score_history(ticker, start, end) -> list[CompanyScore] chronological
  - Package root re-exports (from ai_washer import get_score)
affects: [phase-10-pipeline-automation, downstream-portfolio-modules]

tech-stack:
  added: []
  patterns: [public-api-facade-over-orm, frozen-dataclass-contracts, case-insensitive-ticker-lookup]

key-files:
  created: [src/ai_washer/api.py, tests/unit/test_api.py]
  modified: [src/ai_washer/__init__.py]

key-decisions:
  - "signal_freshness populated lazily from SignalDetail.as_of_date aggregation per company"
  - "Own-session pattern: auto-create session if not provided, close it in finally block"

patterns-established:
  - "Public API facade: api.py returns frozen dataclasses, no ORM models leak to consumers"
  - "Case-insensitive ticker lookup via func.upper() comparison"
  - "Package root re-export via __init__.py __all__ for consumer convenience"

requirements-completed: [INT-02, INT-03]

duration: 4min
completed: 2026-03-29
---

# Phase 9 Plan 3: Public Python API Summary

**Three public API functions (get_score, get_latest_scores, get_score_history) returning frozen CompanyScore dataclasses with signal freshness, re-exported from package root**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-29T20:21:16Z
- **Completed:** 2026-03-29T20:25:21Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 3

## Accomplishments
- Public API module with 3 functions for downstream module consumption
- All returned objects are frozen CompanyScore with composite, sub-scores, confidence, risk_band, signals_available/missing, run_id, and signal_freshness
- Case-insensitive ticker lookup and optional session parameter on all functions
- Re-exported from ai_washer package root for consumer convenience (`from ai_washer import get_score`)

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for public API** - `b2a65d3` (test)
2. **Task 1 (GREEN): Implement API + __init__ re-exports** - `ddfd7a4` (feat)

## Files Created/Modified
- `src/ai_washer/api.py` - Public Python API facade returning frozen dataclasses
- `src/ai_washer/__init__.py` - Re-exports get_score, get_latest_scores, get_score_history
- `tests/unit/test_api.py` - 14 unit tests covering all 3 functions with mock sessions

## Decisions Made
- signal_freshness populated lazily from SignalDetail max(as_of_date) grouped by signal_type
- Own-session pattern: auto-create via get_session_factory() if caller does not pass one, close in finally block
- Risk band reconstructed from composite_score via classify_risk_band (not stored in DailyScore)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Public API complete, ready for pipeline automation (Phase 10)
- All 3 API functions tested and importable from package root
- 803 tests pass across the full test suite

---
*Phase: 09-composite-scoring-and-integration-api*
*Completed: 2026-03-29*
