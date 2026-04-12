---
phase: 02-data-pipeline
plan: 02
subsystem: daemon
tags: [apscheduler, polling, warmup, tdd, green-phase, factory-pattern]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: KalshiClient, MarketSnapshot domain types, ORM models, AppSettings
  - phase: 02-data-pipeline
    plan: 01
    provides: daemon package skeleton, RED tests, poll_interval_seconds, warmup_snapshots
provides:
  - WarmupTracker class (threshold-based per-ticker counter, thread-safe)
  - make_poll_tick factory function (APScheduler job factory with injected dependencies)
  - _to_orm translator (pure domain-to-ORM mapping)
  - PollingDaemon class (BackgroundScheduler wrapper with graceful shutdown)
  - CLI start command fully wired to PollingDaemon
affects: [03-signal-detection, 05-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "make_poll_tick factory pattern: returns zero-arg callable for APScheduler injection"
    - "_to_orm pure translator: no side effects, accepts DomainSnapshot returns OrmSnapshot"
    - "DomainSnapshot/OrmSnapshot alias pattern: prevents MarketSnapshot name collision"
    - "PollingDaemon uses signal.pause() on main thread + BackgroundScheduler for graceful SIGTERM handling"

key-files:
  created:
    - src/kalshi_tracker/daemon/warmup.py
    - src/kalshi_tracker/daemon/poller.py
  modified:
    - src/kalshi_tracker/cli.py
    - src/kalshi_tracker/kalshi/types.py

key-decisions:
  - "DomainSnapshot/OrmSnapshot alias: explicit import aliases prevent MarketSnapshot collision (both kalshi.types and db.models define the class)"
  - "market_id and title made optional (default='') in domain MarketSnapshot to match test fixture contract from 02-01"
  - "poll_tick factory (not class method): plain callable required by APScheduler — no serialization needed"
  - "signal.pause() on main thread: blocks until SIGTERM/SIGINT, allows BackgroundScheduler to run jobs in worker threads"

# Metrics
duration: 8min
completed: 2026-04-03
---

# Phase 02 Plan 02: Data Pipeline Wave 2 — Polling Daemon Implementation Summary

**APScheduler-based polling daemon implemented: WarmupTracker, make_poll_tick factory, _to_orm translator, PollingDaemon scheduler wrapper, and CLI start command fully wired — all 10 RED tests from Plan 01 turned GREEN**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-04-03T04:38:00Z
- **Completed:** 2026-04-03T04:46:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Implemented `WarmupTracker` with thread-safe threshold counter and copy-returning `status()` method
- Implemented `_to_orm()` pure translator mapping `DomainSnapshot` to `OrmSnapshot` (explicit alias imports prevent name collision)
- Implemented `make_poll_tick()` factory returning APScheduler-compatible callable with injected `KalshiClient`, `sessionmaker`, and `WarmupTracker`
- Implemented `PollingDaemon` wrapping `BackgroundScheduler` with `IntervalTrigger`, `max_instances=1`, and graceful SIGTERM shutdown via `signal.pause()`
- Wired `cli.py` start command: loads settings, creates engine, session factory, client, warmup, poll_tick, daemon
- Turned all 10 RED tests GREEN (5 warmup + 5 poller) with no test modifications
- Full unit suite: 33/33 tests pass (no regressions)

## Task Commits

1. **Task 1: Implement WarmupTracker** - `3712067` (feat)
2. **Task 2: Implement poller, PollingDaemon, wire CLI** - `9eca0a1` (feat)

## Files Created/Modified

- `src/kalshi_tracker/daemon/warmup.py` — WarmupTracker class (thread-safe, threshold-based, copy-returning status)
- `src/kalshi_tracker/daemon/poller.py` — make_poll_tick factory, _to_orm translator, PollingDaemon class
- `src/kalshi_tracker/cli.py` — start command fully wired (PollingDaemon, all dependencies assembled)
- `src/kalshi_tracker/kalshi/types.py` — market_id and title made optional (Rule 1 fix, see Deviations)

## Decisions Made

- `DomainSnapshot`/`OrmSnapshot` alias pattern chosen over renaming — keeps import clarity when both domain and ORM types share the name `MarketSnapshot`
- `signal.pause()` on main thread chosen over `while True: time.sleep(1)` — more responsive to SIGTERM (no sleep granularity delay)
- `make_poll_tick` factory over closure in class — keeps the job callable a plain function, avoids APScheduler serialization edge cases

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Made market_id and title optional in domain MarketSnapshot**
- **Found during:** Task 2 (before writing poller.py)
- **Issue:** `kalshi_tracker.kalshi.types.MarketSnapshot` had `market_id: str` and `title: str` as required positional fields. The test fixture in `test_poller.py` (written in Plan 01 against the plan's interface spec which omitted these fields) constructed `DomainSnapshot` without them — causing a `TypeError` at test time.
- **Fix:** Moved `market_id` and `title` to the end of the dataclass with `default=""`. The `from_sdk_market()` classmethod continues to populate both fields explicitly. Tests now pass without modification.
- **Files modified:** `src/kalshi_tracker/kalshi/types.py`
- **Commit:** `9eca0a1`

## Known Stubs

None — all plan goals achieved. CLI start command is fully wired (not a stub).

## Self-Check

- [x] `src/kalshi_tracker/daemon/warmup.py` exists
- [x] `src/kalshi_tracker/daemon/poller.py` exists (exports make_poll_tick, _to_orm, PollingDaemon)
- [x] `src/kalshi_tracker/cli.py` contains `PollingDaemon`
- [x] `grep "DomainSnapshot" src/kalshi_tracker/daemon/poller.py` matches
- [x] `grep "session.commit()" src/kalshi_tracker/daemon/poller.py` matches
- [x] Commit `3712067` exists
- [x] Commit `9eca0a1` exists
- [x] 10/10 daemon tests pass
- [x] 33/33 full unit suite passes
- [x] ruff check and format: zero errors

## Self-Check: PASSED
