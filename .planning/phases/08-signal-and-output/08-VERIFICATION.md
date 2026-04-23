---
phase: 08-signal-and-output
verified: 2026-04-23T08:25:11Z
status: human_needed
score: 4/4 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Compliance reviewer reconstructs an audit trail for a real signal"
    expected: "Given an episodic_id from a live (non-stubbed) run, `uv run python -m ai_hedge_fund.scripts.audit_reconstruct --episodic-id <id>` prints JSON containing analysis_row + review_row + langfuse_trace_hint + per-agent Langfuse span summaries, and a human compliance officer can trace backward end-to-end in under 5 minutes"
    why_human: "SIG-04 compliance-grade traceability is a usability/timing claim — automation asserts completeness of the dump, but 'a human compliance officer can actually navigate the trail' requires a human. UAT scripted in 08-VALIDATION.md Manual-Only Verifications."
  - test: "Reviewer reads a Markdown review request on stdout and makes an informed decision"
    expected: "Running run_analysis end-to-end on a high-conviction ticker produces a format_review_request_md packet on stdout whose thesis + debate transcript + risk_assessment sections are clearly structured enough that a reviewer can approve or reject with a coherent reviewer_note"
    why_human: "SIG-03 usability is subjective — automation asserts the Markdown renders and the interrupt/resume mechanics work, but 'a human reviewer understands and can decide' is a human judgment. UAT scripted in 08-VALIDATION.md Manual-Only Verifications."
---

# Phase 8: Signal and Output Verification Report

**Phase Goal:** The pipeline produces investor-ready output with full audit trail and human review gate — so every signal that reaches a trading decision has been researched, debated, risk-checked, and approved by a human.

**Verified:** 2026-04-23T08:25:11Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| 1 | SIG-01 — Each ticker's signal output includes direction + conviction (0-100) + one-paragraph thesis summary + risk score + thesis link, all fields populated, no nulls | ✓ VERIFIED | `src/ai_hedge_fund/schemas/signal_output.py::FinalSignalOutput` is a frozen Pydantic class with 11 required fields and 0 Optional/None unions (`grep -c "\| None\|= None" src/ai_hedge_fund/schemas/signal_output.py` = 0); `extra="forbid"` + `frozen=True` (grep count 3 for the pair). `assemble_final_signal` (pure Python, zero LLM — `grep -r "agent.run" src/ai_hedge_fund/output/` returns nothing) composes it. 27 tests in `tests/output/test_final_signal.py` cover parametrized missing-field raises + boundary rejects + JSON round-trip + VETOED/APPROVED assembler paths. Phase-gate e2e `tests/integration/test_phase8_e2e.py::test_above_threshold_fires_interrupt` + `::test_approved_resume_completes` assert all SIG-01 fields populated with no nulls on a composed run. |
| 2 | SIG-02 — Portfolio view ranks by conviction, shows thesis summaries, groups by sector, updates on new analyses | ✓ VERIFIED | `src/ai_hedge_fund/output/portfolio_view.py::query_portfolio_view` executes `select(EpisodicMemory).where(record_type=='analysis').where(as_of_date<=target)` + latest-per-ticker + sort by conviction DESC + group by sector + `limit_per_sector=50` DoS cap. No `@lru_cache`/`@cache` (grep = 0) — append-only truth is the cache. 11 unit tests in `tests/output/test_portfolio_view.py` cover ranking, grouping, freshness-after-insert, temporal cutoff, record_type exclusion, DoS cap, entry-shape. Phase-gate `tests/integration/test_phase8_e2e.py::test_portfolio_view_freshness_after_run` proves a live pipeline run's ticker immediately surfaces in the view with zero explicit refresh. CLI at `src/ai_hedge_fund/scripts/portfolio_view.py` (7 tests in `tests/scripts/test_portfolio_view_cli.py`). |
| 3 | SIG-03 — High-conviction signals trigger human review pause (LangGraph interrupt); pipeline does not finalize until APPROVED/REJECTED | ✓ VERIFIED | `src/ai_hedge_fund/graph/nodes.py::human_review_node` calls `interrupt(review_request)` — `grep -c "interrupt(review_request)" src/ai_hedge_fund/graph/nodes.py` = 1 (exact source-grep match required by VALIDATION.md). Import confirmed at line 43: `from langgraph.types import interrupt`. Resume boundary validates via `ReviewDecision.model_validate(decision_raw)` at line 1303 (T-08-04 schema enforcement). `route_before_review` fail-closed router + `review_store_node` append-only row (`record_type="review"` at line 1341). `build_debate_pipeline` exposes `with_review=True` with 4 ValueError guards (lines 324-342). 7 review-node + 14 pipeline-review tests. Phase-gate scenarios `test_above_threshold_fires_interrupt` + `test_approved_resume_completes` + `test_rejected_resume_persists_row_and_analysis_unchanged` + `test_below_threshold_skips_review` + `test_vetoed_never_reaches_review` + `test_not_required_path_writes_review_row_uniform_audit` all green. CLI `run_analysis.py` drives the reviewer prompt + `Command(resume=...)` round-trip. |
| 4 | SIG-04 — Every agent step logged with inputs/outputs/reasoning/model/tokens/timestamp; compliance reviewer can trace backward | ✓ VERIFIED | A7 discharged empirically — `scripts/verify_langfuse_spans.py` re-run at verification time captured 25 structlog events across the composed Phase-7 pipeline (APPROVED + VETOED branches), all 13 required events emit ticker + input_tokens + output_tokens + total_tokens + (where applicable) policy_sha. Script exits 0 with banner `"SIG-04 audit coverage: ALL REQUIRED FIELDS PRESENT. A7 assumption discharged"`. `reconstruct_audit_trail` in `src/ai_hedge_fund/scripts/audit_reconstruct.py` surfaces analysis_row + review_row (latest by id) + langfuse_trace_hint (thread_id = `analysis-{ticker}-{as_of_date}`) + policy_sha + review_policy_sha. 10 unit tests (`tests/output/test_audit_reconstruct.py`) + 4 phase-gate integration scenarios (`tests/integration/test_phase8_audit_reconstruction.py`) — including wrong-id ValueError fail-closed + both policy_shas surfaced + Langfuse hint format. See Human Verification items #1 for the usability claim that requires human UAT. |

