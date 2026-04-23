---
phase: 07-memory-and-learning
verified: 2026-04-22T22:10:00Z
status: human_needed
score: 4/4 must-haves verified (automated); 2 manual UAT items outstanding
overrides_applied: 0
re_verification: null
human_verification:
  - test: "Human opens a belief YAML and reads it in plain language (MEM-02 subjective quality bar)"
    expected: "Every field is plain English or a labeled scalar; no opaque base64/hash values; the '# flagged' comment survives a round-trip write"
    why_human: "Human-readability is a subjective quality bar — automation can verify structure + comment-preservation (done in test_belief_schema.py and test_belief_writer.py round-trip test) but 'a reasonable human understands this' requires a human review of the fixture files"
  - test: "Human edits a belief and the next analysis reflects the edit end-to-end through a live pipeline (MEM-03 full loop)"
    expected: "Open `tests/memory/fixtures/belief_aapl.yaml` (or a deployed belief), change confidence to 20 and add a human_note; run `build_debate_pipeline(with_memory=True, ...)` on AAPL; inspect the analyst prompts via Langfuse trace and confirm the edited belief appears in the context and the resulting thesis confidence reflects the human override"
    why_human: "The read-side is verified automatically (test_human_edited_belief_survives_pipeline_read in tests/integration/test_phase7_e2e.py asserts human_edited=True and confidence=20 reach state['beliefs_consulted']); however observing the Langfuse trace and confirming the downstream analyst thesis actually cites the human-edited confidence requires a running LLM + Langfuse instance"
---

# Phase 7: Memory and Learning — Verification Report

**Phase Goal:** The system remembers past analyses and learns from outcomes — so research quality improves over time instead of starting from zero every session.

