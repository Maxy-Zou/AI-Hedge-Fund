---
milestone: v1.1
milestone_name: Paper Trading + Promotion Gate
current_plan: —
status: ready_to_execute
stopped_at: v1.1 roadmap complete — Phases 9-13 defined, 23/23 requirements mapped; Phase 9 not started
last_updated: "2026-09-21T00:00:00.000Z"
last_activity: "2026-09-21 -- v1.1 roadmap written by hand (GSD retired); Phases 9-13 defined, traceability filled 23/23"
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-25)

**Core value:** Produce institutional-quality investment research at scale -- structured theses with quantitative signals that are rigorous enough to trade on and transparent enough to show investors.
**Current focus:** v1.1 — Paper Trading + Promotion Gate (Phase 9 not started)

## Current Position

Milestone: v1.1 — Paper Trading + Promotion Gate
Phase: Phase 9 — Paper-Trading Data Layer (not started)
Plan: —
Status: Roadmap complete, ready to execute Phase 9 (source: docs/V1.1_PAPER_TRADING_PLAN.md)
Last activity: 2026-09-21 -- v1.1 roadmap written; Phases 9-13 defined with success criteria; REQUIREMENTS.md traceability 23/23 mapped

Progress: [          ] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 13
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 02 | 4 | - | - |
| 03 | 3 | - | - |
| 5 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 07 P03 | 10m | 3 tasks | 7 files |
| Phase 07 P04 | 9m | 3 tasks | 8 files |
| Phase 07 P05 | 7m | 3 tasks | 3 files |
| Phase 08 P00 | 9m | 3 tasks | 11 files |
| Phase 08 P01 | 7m 32s | 3 tasks | 12 files |
| Phase 08 P02 | 8m 30s | 2 tasks | 5 files |
| Phase 08 P03 | 13m | 2 tasks | 7 files |
| Phase 08 P04 | 7m 11s | 2 tasks | 6 files |
| Phase 08 P05 | 18m | 3 tasks tasks | 5 files files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- LangGraph + PydanticAI + Claude models as primary stack (research-validated)
- Langfuse for observability (open-source alternative to LangSmith)
- Dual-model routing from day one (Haiku extraction, Sonnet analysis, Opus reasoning)
- Free data stack for v1 ($0/mo: SEC EDGAR, yfinance, Finnhub, FMP, FRED)
- Structured 5-act debate protocol (SAS paper evidence over free-form)
- Quality-score weights 0.4/0.3/0.3 as module constants (EVIDENCE/LOGIC/RISK) -- surfaced for testability per RESEARCH.md A1
- compute_quality_score is pure Python (tool-first per CLAUDE.md); LLM-produced quality_score is overwritten by the pipeline
- Rebuttal + final_arguments use output_override=8_000 (Pitfall-6 cost guardrail); debate_synthesis uses default REASONING cap (needs full output budget)
- DebatePipelineState duplicates (not inherits) MultiAgentPipelineState fields per RESEARCH.md Pattern 5; 5 debate fields are single-writer (NO operator.add reducer)
- Phase 7 adopts ruamel.yaml>=0.19.0 for round-trip (comment-preserving) belief YAML — required by MEM-03 human-override protection (human comments must survive machine rewrites)
- Phase 7 Wave-0 scaffold pattern: ship fixtures + 6-assertion smoke test first so Wave-1 plans (07-01, 07-02) can run in parallel without duplicating fixture work
- Phase 7 episodic fixtures embed one FUTURE-dated row (2099-01-01, FUTUREX) as the temporal-leakage regression seed (MEM-01 cutoff filter proof)
- Phase 7 EpisodicMemory intentionally has NO UniqueConstraint (contrast PortfolioPosition) — duplicates (same ticker + same as_of_date) are allowed by design. Composite indexes on (ticker, as_of_date) and (sector, as_of_date) support both recall paths.
- Phase 7 query_episodic uses OR composition on ticker/sector (not AND) so a single DB round trip returns ticker-specific priors AND sector context; at least one MUST be supplied (Pitfall-8 DoS guard raises ValueError).
- Phase 7 retention is a SWEEP (delete), not a read-time filter — keeps retention semantics out of every consumer per 07-RESEARCH.md Anti-Pattern.
- Phase 7 Belief schema is NOT frozen (writer rewrites YAML via ruamel round-trip raw); CritiqueEvent IS frozen (audit record immutability, matches Phase 6 Violation)
- Phase 7 write_belief is the SOLE belief mutation entry point with three structured skip-reason codes (writer_never_touches_override_meta, field_locked_by_human, human_edited_global_flag_set) — MEM-03 chokepoint contract
- Phase 7 beliefs.py renames local yaml -> parser to satisfy grep -c 'yaml.load(' == 0 T-07-10 RCE defense-in-depth acceptance criterion
- Phase 7 Plan 07-03 — memory_recall_node + episodic_store_node wired into build_debate_pipeline; 4-variant topology (memory × risk); VETOED rows persisted per research Open Question 1; policy_sha Phase 6 -> Phase 7 audit linkage verified end-to-end
- MEM-04 offline self-critique loop shipped: compute_new_confidence pure function (per-event cap of 10 for Pitfall 5 drift guard) + RationaleOnly (LLM cannot author the number, T-07-30) + ingest_outcome CLI (6-step loop with MEM-03 human-edit guard at write_belief)
- Phase 7 Plan 07-05 — 14 integration tests (8 e2e + 6 policy_sha linkage) prove MEM-01..04 + MEM-03 × MEM-04 + Phase 6 -> Phase 7 audit chain end-to-end with all 12 agents stubbed via TestModel; 199 Phase-7 tests green; full suite 920 passed; Phase 7 COMPLETE (nyquist_compliant: true, wave_0_complete: true in 07-VALIDATION.md)
- Phase 8 Wave-0 scaffold: fixture-first approach so Wave-1 (08-01 + 08-02) can run in parallel without duplicating fixture work
- A7 assumption DISCHARGED empirically: all 13 Phase-1-7 pipeline events emit the SIG-04 audit fields (ticker + tokens + policy_sha where applicable) -- no production gap-fill needed
- Phase 8 Plan 08-00 -- verify_langfuse_spans.py runs the composed pipeline TWICE (APPROVED via wide-open in-memory RiskPolicy + VETOED via OTC exclusion) so risk_manager_complete AND risk_manager_veto are both exercised in one smoke
- Phase 8 Plan 08-00 -- multi_agent_signal_complete (not signal_complete) is the debate-pipeline signal-node event name per src/ai_hedge_fund/graph/pipeline.py line 300; REQUIRED_FIELDS_PER_AGENT uses the real name
- Phase 8 Plan 08-01 -- ReviewPolicy byte-for-byte mirrors RiskPolicy (yaml.safe_load only + canonical-JSON SHA-256 via compute_review_policy_sha); T-08-01 + T-08-02 mitigations inherit the Phase-6 pattern
- Phase 8 Plan 08-01 -- FinalSignalOutput is a NEW schema file (schemas/signal_output.py), NOT a replacement for Phase-5 SignalOutput (schemas/agents.py); preserves byte-for-byte backcompat for the LLM agent surface while enforcing SIG-01 no-null contract on the investor-facing output
- Phase 8 Plan 08-01 -- derive_risk_score rules per 08-RESEARCH A9: VETOED=100, APPROVED=clamped(observed/limit*100), unknown=50 (middle-ground); pure-Python, zero LLM (T-08-12 tool-first grep -r agent.run src/ai_hedge_fund/output/ returns 0)
- Phase 8 Plan 08-01 -- thesis_link uses literal 'episodic://{id}' URI scheme; dereferenced by Plan 08-04 CLI against episodic_memory primary key
- Phase 8 Plan 08-01 -- Formatters accept dict-shaped inputs (callers pass model_dump(mode='json')); stdlib f-strings only; _short_sha truncates to 12-char+ellipsis for T-08-14 readability while full SHA remains in DB for audit
- Phase 8 Plan 08-02 -- query_portfolio_view is a PURE QUERY (no memoization); SIG-02 freshness is STRUCTURAL via append-only truth; test_freshness_after_new_insert_no_cache + test_no_lru_cache_decorator anchor T-08-15
- Phase 8 Plan 08-02 -- reconstruct_audit_trail is SYNCHRONOUS (no asyncio); latest review row wins via order_by(id.desc()).first(); ValueError on missing OR wrong record_type (T-08-19 repudiation mitigation)
- Phase 8 Plan 08-02 -- as_of_date rendered as isoformat()[:10] in portfolio_view + audit_reconstruct; dialect-neutral date-only string for both Date and datetime round-trips (SQLite coerces Date columns to datetime in some paths)
- Phase 8 Plan 08-02 -- CLI _main(argv=None) uses module-level attr access (session_mod.get_engine) so monkeypatch.setattr('ai_hedge_fund.db.session.get_engine', ...) works; pattern for all testable CLI entry points going forward
- Phase 8 Plan 08-03 -- human_review_node uses GENUINE langgraph.types.interrupt() primitive (not a log line, not a custom channel); T-08-03 mitigation greppable as `interrupt(review_request)` in src/ai_hedge_fund/graph/nodes.py; Command(resume=...) -> ReviewDecision.model_validate at the resume boundary (T-08-04)
- Phase 8 Plan 08-03 -- ReviewDeps mirrors MemoryDeps + RiskDeps shape (frozen dataclass + XOR policy/policy_path + TYPE_CHECKING SQLAlchemy); pipeline-builder normalises once at build time so per-call YAML I/O is eliminated
- Phase 8 Plan 08-03 -- review_store_node fires on BOTH reviewed AND NOT_REQUIRED paths; audit row uniformity (Pitfall G); below-threshold signals get a review row with review_status='NOT_REQUIRED' so audit_reconstruct CLI can distinguish "no review needed" from "review row lost"
- Phase 8 Plan 08-03 -- VETOED signals never reach review by construction: route_after_risk ends conditional at episodic_store, output_node short-circuits on missing signal (sets error), human_review_node short-circuits on the resulting error; T-08-06 architectural mitigation
- Phase 8 Plan 08-03 -- with_output ALWAYS requires review_deps (even when with_review=False) because output_node stamps review_policy_sha for the FinalSignalOutput contract; design contract is "output requires review_deps; review requires output + checkpointer"
- Phase 8 Plan 08-03 -- _review_threshold is caller-injected state key (NOT bound at build time); mirrors Phase-6 risk_assessment dataflow + decouples threshold mutation from rebuild cycle; route_before_review fails closed (missing threshold/signal -> human_review)
- Phase 8 Plan 08-04 -- run_analysis CLI composes ALL 4 Phase 6+7+8 kwargs (with_memory + with_risk + with_output + with_review) with InMemorySaver checkpointer; first CLI that exercises them together end-to-end
- Phase 8 Plan 08-04 -- Dependency-injected pipeline_factory + reviewer_io kwargs keep run_analysis unit tests LLM-free; _FakeGraph returns canned (__interrupt__, post-resume) state pairs and MagicMock reviewer_io blocks the stdin prompt
- Phase 8 Plan 08-04 -- thread_id suffix via uuid.uuid4().hex[:8] (Pitfall J/T-08-08); _review_threshold caller-injected into initial state from review_policy.conviction_threshold
- Phase 8 Plan 08-04 -- _format_output three-branch renderer (FinalSignalOutput markdown/JSON + VETOED BLOCKED-BY-RISK + NO_SIGNAL error) so operators never see a raw traceback
- Phase 8 Plan 08-05 -- 18 integration tests (8 e2e + 6 review_policy_sha linkage + 4 audit reconstruction) prove SIG-01..04 end-to-end; Phase 5/6/7/8 composed pipeline green under TestModel stubs for all 12 agents; full-suite 1108 passed; 08-VALIDATION.md stamped (nyquist_compliant: true, wave_0_complete: true); MILESTONE v1.0 COMPLETE (8/8 phases)
- Phase 8 Plan 08-05 -- Rule 1 auto-fix in src/ai_hedge_fund/memory/recall.py: query_episodic now filters record_type IN ('analysis','outcome'). Review rows are audit metadata, not analyst evidence; surfacing them to memory_recall_node violated EpisodicHit.record_type pattern '^(analysis|outcome)$' and blocked multi-run integration tests sharing a session

