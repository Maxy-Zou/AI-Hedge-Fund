---
phase: 06-risk-management
plan: 02
subsystem: risk-management
tags: [risk, portfolio, schema, persistence, append-only, temporal-correctness]
provides:
  - ai_hedge_fund.db.models.PortfolioPosition
  - ai_hedge_fund.risk.portfolio.PortfolioSnapshot
  - ai_hedge_fund.risk.portfolio.PortfolioSnapshotPosition
  - ai_hedge_fund.risk.portfolio.load_portfolio
  - ai_hedge_fund.risk.portfolio.seed_portfolio_from_csv
  - alembic/versions/002_create_portfolio_positions.py
requires:
  - ai_hedge_fund.db.base.Base
  - ai_hedge_fund.db.base.DualTimestampMixin
affects:
  - src/ai_hedge_fund/db/models.py (appended PortfolioPosition)
  - src/ai_hedge_fund/risk/__init__.py (re-exports the four new symbols alongside RiskPolicy)
tech-stack:
  added: []
  patterns:
    - "Append-only SQLAlchemy model on DualTimestampMixin (mirrors DailyPrice)"
    - "UniqueConstraint(ticker, as_of_date) enforces per-business-date snapshot contract"
    - "Frozen Pydantic models via ConfigDict(frozen=True) for immutable portfolio snapshots"
    - "Temporal-correctness ORM filter: PortfolioPosition.as_of_date <= target"
    - "Latest-per-ticker collapse via dict-of-first-seen over desc-ordered rows"
key-files:
  created:
    - alembic/versions/002_create_portfolio_positions.py
    - src/ai_hedge_fund/risk/portfolio.py
    - tests/risk/fixtures/portfolio_sample.csv
    - tests/risk/test_portfolio_loader.py
    - tests/risk/test_portfolio_model.py
  modified:
    - src/ai_hedge_fund/db/models.py (appended PortfolioPosition class)
    - src/ai_hedge_fund/risk/__init__.py (added 4 new re-exports)
decisions:
  - "PortfolioPosition stores as_of_date as timezone-aware DateTime (mirrors DualTimestampMixin contract) rather than the plain Date used by DailyPrice.trade_date; test inputs use datetime(Y,M,D,tzinfo=UTC)."
  - "CSV fixture uses 5 positions across 4 sectors (Technology x2, Healthcare, Financials, Consumer Staples) -- exceeds the 3-sector minimum and gives sector-concentration tests realistic variation."
  - "test_portfolio_loader.py declares the fixture path inline via _SAMPLE_CSV rather than depending on the sample_portfolio_csv_path conftest fixture -- avoids cross-plan coupling with 06-01's conftest while still reading the same committed CSV file."
  - "_normalise_as_of accepts str | date | datetime and always returns a UTC datetime for the ORM filter; naive datetimes are treated as UTC."
metrics:
  duration_seconds: 453
  completed_date: 2026-04-22
  tasks_completed: 2
  tests_added: 12
  tests_passing: 12
  loc_added: 543
  commits: 2
requirements-completed:
  - RISK-03 (partial — portfolio-state persistence and temporal-correct loader; actual risk checks land in 06-03, node orchestration in 06-05)
---

# Phase 6 Plan 02: Portfolio Data Layer Summary

**One-liner:** Append-only ``portfolio_positions`` table + frozen ``PortfolioSnapshot`` with temporal-correct ``load_portfolio(db_session, as_of_date)`` and a CSV seeder for paper-portfolio fixtures.

## Overview

Plan 06-02 lays the persistence + loading foundation for the Phase 6 risk manager. The ``PortfolioPosition`` SQLAlchemy model is an append-only row on ``DualTimestampMixin`` with a ``UniqueConstraint(ticker, as_of_date)`` that makes "new snapshot = new row" a schema-level contract (no UPDATE path). The companion ``PortfolioSnapshot`` Pydantic model is frozen and carries the helper math (``sector_weight_pct``, ``position_value_pct``, ``weights``, ``tickers``) that plans 06-03 and 06-05 will depend on. ``load_portfolio`` implements the Pitfall 2 temporal filter (``as_of_date <= target``) and collapses duplicate-ticker history by taking the latest row per ticker — the "current state" semantics the risk checks expect. ``seed_portfolio_from_csv`` reads the 5-position fixture CSV (4 sectors) and inserts one row per position for a given ``as_of_date``, making integration tests in 06-06 trivial to set up.

## Task Breakdown

