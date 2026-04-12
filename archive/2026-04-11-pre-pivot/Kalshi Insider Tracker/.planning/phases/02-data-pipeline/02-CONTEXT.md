# Phase 2: Data Pipeline - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

The system continuously collects live market snapshots and accumulates baseline data before any signals can fire. This phase delivers the polling daemon (APScheduler with IntervalTrigger), snapshot persistence to PostgreSQL, and warm-up period enforcement.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and fund-wide conventions to guide decisions.

Key constraints from research:
- APScheduler with IntervalTrigger(seconds=10) for the polling loop — NOT Prefect or cron
- Each poll: call KalshiClient.get_politics_markets() → persist MarketSnapshot rows to DB
- Warm-up period: collect N snapshots per market before allowing signals (configurable threshold)
- Rate limiter already built into KalshiClient (Phase 1) — poller must respect it
- Single-process synchronous daemon — no async, no message queues for v1
- Append-only MarketSnapshot persistence (Phase 1 ORM models already enforce this)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `KalshiClient.get_politics_markets()` → returns `list[MarketSnapshot]` (from Phase 1)
- `MarketSnapshot` ORM model with AppendOnlyMixin (from Phase 1)
- `get_session_factory()` and `create_engine_from_settings()` (from Phase 1)
- `AppSettings` and `KalshiSettings` with Pydantic validation (from Phase 1)
- structlog already configured

### Established Patterns
- Typer CLI at `src/kalshi_tracker/cli.py` — add `poll` or `daemon` command
- Config via Pydantic settings with env vars
- Token bucket rate limiter in KalshiClient

### Integration Points
- CLI command to start/stop the polling daemon
- Database session for persisting snapshots
- KalshiClient for fetching market data
- Future: Signal engine (Phase 3) will read from accumulated snapshots

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. The daemon should be runnable via CLI command (e.g., `kalshi-tracker poll start`).

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase stayed within scope.

</deferred>
