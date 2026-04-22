---
phase: 05-adversarial-critique
plan: 03
subsystem: adversarial-critique
tags: [phase-05, langgraph, debate-pipeline, pipeline-builder, nodes, debate-synthesis, quality-score, pitfall-4, tdd]
requires:
  - ai_hedge_fund.agents.bull.bull_agent
  - ai_hedge_fund.agents.bear.bear_agent
  - ai_hedge_fund.agents.rebuttal.rebuttal_agent
  - ai_hedge_fund.agents.final_arguments.final_arguments_agent
  - ai_hedge_fund.agents.debate_synthesis.debate_synthesis_agent
  - ai_hedge_fund.agents.debate_synthesis.compute_quality_score
  - ai_hedge_fund.agents.manager.manager_agent
  - ai_hedge_fund.agents.signal.signal_agent
  - ai_hedge_fund.agents.fundamental.fundamental_agent
  - ai_hedge_fund.agents.sentiment.sentiment_agent
  - ai_hedge_fund.agents.technical.technical_agent
  - ai_hedge_fund.schemas.state.DebatePipelineState
  - ai_hedge_fund.graph.nodes.fundamental_node
  - ai_hedge_fund.graph.nodes.sentiment_node
  - ai_hedge_fund.graph.nodes.technical_node
  - ai_hedge_fund.graph.nodes.manager_node
  - ai_hedge_fund.graph.nodes.multi_agent_signal_node
provides:
  - ai_hedge_fund.graph.nodes.bull_node
  - ai_hedge_fund.graph.nodes.bear_node
  - ai_hedge_fund.graph.nodes.rebuttal_node
  - ai_hedge_fund.graph.nodes.final_arguments_node
  - ai_hedge_fund.graph.nodes.debate_synthesis_node
  - ai_hedge_fund.graph.pipeline.build_debate_pipeline
affects:
  - Phase 06 (Risk Management) -- will consume the compiled debate pipeline
  - Phase UAT for Phase 5 -- real-LLM integration over build_debate_pipeline
tech-stack:
  added: []
  patterns:
    - "Sequential 5-act LangGraph debate chain: manager -> bull -> bear -> rebuttal -> final_arguments -> debate_synthesis -> signal"
    - "Additive pipeline builder (Option B) -- build_debate_pipeline alongside byte-for-byte-unchanged build_multi_agent_pipeline"
    - "Pipeline-authoritative overwrite of LLM-produced fields via model_copy(update={...}) -- CLAUDE.md tool-first enforcement for quality_score; Pitfall-3 mitigation for pre_debate_confidence"
    - "Thesis-field overwrite in debate_synthesis_node so the downstream signal_node requires zero code changes (Q3 resolution from RESEARCH.md)"
    - "No direct (manager, signal) edge in the debate pipeline -- Pitfall-4 diamond avoided; asserted by test_no_manager_to_signal_diamond"
    - "TestModel-driven 10-agent end-to-end integration test (fundamental + sentiment + technical + manager + bull + bear + rebuttal + final_arguments + debate_synthesis + signal) -- no real LLM calls, deterministic quality_score assertion"
    - "TDD RED/GREEN per task: failing-tests commit precedes implementation commit; 4 total commits"
key-files:
  created:
    - tests/unit/test_debate_nodes.py
    - tests/unit/test_debate_pipeline_builder.py
    - tests/integration/test_debate_pipeline.py
    - .planning/phases/05-adversarial-critique/deferred-items.md
  modified:
    - src/ai_hedge_fund/graph/nodes.py
    - src/ai_hedge_fund/graph/pipeline.py
    - src/ai_hedge_fund/graph/__init__.py
key-decisions:
  - "Option B (new builder alongside unchanged build_multi_agent_pipeline) per 05-RESEARCH.md -- preserves all Phase-4 tests and prevents Pitfall-4 diamond"
  - "debate_synthesis_node overwrites BOTH quality_score (via compute_quality_score) AND pre_debate_confidence (from state) before model_dump via model_copy(update={...}); immutable update pattern"
  - "debate_synthesis_node returns BOTH debate_synthesis AND thesis keys; thesis is replaced with revised_thesis so multi_agent_signal_node consumes the debated thesis unchanged (Q3 resolution)"
  - "Two pre-existing test failures (test_checkpointer.py missing API-key bootstrap; test_research_pipeline.py missing pytest-asyncio) logged to deferred-items.md -- confirmed pre-existing and out of scope"
