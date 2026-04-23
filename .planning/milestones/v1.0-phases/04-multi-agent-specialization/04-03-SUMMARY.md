---
phase: 04-multi-agent-specialization
plan: 03
subsystem: graph
tags:
  - langgraph
  - multi-agent
  - fan-out-fan-in
  - state-reducer
  - integration-testing
  - phase-gate

requires:
  - phase: 04-01
    provides: fundamental_agent, sentiment_agent, technical_agent (Agents with ResearchDeps), FundamentalAnalysis/SentimentAnalysis/TechnicalAnalysis, AnalystReport
  - phase: 04-02
    provides: manager_agent (Agent[None, ThesisOutput]), format_analyst_reports helper, get_manager_limits
  - phase: 03-02
    provides: ResearchPipelineState, research_node, signal_node, build_research_pipeline (untouched by this plan)
provides:
  - src/ai_hedge_fund/schemas/state.py (MultiAgentPipelineState TypedDict with Annotated[list[dict], operator.add] reducer on analyst_reports)
  - src/ai_hedge_fund/graph/nodes.py (fundamental_node, sentiment_node, technical_node, manager_node, multi_agent_signal_node -- 5 new async nodes; existing nodes untouched)
  - src/ai_hedge_fund/graph/pipeline.py (build_multi_agent_pipeline builder with fan-out/fan-in topology; existing builders untouched)
  - src/ai_hedge_fund/agents/__init__.py (re-exports for 04-01/04-02 surface)
  - src/ai_hedge_fund/graph/__init__.py (re-exports for Phase-4 nodes and builder)
  - src/ai_hedge_fund/schemas/__init__.py (re-exports for Phase-4 analysis schemas and MultiAgentPipelineState)
  - tests/unit/test_multi_agent_nodes.py (26 tests: state schema, node async contract, happy path, error propagation, no-regression on Phase-1/3 nodes)
  - tests/integration/test_multi_agent_pipeline.py (11 tests: pipeline compilation + topology, TestModel end-to-end flow, Phase-1/3 no-regression compile checks)
affects:
  - 05-adversarial-critique (bull/bear agents will extend MultiAgentPipelineState with debate fields)
  - 06-risk-management (risk manager node will hang off the manager -> signal edge or replace signal entirely)
  - 07-memory-and-learning (checkpointer interface already threaded through build_multi_agent_pipeline)

tech-stack:
  added: []
  patterns:
    - "Annotated[list[dict], operator.add] state reducer: lets parallel LangGraph nodes (fundamental_node, sentiment_node, technical_node) each return {\"analyst_reports\": [single_dict]} and LangGraph concatenates into a 3-element list before the manager node runs. Required because the default TypedDict semantics overwrite — last-write-wins would silently drop analyst outputs."
    - "Thin async node wrappers over specialist agents: each analyst_node is a coroutine that builds ResearchDeps from state, calls agent.run(ticker_prompt, deps=deps, usage_limits=get_<domain>_limits()), catches Exception to propagate into the reducer-compatible analyst_reports list rather than raising (so partial failure doesn't kill the pipeline)"
    - "Manager node reads pre-aggregated analyst_reports from state (3 elements after fan-in) and calls format_analyst_reports() to construct the user prompt — the manager agent itself remains stateless and tool-less"

key-files:
  created:
    - tests/unit/test_multi_agent_nodes.py
    - tests/integration/test_multi_agent_pipeline.py
  modified:
    - src/ai_hedge_fund/schemas/state.py (added MultiAgentPipelineState TypedDict)
    - src/ai_hedge_fund/graph/nodes.py (added 5 async node functions; existing nodes and imports untouched)
    - src/ai_hedge_fund/graph/pipeline.py (added build_multi_agent_pipeline; existing builders untouched)
    - src/ai_hedge_fund/agents/__init__.py (re-exports)
    - src/ai_hedge_fund/graph/__init__.py (re-exports)
    - src/ai_hedge_fund/schemas/__init__.py (re-exports)

