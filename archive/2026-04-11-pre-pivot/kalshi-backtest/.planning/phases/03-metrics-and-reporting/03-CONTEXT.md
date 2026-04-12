# Phase 3: Metrics and Reporting - Context

**Gathered:** 2026-04-06
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous discuss skipped)

<domain>
## Phase Boundary

After any backtest run, an investor-useful performance summary and interactive dashboard are generated automatically. This phase delivers core metrics (Sharpe, Sortino, max drawdown, win rate, CAGR), trade log output, equity curve visualization, strategy comparison, interactive Plotly dashboard with per-category breakdown, and sample size warnings.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints:
- quantstats for standard tearsheet metrics (Sharpe, Sortino, Calmar, drawdown, CAGR)
- Plotly for interactive dashboard (equity curve, trade markers, per-category breakdown)
- Strategy comparison: side-by-side metrics table in terminal via Rich
- Sample size warnings: flag N<30 settled contracts as statistically unreliable
- Trade log: CSV/DataFrame with timestamp, prices, contract ticker, fees paid
- Dashboard output as interactive HTML file (dashboard.html)
- BacktestResult from Phase 2 is the input — daily returns Series + trade log DataFrame

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- simulation/runner.py — BacktestResult (daily_returns: pd.Series, trade_log: pd.DataFrame, positions: list)
- simulation/types.py — Position, Fill with all P&L fields
- simulation/position_tracker.py — PositionTracker.to_trade_log(), to_daily_pnl_series()
- cli.py — Typer app with `ingest` and `run` commands

### Established Patterns
- Rich for terminal output (already used in validator.py)
- Typer for CLI commands
- Frozen Pydantic models for data contracts
- structlog for logging

### Integration Points
- Metrics layer consumes BacktestResult from BacktestRunner.run()
- Dashboard writes dashboard.html to current directory or specified output path
- `compare` CLI command runs multiple strategies and shows side-by-side table
- Sample size warning integrated into metrics output

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond ROADMAP success criteria.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>