### Task 1: PortfolioPosition SQLAlchemy model + Alembic 002 + CSV fixture
- Commit: **5500dfb**
- Files:
  - `src/ai_hedge_fund/db/models.py` (+37 lines — appended PortfolioPosition class)
  - `alembic/versions/002_create_portfolio_positions.py` (new, 56 lines)
  - `tests/risk/fixtures/portfolio_sample.csv` (new, 6 lines / 5 data rows)
  - `tests/risk/test_portfolio_model.py` (new, 127 lines, 4 tests)
- 4 tests passing (insert success, duplicate rejection, append-only across dates, schema introspection).

### Task 2: PortfolioSnapshot + load_portfolio + seed_portfolio_from_csv
- Commit: **071e5f9**
- Files:
  - `src/ai_hedge_fund/risk/portfolio.py` (new, 177 lines)
  - `src/ai_hedge_fund/risk/__init__.py` (+8 lines — added 4 re-exports)
  - `tests/risk/test_portfolio_loader.py` (new, 177 lines, 8 tests)
- 8 tests passing (schema validation, empty DB, CSV seeding, temporal filter, latest-per-ticker collapse, sector-weight math, frozen-model enforcement, round-trip count).

## Test Results

```
uv run pytest tests/risk/test_portfolio_model.py tests/risk/test_portfolio_loader.py -q
............                                                                  [100%]
12 passed in 0.05s
```

Broader suite (tests/risk — 06-01 + 06-02): **30 passed**.

Ruff clean on all modified files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 – Bug] Test as_of_date string caused SQLite DateTime type error**
- **Found during:** Task 1 initial test run (RED → GREEN transition)
- **Issue:** The plan's example behavior used ``as_of_date="2026-03-01T00:00:00+00:00"`` (ISO string). SQLite's ``DateTime(timezone=True)`` binding rejects raw strings with ``TypeError("SQLite DateTime type only accepts Python datetime and date objects as input")``. Existing codebase uses ``datetime(..., tzinfo=UTC)`` (see ``tests/unit/test_price_tools.py::test_...`` seeding ``DailyPrice.as_of_date``).
- **Fix:** Updated all four model tests and the loader tests to pass ``datetime(Y, M, D, tzinfo=UTC)`` instances. Model tests still enforce the same append-only + duplicate-rejection contract; behaviour is identical.
- **Files modified:** tests/risk/test_portfolio_model.py, tests/risk/test_portfolio_loader.py
- **Commit:** 5500dfb (Task 1) and 071e5f9 (Task 2)

### Architectural deviations
None. The model class, column list, Alembic revision id, CSV schema, and module layout all follow the plan exactly.

### Scope-boundary notes
- Two untracked 06-01 files (``tests/risk/conftest.py`` and ``tests/risk/test_policy_schema.py``) appeared as modified in my working tree during execution because 06-01 committed subsequent changes in parallel. These were **not** staged into any 06-02 commit; they remain the property of 06-01.

## Threat Mitigations Exercised

| Threat ID | Mitigation | Verification |
|-----------|-----------|--------------|
| T-06-03 (SQL injection via portfolio loader) | SQLAlchemy ORM exclusive; no raw SQL | `grep -c "execute\|text(" src/ai_hedge_fund/risk/portfolio.py` == 0 |
| T-06-X1 (Append-only violation) | UniqueConstraint(ticker, as_of_date) + IntegrityError test | test_duplicate_ticker_as_of_date_raises_integrity_error |
| T-06-06 (Portfolio staleness) | Documented in module docstring; load_portfolio is a per-call query (callers invoke inside the node, not at builder scope) | Module docstring Pitfall 2 reference |

## Self-Check: PASSED

File existence:
- FOUND: src/ai_hedge_fund/db/models.py (PortfolioPosition class)
- FOUND: src/ai_hedge_fund/risk/portfolio.py
- FOUND: src/ai_hedge_fund/risk/__init__.py
- FOUND: alembic/versions/002_create_portfolio_positions.py
- FOUND: tests/risk/fixtures/portfolio_sample.csv (5 rows, 4 unique sectors)
- FOUND: tests/risk/test_portfolio_model.py
- FOUND: tests/risk/test_portfolio_loader.py

Commit verification:
- FOUND: 5500dfb feat(06-02): add PortfolioPosition model + Alembic 002 + CSV fixture
- FOUND: 071e5f9 feat(06-02): add PortfolioSnapshot + load_portfolio + seed_portfolio_from_csv

Acceptance criteria:
- PortfolioPosition class present, __tablename__ == "portfolio_positions"
- Alembic revision = "002", down_revision = "001"
- CSV has 5 data rows across 4 sectors (≥3 required)
- ``uv run pytest tests/risk/test_portfolio_model.py tests/risk/test_portfolio_loader.py -q`` → 12 passed
- ``python -c "from ai_hedge_fund.risk import PortfolioSnapshot, load_portfolio"`` → OK
- Ruff clean on all modified files
