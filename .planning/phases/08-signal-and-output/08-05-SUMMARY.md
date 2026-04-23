---
phase: 08-signal-and-output
plan: 05
subsystem: Signal + Output (Phase-gate integration)
tags: [phase-8, integration, phase-gate, e2e, wave-4, SIG-01, SIG-02, SIG-03, SIG-04]

dependency_graph:
  requires:
    - ai_hedge_fund.graph.pipeline.build_debate_pipeline  # Phase 5/6/7/8 composed
    - ai_hedge_fund.graph.review_deps.ReviewDeps
    - ai_hedge_fund.graph.risk_deps.RiskDeps
    - ai_hedge_fund.graph.memory_deps.MemoryDeps
    - ai_hedge_fund.review.policy.ReviewPolicy
    - ai_hedge_fund.review.policy.compute_review_policy_sha
    - ai_hedge_fund.review.decision.ReviewDecision
    - ai_hedge_fund.output.portfolio_view.query_portfolio_view
    - ai_hedge_fund.scripts.audit_reconstruct.reconstruct_audit_trail
    - ai_hedge_fund.db.models.EpisodicMemory
    - ai_hedge_fund.risk.policy.RiskPolicy
  provides:
    - tests/integration/test_phase8_e2e.py  # 8 SIG-01..04 composed-pipeline scenarios
    - tests/integration/test_phase8_review_policy_sha_linkage.py  # 6 three-way SHA scenarios
    - tests/integration/test_phase8_audit_reconstruction.py  # 4 audit-trail scenarios
    - .planning/phases/08-signal-and-output/08-VALIDATION.md  # stamped sign-off
  affects:
    - src/ai_hedge_fund/memory/recall.py  # Rule 1 bug-fix: filter review rows out of query_episodic

tech_stack:
  added: []
  patterns:
    - TestModel stubbing for all 12 agents (12 overrides per ExitStack)
    - langgraph.types.Command(resume=decision) for HITL resume under test
    - langgraph.checkpoint.memory.InMemorySaver for interrupt persistence
    - pd.read_csv fixtures for returns_golden (Phase-6/7/8 shared)
    - Three-way SHA equality (state, row.payload, recomputed) for policy audit
    - as_of_date=2024-06-03 inside returns_golden window for risk-checked runs

key_files:
  created:
    - tests/integration/test_phase8_e2e.py
    - tests/integration/test_phase8_review_policy_sha_linkage.py
    - tests/integration/test_phase8_audit_reconstruction.py
  modified:
    - .planning/phases/08-signal-and-output/08-VALIDATION.md
    - src/ai_hedge_fund/memory/recall.py  # Rule 1 auto-fix

decisions:
  - Phase 8 Plan 08-05 -- query_episodic(record_type IN analysis,outcome) filter (Rule 1 auto-fix) unblocks multi-run Phase-8 integration tests. Review rows are audit metadata, not analyst evidence; surfacing them to memory_recall_node violated the EpisodicHit schema pattern '^(analysis|outcome)$' and raised ValidationError on the 2nd+ pipeline run sharing a session with a prior review row.
  - Phase 8 Plan 08-05 -- debate_synthesis_agent stub carries a full DebateSynthesis payload (revised_thesis + pre/post_debate_confidence + evidence/logical/risk sub-scores + synthesis_notes); bare TestModel() defaults confidence=0 which maps to conviction below threshold, so above-threshold scenarios override via custom_output_args.
  - Phase 8 Plan 08-05 -- All e2e scenarios use as_of_date=2024-06-03 (inside returns_golden.csv window 2024-01-02..2024-12-18) + PG / Consumer Staples candidate + wide-open RiskPolicy so the deterministic risk checks (correlation/drawdown) pass on an empty portfolio. Mirror of scripts/verify_langfuse_spans.py approach.
  - Phase 8 Plan 08-05 -- VETOED scenario uses excluded_sectors=['Technology'] + AAPL (Technology) + conviction=85 so the first-violation-wins exclusion check fires BEFORE correlation/drawdown checks; T-08-06 (veto bypass) verified by post-VETO topology traversal (output_node short-circuits on missing signal, human_review_node short-circuits on error, review_store_node short-circuits on error -> zero review rows, no interrupt).
  - Phase 8 Plan 08-05 -- Stub helpers duplicated across the 3 test files per 07-05 SUMMARY decision 3; no shared extraction to tests/integration/conftest.py (deferred; each phase-gate file stays self-contained for readability).

