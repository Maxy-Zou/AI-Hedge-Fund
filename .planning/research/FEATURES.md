# Feature Landscape: v1.1 Live End-to-End Pipeline

**Domain:** Operational pipeline commissioning — going from demo mode to real data
**Researched:** 2026-03-29
**Scope:** Features needed ONLY to move from v1.0 (all demo/synthetic data) to v1.1 (real data flowing through the full stack)
**Overall confidence:** HIGH — based on direct codebase inspection, not estimation

---

## Context: What Is Already Built

All backtesting logic is complete and verified (185 tests, 90.27% coverage). The gap is purely
operational: no PostgreSQL instance exists, no real data has been downloaded, the AI Washing
Detector has never been run against real SEC filings, and the dashboard is hardcoded to
synthetic demo data. v1.1 is a commissioning milestone, not a feature-building milestone.

**Already built (v1.0, do not rebuild):**
- Mid-cap universe management (`fund-backtest universe refresh/status`)
- Daily OHLCV pipeline (`fund-backtest data download/update/coverage`)
- Signal adapter + look-ahead bias prevention
- Vectorized portfolio simulator with transaction/borrow cost models
- Risk metrics engine (Sharpe, Sortino, Calmar, alpha, beta, drawdown, rolling windows)
- Streamlit dashboard (demo mode — equity curve, drawdown, monthly heatmap, sector exposure)
- PDF tearsheet + CSV/JSON exports
- `backtest run --signal ai-washing` end-to-end CLI command
- AI Washing Detector full pipeline: 6-signal ingestion + composite scoring + `daily_pipeline_flow`

---

## Table Stakes

Features required for v1.1 to work at all. Missing any one = pipeline cannot run.

| Feature | Why Required | Complexity | Depends On |
|---------|--------------|------------|------------|
| Docker Compose for PostgreSQL | Both the backtester and Detector require `FUND_BACKTEST_DATABASE_URL` / `AI_WASHER_DATABASE_URL`. No DB = every CLI command exits 1. No Docker Compose exists in the repo today. | Low | Docker installed locally |
| Alembic migrations for both packages | The backtest DB schema (universe_tickers, price_bars, etc.) and Detector DB schema (companies, daily_scores, etc.) must be created before any data can be written. Migrations exist but have never been run against a real DB. | Low | Docker Compose PostgreSQL running |
| `.env` files for both packages | `FUND_BACKTEST_DATABASE_URL` and `AI_WASHER_DATABASE_URL` must point to the same PostgreSQL instance (shared DB). `AI_WASHER_EDGAR_IDENTITY` is legally required by SEC. Without these, both CLIs raise Pydantic ValidationError at startup. | Low | PostgreSQL instance URL |
| Universe population (`fund-backtest universe refresh`) | The backtester needs active tickers before it can download price data. The Detector's universe scan is independent but targets the same companies. The price downloader queries `universe_tickers` — empty table = zero bars downloaded. | Low | Backtest migrations run |
| Price data download (`fund-backtest data download`) | `backtest run` loads prices from `price_bars` table. Empty table = empty `price_frame` = portfolio simulator returns zero-length result = metrics engine divide-by-zero. Download takes ~10-30 min for 5 years x 200+ tickers. | Medium | Universe populated, yfinance accessible |
| AI Washing Detector pipeline execution (`ai-washer pipeline run` or `daily_pipeline_flow`) | `AiWashingLoader.load()` queries `daily_scores JOIN companies`. Empty `daily_scores` raises `SignalLoadError("scores table is empty")` — `backtest run` exits 1 immediately. Pipeline must run at least once to produce any scores. | High | Detector migrations run, EDGAR identity configured, SEC accessible |
| `backtest run --signal ai-washing` completing successfully | The end-to-end CLI command (`signal load → adapt → simulate → metrics`) is the v1.1 milestone. This is the integration test the whole milestone builds toward. | Low | All above complete |

---

## Differentiators

Features that make the live results *useful* and investor-ready rather than just technically
running. Not required for pipeline to execute, but required for the output to be credible.

| Feature | Value Proposition | Complexity | Depends On |
|---------|-------------------|------------|------------|
| Dashboard live mode (replace demo data with real DB query) | Dashboard hardcodes `make_demo_result()` and `DEMO_TICKER_SECTORS`. Investor demo showing real results from real SEC filings is qualitatively different from synthetic data. Identified as INTG-02 tech debt in v1.0 audit. | Low | `backtest run` successful, DB populated |
| Tearsheet PDF from live run path | `backtest run --export-all` currently produces CSV + JSON but skips `TearsheetBuilder`. The tearsheet is the investor-facing artifact. Identified as INTG-01 tech debt in v1.0 audit. The fix is a 5-line wiring change in `cli.py`. | Low | `backtest run` successful |
| Benchmark returns in CLI run path | `alpha` and `beta` are hardcoded `0.0` in all CLI-path exports because `yfinance` benchmark fetch only runs inside the dashboard. SPY/IWM download exists in `dashboard/app.py` but not wired to `backtest run`. Identified as Phase 5/8 tech debt. | Low | `backtest run` successful, yfinance accessible |
| Run documentation / operator playbook | The sequence `docker compose up → migrate → universe → download → pipeline run → backtest run → view dashboard` has never been written down. A developer joining the project cannot reproduce the live pipeline without reverse-engineering all the CLI commands. A `docs/RUNBOOK.md` or `README.md` section eliminates this. | Low | All steps known |

