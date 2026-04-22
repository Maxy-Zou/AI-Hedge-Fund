---
phase: 07-memory-and-learning
reviewed: 2026-04-22T00:00:00Z
depth: standard
files_reviewed: 33
files_reviewed_list:
  - alembic/versions/003_create_episodic_memory.py
  - pyproject.toml
  - src/ai_hedge_fund/agents/self_critique.py
  - src/ai_hedge_fund/db/models.py
  - src/ai_hedge_fund/graph/memory_deps.py
  - src/ai_hedge_fund/graph/nodes.py
  - src/ai_hedge_fund/graph/pipeline.py
  - src/ai_hedge_fund/memory/__init__.py
  - src/ai_hedge_fund/memory/beliefs.py
  - src/ai_hedge_fund/memory/critique.py
  - src/ai_hedge_fund/memory/episodic.py
  - src/ai_hedge_fund/memory/recall.py
  - src/ai_hedge_fund/schemas/memory.py
  - src/ai_hedge_fund/schemas/state.py
  - src/ai_hedge_fund/scripts/__init__.py
  - src/ai_hedge_fund/scripts/ingest_outcome.py
  - src/ai_hedge_fund/scripts/purge_expired_episodic.py
  - tests/graph/conftest.py
  - tests/graph/test_memory_nodes.py
  - tests/graph/test_pipeline_with_memory.py
  - tests/integration/conftest.py
  - tests/integration/test_phase7_e2e.py
  - tests/integration/test_phase7_policy_sha_linkage.py
  - tests/memory/__init__.py
  - tests/memory/conftest.py
  - tests/memory/test_belief_schema.py
  - tests/memory/test_belief_writer.py
  - tests/memory/test_critique_math.py
  - tests/memory/test_episodic_model.py
  - tests/memory/test_episodic_recall.py
  - tests/memory/test_episodic_retention.py
  - tests/memory/test_ingest_outcome.py
  - tests/memory/test_self_critique_agent.py
  - tests/memory/test_wave0_scaffold.py
findings:
  critical: 0
  warning: 3
  info: 6
  total: 9
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-04-22
**Depth:** standard
**Files Reviewed:** 33
**Status:** issues_found

## Summary

Phase 7 (Memory and Learning) is a careful, well-architected addition to the
LangGraph + PydanticAI pipeline. The central threat model (T-07-01..T-07-41)
is addressed at the right layers:

- **MEM-03 human-authoritative invariant** is enforced correctly in
  `write_belief` via three independent skip paths (override-meta blacklist,
  per-field locks, global `human_edited` flag) with structured reason codes.
  The writer is the sole mutation entry point and is atomic
  (tmp+rename).
- **Pattern 2 Pitfall 1** (LLM cannot author the number) is structurally
  enforced by `RationaleOnly` having exactly one `rationale: str` field;
  `tests/memory/test_self_critique_agent.py` locks this with
  `assert list(RationaleOnly.model_fields) == ["rationale"]` plus a
  disjoint-set check against forbidden field names.
- **Temporal correctness (Pitfall 2)** is enforced at a single chokepoint in
  `query_episodic` (`src/ai_hedge_fund/memory/recall.py:89`,
  `.filter(EpisodicMemory.as_of_date <= target)`). No code path bypasses it.
  `test_recall_excludes_future_rows` regresses a 2099-01-01 row.
- **Append-only invariant**: `EpisodicMemory` has no `UniqueConstraint`; the
  episodic writers (`episodic_store_node`, `_append_outcome_row`,
  `seed_episodic_from_csv`) only call `session.add()` / `session.add_all()`
  — never `UPDATE`. Retention is a `delete()` (not `UPDATE`).
- **YAML safety (T-07-10)**: ruamel `YAML()` (safe by default) is used
  exclusively; `tests/memory/test_belief_writer.py::test_no_unsafe_yaml_load_in_beliefs_module`
  greps for `yaml.load(` and fails if reintroduced.