metrics:
  duration: 18m
  tasks: 3
  completed_date: 2026-04-23
---

# Phase 08 Plan 05: Phase-Gate Integration Suite — SIG-01..04 End-to-End

Proven: 18 integration tests across three files exercise the composed Phase 5+6+7+8 pipeline under TestModel stubs and verify that all four Phase-8 requirements (SIG-01 no-null signal; SIG-02 portfolio view freshness; SIG-03 HITL interrupt + resume; SIG-04 audit reconstruction + three-way SHA equality) are delivered end-to-end with zero real LLM calls, preserving Phase 5/6/7 backcompat.

## Performance

- **Duration:** ~18 minutes (planning context load + 3 task executions with inline Rule-1 debug + full-suite regression + sign-off)
- **Tasks completed:** 3 (Task 1: 8 e2e scenarios; Task 2: 6 SHA linkage; Task 3: 4 audit reconstruction + VALIDATION.md stamp)
- **Files created:** 3 (tests only)
- **Files modified:** 2 (08-VALIDATION.md + src/ai_hedge_fund/memory/recall.py Rule-1 fix)
- **Lines of code:** 1,260 LOC across three integration test files
- **Test runtime:** ~3s for 18 Phase-8 integration tests; ~22s for full suite (1108 pass + 9 skip + 2 documented baseline failures)

## Accomplishments

### Test files shipped

1. **`tests/integration/test_phase8_e2e.py`** — 8 SIG-01..04 composed-pipeline scenarios:
   - `test_above_threshold_fires_interrupt` — conviction=85 >= threshold=70 fires LangGraph `__interrupt__`; payload contains ticker, as_of_date, signal, thesis, debate, risk_assessment, episodic_hits, beliefs_consulted.
   - `test_below_threshold_skips_review` — conviction=50 below threshold: no interrupt, `review_status='NOT_REQUIRED'`.
   - `test_approved_resume_completes` — `Command(resume=ReviewDecision(APPROVED))` drives the pipeline to completion; review row persisted with `record_type='review'`.
   - `test_rejected_resume_persists_row_and_analysis_unchanged` — REJECTED resume writes review row; analysis row is byte-identical post-resume (T-08-05 append-only invariant).
   - `test_vetoed_never_reaches_review` — `excluded_sectors=['Technology']` + AAPL vetoes before output; no interrupt, no review row, `final_signal is None` (T-08-06 veto-bypass prevention).
   - `test_not_required_path_writes_review_row_uniform_audit` — below-threshold path still writes a `record_type='review'` row for audit uniformity (Pitfall G).
   - `test_portfolio_view_freshness_after_run` — SIG-02: live pipeline run -> ticker visible in `query_portfolio_view` without explicit refresh.
   - `test_phase5_backcompat_no_kwargs_still_compiles` — `build_debate_pipeline()` with no kwargs retains Phase-5 topology; no Phase 6/7/8 nodes leak in.

2. **`tests/integration/test_phase8_review_policy_sha_linkage.py`** — 6 three-way SHA scenarios (mirror of Phase 7 `test_phase7_policy_sha_linkage.py` adapted for the review policy):
   - `test_same_policy_same_review_sha` — determinism: two runs with the same `ReviewPolicy` produce identical `review_policy_sha` on both stored rows.
   - `test_different_policy_different_review_sha` — change sensitivity: `threshold=70` vs `threshold=71` produce different SHAs.
   - `test_idempotent_revert` — A, B, A sequence: rows 1 and 3 share SHA; row 2 differs.
   - `test_sha_format_on_approved` — 64-char lowercase hex on APPROVED row; plus `review_status='APPROVED'`.
   - `test_sha_format_on_rejected` — 64-char lowercase hex on REJECTED row; plus `review_status='REJECTED'`.
   - `test_three_way_sha_equality` — T-08-02/T-08-22 lock: `state['review_decision']['review_policy_sha']` == `row.payload['review_policy_sha']` == `compute_review_policy_sha(policy)` for a single composed run.

