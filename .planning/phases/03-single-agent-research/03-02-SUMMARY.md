---
phase: 03-single-agent-research
plan: 02
subsystem: agent-logic
tags:
  - pydantic-ai
  - langgraph
  - state-graph
  - signal-agent
  - pipeline
  - tdd

requires:
  - phase: 01-agent-infrastructure
    provides: create_agent factory, ModelTier routing, UsageLimits, SignalOutput schema, legacy build_pipeline + PipelineState
  - phase: 03-01
    provides: research_agent (Agent[ResearchDeps, ThesisOutput]), ResearchDeps frozen dataclass, get_research_limits, ThesisOutput + ThesisPoint schema
provides:
  - signal_agent (Agent[None, SignalOutput], ANALYSIS tier, retries=2, no tools)
  - get_signal_limits helper returning ANALYSIS-tier UsageLimits
  - ResearchPipelineState TypedDict (ticker, as_of_date, thesis, signal, error)
  - research_node async LangGraph node wrapping research_agent with budget enforcement
  - signal_node async LangGraph node wrapping signal_agent with thesis-input short-circuiting
  - build_research_pipeline() compiling START -> research -> signal -> END StateGraph
affects:
  - 03-03 (observability/verification, phase-level graph invocation tests)
  - 04-multi-agent-specialization (analyst nodes will follow the research_node/signal_node pattern)

tech-stack:
  added: []
  patterns:
    - "Two-phase agent pipeline: research agent (tool-augmented thesis) -> signal agent (thesis -> SignalOutput)"
    - "ResearchPipelineState TypedDict with ISO-string as_of_date for JSON-serialisable checkpoint state"
    - "Signal-node short-circuit pattern: empty dict when upstream error, explicit error when thesis missing"
    - "Separate legacy PipelineState from new ResearchPipelineState to keep Phase-1 pipeline untouched"

key-files:
  created:
    - src/ai_hedge_fund/agents/signal.py
    - tests/unit/test_signal_agent.py
    - tests/unit/test_research_node.py
  modified:
    - src/ai_hedge_fund/schemas/state.py
    - src/ai_hedge_fund/schemas/__init__.py
    - src/ai_hedge_fund/agents/__init__.py
    - src/ai_hedge_fund/graph/nodes.py
    - src/ai_hedge_fund/graph/pipeline.py
    - src/ai_hedge_fund/graph/__init__.py

key-decisions:
  - "signal_agent on ANALYSIS tier (Sonnet) with zero tools -- same budget as research agent; no deps needed since thesis is serialised into the prompt"
  - "ResearchPipelineState keeps as_of_date as an ISO string (not date) so LangGraph checkpoints stay JSON-serialisable"
  - "signal_node returns empty dict on upstream error (don't overwrite) and explicit error dict when thesis missing (so upstream gap is surfaced)"
  - "Kept legacy PipelineState + build_pipeline untouched to avoid Phase-1 regression; Phase-3 pipeline is an additional builder, not a replacement"
  - "retries=2 on signal_agent mirrors research_agent to recover from transient SignalOutput schema validation failures"

patterns-established:
  - "Two-stage PydanticAI pipeline pattern: tool-augmented research agent produces ThesisOutput -> lighter synthesis agent consumes dict and produces SignalOutput"
  - "LangGraph node short-circuit: node returns {} when state['error'] is truthy so edges can propagate error state without clobbering it"
  - "Dual StateGraph pattern: legacy and new pipelines coexist in pipeline.py over distinct TypedDict state types"

requirements-completed:
  - AGENT-04

duration: 5min
completed: 2026-04-12
---

# Phase 03 Plan 02: Signal agent + Research pipeline graph Summary

**Signal agent on Claude Sonnet + LangGraph research pipeline wiring: ResearchPipelineState carries ticker/as_of_date/thesis/signal through a compiled START -> research -> signal -> END graph, with per-node UsageLimits and short-circuiting on upstream error.**

## Performance

- **Duration:** 5 min (295 s)
- **Started:** 2026-04-12T17:49:29Z
- **Completed:** 2026-04-12T17:54:24Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 9 (3 created, 6 modified)

## Accomplishments

