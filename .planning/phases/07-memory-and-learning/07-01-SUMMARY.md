---
phase: 07-memory-and-learning
plan: 01
subsystem: memory
tags: [episodic-memory, sqlalchemy, alembic, retention, temporal-correctness, phase-7, mem-01]

# Dependency graph
requires:
  - phase: 07-memory-and-learning
    plan: 00
    provides: "tests/memory/ fixtures (memory_db_session, sample_episodic_csv_path with FUTUREX regression row)"
  - phase: 06-risk-management
    provides: "RiskAssessment.policy_sha audit key — stored as policy_sha column on EpisodicMemory rows"
provides:
  - "ai_hedge_fund.db.models.EpisodicMemory — append-only SQLAlchemy model with DualTimestampMixin, JSONB payload, and composite indexes (ix_episodic_ticker_asof, ix_episodic_sector_asof)"
  - "ai_hedge_fund.memory.episodic.EpisodicHit — frozen Pydantic read-path schema (extra=forbid)"
  - "ai_hedge_fund.memory.episodic.seed_episodic_from_csv — CSV fixture loader (blank cells -> None; returns row count)"
  - "ai_hedge_fund.memory.recall.query_episodic — MEM-01 read path with mandatory as_of_date <= target filter (Pitfall 2), ticker OR sector match, DESC ordering, limit cap"
  - "ai_hedge_fund.scripts.purge_expired_episodic.purge_expired — idempotent 90-day retention sweep (ORM delete; Pitfall 8 safe)"
  - "alembic/versions/003_create_episodic_memory.py — deploy-time DDL artifact (tests run on SQLite via Base.metadata.create_all)"