3. **`tests/integration/test_phase8_audit_reconstruction.py`** — 4 audit-trail scenarios:
   - `test_reconstruct_after_approved_run` — trail contains analysis row + review row (APPROVED) + Langfuse thread_id hint embedding the ticker.
   - `test_reconstruct_after_not_required_run` — NOT_REQUIRED runs still have a full audit trail.
   - `test_reconstruct_shows_both_policy_shas` — T-08-19: risk `policy_sha` on analysis row + `review_policy_sha` on review row.
   - `test_reconstruct_raises_on_wrong_id` — fail-closed: unknown id raises `ValueError`.

### Validation sign-off

- `.planning/phases/08-signal-and-output/08-VALIDATION.md` frontmatter flipped:
  - `status: complete`
  - `nyquist_compliant: true`
  - `wave_0_complete: true`
  - `completed: 2026-04-23`
- Wave 0 Requirements checklist ticked (4/4).
- Per-Task Verification Map populated with 15 rows across Plans 08-00..08-05, all marked `✅ green`.
- Validation Sign-Off checklist ticked (6/6).
- Approval stamped `2026-04-23, executor (phase-8 plan-05)`.

## Task Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | `aefb924` | test(08-05): add Phase 8 end-to-end integration scenarios |
| Task 2 | `71f0ce1` | test(08-05): add Phase 8 review_policy_sha audit linkage tests |
| Task 3 | `0a33c03` | test(08-05): add Phase 8 audit reconstruction e2e tests + phase sign-off |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `query_episodic` returned review rows that broke `EpisodicHit` schema validation**
- **Found during:** Task 2 — second pipeline run in `test_same_policy_same_review_sha` raised `pydantic_core.ValidationError: record_type / String should match pattern '^(analysis|outcome)$' [input_value='review']` inside `memory_recall_node`.
- **Root cause:** `src/ai_hedge_fund/memory/recall.py::query_episodic` filtered by `as_of_date` + `or_(ticker, sector)` but did NOT filter by `record_type`. When a prior pipeline run landed a `record_type='review'` row on the same ticker/sector, the next run's `memory_recall_node` surfaced it, and the `EpisodicHit.record_type` Pydantic validator (pattern `^(analysis|outcome)$`) rejected it. This was a latent bug introduced in Plan 08-03 (review rows) that only manifests when a test/session runs the pipeline twice with overlapping ticker/sector keys — Phase-7 integration tests sidestep it because they never produce review rows.
- **Fix:** Added `.filter(EpisodicMemory.record_type.in_(("analysis", "outcome")))` to `query_episodic`. Review rows are audit metadata, not analyst evidence; they should not surface to downstream agents as "priors".
- **Files modified:** `src/ai_hedge_fund/memory/recall.py`
- **Regression:** All 177 Phase-7 memory + integration tests still green after the fix. 1108 pass in full suite.
- **Commit:** `71f0ce1` (bundled with Task 2 since the fix was a blocker for those tests).

**2. [Rule 3 - Blocking] Plan's `_build_pipeline` helper omitted `returns` from `RiskDeps` construction**
- **Found during:** Task 1 — initial attempt to instantiate `RiskDeps(db_session=session, policy=risk_policy)` would have failed because `RiskDeps` is a frozen dataclass with `returns: pd.DataFrame` as a required field.
- **Fix:** All three test files load the Phase-6/7 shared fixture `tests/risk/fixtures/returns_golden.csv` and pass it via `RiskDeps(db_session=..., returns=..., policy=...)`. Matches the pattern already used by `tests/integration/test_phase7_policy_sha_linkage.py` and `scripts/verify_langfuse_spans.py`. Tests use `as_of_date=2024-06-03` (inside the returns_golden window 2024-01-02..2024-12-18) so the deterministic correlation + drawdown checks pass on an empty portfolio with a wide-open APPROVED policy.
- **No production changes.**