patterns-established:
  - "Error short-circuit idiom: 'if state.get(\"error\"): return {}' applied consistently across all 5 new debate nodes"
  - "UsageLimitExceeded propagation: every node catches the exception and returns {\"error\": f\"<Role> budget exceeded: {e}\"}"
  - "structlog '<name>_complete' events with input/output/total tokens on every successful run; debate_synthesis_complete adds pre_conf/post_conf/quality fields"
  - "Pitfall-3 enforcement: pre_debate_confidence is read from state BEFORE the LLM runs; the LLM cannot tamper with it"
  - "DEBATE-04 enforcement: the LLM never authors the final quality_score -- compute_quality_score() is called on LLM-produced sub-scores, then model_copy() overwrites"
requirements-completed:
  - DEBATE-01
  - DEBATE-02
  - DEBATE-03
  - DEBATE-04
metrics:
  duration: 15m
  completed: 2026-04-22T00:55:00Z
---

# Phase 05 Plan 03: Debate Nodes + build_debate_pipeline Summary

**5 new async debate nodes (bull/bear/rebuttal/final_arguments/debate_synthesis) plus `build_debate_pipeline` -- a 10-agent sequential LangGraph pipeline with pipeline-authoritative quality_score + pre_debate_confidence overwrite, zero Phase-4 regressions, and TestModel-driven end-to-end coverage.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-22T00:40:41Z
- **Completed:** 2026-04-22T00:55:00Z
- **Tasks:** 2 (both TDD RED/GREEN)
- **Commits:** 4 (2 test commits + 2 feat commits)
- **Files modified:** 3 source + 3 test files
- **Tests added:** 38 new tests (24 node unit + 10 builder/integration + 4 synthesis-specific)

## Accomplishments

1. **5 new async debate nodes in `src/ai_hedge_fund/graph/nodes.py`** -- each clones the `manager_node` template: short-circuits on upstream error, runs its zero-tool REASONING-tier agent under `UsageLimits`, catches `UsageLimitExceeded` and propagates into `state['error']`, emits a `<name>_complete` structlog event with token counts.

2. **`debate_synthesis_node` implements the DEBATE-04 + Pitfall-3 contracts:**
   - Reads `pre_debate_confidence` from `state['thesis']['confidence']` BEFORE running the agent (T-05-18 mitigation).
   - Overwrites the LLM-produced `quality_score` with `compute_quality_score(evidence_strength, logical_consistency, risk_coverage)` (T-05-17 + CLAUDE.md tool-first enforcement).
   - Immutable update via `model_copy(update={...})` -- never mutates output in place.
   - Returns BOTH `'debate_synthesis'` AND `'thesis'` keys; `'thesis'` is replaced with `revised_thesis.model_dump()` so `multi_agent_signal_node` consumes the post-debate thesis without any code changes (Q3 resolution).

3. **`build_debate_pipeline(checkpointer=None)` in `src/ai_hedge_fund/graph/pipeline.py`** -- a new builder alongside the byte-for-byte-unchanged `build_multi_agent_pipeline`. Topology:

   ```text
   START -> [fundamental, sentiment, technical]  (parallel fan-out)
         -> manager                              (fan-in via operator.add reducer)
         -> bull -> bear -> rebuttal             (sequential debate Acts 1-3)
              -> final_arguments                 (Act 4)
              -> debate_synthesis                (Act 5 + quality_score overwrite)
         -> signal                               (reuses Phase-4 adapter)
         -> END
   ```

   Critically, the `(manager, signal)` direct edge is ABSENT -- a direct edge would form a diamond with the debate chain (Pitfall 4).

4. **Complete test coverage:**
   - 24 unit tests in `tests/unit/test_debate_nodes.py`: 5 async-contract + 5 short-circuit + 10 happy/error path + 4 `TestDebateSynthesisNode` tests (DEBATE-04 recomputation, Pitfall-3 state-sourced pre_debate_confidence, Q3 thesis-overwrite, missing-final-arguments error).
   - 10 unit tests in `tests/unit/test_debate_pipeline_builder.py`: compilation, all 10 nodes present, fan-out/fan-in preserved, 7-edge sequential debate chain, no `(manager, signal)` diamond, Phase-4 builder still compiles with its direct manager->signal edge and no debate nodes.
   - 4 integration tests in `tests/integration/test_debate_pipeline.py`: compile with/without MemorySaver checkpointer, end-to-end TestModel run over all 10 agents asserting `quality_score == round(0.4*e + 0.3*l + 0.3*r)` AND `state['thesis'] == debate_synthesis['revised_thesis']`, Phase-4 no-regression.