- Added `signal_agent: Agent[None, SignalOutput]` on `ModelTier.ANALYSIS` with `retries=2` and zero tools. System prompt maps thesis confidence to conviction (>=70 high / 40-69 medium / <40 low), caps position size at 10 percent, and forbids reasoning outside the provided thesis (AGENT-04).
- Added `get_signal_limits()` returning Sonnet-tier `UsageLimits` (50K input / 8K output / 58K total) -- same preset as research agent for consistency.
- Added `ResearchPipelineState` TypedDict (`total=False`) with required `ticker` + ISO-string `as_of_date`, and optional `thesis`/`signal`/`error` slots. Keeps state JSON-serialisable for LangGraph checkpointing without coupling to `datetime.date`.
- Added `research_node` and `signal_node` async LangGraph nodes in `graph/nodes.py`. Both enforce `UsageLimits` via `get_research_limits()` / `get_signal_limits()`, log usage through structlog, and trap `UsageLimitExceeded` back into `state["error"]`.
- `signal_node` short-circuits with an empty dict when upstream set `state["error"]` (never overwrites it) and returns an explicit error dict when thesis is missing or None (surfaces upstream gaps rather than producing a signal from nothing).
- Added `build_research_pipeline(checkpointer=None)` compiling a static `StateGraph(ResearchPipelineState)` with edges `START -> research -> signal -> END`. Kept legacy `build_pipeline` untouched so Phase-1 integration tests still pass.
- 15 new unit tests (`test_signal_agent.py` + `test_research_node.py`) covering agent wiring, usage limits, state typing, node short-circuits, pipeline node/edge structure, and legacy-pipeline regression checks. Full test run: 288 passed, 3 skipped (LLM integration tests without API key), 0 regressions.

## Task Commits

Each task was executed test-first (RED) and then implemented (GREEN):

1. **Task 1 RED (signal-agent tests)** -- `a15aadd` (test)
2. **Task 1 GREEN (signal-agent impl)** -- `5b689b1` (feat)
3. **Task 2 RED (node + pipeline tests)** -- `3b31c7b` (test)
4. **Task 2 GREEN (node + pipeline impl)** -- `383235d` (feat)

## Files Created/Modified

- `src/ai_hedge_fund/agents/signal.py` -- New module: `SIGNAL_SYSTEM_PROMPT`, `signal_agent`, `get_signal_limits`.
- `src/ai_hedge_fund/schemas/state.py` -- Added `ResearchPipelineState` TypedDict; kept `PipelineState` unchanged; expanded module docstring.
- `src/ai_hedge_fund/schemas/__init__.py` -- Re-export `ResearchPipelineState`.
- `src/ai_hedge_fund/agents/__init__.py` -- Re-export `signal_agent`, `get_signal_limits`; docstring updated.
- `src/ai_hedge_fund/graph/nodes.py` -- Imports for `ResearchDeps`, research/signal agents and their limits helpers, `ResearchPipelineState`, `datetime.date`. Added `research_node` and `signal_node` async functions with budget enforcement, structlog logging, and `UsageLimitExceeded` -> error handling. Existing `extract_node` / `analyze_node` untouched.
- `src/ai_hedge_fund/graph/pipeline.py` -- Added `build_research_pipeline` over `ResearchPipelineState`; kept `build_pipeline` bit-for-bit identical.
- `src/ai_hedge_fund/graph/__init__.py` -- Re-export `build_research_pipeline`, `research_node`, `signal_node`.
- `tests/unit/test_signal_agent.py` -- New test module: `TestSignalAgent`, `TestSignalLimits`, `TestResearchPipelineState`.
- `tests/unit/test_research_node.py` -- New test module: `TestNodesExist`, `TestSignalNodeShortCircuits`, `TestResearchPipeline`, `TestExistingPipeline`.

## Decisions Made

