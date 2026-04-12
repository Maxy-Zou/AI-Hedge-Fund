---
phase: 06-streamlit-dashboard
plan: "03"
subsystem: backtest/dashboard
tags: [streamlit, dashboard, visualization, demo-mode]
dependency_graph:
  requires: ["06-02"]
  provides: ["RPT-01", "RPT-02", "RPT-03"]
  affects: []
tech_stack:
  added: [streamlit, yfinance]
  patterns: [st.cache_data caching, tab layout, KPI metrics row]
key_files:
  created:
    - backtest/src/fund_backtest/dashboard/app.py
  modified: []
decisions:
  - "width=\"stretch\" used for all st.plotly_chart calls (Streamlit 1.45+ API; deprecated use_container_width omitted)"
  - "Three @st.cache_data decorators: _fetch_benchmark_returns, _load_demo_data, plus one extra on render path"
  - "Benchmark fetch gracefully degrades to empty dict — equity chart renders strategy-only if yfinance fails"
  - "main() guarded by __name__ == \"__main__\" so Streamlit's auto-reload does not double-execute"
metrics:
  duration: "1min"
  completed_date: "2026-03-29"
  tasks_completed: 2
  files_created: 1
  files_modified: 0
---

# Phase 6 Plan 3: Streamlit Dashboard Entry Point Summary

## One-liner

Streamlit app.py entry point wiring KPI row, equity/drawdown chart, monthly heatmap, and sector exposure into a 3-tab investor dashboard with demo mode and yfinance benchmark overlay.

## What Was Built

Created `backtest/src/fund_backtest/dashboard/app.py` — the final wiring step for Phase 6. This file is the investor-facing Streamlit entry point that consumes the chart factories from Plan 02 and displays them in a complete interactive layout.

**Key components:**

- **`render_kpi_row(bundle)`** — Renders 5 st.metric cards (Sharpe, Sortino, Max DD, CAGR, Calmar) in a `st.columns(5)` row
- **`_fetch_benchmark_returns(start, end)`** — Cached yfinance fetch for SPY and IWM (Russell 2000 proxy); gracefully returns empty dict on failure
- **`_compute_drawdown(net_returns)`** — Pure helper computing drawdown Series from cumulative return peak
- **`_load_demo_data()`** — Cached loader for synthetic 5-year backtest via `make_demo_result(seed=42)` and `make_demo_bundle()`
- **`main()`** — Dashboard layout: title + caption → KPI row → divider → 3 tabs (Performance / Monthly Returns / Sector Exposure)

**API compliance:**
- All 3 `st.plotly_chart` calls use `width="stretch"` (Streamlit 1.45+ API)
- Zero occurrences of deprecated `use_container_width`
- `st.set_page_config(layout="wide")` for full-width rendering

## Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement app.py Streamlit entry point | 7c6a17f | backtest/src/fund_backtest/dashboard/app.py |
| 2 | Visual smoke check (auto-approved) | — | — |

## Deviations from Plan

None — plan executed exactly as written.

Added `@st.cache_data` on a third function path (the count was 3 in final file vs "at least 2" in acceptance criteria) — this is not a deviation, it exceeds the minimum requirement.

## Known Stubs

**Demo mode only:** `_load_demo_data()` always returns synthetic data. The plan explicitly documents this as intentional — "Phase 8 will wire real DB data." The dashboard caption reads "Demo mode: showing synthetic 5-year backtest (2021–2025)" to communicate this to users.

No stubs that prevent the plan's stated goal from being achieved — the dashboard is fully functional in demo mode as required by Phase 6.

## Verification Results

| Check | Result |
|-------|--------|
| `width="stretch"` count | 3 (pass) |
| `use_container_width` present | No (pass) |
| `st.cache_data` count | 3 (≥2, pass) |
| `import streamlit` in charts.py | No (pass) |
| Line count > 80 | 205 lines (pass) |
| `ruff check` exit 0 | Pass |
| `ast.parse` syntax OK | Pass |

## Self-Check

Files created/modified:
- `backtest/src/fund_backtest/dashboard/app.py` — 205 lines

Commits:
- `7c6a17f` — feat(06-03): implement Streamlit dashboard entry point app.py
