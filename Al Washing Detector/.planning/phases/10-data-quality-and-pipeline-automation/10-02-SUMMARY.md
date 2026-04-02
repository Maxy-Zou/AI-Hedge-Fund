---
phase: 10-data-quality-and-pipeline-automation
plan: 02
subsystem: pipeline
tags: [pydantic, validation, staleness, monitoring, data-quality, structlog]

requires:
  - phase: 10-01
    provides: "StageResult, PipelineRunResult types, DataSourceStatus ORM model"
provides:
  - "validate_records() batch Pydantic validation with rejection logging"
  - "validate_score_range() for 0-100 enforcement"
  - "check_staleness() data source freshness detection"
  - "update_source_status() success/failure recording"
  - "get_all_source_status() ordered status listing"
affects: [10-03, 10-04, pipeline-orchestrator]

tech-stack:
  added: []
  patterns:
    - "now_utc parameter injection for deterministic time testing (avoids freezegun/SQLAlchemy conflicts)"
    - "Single-table SQLite fixture (DataSourceStatus only) to avoid JSONB compatibility issues"

key-files:
  created:
    - src/ai_washer/pipeline/validation.py
    - src/ai_washer/pipeline/monitoring.py
    - tests/unit/test_pipeline_validation.py
    - tests/unit/test_source_monitoring.py
  modified: []

key-decisions:
  - "now_utc parameter over freezegun: freezegun hangs with SQLAlchemy func.now()/onupdate; explicit param is simpler and more reliable"
  - "Single-table SQLite fixture: create only DataSourceStatus table to avoid JSONB compilation errors from other models"

patterns-established:
  - "Time injection pattern: functions accepting optional now_utc kwarg default to datetime.now(tz=timezone.utc)"
  - "Batch validation pattern: validate_records() returns immutable ValidationResult with valid/rejected split"

requirements-completed: [DQ-01, DQ-02, DQ-03]

duration: 11min
completed: 2026-03-30
---

# Phase 10 Plan 02: Data Quality Validation and Staleness Monitoring Summary

**Pydantic batch validation with structured rejection logging and data source staleness detection via cadence comparison**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-30T01:56:00Z
- **Completed:** 2026-03-30T02:07:13Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Batch Pydantic validation (validate_records) catches malformed ingestion data with structured structlog warnings
- Score range enforcement (validate_score_range) validates 0-100 boundaries with custom field names
- Staleness monitoring (check_staleness) detects exceeded_cadence and never_succeeded sources, updates is_stale column
- Source status tracking (update_source_status) records success/failure with auto-create for unknown sources
- 29 total unit tests across both modules

## Task Commits

Each task was committed atomically:

1. **Task 1: Pydantic validation wrappers at ingestion boundaries** - `e886760` (feat)
2. **Task 2: Data source staleness monitoring** - `8ecc169` (feat)

_Both tasks followed TDD: RED (import failure confirmed) -> GREEN (implementation passes all tests)_

## Files Created/Modified
- `src/ai_washer/pipeline/validation.py` - validate_records(), validate_score_range(), ValidationResult, RejectedRecord
- `src/ai_washer/pipeline/monitoring.py` - check_staleness(), update_source_status(), get_all_source_status(), StalenessReport
- `tests/unit/test_pipeline_validation.py` - 17 tests for DQ-01 and DQ-03
- `tests/unit/test_source_monitoring.py` - 12 tests for DQ-02

## Decisions Made
- **now_utc parameter injection over freezegun:** freezegun causes hangs when SQLAlchemy uses `func.now()` / `onupdate=func.now()` in SQLite. Explicit `now_utc` keyword parameter is simpler, faster, and more reliable for time-dependent tests.
- **Single-table SQLite fixture:** Creating only `DataSourceStatus.__table__` avoids JSONB compilation errors from Company and other models that use PostgreSQL-specific types.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] freezegun/SQLAlchemy hang in staleness tests**
- **Found during:** Task 2 (staleness monitoring)
- **Issue:** `@freeze_time` decorator caused tests to hang indefinitely due to freezegun intercepting SQLAlchemy's internal `func.now()` calls in `onupdate` handlers
- **Fix:** Replaced freezegun with explicit `now_utc` keyword parameter on `check_staleness()` and `update_source_status()`. Tests pass a fixed datetime instead of mocking system time.
- **Files modified:** `src/ai_washer/pipeline/monitoring.py`, `tests/unit/test_source_monitoring.py`
- **Verification:** All 12 monitoring tests pass in ~3s with no hangs
- **Committed in:** `8ecc169` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Deviation improves API design (explicit time parameter is better for testing). No scope creep.

## Issues Encountered
None beyond the freezegun deviation above.

## Known Stubs
None - all functions are fully implemented with real logic.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- validation.py and monitoring.py ready for integration into pipeline orchestrator (10-04)
- check_staleness() can be called at pipeline start to detect stale sources before processing
- update_source_status() can be called after each collector stage completes

---
*Phase: 10-data-quality-and-pipeline-automation*
*Completed: 2026-03-30*
