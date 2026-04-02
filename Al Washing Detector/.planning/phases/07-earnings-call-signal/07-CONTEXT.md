# Phase 7: Earnings Call Signal - Context

**Gathered:** 2026-03-29
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

The system produces vagueness scores for earnings calls by distinguishing buzzword-heavy AI claims from substantive technical discussion. Ingests earnings call transcripts for target companies using free sources with quarterly refresh tied to earnings calendar. A dual-lexicon scorer classifies vague AI claims ("AI-powered", "leveraging AI") vs substantive claims ("deployed transformer model", "trained on 100M parameters"). FinBERT sentiment analysis runs on earnings call segments. A vagueness score (0-100) combines buzzword density ratio with sentiment-vs-metrics mismatch.

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