key-decisions:
  - "operator.add reducer on analyst_reports (not a custom reducer): the minimal built-in reducer that meets the fan-in need. Custom reducers add maintenance burden and would need their own tests; the built-in is documented, tested by LangGraph itself, and sufficient."
  - "Analyst failures are caught and written into analyst_reports as AnalystReport(error=str(exc)) dicts, not raised. This is a hard requirement from the plan's must_haves list: 'Failed analyst nodes propagate error into analyst_reports (not crash the pipeline).' If one specialist's data tool fails (e.g., SEC EDGAR outage mid-run), the manager should still synthesize from the analysts that did succeed rather than aborting the whole pipeline."
  - "multi_agent_signal_node is a NEW node, not a reuse of Phase-3 signal_node. Phase-3 signal_node reads from ResearchPipelineState (single thesis field), while Phase-4 needs to read from MultiAgentPipelineState (different TypedDict). A thin adapter keeps the state contracts distinct rather than adding conditional logic to the shared signal_node."
  - "TestModel(call_tools=[]) on all three specialist agents in the integration test: without call_tools=[], TestModel invokes every registered tool which triggers real SEC EDGAR / yfinance / Finnhub network calls through the Phase-2 tool wrappers. call_tools=[] bypasses tool execution so TestModel produces the structured output directly. Same pattern as Phase-3 integration tests."
  - "No real-LLM integration tests in this plan. A Phase-4 pipeline run invokes 4 agents (3 specialists + manager, plus signal) — rough cost $1-3 per run. Manual UAT scripts are the right home for that validation; pytest is not."
  - "Pipeline builder registers a SIGNAL node using multi_agent_signal_node, not signal_node. This is deliberate: signal_node binds ResearchPipelineState, and mixing state types inside a single builder risks cryptic KeyError at runtime. Each builder uses exactly one state TypedDict."

patterns-established:
  - "Fan-out/fan-in Graph topology for multi-agent synthesis: START -> [N parallel analysts via operator.add reducer] -> manager -> signal -> END. Reusable for Phase 5 (adversarial debate can hang bull/bear off the manager output with its own operator.add reducer on debate_points) and Phase 6 (risk manager slots in as a new node before signal)."
  - "Error-propagation-not-crash pattern for parallel analyst nodes: try/except around agent.run → write AnalystReport(error=...) to analyst_reports. Keeps the pipeline resilient to partial data-source failures, which is necessary for free-tier data (yfinance fragility, Finnhub rate limits)."
  - "Thin state-adapter node pattern (multi_agent_signal_node): when two pipelines need a similar LLM call on different state shapes, cloning the node with the state-specific projection is cleaner than parameterizing the shared node with a state extractor."

requirements-completed:
  - MULTI-01
  - MULTI-02
  - MULTI-03
  - MULTI-04

duration: ~3.2h (first dispatch was lost to an environment hang; second dispatch landed Tasks 1-2 in commit 90d8033, Tasks 3-4 were finished inline and committed as 676ae44)
completed: 2026-04-21
---

# Phase 04 Plan 03: Multi-Agent LangGraph Pipeline Wiring Summary

**Wires the Phase-4 pipeline end-to-end: MultiAgentPipelineState with an operator.add reducer on analyst_reports, 5 new async LangGraph nodes (3 parallel analysts + manager + signal adapter), and build_multi_agent_pipeline with fan-out/fan-in topology — all alongside the untouched Phase-1/3 pipelines.**

## Performance

- **Duration:** ~3.2h of agent time across two dispatches (first dispatch lost to a corrupted `.venv` that caused `uv run pytest` to hang indefinitely; after env fix, second dispatch landed Tasks 1-2 atomically as `90d8033`, then stream-timed out mid Task 3 with code on disk; Tasks 3-4 finished inline and committed as `676ae44`).
- **Commits:** 2 code commits (`90d8033` nodes/state, `676ae44` pipeline/re-exports/integration-test) plus this SUMMARY.
- **Files:** 8 modified/created across src and tests.
- **Test runs after plan:** 37 multi-agent tests pass (26 unit + 11 integration) in 428s; 373 other unit tests pass in 105s; no regressions on Phase 1/3 tests.

