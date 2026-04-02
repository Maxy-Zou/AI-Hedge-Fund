# Phase 5: Patent Signal - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

The system produces patent gap scores by comparing a company's AI patent filings against its AI claim intensity. Queries the new PatentSearch API at data.uspto.gov for AI-related patents (CPC codes G06N, G06F18) by company, maps patent assignee names to the entity resolution table, and produces a 0-100 patent gap score reflecting divergence between AI claim intensity and actual patent filing trend. Supports incremental collection (weekly refresh without re-fetching stored patents).

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
