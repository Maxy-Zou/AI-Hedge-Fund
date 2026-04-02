---
phase: 02-price-data-pipeline
plan: 01
subsystem: database
tags: [sqlalchemy, alembic, pydantic, yfinance, price-data, cents, immutable]

# Dependency graph
requires:
  - phase: 01-universe-and-sector-data
    provides: Base, TimestampMixin, ORM patterns, migration 001 as down_revision anchor

provides:
  - PriceBarORM and PriceAnomalyORM SQLAlchemy models in db/models.py
  - Alembic migration 002 creating price_bars and price_anomalies tables
  - price/types.py with PriceBar, PriceAnomalyRecord, DownloadSummary, CoverageReport
  - price_to_cents() helper using round() semantics
  - PriceSettings Pydantic config class with default thresholds
  - load_price_settings() factory function

affects:
  - 02-02-downloader (uses PriceBar.from_yfinance_row, DownloadSummary, PriceSettings)
  - 02-03-validator (uses PriceAnomalyRecord, CoverageReport, PriceSettings thresholds)
  - 02-04-repository (uses PriceBarORM, PriceAnomalyORM for DB writes)
  - future signal adapter (reads price_bars via repository)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Append-only ORM pattern: no TimestampMixin on PriceBarORM — only created_at, no updated_at"
    - "price_to_cents uses round() not int() — critical for floating-point safety"
    - "Literal type for anomaly_type — closed enum prevents typos in downstream consumers"
    - "CoverageReport.from_counts() classmethod pattern for computed Pydantic models"
    - "Migration chaining: revision='002', down_revision='001'"

key-files:
  created:
    - backtest/src/fund_backtest/db/migrations/versions/002_price_bars_schema.py
    - backtest/src/fund_backtest/price/__init__.py
    - backtest/src/fund_backtest/price/types.py
    - backtest/tests/unit/test_price_types.py
  modified:
    - backtest/src/fund_backtest/db/models.py
    - backtest/src/fund_backtest/config.py

key-decisions:
  - "PriceBarORM is append-only: no TimestampMixin (no updated_at); created_at added directly as mapped_column"
  - "price_to_cents uses round(), not int(), to prevent floating-point truncation (e.g. 10.009*100=1000.9 -> 1001)"
  - "PriceAnomalyRecord anomaly_type is Literal['return_spike_plus','return_spike_minus'] — closed set prevents drift"
  - "Migration 002 partial index ix_price_anomalies_reviewed uses postgresql_where='is_reviewed = false' for query performance"
  - "CoverageReport.from_counts() takes lists of tickers (not ints) to compute all fields in one call"

patterns-established:
  - "Append-only price table pattern: no updated_at, UUID PK, composite unique constraint on (ticker, bar_date)"
  - "Float-to-cents via round(): always use price_to_cents() helper, never raw int() cast"
  - "TDD tests in tests/unit/test_*.py covering edge cases before implementation"

requirements-completed:
  - DATA-01
  - DATA-02
  - DATA-04

# Metrics
duration: 22min
completed: 2026-03-29
---

# Phase 2 Plan 01: Price Data Schema and Types Summary

**Append-only price_bars/price_anomalies schema (migration 002) with Pydantic type contracts, round()-based float-to-cents conversion, and PriceSettings config — 18 unit tests all passing**

## Performance

- **Duration:** 22 min
- **Started:** 2026-03-29T08:11:18Z
- **Completed:** 2026-03-29T08:33:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- PriceBarORM and PriceAnomalyORM added to db/models.py following the existing append-only pattern (no updated_at on price_bars)
- Alembic migration 002 chained from 001 with 5 indexes (incl. partial index on is_reviewed=false for query efficiency)
- price/types.py exports PriceBar (with from_yfinance_row() factory), PriceAnomalyRecord (Literal type), DownloadSummary, CoverageReport (with from_counts() classmethod)
- price_to_cents() uses round() not int() — verified by unit test that 10.009 -> 1001, not 1000
- PriceSettings added to config.py with batch_size=80, lookback_years=5, coverage_alert_threshold=0.95

## Task Commits

Each task was committed atomically:

1. **Task 1: ORM models + Alembic migration 002** - `dbbc852` (feat)
2. **Task 2: price/types.py + PriceSettings + unit tests** - `a622c2b` (feat)

_Note: Both tasks used TDD — tests written first (RED), then implementation (GREEN)_

## Files Created/Modified

- `backtest/src/fund_backtest/db/models.py` - Added PriceBarORM and PriceAnomalyORM classes
- `backtest/src/fund_backtest/db/migrations/versions/002_price_bars_schema.py` - Alembic migration 002 for price_bars + price_anomalies
- `backtest/src/fund_backtest/price/__init__.py` - New price module entry point
- `backtest/src/fund_backtest/price/types.py` - PriceBar, PriceAnomalyRecord, DownloadSummary, CoverageReport, price_to_cents
- `backtest/src/fund_backtest/config.py` - Added PriceSettings class and load_price_settings() factory
- `backtest/tests/unit/test_price_types.py` - 18 unit tests covering all edge cases

## Decisions Made

- **PriceBarORM is append-only:** No TimestampMixin because append-only tables must not have updated_at (established in Phase 1 decisions). created_at added as a direct mapped_column with server_default=func.now().
- **price_to_cents uses round():** int() truncates — 10.009*100 = 1000.9, int() gives 1000, round() gives 1001. The unit test `test_price_to_cents_fractional_cents` verifies this.
- **Literal anomaly_type:** Closed Literal["return_spike_plus","return_spike_minus"] prevents string drift across the codebase compared to a plain str field.
- **Partial index for is_reviewed:** postgresql_where="is_reviewed = false" makes anomaly review queries fast without indexing already-reviewed rows.
- **CoverageReport.from_counts takes list[str]:** Accepts the same ticker lists the downloader already produces — no extra counting step needed.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `uv run` failed to pick up the backtest .venv due to the AI Washing Detector's `.venv` being active in VIRTUAL_ENV. Resolved by invoking `.venv/bin/pytest` and `.venv/bin/python` directly. This is an environment issue, not a code issue. Existing tests (24 unit tests) continued to pass throughout.

## User Setup Required

None - no external service configuration required. This plan creates schema definitions and types only; migration must be applied separately when a PostgreSQL database is available.

## Next Phase Readiness

- All type contracts are stable — downstream plans (02-02 downloader, 02-03 validator, 02-04 repository) can import from fund_backtest.price.types and fund_backtest.config without changes
- Migration 002 is ready to apply: `alembic upgrade 002`
- Total unit test count: 42 (all passing)

---
*Phase: 02-price-data-pipeline*
*Completed: 2026-03-29*

## Self-Check: PASSED

- FOUND: backtest/src/fund_backtest/db/models.py
- FOUND: backtest/src/fund_backtest/db/migrations/versions/002_price_bars_schema.py
- FOUND: backtest/src/fund_backtest/price/__init__.py
- FOUND: backtest/src/fund_backtest/price/types.py
- FOUND: backtest/src/fund_backtest/config.py
- FOUND: backtest/tests/unit/test_price_types.py
- FOUND: .planning/phases/02-price-data-pipeline/02-01-SUMMARY.md
- FOUND: commit dbbc852 (feat: ORM models + migration)
- FOUND: commit a622c2b (feat: price/types + PriceSettings + tests)
- All 42 unit tests passing
