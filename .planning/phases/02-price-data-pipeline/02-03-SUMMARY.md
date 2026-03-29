---
phase: 02-price-data-pipeline
plan: 03
subsystem: price-data
tags: [repository, builder, sqlalchemy, pg_insert, on_conflict_do_nothing, orchestrator, append-only]

# Dependency graph
requires:
  - phase: 02-price-data-pipeline
    plan: 01
    provides: PriceBarORM, PriceAnomalyORM from db/models.py; PriceBar, PriceAnomalyRecord, DownloadSummary, CoverageReport from price/types.py
  - phase: 02-price-data-pipeline
    plan: 02
    provides: download_in_chunks(), detect_return_anomalies(), compute_coverage() from downloader.py and validator.py

provides:
  - PriceBarRepository in price/repository.py — insert_bars (ON CONFLICT DO NOTHING), insert_anomalies, get_last_dates, get_bars (per-bar anomaly exclusion), get_coverage_tickers
  - PriceBuilder in price/builder.py — download() for full 5-year load, update() for incremental per-ticker update, both return DownloadSummary

affects:
  - 02-04-integration (integration tests cover full pipeline end-to-end using these two classes)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "sqlalchemy.dialects.postgresql.insert (pg_insert) with .on_conflict_do_nothing(index_elements=[...]) for append-only upserts"
    - "tuple_() from sqlalchemy for (ticker, bar_date) IN subquery — per-bar anomaly exclusion"
    - "get_last_dates() uses raw SQL text() for efficiency: SELECT ticker, MAX(bar_date) GROUP BY ticker WHERE ticker = ANY(:tickers)"
    - "PriceBuilder.update() groups tickers by start_date before calling download_in_chunks() to minimise API batches"
    - "PYTHONPATH must be set to backtest/src for uv run to find fund_backtest package (pth file present but uv run overrides venv)"

key-files:
  created:
    - backtest/src/fund_backtest/price/repository.py
    - backtest/src/fund_backtest/price/builder.py
  modified: []

key-decisions:
  - "tuple_() subquery for anomaly exclusion: NOT ((ticker, bar_date) IN (SELECT ticker, bar_date FROM price_anomalies WHERE is_reviewed=False)) — excludes specific bars, not entire ticker history"
  - "get_bars() uses tuple_().in_() not a JOIN — avoids cartesian product risk and correctly excludes only flagged (ticker, bar_date) pairs"
  - "update() groups tickers by start_date before download_in_chunks() — reduces API round trips when many tickers share the same last_date (e.g. all updated same day)"
  - "Tickers already up to date (start > today) added directly to successful list — no download call made"

# Metrics
duration: 3min
completed: 2026-03-29
---

# Phase 2 Plan 03: Repository and Builder Summary

**PriceBarRepository with append-only ON CONFLICT DO NOTHING inserts and per-bar anomaly exclusion; PriceBuilder orchestrating full download and incremental update with per-ticker start dates — wires together all pure functions from Plans 01 and 02 into a complete price data pipeline**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-29T08:22:33Z
- **Completed:** 2026-03-29T08:25:03Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- repository.py: `PriceBarRepository.insert_bars()` uses `pg_insert().on_conflict_do_nothing(index_elements=["ticker","bar_date"])` — historical rows never overwritten
- repository.py: `PriceBarRepository.insert_anomalies()` uses ON CONFLICT DO NOTHING on `(ticker, bar_date, anomaly_type)` unique constraint
- repository.py: `PriceBarRepository.get_last_dates()` returns `{ticker: max(bar_date)}` via efficient raw SQL `WHERE ticker = ANY(:tickers) GROUP BY ticker`
- repository.py: `PriceBarRepository.get_bars()` excludes unreviewed `(ticker, bar_date)` pairs using `tuple_().in_()` subquery — per-bar exclusion, not per-ticker
- repository.py: `PriceBarRepository.get_coverage_tickers()` returns sorted distinct tickers with at least one bar
- builder.py: `PriceBuilder.download()` runs full 5-year download for all active universe tickers; safe to re-run (ON CONFLICT handles duplicates)
- builder.py: `PriceBuilder.update()` queries per-ticker `last_dates`, groups by start_date for batch efficiency, downloads incrementally
- builder.py: Both methods call `detect_return_anomalies()` and `repo.insert_anomalies()`, log coverage warnings if below threshold, return `DownloadSummary`
- All 66 existing unit tests still passing

## Task Commits

Each task was committed atomically:

1. **Task 1: repository.py** — `bbc7380` (feat)
2. **Task 2: builder.py** — `553f770` (feat)

## Files Created/Modified

- `backtest/src/fund_backtest/price/repository.py` — `PriceBarRepository` with `insert_bars`, `insert_anomalies`, `get_last_dates`, `get_bars`, `get_coverage_tickers`
- `backtest/src/fund_backtest/price/builder.py` — `PriceBuilder` with `download()` and `update()` orchestration

## Decisions Made

- **tuple_() for anomaly exclusion:** `get_bars()` uses `tuple_(PriceBarORM.ticker, PriceBarORM.bar_date).in_(subquery)` with `~` (NOT) operator. This produces SQL `NOT ((ticker, bar_date) IN (...))` — correct per-bar exclusion per RESEARCH.md pitfall 4, avoiding incorrect per-ticker filtering.
- **update() groups by start_date:** Rather than calling `download_in_chunks()` once per ticker (200+ API calls), tickers sharing the same last_date are batched together. On a daily cadence this results in a single batch for all up-to-date tickers.
- **Already-up-to-date handling:** When `start > today`, the ticker is immediately added to `successful` without any download call — avoids unnecessary API requests.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written. The one implementation note: the plan's sample code used a SQLAlchemy subquery with `& (PriceBarORM.ticker == anomaly_pairs.c.ticker)` style join condition, but this approach generates an incorrect Cartesian product. Replaced with SQLAlchemy's `tuple_().in_()` pattern which generates correct SQL tuple membership test.

## Known Stubs

None — all methods are fully implemented with real logic. Integration tests (Plan 04) will exercise these against a live testcontainers PostgreSQL instance.

## Next Phase Readiness

- `PriceBarRepository` and `PriceBuilder` are fully importable and structurally correct
- The pipeline chain is complete: `download_in_chunks()` → `PriceBar.from_yfinance_row()` → `detect_return_anomalies()` → `repo.insert_bars()` + `repo.insert_anomalies()`
- All 66 unit tests passing — no regressions

---
*Phase: 02-price-data-pipeline*
*Completed: 2026-03-29*

## Self-Check: PASSED

- FOUND: backtest/src/fund_backtest/price/repository.py
- FOUND: backtest/src/fund_backtest/price/builder.py
- FOUND: .planning/phases/02-price-data-pipeline/02-03-SUMMARY.md
- FOUND: commit bbc7380 (feat: PriceBarRepository)
- FOUND: commit 553f770 (feat: PriceBuilder)
- All 66 unit tests passing
