# Technical Debt Register

Deferred refactors and known debt. Each entry cites the phase/plan that introduced
the debt and the expected resolution timing.

## Open

- **nodes.py split (introduced Phase 6, plan 06-05):** `src/ai_hedge_fund/graph/nodes.py`
  grew to ~910 lines after Phase 6, exceeding CLAUDE.md's 800-line soft cap. Split
  deferred to avoid diff/merge risk against Phase 6 integration tests. Target: Phase 7
  prelude or a dedicated refactor plan — split into `nodes/foundation.py`,
  `nodes/multi_agent.py`, `nodes/debate.py`, `nodes/risk.py` with a re-exporting
  `nodes/__init__.py`. Pure refactor with zero behavior change.

- **Append-only guard not retrofitted to v1.0 tables (Phase 9, D5):** `episodic_memory` and
  `portfolio_positions` still rely on docstring convention; only `paper_trades` / `paper_fills`
  inherit `AppendOnlyGuard`. `episodic_memory` has a legitimate retention DELETE
  (`scripts/purge_expired_episodic.py`), so a retrofit needs an allow-listed sweep path first.
  Target: v1.2 hardening.

- **`EpisodicMemory.payload` accepts JSON null (found Phase 9 T2):** the column is
  `nullable=False`, but SQLAlchemy's JSON type stores a Python `None` as the JSON *string*
  `'null'`, so a half-written audit row can slip past NOT NULL. Paper tables use
  `JSON(none_as_null=True)`; episodic should too. One-line change with the full suite as proof;
  kept out of Phase 9 because it alters a v1.0 table's storage contract.

- **submit_signal has no concurrency guard (Phase 10 review F6; narrowed by review round 2):**
  two concurrent runs for one signal compute the same attempt and therefore the same deterministic
  client_order_id, so the broker accepts only one order (the other gets "duplicate" and adopts it).
  What remains: the losing run fails at the (signal_id, attempt_no) unique constraint with a DB error
  instead of a clean AlreadySubmitted. Safe for the single-threaded CLI; a scheduler (PAPER-03) should
  take a per-signal advisory lock. Deferred. Filed 2026-09-24, updated same day.

- **Price source precedence is undecided (Phase 10 review round 2, R10):** `daily_prices` can hold a
  yfinance and a tiingo row for the same day. `execution/prices.py` now resolves ties to the most
  recently collected row -- deterministic, so dry-run and submit agree -- but prefers no source.
  Whether one vendor should always win is a product decision; the chosen source is also not yet
  recorded in the trade payload. Filed 2026-09-24. *Update 2026-09-25 (Phase 11):* the EOD job uses
  the same tie rule on the exact date and records `price_source` on every `paper_pnl_daily` row.

- **Mark-to-market: corporate actions detected, not applied (Phase 11, A1):** a SPLIT / SPIN /
  MA / NC after a signal's first fill makes the EOD job skip that signal (`skipped_corporate_action`)
  from then on. Applying them needs lot adjustment (qty and cost basis) per action type. Until then
  such a signal stops accruing P&L rows. Filed 2026-09-25.

- **Mark-to-market: no correction path for a written `paper_pnl_daily` row (Phase 11, D6):** rows
  are append-only with one row per (signal, date). A row computed before that day's fills or
  dividends were ingested is permanently incomplete. Mitigation today is operating order (ingest,
  then mark); the PAPER-03 scheduler must enforce it, or a revisioned-row design is needed.
  Filed 2026-09-25.

- **Mark-to-market: broker account is not reconciled against the ledger (Phase 11, D1):** fills for
  orders we did not place (manual trades) are skipped with a warning, so a manual close leaves the
  ledger showing an open position the broker no longer holds. A periodic position reconciliation
  (broker positions vs ledger open qty) would surface this. Filed 2026-09-25.

- **Mark-to-market: dividends use pay-date holdings, not ex-date (Phase 11 review, MEDIUM):**
  Alpaca's DIV activity is dated on the payment date and carries no ex-date. Since review H5 each
  signal is credited `net * its shares at the start of the pay date / activity qty`, so a signal
  that sold between ex-date and pay date gets nothing, and one that bought in that window is
  credited (flagged by `dividend_holdings_exceed_paid`). Credits can never exceed what was paid.
  Fix needs the ex-date (corporate-actions feed). Ruling: defer; paper holding periods are short
  and the error is bounded by the payment. Filed 2026-09-25.

- **Mark-to-market: no exchange calendar (Phase 11):** market holidays surface as
  `skipped_no_price`, and early-close days use the normal 16:00 ET guard. Correct but noisy.
  Filed 2026-09-25.

