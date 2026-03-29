# Roadmap: Shared Backtesting Infrastructure

## Overview

Eight phases take this module from a clean Python package to a fully integrated, investor-ready backtesting framework. The pipeline flows in strict dependency order: universe and price data must exist before the simulator can run, the simulator must produce a PortfolioResult before risk metrics can be computed, and risk metrics must exist before the reporting layer can render them. Integration with the AI Washing Detector is last — the contract must be stable before live data crosses module boundaries.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Universe and Sector Data** - Build and maintain the mid-cap ticker universe with GICS sector classification (completed 2026-03-28)
- [x] **Phase 2: Price Data Pipeline** - Download, cache, validate, and incrementally update daily OHLCV data for the full universe (completed 2026-03-29)
- [x] **Phase 3: Signal Adapter and Integration Contract** - Define the signal DataFrame contract and build the adapter that normalizes raw strategy scores into portfolio weights (completed 2026-03-29)
- [x] **Phase 4: Cost Model and Portfolio Simulator** - Implement fully vectorized long/short simulation with realistic transaction and borrow costs (completed 2026-03-29)
- [x] **Phase 5: Risk Metrics Engine** - Compute the full institutional metric suite (Sharpe, Sortino, drawdown, benchmarks, rolling windows) (completed 2026-03-29)
- [x] **Phase 6: Streamlit Dashboard** - Interactive investor-facing dashboard showing equity curves, drawdown, sector exposure, and monthly returns (completed 2026-03-29)
- [x] **Phase 7: Tearsheet and Data Exports** - PDF tearsheet, CSV/JSON exports, and explicit cost labeling on all outputs (completed 2026-03-29)
- [ ] **Phase 8: AI Washing Detector Integration** - Wire live AI Washing Risk Scores into the backtester and validate the end-to-end pipeline

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
- [ ] 08-01-PLAN.md — AiWashingLoader: signal/loaders/ package, raw SQL query, SignalLoadError, TDD unit tests (INT-02)
- [ ] 08-02-PLAN.md — CLI backtest run command + integration test against PostgreSQL testcontainer (INT-03)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Universe and Sector Data | 3/3 | Complete   | 2026-03-28 |
| 2. Price Data Pipeline | 4/4 | Complete   | 2026-03-29 |
| 3. Signal Adapter and Integration Contract | 2/2 | Complete   | 2026-03-29 |
| 4. Cost Model and Portfolio Simulator | 2/2 | Complete   | 2026-03-29 |
| 5. Risk Metrics Engine | 2/2 | Complete   | 2026-03-29 |
| 6. Streamlit Dashboard | 3/3 | Complete   | 2026-03-29 |
| 7. Tearsheet and Data Exports | 2/2 | Complete   | 2026-03-29 |
| 8. AI Washing Detector Integration | 0/2 | Not started | - |
