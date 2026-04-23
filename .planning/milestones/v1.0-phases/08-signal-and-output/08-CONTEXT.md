---
phase: 08
phase_name: Signal and Output
gathered: 2026-04-22
status: ready_for_planning
mode: auto-generated
---

# Phase 8: Signal and Output - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

The pipeline produces investor-ready output with full audit trail and human review gate — so every signal that reaches a trading decision has been researched, debated, risk-checked, and approved by a human.

### Requirements
- **SIG-01** — Signal output schema: direction (long/short/neutral), conviction (0-100), one-paragraph thesis summary, risk_score, link to full thesis document. All fields populated; no nulls.
- **SIG-02** — Portfolio-level view: ranks analyzed tickers by conviction, shows thesis summaries, groups by sector. Ranking updates when new analyses complete.
- **SIG-03** — Human review gate: signals with conviction above a configurable threshold pause the pipeline, present thesis + debate transcript to a reviewer, and do not finalize until human approves/rejects.
- **SIG-04** — Full audit trail: every agent step (inputs, outputs, reasoning, model used, tokens consumed, timestamp) is logged. A compliance reviewer can trace backward through every step that produced a given final signal.

### Success Criteria (must be TRUE at phase end)
1. Each ticker's signal output includes all five SIG-01 fields, every run.
2. Portfolio view ranks by conviction, shows summaries, groups by sector, updates on new analyses.
3. Above-threshold signals pause the pipeline until a human approves/rejects.
4. Given any final signal, every step is traceable end-to-end via logs (compliance-grade).

### Depends on
Phase 7 (Memory and Learning) — complete 2026-04-22. The pipeline now carries risk_assessment (Phase 6, with policy_sha), episodic_hits/beliefs_consulted/episodic_stored_id (Phase 7), plus the thesis/signal/debate context from Phase 3-5. Phase 8 is the last assembly layer: output formatting, portfolio aggregation, human-in-the-loop interrupt, observability/audit.

### Positioning / non-negotiable
Human review is NON-NEGOTIABLE per CLAUDE.md and per the founder's AI-washing aversion. This phase exists so no signal escapes to a live trade without explicit human approval. The human gate must be a real LangGraph interrupt (not a log line the human is supposed to read after the fact).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
Implementation choices at executor discretion (discuss phase skipped per `workflow.skip_discuss=true`). Use ROADMAP goal + success criteria + Phase 1-7 conventions.

