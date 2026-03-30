# Requirements: Shared Backtesting Infrastructure

**Defined:** 2026-03-28
**Core Value:** Produce compelling, realistic backtest results the moment any strategy signal is ready.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Market Data

- [x] **DATA-01**: System downloads daily OHLCV price data via yfinance for all tickers in the mid-cap universe
- [x] **DATA-02**: System caches price data in PostgreSQL to avoid redundant API calls
- [x] **DATA-03**: System performs incremental daily updates (append new bars, never overwrite historical)
- [x] **DATA-04**: System validates downloaded data (gap detection, daily return sanity check > +/-50%, missing ticker alerts)
- [x] **DATA-05**: System manages a universe of mid-cap tickers ($2B-$10B market cap) with refresh capability
- [x] **DATA-06**: System chunks yfinance downloads (~80 tickers/batch) with retry logic to handle rate limits
- [x] **DATA-07**: System stores GICS sector classification for each ticker (required for sector exposure reporting)

### Backtesting Engine

- [x] **BT-01**: Engine accepts a signal DataFrame (date x ticker -> score) and simulates a long/short portfolio
- [x] **BT-02**: Engine supports short positions as a first-class operation
- [x] **BT-03**: Engine models transaction costs (slippage + commission, configurable bps)
- [x] **BT-04**: Engine models short borrow costs (configurable flat rate, default 50bps/yr)
- [x] **BT-05**: Engine enforces look-ahead bias prevention (signal shifted by 1 day before execution)
- [x] **BT-06**: Engine uses equal-weight position sizing across all signal-selected tickers
- [x] **BT-07**: Engine produces a daily returns series and a trade log as output

### Risk Metrics

- [x] **RISK-01**: System computes Sharpe ratio, Sortino ratio, max drawdown, and Calmar ratio
- [x] **RISK-02**: System computes hit rate, win/loss ratio, and portfolio turnover
- [x] **RISK-03**: System compares strategy returns against S&P 500 and Russell 2000 benchmarks
- [x] **RISK-04**: System computes rolling Sharpe and rolling drawdown over configurable windows

### Reporting

- [x] **RPT-01**: Interactive Streamlit dashboard displays equity curve and drawdown chart
- [x] **RPT-02**: Dashboard displays monthly returns heatmap (calendar table)
- [x] **RPT-03**: Dashboard displays sector exposure breakdown
- [x] **RPT-04**: PDF tearsheet generates a single-page fund factsheet with key metrics and charts
- [x] **RPT-05**: System exports daily returns, positions, and trade log as CSV and JSON
- [x] **RPT-06**: All outputs label cost assumptions (slippage, borrow rate, commission) explicitly

### Integration

- [x] **INT-01**: Well-defined signal contract (DataFrame schema) that any strategy module can conform to
- [x] **INT-02**: AI Washing Detector scores can be loaded and converted to the signal contract format
- [x] **INT-03**: End-to-end pipeline runs from signal input to dashboard output without manual steps

## v1.1 Requirements

Requirements for live end-to-end pipeline. Each maps to roadmap phases 9+.

### Infrastructure

- [x] **INFRA-01**: PostgreSQL 16 runs locally via Docker Compose with a named volume for data persistence
- [x] **INFRA-02**: A shared `.env` convention configures both packages (`ai_washer` and `fund_backtest`) to connect to the same database
- [x] **INFRA-03**: Alembic `version_table` is unique per package so both migration chains run without collision
- [ ] **INFRA-04**: Both Alembic migration chains run successfully against the Docker PostgreSQL instance

### Data Population

- [ ] **POP-01**: Running `fund-backtest universe refresh` populates the universe_tickers table with real mid-cap tickers
- [ ] **POP-02**: Running `fund-backtest data download` populates price_bars with 5 years of real OHLCV data for all universe tickers
- [ ] **POP-03**: Running `fund-backtest data coverage` confirms ≥95% ticker coverage after download
- [ ] **POP-04**: Ticker overlap between `ai_washer` companies and `fund_backtest` universe is verified and sufficient for backtesting

### Detector Execution

- [ ] **DET-01**: Running `ai-washer universe scan` populates the companies table with real mid-cap entities from SEC EDGAR
- [ ] **DET-02**: Running the AI Washing Detector pipeline produces real `daily_scores` rows in PostgreSQL from SEC filing analysis
- [ ] **DET-03**: The pipeline completes without manual intervention and logs progress via structlog

### Bug Fixes & Wiring

- [x] **FIX-01**: Alembic `env.py` in both packages sets a distinct `version_table` to prevent migration collisions
- [ ] **FIX-02**: `backtest run` intersects signal and price date indices before calling the simulator (no silent 0% returns)
- [ ] **FIX-03**: `backtest export` uses real backtest results instead of `make_demo_result()` demo stubs
- [ ] **FIX-04**: Dashboard renders real backtest data instead of hardcoded demo data when results are available
- [ ] **FIX-05**: Benchmark alpha/beta values are correctly computed and included in CLI exports

