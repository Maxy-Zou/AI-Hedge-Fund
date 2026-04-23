---
phase: 07-memory-and-learning
plan: 03
subsystem: memory
tags: [langgraph, memory-integration, mem-01, mem-03, pipeline-composition, policy-sha-audit, phase-7]

# Dependency graph
requires:
  - phase: 07-memory-and-learning
    plan: 00
    provides: "tests/memory/ fixtures (beliefs_tmp_dir, memory_db_session, sample_episodic_csv_path with FUTUREX Pitfall-2 seed)"
  - phase: 07-memory-and-learning
    plan: 01
    provides: "EpisodicMemory model + query_episodic (mandatory as_of_date<=target filter) + seed_episodic_from_csv + _normalise_as_of"
  - phase: 07-memory-and-learning
    plan: 02
    provides: "Belief schema (extra=forbid, NOT frozen) + CritiqueEvent (frozen) + load_belief + belief_path_for_ticker (regex guard)"
  - phase: 06-risk-management
    provides: "RiskAssessment.policy_sha audit key — copied verbatim into EpisodicMemory.policy_sha column + payload by episodic_store_node"
provides:
  - "ai_hedge_fund.graph.memory_deps.MemoryDeps — frozen dataclass (db_session, beliefs_path, recall_limit=10) mirroring RiskDeps shape"
  - "ai_hedge_fund.graph.nodes.memory_recall_node — async, short-circuit-safe, temporal-filter-correct, human-edit-preserving, missing-belief-tolerant pre-fan-out recall"
  - "ai_hedge_fund.graph.nodes.episodic_store_node — async, short-circuit-safe; persists BOTH APPROVED and VETOED decisions; policy_sha audit column + payload copy"
  - "ai_hedge_fund.graph.pipeline.build_debate_pipeline(with_memory=..., memory_deps=...) — 4-variant topology (neither / memory-only / risk-only / both)"
  - "DebatePipelineState gains 3 single-writer keys: episodic_hits, beliefs_consulted, episodic_stored_id (NO operator.add reducer)"
affects: [07-04-self-critique, 07-05-integration-tests, 08-deployment]

# Tech tracking
tech-stack:
  added: []  # No new deps; consumes MemoryDeps + existing memory subpackage
  patterns:
    - "Closure-bound async wrapper registration (_memory_recall_bound / _episodic_store_bound) mirrors _risk_manager_bound idiom from Phase 6"
    - "Four-variant compile-time-static topology: memory × risk × neither (T-07-22 preserves the no-runtime-graph-modification invariant)"
    - "policy_sha authoritative-column + convenience-payload pattern for cross-phase audit (row.policy_sha is source of truth; payload copy survives round-trip for offline inspection)"
    - "VETOED-path persistence: research Open Question 1 shipped as code — vetoes flow through episodic_store before END alongside APPROVED, because vetoes are the richest learning signal"
    - "_normalise_as_of reuse at graph-node boundary — ISO string state -> DateTime column on SQLite is a recurring Rule-1 bug the helper solves once"

key-files:
  created:
    - "src/ai_hedge_fund/graph/memory_deps.py (MemoryDeps frozen dataclass, 46 lines)"
    - "tests/graph/test_memory_nodes.py (14 tests — 4 Task 1 + 10 Task 2)"
    - "tests/graph/test_pipeline_with_memory.py (9 tests — 6 structural + 3 end-to-end TestModel-stubbed)"
  modified:
    - "src/ai_hedge_fund/graph/nodes.py (imports for EpisodicMemory/MemoryDeps/belief_path_for_ticker/load_belief/_normalise_as_of/query_episodic; appended memory_recall_node + episodic_store_node AFTER risk_manager_node + route_after_risk, no existing-code mutation)"
    - "src/ai_hedge_fund/graph/pipeline.py (signature extended with with_memory + memory_deps; ValueError guard added; closure-bound node registration block; START fan-out + debate_synthesis-to-END branching rewritten to four-variant form; docstring updated)"
    - "src/ai_hedge_fund/schemas/state.py (appended 3 single-writer optional keys to DebatePipelineState — episodic_hits, beliefs_consulted, episodic_stored_id — with full docstrings)"
    - "tests/graph/conftest.py (re-exports 7 memory fixtures from tests/memory/conftest.py so tests/graph/* can consume them without duplication)"