- **Path traversal (T-07-11 / T-07-40)**: `belief_path_for_ticker` regex-guards
  every ticker before any filesystem join. `test_path_traversal_guard` and
  `test_ingest_outcome_path_traversal_rejected` lock it.
- **SQL injection (T-07-01/02)**: 100% SQLAlchemy ORM; no raw string SQL.
  `query_episodic` uses bound parameters via the `==` and `or_()` expression
  API; `purge_expired` uses `delete(...).where(...)`.
- **Pipeline backcompat**: `build_debate_pipeline()` with no kwargs preserves
  the Phase-5 node list and edge set byte-for-byte; regressed by
  `test_builder_no_kwargs_backcompat` and `test_phase5_backcompat_no_kwargs_still_compiles`.
- **Pitfall 5 drift guard**: `_PER_EVENT_DELTA_CAP = 10` is applied via
  `min(raw_adjustment, float(_PER_EVENT_DELTA_CAP))` BEFORE clamping to [0,100];
  `test_per_event_cap_prevents_oversized_jumps` regresses it.

No Critical issues were found. Three Warnings relate to defense-in-depth
gaps (sector-derived path, partial-state on FileNotFoundError, nullable
`observed_date`). Six Info items cover minor style or future-hardening notes.

## Warnings

### WR-01: `sector` string flows into filesystem path without regex guard

**File:** `src/ai_hedge_fund/graph/nodes.py:1066-1071`
**Issue:** `memory_recall_node` constructs the sector belief path as
`deps.beliefs_path / "sectors" / f"{sector}.yaml"` where `sector` is read
from `state["candidate_metadata"]["sector"]`. While the `CandidateMetadata`
Pydantic schema in `src/ai_hedge_fund/schemas/state.py:58` validates
`min_length=1`, there is no character-class guard equivalent to
`belief_path_for_ticker`'s `_TICKER_RE`. A caller that bypasses the
Pydantic validator and pushes a raw dict directly into state (LangGraph
accepts dicts for TypedDict states) can set
`sector="../tickers/AAPL"` (valid per the schema's sole `min_length=1`
rule) and read an arbitrary YAML from the beliefs directory as if it
were a sector file. This mirrors the T-07-11 threat class that
`belief_path_for_ticker` defends against for the ticker subtree —
the sector subtree has no equivalent guard.

Empirically the risk is small today (sector values come from the
pipeline caller, not over the network), but defense-in-depth demands
the same guard on both subtrees.

**Fix:** Add a regex guard mirroring `belief_path_for_ticker`. Either
- inline guard in `memory_recall_node` before the path join, OR
- factor a `belief_path_for_sector(beliefs_dir, sector)` helper in
  `src/ai_hedge_fund/memory/beliefs.py` with its own
  `^[A-Za-z][A-Za-z0-9 \-_]{0,49}$` regex (GICS-like sector names
  tolerate spaces and hyphens), and call it from the node:

```python
# src/ai_hedge_fund/memory/beliefs.py
_SECTOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 \-_]{0,49}$")

def belief_path_for_sector(beliefs_dir: Path, sector: str) -> Path:
    if not _SECTOR_RE.fullmatch(sector):
        raise ValueError(f"Invalid sector {sector!r}")
    return beliefs_dir / "sectors" / f"{sector}.yaml"

# src/ai_hedge_fund/graph/nodes.py (memory_recall_node)
if sector != "Unknown":
    try:
        sector_path = belief_path_for_sector(deps.beliefs_path, sector)
    except ValueError:
        sector_path = None
    if sector_path is not None and sector_path.is_file():
        sector_belief, _raw = load_belief(sector_path)
        beliefs_consulted.append(sector_belief.model_dump(mode="json"))
```

Add `tests/memory/test_belief_writer.py::test_sector_path_traversal_rejected`
to regress.

---

### WR-02: FileNotFoundError after committed outcome row creates partial-state audit gap

