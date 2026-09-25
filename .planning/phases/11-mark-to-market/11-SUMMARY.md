---
phase: 11
slug: mark-to-market
status: implementation complete -- code review (T10) pending, PR not opened
delivered: 2026-09-25
branch: phase/11-mark-to-market
requirements: [MTM-01, MTM-02, MTM-03, MTM-04]
migrations: [007]
---

# Phase 11 -- Mark-to-Market and Attribution: Summary

**Goal:** A daily job that turns fills into an append-only P&L series decomposed by analyst, debate side, and conviction -- so performance can be attributed rather than merely totaled.

**Outcome:** Implemented. All four ROADMAP criteria have a proving test, and the suite is green on SQLite and, for every DB-touching `mtm` test, on PostgreSQL. Every implementation commit was preceded by a RED test commit. **Not yet reviewed:** T10 (independent review) has not run, so this is not ready to merge.

## Goal achievement

| # | Success criterion | Status | Evidence |
|---|---|---|---|
| 11.1 | P&L from fills + the day's close + broker dividends, pure Python, no LLM (amended by A1) | VERIFIED | `tests/mtm/test_pnl.py` (pure table tests, int-only), `test_job.py::test_mark_uses_close_cents_not_adj_close`; `tests/mtm/test_no_llm.py` (source scan and an import-closure check in a clean interpreter) |
| 11.2 | Re-run adds zero rows and issues zero UPDATEs | VERIFIED | `test_job.py::test_rerun_issues_no_update` and `test_store.py::test_rerun_skips_existing_and_issues_no_update` (a `before_cursor_execute` counter sees no UPDATE/DELETE); PG trigger `test_migration_007.py::test_pg_trigger_rejects_update` |
| 11.3 | Analyst / debate / conviction components sum to the total | VERIFIED (exactly, not within tolerance) | `test_rollup.py::test_each_dimension_sums_to_total` (500 random books incl. 1-cent and negative totals); `rollup_rows` raises `AttributionInvariantError` on any mismatch (`::test_invariant_violation_raises_not_logs`) |
| 11.4 | One row per (signal, date); earlier rows byte-identical after a re-run | VERIFIED | `UNIQUE (signal_id, pnl_date)` (`test_migration_007.py::test_unique_signal_date`); `test_job.py::test_prior_rows_byte_identical` (every column incl. JSON text, after a new price source and a new signal) |

## What shipped