**Verified:** 2026-04-22T22:10:00Z
**Status:** human_needed (all 4 success criteria automated-verified; 2 manual UAT items per 07-VALIDATION.md)
**Re-verification:** No — initial verification.

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth (ROADMAP SC) | Status | Evidence |
|---|--------------------|--------|----------|
| 1 | Episodic memory stores analyses + outcomes in PostgreSQL with 90-day active retention; querying by ticker/sector/date returns relevant prior analyses the agent references in new research | PASSED | `src/ai_hedge_fund/db/models.py::EpisodicMemory` (append-only, JSONB payload, composite indexes `ix_episodic_ticker_asof` + `ix_episodic_sector_asof`, `policy_sha` column); `alembic/versions/003_create_episodic_memory.py`; `src/ai_hedge_fund/memory/recall.py::query_episodic` (mandatory `as_of_date <= target` Pitfall-2 filter, OR-composed ticker/sector, limit=10 DoS cap); `src/ai_hedge_fund/scripts/purge_expired_episodic.py::purge_expired` (idempotent ORM delete sweep); graph integration via `memory_recall_node` (pre-fan-out) + `episodic_store_node` (post-signal, APPROVED + VETOED) in `src/ai_hedge_fund/graph/nodes.py`. Tests: 6 model + 8 recall (incl. FUTUREX 2099 pitfall-2 regression) + 6 retention + 1 graph-level pitfall-2 + 1 e2e pitfall-2 + 1 e2e hits-populated + 8 e2e scenarios all green. |
| 2 | Belief memory stored as structured YAML/JSON; a human can open the file, read beliefs in plain language, and understand why the system holds each belief | PASSED | `src/ai_hedge_fund/schemas/memory.py::Belief` (Pydantic `extra="forbid"`, bounded thesis 10_000 / rationale 2000 / confidence 0..100) + `CritiqueEvent` (frozen audit record); `src/ai_hedge_fund/memory/beliefs.py::load_belief` returns `(Belief, ruamel.yaml raw)` — preserves comments via ruamel round-trip; test fixture `tests/memory/fixtures/belief_aapl.yaml` carries a `# flagged` comment that round-trip test `test_round_trip_preserves_comments` proves survives write. 12 schema tests (extra=forbid, types, bounds, round-trip) + 13 writer tests (comment preservation, atomic write, DoS guards) all green. |
| 3 | A human can edit a belief entry and the next analysis reflects the human edit — system does not silently overwrite human corrections | PASSED | `src/ai_hedge_fund/memory/beliefs.py::write_belief` is the MEM-03 chokepoint with three structured skip paths: `_REASON_OVERRIDE_META` (human_edited/edited_at/field_locks never machine-writable), `_REASON_FIELD_LOCKED` (field_locks[k] is True vetoes), `_REASON_HUMAN_EDITED` (global flag blocks thesis+confidence). Return dict surfaces applied[] + skipped{field: reason} for operator visibility. Read-side: `memory_recall_node` calls `load_belief` so `beliefs_consulted` state reflects the on-disk human-edited YAML. Tests: 13 writer tests incl. all three skip paths + WR-01 sector regex guard (added post-review) + WR-02 orphan-row logging. E2E: `test_human_edited_belief_survives_pipeline_read` asserts human_edited=True + confidence=20 reach state. Cross-req: `test_ingest_outcome_respects_human_edited_belief` asserts confidence stays 20 after outcome ingest while critique_history IS updated and skip is audited. |
| 4 | After a trade outcome is known, self-critique updates relevant beliefs with the outcome and adjusts confidence — document shows outcome, critique reasoning, new confidence level | PASSED | `src/ai_hedge_fund/memory/critique.py::compute_new_confidence` (pure deterministic math, int [0,100], per-event \|delta\| capped at 10 Pitfall-5 drift guard; 93 tests incl. 75-combination property grid). `src/ai_hedge_fund/agents/self_critique.py::RationaleOnly` has EXACTLY ONE field `rationale: str` — verified programmatically: `list(RationaleOnly.model_fields) == ['rationale']`; no `new_confidence`/`confidence`/`number`/`score`. `self_critique_agent` on REASONING tier with forbidden-verb word-boundary regex ({decide,judge,determine,rule,verdict} + plurals absent). `src/ai_hedge_fund/scripts/ingest_outcome.py::ingest_outcome` implements the 6-step loop: ticker regex guard → append outcome row (commits FIRST) → load belief → compute_new_confidence → LLM rationale → write_belief with CritiqueEvent append to `critique_history`. E2E `test_outcome_ingest_updates_plain_belief`: confidence moves 72 → 82 deterministically (72 + min(0.3 * 4.2 * 10, 10) = 82); critique_history gains entry with source='self_critique' + stubbed rationale. |

