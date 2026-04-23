---
phase: 07-memory-and-learning
plan: 05
subsystem: memory
tags: [integration, phase-gate, mem-01, mem-02, mem-03, mem-04, policy-sha-audit, testmodel-stubs, phase-7]

# Dependency graph
requires:
  - phase: 07-memory-and-learning
    plan: 00
    provides: "tests/memory/conftest.py fixtures (memory_db_session, beliefs_tmp_dir, sample_episodic_csv_path, belief YAMLs including AAPL_human.yaml for MEM-03)"
  - phase: 07-memory-and-learning
    plan: 01
    provides: "EpisodicMemory model + append-only contract + policy_sha column + seed_episodic_from_csv + query_episodic temporal filter"
  - phase: 07-memory-and-learning
    plan: 02
    provides: "Belief schema + load_belief + write_belief (MEM-03 chokepoint) + belief_path_for_ticker (regex guard)"
  - phase: 07-memory-and-learning
    plan: 03
    provides: "build_debate_pipeline(with_memory=...) 4-variant topology + memory_recall_node + episodic_store_node (VETOED persistence + policy_sha linkage column)"
  - phase: 07-memory-and-learning
    plan: 04
    provides: "ingest_outcome async CLI + compute_new_confidence + self_critique_agent (RationaleOnly)"
  - phase: 06-risk-management
    plan: 06
    provides: "RiskAssessment.policy_sha authoritative audit key (Phase-6 compute_policy_sha + 6 audit tests; Phase 7 builds on this by asserting EpisodicMemory.policy_sha equality)"

provides:
  - "tests/integration/test_phase7_e2e.py (8 end-to-end scenarios: with_memory only, composed with_memory+with_risk, VETOED persistence, MEM-03 read, MEM-04 write, MEM-03 x MEM-04 interaction, Pitfall-2 temporal regression, Phase-5 backcompat smoke)"
  - "tests/integration/test_phase7_policy_sha_linkage.py (6 policy_sha audit linkage tests: same-policy equality, different-policy sensitivity, revert idempotence, 64-hex format on APPROVED, 64-hex format on VETOED, three-way cross-layer equality)"
  - "tests/integration/conftest.py (re-export shim for the 7 memory fixtures so Phase-7 integration tests can consume them without duplication — pytest fixture-discovery pattern that also sidesteps the F811 false-positive from direct module imports)"
affects: []  # Plan 07-05 is the phase gate; no downstream plans in Phase 7

# Tech tracking
tech-stack:
  added: []  # Zero new production code; tests only. All composition was wired in 07-01..07-04.
  patterns:
    - "ExitStack all-agents stubbing pattern: single helper (_stubbed_stack) layers 12 agent.override contexts so every test body gets a zero-LLM-call run with one line"
    - "Integration-conftest re-export pattern: tests/integration/conftest.py re-exports tests/memory/conftest.py fixtures via import — pytest's fixture-discovery walks upward from the test file to find a sibling conftest, so this avoids the F811 false-positive that arises from importing fixtures directly into a test module"
    - "Phase-gate plan pattern (zero new source code): shipped two integration test files that prove the COMPOSITION works. The TDD gate is satisfied by the plan being a GREEN-landed TestModel stub stack on already-wired code — the 199 new tests are the feature"
    - "12-agent TestModel stack: fundamental/sentiment/technical get call_tools=[]; bear gets _valid_bear_case() (WR-01); risk_manager + self_critique get custom_output_args={'rationale': ...}; others use TestModel() default (confidence=0 maps to low conviction -> APPROVED under safe policy)"
    - "Policy-copy + seeder pattern: tests construct a VETOED scenario by doing policy.model_copy(update={'excluded_sectors': ['Technology']}) and running the pipeline with a Technology ticker — deterministic veto without touching portfolio shape"

key-files:
  created:
    - "tests/integration/test_phase7_e2e.py (389 lines; 8 test functions)"
    - "tests/integration/test_phase7_policy_sha_linkage.py (277 lines; 6 test functions)"
    - "tests/integration/conftest.py (23 lines; re-exports 7 fixtures from tests/memory/conftest.py)"
  modified:
    - ".planning/phases/07-memory-and-learning/07-VALIDATION.md (nyquist_compliant: true; wave_0_complete: true; Per-Task Verification Map populated with all 15 Plan 07-00..07-05 task rows; Wave-0 checklist ticked; Validation Sign-Off checklist ticked)"
    - ".planning/phases/07-memory-and-learning/deferred-items.md (logged pre-existing ruff I001 in tests/memory/test_episodic_model.py from 07-01 — unrelated to Plan 07-05)"

