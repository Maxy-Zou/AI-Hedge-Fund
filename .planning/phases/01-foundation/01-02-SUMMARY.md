---
phase: 01-foundation
plan: 02
subsystem: agents
tags: [pydantic-ai, agent-factory, budget-enforcement, immutable-dataclass, model-routing]

# Dependency graph
requires:
  - 01-01 (ModelTier enum, AgentBudget, MODEL_BUDGETS, ExtractionOutput, AnalysisOutput schemas)
provides:
  - Agent factory (create_agent) with model-tier routing via ModelTier enum
  - Per-tier UsageLimits helper (get_usage_limits) with custom overrides
  - PipelineBudgetTracker immutable accumulator with BudgetExceededError enforcement
  - AgentUsageRecord frozen audit trail for per-agent token usage
  - Extraction agent (Haiku) with ExtractionOutput schema and tool-first prompt
  - Analysis agent (Sonnet) with AnalysisOutput schema and data-only prompt
  - get_extraction_limits and get_analysis_limits tier-specific helpers
affects: [01-03, 02-data-pipeline, 03-agents]

# Tech tracking
tech-stack:
  added: []
  patterns: [agent-factory with enum-based model routing, frozen-dataclass pipeline budget tracker, immutable record_usage returning new instances, module-level agent singletons]

key-files:
  created:
    - src/ai_hedge_fund/agents/__init__.py
    - src/ai_hedge_fund/agents/base.py
    - src/ai_hedge_fund/agents/extraction.py
    - src/ai_hedge_fund/agents/analysis.py
    - tests/unit/test_agents.py
    - tests/unit/test_budget.py
  modified: []

key-decisions:
  - "create_agent is a thin factory -- value is centralizing model string resolution through ModelTier enum"
  - "PipelineBudgetTracker uses frozen dataclass with tuple records for guaranteed immutability"
  - "record_usage returns new tracker instance, never mutates original (immutable pattern per CLAUDE.md)"
  - "Module-level agent singletons (extraction_agent, analysis_agent) for import convenience"
  - "System prompts enforce tool-first rules: 'never estimate or calculate' and 'never generate financial numbers'"

patterns-established:
  - "Agent creation: create_agent(ModelTier, output_type, system_prompt) -> Agent"
  - "Budget limits: get_usage_limits(ModelTier) -> UsageLimits with optional overrides"
  - "Pipeline tracking: PipelineBudgetTracker().record_usage() -> new PipelineBudgetTracker"
  - "Concrete agents: module-level instances created via factory, with tier-specific limit helpers"

requirements-completed: [FOUND-02, FOUND-03, FOUND-05]

# Metrics
duration: 4min
completed: 2026-04-12
---

# Phase 1 Plan 2: PydanticAI Agent Layer Summary

**Agent factory with budget-enforced model routing (Haiku extraction, Sonnet analysis), immutable pipeline budget tracker, and 48 unit tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-12T06:50:00Z
- **Completed:** 2026-04-12T06:54:34Z
- **Tasks:** 2
- **Files created:** 6

## Accomplishments

- Agent factory (`create_agent`) centralizes PydanticAI Agent creation with ModelTier enum routing
- `get_usage_limits` converts AgentBudget presets to PydanticAI UsageLimits with per-field overrides
- PipelineBudgetTracker is a frozen dataclass that accumulates token usage immutably and raises BudgetExceededError on pipeline cap overrun
- AgentUsageRecord provides frozen per-agent audit trail (threat model T-02-03)
- Extraction agent configured with Haiku model and ExtractionOutput schema, system prompt enforces "never estimate or calculate"
- Analysis agent configured with Sonnet model and AnalysisOutput schema, system prompt enforces "never generate financial numbers"
- 48 unit tests passing covering factory, budget tracker, concrete agents, and limit helpers

## Task Commits

Each task was committed atomically:

1. **Task 1: Agent factory with budget enforcement and pipeline budget tracker**
   - `17d99be` (test: failing tests for agent factory and budget tracker -- TDD RED)
   - `480b8e5` (feat: agent factory with budget enforcement and pipeline tracker -- TDD GREEN)
2. **Task 2: Concrete extraction and analysis agents**
   - `fe3f790` (test: failing tests for concrete extraction and analysis agents -- TDD RED)
   - `63cff1a` (feat: concrete extraction and analysis agents -- TDD GREEN)

## Files Created/Modified

- `src/ai_hedge_fund/agents/__init__.py` -- Re-exports all agent layer components
- `src/ai_hedge_fund/agents/base.py` -- Agent factory, get_usage_limits, PipelineBudgetTracker, BudgetExceededError, AgentUsageRecord
- `src/ai_hedge_fund/agents/extraction.py` -- Haiku extraction agent with ExtractionOutput schema
- `src/ai_hedge_fund/agents/analysis.py` -- Sonnet analysis agent with AnalysisOutput schema
- `tests/unit/test_agents.py` -- 26 tests for agent factory, concrete agents, and limit helpers
- `tests/unit/test_budget.py` -- 22 tests for PipelineBudgetTracker, BudgetExceededError, AgentUsageRecord

## Decisions Made

- `create_agent` is a thin factory -- the value is centralizing model string resolution through ModelTier enum so every agent goes through a single creation path
- PipelineBudgetTracker uses frozen dataclass with tuple records (not list) for guaranteed immutability per CLAUDE.md conventions
- `record_usage` returns a NEW tracker instance -- original is never mutated (immutable pattern)
- Module-level agent singletons (`extraction_agent`, `analysis_agent`) for import convenience; created via the factory
- System prompts enforce tool-first rules from CLAUDE.md: extraction says "never estimate or calculate", analysis says "never generate financial numbers"
- Tests use `ANTHROPIC_API_KEY=test-key-for-unit-tests` env var to bypass PydanticAI provider validation without real API calls

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None -- no external service configuration required. ANTHROPIC_API_KEY is only needed for actual LLM calls, not for agent construction in tests.

## Next Phase Readiness

- Agent factory and concrete agents ready for LangGraph node wrapping in Plan 03
- PipelineBudgetTracker ready for integration into graph execution context
- get_usage_limits ready to be passed to agent.run() calls in pipeline nodes

## Self-Check: PASSED
