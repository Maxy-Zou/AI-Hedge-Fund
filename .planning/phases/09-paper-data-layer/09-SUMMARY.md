---
phase: 09
slug: paper-data-layer
status: complete
delivered: 2026-09-22
branch: phase/09-paper-data-layer
pr: 2
requirements: [PT-01, PT-02, PT-03, PT-04, PT-05]
tests_added: 94 functions (1134 -> 1283 passed incl. parametrized; 11 skipped, 2 of them PostgreSQL-gated)
---

# Phase 9 -- Paper-Trading Data Layer: Summary

**Goal:** Append-only tables that record every order intent and fill with full lineage back to the source thesis -- so no later execution work is capable of writing an unauditable row.

**Outcome:** Delivered. All five ROADMAP success criteria proven by named tests. Every implementation commit was preceded by a RED commit; no implementation file exists without a failing test that motivated it.

## Goal achievement

| # | Success criterion | Status | Evidence |
|---|---|---|---|
| 9.1 | Migration creates the tables + indexes; `downgrade` then `upgrade head` round-trips cleanly | VERIFIED | `tests/paper/test_migration_roundtrip.py::test_sqlite_upgrade_head_creates_paper_tables` (both tables, 4 indexes, 3 uniques, both FKs present at `004`), `::test_sqlite_downgrade_removes_only_paper_tables_and_is_reversible` (paper tables gone at `003`, every v1.0 table intact, `head` restorable), `::test_migration_matches_models` (`compare_metadata` reports zero structural diffs between migration DDL and ORM). Postgres-gated `::test_pg_downgrade_leaves_no_orphan_function`. Scope amended per D1: `paper_pnl_daily` is Phase 11's. |
| 9.2 | UPDATE against any paper row is rejected mechanically | VERIFIED | `tests/paper/test_append_only.py` -- L1 `::test_orm_update_rejected`, `::test_orm_update_rejected_on_fills`, `::test_orm_delete_rejected`; L2 `::test_core_update_statement_rejected`, `::test_core_delete_statement_rejected`; scope `::test_episodic_core_delete_unaffected`, `::test_episodic_orm_update_unaffected`; registration `::test_guard_registered_via_db_package_import` (subprocess importing only `db.session`). L3 Postgres trigger: `test_migration_roundtrip.py::test_pg_trigger_blocks_raw_sql` (gated). |
| 9.3 | Every `paper_trades` row carries both timestamps; insert missing either fails | VERIFIED | `tests/paper/test_models.py::test_as_of_date_required`, `::test_observed_date_server_default_and_not_nullable` (server-populated, `nullable=False` on both tables). |
| 9.4 | `signal_id` FK to `episodic_memory.id`; unknown signal rejected | VERIFIED | `test_models.py::test_sqlite_fk_pragma_enabled` (the guard that makes FK tests non-vacuous), `::test_fk_rejects_unknown_signal`, `::test_fk_rejects_fill_for_unknown_trade`; `test_store.py::test_insert_raises_signal_not_found`, `::test_insert_raises_wrong_record_type`, `::test_insert_raises_ticker_mismatch`. |
| 9.5 | FUTUREX row (2099-01-01) invisible to every `as_of_date <= target` recall | VERIFIED | `tests/paper/test_recall.py::test_recall_excludes_future_trades`, `::test_recall_excludes_future_fills`, `::test_future_rows_visible_once_target_reaches_them` (seed really exists), `::test_boundary_row_at_target_is_included` (`<=` not `<`), `::test_naive_and_aware_inputs_equivalent`. |

## What shipped