affects: [07-03-pipeline-integration, 07-04-self-critique, 07-05-integration-tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "JSONB().with_variant(JSON, 'sqlite') — dialect-aware payload column that tests cleanly in-memory and ships GIN-indexable JSONB on Postgres"
    - "Temporal-correct query helper that shares _normalise_as_of with risk/portfolio.py — same contract (as_of_date <= target) applied to a second domain table"
    - "Append-only + retention-delete pattern: Pattern 5 from 07-RESEARCH.md applied verbatim — no UPDATE path anywhere, just INSERT + scheduled DELETE"
    - "CLI entry with pragma:no-cover for shell-out body (exercises AppSettings + get_engine wiring that only runs against live Postgres)"

key-files:
  created:
    - "src/ai_hedge_fund/memory/__init__.py"
    - "src/ai_hedge_fund/memory/episodic.py (EpisodicHit + seed_episodic_from_csv + _normalise_as_of)"
    - "src/ai_hedge_fund/memory/recall.py (query_episodic with mandatory temporal filter)"
    - "src/ai_hedge_fund/scripts/__init__.py"
    - "src/ai_hedge_fund/scripts/purge_expired_episodic.py (purge_expired + CLI entry)"
    - "alembic/versions/003_create_episodic_memory.py (revision=003, down_revision=002)"
    - "tests/memory/test_episodic_model.py (6 tests)"
    - "tests/memory/test_episodic_recall.py (8 tests)"
    - "tests/memory/test_episodic_retention.py (6 tests)"
  modified:
    - "src/ai_hedge_fund/db/models.py (appended EpisodicMemory class; added Index + JSON imports; added postgresql JSONB import)"

key-decisions:
  - "NO UniqueConstraint on EpisodicMemory — duplicates (same ticker + same as_of_date) are allowed by design per 07-PATTERNS.md. This is the defining contrast with PortfolioPosition."
  - "Two composite indexes (ticker, as_of_date) and (sector, as_of_date) — B-tree friendly for both ticker-scoped and sector-scoped recall without a full-table scan."
  - "query_episodic accepts ticker OR sector (not AND) to let memory_recall_node pull ticker-specific priors AND sector-wide context in one DB round trip. At least one of the two is REQUIRED (ValueError otherwise — Pitfall 8 DoS guard against a table scan)."
  - "Retention sweep is a delete (Pattern 5), not a read-time filter (Anti-Pattern per 07-RESEARCH.md). Read-time retention would leak semantics into every consumer and complicate tests."
  - "CSV seed payload contains {schema_version: 1, source: csv_seed} — deliberate sentinel so downstream plans can distinguish seeded rows from production-written rows without schema changes."
  - "Alembic migration 003 is shipped but NOT executed by this plan (deploy-step out of scope). Tests use Base.metadata.create_all on SQLite; operator runs 'uv run alembic upgrade head' once per environment."

requirements-completed: []  # MEM-01 substrate only — full MEM-01 closure requires Plan 07-03 (graph integration)
requirements-partial:
  - id: MEM-01
    scope: "Storage + recall + retention substrate ready. Graph integration (memory_recall_node + episodic_store_node wiring) lands in 07-03."

# Metrics
duration: 6m
completed: 2026-04-22
---

# Phase 7 Plan 01: Episodic Memory Substrate Summary

**Append-only episodic_memory table + temporal-correct recall (as_of_date <= target, Pitfall-2 regression proven) + idempotent 90-day retention sweep — 20 new tests green, Phase 6 regression clean.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-04-22T20:46:14Z
- **Completed:** 2026-04-22T20:51:59Z
- **Tasks:** 3 (all TDD: RED -> GREEN commits)
- **Files created:** 9
- **Files modified:** 1 (src/ai_hedge_fund/db/models.py — 2 import lines + new class appended)

## Accomplishments

- **EpisodicMemory model:** Append-only SQLAlchemy table with `DualTimestampMixin`, 12 columns (id, ticker, sector, record_type, signal_direction, confidence, outcome_pct, linked_analysis_id, policy_sha, payload, as_of_date, observed_date), composite indexes `ix_episodic_ticker_asof` + `ix_episodic_sector_asof`, JSONB payload with SQLite fallback. **No UniqueConstraint** — duplicates-by-design per plan.
- **Alembic 003:** Deploy-time DDL artifact mirroring 002's revision-chain style. Ships `upgrade()` + `downgrade()`. Not invoked by tests (Base.metadata.create_all on SQLite).
- **query_episodic read path:** Mandatory `as_of_date <= target` temporal filter (Pitfall 2). Accepts ticker OR sector (`OR` composition so both can be supplied for combined recall). Raises `ValueError` when neither is supplied (Pitfall 8 DoS guard). Orders `as_of_date DESC`, bounds by `limit` (default 10). Returns a list of frozen `EpisodicHit` Pydantic models.
- **FUTUREX regression proven:** A row seeded at `as_of_date=2099-01-01` is NEVER returned by `query_episodic(..., as_of_date="2030-01-01")`. This is the load-bearing MEM-01 temporal-correctness test.
- **seed_episodic_from_csv:** Fixture loader that round-trips blank `outcome_pct`/`confidence` cells to Python `None` (not `0.0`), inserts all 10 rows of `seeded_episodic.csv`, and preserves `policy_sha` for Phase-6 audit linkage.
- **purge_expired:** Idempotent 90-day retention sweep via SQLAlchemy `delete()` (T-07-02 ORM-only). Tests confirm second call returns 0. Rejects negative `retention_days`. Logs `episodic_retention_sweep` event with cutoff + deleted count via structlog.
- **26 memory tests green** (6 Wave-0 smoke + 6 model + 8 recall + 6 retention). **106 Phase-5/6 cross-phase tests still green.**

## Task Commits

Each task committed atomically after its verification passed:

1. **Task 1 — EpisodicMemory model + Alembic 003:** `4f45518` (feat)
2. **Task 2 — query_episodic + EpisodicHit + seed_episodic_from_csv:** `5e92a64` (feat)
3. **Task 3 — purge_expired retention sweep:** `f9b8f1b` (feat)

## Files Created/Modified

- `src/ai_hedge_fund/db/models.py` — appended `EpisodicMemory` class; added `Index`, `JSON` to SQLAlchemy import tuple; added `from sqlalchemy.dialects.postgresql import JSONB as _JSONB`. No `noqa: E402` markers. No modifications to pre-existing classes.
- `src/ai_hedge_fund/memory/__init__.py` — subpackage re-export surface (`EpisodicHit`, `query_episodic`, `seed_episodic_from_csv`).
- `src/ai_hedge_fund/memory/episodic.py` — `EpisodicHit` (frozen, extra=forbid), `_normalise_as_of` helper, `seed_episodic_from_csv`.
- `src/ai_hedge_fund/memory/recall.py` — `query_episodic` with mandatory temporal filter + `_to_hit` row-to-schema converter.
- `src/ai_hedge_fund/scripts/__init__.py` — operator-CLI package marker.
- `src/ai_hedge_fund/scripts/purge_expired_episodic.py` — `purge_expired` + `_main` CLI entry (pragma: no cover for shell-out body).
- `alembic/versions/003_create_episodic_memory.py` — revision=003, down_revision=002, `upgrade()`/`downgrade()`.
- `tests/memory/test_episodic_model.py` — 6 tests (round-trip, append-only duplicates, column set, nested JSONB, nullable fields, index registration).
- `tests/memory/test_episodic_recall.py` — 8 tests (schema validation, CSV seed, ticker recall + DESC order, **FUTUREX regression**, sector recall, limit enforcement, `ValueError` guard, `policy_sha` round-trip).
- `tests/memory/test_episodic_retention.py` — 6 tests (cutoff correctness, in-window preservation, idempotency, retention=0 edge case, negative-retention guard, default-signature usability).

## Decisions Made

All plan-specified decisions applied as written. Two worth highlighting:

1. **`query_episodic` uses OR composition on ticker/sector (not AND).** When `memory_recall_node` supplies both, the caller gets ticker-specific priors AND sector-wide context in one round trip. The AND semantics would force two separate queries and double the DB traffic.
2. **CSV seed payload contains a sentinel `{schema_version: 1, source: csv_seed}`.** Lets Plan 07-04 differentiate fixture-seeded rows from production-ingested rows without schema drift. Harmless on Postgres JSONB; serialized as standard JSON on SQLite.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Test setup used ISO-8601 strings for `as_of_date`, which SQLite's DateTime binder rejected.**

- **Found during:** Task 1 initial GREEN run (after writing the 6 model tests with string `as_of_date`).
- **Issue:** `sqlalchemy.exc.StatementError: SQLite DateTime type only accepts Python datetime and date objects as input.` The model's `as_of_date` is `DateTime(timezone=True)` (inherited from `DualTimestampMixin`). The project's production CSV-seeded path (`seed_portfolio_from_csv`) calls `_normalise_as_of` before insertion, converting strings to `datetime`. My tests bypassed that helper and passed raw strings.
- **Fix:** Introduced module-level `datetime(2026, 1, 10, tzinfo=UTC)` constants (`_AS_OF_JAN10`, `_AS_OF_FEB01`, `_AS_OF_MAR15`) and bound them to the model rows. Query round-trip uses `read_back.as_of_date` as whatever SQLite returns (opaque to the assertions). No production code changed — this was strictly a test-fixture correction.
- **Files modified:** `tests/memory/test_episodic_model.py` (only).
- **Committed in:** `4f45518` (Task 1 commit).

**2. [Rule 3 — Blocking] Ruff E501 on EpisodicMemory docstring line exceeding 100 chars.**

- **Found during:** Task 1 post-format `ruff check`.
- **Issue:** The docstring line describing `record_type='outcome'` referenced `src/ai_hedge_fund/scripts/ingest_outcome.py` — a 103-character line with ruff's `line-length=100`.
- **Fix:** Shortened the reference to `scripts/ingest_outcome.py` (project-root-relative, still unambiguous). Lint clean; meaning preserved.
- **Files modified:** `src/ai_hedge_fund/db/models.py`.
- **Committed in:** `4f45518` (Task 1 commit).

**Total deviations:** 2 local test/format fixes. No architectural or scope changes.

## Issues Encountered

None beyond the two auto-fixed items above. The upstream uv/macOS UF_HIDDEN bug documented in `deferred-items.md` was anticipated — tests run under `.venv/bin/python -m pytest ...` after `chflags nohidden .venv/lib/python3.13/site-packages/*.pth`, exactly as prescribed.

## Threat Register Verification

All STRIDE mitigations from the plan's `<threat_model>` verified by `grep` and test coverage:

| Threat | Status | Evidence |
|--------|--------|----------|
| T-07-01 temporal leakage | mitigated | `test_recall_excludes_future_rows` asserts FUTUREX 2099-01-01 is never returned by a 2030-01-01 query |
| T-07-02 SQL injection | mitigated | `grep -rEc "execute\(text\|\.format\(" src/ai_hedge_fund/memory/ src/ai_hedge_fund/scripts/purge_expired_episodic.py` → 0 per file |
| T-07-03 DoS (oversize recall) | mitigated | `limit: int = 10` default in `query_episodic`; `ValueError` when neither ticker nor sector supplied (prevents table scan) |
| T-07-04 accidental UPDATE | mitigated | `grep -rn "db_session.merge\|\.update("` in memory + scripts → 0 hits. Retention uses `delete()` only. |
| T-07-05 policy_sha disclosure | accepted | Already audit-tier in Phase 6; no new exposure surface |

No new threat surface introduced beyond the plan's register — threat flags section omitted.

## Cross-phase Regression

```
.venv/bin/python -m pytest tests/risk tests/graph tests/integration/test_phase6_e2e.py -q
106 passed, 5 warnings in 0.81s
```

Phase 5 and Phase 6 suites untouched.

## User Setup Required

- **Postgres deploy step (NOT part of this plan):** `uv run alembic upgrade head` once per environment (dev/staging/prod). The migration is shipped; the invocation is the operator's responsibility per the plan's `<manual>` section.
- **uv/macOS UF_HIDDEN workaround (inherited from 07-00):** `chflags nohidden .venv/lib/python3.13/site-packages/*.pth` before `uv run --no-sync pytest ...` or use `.venv/bin/python -m pytest ...` directly. Documented in `deferred-items.md`.

## Next Plan Readiness

- **Plan 07-03 (graph integration):** Can now import `from ai_hedge_fund.memory import query_episodic, seed_episodic_from_csv, EpisodicHit` and `from ai_hedge_fund.db.models import EpisodicMemory`. The recall contract (`as_of_date <= target` + `OR(ticker, sector)` + `limit`) is frozen.
- **Plan 07-04 (self-critique):** Can append `record_type="outcome"` rows via `db_session.add(EpisodicMemory(...))`. The `linked_analysis_id` FK-like field is ready to reference prior analysis rows.
- **Plan 07-05 (integration tests):** Can reuse `seed_episodic_from_csv` end-to-end; the `policy_sha` Phase-6 link-back substrate is verified round-trippable.

No blockers.

## Self-Check: PASSED

Verified on disk (2026-04-22T20:52Z):

- `src/ai_hedge_fund/db/models.py` contains `class EpisodicMemory`: FOUND
- `alembic/versions/003_create_episodic_memory.py`: FOUND (revision=003, down_revision=002)
- `src/ai_hedge_fund/memory/__init__.py`: FOUND
- `src/ai_hedge_fund/memory/episodic.py` (EpisodicHit + seed_episodic_from_csv): FOUND
- `src/ai_hedge_fund/memory/recall.py` (query_episodic with temporal filter): FOUND
- `src/ai_hedge_fund/scripts/__init__.py`: FOUND
- `src/ai_hedge_fund/scripts/purge_expired_episodic.py` (ORM delete + CLI): FOUND
- `tests/memory/test_episodic_model.py` (6 tests): FOUND
- `tests/memory/test_episodic_recall.py` (8 tests): FOUND
- `tests/memory/test_episodic_retention.py` (6 tests): FOUND
- Commits `4f45518`, `5e92a64`, `f9b8f1b`: all present in `git log --oneline`.
- 26 memory tests + 106 Phase-5/6 regression tests all green.

---
*Phase: 07-memory-and-learning*
*Completed: 2026-04-22*