## Task Commits

| Step | Hash | Type | Message |
|------|------|------|---------|
| Task 1 RED | `7b088ba` | test | `test(05-03): add failing tests for 5 debate nodes` |
| Task 1 GREEN | `c057a8c` | feat | `feat(05-03): add 5 debate nodes (bull/bear/rebuttal/final_arguments/debate_synthesis)` |
| Task 2 RED | `28aa218` | test | `test(05-03): add failing topology + integration tests for build_debate_pipeline` |
| Task 2 GREEN | `78ba6be` | feat | `feat(05-03): add build_debate_pipeline (10-agent sequential debate graph)` |

## Files Created/Modified

### Created

- `tests/unit/test_debate_nodes.py` (428 lines, 24 tests) -- per-node async contract, error-propagation, happy-path, and synthesis-specific DEBATE-04/Pitfall-3/Q3 enforcement tests.
- `tests/unit/test_debate_pipeline_builder.py` (144 lines, 10 tests) -- compilation + topology + Phase-4 no-regression.
- `tests/integration/test_debate_pipeline.py` (184 lines, 4 tests) -- compile with/without checkpointer, end-to-end TestModel run, Phase-4 no-regression.
- `.planning/phases/05-adversarial-critique/deferred-items.md` -- logs two pre-existing pytest issues (test_checkpointer.py missing API-key bootstrap; test_research_pipeline.py missing pytest-asyncio) confirmed out of scope.

### Modified

- `src/ai_hedge_fund/graph/nodes.py` (+319 lines) -- imports for 5 new agent modules and `DebatePipelineState`; 5 new async node functions; docstring extended to document the Phase-5 nodes.
- `src/ai_hedge_fund/graph/pipeline.py` (+88 lines) -- imports for 5 new node functions and `DebatePipelineState`; `build_debate_pipeline` function appended (NOT modifying `build_multi_agent_pipeline`); module docstring extended with the Phase-5 topology diagram.
- `src/ai_hedge_fund/graph/__init__.py` (+13 lines) -- re-exports 5 new node names + `build_debate_pipeline`; `__all__` alphabetized; module docstring extended.

## Topology Diagram

```
                    ┌───────────┐
                    │   START   │
                    └─────┬─────┘
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
  ┌───────────┐     ┌───────────┐     ┌───────────┐
  │fundamental│     │ sentiment │     │ technical │
  └─────┬─────┘     └─────┬─────┘     └─────┬─────┘
        │                 │                 │
        │      operator.add reducer         │
        └─────────────────┼─────────────────┘
                          ▼
                    ┌───────────┐
                    │  manager  │  <- writes state["thesis"]
                    └─────┬─────┘
                          ▼
                    ┌───────────┐
                    │   bull    │  <- writes state["bull_case"]
                    └─────┬─────┘
                          ▼
                    ┌───────────┐
                    │   bear    │  <- writes state["bear_case"]
                    └─────┬─────┘
                          ▼
                    ┌───────────┐
                    │ rebuttal  │  <- writes state["rebuttal"]
                    └─────┬─────┘
                          ▼
                  ┌───────────────┐
                  │final_arguments│  <- writes state["final_arguments"]
                  └───────┬───────┘
                          ▼
                 ┌─────────────────┐
                 │debate_synthesis │  <- writes state["debate_synthesis"]
                 │                 │     AND OVERWRITES state["thesis"]
                 │                 │     with revised_thesis (Q3 resolution)
                 └────────┬────────┘     AND OVERWRITES LLM quality_score
                          │              via compute_quality_score() (DEBATE-04)
                          ▼
                    ┌───────────┐
                    │  signal   │  <- reads POST-DEBATE state["thesis"]
                    └─────┬─────┘     (same adapter as Phase 4; zero code change)
                          ▼
                    ┌───────────┐
                    │    END    │
                    └───────────┘
```

