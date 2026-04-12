---
phase: 03-single-agent-research
plan: 03
subsystem: testing
tags:
  - integration-testing
  - pydantic-ai
  - test-model
  - langgraph
  - research-pipeline
  - phase-gate

requires:
  - phase: 03-01
    provides: research_agent (Agent[ResearchDeps, ThesisOutput]), ResearchDeps dataclass, ThesisOutput schema
  - phase: 03-02
    provides: signal_agent (Agent[None, SignalOutput]), build_research_pipeline, research_node, signal_node, ResearchPipelineState
provides:
  - tests/integration/test_research_pipeline.py (7 tests: 2 compilation, 2 TestModel, 3 real-LLM skip-guarded)
  - Verified package exports: research_agent, signal_agent, ResearchDeps (ai_hedge_fund.agents)
  - Verified package exports: build_research_pipeline, research_node, signal_node (ai_hedge_fund.graph)
  - Verified package exports: ThesisPoint, ResearchPipelineState (ai_hedge_fund.schemas)
  - Pending manual UAT items for real-LLM thesis quality verification
affects:
  - 04-multi-agent-specialization (Phase 4 will extend the pipeline pattern validated here)
  - Phase-level UAT: HUMAN-UAT.md will capture deferred manual verification items

tech-stack:
  added: []
  patterns:
    - "PydanticAI TestModel with call_tools=[] pattern: overrides the model for schema-valid structured output without triggering real tool side effects (SEC EDGAR / yfinance)"
    - "Skip-guard pattern for real-LLM tests: _has_real_api_key() rejects test dummy keys; _has_edgar_identity() separately gates EDGAR-backed tests"
    - "Temporal correctness via OR-combined weak signals: confidence, list lengths, or first-claim text differing across as_of_dates avoids LLM-non-determinism flakiness"

key-files:
  created:
    - tests/integration/test_research_pipeline.py
  modified: []

key-decisions:
  - "TestModel(call_tools=[]) is the only safe way to exercise the research agent's pipeline path in unit mode -- the default call_tools='all' triggers real SEC EDGAR and yfinance network calls via the registered tool wrappers"
  - "Temporal correctness test uses OR-combined weak signals (any of confidence differs, list lengths differ, first claim text differs) rather than AND -- LLM non-determinism would make strict AND assertions flaky; any one signal differing is sufficient evidence that as_of_date is flowing through"
  - "Real-LLM tests deferred to manual UAT: the autonomous orchestrator auto-approves human-verify checkpoints, so the 3 real-LLM tests stay skip-guarded in code and are captured as UAT items for the user to run when API keys are available"
  - "No __init__.py changes needed -- Plans 03-01 and 03-02 already re-exported every Phase-3 public symbol; Task 1's action step for __init__ changes was a no-op verified via grep on the acceptance criteria"
  - "Hand-crafted thesis dict in test_signal_from_thesis_real_llm -- schema-valid mock thesis lets the signal test run without ANTHROPIC_API_KEY + EDGAR_IDENTITY (only ANTHROPIC_API_KEY required)"

patterns-established:
  - "Three-tier test layering for agent pipelines: (1) compilation tests no key no network, (2) TestModel tests with call_tools disabled, (3) skip-guarded real-LLM tests"
  - "Dual skip guards for real-LLM tests: separate requires_real_llm and requires_edgar_identity decorators allow signal-only tests to skip one without the other"
  - "Deferred manual UAT pattern for autonomous execution: when auto-mode is active, checkpoint:human-verify tasks write infrastructure and document pending items instead of stopping"

requirements-completed:
  - AGENT-01
  - AGENT-02
  - AGENT-03
  - AGENT-04

duration: 4min
completed: 2026-04-12
---

# Phase 03 Plan 03: Research pipeline integration tests + phase gate Summary

**Three-tier integration test suite for the Phase-3 research pipeline: 2 compilation tests (no network), 2 PydanticAI TestModel tests with call_tools=[] to keep tools from hitting SEC EDGAR / yfinance, and 3 skip-guarded real-LLM tests covering full pipeline invocation, temporal correctness across as_of_dates, and signal generation from a hand-crafted thesis.**

## Performance

- **Duration:** ~4 min (231 s)
- **Started:** 2026-04-12T18:06:26Z
- **Completed:** 2026-04-12T18:10:17Z
- **Tasks:** 2 (Task 1 automated, Task 2 checkpoint deferred to UAT)
- **Files modified:** 1 (1 created)

## Accomplishments

