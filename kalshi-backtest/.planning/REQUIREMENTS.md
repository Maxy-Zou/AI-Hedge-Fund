# Requirements: Kalshi Backtesting Engine

**Defined:** 2026-04-04
**Core Value:** Accurately simulate any Kalshi trading strategy against historical data so you can validate signal quality and optimize parameters before risking real capital.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Data Ingestion

- [x] **DATA-01**: Ingest historical market and contract data from Kalshi API (all event categories)
- [x] **DATA-02**: Handle live/historical API tier split with runtime cutoff resolution
- [ ] **DATA-03**: Store contract snapshots in append-only DuckDB with lookahead-safe schema (settlement result physically separated from price observations)
- [x] **DATA-04**: Support incremental sync — only fetch new data on subsequent runs
- [x] **DATA-05**: Validate ingested data — gap detection, anomaly alerting, coverage reporting
- [x] **DATA-06**: All timestamps stored in UTC with Eastern Time conversion for Kalshi event times

### Simulation Engine

- [x] **SIM-01**: Strategy Protocol interface — implement `generate_signals()` to plug in any strategy
- [x] **SIM-02**: Bar-by-bar replay engine that prevents look-ahead bias (settlement result hidden until after close_time)
- [x] **SIM-03**: Exact Kalshi fee formula: `ceil(0.07 * C * P * (1-P))`
- [x] **SIM-04**: Conservative fill model with spread-aware execution
- [x] **SIM-05**: Binary P&L calculation — hold-to-settlement ($0/$1 payoff) and pre-resolution exit (mark-to-market)
- [x] **SIM-06**: Parameter grid sweep — test multiple strategy configurations in a single run
- [x] **SIM-07**: Walk-forward validation — rolling train/test splits to detect overfitting

### Metrics & Reporting

- [ ] **MET-01**: Core metrics — total return, Sharpe, Sortino, max drawdown, win rate, avg trade P&L, CAGR
- [ ] **MET-02**: Trade log — every entry/exit with timestamps, prices, contract details, fees paid
- [ ] **MET-03**: Equity curve visualization
- [ ] **MET-04**: Brier score — prediction calibration quality metric
- [ ] **MET-05**: Strategy comparison — run multiple strategies side-by-side with comparative metrics
- [ ] **MET-06**: Interactive Plotly dashboard with per-category performance breakdown
- [ ] **MET-07**: Sample size warnings — flag results with N<30 events as statistically unreliable

### Strategy Plugins

- [ ] **STRAT-01**: Insider Tracker adapter — consume signals from the Kalshi Insider Tracker as the first strategy plugin
- [ ] **STRAT-02**: Example/template strategy — demo plugin for onboarding future strategies

### CLI

- [x] **CLI-01**: CLI entry point for running backtests, data ingestion, and viewing results
- [x] **CLI-02**: Configurable lookback window per backtest run (default ~1 year)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Simulation

- **ASIM-01**: Market-making strategy support (bid/ask placement simulation)
- **ASIM-02**: L2 order book replay (if Kalshi exposes historical depth data)
- **ASIM-03**: Real-time streaming backtest mode (live paper trading)

### Advanced Reporting

- **AREP-01**: PDF tearsheet generation (investor-ready output)
- **AREP-02**: Multi-timeframe analysis (1m, 1h, 1d candle granularity)
- **AREP-03**: Regime analysis (pre/post liquidity shifts)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Equities/stock backtesting | Already handled by `backtest/` module |
| Live trading execution | Simulation only — no real order placement |
| Market-making strategies | Signal-based only for v1; fundamentally different problem domain |
| Real-time streaming | Batch historical analysis, not live feeds |
| Mobile/web deployment | CLI and local dashboard only |
| Third-party data providers | Kalshi API only for v1 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 1 | Complete |
| DATA-03 | Phase 1 | Pending |
| DATA-04 | Phase 1 | Complete |
| DATA-05 | Phase 1 | Complete |
| DATA-06 | Phase 1 | Complete |
| CLI-01 | Phase 1 | Complete |
| SIM-01 | Phase 2 | Complete |
| SIM-02 | Phase 2 | Complete |
| SIM-03 | Phase 2 | Complete |
| SIM-04 | Phase 2 | Complete |
| SIM-05 | Phase 2 | Complete |
| SIM-06 | Phase 2 | Complete |
| SIM-07 | Phase 2 | Complete |
| CLI-02 | Phase 2 | Complete |
| MET-01 | Phase 3 | Pending |
| MET-02 | Phase 3 | Pending |
| MET-03 | Phase 3 | Pending |
| MET-05 | Phase 3 | Pending |
| MET-06 | Phase 3 | Pending |
| MET-07 | Phase 3 | Pending |
| STRAT-01 | Phase 4 | Pending |
| STRAT-02 | Phase 4 | Pending |
| MET-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0

---
*Requirements defined: 2026-04-04*
*Last updated: 2026-04-04 after roadmap creation*
