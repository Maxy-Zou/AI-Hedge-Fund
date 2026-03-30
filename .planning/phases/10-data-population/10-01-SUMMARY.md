---
phase: 10-data-population
plan: 01
subsystem: infra, cli, config
tags: [testcontainers, yfinance, rate-limiting, cli, config]

# Dependency graph
requires: ["09-02"]
provides:
  - "testcontainers.postgres importable in backtest venv"
  - "backtest/config/price.yaml with batch_sleep_secs=3.0"
  - "CLI download and update commands auto-load config/price.yaml"
affects: [phase-10-wave2, phase-10-wave3, all unit tests in backtest/]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "uv pip install --force-reinstall resolves testcontainers ' 2' suffix dirs caused by Python 3.12 .pth-skipping bug"
    - "Path(__file__).parent.parent.parent / 'config' / 'price.yaml' — three .parent calls from cli.py to backtest/config/"
    - "load_price_settings(config_path=_price_yaml if _price_yaml.exists() else None) — fallback to defaults when file absent"

key-files:
  created:
    - backtest/config/price.yaml
  modified:
    - backtest/src/fund_backtest/cli.py

key-decisions:
  - "uv pip install --force-reinstall testcontainers[postgres] resolves the ' 2'-suffix directory issue cleanly without needing a symlink"
  - "price.yaml placed in backtest/config/ (same directory as universe.yaml) for consistency"
  - "update() command also patched for consistency even though batch_sleep_secs is less critical for daily incremental updates"

requirements-completed: [POP-02]

# Metrics
duration: 3min
completed: 2026-03-30
---

# Phase 10 Plan 01: Prerequisites — testcontainers fix and price config Summary

**Force-reinstalled testcontainers to fix Python 3.12 .pth-skipping directory-naming bug, and created config/price.yaml with batch_sleep_secs=3.0 to prevent 429 rate-limit failures on the first bulk yfinance download**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-30T15:37:24Z
- **Completed:** 2026-03-30T15:40:02Z
- **Tasks:** 2
- **Files modified:** 2 (cli.py patched, price.yaml created)

## Accomplishments

- Fixed testcontainers.postgres import: `uv pip install --force-reinstall testcontainers[postgres]` resolved the Python 3.12 .pth-skipping bug that caused all subdirectories to install with " 2" suffix instead of clean names
- All 166 unit tests collect and pass without ModuleNotFoundError in conftest.py
- Created `backtest/config/price.yaml` with `batch_sleep_secs: 3.0` — prevents yfinance 429 rate-limit errors during first bulk download of 200-400 tickers
- Patched `download()` command in cli.py: auto-loads `config/price.yaml` via `load_price_settings(config_path=...)` using `Path(__file__).parent.parent.parent / "config" / "price.yaml"` (3 .parent calls from cli.py to backtest/config/)
- Patched `update()` command with identical pattern for consistency
- Both commands fall back to `PriceSettings` defaults (batch_sleep_secs=1.0) when config/price.yaml is absent

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix testcontainers.postgres broken install | edce180 | venv only (no tracked source files) |
| 2 | Patch CLI download + create config/price.yaml | 46d00c0 | backtest/src/fund_backtest/cli.py, backtest/config/price.yaml |

## Files Created/Modified

- `backtest/config/price.yaml` — created with `batch_sleep_secs: 3.0`, `batch_size: 80`, `lookback_years: 5`, `coverage_alert_threshold: 0.95`
- `backtest/src/fund_backtest/cli.py` — download() and update() now call `load_price_settings(config_path=_price_yaml if _price_yaml.exists() else None)`

## Decisions Made

- `uv pip install --force-reinstall testcontainers[postgres]` is the clean fix for the " 2" suffix directory naming issue caused by Python 3.12 skipping .pth files when project paths contain spaces. Prior fix in Phase 9 was PYTHONPATH for alembic; this is a parallel manifestation of the same root cause but with a cleaner resolution available via reinstall.
- Three `.parent` calls from `cli.py` resolves to `backtest/` root: `Path(__file__).parent` = `backtest/src/fund_backtest/`, `.parent` = `backtest/src/`, `.parent` = `backtest/`
- `update()` command also patched for consistency — daily incremental updates benefit from configurable batch_sleep_secs too

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written. The plan offered symlink as a fallback in Step 3 if reinstall failed; reinstall succeeded on first attempt.

## Known Stubs

None — this plan is infrastructure and config; no UI or data rendering involved.

## Self-Check: PASSED

- `backtest/config/price.yaml` exists and contains `batch_sleep_secs: 3.0` ✓
- `backtest/src/fund_backtest/cli.py` contains 4 references to `price.yaml` (2 per command) ✓
- Commits `edce180` and `46d00c0` exist in git log ✓
- `from testcontainers.postgres import PostgresContainer` imports without error ✓
- 166 unit tests collected and pass ✓

---
*Phase: 10-data-population*
*Completed: 2026-03-30*