### Live Backtest

- [ ] **LIVE-01**: Running `fund-backtest backtest run --signal ai-washing` produces a PortfolioResult and MetricsBundle from real data
- [ ] **LIVE-02**: The Streamlit dashboard displays actual equity curves, drawdown, monthly returns, and sector exposure from the real backtest
- [ ] **LIVE-03**: PDF tearsheet and CSV/JSON exports contain real backtest metrics with correct cost assumption labels

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Data

- **DATA-08**: Historical universe snapshots with as_of_date for full survivorship bias correction
- **DATA-09**: Corporate actions handling beyond yfinance auto_adjust
- **DATA-10**: Alternative data provider support (Polygon, EODHD) for coverage gaps

### Advanced Engine

- **BT-08**: Score-proportional position sizing (higher conviction = larger position)
- **BT-09**: Risk parity position sizing
- **BT-10**: ADV-based position caps (limit position size by average daily volume)
- **BT-11**: Signal quantile analysis (information coefficient, turnover by quintile)
- **BT-12**: Out-of-sample vs in-sample split with separate metrics

### Advanced Reporting

- **RPT-07**: HTML export from Streamlit dashboard
- **RPT-08**: Walk-forward optimization visualization
- **RPT-09**: Drawdown attribution (which positions drove drawdowns)

### Advanced Risk

- **RISK-05**: Sub-period breakdown (annual returns, crisis period performance)
- **RISK-06**: Tail risk metrics (VaR, CVaR)
- **RISK-07**: Correlation analysis with common factors (market, size, value, momentum)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Event-driven / tick-level backtesting | Daily signal cadence doesn't need tick simulation; adds massive complexity |
| Live trading execution | This is backtesting only, not an execution system |
| Intraday data | Daily granularity matches the fund's signal frequency |
| Paid data providers | yfinance sufficient for v1; upgrade path documented |
| Jupyter notebook output | Dashboard + tearsheet cover investor needs |
| Real-time borrow rate data | Flat rate assumption sufficient for v1; IBKR API integration deferred |
| Dividend liability modeling | yfinance auto_adjust handles most cases; edge cases documented as known limitation |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 2 | Complete |
| DATA-02 | Phase 2 | Complete |
| DATA-03 | Phase 2 | Complete |
| DATA-04 | Phase 2 | Complete |
| DATA-05 | Phase 1 | Complete |
| DATA-06 | Phase 2 | Complete |
| DATA-07 | Phase 1 | Complete |
| BT-01 | Phase 3 | Complete |
| BT-02 | Phase 4 | Complete |
| BT-03 | Phase 4 | Complete |
| BT-04 | Phase 4 | Complete |
| BT-05 | Phase 3 | Complete |
| BT-06 | Phase 4 | Complete |
| BT-07 | Phase 4 | Complete |
| RISK-01 | Phase 5 | Complete |
| RISK-02 | Phase 5 | Complete |
| RISK-03 | Phase 5 | Complete |
| RISK-04 | Phase 5 | Complete |
| RPT-01 | Phase 6 | Complete |
| RPT-02 | Phase 6 | Complete |
| RPT-03 | Phase 6 | Complete |
| RPT-04 | Phase 7 | Complete |
| RPT-05 | Phase 7 | Complete |
| RPT-06 | Phase 7 | Complete |
| INT-01 | Phase 3 | Complete |
| INT-02 | Phase 8 | Complete |
| INT-03 | Phase 8 | Complete |
| INFRA-01 | Phase 9 | Complete |
| INFRA-02 | Phase 9 | Complete |
| INFRA-03 | Phase 9 | Complete |
| INFRA-04 | Phase 9 | Pending |
| FIX-01 | Phase 9 | Complete |
| POP-01 | Phase 10 | Pending |
| POP-02 | Phase 10 | Pending |
| POP-03 | Phase 10 | Pending |
| POP-04 | Phase 10 | Pending |
| DET-01 | Phase 11 | Pending |
| DET-02 | Phase 11 | Pending |
| DET-03 | Phase 11 | Pending |
| FIX-02 | Phase 12 | Pending |
| FIX-03 | Phase 12 | Pending |
| FIX-04 | Phase 12 | Pending |
| FIX-05 | Phase 12 | Pending |
| LIVE-01 | Phase 13 | Pending |
| LIVE-02 | Phase 13 | Pending |
| LIVE-03 | Phase 13 | Pending |

**v1 Coverage:**
- v1 requirements: 27 total
- Mapped to phases: 27
- Unmapped: 0

**v1.1 Coverage:**
- v1.1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-03-28*
*Last updated: 2026-03-29 — v1.1 traceability complete (phases 9-13)*
