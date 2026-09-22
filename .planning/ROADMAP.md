# Roadmap: AI-Native Hedge Fund Multi-Agent Research System

## Milestones

- ✅ **v1.0 — Multi-Agent Research System** — Phases 1-8 (shipped 2026-04-23) — [archive](milestones/v1.0-ROADMAP.md) · [requirements](milestones/v1.0-REQUIREMENTS.md) · [audit](milestones/v1.0-MILESTONE-AUDIT.md) · [phases](milestones/v1.0-phases/)
- 🚧 **v1.1 — Paper Trading + Promotion Gate** — Phases 9-13 (planned 2026-09-21) — [requirements](REQUIREMENTS.md) · [source plan](../docs/V1.1_PAPER_TRADING_PLAN.md)

## Phases

<details>
<summary>✅ v1.0 — Multi-Agent Research System (Phases 1-8) — SHIPPED 2026-04-23</summary>

- [x] Phase 1: Foundation (3/3 plans) — completed 2026-04-12
- [x] Phase 2: Data Ingestion (4/4 plans) — completed 2026-04-12
- [x] Phase 3: Single-Agent Research (3/3 plans) — completed 2026-04-12
- [x] Phase 4: Multi-Agent Specialization (3/3 plans) — completed 2026-04-21
- [x] Phase 5: Adversarial Critique (3/3 plans) — completed 2026-04-22
- [x] Phase 6: Risk Management (6/6 plans) — completed 2026-04-22
- [x] Phase 7: Memory and Learning (6/6 plans) — completed 2026-04-22
- [x] Phase 8: Signal and Output (6/6 plans) — completed 2026-04-23

**Delivered:** LangGraph + PydanticAI multi-agent research system with 5-act bull/bear debate, Risk Manager veto, episodic + belief memory, human review gate, and compliance-grade audit trail. 1,108 tests green. See [MILESTONES.md](MILESTONES.md) for details.

</details>

### 🚧 v1.1 — Paper Trading + Promotion Gate (Phases 9-13)

**Overview:** Prove the v1.0 pipeline produces tradable signals on a real clock, with a compliance-grade record. The append-only storage substrate lands first (Phase 9) so no execution work can ever write an unauditable row; the Alpaca paper execution surface builds on it (Phase 10); daily mark-to-market turns fills into an attributable P&L series (Phase 11); a SHA-pinned promotion gate decides what has earned live capital (Phase 12); and the track-record report makes the result shareable and verifiable (Phase 13).

**Phase numbering:** Continues from v1.0 (last phase was 8).

- [ ] **Phase 9: Paper-Trading Data Layer** - Append-only `paper_trades` / `paper_fills` / `paper_pnl_daily` with dual timestamps, thesis lineage, and temporal-leakage regression
- [ ] **Phase 10: Paper Execution Surface** - Alpaca paper client, deterministic sizing tool, idempotent submit, VETOED circuit breaker
- [ ] **Phase 11: Mark-to-Market and Attribution** - Daily EOD P&L job, append-only series, attribution by analyst / debate-side / conviction
- [ ] **Phase 12: Promotion Gate** - SHA-pinned `promotion_policy.yaml`, pure-Python gate verdict, audit-chain round-trip
- [ ] **Phase 13: Track-Record Reporting** - `render_track_record` CLI, LP/YC-shareable markdown, machine-verifiable JSON

## Phase Details (v1.1)

### Phase 9: Paper-Trading Data Layer
**Goal**: Append-only tables that record every order intent and fill with full lineage back to the source thesis -- so no later execution work is capable of writing an unauditable row
**Depends on**: Phase 8 (`episodic_memory.id` is the FK target)
**Requirements**: PT-01, PT-02, PT-03, PT-04, PT-05
**Success Criteria** (what must be TRUE):
  1. An Alembic migration creates `paper_trades`, `paper_fills`, and `paper_pnl_daily` with their indexes, and `downgrade -1` followed by `upgrade head` round-trips cleanly leaving no orphaned tables, indexes, or constraints
  2. An attempted UPDATE against any row in those three tables is rejected mechanically (DB constraint or repository chokepoint) -- append-only is enforced by the system, not by convention
  3. Every `paper_trades` row carries both `as_of_date` and `observed_date`; an insert missing either one fails rather than defaulting
  4. `paper_trades.signal_id` foreign-keys to `episodic_memory.id` -- inserting a trade whose signal does not exist is rejected, so every order traces back to a thesis
  5. A FUTUREX-style regression seed dated 2099-01-01 is invisible to every recall query filtering `as_of_date <= target`, proving the temporal guarantee holds on the new tables
**Plans:** written during the Plan -> Spec -> Pre-mortem stages (CLAUDE.md, Development Workflow) before any code