---

## Anti-Features

Features to explicitly NOT build in v1.1. The milestone is commissioning, not feature expansion.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| New signal sources or scoring changes | Adding signals during commissioning mixes "does the pipeline run?" with "is the signal correct?" — two different failure modes. | Treat existing 6-signal composite score as fixed input. Evaluate signal quality after the pipeline runs successfully. |
| Scheduled / automated pipeline runs (cron, Prefect server) | Prefect `daily_pipeline_flow` exists but requires a Prefect server or Cloud account for scheduling. Setting up Prefect orchestration is a separate operational concern unrelated to proving the pipeline works once. | Run `daily_pipeline_flow` manually via `prefect run` or direct Python invocation for v1.1. Scheduling is v1.2+. |
| Production deployment / cloud infrastructure | AWS/GCP/Kubernetes setup is months of work and operational risk. v1.1 target is local development proving real data flows. | Local Docker Compose is sufficient for v1.1 investor demo. Production deployment is a separate milestone. |
| PostgreSQL performance tuning / partitioning verification | `daily_scores` has monthly RANGE partitioning in the migration. Verifying partition pruning performance requires significant data volume. | Accept whatever performance the first run produces. Tune after data volume is meaningful. |
| New dashboard pages or chart types | The dashboard has three working tabs (Performance, Monthly Returns, Sector Exposure). Adding charts before real data is available means testing charts with no data. | Wire real data to existing charts first. New visualizations after data quality is validated. |
| CI/CD pipeline setup | Adding GitHub Actions or Docker build pipelines adds complexity without unblocking the live pipeline. | Manual local execution for v1.1. CI/CD is a DevOps milestone. |
| Multi-user or multi-strategy setup | The framework supports multiple strategies by design, but no second strategy exists yet. Multi-strategy configuration is premature. | One signal source (`ai-washing`) for v1.1. |

---

## Feature Dependencies (v1.1 Specific)

```
Docker Compose (PostgreSQL running)
  → Alembic migrations (backtest + detector)
    → .env files configured
      → Universe refresh (fund-backtest universe refresh)
        → Price data download (fund-backtest data download)  [~10-30 min]
      → Detector universe scan (ai-washer universe scan)
        → Detector pipeline run (ai-washer pipeline run or daily_pipeline_flow)  [hours — SEC rate-limited]
          → backtest run --signal ai-washing
            → Dashboard live mode (replace _load_demo_data with DB query)
            → Tearsheet PDF (wire TearsheetBuilder into run path)
            → Benchmark returns (wire yfinance SPY/IWM fetch into run path)
```

Critical bottleneck: The Detector pipeline is SEC EDGAR rate-limited at 10 req/sec. For 200+
companies across 5+ years of filings, initial ingestion takes multiple hours. Everything
downstream of the Detector pipeline is blocked until at least one batch completes.

---

## Operational Behaviors: Expected Patterns

### PostgreSQL via Docker Compose

Standard pattern for local development. The shared DB approach means both packages write to
the same PostgreSQL instance but separate tables:
- Backtest package owns: `universe_tickers`, `universe_snapshots`, `price_bars`, `price_anomalies`
- Detector package owns: `companies`, `daily_scores`, `signal_details`, `sec_filings`, `xbrl_facts`, `patents`, `github_repos`, `earnings_transcripts`, `job_postings`, `pipeline_runs`, `data_source_status`
- No foreign keys cross package boundaries — integration is via raw SQL in `AiWashingLoader`

Expected behavior: `docker compose up -d` → postgres container starts → both `FUND_BACKTEST_DATABASE_URL` and `AI_WASHER_DATABASE_URL` point to `postgresql://localhost:5432/hedgefund` → both `alembic upgrade head` commands succeed → all tables exist.

Risk: Port conflicts if local PostgreSQL is already running on 5432. Standard mitigation: use 5433 in Docker Compose and document the non-standard port.

### Bulk Historical Price Data Download

yfinance downloads in 80-ticker batches with 1-second sleep between batches. For 200 tickers
over 5 years:
- Expected duration: 3-8 minutes (network-dependent)
- Expected bars inserted: ~250,000 (200 tickers x 252 trading days x 5 years)
- Expected failures: 1-5 tickers with gaps or delistings (handled by `failed` list in summary)
- Rate limiting: yfinance has undocumented rate limits — the 1-second batch sleep is the existing mitigation. If rate-limited, download resumes from where it left off on next run (incremental update logic already built)

Expected behavior: `fund-backtest data download` → Rich table showing "Tickers requested: 200 / Tickers successful: 197 / Bars inserted: 248,000". Non-zero `failed` count is normal and non-blocking.

### AI Washing Detector Pipeline Execution

