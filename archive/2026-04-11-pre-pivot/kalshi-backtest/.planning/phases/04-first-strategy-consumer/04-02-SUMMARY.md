---
phase: 04-first-strategy-consumer
plan: 02
subsystem: strategies
tags: [strategies, sqlalchemy, insider-tracker, example-strategy, strategy-registry]

# Dependency graph
requires:
  - phase: 04-first-strategy-consumer/04-01
    provides: RED test scaffold for strategies and Strategy Protocol in simulation/protocol.py

provides:
  - ExampleStrategy: threshold-based YES buyer satisfying Strategy Protocol
  - InsiderTrackerAdapter: SQLAlchemy text() reader against Insider Tracker signals table
  - STRATEGY_REGISTRY dict with pass-through, example, insider-tracker keys
  - sqlalchemy>=2.0.0 added as project dependency

affects:
  - 04-first-strategy-consumer/04-03 (CLI --strategy flag wires STRATEGY_REGISTRY into `run` command)

# Tech tracking
tech-stack:
  added:
    - sqlalchemy 2.0.49 (SQLAlchemy ORM, text() raw SQL)
  patterns:
    - Strategy Protocol: structural subtyping via typing.Protocol, no inheritance required
    - InsiderTrackerAdapter: read-only raw SQL via create_engine + sessionmaker + text()
    - Independence constraint: zero imports from kalshi_tracker package
    - Lazy registry population: InsiderTrackerAdapter added to registry inside try/except ImportError

key-files:
  created:
    - kalshi-backtest/src/kalshi_backtest/strategies/__init__.py
    - kalshi-backtest/src/kalshi_backtest/strategies/example.py
    - kalshi-backtest/src/kalshi_backtest/strategies/insider_tracker.py
  modified:
    - kalshi-backtest/pyproject.toml (sqlalchemy added)
    - kalshi-backtest/uv.lock (sqlalchemy 2.0.49 pinned)

key-decisions:
  - "buy_threshold parameter name matches test scaffold (not entry_threshold as plan text suggested)"
  - "sqlalchemy added to pyproject.toml via direct edit + uv sync (uv add failed to write pyproject.toml)"
  - "InsiderTrackerAdapter: details column handled as str or dict to support both SQLite (JSON string) and PostgreSQL JSONB"
  - "STRATEGY_REGISTRY uses lazy ImportError guard for InsiderTrackerAdapter — package still works without sqlalchemy"

patterns-established:
  - "Strategy plugin: implement generate_signals(snapshot, open_positions) -> list[Signal], no ABC needed"
  - "held_tickers set check: first action in generate_signals to avoid pyramiding"
  - "DB error resilience: catch Exception in InsiderTrackerAdapter, log warning with exc_info=True, return []"

requirements-completed:
  - STRAT-01
  - STRAT-02

# Metrics
duration: 25min
completed: 2026-04-06
---

# Phase 4 Plan 02: First Strategy Consumer Summary

**ExampleStrategy (threshold buy) and InsiderTrackerAdapter (SQLAlchemy text() over signals DB) implement STRAT-01 and STRAT-02 — all 11 strategy tests GREEN**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-06T02:44:05Z
- **Completed:** 2026-04-06T03:09:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- ExampleStrategy: buys YES when `close_price < buy_threshold` (strictly less-than), skips held tickers, satisfies Strategy Protocol via isinstance check
- InsiderTrackerAdapter: look-ahead-safe `detected_at < :end` query, handles SQLite JSON strings and PostgreSQL JSONB dicts, catches all DB errors returning []
- STRATEGY_REGISTRY published with "pass-through", "example", and "insider-tracker" keys; InsiderTrackerAdapter added lazily when sqlalchemy available
- sqlalchemy 2.0.49 added as explicit project dependency

## Task Commits

Each task was committed atomically:

1. **Task 1+2: ExampleStrategy, InsiderTrackerAdapter, STRATEGY_REGISTRY** - `16dfd62` (feat)

