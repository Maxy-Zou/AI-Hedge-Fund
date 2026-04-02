---
phase: 02-entity-resolution-and-universe-builder
plan: 01
subsystem: database, entity-resolution, universe-builder
tags: [pydantic, sqlalchemy, alembic, edgartools, httpx, rapidfuzz, tenacity, efts]

# Dependency graph
requires:
  - phase: 01-project-skeleton-and-database
    provides: Company model, AppSettings, Alembic migrations, pyproject.toml
provides:
  - Phase 2 dependencies installed (edgartools, httpx, rapidfuzz, tenacity, freezegun, pytest-httpx)
  - Company.is_active and Company.deactivation_reason columns with Alembic migration 002
  - AliasesSchema Pydantic model matching Company.aliases JSONB structure per D-02
  - ResolutionMetadata and EntityResolutionResult types for entity resolution pipeline
  - EFTSHit, EFTSResponse types for EFTS full-text search parsing
  - MarketCapRange validator and UniverseSettings config with widened market cap thresholds
  - entity/, ingestion/, universe/ subpackage directories
affects: [02-02-PLAN, 02-03-PLAN, 02-04-PLAN, 02-05-PLAN]

# Tech tracking
tech-stack:
  added: [edgartools, httpx, rapidfuzz, tenacity, freezegun, pytest-httpx]
  patterns: [soft-delete via is_active/deactivation_reason, Pydantic type contracts as module interfaces, widened market cap proxy thresholds]

key-files:
  created:
    - src/ai_washer/entity/__init__.py
    - src/ai_washer/entity/types.py
    - src/ai_washer/ingestion/__init__.py
    - src/ai_washer/universe/__init__.py
    - src/ai_washer/universe/types.py
    - src/ai_washer/db/migrations/versions/002_add_company_active_fields.py
    - tests/unit/test_entity_types.py
    - tests/unit/test_universe_types.py
  modified:
    - pyproject.toml
    - uv.lock
    - src/ai_washer/db/models.py
    - src/ai_washer/config.py
    - tests/unit/test_models.py

key-decisions:
  - "edgartools imports as 'edgar' not 'edgartools' -- verified at runtime"
  - "UniverseSettings uses $1.5B-$9B range (wider than $2B-$10B target) to account for EntityPublicFloat proxy approximation per Pitfall 2"
  - "Soft-delete pattern: is_active Boolean with server_default='true' + deactivation_reason String(255) per D-10"

patterns-established:
  - "Pydantic type contracts defined before implementation modules: types.py in each subpackage"
  - "TDD for all new types: write test file first, verify RED, then implement GREEN"
  - "Package __init__.py as minimal docstring markers (no re-exports until needed)"

requirements-completed: [FNDN-02, FNDN-03]

# Metrics
duration: 13min
completed: 2026-03-27
---

# Phase 2 Plan 1: Dependencies, Schema, and Type Contracts Summary

**Phase 2 dependencies installed, Company model extended with soft-delete columns, Pydantic type contracts defined for EFTS responses, entity aliases, and universe configuration with widened market cap thresholds**

## Performance

- **Duration:** 13 min
- **Started:** 2026-03-27T22:36:00Z
- **Completed:** 2026-03-27T22:49:06Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments
- Installed 6 new dependencies (edgartools, httpx, rapidfuzz, tenacity + freezegun, pytest-httpx for dev)
- Extended Company model with is_active/deactivation_reason for soft-delete per D-10, with Alembic migration 002
- Defined complete Pydantic type contracts for entity resolution (AliasesSchema, ResolutionMetadata, EntityResolutionResult) and universe building (EFTSHit, EFTSResponse, MarketCapRange, UniverseSettings)
- Created entity/, ingestion/, universe/ subpackage directories for Phase 2 module organization
- 44 new unit tests (5 for Company model, 39 for type contracts), all 112 unit tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Install dependencies, update Company model, create Alembic migration 002** - `0075235` (feat)
2. **Task 2: Define Pydantic type contracts for entity resolution and universe building** - `4a65baf` (feat)

## Files Created/Modified
- `pyproject.toml` - Added edgartools, httpx, rapidfuzz, tenacity, freezegun, pytest-httpx
- `uv.lock` - Updated lockfile with 31 new packages
- `src/ai_washer/db/models.py` - Added is_active and deactivation_reason to Company model
- `src/ai_washer/db/migrations/versions/002_add_company_active_fields.py` - Alembic migration for new columns
- `src/ai_washer/config.py` - Added UniverseSettings Pydantic model
- `src/ai_washer/entity/__init__.py` - Package marker for entity resolution module
- `src/ai_washer/entity/types.py` - AliasesSchema, ResolutionMetadata, ResolutionMethod, EntityResolutionResult
- `src/ai_washer/ingestion/__init__.py` - Package marker for data ingestion module
- `src/ai_washer/universe/__init__.py` - Package marker for universe builder module
- `src/ai_washer/universe/types.py` - EFTSHit, EFTSResponse, MarketCapRange
- `tests/unit/test_models.py` - 5 new tests for Company is_active/deactivation_reason
- `tests/unit/test_entity_types.py` - 17 tests for entity resolution type contracts
- `tests/unit/test_universe_types.py` - 22 tests for universe builder type contracts

## Decisions Made
- edgartools imports as `edgar` at runtime (package name on PyPI is `edgartools`)
- UniverseSettings market cap thresholds widened to $1.5B-$9B (vs $2B-$10B target) per Pitfall 2 research on EntityPublicFloat proxy
- Company soft-delete uses server_default=sa.text("true") for database-level default on is_active

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All Pydantic type contracts are defined and tested for downstream plans
- Company model has soft-delete columns ready for universe builder to use
- EFTS response types ready for Plan 02 (EFTS client implementation)
- AliasesSchema ready for Plan 03 (entity resolver)
- UniverseSettings ready for Plan 04 (universe builder)
- All 6 new dependencies installed and importable

## Self-Check: PASSED

All 8 created files verified present. Both commit hashes (0075235, 4a65baf) verified in git log.

---
*Phase: 02-entity-resolution-and-universe-builder*
*Completed: 2026-03-27*
