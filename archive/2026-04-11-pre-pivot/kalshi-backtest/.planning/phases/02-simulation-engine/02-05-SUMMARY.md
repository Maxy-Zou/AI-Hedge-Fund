---
phase: 02-simulation-engine
plan: 05
subsystem: cli
tags: [typer, cli, backtest-runner, dry-run, tdd, integration]

# Dependency graph
requires:
  - phase: 02-simulation-engine/02-03
    provides: BacktestRunner.run(), BacktestResult frozen dataclass
  - phase: 01-data-foundation/01-05
    provides: MarketRepository, get_or_create_db(), load_settings()

provides:
  - kalshi-backtest run command — CLI entry point for BacktestRunner
  - --lookback-days (default 365), --series filter, --dry-run preview, --log-level
  - Credentials validation with exit 1 and actionable error on missing env vars

affects:
  - 03-xx (Metrics phase: run command is the primary CLI surface for strategy execution)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dry-run before credentials: --dry-run exits 0 without loading settings; credentials validated only for live execution"
    - "Stub strategy inline class: _PassThroughStrategy defined inside run() — avoids polluting module scope, clear replacement point for Phase 4"
    - "Lazy imports inside command body: heavy simulation deps loaded only when live run triggered, not on import"
    - "Multi-command Typer: adding second command changes routing — subcommand name required in all test invocations"

key-files:
  created: []
  modified:
    - src/kalshi_backtest/cli.py
    - tests/test_cli.py
    - tests/test_coverage_boost.py

key-decisions:
  - "Dry-run skips credentials: --dry-run is purely informational (date window preview), so load_settings() is only called for live execution — eliminates friction for quick planning checks"
  - "Stub strategy in CLI layer: _PassThroughStrategy defined inline rather than in simulation module — keeps simulation layer clean; Phase 4 will replace with real Strategy implementation"
  - "Multi-command Typer routing fix: adding run command switched app from single-command to multi-command mode, requiring ingest subcommand prefix in all existing tests"

# Metrics
duration: 3min
completed: 2026-04-06
---

# Phase 2 Plan 5: CLI `run` Command Summary

**`run` command wired into Typer CLI with --lookback-days, --series, --dry-run, --log-level; credentials validated on live execution; stub strategy scaffolds BacktestRunner integration for Phase 4**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-04-06T00:18:16Z
- **Completed:** 2026-04-06T00:20:56Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Added `@app.command() def run(...)` to `cli.py` following the exact `ingest` command pattern
- `--dry-run` exits 0 and prints the backtest window (start/end date, lookback days, series filter) without requiring credentials
- `--lookback-days` defaults to 365 and is configurable per invocation
- `--series` filter is echoed in dry-run output and passed to `BacktestRunner.run()` as `series_tickers`
- Credentials validated via `load_settings()` / `ValidationError` → exit 1 with field-level error messages (only for live execution)
- Inline `_PassThroughStrategy` stub wired to `BacktestRunner` — no signals generated, serves as placeholder until Phase 4 real strategy
- 6 new TDD tests in `test_cli.py`: dry-run exit 0, date range output, missing credentials exit 1, default 365, custom 90, series filter echo
- Full suite: 206 tests pass (up from 202)

## Task Commits

1. **Task 1: Add `run` command to CLI with --lookback-days and --dry-run** - `599aff4` (feat)

_Note: TDD task — tests written RED before GREEN_

## Files Created/Modified

- `src/kalshi_backtest/cli.py` - Added `run` command (+100 lines); updated docstring to list both commands
- `tests/test_cli.py` - Added 6 new `run` command tests for CLI-02; updated existing ingest tests to use subcommand prefix
- `tests/test_coverage_boost.py` - Fixed 4 `TestCliIngestFullPath` tests to use `["ingest", ...]` prefix (broken by multi-command Typer switch)

## Decisions Made

- **Dry-run skips credentials**: `--dry-run` is purely informational — only the date window and series filter are shown. `load_settings()` is not called, so the command works without any environment configuration.
- **Stub strategy inline**: `_PassThroughStrategy` is defined inside `run()` to avoid polluting the module namespace. It generates zero signals — the backtest loop runs but produces no trades. This is the correct scaffold for Phase 4's real strategy integration.
- **Multi-command Typer routing**: Adding a second command changed Typer from single-command to multi-command routing. All existing CLI tests that invoked `app` with `["--dry-run"]` (no subcommand prefix) broke. Fixed by prefixing with `"ingest"`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Multi-command Typer broke existing CLI test invocations**
- **Found during:** Task 1 (GREEN phase, running full suite after implementing `run`)
- **Issue:** Adding the second `run` command changed Typer's routing from single-command to multi-command mode. Existing tests in `test_cli.py` (3 tests) and `test_coverage_boost.py` (4 tests) called `runner.invoke(app, ["--dry-run"])` or `runner.invoke(app, [])` without a subcommand name — these all returned exit code 2 (unrecognized argument).
- **Fix:** Updated all 7 affected test invocations to include `"ingest"` as the first argument (e.g., `["ingest", "--dry-run"]`, `["ingest"]`). No implementation changes required.
- **Files modified:** `tests/test_cli.py`, `tests/test_coverage_boost.py`
- **Commit:** `599aff4` (included in task commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - pre-existing tests broken by correct new implementation)
**Impact on plan:** No implementation changes. Test fixes restored 7 previously-passing tests that regressed due to Typer routing change.

## Issues Encountered

- Typer multi-command routing change (documented above). No other issues.

## User Setup Required

None — `--dry-run` works without any environment configuration. Live `run` execution requires the same env vars as `ingest`:
- `KALSHI_BACKTEST_API_KEY_ID`
- `KALSHI_BACKTEST_PRIVATE_KEY_PATH`
- `KALSHI_BACKTEST_DB_PATH` (optional)

## Known Stubs

**1. `_PassThroughStrategy` in `src/kalshi_backtest/cli.py` (run command, ~line 195)**
- **Type:** Inline stub strategy class
- **Reason:** Phase 4 will implement the real Insider Tracker adapter. The stub exists to wire BacktestRunner into the CLI end-to-end without blocking on strategy implementation.
- **Impact:** `kalshi-backtest run` (live mode) executes the full backtest loop but generates zero trades. This is intentional — the infrastructure is wired; only the strategy is stubbed.
- **Resolved by:** Phase 4 plan that implements the real `InsiderTrackerStrategy`.

## Next Phase Readiness

- Phase 3 (Metrics): `BacktestResult.trade_log` and `BacktestResult.daily_pnl` are fully accessible via `BacktestRunner.run()` — metrics can consume them directly
- Phase 4 (Strategy): Replace `_PassThroughStrategy` stub in `cli.py` with real strategy implementation; `--strategy` flag can be added at that point to select between strategies
- CLI-02 requirement fully satisfied

## Self-Check: PASSED

- FOUND: src/kalshi_backtest/cli.py
- FOUND: tests/test_cli.py
- FOUND: .planning/phases/02-simulation-engine/02-05-SUMMARY.md
- FOUND: commit 599aff4

---
*Phase: 02-simulation-engine*
*Completed: 2026-04-06*
