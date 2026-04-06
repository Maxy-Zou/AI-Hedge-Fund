---
phase: 03-metrics-and-reporting
plan: "01"
subsystem: metrics
tags: [tdd, red-tests, dependencies, quantstats, plotly]
dependency_graph:
  requires: [02-simulation-engine]
  provides: [RED test baseline for metrics module]
  affects: [03-02-PLAN.md, 03-03-PLAN.md, 03-04-PLAN.md]
tech_stack:
  added: [quantstats==0.0.81, plotly==6.6.0]
  patterns: [TDD RED phase — test files import non-existent modules]
key_files:
  created:
    - kalshi-backtest/tests/test_metrics_calculator.py
    - kalshi-backtest/tests/test_trade_log.py
    - kalshi-backtest/tests/test_dashboard.py
  modified:
    - kalshi-backtest/pyproject.toml
    - kalshi-backtest/uv.lock
decisions:
  - plotly resolved to 6.6.0 (plan requested >=5.0) — no conflict with pandas 3.x / numpy 2.x
  - quantstats 0.0.81 pulled in yfinance, scipy, matplotlib as transitive deps — acceptable for analytics library
  - test_dashboard.py imports BacktestMetrics from calculator module (not yet created) to ensure dashboard tests also fail RED
  - sample_size_warning threshold set at 30 distinct settled tickers per MET-07 spec
metrics:
  duration_minutes: 10
  completed_date: "2026-04-06"
  tasks_completed: 2
  files_modified: 5
---

# Phase 3 Plan 01: RED Test Scaffold and Dependency Setup Summary

**One-liner:** quantstats 0.0.81 + plotly 6.6.0 added to venv; 12 RED tests across 3 files covering MET-01, MET-02, MET-03, MET-06, MET-07 — all fail with ModuleNotFoundError until Plan 02 creates the metrics module.

## What Was Built

### Task 1: Dependency declarations and installation

Added `quantstats>=0.0.81` and `plotly>=5.0` to `pyproject.toml` `[project] dependencies`. Ran `uv add quantstats plotly` to resolve, download, and install both packages plus 27 transitive dependencies into the project venv. Resolved versions: quantstats 0.0.81, plotly 6.6.0.

Both packages verified importable via `uv run python -c "import quantstats; import plotly; print('ok')"`.

### Task 2: RED test scaffolds (TDD baseline)

Created three test files, each importing from `kalshi_backtest.metrics.*` — a package that does not yet exist. All 12 tests fail with `ModuleNotFoundError: No module named 'kalshi_backtest.metrics'` at collection time.

**test_metrics_calculator.py** (195 lines, 6 tests):
- `test_sharpe_is_finite` — MetricsCalculator().compute() returns BacktestMetrics with a finite sharpe float
- `test_total_return_positive` — total_return_pct > 0 for net-profitable result
- `test_win_rate_range` — win_rate_pct in [0.0, 100.0]
- `test_sample_warning_true_when_few` — 3 distinct tickers → sample_size_warning True
- `test_sample_warning_false_when_enough` — 30 distinct tickers → sample_size_warning False
- `test_empty_result_no_error` — empty trade_log → total_return_pct == 0.0, no exception

**test_trade_log.py** (138 lines, 3 tests):
- `test_export_columns` — CSV contains pnl_usd, fee_usd, ticker, direction, entry_ts, exit_ts
- `test_dollar_conversion` — pnl_usd == pnl_cents / 100 for each row
- `test_empty_trade_log_no_file` — empty result → no file or zero-row file

**test_dashboard.py** (148 lines, 3 tests):
- `test_equity_curve_trace_present` — Figure has at least one trace named 'Equity'
- `test_write_html_creates_file` — DashboardBuilder.write_html() creates non-empty .html
- `test_category_breakdown_groups` — KXBTC and KXETH rows present from ticker prefix grouping

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | `2a7a2a2` | chore(03-01): add quantstats and plotly dependencies |
| 2 | `b156e63` | test(03-01): add RED test scaffolds for metrics, trade log, and dashboard |

## Verification Results

1. `uv run python -c "import quantstats; import plotly"` — exits 0 (PASS)
2. All 3 test files fail with `ModuleNotFoundError: No module named 'kalshi_backtest.metrics'` (PASS — expected RED state)
3. Test file line counts: test_metrics_calculator.py=195, test_trade_log.py=138, test_dashboard.py=148 (all above minimums)
4. pyproject.toml contains `quantstats>=0.0.81` and `plotly>=5.0` (PASS)

## Known Stubs

None — this plan only adds dependencies and test files. No implementation code was created.

## Self-Check: PASSED

- `/Users/maxzou/Documents/projects/AI Hedgefund/kalshi-backtest/tests/test_metrics_calculator.py` — FOUND
- `/Users/maxzou/Documents/projects/AI Hedgefund/kalshi-backtest/tests/test_trade_log.py` — FOUND
- `/Users/maxzou/Documents/projects/AI Hedgefund/kalshi-backtest/tests/test_dashboard.py` — FOUND
- Commit `2a7a2a2` — FOUND
- Commit `b156e63` — FOUND