## Accomplishments

- **`MultiAgentPipelineState`** in `schemas/state.py`: TypedDict with ticker, as_of_date (pass-through), `analyst_reports: Annotated[list[dict], operator.add]` (reducer-based fan-in), `thesis: dict | None`, `signal: dict | None`, `error: str | None`. The `Annotated[..., operator.add]` is the linchpin — without it, the three parallel analysts would each overwrite the last-written report instead of appending.
- **5 new async nodes** in `graph/nodes.py` (existing nodes untouched):
  - `fundamental_node`, `sentiment_node`, `technical_node`: thin wrappers around Phase-4 specialist agents. Each builds `ResearchDeps` from state, runs its agent with `usage_limits=get_<domain>_limits()`, catches `Exception` and writes an `AnalystReport(error=str(exc))` into the single-element return list rather than raising.
  - `manager_node`: reads the 3-element `analyst_reports` list from post-fan-in state, passes through `format_analyst_reports(reports)`, runs `manager_agent` (Opus, zero tools), writes the resulting `ThesisOutput.model_dump()` into `thesis`.
  - `multi_agent_signal_node`: Phase-4-state-shaped signal node that projects `state["thesis"]` into the signal-agent prompt and writes the result into `state["signal"]`. Cloned from Phase-3's `signal_node` rather than shared to avoid state-shape coupling.
- **`build_multi_agent_pipeline(checkpointer: BaseCheckpointSaver | None)`** in `graph/pipeline.py`:
  ```
  START -> [fundamental, sentiment, technical]  (parallel fan-out)
       -> manager                               (fan-in via reducer)
       -> signal
       -> END
  ```
  Compile-time static (threat model T-04-09: no runtime graph modification). Accepts an optional checkpointer so Phase-7 memory can drop in a `PostgresSaver` without changing the signature.
- **Package re-exports** across `agents/__init__.py`, `graph/__init__.py`, `schemas/__init__.py`: every new Phase-4 symbol (5 agents, 5 node functions, 1 pipeline builder, 9 schemas, 1 state TypedDict) is importable from its top-level package without reaching into submodules.
- **Unit tests** (`tests/unit/test_multi_agent_nodes.py`, 26 tests): state schema shape, node async contract, happy-path state transitions for each of the 5 nodes, error-propagation-not-crash behavior on the analyst nodes, and no-regression assertions on Phase-1 (`extract_node`, `analyze_node`) and Phase-3 (`research_node`, `signal_node`) nodes.
- **Integration tests** (`tests/integration/test_multi_agent_pipeline.py`, 11 tests): 5 compilation tests (all three pipelines compile, topology shape checks), 4 TestModel end-to-end flow tests with `call_tools=[]` guards, 2 MemorySaver checkpointer tests. No real-LLM tests — deferred to phase UAT per cost rationale.

## Task Commits

1. **Task 1: MultiAgentPipelineState + analyst/manager nodes** — `90d8033`
   - `feat(04-03): MultiAgentPipelineState + parallel analyst/manager nodes`
   - Adds state TypedDict with reducer, 5 node functions (3 analyst + manager + signal adapter) with error-propagation, and the 26-test unit suite.
2. **Tasks 2-3: Pipeline builder + re-exports + integration test** — `676ae44`
   - `feat(04-03): build_multi_agent_pipeline + package re-exports + integration tests`
   - Adds `build_multi_agent_pipeline`, 3 `__init__.py` re-exports, and the 11-test integration suite.

Granularity deviation: the plan defined 4 tasks; two were bundled into `90d8033` (task 1 — schema/state + nodes) and two into `676ae44` (task 2 — pipeline builder + integration test). This is a smaller-than-ideal split but still atomic per commit (each commit is individually revertible; code + tests ship together).

## Files Created/Modified