key-decisions:
  - "MemoryDeps mirrors RiskDeps verbatim in shape — frozen dataclass with TYPE_CHECKING-only sqlalchemy.Session import keeps the module lightweight and the fixture injection ergonomic"
  - "The 3 new DebatePipelineState keys are SINGLE-writer (NO operator.add reducer). Test 4 locks the invariant via include_extras=True hint inspection — a future reducer introduction breaks the test"
  - "VETOED episodic rows ARE stored (research Open Question 1 recommendation). episodic_store_node fires regardless of risk_assessment.status — vetoes are the richest learning signal for Plan 07-04's self-critique loop"
  - "row.policy_sha (the EpisodicMemory column) is the AUTHORITATIVE audit SHA. The payload['risk_assessment']['policy_sha'] is a convenience snapshot. Test 12 asserts equality on every write; the contract document (docstring) tells consumers to read the column, not the payload"
  - "Memory-enabled topology routes BOTH signal and veto paths through episodic_store before END (not just signal). The conditional edge on risk_manager maps __end__ to episodic_store when with_memory=True, so vetoes flow through the storage node en route to END"
  - "as_of_date normalisation at the INSERT boundary (_normalise_as_of) rather than changing the state schema — DebatePipelineState intentionally carries as_of_date as an ISO string (JSON-serialisable for LangGraph checkpoints per Phase 3/5 contract); the graph node does the conversion on the DB boundary just like seed_episodic_from_csv"
  - "Missing belief files are NOT fatal. memory_recall_node returns beliefs_consulted=[] rather than raising FileNotFoundError — a brand-new ticker with no prior belief is a normal operational case (the offline Plan 07-04 writes the first belief)"
  - "Pipeline topology stays compile-time static (T-07-22 / T-05-19 / T-06-08). with_memory is a build-time boolean — no runtime plugin system, no user-supplied node names, no reflection"

patterns-established:
  - "Pattern: Closure-bound memory nodes — the async wrappers _memory_recall_bound / _episodic_store_bound are exactly one expression deep around the node, so the type-checker sees MemoryDeps explicitly without a global or module-level cache"
  - "Pattern: Four-variant topology builder — build_debate_pipeline(with_risk=?, with_memory=?) produces 4 byte-deterministic graphs; Phase-5 backcompat is preserved by defaulting both to False"
  - "Pattern: Graph-level Pitfall-2 regression — seeding a FUTURE-dated row (FUTUREX 2099-01-01) and running memory_recall_node end-to-end proves the temporal filter survives the wire-up (not just the query helper unit test)"
  - "Pattern: graph/conftest.py re-export shim — tests in tests/graph/* consume tests/memory/conftest.py fixtures via a single-line import block without sibling-directory test duplication"

requirements-completed: [MEM-01, MEM-03]

# Metrics
duration: 10m
completed: 2026-04-22
---

# Phase 7 Plan 03: Memory-Substrate Graph Integration Summary

**memory_recall_node (pre-fan-out, Pitfall-2-correct, human-edit-preserving) + episodic_store_node (post-signal/veto, persists BOTH APPROVED and VETOED rows with Phase-6 policy_sha audit linkage) + build_debate_pipeline extended to a 4-variant topology (memory × risk), with MemoryDeps + 3 single-writer DebatePipelineState keys. 23 new tests green; Phase 5/6/7 cross-phase regression 125/125.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-22T21:09:09Z
- **Completed:** 2026-04-22T21:19:24Z
- **Tasks:** 3 (all TDD: RED -> GREEN commits)
- **Files created:** 3 (`graph/memory_deps.py` + 2 test files)
- **Files modified:** 4 (`graph/nodes.py`, `graph/pipeline.py`, `schemas/state.py`, `tests/graph/conftest.py`)

## Accomplishments

