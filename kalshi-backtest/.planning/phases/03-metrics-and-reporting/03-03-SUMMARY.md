---
phase: 03-metrics-and-reporting
plan: "03"
subsystem: metrics/dashboard
tags: [plotly, dashboard, visualization, category-breakdown]
dependency_graph:
  requires:
    - 03-02  # BacktestMetrics, MetricsCalculator
    - 03-01  # test scaffold (test_dashboard.py RED tests)
  provides:
    - dashboard.py with build_dashboard, compute_category_breakdown, DashboardBuilder
  affects:
    - metrics/__init__.py (new exports)
    - calculator.py (BacktestMetrics field defaults added)
tech_stack:
  added:
    - plotly.subplots.make_subplots (4-panel layout)
    - plotly.graph_objects (Scatter, Bar traces)
    - quantstats.stats.to_drawdown_series (drawdown panel)
  patterns:
    - CDN Plotly JS (include_plotlyjs="cdn") keeps HTML files small
    - Pydantic field defaults for partial-constructor test fixtures
    - try/except guard on quantstats calls to handle sparse data
key_files:
  created:
    - kalshi-backtest/src/kalshi_backtest/metrics/dashboard.py
  modified:
    - kalshi-backtest/src/kalshi_backtest/metrics/__init__.py
    - kalshi-backtest/src/kalshi_backtest/metrics/calculator.py
decisions:
  - "BacktestMetrics fields given defaults so test fixtures can use partial constructors — preserves backward compatibility with MetricsCalculator.compute() which always supplies all fields"
  - "Monthly resample uses 'ME' (pandas 3.x), not deprecated 'M'"
  - "Trade markers capped at 200 by abs(pnl_cents) to limit HTML size"
  - "Drawdown panel wraps qs.stats.to_drawdown_series in try/except — handles edge case of empty daily_returns"
metrics:
  duration_seconds: 158
  completed_date: "2026-04-06"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 2
---

# Phase 03 Plan 03: Plotly Dashboard Summary

**One-liner:** 4-panel interactive HTML dashboard (equity curve, drawdown, monthly P&L, category breakdown) via Plotly CDN with `build_dashboard`, `compute_category_breakdown`, and `DashboardBuilder`.

## What Was Built

### `compute_category_breakdown(trade_log) -> pd.DataFrame`
Groups trade log rows by ticker category prefix (split on `-`, take index 0). Returns a DataFrame with columns `[category, trades, win_rate_pct, net_pnl_cents]`. Input is never mutated (operates on `.copy()`). Empty input returns an empty DataFrame with the correct column schema.

### `build_dashboard(metrics, trade_log) -> go.Figure`
Builds a 3-row × 2-column Plotly subplot:
- **(1,1)** Equity curve — `go.Scatter` from `metrics.equity_curve`
- **(1,2)** Drawdown % — `qs.stats.to_drawdown_series(daily_returns)` with `fill="tozeroy"`
- **(2,1)** Monthly P&L bar chart — equity curve resampled to month-end (`"ME"`)
- **(2,2)** Category net P&L bar chart — from `compute_category_breakdown`
- **(3,1)** Category win rate bar chart — from `compute_category_breakdown`
- **(3,2)** Empty

Sample-size warning annotation is added when `metrics.sample_size_warning` is True. Trade markers on the equity curve are limited to the top 200 by `abs(pnl_cents)`.

### `DashboardBuilder`
Convenience class: `__init__(metrics, trade_log)` + `write_html(output_path)`. Calls `fig.write_html(str(output_path), full_html=True, include_plotlyjs="cdn")`.

### `BacktestMetrics` defaults (Rule 1 fix)
All fields given sensible defaults so the RED test scaffold `sample_metrics` fixture works with a partial constructor. `MetricsCalculator.compute()` still supplies all fields explicitly — no behavior change in production.

## Test Results

| Test File | Tests | Status |
|-----------|-------|--------|
| test_dashboard.py | 3 | PASSED |
| test_metrics_calculator.py | 6 | PASSED |
| test_trade_log.py | 3 | PASSED |
| **Total** | **12** | **ALL GREEN** |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] BacktestMetrics missing field defaults broke test fixtures**
- **Found during:** Task 2 (running dashboard tests)
- **Issue:** The RED test scaffold `sample_metrics` fixture constructs `BacktestMetrics` with only 7 of 17 required fields. The frozen Pydantic model had no defaults, causing `ValidationError` for 10 missing fields.
- **Fix:** Added sensible defaults to all `BacktestMetrics` fields (`""` for strings, `0.0`/`0` for numerics, `pd.Series(dtype=float)` for Series, `False` for bool). `MetricsCalculator.compute()` continues to supply all fields explicitly — no behavior change in production.
- **Files modified:** `kalshi-backtest/src/kalshi_backtest/metrics/calculator.py`
- **Commit:** 68f3135

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | f71d647 | feat(03-03): implement compute_category_breakdown in dashboard.py |
| Task 2 | 68f3135 | feat(03-03): implement build_dashboard, DashboardBuilder; add defaults to BacktestMetrics |

## Known Stubs

None — all panels render from real data. Empty trade logs and empty equity curves produce empty traces (no placeholder text).

## Self-Check: PASSED
