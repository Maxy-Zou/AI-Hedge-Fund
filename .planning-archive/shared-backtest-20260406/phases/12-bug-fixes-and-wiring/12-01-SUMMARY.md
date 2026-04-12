---
phase: 12-bug-fixes-and-wiring
plan: 01
subsystem: backtest-cli
tags: [bug-fix, cli, benchmark, date-alignment, tdd]
dependency_graph:
  requires: []
  provides: [cli-run-date-intersection, cli-run-benchmark-fetch]
  affects: [backtest/src/fund_backtest/cli.py, backtest/tests/unit/test_cli.py]
tech_stack:
  added: [yfinance imported in cli.py (was only in dashboard/app.py)]
  patterns: [pandas Index.intersection for date alignment, yf.download with graceful except fallback]
key_files:
  created: []
  modified:
    - backtest/src/fund_backtest/cli.py
    - backtest/tests/unit/test_cli.py
decisions:
  - "FIX-02 intersection placed before SignalAdapter.adapt() per Phase 3 constraint: shift(1) must only happen inside the adapter, not in cli.py"
  - "FIX-05 uses SPY only (not IWM) as benchmark — standard for fund reporting; IWM available in dashboard for visual overlay only"
  - "benchmark_returns falls back to None on any Exception — matches MetricsEngine documented default of alpha=0.0/beta=0.0, no crash"
metrics:
  duration: "9 minutes"
  completed_date: "2026-03-30"
  tasks_completed: 2
  files_modified: 2
requirements_satisfied: [FIX-02, FIX-05]
---

# Phase 12 Plan 01: FIX-02 and FIX-05 Bug Fixes Summary

**One-liner:** Signal-price date intersection before adapt() and SPY benchmark fetch before MetricsEngine.compute() — prevents silent zero returns and enables real alpha/beta values.

## What Was Built

Two surgical fixes to `backtest/src/fund_backtest/cli.py:run()`:

**FIX-02 — Signal-Price Date Intersection:**
After Stage 2 builds `price_frame` from the database pivot, the code now computes `common_dates = signal_frame.index.intersection(price_frame.index)`. If no overlap exists, exits 1 with an error message. If partial overlap, logs a structured warning via `_log.warning("signal_price_date_mismatch", ...)`. The trimmed `signal_frame` is then passed to `SignalAdapter().adapt()`. This ensures the WeightFrame and PriceFrame share the same date spine from the start — preventing the `_align_frames()` fallback in the simulator from silently creating zero-return rows on non-overlapping dates.

**FIX-05 — SPY Benchmark Fetch:**
After Stage 4 (`PortfolioSimulator().simulate()`), the code now fetches SPY via `yf.download()` using `portfolio_result.net_returns.index` bounds. On success, `spy_df["Close"].squeeze().pct_change().dropna()` is passed as `benchmark=` to `MetricsEngine().compute()`. On any exception (network failure, empty DataFrame), `benchmark_returns` remains `None` — which `MetricsEngine` handles gracefully with `alpha=0.0, beta=0.0`. This mirrors the pattern from `dashboard/app.py:_fetch_benchmark_returns()`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add failing tests for FIX-02 and FIX-05 (RED) | e181649 | backtest/tests/unit/test_cli.py |
| 2 | Implement FIX-02 and FIX-05 in cli.py:run() (GREEN) | 7ba0fd6 | backtest/src/fund_backtest/cli.py, backtest/tests/unit/test_cli.py |

## Verification

- `test_run_date_intersection`: PASSED — `SignalAdapter.adapt()` received 8-row frame (not 10) when price_frame covered only 8 of 10 signal dates
- `test_run_benchmark_passed`: PASSED — `MetricsEngine.compute()` received non-None `benchmark=` when SPY mock returned non-empty DataFrame
- `test_run_benchmark_fallback`: PASSED — `MetricsEngine.compute()` received `benchmark=None` when `yf.download` raised Exception; exit_code == 0
- Full unit suite: 169 passed, 0 failed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed indentation in test_run_benchmark_passed and test_run_benchmark_fallback**
- **Found during:** Task 2 GREEN verification (first run failed)
- **Issue:** `PriceBarRepository` patch context closed before `PortfolioSimulator` and `MetricsEngine` patches in two test functions. Mock bars were not active when the CLI tried to build `price_frame` via `pivot_table(values="close")`, causing `KeyError: 'close'`.
- **Fix:** Re-indented `PortfolioSimulator`, `MetricsEngine`, and `yf` patch blocks to be children of the `PriceBarRepository` context manager.
- **Files modified:** backtest/tests/unit/test_cli.py
- **Commit:** 7ba0fd6 (same commit as the implementation)

## Known Stubs

None — both fixes wire real computation paths.

## Self-Check: PASSED
