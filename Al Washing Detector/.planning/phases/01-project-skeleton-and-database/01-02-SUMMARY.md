---
phase: 01-project-skeleton-and-database
plan: 02
subsystem: database
tags: [sqlalchemy, postgresql, orm, uuid, jsonb, partitioning, append-only]

# Dependency graph
requires:
  - phase: 01-project-skeleton-and-database
    plan: 01
    provides: "pip-installable ai_washer package, AppSettings with database_url, pytest infrastructure"
provides:
  - DeclarativeBase, DualTimestampMixin, AppendOnlyMixin base classes
  - Company, DailyScore, SignalDetail, PipelineRun ORM models
  - Session factory wired to AppSettings.database_url
  - 58 passing unit tests for all models and session factory
affects: [01-03-PLAN, all-future-phases]

# Tech tracking
tech-stack:
  added: []
  patterns: [dual-timestamp-mixin, append-only-mixin, uuid-pk, composite-pk-partitioning, jsonb-columns, bigint-money, session-factory]

key-files:
  created:
    - src/ai_washer/db/base.py
    - src/ai_washer/db/models.py
    - src/ai_washer/db/session.py
    - tests/unit/test_models.py
  modified:
    - src/ai_washer/db/__init__.py
    - docs/PROGRESS.md

key-decisions:
  - "DailyScore uses DualTimestampMixin (not AppendOnlyMixin) due to custom composite PK required by partitioning"
  - "Company is not append-only -- entity table allows updates to aliases, market_cap, sector"
  - "PipelineRun has no dual timestamps -- operational tracking, not financial data"

patterns-established:
  - "DualTimestampMixin: as_of_date (business date) + observed_date (collection date) on all financial tables"
  - "AppendOnlyMixin: UUID PK + created_at + dual timestamps, no update/delete methods"
  - "Session factory pattern: create_engine_from_settings(settings) + get_session_factory(engine)"
  - "JSONB columns for flexible content (aliases, signal_breakdown, evidence, errors)"
  - "BIGINT for monetary values (market_cap_cents) to avoid floating point"

requirements-completed: [FNDN-01, INT-01]

# Metrics
duration: 7min
completed: 2026-03-27
---

# Phase 1 Plan 02: SQLAlchemy ORM Models Summary

**Four SQLAlchemy 2.0 ORM models (Company, DailyScore, SignalDetail, PipelineRun) with dual-timestamp mixin, UUID PKs, JSONB columns, BIGINT money, and RANGE partitioning on DailyScore**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-27T14:35:18Z
- **Completed:** 2026-03-27T14:43:14Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Created base class hierarchy: DeclarativeBase, DualTimestampMixin (as_of_date + observed_date per D-08), AppendOnlyMixin (UUID PK per D-07 + created_at + dual timestamps)
- Four ORM models matching INT-01 schema: Company (entity), DailyScore (partitioned append-only), SignalDetail (append-only), PipelineRun (operational)
- DailyScore declares composite PK (id, scored_at) and RANGE partition by scored_at per D-06 (monthly partitions created in Plan 03 migration)
- Session factory reads database_url from AppSettings, with pool_pre_ping and configurable echo
- Full TDD red/green cycle: tests written first (failing), then implementation to pass them
- 58 new unit tests covering all columns, types, constraints, indexes, no-mutation guarantees, session factory, and public API exports

## Task Commits

Each task was committed atomically:

1. **Task 1: Database base classes and mixins** - `316e3f2` (test)
2. **Task 2: ORM models and session factory** - `958fd62` (feat)

_Note: Both tasks followed TDD red/green cycle with tests written before implementation._

## Files Created/Modified
- `src/ai_washer/db/base.py` - DeclarativeBase, DualTimestampMixin, AppendOnlyMixin
- `src/ai_washer/db/models.py` - Company, DailyScore, SignalDetail, PipelineRun ORM models
- `src/ai_washer/db/session.py` - create_engine_from_settings, get_session_factory
- `src/ai_washer/db/__init__.py` - Public DB API re-exports (all models + session factory)
- `tests/unit/test_models.py` - 58 unit tests for base classes, models, session factory, exports
- `docs/PROGRESS.md` - Updated with Plan 02 progress

## Decisions Made
- DailyScore uses DualTimestampMixin (not AppendOnlyMixin) because PostgreSQL requires the partition key in the primary key, necessitating a custom composite PK (id, scored_at)
- Company is not append-only -- as an entity table, it needs updates to aliases, market_cap, and sector
- PipelineRun has no dual timestamps -- it tracks operational pipeline state, not financial data

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Recreated venv to fix .pth file processing**
- **Found during:** Task 1 (running tests)
- **Issue:** Python .pth file for editable install was not being processed by the venv's Python, causing ModuleNotFoundError on import
- **Fix:** Recreated venv from scratch with `uv sync --all-extras`
- **Files modified:** None (venv-level fix)
- **Verification:** `uv run pytest` successfully imports ai_washer.db
- **Committed in:** N/A (venv, not source code)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Venv recreation was necessary to unblock test execution. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviation above.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all models are fully defined with correct column types, constraints, and indexes. No placeholder data or TODO items.

## Next Phase Readiness
- All four ORM models complete, ready for Plan 03 (Alembic migrations)
- Models define the contract for schema generation (companies, daily_scores, signal_details, pipeline_runs)
- DailyScore RANGE partition declaration ready for monthly partition creation in migration
- Session factory available for integration tests in Plan 03
- No blockers for subsequent plans

---
*Phase: 01-project-skeleton-and-database*
*Completed: 2026-03-27*
