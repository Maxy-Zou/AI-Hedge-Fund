# Roadmap: Shared Backtesting Infrastructure

## Overview

Eight phases built the full backtesting framework (v1.0). Five phases commission it with real data (v1.1). The v1.1 pipeline flows in strict operational order: infrastructure must exist before data can land, data must populate before the Detector can run, the Detector produces scores that unlock the live backtest, and bug fixes are wired in while the long-running Detector executes so nothing blocks Phase 13.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

### v1.0 History (Completed 2026-03-29)

- [x] **Phase 1: Universe and Sector Data** - Build and maintain the mid-cap ticker universe with GICS sector classification (completed 2026-03-28)
- [x] **Phase 2: Price Data Pipeline** - Download, cache, validate, and incrementally update daily OHLCV data for the full universe (completed 2026-03-29)
- [x] **Phase 3: Signal Adapter and Integration Contract** - Define the signal DataFrame contract and build the adapter that normalizes raw strategy scores into portfolio weights (completed 2026-03-29)
- [x] **Phase 4: Cost Model and Portfolio Simulator** - Implement fully vectorized long/short simulation with realistic transaction and borrow costs (completed 2026-03-29)
- [x] **Phase 5: Risk Metrics Engine** - Compute the full institutional metric suite (Sharpe, Sortino, drawdown, benchmarks, rolling windows) (completed 2026-03-29)
- [x] **Phase 6: Streamlit Dashboard** - Interactive investor-facing dashboard showing equity curves, drawdown, sector exposure, and monthly returns (completed 2026-03-29)
- [x] **Phase 7: Tearsheet and Data Exports** - PDF tearsheet, CSV/JSON exports, and explicit cost labeling on all outputs (completed 2026-03-29)
- [x] **Phase 8: AI Washing Detector Integration** - Wire live AI Washing Risk Scores into the backtester and validate the end-to-end pipeline (completed 2026-03-29)

### v1.1 Active

- [x] **Phase 9: Infrastructure and Database Setup** - Docker Compose PostgreSQL instance running, shared .env convention established, and both Alembic migration chains applied without collision (completed 2026-03-30)
- [ ] **Phase 10: Data Population** - Real mid-cap universe and 5 years of price data land in PostgreSQL; ticker overlap between the two packages is verified as sufficient for backtesting
- [ ] **Phase 11: Detector Execution** - AI Washing Detector runs end-to-end against real SEC filings and writes daily_scores rows to the shared database
- [ ] **Phase 12: Bug Fixes and Wiring** - Signal-price alignment, export stubs, dashboard demo data, and benchmark computation are all corrected before the live backtest
- [ ] **Phase 13: Live Backtest and Dashboard** - Full pipeline executes with real data; dashboard and tearsheet display actual AI Washing backtest results

## Phase Details

### Phase 1: Universe and Sector Data
**Goal**: A queryable, refreshable mid-cap ticker universe with GICS sector classification is available for all downstream phases
**Depends on**: Nothing (first phase)
**Requirements**: DATA-05, DATA-07
**Success Criteria** (what must be TRUE):
  1. Running `universe refresh` produces a list of tickers whose current market cap falls between $2B and $10B
  2. Each ticker in the universe has a GICS sector stored in PostgreSQL, fetched from yfinance and cached on first access
  3. Running `universe refresh` again appends new entrants and marks delisted tickers without deleting historical snapshots
  4. A CLI command displays the current universe size and sector breakdown
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Package scaffold: fund-backtest package, config, ORM models, Alembic migration, test structure
- [x] 01-02-PLAN.md — Universe domain logic: types, seeder (Wikipedia S&P 400), enricher (yfinance), UniverseBuilder with unit tests
- [x] 01-03-PLAN.md — CLI commands (`universe refresh`, `universe status`) and integration tests with PostgreSQL testcontainer

### Phase 2: Price Data Pipeline
**Goal**: Daily OHLCV price data for all universe tickers is cached in PostgreSQL, validated, and incrementally updated without overwriting historical bars
**Depends on**: Phase 1
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-06
**Success Criteria** (what must be TRUE):
  1. Running `data download` for a fresh universe populates PostgreSQL with 5 years of daily OHLCV bars for all tickers
  2. Running `data update` the next day appends only the new trading day's bars — no historical rows are modified
  3. Any ticker with a single-day return exceeding ±50% is flagged in the log and excluded from downstream use until manually reviewed
  4. A coverage report shows how many of the requested tickers returned valid data; the pipeline alerts if coverage falls below 95%
  5. Downloads are chunked (~80 tickers per batch) with exponential backoff — no 429 errors cause a silent data gap
**Plans**: 4 plans