**Score:** 4/4 ROADMAP success criteria verified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/ai_hedge_fund/schemas/signal_output.py` | FinalSignalOutput Pydantic class, no nullable required fields | ✓ VERIFIED | Exists; 3345 bytes; `extra="forbid"` + `frozen=True`; zero `\| None`/`= None` occurrences; 11 required fields; imported by `output/signal.py::assemble_final_signal` and `graph/nodes.py::output_node` |
| `src/ai_hedge_fund/output/signal.py` | `assemble_final_signal` + `derive_risk_score` (pure Python, tool-first) | ✓ VERIFIED | Exists; 3706 bytes; zero `agent.run` calls in `src/ai_hedge_fund/output/`; wired to FinalSignalOutput constructor |
| `src/ai_hedge_fund/output/formatter.py` | `format_signal_md` + `format_review_request_md` | ✓ VERIFIED | Exists; 7061 bytes (grew from plan-baseline after WR-02 fix added `_fmt_risk`/`_fmt_hit` SHA-truncation helpers); used by `scripts/run_analysis.py` |
| `src/ai_hedge_fund/output/portfolio_view.py` | `query_portfolio_view` with record_type + temporal filters | ✓ VERIFIED | Exists; 5237 bytes; no `lru_cache`/`@cache` (grep = 0); uses `_normalise_as_of` from Phase-7 helper |
| `src/ai_hedge_fund/review/policy.py` | ReviewPolicy + `load_review_policy` (yaml.safe_load only) + `compute_review_policy_sha` | ✓ VERIFIED | Exists; 3636 bytes; `yaml.safe_load` present (3 total safe references) + zero `yaml.load(` occurrences; frozen + `extra="forbid"`; sha is canonical-JSON sha256 hex |
| `src/ai_hedge_fund/review/decision.py` | ReviewDecision frozen schema | ✓ VERIFIED | Exists; 1773 bytes; frozen + `extra="forbid"`; Literal status; min/max 64 on review_policy_sha |
| `config/review_policy.yaml` | Production default (threshold 70) | ✓ VERIFIED | Exists; 496 bytes; `conviction_threshold: 70`; loadable via `load_review_policy(Path('config/review_policy.yaml'))` |
| `src/ai_hedge_fund/graph/review_deps.py` | ReviewDeps frozen dataclass (XOR policy/policy_path) | ✓ VERIFIED | Exists; ReviewDeps importable from `ai_hedge_fund.graph.review_deps` |
| `src/ai_hedge_fund/graph/nodes.py` (+4 functions) | output_node, human_review_node, review_store_node, route_before_review | ✓ VERIFIED | All 4 defined (grep count 4); output_node line 1191, human_review_node line 1255, review_store_node line 1315, route_before_review line 1372 |
| `src/ai_hedge_fund/graph/pipeline.py` | build_debate_pipeline extended with with_output/with_review/review_deps kwargs | ✓ VERIFIED | `with_output` + `with_review` present with 4 ValueError guards (lines 324-342); byte-for-byte backcompat maintained for no-kwargs/with_risk/with_memory variants (14 pipeline-review tests incl. `test_phase5_backcompat_no_kwargs_still_compiles`) |
| `src/ai_hedge_fund/scripts/audit_reconstruct.py` | `reconstruct_audit_trail` + `_main` CLI | ✓ VERIFIED | Exists; 5636 bytes; `--episodic-id` argparse CLI + structured JSON stdout; ValueError fail-closed on missing/wrong-record_type ids |
| `src/ai_hedge_fund/scripts/run_analysis.py` | founder-facing CLI w/ interrupt + resume handling | ✓ VERIFIED | Exists; 14676 bytes (grew post WR-03 fix — re-prompt loop for reviewer_note length cap); composes `build_debate_pipeline(with_memory=True, with_risk=True, with_output=True, with_review=True)` + InMemorySaver + uuid-suffixed thread_id |
| `src/ai_hedge_fund/scripts/portfolio_view.py` | portfolio view CLI | ✓ VERIFIED | Exists; 4939 bytes; wraps `query_portfolio_view`; markdown + JSON rendering |

All 13 artifacts pass Levels 1-3 (exists, substantive, wired). For Level 4 (data flow), the data-producing artifacts (portfolio_view, audit_reconstruct, assemble_final_signal) are verified by integration tests that seed real EpisodicMemory rows and assert non-empty derived output — see Behavioral Spot-Checks below.

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `graph/nodes.py::human_review_node` | `langgraph.types.interrupt` | `decision_raw = interrupt(review_request)` | WIRED | `grep -c "interrupt(review_request)" src/ai_hedge_fund/graph/nodes.py` = 1 (exact SIG-03 non-negotiable source-level anchor). Import at line 43. |
| `graph/nodes.py::human_review_node` | `review/decision.py::ReviewDecision` | `ReviewDecision.model_validate(decision_raw)` | WIRED | Line 1303 of nodes.py; integration tests round-trip approval + rejection payloads. |
| `graph/nodes.py::review_store_node` | `db/models.py::EpisodicMemory` | `EpisodicMemory(record_type="review", linked_analysis_id=..., ...)` | WIRED | Line 1341; 6 SHA-linkage tests + 4 audit-reconstruction tests confirm the row lands and is retrievable. |
| `graph/pipeline.py::build_debate_pipeline` | output_node + human_review_node + review_store_node | conditional edges + with_output/with_review gating | WIRED | 14 pipeline-review tests cover all 4 ValueError guards + 4 existing backcompat variants (no-kwargs / with_risk / with_memory / with_risk+with_memory). |
| `scripts/run_analysis.py` | `build_debate_pipeline` | `build_debate_pipeline(with_memory=True, with_risk=True, with_output=True, with_review=True, checkpointer=InMemorySaver(), ...)` | WIRED | 12 run_analysis CLI tests with DI-injected pipeline factory + reviewer_io. |
| `scripts/run_analysis.py` | `langgraph.types.Command` | `graph.ainvoke(Command(resume=decision_dict), config=cfg)` | WIRED | Resume path exercised by `test_approved_resume_completes` + `test_rejected_resume_persists_row_and_analysis_unchanged` phase-gate tests. |
| `output/portfolio_view.py::query_portfolio_view` | `EpisodicMemory` | `select(EpisodicMemory).where(record_type=='analysis').where(as_of_date<=target)` | WIRED | Freshness-after-insert test + temporal-cutoff regression test + record_type-exclusivity test all green. |
| `scripts/audit_reconstruct.py::reconstruct_audit_trail` | `EpisodicMemory` review rows | `select(EpisodicMemory).where(record_type=='review', linked_analysis_id=id).order_by(id.desc()).first()` | WIRED | 10 unit tests + 4 phase-gate integration tests cover happy path + no-review + ValueError on wrong id + latest-review resolution + both policy_shas + thread_id format. |
| `review/policy.py::load_review_policy` | `yaml.safe_load` | `data = yaml.safe_load(text)` | WIRED | T-08-01 defense-in-depth — `grep "yaml.load(" src/ai_hedge_fund/review/policy.py` = 0. Regression test `test_policy_module_uses_safe_load_only` asserts this at the source level. |
| `output/signal.py::assemble_final_signal` | `schemas/signal_output.py::FinalSignalOutput` | `FinalSignalOutput(**kwargs_from_state)` | WIRED | Zero LLM in `output/` (`grep -r "agent.run"` = 0); SIG-01 no-null contract enforced via ValidationError on missing fields. |

All 10 key links verified.

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `query_portfolio_view` | `rows = db_session.scalars(q).all()` | Live query on EpisodicMemory (no static returns, no cache) | Yes — phase-gate `test_portfolio_view_freshness_after_run` seeds a real composed-pipeline run and asserts the inserted ticker surfaces in the next view call | ✓ FLOWING |
| `assemble_final_signal` | `FinalSignalOutput(...)` populated from `state["signal"]` + `state["thesis"]` + `state["risk_assessment"]` | DebatePipelineState carrying Phase-5 signal + Phase-6 risk_assessment + Phase-7 episodic_stored_id | Yes — phase-gate `test_above_threshold_fires_interrupt` + `test_approved_resume_completes` assert every SIG-01 field is non-null after a real composed-pipeline run | ✓ FLOWING |
| `reconstruct_audit_trail` | `analysis_row` + `review_row` dicts | Live SQLAlchemy `session.get` + `session.scalars(select...).first()` on EpisodicMemory | Yes — phase-gate `test_reconstruct_shows_both_policy_shas` asserts analysis.policy_sha and review_row.review_policy_sha both populated from a real run | ✓ FLOWING |
| `human_review_node` | `decision_raw` from `interrupt(review_request)` | LangGraph runtime HITL primitive (resumed by `Command(resume=...)`) | Yes — phase-gate approved + rejected resume tests confirm the resumed payload flows through `ReviewDecision.model_validate` into state | ✓ FLOWING |
| `format_signal_md` / `format_review_request_md` | dict input from `final_signal.model_dump()` / review_request | Caller-supplied dicts; no hollow prop sites | Yes — 11 formatter unit tests validate structure; CLI integration tests print real outputs | ✓ FLOWING |

No hollow or disconnected artifacts. Every dynamic-data artifact traces back to a live query or state dict populated by the composed pipeline.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All Phase-8 tests pass under the phase-8 subsuite | `uv run --no-sync pytest tests/output tests/review tests/graph/test_review_node.py tests/graph/test_output_node.py tests/graph/test_pipeline_review.py tests/scripts tests/integration/test_phase8_e2e.py tests/integration/test_phase8_review_policy_sha_linkage.py tests/integration/test_phase8_audit_reconstruction.py -q` | 187 passed in 1.19s | ✓ PASS |
| Full-suite regression preserves Phase 5/6/7 | `uv run --no-sync pytest -q` | 1108 passed, 9 skipped, 2 documented pre-existing failures (pytest-asyncio absence in `tests/integration/test_research_pipeline.py` — baseline, not a Phase 8 regression) | ✓ PASS |
| A7 Langfuse/structlog span coverage smoke (SIG-04 discharge) | `uv run --no-sync python scripts/verify_langfuse_spans.py` | Exit 0; `"Captured 25 structlog events"` + `"SIG-04 audit coverage: ALL REQUIRED FIELDS PRESENT. A7 assumption discharged"` | ✓ PASS |
| HITL interrupt primitive is genuinely wired (not a log line) | `grep -c "interrupt(review_request)" src/ai_hedge_fund/graph/nodes.py` | 1 | ✓ PASS |
| Tool-first invariant: LLM never authors risk_score | `grep -r "agent.run\|agent.arun" src/ai_hedge_fund/output/ src/ai_hedge_fund/scripts/audit_reconstruct.py` | (empty output — 0 matches) | ✓ PASS |
| SIG-01 no-nullable-required-fields contract | `grep -c "\| None\|= None" src/ai_hedge_fund/schemas/signal_output.py` | 0 | ✓ PASS |
| Public API surface importable | `python -c "from ai_hedge_fund.review import ...; from ai_hedge_fund.output import ...; from ai_hedge_fund.scripts.audit_reconstruct import ...; from ai_hedge_fund.graph.nodes import ...; from ai_hedge_fund.graph.pipeline import build_debate_pipeline"` + config loads | OK — threshold=70, sha length=64 | ✓ PASS |

All 7 automated spot-checks pass.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SIG-01 | 08-00, 08-01, 08-03, 08-04, 08-05 | Quantitative signal output per ticker: direction, conviction, thesis summary, risk score | ✓ SATISFIED | FinalSignalOutput schema + assemble_final_signal + output_node + run_analysis CLI + phase-gate no-null e2e assertions. |
| SIG-02 | 08-00, 08-02, 08-04, 08-05 | Portfolio-level ranked opportunity list with thesis summaries | ✓ SATISFIED | query_portfolio_view + CLI + freshness-after-insert phase-gate proof. |
| SIG-03 | 08-00, 08-01, 08-03, 08-04, 08-05 | Human-in-the-loop review step for signals above configurable conviction threshold | ✓ SATISFIED | ReviewPolicy + ReviewDecision + human_review_node `interrupt(review_request)` + route_before_review + run_analysis stdin reviewer prompt + phase-gate APPROVED/REJECTED/VETOED-never-reaches-review scenarios. |
| SIG-04 | 08-00, 08-02, 08-03, 08-04, 08-05 | Decision audit trail — every agent step logged with inputs, outputs, reasoning | ✓ SATISFIED | A7 span-coverage smoke green (13 events emit full SIG-04 fields) + reconstruct_audit_trail primitive + audit_reconstruct CLI + review_store_node append-only row + 3-way review_policy_sha equality tests + 4 phase-gate audit reconstruction scenarios. Human UAT timing-claim pending (see Human Verification). |

No orphaned requirements. REQUIREMENTS.md traceability table already marks all four as "Complete (shipped 2026-04-23)".

### Anti-Patterns Found

None material. Exhaustive scan (TODO/FIXME/PLACEHOLDER/empty-returns/console.log/lru_cache/yaml.load/hardcoded empty props) across `src/ai_hedge_fund/review/`, `src/ai_hedge_fund/output/`, `src/ai_hedge_fund/schemas/signal_output.py`, `src/ai_hedge_fund/scripts/{run_analysis,portfolio_view,audit_reconstruct}.py`, and Phase-8 additions to `src/ai_hedge_fund/graph/{nodes,pipeline,review_deps}.py` returned:

- Zero `yaml.load(` in the review subsystem (T-08-01 — regression-tested via `test_policy_module_uses_safe_load_only`).
- Zero `lru_cache`/`@cache` in portfolio_view.py (T-08-15 / Pitfall C — regression-tested via `test_no_lru_cache_decorator`).
- Zero `agent.run`/`agent.arun` in output/ or audit_reconstruct.py (tool-first invariant / T-08-12).
- Zero `| None`/`= None` on required fields in signal_output.py (T-08-11 SIG-01 no-null).
- All 3 code-review warnings from 08-REVIEW.md fixed post-execution (WR-01/02/03 per 08-REVIEW-FIX.md `status: all_fixed`, 3/3 closed, zero skipped): WR-01 (JSON branch SHA documented), WR-02 (formatter SHA truncation for risk_assessment + hits via new `_fmt_risk`/`_fmt_hit` helpers), WR-03 (re-prompt loop for reviewer_note length cap).

### Human Verification Required

Two items require human testing before full goal-closure. These do not block the automated score (4/4 must-haves verified) but are surfaced because ROADMAP SIG-03/SIG-04 include usability claims that automation cannot adjudicate:

1. **Compliance reviewer audit-trail reconstruction (SIG-04 timing claim)**
   - Test: Pick an `episodic_id` from a live (non-stubbed) pipeline run, execute `uv run python -m ai_hedge_fund.scripts.audit_reconstruct --episodic-id <id>`, then follow the `langfuse_trace_hint.thread_id` into the Langfuse UI.
   - Expected: analysis_row + review_row + per-agent span summaries with inputs/outputs/reasoning/model/tokens/timestamp all present; total reconstruction time under 5 minutes.
   - Why human: the completeness assertion is automated (4 phase-gate audit-reconstruction tests), but the 5-minute compliance-reviewer timing claim in ROADMAP SC-4 is a usability measurement that requires a human.

2. **Reviewer CLI usability (SIG-03 subjective decision quality)**
   - Test: Run `run_analysis.py` end-to-end against a high-conviction ticker (with real LLM calls) until the interrupt fires; read the `format_review_request_md` packet on stdout; type an approve/reject decision + reviewer note.
   - Expected: thesis + debate transcript + risk_assessment sections clear enough that the reviewer can form a coherent judgment and write a useful note.
   - Why human: Markdown renders and interrupt/resume mechanics are automated; "a reviewer actually understands the thesis and makes an informed call" is subjective.

These two items match the Manual-Only Verifications table in `08-VALIDATION.md` (authoritative spec).

### Gaps Summary

No blocking gaps. Every ROADMAP success criterion and every v1 SIG-xx requirement is satisfied at the code + test + integration layers:

- **SIG-01 shipped and verified:** 11-field FinalSignalOutput with zero nullable required fields, pure-Python assembler, no-LLM tool-first guarantee, 27 unit tests + 8 phase-gate e2e tests.
- **SIG-02 shipped and verified:** query_portfolio_view + CLI, freshness-by-construction (no cache), 11 unit tests + phase-gate freshness-after-insert proof.
- **SIG-03 shipped and verified:** real `langgraph.types.interrupt(review_request)` primitive (1 source-grep match), Command(resume=) round-trip, fail-closed routing, VETOED-never-reaches-review protection, 7 + 14 graph tests + 5 phase-gate scenarios covering above/below threshold + APPROVED/REJECTED/NOT_REQUIRED + veto-bypass.
- **SIG-04 shipped and verified:** A7 span-coverage smoke empirically discharged (25 events, 13 required event types, all SIG-04 fields present), reconstruct_audit_trail primitive + CLI, append-only review row, 3-way review_policy_sha equality across state/row/recomputed, 4 phase-gate audit-reconstruction scenarios.

Full-suite regression (1108 passed, 9 skipped, 2 pre-existing baseline failures documented in `07-memory-and-learning/deferred-items.md`) confirms zero Phase 5/6/7 regressions. Status is `human_needed` (not `passed`) solely because ROADMAP SIG-03 and SIG-04 carry usability/timing claims that require human UAT; all automated gates are green.

---

_Verified: 2026-04-23T08:25:11Z_
_Verifier: Claude (gsd-verifier)_