key-decisions:
  - "Phase-gate plan treated as 'test(...)' conventional-commit only — NO new production code. The composition being tested was wired by 07-01 (query_episodic / append-only), 07-02 (write_belief chokepoint), 07-03 (4-variant topology + memory_recall_node + episodic_store_node), and 07-04 (ingest_outcome + self_critique_agent). Plan 07-05's deliverable is proving the COMPOSITION via 14 integration tests."
  - "Created tests/integration/conftest.py re-export shim instead of duplicating memory fixture definitions. Mirrors tests/graph/conftest.py's pattern — solves the F811 false-positive ruff raises when test modules import fixtures directly. Fixture discovery goes via pytest's sibling-conftest walk, not via Python import."
  - "Helper _stubbed_stack() NOT extracted to conftest.py despite Task-2's suggestion. The two test files each define their own copy (with different self_critique rationale args) because self_critique_agent is only used by ingest_outcome in test_phase7_e2e.py (MEM-04 test), and the policy_sha file's helper intentionally uses minimal 'r' rationale strings. Keeping helpers per-file avoids a leaky abstraction — conftest.py would need a parametrised factory that readers then have to reason about. Duplicated ~60 lines across the two files; acceptable for clarity."
  - "test_phase5_backcompat_no_kwargs asserts ABSENCE of memory + risk nodes AND PRESENCE of the full Phase-5 debate chain (10 nodes). Tighter regression than just 'does it compile' — catches a future refactor that drops a Phase-5 node by mistake."
  - "VETOED persistence test uses excluded_sectors=['Technology'] + AAPL (Technology) rather than a conviction-triggered position-size veto. Exclusion vetoes are deterministic under TestModel stubs — conviction-triggered vetoes depend on LLM-authored thesis.confidence which TestModel() defaults to 0 (low conviction, low size, no veto). Exclusion deterministic, confidence-dependent not."
  - "Ruff I001 in tests/memory/test_episodic_model.py documented as pre-existing (last touched in commit 4f45518 from Plan 07-01) and deferred to a future cleanup chore. Plan 07-05's new files are all ruff-clean in isolation."

# Threat register (closing)
requirements-completed:
  - MEM-01  # End-to-end: episodic recall (temporal-filter-correct) + append-only store (APPROVED + VETOED) proven via composed pipeline runs
  - MEM-02  # Belief read-round-trip proven via state['beliefs_consulted'] end-to-end (ticker-level belief loaded through memory_recall_node and asserted in final state)
  - MEM-03  # Full closure: read path (human_edited=true + confidence=20 reach beliefs_consulted) + write-side guard (ingest_outcome skips confidence but updates critique_history)
  - MEM-04  # Full loop end-to-end: outcome ingest updates plain belief (72 -> 82 via deterministic math + LLM rationale via TestModel stub) AND outcome ingest preserves human-edited belief (confidence stays 20, skip audited)

# Metrics
duration: 7m
completed: 2026-04-22
---

# Phase 7 Plan 05: Integration Test Suite + Phase Gate Summary

**Shipped 2 integration test files (14 tests) + tests/integration/conftest.py. 8 e2e scenarios prove MEM-01..04 + MEM-03 x MEM-04 + Pitfall-2 + Phase-5 backcompat. 6 policy_sha linkage tests prove Phase 6 -> Phase 7 audit chain (deterministic, change-sensitive, idempotent, format-correct on APPROVED + VETOED, three-way equal). Zero new production code — the 199 Phase-7 tests are the feature. Full suite: 920 passed, 9 skipped, 2 pre-existing baseline failures.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-04-22T21:40:24Z
- **Completed:** 2026-04-22T21:47:10Z
- **Tasks:** 3 (Task 1 + Task 2 each shipped a test file; Task 3 ran the full regression suite + validation sign-off)
- **Files created:** 3 (2 integration test files + 1 integration conftest)
- **Files modified:** 2 (validation sign-off + deferred-items)