Plans:
- [x] 02-01-PLAN.md — ORM models (PriceBarORM, PriceAnomalyORM), Alembic migration 002, price/types.py (PriceBar, PriceAnomalyRecord, DownloadSummary, CoverageReport), PriceSettings config, unit tests for cents conversion
- [x] 02-02-PLAN.md — price/downloader.py (chunked download, tenacity retry on YFRateLimitError) + price/validator.py (anomaly detection, gap detection, coverage) with unit tests
- [x] 02-03-PLAN.md — price/repository.py (PriceBarRepository: insert_bars ON CONFLICT DO NOTHING, get_last_dates, get_bars with per-bar anomaly exclusion) + price/builder.py (PriceBuilder: download and update orchestration)
- [x] 02-04-PLAN.md — CLI data subgroup (download, update, coverage commands) + integration tests against PostgreSQL testcontainer

### Phase 3: Signal Adapter and Integration Contract
**Goal**: A typed, validated signal contract exists that any strategy module can conform to, and a Signal Adapter normalizes raw 0-100 scores into portfolio-ready weights
**Depends on**: Phase 1
**Requirements**: BT-01, BT-05, INT-01
**Success Criteria** (what must be TRUE):
  1. A SignalFrame schema is documented: rows = dates, columns = tickers, values = float scores with an `available_date` index that is always strictly after the `filing_date`
  2. Passing a signal DataFrame through the Signal Adapter produces a WeightFrame where all values are in [-1, +1] and rows with insufficient history are dropped
  3. A unit test verifies that a signal spike on date T produces zero weight on date T and nonzero weight on date T+1 (look-ahead bias guard)
  4. Invalid signal inputs (wrong columns, future-dated index, NaN-only rows) raise a descriptive validation error, not a silent failure
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md — Signal contracts (signal/types.py, signal/validator.py, SignalAdapterConfig in config.py) with TDD test scaffold (test_signal_types.py)
- [x] 03-02-PLAN.md — SignalAdapter implementation (signal/adapter.py) with TDD tests (test_signal_adapter.py) covering normalization, look-ahead bias guard, and mutation safety

### Phase 4: Cost Model and Portfolio Simulator
**Goal**: A fully vectorized portfolio simulator produces daily returns and a trade log from a WeightFrame, with realistic short borrow and transaction costs built in
**Depends on**: Phase 2, Phase 3
**Requirements**: BT-02, BT-03, BT-04, BT-06, BT-07
**Success Criteria** (what must be TRUE):
  1. The simulator accepts a WeightFrame and produces a `PortfolioResult` containing a daily returns Series and a trade log DataFrame
  2. Short positions appear in the trade log with borrow cost deducted at the configured annual rate (default 50 bps/yr)
  3. Each trade in the log shows slippage and commission charges at the configured basis points — gross and net returns are reported separately
  4. Running the simulator on synthetic data where all positions are fully known produces returns that match a hand-calculated reference to within floating-point tolerance
  5. All cost parameters (slippage, commission, borrow rate) live in a frozen `CostConfig` object — no hardcoded values exist in the simulator
**Plans**: 2 plans

Plans:
- [x] 04-01-PLAN.md — Type contracts (CostConfig, PortfolioResult) and TDD scaffolds (RED state)
- [x] 04-02-PLAN.md — PortfolioSimulator engine implementation (GREEN phase)

### Phase 5: Risk Metrics Engine
**Goal**: A MetricsBundle containing the full institutional metric suite can be computed from any PortfolioResult, including benchmark comparison and rolling statistics
**Depends on**: Phase 4
**Requirements**: RISK-01, RISK-02, RISK-03, RISK-04
**Success Criteria** (what must be TRUE):
  1. Given a `PortfolioResult.returns` Series, the engine produces Sharpe, Sortino, Calmar, max drawdown, CAGR, hit rate, win/loss ratio, and portfolio turnover
  2. Benchmark comparison runs against SPY and Russell 2000; alpha and beta are included in the MetricsBundle
  3. Rolling Sharpe and rolling drawdown are available at configurable window sizes (default 252 trading days)
  4. All metrics can be computed from synthetic test data without any database or network access
**Plans**: 2 plans

Plans:
- [x] 05-01-PLAN.md — Type contracts (MetricsConfig, MetricsBundle) and TDD scaffolds (RED state)
- [x] 05-02-PLAN.md — MetricsEngine implementation (GREEN phase)

