# Phase 10: Data Population - Research

**Researched:** 2026-03-30
**Domain:** CLI operations, database population, yfinance bulk download, ticker overlap verification
**Confidence:** HIGH

## Summary

Phase 10 is an operational data-loading phase with no new code to write. All required functionality already exists in compiled, tested CLI commands. The task is to execute them in the correct order with the right environment variables, handle expected rate-limit failures gracefully, and verify the resulting database state.

The fund-backtest CLI is functional with the PYTHONPATH workaround established in Phase 9. `fund-backtest universe refresh` will pull ~400 S&P 400 tickers from Wikipedia, filter to the $2B-$10B mid-cap range, and upsert into `universe_tickers`. `fund-backtest data download` will then pull 5 years of daily OHLCV from yfinance in 80-ticker batches. Both commands are idempotent (ON CONFLICT DO NOTHING). The ticker overlap verification requires a simple SQL JOIN between `universe_tickers` and `companies` — no new application code needed.

One blocker identified: `testcontainers[postgres]` is broken in the backtest venv due to the same path-with-spaces Python 3.12 bug that affected alembic in Phase 9. The testcontainers package installed files with " 2" suffix duplicates, making `from testcontainers.postgres import PostgresContainer` fail. This means integration tests cannot run until the package is reinstalled cleanly. Unit tests are unaffected.

