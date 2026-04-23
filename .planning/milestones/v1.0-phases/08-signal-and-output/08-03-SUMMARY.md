---
phase: 08-signal-and-output
plan: 03
subsystem: graph-pipeline-integration
tags: [phase-8, wave-2, graph, langgraph, interrupt, human-review, hitl, sig-01, sig-03, sig-04]

# Dependency graph
requires:
  - phase: 08-signal-and-output
    plan: 01
    provides: ReviewPolicy / ReviewDecision / FinalSignalOutput / assemble_final_signal / compute_review_policy_sha (consumed by output_node + human_review_node)
  - phase: 08-signal-and-output
    plan: 02
    provides: portfolio_view + audit_reconstruct (no overlap; this plan only consumes plan 02 transitively)
  - phase: 07-memory-and-learning
    plan: 03
    provides: episodic_store_node + with_memory pipeline kwarg + episodic_stored_id state key (Phase-8 chains episodic_store -> output)
  - phase: 06-risk-governance
    provides: route_after_risk + risk_manager_node + with_risk pipeline kwarg (Phase-8 composes with these on the VETO/APPROVED branches)
provides:
  - src/ai_hedge_fund/graph/review_deps.py (ReviewDeps frozen dataclass; XOR policy/policy_path)
  - src/ai_hedge_fund/graph/nodes.py::output_node (SIG-01 pure-Python FinalSignalOutput assembler)
  - src/ai_hedge_fund/graph/nodes.py::human_review_node (SIG-03 langgraph interrupt() primitive)
  - src/ai_hedge_fund/graph/nodes.py::review_store_node (SIG-04 record_type='review' append; T-08-05 append-only)
  - src/ai_hedge_fund/graph/nodes.py::route_before_review (fail-closed conditional router)
  - src/ai_hedge_fund/graph/pipeline.py::build_debate_pipeline (extended with with_output + with_review + review_deps; 4 new ValueError guards)
  - src/ai_hedge_fund/schemas/state.py::DebatePipelineState (extended with final_signal + review_decision + review_stored_id + _review_threshold)
