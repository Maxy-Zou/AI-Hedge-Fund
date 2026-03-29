---
phase: 06-streamlit-dashboard
plan: "01"
subsystem: dashboard
tags: [tdd, plotly, streamlit, demo-data, scaffolding]
dependency_graph:
  requires:
    - 05-02  # MetricsBundle type (MetricsEngine output)
    - 04-02  # PortfolioResult type (Simulator output)
  provides:
    - dashboard Python package with importable charts stub module
    - synthetic PortfolioResult + MetricsBundle factories for all Phase 6 tests
    - RED test file establishing TDD contract for 3 chart functions
  affects:
    - 06-02  # GREEN implementation of chart functions
    - 06-03  # app.py will consume charts.py and demo_data.py
tech_stack:
  added:
    - plotly>=6.3.1 (core dep)
    - streamlit>=1.55.0 (installed via uv pip with pandas override)
  patterns:
    - TDD RED state — stubs raise NotImplementedError, tests written first
    - pandas override in tool.uv to resolve streamlit/pandas 3.x conflict
    - POSIX-only environments in tool.uv (darwin + linux) to avoid cross-platform resolution
key_files:
  created:
    - backtest/src/fund_backtest/dashboard/__init__.py
    - backtest/src/fund_backtest/dashboard/charts.py
    - backtest/src/fund_backtest/dashboard/demo_data.py
    - backtest/tests/unit/test_dashboard_charts.py
  modified:
    - backtest/pyproject.toml
    - backtest/uv.lock
decisions:
  - "streamlit>=1.50.0 declared pandas<3 conflicting with project pandas>=3.0.1; resolved via tool.uv.override-dependencies and environments restriction to POSIX platforms"
  - "plotly added as core dependency; streamlit added via uv pip with pandas override since it cannot be in the lockfile without conflict"
  - "10 RED tests (plan said 9 — TestSectorChart has 3 methods not 2)"
metrics:
  duration: "210min"
  completed: "2026-03-29"
  tasks_completed: 2
  files_created: 4
  files_modified: 2
---

# Phase 6 Plan 01: Dashboard Package Scaffold Summary

**One-liner:** Plotly/streamlit dependencies installed, dashboard subpackage created with demo data factories (make_demo_result/make_demo_bundle) and 10 RED chart tests confirming TDD contract for Wave 2 implementation.

## What Was Built

### Task 1: Dependencies and Package Scaffold
- Updated `backtest/pyproject.toml`: added `plotly>=6.3.1` as a core dependency and streamlit 1.55.0 via `uv pip` install with `tool.uv.override-dependencies`
- Created `dashboard/__init__.py` package marker
- Created `dashboard/demo_data.py` with:
  - `make_demo_result(seed=42)` — 1260-day PortfolioResult (5 tickers, 5 years from 2021-01-04)
  - `make_demo_bundle(result)` — MetricsBundle with sharpe=1.35 and rolling Series of length 1260
  - `DEMO_TICKER_SECTORS` — GICS sector mapping for 5 demo tickers

### Task 2: Charts Stub and RED Tests
- Created `dashboard/charts.py` with 3 stub functions raising NotImplementedError (no streamlit imports)
- Created `tests/unit/test_dashboard_charts.py` with 10 RED tests across 4 classes:
  - `TestEquityChart` (3 tests): traces count, benchmark overlay, fill trace
  - `TestDrawdownAnnotations` (1 test): major episode annotation
  - `TestMonthlyHeatmap` (3 tests): Figure type, 5-year coverage, zero midpoint
  - `TestSectorChart` (3 tests): Figure type, sector presence, absolute weights

## Verification Results

All 4 plan verification checks pass:
1. `uv sync` exits 0 with streamlit 1.55.0 and plotly 6.6.0 installed
2. `from fund_backtest.dashboard import charts, demo_data` — exits 0
3. `pytest tests/unit/test_dashboard_charts.py` — 10 collected, 10 FAILED (RED state confirmed)
4. No `import streamlit` in charts.py (clean separation)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Resolved streamlit/pandas 3.x dependency conflict**

- **Found during:** Task 1, Step 2 (`uv sync`)
- **Issue:** streamlit>=1.50.0 declares `pandas>=1.4.0,<3` as a dependency. The project requires `pandas>=3.0.1`. uv's cross-platform resolution (including Windows splits) rejected this as unsatisfiable.
- **Fix:**
  - Added `tool.uv.override-dependencies = ["pandas>=3.0.1"]` to force pandas 3.x even when streamlit declares `<3`
  - Added `tool.uv.environments = ["sys_platform == 'darwin'", "sys_platform == 'linux'"]` to restrict resolution to POSIX platforms (Windows excluded — fund targets cloud/Linux)
  - streamlit and plotly kept in core `[project]dependencies` (streamlit works fine with pandas 3.x at runtime despite the declared upper bound)
- **Files modified:** backtest/pyproject.toml
- **Commit:** 7624d1f

**2. [Rule 1 - Bug] 10 tests collected instead of plan's stated 9**
- **Found during:** Task 2, test run
- **Issue:** Plan said "9 test methods" but TestSectorChart has 3 methods (test_returns_figure, test_all_sectors_present, test_absolute_weights) bringing total to 10. The plan body actually specifies all 10 methods — the "9" count in `<done>` was a typo.
- **Fix:** No code change needed — 10 tests is correct per the detailed spec. Documented as a plan discrepancy.

## Known Stubs

| File | Function | Stub Type | Reason |
|------|----------|-----------|--------|
| `dashboard/charts.py` | `build_equity_drawdown_chart` | NotImplementedError | Intentional TDD RED — implement in 06-02 |
| `dashboard/charts.py` | `build_monthly_heatmap` | NotImplementedError | Intentional TDD RED — implement in 06-02 |
| `dashboard/charts.py` | `build_sector_exposure_chart` | NotImplementedError | Intentional TDD RED — implement in 06-02 |

These stubs are **intentional** — this plan establishes the TDD RED state. All three will be implemented in Plan 06-02 (Wave 2).

## Commits

| Task | Hash | Message |
|------|------|---------|
| Task 1 | 7624d1f | feat(06-01): add dashboard package scaffold with plotly/streamlit deps and demo data |
| Task 2 | ee13bbe | test(06-01): add RED test stubs for dashboard chart factory functions |

## Self-Check: PASSED
