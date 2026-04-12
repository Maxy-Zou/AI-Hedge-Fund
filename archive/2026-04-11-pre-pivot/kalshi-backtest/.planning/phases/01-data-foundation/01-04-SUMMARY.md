---
phase: 01-data-foundation
plan: "04"
subsystem: ingestion
tags: [pipeline, validator, incremental-sync, gap-detection, lookahead-protection, duckdb]
dependency_graph:
  requires: [01-02, 01-03]
  provides: [IngestionPipeline, IngestionResult, DataValidator, ValidationReport, GapRecord]
  affects: [phase-02-backtest-engine]
tech_stack:
  added: [rich]
  patterns: [TDD, incremental-sync, lookahead-protection, circular-import-avoidance]
key_files:
  created:
    - kalshi-backtest/src/kalshi_backtest/ingestion/pipeline.py
    - kalshi-backtest/src/kalshi_backtest/ingestion/validator.py
    - kalshi-backtest/tests/test_pipeline.py
  modified:
    - kalshi-backtest/src/kalshi_backtest/ingestion/__init__.py
    - kalshi-backtest/tests/test_validation.py
decisions:
  - "pipeline/validator excluded from ingestion __init__.py eager imports — circular import via db.repository → ingestion.types → ingestion.__init__ → pipeline → db.repository"
  - "utcnow() retained intentionally — plan explicitly specifies naive UTC discipline; deprecation warning is cosmetic, pipeline is correct"
metrics:
  duration_seconds: 824
  completed_date: "2026-04-04"
  tasks_completed: 2
  files_created: 3
  files_modified: 2
---

# Phase 1 Plan 4: IngestionPipeline + DataValidator Summary

**One-liner:** IngestionPipeline orchestrates MarketFetcher→CandlestickFetcher→MarketRepository with incremental sync and lookahead protection; DataValidator detects gaps using DuckDB LAG() window functions and prints a Rich coverage table.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | IngestionPipeline orchestrator | 968cd1e | pipeline.py, test_pipeline.py |
| 2 | DataValidator + test stubs | ade54b5 | validator.py, __init__.py, test_validation.py |

## What Was Built

### Task 1: IngestionPipeline (968cd1e)

`src/kalshi_backtest/ingestion/pipeline.py` implements the full ingestion orchestrator:

- `IngestionPipeline.run(lookback_days, series_tickers)` — wires MarketFetcher → CandlestickFetcher → MarketRepository
- Incremental sync: calls `repo.get_last_candle_ts(ticker)` before each market's candle fetch; passes `last_ingested_ts` to `CandlestickFetcher.fetch_for_market()` so only new candles are fetched
- Lookahead protection: `safe_result = market.result if market.status == "settled" else None` — result column never written for active/closed markets
- Per-market fault isolation: exceptions logged as warnings, failing ticker appended to `result.markets_failed`, run continues
- `IngestionResult` dataclass: `markets_upserted`, `candles_inserted`, `markets_failed`, `duration_seconds`

### Task 2: DataValidator (ade54b5)

`src/kalshi_backtest/ingestion/validator.py` implements post-ingestion quality checks:

- `DataValidator.validate_ticker(ticker)` → `ValidationReport` with coverage_pct, gap_count, anomaly_count
- Gap detection uses DuckDB `LAG(ts) OVER (PARTITION BY ticker ORDER BY ts)` window function — O(n) SQL, not Python iteration
- `_COVERAGE_QUERY` computes total_candles and expected_days via `DATE_DIFF`
- `_ANOMALY_QUERY` catches prices outside 0-100 cents range
- `validate_all(tickers)` prints Rich table with color-coded gaps and anomalies
- Filled all 3 previously-skipped stubs in `test_validation.py`

## Test Results

```
43 passed, 2 skipped (CLI stubs deferred to plan 05)
```

- `tests/test_pipeline.py`: 4 new tests (store, incremental sync, lookahead, fault isolation)
- `tests/test_validation.py`: 3 stubs replaced with implementations (gap detection, no false positives, report structure)
- `tests/test_schema.py`: DST timestamp roundtrip already passing — verified unchanged

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Circular Import] Excluded pipeline/validator from ingestion `__init__.py` eager imports**
- **Found during:** Task 2 — running tests after updating `__init__.py`
- **Issue:** `db.repository` imports `ingestion.types` at module level; `ingestion.__init__` importing `pipeline` causes a cycle: `db.repository → ingestion.types → ingestion.__init__ → pipeline → db.repository`
- **Fix:** Removed top-level re-exports of `IngestionPipeline`, `IngestionResult`, `DataValidator`, `GapRecord`, `ValidationReport` from `__init__.py`. They remain in `__all__` (documentation) but callers must import directly from submodules. Added docstring explaining the constraint.
- **Files modified:** `src/kalshi_backtest/ingestion/__init__.py`
- **Commit:** ade54b5

## Known Stubs

None — all DATA-04, DATA-05, DATA-06 requirements are fully implemented. The 2 skipped tests in the suite are CLI stubs from `test_cli.py`, intentionally deferred to plan 05.

## Self-Check: PASSED

- FOUND: pipeline.py
- FOUND: validator.py
- FOUND: test_pipeline.py
- FOUND: test_validation.py
- FOUND: 01-04-SUMMARY.md
- FOUND: commit 968cd1e (Task 1)
- FOUND: commit ade54b5 (Task 2)