| Area | Files |
|---|---|
| Policy | `config/mtm_policy.yaml`, `mtm/policy.py` -- conviction buckets (must cover 0..100 exactly), sentiment threshold, stance-rule version, close buffer; SHA-pinned |
| Attribution inputs | `graph/nodes.py` `episodic_store_node` writes payload v2 (`analyst_stances`, `debate`, `mtm_policy_sha`); `graph/memory_deps.py` gains `mtm_policy` |
| Schema | `alembic/versions/007_create_paper_pnl_daily.py`: `paper_pnl_daily` (cumulative, one row per signal/day, total = realized + unrealized CHECK) and `paper_cash_events`; both append-only (ORM guard + PG trigger on 004's function) |
| Store | `mtm/records.py`, `mtm/store.py` (skip-or-insert, whole-batch rollback -> `ConcurrentRun`), `mtm/errors.py` |
| Broker | `BrokerClient.list_activities`; `execution/alpaca_activities.py` (SDK-model shape check, exact cents, fractional refused); adapter paging via the SDK's `RESTClient.get` |
| Ingest | `mtm/ingest.py`, `scripts/ingest_fills.py` |
| P&L | `mtm/pnl.py` (FIFO, raw-close mark, dividends), `mtm/dividends.py` (pro rata, exact), `mtm/inputs.py`, `mtm/job.py`, `scripts/mark_to_market.py` |
| Rollup | `mtm/rollup.py` (`attribution_rollup` -- Phase 13 calls this) |
| Shared | `db/dates.py` `trading_date` / `market_midnight_utc` (New York) |

Operating order (until PAPER-03 schedules it): after the close, run `python -m ai_hedge_fund.scripts.ingest_fills --since <date>`, then `python -m ai_hedge_fund.scripts.mark_to_market` (defaults to the last completed trading day).

## Decisions as executed

D1 (fill ingestion in scope), D2 (additive payload v2), D3 (confidence-delta debate rule), D5 (FIFO; realized is dividends-only until an exit policy exists), D6 (skip-or-insert, completed-day guard), D7 (rollup computed on read) -- as planned. D4 was replaced in the Spec stage by **A1**, and D3's analyst rule was defined by **A2** (both below).

## Deviations from 11-PLAN

- **A1 -- price basis.** The plan's adjusted-close ratio could not work: `store_prices` inserts with `ON CONFLICT DO NOTHING`, so each cached `adj_close` keeps the adjustment factor of the day it was downloaded. Marks use the raw close; dividends come from broker `DIV*` activities as realized income. **Deliberate exception** to CLAUDE.md's "always use adjusted close for return calculations": this is an accounting P&L of a broker account, and the cumulative series already includes dividends, so return series derived from it (Phase 12) are total-return. ROADMAP 11.1 and MTM-01 were reworded.
- **A2 -- analyst stance.** Analyst outputs have no direction field; the stance is derived (factor counts; sentiment threshold) and frozen at store time.
- **New table `paper_cash_events`** in migration 007 (needed by A1).
- **`BrokerClient.list_activities`** replaces the plan's `list_fills`; it also carries dividends and corporate actions.
- **`Attribution.schema` -> `attribution_schema`** (shadowed `BaseModel.schema`); spec updated.
- **Corporate actions** are detected and the affected signal skipped, not applied (TECH-DEBT).

## Found and fixed along the way (separate commits)

- **Worktree could not import the package** -- the new venv's editable `.pth` carried the macOS `hidden` flag, which Python 3.13 skips (environment fix; noted in project memory).
- **`submit_signal --json` stdout was not pure JSON in production** (`fix:` commit): structlog was never configured, so the Alpaca adapter's `paper_order_submitted` line printed ahead of the JSON. `route_logs_to_stderr()` added; regression test uses a broker that logs.
- Migration 004 docstring named the wrong migration for `paper_pnl_daily`.

## Pre-mortem coverage

All 36 rows map to a test that exists in the suite -- checked mechanically at T9 by matching every `::test_name` in `11-PREMORTEM.md` against the test files (five names were reconciled to the tests as written; one test lives in `test_store.py` rather than `test_job.py`). The "known and accepted" items are in `.planning/TECH-DEBT.md`.

## Vendor contract notes

- alpaca-py 0.44.0 has `TradeActivity` / `NonTradeActivity` models but no `TradingClient` method for `/account/activities`; the adapter uses the SDK's own `RESTClient.get` (same auth and paper-host guard), so no new dependency.
- **Probed live 2026-09-25:** the endpoint returns a JSON list; the paper account had **no FILL or DIV activity yet**, so item bodies in the unit tests follow Alpaca's documented shape, not a captured one. `test_alpaca_live.py::test_list_activities_roundtrip` passed (read-only). The first real fill should be checked against the parser.

## Verification

- `uv run pytest -q` -> **1751 passed, 14 skipped** (from 1515 at branch start).
- `uv run ruff format --check . && uv run ruff check .` -> clean.
- `uv sync --frozen --extra dev` -> resolves (no dependency change this phase).
- PostgreSQL: `TEST_DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund_test uv run pytest -m slow tests/mtm tests/paper` -> migration 007 trigger + downgrade tests pass. The DB-touching `mtm` tests (`test_job`, `test_store`, `test_rollup`, `test_ingest`: 57) also passed against a throwaway Postgres database via a temporary fixture override -- the suite's fixtures are SQLite-only, so this run is manual (TECH-DEBT).
- Live: `test_alpaca_live.py::test_list_activities_roundtrip` passed against Alpaca paper.

## Code review

Pending (T10).

## Handoff to Phase 12 (Promotion Gate)

- Read P&L through `mtm.rollup.attribution_rollup` or `mtm.store.query_pnl_rows`; rows are cumulative per signal, so daily returns are differences of consecutive rows.
- Realized P&L is dividends only until an exit policy exists (D5); hit-rate on realized trades is not yet meaningful.
- Days a signal was skipped (no price, corporate action, oversold) have no row: treat as missing, not as zero.
