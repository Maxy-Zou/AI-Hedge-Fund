---
phase: 08-ai-washing-detector-integration
plan: "02"
subsystem: backtest/cli-integration
tags: [cli, integration-test, tdd, end-to-end, pipeline]
dependency_graph:
  requires:
    - "Phase 08-01 AiWashingLoader (AiWashingLoader, SignalLoadError)"
    - "Phase 03 SignalAdapter (adapt() pipeline with shift(1))"
    - "Phase 04 PortfolioSimulator (simulate())"
    - "Phase 05 MetricsEngine (compute())"
    - "Phase 07 ExportBuilder (export_csv, export_json)"
    - "AI Washing Detector shared PostgreSQL database (companies, daily_scores)"
  provides:
    - "`backtest run --signal ai-washing` CLI command on backtest_app Typer subapp"
    - "INT-03: end-to-end pipeline from signal load through metrics without manual steps"
    - "Integration test suite proving full pipeline against real PostgreSQL testcontainer"
  affects:
    - "backtest/src/fund_backtest/cli.py (new run command)"
    - "backtest/tests/unit/test_cli.py (3 new tests)"
    - "backtest/tests/integration/ (new test_ai_washing_integration.py)"
tech_stack:
  added:
    - "pandas (module-level import in cli.py for price_frame pivot)"
    - "testcontainers PostgreSQL for integration test schema creation via raw DDL"
  patterns:
    - "TDD RED-GREEN cycle for CLI unit tests"
    - "Signal guard before load_app_settings() to avoid DB config requirement"
    - "Simplified DDL in integration tests (no detector Alembic migrations)"
    - "autouse fixture for per-test schema drop/recreate isolation"
key_files:
  created:
    - "backtest/tests/integration/test_ai_washing_integration.py"
  modified:
    - "backtest/src/fund_backtest/cli.py"
    - "backtest/tests/unit/test_cli.py"
decisions:
  - "Signal guard before load_app_settings(): unknown signal exits 1 without requiring DATABASE_URL — keeps tests simple and user experience fast"
  - "Module-level imports for AiWashingLoader, PortfolioSimulator, MetricsEngine, SignalAdapter: required for unittest.mock.patch targeting fund_backtest.cli.* namespace"
  - "Simplified DDL in integration tests: CREATE TABLE companies/daily_scores without partitioning — testcontainer has only backtest Alembic migrations, not detector migrations"
  - "autouse fixture drops/recreates AI Washing tables per test: daily_scores inserts are committed so conftest rollback cannot undo them — table recreation is the only reliable isolation"
  - "Synthetic price_frame in pipeline test: random noise around $100 constant price avoids needing price_bars seeded in DB while still exercising the full simulator/metrics stack"
metrics:
  duration: "5 min"
  completed_date: "2026-03-29"
  tasks_completed: 2
  files_created: 1
  files_modified: 2
---

# Phase 08 Plan 02: CLI Integration and End-to-End Pipeline Summary

**One-liner:** `backtest run --signal ai-washing` wires AiWashingLoader through SignalAdapter, PortfolioSimulator, and MetricsEngine with 3 CLI unit tests and 3 PostgreSQL integration tests all green.

## What Was Built

### `backtest run` CLI command (`cli.py`)

Added `@backtest_app.command(name="run")` implementing the 5-stage pipeline:

1. **Load signal** — `AiWashingLoader(session).load()` -> `SignalFrame`
2. **Load prices** — `PriceBarRepository.get_bars()` -> pivot to `PriceFrame`
3. **Adapt** — `SignalAdapter().adapt(signal_frame)` -> `WeightFrame`
4. **Simulate** — `PortfolioSimulator().simulate(weight_frame, price_frame)` -> `PortfolioResult`
5. **Metrics** — `MetricsEngine().compute(portfolio_result)` -> `MetricsBundle`

Optional `--export-all` flag triggers CSV + JSON export after metrics. Signal guard runs before `load_app_settings()` — unknown signals exit 1 without requiring DATABASE_URL. `SignalLoadError` caught with exit 1 + red message; all other exceptions caught with exit 1 + pipeline error.

