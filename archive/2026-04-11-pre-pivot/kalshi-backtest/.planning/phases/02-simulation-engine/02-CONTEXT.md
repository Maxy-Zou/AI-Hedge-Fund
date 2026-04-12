# Phase 2: Simulation Engine - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Any strategy implementing the Strategy Protocol can be replayed bar-by-bar against historical data with correct P&L, fees, and fill prices — and look-ahead bias is structurally impossible. This phase delivers the Strategy Protocol interface, bar-by-bar replay engine, exact Kalshi fee formula, conservative fill model, parameter grid sweep, and walk-forward validation.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints from research:
- Strategy Protocol (not ABC) — structural subtyping so strategies don't import engine internals
- `generate_signals()` is the plugin interface method
- Bar-by-bar replay: bulk-load candles upfront (vectorized), iterate chronologically per market per day (event-driven) to prevent lookahead
- MarketSnapshot must expose `result=None` for all bars before close_time — enforced by the BarIterator
- Exact Kalshi fee formula: `ceil(0.07 * C * P * (1-P))` where C=contracts, P=price in [0,1]
- Conservative fill: use ask price for buys, bid price for sells, minimum spread floor
- Binary P&L: hold-to-settlement ($0/$1) and pre-resolution exit (mark-to-market)
- Parameter grid sweep: test multiple strategy configs in a single run
- Walk-forward validation: rolling train/test splits

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- src/kalshi_backtest/db/repository.py — MarketRepository.get_markets(), get_candles() for querying historical data
- src/kalshi_backtest/ingestion/types.py — MarketRecord, CandlestickRecord frozen Pydantic models
- src/kalshi_backtest/config.py — KalshiBacktestSettings
- src/kalshi_backtest/db/schema.py — DuckDB connection factory

### Established Patterns
- Frozen Pydantic models for data contracts (MarketRecord, CandlestickRecord)
- DuckDB for all data queries
- structlog for logging
- Typer for CLI

### Integration Points
- Simulation engine reads from DuckDB via MarketRepository
- CLI will need `run` and `compare` commands (Phase 2 adds CLI-02: configurable lookback)
- Metrics layer (Phase 3) consumes daily returns Series + trade log DataFrame from simulator

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
