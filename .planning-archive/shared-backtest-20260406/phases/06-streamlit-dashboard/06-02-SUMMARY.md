---
phase: 06-streamlit-dashboard
plan: "02"
subsystem: dashboard
tags: [tdd, plotly, charts, green-phase, RPT-01, RPT-02, RPT-03]
dependency_graph:
  requires:
    - 06-01  # RED test suite and chart stubs from scaffold plan
  provides:
    - Three working Plotly chart factory functions (no NotImplementedError)
    - 10/10 GREEN tests for all chart assertions
  affects:
    - 06-03  # app.py will consume charts.py
tech_stack:
  added: []
  patterns:
    - TDD GREEN phase — stubs replaced with working implementations
    - make_subplots(rows=2) for equity+drawdown dual-panel chart
    - px.imshow with color_continuous_midpoint=0.0 for monthly heatmap
    - go.Bar with orientation='h' for sector exposure chart
    - Private helper _annotate_drawdown_episodes for episode detection
key_files:
  created: []
  modified:
    - backtest/src/fund_backtest/dashboard/charts.py
decisions:
  - "ME resample alias used (not M) — required for pandas 3.x month-end compatibility"
  - "_annotate_drawdown_episodes handles open-ended trailing episodes (no closing transition at end of series)"
  - "Edge case guard: empty/short Series returns minimal Figure with 'Insufficient data' annotation rather than crashing"
metrics:
  duration: "15min"
  completed: "2026-03-29"
  tasks_completed: 2
  files_created: 0
  files_modified: 1
---

# Phase 6 Plan 02: Chart Factory GREEN Implementation Summary

**One-liner:** Three Plotly chart factory functions implemented (equity+drawdown subplot, monthly RdYlGn heatmap, horizontal sector bar) turning all 10 RED TDD tests GREEN with 91% coverage.

## What Was Built

### Task 1: Equity+Drawdown and Monthly Heatmap (RPT-01, RPT-02)

**`build_equity_drawdown_chart`** — 2-row Plotly subplot:
- Row 1 (65%): Cumulative equity curve for strategy (`#1f77b4`) plus optional dashed benchmark overlays
- Row 2 (35%): Drawdown area fill (`rgba(220,50,50,0.3)`) with `fill="tozeroy"`
- Episode annotations via `_annotate_drawdown_episodes` for episodes below -5% threshold
- Edge case: empty/< 2 row Series returns minimal Figure with "Insufficient data" annotation

**`_annotate_drawdown_episodes`** — private episode annotation helper:
- Iterates contiguous segments where drawdown < threshold
- Annotates at each episode's max-depth point with depth and duration text
- Handles open-ended episodes that extend to the last data row (no closing transition)

**`build_monthly_heatmap`** — year×month heatmap:
- Resamples with `"ME"` (month-end) — required for pandas 3.x; `"M"` raises FutureWarning
- `px.imshow` with `color_continuous_midpoint=0.0` to anchor red/green split at zero (not data mean)
- `text_auto=".1%"` for cell labels; 5-year pivot covering 2021–2025

### Task 2: Sector Exposure Chart (RPT-03) + Full GREEN Suite

**`build_sector_exposure_chart`** — horizontal bar chart:
- `pd.Series(ticker_sectors)` + `positions.columns.intersection(sector_map.index)` for unknown-ticker safety
- `positions[valid].abs().mean()` — time-average absolute weights (both long and short contribute positively)
- `.groupby(sector_map[valid]).sum().sort_values(ascending=True)` — largest sector at top
- `go.Bar(orientation="h")` with `margin={"l": 200}` for long sector names

## Verification Results

All plan success criteria met:

1. `uv run pytest tests/unit/test_dashboard_charts.py -v` — **10/10 PASSED**
2. `grep "import streamlit" charts.py` — no output (clean separation)
3. `grep 'resample("M")' charts.py` — no output ("ME" used)
4. `uv run ruff check charts.py` — All checks passed
5. `charts.py` coverage: **91%** (target: 80%)

## Deviations from Plan

None — plan executed exactly as written. All interface patterns from the `<interfaces>` block applied without modification.

**Note on overall unit suite coverage:** `uv run pytest tests/unit/ --cov-fail-under=80` reports 73% total due to pre-existing gaps in `price/repository.py` (35%) and `universe/builder.py` (62%) — both untouched by this plan. This is a pre-existing issue out of scope for Plan 06-02. The `charts.py` module itself is at 91%.

## Commits

| Task | Hash | Message |
|------|------|---------|
| Task 1 | 8bfc54e | feat(06-02): implement equity+drawdown chart and monthly heatmap (RPT-01, RPT-02) |
| Task 2 | 3b97f76 | feat(06-02): implement sector exposure chart and ruff-format charts.py (RPT-03) |

## Known Stubs

None — all three chart functions are fully implemented. The NotImplementedError stubs from 06-01 are replaced.

## Self-Check: PASSED
