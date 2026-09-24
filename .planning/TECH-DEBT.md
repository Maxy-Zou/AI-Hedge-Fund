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
  `os.environ.setdefault` would fix isolated runs.)

- **Duplicate-client-order-id with no local row leaves a broker order untracked (Phase 10 review F3):**
  in `execution/submit.py::_submit_order`, if the broker reports DuplicateClientOrderId but no local
  paper_trades row exists for that (signal_id, attempt), submit raises AlreadySubmitted without
  recording a row -- a broker-side order with no ledger entry. Prevents double-fill but not the
  orphan. Proper fix needs a broker `get_order_by_client_id` on the BrokerClient Protocol to recover
  the broker order id and record it. Deferred; accept for single-operator v1.1 paper. Filed 2026-09-24.

- **submit_signal has no concurrency guard (Phase 10 review F6):** next_attempt reads prior attempts
  then the order path submits to the broker before insert_paper_trade, so two concurrent runs for one
  signal can both submit and the second only fails at the DB unique constraint (after its order was
  sent). Safe for the single-threaded CLI; a scheduler (PAPER-03) would need a per-signal advisory
  lock or a pre-insert reservation row. Deferred. Filed 2026-09-24.

## Closed

_(none yet)_
