---
phase: 09-infrastructure-and-database-setup
plan: 01
subsystem: infra
tags: [docker, postgres, alembic, migrations, env]

# Dependency graph
requires: []
provides:
  - "docker-compose.yml: PostgreSQL 16 via Docker with named volume and healthcheck"
  - ".env.example at repo root with all three DATABASE_URL variants"
  - "backtest/.env.example with FUND_BACKTEST_DATABASE_URL reference"
  - "Al Washing Detector/.env.example updated to shared ai_hedge_fund database"
  - "fund_backtest Alembic env.py isolated via version_table=fund_backtest_alembic_version"
  - "ai_washer Alembic env.py isolated via version_table=ai_washer_alembic_version"
affects: [phase-10-price-data-backfill, phase-11-detector-first-run, all phases requiring database]

# Tech tracking
tech-stack:
  added: [docker compose, postgres:16-alpine]
  patterns: [shared database with package-namespaced Alembic version tables, repo-root .env convention]

key-files:
  created:
    - docker-compose.yml
    - .env.example
    - backtest/.env.example
  modified:
    - Al Washing Detector/.env.example
    - backtest/src/fund_backtest/db/migrations/env.py
    - Al Washing Detector/src/ai_washer/db/migrations/env.py

key-decisions:
  - "Both packages share ai_hedge_fund database; Alembic collision prevented by version_table namespacing (fund_backtest_alembic_version, ai_washer_alembic_version)"
  - "Docker Compose named volume ai_hedge_fund_pgdata prevents data loss on docker system prune"
  - "Repo-root .env.example is the canonical reference; package-level .env.example files are reference-only"

patterns-established:
  - "Package-namespaced Alembic version tables: each package sets version_table in both offline and online context.configure() calls"
  - "Shared database convention: FUND_BACKTEST_DATABASE_URL and AI_WASHER_DATABASE_URL both point to same ai_hedge_fund database"

requirements-completed: [INFRA-01, INFRA-02, INFRA-03, FIX-01]

# Metrics
duration: 2min
completed: 2026-03-30
---

# Phase 9 Plan 01: Infrastructure and Database Setup Summary

**PostgreSQL 16 Docker Compose with named volume, shared .env convention, and Alembic version table isolation for both fund-backtest and ai-washer packages**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-30T15:09:21Z
- **Completed:** 2026-03-30T15:10:53Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Created `docker-compose.yml` at repo root with postgres:16-alpine, named volume `ai_hedge_fund_pgdata`, and healthcheck — ready to `docker compose up -d`
- Established shared `.env.example` at repo root documenting all three DATABASE_URL variants so both packages use the same `ai_hedge_fund` database
- Fixed Alembic version table collision by adding `version_table` to both offline and online `context.configure()` calls in both packages — fund_backtest gets `fund_backtest_alembic_version`, ai_washer gets `ai_washer_alembic_version`

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Docker Compose and .env convention** - `3ce64c8` (chore)
2. **Task 2: Fix Alembic version_table collision in both packages** - `3c1d3b6` (fix)

## Files Created/Modified

- `docker-compose.yml` - PostgreSQL 16 service with named volume and healthcheck
- `.env.example` - Shared env template with DATABASE_URL, FUND_BACKTEST_DATABASE_URL, AI_WASHER_DATABASE_URL
- `backtest/.env.example` - Fund-backtest specific reference (FUND_BACKTEST_DATABASE_URL)
- `Al Washing Detector/.env.example` - Updated to use shared `ai_hedge_fund` database (was `ai_washer`)
- `backtest/src/fund_backtest/db/migrations/env.py` - Added `version_table="fund_backtest_alembic_version"` to both offline and online modes
- `Al Washing Detector/src/ai_washer/db/migrations/env.py` - Added `version_table="ai_washer_alembic_version"` to both offline and online modes

## Decisions Made

- Both packages share the `ai_hedge_fund` database; Alembic collision is prevented by package-namespaced version tables rather than separate databases — keeps operational overhead minimal while avoiding migration conflicts
- Named Docker volume (`ai_hedge_fund_pgdata`) is mandatory per STATE.md decision: prevents data loss on `docker system prune`
- Repo-root `.env.example` is the canonical reference; package-level files are reference-only (comment says "prefer running from repo root")

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

To start the database:
```bash
cp .env.example .env
docker compose up -d
```

Then run migrations for each package:
```bash
cd backtest && uv run alembic upgrade head
cd "Al Washing Detector" && uv run alembic upgrade head
```

## Next Phase Readiness

- Docker Compose ready: `docker compose up -d` starts PostgreSQL 16
- Both Alembic chains can run against the same database without collision
- `.env.example` copied to `.env` is all that's needed before Phase 10 (price data backfill) and Phase 11 (Detector first run)
- No blockers for Phase 09 Plan 02 (run migrations)

---
*Phase: 09-infrastructure-and-database-setup*
*Completed: 2026-03-30*

## Self-Check: PASSED

All 6 files verified present. Both task commits (3ce64c8, 3c1d3b6) confirmed in git log.
