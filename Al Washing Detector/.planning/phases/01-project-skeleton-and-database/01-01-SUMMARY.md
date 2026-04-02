---
phase: 01-project-skeleton-and-database
plan: 01
subsystem: infra
tags: [python, typer, pydantic, structlog, uv, ruff, cli, config]

# Dependency graph
requires:
  - phase: none
    provides: greenfield project
provides:
  - pip-installable ai_washer package with src layout
  - Typer CLI entry point (ai-washer command)
  - Pydantic AppSettings (env vars with AI_WASHER_ prefix)
  - Pydantic ScoringConfig (YAML-based signal weights and thresholds)
  - SignalWeights model with sum-to-1.0 validation
  - structlog logging (JSON prod / console dev)
  - pytest test infrastructure with shared fixtures
affects: [01-02-PLAN, 01-03-PLAN, all-future-phases]

# Tech tracking
tech-stack:
  added: [uv, ruff, typer, pydantic, pydantic-settings, structlog, sqlalchemy, psycopg, alembic, pytest, factory-boy, testcontainers]
  patterns: [src-layout, pydantic-settings-yaml, env-prefix-config, typer-cli, structlog-logging]

key-files:
  created:
    - pyproject.toml
    - src/ai_washer/__init__.py
    - src/ai_washer/__main__.py
    - src/ai_washer/cli.py
    - src/ai_washer/config.py
    - src/ai_washer/logging.py
    - config/scoring.yaml
    - config/scoring.example.yaml
    - .env.example
    - .python-version
    - tests/conftest.py
    - tests/unit/test_package.py
    - tests/unit/test_config.py
  modified:
    - CLAUDE.md
    - .gitignore

key-decisions:
  - "Used pydantic-settings YamlConfigSettingsSource for scoring config with _yaml_file override for testing"
  - "Installed uv globally as project toolchain (was not pre-installed)"
  - "Combined import lint fix in config.py (ruff I001)"

patterns-established:
  - "AppSettings with AI_WASHER_ env prefix for all secrets and connection strings"
  - "ScoringConfig with YAML file source and pydantic validation"
  - "SignalWeights model_validator ensuring weights sum to 1.0"
  - "structlog configure_logging() factory with JSON/console toggle"
  - "conftest.py autouse fixture for test env var isolation"

requirements-completed: [FNDN-04, FNDN-05]

# Metrics
duration: 5min
completed: 2026-03-27
---

# Phase 1 Plan 01: Package Scaffold Summary

**Pip-installable ai_washer package with Typer CLI, Pydantic env+YAML config, structlog logging, and 10 passing unit tests**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-27T14:26:09Z
- **Completed:** 2026-03-27T14:31:32Z
- **Tasks:** 2
- **Files modified:** 18

## Accomplishments
- Scaffolded ai_washer Python package with src layout, installable via `uv sync`
- Typer CLI with `ai-washer version` and `ai-washer check-config` commands
- Pydantic AppSettings validates required env vars (DATABASE_URL, EDGAR_IDENTITY) with AI_WASHER_ prefix
- ScoringConfig loads signal weights and thresholds from config/scoring.yaml with range validation
- SignalWeights model validates all 6 signal weights sum to 1.0 (tolerance 0.001)
- structlog configured with JSON renderer (production) or ConsoleRenderer (debug)
- Full TDD red/green cycle: test scaffolds first, then production code to pass them
- Updated CLAUDE.md Architecture section from old src/ingestion/ layout to actual src/ai_washer/ package

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave 0 test infrastructure (TDD red phase)** - `d57b6cb` (test)
2. **Task 2: Scaffold package, CLI, config, logging, and update CLAUDE.md** - `1696f93` (feat)

## Files Created/Modified
- `pyproject.toml` - PEP 621 metadata, CLI entry point, dependencies, ruff/pytest config
- `src/ai_washer/__init__.py` - Package root with __version__ = "0.1.0"
- `src/ai_washer/__main__.py` - python -m ai_washer entry point
- `src/ai_washer/cli.py` - Typer CLI app with version and check-config commands
- `src/ai_washer/config.py` - AppSettings, SignalWeights, ScoringConfig with YAML source
- `src/ai_washer/logging.py` - structlog configuration factory
- `config/scoring.yaml` - Default signal weights and risk thresholds
- `config/scoring.example.yaml` - Template copy of scoring config
- `.env.example` - Required environment variables template
- `.python-version` - Python 3.12 pinned
- `uv.lock` - Dependency lockfile
- `.gitignore` - Added .pytest_cache/ entry
- `CLAUDE.md` - Architecture section updated to src/ai_washer/ layout
- `tests/conftest.py` - Shared fixtures (env var isolation, scoring.yaml factory)
- `tests/__init__.py` - Test package marker
- `tests/unit/__init__.py` - Unit test package marker
- `tests/unit/test_package.py` - Import, version, CLI app existence tests
- `tests/unit/test_config.py` - AppSettings, SignalWeights, ScoringConfig, logging tests
- `tests/integration/__init__.py` - Integration test package marker

## Decisions Made
- Used pydantic-settings `YamlConfigSettingsSource` with `_yaml_file` constructor override for testability (avoiding global state)
- Installed uv globally since it was not pre-installed on the system
- Combined two `pydantic_settings` import lines to satisfy ruff I001 sort rule

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed uv package manager**
- **Found during:** Task 2 (uv sync step)
- **Issue:** uv was not installed on the system, blocking package installation
- **Fix:** Installed uv 0.11.2 via official install script
- **Files modified:** None (system-level install)
- **Verification:** `uv sync --all-extras` completed successfully
- **Committed in:** N/A (system tool)

**2. [Rule 1 - Bug] Fixed ruff I001 import sort error in config.py**
- **Found during:** Task 2 (ruff check step)
- **Issue:** Two separate `from pydantic_settings import ...` lines violated import sorting rules
- **Fix:** Combined into single import line
- **Files modified:** src/ai_washer/config.py
- **Verification:** `uv run ruff check src/ tests/` passes clean
- **Committed in:** 1696f93 (part of Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary for execution. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Package skeleton complete, ready for Plan 02 (SQLAlchemy ORM models)
- All dependencies installed including SQLAlchemy, psycopg, Alembic for database work
- Test infrastructure ready with conftest.py fixtures for env isolation
- No blockers for subsequent plans

## Self-Check: PASSED

All 16 files verified present. Both commit hashes (d57b6cb, 1696f93) confirmed in git log.

---
*Phase: 01-project-skeleton-and-database*
*Completed: 2026-03-27*