- **Postgres-backed test fixture (Phase 11):** the suite's `db_session` is SQLite-only; the Phase 11
  DB tests were run against Postgres once by a temporary fixture override. A `TEST_DATABASE_URL`
  switch in `tests/conftest.py` would make that repeatable (Phase 10's VARCHAR defect is the
  precedent for why it matters). Filed 2026-09-25.

- **Mark-to-market: no ingest watermark; fills/cash not filtered by `observed_date` (Phase 11 review,
  MEDIUM):** the job does not check that `ingest_fills` has caught up to `pnl_date`'s close, and a
  re-run with a pinned `now` still sees fills and cash events ingested later, so a reproduction is
  not exact. Extends the "no correction path" entry. Ruling: defer to PAPER-03 (scheduler enforces
  ingest-then-mark and records a watermark). Filed 2026-09-25.

- **Rollup: conviction dimension omits empty buckets; labels taken from the latest row (Phase 11
  review, LOW):** `by_conviction_bucket` lists only buckets that occur (spec s7 says every policy
  bucket + `unknown`) because `attribution_rollup` has no policy; after a policy change the whole
  range's P&L goes to the latest row's labels (deterministic, sums still exact; `mtm_policy_shas`
  reports the mix). `signals` counts signals whose last row predates `start`. Ruling: Phase 13 passes
  the policy and fixes the key set; document the label rule in the report. Filed 2026-09-25.

- **Row `mtm_policy_sha` is the job's policy, not the one that froze the stances (Phase 11 review,
  LOW):** stances carry their own `mtm_policy_sha` in the episodic payload; the P&L row stamps the
  job's. After a stance-rule change the row's SHA misdescribes its stances. Ruling: defer; record
  both SHAs in `attribution` when a second rule version exists. Filed 2026-09-25.

- **Test gaps from the Phase 11 review (LOW):** the no-UPDATE test classifies statements by first
  word (an `INSERT ... ON CONFLICT DO UPDATE` would pass it; the byte-identical and new-price-source
  tests do catch it); `mark_to_market`'s subprocess test runs only `--help`; policy paths are
  CWD-relative (`MemoryDeps()` and the CLI fail outside the repo root -- same convention as the
  risk/review policies). Ruling: defer. Filed 2026-09-25.

## Closed

- **Migration 002 `observed_date` nullability drift (found Phase 9 pre-mortem #23):** wider than
  filed -- migration 001 had the same gap on `observed_date` in all six ingestion tables plus
  `daily_prices.source` (8 columns total). Migration 008 sets all eight NOT NULL and *refuses* to
  upgrade if any NULL exists (no backfill: `observed_date` is provenance). Checked the local dev
  database first (read-only): 0 NULLs in every column, and the columns were already NOT NULL there
  (built via `create_all`), so 008 is a no-op on it. Closed 2026-09-26.

- **Migrations 001-003 have no round-trip test (found Phase 9 T4):** `tests/db/test_migration_chain.py`
  runs the whole chain 001 -> head on SQLite and PostgreSQL: head -> base -> head, a step-wise
  walk down and back up one revision at a time, a linear-chain check, and *unfiltered*
  `compare_metadata` parity over every table (nullability included) plus a per-table nullability
  check for the eight v1.0 tables. Closed 2026-09-26.

- **Async pipeline invoked against a sync PostgresSaver (found Phase 10, pre-existing since Phase 1):**
  `test_checkpoint_resume` drove `ainvoke` through the sync `PostgresSaver` (no `aget_tuple` ->
  `NotImplementedError`), hidden because its `requires_db` guard skipped while Docker was down.
  Closed by PR #5: the test uses the existing `create_async_checkpointer`, agents are stubbed with
  `TestModel`, five docstrings that pointed `ainvoke` graphs at the sync saver are corrected, and
  `tests/conftest.py` defaults a `test-key` dummy API key so isolated runs collect. No production
  path used the Postgres checkpointer (`run_analysis.py` uses `InMemorySaver`). Full suite now runs
  with no deselect. Closed 2026-09-25.

- **Duplicate-client-order-id with no local row left a broker order untracked (Phase 10 review F3):**
  closed by review round 2 (R3). On "duplicate", `_submit_order` now looks the order up by
  client_order_id (`BrokerClient.get_order_by_client_order_id`) and records it as submitted -- only
  if its symbol/side/qty match what we would place; otherwise `ClientOrderIdConflict`. The
  client_order_id is namespaced per database (R7), so a foreign order cannot be adopted by id alone.
  Verified live against Alpaca paper. Closed 2026-09-24.