**3. [Rule 1 - Bug] Plan's `debate_synthesis` stub used `final_confidence` instead of the real `DebateSynthesis` field names**
- **Found during:** Task 1 design — plan's sample code carried `{"final_confidence": 85, "revised_thesis": {...}, "synthesis_rationale": "..."}` for the `debate_synthesis_agent` override. The real `DebateSynthesis` schema (`src/ai_hedge_fund/schemas/debate.py`) has `pre_debate_confidence`, `post_debate_confidence`, `evidence_strength`, `logical_consistency`, `risk_coverage`, `quality_score`, `synthesis_notes` — not `final_confidence` or `synthesis_rationale`. A TestModel with the plan's kwargs would have raised Pydantic ValidationError before the test body ran.
- **Fix:** `_debate_synth_stub(confidence)` helper in each test file carries the full 9-field `DebateSynthesis` payload (ticker + revised_thesis + pre/post_debate_confidence + 3 sub-scores + quality_score + synthesis_notes); `debate_synthesis_node` overwrites `state['thesis']` with `synthesis.revised_thesis.model_dump()`, so the `revised_thesis.confidence` field drives the downstream conviction used by `route_before_review`.
- **No production changes.**

**4. [Rule 1 - Bug] Plan's `_valid_bear_case` stub had the wrong schema shape**
- **Found during:** Task 1 design — plan carried `{"claims": ["supply risk", ...], "cited_sources": [...], "counter_evidence": "..."}` but the real `BearCase` schema uses a list-of-dicts shape with cross-linked `addresses_bull_claim` per-claim.
- **Fix:** Reused the canonical `_valid_bear_case()` helper from `tests/integration/test_phase7_e2e.py` + `scripts/verify_langfuse_spans.py` (already in the codebase). Triple-claim list with two claims carrying `addresses_bull_claim='a'` and one with `addresses_bull_claim=None`; `addressed_bull_claims=['a','a']`; `headline='a'`.
- **No production changes.**

**5. [Rule 1 - Bug] Plan's Phase-5 backcompat test referenced `bull_case` in expected nodes instead of `bull`**
- **Found during:** Task 1 verification — plan's sample test had `"bull_case"` / `"bear_case"` in the `expected_phase5_nodes` set. The actual LangGraph node IDs in `build_debate_pipeline` (verified via `graph.get_graph().nodes` on a fresh build) are `bull`, `bear`, `rebuttal`, etc. — single words, not the schema field names.
- **Fix:** Test uses `{"fundamental", "sentiment", "technical", "manager", "bull", "bear", "rebuttal", "final_arguments", "debate_synthesis", "signal"}` — the exact 10-node Phase-5 topology.
- **No production changes.**

### Scope Boundary

No out-of-scope fixes were attempted. The 2 pre-existing baseline failures in `tests/integration/test_research_pipeline.py::test_research_agent_with_test_model` and `::test_signal_agent_with_test_model` (pytest-asyncio plugin missing) are documented in `.planning/phases/07-memory-and-learning/deferred-items.md` and remain unchanged.

## Test Coverage

### Phase-8 integration (this plan)

```
tests/integration/test_phase8_e2e.py ........................      8 passed
tests/integration/test_phase8_review_policy_sha_linkage.py .....   6 passed
tests/integration/test_phase8_audit_reconstruction.py ........     4 passed
                                                                   --------
                                                                  18 passed
```

### Full suite regression

```
1108 passed, 9 skipped, 2 failed (documented pre-existing baseline)
```

The 2 failing tests (`test_research_pipeline.py::test_research_agent_with_test_model` + `::test_signal_agent_with_test_model`) failed before Plan 08-05 changes and continue to fail the same way; they are waiting on `pytest-asyncio` dev-dep installation (see `07-memory-and-learning/deferred-items.md`). Zero new failures introduced by this plan.

### Backcompat proof

- `tests/integration/test_phase5_*.py` — no direct test files at this path, but Phase-5 debate nodes + pipeline topology preserved via `test_phase5_backcompat_no_kwargs_still_compiles`.
- `tests/integration/test_phase6_e2e.py` — passes unchanged.
- `tests/integration/test_phase7_e2e.py` — passes unchanged (including the seven scenarios proving MEM-01..04 + MEM-03 × MEM-04 + Phase-5 backcompat).
- `tests/integration/test_phase7_policy_sha_linkage.py` — passes unchanged.
- `tests/graph/test_pipeline_review.py` — 13 backcompat + Phase-8 topology tests passes unchanged.

