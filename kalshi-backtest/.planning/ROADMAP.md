# Roadmap: Kalshi Backtesting Engine

## Overview

Four phases deliver a complete strategy-agnostic backtesting engine for Kalshi prediction markets. Phase 1 builds the data foundation with lookahead-safe schema and full ingestion pipeline — nothing else can be built correctly without it. Phase 2 builds the simulation engine core: the Strategy Protocol, bar-by-bar replay loop, exact fee formula, and conservative fill model. Phase 3 turns the simulation's fill stream into investor-useful output: performance metrics, trade logs, and an interactive dashboard. Phase 4 proves the engine end-to-end with the first real strategy consumer — the Insider Tracker adapter — and a template plugin for future strategies.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Data Foundation** - Ingest historical Kalshi contract data into a lookahead-safe, append-only DuckDB store (completed 2026-04-05)
- [ ] **Phase 2: Simulation Engine** - Bar-by-bar replay with Strategy Protocol, exact fee formula, and conservative fill model
- [ ] **Phase 3: Metrics and Reporting** - Turn the fill stream into performance metrics, trade logs, and an interactive dashboard
- [ ] **Phase 4: First Strategy Consumer** - Insider Tracker adapter and example template prove the Strategy Protocol end-to-end

## Phase Details

### Phase 1: Data Foundation
**Goal**: Historical Kalshi contract data is available locally in a lookahead-safe, append-only DuckDB store that the simulation engine can query safely
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, CLI-01
**Success Criteria** (what must be TRUE):
  1. Running `kalshi-backtest ingest` populates the local DuckDB database with at least 1 year of contract snapshots across all event categories
  2. Re-running `ingest` on already-ingested data produces no duplicate rows (append-only, idempotent)
  3. The database schema physically separates settlement results from price observations — the `result` column is never populated for bars before `close_time`
  4. A data validation report is printed after each ingestion run showing coverage, gap count, and any anomalies detected
  5. All stored timestamps are UTC; running the CLI on any machine produces identical data regardless of local timezone
**Plans**: 5 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffold, pyproject.toml, Wave 0 test stubs and fixture JSON files
- [x] 01-02-PLAN.md — DuckDB schema DDL, KalshiBacktestSettings config, Pydantic types, MarketRepository
- [x] 01-03-PLAN.md — Dual API clients (live SDK + historical httpx), CutoffResolver, fetchers
- [x] 01-04-PLAN.md — IngestionPipeline orchestrator, DataValidator with gap detection
- [x] 01-05-PLAN.md — CLI `ingest` command wiring all components; full phase test suite green

### Phase 2: Simulation Engine
**Goal**: Any strategy implementing the Strategy Protocol can be replayed bar-by-bar against historical data with correct P&L, fees, and fill prices — and look-ahead bias is structurally impossible
**Depends on**: Phase 1
**Requirements**: SIM-01, SIM-02, SIM-03, SIM-04, SIM-05, SIM-06, SIM-07, CLI-02
**Success Criteria** (what must be TRUE):
  1. A strategy implementing `generate_signals()` can be passed to the backtest runner and produces a complete fill log
  2. The bar iterator never exposes `result` to a strategy before the contract's `close_time` — verified by a unit test that asserts `MarketSnapshot.result is None` on all pre-close bars
  3. Fee calculations match the exact Kalshi formula `ceil(0.07 * C * P * (1-P))` — verified by unit tests against known contract sizes and prices
  4. Fills use ask price for buys and bid price for sells with a minimum spread floor applied — no midpoint fills
  5. Running `kalshi-backtest run --lookback 90d` executes a full backtest and prints a summary of trades and P&L
**Plans**: 5 plans

Plans:
- [x] 02-01-PLAN.md — Simulation type contracts: Strategy Protocol, Signal, Position, MarketSnapshot
- [ ] 02-02-PLAN.md — BarIterator (lookahead prevention) and FillEngine (fee formula, fill model, P&L)
- [ ] 02-03-PLAN.md — PositionTracker (open/close lifecycle) and BacktestRunner (full bar-by-bar loop)
- [ ] 02-04-PLAN.md — ParameterSweeper (grid sweep) and WalkForwardValidator (rolling splits)
- [ ] 02-05-PLAN.md — CLI `run` command with --lookback-days and --dry-run (CLI-02)

### Phase 3: Metrics and Reporting
**Goal**: After any backtest run, an investor-useful performance summary and interactive dashboard are generated automatically
**Depends on**: Phase 2
**Requirements**: MET-01, MET-02, MET-03, MET-05, MET-06, MET-07
**Success Criteria** (what must be TRUE):
  1. The backtest output includes total return, Sharpe, Sortino, max drawdown, win rate, avg trade P&L, and CAGR — all in dollar terms, not percentage-of-percentage distorted values
  2. A trade log file is written after each run listing every entry and exit with timestamp, prices, contract ticker, and fees paid
  3. An interactive `dashboard.html` opens in the browser showing an equity curve with trade markers and per-category performance breakdown
  4. Running two strategies through `kalshi-backtest compare` produces a side-by-side metrics table in the terminal
  5. Any backtest result with fewer than 30 settled contracts prints a visible warning flagging the result as statistically unreliable
**Plans**: TBD
**UI hint**: yes

### Phase 4: First Strategy Consumer
**Goal**: The Insider Tracker's signals drive a complete end-to-end backtest, proving the Strategy Protocol works with a real signal source, and a template plugin makes adding future strategies trivial
**Depends on**: Phase 3
**Requirements**: STRAT-01, STRAT-02, MET-04
**Success Criteria** (what must be TRUE):
  1. `InsiderTrackerAdapter` loads signals from the Kalshi Insider Tracker's output and runs a full backtest without any modifications to the engine
  2. The Brier score for the Insider Tracker strategy is computed and displayed alongside standard P&L metrics after each run
  3. A new strategy can be added to the project by copying the example template, implementing `generate_signals()`, and passing it to the runner — no other changes required
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Foundation | 6/6 | Complete    | 2026-04-05 |
| 2. Simulation Engine | 1/5 | In Progress|  |
| 3. Metrics and Reporting | 0/? | Not started | - |
| 4. First Strategy Consumer | 0/? | Not started | - |
