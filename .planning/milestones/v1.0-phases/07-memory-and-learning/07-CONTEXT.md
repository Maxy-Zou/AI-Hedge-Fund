---
phase: 07
phase_name: Memory and Learning
gathered: 2026-04-22
status: ready_for_planning
mode: auto-generated
---

# Phase 7: Memory and Learning - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

The system remembers past analyses and learns from outcomes — so research quality improves over time instead of starting from zero every session.

### Requirements
- **MEM-01** — Episodic memory: store completed analyses (and trade outcomes when available) in PostgreSQL with 90-day active retention; query by ticker, sector, or date range; returned results are referenced by agents in new research.
- **MEM-02** — Belief memory: structured YAML/JSON documents containing investment theses, sector models, and learned patterns. Human-readable in plain language.
- **MEM-03** — Human-editable beliefs: a human can change confidence, add notes, or mark a belief as incorrect; the next analysis for that ticker/sector reflects the human edit without being silently overwritten.
- **MEM-04** — Outcome-driven self-critique: after a trade outcome is known, the system updates relevant beliefs with the outcome and adjusts confidence. The updated belief document shows outcome, critique reasoning, and new confidence level.

### Success Criteria (must be TRUE at phase end)
1. Episodic memory stores completed analyses (and trade outcomes when available) in PostgreSQL with 90-day active retention — queries by ticker, sector, or date range return relevant prior analyses that the agent references in new research.
2. Belief memory is stored as structured YAML/JSON documents — a human can open the file, read the beliefs in plain language, and understand why the system holds each belief.
3. A human can edit a belief memory entry; the next analysis for that ticker/sector reflects the human edit — the system does not silently overwrite human corrections.
4. After a trade outcome is known, the self-critique process updates relevant beliefs with the outcome and adjusts confidence — the updated belief document shows outcome, critique reasoning, and new confidence level.

### Depends on
Phase 6 (Risk Management) — completed 2026-04-22. `RiskAssessment` and its `policy_sha` are now an authoritative audit key per Phase 6 SUMMARY; Phase 7 episodic records can and should reference `policy_sha` so replayed analyses link back to the exact policy version that produced them.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting (`workflow.skip_discuss=true`). Use the ROADMAP phase goal, success criteria, and codebase conventions (CLAUDE.md, Phase 1-6 patterns) to guide decisions.

### Non-Negotiable Invariants (from CLAUDE.md and Phase 1-6 precedent)
- **Append-only** for financial time-series — applies to episodic memory records.
- **Dual timestamps** — `as_of_date` (business date) vs `observed_date` (collection date) for every stored observation.
- **Human-readable belief memory** — never store beliefs as opaque embeddings. YAML or JSON only.
- **Immutability in code** — return new objects; no in-place mutation.
- **Tool-first** — LLMs orchestrate memory read/write via typed tools; they never compute memory operations directly.
- **Temporal correctness** — episodic queries filter by "available as of analysis date" to prevent look-ahead bias in learned patterns.
- **Humans are authoritative** — belief memory records must track a "human_edited" flag and preserve human edits against machine overwrites.

### Expected Architectural Shape
- Episodic memory = append-only SQLAlchemy table mirroring Phase 1-6 patterns (likely `DualTimestampMixin` from Phase 1), optional pgvector/embedding for semantic recall (only if it demonstrably outperforms SQL filters — do not add vector complexity without a hit rate comparison).
- Belief memory = structured YAML (or JSON) documents under a versioned `beliefs/` directory with a schema-validated loader. Each belief has an audit-trail of revisions.
- Self-critique loop = a new LangGraph node (`self_critique_node`) invoked when a trade outcome is ingested; produces a rationale-only LLM update to a belief (same Pattern 2 as Phase 6 — deterministic Python does the confidence math, LLM produces rationale only).
- Policy link-back — episodic records store `policy_sha` from Phase 6 so a reviewer can reconstruct the policy version that produced the decision.
- Integration with existing pipeline — `build_debate_pipeline` gains an optional `with_memory` switch mirroring the `with_risk` pattern; default `False` for backward compat.

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered in detail during plan-phase research (`gsd-phase-researcher` will map current patterns to RESEARCH.md). Known anchors the researcher should revisit:

- `src/ai_hedge_fund/graph/pipeline.py` — `build_debate_pipeline(with_risk=...)` — extend with `with_memory=...` mirroring the same closure-binding pattern.
- `src/ai_hedge_fund/graph/risk_deps.py` — `@dataclass(frozen=True)` deps bundle — precedent for a `MemoryDeps` bundle carrying db_session, beliefs_path, etc.
- `src/ai_hedge_fund/schemas/state.py` — `DebatePipelineState` — will likely need new keys: `episodic_hits` (list of prior analyses the agent was given) and `beliefs_consulted`.
- Phase 6 `RiskAssessment.policy_sha` — the stable audit fingerprint to carry across into episodic records.
- Phase 1 database setup (whatever PostgreSQL + SQLAlchemy scaffolding exists) — reuse session factory, `DualTimestampMixin`, and append-only conventions.
- `tests/risk/fixtures/` — Phase 6 fixture pattern (CSV-seeded portfolio, golden returns) — replicate for Phase 7 (seed a small episodic table + a few belief files for integration tests).
- Phase 5-6 TestModel stubbing pattern for PydanticAI agents — `tests/integration/test_phase6_e2e.py` is the canonical example for any new LangGraph node with an LLM agent.

</code_context>

<specifics>
## Specific Ideas

No specific pre-decided requirements — discuss was skipped. Use the four success criteria as the acceptance contract. Plan-phase should produce concrete subplans covering, at minimum:

1. **Episodic memory storage** — SQLAlchemy model + tool functions + agent-callable retrieval.
2. **Belief memory storage** — YAML/JSON schema + loader/writer + revision-tracking.
3. **Human override protection** — `human_edited` flag + test that machine updates do not clobber human edits.
4. **Self-critique on outcomes** — LangGraph node + Pattern 2 (deterministic confidence update + LLM rationale).
5. **Wiring into existing pipeline** — `build_debate_pipeline(with_memory=True)` + deps bundle + state keys.
6. **Integration tests** — end-to-end scenario: run analysis → store episodic → consult beliefs → critique on simulated outcome → verify belief updated without clobbering.

</specifics>

<deferred>
## Deferred Ideas

- **Embedding-based semantic recall** (pgvector) — deferred unless SQL filtering on ticker/sector/date range is demonstrably insufficient. Phase 7 should ship the SQL-based path first and measure recall quality before adding an embedding layer.
- **Cross-ticker pattern mining** — extracting sector-wide patterns from many episodic records is a Phase 9+ concern; Phase 7 just needs the substrate.
- **Decay / forgetting models** — 90-day retention is enforced via a scheduled job; more sophisticated decay curves can wait.
- **Belief-conflict resolution UI** — out of scope; a CLI-readable YAML is enough for MEM-02/03.

</deferred>