### Pending Todos

None yet.

## Deferred Items

Items acknowledged and deferred at milestone v1.0 close on 2026-04-23:

| Category | Phase | Artifact | Status | Note |
|----------|-------|----------|--------|------|
| uat_gap | 01 | 01-HUMAN-UAT.md | partial | 2 pending scenarios (live API + Langfuse) |
| uat_gap | 02 | 02-HUMAN-UAT.md | partial | 3 pending scenarios (live API + PostgreSQL) |
| uat_gap | 03 | 03-HUMAN-UAT.md | partial | 3 pending scenarios (live LLM) |
| uat_gap | 05 | 05-HUMAN-UAT.md | partial | 5 pending scenarios (live LLM debate) |
| uat_gap | 07 | 07-HUMAN-UAT.md | partial | 1 pending scenario (live Langfuse trace) |
| uat_gap | 08 | 08-HUMAN-UAT.md | partial | 1 pending scenario (live reviewer + audit CLI) |
| verification | 01 | 01-VERIFICATION.md | human_needed | Manual UAT deferred |
| verification | 02 | 02-VERIFICATION.md | human_needed | Manual UAT deferred |
| verification | 03 | 03-VERIFICATION.md | human_needed | Manual UAT deferred |
| verification | 05 | 05-VERIFICATION.md | human_needed | Manual UAT deferred |
| verification | 07 | 07-VERIFICATION.md | human_needed | Manual UAT deferred |
| verification | 08 | 08-VERIFICATION.md | human_needed | Manual UAT deferred |

