---
phase: 09
slug: paper-data-layer
title: Paper-Trading Data Layer
milestone: v1.1
requirements: [PT-01, PT-02, PT-03, PT-04, PT-05]
depends_on: [Phase 8]
branch: phase/09-paper-data-layer
status: complete
signed_off: 2026-09-22
delivered: 2026-09-22
pr: 2
companion_docs: [09-SPEC.md, 09-PREMORTEM.md]
written: 2026-09-22
---

# Phase 9 — Paper-Trading Data Layer: Plan

**Goal** (from ROADMAP.md): Append-only tables that record every order intent and fill with full lineage back to the source thesis -- so no later execution work is capable of writing an unauditable row.

**Why this phase is first:** EXEC-03 (idempotent submit on `signal_id`) has nothing to deduplicate against until a `paper_trades` row can exist, and EXEC-01 records order intent at submission time. Execution depends on the table it writes to. Building storage first also means no execution code ever exists that could write an unauditable row.

**Scope reality check:** this phase is pure PostgreSQL/SQLAlchemy work. It needs no API keys, no LLM budget, and -- because the test suite runs on in-memory SQLite and the migration chain is SQLite-compatible -- no Docker for the primary test suite. One optional Postgres-gated test exercises the DB-level trigger and is skipped when `TEST_DATABASE_URL` is unset.

---

## Decisions requiring sign-off

Each of these changes what gets built. Approve, amend, or reject before the TDD stage starts.

**D1 -- Defer `paper_pnl_daily` to Phase 11.** ROADMAP.md success criterion 9.1 and the source plan both list three tables for this phase. Recommend creating only `paper_trades` and `paper_fills` in migration 004. `paper_pnl_daily`'s columns are defined entirely by MTM-01..04 (realized/unrealized P&L, attribution dimensions, idempotency-by-natural-key); designing them now means guessing Phase 11's spec and probably rewriting the migration. A table's schema belongs to the phase that defines its write semantics. If approved, ROADMAP 9.1 and the Phase 9 bullet get amended in this branch.

**D2 -- Forbid DELETE as well as UPDATE on paper tables.** PT-01 says "no UPDATE". A track record is permanent, and unlike `episodic_memory` there is no retention sweep planned for paper tables. Recommend the guard reject both. Corrections are new rows, never deletions.

**D3 -- `quantity` is whole shares (`Integer`).** Alpaca supports fractional shares, but the deterministic sizing tool (EXEC-02, Phase 10) will floor to whole shares, and whole-share P&L is simpler to attribute. Fractional support would be a v1.2 column change. Recommend `Integer` with `CHECK (quantity > 0)`.