### Non-Negotiable Invariants (from CLAUDE.md and precedent)
- **Human review gate is a REAL interrupt** — LangGraph `interrupt_before` / `interrupt_after` on the output node, or an explicit interrupt primitive. A log message saying "please review" is not enough.
- **Every agent step logged** — Langfuse is the primary audit store (open-source, self-hosted). Local structlog already captures per-node events; Langfuse adds cross-session traceability.
- **Schema validation at the output boundary** — `SignalOutput` is a Pydantic model with no optional/null fields on the required contract (direction, conviction, thesis_summary, risk_score, thesis_link). Nulls violate SIG-01.
- **Portfolio view is a query**, not a materialized table — derived from episodic_memory + latest-analysis-per-ticker. Freshness follows writes automatically.
- **Threshold is configurable** — a YAML-loaded `review_policy` (mirrors Phase 6's `RiskPolicy`) with an integer conviction threshold (default e.g. 70). Re-uses the `policy_sha`-style audit fingerprint concept.
- **Backcompat** — `build_debate_pipeline()` with no kwargs and `build_debate_pipeline(with_risk=True)` + `build_debate_pipeline(with_memory=True)` remain byte-for-byte compatible. Phase 8 adds `with_review=True` + `with_output=True` kwargs (or a single `with_output=True` that implies the review gate, TBD in planning).

### Expected Architectural Shape
- `src/ai_hedge_fund/schemas/signal_output.py` — `SignalOutput` Pydantic model (all required fields; no nulls).
- `src/ai_hedge_fund/output/portfolio_view.py` — query function that ranks by conviction + groups by sector (reads from episodic_memory).
- `src/ai_hedge_fund/graph/review_gate.py` or `nodes.py::human_review_node` — LangGraph interrupt at the output boundary.
- `src/ai_hedge_fund/schemas/review_policy.py` — `ReviewPolicy` YAML loader (threshold + review message template).
- Langfuse instrumentation is likely already live from Phase 1; Phase 8 extends per-node metadata (tokens, duration, model) if gaps exist.
- CLI or simple JSON-output command for end-users (e.g., `scripts/run_analysis.py --ticker AAPL --json`) so the fund's founder can run an analysis and get a human-readable signal back.

</decisions>

<code_context>
## Existing Code Insights

Details mapped during plan-phase research (`gsd-phase-researcher` writes RESEARCH.md). Anchors the researcher should revisit:

- `src/ai_hedge_fund/graph/pipeline.py` — `build_debate_pipeline(with_risk=False, risk_deps=None, with_memory=False, memory_deps=None)` — Phase 8 extends with `with_output=True` and optionally `with_review=True`. Mirror the kwarg-only + ValueError-guard pattern.
- `src/ai_hedge_fund/graph/nodes.py::signal_node` — current exit node. Phase 8 either wraps this or replaces it with `output_node` + `human_review_node`.
- `src/ai_hedge_fund/schemas/state.py::DebatePipelineState` — add output-related keys: `signal_output`, `review_decision` (APPROVED/REJECTED), `review_timestamp`, `portfolio_view` (transient).
- Phase 6 `RiskPolicy` + `policy_sha` pattern — direct template for `ReviewPolicy` + `review_policy_sha`.
- Phase 7 `EpisodicMemory` table — **source of truth** for portfolio view queries. `query_episodic` + a new `latest_analysis_per_ticker` helper.
- Langfuse setup (Phase 1) — verify span/event coverage is sufficient for SIG-04 compliance-grade audit; gap-fill if not.
- Phase 5/6/7 TestModel stubbing patterns — `tests/integration/test_phase7_e2e.py` is the canonical integration test shape. Phase 8 integration tests will stub the human review decision (accept/reject) and assert the downstream flow.
- `.env` / config conventions — `ReviewPolicy` lives under `config/` or as a path arg, same pattern as `tests/risk/fixtures/risk_policy_sample.yaml`.

</code_context>

<specifics>
## Specific Ideas

Use the four success criteria as the acceptance contract. Plan-phase should produce concrete subplans covering, at minimum:

1. **SignalOutput schema + formatter** — Pydantic model, never-null contract, serializer to Markdown + JSON.
2. **Portfolio view** — query over episodic_memory returning ranked list grouped by sector.
3. **Human review gate** — LangGraph interrupt node with a structured `ReviewRequest` payload (thesis, debate transcript, risk_assessment, proposed signal); resume via `ReviewDecision` (APPROVED/REJECTED + reviewer_note).
4. **Review policy** — YAML-loaded threshold + review_policy_sha fingerprint mirror of RiskPolicy.
5. **Audit trail completeness** — verify Langfuse captures per-agent tokens/model/timestamp; extend structlog if gaps.
6. **Pipeline integration** — `build_debate_pipeline(with_output=True, review_policy_path=...)`; routes high-conviction signals to human_review_node; persists review decision in episodic_memory as an outcome-style row; compose with with_risk and with_memory.
7. **Integration tests** — End-to-end: run pipeline → high-conviction signal → interrupt fires → simulate approval → episodic row updated with decision → trace is complete.
8. **CLI entry** — `scripts/run_analysis.py --ticker X` that prints the structured SignalOutput (markdown + JSON flag). First user-facing deliverable.

</specifics>

<deferred>
## Deferred Ideas

- **Interactive CLI / TUI / web UI for human review** — a minimal "print the review request + read stdin for APPROVED/REJECTED" is enough for v1. Rich UI can come in a later milestone.
- **Multi-reviewer consensus / approval workflow** — single-reviewer is enough for v1; compliance flags can come later.
- **Real-time portfolio rebalancing suggestions** — out of scope; Phase 8 delivers per-ticker signals + a portfolio *view*, not portfolio *actions*.
- **Broker integration / live order submission** — explicitly out of scope. No signal is ever sent to a broker in v1.
- **Automated compliance report generation** — SIG-04 ships the audit log substrate; formatted compliance reports are a later deliverable.
- **Email/Slack/Teams notifications of pending reviews** — nice-to-have for v2; for v1 the reviewer runs the CLI and sees the interrupt directly.
</deferred>