**Score:** 4/4 ROADMAP success criteria verified by automated tests + code inspection.

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/ai_hedge_fund/db/models.py::EpisodicMemory` | Append-only ORM model, JSONB payload, composite indexes, policy_sha column | PASSED | Class defined at line 196; `record_type` {'analysis','outcome'}; `policy_sha: String(64) nullable`; 2 composite indexes present; NO UniqueConstraint (append-only by design) |
| `src/ai_hedge_fund/memory/recall.py::query_episodic` | Mandatory as_of_date<=target filter, OR-composed ticker/sector, limit cap, ValueError on missing predicate | PASSED | Function present with `as_of_date <= target` filter (line ~80), limit=10 default, raises ValueError when both ticker & sector are None |
| `src/ai_hedge_fund/scripts/purge_expired_episodic.py` | Idempotent 90-day retention sweep via ORM delete | PASSED | `purge_expired` exists; ORM `delete()` only (no raw SQL); structlog emits `episodic_retention_sweep`; CLI entry under pragma:no-cover |
| `alembic/versions/003_create_episodic_memory.py` | Deploy DDL revision=003, down_revision=002 | PASSED | File exists (2062 bytes), revision chain correct; WR-03 fix added `nullable=False` on observed_date |
| `src/ai_hedge_fund/schemas/memory.py` | Belief (extra=forbid) + CritiqueEvent (frozen=True, extra=forbid) | PASSED | Both classes present; Belief bounds thesis≤10_000, confidence 0..100; CritiqueEvent frozen with source regex `^(self_critique\|human)$` and rationale max_length=2000 |
| `src/ai_hedge_fund/memory/beliefs.py` | load_belief (ruamel.yaml round-trip) + write_belief (3 skip paths) + belief_path_for_ticker (regex guard) | PASSED | All three functions present; 3 skip-reason constants (`_REASON_OVERRIDE_META`, `_REASON_FIELD_LOCKED`, `_REASON_HUMAN_EDITED`); atomic tmp+rename via Path.replace; `grep -c 'yaml.load(' beliefs.py` = 0 (T-07-10 RCE defense) |
| `src/ai_hedge_fund/graph/memory_deps.py::MemoryDeps` | Frozen dataclass: db_session, beliefs_path, recall_limit=10 | PASSED | @dataclass(frozen=True); TYPE_CHECKING-only SQLAlchemy import |
| `src/ai_hedge_fund/graph/nodes.py::memory_recall_node` | Pre-fan-out async node; short-circuit-safe; temporal-filter correct; human-edit-preserving; missing-belief tolerant | PASSED | Function at line 1008; calls `query_episodic` + `load_belief`; WR-01 fix added regex guard on sector path; returns `{"episodic_hits": [...], "beliefs_consulted": [...]}` as mode='json' dicts |
| `src/ai_hedge_fund/graph/nodes.py::episodic_store_node` | Post-signal/veto recorder persisting BOTH APPROVED & VETOED with policy_sha audit | PASSED | Function at line 1100; `_normalise_as_of` at DB boundary; policy_sha authoritative column + payload snapshot; VETOED persistence verified in e2e test 3 |
| `src/ai_hedge_fund/graph/pipeline.py::build_debate_pipeline` | 4-variant topology (memory × risk); ValueError guards on None deps | PASSED | `with_memory: bool = False, memory_deps: MemoryDeps \| None = None` kwargs added AFTER risk_deps (signature-order backcompat); no-kwargs call compiles cleanly (verified: CompiledStateGraph); 4 topology branches documented in docstring |
| `src/ai_hedge_fund/schemas/state.py::DebatePipelineState` | Three new single-writer keys (episodic_hits, beliefs_consulted, episodic_stored_id) — NO operator.add reducer | PASSED | Appended to class; no reducer annotation; Test 4 in test_memory_nodes.py locks the single-writer invariant via get_type_hints(include_extras=True) |
| `src/ai_hedge_fund/memory/critique.py::compute_new_confidence` | Pure deterministic math, int [0,100], per-event \|delta\| cap=10 (Pitfall-5 drift guard), ValueError on unknown direction | PASSED | Function present; `_PER_EVENT_DELTA_CAP: int = 10`; 93 tests incl. 75-combination property grid asserting bounded int |
| `src/ai_hedge_fund/agents/self_critique.py::RationaleOnly` | EXACTLY ONE field rationale:str; NO numeric field reachable | PASSED | Programmatically verified: `list(RationaleOnly.model_fields) == ['rationale']`; `{new_confidence, confidence, number, score}` disjoint; max_length=2000 DoS guard; dual-bounded with output_tokens_limit=4_000 |
| `src/ai_hedge_fund/agents/self_critique.py::self_critique_agent` | REASONING tier, retries=2, EXPLAIN-only system prompt, forbidden-verb regex absent | PASSED | `Agent[None, RationaleOnly]` on ModelTier.REASONING; `grep -ciE "\\b(decide\|judge\|determine\|rule\|verdict)\\b" self_critique.py` = 0 verified |
| `src/ai_hedge_fund/scripts/ingest_outcome.py::ingest_outcome` | 6-step loop: regex guard → append outcome → load belief → compute → LLM rationale → write_belief | PASSED | Async function at line 107; calls belief_path_for_ticker + compute_new_confidence + self_critique_agent.run + write_belief; WR-02 fix adds `logger.warning('orphan_outcome_row_created', ...)` between DB commit and belief read |

All 15 required artifacts: VERIFIED (exists, substantive, wired, data flows).

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|-----|------|--------|---------|
| `memory_recall_node` | `query_episodic` | direct call in nodes.py:1048 | WIRED | Both imported; as_of_date<=target filter enforced at the helper |
| `memory_recall_node` | `load_belief` | direct call in nodes.py:1067,1083 | WIRED | Both imported; missing file returns [] (not fatal); WR-01 sector regex guard added |
| `episodic_store_node` | `EpisodicMemory` | direct INSERT in nodes.py:1147 | WIRED | `_normalise_as_of` used at boundary; policy_sha column = payload['risk_assessment']['policy_sha'] |
| `build_debate_pipeline` | `memory_recall_node` + `episodic_store_node` | closure-bound async wrappers + add_node/add_edge | WIRED | 4-variant topology; when with_memory=True + with_risk=True, conditional_edge maps BOTH 'signal' and '__end__' through episodic_store before END |
| `ingest_outcome` | `belief_path_for_ticker` → `load_belief` → `compute_new_confidence` → `self_critique_agent.run` → `write_belief` | 6-step async call chain | WIRED | All five symbols imported from their source modules; outcome row committed FIRST (survives FileNotFoundError); write_belief skip audit returned to caller |
| `EpisodicMemory.policy_sha` | `RiskAssessment.policy_sha` (Phase 6) | episodic_store_node copies risk_assessment['policy_sha'] into column + payload | WIRED | Three-way equality asserted by `test_three_way_sha_equality`: state['risk_assessment']['policy_sha'] == row.policy_sha == row.payload['risk_assessment']['policy_sha'] == compute_policy_sha(policy) |
| `write_belief` | human-edit guard + field-lock guard + override-meta blacklist | three reason-code skip paths | WIRED | All three paths exercised by 13 writer tests + 1 e2e cross-requirement test |

All 7 critical links: WIRED with data flowing.

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `memory_recall_node` output | `episodic_hits`, `beliefs_consulted` | `query_episodic` (real SQLAlchemy SELECT) + `load_belief` (real YAML parse) | Yes — e2e test seeds 10-row CSV + belief fixture and asserts hits non-empty | FLOWING |
| `episodic_store_node` output | `episodic_stored_id` | SQLAlchemy session.add(EpisodicMemory(...)) + flush → row.id | Yes — e2e asserts stored_id is int and row queryable by ID | FLOWING |
| `ingest_outcome` belief update | updated `critique_history` + `confidence` | compute_new_confidence(deterministic) + self_critique_agent.run(LLM) + write_belief(atomic disk write) | Yes — e2e asserts confidence moves 72→82 (deterministic) and critique_history gains entry with LLM rationale; human-edited variant preserves confidence=20 | FLOWING |
| `build_debate_pipeline(with_memory=True)` state at END | `state['episodic_hits']`, `state['beliefs_consulted']`, `state['episodic_stored_id']` | Real seeded PG/SQLite session + beliefs_tmp_dir | Yes — 8 e2e scenarios run full compositions and assert populated state | FLOWING |

No HOLLOW or DISCONNECTED artifacts detected.

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite green | `.venv/bin/python -m pytest -q` | 921 passed, 9 skipped, 2 failed (pre-existing, unrelated) | PASS |
| Phase 7 subsuite green | `.venv/bin/python -m pytest tests/memory tests/graph/test_memory_nodes.py tests/graph/test_pipeline_with_memory.py tests/integration/test_phase7_*.py -q` | 200 passed in 1.05s | PASS |
| Phase-5 backcompat (`build_debate_pipeline()` with no kwargs) | `ANTHROPIC_API_KEY=test-key python -c "from ai_hedge_fund.graph.pipeline import build_debate_pipeline; build_debate_pipeline()"` | CompiledStateGraph returned, no errors | PASS |
| Pattern 2 (LLM unreachable number): RationaleOnly has exactly 1 field | `python -c "from ai_hedge_fund.agents.self_critique import RationaleOnly; assert list(RationaleOnly.model_fields) == ['rationale']"` | Assertion passes | PASS |
| T-07-10 YAML RCE defense (no `yaml.load(` in beliefs module source) | `grep -c "yaml.load(" src/ai_hedge_fund/memory/beliefs.py` | 0 | PASS |
| T-07-31 forbidden-verb invariant on self_critique prompt | `grep -ciE "\\b(decide\|judge\|determine\|rule\|verdict)\\b" src/ai_hedge_fund/agents/self_critique.py` | 0 | PASS |
| FUTUREX temporal-leakage regression seed present | `grep -n "FUTUREX\|2099" tests/memory/test_episodic_recall.py tests/graph/test_memory_nodes.py` | Multiple hits across unit + graph-integration layers | PASS |

---

## Requirements Coverage

| Req ID | Description | Status | Evidence |
|--------|-------------|--------|----------|
| MEM-01 | Episodic memory in PostgreSQL with 90-day active retention; recall by ticker/sector/date | SATISFIED | EpisodicMemory model + query_episodic (Pitfall-2 filter) + purge_expired + memory_recall_node/episodic_store_node graph wiring + 8 e2e scenarios. 26 substrate tests + 23 graph tests + 14 integration tests all green. |
| MEM-02 | Belief memory as structured human-readable YAML/JSON | SATISFIED | Belief schema with plain-English fields + ruamel.yaml round-trip preserving `# flagged` comment + `test_round_trip_preserves_comments` green. Human subjective quality verification routed to manual UAT (see human_verification). |
| MEM-03 | Human can edit a belief entry and next analysis reflects edit | SATISFIED (automated portions) | write_belief chokepoint (3 skip paths) + memory_recall_node read path + `test_human_edited_belief_survives_pipeline_read` + `test_ingest_outcome_respects_human_edited_belief` cross-requirement. Full live-pipeline + Langfuse trace review is the manual UAT item. |
| MEM-04 | Cross-session learning via self-critique after outcomes | SATISFIED | compute_new_confidence (deterministic, capped) + RationaleOnly (LLM unreachable) + ingest_outcome (6-step loop) + e2e `test_outcome_ingest_updates_plain_belief` (72→82 with audit trail). |

All 4 requirements marked complete in REQUIREMENTS.md traceability table. No orphaned requirements detected for Phase 7.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None detected in Phase 7 production code | — | — | — | — |

Grep sweep across the 15 Phase-7 source files found:
- Zero TODO/FIXME/PLACEHOLDER/HACK comments
- Zero `return null`/`return {}` placeholder bodies
- Zero hardcoded empty-array renders
- Zero `yaml.load(` unsafe-loader call patterns (verified)
- Zero forbidden verbs in self_critique prompt (verified)
- Zero raw-SQL calls in memory module or purge script (verified via `grep -rEc "execute\(text\|\.format\("`)

Pre-existing environment-level items (documented in `deferred-items.md`, out of Phase 7 scope):
- macOS `UF_HIDDEN` uv/venv workaround (chflags required before pytest invocation)
- 2 pre-existing `tests/integration/test_research_pipeline.py` async-test failures (missing pytest-asyncio plugin; fails identically on main pre-Phase-7)
- Pre-existing ruff I001 in `tests/memory/test_episodic_model.py` from 07-01 commit 4f45518 (auto-fixable; defers to cleanup chore)

---

## Cross-Phase Regression Check

Full suite: **921 passed, 9 skipped, 2 failed** (the 2 failures are documented pre-existing baseline items — `test_research_pipeline::test_research_agent_with_test_model` + `::test_signal_agent_with_test_model` — failing on main before Phase 7 started, unrelated to memory-and-learning work).

Phase-5 debate pipeline (17 integration tests + graph topology): all green, byte-for-byte backcompat when `build_debate_pipeline()` called with no kwargs.

Phase-6 risk management (122 graph/risk + 17 integration tests): all green; `test_three_way_sha_equality` proves Phase 6 → Phase 7 policy_sha audit chain remains intact.

Phase-7 subsuite: **200 tests green** (162 memory + 23 graph + 14 integration + 1 Wave-0 scaffold smoke).

---

## Code Review Status

- **07-REVIEW.md:** 9 findings (0 Critical, 3 Warning, 6 Info).
- **07-REVIEW-FIX.md:** All 3 Warnings resolved in a single iteration (WR-01 sector regex guard; WR-02 orphan-row logging; WR-03 observed_date nullable=False in mixin + migration). 6 Info findings out of scope per `fix_scope: critical_warning`.
- Full Phase 7 subsuite remained green after all three fixes.

---

## Human Verification Required

Two UAT items carried forward from `07-VALIDATION.md::Manual-Only Verifications`:

### 1. Human opens a belief YAML and reads it in plain language (MEM-02 subjective quality)

**Test:** Open `tests/memory/fixtures/belief_aapl.yaml` (or a deployed `beliefs/AAPL.yaml`) in a text editor.
**Expected:** Every field is either plain English or a labeled scalar; no opaque base64/hash values in the body; the `# flagged` inline comment is present and visible; a reasonable human can understand every belief's content without reference to code.
**Why human:** Human-readability is a subjective quality bar. Automation verifies structure (`extra=forbid`, bounds, types), round-trip comment preservation, and the absence of opaque byte-encoded fields — but the "reasonable human understands this" judgment requires a human reviewer.

### 2. Full MEM-03 end-to-end edit-then-analyze loop with live LLM + Langfuse trace

**Test:** Edit `beliefs/AAPL.yaml` (set `confidence: 20`, add a `human_note:` line, set `human_edited: true`). Run a new AAPL analysis through `build_debate_pipeline(with_memory=True, with_risk=True, ...)` with real Anthropic API keys. Open the Langfuse trace for the run.
**Expected:** The analyst prompts include the human-edited confidence (= 20) and the `human_note` text; the resulting thesis confidence reflects the human override rather than overwriting it; the stored episodic row references the same belief.
**Why human:** The read-side is verified programmatically (`test_human_edited_belief_survives_pipeline_read` asserts `human_edited=True` + `confidence=20` reach `state['beliefs_consulted']` in an e2e TestModel-stubbed run). However, confirming the downstream analyst thesis text actually cites the human-edited confidence — and that the edit drives the final thesis reasoning — requires a running LLM plus Langfuse trace inspection.

---

## Gaps Summary

**No gaps blocking goal achievement.** All 4 ROADMAP success criteria are satisfied by a combination of:
- Append-only episodic memory with mandatory temporal-filter recall (MEM-01)
- ruamel.yaml-backed human-readable belief documents with comment preservation (MEM-02)
- Three-layer human-override protection in `write_belief` + read-side integration via `memory_recall_node` (MEM-03)
- Deterministic Python `compute_new_confidence` + LLM-unreachable `RationaleOnly` schema + 6-step `ingest_outcome` loop (MEM-04)

Two manual UAT items remain open per the phase's validation strategy (MEM-02 subjective readability, MEM-03 live-pipeline edit observation). These are **by design** human-in-the-loop checks, not implementation gaps.

**Status: `human_needed`** — all automated checks passed (200/200 Phase-7 tests, 921/923 full-suite excluding pre-existing failures); handoff to UAT is the final step before Phase 8 kickoff.

---

*Verified: 2026-04-22T22:10:00Z*
*Verifier: Claude (gsd-verifier)*