**D4 -- Idempotency grain is `(signal_id, attempt_no)`, not `signal_id` alone.** A unique constraint on `signal_id` alone would make a broker rejection unrecoverable under append-only (can't update the row's status, can't insert a retry). `UNIQUE (signal_id, attempt_no)` with `attempt_no` defaulting to 1 gives: a *network* retry of the same attempt hits the constraint and is deduplicated (EXEC-03 satisfied mechanically); a *deliberate* retry after rejection is `attempt_no = 2`, a new immutable row. Phase 10 owns the policy for when to bump `attempt_no` and how many attempts are allowed.

**D5 -- Three-layer append-only enforcement, scoped to paper tables only.** Today "append-only" is a docstring convention. Roadmap criterion 9.2 asks for mechanical rejection. Recommend: (L1) SQLAlchemy `before_flush` listener rejects ORM updates/deletes; (L2) `do_orm_execute` listener rejects Core-style `update()`/`delete()` statements; (L3) a PostgreSQL `BEFORE UPDATE OR DELETE` trigger in migration 004 as defense-in-depth against raw SQL. Opt-in via a class marker so `episodic_memory` -- whose retention sweep legitimately deletes -- is untouched. Retrofitting v1.0 tables is explicitly out of scope (candidate for TECH-DEBT).

**D6 -- Two fix-as-you-find commits, separate from the phase commits.** (a) Remove the dead `AppendOnlyMixin` from `db/base.py`: it is referenced nowhere, has a nullable `as_of_date` that contradicts the real convention, and would be confused with the new guard. (b) Promote the `_normalise_as_of` helper -- currently duplicated verbatim in `memory/episodic.py` and `risk/portfolio.py` -- to `db/dates.py`, and have both existing modules import it. A third copy for the paper layer would be the wrong call in a project whose core invariant is temporal correctness. Both changes are behavior-preserving and covered by existing tests.

---

## Success criteria -> proof

| # | ROADMAP criterion | Proven by |
|---|---|---|
| 9.1 | Migration creates the tables + indexes; `downgrade -1` then `upgrade head` round-trips cleanly | `tests/paper/test_migration_roundtrip.py::test_sqlite_upgrade_head_creates_paper_tables + test_sqlite_downgrade_removes_only_paper_tables_and_is_reversible`, `::test_migration_matches_models` (autogenerate diff is empty) |
| 9.2 | UPDATE against any paper row is rejected mechanically | `tests/paper/test_append_only.py` (L1 ORM update + delete, L2 Core `update()` + `delete()`, guard NOT applied to `episodic_memory`), Postgres-gated `test_pg_trigger_blocks_raw_sql` |
| 9.3 | Every `paper_trades` row carries both timestamps; insert missing either fails | `tests/paper/test_models.py::test_as_of_date_required`, `::test_observed_date_server_default_and_not_nullable` |
| 9.4 | `signal_id` FK to `episodic_memory.id`; unknown signal rejected | `tests/paper/test_models.py::test_sqlite_fk_pragma_enabled` (guard), `::test_fk_rejects_unknown_signal`, `tests/paper/test_store.py::test_insert_raises_signal_not_found` |
| 9.5 | FUTUREX row (2099-01-01) invisible to every `as_of_date <= target` recall | `tests/paper/test_recall.py::test_recall_excludes_future_trades`, `::test_recall_excludes_future_fills`, `::test_boundary_row_at_target_is_included` |

---

## Tasks (ordered; each is one or more atomic commits)

Every task follows RED -> GREEN -> refactor. No implementation file is created before its failing test exists. Commit prefixes: `test:` for RED, `feat:` / `fix:` / `refactor:` for GREEN, `chore:` for fixtures and tooling.

**T0 -- Fix-as-you-find (D6), two commits, before any phase code.**
- `refactor(db): remove dead AppendOnlyMixin` -- delete the class + docstring mention; full suite must stay 1134/9.
- `refactor(db): promote normalise_as_of to db/dates.py` -- new module; `memory/episodic.py` and `risk/portfolio.py` import it under their existing private names. Existing tests are the proof.

**T1 -- SQLite FK enforcement + guard test.**
- RED: `test_sqlite_fk_pragma_enabled` asserts `PRAGMA foreign_keys` returns 1 on the `sqlite_engine` fixture. Fails today.
- GREEN: `db/sqlite_compat.py` registers a global `Engine "connect"` listener that sets the pragma for `sqlite3` connections. `db/__init__.py` imports it for its side effect so registration happens whenever anything under `ai_hedge_fund.db` is imported (tests and prod alike).

**T2 -- Models + migration 004.**
- RED: `tests/paper/test_models.py` -- column presence, NOT NULLs, CHECK constraints, unique constraints, FK rejection (needs T1), timestamp semantics.
- GREEN: `PaperTrade` + `PaperFill` in `db/models.py` (both use `DualTimestampMixin` + the new `AppendOnlyGuard` marker). `alembic/versions/004_create_paper_trading_tables.py` with reversible downgrade and a dialect-guarded Postgres trigger.

**T3 -- Append-only guard (D5).**
- RED: `tests/paper/test_append_only.py` -- ORM update raises, ORM delete raises, Core `update()` raises, Core `delete()` raises, `AppendOnlyViolation` names the table, guard is registered on the `Session` class, Core delete on `EpisodicMemory` still succeeds.
- GREEN: `db/append_only.py` -- `AppendOnlyGuard` marker mixin, `AppendOnlyViolation` exception, two listeners. Imported by `db/__init__.py`.

**T4 -- Migration round-trip.**
- RED: `tests/paper/test_migration_roundtrip.py` -- file-based SQLite: `upgrade head` -> both tables + all indexes present -> `downgrade 003` -> paper tables absent, `episodic_memory` etc. intact -> `upgrade head` again. Plus `test_migration_matches_models` using `alembic.autogenerate.compare_metadata` scoped to the two paper tables (catches ORM/DDL drift, the classic "tests green on `create_all`, prod schema wrong" failure).
- GREEN: whatever 004 needs to make it pass. If an earlier revision turns out not to run on SQLite, that is a finding to record, and the test falls back to Postgres-gated.
- Postgres-gated (`@pytest.mark.slow`, skipped without `TEST_DATABASE_URL`): same round-trip, plus `test_pg_trigger_blocks_raw_sql` proving `text("UPDATE paper_trades ...")` is rejected by the trigger, plus assertion that `downgrade` leaves no orphaned function in `pg_proc`.

**T5 -- Records + store.**
- RED: `tests/paper/test_store.py` -- happy-path insert returns a frozen record; `SignalNotFound`; `SignalTickerMismatch` (denormalized ticker must equal the episodic row's); `SignalWrongRecordType` (only `record_type='analysis'` rows are signals); `DuplicateSubmission` on same `(signal_id, attempt_no)` with the session still usable afterwards (rollback happened); `attempt_no + 1` succeeds; fill insert; `TradeNotFound`; `DuplicateFill`; payload validator rejects top-level keys that look like secrets; cents fields reject floats and negatives.
- GREEN: `paper/errors.py`, `paper/records.py` (frozen `NewPaperTrade`, `NewPaperFill`, `PaperTradeRecord`, `PaperFillRecord`), `paper/store.py` (`insert_paper_trade`, `insert_paper_fill`).

**T6 -- Recall (PT-05).**
- RED: `tests/paper/test_recall.py` -- temporal filter on trades and fills, FUTUREX exclusion, boundary inclusion (row exactly at target is returned), `as_of_date DESC` ordering, `limit`, DoS guard (`ticker` or `signal_id` required), naive vs aware datetime inputs produce identical results.
- GREEN: `paper/recall.py` (`query_paper_trades`, `query_paper_fills`).

**T7 -- CSV seeders + fixtures.**
- RED: `tests/paper/test_seed.py` -- seeder resolves `signal_id` by `(ticker, as_of_date, record_type='analysis')`; raises `SignalNotFound` on zero matches and `AmbiguousSignal` on more than one (episodic allows duplicates by design); fill seeder resolves trade by `broker_order_id`; row count returned.
- GREEN: `paper/seed.py`; `tests/paper/fixtures/seeded_paper_trades.csv` (includes the FUTUREX 2099-01-01 row referencing the existing FUTUREX episodic row) and `seeded_paper_fills.csv`; `tests/paper/conftest.py`.

**T8 -- Amend planning docs (if D1 approved).** ROADMAP 9.1 + Phase 9 bullet drop `paper_pnl_daily`; Phase 11 Requirements line notes it owns migration 005. `09-SUMMARY.md` written with each criterion checked off against the test that proves it. PROGRESS.md entry. TECH-DEBT.md entry for "retrofit append-only guard to v1.0 tables".

**T9 -- Code review, then PR.** Full-branch review against 09-SPEC.md, 09-PREMORTEM.md, and CLAUDE.md Agent Development Rules. CRITICAL/HIGH fixed in-branch; MEDIUM/LOW to TECH-DEBT. PR to `main` linking all three docs.

---

## Explicitly out of scope

- Any Alpaca client, HTTP, or credential handling (Phase 10).
- Order sizing, submit logic, the VETOED circuit breaker (Phase 10). Phase 9 stores `risk_status_at_submit` as an audit fact; it does not decide anything from it.
- `paper_pnl_daily`, P&L, attribution (Phase 11, per D1).
- Any LangGraph node or `Deps` dataclass. Storage functions take a `Session`; Phase 10 wires them into a node.
- A production seed CLI. Seeders are test fixtures. PT-05 is a test-level proof.
- Retrofitting the append-only guard onto `episodic_memory` / `portfolio_positions`.

## Verification gates (every commit that touches code)

- `uv run pytest -q` -- green; count grows from 1134.
- `uv run ruff format --check . && uv run ruff check .` -- clean.
- `uv sync --frozen --extra dev` -- resolves. Phase 9 adds no dependencies.

## Open questions

None that block this phase. The four open questions in `docs/V1.1_PAPER_TRADING_PLAN.md` (NAV baseline, promotion thresholds, live data feed, short side) belong to Phases 10-12 and are unaffected by anything here.