affects: [08-04, 08-05, run_analysis-cli, e2e-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "langgraph.types.interrupt() literal invocation (T-08-03 -- greppable as defense-in-depth)"
    - "Command(resume=...) -> ReviewDecision.model_validate(...) at the resume boundary (T-08-04 schema enforcement)"
    - "Append-only review row via record_type='review' + linked_analysis_id (T-08-05 -- analysis row never mutated)"
    - "Fail-closed conditional router: missing threshold or signal -> human_review (stricter branch)"
    - "Closure-bound deps for graph nodes (mirror of Phase-6 / Phase-7 pattern)"
    - "Pipeline-builder normalises ReviewDeps once at build time (loads YAML if policy_path supplied) -- per-call I/O eliminated"
    - "Single-writer state keys with NO operator.add reducer (4 new keys -- final_signal, review_decision, review_stored_id, _review_threshold)"
    - "Surgical edge edits over file rewrites: episodic_store -> END becomes conditional on (not with_output) so Phase-7 backcompat is byte-preserved"

key-files:
  created:
    - "src/ai_hedge_fund/graph/review_deps.py"
    - "tests/graph/test_review_node.py"
    - "tests/graph/test_output_node.py"
    - "tests/graph/test_pipeline_review.py"
  modified:
    - "src/ai_hedge_fund/graph/nodes.py (added 4 new functions: output_node + human_review_node + review_store_node + route_before_review; +6 imports)"
    - "src/ai_hedge_fund/graph/pipeline.py (extended build_debate_pipeline with 3 new kwargs + 4 ValueError guards + node registration + 5 new edges)"
    - "src/ai_hedge_fund/schemas/state.py (added 4 new DebatePipelineState keys: final_signal, review_decision, review_stored_id, _review_threshold)"
    - "tests/graph/conftest.py (added portfolio_db_session alias re-export)"

key-decisions:
  - "Reuse existing langgraph.types.interrupt primitive instead of building a custom HITL channel -- T-08-03 mitigation; greppable in source"
  - "ReviewDeps mirrors MemoryDeps + RiskDeps shape (frozen dataclass, XOR policy/policy_path, TYPE_CHECKING imports for SQLAlchemy Session) -- single repository pattern across phases 6/7/8"
  - "Pipeline-builder normalises review_deps once at build time (loads YAML if policy_path supplied) -- avoids per-call I/O while keeping callers free to pass either form"
  - "_review_threshold is caller-injected state key (NOT bound at build time) -- mirrors Phase-6 risk_assessment dataflow + decouples threshold mutation from rebuild cycle"
  - "with_output ALWAYS requires review_deps (even when with_review=False) -- output_node needs review_policy_sha for the FinalSignalOutput contract; design contract is 'output requires review_deps; review requires output + checkpointer'"
  - "review_store_node fires on BOTH reviewed AND NOT_REQUIRED paths -- audit trail uniformity (Pitfall G); below-threshold signals get a review row with review_status='NOT_REQUIRED'"
  - "VETOED signals never reach review by construction -- route_after_risk ends the conditional at episodic_store; output_node short-circuits on missing signal; human_review_node short-circuits on the resulting error"
  - "route_before_review uses >= comparison (boundary value triggers review) and fails closed on missing threshold/signal (stricter branch -- never auto-approves with ambiguous state)"

# Tests / verification
tests:
  added: 45  # 31 in test_review_node.py + test_output_node.py (Task 1) + 14 in test_pipeline_review.py (Task 2)
  total_passing: 1071  # full suite minus 2 pre-existing pytest-asyncio failures (deferred-items 07-04)
  graph_subsuite: 101
  cross_phase_regression: 31  # test_debate_pipeline + test_phase6_e2e + test_policy_sha_audit + test_phase7_e2e + test_phase7_policy_sha_linkage all green
  notes: "2 pre-existing failures (test_research_pipeline.py async tests) are documented in .planning/phases/07-memory-and-learning/deferred-items.md and unrelated to Phase 8."

# Metrics
metrics:
  duration: ~13m
  completed: 2026-04-23T07:34:33Z
  task_count: 2
  file_count: 7  # 4 production + 3 test
  commits:
    - hash: 1466af5
      type: test
      title: "RED — review_node + output_node + review_store + route_before_review tests"
    - hash: 8492bc4
      type: feat
      title: "ReviewDeps + output_node + human_review_node + review_store_node + route_before_review"
    - hash: b4a8e0f
      type: test
      title: "RED — pipeline integration tests for with_output + with_review"
    - hash: 2e984c5
      type: feat
      title: "extend build_debate_pipeline with with_output/with_review/review_deps"
---

# Phase 8 Plan 08-03: Graph Pipeline Integration (HITL Interrupt + Output + Review Store)

Wires the four Phase-8 graph primitives (`output_node`, `human_review_node`, `review_store_node`, `route_before_review`) into `build_debate_pipeline` behind three new kwargs (`with_output`, `with_review`, `review_deps`). The human review gate uses the genuine `langgraph.types.interrupt()` primitive (T-08-03 non-negotiable per CLAUDE.md) -- not a log line, not a custom channel, not a polling loop.

## What was built

### ReviewDeps (`src/ai_hedge_fund/graph/review_deps.py`)

Frozen dataclass mirroring `MemoryDeps` + `RiskDeps` shape. Carries `db_session` plus exactly one of `policy` (preferred) or `policy_path` (loaded once at pipeline build). XOR enforced in `__post_init__`. `TYPE_CHECKING` imports for SQLAlchemy `Session` keep the runtime import surface minimal.

### Four new graph primitives (`src/ai_hedge_fund/graph/nodes.py`)

`output_node` (SIG-01) — Pure-Python assembly of `FinalSignalOutput` from authoritative state (`signal`, `thesis`, `risk_assessment`, `episodic_stored_id`). Stamps `review_policy_sha` from `deps.policy`. Short-circuits on upstream error / missing signal / missing episodic_id. Zero LLM (CLAUDE.md tool-first invariant).

`human_review_node` (SIG-03) — Builds the `review_request` dict (ticker + signal + thesis + 5-act debate + risk + episodic hits + beliefs) then calls `interrupt(review_request)`. The LangGraph checkpointer persists state; the caller resumes via `Command(resume=decision_dict)`. Validates the resumed payload via `ReviewDecision.model_validate` (T-08-04). Short-circuits on state error / missing final_signal.

`review_store_node` (SIG-04) — Appends a brand-new `EpisodicMemory` row with `record_type='review'` and `linked_analysis_id` referencing the analysis row (T-08-05 append-only). Fires on BOTH reviewed AND NOT_REQUIRED paths so the audit trail is uniform. Carries `policy_sha` (from risk) on the column and `review_policy_sha` (from review_decision or final_signal) in the payload.

`route_before_review` — Conditional router. Returns `human_review` when `conviction >= threshold` (boundary value triggers review); `review_store` when `conviction < threshold`. Fail-closed: missing `final_signal` or missing `_review_threshold` routes to `human_review` (stricter branch).

### DebatePipelineState extensions (`src/ai_hedge_fund/schemas/state.py`)

Four new single-writer keys with NO `operator.add` reducer:
- `final_signal: dict | None` — written by `output_node`
- `review_decision: dict | None` — written by `human_review_node` when gate fires
- `review_stored_id: int | None` — written by `review_store_node`
- `_review_threshold: int | None` — caller-injected; ephemeral; underscore-prefixed as builder-internal

### build_debate_pipeline extension (`src/ai_hedge_fund/graph/pipeline.py`)

Three new kwarg-only parameters (`with_output`, `with_review`, `review_deps`) plus four `ValueError` guards:

| Guard                                                | Mitigation |
|------------------------------------------------------|------------|
| `with_output=True` requires `with_memory=True`       | T-08-23 (no episodic_id for thesis_link) |
| `with_output=True` requires `review_deps`            | structural — output stamps review_policy_sha |
| `with_review=True` requires `with_output=True`       | structural — gate reads from final_signal |
| `with_review=True` requires `checkpointer is not None` | T-08-21 / Pitfall I — interrupt persists state via checkpointer |

Pipeline-builder normalises `review_deps` once at build time. If `policy_path` is supplied (vs `policy`), `load_review_policy` runs once and the resolved `ReviewDeps` is rebuilt with the loaded `policy`. Bound closures (`_output_bound`, `_review_store_bound`) capture this normalised deps so each node call avoids repeated YAML I/O.

The two existing `episodic_store -> END` edges (Phase-7 with_memory and Phase-7 with_memory + with_risk branches) are now conditional on `not with_output`. When `with_output=True`, a new tail block adds:

```
episodic_store -> output -> [route_before_review (if with_review) | review_store]
                            human_review -> review_store
                            review_store -> END
```

## Why this approach

**Reuse the LangGraph interrupt primitive over a custom HITL channel.** The LangGraph contract for HITL is documented and battle-tested: state checkpointed by the saver, resumed via `Command(resume=...)`. Building our own would duplicate state-persistence work and miss subtle integration points (token budgets, observability spans, durable execution). A grep for `interrupt(review_request)` is the canonical T-08-03 acceptance criterion -- one line of code, audit-friendly, can't be silently bypassed without a code review noticing.

**Single ReviewDeps shape across phases.** ReviewDeps mirrors `MemoryDeps` and `RiskDeps` byte-for-byte: frozen dataclass, `TYPE_CHECKING` SQLAlchemy import, optional `policy`/`policy_path` XOR. This matters because the pipeline-builder closure pattern is the same across Phase 6/7/8 -- the executor only reads three deps containers and binds three pairs of closures. Cognitive load stays flat as we add HITL.

**Audit-row uniformity.** `review_store_node` writes a row on BOTH the reviewed path AND the NOT_REQUIRED path. Skipping the row when conviction is below threshold would mean the audit reconstruct CLI (Plan 08-02) couldn't distinguish "no review needed" from "review row lost". Writing every time keeps the post-hoc reconstruction unambiguous (per Plan 08-02 SIG-04 contract).

**Fail-closed routing.** The `route_before_review` router defaults to `human_review` on any ambiguity (missing threshold, missing signal). The cost is occasional unwanted reviews when state is malformed; the benefit is no auto-approve on broken upstream. Mirrors the Phase-6 `route_after_risk` posture (defaults to `__end__` on missing risk_assessment).

**Caller-injected threshold.** `_review_threshold` lives in state, not on the deps -- callers (CLI in Plan 08-04, tests inject directly) seed it from `review_deps.policy.conviction_threshold`. This decouples threshold value from the pipeline rebuild cycle and matches the Phase-6 `risk_assessment` dataflow (state-carried, single-writer).

## Deviations from Plan

None of the auto-fix rules (1-3) fired. Plan was executed as written with two minor adaptations:

**1. [Task 1 small adjustment] Replaced bare `pytest.raises(Exception)` with `FrozenInstanceError`.**
- The plan's test_review_deps_is_frozen used `pytest.raises(Exception)` which ruff B017 flags as too broad. Switched to `dataclasses.FrozenInstanceError` -- behavior-equivalent and lint-clean.
- Files modified: `tests/graph/test_output_node.py`
- Commit: included in `8492bc4` (Task 1 GREEN)

**2. [Task 2 small addition] Added `test_vetoed_path_short_circuits_before_interrupt`.**
- Success criteria called out a VETOED-no-review test as part of Plan 08-03 invariants ("VETOED-no-review test passes"). The plan deferred the full e2e VETO->skip-review test to Plan 08-05 but a unit-level guarantee is cheap and worth shipping now. Drives `human_review_node` directly with a VETO-style state and asserts the empty-dict short-circuit. The graph-level e2e remains a Plan 08-05 deliverable.
- Files modified: `tests/graph/test_pipeline_review.py`
- Commit: included in `2e984c5` (Task 2 GREEN)

## Verification

```
$ uv run --no-sync pytest tests/graph -q
101 passed, 4 warnings in 0.72s

$ uv run --no-sync pytest tests/integration/test_phase7_e2e.py tests/integration/test_phase7_policy_sha_linkage.py tests/integration/test_debate_pipeline.py tests/integration/test_phase6_e2e.py tests/integration/test_policy_sha_audit.py -q
31 passed, 4 warnings in 2.76s

$ uv run --no-sync pytest tests -q --ignore=tests/integration/test_checkpointer.py
2 failed, 1071 passed, 6 skipped, 7 warnings in 20.10s
# 2 failures are pre-existing pytest-asyncio issues -- see deferred-items 07-04

$ uv run --no-sync ruff check src/ai_hedge_fund/graph/ src/ai_hedge_fund/schemas/state.py tests/graph/
All checks passed!

$ grep -c "interrupt(review_request)" src/ai_hedge_fund/graph/nodes.py
1  # T-08-03 mitigation: greppable as defense-in-depth
```

## Threat Mitigations Discharged

| Threat ID | Status | Evidence |
|-----------|--------|----------|
| T-08-03 | mitigated | `human_review_node` calls `interrupt(review_request)`; verified by source grep (`tests/graph/test_review_node.py::test_interrupt_primitive_is_invoked_in_source`) |
| T-08-04 | mitigated | `ReviewDecision.model_validate` raises `ValidationError` on bad payloads (`test_malformed_resume_raises`) |
| T-08-05 | mitigated | `review_store_node` appends a new row; analysis row byte-identical after run (`test_analysis_row_unchanged_after_review_store`) |
| T-08-06 | mitigated (architectural) | `route_after_risk` ends conditional at `episodic_store` on VETO; `output_node` short-circuits on missing signal; `human_review_node` short-circuits on the resulting error (`test_vetoed_path_short_circuits_before_interrupt`) |
| T-08-21 | mitigated | `with_review=True` without `checkpointer` raises ValueError (`test_with_review_requires_checkpointer`) |
| T-08-22 | mitigated | `ReviewDeps` is frozen dataclass; `ReviewPolicy` is frozen + extra='forbid'; `compute_review_policy_sha` is deterministic |
| T-08-23 | mitigated | `with_output=True` without `with_memory=True` raises ValueError (`test_with_output_requires_with_memory`) |
| T-08-24 | accepted (by design) | Missing `_review_threshold` routes to human_review (fail-closed) -- documented in `route_before_review` docstring |

## What's next (08-04)

Plan 08-04 ships the `run_analysis` CLI that drives the composed pipeline (Phase 5+6+7+8) end-to-end. The CLI:
- Loads `RiskPolicy` + `ReviewPolicy` from `config/`
- Builds the pipeline with `with_risk=True, with_memory=True, with_output=True, with_review=True` + a `PostgresSaver` checkpointer
- Seeds initial state with `_review_threshold=review_policy.conviction_threshold`
- On `__interrupt__`, prompts the operator via stdin (uses `format_review_request_md` from Plan 08-01) and resumes via `Command(resume=ReviewDecision(...))`

Plan 08-05 ships the integration tests that exercise the full HITL loop end-to-end (high-conviction interrupt + APPROVED resume; low-conviction skip; VETOED -> never reaches review).

## Self-Check: PASSED

- `src/ai_hedge_fund/graph/review_deps.py` exists
- `src/ai_hedge_fund/graph/nodes.py` contains `output_node`, `human_review_node`, `review_store_node`, `route_before_review` (each greppable count = 1)
- `src/ai_hedge_fund/graph/pipeline.py` contains `with_output`, `with_review`, `review_deps`, `route_before_review`, `load_review_policy`
- `src/ai_hedge_fund/schemas/state.py` contains `final_signal`, `review_decision`, `review_stored_id`, `_review_threshold` (each greppable count = 1)
- All 4 commits exist in git log: `1466af5` (RED 1), `8492bc4` (GREEN 1), `b4a8e0f` (RED 2), `2e984c5` (GREEN 2)
- `grep -c "interrupt(review_request)" src/ai_hedge_fund/graph/nodes.py` = 1 (T-08-03)
