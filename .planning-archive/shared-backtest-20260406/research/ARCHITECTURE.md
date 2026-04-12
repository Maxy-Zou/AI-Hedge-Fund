# Architecture Patterns: Live End-to-End Pipeline Integration

**Domain:** Two-package shared-database integration via Docker Compose
**Researched:** 2026-03-29
**Confidence:** HIGH — derived entirely from live codebase inspection, not training data

---

## Context

This document supersedes the v1.0 architecture doc for milestone v1.1. The static backtesting architecture (signal contract, vectorized simulator, layers) is already built and correct. This document focuses on **how the two packages connect at runtime** to produce real backtest results from real AI Washing Detector scores.

The core integration challenge: `ai_washer` and `fund_backtest` are two separate Python packages in two separate directories, both targeting the same PostgreSQL instance, with independent Alembic migration chains and independent environment variable namespaces. Running the live pipeline requires both packages to be configured, migrated, and executed in the right order against the same database.

---

## Recommended Architecture

### Integration Topology

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Docker Compose                                                               │
│                                                                               │
│  ┌───────────────────┐         ┌──────────────────────────────────────────┐  │
│  │  PostgreSQL 16    │◄────────┤  Shared Database: ai_hedge_fund          │  │
│  │  port 5432        │         │                                          │  │
│  │  (single instance)│         │  ai_washer tables (Alembic chain A):     │  │
│  └───────────────────┘         │    companies, daily_scores,              │  │
│           │                    │    signal_details, pipeline_runs,        │  │
│           │                    │    sec_filings, xbrl_facts, patents,     │  │
│           │                    │    github_repos, earnings_transcripts,   │  │
│           │                    │    job_postings, data_source_status      │  │
│           │                    │                                          │  │
│           │                    │  fund_backtest tables (Alembic chain B): │  │
│           │                    │    universe_tickers, universe_snapshots, │  │
│           │                    │    price_bars, price_anomalies           │  │
│           │                    └──────────────────────────────────────────┘  │
│           │                                                                   │
│  ┌────────┴──────────────────────────────────────────────────────────────┐   │
│  │  Host (developer machine)                                             │   │
│  │                                                                       │   │
│  │  Al Washing Detector/           backtest/                            │   │
│  │    ai-washer CLI                  fund-backtest CLI                  │   │
│  │    (separate venv)                (separate venv)                    │   │
│  │    env: AI_WASHER_*               env: FUND_BACKTEST_*               │   │
│  │    connects to localhost:5432     connects to localhost:5432          │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

The database is the **only coupling point** between the two packages. There are no Python imports across package boundaries. `fund_backtest.signal.loaders.ai_washing` executes a raw SQL `JOIN` query against `daily_scores JOIN companies` — it reads `ticker`, `scored_at::date`, and `composite_score` and nothing else. This is explicitly enforced by the comment on line 6 of `ai_washing.py`: "no Python imports cross package boundaries."

---

## Component Boundaries

