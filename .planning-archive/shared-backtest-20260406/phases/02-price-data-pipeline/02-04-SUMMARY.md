---
phase: 02-price-data-pipeline
plan: 04
subsystem: price-data
tags: [cli, typer, integration-tests, testcontainers, postgresql, on_conflict_do_nothing, returning]

# Dependency graph
requires:
  - phase: 02-price-data-pipeline
    plan: 03
    provides: PriceBarRepository, PriceBuilder from price/repository.py and price/builder.py

provides:
  - data_app Typer subgroup in cli.py: download, update, coverage commands
  - integration test suite in tests/integration/test_price_pipeline.py covering DATA-01..DATA-04, DATA-06

affects:
  - Phase 3+ consumers: full price pipeline is now CLI-operable and integration-verified

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "pg_insert().on_conflict_do_nothing().returning(Model.id) — use RETURNING to count actual inserts; psycopg3 returns rowcount=-1 for multi-row ON CONFLICT DO NOTHING without RETURNING"
    - "autouse fixture DELETE FROM tables before each integration test — compensates for explicit session.commit() inside repository methods which prevents conftest rollback from cleaning up"
    - "patch('fund_backtest.price.downloader.yf.download') for mocking yfinance in integration tests"

key-files:
  created:
    - backtest/tests/integration/test_price_pipeline.py
  modified:
    - backtest/src/fund_backtest/cli.py
    - backtest/src/fund_backtest/price/repository.py

key-decisions:
  - "RETURNING clause for insert rowcount: pg_insert().on_conflict_do_nothing().returning(id) gives exact inserted count; without RETURNING, psycopg3 returns -1 for multi-row batch inserts"
  - "autouse clean_price_tables fixture deletes from price_anomalies, price_bars, universe_tickers before each integration test to avoid inter-test contamination from committed transactions"

# Metrics
duration: 4min
completed: 2026-03-29
---

# Phase 2 Plan 04: CLI and Integration Tests Summary

**Three CLI commands (data download, update, coverage) wiring PriceBuilder/PriceBarRepository to Typer; 9 integration tests against PostgreSQL testcontainer proving idempotency, incremental update, anomaly exclusion, and mocked yfinance end-to-end; fixed insert_bars() and insert_anomalies() rowcount using RETURNING clause**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-29T08:27:20Z
- **Completed:** 2026-03-29T08:31:22Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- cli.py: `data_app` Typer subgroup registered as `data` on main app
- cli.py: `download` command — calls `PriceBuilder.download(dry_run)`, prints Rich table with requested/successful/failed/bars_inserted metrics
- cli.py: `update` command — calls `PriceBuilder.update()`, prints Rich table with incremental metrics
- cli.py: `coverage` command — queries `PriceBarRepository.get_coverage_tickers()` + raw SQL for min/max date + `PriceAnomalyORM` unreviewed count, prints Rich table
- cli.py: all three commands follow identical error-handling pattern to `universe_app` (try/except + `log.exception` + `typer.Exit(1)`)
- repository.py: fixed `insert_bars()` and `insert_anomalies()` to use `.returning(id)` — resolves psycopg3 returning `rowcount=-1` for multi-row ON CONFLICT DO NOTHING inserts
- test_price_pipeline.py: 9 integration tests covering:
  - `test_insert_bars_populates_price_bars_table` — 3 rows with correct ticker/date/close_cents
  - `test_insert_bars_idempotent_on_conflict_do_nothing` — second insert returns 0
  - `test_update_appends_only_new_bars` — get_last_dates reflects max date; later insert adds rows
  - `test_anomaly_record_inserted_for_spike` — anomaly persisted with is_reviewed=False
  - `test_get_bars_excludes_anomalous_bar` — unreviewed anomaly hides specific (ticker, bar_date)
  - `test_get_bars_includes_anomalous_bar_when_reviewed` — reviewed anomaly no longer excluded
  - `test_price_builder_download_with_mocked_yfinance` — 2 tickers × 5 bars = 10 rows
  - `test_price_builder_download_dry_run_no_db_writes` — dry_run inserts 0 rows
  - `test_price_builder_update_incremental` — pre-seeded bar not duplicated after update
