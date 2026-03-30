# Technology Stack

**Project:** Shared Backtesting Infrastructure — v1.1 Live End-to-End Pipeline
**Researched:** 2026-03-29
**Milestone scope:** Stack additions/changes needed to run the full pipeline with real data.
**NOT re-researched:** Python 3.12, uv, SQLAlchemy 2.0, Alembic, Pydantic, Typer CLI, yfinance, quantstats-lumi, Streamlit, Plotly, psycopg3, structlog, testcontainers. These are already validated in `.planning/research/STACK.md` from v1.0.

---

## What v1.1 Adds

v1.0 built and tested the full pipeline in-process with synthetic data. v1.1 runs that same pipeline against:

1. A real PostgreSQL instance (not testcontainers)
2. Real OHLCV data downloaded from yfinance
3. Real AI Washing Risk Scores produced by the AI Washing Detector from SEC filings

The stack delta is small: one Docker Compose file, one `.env.example` for the backtest module, and confirmation that the EDGAR API requirements are already satisfied by the Detector's `AI_WASHER_EDGAR_IDENTITY` configuration.

---

## New Capabilities Required

### Local PostgreSQL via Docker Compose

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker Compose | v2 (compose spec) | Local PostgreSQL for development and integration testing | Both the backtest module and AI Washing Detector need a real PostgreSQL instance to run end-to-end. testcontainers spins up isolated containers per test — correct for unit/integration tests, but not for persistent dev data. Docker Compose gives a stable, persistent local PostgreSQL that both modules can share via the same connection string. |
| postgres image | 16-alpine | PostgreSQL database | `16-alpine` is the smallest stable image: 85MB vs 379MB for full `16`. Alpine has no bash (use `sh`), but the health check only needs `pg_isready`. No extensions required — TimescaleDB was deferred to v2. |

**Compose file location:** `backtest/docker-compose.yml` (backtest module owns it; Detector can use the same instance by pointing at the same port)

**Required services:**
- `postgres` — PostgreSQL 16 with health check via `pg_isready`
- No Redis, no broker, no additional services needed for v1.1

**Health check pattern (HIGH confidence — standard Docker Compose v2 pattern):**
```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-fund} -d ${POSTGRES_DB:-fund_backtest}"]
  interval: 5s
  timeout: 5s
  retries: 5
  start_period: 10s
```

**Why not Docker Compose v1 (`docker-compose`):** Docker Compose v1 (the Python binary) is EOL as of July 2023. Docker Desktop bundles Compose v2 (`docker compose` plugin) — the Compose Spec format is the correct target.

**Why not a managed PostgreSQL (RDS, Supabase):** Over-engineered for local development. Docker Compose gives identical PostgreSQL behavior with zero cost and no external dependency.

### Environment Configuration for Backtest Module

The backtest module currently has no `.env.example`. v1.1 requires one because the live pipeline needs a real database URL and (when running with Detector integration) the EDGAR identity.

| Variable | Required | Purpose |
|----------|----------|---------|
| `FUND_DATABASE_URL` | Yes | PostgreSQL connection string for backtest data |
| `FUND_LOG_LEVEL` | No (default: INFO) | Logging level |

**Not needed in backtest `.env`:** `EDGAR_IDENTITY`, API keys — those live in the Detector's `.env`. The backtest module reads pre-computed scores from PostgreSQL; it does not call EDGAR directly.

**Connection string format (psycopg3 sync driver):**
```
FUND_DATABASE_URL=postgresql+psycopg://fund:fund@localhost:5432/fund_backtest
```

Note: The existing `backtest/pyproject.toml` uses `psycopg[binary]>=3.2` (sync driver). The connection string prefix must be `postgresql+psycopg` (not `postgresql+asyncpg`) to match. This is already consistent with the Detector's `AI_WASHER_DATABASE_URL` pattern in `Al Washing Detector/.env.example`.

### SEC EDGAR API — Already Satisfied

The AI Washing Detector's stack already handles all EDGAR API requirements:

| Requirement | Status | Where |
|-------------|--------|-------|
| User-Agent header (`name email`) | Done | `AI_WASHER_EDGAR_IDENTITY` env var, passed to all `edgartools` / `httpx` calls |
| Rate limiting (10 req/sec max) | Done | `tenacity` retry with 0.1s inter-request delay in `FilingCollector` |
| edgartools >=5.26.1 | Done | `Al Washing Detector/pyproject.toml` dependency |

The backtest module does not call EDGAR. It reads scores the Detector has already written to PostgreSQL. No EDGAR-related additions are needed in the backtest stack.

---

## No New Python Dependencies

The backtest `pyproject.toml` already has everything needed for the live pipeline:

```
yfinance>=1.2.0       # real OHLCV download
sqlalchemy>=2.0.48    # read scores from shared DB
psycopg[binary]>=3.2  # PostgreSQL driver
tenacity>=9.1.4       # retry on yfinance 429 errors
structlog>=25.5.0     # operational logging
```

No new `uv add` commands are required for the backtest module in v1.1.

The AI Washing Detector's `pyproject.toml` similarly already has `prefect>=3.6.23` for pipeline scheduling if a daily run is desired — no additions there either.

---

## Operational Tooling

### What to Build (Not Install)

v1.1 requires authoring three files that do not yet exist:

| File | Purpose |
|------|---------|
| `backtest/docker-compose.yml` | Spin up local PostgreSQL 16 |
| `backtest/.env.example` | Document `FUND_DATABASE_URL` and `FUND_LOG_LEVEL` |
| `backtest/.env` | Local dev values (gitignored, derived from `.env.example`) |

No new CLI tools, no new services, no new Python packages.

### Alembic Migrations

Both modules have Alembic configured. For v1.1, the shared PostgreSQL instance can use separate databases or separate schemas:

- **Separate databases (recommended):** `fund_backtest` for backtest, `ai_washer` for Detector. Connection string isolation, no migration conflicts, simpler per-module `alembic upgrade head`.
- **Separate schemas in one database:** Works but complicates Alembic's `env.py` in each module.

Use separate databases. One Compose file, two `POSTGRES_DB` values, two `alembic upgrade head` commands.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Local PostgreSQL | Docker Compose | Homebrew `postgresql@16` | Brew install pollutes the host; version management fragile; no easy reset. Docker gives hermetic, reproducible environments. |
| Local PostgreSQL | Docker Compose | testcontainers per-run | testcontainers is per-test-session; data doesn't persist between runs. Fine for tests, wrong for a dev environment where you accumulate real data over days. |
| Local PostgreSQL | `postgres:16-alpine` | `postgres:16` (full image) | Full image is 4x larger (379MB vs 85MB). No functional difference for development. Alpine constraint: no bash, use `sh` in override commands. |
| DB layout | Separate databases | Separate schemas | Separate schemas require coordinating Alembic `version_table` names and `include_schemas` config. More error-prone. Separate databases are conceptually clean. |

---

## Integration Points

### How the Live Pipeline Uses the Stack

```
[Docker Compose] → PostgreSQL 16 (localhost:5432)
    ├── database: ai_washer    ← Detector writes DailyScore rows here
    └── database: fund_backtest ← Backtest reads scores, writes results here

[AI Washing Detector]
    ├── reads: SEC EDGAR via edgartools + httpx
    ├── writes: DailyScore rows to ai_washer DB
    └── driven by: Prefect flow or CLI `ai-washer collect all`

[fund-backtest CLI]
    ├── reads: DailyScore from ai_washer DB (SignalAdapter)
    ├── reads: OHLCV from fund_backtest DB (PriceRepository) + yfinance fallback
    ├── runs: vectorbt Portfolio.from_signals()
    ├── computes: quantstats-lumi metrics
    └── writes: results to fund_backtest DB + Streamlit dashboard + PDF tearsheet
```

The shared PostgreSQL instance is the only coupling point between the two modules. This preserves the "no hard dependency on Detector internals" constraint from PROJECT.md.

---

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| Docker Compose v2 / postgres:16-alpine | HIGH | Official Docker Hub image, Compose Spec v2 is current standard, `pg_isready` health check is documented pattern |
| EDGAR requirements already satisfied | HIGH | Verified in Al Washing Detector pyproject.toml (edgartools>=5.26.1) and .env.example (EDGAR_IDENTITY) |
| No new Python dependencies | HIGH | Verified against backtest/pyproject.toml — all live-pipeline libraries already present |
| Separate databases (not schemas) | MEDIUM | Alembic multi-schema config is documented but has known pitfalls; separate databases sidestep those issues |
| psycopg3 connection string prefix | HIGH | Verified against existing Detector .env.example which uses identical pattern |

---

## Sources

- Docker Hub `postgres:16-alpine` image — official image, 85MB
- Docker Compose Spec v2 healthcheck documentation — `pg_isready` pattern
- `Al Washing Detector/pyproject.toml` — edgartools>=5.26.1, tenacity>=9.1.4 verified
- `Al Washing Detector/.env.example` — EDGAR_IDENTITY and DATABASE_URL format verified
- `backtest/pyproject.toml` — confirmed all live-pipeline dependencies already present (yfinance, sqlalchemy, psycopg, tenacity, structlog)
- SEC EDGAR developer FAQ — 10 req/sec rate limit, User-Agent requirement (name + email)