## Accomplishments

### Task 1 — tests/integration/test_phase7_e2e.py (8 scenarios, 389 lines)

Each scenario stubs all 12 agents (fundamental, sentiment, technical, manager, bull, bear, rebuttal, final_arguments, debate_synthesis, risk_manager, signal, self_critique) via `TestModel` inside a shared `_stubbed_stack()` `ExitStack`:

1. **`test_with_memory_loads_episodic_hits_and_beliefs`** — seeds the 10-row episodic CSV + AAPL belief fixture, runs `build_debate_pipeline(with_memory=True)`, asserts episodic_hits is non-empty with all hits dated `<= 2026-04-20`, beliefs_consulted includes the AAPL ticker-level belief, and a NEW episodic row with `record_type='analysis'` has been persisted. Proves the MEM-01 read + MEM-02 belief-read + MEM-01 write triad end-to-end in one run.
2. **`test_composed_with_risk_persists_episodic_with_policy_sha`** — composed `with_risk=True, with_memory=True` run on PG/Consumer-Staples. Asserts `final_state['risk_assessment']['policy_sha']` is non-empty, `episodic_stored_id` is an int, and the stored row's column + payload SHA BOTH equal the state's SHA. This is the canonical Phase 6 -> Phase 7 audit link.
3. **`test_vetoed_decision_is_persisted_end_to_end`** — Open-Question-1 ratification. Uses `policy.model_copy(update={'excluded_sectors': ['Technology']})` + AAPL (Technology) for a deterministic exclusion veto under TestModel stubs. Asserts `risk_assessment.status=='VETOED'`, `signal is None` (Pitfall 8), AND `episodic_stored_id` is set (the row IS still written — vetoes are the richest learning signal).
4. **`test_human_edited_belief_survives_pipeline_read`** — MEM-03 read path. Copies `beliefs_tmp_dir/tickers/AAPL_human.yaml` over `AAPL.yaml` BEFORE the run, runs the pipeline, asserts `beliefs_consulted[0].human_edited is True` and `beliefs_consulted[0].confidence == 20`. The human's value survives the analysts' consumption.
5. **`test_outcome_ingest_updates_plain_belief`** — MEM-04 full write loop. Seeds a linked analysis row + runs `ingest_outcome(outcome_pct=+4.2, as_of_date=2026-04-20)` under a TestModel stub that returns `rationale='stubbed MEM-04 rationale'`. Reloads the belief YAML: confidence moved `72 -> 82` (deterministic `compute_new_confidence(72, +4.2, 'long') = 72 + min(0.3 * 4.2 * 10, 10) = 72 + 10 = 82`), and the last critique_history entry has the stubbed rationale with `source='self_critique'`.
6. **`test_outcome_ingest_preserves_human_edited_belief`** — MEM-03 x MEM-04 interaction. Starts with the human-edited variant + runs ingest_outcome. Reloads belief: confidence STAYS 20. The return dict's `skipped['confidence']` is `'human_edited_global_flag_set'`. `critique_history` IS updated (audit trail matters). And the outcome row still landed (operational fact preserved).
7. **`test_pipeline_never_returns_future_dated_episodic_hits`** — Pitfall-2 regression at integration tier. Seeds FUTUREX at 2099-01-01; queries with as_of='2026-06-01'. Asserts no returned hit's `as_of_date` starts with `'2099'`. This is a pipeline-integration regression — the unit test in Plan 07-01 proves `query_episodic`, but this proves memory_recall_node wired via MemoryDeps also respects the filter.
8. **`test_phase5_backcompat_no_kwargs_still_compiles`** — tighter than a pure compile smoke: asserts memory + risk nodes are ABSENT AND all 10 Phase-5 nodes (fundamental/sentiment/technical/manager/bull/bear/rebuttal/final_arguments/debate_synthesis/signal) are PRESENT. Future refactors that drop a Phase-5 node by mistake will fail here.

### Task 2 — tests/integration/test_phase7_policy_sha_linkage.py (6 tests, 277 lines)

Mirrors `tests/integration/test_policy_sha_audit.py`'s six-scenario structure but targets `EpisodicMemory.policy_sha` (Phase 7 column) instead of the Phase 6 RiskAssessment alone:

1. **`test_same_policy_same_episodic_sha`** — two runs with the SAME fixture policy produce stored rows whose `policy_sha` both equal `compute_policy_sha(policy)`. Deterministic fingerprinting.
2. **`test_different_policy_different_episodic_sha`** — increment `max_single_position_pct` by 1.0; assert the two stored rows have DIFFERENT 64-char hex SHAs. Change sensitivity.
3. **`test_idempotent_revert`** — run policy_a, policy_b, policy_a. Rows 1 and 3 match byte-for-byte; row 2 differs. Revert idempotence (same as Phase-6 test 6, reflected to the Phase-7 column).
4. **`test_sha_format_on_approved`** — `SHA_RE.fullmatch(row.policy_sha)` + lowercase assertion on an APPROVED run.
5. **`test_sha_format_on_vetoed`** — same format check on a VETOED row (Open-Question-1 ratified — the SHA is present even when the signal is not).
6. **`test_three_way_sha_equality`** — three-way equality: `state['risk_assessment']['policy_sha'] == row.policy_sha == row.payload['risk_assessment']['policy_sha'] == compute_policy_sha(policy)`. Locks the cross-layer audit contract end-to-end; any silent transformation layer fails this test.

### Task 3 — full regression + validation sign-off

- Phase 7 subsuites: **162** memory + **23** graph + **14** integration = **199** Phase-7 tests green.
- Cross-phase regression: **17** Phase 5/6 integration tests (debate + phase6_e2e + policy_sha_audit) + **122** graph/risk tests all still green. No new failures introduced.
- Full `uv run pytest -q`: **920 passed, 9 skipped, 2 failed** (the 2 pre-existing `test_research_pipeline.py` async tests missing `pytest-asyncio`, documented in both `06-06-SUMMARY.md` and `07-04-SUMMARY.md`).
- Ruff clean on all three Plan-07-05 files in isolation. Pre-existing I001 in `tests/memory/test_episodic_model.py` (from Plan 07-01) documented in `deferred-items.md` per scope-boundary rule.
- 07-VALIDATION.md: `nyquist_compliant: true`, `wave_0_complete: true`, Per-Task Verification Map populated with 15 rows (all Plan 07-00..07-05 tasks), Wave-0 checklist ticked, Validation Sign-Off ticked, approval stamped.

## Task Commits

1. **Task 1 — `e2a5a4a`** `test(07-05): add Phase 7 end-to-end integration scenarios` — 2 files, +470 lines
2. **Task 2 — `5f6285a`** `test(07-05): add Phase 6 -> Phase 7 policy_sha audit linkage tests` — 1 file, +297 lines
3. **Task 3 — `da57605`** `docs(07-05): Phase 7 validation sign-off + ruff deferral` — 2 files modified

## Files Created/Modified

- **`tests/integration/test_phase7_e2e.py`** — NEW. 389 lines (post ruff-format). 8 test functions, one helper (`_stubbed_stack` for 12 agents), one tiny fixture helper (`_initial_state`), one returns-df helper.
- **`tests/integration/test_phase7_policy_sha_linkage.py`** — NEW. 277 lines. 6 test functions, `_stubbed_stack` (duplicated minimally vs. e2e, per decision above), `_run` helper for the common pipeline invocation, `SHA_RE` regex.
- **`tests/integration/conftest.py`** — NEW. 23 lines. Re-exports 7 memory fixtures from `tests/memory/conftest.py` so integration tests consume them via pytest's sibling-conftest discovery rather than direct import (avoids F811).
- **`.planning/phases/07-memory-and-learning/07-VALIDATION.md`** — MODIFIED. Frontmatter flipped (`nyquist_compliant: true`, `wave_0_complete: true`, `status: complete`, `completed: 2026-04-22` added). Per-Task Verification Map populated with 15 task-row entries (07-00 T1-T3, 07-01 T1-T3, 07-02 T1-T2, 07-03 T1-T3, 07-04 T1-T3, 07-05 T1-T3), all `✅ green`. Wave-0 Requirements checklist ticked with pointers to the actual shipped paths. Validation Sign-Off section ticked with approval note.
- **`.planning/phases/07-memory-and-learning/deferred-items.md`** — MODIFIED. Appended a 07-05 entry for the pre-existing ruff I001 in `tests/memory/test_episodic_model.py` (from Plan 07-01 commit 4f45518; verified pre-existing via `git stash` + re-run).