- All 82 tests pass; 82.78% coverage (≥ 80% threshold)

## Task Commits

Each task was committed atomically:

1. **Task 1: CLI data subgroup** — `38ba6fe` (feat)
2. **Task 2: Integration tests + rowcount fix** — `76f2bf0` (feat)

## Files Created/Modified

- `backtest/src/fund_backtest/cli.py` — added data_app subgroup with download, update, coverage commands
- `backtest/tests/integration/test_price_pipeline.py` — 9 integration tests for full price pipeline
- `backtest/src/fund_backtest/price/repository.py` — fixed rowcount via RETURNING clause

## Decisions Made

- **RETURNING clause for rowcount:** `pg_insert().on_conflict_do_nothing().returning(PriceBarORM.id)` followed by `len(result.all())`. Without RETURNING, psycopg3 returns `-1` for multi-row batch inserts with ON CONFLICT — this is a driver limitation, not a bug. Using RETURNING gives the exact set of inserted IDs.
- **autouse DELETE fixture:** `insert_bars()` explicitly calls `session.commit()`, so the conftest.py `session.rollback()` teardown cannot undo committed inserts. Added `clean_price_tables` autouse fixture that DELETEs from price_anomalies, price_bars, and universe_tickers at the start of each test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `insert_bars()` and `insert_anomalies()` rowcount returning -1**
- **Found during:** Task 2 (RED → GREEN phase)
- **Issue:** `result.rowcount` returns `-1` for psycopg3 multi-row `ON CONFLICT DO NOTHING` inserts without `RETURNING` clause. Test `test_insert_bars_populates_price_bars_table` asserted `inserted == 3` but got `-1`.
- **Fix:** Added `.returning(PriceBarORM.id)` / `.returning(PriceAnomalyORM.id)` to both insert statements; use `len(result.all())` to count the returned IDs (exact count of rows actually inserted).
- **Files modified:** `backtest/src/fund_backtest/price/repository.py`
- **Commit:** `76f2bf0`

**2. [Rule 2 - Missing] Added `clean_price_tables` autouse fixture for test isolation**
- **Found during:** Task 2 (first test passed; second test failed due to leftover data)
- **Issue:** `insert_bars()` commits explicitly, so conftest `session.rollback()` couldn't undo prior inserts. Tests sharing the session-scoped testcontainer accumulated data between runs.
- **Fix:** Added `autouse=True` `clean_price_tables` fixture that DELETEs all price/universe test data before each test.
- **Files modified:** `backtest/tests/integration/test_price_pipeline.py`
- **Commit:** `76f2bf0`

## Known Stubs

None — all commands are fully wired to real PriceBuilder/PriceBarRepository implementations.

## Phase 2 Requirements Coverage

| Requirement | Test | Status |
|-------------|------|--------|
| DATA-01: Download 5-year OHLCV | test_price_builder_download_with_mocked_yfinance | PASSED |
| DATA-02: Incremental update | test_price_builder_update_incremental | PASSED |
| DATA-03: Idempotent insert | test_insert_bars_idempotent_on_conflict_do_nothing | PASSED |
| DATA-04: Anomaly detection | test_anomaly_record_inserted_for_spike | PASSED |
| DATA-06: Anomaly exclusion in queries | test_get_bars_excludes_anomalous_bar, test_get_bars_includes_anomalous_bar_when_reviewed | PASSED |

---
*Phase: 02-price-data-pipeline*
*Completed: 2026-03-29*

## Self-Check: PASSED

- FOUND: backtest/tests/integration/test_price_pipeline.py
- FOUND: backtest/src/fund_backtest/cli.py
- FOUND: backtest/src/fund_backtest/price/repository.py
- FOUND: .planning/phases/02-price-data-pipeline/02-04-SUMMARY.md
- FOUND: commit 38ba6fe (feat(02-04): add data_app CLI subgroup)
- FOUND: commit 76f2bf0 (feat(02-04): integration tests and rowcount fix)
- All 82 tests passing; 82.78% coverage (>= 80%)