### CLI unit tests (`test_cli.py`, 3 new tests)

- `test_backtest_run_ai_washing_exits_zero`: full mock pipeline, exit 0, "complete" in output
- `test_backtest_run_exits_1_on_signal_load_error`: `SignalLoadError("scores table is empty")` -> exit 1, "empty" in output
- `test_backtest_run_unknown_signal_exits_1`: `--signal unknown-strategy` -> exit 1, "unknown" in output

### Integration tests (`test_ai_washing_integration.py`, 3 tests)

- `test_loader_returns_signal_frame_from_real_db`: seeds 2 tickers x 3 days, asserts shape (3,2), float dtypes, DatetimeIndex
- `test_loader_raises_on_empty_table`: seeds only companies (no scores), asserts SignalLoadError with "empty"
- `test_full_pipeline_load_adapt_simulate_metrics`: seeds 5 tickers x 60 days, builds synthetic price_frame, runs full pipeline, asserts finite sharpe/cagr/max_drawdown

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 RED | Add failing CLI run tests | f0bec3f | backtest/tests/unit/test_cli.py |
| 1 GREEN | Add backtest run command | 02c5370 | backtest/src/fund_backtest/cli.py, backtest/tests/unit/test_cli.py |
| 2 | Integration test — full pipeline against PostgreSQL testcontainer | 721b64c | backtest/tests/integration/test_ai_washing_integration.py |

## Verification Results

```
=== CLI unit tests ===
tests/unit/test_cli.py::test_backtest_run_ai_washing_exits_zero PASSED
tests/unit/test_cli.py::test_backtest_run_exits_1_on_signal_load_error PASSED
tests/unit/test_cli.py::test_backtest_run_unknown_signal_exits_1 PASSED
19 passed in 7.90s (all existing tests still pass)

=== Integration tests ===
tests/integration/test_ai_washing_integration.py::test_loader_returns_signal_frame_from_real_db PASSED
tests/integration/test_ai_washing_integration.py::test_loader_raises_on_empty_table PASSED
tests/integration/test_ai_washing_integration.py::test_full_pipeline_load_adapt_simulate_metrics PASSED
3 passed in 10.54s

=== Full suite ===
185 passed in 42.63s
Coverage: 90.27% (Required: 80%)
signal/loaders/ai_washing.py: 100% covered
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Signal guard reordered before load_app_settings()**
- **Found during:** Task 1 GREEN (test_backtest_run_unknown_signal_exits_1 failed)
- **Issue:** Plan template placed `load_app_settings()` before the `signal != "ai-washing"` guard. The unknown signal test invoked with no DATABASE_URL env var, causing a Pydantic ValidationError before the guard could run, producing empty output instead of "unknown" in the error.
- **Fix:** Moved the signal guard before `load_app_settings()` — validates the signal name first, no DB config needed for that check.
- **Files modified:** `backtest/src/fund_backtest/cli.py`
- **Commit:** 02c5370

**2. [Rule 2 - Missing] Module-level imports for patchable names**
- **Found during:** Task 1 GREEN (test_backtest_run_ai_washing_exits_zero failed with AttributeError on patch)
- **Issue:** Plan suggested `from fund_backtest.signal.loaders import AiWashingLoader` inside the function body, but `unittest.mock.patch("fund_backtest.cli.AiWashingLoader")` requires the name to exist at module scope.
- **Fix:** Added module-level imports: `AiWashingLoader`, `SignalLoadError`, `SignalAdapter`, `PortfolioSimulator`, `MetricsEngine`, `pd` (pandas). Removed local imports from function body.
- **Files modified:** `backtest/src/fund_backtest/cli.py`
- **Commit:** 02c5370

## Known Stubs

None - the `run` command is fully wired to the real pipeline. No placeholder or demo data is used. The `export` command still uses `make_demo_result()`/`make_demo_bundle()` from Phase 7, but that is outside this plan's scope.

## Self-Check: PASSED
