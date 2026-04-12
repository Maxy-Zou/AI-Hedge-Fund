---
phase: 01-foundation
plan: 01
subsystem: project-scaffold
tags: [scaffold, config, pydantic-settings, structlog, typer, tdd]
dependency_graph:
  requires: []
  provides:
    - kalshi_tracker Python package (installable)
    - AppSettings + KalshiSettings Pydantic config models
    - configure_logging() structlog setup
    - Typer CLI skeleton (kalshi-tracker start)
    - TDD test stubs for Plans 02 and 03
  affects:
    - All subsequent plans (02, 03) depend on this scaffold
tech_stack:
  added:
    - kalshi-python>=2.1.4 (Kalshi REST API SDK with RSA auth)
    - sqlalchemy>=2.0.48 (ORM, imported for future plans)
    - psycopg[binary]>=3.2 (PostgreSQL driver)
    - alembic>=1.18.4 (DB migrations)
    - pydantic>=2.12.5 + pydantic-settings>=2.13.1 (settings, validation)
    - structlog>=25.5.0 (structured logging)
    - tenacity>=9.1.4 (retry logic)
    - typer>=0.24.1 + rich>=14.0 (CLI framework)
    - pytest>=9.0.2 + pytest-cov>=7.0 + ruff>=0.15 (dev tooling)
  patterns:
    - Dual Pydantic settings pattern (AppSettings + KalshiSettings with distinct env prefixes)
    - structlog ConsoleRenderer (DEBUG) / JSONRenderer (INFO+) switching
    - TDD stub pattern with pytestmark = pytest.mark.skip for future-plan tests
key_files:
  created:
    - Kalshi Insider Tracker/pyproject.toml
    - Kalshi Insider Tracker/.env.example
    - Kalshi Insider Tracker/alembic.ini
    - Kalshi Insider Tracker/src/kalshi_tracker/__init__.py
    - Kalshi Insider Tracker/src/kalshi_tracker/__main__.py
    - Kalshi Insider Tracker/src/kalshi_tracker/cli.py
    - Kalshi Insider Tracker/src/kalshi_tracker/config.py
    - Kalshi Insider Tracker/src/kalshi_tracker/logging.py
    - Kalshi Insider Tracker/tests/__init__.py
    - Kalshi Insider Tracker/tests/conftest.py
    - Kalshi Insider Tracker/tests/unit/__init__.py
    - Kalshi Insider Tracker/tests/unit/test_config.py
    - Kalshi Insider Tracker/tests/unit/test_client.py
    - Kalshi Insider Tracker/tests/unit/test_models.py
    - Kalshi Insider Tracker/tests/integration/__init__.py
    - Kalshi Insider Tracker/tests/integration/test_migrations.py
  modified: []
decisions:
  - id: D-SCAFFOLD-01
    summary: KalshiSettings.api_base_url defaults to demo API, not production — safety constraint preventing accidental live trades during development
  - id: D-SCAFFOLD-02
    summary: rate_limit_rpm=60 declared as DATA-05 constant in KalshiSettings with validator rejecting 0 — cannot be accidentally disabled
  - id: D-SCAFFOLD-03
    summary: Separate AppSettings (KALSHI_TRACKER_ prefix) and KalshiSettings (KALSHI_ prefix) to allow different deployment configs for infra vs API credentials
metrics:
  duration_minutes: 3
  tasks_completed: 2
  files_created: 16
  completed_date: "2026-04-02T22:54:00Z"
---

# Phase 01 Plan 01: Project Scaffold and Configuration Summary

Bootstrap Kalshi Insider Tracker Python package with Pydantic settings, structlog, Typer CLI, and TDD test stubs — installable package with config validation and 6 passing config unit tests.

## What Was Built

### Task 1: Project Scaffold

Created the complete Python package scaffold for Kalshi Insider Tracker, copying patterns directly from the sibling Al Washing Detector project.

**Key implementation details:**
- `pyproject.toml` uses hatchling build backend, `src/` layout, `line-length = 100` ruff config
- `AppSettings` uses `KALSHI_TRACKER_` env prefix (database, logging config)
- `KalshiSettings` uses `KALSHI_` env prefix (API key, private key path, rate limit, base URL)
- `KalshiSettings.api_base_url` defaults to `https://demo-api.kalshi.co/trade-api/v2` — production URL must be explicitly set via env var (safety constraint)
- `KalshiSettings.rate_limit_rpm = 60` with validator rejecting `<= 0` values (DATA-05)
- `configure_logging()` switches between ConsoleRenderer (DEBUG) and JSONRenderer (INFO+)
- CLI: `typer.Typer` app with `start` command; `python -m kalshi_tracker --help` works

### Task 2: TDD Test Stubs

Created test infrastructure with 6 passing config tests and 9 skipped stubs for future plans.

**Test structure:**
- `tests/unit/test_config.py` — 6 tests GREEN (AppSettings, KalshiSettings validation)
- `tests/unit/test_client.py` — 4 stubs SKIPPED (DATA-01, DATA-03, DATA-05; activate in Plan 03)
- `tests/unit/test_models.py` — 4 stubs SKIPPED (LOG-03; activate in Plan 02)
- `tests/integration/test_migrations.py` — 1 stub SKIPPED (LOG-03; activate in Plan 02)
- `tests/conftest.py` — `kalshi_env` and `app_env` fixtures for clean env isolation

## Verification Results

```
pytest tests/unit/test_config.py  →  6 passed
pytest tests/unit/               →  6 passed, 8 skipped
pytest tests/integration/        →  1 skipped
ruff check src/ tests/           →  All checks passed
python -m kalshi_tracker --help  →  CLI help displayed
```

## Commits

| Hash | Message |
|------|---------|
| `040f64c` | feat(01-foundation-01): scaffold Kalshi Insider Tracker — pyproject.toml, config, logging, CLI |
| `9af336f` | test(01-foundation-01): add TDD test stubs for Phase 1 requirements |

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

All created files exist and commits are present on `shared/backtest-framework` branch.
