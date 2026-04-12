# Phase 4: First Strategy Consumer - Context

**Gathered:** 2026-04-06
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous discuss skipped)

<domain>
## Phase Boundary

The Insider Tracker's signals drive a complete end-to-end backtest, proving the Strategy Protocol works with a real signal source, and a template plugin makes adding future strategies trivial. This phase delivers the InsiderTrackerAdapter strategy, Brier score metric, and an example template strategy.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion. Key considerations:

- InsiderTrackerAdapter must implement the Strategy Protocol (generate_signals())
- It consumes signals from the Kalshi Insider Tracker's output — need to understand what that output looks like
- Brier score: measures calibration quality of probability predictions, computed alongside standard P&L metrics
- Example template: copy-and-implement pattern for future strategies
- The _PassThroughStrategy stub in cli.py should be replaced by a proper strategy selection mechanism

Reference: The Kalshi Insider Tracker lives at "../Kalshi Insider Tracker/" — check its output format for the adapter.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- simulation/protocol.py — Strategy Protocol with generate_signals()
- simulation/runner.py — BacktestRunner.run() returns BacktestResult
- metrics/calculator.py — MetricsCalculator.compute() returns BacktestMetrics
- cli.py — `run` and `compare` commands with _PassThroughStrategy stub

### Established Patterns
- Strategy Protocol uses structural subtyping (no inheritance needed)
- Signal model: Signal(ticker, direction, contracts, price_cents)
- BacktestResult feeds into MetricsCalculator and dashboard builder

### Integration Points
- InsiderTrackerAdapter reads Insider Tracker output (format TBD — check ../Kalshi Insider Tracker/)
- Brier score added to BacktestMetrics model and MetricsCalculator
- CLI --strategy flag selects which strategy to use
- Example template in strategies/ directory

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond ROADMAP success criteria.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>
