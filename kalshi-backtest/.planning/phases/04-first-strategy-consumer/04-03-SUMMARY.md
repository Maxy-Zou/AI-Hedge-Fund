---
phase: 04-first-strategy-consumer
plan: "03"
subsystem: metrics + cli
tags: [brier-score, metrics, cli, strategy-registry, MET-04, STRAT-01, STRAT-02]
dependency_graph:
  requires:
    - "04-01"  # strategies module with STRATEGY_REGISTRY
    - "03-02"  # BacktestMetrics model and MetricsCalculator
  provides:
    - brier_score field on BacktestMetrics
    - _compute_brier_score() helper
    - --strategy CLI flag dispatching to STRATEGY_REGISTRY
    - --strategy-a / --strategy-b flags on compare command
    - Brier Score row in metrics display tables
  affects:
    - kalshi-backtest/src/kalshi_backtest/metrics/calculator.py
    - kalshi-backtest/src/kalshi_backtest/cli.py
    - kalshi-backtest/.env.example
tech_stack:
  added: []
  patterns:
    - numpy vectorized computation for Brier score
    - STRATEGY_REGISTRY dispatch replacing inline stubs
key_files:
  created: []
  modified:
    - kalshi-backtest/src/kalshi_backtest/metrics/calculator.py
    - kalshi-backtest/src/kalshi_backtest/cli.py
    - kalshi-backtest/.env.example
decisions:
  - "brier_score is float | None (not float) — None distinguishes 'no settlement data' from 'perfect calibration (0.0)'"
  - "NO direction uses probability complement: (100 - entry_price) / 100, not entry_price / 100"
  - "STRATEGY_REGISTRY dispatch replaces all inline _PassThroughStrategy stubs in CLI"
  - "insider-tracker fail-fast: checks KALSHI_TRACKER_DATABASE_URL before instantiating adapter"
  - "Brier Score row added to _SCALAR_ROWS once — propagates automatically to both print_metrics_summary and print_comparison_table"
metrics:
  duration_minutes: 15
  completed_date: "2026-04-06"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Phase 4 Plan 3: Brier Score and Strategy Registry Wiring Summary

**One-liner:** Brier score calibration metric (MET-04) added to BacktestMetrics via settlement-only numpy computation, and --strategy CLI flag wired to STRATEGY_REGISTRY replacing all inline stub classes.

## Objective

Close the final two RED test groups from Phase 4:
1. 4 Brier score tests in `test_metrics_calculator.py` — `AttributeError: no brier_score field`
2. 1 CLI --strategy test in `test_cli.py` — `No such option: --strategy`

## Tasks Completed

### Task 1: Add brier_score to BacktestMetrics and MetricsCalculator

**Commit:** `c29eac8`
**Files:** `src/kalshi_backtest/metrics/calculator.py`

- Added `import numpy as np` to calculator imports
- Added `brier_score: float | None = None` field to `BacktestMetrics` after `sample_size_warning`
- Added `_compute_brier_score(trade_log)` private helper:
  - Filters `trade_log` to `exit_reason == "settlement"` rows only
  - Returns `None` immediately if no settlement rows exist
  - Computes predicted probability: `entry_price / 100` for YES, `(100 - entry_price) / 100` for NO
  - Computes outcome: `1.0` if the held direction won, `0.0` if it lost
  - Returns `float(np.mean((predicted - outcome) ** 2))`
- Wired `brier_score=None` into the empty-guard `BacktestMetrics` return
- Added `brier_score = _compute_brier_score(result.trade_log)` call before the full return
- Added `brier_score=brier_score` to the full `BacktestMetrics` constructor call

**Verification:** All 4 Brier score tests GREEN (`test_brier_score_yes_settlement`, `test_brier_score_no_settlement`, `test_brier_score_none_when_no_settlement`, `test_brier_score_excludes_mtm`)

### Task 2: Wire --strategy flag into CLI run and compare commands

**Commit:** `5f221cf`
**Files:** `src/kalshi_backtest/cli.py`, `.env.example`

- Added `("Brier Score", lambda m: ...)` entry to `_SCALAR_ROWS` — displays `0.1234` or `N/A`
- Added `--strategy` option to `run` command (default: `"pass-through"`)
- Replaced inline `_PassThroughStrategy` stub in `run()` with `STRATEGY_REGISTRY` dispatch
- Added fail-fast guard: if `strategy_name == "insider-tracker"` and `KALSHI_TRACKER_DATABASE_URL` not set, prints clear error and exits 1
- Added `--strategy-a` / `--strategy-b` options to `compare` command (defaults: `"pass-through"` / `"example"`)
- Replaced inline `_PassThroughStrategy` stub in `compare()` with same `STRATEGY_REGISTRY` dispatch pattern
- Updated `.env.example` to document `KALSHI_TRACKER_DATABASE_URL` as commented-out optional var

**Verification:** All 13 CLI tests GREEN including new `test_run_strategy_flag_dry_run`

## Test Results

- Full test suite: **237 passed, 0 failed** (15 deprecation warnings — pre-existing)
- All 5 previously RED tests now GREEN

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all wired paths are live. The `--strategy insider-tracker` path requires a real PostgreSQL database URL at runtime, but the CLI properly fails fast with a clear message when the URL is absent, so the stub behavior is intentional and documented.

## Self-Check: PASSED

- `src/kalshi_backtest/metrics/calculator.py` — modified, contains `brier_score`
- `src/kalshi_backtest/cli.py` — modified, contains `--strategy` and `STRATEGY_REGISTRY`
- `.env.example` — modified, contains `KALSHI_TRACKER_DATABASE_URL`
- Commit `c29eac8` — verified in git log
- Commit `5f221cf` — verified in git log
- 237 tests passing