## Decisions Made

All plan-specified decisions applied as written. Four worth highlighting:

1. **Phase-gate plan is 'test(...)' only, no feat commits.** Plan 07-05's objective was to prove the composition of 07-01..07-04's already-wired code end-to-end. Wiring existed; the deliverable is the integration tests asserting it. No RED/GREEN TDD cycle was needed — the tests were shipped directly as passing assertions on existing behaviour. This is a documented "phase gate" shape: similar to how Phase 6's `test_policy_sha_audit.py` landed (also test-only commit on existing wired code).
2. **Created `tests/integration/conftest.py` re-export shim instead of duplicating fixtures or accepting F811.** Mirrors `tests/graph/conftest.py`'s pattern from Plan 07-03. Pytest's fixture discovery walks upward from the test file to find a sibling `conftest.py`, so fixtures imported there are auto-injected into every test in `tests/integration/*` without the test modules needing to import them directly. Direct imports cause F811 ("redefined here") because the fixture name appears both as a module-level import and as a function parameter — the conftest route avoids this entirely.
3. **`_stubbed_stack()` NOT extracted to conftest.** The two test files each carry their own copy (~60 lines each). The reason: `test_phase7_e2e.py` passes a specific `rationale='stubbed MEM-04 rationale'` to `self_critique_agent.override` so test 5 can assert on the exact string, while `test_phase7_policy_sha_linkage.py` uses a minimal `'r'` rationale because the tests don't care about the self-critique content. A shared helper would need a parametrised factory, which readers would then have to reason about. Duplicated ~60 lines is acceptable for clarity — the two copies diverge by exactly two literals.
4. **VETOED scenario uses `excluded_sectors` rather than a confidence-triggered position-size veto.** TestModel defaults `ThesisOutput.confidence=0` which maps to "low" conviction and a size below `max_single_position_pct`, so a conviction-triggered veto would never fire under the default stub. Exclusion vetoes fire deterministically regardless of LLM output — same approach Phase-6 `test_phase6_e2e.py` uses for its position-size-veto scenario 2.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] F811 ruff errors from direct fixture imports in the test module.**

- **Found during:** Task 1 post-write ruff check.
- **Issue:** Initially imported `memory_db_session`, `beliefs_tmp_dir`, `sample_episodic_csv_path` directly from `tests.memory.conftest` into `test_phase7_e2e.py`. Ruff F811 flagged every test function that named those fixtures as parameters ("redefined here"). This is a known false-positive vs. the pytest-fixture-injection pattern, but the standard fix is to route fixtures through a sibling `conftest.py` so pytest's discovery picks them up without a module-level import.
- **Fix:** Created `tests/integration/conftest.py` (23 lines) that re-exports the 7 memory fixtures from `tests/memory/conftest.py`. Removed the direct imports from `test_phase7_e2e.py`. Ruff F811 cleared; all 8 tests still pass. Mirrors exactly the pattern `tests/graph/conftest.py` used in Plan 07-03.
- **Files modified:** `tests/integration/test_phase7_e2e.py` (imports cleaned), `tests/integration/conftest.py` (new).
- **Committed in:** `e2a5a4a` (Task 1 commit).

**2. [Rule 3 — Blocking] Unused `pytest` import in the test module.**

- **Found during:** Task 1 post-write ruff check (same pass).
- **Issue:** Initial template included `import pytest` but no test actually referenced `pytest` (no `@pytest.fixture`, no `pytest.raises`). Ruff F401 flagged it.
- **Fix:** Removed the unused import. Noted for future: test files that only use synchronous `asyncio.run(...)` and `assert` statements don't need pytest imports.
- **Files modified:** `tests/integration/test_phase7_e2e.py`.
- **Committed in:** `e2a5a4a`.

### Out-of-Scope Issues (documented, not fixed)

**3. [Scope Boundary — deferred] Pre-existing ruff I001 in `tests/memory/test_episodic_model.py`.**

