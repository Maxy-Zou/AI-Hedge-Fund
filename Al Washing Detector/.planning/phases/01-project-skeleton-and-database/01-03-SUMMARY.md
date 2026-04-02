---
phase: 01-project-skeleton-and-database
plan: 03
subsystem: database
tags: [alembic, postgresql, migrations, partitioning, testcontainers, sqlalchemy]

# Dependency graph
requires:
  - phase: 01-project-skeleton-and-database (plan 02)
    provides: SQLAlchemy ORM models (Company, DailyScore, SignalDetail, PipelineRun) and Base class
provides:
  - Alembic migration framework reading DATABASE_URL from environment
  - Initial migration creating all four tables with correct constraints
  - 18 monthly partitions for daily_scores (12x2026 + 6x2027) per D-06
  - Integration test infrastructure with testcontainers PostgreSQL
affects: [phase-02-entity-resolution, phase-03-sec-collection, phase-10-pipeline-automation]

# Tech tracking
tech-stack:
  added: [pytest-timeout]
  patterns: [manual Alembic migration for partitioned tables, testcontainers integration fixtures, Docker Desktop auto-detection for macOS]

key-files:
  created:
    - alembic.ini
    - src/ai_washer/db/migrations/env.py
    - src/ai_washer/db/migrations/script.py.mako
    - src/ai_washer/db/migrations/versions/001_initial_schema.py
    - tests/integration/conftest.py
    - tests/integration/test_migrations.py
    - tests/integration/test_schema.py
  modified:
    - pyproject.toml

key-decisions:
  - "Manual Alembic migration (not autogenerate) for daily_scores partitioned table -- autogenerate does not handle PARTITION BY"
  - "Docker Desktop socket auto-detection in conftest.py for macOS compatibility"
  - "stdlib venv (python3 -m venv) used instead of uv-managed venv due to .pth file processing bug"

patterns-established:
  - "Integration test pattern: session-scoped testcontainers PostgreSQL with per-test rollback"
  - "Migration pattern: raw SQL via op.execute(sa.text(...)) for partitioned table DDL"
  - "Docker host detection: check ~/.docker/run/docker.sock for Docker Desktop on macOS"

requirements-completed: [FNDN-06, FNDN-01, INT-01]

# Metrics
duration: 28min
completed: 2026-03-27
---

# Phase 1, Plan 03: Alembic Migrations Summary

**Alembic migration framework with manually-written initial schema creating 4 tables and 18 monthly partitions, verified by 11 integration tests against real PostgreSQL via testcontainers**

## Performance

- **Duration:** 28 min
- **Started:** 2026-03-27T14:45:32Z
- **Completed:** 2026-03-27T15:14:05Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments
- Alembic framework configured with env.py that reads DATABASE_URL from AI_WASHER_DATABASE_URL environment variable (no hardcoded credentials)
- Initial migration creates all four tables (companies, daily_scores, signal_details, pipeline_runs) with correct types, constraints, indexes
- daily_scores uses RANGE partitioning on scored_at with 18 monthly partitions (12 for 2026 + 6 for 2027 buffer) per locked decision D-06
- 11 integration tests verify schema correctness against real PostgreSQL via testcontainers, including partition verification, idempotency, and CRUD operations

## Task Commits

Each task was committed atomically:

1. **Task 1: Alembic setup and initial migration with monthly partitions** - `a228693` (feat)
2. **Task 2: Integration tests with testcontainers PostgreSQL** - `492a934` (test)

## Files Created/Modified
- `alembic.ini` - Alembic configuration pointing to migrations directory
- `src/ai_washer/db/migrations/__init__.py` - Package marker
- `src/ai_washer/db/migrations/env.py` - Alembic env reading DATABASE_URL from environment
- `src/ai_washer/db/migrations/script.py.mako` - Template for future migration files
- `src/ai_washer/db/migrations/versions/__init__.py` - Package marker
- `src/ai_washer/db/migrations/versions/001_initial_schema.py` - Initial migration with 4 tables and 18 monthly partitions
- `tests/integration/conftest.py` - testcontainers PostgreSQL fixtures with Docker Desktop auto-detection
- `tests/integration/test_migrations.py` - Migration correctness and idempotency tests
- `tests/integration/test_schema.py` - Column types, constraints, and CRUD operation tests
- `pyproject.toml` - Added pytest-timeout dependency and integration marker
- `uv.lock` - Updated lockfile