**File:** `src/ai_hedge_fund/scripts/ingest_outcome.py:141-156`
**Issue:** `_append_outcome_row` commits the outcome row to
`episodic_memory` BEFORE the belief file existence check at
line 152. When the belief file does not exist (bootstrap case, or after a
manual `rm`), a `FileNotFoundError` propagates to the caller leaving
the DB in a state where an outcome row exists but no corresponding
belief update happened. The accompanying test
(`test_ingest_outcome_missing_belief_file`) documents this as intentional,
but there is no log-level signal on the orphan row that a belief update
was expected and failed.

A reader of the episodic table cannot distinguish "operator ingested an
outcome for a ticker with no belief yet" from "operator ingested and the
belief update silently failed". The function swallows the asymmetry
because the `FileNotFoundError` propagates BEFORE `logger.info
("self_critique_applied", ...)` runs.

**Fix:** Either (a) reorder the checks so the belief file existence is
validated BEFORE the outcome row is committed, falling back to the
documented bootstrap case path only when explicitly requested; OR (b)
emit a structured `logger.warning("self_critique_missing_belief", ...)`
log BEFORE re-raising so the orphan is recoverable via log grep.
Option (b) is minimally invasive:

```python
# src/ai_hedge_fund/scripts/ingest_outcome.py around line 152
if not belief_path.is_file():
    logger.warning(
        "self_critique_missing_belief",
        ticker=ticker,
        as_of_date=as_of_date.isoformat(),
        outcome_row_id=outcome_row.id,
        belief_path=str(belief_path),
    )
    raise FileNotFoundError(
        f"Belief file not found for {ticker}; run the analysis "
        f"pipeline first to auto-create {belief_path}"
    )
```

---

### WR-03: `observed_date` on `episodic_memory` migration is implicitly NULLABLE

**File:** `alembic/versions/003_create_episodic_memory.py:45-49`
**Issue:** The migration declares
`sa.Column("observed_date", sa.DateTime(timezone=True), server_default=sa.func.now())`
without `nullable=False`. SQLAlchemy's default is `nullable=True` when the
argument is omitted, so the PostgreSQL column ships as NULLABLE. The
corresponding ORM model in `src/ai_hedge_fund/db/base.py:51-54`
(`DualTimestampMixin.observed_date`) also omits `nullable=False` — so
the ORM and migration agree, but both are permissive.

