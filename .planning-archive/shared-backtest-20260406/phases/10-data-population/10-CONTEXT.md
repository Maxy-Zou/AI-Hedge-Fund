# Phase 10: Data Population - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning
**Mode:** Auto-generated (operational phase — discuss skipped)

<domain>
## Phase Boundary

Real mid-cap universe tickers loaded into PostgreSQL, 5 years of OHLCV price data downloaded from yfinance, and ticker overlap between the two packages verified as sufficient for backtesting.

</domain>

<decisions>
## Implementation Decisions

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

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backtest/src/fund_backtest/universe/builder.py` — `UniverseBuilder` seeds from Wikipedia S&P 400
- `backtest/src/fund_backtest/price/builder.py` — `PriceBuilder` orchestrates chunked yfinance download
- `backtest/src/fund_backtest/cli.py` — Typer CLI with `universe refresh`, `data download`, `data coverage` commands
- `Al Washing Detector/src/ai_washer/cli.py` — Typer CLI with `universe scan` command

### Integration Points
- Shared PostgreSQL database `ai_hedge_fund`
- Both packages write to different tables (universe_tickers vs companies)
- Ticker overlap query: JOIN fund_backtest.universe_tickers ON ai_washer.companies.ticker

</code_context>