## Decisions Made
- **Manual migration for partitioned tables:** Alembic autogenerate does not support PostgreSQL PARTITION BY. The initial migration uses raw SQL via `op.execute(sa.text(...))` for the daily_scores partitioned table and its monthly partitions. Standard `op.create_table()` used for non-partitioned tables.
- **Docker Desktop socket auto-detection:** Added `_ensure_docker_host()` helper to conftest.py that detects `~/.docker/run/docker.sock` on macOS, since the docker-py library defaults to `/var/run/docker.sock` which doesn't exist with Docker Desktop.
- **stdlib venv over uv-managed venv:** The uv-managed venv had a `.pth` file processing bug where the editable install path was not being added to sys.path. Recreated with `python3 -m venv` + `pip install -e` for correct behavior.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Docker Desktop socket not found by testcontainers**
- **Found during:** Task 2 (integration test execution)
- **Issue:** Docker Desktop on macOS uses `~/.docker/run/docker.sock` instead of `/var/run/docker.sock`. The docker-py library (used by testcontainers) could not connect.
- **Fix:** Added `_ensure_docker_host()` function to `tests/integration/conftest.py` that detects the Docker Desktop socket and sets `DOCKER_HOST` environment variable.
- **Files modified:** tests/integration/conftest.py
- **Verification:** Integration tests connect to Docker and run PostgreSQL container successfully.
- **Committed in:** 492a934 (Task 2 commit)

**2. [Rule 3 - Blocking] uv-managed venv .pth file processing bug**
- **Found during:** Task 1 verification (ai_washer not importable)
- **Issue:** After `uv sync`, the `.pth` file in site-packages was not being processed, causing `import ai_washer` to fail. All `.pth` files (including `_virtualenv.pth`) were non-functional.
- **Fix:** Recreated venv using `python3 -m venv .venv` + `pip install -e ".[dev]"` instead of uv-managed venv.
- **Files modified:** None (runtime environment fix only)
- **Verification:** `import ai_washer` succeeds, all 79 tests pass.
- **Committed in:** N/A (no code change, environment fix)

**3. [Rule 3 - Blocking] Docker daemon not running**
- **Found during:** Task 2 (integration test execution)
- **Issue:** Docker Desktop was installed but the daemon was not running. It required an admin password dialog to complete first-time setup.
- **Fix:** Started Docker Desktop via `open -a Docker` and the backend binary directly. Waited for daemon to become responsive.
- **Files modified:** None (infrastructure fix)
- **Verification:** `docker ps` succeeds, testcontainers creates PostgreSQL container.
- **Committed in:** N/A (no code change, infrastructure fix)

**4. [Rule 3 - Blocking] pytest-timeout not installed**
- **Found during:** Task 2 (before test execution)
- **Issue:** Plan verification uses `--timeout=120` flag which requires pytest-timeout, not in dev dependencies.
- **Fix:** Added `pytest-timeout>=2.3` to pyproject.toml dev dependencies.
- **Files modified:** pyproject.toml
- **Verification:** `--timeout=120` flag accepted by pytest.
- **Committed in:** 492a934 (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (4 blocking issues)
**Impact on plan:** All auto-fixes were necessary for test execution. No scope creep. Final test suite passes all 79 tests (68 unit + 11 integration).

## Issues Encountered
- Docker Desktop required privileged access setup on first launch, which initially blocked integration tests for several minutes until the daemon became responsive.
- The uv package manager's venv creation has a bug where `.pth` files are not processed by Python's site module, preventing editable installs from working. Workaround: use stdlib `python3 -m venv` instead.

## User Setup Required
None - no external service configuration required. Docker Desktop must be running for integration tests.

## Known Stubs
None - all code is fully functional with no placeholder data or unimplemented features.

## Next Phase Readiness
- Database foundation complete: all 4 tables created with correct schema via Alembic migration
- Phase 1 complete: package scaffold, ORM models, and migrations all in place
- Ready for Phase 2 (entity resolution and universe builder) which will use the companies table
- Integration test pattern established for all future database-dependent tests

## Self-Check: PASSED

- All 9 created files verified on disk
- Commit a228693 (Task 1) verified in git log
- Commit 492a934 (Task 2) verified in git log
- All 79 tests pass (68 unit + 11 integration)

---
*Phase: 01-project-skeleton-and-database*
*Completed: 2026-03-27*