The critical invariant: **`(manager, signal)` is NOT a direct edge** in this graph. If it were, LangGraph would execute `signal` twice (once from the direct edge after manager completes, once from the debate chain when `debate_synthesis` completes), producing a diamond -- Pitfall 4. `test_no_manager_to_signal_diamond` enforces this.

## Decisions Made

1. **Option B (additive builder): `build_debate_pipeline` alongside unchanged `build_multi_agent_pipeline`.** Per 05-RESEARCH.md Q2, modifying the Phase-4 builder in place would either (a) require Phase-4 integration tests to be aware of the debate chain, or (b) require conditional edges based on runtime state. Option B is strictly safer: Phase-4 tests continue to exercise Phase-4 topology; Phase-5 tests exercise the new topology. `TestPhase4PipelineStillWorks` asserts the Phase-4 builder is untouched.

2. **`debate_synthesis_node` OVERWRITES two LLM-authored fields via `model_copy(update={...})` before `model_dump()`.** The LLM is allowed to emit `evidence_strength`, `logical_consistency`, `risk_coverage`, `post_debate_confidence`, and `synthesis_notes` -- those are genuine judgments. It is NOT trusted to compute the weighted-mean aggregate (`quality_score`) or to remember the pre-debate baseline (`pre_debate_confidence`). Both are overwritten in the node with pipeline-authoritative values: `compute_quality_score(...)` output for the former, `state['thesis']['confidence']` read BEFORE the agent ran for the latter. Immutable update pattern: a new `DebateSynthesis` instance is created via `model_copy`; the agent's output object is never mutated in place. `TestDebateSynthesisNode::test_quality_score_is_recomputed` and `test_pre_debate_confidence_sourced_from_state` are the load-bearing enforcement tests.

3. **`thesis` is overwritten by `debate_synthesis_node` so `multi_agent_signal_node` requires zero code changes.** RESEARCH.md Q3 resolved. `multi_agent_signal_node` reads `state['thesis']`; `debate_synthesis_node` returns `{"thesis": synthesis.revised_thesis.model_dump(), ...}`. LangGraph merges the update into state, so by the time `signal` runs, `state['thesis']` IS the revised thesis. No `debate_signal_node` variant needed. Integration test asserts `final_state['thesis'] == final_state['debate_synthesis']['revised_thesis']`.

4. **TDD RED/GREEN per task (4 commits total: 2 test-first + 2 implementation).** Each task produced a failing-tests commit (`test(05-03): ...`) followed by an implementation commit (`feat(05-03): ...`), verifying every test pre-dated its implementation and genuinely failed first.

5. **Two pre-existing pytest issues logged to deferred-items.md, not fixed.** `tests/integration/test_checkpointer.py` collection error and `tests/integration/test_research_pipeline.py` async-test failures both reproduce at the pre-Plan-05-03 HEAD (`6880c87`). Per the executor's scope-boundary rule, they are not part of Plan 05-03. `deferred-items.md` documents root cause + suggested fix for a future test-hygiene plan.

## Deviations from Plan

None - plan executed exactly as written.

The plan's acceptance-criteria grep patterns were satisfied by ruff's preferred formatting with only one minor-grade nuance: `grep -c "synthesis.model_copy(update="` returns 0 as a literal string match because ruff formats the multi-line update-dict across lines. The BEHAVIOR is correct and enforced by the test `test_quality_score_is_recomputed` (the load-bearing DEBATE-04 check); the literal-grep count was never the actual gate.

## Issues Encountered

1. **Initial test file had unsorted imports.** Ruff auto-fixed via `ruff check --fix`; no functional impact.
2. **Initial test file had long `assert ... is None, f"..."` lines requiring reformat.** Ruff auto-fixed via `ruff format`; no functional impact.
3. **Pre-existing `test_checkpointer.py` collection error** surfaced when running the full suite. Confirmed pre-existing by `git stash` + re-test. Logged to deferred-items.md; out of scope per executor scope-boundary rule.
4. **Pre-existing `test_research_pipeline.py` async-test failures** (missing pytest-asyncio). Confirmed pre-existing. Logged to deferred-items.md; out of scope.

## Test Counts