**Primary recommendation:** Execute the three commands in sequence — `universe refresh`, `data download` (with batch_sleep_secs=3.0 override), then verify with `data coverage` and SQL overlap query. Fix testcontainers as Wave 0 so tests can run.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
(None — all choices are at Claude's discretion for this operational phase.)

### Claude's Discretion
All implementation choices are at Claude's discretion — operational data loading phase.

Key constraints from research:
- `fund-backtest universe refresh` populates universe_tickers from S&P 400 (Wikipedia source)
- `fund-backtest data download` pulls yfinance OHLCV data — chunking already implemented
- `ai-washer universe scan` populates companies from SEC EDGAR EFTS
- Ticker overlap must be verified between ai_washer companies and fund_backtest universe
- `SignalAdapter.min_coverage=5` threshold must be met
- yfinance rate limiting: use `batch_sleep_secs=3.0` for first bulk download
- Python path workaround needed due to spaces in project path (see 09-02-SUMMARY.md)

### Deferred Ideas (OUT OF SCOPE)
- Running ai-washer universe scan is Phase 11, not Phase 10
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| POP-01 | Running `fund-backtest universe refresh` populates the universe_tickers table with real mid-cap tickers | CLI command verified functional via dry-run; UniverseBuilder.refresh() reads Wikipedia S&P 400, filters $2B-$10B market cap, upserts to universe_tickers |
| POP-02 | Running `fund-backtest data download` populates price_bars with 5 years of real OHLCV data for all universe tickers | PriceBuilder.download() confirmed: fetches active tickers, calls download_in_chunks() with batch_size=80, inserts via ON CONFLICT DO NOTHING; requires universe populated first |
| POP-03 | Running `fund-backtest data coverage` confirms ≥95% ticker coverage after download | CLI command confirmed: queries price_bars via repo.get_coverage_tickers(), checks min/max date, counts unreviewed anomalies. PriceSettings.coverage_alert_threshold=0.95 already configured |
| POP-04 | Ticker overlap between ai_washer companies and fund_backtest universe is verified and sufficient for backtesting | Verified via SQL JOIN on universe_tickers.ticker = companies.ticker; min 5 overlapping tickers required for SignalAdapter.min_coverage=5 |
</phase_requirements>

## Standard Stack

### Core — Already Installed
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| yfinance | (in backtest venv) | Daily OHLCV download from Yahoo Finance | Only free daily bar source; already integrated in downloader.py |
| SQLAlchemy 2.0 | 2.0.48+ | ORM + session for DB writes | Existing project standard |
| tenacity | 9.1.4+ | Retry with exponential backoff on 429 errors | Already wrapping _download_batch() |
| structlog | 25.5.0+ | Structured logging | Already wired in all builders |
| PostgreSQL 16 | running via Docker | Shared data store | ai_hedge_fund_postgres container already running |

### No New Dependencies Required
Phase 10 is purely operational — no new libraries needed.

## Architecture Patterns

### Command Execution Order (CRITICAL — sequential dependency)
```
1. fund-backtest universe refresh     # Populates universe_tickers first
2. fund-backtest data download        # Reads active tickers from universe_tickers
3. fund-backtest data coverage        # Verifies ≥95% coverage
4. SQL overlap query                  # Verifies companies vs universe_tickers JOIN
```

`data download` depends on `universe refresh` completing first. If universe is empty, `download` logs `download_skipped_empty_universe` and returns a zero-count DownloadSummary.

### Canonical CLI Command Pattern (Python path workaround)

```bash
# fund-backtest commands (from backtest/ directory)
cd "/Users/maxzou/Documents/projects/AI Hedgefund/backtest"
FUND_BACKTEST_DATABASE_URL="postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund" \
  PYTHONPATH="$(pwd)/src" \
  .venv/bin/fund-backtest universe refresh

# Alternative: pass DATABASE_URL from .env manually (no xargs — .env has spaces in values)
cd "/Users/maxzou/Documents/projects/AI Hedgefund/backtest"
FUND_BACKTEST_DATABASE_URL="postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund" \
  PYTHONPATH="$(pwd)/src" \
  .venv/bin/fund-backtest <command>
```

**CRITICAL: Do NOT use `uv run fund-backtest`** — Python 3.12 skips .pth files when the venv path contains spaces, causing `ModuleNotFoundError: No module named 'fund_backtest'`. Use `.venv/bin/fund-backtest` with explicit `PYTHONPATH` instead.

**CRITICAL: Do NOT use `export $(grep -v '^#' .env | xargs)`** — `.env` contains `AI_WASHER_EDGAR_IDENTITY=YourCompany yourname@example.com` with a space in the value, which breaks xargs. Set env vars directly on the command line.

### Overriding batch_sleep_secs for First Bulk Download

The default `PriceSettings.batch_sleep_secs=1.0` is insufficient for a 400-ticker first bulk download. yfinance 429 rate-limit errors are likely. The CONTEXT.md specifies using `3.0` for the first run.

`PriceSettings` is a Pydantic BaseModel loaded from YAML or defaults. The config is loaded at runtime by `load_price_settings()`. To override:

**Option A — Environment variable (not supported by PriceSettings BaseModel, only AppSettings uses BaseSettings)**

`PriceSettings` is a plain `pydantic.BaseModel`, not `pydantic_settings.BaseSettings`. It cannot read environment variables. The only injection point is a `config_path: Path` argument to `load_price_settings()`.

**Option B — YAML config file (recommended)**

```bash
# Create backtest/config/price.yaml
mkdir -p "/Users/maxzou/Documents/projects/AI Hedgefund/backtest/config"
cat > "/Users/maxzou/Documents/projects/AI Hedgefund/backtest/config/price.yaml" << 'EOF'
price:
  batch_sleep_secs: 3.0
  batch_size: 80
  lookback_years: 5
  coverage_alert_threshold: 0.95
EOF
```

However, the CLI `download` command calls `load_price_settings()` with no arguments (no config_path), so the YAML config is not read automatically by the current CLI code.

**Option C — Patch CLI to pass config_path (requires code change)**

The `data download` CLI command currently calls `load_price_settings()` with no config_path. A small code change would allow it to read from `backtest/config/price.yaml` if the file exists.

**Option D — Direct Python execution with settings override**

```python
# Run via python with overridden settings — bypasses the CLI
from fund_backtest.config import PriceSettings
settings = PriceSettings(batch_sleep_secs=3.0)
builder = PriceBuilder(session=session, settings=settings)
builder.download()
```

**Decision for planner:** Option C (patch `data download` CLI to auto-load config/price.yaml if it exists) or Option D (create a small wrapper script) are the cleanest. The planner should choose the approach.

### Ticker Overlap SQL Query

After universe_tickers is populated (Phase 10 POP-01) and companies is populated (Phase 11), the overlap query is:

```sql
-- Count overlap between fund_backtest universe and ai_washer companies
SELECT COUNT(*) AS overlap_count
FROM universe_tickers ut
JOIN companies c ON ut.ticker = c.ticker
WHERE ut.is_active = TRUE AND c.is_active = TRUE;

-- List overlapping tickers
SELECT ut.ticker, ut.name AS universe_name, c.name AS washer_name
FROM universe_tickers ut
JOIN companies c ON ut.ticker = c.ticker
WHERE ut.is_active = TRUE AND c.is_active = TRUE
ORDER BY ut.ticker;
```

Run via docker exec:
```bash
docker exec ai_hedge_fund_postgres psql -U hedge -d ai_hedge_fund \
  -c "SELECT COUNT(*) FROM universe_tickers ut JOIN companies c ON ut.ticker = c.ticker WHERE ut.is_active = TRUE AND c.is_active = TRUE;"
```

**Note for POP-04:** The `companies` table is populated in Phase 11 by `ai-washer universe scan`. In Phase 10, we can verify the universe_tickers count and confirm the overlap SQL works, but the actual overlap count will be 0 until Phase 11 completes. The POP-04 verification step should be documented as a post-Phase-11 check, or run after a dry-run of `ai-washer universe scan` populates some companies.

### Expected Universe Scale

S&P 400 has ~400 companies. After market cap filtering to $2B-$10B range, expect 150-300 active tickers. The exact count depends on current market caps (fetched live from yfinance during refresh). Download will be ~2-4 batches of 80 tickers = 3-4 yfinance API calls total.

At `batch_sleep_secs=3.0` and 5 batches: ~15 seconds of sleep plus download time. Total expected runtime: 5-15 minutes for full 5-year download.

### Idempotency (Safe to Re-Run)

Both commands are idempotent:

- `universe refresh`: Upserts via `_upsert_ticker()` — existing rows updated, no duplicates
- `data download`: Uses `pg_insert(...).on_conflict_do_nothing(index_elements=["ticker", "bar_date"])` — safe to re-run; duplicate bars silently skipped

If yfinance fails mid-download, re-running `data download` will retry only missing bars (the update() flow) or re-download and skip already-inserted bars (the download() flow with ON CONFLICT DO NOTHING).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Universe population | Custom Wikipedia scraper | `fund-backtest universe refresh` | Already implemented in UniverseBuilder |
| OHLCV download | Custom yfinance loop | `fund-backtest data download` | Chunking, retry, anomaly detection, DB insert all implemented |
| Coverage check | Custom SQL query | `fund-backtest data coverage` | CLI command already queries price_bars and formats output |
| Ticker overlap | Custom Python code | Docker exec psql with JOIN query | Simple SQL, no application code needed |

## Common Pitfalls

### Pitfall 1: Running data download before universe refresh
**What goes wrong:** `data download` queries `universe_tickers WHERE is_active=True` — if empty, it logs `download_skipped_empty_universe` and returns 0 bars inserted. No error raised, silently does nothing.
**Why it happens:** Commands are independent; no built-in dependency enforcement.
**How to avoid:** Always run `universe refresh` first. Verify with `universe status` before proceeding to `data download`.
**Warning signs:** `bars_inserted=0` in the download summary table.

### Pitfall 2: yfinance 429 Rate Limit Errors on Bulk Download
**What goes wrong:** First bulk download of 200-400 tickers triggers Yahoo Finance rate limiting. With `batch_sleep_secs=1.0` (default), the 5-attempt tenacity retry with 5-60s backoff may not be sufficient — a batch can fail entirely after all retries.
**Why it happens:** yfinance uses Yahoo Finance's unofficial API which rate-limits aggressive requests.
**How to avoid:** Use `batch_sleep_secs=3.0` or higher for the first bulk download. After the initial load, incremental `data update` with default 1.0s is fine.
**Warning signs:** `tickers_failed_in_batch` warnings in structlog output; `Tickers failed` > 0 in the Download Complete table.

### Pitfall 3: xargs fails on .env values with spaces
**What goes wrong:** `export $(grep -v '^#' .env | xargs)` splits `AI_WASHER_EDGAR_IDENTITY=YourCompany yourname@example.com` into two separate tokens, causing shell errors or incorrect variable assignment.
**Why it happens:** xargs splits on whitespace; EDGAR identity requires `Company Name email@domain.com` format with a space.
**How to avoid:** Always set DATABASE_URL and other env vars directly on the command line (prefixed before the command), never via xargs .env loading.
**Warning signs:** `BadParameter` or `ValidationError` from pydantic-settings; missing DATABASE_URL error.

### Pitfall 4: testcontainers.postgres import failure (integration tests)
**What goes wrong:** `from testcontainers.postgres import PostgresContainer` raises `ModuleNotFoundError`. This breaks `conftest.py` and prevents ALL tests (including unit tests) from running.
**Why it happens:** Same Python 3.12 .pth-skipping bug as alembic in Phase 9. The testcontainers package was installed when the venv path contained spaces, creating empty subdirectories named `postgres 2` instead of `postgres/`. The module content is missing entirely.
**How to avoid:** Reinstall testcontainers with `uv sync` in a clean environment, or install from a path without spaces. As a workaround, `uv sync` after Phase 9 ran and shows testcontainers 4.14.2 installed but the module is still broken — the venv needs to be rebuilt.
**Warning signs:** `ModuleNotFoundError: No module named 'testcontainers.postgres'` at conftest.py line 11.
**Fix:** Delete and recreate the venv: `cd backtest && uv sync` from a working directory without spaces would fix it, but the project path itself has a space. The most reliable fix is: symlink the project to a path without spaces for the reinstall, or directly create the missing `__init__.py` and copy from a clean install.

### Pitfall 5: data coverage shows correct ticker count but insufficient date range
**What goes wrong:** Coverage reports correct ticker count but date range starts too recently (e.g., only 2 years of data) if yfinance returns partial history for some tickers.
**Why it happens:** Some mid-cap tickers may have been listed less than 5 years ago (IPOs, spinoffs). yfinance returns whatever data exists; no error for shorter history.
**How to avoid:** Verify `Earliest bar date` in the coverage output is approximately 5 years ago. Tickers with shorter history are acceptable — the backtester handles sparse data.
**Warning signs:** `Earliest bar date` is after ~2020-12-30.

## Code Examples

### Running universe refresh with correct environment
```bash
# From repo root (not inside backtest/)
cd "/Users/maxzou/Documents/projects/AI Hedgefund/backtest"
FUND_BACKTEST_DATABASE_URL="postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund" \
  PYTHONPATH="$(pwd)/src" \
  .venv/bin/fund-backtest universe refresh
```

Expected output:
```
              Universe Refresh Complete
┌─────────────────┬────────────────────────┐
│ Metric          │ Value                  │
├─────────────────┼────────────────────────┤
│ Snapshot date   │ 2026-03-30             │
│ Active tickers  │ ~200-350               │
│ New tickers     │ ~200-350               │
│ Removed tickers │ 0                      │
└─────────────────┴────────────────────────┘
```

### Running data coverage after download
```bash
cd "/Users/maxzou/Documents/projects/AI Hedgefund/backtest"
FUND_BACKTEST_DATABASE_URL="postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund" \
  PYTHONPATH="$(pwd)/src" \
  .venv/bin/fund-backtest data coverage
```

Expected output after successful download:
```
         Price Data Coverage
┌──────────────────────┬────────────────┐
│ Metric               │ Value          │
├──────────────────────┼────────────────┤
│ Tickers with bars    │ ~200-350       │
│ Earliest bar date    │ ~2021-03-30    │
│ Latest bar date      │ 2026-03-30     │
│ Unreviewed anomalies │ 0-50 (normal)  │
└──────────────────────┴────────────────┘
```

### Ticker overlap verification SQL
```sql
-- Run via docker exec after both universe_refresh AND ai-washer universe scan complete
SELECT COUNT(*) AS overlap_count
FROM universe_tickers ut
JOIN companies c ON ut.ticker = c.ticker
WHERE ut.is_active = TRUE AND c.is_active = TRUE;
```

Minimum acceptable: 5 (SignalAdapter.min_coverage threshold). Expected: 50-150+ tickers.

### Checking PriceSettings defaults (no override needed unless rate-limiting occurs)
```python
# Source: backtest/src/fund_backtest/config.py
class PriceSettings(BaseModel):
    lookback_years: int = 5
    batch_size: int = 80
    batch_sleep_secs: float = 1.0       # Increase to 3.0 for first bulk download
    coverage_alert_threshold: float = 0.95
    return_anomaly_threshold: float = 0.50
    max_gap_days: int = 3
```

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | PostgreSQL container | Yes | 24.x (Docker Compose v2.40.3) | — |
| PostgreSQL 16 | All DB operations | Yes (container running) | 16-alpine | — |
| fund-backtest CLI | POP-01, POP-02, POP-03 | Yes (via .venv/bin/ + PYTHONPATH) | in backtest/.venv | Cannot use uv run |
| ai-washer CLI | POP-04 overlap check | Yes (in PATH at /Al Washing Detector/.venv/bin/) | in .venv | — |
| yfinance | POP-02 OHLCV download | Yes (in backtest venv) | (locked in uv.lock) | None for free daily data |
| testcontainers[postgres] | Integration tests | BROKEN | 4.14.2 (installed but unusable) | Fix required — see pitfall 4 |

**Missing dependencies with no fallback:**
- None blocking execution of Phase 10 commands

**Missing dependencies with fallback:**
- testcontainers.postgres import fails — blocks conftest.py and prevents test execution. Fix: reinstall the package with a clean uv sync (see Pitfall 4). Wave 0 must address this before any test runs.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (configured in backtest/pyproject.toml) |
| Config file | `backtest/pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `cd backtest && PYTHONPATH=src .venv/bin/pytest tests/unit/ -q -m "not integration"` |
| Full suite command | `cd backtest && PYTHONPATH=src .venv/bin/pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| POP-01 | universe_tickers populated with active tickers after refresh | CLI + DB verification | Manual — run `fund-backtest universe status` | N/A (CLI op) |
| POP-02 | price_bars populated with 5y OHLCV data | CLI + DB verification | Manual — run `fund-backtest data coverage` | N/A (CLI op) |
| POP-03 | Coverage ≥95% confirmed | CLI output verification | Manual — `fund-backtest data coverage` shows "Tickers with bars" ≥ 95% of universe | N/A (CLI op) |
| POP-04 | Ticker overlap ≥ 5 tickers | SQL query verification | `docker exec ai_hedge_fund_postgres psql -U hedge -d ai_hedge_fund -c "SELECT COUNT(*) FROM universe_tickers ut JOIN companies c ON ut.ticker = c.ticker WHERE ut.is_active = TRUE AND c.is_active = TRUE;"` | N/A (SQL op) |

Note: Phase 10 requirements are operational (run existing CLIs and verify DB state). They are not unit-testable — the verification is inspection of CLI output and SQL queries. No new test files needed for Phase 10 itself.

### Sampling Rate
- **Per task commit:** `cd backtest && PYTHONPATH=src .venv/bin/pytest tests/unit/ -q -m "not integration"` (unit tests only, skips broken integration tests)
- **Per wave merge:** Same command — integration tests blocked until testcontainers is fixed
- **Phase gate:** CLI output + SQL query confirm POP-01 through POP-04 before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Fix `testcontainers[postgres]` broken install — required for conftest.py to load and unit tests to run
  - Fix command: `cd backtest && uv sync --reinstall-package testcontainers` (may not work if path-with-spaces is root cause)
  - Alternative: Manually recreate missing `postgres/__init__.py` from testcontainers source
  - Blocker: Until fixed, `pytest tests/unit/` fails at conftest import even for tests that don't use testcontainers

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `uv run fund-backtest` | `.venv/bin/fund-backtest` with PYTHONPATH | Phase 9 (2026-03-30) | Required due to Python 3.12 .pth-skip bug in paths with spaces |
| `export $(xargs .env)` | Inline env vars on command line | Phase 9 (2026-03-30) | Required due to EDGAR_IDENTITY containing a space |
| batch_sleep_secs=1.0 (default) | batch_sleep_secs=3.0 for first bulk download | Phase 10 recommendation | Reduces yfinance 429 errors during initial 400-ticker load |

## Open Questions

1. **How to override batch_sleep_secs=3.0 without modifying CLI code?**
   - What we know: `PriceSettings` is a plain BaseModel — no env var support; `load_price_settings()` in the CLI is called with no config_path argument
   - What's unclear: Whether to add config/price.yaml auto-loading to the CLI (clean) or create a Python wrapper script (quick)
   - Recommendation: Add one line to the CLI's `download` command to check for `config/price.yaml` and pass it to `load_price_settings()`. This is a ~3-line code change consistent with the existing YAML-loading pattern. Alternatively, the plan can include a Wave 0 task to patch the CLI.

2. **POP-04 timing: when can ticker overlap be verified?**
   - What we know: `companies` table is empty until Phase 11 (`ai-washer universe scan` runs). The overlap count will be 0 during Phase 10.
   - What's unclear: Whether POP-04 can be "satisfied" in Phase 10 by verifying the SQL query structure works and documenting expected overlap count, then doing a final count check after Phase 11.
   - Recommendation: Phase 10 plan should verify POP-04 SQL query works and document expected overlap. The actual count verification should be a checkpoint deferred to after Phase 11 completes, or Phase 10 can run `ai-washer universe scan --dry-run` to get a sense of expected company count without persisting.

3. **testcontainers fix approach**
   - What we know: `testcontainers 4.14.2` is installed but `postgres` submodule is empty/broken; `uv sync` shows it as installed but doesn't fix the import
   - What's unclear: Whether `uv sync --reinstall-package testcontainers` from the same path-with-spaces would fix it
   - Recommendation: Wave 0 should attempt `uv sync --reinstall-package testcontainers` first. If that fails, create a symlink: `ln -s "/Users/maxzou/Documents/projects/AI Hedgefund/backtest/.venv/lib/python3.12/site-packages/testcontainers/postgres 2" "/Users/maxzou/Documents/projects/AI Hedgefund/backtest/.venv/lib/python3.12/site-packages/testcontainers/postgres"` (symlink the " 2" version to the expected name). Verify with `python -c "from testcontainers.postgres import PostgresContainer; print('OK')"` after each attempt.

## Project Constraints (from CLAUDE.md)

- **Immutability:** Historical price data must never be overwritten — append new snapshots only. Both `insert_bars()` and `insert_anomalies()` use ON CONFLICT DO NOTHING.
- **Data source:** yfinance only for v1 — no alternatives.
- **Frequency:** Daily bars only.
- **History:** 5 years minimum (back to ~2021).
- **Stack:** Python 3.11+, uv, PostgreSQL.
- **Independence:** fund-backtest must work as standalone module — no hard dependency on ai_washer internals.
- **PYTHONPATH workaround:** Python 3.12 skips .pth files in venvs when path contains spaces — use `.venv/bin/<cmd>` with explicit PYTHONPATH, never `uv run`.

## Sources

### Primary (HIGH confidence)
- Source code reading: `backtest/src/fund_backtest/cli.py` — exact CLI commands, argument signatures, error handling
- Source code reading: `backtest/src/fund_backtest/price/builder.py` — PriceBuilder.download() flow, batch_sleep_secs usage
- Source code reading: `backtest/src/fund_backtest/universe/builder.py` — UniverseBuilder.refresh() flow
- Source code reading: `backtest/src/fund_backtest/config.py` — PriceSettings defaults (batch_size=80, batch_sleep_secs=1.0, lookback_years=5, coverage_alert_threshold=0.95)
- Live environment: `docker ps` confirms container running; `fund-backtest --help` works with PYTHONPATH; `fund-backtest universe status` confirms empty universe; `fund-backtest data coverage` confirms no price data
- Phase 09-02-SUMMARY.md: PYTHONPATH workaround, xargs .env failure documented with exact fix
- Database inspection: `\dt` and `\d universe_tickers` and `\d companies` confirmed schema — both tables have `ticker` column for JOIN

### Secondary (MEDIUM confidence)
- CONTEXT.md and STATE.md: batch_sleep_secs=3.0 recommendation for first bulk download
- STATE.md: SignalAdapter.min_coverage=5 threshold (from Phase 3 decisions)

## Metadata

**Confidence breakdown:**
- CLI commands and flags: HIGH — verified by live dry-run and source reading
- PriceSettings defaults: HIGH — verified by live Python execution in venv
- testcontainers bug: HIGH — verified by live import failure and directory listing
- batch_sleep_secs=3.0 recommendation: MEDIUM — from STATE.md context, not empirically tested
- Expected ticker count (200-350): MEDIUM — based on S&P 400 size and $2B-$10B market cap filter heuristic

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (Wikipedia S&P 400 table changes quarterly; yfinance API is stable)
