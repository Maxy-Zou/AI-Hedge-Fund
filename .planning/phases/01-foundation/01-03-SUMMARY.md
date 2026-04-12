---
phase: 01-foundation
plan: 03
subsystem: pipeline
tags: [langgraph, pipeline, checkpointer, langfuse, observability, budget-enforcement]

# Dependency graph
requires:
  - 01-01 (AppSettings, ModelTier, PipelineState TypedDict, ExtractionOutput/AnalysisOutput schemas)
  - 01-02 (create_agent factory, get_usage_limits, PipelineBudgetTracker, extraction_agent, analysis_agent)
provides:
  - Compiled LangGraph StateGraph with extract -> analyze nodes (build_pipeline)
  - Node functions wrapping PydanticAI agents with UsageLimits enforcement
  - PostgresSaver checkpointer context managers (sync and async)
  - Langfuse CallbackHandler factory with graceful degradation
  - Langfuse invocation config with thread_id and trace metadata
  - Budget-enforced invocation config bundling Langfuse + PipelineBudgetTracker
affects: [02-data-pipeline, 03-agents, 04-debate]

# Tech tracking
tech-stack:
  added: [langchain]
  patterns: [PydanticAI agent wrapped as LangGraph node function, context manager for PostgresSaver lifecycle, graceful degradation when observability credentials absent, immutable dict returns from node functions]

key-files:
  created:
    - src/ai_hedge_fund/graph/__init__.py
    - src/ai_hedge_fund/graph/pipeline.py
    - src/ai_hedge_fund/graph/nodes.py
    - src/ai_hedge_fund/graph/checkpointer.py
    - src/ai_hedge_fund/observability/__init__.py
    - src/ai_hedge_fund/observability/langfuse.py
    - src/ai_hedge_fund/observability/budget.py
    - tests/integration/__init__.py
    - tests/integration/test_graph.py
    - tests/integration/test_checkpointer.py
    - tests/integration/test_observability.py
  modified:
    - pyproject.toml

key-decisions:
  - "Node functions return NEW dicts (never mutate state) per immutable pattern and threat model T-03-03"
  - "UsageLimits enforced on every agent.run() call via get_extraction_limits/get_analysis_limits per threat model T-03-02"
  - "Langfuse CallbackHandler created only when both public and secret keys present -- pipeline runs without tracing otherwise"
  - "create_invocation_config bundles Langfuse config + PipelineBudgetTracker for one-call pipeline setup"
  - "build_pipeline accepts BaseCheckpointSaver (not just PostgresSaver) for testability without DB"
  - "Added langchain as dependency for Langfuse CallbackHandler LangChain integration"
  - "LLM integration tests use _has_real_api_key() to distinguish dummy test keys from real API keys"

patterns-established:
  - "Graph node pattern: async def node(state: PipelineState) -> dict with try/except UsageLimitExceeded"
  - "Checkpointer pattern: context manager yielding PostgresSaver with auto table setup"
  - "Observability pattern: create_langfuse_config() -> dict with optional callbacks based on env"
  - "Invocation pattern: create_invocation_config(thread_id, ticker) -> (config, tracker)"

requirements-completed: [FOUND-01, FOUND-03, FOUND-04, FOUND-05]

# Metrics
duration: 7min
completed: 2026-04-12
---

# Phase 1 Plan 3: LangGraph Pipeline Integration Summary

**Two-node LangGraph pipeline (extract -> analyze) with PostgreSQL checkpointing, Langfuse observability, and budget-enforced invocation config -- completing all four Phase 1 success criteria**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-12T06:58:57Z
- **Completed:** 2026-04-12T07:05:57Z
- **Tasks:** 2
- **Files created:** 11
- **Files modified:** 1

## Accomplishments

- LangGraph StateGraph with two nodes (extract -> analyze) compiles and is ready for invocation
- Node functions wrap PydanticAI agents with UsageLimits on every run() call; catch UsageLimitExceeded and store error in state
- PostgresSaver checkpointer via context manager with automatic table creation (sync + async versions)
- Langfuse CallbackHandler factory with graceful degradation when credentials not configured
- create_langfuse_config produces LangGraph invocation config with thread_id and optional Langfuse tracing
- create_invocation_config bundles Langfuse config + PipelineBudgetTracker for complete run setup
- 96 tests passing across entire test suite (5 graph compilation + 9 observability + 82 existing unit tests)
- 3 LLM integration tests and 3 checkpointer tests available but skip without real credentials/DB