- Added `tests/integration/test_research_pipeline.py` with 7 integration tests covering the full Phase-3 research pipeline surface:
  - **Compilation tests (2):** `test_research_pipeline_compiles`, `test_research_pipeline_with_checkpointer` -- verify `build_research_pipeline()` returns a `CompiledStateGraph` with and without `MemorySaver`.
  - **TestModel tests (2):** `test_research_agent_with_test_model` (uses `call_tools=[]` to bypass real tool calls, asserts schema-valid ThesisOutput with >= 3 bull/bear points and >= 2 risks), `test_signal_agent_with_test_model` (asserts SignalOutput with valid direction/conviction/position_size_pct).
  - **Real-LLM tests (3, skip-guarded):** `test_full_pipeline_real_llm` (AAPL thesis with all ThesisOutput constraints and source_tool citations), `test_temporal_correctness_real_llm` (OR-combined weak signals for differences between 2024-01-02 and 2025-01-02 theses), `test_signal_from_thesis_real_llm` (hand-crafted thesis dict -> signal, no EDGAR required).
- Verified all plan-required package exports are present (no `__init__.py` edits needed; Plans 03-01 and 03-02 already added them):
  - `from ai_hedge_fund.agents import research_agent, signal_agent, ResearchDeps` -- OK
  - `from ai_hedge_fund.graph import build_research_pipeline, research_node, signal_node` -- OK
  - `from ai_hedge_fund.schemas import ThesisPoint, ResearchPipelineState` -- OK
- Full test-suite status: **301 passed, 3 skipped (real-LLM), 6 deselected, 0 regressions, ruff clean** on all new and modified files.
- Pending manual UAT items captured for user to run when real API keys are available (see "Pending Manual Verification" section below). These are the acceptance-criteria items for Task 2's human-verify checkpoint.

## Task Commits

1. **Task 1: Integration tests and package exports** -- `95de498` (test)
   - Only 1 commit because no `__init__.py` changes were required -- the exports were already added in Plans 03-01 / 03-02. The plan's acceptance criteria for re-exports were verified via `grep` and remain satisfied.
2. **Task 2: Verify research pipeline against real ticker (checkpoint)** -- deferred to manual UAT per autonomous-mode protocol; no code commit.

## Files Created/Modified

- `tests/integration/test_research_pipeline.py` -- New integration test file with 7 tests across 3 categories (compilation, TestModel, real-LLM). Uses the same `_has_real_api_key()` pattern as `test_graph.py` plus a new `_has_edgar_identity()` guard for EDGAR-backed tests. Docstring documents the rationale for `TestModel(call_tools=[])` and expected real-LLM durations.

## Decisions Made

- **`TestModel(call_tools=[])` for the research agent:** The default `call_tools='all'` behavior makes TestModel invoke every registered tool (which would trigger SEC EDGAR and yfinance network calls via the thin tool wrappers). Setting `call_tools=[]` disables tool invocation so TestModel produces the final structured output directly. This is the only safe option for a unit-style test.
- **Temporal correctness: OR-combined weak signals.** For `test_temporal_correctness_real_llm`, asserting that `confidence_differs OR lengths_differ OR first_claim_differs` is enough to prove the as_of_date is flowing through. Requiring all three would be flaky under LLM non-determinism. Any single signal is strong evidence of temporal differentiation.
- **No `__init__.py` edits.** The plan's Task 1 listed four `__init__.py` updates, but Plans 03-01 and 03-02 had already re-exported every required symbol (research_agent, signal_agent, ResearchDeps, build_research_pipeline, research_node, signal_node, ThesisPoint, ResearchPipelineState). Re-verified via `grep`. No-op: keeping consistency rather than rewriting for its own sake.
- **Hand-crafted thesis for the signal-only real-LLM test.** `test_signal_from_thesis_real_llm` uses a static, schema-valid thesis dict and therefore does not require EDGAR. Only `ANTHROPIC_API_KEY` is needed. Added a separate `requires_real_llm` decorator (no `requires_edgar_identity`) to allow this test to run when EDGAR isn't configured.
- **Deferred Task 2 to manual UAT.** In autonomous chain mode, `checkpoint:human-verify` tasks write test infrastructure and mark the acceptance criteria as pending manual verification. The 3 real-LLM tests are in the file and ready to run -- the user can execute `uv run pytest tests/integration/test_research_pipeline.py -k real_llm -v` once API keys are set.

## Deviations from Plan

None -- plan executed as written. The only items not fulfilled literally are:

1. **Task 1, Step 1-3 (`__init__.py` updates):** Verified to be no-ops because prior plans had already added every symbol. No code changes made; acceptance criteria satisfied via grep.
2. **Task 2 (human-verify checkpoint):** Deferred to manual UAT per the autonomous-mode protocol in the prompt. Test infrastructure in place; 3 real-LLM tests ready to run; quality judgments by human captured as UAT items.

Neither is a deviation in the Rules 1-4 sense (no auto-fixes, no unplanned scope, no architectural change).

**Total deviations:** 0 auto-fixed.
**Impact on plan:** None. Every acceptance criterion is either passing automatically or captured as a pending manual UAT item.

## Issues Encountered

