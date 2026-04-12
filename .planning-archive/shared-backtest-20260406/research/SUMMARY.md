# Research Summary: v1.1 Live End-to-End Pipeline

**Milestone:** v1.1
**Researched:** 2026-03-29
**Confidence:** HIGH — all findings from direct codebase inspection

---

## Executive Summary

v1.1 is a **commissioning milestone**, not a feature-building milestone. All backtesting logic is complete (185 tests, 90.27% coverage). The gap is purely operational: no PostgreSQL instance exists, no real data has been downloaded, the AI Washing Detector has never been run against real SEC filings, and the dashboard is hardcoded to synthetic demo data.

The stack delta is minimal: one Docker Compose file, one `.env.example`, and zero new Python dependencies. The dominant risk is operational — Alembic migration collisions between the two packages, yfinance rate limiting on bulk downloads, and SEC EDGAR's 10 req/sec limit making the first Detector run take 4-10 hours.

---

## Key Findings

### Stack Additions

- **Docker Compose v2** with `postgres:16-alpine` (85MB) — the only new infrastructure component
- **No new Python packages needed** — both `backtest/pyproject.toml` and `Al Washing Detector/pyproject.toml` already declare everything
- **Three files to author:** `docker-compose.yml` (repo root), `backtest/.env.example`, `backtest/.env` (gitignored)

### Critical Bugs to Fix Before Live Run

1. **Alembic collision:** Both packages write to `public.alembic_version` — neither `env.py` sets `version_table`. Will break on first joint migration run.
2. **Signal-price date misalignment:** `cli.py backtest run` doesn't intersect signal and price date indices before calling the simulator — ~50 rows silently become 0% returns with real data.
3. **Export uses demo stubs:** `backtest export` still calls `make_demo_result()` — tearsheets show synthetic data until wired to real results.
4. **Dashboard sector chart hardcoded to demo data** (INTG-02 from v1.0 audit).
5. **Benchmark alpha/beta always 0.0** in CLI exports (Phase 5/8 tech debt).

### Architecture

- **Single shared database** (`ai_hedge_fund`) with two independent Alembic chains
- **Integration surface:** One raw SQL query in `AiWashingLoader` (`daily_scores JOIN companies`) — no cross-package Python imports
- **Ticker overlap not guaranteed:** `ai_washer` builds universe from SEC EDGAR EFTS; `fund_backtest` from Wikipedia S&P 400. Must verify overlap before first backtest.
- **Docker Compose at repo root** — shared by both packages

### Operational Risks

- **Detector first run is the long pole:** 4-10 hours due to SEC EDGAR rate limits
- **yfinance bulk download:** Chunking already implemented but needs `batch_sleep_secs=3.0` for first run
- **Docker volume risk:** Must use named volume or `docker system prune` destroys data
- **Env var coordination:** Three different variable names (`DATABASE_URL`, `AI_WASHER_DATABASE_URL`, `FUND_BACKTEST_DATABASE_URL`) must point to the same connection string

---

## Suggested Build Order

1. **Infrastructure** — Docker Compose + `.env` + fix Alembic `version_table` + run both migrations
2. **Data Population** — `fund-backtest universe refresh` + `fund-backtest data download` + `ai-washer universe scan`
3. **Detector Execution** — Run full AI Washing Detector pipeline against real SEC filings (long-running)
4. **Bug Fixes + Wiring** — Fix signal-price alignment, wire exports to real results, fix dashboard demo stubs
5. **Live Backtest + Dashboard** — `fund-backtest backtest run --signal ai-washing` + dashboard with real data

---

## Watch Out For

- Alembic version table collision (fix BEFORE any migration run)
- yfinance 429 errors on first bulk download (chunking exists, but verify coverage after)
- SEC EDGAR `AI_WASHER_EDGAR_IDENTITY` must be a valid email in User-Agent
- `SignalAdapter.min_coverage=5` threshold — verify enough tickers overlap between universes
- Docker anonymous volumes destroyed by `docker system prune`

---

*Synthesized from: STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md*