| Area | Files |
|---|---|
| Schema | `src/ai_hedge_fund/db/models.py` (`PaperTrade`, `PaperFill`), `alembic/versions/004_create_paper_trading_tables.py` |
| Guards | `src/ai_hedge_fund/db/append_only.py` (L1 + L2 listeners, `AppendOnlyGuard`, `AppendOnlyViolation`), `src/ai_hedge_fund/db/sqlite_compat.py` (FK pragma), `src/ai_hedge_fund/db/__init__.py` (side-effect registration) |
| Shared | `src/ai_hedge_fund/db/dates.py` (`normalise_as_of`, promoted from two private copies) |
| Package | `src/ai_hedge_fund/paper/` -- `errors.py`, `records.py`, `store.py`, `recall.py`, `seed.py`, `__init__.py` |
| Tests | `tests/paper/` (6 modules, `conftest.py`, 3 CSV fixtures), `tests/unit/test_db_dates.py` |
| Removed | `AppendOnlyMixin` (dead since Phase 1) |

## Decisions as executed

| | Decision | Outcome |
|---|---|---|
| D1 | Defer `paper_pnl_daily` to Phase 11 | Done. ROADMAP 9.1 and Phase 11 requirements line amended in this branch. |
| D2 | Forbid DELETE as well as UPDATE | Done. Both ORM layers and the PG trigger reject both. |
| D3 | `quantity` whole shares | Done. `Integer` + `CHECK > 0`; `NewPaperTrade.quantity` is a strict int. |
| D4 | Idempotency = `(signal_id, attempt_no)` | Done. `uq_paper_trades_signal_attempt`; `test_store.py::test_next_attempt_succeeds` proves a rejection is recoverable. |
| D5 | 3-layer guard, opt-in | Done. `EpisodicMemory` untouched; its retention `delete()` statement is pinned by a test. |
| D6 | Two fix-as-you-find commits first | Done. `e8aaad3` (dead mixin), `976a14b` (helper promotion, 7 new unit tests). |

## Deviations from 09-PLAN

- **Migration 004 moved from T2 to T4.** Nothing tests a migration until the round-trip test, so writing it in T2 would have been code before its test. Same scope, stricter ordering.
- **T7 (seeders + fixtures) ran before T6 (recall)** so recall tests could use the seeded ledger instead of hand-built rows.
- **Fixtures are self-contained** (`tests/paper/fixtures/seeded_signals.csv`) rather than borrowing `tests/memory/`'s CSV as 09-SPEC §4 suggested. The paper suite cannot now break when another suite's data changes.
- **Seven test names in 09-PLAN / 09-PREMORTEM were reconciled to the names actually used** (e.g. the float/negative money checks folded into parametrized `test_new_trade_rejects`). Docs follow code; intent unchanged.
- **One test-count correction:** the T5 commit message says 47 tests; `test_store.py` has 17 functions expanding to 44 cases. The suite total in each commit message is the authoritative number.

## Pre-mortem coverage