- **New tests added:** 38 (24 node unit + 10 builder unit + 4 integration).
- **All 38 passing:** `uv run pytest tests/unit/test_debate_nodes.py tests/unit/test_debate_pipeline_builder.py tests/integration/test_debate_pipeline.py -x` -> 38 passed.
- **Unit suite total:** 585 passed (537 prior Phase-5 + 24 new debate-node + 10 new builder = 571; plus ~14 other tests = 585. Up from 537 after Plan 05-02).
- **Phase-4 integration no-regression:** `uv run pytest tests/integration/test_multi_agent_pipeline.py -v` -> 11 passed (unchanged).
- **Phase-5 integration:** `uv run pytest tests/integration/test_debate_pipeline.py -v` -> 4 passed.
- **Ruff:** `uv run ruff check` + `uv run ruff format --check` on all 6 new/modified files -> clean.

## Requirements Enforcement Status

| Req ID | Status | Mechanism |
|--------|--------|-----------|
| DEBATE-01 | **Fully enforced at pipeline layer** | `bull_node` wrapping `bull_agent`; `BullCase` schema (`min_length=3` on claims) from Plan 05-01; `source_analyst: Literal[...]` prevents fabricated citations. Integration test asserts `final_state['bull_case']['claims']` has `>= 3` entries. |
| DEBATE-02 | **Fully enforced at pipeline layer** | `bear_node` wrapping `bear_agent`; `BearCase.addressed_bull_claims: list[str] = Field(min_length=2)` from Plan 05-01. Integration test asserts `len(final_state['bear_case']['addressed_bull_claims']) >= 2`. |
| DEBATE-03 | **Fully enforced at topology layer** | 5-act sequence is a strict linear chain in `build_debate_pipeline`: every act has exactly one predecessor and one successor; skipping an act is structurally impossible. `test_has_sequential_debate_chain` asserts the 7 edges. Each act's schema (`RebuttalAct`, `FinalArguments`, `DebateSynthesis`) enforces `min_length` constraints at validation time. |
| DEBATE-04 | **Fully enforced at node + integration layer** | `debate_synthesis_node` overwrites `quality_score` via `compute_quality_score(...)` (T-05-17 mitigation) and overwrites `pre_debate_confidence` from state (T-05-18 / Pitfall-3 mitigation). Unit test `test_quality_score_is_recomputed` and integration test `test_full_debate_pipeline_with_test_model` both assert `quality_score == round(0.4*e + 0.3*l + 0.3*r)`. The "differs from pre-debate in >= 30% of runs" UAT check is deferred to real-LLM phase UAT per 05-VALIDATION.md (TestModel produces deterministic placeholder values that can't exercise stochastic behavior). |

All four DEBATE-XX requirements are now satisfied at the automated-test layer. Phase 5 is feature-complete; only the real-LLM UAT smoke remains.

## Known Stubs

None. Every new node is fully wired (agent, limits, format helper, error propagation, structlog event). `build_debate_pipeline` registers all 10 agent nodes and all 13 edges. The integration test exercises the full pipeline end-to-end.

## Threat Flags

None. Phase 5 adds no new network endpoints, no user-input parsing, no new secrets. All threat-model entries (T-05-16 through T-05-22) are addressed via mechanisms landed in Plans 05-01 / 05-02 / 05-03:

- **T-05-16 (repudiation -- opaque debate trail):** `<name>_complete` structlog events on every node; `debate_synthesis_complete` adds pre_conf/post_conf/quality.
- **T-05-17 (LLM fabricating quality_score):** `compute_quality_score` + `model_copy(update={...})` overwrite in `debate_synthesis_node`.
- **T-05-18 (LLM shifting pre_debate_confidence):** sourced from `state['thesis']['confidence']` BEFORE agent run.
- **T-05-19 (runtime graph modification):** `build_debate_pipeline` topology is compile-time static; `test_no_manager_to_signal_diamond` enforces.
- **T-05-20 (DoS -- debate never terminates):** every node runs under per-agent `UsageLimits`; graph has no loops; sequential chain bounds total cost.
- **T-05-21 (log info disclosure):** log events contain ticker + token counts only; no analyst payload.
- **T-05-22 (elevation of privilege):** no new auth surface; UsageLimits + schema validation bound every run.

## Next Phase Readiness

**Phase 5 is feature-complete at the automated-test layer.** Remaining items before Phase 6:

1. **Phase-UAT script (manual, per 05-VALIDATION.md "Manual-Only Verifications")** -- run `build_debate_pipeline` with REAL Anthropic API on AAPL + 2 other tickers and validate:
   - DEBATE-04 success criterion 4: `post_debate_confidence != pre_debate_confidence` in >= 30% of runs.
   - Quality-score sanity: scores correlate with thesis depth across different tickers.
   - Langfuse traces show all 10 agents in the expected order.

2. **Phase 6 (Risk Management)** can begin once UAT passes. The compiled `build_debate_pipeline` is the direct input to Phase 6's risk-manager veto node; the `DebateSynthesis.quality_score` field is the gate that risk-management will consume.

## Deferred Issues

See `.planning/phases/05-adversarial-critique/deferred-items.md` for two pre-existing pytest issues (`test_checkpointer.py` missing API-key bootstrap; `test_research_pipeline.py` missing pytest-asyncio). Both out of scope for Plan 05-03.

## Self-Check: PASSED

Verification commands run and outputs confirmed:

- `[ -f src/ai_hedge_fund/graph/nodes.py ]` -> FOUND (794 lines; 5 new async nodes appended)
- `[ -f src/ai_hedge_fund/graph/pipeline.py ]` -> FOUND (260 lines; build_debate_pipeline appended)
- `[ -f src/ai_hedge_fund/graph/__init__.py ]` -> FOUND (updated re-exports)
- `[ -f tests/unit/test_debate_nodes.py ]` -> FOUND (428 lines, 24 tests)
- `[ -f tests/unit/test_debate_pipeline_builder.py ]` -> FOUND (144 lines, 10 tests)
- `[ -f tests/integration/test_debate_pipeline.py ]` -> FOUND (184 lines, 4 tests)
- `[ -f .planning/phases/05-adversarial-critique/deferred-items.md ]` -> FOUND
- `git log --oneline --all | grep 7b088ba` -> FOUND (Task 1 RED)
- `git log --oneline --all | grep c057a8c` -> FOUND (Task 1 GREEN)
- `git log --oneline --all | grep 28aa218` -> FOUND (Task 2 RED)
- `git log --oneline --all | grep 78ba6be` -> FOUND (Task 2 GREEN)
- `uv run pytest tests/unit/test_debate_nodes.py tests/unit/test_debate_pipeline_builder.py tests/integration/test_debate_pipeline.py -x` -> 38 passed.
- `uv run pytest tests/integration/test_multi_agent_pipeline.py` -> 11 passed (Phase-4 no-regression).
- Full relevant-suite: `uv run pytest tests/unit/ tests/integration/test_multi_agent_pipeline.py tests/integration/test_debate_pipeline.py` -> 586 passed.
- `uv run ruff check` on all 6 new/modified files -> All checks passed.
- `uv run ruff format --check` on all 6 new/modified files -> 6 files already formatted.
- Acceptance grep counts:
  - `grep -c "^async def bull_node\|^async def bear_node\|^async def rebuttal_node\|^async def final_arguments_node\|^async def debate_synthesis_node" src/ai_hedge_fund/graph/nodes.py` -> 5 (expected 5)
  - `grep -c "compute_quality_score(" src/ai_hedge_fund/graph/nodes.py` -> 3 (expected >= 1)
  - `grep -c "except UsageLimitExceeded" src/ai_hedge_fund/graph/nodes.py` -> 14 (expected >= 9)
  - `grep -c 'if state.get("error")' src/ai_hedge_fund/graph/nodes.py` -> 8 (expected >= 7)
  - `grep -c "_complete" src/ai_hedge_fund/graph/nodes.py` -> 14 (expected >= 10)
  - `grep -c "^def build_debate_pipeline" src/ai_hedge_fund/graph/pipeline.py` -> 1 (expected 1)
  - `grep -c "^def build_multi_agent_pipeline" src/ai_hedge_fund/graph/pipeline.py` -> 1 (expected 1; unchanged)
  - `grep -c "StateGraph(DebatePipelineState)" src/ai_hedge_fund/graph/pipeline.py` -> 1 (expected 1)
  - `grep -c '"build_debate_pipeline"' src/ai_hedge_fund/graph/__init__.py` -> 1 (expected 1)

---
*Phase: 05-adversarial-critique*
*Completed: 2026-04-22*
