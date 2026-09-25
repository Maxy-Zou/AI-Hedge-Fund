---
phase: 11
slug: mark-to-market
title: Mark-to-Market and Attribution
milestone: v1.1
requirements: [MTM-01, MTM-02, MTM-03, MTM-04]
depends_on: [Phase 10]
branch: phase/11-mark-to-market
status: signed-off (D1-D7 as recommended; D3/D4 amended by 11-SPEC A1/A2)
signed_off: 2026-09-25
companion_docs: [11-SPEC.md, 11-PREMORTEM.md]
written: 2026-09-25
---

# Phase 11 -- Mark-to-Market and Attribution: Plan

**Goal** (ROADMAP.md): A daily job that turns fills into an append-only P&L series decomposed by analyst, debate side, and conviction -- so performance can be attributed rather than merely totaled.

**Success criteria** (ROADMAP.md):
1. The EOD job computes realized and unrealized P&L per position from fills plus adjusted-close prices, entirely in Python, with no LLM in the path.
2. Re-running the job for an already-processed date adds zero rows and issues zero UPDATEs -- skip-or-insert, never mutation.
3. The attribution rollup decomposes total P&L by analyst (fundamental / sentiment / technical), by debate-side winner (bull / bear), and by conviction bucket, and the components sum to the total within rounding tolerance.
4. `paper_pnl_daily` holds exactly one row per (signal, date), and rows written on previous runs are byte-identical after a re-run.

**What Phase 10 left ready:** `paper_trades` rows with `broker_order_id`, deterministic `client_order_id`, and `execution_policy_sha` in `payload`; `insert_paper_fill()` with `UNIQUE (broker_fill_id)`; `latest_adj_close_cents()` with the "latest observed row wins" tie rule; `policy_sha.fingerprint()`; the `AppendOnlyGuard` + PG trigger pattern; the standalone-CLI shape (`submit_signal`, D1 of Phase 10).

**What this phase needs from the environment:** Alpaca paper credentials (already in `.env`) for one live-gated fill-ingestion smoke test. Everything else runs on SQLite with `FakeBroker`; Postgres for the migration round-trip and trigger test, same split as Phases 9-10.

---

## Gaps found while planning (drive D1-D3)

- **Nothing writes `paper_fills` in production.** Only `paper/seed.py` (a test fixture) calls `insert_paper_fill`; Phase 10 explicitly deferred fill ingestion here. MTM has no input until this exists.
- **Attribution inputs are not persisted.** `episodic_store_node` (`graph/nodes.py:1178`) stores `thesis`, `signal`, `risk_assessment` only. The per-analyst outputs (`analyst_signals`) and `debate_synthesis` live in graph state and are discarded. There is also no stored "debate winner" field anywhere -- `DebateSynthesis` carries `pre_debate_confidence` / `post_debate_confidence` but no verdict.
- **Migration numbering:** 005 and 006 are taken by Phase 10, so `paper_pnl_daily` is **007** (ROADMAP already says so; the docstring in `004_*.py` still says 005 -- fix-as-you-find, T0).

---

## Decisions requiring sign-off

**D1 -- Fill ingestion is in scope, as its own standalone step.** `ingest_fills --since DATE` pulls Alpaca account activities of type `FILL` (one record per execution, stable activity id -> `broker_fill_id`), joins each to its `paper_trades` row by `broker_order_id`, and appends via `insert_paper_fill`. Idempotent by the existing `UNIQUE (broker_fill_id)`: a re-run hits the constraint and skips. A fill whose order is not in `paper_trades` is logged and skipped, never inserted with a guessed trade id. `BrokerClient` gains `list_fills(since) -> list[BrokerFill]`; `FakeBroker` implements it. Alternative rejected: reading `filled_qty` / `filled_avg_price` off the order -- it collapses partial fills into one synthetic row with no stable id.

**D2 -- Persist attribution inputs going forward; old rows are `unattributed`, never backfilled.** `episodic_store_node` payload moves to `schema_version: 2`, adding `analyst_signals` (per analyst: `analyst`, `direction`, `confidence`) and `debate` (`pre_debate_confidence`, `post_debate_confidence`, `quality_score`). Rows at `schema_version: 1` land in an explicit `unattributed` bucket on every dimension except conviction (which *is* stored, as `confidence`). Reconstructing analyst views for old rows would be fabricated data. **This touches a v1.0 graph node**, which is why it needs your sign-off; the change is additive (readers of v1 payloads are unaffected) and covered by the existing Phase 7-8 store tests plus new ones.

