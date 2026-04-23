# Phase 6: Risk Management - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

A Risk Manager agent enforces hard portfolio constraints that cannot be overridden by research agents -- so no signal reaches the human reviewer without passing quantitative risk checks.

**Requirements:** RISK-01, RISK-02, RISK-03

**Success Criteria:**
1. The Risk Manager can veto a high-conviction recommendation and the veto is final -- the pipeline produces a "blocked by risk" output with the specific constraint violated, not a modified recommendation.
2. Position sizing constraints are enforced as hard limits: a signal suggesting >X% allocation to a single position is rejected (not silently capped), and the rejection reason references the specific limit.
3. Portfolio-level checks run against the current portfolio state: sector concentration exceeding threshold, correlation above threshold with existing positions, or projected max drawdown breaching limits each trigger a named constraint violation.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Grounding guardrails (project-wide):
- Risk checks must be deterministic tool calls — LLMs never compute position sizes, drawdowns, or correlations directly.
- Veto output is structured (pydantic model) with named constraint, observed value, limit, and blocked signal reference.
- Hard limits come from a human-editable YAML/JSON policy file (belief-memory-adjacent) — not hardcoded constants.
- Portfolio state is loaded from PostgreSQL; append-only history preserved.

### Locked Decisions (added 2026-04-22 during revision)

- **D-06-M01: Candidate metadata injection via explicit state key.** Candidate metadata (sector, instrument_type) is injected via an explicit `candidate_metadata: dict | None` state key on `DebatePipelineState` — NOT extracted from `ThesisOutput`. Rationale: `ThesisOutput` (defined in `src/ai_hedge_fund/schemas/agents.py:82`) is a Phase-3 immutable schema with no sector/instrument_type fields; adding them would break Phase 3 compatibility. Upstream callers (pipeline entry or research manager) set this field; when absent, `risk_manager_node` treats sector as "Unknown" (safe default: never matches excluded_sectors, never matches a sector-concentration threshold). See 06-05-PLAN.md Task 1 and 06-06-PLAN.md Task 1 Scenario 3 for implementation and integration-test usage.

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered during plan-phase research. Prior phases established:
- LangGraph pipeline with typed state (Phase 1)
- Data ingestion with temporal controls (Phase 2)
- Single-agent research loop producing theses with quantitative signals (Phase 3)
- Multi-agent specialization with Research Manager synthesis (Phase 4)
- Adversarial bull/bear debate producing stress-tested theses (Phase 5)

The Risk Manager is the next node after Phase 5 synthesis and before the human review gate.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — discuss phase skipped. Refer to ROADMAP phase description and success criteria. Research phase will surface references for hard-limit policy design, portfolio risk checks (sector concentration, correlation, drawdown projection), and the veto-gate pattern in LangGraph.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
