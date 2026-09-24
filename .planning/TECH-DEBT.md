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

- **Migration 002 `observed_date` nullability drift (found Phase 9 pre-mortem #23):**
  `002_create_portfolio_positions.py` declares `observed_date` without `nullable=False`; the
  ORM mixin requires it. Production schema is looser than the model. Needs a corrective
  migration (`ALTER COLUMN ... SET NOT NULL`) after confirming no NULLs exist in prod.

- **Migrations 001-003 have no round-trip test (found Phase 9 T4):**
  `tests/paper/test_migration_roundtrip.py` is the first migration the suite has ever executed
  and provides the pattern (file-based SQLite + `alembic.autogenerate.compare_metadata`).
  Extend to the full chain, and add parity checks for every v1.0 table, in a v1.x cleanup.

- **Async pipeline invoked against a sync PostgresSaver (found Phase 10, pre-existing since Phase 1):**
  `tests/integration/test_checkpointer.py::test_checkpoint_resume` calls `graph.ainvoke(...)` on a
  pipeline built with `create_checkpointer()`, which yields a synchronous
  `langgraph.checkpoint.postgres.PostgresSaver`. Under the current langgraph, the async loop calls
  `aget_tuple()` on the sync saver -> `NotImplementedError`. The test has been skipped its entire life
  (its `requires_db` guard skips when Docker is down, which was always the case until Phase 9 started
  Postgres), so this never ran. Fix needs a decision: yield `AsyncPostgresSaver` from an async
  `create_checkpointer` path, or invoke synchronously in the test. Touches `graph/checkpointer.py`,
  `graph/pipeline.py`, and how production runs the graph -> its own session, not a mid-phase patch.
  Filed 2026-09-24. (Secondary: module-level `create_agent()` in `agents/analysis.py` /
  `extraction.py` makes graph imports need `ANTHROPIC_API_KEY` at import; isolated collection of any
  graph-importing test errors unless a dummy key is set. A session-scoped conftest
  `os.environ.setdefault` would fix isolated runs.) **Fixed in PR #5** (`fix/checkpointer-async`):
  the test uses the existing `create_async_checkpointer`; conftest defaults a dummy key. Move to
  Closed, and drop the Phase 10 gate's `--deselect`, once PR #5 merges.

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
  recorded in the trade payload. Filed 2026-09-24.

## Closed

- **Duplicate-client-order-id with no local row left a broker order untracked (Phase 10 review F3):**
  closed by review round 2 (R3). On "duplicate", `_submit_order` now looks the order up by
  client_order_id (`BrokerClient.get_order_by_client_order_id`) and records it as submitted -- only
  if its symbol/side/qty match what we would place; otherwise `ClientOrderIdConflict`. The
  client_order_id is namespaced per database (R7), so a foreign order cannot be adopted by id alone.
  Verified live against Alpaca paper. Closed 2026-09-24.
