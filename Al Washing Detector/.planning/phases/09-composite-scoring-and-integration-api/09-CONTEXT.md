# Phase 9: Composite Scoring and Integration API - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

All six signals combine into a single composite AI Washing Risk Score with configurable weights, graceful degradation, and a clean Python API for downstream modules. The composite score (0-100) is a weighted average of all 6 sub-scores with configurable weights (default: Jobs 25%, SEC 20%, Earnings 20%, Patents 15%, GitHub 10%, Compute 10%). When one or more data sources are unavailable, the system produces a partial score with re-normalized weights and attaches a reduced confidence indicator. Score interpretation thresholds classify companies into risk bands. All scores are immutable — each daily run produces new snapshot rows.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion -- discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered during plan-phase research.

</code_context>

<specifics>
## Specific Ideas

No specific requirements -- discuss phase skipped. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None -- discuss phase skipped.

</deferred>
