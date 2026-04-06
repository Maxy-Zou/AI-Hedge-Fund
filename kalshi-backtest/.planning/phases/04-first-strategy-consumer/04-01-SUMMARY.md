---
phase: 04-first-strategy-consumer
plan: "01"
subsystem: testing
tags: [tdd, red-scaffold, strategies, brier-score, cli]
dependency_graph:
  requires: []
  provides:
    - "RED tests for InsiderTrackerAdapter (STRAT-01)"
    - "RED tests for ExampleStrategy (STRAT-02)"
    - "RED Brier score tests on BacktestMetrics (MET-04)"
    - "RED CLI --strategy flag test"
    - "sqlite_signals_db fixture for adapter unit tests"
  affects:
    - "kalshi-backtest/tests/test_strategies.py"
    - "kalshi-backtest/tests/test_metrics_calculator.py"
    - "kalshi-backtest/tests/test_cli.py"
    - "kalshi-backtest/tests/conftest.py"
tech_stack:
  added: []
  patterns:
    - "sqlite3 temp-file fixture pattern for cross-process DB access in unit tests"
    - "SimpleNamespace for lightweight MarketSnapshot stand-ins in strategy tests"
key_files:
  created:
    - path: "kalshi-backtest/tests/test_strategies.py"
      purpose: "10 RED tests covering STRAT-01 (InsiderTrackerAdapter) and STRAT-02 (ExampleStrategy)"
  modified:
    - path: "kalshi-backtest/tests/conftest.py"
      purpose: "Added sqlite_signals_db fixture (temp-file SQLite DB) and insert_signal_row helper"
    - path: "kalshi-backtest/tests/test_metrics_calculator.py"
      purpose: "Appended 4 RED Brier score tests (MET-04) with fixture helpers"
    - path: "kalshi-backtest/tests/test_cli.py"
      purpose: "Appended 1 RED --strategy flag test"
decisions:
  - "sqlite_signals_db uses a temp file (not :memory:) so the adapter can open it by URL string — SQLAlchemy not available in this project"
  - "SimpleNamespace used for MarketSnapshot stand-ins to avoid import coupling in test scaffold"
  - "insert_signal_row is a module-level helper (not a fixture) to allow per-test row insertion with flexible params"
  - "Brier score for NO trade: predicted probability = 1 - entry_price/100; outcome = 1.0 if NO settled"
metrics:
  duration_seconds: 480
  completed_date: "2026-04-06T02:39:00Z"
  tasks_completed: 1
  files_modified: 4
---

# Phase 4 Plan 1: RED Test Scaffolds Summary

**One-liner:** TDD RED scaffolds for InsiderTrackerAdapter, ExampleStrategy, Brier score metric, and CLI --strategy flag — 16 new failing tests defining the Phase 4 contract.

## What Was Built

Single task executed: wrote all RED test scaffolds for Phase 4 requirements before any implementation exists.

### conftest.py additions

- `sqlite_signals_db` fixture: yields `(url_string, sqlite3.Connection)` tuple. Creates a temp-file SQLite DB with the Insider Tracker `signals` table schema. Uses a real file (not `:memory:`) so the `InsiderTrackerAdapter` can open it by URL string. Cleaned up after each test.
- `insert_signal_row` helper: module-level function for inserting individual signal rows with keyword args.

### tests/test_strategies.py (new, 235 lines)

10 RED tests across two strategy classes:

**STRAT-01 InsiderTrackerAdapter (6 tests):**
- `test_insider_adapter_generates_signal` — matching DB row → Signal returned
- `test_insider_adapter_no_lookahead` — signal at exactly `snapshot.ts` excluded (strictly `<`)
- `test_insider_adapter_no_signals` — empty table → `[]`
- `test_insider_adapter_skips_held` — ticker in open_positions → `[]`
- `test_insider_adapter_db_error` — bad DB URL → `[]`, no raise
- `test_insider_adapter_confidence_filter` — row below `min_confidence` → filtered

**STRAT-02 ExampleStrategy (4 tests):**
- `test_example_strategy_buys_cheap` — `close_price < threshold` → Signal(direction='yes')
- `test_example_strategy_skips_expensive` — `close_price >= threshold` → `[]`
- `test_example_strategy_at_threshold` — exactly at threshold → `[]` (strictly `<`)
- `test_example_strategy_skips_held` — ticker in open_positions → `[]`
- `test_example_strategy_satisfies_protocol` — `isinstance(ExampleStrategy(), Strategy)` → True

### test_metrics_calculator.py additions (4 tests)

**MET-04 Brier score:**
- `test_brier_score_yes_settlement` — YES at 60¢ settling YES → `brier_score ≈ 0.16`
- `test_brier_score_no_settlement` — NO at 40¢ settling NO → `brier_score ≈ 0.16`
- `test_brier_score_none_when_no_settlement` — all MTM exits → `brier_score is None`
- `test_brier_score_excludes_mtm` — mixed exits → only settlement rows counted

### test_cli.py additions (1 test)

- `test_run_strategy_flag_dry_run` — `run --strategy pass-through --dry-run` exits 0

## RED Confirmation

All new tests fail with the correct error types:

| Test group | Error type | Root cause |
|---|---|---|
| test_strategies.py | `ModuleNotFoundError` | `kalshi_backtest.strategies` module does not exist yet |
| brier score tests | `AttributeError` | `BacktestMetrics` has no `brier_score` attribute yet |
| CLI strategy flag | `AssertionError` (exit code 2) | `--strategy` option not yet registered on `run` command |

All 221 previously passing tests remain GREEN.

## Deviations from Plan

**1. [Rule 3 - Blocking] SQLAlchemy not installed in project**

- **Found during:** Task 1 (conftest.py)
- **Issue:** The plan described using SQLAlchemy for the `sqlite_signals_db` fixture, but `sqlalchemy` is not in the project's dependencies. `import sqlalchemy` raises `ModuleNotFoundError`.
- **Fix:** Replaced SQLAlchemy with stdlib `sqlite3`. Changed fixture from `:memory:` to a `tempfile.NamedTemporaryFile` so the adapter can open the DB by file path URL string. Returns `(url_string, conn)` tuple.
- **Files modified:** `tests/conftest.py`
- **Commit:** 57140ae

## Known Stubs

None — this plan only creates test scaffolds. No production code was written.

## Self-Check: PASSED

- `tests/test_strategies.py` — FOUND (235 lines, 10 test functions)
- `tests/conftest.py` contains `sqlite_signals_db` — FOUND
- `tests/test_metrics_calculator.py` contains `test_brier_score_yes_settlement` — FOUND
- `tests/test_cli.py` contains `test_run_strategy_flag_dry_run` — FOUND
- Commit 57140ae — FOUND