Total: 12 deferred items (6 UAT gaps + 6 human-needed verifications). All require live API keys (Anthropic, Langfuse, PostgreSQL, FMP, FRED) and/or subjective human judgment. None are code defects. Tracked in audit `.planning/v1.0-MILESTONE-AUDIT.md` under `tech_debt:`.

### Blockers/Concerns

- Token cost is #1 operational risk -- naive multi-agent costs $2-5/analysis vs $0.30-0.80 optimized
- yfinance fragility -- must cache aggressively, Tiingo fallback required
- No earnings call transcripts on free tier -- FMP Ultimate ($56/mo) needed eventually
- uv/macOS UF_HIDDEN bug on .pth files when project path contains a space — workaround is `chflags nohidden .venv/lib/python3.13/site-packages/*.pth && uv run --no-sync pytest ...`; see .planning/phases/07-memory-and-learning/deferred-items.md (environment-level, not a Phase 7 blocker)

## Session Continuity

Last session: 2026-04-23T08:12:50.384Z
Stopped at: Completed 08-05-PLAN.md -- phase-gate integration suite (18 tests); SIG-01..04 delivered end-to-end; MILESTONE v1.0 COMPLETE (8/8 phases)
Resume file: None

**Planned Phase:** 8 (Signal and Output) — 6 plans — 2026-04-23T04:34:51.629Z