### Phase 6: Streamlit Dashboard
**Goal**: An interactive investor-facing dashboard renders the full backtest story — equity curve, drawdown, monthly returns, and sector exposure — from a completed MetricsBundle and PortfolioResult
**Depends on**: Phase 5
**Requirements**: RPT-01, RPT-02, RPT-03
**Success Criteria** (what must be TRUE):
  1. Opening the dashboard in a browser shows an equity curve with benchmark overlays (SPY and Russell 2000) covering the full backtest period
  2. A drawdown chart beneath the equity curve shows underwater periods visually; each major drawdown episode is labelled with its depth and duration
  3. A monthly returns heatmap renders the full calendar with each month cell colour-coded red/green by return magnitude
  4. A sector exposure chart shows the portfolio's allocation breakdown by GICS sector, updated by the currently displayed backtest run
**Plans**: 3 plans
**UI hint**: yes

Plans:
- [x] 06-01-PLAN.md — Scaffold: add streamlit+plotly deps, dashboard/ package, charts.py stubs, demo_data.py, RED test file
- [x] 06-02-PLAN.md — Implement charts.py: build_equity_drawdown_chart, build_monthly_heatmap, build_sector_exposure_chart (GREEN)
- [x] 06-03-PLAN.md — app.py Streamlit entry point: KPI row, tabs layout, benchmark fetch, demo mode, checkpoint verification

### Phase 7: Tearsheet and Data Exports
**Goal**: A single-page PDF tearsheet and machine-readable CSV/JSON exports are generated from any backtest run, with all cost assumptions explicitly labelled
**Depends on**: Phase 5, Phase 6
**Requirements**: RPT-04, RPT-05, RPT-06
**Success Criteria** (what must be TRUE):
  1. Running `backtest export --tearsheet` produces a PDF file containing the equity curve, core metrics table, drawdown chart, and monthly returns heatmap on a single page
  2. Running `backtest export --csv` produces three files: `daily_returns.csv`, `positions.csv`, and `trade_log.csv`, with dates in ISO 8601 format
  3. Running `backtest export --json` produces a metrics JSON file consumable by downstream portfolio management modules
  4. Every generated output (PDF, CSV, JSON) includes a header or annotation stating the slippage, commission, and borrow rate assumptions used in that run
**Plans**: 2 plans

Plans:
- [x] 07-01-PLAN.md — reports/ module: TearsheetBuilder (matplotlib PDF) and ExportBuilder (CSV/JSON) with TDD tests
- [x] 07-02-PLAN.md — CLI wiring: backtest export subgroup (--tearsheet, --csv, --json, --all) + CLI tests

### Phase 8: AI Washing Detector Integration
**Goal**: Live AI Washing Risk Scores from the Detector's PostgreSQL output can be loaded, adapted to the SignalFrame contract, and run through the full backtesting pipeline without manual steps
**Depends on**: Phase 7
**Requirements**: INT-02, INT-03
**Success Criteria** (what must be TRUE):
  1. Running `backtest run --signal ai-washing` loads DailyScore records from the shared PostgreSQL database and converts them to a valid SignalFrame with correct `available_date` offsets
  2. The end-to-end pipeline — from signal load through simulation, metrics computation, and dashboard render — completes without any manual intervention
  3. The pipeline exits with a non-zero status code and a descriptive error message if the Detector's scores table is empty or unavailable, rather than producing a silent empty backtest
**Plans**: 2 plans

Plans:
- [x] 08-01-PLAN.md — AiWashingLoader: signal/loaders/ package, raw SQL query, SignalLoadError, TDD unit tests (INT-02)
- [x] 08-02-PLAN.md — CLI backtest run command + integration test against PostgreSQL testcontainer (INT-03)

### Phase 9: Infrastructure and Database Setup
**Goal**: A running PostgreSQL 16 instance is reachable by both packages via a shared .env convention, and both Alembic migration chains apply cleanly without version table collision
**Depends on**: Phase 8
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, FIX-01
**Success Criteria** (what must be TRUE):
  1. Running `docker compose up -d` starts a PostgreSQL 16 container with a named volume; the container survives `docker compose restart` with data intact
  2. A single `.env` file at the repo root (or package level) configures `DATABASE_URL`, `AI_WASHER_DATABASE_URL`, and `FUND_BACKTEST_DATABASE_URL` to the same connection string — both CLI tools connect without additional setup
  3. Running `alembic upgrade head` in both package directories completes without error and without either chain overwriting the other's version row
  4. Both packages' `env.py` files declare a distinct `version_table` name so migration state is tracked independently
**Plans**: TBD