- **signal_agent has zero tools and no deps.** The thesis already carries every bull/bear point, confidence score, and risk factor needed to derive a signal. Adding tools would invite the agent to re-fetch data that was already synthesised, which risks temporal inconsistency and wasted tokens. Passing the thesis dict into the prompt is enough; the agent's job is synthesis, not retrieval.
- **`ResearchPipelineState.as_of_date` is an ISO string, not `datetime.date`.** `date` is not JSON-serialisable, which would break `PostgresSaver` checkpointing. Nodes convert with `date.fromisoformat(state["as_of_date"])` internally; the outward-facing state stays serialisable.
- **`signal_node` returns `{}` on upstream error, `{"error": ...}` on missing thesis.** These are two different conditions: an upstream error is propagated (empty update preserves the existing `error`), while a missing thesis on a clean state is a new failure that should be surfaced. This matches the existing `analyze_node` contract where `{}` means "skip" and `{"error": ...}` means "fail".
- **Kept the legacy `PipelineState` + `build_pipeline` intact.** Changing them would require updating the Phase-1 tests that exist in `tests/integration/test_graph.py`, which test a different state shape (`raw_text`). Two StateGraphs coexisting is clearer than retrofitting the old one.
- **signal_agent uses `ANALYSIS` tier (not `REASONING`).** Signal synthesis from a pre-validated thesis does not require Opus-level reasoning. Sonnet is the right cost/quality trade-off and matches the research agent's budget, so a pipeline run stays inside a predictable 2x-ANALYSIS envelope.

## Deviations from Plan

None -- plan executed exactly as written. The only adjustments beyond the literal prompt text were minor polish driven by project conventions (which the plan itself references):

- Added a `datetime.date` import at the top of `graph/nodes.py` (the plan's action step flagged this).
- Also re-exported the new symbols from `graph/__init__.py` and `agents/__init__.py` for consistency with existing re-export patterns (the plan did not require this, but the project's existing `__init__.py` files re-export everything, so omitting new public symbols would be inconsistent).

Neither change required behaviour outside the plan's `must_haves.truths` or altered any interface.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** None. Plan executed verbatim against the acceptance criteria.

## Issues Encountered

- One environment blip: the worktree's `uv` venv lost the editable install of the package between test runs (conftest `ModuleNotFoundError`). Resolved with `uv pip install -e .`, which is idempotent. Noted here only because it appeared twice and might recur in future parallel executors.

## User Setup Required

None -- no external service configuration required. Existing `ANTHROPIC_API_KEY` env var (or a dummy test key for unit tests) is sufficient.

## Self-Check: PASSED

**Files verified present:**
- `src/ai_hedge_fund/agents/signal.py` -- FOUND
- `src/ai_hedge_fund/schemas/state.py` -- FOUND (contains both `class PipelineState` and `class ResearchPipelineState`)
- `src/ai_hedge_fund/graph/nodes.py` -- FOUND (contains `async def research_node` and `async def signal_node`)
- `src/ai_hedge_fund/graph/pipeline.py` -- FOUND (contains both `def build_pipeline` and `def build_research_pipeline`)
- `tests/unit/test_signal_agent.py` -- FOUND (15 tests)
- `tests/unit/test_research_node.py` -- FOUND (12 tests)

**Commits verified present:**
- `a15aadd` -- test(03-02): failing tests for signal_agent and ResearchPipelineState
- `5b689b1` -- feat(03-02): signal_agent and ResearchPipelineState
- `3b31c7b` -- test(03-02): failing tests for research_node, signal_node, and pipeline
- `383235d` -- feat(03-02): research_node, signal_node, and build_research_pipeline

**Test suite status:** 288 passed, 3 skipped (LLM integration tests requiring real API key), 0 regressions, 0 failures. `ruff check` clean on all created/modified files.

## Next Plan Readiness

- `build_research_pipeline()` is ready to be invoked end-to-end by Plan 03-03 (phase-level observability and verification), and by the phase-verify step. Callers only need `{"ticker": "AAPL", "as_of_date": "2024-01-01"}` as input.
- Every node enforces `UsageLimits` and records token usage via structlog, which gives 03-03 immediate signal for cost/observability checks (once Langfuse is wired, `CallbackHandler` can snapshot the same traces).
- `ResearchPipelineState` is JSON-serialisable (ISO-string `as_of_date`), so the existing `create_checkpointer` / `create_async_checkpointer` helpers in `graph/checkpointer.py` should work without modification for durable research runs.
- If the signal agent produces malformed `SignalOutput`, PydanticAI's `retries=2` will regenerate output before the node surfaces a failure. Consider monitoring retry counts via Langfuse once integrated; chronic retries would signal a need to tighten the system prompt.
- Phase 4 analyst specialisation can follow the `research_node` template directly: build a frozen deps dataclass, wrap the agent in an async node with budget enforcement, and add it to the `StateGraph`.

---
*Phase: 03-single-agent-research*
*Completed: 2026-04-12*
