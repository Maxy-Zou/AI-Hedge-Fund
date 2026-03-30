---
phase: 09-infrastructure-and-database-setup
plan: 02
subsystem: infra
tags: [docker, postgres, alembic, migrations, verification]

# Dependency graph
requires: ["09-01"]
provides:
  - "PostgreSQL 16 running and healthy via Docker Compose"
  - "fund-backtest migrations at head (002) — fund_backtest_alembic_version table populated"
  - "ai-washer migrations at head (008_add_data_source_status) — ai_washer_alembic_version table populated"
  - "Both version tables coexist in ai_hedge_fund database without collision"
  - "Data persistence verified across docker compose restart"
affects: [phase-10-price-data-backfill, phase-11-detector-first-run, all phases requiring database]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PYTHONPATH workaround required for alembic in uv venvs when project path contains spaces"
    - "uv run alembic fails silently (no module error) when .pth files are skipped — use PYTHONPATH explicitly"

key-files:
  created:
    - .env (from .env.example — not committed, in .gitignore)
  modified: []

key-decisions:
  - "PYTHONPATH must be set explicitly when running alembic from backtest/ and Al Washing Detector/ — Python 3.12 skips .pth files in site-packages when the venv path contains spaces"
  - "uv run alembic is not reliable in this repo due to spaces in project path; use .venv/bin/alembic with PYTHONPATH instead"

patterns-established:
  - "Migration command pattern: cd <package-dir> && DATABASE_URL=... PYTHONPATH=<package-dir>/src .venv/bin/alembic upgrade head"

requirements-completed: [INFRA-04]

# Metrics
duration: 5min
completed: 2026-03-30
---

# Phase 9 Plan 02: Run Both Migration Chains Summary

**PostgreSQL 16 started via Docker Compose, both Alembic migration chains applied to head, and two distinct version tables confirmed coexisting in the shared ai_hedge_fund database**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-30T15:13:16Z
- **Completed:** 2026-03-30T15:18:18Z
- **Tasks:** 2 (1 auto + 1 checkpoint, auto-approved)
- **Files modified:** 1 (.env created, not committed)

## Accomplishments

- Started `ai_hedge_fund_postgres` container — reached healthy status in ~15 seconds
- Applied fund-backtest migration chain: 001 (universe_tickers, universe_snapshots) + 002 (price_bars, price_anomalies) — `fund_backtest_alembic_version` table at `002`
- Applied ai-washer migration chain: 001 through 008 covering companies, daily_scores, signal_details, sec_filings, xbrl_facts, patents, github_repos, earnings_transcripts, job_postings, data_source_status — `ai_washer_alembic_version` table at `008_add_data_source_status`
- Verified two distinct alembic version tables (`ai_washer_alembic_version`, `fund_backtest_alembic_version`) via `information_schema.tables`
- Verified data persistence: both version tables survived `docker compose restart`

## Task Commits

Task 1 is purely operational (database state changes, no tracked source files modified). No per-task commit required.

- **Checkpoint Task 2** auto-approved (auto_advance=true): infrastructure verified operational

## Files Created/Modified

- `.env` — created from `.env.example` at repo root (not committed — in .gitignore)

## Decisions Made

- `PYTHONPATH` must be set explicitly when running alembic from packages in this repo. Python 3.12 skips `.pth` files in venv site-packages when the project path contains spaces ("AI Hedgefund"). `uv run alembic` triggers the same bug. The reliable command pattern is: `cd <pkg-dir> && DATABASE_URL=... PYTHONPATH=<pkg-dir>/src .venv/bin/alembic upgrade head`
- `uv run alembic upgrade head` is not reliable here — use `.venv/bin/alembic` with explicit `PYTHONPATH`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Python 3.12 skips .pth files in venvs when project path contains spaces**

- **Found during:** Task 1
- **Issue:** `uv run alembic upgrade head` in `backtest/` raised `ModuleNotFoundError: No module named 'fund_backtest'`. Root cause: Python 3.12's `site.py` logs "Skipping hidden .pth file" for ALL .pth files in the venv when the venv path contains a space. The AI Hedgefund project directory name has a space, so `_fund_backtest.pth` was never processed during Python startup.
- **Fix:** Run `PYTHONPATH="/path/to/backtest/src" .venv/bin/alembic upgrade head` instead of `uv run alembic`. PYTHONPATH bypasses the pth mechanism entirely and adds the src directory directly to the import path.
- **Files modified:** None (workaround via environment variable)
- **Impact:** Both migration chains ran successfully with PYTHONPATH workaround

## Known Stubs

None — this plan is purely infrastructure verification with no application code.

## Issues Encountered

- `export $(grep -v '^#' ../.env | xargs)` fails when .env contains values with spaces (e.g., `AI_WASHER_EDGAR_IDENTITY=YourCompany yourname@example.com`). Worked around by setting env vars directly on the command line.
- Multiple stale `.pth` files with spaces in their names (`_fund_backtest 2.pth` through `_fund_backtest 5.pth`) exist from prior editable installs. These are harmless but contribute to the "skipping hidden" output.

## Developer Setup (Canonical Migration Commands)

```bash
# Start database
cp .env.example .env  # only if .env doesn't exist
docker compose up -d

# fund-backtest migrations
cd backtest
FUND_BACKTEST_DATABASE_URL="postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund" \
  PYTHONPATH="$(pwd)/src" \
  .venv/bin/alembic upgrade head

# ai-washer migrations
cd "Al Washing Detector"
AI_WASHER_DATABASE_URL="postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund" \
  PYTHONPATH="$(pwd)/src" \
  .venv/bin/alembic upgrade head
```

## Next Phase Readiness

- PostgreSQL 16 running with all tables from both packages
- Phase 10 (price data backfill): set `FUND_BACKTEST_DATABASE_URL` and run `fund-backtest price update`
- Phase 11 (Detector first run): set `AI_WASHER_DATABASE_URL` and `AI_WASHER_EDGAR_IDENTITY` then run `ai-washer` commands
- No blockers for subsequent phases

---
*Phase: 09-infrastructure-and-database-setup*
*Completed: 2026-03-30*