| Component | Package | Responsibility | Communicates With |
|-----------|---------|---------------|-------------------|
| `daily_pipeline_flow` (Prefect) | `ai_washer` | Orchestrates all 5 ingestion stages + scoring, writes `daily_scores` | PostgreSQL (writes) |
| `ScoringOrchestrator` | `ai_washer` | Reads Filing/XBRL/Patent/GitHub/Earnings/Job rows, calls pure scorers, writes `SignalDetail` and `DailyScore` | PostgreSQL (reads + writes) |
| `ai_washer` Alembic | `ai_washer` | Manages 10 tables: companies → data_source_status | PostgreSQL (DDL) |
| `AiWashingLoader` | `fund_backtest` | Raw SQL JOIN against `daily_scores JOIN companies`, pivots to `SignalFrame` | PostgreSQL (reads only) |
| `UniverseBuilder` | `fund_backtest` | Scrapes S&P 400 from Wikipedia, validates market caps via yfinance, writes `universe_tickers` | PostgreSQL (writes), yfinance, Wikipedia |
| `PriceBuilder` | `fund_backtest` | Downloads OHLCV via yfinance, writes `price_bars` | PostgreSQL (writes), yfinance |
| `fund_backtest` Alembic | `fund_backtest` | Manages 4 tables: universe_tickers, universe_snapshots, price_bars, price_anomalies | PostgreSQL (DDL) |
| `fund-backtest backtest run` | `fund_backtest` | End-to-end backtest: load signal → adapt → simulate → metrics | PostgreSQL (reads both packages' tables) |

---

## Data Flow: Live End-to-End Execution

The complete data flow for a real backtest run, in dependency order:

```
Step 0: Infrastructure
  docker compose up -d postgres
  [waits for postgres to accept connections]

Step 1: Migrate ai_washer schema
  cd "Al Washing Detector/"
  AI_WASHER_DATABASE_URL=postgresql+psycopg://... alembic upgrade head
  → creates: companies, daily_scores (partitioned), signal_details,
             pipeline_runs, sec_filings, xbrl_facts, patents,
             github_repos, earnings_transcripts, job_postings,
             data_source_status

Step 2: Migrate fund_backtest schema
  cd backtest/
  DATABASE_URL=postgresql+psycopg://... alembic upgrade head
  → creates: universe_tickers, universe_snapshots, price_bars,
             price_anomalies

Step 3: Seed fund_backtest universe
  fund-backtest universe refresh
  → scrapes S&P 400, validates market caps via yfinance
  → writes universe_tickers rows (200-400 active tickers)
  → writes universe_snapshots record

Step 4: Populate ai_washer companies (must match fund_backtest universe)
  ai-washer universe scan
  → queries SEC EDGAR EFTS for AI-mentioning companies
  → validates market caps, resolves entity aliases
  → writes companies rows with ticker + CIK

Step 5: Download price data
  fund-backtest data download
  → reads active universe_tickers from PostgreSQL
  → downloads 5yr OHLCV via yfinance in 80-ticker batches
  → writes price_bars rows (append-only, ~250K rows for 200 tickers × 1250 days)

Step 6: Run AI Washing Detector pipeline
  ai-washer pipeline run   (or trigger daily_pipeline_flow via Prefect)
  → collect_sec_filings_stage  → writes sec_filings, xbrl_facts
  → collect_patents_stage      → writes patents
  → collect_github_stage       → writes github_repos
  → collect_earnings_stage     → writes earnings_transcripts
  → collect_jobs_stage         → writes job_postings
  → score_all_stage            → writes signal_details
  → compute_composites_stage   → writes daily_scores

Step 7: Run backtest
  fund-backtest backtest run --signal ai-washing
  Stage 1: AiWashingLoader reads daily_scores JOIN companies
           → pivots to SignalFrame (DatetimeIndex × tickers, float scores)
  Stage 2: PriceBarRepository reads price_bars for signal tickers/dates
           → pivots to PriceFrame (DatetimeIndex × tickers, close prices)
  Stage 3: SignalAdapter.adapt(signal_frame)
           → cross-sectional rank → weights → shift(1) → WeightFrame
  Stage 4: PortfolioSimulator.simulate(weight_frame, price_frame)
           → daily returns + trade log + positions → PortfolioResult
  Stage 5: MetricsEngine.compute(portfolio_result)
           → Sharpe, CAGR, drawdown, etc. → MetricsBundle
  [Stage 6: optional --export-all → CSV/JSON exports]

Step 8: Launch dashboard
  cd backtest/
  streamlit run src/fund_backtest/dashboard/app.py
  → reads PortfolioResult + MetricsBundle (from file or in-memory)
  → renders equity curve, drawdown, monthly heatmap, sector exposure
```

---

## Integration Points: New vs Modified

### New Components Required for v1.1

| Component | Type | Why Needed |
|-----------|------|-----------|
| `docker-compose.yml` | New file (root of repo) | No Docker Compose exists yet. PostgreSQL must be containerized for local development — hardcoded localhost:5432 is not reproducible across machines. |
| `.env` for `backtest/` | New file | `backtest/` has `.env.example` missing (unlike `Al Washing Detector/` which has `.env.example`). Need `FUND_BACKTEST_DATABASE_URL` pointing to the Docker Compose postgres. |
| `docker-compose.yml` healthcheck | New (inside compose file) | Both packages' CLIs will fail immediately if postgres is not ready. Healthcheck ensures `pg_isready` passes before any CLI is invoked. |
| Migration run order script / README | New file (optional) | Steps 1–8 above must be documented. Currently there is no runbook for the full v1.1 pipeline. |

### Modified Components for v1.1

| Component | Current State | Required Change |
|-----------|---------------|----------------|
| `ai_washer` Alembic `env.py` | Reads `AI_WASHER_DATABASE_URL` | No change needed — already correct |
| `fund_backtest` Alembic `env.py` | Reads `DATABASE_URL` or `FUND_BACKTEST_DATABASE_URL` | No change needed — already has dual env var support |
| `fund-backtest backtest run` CLI | Already wired to `AiWashingLoader` | No functional change — just needs live data |
| `AiWashingLoader` | Reads `daily_scores JOIN companies` | No change needed — already correct |

### Confirmed Working Integration Code

`backtest/src/fund_backtest/signal/loaders/ai_washing.py` already executes:

```sql
SELECT companies.ticker,
       daily_scores.scored_at::date AS signal_date,
       daily_scores.composite_score
FROM daily_scores
JOIN companies ON daily_scores.company_id = companies.id
ORDER BY signal_date, ticker
```

This is the complete integration surface. There is no other cross-package coupling.

---

## Environment Configuration

### ai_washer `.env` (in `Al Washing Detector/`)

```
AI_WASHER_DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund
AI_WASHER_EDGAR_IDENTITY=YourName yourname@example.com
AI_WASHER_GITHUB_TOKEN=ghp_...
AI_WASHER_PATENTSVIEW_API_KEY=...
AI_WASHER_EARNINGSCALL_API_KEY=...
AI_WASHER_LOG_LEVEL=INFO
```

### fund_backtest `.env` (in `backtest/`)

```
FUND_BACKTEST_DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund
FUND_BACKTEST_LOG_LEVEL=INFO
```

Both packages point to **the same database name** (`ai_hedge_fund`). They use different table namespaces (no schema-level separation — both in `public`). The env var prefixes (`AI_WASHER_` vs `FUND_BACKTEST_`) prevent collision.

### Docker Compose (to be created at repo root)

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: hedge
      POSTGRES_PASSWORD: hedge
      POSTGRES_DB: ai_hedge_fund
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hedge -d ai_hedge_fund"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  postgres_data:
```

The `docker-compose.yml` belongs at the repo root (`AI Hedgefund/`) so it is shared by both packages. Neither package-level directory should own it.

---

## Migration Ordering and Schema Ownership

The two Alembic chains are **fully independent**. They share a database but do not share a migration history. Each chain manages its own tables:

| Alembic Chain | Tables Owned | Run From |
|--------------|-------------|---------|
| `ai_washer` (001_initial → 008_add_data_source_status) | companies, daily_scores, signal_details, pipeline_runs, sec_filings, xbrl_facts, patents, github_repos, earnings_transcripts, job_postings, data_source_status | `Al Washing Detector/` |
| `fund_backtest` (001_universe_schema, 002_price_bars_schema) | universe_tickers, universe_snapshots, price_bars, price_anomalies | `backtest/` |

Order matters for the cross-package JOIN: `ai_washer` migrations must run before `fund_backtest` migrations only if `fund_backtest` had a foreign-key dependency on `ai_washer` tables — which it does **not**. The JOIN in `AiWashingLoader` is raw SQL at query time. Both migration chains can run in any order.

However, the **data population order** matters strictly (Steps 3–6 above):
- `ai_washer` `companies` must be populated before scoring can write `daily_scores`.
- `fund_backtest` `universe_tickers` must be populated before `price_bars` can be downloaded.
- Both `daily_scores` and `price_bars` must have data before `fund-backtest backtest run` succeeds.

---

## Ticker Overlap: Critical Dependency

The `AiWashingLoader` query returns only tickers present in the `ai_washer` `companies` table that also have `daily_scores`. The `PriceBarRepository` query returns only tickers present in `fund_backtest` `price_bars`.

For the backtest to produce meaningful results, the tickers in `ai_washer` `companies` must **overlap significantly** with tickers in `fund_backtest` `universe_tickers`.

**Current state:** These are populated independently:
- `ai_washer` universe comes from SEC EDGAR EFTS queries for AI-mentioning companies, filtered by market cap
- `fund_backtest` universe comes from Wikipedia S&P 400 list, filtered by market cap

**Risk:** Overlap may be partial. `AiWashingLoader` handles this gracefully — it returns whatever tickers have scores, and `SignalAdapter` will drop tickers without price data automatically. The backtest still runs with partial overlap, but coverage will be lower.

**Verification step:** After running both universe seeds, verify overlap:

```sql
SELECT
  COUNT(DISTINCT c.ticker) AS ai_washer_tickers,
  COUNT(DISTINCT ut.ticker) AS fund_backtest_tickers,
  COUNT(DISTINCT c.ticker) FILTER (WHERE ut.ticker IS NOT NULL) AS overlap
FROM companies c
LEFT JOIN universe_tickers ut ON ut.ticker = c.ticker
WHERE c.is_active = TRUE AND ut.is_active = TRUE;
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Running Migrations Against Wrong Database
**What goes wrong:** `alembic upgrade head` runs against a different database URL than the application uses. This creates schema in one place and the app connects to another.
**Prevention:** Both Alembic `env.py` files read from environment variables (not `alembic.ini`). Always set `AI_WASHER_DATABASE_URL` or `DATABASE_URL` before running migrations. Never hardcode credentials in `alembic.ini`.

### Anti-Pattern 2: Two Separate PostgreSQL Instances
**What goes wrong:** Developer starts two separate postgres containers (one per package). The `AiWashingLoader` SQL JOIN finds no rows because `companies` and `daily_scores` are in different databases.
**Prevention:** One `docker-compose.yml` at the repo root. One postgres container. Both packages point to the same `DATABASE_URL`. The compose file must live at repo root, not inside either package directory.

### Anti-Pattern 3: Scoring Before Universe Population
**What goes wrong:** Running `ai-washer pipeline run` before `ai-washer universe scan`. The `ScoringOrchestrator.score_all()` queries `companies WHERE is_active = TRUE AND cik IS NOT NULL` — if `companies` is empty, no scoring occurs and `daily_scores` stays empty. `AiWashingLoader` then raises `SignalLoadError: scores table is empty`.
**Prevention:** Follow execution order in Step 4 before Step 6. Verify `SELECT COUNT(*) FROM companies WHERE is_active = TRUE` returns non-zero before triggering the pipeline.

### Anti-Pattern 4: `daily_scores` Partitions Missing Future Dates
**What goes wrong:** `ai_washer` migration `001_initial` creates monthly partitions from 2026-01 through 2027-06. If scoring runs after 2027-06, the insert fails with a partition-not-found error.
**Prevention:** For v1.1, partition range covers 18 months (sufficient). Add a monitoring alert or extend partitions in a future migration if the project runs past mid-2027.

### Anti-Pattern 5: Separate `.env` Files Out of Sync
**What goes wrong:** Developer updates `AI_WASHER_DATABASE_URL` to point to a new host but forgets `FUND_BACKTEST_DATABASE_URL`. Scoring writes to one postgres, backtest reads from another.
**Prevention:** Document that both `.env` files must have matching host/port/db. Consider a shared `.env` at repo root with a symlink or source-include pattern, though this adds complexity.

---

## Scalability Considerations

| Concern | v1.1 (live run) | Future |
|---------|----------------|--------|
| postgres storage | ~500MB estimated (5yr prices + all signal data) | Fine on developer machine |
| `daily_scores` partition expiry | Covered to 2027-06 | Add migration to extend partitions |
| Scoring runtime | Sequential per SEC rate limits (~hours for full universe) | Acceptable for daily batch |
| Price download runtime | ~5-10 min for 200 tickers (80-ticker batches, 1s sleep) | Acceptable for initial load |
| `AiWashingLoader` query | Full table scan — no date filter applied | Add date range filter if perf degrades |
| Docker Compose network | localhost port-forward — fine for local dev | For production, use named network and service discovery |

---

## Build Order for v1.1 Milestone

Phases ordered by data dependency (each step depends on the previous):

```
1. Infrastructure
   [NEW] docker-compose.yml at repo root
   [NEW] backtest/.env with FUND_BACKTEST_DATABASE_URL
   [VERIFY] Al Washing Detector/.env with AI_WASHER_DATABASE_URL

2. Schema
   ai_washer: alembic upgrade head  (from Al Washing Detector/)
   fund_backtest: alembic upgrade head  (from backtest/)

3. Universe Population
   ai-washer universe scan          (writes ai_washer.companies)
   fund-backtest universe refresh   (writes fund_backtest.universe_tickers)

4. Data Collection
   fund-backtest data download      (writes fund_backtest.price_bars, ~hours first run)
   ai-washer pipeline run           (writes all signal + score tables, ~hours first run)

5. First Live Backtest
   fund-backtest backtest run --signal ai-washing [--export-all]

6. Dashboard
   streamlit run backtest/src/fund_backtest/dashboard/app.py
```

---

## Sources

All findings derived from direct codebase inspection (HIGH confidence):

- `/Users/maxzou/Documents/projects/AI Hedgefund/backtest/src/fund_backtest/signal/loaders/ai_washing.py` — integration SQL query, no cross-package imports
- `/Users/maxzou/Documents/projects/AI Hedgefund/backtest/src/fund_backtest/cli.py` — `backtest run` pipeline stages
- `/Users/maxzou/Documents/projects/AI Hedgefund/backtest/src/fund_backtest/config.py` — `FUND_BACKTEST_DATABASE_URL` env var
- `/Users/maxzou/Documents/projects/AI Hedgefund/Al Washing Detector/src/ai_washer/config.py` — `AI_WASHER_DATABASE_URL` env var
- `/Users/maxzou/Documents/projects/AI Hedgefund/backtest/src/fund_backtest/db/migrations/env.py` — reads `DATABASE_URL` or `FUND_BACKTEST_DATABASE_URL`
- `/Users/maxzou/Documents/projects/AI Hedgefund/Al Washing Detector/src/ai_washer/db/migrations/env.py` — reads `AI_WASHER_DATABASE_URL`
- `/Users/maxzou/Documents/projects/AI Hedgefund/Al Washing Detector/src/ai_washer/db/models.py` — `daily_scores` (partitioned), `companies`, and 9 other tables
- `/Users/maxzou/Documents/projects/AI Hedgefund/backtest/src/fund_backtest/db/models.py` — `universe_tickers`, `price_bars`, and 2 other tables
- `/Users/maxzou/Documents/projects/AI Hedgefund/Al Washing Detector/src/ai_washer/pipeline/daily_flow.py` — 5-stage Prefect pipeline orchestration
- `/Users/maxzou/Documents/projects/AI Hedgefund/Al Washing Detector/.env.example` — env var names and format
