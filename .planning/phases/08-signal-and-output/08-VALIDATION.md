---
phase: 8
slug: signal-and-output
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-22
completed: 2026-04-23
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (already installed) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run --no-sync pytest tests/output tests/review tests/graph/test_review_node.py tests/graph/test_output_node.py tests/graph/test_pipeline_review.py -q` |
| **Phase-8 integration command** | `uv run --no-sync pytest tests/integration/test_phase8_e2e.py tests/integration/test_phase8_review_policy_sha_linkage.py tests/integration/test_phase8_audit_reconstruction.py -q` |
| **Full suite command** | `uv run --no-sync pytest -q` |
| **Estimated runtime** | ~3s for Phase-8 integration subsuite, ~22s for full suite |

---

## Sampling Rate

- **After every task commit:** Run the quick Phase-8 subsuite.
- **After every plan wave:** Run the full suite to catch cross-phase regressions.
- **Before `/gsd-verify-work`:** Full suite must be green (modulo 2 pre-existing baseline failures).
- **Max feedback latency:** 30 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-00-T1 | 08-00 | 0 | Scaffold | T-08-40 | Test packages + fixtures bootstrapped | scaffold | `ls tests/output/conftest.py tests/review/conftest.py` | ✅ | ✅ green |
| 08-00-T2 | 08-00 | 0 | Fixtures | T-08-40 | Review-policy YAML fixtures (sample + malformed) | scaffold | `ls tests/review/fixtures/review_policy_*.yaml` | ✅ | ✅ green |
| 08-00-T3 | 08-00 | 0 | SIG-04 | A7 | Langfuse/structlog span coverage verified empirically | integration | `uv run --no-sync python scripts/verify_langfuse_spans.py` | ✅ | ✅ green |
| 08-01-T1 | 08-01 | 1 | SIG-03 | T-08-01, T-08-02 | ReviewPolicy load + SHA fingerprint (yaml.safe_load only) | unit | `uv run --no-sync pytest tests/review/test_review_policy.py -q` | ✅ | ✅ green |
| 08-01-T2 | 08-01 | 1 | SIG-03 | T-08-13 | ReviewDecision frozen + extra=forbid | unit | `uv run --no-sync pytest tests/review/test_review_decision.py -q` | ✅ | ✅ green |
| 08-01-T3 | 08-01 | 1 | SIG-01 | T-08-11, T-08-12 | FinalSignalOutput + assemble_final_signal + derive_risk_score + formatters | unit | `uv run --no-sync pytest tests/output/ -q` | ✅ | ✅ green |
| 08-02-T1 | 08-02 | 2 | SIG-02 | T-08-15, T-08-17, T-08-18, T-08-20 | query_portfolio_view + temporal filter + DoS cap + freshness | unit | `uv run --no-sync pytest tests/output/test_portfolio_view.py -q` | ✅ | ✅ green |
| 08-02-T2 | 08-02 | 2 | SIG-04 | T-08-19 | reconstruct_audit_trail (analysis + review + langfuse hint) | unit | `uv run --no-sync pytest tests/scripts/test_portfolio_view_cli.py -q` | ✅ | ✅ green |
| 08-03-T1 | 08-03 | 3 | SIG-03 | T-08-03, T-08-04, T-08-21 | human_review_node via langgraph.types.interrupt + ReviewDecision.model_validate | unit | `uv run --no-sync pytest tests/graph/test_review_node.py -q` | ✅ | ✅ green |
| 08-03-T2 | 08-03 | 3 | SIG-01, SIG-03 | T-08-06, T-08-23 | build_debate_pipeline(with_output, with_review) + veto-bypass guard | unit | `uv run --no-sync pytest tests/graph/test_pipeline_review.py -q` | ✅ | ✅ green |
| 08-04-T1 | 08-04 | 3 | SIG-01, SIG-03 | T-08-08 | run_analysis CLI (markdown/json output + resume) | unit | `uv run --no-sync pytest tests/scripts/test_run_analysis.py -q` | ✅ | ✅ green |
| 08-04-T2 | 08-04 | 3 | SIG-02 | T-08-20 | portfolio_view CLI | unit | `uv run --no-sync pytest tests/scripts/test_portfolio_view_cli.py -q` | ✅ | ✅ green |
| 08-05-T1 | 08-05 | 4 | SIG-01..04 | T-08-05, T-08-06, T-08-40, T-08-42 | 8 e2e scenarios (above/below threshold + APPROVED/REJECTED resume + VETOED + portfolio view freshness + Phase-5 backcompat) | integration | `uv run --no-sync pytest tests/integration/test_phase8_e2e.py -q` | ✅ | ✅ green |
| 08-05-T2 | 08-05 | 4 | SIG-03, SIG-04 | T-08-02, T-08-22, T-08-41 | 6 review_policy_sha linkage scenarios (state vs row vs recomputed) | integration | `uv run --no-sync pytest tests/integration/test_phase8_review_policy_sha_linkage.py -q` | ✅ | ✅ green |
| 08-05-T3 | 08-05 | 4 | SIG-04 | T-08-19 | 4 audit reconstruction scenarios (APPROVED + NOT_REQUIRED + both SHAs + wrong id raises) | integration | `uv run --no-sync pytest tests/integration/test_phase8_audit_reconstruction.py -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/output/__init__.py` + `tests/output/conftest.py` — test package + shared fixtures
- [x] `tests/review/fixtures/review_policy_sample.yaml` — example ReviewPolicy (threshold=70, valid schema)
- [x] `tests/review/fixtures/review_policy_malformed.yaml` — malformed YAML for extra="forbid" test
- [x] Langfuse span coverage verification — `scripts/verify_langfuse_spans.py` exits 0; A7 assumption discharged empirically. No production gap-fill needed (all 13 Phase-1-7 pipeline events emit ticker + tokens + policy_sha where applicable).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Compliance reviewer reconstructs an audit trail for a real signal | SIG-04 | End-to-end compliance scenario — automation can assert completeness, but "a human compliance officer can trace backward in <5 min" requires a human | UAT: pick an episodic_id from a live run; execute `uv run python -m ai_hedge_fund.scripts.audit_reconstruct --episodic-id <id>`; verify output contains analysis row + review row + Langfuse trace link + every agent's span summary; time the reconstruction. |
| Reviewer reads a Markdown review request and makes an informed decision | SIG-03 | Subjective usability — automation can assert the Markdown renders, but "a reviewer understands the thesis and can decide" requires a human | UAT: run the CLI end-to-end on a high-conviction ticker; read the review request on stdout; note whether thesis + debate transcript + risk_assessment are clearly structured; approve or reject with a reviewer_note. |

---

## Validation Architecture

Derived from `08-RESEARCH.md` and the four ROADMAP success criteria. Each criterion maps to at least one automated test.

### Success Criterion 1 — Signal output schema with no nulls (SIG-01)

**Validated by:** Pydantic model construction + serialization round-trip + no-None contract (every required field raises on missing).

- `tests/output/test_signal_output_schema.py` — Plan 08-01. Green.
- Phase-gate e2e: `tests/integration/test_phase8_e2e.py::test_above_threshold_fires_interrupt` + `::test_approved_resume_completes` assert `final_signal` contains all SIG-01 fields (ticker, direction, conviction, thesis_summary, risk_score, thesis_link, policy_sha, review_policy_sha, episodic_id, review_status) populated with no nulls.

### Success Criterion 2 — Portfolio view freshness + ranking + grouping (SIG-02)

**Validated by:** Seed episodic rows → call portfolio_view → assert ordering + grouping + freshness.

- `tests/output/test_portfolio_view.py` — Plan 08-02. Green.
- Phase-gate e2e: `tests/integration/test_phase8_e2e.py::test_portfolio_view_freshness_after_run` proves a live pipeline run's analysis row is immediately visible in `query_portfolio_view` without any explicit refresh.

### Success Criterion 3 — Human review gate actually interrupts (SIG-03)

**Validated by:** Pipeline runs through with_output=True; high-conviction signal triggers the LangGraph `interrupt()` primitive; execution halts; `Command(resume=ReviewDecision(...))` completes the pipeline with the human-supplied decision persisted.

- `tests/graph/test_review_node.py` + `tests/graph/test_pipeline_review.py` — Plan 08-03. Green.
- Phase-gate e2e: `tests/integration/test_phase8_e2e.py::test_above_threshold_fires_interrupt` + `::test_approved_resume_completes` + `::test_rejected_resume_persists_row_and_analysis_unchanged` + `::test_below_threshold_skips_review` + `::test_vetoed_never_reaches_review` + `::test_not_required_path_writes_review_row_uniform_audit` all green.

### Success Criterion 4 — Compliance-grade audit trail (SIG-04)

**Validated by:** Given a final signal's episodic_id, a reconstruction tool emits every agent span + DB row that produced it. Langfuse spans include input, output, model, tokens, duration, timestamp per span.

- Wave-0: `scripts/verify_langfuse_spans.py` — exit 0 proves A7 assumption empirically.
- Plan 08-02: `reconstruct_audit_trail` primitive + CLI.
- Phase-gate e2e: `tests/integration/test_phase8_audit_reconstruction.py` — 4 scenarios reconstruct the trail after a live run (APPROVED + NOT_REQUIRED + both policy_shas + wrong-id fail-closed).
- Phase-gate review SHA chain: `tests/integration/test_phase8_review_policy_sha_linkage.py` — 6 scenarios lock state → row → recomputed equality for the review policy (mirror of Phase 6 → 7 policy_sha pattern).

### Backcompat + composition

- `tests/integration/test_phase8_e2e.py::test_phase5_backcompat_no_kwargs_still_compiles` — Phase-5 topology unchanged.
- Full-suite: Phase-6 + Phase-7 integration tests pass unchanged (`test_phase6_e2e.py`, `test_phase7_e2e.py`, `test_phase7_policy_sha_linkage.py`).
- 6 backcompat tests in `tests/graph/test_pipeline_review.py` verify prior kwarg combos.

### Nyquist coverage

- Every must-have has at least one automated test with a concrete assertion.
- No test uses grep-only or file-existence-only verification.
- Sampling continuity: no three consecutive plan tasks are automated-free.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s (Phase-8 subsuite ~3s; full suite ~22s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** stamped 2026-04-23, executor (phase-8 plan-05)

Phase-gate summary:
- **Integration tests:** 18 Phase-8 scenarios green (8 e2e + 6 review_policy_sha + 4 audit reconstruction)
- **Full suite:** 1108 passed, 9 skipped, 2 pre-existing baseline failures (pytest-asyncio absence on two Phase-3 research_pipeline tests; documented in `.planning/phases/07-memory-and-learning/deferred-items.md`)
- **SIG-01..04:** All four requirements closed end-to-end
- **Backcompat:** Phase 5/6/7 integration tests green unchanged