24 failure modes listed. 20 have a test that exercises them on SQLite. Three are PostgreSQL-gated and skip without `TEST_DATABASE_URL` (#3 raw-SQL trigger, #12 orphan function, and the PG half of #11). One (#21, "Phase 11 forgets `paper_pnl_daily`") is a documentation control, now recorded in ROADMAP. Accepted residuals are unchanged from the pre-mortem: raw SQL on SQLite, nested secret-like payload keys, unbounded `attempt_no` (Phase 10's cap).

Two findings the pre-mortem did not predict surfaced during TDD and are in TECH-DEBT.md: SQLAlchemy's JSON type stores `None` as the string `'null'` (the paper tables now use `none_as_null=True`; `EpisodicMemory.payload` has the same latent gap), and the suite had never executed an alembic migration before this phase.

## Code review (T9)

Reviewed at high effort against the spec, the pre-mortem, and CLAUDE.md before un-drafting. **Ten findings, all fixed in `07104d8`, each with a RED test first.** The two that mattered most:

- **The payload secret tripwire rejected `tokens_used`** -- a key every v1.0 pipeline event already emits. Phase 10's first real order would have failed validation. The regex is now anchored on underscore/edge.
- **The L3 trigger existed only in the migration.** A database bootstrapped with `Base.metadata.create_all` -- exactly what was done on 2026-04-24 -- would have had no trigger and no error. The idempotent DDL is now also attached to the `Table` objects, so either path produces it.

The rest: L2 was blind to `update(Model.__table__)` (now keyed on table name as well as mapper; legacy `Query.update()` covered too); the parity test silently dropped FK diff kinds and never compared CHECKs (both now covered); `limit` accepted negatives (unbounded on SQLite); unique-violation detection was a substring match on driver text (now SQLSTATE / `sqlite_errorname`); seed CSV headers were never validated and `attempt_no=0` became 1; three modules still imported the private `_normalise_as_of` alias; migration `upgrade()` was 75 lines; and the `RAISE` message carried a bare `%` through two formatting layers (now `USING MESSAGE`, no `%` at all).

**PostgreSQL verification (after review):** all three layers proven on a real PostgreSQL 16 instance (docker container `ai_hedge_fund_postgres`, scratch databases `ai_hedge_fund_test` / `ai_hedge_fund_scratch`). The two `@slow` tests passed: raw `text()` `UPDATE` and `DELETE` are rejected by the trigger with `append-only table paper_trades: UPDATE not permitted; write a new row instead`, and `downgrade` leaves no orphan in `pg_proc`. The `create_all` path was proven separately on a scratch database: both `trg_paper_*_append_only` triggers and the function exist after `Base.metadata.create_all`, raw mutations are blocked, and a second `create_all` is idempotent. Migrations 001-004 also ran end-to-end on PostgreSQL for the first time in the suite's history.

## Handoff to Phase 10

- Write orders through `ai_hedge_fund.paper.insert_paper_trade(session, NewPaperTrade(...))`. It validates lineage and raises typed `PaperStoreError`s; after any of them the session is already rolled back.
- Idempotency is structural: a network retry of the same `(signal_id, attempt_no)` raises `DuplicateSubmission` -- treat it as "already submitted", do not resubmit. A deliberate retry after broker rejection is `attempt_no + 1`. **Phase 10 owns the attempt cap**; the DDL only enforces `>= 1`.
- **Redact before building `payload`.** The store rejects top-level keys that look like secrets; it does not scan nested dicts. Broker request/response objects must be scrubbed of headers and credentials at the client boundary.
- `risk_status_at_submit` is an audit snapshot the store does not act on. The EXEC-04 circuit breaker (refuse when VETOED) is Phase 10 logic; when it fires, record the refusal as `submit_status='refused_veto'`, `broker_order_id=None`.
- **The dev database (`ai_hedge_fund`) carries a stale April prototype of the paper schema** -- `paper_trades` / `paper_fills` / `paper_pnl_daily` with different columns (`target_qty` float, no `attempt_no`, no policy SHAs, no `payload`), no triggers, all three empty, and `alembic_version` already stamped `004` by a migration file that never reached the repo. `alembic upgrade head` will therefore do nothing there and report current. Before Phase 10 writes to dev: drop the three empty tables, `UPDATE alembic_version SET version_num='003'`, then `alembic upgrade head`. Verified 2026-09-22 that no rows exist to lose.
- To run the PostgreSQL-gated tests: `docker compose up -d` (the compose project is pinned to `aihedgefund` in `docker-compose.yml` so it adopts the container created from the old directory name), then `TEST_DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund_test uv run pytest tests/paper -m slow`. The database name must contain `test` or the tests refuse to run.

## Commits (in order)

`195befe` merge main · `e8aaad3` remove dead AppendOnlyMixin · `976a14b` promote normalise_as_of · `aa88072` SQLite FK pragma · `b867d26` models · `0a42ecc` append-only guard · `969819c` migration 004 + round-trip · `1791d3e` records + store · `b8b7a79` seeders + fixtures · `95ccc89` recall · `e1a72fe` docs · `07104d8` review fixes (10/10) · (this commit) summary.
