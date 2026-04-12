---
phase: 01-data-foundation
plan: "02"
subsystem: data-contracts
tags: [duckdb, pydantic, config, schema, repository, types]
dependency_graph:
  requires: []
  provides:
    - kalshi_backtest.config.KalshiBacktestSettings
    - kalshi_backtest.db.schema.SCHEMA_DDL
    - kalshi_backtest.db.schema.apply_schema
    - kalshi_backtest.db.schema.get_connection
    - kalshi_backtest.db.schema.get_or_create_db
    - kalshi_backtest.db.repository.MarketRepository
    - kalshi_backtest.ingestion.types.MarketRecord
    - kalshi_backtest.ingestion.types.CandlestickRecord
  affects:
    - All Wave 2+ plans that depend on the data layer contracts
tech_stack:
  added:
    - duckdb 1.5.x — local analytical store with naive-UTC TIMESTAMP schema
    - pydantic-settings 2.x — KalshiBacktestSettings with KALSHI_BACKTEST_ env prefix
  patterns:
    - Frozen Pydantic models for immutable data contracts
    - ON CONFLICT DO NOTHING for idempotent candle inserts
    - ON CONFLICT DO UPDATE for market upserts (status/result change on settlement)
    - Parameterized queries everywhere in repository (no f-string SQL for values)
key_files:
  created:
    - kalshi-backtest/pyproject.toml
    - kalshi-backtest/src/kalshi_backtest/__init__.py
    - kalshi-backtest/src/kalshi_backtest/config.py
    - kalshi-backtest/src/kalshi_backtest/ingestion/__init__.py
    - kalshi-backtest/src/kalshi_backtest/ingestion/types.py
    - kalshi-backtest/src/kalshi_backtest/db/__init__.py
    - kalshi-backtest/src/kalshi_backtest/db/schema.py
    - kalshi-backtest/src/kalshi_backtest/db/repository.py
    - kalshi-backtest/tests/__init__.py
    - kalshi-backtest/tests/conftest.py
    - kalshi-backtest/tests/test_config_and_types.py
    - kalshi-backtest/tests/test_schema.py
  modified: []
decisions:
  - "Store datetime as naive UTC (TIMESTAMP not TIMESTAMPTZ) — DuckDB 1.5.x TIMESTAMPTZ requires pytz and returns offset-aware datetimes; naive UTC is simpler and sufficient when application layer enforces UTC discipline"
  - "CandlestickRecord.ts accepts int (Unix epoch) or datetime — Kalshi API returns Unix epoch integers for candlestick timestamps; validator converts to naive UTC datetime before storage"
  - "MarketRepository uses executemany for batch candle inserts — DuckDB executemany is more efficient than looped execute for bulk insert"
  - "private_key_path validates .pem/.key extension only (not existence) — config is loaded before the key is needed; existence check deferred to API client initialization"
metrics:
  duration_seconds: 251
  completed_date: "2026-04-04"
  tasks_completed: 2
  files_created: 12
  files_modified: 0
  tests_added: 31
---

# Phase 01 Plan 02: Config and Data Contracts Summary

**One-liner:** DuckDB schema with idempotent insert patterns, typed MarketRepository, and frozen Pydantic contracts (KalshiBacktestSettings, MarketRecord, CandlestickRecord) with naive-UTC datetime normalization.

## What Was Built

### Task 1: Config and Pydantic Types (commit ab45734)

- `config.py` — `KalshiBacktestSettings` with `KALSHI_BACKTEST_` env prefix, `.pem`/`.key` extension validation, and `load_settings()` factory
- `ingestion/types.py` — `MarketRecord` and `CandlestickRecord` as frozen Pydantic models
  - `MarketRecord`: strips `tzinfo` from all datetime fields on construction; `result` defaults to `None` for unsettled markets
  - `CandlestickRecord`: accepts Unix epoch int or datetime for `ts` field; validates `close_price`/`open_price`/`high_price`/`low_price` in 0-100 range
