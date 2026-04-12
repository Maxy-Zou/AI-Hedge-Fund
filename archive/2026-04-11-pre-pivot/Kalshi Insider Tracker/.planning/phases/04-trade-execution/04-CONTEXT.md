# Phase 4: Trade Execution - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Detected signals result in copy trades, with a hard Risk Guard enforcing position limits before any order reaches the market. This phase delivers: paper trading mode, Risk Guard ($50/trade, $500 total as code constants), live order execution via Kalshi API, signal deduplication, and in-flight order tracking.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure phase. Key constraints:

- Risk Guard limits ($50/trade, $500 total) MUST be code-level constants, NOT config values — this is a critical safety constraint from research
- Paper trading mode is the default — live mode requires explicit opt-in
- Signal deduplication: prevent same signal from triggering duplicate orders across consecutive polls
- In-flight order tracking: prevent re-submission while a prior order is pending
- All trade data (placed, blocked, simulated) persists to the Trade table (append-only)
- Signal log (LOG-01): every signal detection event logged to DB
- Trade log (LOG-02): every trade placed/blocked/simulated logged to DB
- Use kalshi-python SDK for order placement (KalshiClient already built in Phase 1)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SignalEngine.run()` produces signals (Phase 3) — trade execution consumes these
- `Trade` ORM model with AppendOnlyMixin (Phase 1)
- `Signal` ORM model (Phase 1) — already written by SignalEngine
- `KalshiClient` with RSA auth and rate limiting (Phase 1)
- Database session factory (Phase 1)
- `AppSettings` / `KalshiSettings` (Phase 1)

### Integration Points
- SignalEngine produces signals → TradeExecutor consumes them
- Risk Guard gates all orders before they reach Kalshi API
- CLI command to toggle paper/live mode
- Future: Dashboard (Phase 5) reads trade data

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond what's in the roadmap. Follow the Risk Guard → Paper/Live executor pattern from research.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>
