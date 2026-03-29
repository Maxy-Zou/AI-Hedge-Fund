---
phase: 08-ai-washing-detector-integration
plan: "01"
subsystem: backtest/signal-loaders
tags: [signal-loader, integration-boundary, tdd, ai-washing]
dependency_graph:
  requires:
    - "Phase 03 Signal Adapter (SignalFrame type alias, validator)"
    - "AI Washing Detector shared PostgreSQL database (daily_scores, companies tables)"
  provides:
    - "AiWashingLoader: converts daily_scores rows to SignalFrame"
    - "SignalLoadError: typed exception for all loader failure modes"
    - "signal/loaders/ subdirectory establishing the loader pattern for future strategies"
  affects:
    - "backtest/src/fund_backtest/signal/ (new loaders subpackage)"
tech_stack:
  added:
    - "sqlalchemy.text() for raw SQL cross-module query"
    - "pandas.pivot_table(aggfunc='last') for deduplication"
  patterns:
    - "DB-as-integration-boundary: no Python cross-package imports (no 'from ai_washer import')"
    - "TDD RED-GREEN cycle"
    - "structlog contextual binding in loader"
key_files:
  created:
    - "backtest/src/fund_backtest/signal/loaders/__init__.py"
    - "backtest/src/fund_backtest/signal/loaders/ai_washing.py"
    - "backtest/tests/unit/test_ai_washing_loader.py"
  modified: []
decisions:
  - "DB-as-integration-boundary: AiWashingLoader uses sqlalchemy.text() raw SQL — no 'from ai_washer import' anywhere in backtest package. Database is the only coupling point."
  - "pivot_table(aggfunc='last') for deduplication: most recently inserted row wins when multiple scores share (ticker, date) — matches detector upsert pattern"
  - "No shift(1) in loader: SignalAdapter.adapt() applies shift(1) as final step; adding it here would create 2-day look-ahead lag"
  - "SignalLoadError(RuntimeError): typed exception wraps both OperationalError (DB unavailable) and empty-table cases with descriptive messages"
metrics:
  duration: "1 min"
  completed_date: "2026-03-29"
  tasks_completed: 2
  files_created: 3
  files_modified: 0
---

# Phase 08 Plan 01: AiWashingLoader Integration Boundary Summary

**One-liner:** AiWashingLoader bridges AI Washing Detector and backtester via raw SQL JOIN + pivot_table, returning SignalFrame from shared PostgreSQL with typed SignalLoadError on failure.

## What Was Built

Implemented the cross-module signal ingestion layer (`signal/loaders/`) that reads AI Washing Risk Scores from the shared PostgreSQL database and converts them into the SignalFrame contract. This establishes the integration boundary between the AI Washing Detector and the backtesting framework — the database is the only coupling point with zero Python cross-package imports.

### Key Components

**`signal/loaders/ai_washing.py`** (150 lines):
- `SignalLoadError(RuntimeError)`: typed exception covering empty-table and DB-unavailable failures
- `AiWashingLoader.__init__(session)`: binds session + structlog logger
- `AiWashingLoader.load()`: executes `_SCORE_QUERY` via `sqlalchemy.text()`, raises on `OperationalError` before checking empty rows, returns `_pivot()` result
- `AiWashingLoader._pivot(rows)`: `pd.DataFrame → pivot_table(aggfunc='last') → DatetimeIndex tz-naive → .astype(float)`

**`signal/loaders/__init__.py`** (13 lines):
- Re-exports `AiWashingLoader` and `SignalLoadError` as public API

**`tests/unit/test_ai_washing_loader.py`** (145 lines):
- 5 unit tests covering all INT-02 behaviors with mocked sessions
- TDD RED-GREEN cycle confirmed (ImportError → 5 passed)

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write failing unit tests (RED) | 0f776cd | backtest/tests/unit/test_ai_washing_loader.py |
| 2 | Implement AiWashingLoader (GREEN) | 829a62e | backtest/src/fund_backtest/signal/loaders/__init__.py, backtest/src/fund_backtest/signal/loaders/ai_washing.py |

## Verification Results

```
tests/unit/test_ai_washing_loader.py::TestAiWashingLoaderHappyPath::test_load_returns_signal_frame PASSED
tests/unit/test_ai_washing_loader.py::TestAiWashingLoaderHappyPath::test_signal_frame_contract PASSED
tests/unit/test_ai_washing_detector-integration/TestAiWashingLoaderErrors::test_load_raises_on_empty PASSED
tests/unit/test_ai_washing_loader.py::TestAiWashingLoaderErrors::test_load_raises_on_missing_table PASSED
tests/unit/test_ai_washing_loader.py::TestAiWashingLoaderDedup::test_dedup_same_day_scores PASSED

163 passed in 17.72s (full unit suite — no regressions)
```

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - AiWashingLoader is fully wired to execute the SQL query and return real data. No mock/placeholder values flow to any rendering or downstream consumer.

## Self-Check: PASSED

Files exist:
- FOUND: backtest/src/fund_backtest/signal/loaders/__init__.py
- FOUND: backtest/src/fund_backtest/signal/loaders/ai_washing.py
- FOUND: backtest/tests/unit/test_ai_washing_loader.py

Commits exist:
- FOUND: 0f776cd (test RED)
- FOUND: 829a62e (feat GREEN)

No ai_washer imports in backtest/src/ (grep confirms only doc comments, not import statements).