- **MemoryDeps frozen dataclass:** 46 lines mirroring `RiskDeps` — `db_session`, `beliefs_path: Path`, `recall_limit: int = 10`. TYPE_CHECKING-only SQLAlchemy import keeps the module lightweight; frozen=True locks post-construction mutation; tests cover both default and custom recall_limit.
- **DebatePipelineState extended:** Three new optional keys appended (never reordered existing fields) — `episodic_hits: list[dict] | None`, `beliefs_consulted: list[dict] | None`, `episodic_stored_id: int | None`. Full per-key docstrings; ALL single-writer (NO `Annotated[..., operator.add]` reducer). Test 4 locks the invariant via `typing.get_type_hints(..., include_extras=True)`.
- **memory_recall_node (~75 lines):** Pre-fan-out node. Reads `ticker` + `as_of_date` + `candidate_metadata.sector` from state; calls `query_episodic(... , sector=..., ticker=..., limit=deps.recall_limit)` (mandatory `as_of_date <= target` via Plan 07-01's helper); loads `beliefs_path/tickers/<ticker>.yaml` + `beliefs_path/sectors/<sector>.yaml` via `load_belief`; returns `{"episodic_hits": [...], "beliefs_consulted": [...]}` as `model_dump(mode='json')` dicts. Short-circuits `{}` on upstream error. Missing belief files are tolerated (not fatal — returns `[]`). Invalid ticker-regex tolerated (skips belief lookup, recall still runs).
- **episodic_store_node (~60 lines):** Pipeline-end recorder (MEM-01 write path). Builds an `EpisodicMemory(record_type='analysis', ..., policy_sha=risk['policy_sha'], payload={...})` and commits. **Persists BOTH APPROVED and VETOED decisions** (07-RESEARCH.md Open Question 1 recommendation — vetoes are the richest learning signal for Plan 07-04). Short-circuits `{}` on upstream error. `row.policy_sha` IS the authoritative audit column; `row.payload['risk_assessment']['policy_sha']` is a convenience snapshot — test 12 asserts equality on every write.
- **build_debate_pipeline extended:** New kwargs `with_memory: bool = False, memory_deps: MemoryDeps | None = None` AFTER `risk_deps` (signature-order backcompat). ValueError guard mirrors `with_risk`. Closure-bound async wrappers register the two memory nodes. Four-variant topology:
  - `with_memory=False, with_risk=False` -> Phase-5 byte-for-byte unchanged
  - `with_memory=False, with_risk=True` -> Phase-6 byte-for-byte unchanged
  - `with_memory=True, with_risk=False` -> `START -> memory_recall -> [3 analysts] -> ... -> signal -> episodic_store -> END`
  - `with_memory=True, with_risk=True` -> conditional on `risk_manager` routes BOTH `signal` and `__end__` into `episodic_store` before END (vetoes ARE stored)
- **3 grep invariants verified:**
  - `signal -> END` occurs exactly 2x inside `build_debate_pipeline` (risk-only + no-kwargs)
  - `episodic_store -> END` occurs exactly 2x (one per memory-enabled branch)
  - `build_debate_pipeline()` no-kwargs compiles cleanly (`ai_hedge_fund.graph.pipeline.build_debate_pipeline; build_debate_pipeline(); print('OK')`)
- **23 new tests green** (14 `test_memory_nodes.py` + 9 `test_pipeline_with_memory.py`); **125 cross-phase tests** (tests/graph + tests/integration/test_debate_pipeline.py + tests/integration/test_phase6_e2e.py + tests/integration/test_policy_sha_audit.py + tests/memory) **all green**.

## Task Commits

Each task RED->GREEN:

1. **Task 1 RED — failing MemoryDeps + DebatePipelineState tests:** `ad73c7c` (test)
2. **Task 1 GREEN — MemoryDeps frozen dataclass + 3 single-writer state keys:** `222894c` (feat)
3. **Task 2 RED — failing memory_recall_node + episodic_store_node tests:** `a65728f` (test)
4. **Task 2 GREEN — memory_recall_node + episodic_store_node:** `a3c2647` (feat)
5. **Task 3 RED — failing build_debate_pipeline(with_memory=...) tests:** `105b5f2` (test)
6. **Task 3 GREEN — build_debate_pipeline extended with 4-variant topology:** `5cf5252` (feat)

## Files Created/Modified

- `src/ai_hedge_fund/graph/memory_deps.py` — NEW. 46 lines. `MemoryDeps(db_session, beliefs_path, recall_limit=10)`.
- `src/ai_hedge_fund/graph/nodes.py` — MODIFIED. Added 6 imports (EpisodicMemory, MemoryDeps, belief_path_for_ticker, load_belief, _normalise_as_of, query_episodic). Appended `memory_recall_node` + `episodic_store_node` at EOF (after `route_after_risk`). No pre-existing node touched.
- `src/ai_hedge_fund/graph/pipeline.py` — MODIFIED. Imports: added `MemoryDeps`, `episodic_store_node`, `memory_recall_node` (sorted alphabetically). Signature: added `with_memory: bool = False, memory_deps: MemoryDeps | None = None`. Body: added `with_memory` ValueError guard; added closure-bound node registration block; rewrote START fan-out with `if with_memory: ...else: ...`; rewrote `if with_risk: ...else: ...` debate_synthesis-to-END branching into a unified 4-variant block. Docstring extended with memory topology diagrams.
- `src/ai_hedge_fund/schemas/state.py` — MODIFIED. Appended 3 keys to `DebatePipelineState` (`episodic_hits`, `beliefs_consulted`, `episodic_stored_id`) with full per-key docstrings. Updated class-level docstring "Optional fields" block. NO reordering of existing fields. NO `Annotated[...]` reducer.
- `tests/graph/conftest.py` — MODIFIED. Added re-export shim `from tests.memory.conftest import ...` (7 memory fixtures). Existing Phase-6 fixtures (`golden_returns_df`, `seeded_portfolio_session`, `safe_policy`, `risk_deps`) preserved byte-for-byte.
- `tests/graph/test_memory_nodes.py` — NEW. 14 tests: 4 introspection (MemoryDeps frozenness, custom recall_limit, state-key presence, single-writer invariant) + 6 memory_recall (short-circuit, OR-predicate ticker+sector, Pitfall-2 FUTUREX regression at graph level, MEM-03 human-edit read path, OR composition across JNJ exclusion, missing-belief tolerance) + 4 episodic_store (row INSERT with full fields, policy_sha column=payload equality, VETOED-row persistence, short-circuit on error).
- `tests/graph/test_pipeline_with_memory.py` — NEW. 9 tests: 6 structural (no-kwargs backcompat, ValueError guard, memory-only node set, composed-with-risk node set, START fan-out topology, signal->episodic_store->END routing) + 3 end-to-end TestModel-stubbed (memory-only populates state, MEM-03 human-edit reaches state, policy_sha Phase-6->Phase-7 linkage).

## Decisions Made

All plan-specified decisions applied as written. Three worth highlighting:

1. **Closure-bound memory nodes registered AFTER the risk registration block, not before.** Reason: matches pipeline.py's code-layout convention (kwarg-driven node registrations accumulate top-to-bottom in signature-order) and makes the composed variant's flow easy to read top-down.
2. **Memory-enabled signal AND veto both flow through episodic_store.** The conditional edge on risk_manager maps `__end__ -> "episodic_store"` (not `END`) when `with_memory=True`. Vetoes are persisted because they are the richest learning signal (07-RESEARCH.md Open Question 1). Test 13 covers the stored VETOED row; test 22 covers the composed end-to-end APPROVED path.
3. **policy_sha authoritative column + convenience payload pattern.** `row.policy_sha` (the column) is the audit source of truth. `row.payload['risk_assessment']['policy_sha']` is a convenience copy for offline inspection. Every write keeps them equal (test 12 asserts equality byte-for-byte). Documented in `episodic_store_node` docstring so consumers read the column, not the payload.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] state['as_of_date'] is an ISO string; SQLite's DateTime binder rejects strings**