## Task Commits

Each task was committed atomically:

1. **Task 1: LangGraph graph definition, node functions, and checkpointer**
   - `85ae723` -- feat(01-03): LangGraph pipeline with extract/analyze nodes, checkpointer, and integration tests
2. **Task 2: Langfuse observability integration and budget-enforced invocation config**
   - `5709515` -- feat(01-03): Langfuse observability integration and budget-enforced invocation config

## Files Created/Modified

- `src/ai_hedge_fund/graph/__init__.py` -- Re-exports build_pipeline, node functions, checkpointer helpers
- `src/ai_hedge_fund/graph/pipeline.py` -- StateGraph with extract -> analyze nodes, build_pipeline factory
- `src/ai_hedge_fund/graph/nodes.py` -- extract_node and analyze_node wrapping PydanticAI agents with UsageLimits
- `src/ai_hedge_fund/graph/checkpointer.py` -- Sync/async PostgresSaver context managers with auto-setup
- `src/ai_hedge_fund/observability/__init__.py` -- Re-exports create_langfuse_config, create_invocation_config, shutdown_langfuse
- `src/ai_hedge_fund/observability/langfuse.py` -- CallbackHandler factory, config builder, shutdown helper
- `src/ai_hedge_fund/observability/budget.py` -- Budget-enforced invocation config combining Langfuse + PipelineBudgetTracker
- `tests/integration/__init__.py` -- Integration test package
- `tests/integration/test_graph.py` -- 5 compilation tests + 3 skippable LLM integration tests
- `tests/integration/test_checkpointer.py` -- 3 skippable PostgreSQL checkpointer tests
- `tests/integration/test_observability.py` -- 9 observability and budget config tests
- `pyproject.toml` -- Added langchain dependency for Langfuse CallbackHandler support

## Decisions Made

- Node functions return NEW dicts (never mutate state parameter) per immutable pattern and threat model T-03-03
- UsageLimits enforced on every agent.run() call via tier-specific limit helpers per threat model T-03-02
- Langfuse CallbackHandler created only when both LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set -- pipeline runs without tracing otherwise (graceful degradation per T-03-01)
- build_pipeline() accepts BaseCheckpointSaver (not just PostgresSaver) for testability without database
- Added `langchain` as a production dependency because Langfuse's CallbackHandler requires it for LangChain/LangGraph integration
- LLM integration tests use _has_real_api_key() helper to distinguish dummy test keys from real API keys, preventing test failures during CI with dummy credentials

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added langchain dependency for Langfuse CallbackHandler**
- **Found during:** Task 1
- **Issue:** `from langfuse.langchain import CallbackHandler` requires the `langchain` package which was not in dependencies
- **Fix:** Added `langchain>=1.2.15` to pyproject.toml dependencies
- **Files modified:** pyproject.toml
- **Commit:** 85ae723

**2. [Rule 1 - Bug] Fixed test filtering for LLM integration tests**
- **Found during:** Task 1
- **Issue:** `-k "not requires"` filter did not match test function names, causing LLM tests to run and fail with dummy API key
- **Fix:** Renamed LLM test functions to include "requires" prefix and added _has_real_api_key() helper to skip tests with dummy keys
- **Files modified:** tests/integration/test_graph.py
- **Commit:** 85ae723

## Issues Encountered

None.

## User Setup Required

- **Langfuse (optional):** Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY for observability tracing. Pipeline runs without tracing if not configured.
- **Anthropic API key (for LLM tests):** Set ANTHROPIC_API_KEY to run LLM integration tests.
- **PostgreSQL (for checkpointer tests):** Run `docker compose up -d` to start PostgreSQL for checkpointer integration tests.

## Phase 1 Success Criteria Verification

| Criterion | Status | Evidence |
|-----------|--------|----------|
| LangGraph graph with checkpointing | DONE | build_pipeline(checkpointer) compiles with PostgresSaver |
| Typed agent schemas | DONE | ExtractionOutput, AnalysisOutput validated by PydanticAI |
| Multi-model routing with traces | DONE | Haiku extract, Sonnet analyze, Langfuse CallbackHandler |
| Token budget enforcement | DONE | UsageLimits on every agent.run(), PipelineBudgetTracker |

## Self-Check: PASSED

- All 11 created files verified present on disk
- Both task commits verified in git log (85ae723, 5709515)
- 96/96 non-skipped tests passing
- ruff check src/ clean
