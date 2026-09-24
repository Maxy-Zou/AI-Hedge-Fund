# Milestone v1.1 Requirements — Paper Trading + Promotion Gate

**Source-of-truth plan:** `docs/V1.1_PAPER_TRADING_PLAN.md`
**Goal:** Generate a credible track record from v1.0 signals via paper trading on a real clock, gated by a SHA-pinned promotion policy that joins the existing `risk_policy_sha` + `review_policy_sha` audit chain.

**Phase numbering:** Continues from v1.0 (last phase was 8). v1.1 starts at Phase 9.

**Supersedes from v1.0 deferred list:** `PAPER-01` (Alpaca paper trading) and `PAPER-02` (P&L + attribution) are decomposed into the new categories below. `PAPER-03` (automated daily research cycle) stays out of v1.1.

---

## v1.1 Requirements

### Execution surface — `EXEC-*`

- [ ] **EXEC-01**: Paper-broker client connects to Alpaca paper endpoint and submits market/limit orders for a `FinalSignalOutput` payload.
- [ ] **EXEC-02**: Deterministic order-sizing tool computes share count from `(signal, NAV, conviction)` — pure Python, never authored by an LLM (tool-first invariant).
- [ ] **EXEC-03**: Order submission is idempotent on `signal_id` so retries cannot double-fill.
- [ ] **EXEC-04**: Submission path refuses to send when `risk_assessment.status == VETOED` (fail-closed circuit breaker).
- [ ] **EXEC-05**: Broker credentials load from env vars (`ALPACA_PAPER_API_KEY`, `ALPACA_PAPER_SECRET`, `ALPACA_PAPER_HOST`); startup fails fast if any are missing.

### Paper-trading data layer — `PT-*`

- [ ] **PT-01**: `paper_trades` table is append-only (no UPDATE), records every order intent with dual timestamps (`as_of_date`, `observed_date`).
- [ ] **PT-02**: `paper_fills` table records broker fill events one row per fill, with foreign key to `paper_trades`.
- [ ] **PT-03**: `paper_trades.signal_id` foreign-keys to `episodic_memory.id` so every order traces back to its source thesis.
- [ ] **PT-04**: Alembic migration creates new tables and indexes; downgrade is reversible.
- [ ] **PT-05**: Temporal-leakage regression seed (FUTUREX-style row dated 2099-01-01) proves `as_of_date <= target` filter still holds on the new tables.

### Mark-to-market & attribution — `MTM-*`

- [ ] **MTM-01**: Daily EOD job pulls fills + current adjusted-close prices and computes per-position P&L deterministically (pure Python, no LLM).
- [ ] **MTM-02**: `paper_pnl_daily` table appends one row per (signal, date) with realized + unrealized P&L; never overwrites historical rows.
- [ ] **MTM-03**: Attribution rollup decomposes P&L by analyst (fundamental/sentiment/technical), debate-side (bull/bear winner), and conviction bucket.
- [ ] **MTM-04**: Job is idempotent — re-running for the same EOD date produces no duplicate rows (uses upsert-by-natural-key or skip-if-exists, not row UPDATE).

### Promotion gate — `PROMO-*`

- [ ] **PROMO-01**: `config/promotion_policy.yaml` declares thresholds: minimum N paper-days, minimum Sharpe, maximum drawdown, minimum hit-rate, minimum sample size.
- [ ] **PROMO-02**: `promotion_policy_sha` is computed via canonical-JSON SHA-256 — byte-for-byte identical pattern to `risk_policy_sha` (Phase 6) and `review_policy_sha` (Phase 8).
- [ ] **PROMO-03**: Pure-Python gate function maps each signal to `{paper-only, eligible-for-live, rejected}` based on its track record vs the policy thresholds. LLM may produce rationale strings only.
- [ ] **PROMO-04**: `promotion_policy_sha` joins the audit chain: state == column == payload, three-way equality test passes end-to-end.
- [ ] **PROMO-05**: Promotion-gate decisions are append-only (new row with `record_type='promotion'`), never updates.

### Track-record reporting — `TRACK-*`

- [ ] **TRACK-01**: `render_track_record --since YYYY-MM-DD --format {json,md}` CLI emits the rolling track record from `paper_pnl_daily`.
- [ ] **TRACK-02**: Markdown output is LP/YC-shareable — no internal paths, no SHAs raw, headline metrics first (Sharpe, max DD, hit rate, total return).
- [ ] **TRACK-03**: JSON output is machine-readable and includes `promotion_policy_sha` so any consumer can verify the gate the report was built against.
- [ ] **TRACK-04**: Track-record generation emits a Langfuse trace so cost-per-report can be correlated with the existing token-budget telemetry.

---

## v1.1 Non-negotiables (carried from v1.0)

These are not numbered requirements — they are invariants every v1.1 phase must honor. Verification is a per-phase responsibility.