**Created:**
- `tests/unit/test_multi_agent_nodes.py` — 26 tests in 321 lines
- `tests/integration/test_multi_agent_pipeline.py` — 11 tests in 215 lines

**Modified:**
- `src/ai_hedge_fund/schemas/state.py` — added MultiAgentPipelineState (+44 lines)
- `src/ai_hedge_fund/graph/nodes.py` — added 5 async node functions (+296 lines)
- `src/ai_hedge_fund/graph/pipeline.py` — added build_multi_agent_pipeline (+94 lines), existing builders untouched
- `src/ai_hedge_fund/agents/__init__.py` — re-exports (+23 lines)
- `src/ai_hedge_fund/graph/__init__.py` — re-exports (+24 lines)
- `src/ai_hedge_fund/schemas/__init__.py` — re-exports (+23 lines)

## Decisions Made

See `key-decisions` in frontmatter. Highlights:
- `operator.add` reducer (not a custom reducer).
- Analyst failures propagate into `analyst_reports` as error dicts, pipeline continues.
- `multi_agent_signal_node` is a new node, not a shared one.
- `TestModel(call_tools=[])` on all three specialist agents in integration tests (same Phase-3 pattern).
- No real-LLM pytest — Phase-level UAT is the right home for that.

## Deviations from Plan

1. **Two-commit split instead of four-commit per-task split**: plan had 4 tasks; they were bundled into 2 commits due to stream timeouts in the subagent dispatch. Each commit is atomic and revertible; no scope changes vs plan.
2. **test filename / location**: plan listed `tests/unit/test_multi_agent_nodes.py` (correct, matches) and `tests/integration/test_multi_agent_pipeline.py` (correct, matches). No renames.
3. **No `manager_node` reuse from Phase 3**: plan notes this. Confirmed — Phase 3 has no `manager_node`, so this plan creates it from scratch.

## Issues Encountered

1. **First subagent dispatch timed out with 0 commits.** Root cause: `.venv` corruption from prior concurrent worktree agents. `uv run pytest` hung indefinitely while uv tried to reconcile 10+ duplicate dist-info files and a `.pth` file missing its trailing newline. Fix: rebuilt `.venv` from scratch with `rm -rf .venv && uv sync`. Also set `workflow.use_worktrees=false` to prevent recurrence (committed as `5811ee0`).
2. **macOS `hidden` flag keeps re-attaching to `.pth` files.** On macOS, files inside a directory with `UF_HIDDEN` (which uv sets on `.venv/` deliberately, so Finder hides it) can inherit the hidden flag. Python's `site.py` silently skips hidden `.pth` files — so `ai_hedge_fund_editable.pth` gets skipped, the `src/` directory is never added to `sys.path`, and `import ai_hedge_fund` fails. Mitigation: `chflags nohidden .venv/lib/python3.13/site-packages/*.pth` before each pytest run. This should ideally be a project Makefile target or a `PostToolUse` hook; captured as a follow-up item below.
3. **Second subagent dispatch stream-timed out during Task 3 work.** Had completed Tasks 1-2 (committed as `90d8033`) and had Task 3 changes (pipeline + `__init__`s) + Task 4 changes (integration test) on disk uncommitted. Finished inline: reverted the unrelated `ruff format .`-induced changes in `archive/` and the broader src/tests reformatting (~183 files reformatted, only 5 files actually part of plan 04-03), committed the plan-04-03 changes as `676ae44`.
4. **`ruff format .` was too aggressive** — it reformatted 183 files including the entire `archive/` pre-pivot directory. Reverted those with `git checkout HEAD -- archive/` and reverted the unrelated src/tests reformatting with `git checkout HEAD -- <specific files>`. Remaining plan-scoped changes were clean.

## Pending Manual Verification

Deferred to phase-level UAT (Phase 4 gate):