### Phase 10: Data Population
**Goal**: Real mid-cap universe tickers and five years of OHLCV price data are loaded into PostgreSQL, and the ticker overlap between the Detector's company universe and the backtester's price universe is confirmed as sufficient for a live backtest
**Depends on**: Phase 9
**Requirements**: POP-01, POP-02, POP-03, POP-04
**Success Criteria** (what must be TRUE):
  1. Running `fund-backtest universe refresh` completes and the `universe_tickers` table contains real mid-cap tickers from the S&P 400 list
  2. Running `fund-backtest data download` completes and `price_bars` contains at least 5 years of daily OHLCV bars; the coverage report confirms 95%+ ticker coverage
  3. Running `ai-washer universe scan` completes and the `companies` table contains real mid-cap entities sourced from SEC EDGAR
  4. A manual or scripted overlap check confirms that enough tickers appear in both universes to meet `SignalAdapter.min_coverage=5`, making a live backtest viable
**Plans**: TBD

### Phase 11: Detector Execution
**Goal**: The AI Washing Detector runs its full filing analysis pipeline against real SEC EDGAR data and writes daily AI Washing Risk Scores into the shared PostgreSQL database, completing without manual intervention
**Depends on**: Phase 10
**Requirements**: DET-01, DET-02, DET-03
**Success Criteria** (what must be TRUE):
  1. Running the Detector's score-generation pipeline against the populated `companies` table produces rows in `daily_scores` for at least the companies with ticker overlap
  2. The pipeline runs to completion without manual restarts; structlog output shows per-company progress and a final summary row count
  3. The `daily_scores` table contains entries spanning at least 12 months, confirming sufficient signal history for a meaningful backtest
**Plans**: TBD

### Phase 12: Bug Fixes and Wiring
**Goal**: The four known bugs blocking a clean live run are corrected: signal-price date alignment, export demo stubs, dashboard hardcoded data, and benchmark alpha/beta computation
**Depends on**: Phase 9 (can run concurrently with Phase 11)
**Requirements**: FIX-02, FIX-03, FIX-04, FIX-05
**Success Criteria** (what must be TRUE):
  1. Running `backtest run --signal ai-washing` with misaligned signal and price date ranges produces correctly aligned returns — no silent 0% return rows from unmatched dates
  2. Running `backtest export --csv` and `backtest export --tearsheet` uses actual `PortfolioResult` data from the last run, not the `make_demo_result()` stub
  3. Opening the Streamlit dashboard when a real backtest result is available shows real equity curve and sector data — the demo data fallback only activates when no result exists
  4. Alpha and beta values in CLI export JSON are non-zero when benchmark data is available and are numerically consistent with the MetricsBundle values
**Plans**: TBD
**UI hint**: yes

### Phase 13: Live Backtest and Dashboard
**Goal**: The full end-to-end pipeline executes with real AI Washing scores and real price data, producing a PortfolioResult and MetricsBundle that the dashboard and tearsheet render as actual investment results
**Depends on**: Phase 11, Phase 12
**Requirements**: LIVE-01, LIVE-02, LIVE-03
**Success Criteria** (what must be TRUE):
  1. Running `fund-backtest backtest run --signal ai-washing` completes and prints a non-empty MetricsBundle with real Sharpe, drawdown, and CAGR values sourced from actual SEC filing scores
  2. Opening the Streamlit dashboard shows a real equity curve with benchmark overlays, a non-trivial drawdown chart, a populated monthly heatmap, and a sector exposure breakdown — none of the panels display demo or placeholder data
  3. Running `backtest export --all` produces a PDF tearsheet, three CSV files, and a JSON metrics file where every output header identifies the actual slippage, commission, and borrow rate used in the run
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
v1.0: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 (complete)
v1.1: 9 → 10 → 11 → 12 (parallel with 11) → 13

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Universe and Sector Data | 3/3 | Complete | 2026-03-28 |
| 2. Price Data Pipeline | 4/4 | Complete | 2026-03-29 |
| 3. Signal Adapter and Integration Contract | 2/2 | Complete | 2026-03-29 |
| 4. Cost Model and Portfolio Simulator | 2/2 | Complete | 2026-03-29 |
| 5. Risk Metrics Engine | 2/2 | Complete | 2026-03-29 |
| 6. Streamlit Dashboard | 3/3 | Complete | 2026-03-29 |
| 7. Tearsheet and Data Exports | 2/2 | Complete | 2026-03-29 |
| 8. AI Washing Detector Integration | 2/2 | Complete | 2026-03-29 |
| 9. Infrastructure and Database Setup | 2/2 | Complete   | 2026-03-30 |
| 10. Data Population | 0/TBD | Not started | - |
| 11. Detector Execution | 0/TBD | Not started | - |
| 12. Bug Fixes and Wiring | 0/TBD | Not started | - |
| 13. Live Backtest and Dashboard | 0/TBD | Not started | - |
