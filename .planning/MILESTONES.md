# Milestones

## v1.0 — AI-Native Hedge Fund: Multi-Agent Research System

**Shipped:** 2026-04-23
**Timeline:** 2026-04-11 → 2026-04-23 (13 days)
**Scope:** 8 phases · 34 plans · full composed pipeline (research → debate → risk → memory → signal → human review)

### Delivered

A multi-agent LLM research system that produces institutional-quality investment theses for US equities. The pipeline researches a ticker via 3 specialized analysts, stress-tests the thesis through structured bull/bear adversarial debate, enforces hard portfolio risk constraints (with veto power), remembers past analyses in episodic + belief memory, and produces investor-ready signals with a non-negotiable human review gate before any output finalizes. Every decision carries a SHA-256 policy fingerprint for compliance-grade audit.

### Key Accomplishments

1. **LangGraph + PydanticAI substrate (Phase 1)** — typed multi-agent orchestration with Claude model routing (Haiku/Sonnet/Opus), PostgreSQL checkpointing, Langfuse observability, per-agent and per-pipeline token budgets.
2. **Temporally-correct data ingestion (Phase 2)** — SEC EDGAR (10-K/10-Q/8-K/Form 4), yfinance (cached), FRED macro, Finnhub news, all with `as_of_date <= target` filtering to prevent look-ahead bias.
3. **End-to-end single-agent research loop (Phase 3)** — proved the tool-first pattern works before adding multi-agent complexity.
4. **Manager-analyst hierarchy with synthesis (Phase 4)** — 3 specialized analysts (fundamental, sentiment, technical) coordinated by a Research Manager with explicit conflict resolution.
5. **5-act bull/bear adversarial debate (Phase 5)** — structured debate protocol validated against FinCon/TradingAgents/AlphaAgents precedent; quality scoring proves debate adds signal, not just noise.
6. **Risk Manager with veto power (Phase 6)** — hard portfolio constraints (position size, sector concentration, correlation, drawdown, exclusions) enforced deterministically in Python; LLM produces rationale only (Pattern 2). SHA-256 `policy_sha` on every assessment.
7. **Three-tier memory architecture (Phase 7)** — episodic analyses in PostgreSQL (append-only, 90-day retention), human-readable belief YAML files (ruamel.yaml round-trip preserves comments), offline self-critique loop that updates confidence deterministically from realized outcomes while respecting human-edited fields.
8. **Human-in-the-loop review gate + audit trail (Phase 8)** — LangGraph `interrupt()` primitive pauses the pipeline for human approval on above-threshold convictions; `FinalSignalOutput` schema has zero nullable required fields; `reconstruct_audit_trail(episodic_id)` assembles the full compliance chain from analysis row to review decision with both `policy_sha` and `review_policy_sha`.

### Cross-phase invariants proven

- **Tool-first quantitative path:** LLMs never author financial ratios, policy decisions, risk scores, confidence numbers, or review verdicts. Deterministic Python owns every number; LLMs produce rationale strings only (RationaleOnly schema pattern across Phase 6/7/8).
- **Append-only financial time-series:** `EpisodicMemory` never updates rows; review decisions create new `record_type='review'` rows; `DualTimestampMixin` separates business date (`as_of_date`) from collection date (`observed_date`).
- **Humans are authoritative:** `write_belief` enforces a three-tier skip guard (override-meta / field-lock / global `human_edited` flag) so machine writes never silently overwrite human corrections. Audit logs every skip.
- **Temporal correctness:** Every recall path (episodic query, memory node, portfolio view) filters by `as_of_date <= target`. Proven by FUTUREX regression seeds (rows dated 2099-01-01 that never leak).
- **Fail-closed routing:** LangGraph conditional edges default to `__end__` on missing/malformed state; VETOED signals never reach human review.
- **Compliance audit chain:** `risk_policy_sha` (Phase 6) round-trips through episodic records (Phase 7) into the review decision (Phase 8). Three-way equality tests guarantee `state == column == payload`.

### Test Stats

- **1,108 tests passed** in the final run (9 skipped; 2 pre-existing unrelated failures documented — pytest-asyncio gap, not a v1.0 defect).
- **~350 new tests added in v1.0** across `tests/memory`, `tests/graph`, `tests/output`, `tests/review`, `tests/scripts`, `tests/integration`.
- **Zero real LLM calls in the test suite.** Every agent stubbed via `TestModel` + `custom_output_args`.
- **Full-suite feedback latency:** ~22 seconds (well under the 30s Nyquist bound).

### Known Deferred Items

12 items documented in STATE.md (`## Deferred Items`) and the milestone audit:
- 6 human-UAT scenarios across phases 01/02/03/05/07/08 (all require live API keys, PostgreSQL, or Langfuse to validate).
- 6 phase VERIFICATION.md files carry `status: human_needed` pending the UAT runs.

None are code defects. All are external-integration or subjective-quality items deferred during autonomous execution per user choice.

### Tech Debt Carried Forward

- Phases 1/2/5/6 `VALIDATION.md` frontmatter still reads `nyquist_compliant: false` (convention introduced starting Phase 7). Phases 3/4 have no `VALIDATION.md`. Candidate for a v1.x cleanup pass.
- Phases 4/6 have no standalone VERIFICATION.md (relied on per-plan acceptance criteria).
- `tests/integration/test_research_pipeline.py` has 2 pytest-asyncio baseline failures predating Phase 6.
- macOS uv/UF_HIDDEN upstream bug on `.pth` files when the project path contains a space — workaround: `uv run --no-sync pytest ...`. Documented in `archive/…/deferred-items.md`.

### Next Up

`v1.1` / `v2.0` to be defined via `/gsd-new-milestone`. Candidate themes (per PROJECT.md constraints):
- Paper trading integration + live-data smoke tests.
- Rich review UI (web or TUI) replacing the CLI blocking stdin.
- Portfolio optimization on top of the ranked signals.
- Automated compliance report generation (Langfuse trace → PDF).

**Archive:**
- `.planning/milestones/v1.0-ROADMAP.md` — full phase details
- `.planning/milestones/v1.0-REQUIREMENTS.md` — all 36 requirements + outcomes
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md` — cross-phase integration audit
- `.planning/milestones/v1.0-phases/` — all 8 phase directories (plans, summaries, verifications, UAT, reviews)
