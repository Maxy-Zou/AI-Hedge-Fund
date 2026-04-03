---
phase: 02-data-pipeline
plan: 01
subsystem: infra
tags: [apscheduler, freezegun, pytest-asyncio, pydantic, polling, tdd]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: AppSettings base class, KalshiClient, MarketSnapshot domain types, ORM models
provides:
  - apscheduler>=3.11.0 runtime dependency declared and installed
  - freezegun>=1.5.5 and pytest-asyncio>=1.0 dev dependencies declared and installed
  - AppSettings.poll_interval_seconds (default 10, range 1-60) with validator
  - AppSettings.warmup_snapshots (default 60, must be >0) with validator
  - src/kalshi_tracker/daemon/ package directory skeleton
  - RED tests for WarmupTracker (5 tests, ImportError confirmed)
  - RED tests for polling job make_poll_tick and _to_orm (5 tests, ImportError confirmed)
affects: [02-data-pipeline, 03-signal-detection]

# Tech tracking
tech-stack:
  added: [apscheduler==3.11.2, freezegun==1.5.5, pytest-asyncio==1.3.0, tzlocal==5.3.1]
  patterns: [TDD RED phase — test contracts written before implementation, field_validator for domain constraints]

key-files:
  created:
    - src/kalshi_tracker/daemon/__init__.py
    - tests/unit/daemon/__init__.py
    - tests/unit/daemon/test_warmup.py
    - tests/unit/daemon/test_poller.py
  modified:
    - pyproject.toml
    - src/kalshi_tracker/config.py
    - tests/conftest.py

key-decisions:
  - "poll_interval_seconds range 1-60: upper bound prevents accidental high-frequency polling"
  - "warmup_snapshots default 60 = ~10 minutes at 10s interval, aligns with DATA-06"
  - "pytest-asyncio added even though Wave 1 has no async tests — needed for Wave 2 poller tests"

patterns-established:
  - "WarmupTracker contract: threshold-based per-ticker counter, status() returns a copy (immutability)"
  - "make_poll_tick pattern: factory function returning a callable for APScheduler job injection"
  - "_to_orm pattern: pure mapping function from domain dataclass to ORM row (no side effects)"

requirements-completed: [DATA-02, DATA-04, DATA-06]

# Metrics
duration: 8min
completed: 2026-04-03
---

# Phase 02 Plan 01: Data Pipeline Wave 1 — Contracts and RED Tests Summary

**APScheduler dependency added, AppSettings extended with polling config fields (poll_interval_seconds, warmup_snapshots), daemon package skeleton created, and 10 RED TDD tests written for WarmupTracker and polling job contracts**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-04-03T04:30:00Z
- **Completed:** 2026-04-03T04:38:00Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Installed apscheduler 3.11.2 (runtime), freezegun 1.5.5 and pytest-asyncio 1.3.0 (dev) into project
- Extended AppSettings with poll_interval_seconds=10 (range 1-60) and warmup_snapshots=60 (>0) with Pydantic field validators
- Created daemon package directory structure at src/kalshi_tracker/daemon/
- Wrote 5 RED tests for WarmupTracker (threshold tracking, per-ticker isolation, copy semantics)
- Wrote 5 RED tests for make_poll_tick/_to_orm (client call, DB persist, RateLimitError handling, generic error, ORM field mapping)

## Task Commits

1. **Task 1: Add dependencies and extend AppSettings config** - `07bbec4` (feat)
2. **Task 2: Create daemon package and write RED tests** - `7593632` (test)

## Files Created/Modified
- `pyproject.toml` - Added apscheduler to runtime deps, freezegun/pytest-asyncio to dev deps (both optional-dependencies and dependency-groups)
- `src/kalshi_tracker/config.py` - Extended AppSettings with poll_interval_seconds and warmup_snapshots fields + validators
- `src/kalshi_tracker/daemon/__init__.py` - Created daemon package init
- `tests/unit/daemon/__init__.py` - Created test package init
- `tests/unit/daemon/test_warmup.py` - 5 RED tests for WarmupTracker (ImportError on run)
- `tests/unit/daemon/test_poller.py` - 5 RED tests for make_poll_tick and _to_orm (ImportError on run)
- `tests/conftest.py` - Added mock_kalshi_client and mock_session fixtures

## Decisions Made
- poll_interval_seconds validator enforces 1-60 range (not just >0): upper bound prevents accidental sub-second or excessively slow polling that would violate DATA-02 (5-10s target)
- pytest-asyncio added in Wave 1 even though no async tests yet — Wave 2 poller implementation will use async; better to install with the rest of the dependencies upfront

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — all dependencies resolved cleanly. apscheduler 3.11.2 (>= 3.11.0) installed with tzlocal 5.3.1 as its timezone dependency.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Wave 1 (this plan) establishes all contracts: config fields, package structure, test expectations
- Wave 2 (02-02) can immediately implement WarmupTracker and make_poll_tick to turn RED tests GREEN
- All 10 failing tests define the exact API surface that Wave 2 must satisfy

---
*Phase: 02-data-pipeline*
*Completed: 2026-04-03*
