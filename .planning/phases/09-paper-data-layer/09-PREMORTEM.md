---
phase: 09
slug: paper-data-layer
status: tests-landed
delivered: 2026-09-22
written: 2026-09-22
---

# Phase 9 -- Pre-mortem

Premise: it is three months from now. Phase 9 merged, Phases 10 and 11 were built on it, and something went wrong that traces back here. Each row below is one way that happens, the invariant it breaks, and the test that would have caught it. **Every row with a test name becomes a RED test in the TDD stage before the corresponding code exists.**

Severity: **C** = corrupts the track record or leaks future data; **H** = silent wrong behaviour in prod; **M** = loud failure, easy to diagnose.

| # | Sev | Failure mode | Invariant violated | Test that catches it |
|---|---|---|---|---|
| 1 | C | The FK on `signal_id` was "tested" on in-memory SQLite, which ignores foreign keys by default. Test passed vacuously. In prod, an orphaned trade with `signal_id=99999` was inserted and the audit chain broke. | PT-03: every order traces to a thesis | `test_sqlite_fk_pragma_enabled` (asserts `PRAGMA foreign_keys == 1` on the fixture engine -- the guard for every other FK test), `test_fk_rejects_unknown_signal` (must observe `IntegrityError`) |
| 2 | C | Append-only guard was implemented as an ORM `before_flush` listener. Phase 11's mark-to-market job used `session.execute(update(PaperFill)...)` for a "quick correction". The listener never fired. History was rewritten silently. | PT-01: no UPDATE, ever | `test_core_update_statement_rejected`, `test_core_delete_statement_rejected` (L2 `do_orm_execute`) |
| 3 | C | Same as 2 but via `session.execute(text("UPDATE paper_trades SET ..."))`. Neither ORM listener can see raw SQL. | PT-01 | Postgres-gated `test_pg_trigger_blocks_raw_sql`. Plus the standing codebase rule (T-07-01: ORM only). Accepted residual: raw SQL on SQLite is unguarded, and SQLite is test-only. |
| 4 | H | The guard was registered by `tests/conftest.py` importing `db.append_only`, but no prod entry point imported it. Tests green; prod had no guard. | PT-01 in prod | `test_guard_registered_via_db_package_import` (imports only `ai_hedge_fund.db.session`, asserts `event.contains(Session, "before_flush", ...)`) |
| 5 | H | The guard was applied by checking `isinstance(obj, Base)` instead of an opt-in marker. `purge_expired_episodic` -- a legitimate retention DELETE on `episodic_memory` -- started raising in the nightly job. | v1.0 retention contract | `test_episodic_core_delete_unaffected` (runs the sweep's exact `delete(EpisodicMemory)` statement with the guard registered) |
| 6 | C | Recall used `as_of_date < target` instead of `<=`. Trades placed on the analysis date itself were invisible to same-day mark-to-market; P&L understated. | Temporal correctness, PT-05 | `test_boundary_row_at_target_is_included` |
| 7 | C | Recall omitted the temporal filter on `paper_fills` (only trades were filtered). Future-dated fills leaked into an as-of query during a backfill. | PT-05 | `test_recall_excludes_future_fills` (FUTUREX fill @ 2099-01-01) |
| 8 | H | `as_of_date` was compared as a naive datetime against an aware column (or vice versa). SQLite silently compared strings; Postgres raised. Behaviour differed by environment. | Temporal correctness | `test_naive_and_aware_inputs_equivalent`; `normalise_as_of` is the single chokepoint |
| 9 | H | Unique constraint was on `signal_id` alone. First broker rejection made that signal permanently un-submittable under append-only: can't update status, can't insert a retry. | EXEC-03 vs PT-01 (D4) | `test_same_signal_and_attempt_raises_duplicate`, `test_next_attempt_succeeds` |
| 10 | H | After an `IntegrityError` the session was left in a failed transaction. The next unrelated insert raised `PendingRollbackError`. Phase 10's submit loop died on the second signal of the day. | Store contract §3.3 | `test_session_usable_after_duplicate_submission` |
| 11 | H | ORM model and migration 004 drifted (e.g. a CHECK added to the model but not the migration). Tests run on `Base.metadata.create_all` and stayed green; prod schema, built by alembic, lacked the constraint. | 9.1 | `test_migration_matches_models` (`compare_metadata` scoped to the two paper tables) |
| 12 | M | Migration downgrade dropped the tables but not the Postgres trigger function. Re-running `upgrade` failed with "function already exists". | 9.1 reversibility | Postgres-gated `test_pg_downgrade_leaves_no_orphan_function` (queries `pg_proc`) |
| 13 | M | Migration 004 was the first ever run on SQLite in a test; an earlier revision (001-003) turned out to have a Postgres-only construct and the round-trip failed at revision 002. | 9.1 | `test_sqlite_upgrade_head_creates_paper_tables + test_sqlite_downgrade_removes_only_paper_tables_and_is_reversible` surfaces it. Contingency in PLAN T4: record the finding, fall back to Postgres-gated. Audit of 001-003 found only `JSONB().with_variant(JSON, "sqlite")`, so this is expected to pass. |
| 14 | H | Denormalized `ticker` on `paper_trades` disagreed with the episodic row's ticker after a Phase 10 bug. Recall by ticker returned the wrong company's trades. | Lineage integrity | `test_insert_raises_ticker_mismatch` |
| 15 | H | A `record_type='review'` or `'outcome'` episodic row was passed as `signal_id`. FK satisfied; lineage semantically wrong. | PT-03 | `test_insert_raises_wrong_record_type` |
| 16 | H | The CSV seeder resolved a signal by `(ticker, as_of_date)`, but `episodic_memory` permits duplicates by design. It silently picked the first. A fixture pointed at the wrong analysis and the FUTUREX test was asserting against the wrong row. | Fixture integrity | `test_duplicate_signal_rows_raise_ambiguous` |
| 17 | C | `payload` stored the full broker response, which in Phase 10 included the request headers -- and the API key. The track-record export (Phase 13) shipped it to an LP. | Security | `test_payload_rejects_secret_like_keys` (top-level key matching `secret|api_key|token|password`). Residual: nested keys are not scanned; Phase 10's spec must redact before building the payload. |
| 18 | H | `limit_price_cents` accepted a float (`123.45`) via Pydantic lax coercion and stored `123`. | Money precision (CLAUDE.md) | `test_new_trade_rejects[quantity=10.5] / [limit_price_cents=1.5] and test_new_fill_rejects[filled_qty=2.0] / [fill_price_cents=1.0]`, `test_new_trade_rejects[limit_price_cents=-1] and test_new_fill_rejects[fill_price_cents=-1]` |
| 19 | M | Removing dead `AppendOnlyMixin` broke an import somewhere nobody grepped. | Fix-as-you-find safety | Full suite gate on that commit. Grep on 2026-09-22 found zero references outside its own definition. |
| 20 | M | Promoting `_normalise_as_of` changed a subtle behaviour (e.g. how a `date` is handled) in `risk/portfolio.py`. | Behaviour preservation | Existing `tests/risk/` and `tests/memory/` suites are the proof; the promoted function is a byte-for-byte move. |
| 21 | M | `paper_pnl_daily` was deferred (D1) and Phase 11 forgot it needed a migration. | Roadmap integrity | Not a test. PLAN T8 amends ROADMAP Phase 11 Requirements to say "owns migration 005 (`paper_pnl_daily`)". |
| 22 | H | `DELETE` was permitted (only `UPDATE` guarded, reading PT-01 literally). An operator "cleaned up" a bad paper trade; the P&L series had a hole with no explanation. | Track-record permanence (D2) | `test_orm_delete_rejected`, `test_core_delete_statement_rejected` |
| 23 | M | `observed_date` was `nullable=True` (copying migration 002, which has that latent bug) instead of `nullable=False` (matching migration 003 and the mixin). | Dual-timestamp audit trail | `test_observed_date_server_default_and_not_nullable` -- and note for TECH-DEBT that migration 002's `portfolio_positions.observed_date` lacks `nullable=False`. |
| 24 | M | Test suite runtime ballooned because the file-based SQLite migration test ran the full 001-004 chain in every test in the module. | Developer experience | Module-scoped fixture builds the DB once; only the Postgres variant is `@slow`. |

## Things this phase deliberately does not defend against

- **Raw SQL on SQLite.** Test-only dialect. Accepted.
- **Nested secret-like keys in `payload`.** Phase 10 must redact at the source; Phase 9 checks the top level as a tripwire, not a guarantee.
- **Retry storms bumping `attempt_no` without bound.** Phase 10 owns the attempt cap. Phase 9 provides `CHECK (attempt_no >= 1)` only, so the DDL does not encode a policy number.
- **Concurrent inserts for the same `(signal_id, attempt_no)`.** The unique constraint resolves it at the DB; one wins, the other gets `DuplicateSubmission`. Correct by construction; no extra locking.

## Findings surfaced while writing this (fix-as-you-find candidates, not in scope)

- Migration `002_create_portfolio_positions.py` declares `observed_date` without `nullable=False`, while the ORM mixin declares it `NOT NULL`. Prod schema is looser than the model. Candidate for TECH-DEBT / a later corrective migration.
- No alembic migration has ever been executed in the test suite. Phase 9 introduces the first migration test; the pattern should be applied retroactively to 001-003 in a v1.x cleanup.