- **Found during:** Task 3 ruff sweep across Phase-7 files.
- **Issue:** `I001 Import block is un-sorted or un-formatted` on the import block in `tests/memory/test_episodic_model.py`.
- **Verified pre-existing:** `git log --oneline -1 tests/memory/test_episodic_model.py` shows commit `4f45518 feat(07-01): add EpisodicMemory model + Alembic 003`. Ran `git stash && ruff check tests/memory/test_episodic_model.py` on main — error persists without Plan 07-05's changes.
- **Why not fixed:** Pre-existing, out of scope for Plan 07-05. Auto-fixable with `ruff check --fix` in a future cleanup chore. Not a correctness issue — the file's 7 tests remain green.
- **Files modified:** `.planning/phases/07-memory-and-learning/deferred-items.md` (07-05 entry appended).
- **Committed in:** `da57605`.

**4. [Scope Boundary — documented] 2 pre-existing `test_research_pipeline.py` async test failures.**

- **Found during:** Task 3 full `uv run pytest -q` run.
- **Issue:** Same as documented in Plan 07-04 SUMMARY: `test_research_agent_with_test_model` and `test_signal_agent_with_test_model` fail because `pytest-asyncio` is not installed. `pyproject.toml` references `asyncio_mode` (`PytestConfigWarning: Unknown config option: asyncio_mode`) but the plugin is missing.
- **Why not fixed:** Out of scope for Phase 7; documented in `deferred-items.md` 07-04 entry already. Phase-7 tests all use `asyncio.run(...)` on synchronous test bodies, which sidesteps the plugin.
- **Committed in:** n/a — pre-existing documentation holds.

**Total deviations:** 2 local auto-fixes (both Rule-3 blocking) + 2 pre-existing out-of-scope issues documented. Zero architectural or scope changes. No CLAUDE.md violations.

## Issues Encountered

- The uv/macOS UF_HIDDEN workaround from Plan 07-00 continues to be required: `chflags -R nohidden .venv/lib/python3.13/site-packages/*.pth` before every test run. Applied consistently.
- Initial F811 + F401 issues in the first test file; both auto-fixed during Task 1 and committed in the Task 1 commit.
- No blockers.

## Threat Register Verification

All 4 STRIDE mitigations from the plan's `<threat_model>` verified by test coverage:

| Threat | Status | Evidence |
|--------|--------|----------|
| T-07-50 Cross-phase policy_sha drift | mitigated | `test_three_way_sha_equality` asserts `state['risk_assessment']['policy_sha'] == row.policy_sha == row.payload['risk_assessment']['policy_sha'] == compute_policy_sha(policy)` — any silent transformation fails. Complementary: the 6 linkage tests (deterministic + change-sensitive + idempotent + format-on-APPROVED + format-on-VETOED) lock the full cross-phase contract. |
| T-07-51 Integration tests accept real LLM calls | mitigated | All 12 agents stubbed via `agent.override(model=TestModel(...))` in every scenario. `grep -c "agent.override\|TestModel(" tests/integration/test_phase7_*.py` shows one override per agent per scenario. Tests run under `ANTHROPIC_API_KEY=test-key-for-unit-tests`; no network calls. `uv run pytest tests/integration/test_phase7_*.py` completes in ~2s (no LLM latency). |
| T-07-52 Test fixtures leak into production | accept | Fixtures stay under `tests/memory/fixtures/` and `tests/risk/fixtures/`. `pyproject.toml` wheel target includes only `src/ai_hedge_fund`; tests are not packaged. Low severity, unchanged from plan. |
| T-07-53 Integration tests violate Nyquist sampling rate | mitigated | Feedback latency verified: memory subsuite ~2s, graph ~<1s, integration ~2s, full suite ~20s. All well within the 30s Nyquist threshold. |

No new threat surface introduced — Threat Flags section omitted.

## Cross-phase Regression

```
chflags -R nohidden .venv/lib/python3.13/site-packages/*.pth
.venv/bin/python -m pytest -q
...
920 passed, 9 skipped, 2 failed, 8 warnings in 19.66s
```