The `daily_pipeline_flow` Prefect flow runs 5 sequential ingestion stages + scoring. Sequential
execution is required for SEC EDGAR rate compliance (10 req/sec limit).

For initial run on 200+ companies:
- SEC filings stage: 2-6 hours (rate-limited at 10 req/sec, hundreds of filings per company)
- Patents stage: 30-60 minutes (USPTO PatentsView API is more permissive)
- GitHub stage: 10-30 minutes (5,000 req/hr with token)
- Earnings stage: 1-2 hours (depends on data source availability)
- Jobs stage: 20-40 minutes (python-jobspy scraping)
- Scoring stage: 5-15 minutes (local FinBERT inference, CPU-only)

Total: 4-10 hours for first full run. Subsequent daily runs are incremental (only new filings).

Expected behavior: `ai-washer pipeline run` → Prefect flow logs per stage → `daily_scores` table populated → `AiWashingLoader.load()` returns non-empty SignalFrame.

Known degradation modes: PatentsView API key missing → patent stage skips with warning (graceful degradation built in). GitHub token missing → GitHub stage runs at 60 req/hr unauthenticated rate. EDGAR rate limit hit → tenacity exponential backoff retries automatically.

### End-to-End Backtest Execution

`backtest run --signal ai-washing` runs a 5-stage in-process pipeline:
1. `AiWashingLoader.load()` — single SQL query, < 1 second
2. `PriceBarRepository.get_bars()` — indexed query, < 5 seconds for full universe
3. `SignalAdapter.adapt()` — pandas operations, < 1 second
4. `PortfolioSimulator.simulate()` — vectorized pandas, < 5 seconds for 5-year daily
5. `MetricsEngine.compute()` — scalar calculations, < 1 second

Total expected runtime: < 15 seconds after data is loaded. The pipeline itself is fast — the data loading phases are the one-time setup cost.

Expected output: `Pipeline complete — Sharpe: X.XX, CAGR: X.X%` printed to console. If `--export-all` flag set: CSV files + JSON written to `--output-dir`.

---

## MVP Recommendation for v1.1 Phases

Suggested phase sequence based on dependency order:

1. **Infrastructure provisioning** — Docker Compose + `.env` files + Alembic migrations for both packages. No code changes, just configuration files. Unblocks everything else. Duration: 1-2 hours.

2. **Data population** — Run `universe refresh` + `data download` for backtest; run `universe scan` for Detector. These run in parallel (no dependency between backtest universe and Detector universe — different table ownership). Duration: 30-60 minutes.

3. **Detector pipeline first run** — Execute `daily_pipeline_flow` to populate `daily_scores`. This is the long pole: 4-10 hours for initial ingestion. Can run overnight. Duration: 4-10 hours (background).

4. **Backtest execution + tech debt fixes** — Run `backtest run --signal ai-washing`. Fix the three v1.0 tech debt items (tearsheet wiring, benchmark fetch, dashboard live mode) while Detector pipeline runs. Duration: 1-2 hours coding + run time.

5. **Dashboard live mode** — Wire `backtest run` output into the dashboard (replace `_load_demo_data()` with real DB queries + pass live `PortfolioResult`/`MetricsBundle`). Duration: 1-2 hours.

**Defer to v1.2:**
- Scheduled/automated pipeline runs (Prefect server setup)
- Production cloud deployment
- Second signal source

---

## Tech Debt from v1.0 That Must Be Fixed in v1.1

These are not new features — they are completion items from the v1.0 audit that only become
observable when real data flows through the system.

| Item | File | Fix Description | Complexity |
|------|------|-----------------|------------|
| INTG-01: Tearsheet missing from live run path | `backtest/src/fund_backtest/cli.py` | Add `TearsheetBuilder.build()` call in `run` command's `export_all` branch (5 lines) | Low |
| INTG-02: Dashboard sector chart hardcoded to demo data | `backtest/src/fund_backtest/dashboard/app.py` | Query `UniverseTicker.gics_sector` from DB when `DATABASE_URL` is set; fall back to demo sectors otherwise | Low |
| Phase 5/8: Benchmark returns absent from CLI path | `backtest/src/fund_backtest/cli.py` | Fetch SPY/IWM via yfinance in `run` command and pass to `MetricsEngine.compute(benchmark=...)` | Low |

All three fixes are < 20 lines of code each. They are not blocked by any new infrastructure.

---

## Sources

- Direct codebase inspection: `backtest/src/fund_backtest/cli.py`, `dashboard/app.py`, `signal/loaders/ai_washing.py`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md` — integration gaps INTG-01, INTG-02, Phase 5/8 tech debt
- `.planning/STATE.md` — known blockers and accumulated decisions
- `Al Washing Detector/src/ai_washer/pipeline/daily_flow.py` — Prefect flow structure and stage sequence
- `Al Washing Detector/CLAUDE.md` — Detector stack (Prefect, FinBERT, SEC EDGAR rate limits)
- `.planning/PROJECT.md` — v1.1 milestone target features
- Confidence: HIGH — all findings from direct code inspection, not estimation
