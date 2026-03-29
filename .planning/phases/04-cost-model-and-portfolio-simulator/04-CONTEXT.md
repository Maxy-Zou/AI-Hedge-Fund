# Phase 4: Cost Model and Portfolio Simulator - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

A fully vectorized portfolio simulator produces daily returns and a trade log from a WeightFrame, with realistic short borrow and transaction costs built in. Requirements: BT-02 (short positions), BT-03 (transaction costs), BT-04 (short borrow costs), BT-06 (equal-weight sizing), BT-07 (daily returns + trade log output).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

CRITICAL from Phase 3: WeightFrame already has shift(1) applied. The Portfolio Simulator must NOT apply an additional shift.

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered during plan-phase research.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — discuss phase skipped. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