**D3 -- Deterministic attribution rules (pure Python, integer cents).**
- *Analyst* (stance derivation specified in 11-SPEC.md A2 -- the analyst schemas carry no direction field): a signal's daily P&L is split equally among the analysts whose `direction` matched the executed side; if none matched, it goes to `none_aligned`. Remainder cents go to analysts in fixed order (fundamental, sentiment, technical) so the split is exact and reproducible.
- *Debate side:* `delta = post_debate_confidence - pre_debate_confidence`. `delta > 0` -> the side aligned with the executed direction wins (`bull` for a long); `delta < 0` -> the opposing side; `delta == 0` -> `draw`. **Your call:** this measures "who moved the thesis", not "who argued better". The alternative is an LLM-judged winner, which would put a model in the P&L path (criterion 1) -- not recommended.
- *Conviction:* buckets from `config/mtm_policy.yaml` (default `low <50`, `medium 50-74`, `high >=75`), SHA-pinned via `policy_sha.fingerprint()` as `mtm_policy_sha` on every row.

Each dimension partitions the total, so each sums to the total exactly (criterion 3's "within rounding tolerance" becomes "exactly", which is stricter).

**D4 -- SUPERSEDED by 11-SPEC.md A1** (cached `adj_close` rows keep their download-day adjustment factor, so the ratio below misses dividends; replaced by raw-close marks plus broker dividend cash events). Original text kept for the record: **Price basis: adjusted-return anchored at the fill.** CLAUDE.md requires adjusted close for return calculations, but fill prices are raw. Mixing them (mark at `adj_close`, cost at fill price) produces phantom losses after every dividend. Rule: `unrealized = qty * fill_price * (adj_close[t] / adj_close[fill_date] - 1)`, computed in `Decimal`, rounded half-even to cents once per row. Both closes come from `daily_prices` rows with `observed_date <= run time`, using the same tie rule as `execution/prices.py`; the chosen `price_source` is stored on the row (partly closes the Phase 10 R10 TECH-DEBT item). A missing price for `t` or `fill_date` -> no row for that signal/date and a logged `skipped_no_price`, never a zero row.

**D5 -- Realized P&L is FIFO over sell fills; expect it to be zero for now.** Phase 10 is long-only with no exit logic, so the only sells would be manual closes on Alpaca. The job handles them correctly (FIFO lots per signal) but no exit policy is added here. **Consequence for Phase 12:** hit-rate and Sharpe will run on unrealized P&L until an exit rule exists -- worth deciding before Phase 12's spec.

**D6 -- Idempotency and immutability.** `UNIQUE (signal_id, pnl_date)`; the job computes the full batch, then inserts only the (signal, date) pairs not already present (criteria 2 and 4). Only *completed* trading days may be marked: `pnl_date` must be before today in `America/New_York`, or today after 16:30 ET -- otherwise a partial-day price would be frozen permanently. The table carries `AppendOnlyGuard` + the PG trigger from migration 004. Corrections are out of scope: a wrong row stays wrong, which is why the price-completeness and trading-day guards are hard failures.

**D7 -- The rollup is computed, not stored.** `attribution_rollup(session, start, end)` reads `paper_pnl_daily` and returns a typed `AttributionReport`; each row already stores its own `attribution` JSON (analyst split, debate winner, conviction bucket), so the rollup is a pure `GROUP BY` in Python. No second table to keep in sync. Phase 13's report calls the same function.

---

## Criterion -> proving test (filled in by 11-SPEC.md, finalized in 11-SUMMARY.md)

| # | Criterion | Planned proof |
|---|---|---|
| 11.1 | Pure-Python P&L, no LLM | `tests/mtm/test_pnl.py` table tests; `tests/mtm/test_no_llm.py` (package scan, as Phase 10) |
| 11.2 | Re-run adds 0 rows, 0 UPDATEs | `tests/mtm/test_job.py::test_rerun_inserts_nothing` (row count + SQLAlchemy `before_cursor_execute` counter asserts no UPDATE) |
| 11.3 | Components sum to total | `tests/mtm/test_attribution.py` property test over random splits (hypothesis if already a dev dep, else table tests) |
| 11.4 | One row per (signal, date); byte-identical after re-run | migration 007 unique constraint test; `test_job.py::test_prior_rows_byte_identical` (snapshot rows, re-run, compare) |

---

## Tasks (ordered; RED -> GREEN -> refactor)

**T0 -- Fix-as-you-find.** Correct the stale "migration 005" note in `004_create_paper_trading_tables.py`'s docstring. Separate commit.

**T1 -- MTM policy.** RED: `test_mtm_policy.py` -- loads, `extra=forbid`, bucket bounds contiguous and non-overlapping, SHA deterministic and change-sensitive. GREEN: `mtm/policy.py`, `config/mtm_policy.yaml`.

**T2 -- Persist attribution inputs (D2).** RED: store-node test asserts `schema_version == 2` with `analyst_signals` and `debate`; v1 reader test still passes. GREEN: `episodic_store_node` payload.

**T3 -- Migration 007 (D6).** RED: parity + round-trip + unique + append-only guard tests for `paper_pnl_daily`. GREEN: ORM model, `alembic/versions/007_create_paper_pnl_daily.py`, PG trigger.

**T4 -- Fill ingestion (D1).** RED: `test_ingest_fills.py` (FakeBroker fills -> rows; re-run -> zero new rows; unknown order -> skipped + logged; partial fills -> one row each), adapter test with the SDK mocked. GREEN: `BrokerClient.list_fills`, `AlpacaPaperBroker.list_fills`, `mtm/ingest.py`, `scripts/ingest_fills.py`.

**T5 -- Pure P&L core (D4, D5).** RED: `test_pnl.py` -- adjusted-return anchoring across a dividend, FIFO realized on a manual sell, half-even rounding, no float money, temporal seed (a future price must not be used). GREEN: `mtm/pnl.py`.

**T6 -- Attribution (D3).** RED: `test_attribution.py` -- equal split with remainder, none-aligned, debate delta rules incl. draw, v1 rows -> `unattributed`, sums exact. GREEN: `mtm/attribution.py`.

**T7 -- EOD job + CLI (D6).** RED: `test_job.py` (skip-or-insert, completed-day guard, missing price -> skip not zero, byte-identical re-run, zero UPDATE). GREEN: `mtm/job.py`, `scripts/mark_to_market.py --date` (with `--dry-run`, DI factories as `submit_signal`).

**T8 -- Rollup (D7).** RED: `test_rollup.py` -- each dimension sums to total across a date range. GREEN: `mtm/rollup.py`.

**T9 -- Live-gated smoke + docs.** `test_alpaca_live.py::test_list_fills_roundtrip` (`@slow`, skips without creds). ROADMAP Phase 11 complete; REQUIREMENTS MTM-01..04; `11-SUMMARY.md`; PROGRESS; TECH-DEBT for deferred items (exit policy, row corrections, scheduler).

**T10 -- Code review, then PR.** Same protocol as Phases 9-10, including an independent second-round review.

---

## Explicitly out of scope

- Exit / sell policy and any new order types (D5). Shorts.
- Correcting a written `paper_pnl_daily` row (D6) -- no revision mechanism this phase.
- Backfilling attribution for `schema_version: 1` analyses (D2).
- Scheduling the job (PAPER-03, deferred); Sharpe / drawdown / hit-rate (Phase 12); report rendering (Phase 13).
- Choosing a preferred price vendor (TECH-DEBT R10) -- this phase records the source; it doesn't rank vendors.

## Verification gates (every code commit)

- `uv run pytest -q` green; `uv run ruff format --check . && uv run ruff check .` clean; `uv sync --frozen --extra dev` resolves.
- The `mtm` package contains no LLM import -- enforced by a test.

## Sign-off (2026-09-25)

Approved as recommended: D2 (additive `schema_version: 2` payload), D3 (confidence-delta debate rule), D5 (realized effectively zero until an exit policy exists). Amendments A1 (price basis) and A2 (analyst stance rule) arose during the Spec stage and are recorded in 11-SPEC.md.
