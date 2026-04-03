# Phase 3: Core Signal Detection - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

The system detects volume spikes and sharp price movements and scores them with confidence values. This phase delivers two signal detectors (volume spike, price movement), a confidence scoring system, and a resolution-day false positive suppression filter. Signals are computed from MarketSnapshot data accumulated by the Phase 2 polling daemon.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and fund-wide conventions to guide decisions.

Key constraints from research:
- Volume spike detection: per-market rolling baseline with z-score threshold (configurable)
- Price movement detection: configurable % move relative to market's recent range
- Each signal produces a confidence score between 0.0 and 1.0
- Resolution-day suppression: suppress signals during the final resolution window to avoid false positives
- Signals are computed from MarketSnapshot rows in the database
- Signal results persist to the Signal table (append-only, from Phase 1)
- scipy for statistical computations (z-score, rolling stats)
- Integration with WarmupTracker: signals should only fire after warm-up is complete

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `MarketSnapshot` ORM model with price/volume fields (Phase 1)
- `Signal` ORM model with AppendOnlyMixin (Phase 1)
- `WarmupTracker` for warm-up state (Phase 2)
- `poll_tick()` factory — signals integrate into the polling loop
- Database session factory for reading snapshots and persisting signals

### Established Patterns
- Frozen dataclasses for domain contracts
- structlog with contextual binding
- Pydantic settings for configuration
- TDD: RED tests first, then GREEN implementation

### Integration Points
- Signal detectors consume MarketSnapshot rows from DB
- Signal results written to Signal table
- WarmupTracker gates signal detection (no signals during warm-up)
- Future: Phase 4 (Trade Execution) reads signals to trigger trades

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Follow the z-score approach for volume and percentage-move approach for price as described in research.

</specifics>

<deferred>
## Deferred Ideas

- Timing cluster detection (Phase 6)
- Win streak detection (Phase 6)
- Machine learning signal scoring (v2)

</deferred>
