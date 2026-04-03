---
phase: 05-monitoring-dashboard
plan: "01"
subsystem: dashboard
tags: [streamlit, pandas, queries, read-only, dashboard]
dependency_graph:
  requires:
    - "01-foundation (db/models.py — Market, MarketSnapshot, Signal, Trade)"
    - "01-foundation (db/session.py — Session factory)"
  provides:
    - "dashboard/queries.py — 4 read-only query functions for dashboard panels"
    - "streamlit + pandas available in venv"
  affects:
    - "05-02-PLAN.md (app.py consumes these query contracts directly)"
tech_stack:
  added:
    - "streamlit>=1.45.0 (installed: 1.56.0)"
    - "pandas>=2.2 (installed: 3.0.2)"
  patterns:
    - "Session.query() style (consistent with existing codebase)"
    - "try/except with structlog.warning on all DB errors"
    - "Subquery join pattern for latest-snapshot-per-ticker"
key_files:
  created:
    - "src/kalshi_tracker/dashboard/__init__.py"
    - "src/kalshi_tracker/dashboard/queries.py"
    - "tests/test_dashboard_queries.py"
  modified:
    - "pyproject.toml"
decisions:
  - "streamlit>=1.45.0 declared in pyproject.toml (not optional-dependencies) — dashboard is a first-class feature for v1, not optional"
  - "get_markets uses a subquery join (max captured_at per ticker group) — correct approach for latest-snapshot-per-entity without a lateral join"
  - "realized_pnl_cents always 0 in v1 — Kalshi settled prices not yet stored in DB; documented as TODO for post-v1 schema update"
  - "All 4 query functions wrap in try/except returning empty/zero — dashboard must never crash the UI on DB errors"
metrics:
  duration: "148 seconds"
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_created: 3
  files_modified: 1
  tests_added: 14
---

# Phase 05 Plan 01: Dashboard Dependencies and Query Layer Summary

**One-liner:** Read-only dashboard query layer with 4 typed functions (get_markets, get_recent_signals, get_open_positions, get_pnl_summary) backed by SQLAlchemy Session.query() and 14 passing unit tests.

## What Was Built

Added streamlit and pandas to project dependencies, then implemented the read-only data access layer for the monitoring dashboard.

### Files Created

- **`src/kalshi_tracker/dashboard/__init__.py`** — Package marker for the new dashboard module
- **`src/kalshi_tracker/dashboard/queries.py`** — 4 read-only query functions:
  - `get_markets(session)` — Active markets + latest snapshot via subquery join; returns list of dicts with ticker, title, status, last_price, volume, captured_at
  - `get_recent_signals(session, limit=50)` — Most recent signals ordered by detected_at DESC; returns list of dicts with ticker, signal_type, confidence, detected_at, details
  - `get_open_positions(session)` — Trades with status IN ('pending', 'filled') ordered by placed_at DESC; returns list of dicts with ticker, side, contracts, price_cents, mode, status, placed_at
  - `get_pnl_summary(session)` — Aggregate trade stats; returns dict with trade_count, total_contracts, total_cost_cents, realized_pnl_cents (0 in v1)
- **`tests/test_dashboard_queries.py`** — 14 unit tests using MagicMock (no real DB required); all pass

### Files Modified

- **`pyproject.toml`** — Added `streamlit>=1.45.0` and `pandas>=2.2` to `[project] dependencies`

## Verification Results

```
uv run python -c "import streamlit, pandas; print('ok')"
# → ok

uv run pytest tests/test_dashboard_queries.py -v
# → 14 passed in 0.82s

grep -n "commit|session.add|session.delete" src/kalshi_tracker/dashboard/queries.py
# → PASS: read-only
```

## Commits

| Hash | Message |
|------|---------|
| 469f825 | chore(05-01): add streamlit>=1.45.0 and pandas>=2.2 to project dependencies |
| 453af74 | feat(05-01): implement dashboard queries module with 14 passing tests |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

**`src/kalshi_tracker/dashboard/queries.py` — `get_pnl_summary` `realized_pnl_cents = 0`**

This is an intentional v1 stub documented with a TODO comment. Kalshi does not yet provide settled prices in the database schema, so realized P&L cannot be computed. The field is included in the return dict for Plan 02 (app.py) to display, with a visual indicator that this is always 0 in v1. Resolves when the schema is extended with a `settled_price_cents` column on the Trade model (post-v1).

## Self-Check: PASSED

- `src/kalshi_tracker/dashboard/__init__.py` — EXISTS
- `src/kalshi_tracker/dashboard/queries.py` — EXISTS
- `tests/test_dashboard_queries.py` — EXISTS
- pyproject.toml updated — VERIFIED
- Commit 469f825 — VERIFIED
- Commit 453af74 — VERIFIED