- **Found during:** Task 2 GREEN first run — `test_episodic_store_inserts_row_with_policy_sha_link` failed with `TypeError: SQLite DateTime type only accepts Python datetime and date objects as input.`
- **Issue:** `DebatePipelineState.as_of_date` is declared as `str` (ISO-8601) so LangGraph checkpoints are JSON-serialisable (Phase 3/5 contract). `EpisodicMemory.as_of_date` is `DateTime(timezone=True)` (from `DualTimestampMixin`). Passing the raw string produced a `StatementError` at INSERT time on SQLite. Plan 07-01 hit the same issue inside its own tests and fixed it with `_normalise_as_of`; the graph node had to do the same.
- **Fix:** Added `from ai_hedge_fund.memory.episodic import _normalise_as_of` to `graph/nodes.py` imports. Call `as_of_dt = _normalise_as_of(state["as_of_date"])` immediately before the `EpisodicMemory(...)` constructor and pass the normalised datetime instead of the raw string. No production schema change — consistent with the CSV seeder's boundary behaviour.
- **Files modified:** `src/ai_hedge_fund/graph/nodes.py`.
- **Committed in:** `a3c2647` (Task 2 GREEN commit).

**2. [Rule 3 — Blocking] Ruff I001 import-order on the two new test files.**