**Plan metadata:** (pending — see below)

## Files Created/Modified

- `kalshi-backtest/src/kalshi_backtest/strategies/__init__.py` - STRATEGY_REGISTRY, _PassThroughStrategy, lazy InsiderTrackerAdapter import
- `kalshi-backtest/src/kalshi_backtest/strategies/example.py` - ExampleStrategy implementing Strategy Protocol
- `kalshi-backtest/src/kalshi_backtest/strategies/insider_tracker.py` - InsiderTrackerAdapter with raw SQL via SQLAlchemy text()
- `kalshi-backtest/pyproject.toml` - sqlalchemy>=2.0.0 added to dependencies
- `kalshi-backtest/uv.lock` - sqlalchemy 2.0.49 pinned

## Decisions Made

- **buy_threshold parameter name:** Test scaffold used `buy_threshold=40` not `entry_threshold` as the plan text said. Matched the tests (source of truth).
- **sqlalchemy dependency:** `uv add sqlalchemy` ran but didn't write pyproject.toml — manually added `sqlalchemy>=2.0.0` and ran `uv sync` to update the lock file.
- **details column handling:** Defensive `isinstance(details, dict)` check to support both SQLite (TEXT stored as JSON string) and PostgreSQL (JSONB returns dict directly).
- **Lazy registry pattern:** InsiderTrackerAdapter wrapped in `try/except ImportError` in `__init__.py` so the package still loads in environments without sqlalchemy.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Manually fixed sqlalchemy missing from pyproject.toml**
- **Found during:** Task 2 (InsiderTrackerAdapter requires sqlalchemy)
- **Issue:** `uv add sqlalchemy` installed the package but silently failed to update pyproject.toml — the module was unavailable at test time
- **Fix:** Added `"sqlalchemy>=2.0.0"` directly to pyproject.toml dependencies, ran `uv sync` to update uv.lock
- **Files modified:** kalshi-backtest/pyproject.toml, kalshi-backtest/uv.lock
- **Verification:** `grep -i sqlalchemy uv.lock` shows sqlalchemy-2.0.49 entry; tests pass
- **Committed in:** 16dfd62 (combined task commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 - blocking dependency issue)
**Impact on plan:** Essential fix to make sqlalchemy importable. No scope creep.

## Issues Encountered

- git index.lock file created by background bash processes caused repeated "Unable to create index.lock" errors — resolved by removing the stale lock file between commands
- Some git commands (status, diff, log with no stat args) consistently ran in background mode producing empty output — worked around by using `--stat`, `--cached --stat`, and reading HEAD file directly to verify commits

## Next Phase Readiness

- All strategy classes ready: ExampleStrategy, InsiderTrackerAdapter, _PassThroughStrategy all in STRATEGY_REGISTRY
- Plan 04-03 can wire `--strategy` CLI flag into `run` command using `STRATEGY_REGISTRY[strategy_name]` lookup
- 1 pre-existing RED test remains: `test_run_strategy_flag_dry_run` in test_cli.py (scope of 04-03)
- 4 pre-existing RED tests remain: `test_brier_score_*` in test_metrics_calculator.py (scope of 04-03)

## Self-Check: PASSED

- FOUND: kalshi-backtest/src/kalshi_backtest/strategies/__init__.py
- FOUND: kalshi-backtest/src/kalshi_backtest/strategies/example.py
- FOUND: kalshi-backtest/src/kalshi_backtest/strategies/insider_tracker.py
- FOUND: kalshi-backtest/.planning/phases/04-first-strategy-consumer/04-02-SUMMARY.md
- FOUND: commit 16dfd62 (feat: strategies implementation)
- FOUND: commit 7d1d59d (docs: SUMMARY.md, STATE.md, ROADMAP.md)

---
*Phase: 04-first-strategy-consumer*
*Completed: 2026-04-06*