### Phase 10: Paper Execution Surface
**Goal**: A signal becomes a submitted paper order, sized deterministically and refused when risk vetoes -- so the track record reflects only orders the pipeline actually sanctioned
**Depends on**: Phase 9
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-04, EXEC-05
**Success Criteria** (what must be TRUE):
  1. Given a `FinalSignalOutput` and a NAV, the sizing tool returns a share count computed in pure Python, and the Langfuse trace shows zero LLM calls between the signal and the resulting size
  2. Submitting the same `signal_id` twice produces exactly one broker order and exactly one `paper_trades` row -- a retry cannot double-fill
  3. A signal whose `risk_assessment.status == VETOED` is refused before any broker call is made, verified by asserting zero outbound HTTP requests rather than by inspecting a return value
  4. Missing any of `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET` / `ALPACA_PAPER_HOST` fails at startup with an error naming the absent variable -- not at first order submission
  5. An order submitted against the Alpaca paper endpoint returns a broker order id that is persisted to `paper_trades`, closing the loop between intent and broker state
**Plans:** written during the Plan -> Spec -> Pre-mortem stages (CLAUDE.md, Development Workflow) before any code

### Phase 11: Mark-to-Market and Attribution
**Goal**: A daily job that turns fills into an append-only P&L series decomposed by analyst, debate side, and conviction -- so performance can be attributed rather than merely totaled
**Depends on**: Phase 10
**Requirements**: MTM-01, MTM-02, MTM-03, MTM-04
**Success Criteria** (what must be TRUE):
  1. The EOD job computes realized and unrealized P&L per position from fills plus adjusted-close prices, entirely in Python, with no LLM in the path
  2. Re-running the job for an already-processed date adds zero rows and issues zero UPDATEs -- idempotency is achieved by skip-or-insert, never by mutation
  3. The attribution rollup decomposes total P&L by analyst (fundamental / sentiment / technical), by debate-side winner (bull / bear), and by conviction bucket, and the components sum to the total within rounding tolerance
  4. `paper_pnl_daily` holds exactly one row per (signal, date), and rows written on previous runs are byte-identical after a re-run
**Plans:** written during the Plan -> Spec -> Pre-mortem stages (CLAUDE.md, Development Workflow) before any code

### Phase 12: Promotion Gate
**Goal**: A SHA-pinned policy that decides whether a signal has earned live capital, joined to the existing audit chain so any verdict is reconstructible after the fact
**Depends on**: Phase 11
**Requirements**: PROMO-01, PROMO-02, PROMO-03, PROMO-04, PROMO-05
**Success Criteria** (what must be TRUE):
  1. `config/promotion_policy.yaml` declares minimum paper-days, minimum Sharpe, maximum drawdown, minimum hit-rate, and minimum sample size, and the loader rejects a policy missing any of them
  2. `promotion_policy_sha` is produced by the *same* canonical-JSON SHA-256 helper that computes `risk_policy_sha` and `review_policy_sha` -- a shared function, not a third copy of the logic
  3. The gate maps a signal to exactly one of `{paper-only, eligible-for-live, rejected}` in pure Python; the LLM contributes rationale prose only and cannot alter the verdict
  4. Three-way equality holds end-to-end: `promotion_policy_sha` in graph state == the persisted DB column == the value in the output payload
  5. Every gate decision appends a new row with `record_type='promotion'` -- re-deciding a signal leaves the prior decision row untouched and readable
**Plans:** written during the Plan -> Spec -> Pre-mortem stages (CLAUDE.md, Development Workflow) before any code

### Phase 13: Track-Record Reporting
**Goal**: An LP/YC-shareable record of what the fund actually did, verifiable by a reader against the exact policy it was gated by
**Depends on**: Phase 11, Phase 12
**Requirements**: TRACK-01, TRACK-02, TRACK-03, TRACK-04
**Success Criteria** (what must be TRUE):
  1. `render_track_record --since YYYY-MM-DD --format {json,md}` emits the rolling track record from `paper_pnl_daily` for the requested window
  2. The markdown output contains no absolute filesystem paths and no raw SHAs, and leads with headline metrics (Sharpe, max drawdown, hit rate, total return) before any detail
  3. The JSON output includes `promotion_policy_sha` and validates against a published schema, so a consumer can verify which gate the report was built against
  4. Report generation emits a Langfuse trace, letting cost-per-report be correlated with the existing token-budget telemetry
**Plans:** written during the Plan -> Spec -> Pre-mortem stages (CLAUDE.md, Development Workflow) before any code

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-04-12 |
| 2. Data Ingestion | v1.0 | 4/4 | Complete | 2026-04-12 |
| 3. Single-Agent Research | v1.0 | 3/3 | Complete | 2026-04-12 |
| 4. Multi-Agent Specialization | v1.0 | 3/3 | Complete | 2026-04-21 |
| 5. Adversarial Critique | v1.0 | 3/3 | Complete | 2026-04-22 |
| 6. Risk Management | v1.0 | 6/6 | Complete | 2026-04-22 |
| 7. Memory and Learning | v1.0 | 6/6 | Complete | 2026-04-22 |
| 8. Signal and Output | v1.0 | 6/6 | Complete | 2026-04-23 |
| 9. Paper-Trading Data Layer | v1.1 | 0/- | Not started | - |
| 10. Paper Execution Surface | v1.1 | 0/- | Not started | - |
| 11. Mark-to-Market and Attribution | v1.1 | 0/- | Not started | - |
| 12. Promotion Gate | v1.1 | 0/- | Not started | - |
| 13. Track-Record Reporting | v1.1 | 0/- | Not started | - |