Breakdown:
- **920 green:** all Phase 1/2/3/4/5/6/7 tests
- **9 skipped:** environment-level skips (Postgres checkpointer integration tests that only run with a live Postgres)
- **2 failed:** `test_research_agent_with_test_model` + `test_signal_agent_with_test_model` — pre-existing baseline from 06-06 (missing `pytest-asyncio`); documented in `deferred-items.md` 07-04 entry

Phase 5 (debate pipeline, 17 tests), Phase 6 (risk, 122 graph/risk + 17 integration tests), and earlier Phase 7 (memory substrate, 185 tests) all still green. No regression introduced by Plan 07-05.

## User Setup Required

- **uv/macOS UF_HIDDEN workaround (inherited from 07-00):** `chflags -R nohidden .venv/lib/python3.13/site-packages/*.pth` before every `.venv/bin/python -m pytest ...` or `uv run --no-sync pytest ...`. Documented in `deferred-items.md`.
- **No new API keys or services.** Plan 07-05 adds zero production dependencies. Tests stub all 12 agents via `TestModel`; no real `ANTHROPIC_API_KEY` needed.
- **pytest-asyncio still NOT required for Phase-7 tests.** All 14 new integration tests call `asyncio.run(...)` inside synchronous test bodies. The 2 pre-existing `test_research_pipeline.py` async-test failures are unrelated and continue to be out of scope.

## Next Plan Readiness

**Phase 7 is complete — ready for `/gsd-verify-work`.**

- **REQUIREMENTS.md:** MEM-01, MEM-02, MEM-03, MEM-04 all [x] (MEM-03 + MEM-04 ticked in 07-04 already; MEM-01 + MEM-02 ticked during Plan 07-05 via `requirements mark-complete`).
- **07-VALIDATION.md:** `nyquist_compliant: true` + `wave_0_complete: true` + Per-Task Verification Map complete with 15 green rows + Validation Sign-Off approved.
- **No open blockers.** The 2 `deferred-items.md` entries (uv UF_HIDDEN workaround + pre-existing test_research_pipeline async failures + pre-existing ruff I001) are all environment-level or pre-phase-7; none block the phase.
- **UAT candidates:** The two Manual-Only Verifications in 07-VALIDATION.md (human reads a belief YAML in plain language, MEM-02; human edits a belief and next analysis reflects the edit, MEM-03). Both are designed for a human reviewer with a text editor + Langfuse trace inspection; automation covers everything else.

## Self-Check: PASSED

Verified on disk (2026-04-22T21:47Z):

- `tests/integration/test_phase7_e2e.py` exists and contains exactly 8 `def test_` functions: FOUND (verified via `grep -c '^def test_' tests/integration/test_phase7_e2e.py` = 8).
- `tests/integration/test_phase7_policy_sha_linkage.py` exists and contains exactly 6 `def test_` functions: FOUND (verified via `grep -c '^def test_' tests/integration/test_phase7_policy_sha_linkage.py` = 6).
- `tests/integration/conftest.py` re-exports 7 memory fixtures from `tests.memory.conftest`: FOUND.
- `grep -q "with_memory=True" tests/integration/test_phase7_e2e.py`: PRESENT.
- `grep -q "with_risk=True" tests/integration/test_phase7_e2e.py`: PRESENT.
- `grep -q "self_critique_agent.override" tests/integration/test_phase7_e2e.py`: PRESENT (MEM-04 stub used).
- `grep -q "compute_policy_sha" tests/integration/test_phase7_policy_sha_linkage.py`: PRESENT.
- `grep -q "EpisodicMemory" tests/integration/test_phase7_policy_sha_linkage.py`: PRESENT.
- `uv run pytest tests/integration/test_phase7_e2e.py -q` = 8 passed: VERIFIED.
- `uv run pytest tests/integration/test_phase7_policy_sha_linkage.py -q` = 6 passed: VERIFIED.
- `uv run pytest -q` = 920 passed, 9 skipped, 2 failed (pre-existing): VERIFIED.
- Ruff clean on the 3 new files in isolation: VERIFIED.
- Commits `e2a5a4a`, `5f6285a`, `da57605` all present in `git log --oneline`: VERIFIED.
- 07-VALIDATION.md frontmatter: `nyquist_compliant: true`, `wave_0_complete: true`, `status: complete`: VERIFIED.

---
*Phase: 07-memory-and-learning — COMPLETE*
*Completed: 2026-04-22*