- `pyproject.toml` — project definition with all Phase 1 dependencies declared
- 14 unit tests (all green)

### Task 2: DuckDB Schema and MarketRepository (commit 44e2935)

- `db/schema.py` — `SCHEMA_DDL` constant (markets + candles tables, 5 indexes), `get_connection()`, `apply_schema()`, `get_or_create_db()` factory
- `db/repository.py` — `MarketRepository` with typed methods:
  - `upsert_market()` — `ON CONFLICT DO UPDATE` for status/result fields
  - `insert_candles()` — `ON CONFLICT DO NOTHING` for idempotent append-only inserts
  - `get_last_candle_ts()` — returns Unix epoch of MAX(ts) or None
  - `count_candles()` — row count per ticker
  - `get_markets()` / `get_candles()` — filtered query methods with parameterized WHERE clauses
- `db/__init__.py` — barrel exports for all public symbols
- `tests/conftest.py` — shared `duckdb_con` fixture importing `SCHEMA_DDL` from `kalshi_backtest.db.schema` (not inline)
- 17 schema/repository tests including DST roundtrip test (all green)

## Verification Results

All plan success criteria met:

- `KalshiBacktestSettings` validates correctly; `.pem` extension enforced; all fields typed
- `SCHEMA_DDL` creates both tables and all 5 indexes without error on fresh DuckDB connection
- `MarketRepository.upsert_market()` updates status/result on conflict; inserts new markets
- `MarketRepository.insert_candles()` silently skips duplicate (ticker, ts) rows
- `CandlestickRecord(ts=unix_epoch)` converts to naive UTC datetime; price range validated 0-100
- `MarketRecord` strips tzinfo from all datetime fields on construction
- `uv run pytest tests/ -v` exits 0 with all 31 tests green

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Replaced deprecated `datetime.utcfromtimestamp()` with modern equivalent**
- **Found during:** Task 1 GREEN phase (deprecation warning in Python 3.13)
- **Issue:** `datetime.utcfromtimestamp()` is deprecated in Python 3.12+ and scheduled for removal; produced warnings during test run
- **Fix:** Replaced with `datetime.fromtimestamp(v, tz=timezone.utc).replace(tzinfo=None)` — same naive UTC result, no deprecation warning
- **Files modified:** `kalshi-backtest/src/kalshi_backtest/ingestion/types.py`
- **Commit:** ab45734 (included in Task 1 commit)

**2. [Rule 3 - Blocking] Created pyproject.toml and package scaffold**
- **Found during:** Task 1 — no project existed yet
- **Issue:** Both plan 01-01 and 01-02 run in Wave 1 (parallel). No Python project or package existed; without `pyproject.toml` and `__init__.py`, the package was not importable and tests could not run.
- **Fix:** Created minimal `pyproject.toml`, `src/kalshi_backtest/__init__.py` sufficient to make the package installable and tests runnable. This is additive — plan 01-01 will create the same or extended versions of these files; the merge will favor the more complete version.
- **Files modified:** `kalshi-backtest/pyproject.toml`, `kalshi-backtest/src/kalshi_backtest/__init__.py`
- **Commit:** ab45734

## Known Stubs

None — all contracts are fully implemented with real logic, no placeholder data.

## Self-Check: PASSED

Files created verified present:
- kalshi-backtest/src/kalshi_backtest/config.py — FOUND
- kalshi-backtest/src/kalshi_backtest/ingestion/types.py — FOUND
- kalshi-backtest/src/kalshi_backtest/db/schema.py — FOUND
- kalshi-backtest/src/kalshi_backtest/db/repository.py — FOUND
- kalshi-backtest/src/kalshi_backtest/db/__init__.py — FOUND

Commits verified:
- ab45734 — feat(01-02): config and Pydantic types — FOUND
- 44e2935 — feat(01-02): DuckDB schema and MarketRepository — FOUND

Test suite: 31 passed, 0 failed, 0 skipped
