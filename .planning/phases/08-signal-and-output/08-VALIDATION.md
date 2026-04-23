---
phase: 8
slug: signal-and-output
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-22
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (already installed) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run --no-sync pytest tests/output tests/graph/test_review_gate.py -q` |
| **Full suite command** | `uv run --no-sync pytest -q` |
| **Estimated runtime** | ~5s for phase-8 subsuite, <30s for full suite |

---

## Sampling Rate

- **After every task commit:** Run the quick Phase-8 subsuite.
- **After every plan wave:** Run the full suite to catch cross-phase regressions.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 30 seconds.

---

## Per-Task Verification Map

> Populated during plan execution as subplans ship.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD by planner | — | — | SIG-01..04 | T-08-XX | TBD | unit / integration | `uv run --no-sync pytest …` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/output/__init__.py` + `tests/output/conftest.py` — test package + shared fixtures
- [ ] `tests/output/fixtures/review_policy_sample.yaml` — example ReviewPolicy (threshold=70, valid schema)
- [ ] `tests/output/fixtures/review_policy_malformed.yaml` — malformed YAML for extra="forbid" test
- [ ] Langfuse span coverage verification — smoke script proving existing agent nodes emit input/output/model/tokens/duration/timestamp spans. Gap-fill if Langfuse instrumentation is incomplete (MEDIUM-risk A7 per RESEARCH).

*If already present after planning: mark checkboxes and set `wave_0_complete: true`.*

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

**Validate by:** Pydantic model construction + serialization round-trip + no-None contract (every required field raises on missing).

- `tests/output/test_signal_output_schema.py::test_all_required_fields_populated` — valid construction succeeds; round-trip via `model_dump(mode="json")` preserves all five SIG-01 fields + metadata.
- `tests/output/test_signal_output_schema.py::test_missing_field_raises` — omitting any SIG-01 field raises ValidationError.
- `tests/output/test_signal_output_schema.py::test_extra_field_forbidden` — Pydantic `extra="forbid"` rejects unknown keys.
- `tests/output/test_signal_output_schema.py::test_conviction_bounds` — `conviction` outside [0, 100] raises.
- `tests/output/test_signal_output_schema.py::test_direction_literal` — `direction` outside {long, short, neutral} raises.

### Success Criterion 2 — Portfolio view freshness + ranking + grouping (SIG-02)

**Validate by:** Seed N episodic rows with varied tickers/sectors/confidences → call portfolio_view → assert result ordering + grouping. Fresh after new insert without cache invalidation.

- `tests/output/test_portfolio_view.py::test_ranks_by_conviction_desc` — 3 rows with confidences [30, 80, 50] return in order [80, 50, 30].
- `tests/output/test_portfolio_view.py::test_groups_by_sector` — rows across 2 sectors return with a sector-keyed structure or sector field per row.
- `tests/output/test_portfolio_view.py::test_fresh_after_new_insert` — call view, insert a new row, call view again; new row appears in second result without explicit refresh. Proves "updates when new analyses complete".
- `tests/output/test_portfolio_view.py::test_latest_per_ticker_only` — same ticker with 2 analyses on different dates returns only the latest (most recent as_of_date wins).

### Success Criterion 3 — Human review gate actually interrupts (SIG-03)

**Validate by:** Pipeline runs through with_output=True; high-conviction signal triggers the LangGraph `interrupt()` primitive; execution halts; `Command(resume=ReviewDecision(...))` completes the pipeline with the human-supplied decision persisted.

- `tests/graph/test_review_gate.py::test_high_conviction_triggers_interrupt` — build_debate_pipeline(with_output=True, review_policy threshold=70); run to ticker with confidence=85; assert `__interrupt__` appears in the paused state.
- `tests/graph/test_review_gate.py::test_low_conviction_skips_review` — same pipeline; confidence=50; no interrupt; SignalOutput emitted directly.
- `tests/graph/test_review_gate.py::test_resume_with_approved_decision_completes_pipeline` — paused graph; `Command(resume=ReviewDecision(status="APPROVED", ...))`; pipeline finishes; review row persisted in episodic_memory.
- `tests/graph/test_review_gate.py::test_resume_with_rejected_decision_persists_but_no_signal` — REJECTED decision is still persisted as a `record_type='review'` row; `state["signal"]` is None; Pitfall 8 analog.
- `tests/graph/test_review_gate.py::test_vetoed_runs_never_reach_review` — with_risk=True and a VETOED risk_assessment; no interrupt fires; no review row created; RISK-01 "veto is final" preserved.
- `tests/graph/test_review_gate.py::test_review_policy_sha_linked_in_review_row` — stored review row has review_policy_sha equal to `compute_review_policy_sha(policy)`; different policy → different sha.

### Success Criterion 4 — Compliance-grade audit trail (SIG-04)

**Validate by:** Given a final signal's episodic_id, a reconstruction script emits every agent span + DB row that produced it. Langfuse spans include input, output, model, tokens, duration, timestamp per span.

- `tests/output/test_audit_reconstruct.py::test_reconstruct_lists_all_rows` — seed analysis + review rows for an episodic_id; script output contains both rows.
- `tests/output/test_audit_reconstruct.py::test_reconstruct_includes_policy_shas` — output shows risk `policy_sha` and `review_policy_sha` linked to the analysis.
- `tests/output/test_langfuse_spans.py::test_every_agent_emits_required_fields` — run pipeline end-to-end with TestModel stubs; capture spans; assert each span has input, output, model, tokens, duration, timestamp.

### Backcompat + composition

- `tests/graph/test_pipeline_with_output.py::test_backcompat_no_kwargs` — `build_debate_pipeline()` unchanged topology.
- `tests/graph/test_pipeline_with_output.py::test_compose_with_risk_and_memory_and_output` — all three flags together compile and run end-to-end.
- `tests/graph/test_pipeline_with_output.py::test_phase5_6_7_regression_matrix` — prior-phase tests still green.

### Nyquist coverage

- Every must-have has at least one automated test with a concrete assertion.
- No test uses grep-only or file-existence-only verification.
- Sampling continuity: no three consecutive plan tasks are automated-free.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