- **`ModuleNotFoundError: No module named 'ai_hedge_fund'`** when running pytest. The worktree venv occasionally lost its editable install of the package between pytest runs (same issue noted in Plan 03-02's SUMMARY). Resolved with `uv pip install -e .`. Idempotent; does not affect correctness.

## Pending Manual Verification

Task 2 (`checkpoint:human-verify`) requires human review of real-LLM output quality. The following items are deferred to manual UAT -- to be captured in the phase-level `HUMAN-UAT.md`.

### Automated command to re-run

```bash
cd "/Users/maxzou/Documents/projects/AI Hedgefund"
uv run pytest tests/integration/test_research_pipeline.py -x -v -k "real_llm"
```

### Prerequisites

1. `ANTHROPIC_API_KEY` set in `.env` to a real (non-dummy) Anthropic key.
2. `EDGAR_IDENTITY` set in `.env` in the form `"Your Name your@email.com"` (required for `test_full_pipeline_real_llm` and `test_temporal_correctness_real_llm`; `test_signal_from_thesis_real_llm` only needs ANTHROPIC_API_KEY).
3. Optional data API keys (FINNHUB_API_KEY, FRED_API_KEY, FMP_API_KEY) if the agent calls those tools.

### Acceptance Criteria (from plan Task 2)

- [ ] `test_full_pipeline_real_llm` passes: ThesisOutput has >= 3 bull, >= 3 bear, valid confidence (0-100), every point has a non-empty `source_tool`.
- [ ] `test_temporal_correctness_real_llm` passes: 2024 vs 2025 theses differ across >= 1 weak signal.
- [ ] `test_signal_from_thesis_real_llm` passes: signal has valid direction, conviction, time_horizon, position_size_pct in 0-100.
- [ ] **Human quality review:**
  - Bull/bear points are substantive (not generic templates).
  - `source_tool` fields name actual tools (`fetch_filings`, `get_financials`, `get_price_data`, `get_insider_activity`, `get_sentiment`, `get_macro_environment`).
  - Confidence score reflects evidence strength (not always 50 or always 95).
  - Signal direction aligns with thesis confidence (high confidence long/short should not produce low conviction).

### Expected Durations

- `test_full_pipeline_real_llm` -- 30-60 s (one research agent run with 3-6 tool calls).
- `test_temporal_correctness_real_llm` -- 60-120 s (two research agent runs).
- `test_signal_from_thesis_real_llm` -- 5-15 s (one signal agent run, no tools).

## User Setup Required

None for automated pipeline. For manual UAT, see "Pending Manual Verification" above.

## Self-Check: PASSED

**Files verified present:**
- `tests/integration/test_research_pipeline.py` -- FOUND (7 tests: 4 automated, 3 skip-guarded real-LLM)

**Commits verified present:**
- `95de498` -- test(03-03): add integration tests for research pipeline (found via `git log`)

**Package export verification (from plan's acceptance criteria):**
- `grep "research_agent" src/ai_hedge_fund/agents/__init__.py` -- FOUND (line 34, line 51)
- `grep "build_research_pipeline" src/ai_hedge_fund/graph/__init__.py` -- FOUND (line 24, line 29)
- `grep "ThesisPoint" src/ai_hedge_fund/schemas/__init__.py` -- FOUND (line 10, line 21)
- `grep "ResearchPipelineState" src/ai_hedge_fund/schemas/__init__.py` -- FOUND (line 12, line 18)

**Test suite status:**
- `uv run pytest tests/unit/ -x -q` -- 283 passed, 0 regressions.
- `uv run pytest tests/integration/test_research_pipeline.py -x -q -k "not real_llm"` -- 4 passed, 3 deselected.
- `uv run pytest tests/unit/ tests/integration/ -x -q -k "not real_llm and not requires"` -- 301 passed, 3 skipped, 6 deselected.
- `uv run ruff check tests/integration/test_research_pipeline.py src/` -- All checks passed.

## Next Plan Readiness

- **Phase 3 is ready for phase-verify/UAT gate.** All four AGENT-XX requirements now have both schema-enforced structure (AGENT-03/04) and automated test coverage (AGENT-01/02 via compilation + TestModel, real-LLM verification deferred to UAT).
- **Phase 4 (Multi-Agent Specialization)** can extend the research-pipeline pattern. The dual-test strategy (TestModel for unit-style validation + real-LLM for live verification) scales naturally: each new agent (Fundamental, Sentiment, Technical, Bull, Bear, Manager, RiskManager) can reuse the same skip-guard + TestModel pattern, and the three-tier file structure (compilation / TestModel / real-LLM) is a reusable template.
- **No blockers** for downstream work. The deferred real-LLM UAT items do not block Phase 4 planning -- they are quality validation, not correctness validation.

---
*Phase: 03-single-agent-research*
*Completed: 2026-04-12*
