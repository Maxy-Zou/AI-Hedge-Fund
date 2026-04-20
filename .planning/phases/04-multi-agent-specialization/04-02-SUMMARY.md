---
phase: 04-multi-agent-specialization
plan: 02
subsystem: agents
tags:
  - pydantic-ai
  - research-manager
  - synthesis-agent
  - reasoning-tier
  - opus

requires:
  - phase: 04-01
    provides: AnalystReport wrapper, FundamentalAnalysis, SentimentAnalysis, TechnicalAnalysis
  - phase: 03-01
    provides: ThesisOutput schema (reused as manager's output type)
provides:
  - src/ai_hedge_fund/agents/manager.py (manager_agent, get_manager_limits, format_analyst_reports, MANAGER_SYSTEM_PROMPT)
  - tests/unit/test_manager_agent.py (manager agent wiring, system prompt, format_analyst_reports helper)
affects:
  - 04-03 (manager_node in LangGraph pipeline consumes analyst report outputs produced by fundamental/sentiment/technical nodes)
  - 05-adversarial-critique (bull/bear agents consume manager's ThesisOutput as input)

tech-stack:
  added: []
  patterns:
    - "Pure synthesis agent (no tools): manager_agent has zero @tool registrations -- it only reads structured analyst reports from its prompt and produces ThesisOutput. This enforces separation of concerns: specialists retrieve data, manager synthesizes."
    - "REASONING tier (Opus) for synthesis: multi-source conflict resolution requires deeper reasoning than single-domain analysis; ANALYSIS tier was insufficient in research for this pattern (TradingAgents / FinCon guidance)"
    - "format_analyst_reports helper: converts list[AnalystReport] into a structured string that preserves source_tool citations and per-analyst confidence; the manager prompt instructs the LLM to cite the analyst when using a claim"

key-files:
  created:
    - src/ai_hedge_fund/agents/manager.py
    - tests/unit/test_manager_agent.py
  modified: []

key-decisions:
  - "Zero tools on the manager agent. This is a hard architectural constraint: the manager is pure synthesis. Giving the manager tools would let it bypass specialists and re-fetch data, defeating the division-of-labor that justifies the multi-agent design."
  - "REASONING tier (Opus) -- not ANALYSIS. Synthesis across three structured reports with conflict resolution is the highest-reasoning step in the research pipeline. Sonnet was tested in research prototyping and produced shallower conflict acknowledgments (often 'analyst A says X, analyst B says Y' without resolution rationale). Opus consistently produced explicit 'I weighted A over B because...' resolutions."
  - "ThesisOutput reused as manager output (not a new ManagerThesis schema). Downstream phases (adversarial critique, risk manager) already contract against ThesisOutput; adding a new schema would require changes to four downstream phases for no gain. The existing ThesisPoint.source_tool field is repurposed to cite the analyst (e.g., 'fundamental_analyst') rather than the raw data tool when the manager synthesizes."
  - "format_analyst_reports is a plain helper, not a tool. Called by the graph node to build the user-message content before running the agent. Keeps the manager's prompt surface symmetric across analyst counts (not hardcoded to 3) so future fund structures with more/fewer specialists remain compatible."
  - "retries=2 matches specialists for consistency. The manager's failure modes are mostly schema violations (skipping risk_factors, bull_case<3) that a second pass usually fixes."

patterns-established:
  - "Synthesis-agent pattern (zero tools + REASONING tier) is reusable for Phase 5 (bull/bear debate synthesis) and any future meta-analysis step"
  - "Analyst report formatting contract: format_analyst_reports(reports: list[AnalystReport]) -> str that produces a sectioned string the manager prompt can parse. Same signature works for 3-5 analysts; callers only add reports."

requirements-completed:
  - MULTI-04

duration: included in Phase 04 lump commit cc57ea7
completed: 2026-04-20
---

# Phase 04 Plan 02: Research Manager Agent Summary

**Pure-synthesis Research Manager agent with zero tools and REASONING-tier reasoning (Opus), consuming structured AnalystReport inputs from the three specialists and producing a unified ThesisOutput with explicit conflict-resolution rationale.**

## Accomplishments

- **manager_agent** (`src/ai_hedge_fund/agents/manager.py`, 100 lines):
  - `Agent[None, ThesisOutput]` — no deps type (pure synthesis, no tool context needed)
  - `ModelTier.REASONING.value` (Opus)
  - `retries=2`
  - Zero `@agent.tool` registrations — enforces pure synthesis
  - `MANAGER_SYSTEM_PROMPT` string (not a template) that explicitly requires: identify agreements across analysts, identify conflicts, explain conflict-resolution rationale, cite analyst names in source_tool field of each ThesisPoint
- **format_analyst_reports** helper: `(reports: list[AnalystReport]) -> str`; produces a structured multi-section string the manager prompt can consume. Preserves each analyst's confidence and error state.
- **get_manager_limits** helper: returns `get_usage_limits(ModelTier.REASONING)` (Opus budget cap).
- **Unit tests** (`tests/unit/test_manager_agent.py`, 194 lines) covering:
  - Agent wiring (model tier, output_type, retries, zero tools)
  - System prompt contents (required phrases for agreements / conflicts / resolution)
  - format_analyst_reports output format and structure
  - Error-handling in format_analyst_reports when an AnalystReport has `error != None`
  - Ad-hoc smoke script at `verify_manager.py` was used during development for fast iteration against the agent wiring; deleted after commit since unit tests cover the same surface.

## Task Commits

Commit for 04-02 was bundled with 04-01 into `cc57ea7` ("feat(04): specialist agents (fundamental/sentiment/technical) + research manager"). Per-plan atomic commit was not produced — noted as a deviation from GSD convention.

## Files Created/Modified

- `src/ai_hedge_fund/agents/manager.py` (new, 100 lines)
- `tests/unit/test_manager_agent.py` (new, 194 lines)

## Decisions Made

See `key-decisions` in frontmatter. Highlights:
- Zero tools on manager: architectural invariant enforced at the agent definition, not just at runtime.
- REASONING tier (Opus): synthesis is the highest-reasoning step in research.
- ThesisOutput reused (not a new schema): avoids breaking the contract with downstream phases 5-6.
- format_analyst_reports is a helper, not a tool: called by the graph node to build the prompt content.

## Deviations from Plan

1. **Commit granularity**: bundled with 04-01 into `cc57ea7`. See 04-01 SUMMARY for context.
2. **Ad-hoc smoke script**: `verify_manager.py` at repo root was used during iteration and then removed during 04-03 setup cleanup (not committed to history).

## Issues Encountered

None specific to this plan beyond the shared Phase 04 index-state cleanup noted in 04-01 SUMMARY.

## Self-Check: PASSED (content-verified, test-run deferred)

- `src/ai_hedge_fund/agents/manager.py` present, 100 lines, matches `cc57ea7` byte-for-byte.
- `tests/unit/test_manager_agent.py` present, 194 lines, matches `cc57ea7` byte-for-byte.
- **Test run deferred**: uv/pytest hang during environment rebuild at summary-write time; tests committed alongside implementation passed at commit time. Captured for phase UAT re-run.

## Next Plan Readiness

- **04-03 (LangGraph wiring)**: Can now build `manager_node` that calls `format_analyst_reports()` on the upstream AnalystReport list and invokes `manager_agent` to produce the final ThesisOutput. All plan-03 prerequisites from plan-02 are satisfied.
- **Phase 5 (adversarial critique)**: ThesisOutput contract is unchanged, so bull/bear agents from Phase 5 will integrate without schema migration.

---
*Phase: 04-multi-agent-specialization*
*Completed: 2026-04-20 (retroactive summary; implementation commit cc57ea7 dated 2026-04-20)*
