# Phase 1: Data Foundation - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Historical Kalshi contract data is available locally in a lookahead-safe, append-only DuckDB store that the simulation engine can query safely. This phase delivers the data ingestion pipeline, DuckDB schema with physical separation of settlement results from price observations, incremental sync, data validation, and the CLI scaffold.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints from research:
- Kalshi has a live/historical API tier split enforced by a rolling cutoff timestamp from `GET /historical/cutoff`
- Use `kalshi-python` SDK with `httpx` fallback for historical endpoints not covered by SDK
- DuckDB for storage (columnar OLAP, no server required, append-only enforced at application layer)
- Settlement `result` column must be physically separated or NULL-enforced for bars before `close_time`
- All timestamps UTC with Eastern Time awareness for Kalshi event times
- Fee formula `ceil(0.07 * C * P * (1-P))` is probability-weighted — store raw price data to enable accurate fee calculation downstream

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- No existing code in kalshi-backtest/ yet — greenfield phase

### Established Patterns
- Fund convention: append-only data, immutable financial records
- Existing backtest/ module uses SQLAlchemy + PostgreSQL — this module uses DuckDB instead (different data model)
- Kalshi Insider Tracker exists at ../Kalshi Insider Tracker/ — potential reference for Kalshi API patterns

### Integration Points
- CLI entry point will be the foundation for all future phases
- DuckDB schema must support queries from the simulation engine (Phase 2)
- Data validation output feeds into metrics/reporting (Phase 3)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
