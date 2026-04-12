# Phase 6: Advanced Signals - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

The system detects suspicious timing clusters and win streak patterns, expanding anomaly coverage beyond Phase 3. This phase delivers two new signal detectors that integrate with the existing SignalEngine pipeline (confidence scoring, cooldown dedup, resolution suppression).

Success criterion 2 explicitly accepts "formally documented as infeasible" for win streak if the Kalshi API doesn't expose per-account trade history.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion. Key constraints:

- Timing cluster detector: detect trades bunched in narrow windows before resolution
- Win streak detector: attempt implementation; if Kalshi API doesn't expose per-account history, formally document infeasibility with evidence
- Both detectors must produce confidence scores in [0, 1] (SIG-05 pattern from Phase 3)
- Both must integrate with existing SignalEngine.run() pipeline
- Both must respect existing cooldown dedup and resolution suppression

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SignalEngine` in signals/engine.py — orchestrator to register new detectors
- `DetectionResult` frozen dataclass in signals/types.py
- `VolumeSpikeDetector` and `PriceMoveDetector` patterns in signals/detectors.py
- `MarketSnapshot` ORM model with timestamp and volume data
- `Signal` table for persistence
- Existing test patterns in tests/unit/signals/

### Integration Points
- Register new detectors in SignalEngine.run() alongside existing two
- Same confidence scoring and dedup pipeline
- Same DB persistence path

</code_context>

<specifics>
## Specific Ideas

No specific requirements. Follow the existing detector pattern from Phase 3.

</specifics>

<deferred>
## Deferred Ideas

None — this is the final phase.

</deferred>