- **Found during:** Post-GREEN ruff check on Tasks 1, 2, 3.
- **Issue:** `from __future__ import annotations` + `os.environ.setdefault(...)` followed by `# noqa: E402` third-party imports trips ruff's I001 (un-sorted block). This is the same pattern used by `tests/graph/test_risk_node.py` and `tests/integration/test_phase6_e2e.py`.
- **Fix:** `ruff check --fix` auto-sorted the import block on each offending test file. Tests remained green after the autofix (14/14 and 9/9).
- **Files modified:** `tests/graph/test_memory_nodes.py`, `tests/graph/test_pipeline_with_memory.py`.
- **Committed in:** autofixed alongside the GREEN commits (`222894c`, `a3c2647`, `5cf5252`).

---

**Total deviations:** 2 local auto-fixes (1 Rule-1 bug, 1 Rule-3 blocking). No architectural or scope changes. No CLAUDE.md violations (the as_of_date normalisation preserves the project's "dual timestamps in UTC" convention).

## Issues Encountered

None beyond the two auto-fixed items above. The uv/macOS UF_HIDDEN bug documented in `.planning/phases/07-memory-and-learning/deferred-items.md` was anticipated — tests run under `.venv/bin/python -m pytest ...` after `chflags -R nohidden .venv/lib/python3.13/site-packages/*.pth`, exactly as prescribed by the previous Phase-7 plans.

## Threat Register Verification

All 6 STRIDE mitigations from the plan's `<threat_model>` verified by test coverage:

| Threat | Status | Evidence |
|--------|--------|----------|
| T-07-20 temporal leakage at graph level | mitigated | `test_memory_recall_excludes_future_dated_row_pitfall_2` seeds FUTUREX 2099-01-01 and asserts absence from `memory_recall_node` output for as_of_date=2026-06-01 |
| T-07-21 silent human-edit override | mitigated | `test_memory_recall_preserves_human_edited_belief_mem03_read` + `test_end_to_end_mem03_human_edit_reaches_state` cover the read path end-to-end; `human_edited=True` and `confidence=20` both survive into state['beliefs_consulted'] |
| T-07-22 EoP via runtime node registration | mitigated | `with_memory` is a compile-time boolean; `test_builder_no_kwargs_backcompat` asserts memory_recall/episodic_store absent by default; all four variants produce byte-deterministic graphs |
| T-07-23 DoS via oversized belief load | mitigated | Only two belief files loaded per recall (ticker + sector); `deps.recall_limit=10` default caps episodic hits. No pattern/strategy belief expansion (deferred per research Open Question 5) |
| T-07-24 incorrect policy_sha linkage Phase 6 -> 7 | mitigated | `test_episodic_store_policy_sha_authoritative_column_matches_payload` asserts `row.policy_sha == row.payload['risk_assessment']['policy_sha']`; `test_end_to_end_policy_sha_links_phase6_to_phase7` runs the full Phase-6 -> Phase-7 chain and asserts equality with the computed sha |
| T-07-25 VETOED disclosure | accepted | Vetoed thesis payloads contain the same data that was in memory during analysis; no new disclosure surface. Retention sweep (Plan 07-01) purges after 90 days. Low for v1 |

No new threat surface introduced beyond the plan's register — Threat Flags section omitted.

## Cross-phase Regression

```
chflags -R nohidden .venv/lib/python3.13/site-packages/*.pth
.venv/bin/python -m pytest tests/graph tests/integration/test_debate_pipeline.py \
    tests/integration/test_phase6_e2e.py tests/integration/test_policy_sha_audit.py \
    tests/memory -q
125 passed, 4 warnings in 1.21s
```

Phase 5 (debate pipeline), Phase 6 (risk), and earlier Phase 7 (memory substrate) suites untouched and green.

## User Setup Required

- **uv/macOS UF_HIDDEN workaround (inherited from 07-00):** `chflags -R nohidden .venv/lib/python3.13/site-packages/*.pth` before every `.venv/bin/python -m pytest ...` or `uv run --no-sync pytest ...`. Documented in `deferred-items.md`.
- **No new API keys or services.** Memory nodes operate on the existing SQLite/Postgres session + filesystem belief YAMLs. No network surface.

## Next Plan Readiness

- **Plan 07-04 (offline self-critique loop):** Can now consume `episodic_stored_id` rows (record_type='analysis', record_type='outcome' once Plan 07-04 ships) and use `write_belief` (Plan 07-02's chokepoint) without touching the live pipeline. The VETOED rows episodic_store_node persists are particularly valuable input — Plan 07-04 can critique vetoed decisions to discover policy-gap learning patterns.
- **Plan 07-05 (integration tests):** Can reuse the `_run_pipeline` TestModel-stub pattern from `test_pipeline_with_memory.py` and the seeded-session+beliefs_tmp_dir fixture shape. The 4-variant topology is frozen; 07-05 tests can focus on end-to-end scenarios without needing to assert graph structure.
- **No blockers.** The composed `with_risk=True` + `with_memory=True` topology is end-to-end proven via `test_end_to_end_policy_sha_links_phase6_to_phase7`.

## Self-Check: PASSED

Verified on disk (2026-04-22T21:19:24Z):

- `src/ai_hedge_fund/graph/memory_deps.py` contains `class MemoryDeps` + `@dataclass(frozen=True)`: FOUND
- `src/ai_hedge_fund/graph/nodes.py` contains `async def memory_recall_node` + `async def episodic_store_node` + `memory_recall_complete` + `episodic_store_complete` + `query_episodic(` + `EpisodicMemory(`: FOUND
- `src/ai_hedge_fund/graph/pipeline.py` contains `with_memory: bool = False` + `memory_deps: MemoryDeps | None = None` + `requires memory_deps` + `builder.add_node("memory_recall"` + `builder.add_node("episodic_store"`: FOUND
- `src/ai_hedge_fund/schemas/state.py` contains `episodic_hits` + `beliefs_consulted` + `episodic_stored_id`: FOUND. No new `Annotated[..., operator.add]` reducer added (actual reducer count on `analyst_reports` unchanged: 2).
- Function-scoped grep invariants:
  - `signal -> END` inside `build_debate_pipeline`: 2 (risk-only + no-kwargs)
  - `episodic_store -> END` inside `build_debate_pipeline`: 2 (one per memory-enabled branch)
- `build_debate_pipeline()` with no kwargs compiles cleanly: OK
- Commits `ad73c7c`, `222894c`, `a65728f`, `a3c2647`, `105b5f2`, `5cf5252` all present in `git log --oneline`.
- 23 Plan-07-03 tests + 102 Phase-5/6/earlier-7 regression tests = 125 green.
- Ruff clean on all 7 files (3 source + 2 test + 1 state + 1 conftest).

---
*Phase: 07-memory-and-learning*
*Completed: 2026-04-22*