## Key Decisions

1. **Rule 1 auto-fix in `src/ai_hedge_fund/memory/recall.py`.** Review rows are audit metadata; `query_episodic` now filters `record_type IN ('analysis','outcome')`. This is a contract-preserving fix: `EpisodicHit.record_type` has always been `pattern='^(analysis|outcome)$'`, so review rows were never supposed to flow through this path. The filter closes that latent gap and keeps all 177 Phase-7 tests green. Parallels T-08-17 (spoofing: review/outcome rows surfaced as analyses) — now impossible by construction in both read paths (portfolio_view already filters; memory_recall now filters too).

2. **TestModel-stubbed all 12 agents + custom_output_args for conviction control.** The plan's canonical `_stubbed_stack` overrides all 11 debate/risk agents + self_critique. Above-threshold tests override `debate_synthesis_agent.model` with `custom_output_args=_debate_synth_stub(85)` (the revised_thesis drives the post-debate confidence, which becomes FinalSignalOutput.conviction, which is what route_before_review compares to `_review_threshold`). Below-threshold tests use `_debate_synth_stub(50)`. `manager_agent`'s output is discarded by `debate_synthesis_node` (which overwrites `state['thesis']`), so no manager stub customization is needed.

3. **Stub-helper duplication across three test files.** Per the 07-05 SUMMARY decision 3 precedent, each phase-gate file stays self-contained — `_valid_bear_case`, `_debate_synth_stub`, `_stubbed_stack`, `_golden_returns`, `_wide_open_risk_policy`, `_build` helpers are duplicated. Shared extraction to `tests/integration/conftest.py` is deferred; the cost of a future refactor is small compared to the clarity of each test file standing on its own.

4. **Date window alignment.** All e2e pipeline runs use `as_of_date=2024-06-03` (inside `returns_golden.csv` window 2024-01-02..2024-12-18) + PG / Consumer Staples + a wide-open `RiskPolicy` (max_single_position_pct=10, max_correlation=0.99, max_drawdown=99). This deterministically lets an empty-portfolio candidate pass all five risk checks so the APPROVED path is exercised. VETOED scenarios set `excluded_sectors=['Technology']` + AAPL to fire the first-violation-wins exclusion check before any correlation/drawdown calculation.

## Architecture Notes

This plan is a pure phase-gate — zero new production code was designed or shipped. The one production change (`src/ai_hedge_fund/memory/recall.py` record_type filter) was a Rule-1 bug-fix unblocker, not a new feature. The 18 integration tests compose Plans 08-01..08-04's production code (FinalSignalOutput + ReviewPolicy + ReviewDecision + human_review_node + review_store_node + build_debate_pipeline flags + reconstruct_audit_trail + query_portfolio_view) into a single end-to-end proof surface.

The phase-gate shape mirrors Phase 7 Plan 07-05 exactly:
- 8 e2e scenarios (matches 07-05's 8 MEM-XX scenarios)
- 6 SHA linkage scenarios (matches 07-05's 6 policy_sha linkage)
- 4 audit reconstruction scenarios (new — no Phase-7 analog because there was no audit_reconstruct tool in Phase 7)
- = 18 new integration tests total.

## Self-Check: PASSED

**Created files exist:**
- `tests/integration/test_phase8_e2e.py` — FOUND (540 lines)
- `tests/integration/test_phase8_review_policy_sha_linkage.py` — FOUND (421 lines)
- `tests/integration/test_phase8_audit_reconstruction.py` — FOUND (299 lines)

**Commits exist:**
- `aefb924` — FOUND
- `71f0ce1` — FOUND
- `0a33c03` — FOUND

**Phase-8 integration subsuite:** 18/18 passed (`uv run --no-sync pytest tests/integration/test_phase8_*.py -q`)

**Full-suite regression:** 1108 passed, 9 skipped, 2 documented pre-existing baseline failures (unchanged); zero new failures.

**VALIDATION.md:** `nyquist_compliant: true`, `wave_0_complete: true`, `status: complete`, 15-row Per-Task Verification Map all green, sign-off stamped.

Phase 8 COMPLETE. SIG-01..04 delivered end-to-end. Ready for `/gsd-verify-work`.
