---
phase: 03-metrics-and-reporting
plan: "04"
subsystem: cli
tags: [cli, metrics, reporting, compare, rich]
dependency_graph:
  requires:
    - 03-03  # DashboardBuilder, build_dashboard
    - 03-02  # export_trade_log
    - 03-01  # MetricsCalculator, BacktestMetrics
  provides:
    - enriched-run-command
    - compare-command
    - print_comparison_table
  affects:
    - kalshi_backtest.cli
tech_stack:
  added: []
  patterns:
    - rich.table.Table for terminal comparison output
    - lazy imports inside CLI commands for heavy deps
    - noqa: B008 for typer.Option defaults (standard Typer pattern)
key_files:
  created: []
  modified:
    - kalshi-backtest/src/kalshi_backtest/cli.py
    - kalshi-backtest/tests/test_cli.py
decisions:
  - compare --dry-run uses zero-valued BacktestMetrics(strategy_name=...) directly — no DB, no credentials, no runner
  - print_comparison_table and print_metrics_summary defined as module-level functions (not inside commands) for testability
  - BacktestMetrics.model_copy(update=...) used to override strategy_name after live compare run — stub runner does not propagate name
  - noqa: B008 on typer.Option(Path | None) params — consistent with existing list[str] options in the file
metrics:
  duration_seconds: 152
  completed_date: "2026-04-06"
  tasks_completed: 1
  files_modified: 2
---

# Phase 3 Plan 4: CLI Enrichment (run + compare) Summary

**One-liner:** Rich metrics table wired into `run` command; new `compare --dry-run` command prints side-by-side strategy comparison table via `print_comparison_table`.

## What Was Built

### `print_metrics_summary(metrics, console)`
Module-level function printing a two-column "Metric / Value" Rich table for a single `BacktestMetrics`. Called after every non-dry-run `run` execution. Shows sample_size_warning in bold yellow if `settled_markets < 30`.

### `print_comparison_table(results, console)`
Module-level function printing a multi-column Rich table — one column per strategy — with all nine scalar metrics as rows. Called by `compare` command.

### Enriched `run` command
- Added `--output-dir` option (`Path | None`, default `None`)
- After `runner_obj.run()`, calls `MetricsCalculator().compute(result)` and prints metrics summary
- If `--output-dir` given: creates directory, writes `trade_log.csv` via `export_trade_log` and `dashboard.html` via `DashboardBuilder.write_html`

### New `compare` command
- `--dry-run` path: constructs zero-valued `BacktestMetrics` for "StrategyA" and "StrategyB", calls `print_comparison_table`, exits 0 — no credentials, no DB
- Live path: runs both `_PassThroughStrategy` stubs via `BacktestRunner`, computes metrics, calls `print_comparison_table`
- `--output-dir` option writes `dashboard_StrategyA.html` and `dashboard_StrategyB.html`

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 7ca1ad1 | test | RED — add failing tests for compare command |
| 0a17f8c | feat | GREEN — enrich run + add compare command |

## Test Results

- `tests/test_cli.py`: 12 tests pass (added 3 new: `test_compare_command`, `test_compare_dry_run_no_credentials`, `test_compare_dry_run_shows_both_strategies`)
- Full suite: 221 passed, 0 failed

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

**File size note:** cli.py ended at 463 lines (plan target: under 400). The additional lines are from the `compare` command's live path (strategy loop, credential loading) and two helper functions. All logic is well-factored with no deep nesting. Kept within project max of 800 lines.

## Verification

- [x] `uv run pytest tests/test_cli.py -q` — 12 passed
- [x] `uv run pytest -q` — 221 passed, 0 failed
- [x] `uv run kalshi-backtest compare --dry-run` — exits 0, prints "Strategy Comparison"
- [x] `uv run ruff check src/kalshi_backtest/cli.py` — All checks passed

## Self-Check: PASSED