`DualTimestampMixin` is documented to capture the collection date for
look-ahead-bias prevention (CLAUDE.md "Data Handling" section: "Dual
timestamps where relevant"). A nullable `observed_date` column allows
a future insert with `observed_date=None`, silently defeating the
temporal audit. The server_default almost always fills it, but defense-
in-depth says the type should make NULL a schema error.

**Fix:** Add `nullable=False` to both the migration column and the
mixin:

```python
# alembic/versions/003_create_episodic_memory.py
sa.Column(
    "observed_date",
    sa.DateTime(timezone=True),
    server_default=sa.func.now(),
    nullable=False,
),

# src/ai_hedge_fund/db/base.py (DualTimestampMixin)
observed_date: Mapped[str] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    nullable=False,
)
```

Note: the DualTimestampMixin fix applies project-wide (affects all
existing tables using the mixin). If that is out of scope for Phase 7,
at minimum pin `nullable=False` on the `003_create_episodic_memory.py`
column so the episodic audit trail is strictly non-null.

---

## Info

### IN-01: `ingest_outcome` day-boundary UTC conversion

**File:** `src/ai_hedge_fund/scripts/ingest_outcome.py:94`
**Issue:** `datetime(as_of_date.year, as_of_date.month, as_of_date.day, tzinfo=UTC)`
converts the operator-supplied business date to midnight UTC. This is
consistent with the rest of the project (CLAUDE.md: "All timestamps in UTC")
but worth documenting: an operator in UTC+08 running this at 23:00 local
time on 2026-04-20 will correctly record `as_of_date=2026-04-20T00:00:00Z`
because they pass in the `--as-of` date explicitly.
**Fix:** No change needed; add a one-line docstring note on
`_append_outcome_row` explaining that `as_of_date` is always pinned to
midnight UTC regardless of operator timezone:

```python
# src/ai_hedge_fund/scripts/ingest_outcome.py
def _append_outcome_row(...) -> EpisodicMemory:
    """Insert a single ``record_type='outcome'`` row and return it.

    Append-only: commits immediately so the DB write survives a
    subsequent exception in the rationale step. ``as_of_date`` is
    pinned to midnight UTC for the supplied business date -- operator
    timezone is NOT inferred.
    """
```

---

### IN-02: Hardcoded retention default inconsistent between code and docstring

**File:** `src/ai_hedge_fund/scripts/purge_expired_episodic.py:33`
**Issue:** Default is `retention_days: int = 90`; documented as 90 days in
multiple places (CLAUDE.md mentions "90-day retention" and the module
docstring echoes it). This is fine. Consider extracting the magic number
`90` into a module-level constant `_DEFAULT_RETENTION_DAYS = 90` so a
future change touches one symbol instead of three.
**Fix:**
```python
_DEFAULT_RETENTION_DAYS = 90  # keep in sync with CLAUDE.md

def purge_expired(
    db_session: Session,
    *,
    retention_days: int = _DEFAULT_RETENTION_DAYS,
    today: date | None = None,
) -> int:
```

---

### IN-03: `_TICKER_RE` duplicated verbatim between belief path and EpisodicHit

**File:** `src/ai_hedge_fund/memory/beliefs.py:41`, `src/ai_hedge_fund/memory/episodic.py:36` (via `EpisodicHit`)
**Issue:** `beliefs.py` uses `r"^[A-Z0-9.\-]{1,10}$"` on the ticker; `EpisodicHit`
validates tickers via `Field(min_length=1, max_length=10)` only (no character
class). If a malformed ticker somehow lands in `episodic_memory` (e.g.,
operator SQL), the hit schema would accept it silently while
`belief_path_for_ticker` would reject it. No security risk (the path guard
still wins), but it is a latent drift source.
**Fix:** Export the regex as a public module constant from `beliefs.py` and
reference it from `EpisodicHit`:

```python
# src/ai_hedge_fund/memory/beliefs.py
TICKER_REGEX = r"^[A-Z0-9.\-]{1,10}$"
_TICKER_RE = re.compile(TICKER_REGEX)

# src/ai_hedge_fund/memory/episodic.py
from ai_hedge_fund.memory.beliefs import TICKER_REGEX
...
class EpisodicHit(BaseModel):
    ticker: str = Field(pattern=TICKER_REGEX)
```

---

### IN-04: `record_type` validation asymmetry between ORM model and Pydantic view

**File:** `src/ai_hedge_fund/db/models.py:222`, `src/ai_hedge_fund/memory/episodic.py:38`
**Issue:** The ORM column is `String(20)` with no CHECK constraint; the
`EpisodicHit` Pydantic view constrains `record_type` to
`^(analysis|outcome)$`. A malformed write (e.g., `record_type="Analysis"`
with capital A) would succeed at the DB layer but fail on read-back
validation. Probability is low (writers are `episodic_store_node` and
`_append_outcome_row`, both hardcoded), but a CHECK constraint makes the
invariant explicit at the schema boundary.
**Fix:** Add a CHECK constraint in the migration and a matching
`sa.CheckConstraint` in `__table_args__`:

```python
# alembic/versions/003_create_episodic_memory.py
sa.CheckConstraint(
    "record_type IN ('analysis', 'outcome')",
    name="ck_episodic_record_type",
),

# src/ai_hedge_fund/db/models.py EpisodicMemory.__table_args__
__table_args__ = (
    Index("ix_episodic_ticker_asof", "ticker", "as_of_date"),
    Index("ix_episodic_sector_asof", "sector", "as_of_date"),
    CheckConstraint(
        "record_type IN ('analysis', 'outcome')",
        name="ck_episodic_record_type",
    ),
)
```

---

### IN-05: Unicode em dash in module docstring may not match project style

**File:** `src/ai_hedge_fund/scripts/purge_expired_episodic.py:11-13`
**Issue:** The docstring uses U+2014 EM DASH ("—") in
`"append-only invariant preserved — retention is a *delete* operation"`.
Other Phase 7 files use ASCII double-dash (`--`). Not a bug; consider
normalising to the project-wide style that ruff/black will not rewrite.
**Fix:**
```python
# src/ai_hedge_fund/scripts/purge_expired_episodic.py
Threat mitigation T-07-02: SQLAlchemy ORM ``delete()`` exclusively; no
raw SQL. Mitigation T-07-04: append-only invariant preserved -- retention
is a *delete* operation, never an UPDATE.
```

---

### IN-06: Magic number 10 in `compute_new_confidence` could reference its constant

**File:** `src/ai_hedge_fund/memory/critique.py:77`
**Issue:** `raw_adjustment = k * abs(outcome_pct) * 10` — the trailing `10`
is the "scale outcome_pct to basis-points-on-a-0-100-scale" factor and is
distinct from `_PER_EVENT_DELTA_CAP`, which also happens to be 10. A reader
may assume they are the same number. Add a named constant for the scaling
factor to make the coincidence explicit.
**Fix:**
```python
_OUTCOME_SCALE_FACTOR: float = 10.0  # scales outcome_pct to confidence points

def compute_new_confidence(...) -> int:
    ...
    raw_adjustment = k * abs(outcome_pct) * _OUTCOME_SCALE_FACTOR
    capped_adjustment = min(raw_adjustment, float(_PER_EVENT_DELTA_CAP))
```

---

## Observations (not findings)

Items confirmed healthy during review — documented here so subsequent
reviewers can skip re-verification:

- `build_debate_pipeline()` with no kwargs preserves Phase-5 edges
  byte-for-byte (pipeline.py:374-383); regressed by
  `test_builder_no_kwargs_backcompat` and
  `test_phase5_backcompat_no_kwargs_still_compiles`.
- `write_belief` guard logic correctly orders the three skip conditions
  (override-meta -> field-lock -> global human_edited); version only
  bumps when `applied` is non-empty.
- `RationaleOnly` has exactly one field; `test_rationale_only_has_single_field`
  and `test_rationale_only_forbids_new_confidence` lock the invariant.
- `self_critique` system prompt contains `"EXPLAIN"` and none of the
  forbidden decision-verbs; regressed by `test_system_prompt_forbidden_verbs_absent`.
- `query_episodic` applies `EpisodicMemory.as_of_date <= target`
  unconditionally; `test_memory_recall_excludes_future_dated_row_pitfall_2`
  and `test_recall_excludes_future_rows` regress the temporal filter at
  both the node and module layers.
- `episodic_store_node` always calls `session.add(row)` then
  `session.commit()` — never `UPDATE`. Short-circuits cleanly on
  `state["error"]` with a zero-DB-write guarantee regressed by
  `test_episodic_store_short_circuits_on_upstream_error`.
- `_PER_EVENT_DELTA_CAP = 10` is applied before the `[0, 100]` clamp so
  both bounds (cap and clamp) compose correctly; `test_per_event_cap_prevents_oversized_jumps`
  and `test_per_event_cap_symmetric_on_disagreement` regress both sides.
- `MemoryDeps` is `@dataclass(frozen=True)` and consistently typed with the
  `RiskDeps` pattern (`Session` under `TYPE_CHECKING` to avoid a runtime
  SQLAlchemy import). `test_memory_deps_is_frozen` regresses immutability.
- The `policy_sha` authoritative-column contract is tested end-to-end
  in `tests/integration/test_phase7_policy_sha_linkage.py` (six scenarios:
  determinism, change-sensitivity, idempotence, format on APPROVED,
  format on VETOED, three-way column-payload-state equality).
- The `append-only` invariant on `episodic_memory` is proven by
  `test_append_only_duplicates_allowed` (two rows with identical
  `(ticker, as_of_date)` both succeed — no UniqueConstraint).
- Retention is a `delete()`, never an `UPDATE`;
  `test_purge_is_idempotent` regresses idempotence.

---

_Reviewed: 2026-04-22_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