- [ ] Real-LLM integration test: invoke `build_multi_agent_pipeline().ainvoke({"ticker": "AAPL", "as_of_date": "2025-01-02"})` against real Anthropic API + real SEC EDGAR credentials. Verify:
  - Exactly 3 elements appear in `analyst_reports` (one per specialist), each has the correct `analyst` field.
  - Each report's `analysis` dict validates against its respective schema (FundamentalAnalysis / SentimentAnalysis / TechnicalAnalysis).
  - Manager's `thesis` reconciles conflicting analyst views (e.g., bullish fundamentals + bearish sentiment) — look for explicit "I weighted X because Y" reasoning in the thesis text.
  - Final `signal` is consistent with `thesis` confidence.
- [ ] Cost-per-run measurement: log token usage across all 5 agents; confirm it stays within the configured UsageLimits and that the per-run total is reasonable (target: $0.30-0.80 per analysis).
- [ ] Fault-injection: force one of the Phase-2 data tools to raise (e.g., SEC EDGAR rate limit). Confirm pipeline continues to manager synthesis with 2/3 analyst reports present and an error-tagged third report.

## Follow-up Items (Not Blocking Phase 5)

- macOS `.pth` hidden-flag auto-clear: add a helper script `scripts/fix_venv_pth.sh` or a pre-pytest hook that runs `chflags nohidden .venv/lib/python3.13/site-packages/*.pth`. Low priority but will prevent recurrence of the import-broken state.
- Consider a `uv run` wrapper that doesn't trigger the editable install reconcile: `uv run` with `--no-sync` if the lockfile is already synced, since full `uv run` is what fragments the `.pth` when agents race.
- `ruff format` in CI should scope to the `src/` and `tests/` directories explicitly (e.g. `ruff format src/ tests/`) to avoid sweeping the `archive/` pre-pivot code. Same for `ruff check`.

## Self-Check: PASSED

**Files verified present:**
- `src/ai_hedge_fund/schemas/state.py` — 88 lines total, contains MultiAgentPipelineState
- `src/ai_hedge_fund/graph/nodes.py` — 386 lines, 5 new node functions verified via grep
- `src/ai_hedge_fund/graph/pipeline.py` — 158 lines, build_multi_agent_pipeline function verified
- `src/ai_hedge_fund/agents/__init__.py` — re-exports verified (12 matches for specialist agent names)
- `src/ai_hedge_fund/graph/__init__.py` — re-exports verified (6 matches for multi_agent symbols)
- `src/ai_hedge_fund/schemas/__init__.py` — re-exports verified (MultiAgentPipelineState present)
- `tests/unit/test_multi_agent_nodes.py` — 321 lines, 26 tests
- `tests/integration/test_multi_agent_pipeline.py` — 215 lines, 11 tests

**Commits verified:**
- `90d8033` — feat(04-03): MultiAgentPipelineState + parallel analyst/manager nodes (3 files, +659)
- `676ae44` — feat(04-03): build_multi_agent_pipeline + package re-exports + integration tests (5 files, +367)

**Test-suite status:**
- `tests/unit/test_multi_agent_nodes.py tests/integration/test_multi_agent_pipeline.py` — 37 passed, 0 failed in 428s.
- `tests/unit/` (excluding multi_agent_nodes) — 373 passed in 105s, no regressions.
- `tests/integration/test_research_pipeline.py` (Phase-3 no-regression) — ran as part of integration suite, compile tests passing.

## Next Plan Readiness

- **Phase 4 is ready for phase verification / UAT gate.** All 4 MULTI-XX requirements are now covered by either automatic tests (schema shape, node async contract, pipeline topology, error propagation) or captured manual UAT items (real-LLM output quality, cost measurement, fault injection).
- **Phase 5 (Adversarial Critique)** can extend `MultiAgentPipelineState` with `debate_points: Annotated[list[dict], operator.add]` using the same reducer pattern this plan established. Bull/bear agents hang off the manager output as parallel nodes; Act 3 rebuttal + Act 4 final + Act 5 synthesis are sequential nodes downstream.
- **No blockers.**

---
*Phase: 04-multi-agent-specialization*
*Completed: 2026-04-21*
