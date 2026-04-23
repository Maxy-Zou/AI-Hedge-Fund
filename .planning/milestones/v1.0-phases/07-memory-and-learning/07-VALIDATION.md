---
phase: 7
slug: memory-and-learning
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-22
completed: 2026-04-22
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (already installed) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/memory -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~5s for memory subsuite, <30s for full suite |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/memory -q`
- **After every plan wave:** Run `uv run pytest -q` (full suite) to catch cross-phase regressions
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Each row maps a plan task to its automated verification. Populated during plan execution as subplans were shipped.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-00 T1-T3 | 07-00 | 0 | Wave-0 scaffold | — | Fixtures + smoke test | unit | `uv run pytest tests/memory/test_wave0_scaffold.py -q` | ✅ | ✅ green |
| 07-01 T1 | 07-01 | 1 | MEM-01 | T-07-01/02 | EpisodicMemory append-only + SQLAlchemy ORM only (no raw SQL) | unit | `uv run pytest tests/memory/test_episodic_model.py -q` | ✅ | ✅ green |
| 07-01 T2 | 07-01 | 1 | MEM-01 | — | temporal filter (`as_of_date <= target`); Pitfall-2 regression | unit | `uv run pytest tests/memory/test_episodic_query.py -q` | ✅ | ✅ green |
| 07-01 T3 | 07-01 | 1 | MEM-01 | — | 90-day retention sweep (delete, not read-filter) | unit | `uv run pytest tests/memory/test_episodic_retention.py -q` | ✅ | ✅ green |
| 07-02 T1 | 07-02 | 1 | MEM-02 | T-07-10 | ruamel.yaml round-trip; `yaml.load(` count=0 | unit | `uv run pytest tests/memory/test_belief_schema.py -q` | ✅ | ✅ green |
| 07-02 T2 | 07-02 | 1 | MEM-03 | T-07-12 | write_belief chokepoint + field locks + human-edit guard | unit | `uv run pytest tests/memory/test_human_override.py -q` | ✅ | ✅ green |
| 07-03 T1 | 07-03 | 2 | MEM-01 | — | MemoryDeps frozen + DebatePipelineState single-writer keys | unit | `uv run pytest tests/graph/test_memory_nodes.py -q` | ✅ | ✅ green |
| 07-03 T2 | 07-03 | 2 | MEM-01/03 | T-07-20/21 | memory_recall + episodic_store; Pitfall-2; human-edit read; VETOED persistence | unit | `uv run pytest tests/graph/test_memory_nodes.py -q` | ✅ | ✅ green |
| 07-03 T3 | 07-03 | 2 | MEM-01 | T-07-22/24 | 4-variant topology; policy_sha Phase 6 -> 7 linkage | integration | `uv run pytest tests/graph/test_pipeline_with_memory.py -q` | ✅ | ✅ green |
| 07-04 T1 | 07-04 | 2 | MEM-04 | T-07-36 | compute_new_confidence pure + per-event cap 10 | unit | `uv run pytest tests/memory/test_critique_math.py -q` | ✅ | ✅ green |
| 07-04 T2 | 07-04 | 2 | MEM-04 | T-07-30/31 | RationaleOnly 1-field + forbidden-verb regex | unit | `uv run pytest tests/memory/test_self_critique_agent.py -q` | ✅ | ✅ green |
| 07-04 T3 | 07-04 | 2 | MEM-03/04 | T-07-32/35/40 | ingest_outcome 6-step loop + MEM-03 cross-requirement | unit | `uv run pytest tests/memory/test_ingest_outcome.py -q` | ✅ | ✅ green |
| 07-05 T1 | 07-05 | 3 | MEM-01..04 | T-07-51/52 | 8 e2e scenarios; 12 agents stubbed; VETOED persisted; Pitfall-2; MEM-03 x MEM-04 | integration | `uv run pytest tests/integration/test_phase7_e2e.py -q` | ✅ | ✅ green |
| 07-05 T2 | 07-05 | 3 | MEM-01 + Phase-6 audit | T-07-50 | 6 policy_sha linkage tests across Phase 6 -> Phase 7 | integration | `uv run pytest tests/integration/test_phase7_policy_sha_linkage.py -q` | ✅ | ✅ green |
| 07-05 T3 | 07-05 | 3 | phase gate | T-07-53 | full suite green; Phase 5/6 regression; ruff clean | system | `uv run pytest -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

The following fixtures, stubs, and schemas must exist before Wave 1 (core implementation) starts:

- [x] `tests/memory/__init__.py` — test package marker (shipped in Plan 07-00)
- [x] `tests/memory/conftest.py` — shared fixtures: `memory_db_session`, `beliefs_tmp_dir`, `sample_belief_yaml_path`, `sample_belief_human_edited_path`, `sample_belief_field_locked_path`, `sample_episodic_csv_path`, `sample_outcomes_yaml_path` (shipped in Plan 07-00; re-exported via `tests/graph/conftest.py` in 07-03 and `tests/integration/conftest.py` in 07-05)
- [x] `tests/memory/fixtures/beliefs/` — hand-written sample belief YAML files (flat layout at `tests/memory/fixtures/belief_aapl.yaml` + `belief_aapl_human_edited.yaml` + `belief_aapl_field_locked.yaml`; shipped in Plan 07-00)
- [x] `tests/memory/fixtures/episodic_seed.py` — helper lives at `src/ai_hedge_fund/memory/episodic.py::seed_episodic_from_csv` consuming `tests/memory/fixtures/seeded_episodic.csv` (shipped in Plan 07-00 / 07-01)
- [x] `tests/memory/fixtures/outcomes_sample.yaml` — trade-outcome fixture for self-critique tests (shipped in Plan 07-00)

*All Wave-0 fixtures present. `wave_0_complete: true` set in frontmatter.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Human opens a belief YAML and reads it in plain language | MEM-02 | Human-readability is a subjective quality bar — automation can check structure but not "a reasonable human understands this" | UAT: open `beliefs/AAPL.yaml` in a text editor, verify every field is either a plain-English string or a labeled scalar; no opaque base64/hash values in the body. |
| Human edits a belief (change confidence, add note) and next analysis reflects edit | MEM-03 | End-to-end human-in-the-loop — simulating the edit is automated, but confirming the automated replay of an analysis actually consults the edited file requires running the pipeline and reading the output | UAT: edit `beliefs/AAPL.yaml`, set `confidence: 0.2`, add a `human_note:` line; run a new analysis for AAPL through the memory-enabled pipeline; inspect the analyst prompts (via Langfuse trace) and verify the edited belief appeared in the context and the resulting thesis confidence reflects the human override. |

---

## Validation Architecture

Derived from `07-RESEARCH.md`'s `## Validation Architecture` section and the four success criteria in ROADMAP.md. Each success criterion maps to at least one automated test.

### Success Criterion 1 — Episodic memory stores + queries (MEM-01)

**Validate by:** Seeding N synthetic episodic rows, running a recall query filtered by ticker and by `as_of_date <= query_date`, asserting the returned set equals the expected subset.

- `tests/memory/test_episodic_store.py::test_append_only_insert` — insert three analyses, assert row count = 3, assert no row was mutated in place (verify with `observed_date` differences).
- `tests/memory/test_episodic_query.py::test_recall_by_ticker_filters_by_as_of_date` — seed rows at t0, t1, t2; query with `as_of_date=t1`; assert only t0 and t1 are returned (temporal correctness / Pitfall: no look-ahead).
- `tests/memory/test_episodic_query.py::test_recall_by_sector_returns_all_tickers` — seed AAPL + MSFT + JNJ; query by sector=Technology at current date; assert AAPL + MSFT returned, JNJ excluded.
- `tests/memory/test_episodic_retention.py::test_retention_purges_records_older_than_90d` — seed rows at t0 (100 days old) and t1 (10 days old); run retention job; assert t0 gone, t1 retained.

### Success Criterion 2 — Belief YAML human-readable schema (MEM-02)

**Validate by:** Pydantic round-trip on valid YAML, schema rejection on malformed YAML (unknown keys, missing required fields).

- `tests/memory/test_belief_schema.py::test_valid_yaml_loads_to_model` — read `fixtures/beliefs/AAPL.yaml`, call `Belief.model_validate(yaml.load(...))`, assert fields match expected.
- `tests/memory/test_belief_schema.py::test_unknown_key_raises` — YAML with a `foo_bar: 1` key not in schema raises ValidationError (extra="forbid").
- `tests/memory/test_belief_schema.py::test_round_trip_preserves_comments` — load YAML containing `# comment`, write back via ruamel.yaml, assert the comment survives.
- `tests/memory/test_belief_schema.py::test_field_value_types` — confidence must be float in [0, 1]; status must be literal `active|deprecated|incorrect`.

### Success Criterion 3 — Human-edit preservation (MEM-03)

**Validate by:** Simulate human edit (set `human_edited: true` and a specific `confidence` value) → run self-critique or any machine-write path → assert the human-edited field still has the human-set value.

- `tests/memory/test_human_override.py::test_write_respects_human_edited_flag` — load belief with `human_edited: true, confidence: 0.2`; call `write_belief(ticker, {"confidence": 0.9, ...}, author="machine")`; re-load belief; assert `confidence == 0.2` still; assert a log entry recorded the skip.
- `tests/memory/test_human_override.py::test_write_respects_field_locks` — load belief with `field_locks: {confidence: true}`; machine write to `confidence` skipped; machine write to a non-locked field succeeds.
- `tests/memory/test_human_override.py::test_write_never_clears_human_edited_flag` — machine write path cannot set `human_edited: false`; only explicit human action (separate API) can clear it.
- `tests/memory/test_memory_integration.py::test_next_analysis_sees_human_edit` — simulate human edit on AAPL belief; invoke memory-enabled pipeline; assert the analyst prompt includes the human-edited confidence (via captured prompt fixture).

### Success Criterion 4 — Outcome-driven self-critique (MEM-04)

**Validate by:** Deterministic Pattern 2 math (given known outcome and prior confidence, assert new confidence matches formula); LLM produces rationale only (RationaleOnly schema).

- `tests/memory/test_self_critique_math.py::test_positive_outcome_raises_confidence` — prior 0.5, outcome realized > expected, call `compute_new_confidence`, assert result > 0.5.
- `tests/memory/test_self_critique_math.py::test_negative_outcome_lowers_confidence` — prior 0.8, outcome realized < expected, assert result < 0.8.
- `tests/memory/test_self_critique_math.py::test_confidence_clamped_to_unit_interval` — edge cases at 0 and 1.
- `tests/memory/test_self_critique_node.py::test_rationale_only_schema_blocks_llm_from_writing_confidence` — confirm the LLM agent's output schema has only `rationale`, not `new_confidence` (Pattern 2 enforcement).
- `tests/memory/test_self_critique_node.py::test_critique_appends_revision_record` — after critique runs, belief YAML contains a new entry in `revisions:` with outcome, critique reasoning, new_confidence, and `updated_at`.
- `tests/integration/test_phase7_e2e.py::test_critique_never_overwrites_human_edited_belief` — simulated outcome + human-edited belief; critique runs; human-edited fields unchanged; critique log still records the skip.

### Cross-cutting: Pipeline integration tests

- `tests/integration/test_phase7_e2e.py::test_pipeline_with_memory_true_loads_episodic_hits` — seed 3 records for AAPL; run `build_debate_pipeline(with_memory=True, memory_deps=...)`; assert `state["episodic_hits"]` is non-empty and filtered by as_of_date.
- `tests/integration/test_phase7_e2e.py::test_pipeline_with_memory_and_risk_composes` — both `with_memory=True` and `with_risk=True`; pipeline runs end-to-end; episodic record includes `policy_sha` from the risk assessment (links Phase 6 audit).

### Nyquist sampling guarantee

- Every must-have in the plan checklist (see `must_haves` in PLAN.md files) maps to at least one automated command in this table.
- No must-have is validated by grep or file-existence alone — every one requires a real test function.
- Sampling continuity: no three consecutive tasks in a plan's task list are automated-free.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (15/15 tasks across Plans 07-00..07-05 map to an `uv run pytest …` command in the table above)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task commits with its own pytest run green)
- [x] Wave 0 covers all MISSING references (Wave-0 Requirements block all checked)
- [x] No watch-mode flags (all automated commands are one-shot `uv run pytest …` invocations)
- [x] Feedback latency < 30s (memory subsuite ~2s, graph subsuite <1s, integration subsuite ~2s, full suite ~20s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-22 upon Plan 07-05 completion. 199 Phase-7 tests green; cross-phase Phase-5/6 regression holds (17 integration + 122 graph/risk tests still green); full suite 920 passed, 9 skipped, 2 pre-existing baseline failures (documented in `deferred-items.md`).
