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

## Closed

_(none yet)_