- **Tool-first.** LLM never computes P&L, attribution, position size, promotion verdict, or any number that flows into the track record.
- **Append-only.** No row in `paper_trades`, `paper_fills`, `paper_pnl_daily`, or any new table is ever updated. Decisions create new rows.
- **Temporal correctness.** Every recall path filters `as_of_date <= target`. FUTUREX regression seeds proven on the new tables.
- **SHA-pinned policy round-trip.** `promotion_policy_sha` joins `risk_policy_sha` + `review_policy_sha` in state, column, and payload — byte-for-byte equal across all three.

---

## Future Requirements (deferred to v1.2+)

- [ ] Rich reviewer UI replacing CLI blocking stdin (web or TUI)
- [ ] Portfolio optimization on top of ranked signals (SIG-02 produces the rank; optimization is next)
- [ ] Automated compliance report generation (Langfuse trace → PDF)
- [ ] Live-run UAT closure for v1.0 Phases 1/2/3/5/7/8 (12 human-UAT items)
- [ ] VALIDATION.md frontmatter retrofit for v1.0 Phases 1/2/5/6
- [ ] Live-broker / real-capital execution (only after promotion gate clears on paper)
- [ ] Automated daily research cycle across a configurable ticker universe (v1.0 PAPER-03)

---

## Out of Scope

- **Literature mining / arXiv-SSRN auto-strategy ingestion.** Replication crisis (Hou/Xue/Zhang 2020: ~64% of 452 anomalies failed to replicate); auto-extracting strategies from papers would pollute signal with decayed anomalies. Dilutes the "research-on-filings" pitch. If revisited, ships as a separate side-project Slack digest, never wired into the agent pipeline.
- **Real-broker / live capital execution.** Only after the v1.1 promotion gate has cleared on paper for a documented window.
- **Multi-asset (crypto, forex, options).** Equities-only for v1.1; options remain in long-term scope, not this milestone.
- **High-frequency / intraday execution.** Daily cadence matches v1.0 signal cadence and Alpaca paper realities.

---

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| PT-01 | Phase 9 | Complete (PaperTrade + migration 004; L1/L2 guard `db/append_only.py`, L3 PG trigger; `tests/paper/test_append_only.py`, `test_models.py`; PR #2) |
| PT-02 | Phase 9 | Complete (PaperFill, FK paper_trades.id, UNIQUE broker_fill_id; `test_models.py`, `test_store.py`; PR #2) |
| PT-03 | Phase 9 | Complete (FK episodic_memory.id -- enforced on SQLite via `db/sqlite_compat.py`; store validates record_type='analysis' + ticker; `test_models.py::test_fk_rejects_unknown_signal`, `test_store.py`; PR #2) |
| PT-04 | Phase 9 | Complete (`alembic/versions/004`; SQLite round-trip + `compare_metadata` parity; PG-gated trigger tests; `test_migration_roundtrip.py`; PR #2) |
| PT-05 | Phase 9 | Complete (FUTUREX trade + fill @ 2099-01-01 in `tests/paper/fixtures`; `test_recall.py::test_recall_excludes_future_trades` / `_fills`, boundary `<=` proof; PR #2) |
| EXEC-01 | Phase 10 | Complete (AlpacaPaperBroker + submit_signal; live paper smoke passed; PR #4) |
| EXEC-02 | Phase 10 | Complete (execution/sizing.py pure; test_no_llm.py proves no LLM in the package; PR #4) |
| EXEC-03 | Phase 10 | Complete ((signal_id, attempt_no) DB grain + client_order_id at broker; test_submit.py; PR #4) |
| EXEC-04 | Phase 10 | Complete (decide() refuses VETOED before any broker call; test_submit.py::test_vetoed_refused_zero_broker_calls; PR #4) |
| EXEC-05 | Phase 10 | Complete (AlpacaPaperBroker names each missing credential; refuses non-paper host; PR #4) |
| MTM-01 | Phase 11 | Pending |
| MTM-02 | Phase 11 | Pending |
| MTM-03 | Phase 11 | Pending |
| MTM-04 | Phase 11 | Pending |
| PROMO-01 | Phase 12 | Pending |
| PROMO-02 | Phase 12 | Pending |
| PROMO-03 | Phase 12 | Pending |
| PROMO-04 | Phase 12 | Pending |
| PROMO-05 | Phase 12 | Pending |
| TRACK-01 | Phase 13 | Pending |
| TRACK-02 | Phase 13 | Pending |
| TRACK-03 | Phase 13 | Pending |
| TRACK-04 | Phase 13 | Pending |

**Coverage:**
- v1.1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0

**Phase ordering note.** `docs/V1.1_PAPER_TRADING_PLAN.md` drafted the execution surface as Phase A and storage as Phase B. The roadmap inverts that: storage is Phase 9, execution is Phase 10. EXEC-03 (idempotent submit on `signal_id`) cannot be built or tested without a persisted `paper_trades` row to deduplicate against, and EXEC-01 records order intent on submission -- so execution has a hard dependency on the table it writes to, not the reverse. Building storage first also means no execution code ever exists that could write an unauditable row.

---
*Requirements defined: 2026-04-25*
*Last updated: 2026-09-24 -- Phase 10 complete (EXEC-01..05), 10/23 requirements delivered*
