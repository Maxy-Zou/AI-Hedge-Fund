---
phase: 02-entity-resolution-and-universe-builder
plan: 05
subsystem: universe-builder
tags: [typer, cli, sqlalchemy, postgresql, testcontainers, integration-tests, jsonb, soft-delete]

# Dependency graph
requires:
  - phase: 02-entity-resolution-and-universe-builder/04
    provides: "UniverseBuilder, UniverseBuildResult, build_universe, filter_by_market_cap, soft-remove logic"
  - phase: 02-entity-resolution-and-universe-builder/01
    provides: "Company model with is_active/deactivation_reason, AliasesSchema, UniverseSettings, AppSettings"
  - phase: 02-entity-resolution-and-universe-builder/02
    provides: "EFTSClient, EdgarFactsClient for CLI scan command"
  - phase: 02-entity-resolution-and-universe-builder/03
    provides: "EntityResolver for CLI scan pipeline"
provides:
  - "CLI universe subcommand group: scan (--dry-run), list (--active/--all, --limit), inspect (ticker/CIK lookup)"
  - "Integration tests proving Company JSONB aliases round-trip against real PostgreSQL"
  - "Integration tests proving soft-remove lifecycle (deactivate/reactivate/active-only query) per D-10"
  - "Complete Phase 2 deliverable: entity resolution + universe builder end-to-end"
affects: [03-sec-filing-collection, 10-pipeline-automation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Typer subcommand groups: app.add_typer(universe_app, name='universe') for nested CLI commands"
    - "Lazy imports in CLI commands: import heavy modules inside command functions to keep CLI startup fast"
    - "CliRunner testing: typer.testing.CliRunner with monkeypatch for isolated CLI unit tests"
    - "Testcontainers integration test pattern: real PostgreSQL with Alembic migrations + per-test rollback"

key-files:
  created:
    - tests/unit/test_cli_universe.py
    - tests/integration/test_universe_builder.py
    - tests/integration/test_company_lifecycle.py
  modified:
    - src/ai_washer/cli.py

key-decisions:
  - "Lazy imports in CLI: heavy modules (SQLAlchemy, universe builder) imported inside command functions to avoid slowing CLI startup for simple commands like --version"
  - "CliRunner-based unit tests with monkeypatch for DB and builder mocks, avoiding real database dependency in unit tests"

patterns-established:
  - "CLI subcommand groups via Typer: universe_app = typer.Typer() + app.add_typer(universe_app, name='universe')"
  - "Integration test pattern for JSONB round-trip: insert Company with AliasesSchema.model_dump, query back, validate with AliasesSchema.model_validate"

requirements-completed: [FNDN-02, FNDN-03]

# Metrics
duration: 5min
completed: 2026-03-28
---

# Phase 02 Plan 05: CLI Universe Commands and Integration Tests Summary

**Typer CLI universe subcommand group (scan/list/inspect) with PostgreSQL integration tests proving JSONB aliases round-trip and soft-remove lifecycle**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-27T21:44:00Z
- **Completed:** 2026-03-28T02:09:07Z
- **Tasks:** 3 (2 auto + 1 checkpoint approved)
- **Files created:** 3
- **Files modified:** 1

## Accomplishments
- CLI universe subcommand group with scan (--dry-run for safe testing), list (--active/--all, --limit), and inspect (ticker or CIK lookup with aliases display)
- 9 unit tests for CLI commands using CliRunner with mocked DB and builder dependencies
- 3 integration tests proving Company persistence to real PostgreSQL: insert, JSONB aliases round-trip via AliasesSchema, batch insert
- 4 integration tests proving soft-remove lifecycle: deactivate, reactivate, active-only query exclusion, soft-delete preservation (D-10)
- Full Phase 2 verification: 260 tests passing, all modules importable (EFTSClient, EdgarFactsClient, EntityResolver, UniverseBuilder)

## Task Commits

Each task was committed atomically:

1. **Task 1: CLI universe subcommand group** - `cbe8685` (feat: scan, list, inspect commands + 9 unit tests)
2. **Task 2: Integration tests for persistence and lifecycle** - `670d480` (test: Company JSONB round-trip + soft-remove lifecycle)
3. **Task 3: Human verification checkpoint** - Approved (260 tests passing, all modules importable)

## Files Created/Modified
- `src/ai_washer/cli.py` - Added universe_app Typer subgroup with scan (--dry-run), list (--active/--all, --limit), inspect commands
- `tests/unit/test_cli_universe.py` - 9 unit tests for CLI commands with CliRunner and monkeypatch mocks
- `tests/integration/test_universe_builder.py` - 3 tests: Company insert, AliasesSchema JSONB round-trip, batch persistence
- `tests/integration/test_company_lifecycle.py` - 4 tests: deactivate, reactivate, active-only query exclusion, soft-delete preservation

## Decisions Made
- Lazy imports in CLI command functions to keep startup fast for simple commands (--version, --help)
- CliRunner with monkeypatch for CLI unit tests, avoiding database dependency in unit test layer

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs
None -- all CLI commands are fully wired to real database queries and universe builder. No placeholder data or TODO markers.

## User Setup Required
None - CLI commands use existing AppSettings configuration. No new environment variables or services required.

## Next Phase Readiness
- Phase 2 complete: entity resolution and universe builder fully operational
- All 5 plans executed: type contracts, EFTS/EDGAR clients, entity resolver, universe builder orchestrator, CLI + integration tests
- 260 tests passing (unit + integration) across all Phase 2 modules
- Ready for Phase 3 (SEC Filing Collection) which depends on the Company table and CIK-based entity resolution
- Universe builder can be invoked via CLI (`ai-washer universe scan`) or programmatically (`build_universe()`)

---
*Phase: 02-entity-resolution-and-universe-builder*
*Completed: 2026-03-28*
