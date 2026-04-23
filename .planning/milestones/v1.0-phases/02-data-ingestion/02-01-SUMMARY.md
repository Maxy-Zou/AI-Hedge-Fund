---
phase: 02-data-ingestion
plan: 01
subsystem: data-ingestion-foundation
tags: [temporal, models, summary-formatters, alembic, config]
dependency_graph:
  requires: [01-foundation]
  provides: [data-temporal, data-models, data-summaries, alembic-setup]
  affects: [02-02, 02-03, 02-04]
tech_stack:
  added: [edgartools, yfinance, tiingo, fredapi, finnhub-python, pytest-httpx, ruff]
  patterns: [enforce_as_of_date-decorator, DualTimestampMixin, cents-as-bigint, NL-summary-formatters]
key_files:
  created:
    - src/ai_hedge_fund/data/__init__.py
    - src/ai_hedge_fund/data/temporal.py
    - src/ai_hedge_fund/data/summary.py
    - src/ai_hedge_fund/db/models.py
    - alembic.ini
    - alembic/env.py
    - alembic/versions/001_create_data_ingestion_tables.py
    - tests/unit/test_temporal.py
    - tests/unit/test_summary.py
    - tests/unit/test_data_models.py
  modified:
    - pyproject.toml
    - src/ai_hedge_fund/config.py
    - tests/conftest.py
decisions:
  - Hand-wrote Alembic migration instead of autogenerate (no live PostgreSQL in CI)
  - Used SQLite in-memory for model testing (fast, no external dependencies)
metrics:
  duration: 7m
  completed: "2026-04-12T07:52:00Z"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 50
  files_created: 10
  files_modified: 3
---

# Phase 02 Plan 01: Data Ingestion Foundation Summary

Temporal enforcement decorator, 6 SQLAlchemy models with DualTimestampMixin, 5 NL summary formatters for LLM consumption, Alembic migration setup, and data source dependency installation.

## Completed Tasks

| # | Name | Commit | Tests |
|---|------|--------|-------|
| 1 | Dependencies, config extension, temporal enforcement, NL summary formatters | efbe5dc | 25 |
| 2 | SQLAlchemy data models, Alembic migration, test fixtures | a0e79b3 | 25 |

## Key Artifacts

### Temporal Enforcement (`src/ai_hedge_fund/data/temporal.py`)
- `normalize_as_of_date(as_of_date)` -- validates not None, not future, converts datetime to date
- `@enforce_as_of_date` -- decorator for all data tool functions; intercepts `as_of_date` kwarg and normalizes before calling wrapped function; works with sync and async

### NL Summary Formatters (`src/ai_hedge_fund/data/summary.py`)
- `format_financial_summary()` -- revenue, net income, margins, EPS with YoY changes
- `format_price_summary()` -- current price, period return, volatility, 52w range
- `format_insider_summary()` -- cluster buy narratives or "No significant insider activity"
- `format_news_summary()` -- daily sentiment digest or "No recent news"
- `format_macro_summary()` -- fed funds rate, CPI, GDP, yield curve description
- `_format_dollars(cents)` -- helper converting cents to "$X.XB", "$X.XM", "$X,XXX"

### SQLAlchemy Models (`src/ai_hedge_fund/db/models.py`)
- `SecFiling` -- SEC 10-K/10-Q/8-K filings with sections_json and summary_text
- `XbrlFact` -- XBRL financial concepts with value_cents and fiscal context
- `DailyPrice` -- OHLCV prices in cents with source tracking (yfinance/tiingo)
- `InsiderTrade` -- Form 4 transactions with dedup constraint
- `NewsArticle` -- Finnhub articles with sentiment scores
- `MacroIndicator` -- FRED time series observations

All models inherit `Base` + `DualTimestampMixin` (as_of_date/observed_date).

### Config Extension (`src/ai_hedge_fund/config.py`)
- Added `tiingo_api_key: str = ""` to AppSettings

### Alembic Setup
- `alembic.ini` -- URL loaded from env (never hardcoded)
- `alembic/env.py` -- imports Base + models, loads URL from AppSettings
- `alembic/versions/001_create_data_ingestion_tables.py` -- creates all 6 tables

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Hand-wrote Alembic migration instead of autogenerate**
- **Found during:** Task 2
- **Issue:** `alembic revision --autogenerate` requires a live PostgreSQL connection; no database available in worktree CI environment
- **Fix:** Hand-wrote the migration file with all 6 tables, columns, indexes, and constraints matching the SQLAlchemy models exactly
- **Files created:** `alembic/versions/001_create_data_ingestion_tables.py`

**2. [Rule 1 - Bug] Fixed test data cents-to-dollars conversion**
- **Found during:** Task 1 TDD GREEN
- **Issue:** Test constants used `39_430_000_000_00` (3.9T cents = $39.4B) but comments said $394.3B
- **Fix:** Corrected to `394_300_000_000_00` (39.43T cents = $394.3B)
- **Files modified:** `tests/unit/test_summary.py`

## Verification Results

- 50 unit tests passing (13 temporal + 12 summary + 25 models)
- ruff check clean on all new/modified files
- `alembic heads` shows single migration head (001)
- All acceptance criteria from plan verified
