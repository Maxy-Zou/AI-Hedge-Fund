# Phase 7: Memory and Learning - Research

**Researched:** 2026-04-22
**Domain:** Persistent agent memory (episodic + belief) with human-authoritative overrides and outcome-driven self-critique
**Confidence:** HIGH for schema/storage/LangGraph patterns (extend Phase 1-6 precedent). MEDIUM for library choice (ruamel.yaml vs PyYAML), pgvector deferral. LOW on retention cadence specifics (cron vs scheduled job) — pick one and move on.

## Summary

Phase 7 builds the **domain memory layer** that sits alongside LangGraph's checkpointer (state persistence) and Store (generic KV). The two halves are:

1. **Episodic memory** — append-only SQLAlchemy table of completed analyses + trade outcomes, queryable by ticker/sector/date range with a hard `as_of_date` filter to prevent look-ahead bias. Reuses the Phase 1-6 `DualTimestampMixin` + Alembic migration pattern.
2. **Belief memory** — human-readable YAML documents on disk (one file per ticker/sector), schema-validated via Pydantic `extra="forbid"`, with a `human_edited` boolean that machine writes MUST preserve. Revision history tracked in-file (YAML list) AND in git.

The self-critique loop fires when a trade outcome arrives. It uses the **same Pattern 2 as Phase 6** (06-RESEARCH.md): deterministic Python computes the new confidence from `(old_confidence, outcome_sign, signed_error)`; the LLM produces a `RationaleOnly`-style rationale. The belief file is rewritten (never destructively mutated) with the new confidence + rationale + outcome stamped into `critique_history`. If `human_edited=True` on the target field, the machine writer **refuses to overwrite** and records the skip as a `critique_conflict` event.

Pipeline integration mirrors Phase 6: `build_debate_pipeline(with_memory=True, memory_deps=MemoryDeps(...))` adds a `memory_recall_node` BEFORE `manager_node` (so analysts and debaters see prior work) and a separate `self_critique_node` is NOT part of the live pipeline — it runs offline, triggered by an outcome-ingest script, because it has no place in a ticker-in-signal-out flow.

**Primary recommendation:** Ship the SQL-filter path only (defer pgvector). Use `ruamel.yaml` for belief files (preserves human comments). Treat episodic recall as a graph node (not a PydanticAI tool) for v1 — it pre-loads into state so every downstream agent sees the same `episodic_hits` payload deterministically, making tests reproducible and avoiding per-agent tool-call latency multiplicatively.

## Project Constraints (from CLAUDE.md)

Copied/paraphrased from `CLAUDE.md` + phase CONTEXT.md. These override anything in this document:

- **Append-only** for financial time-series. Applies to `episodic_memory` rows — no UPDATE, no DELETE except retention sweep.
- **Dual timestamps**: `as_of_date` (business date) vs `observed_date` (collection date) on every stored observation. Episodic memory MUST use `DualTimestampMixin`.
- **Immutability in code** — return new objects, never mutate in place. Belief writers return new belief documents; the writer orchestrator replaces the file atomically.
- **Temporal correctness (no look-ahead)** — every episodic recall MUST filter by `as_of_date <= query.as_of_date`. Violation = look-ahead bias in learned patterns.
- **Tool-first** — LLMs orchestrate memory read/write via typed tools; they do NOT compute confidence updates, recall relevance ranking, or belief-file mutations. Same contract as Phase 6's risk node: deterministic Python decides, LLM rationalizes.
- **Human-readable belief memory** — YAML/JSON only. NEVER opaque embeddings for belief memory. (Embeddings may live alongside episodic for recall, not instead of it — and v1 defers even that.)
- **Humans authoritative** — any belief field with `human_edited=true` must NOT be silently overwritten by a machine writer.
- **Functions <50 lines, files <800 lines, ruff clean, type hints mandatory, UTC timestamps.**
- **Honest positioning** — "system learns from outcomes via self-critique" is accurate; claiming beliefs "improve prediction accuracy" is AI-washing until measured (FINSABER, Delphia).

## User Constraints (from CONTEXT.md)

### Locked Decisions
None — CONTEXT.md is auto-generated with `workflow.skip_discuss=true`. All implementation choices are at Claude's discretion.

### Claude's Discretion
All implementation choices for Phase 7. Use ROADMAP phase goal, success criteria, CLAUDE.md conventions, and Phase 1-6 patterns to guide decisions.

### Non-Negotiable Invariants (from CONTEXT.md `<decisions>`)
- Append-only for episodic records.
- Dual timestamps (`as_of_date` vs `observed_date`).
- Human-readable belief memory (YAML/JSON, NEVER opaque embeddings).
- Immutability in code.
- Tool-first: LLMs orchestrate memory operations, never compute them.
- Temporal correctness on recall.
- Humans authoritative: `human_edited` flag preserved against machine overwrites.

### Expected Architectural Shape (from CONTEXT.md)
- Episodic = append-only SQLAlchemy, optional pgvector ONLY if hit rate comparison justifies it (v1 defers).
- Belief = YAML documents under `beliefs/`, schema-validated loader, in-file revision history.
- Self-critique = new LangGraph node invoked on outcome ingestion; Pattern 2 (deterministic Python for confidence math, LLM rationale only).
- Episodic records carry `policy_sha` from Phase 6.
- `build_debate_pipeline(with_memory=...)` mirrors the `with_risk` switch.

### Deferred Ideas (OUT OF SCOPE)
- **Embedding-based semantic recall (pgvector)** — SQL filter path first; measure before adding complexity.
- **Cross-ticker pattern mining** — sector-wide pattern extraction is Phase 9+.
- **Sophisticated decay/forgetting curves** — 90-day hard cutoff is enough for v1.
- **Belief-conflict resolution UI** — CLI-readable YAML is enough; no dashboard.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEM-01 | Episodic memory stores completed analyses + trade outcomes in PostgreSQL, 90-day retention, queryable by ticker/sector/date range; agent references hits in new research. | Episodic Schema (§Architecture Patterns Pattern 1) + Recall Routing (§Pattern 3) + Retention (§Pattern 5). |
| MEM-02 | Belief memory as human-readable YAML/JSON with investment theses, sector models, learned patterns. | Belief Schema (§Pattern 2) + ruamel.yaml (§Standard Stack) + Validation (§Pattern 6). |
| MEM-03 | Human can edit a belief; next analysis reflects the edit; system does not silently overwrite human corrections. | Human-Override Protection (§Pattern 4) + Writer Contract (§Pattern 7). |
| MEM-04 | After trade outcome is known, self-critique updates relevant beliefs with outcome + adjusted confidence; updated doc shows outcome, rationale, new confidence. | Self-Critique Node (§Pattern 8) + Pattern 2 (deterministic math + LLM rationale) + Belief Revision History (§Pattern 2 revisions list). |

## Architectural Responsibility Map

Memory and learning is multi-tier: a node in the graph, a deterministic Python layer for math/retrieval, a DB layer for episodic, a filesystem layer for belief, and an LLM agent for rationale.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Store episodic record after pipeline run | API / Backend (LangGraph node) | Database | Memory write is deterministic Python inside a node. LLM does not author the record. |
| Recall episodic hits before research | API / Backend (LangGraph node) | Database | Pre-load into state once per run (not per-agent tool call) for reproducibility. |
| Belief read (during research) | API / Backend (tool function) | Filesystem | Agents consult beliefs via a typed tool that returns the YAML-loaded object. |
| Belief write (self-critique) | Backend (deterministic Python) | Filesystem | Writer refuses to overwrite `human_edited` fields. LLM produces rationale only. |
| Confidence-update math | Backend (pure Python) | — | Pattern 2 deterministic — LLM never computes numbers. |
| Human edit detection | Filesystem + schema validation | Backend | `human_edited` boolean + `edited_at` timestamp on each belief field. |
| 90-day retention enforcement | Database (scheduled job) | Backend | Soft-delete by `as_of_date < today - 90d` in a background sweep, not on read. |
| LLM rationale for self-critique | LLM (REASONING tier) | Backend | Same Pattern 2 as Phase 6 `risk_manager_agent`: output schema is rationale-only. |

**Why this matters:** Confidence math must live in deterministic Python, not in the LLM. Retention must be a scheduled sweep, not a read-time filter (read-time filters leak retention semantics into every query). Belief writes must be in a single writer function that owns the `human_edited` contract.

## Standard Stack

### Core (already in pyproject.toml, verified in `uv.lock`)

| Library | Version (verified) | Purpose | Why Standard |
|---------|-------------------|---------|--------------|
| sqlalchemy | >=2.0.49 | Episodic memory ORM model | [VERIFIED: pyproject.toml] Already the project ORM; `DualTimestampMixin` + Alembic patterns established in Phase 1/6. |
| alembic | >=1.18.0 | Migration for new `episodic_memory` table (will be `003_create_episodic_memory.py`) | [VERIFIED: `alembic/versions/002_create_portfolio_positions.py`] Precedent pattern from Phase 6 plan 06-02. |
| pydantic | >=2.12.0 | Belief schema validation (`extra="forbid"`) | [VERIFIED: pyproject.toml] Already used for `RiskPolicy` with `ConfigDict(extra="forbid", frozen=True)`. |
| pydantic-ai | >=1.0.0 | `self_critique_agent` (rationale-only) | [VERIFIED: pyproject.toml] Already the agent framework. |
| langgraph | >=1.1.0 | `memory_recall_node` / `episodic_store_node` integration | [VERIFIED: pyproject.toml] Already compiled into every pipeline. |
| psycopg[binary,pool] | >=3.3.0 | PostgreSQL driver (inherits) | [VERIFIED: pyproject.toml] No change needed. |
| pyyaml | 6.0.3 | Currently used for `risk_policy.yaml` — we will **keep for READ**, but add `ruamel.yaml` for WRITE | [VERIFIED: `uv.lock`] Already transitively pinned; do not remove. |

### New Supporting Library

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| ruamel.yaml | >=0.19.0 | Round-trip read/write of belief YAML preserving comments, key order, and quotes | [CITED: https://pypi.org/project/ruamel.yaml/] The **only** Python library that preserves comments across read→edit→write. Humans will annotate beliefs (`# flagged 2026-04-15 by Max: reconsider after Q2 earnings`) and we MUST preserve those notes or we lose the human-authoritative contract (MEM-03). PyYAML strips comments on dump — disqualifying for machine writes that must preserve human edits. |

**Installation command:**
```bash
uv add ruamel.yaml>=0.19.0
```

**Version verification — run before writing code:**
```bash
# Confirm current release:
curl -s https://pypi.org/pypi/ruamel.yaml/json | python -c "import sys,json; print(json.load(sys.stdin)['info']['version'])"
```

### Deferred Libraries (DO NOT ADD in Phase 7)

| Library | Why Deferred |
|---------|--------------|
| pgvector / pgvector-python | [CITED: CONTEXT.md `<deferred>`] Semantic recall is a Phase 9+ concern. Ship SQL filter path first, measure hit rate, justify embeddings with data. Adding pgvector before it is needed bloats the schema and introduces an embedding pipeline as a second failure mode. |
| langmem / LangGraph Store | [CITED: https://docs.langchain.com/oss/python/langgraph/memory] LangGraph's `BaseStore` is a generic KV for cross-thread conversational memory — it is NOT suitable for structured domain memory with schema validation + human-edit contracts. It would double as a second write path that our writer cannot defend. Keep the checkpointer for state persistence only. |
| embedding libraries (sentence-transformers, voyage-python) | Same reason as pgvector. |
| sqlalchemy-json / sqlalchemy-utils JSONB helpers | Native `sqlalchemy.dialects.postgresql.JSONB` is sufficient; no need for extra deps. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ruamel.yaml | PyYAML (already present) | [CITED: https://copyprogramming.com/howto/python-yaml-update-preserving-order-and-comments] PyYAML strips comments and loses key order on dump. Keeping PyYAML for machine writes would destroy human-authored annotations on every critique cycle — violates MEM-03. Use PyYAML for read-only or policy-like files (e.g., `risk_policy.yaml` where humans do not embed operational notes). |
| ruamel.yaml | JSON + sidecar `.md` for human notes | Splits the human-readable unit into two files and breaks the "open the file, read the beliefs, understand why" contract (success criterion 2). Rejected. |
| Append-only SQLAlchemy table | Event-sourced log + projection | Over-engineering for v1. Phase 1-6 established append-only as the project convention; do not deviate. |
| JSONB payload column | Flatten every field into separate columns | [CITED: https://sqlpad.io/tutorial/postgresql-jsonb-vs-columns-performance-guide/] Flattening forces migrations on every thesis-schema change. We WILL extract hot-path filter columns (ticker, sector, as_of_date, policy_sha) as real B-tree-indexed columns AND keep the full `ThesisOutput.model_dump()` in a JSONB `payload` column. Best-of-both. |
| PostgreSQL soft delete for 90-day retention | pg_partman monthly partitions | [CITED: https://www.crunchydata.com/blog/auto-archiving-and-data-retention-management-in-postgres-with-pg_partman] Partitioning is faster at scale but premature for v1 where episodic volume is bounded (one row per analysis, ~few hundred/month at most). Simple cron-invoked `DELETE WHERE as_of_date < CURRENT_DATE - INTERVAL '90 days'` is sufficient. Revisit when episodic crosses ~1M rows. |
| Domain memory in LangGraph Store | Custom SQLAlchemy layer | [CITED: https://docs.langchain.com/oss/python/langgraph/memory] LangGraph Store is a generic KV designed for conversational cross-thread memory, not for structured financial records with dual timestamps and `policy_sha` linkage. Our existing SQLAlchemy infrastructure + `DualTimestampMixin` is the right substrate. |
| PydanticAI tool for episodic recall | LangGraph node that pre-loads | Tool-per-agent means N LLM-driven decisions about when to recall — nondeterministic, expensive, harder to test. Node pre-load = one deterministic query before manager runs; every downstream agent sees the same `episodic_hits`. Node wins for v1. |

## Architecture Patterns

### System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                       LIVE PIPELINE (with_memory=True)               │
│                                                                      │
│  START                                                               │
│    │                                                                 │
│    ▼                                                                 │
│  memory_recall_node ─── reads episodic_memory (SQL) ──┐              │
│    │   (writes episodic_hits + beliefs_consulted      │              │
│    │    into state)                                    │              │
│    ▼                                                   │              │
│  [fundamental, sentiment, technical]  ◄── all 3 see   │              │
│    │   (parallel analysts)                episodic_hits              │
│    ▼                                                                 │
│  manager_node         ◄── reads beliefs_consulted                   │
│    │                                                                 │
│    ▼                                                                 │
│  bull → bear → rebuttal → final_arguments → debate_synthesis        │
│    │                                                                 │
│    ▼                                                                 │
│  risk_manager_node  (Phase 6)                                        │
│    │                                                                 │
│    ▼ (conditional on APPROVED)                                       │
│  signal_node                                                         │
│    │                                                                 │
│    ▼                                                                 │
│  episodic_store_node ── writes NEW row into episodic_memory         │
│    │                    (ticker, as_of_date, payload JSONB,         │
│    │                     policy_sha, signal.direction, ...)          │
│    ▼                                                                 │
│  END                                                                 │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                 OFFLINE LOOP (outcome → self-critique)               │
│                                                                      │
│  Operator script: ingest_outcome.py --ticker X --pnl_pct 4.2        │
│    │                                                                 │
│    ▼                                                                 │
│  append_outcome()  ── INSERT INTO episodic_memory (                 │
│    │                      ticker, as_of_date=today,                 │
│    │                      outcome_pct, linked_signal_id, ...)        │
│    ▼                                                                 │
│  run_self_critique(ticker)                                           │
│    │                                                                 │
│    ├─► load_belief(ticker) ── ruamel.yaml round-trip                │
│    │                                                                 │
│    ├─► compute_new_confidence(                                       │
│    │     old_confidence, outcome_pct, signal_direction)              │
│    │     ── PURE PYTHON, deterministic (Pattern 2)                   │
│    │                                                                 │
│    ├─► self_critique_agent.run(rationale_prompt)                    │
│    │     ── RationaleOnly schema (str ≤ 2000 chars)                 │
│    │                                                                 │
│    └─► write_belief(                                                 │
│          old_belief,                                                 │
│          field_patches={'confidence': new_conf, 'rationale': ...},  │
│          skip_if_human_edited=True   ◄── CRITICAL (MEM-03)          │
│        )                                                             │
│          │                                                           │
│          ▼                                                           │
│        beliefs/X.yaml  (atomic replace via tmp+rename)              │
└──────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
src/ai_hedge_fund/
├── memory/                              # NEW Phase 7 subpackage
│   ├── __init__.py
│   ├── episodic.py                      # SQLAlchemy model + query + retention sweep
│   ├── beliefs.py                       # ruamel.yaml load/write + human-edit guard
│   ├── critique.py                      # deterministic confidence update (Pattern 2)
│   └── recall.py                        # deterministic episodic recall (SQL)
├── agents/
│   └── self_critique.py                 # PydanticAI agent (RationaleOnly, REASONING tier)
├── graph/
│   ├── memory_deps.py                   # NEW frozen dataclass (mirrors risk_deps.py)
│   ├── nodes.py                         # ADD memory_recall_node, episodic_store_node
│   └── pipeline.py                      # EXTEND build_debate_pipeline(with_memory=...)
├── schemas/
│   ├── memory.py                        # NEW: EpisodicHit, Belief, CritiqueEvent
│   └── state.py                         # ADD episodic_hits, beliefs_consulted to DebatePipelineState
├── db/
│   └── models.py                        # ADD EpisodicMemory SQLAlchemy model
└── scripts/
    ├── ingest_outcome.py                # NEW CLI: operator ingests a trade outcome
    └── purge_expired_episodic.py        # NEW CLI: 90-day retention sweep (cron-invoked)

alembic/versions/
└── 003_create_episodic_memory.py        # NEW migration

beliefs/                                 # NEW top-level directory (human-editable)
├── tickers/
│   ├── AAPL.yaml
│   ├── MSFT.yaml
│   └── ...
├── sectors/
│   └── Technology.yaml
└── patterns/
    └── insider_cluster_alpha.yaml

tests/
├── memory/                              # NEW suite
│   ├── conftest.py                      # fixtures: seeded_episodic, sample_belief_dir
│   ├── fixtures/
│   │   ├── belief_aapl.yaml
│   │   ├── belief_aapl_human_edited.yaml
│   │   └── seeded_episodic.csv
│   ├── test_episodic_model.py
│   ├── test_episodic_recall.py
│   ├── test_belief_schema.py
│   ├── test_belief_writer.py            # human-edit preservation
│   ├── test_critique_math.py            # deterministic confidence update
│   └── test_self_critique_agent.py      # TestModel stub
├── graph/
│   └── test_memory_nodes.py             # memory_recall_node, episodic_store_node
└── integration/
    └── test_phase7_e2e.py               # end-to-end: run pipeline → outcome → critique → re-run
```

### Pattern 1: Episodic Memory SQLAlchemy Model (MEM-01)

Follows the Phase 1-6 table conventions exactly. Two dates (`DualTimestampMixin`) + hot-path filter columns + JSONB `payload` for the full thesis dump.

```python
# src/ai_hedge_fund/db/models.py  (append to existing file)
# Source: [CITED] follows the PortfolioPosition pattern in the same file

from sqlalchemy import BigInteger, Date, DateTime, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ai_hedge_fund.db.base import Base, DualTimestampMixin


class EpisodicMemory(Base, DualTimestampMixin):
    """Append-only episodic record of a completed analysis or trade outcome.

    Two record types share this table:
        record_type='analysis'  — produced by episodic_store_node at pipeline end
        record_type='outcome'   — produced by scripts/ingest_outcome.py

    Retention: 90 days from as_of_date, enforced by purge_expired_episodic.py.
    """

    __tablename__ = "episodic_memory"
    __table_args__ = (
        Index("ix_episodic_ticker_asof", "ticker", "as_of_date"),
        Index("ix_episodic_sector_asof", "sector", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    sector: Mapped[str] = mapped_column(String(50), nullable=False, default="Unknown")
    record_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "analysis" | "outcome"

    # Hot-path filter fields extracted from payload for B-tree indexing
    signal_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # set on outcome rows
    linked_analysis_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # outcome -> analysis

    # Phase 6 link-back: which policy produced the decision
    policy_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Full thesis + signal + risk_assessment snapshot
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
```

**Why JSONB + extracted columns, not pure JSONB:**
[CITED: https://sqlpad.io/tutorial/postgresql-jsonb-vs-columns-performance-guide/] — broad GIN indexes on JSONB are slow for filtered queries; B-tree on `(ticker, as_of_date)` delivers sub-ms lookups. Keep the full payload in JSONB so the thesis schema can evolve without migrations.

**Migration** (`alembic/versions/003_create_episodic_memory.py`) follows `002_create_portfolio_positions.py` verbatim with the above column set.

### Pattern 2: Belief Memory YAML Schema (MEM-02, MEM-04)

Each belief file is a Pydantic-validated document. `extra="forbid"` raises on unknown keys — same contract as `RiskPolicy` in `src/ai_hedge_fund/risk/policy.py`. [CITED: `src/ai_hedge_fund/risk/policy.py` lines 41-44]

```yaml
# beliefs/tickers/AAPL.yaml  (example)
ticker: AAPL
sector: Technology
version: 3
thesis: |
  AAPL is a high-margin hardware + services hybrid.
  Services gross margin >70% provides downside protection
  in hardware cycles.
confidence: 72
human_edited: false
edited_at: null

# Machine-writable fields
critique_history:
  - as_of_date: 2026-03-15
    outcome_pct: 4.2
    old_confidence: 70
    new_confidence: 72
    rationale: "Long thesis correct — iPhone upgrade cycle beat consensus"
    source: "self_critique"
  - as_of_date: 2026-01-10
    outcome_pct: -1.8
    old_confidence: 74
    new_confidence: 70
    rationale: "Mild services deceleration"
    source: "self_critique"

# Fields humans flag as locked
field_locks:
  thesis: false        # machine may update
  confidence: false    # machine may update
  sector: true         # sector never changes via machine
```

```python
# src/ai_hedge_fund/schemas/memory.py
# Source: [CITED] pattern follows src/ai_hedge_fund/risk/policy.py::RiskPolicy

from datetime import date
from pydantic import BaseModel, ConfigDict, Field


class CritiqueEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of_date: date
    outcome_pct: float
    old_confidence: int = Field(ge=0, le=100)
    new_confidence: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=1, max_length=2000)
    source: str = Field(pattern=r"^(self_critique|human)$")


class Belief(BaseModel):
    model_config = ConfigDict(extra="forbid")  # NOT frozen — writer produces new instance

    ticker: str = Field(min_length=1, max_length=10)
    sector: str
    version: int = Field(ge=1)
    thesis: str = Field(min_length=1, max_length=10_000)
    confidence: int = Field(ge=0, le=100)
    human_edited: bool = False
    edited_at: date | None = None
    critique_history: list[CritiqueEvent] = Field(default_factory=list)
    field_locks: dict[str, bool] = Field(default_factory=dict)
```

### Pattern 3: Episodic Recall as a LangGraph Node (MEM-01 recall path)

Runs BEFORE the three analyst fan-out so every agent sees the same hits.

```python
# src/ai_hedge_fund/graph/nodes.py  (new node)
# Source: [CITED] structurally mirrors risk_manager_node in the same file

async def memory_recall_node(
    state: DebatePipelineState, deps: MemoryDeps
) -> dict:
    """Pre-load episodic hits + consulted beliefs into state.

    Temporal correctness: queries filter by as_of_date <= state['as_of_date'].
    """
    if state.get("error"):
        return {}

    as_of = date.fromisoformat(state["as_of_date"])
    ticker = state["ticker"]
    sector = (state.get("candidate_metadata") or {}).get("sector", "Unknown")

    hits = deps.db_session.scalars(
        select(EpisodicMemory)
        .where(EpisodicMemory.as_of_date <= as_of)
        .where(
            (EpisodicMemory.ticker == ticker) | (EpisodicMemory.sector == sector)
        )
        .order_by(EpisodicMemory.as_of_date.desc())
        .limit(deps.recall_limit)
    ).all()

    beliefs = load_relevant_beliefs(deps.beliefs_path, ticker=ticker, sector=sector)

    return {
        "episodic_hits": [to_hit_dict(h) for h in hits],
        "beliefs_consulted": [b.model_dump() for b in beliefs],
    }
```

### Pattern 4: Human-Override Detection + Preservation (MEM-03)

The belief writer is the SOLE mutation entry point. Every write path MUST go through it. The writer checks `field_locks[field]` and refuses to overwrite locked fields or any field when `human_edited=True` and the `edited_at` is newer than the last machine critique.

```python
# src/ai_hedge_fund/memory/beliefs.py
# Source: [CITED] contract mirrors Phase 6's risk_manager_node "deterministic overwrite
# discarded" pattern — writer is the authoritative decider

from datetime import date
from pathlib import Path
from ruamel.yaml import YAML

yaml = YAML()  # round-trip mode by default — preserves comments + key order
yaml.preserve_quotes = True


def load_belief(path: Path) -> tuple[Belief, dict]:
    """Return (validated Belief, raw ruamel object for round-trip write)."""
    raw = yaml.load(path)
    return Belief.model_validate(raw), raw


def write_belief(
    path: Path,
    raw: dict,
    patches: dict,
    *,
    skip_if_human_edited: bool = True,
) -> dict:
    """Apply patches to raw belief dict; skip fields the human has locked.

    Returns dict of {applied: [...], skipped: [...], reason: {...}} for audit.
    """
    applied: list[str] = []
    skipped: dict[str, str] = {}
    locks = raw.get("field_locks", {}) or {}
    human_edited = bool(raw.get("human_edited"))

    for field, value in patches.items():
        if field in {"human_edited", "edited_at", "field_locks"}:
            skipped[field] = "writer_never_touches_override_meta"
            continue
        if locks.get(field) is True:
            skipped[field] = "field_locked_by_human"
            continue
        if human_edited and field in {"thesis", "confidence"} and skip_if_human_edited:
            skipped[field] = "human_edited_global_flag_set"
            continue
        raw[field] = value
        applied.append(field)

    raw["version"] = int(raw.get("version", 0)) + 1

    # Atomic write: tmp + rename prevents half-written files
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        yaml.dump(raw, f)
    tmp.replace(path)

    return {"applied": applied, "skipped": skipped}
```

**Contract:**
- `write_belief` NEVER clears `human_edited`. Only a human CLI/command can clear it.
- `human_edited=True` means: any field that would be touched by self-critique (`thesis`, `confidence`) is skipped.
- `field_locks.{field}=true` is the fine-grained version — locks a single field regardless of `human_edited` global.
- Every skip is recorded in the return value and logged via structlog so the audit trail shows WHY a critique did not apply.

### Pattern 5: 90-Day Retention

Simple scheduled sweep. No partitioning yet (defer until episodic >1M rows, per `Deferred Libraries`).

```python
# src/ai_hedge_fund/scripts/purge_expired_episodic.py
# Cron-invoked daily.  Idempotent.

from datetime import date, timedelta
from sqlalchemy import delete
from ai_hedge_fund.db.models import EpisodicMemory

def purge(session, retention_days: int = 90) -> int:
    cutoff = date.today() - timedelta(days=retention_days)
    result = session.execute(
        delete(EpisodicMemory).where(EpisodicMemory.as_of_date < cutoff)
    )
    session.commit()
    return result.rowcount
```

**Note on append-only:** we delete expired rows in the retention sweep but NEVER update them. That's compatible with append-only (the financial time-series convention applies to live data; retention is operational cleanup).

### Pattern 6: Self-Critique — Pattern 2 (Deterministic Math + LLM Rationale)

Exactly mirrors Phase 6's `risk_manager_agent` — the LLM produces `RationaleOnly`; deterministic Python decides the number.

```python
# src/ai_hedge_fund/memory/critique.py
# Source: [CITED] Pattern 2 from 06-RESEARCH.md and src/ai_hedge_fund/agents/risk_manager.py

def compute_new_confidence(
    old_confidence: int,
    outcome_pct: float,
    signal_direction: str,  # "long" | "short" | "neutral"
    k: float = 0.3,
) -> int:
    """Deterministic Bayesian-ish update.

    If the outcome agreed with the signal direction, confidence drifts toward
    min(old + k*|outcome|*10, 100).  If it disagreed, confidence drifts toward
    max(old - k*|outcome|*10, 0).  Neutral signals with big outcomes penalize
    confidence (the system hedged wrongly).
    """
    agreed = (
        (signal_direction == "long" and outcome_pct > 0)
        or (signal_direction == "short" and outcome_pct < 0)
    )
    adjustment = k * abs(outcome_pct) * 10
    if signal_direction == "neutral":
        # neutral gets penalized for any significant move — it missed a signal
        new = max(0, old_confidence - adjustment)
    elif agreed:
        new = min(100, old_confidence + adjustment)
    else:
        new = max(0, old_confidence - adjustment)
    return int(round(new))
```

```python
# src/ai_hedge_fund/agents/self_critique.py
# Source: [CITED] mirrors src/ai_hedge_fund/agents/risk_manager.py verbatim

class RationaleOnly(BaseModel):
    rationale: str = Field(min_length=1, max_length=2000)

SELF_CRITIQUE_SYSTEM_PROMPT = (
    "You are the self-critique rationale writer. A deterministic Python "
    "function has ALREADY computed the new confidence for an investment "
    "thesis given a trade outcome. Your ONLY job is to EXPLAIN the change "
    "in one paragraph.\n"
    "\n"
    "STRICT RULES:\n"
    "1. You DO NOT author the number. You EXPLAIN the number already computed.\n"
    "2. State the direction (raised/lowered/unchanged), the old and new "
    "confidence, and WHICH evidence from the thesis + outcome supports the change.\n"
    "3. Never suggest re-writing the thesis body. Suggesting a rewrite is "
    "a human's job.\n"
    "4. Output a single RationaleOnly object. 2-5 sentences. No headings.\n"
)

self_critique_agent = Agent(
    ModelTier.REASONING.value,
    output_type=RationaleOnly,
    system_prompt=SELF_CRITIQUE_SYSTEM_PROMPT,
    retries=2,
)
```

### Pattern 7: Integration Switch on `build_debate_pipeline`

Mirrors `with_risk` exactly.

```python
# src/ai_hedge_fund/graph/pipeline.py  (EXTEND)
# Source: [CITED] follows build_debate_pipeline(with_risk=True, risk_deps=...) in
# the same file

def build_debate_pipeline(
    checkpointer: BaseCheckpointSaver | None = None,
    *,
    with_risk: bool = False,
    risk_deps: RiskDeps | None = None,
    with_memory: bool = False,
    memory_deps: MemoryDeps | None = None,
) -> CompiledStateGraph:
    if with_memory and memory_deps is None:
        raise ValueError(
            "build_debate_pipeline(with_memory=True) requires memory_deps -- "
            "supply a MemoryDeps instance with db_session and beliefs_path."
        )
    ...
    if with_memory:
        async def _memory_recall_bound(state):
            return await memory_recall_node(state, memory_deps)
        async def _episodic_store_bound(state):
            return await episodic_store_node(state, memory_deps)

        builder.add_node("memory_recall", _memory_recall_bound)
        builder.add_node("episodic_store", _episodic_store_bound)

        # Entry: START -> memory_recall -> 3 analysts (was START -> 3 analysts)
        builder.add_edge(START, "memory_recall")
        builder.add_edge("memory_recall", "fundamental")
        builder.add_edge("memory_recall", "sentiment")
        builder.add_edge("memory_recall", "technical")

        # Exit: signal -> episodic_store -> END (was signal -> END)
        builder.add_edge("signal", "episodic_store")
        builder.add_edge("episodic_store", END)
    else:
        # Phase-6 backcompat path unchanged
        builder.add_edge(START, "fundamental")
        ...
        builder.add_edge("signal", END)
```

**Composition with `with_risk`:** The two flags compose. When both are True, topology is:
```
START → memory_recall → [fund, sent, tech] → manager → debate → risk_manager
                                                                  ├─(APPROVED)→ signal → episodic_store → END
                                                                  └─(VETOED)   → END  (no episodic_store — we only persist approved decisions; alternatively, store with status for audit)
```
**Open decision:** whether to persist VETOED decisions in episodic memory. Recommendation: YES — they are the richest learning signal. Store with `payload.risk_assessment.status="VETOED"` and never produce a signal row. Add as a follow-up edge `risk_manager --conditional--> {signal, episodic_store_vetoed}` if we want both paths to persist. Flag as plan-phase decision.

### Pattern 8: State Schema Extension

```python
# src/ai_hedge_fund/schemas/state.py  (EXTEND DebatePipelineState)

class DebatePipelineState(TypedDict, total=False):
    # ...existing fields unchanged...

    # Phase 7 additions
    episodic_hits: list[dict] | None
    """Prior episodic records loaded by memory_recall_node. Each dict carries
    ticker, as_of_date, record_type ('analysis'|'outcome'), signal_direction,
    confidence, outcome_pct (if outcome row), and a truncated payload snippet."""

    beliefs_consulted: list[dict] | None
    """Loaded belief documents relevant to this ticker/sector — read-only
    snapshot; writes happen offline in the self-critique loop."""
```

### Anti-Patterns to Avoid

- **Self-critique fires inside the live pipeline.** No — outcomes arrive HOURS to DAYS after the signal. Self-critique runs in an offline script triggered by outcome ingestion. Putting it in the live pipeline would require blocking on outcome data that does not exist yet.
- **Embedding index before hit-rate justifies it.** [CITED: CONTEXT.md `<deferred>`] Ship SQL filters, measure recall quality, THEN decide on pgvector. Vector complexity is a second failure mode without data to justify it.
- **LLM-authored confidence number.** Same trap as Phase 6's LLM-authored status. Rationale-only schema; Python decides the number.
- **Read-time retention filter (`WHERE as_of_date > today - 90d` on every query).** Leaks retention semantics into every consumer. Enforce retention in a sweep job, not in the read path.
- **Belief writer that clears `human_edited` after a machine write.** Violates MEM-03. Only a human command clears `human_edited`.
- **Single belief file for all tickers (`beliefs.yaml`).** File-level locking, merge conflicts, and audit-review UX all collapse. One file per ticker/sector.
- **In-place `dict.update()` on loaded belief raw.** Lose ruamel round-trip state → lose comments → violate MEM-03. Use the writer function (Pattern 4).
- **Per-agent PydanticAI tool for episodic recall (v1).** Makes the recall count + relevance sensitive to the LLM's mood. Pre-load deterministically in a node; use tools in v2 if an agent needs follow-up recall.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Round-trip YAML preserving comments | Custom comment-preserving parser | ruamel.yaml | [CITED: https://pypi.org/project/ruamel.yaml/] The problem is nontrivial (comment tokens, anchors, flow vs block style). ruamel.yaml has solved it for a decade. |
| Schema validation with unknown-key rejection | Custom dict checker | Pydantic `ConfigDict(extra="forbid")` | [VERIFIED: `src/ai_hedge_fund/risk/policy.py`] Already the project pattern. |
| Atomic file write | `open("w")` followed by write | `tmp = path.with_suffix(".tmp"); write tmp; tmp.replace(path)` | Python's `Path.replace` is atomic on POSIX — no partial files on crash. |
| JSONB queries from Python | Raw SQL with string concatenation | SQLAlchemy Core + `func.jsonb_*` | [CITED: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#sqlalchemy.dialects.postgresql.JSONB] Parameterized + typed. |
| LLM rationale cap | Truncating LLM output in Python | Pydantic `Field(max_length=2000)` + PydanticAI `UsageLimits(output_tokens_limit=4_000)` | [VERIFIED: `src/ai_hedge_fund/agents/risk_manager.py` lines 52-61] Same dual-bound trick Phase 6 uses. |
| Outcome Bayesian update | Rolling your own Bayesian update library | 4-line pure function (`compute_new_confidence`) | A 4-line bounded-linear update is pedagogically clear, testable with property tests, and auditable. Full Bayesian machinery is premature. |
| Belief file discovery | Walking the filesystem manually | `Path(beliefs_dir).glob("tickers/*.yaml")` | Standard library. |
| Retention cron | Writing a daemon | OS-level cron invoking a Python script | OS cron is battle-tested; writing a daemon adds an ops dependency. |

**Key insight:** The whole phase is `DB model + file-writer + one LangGraph node + one offline script + one Pattern-2 LLM agent`. Every piece has a direct precedent in Phases 1-6. Custom code is the wrong instinct — the shape already exists.

## Runtime State Inventory

N/A — greenfield feature. No rename, refactor, or string replacement. Nothing to migrate.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| PostgreSQL 16+ | episodic_memory table | ✓ | Already used by Phase 1-6 (`docker-compose.yml`) | — |
| Alembic | 003 migration | ✓ | >=1.18.0 | — |
| Python 3.11+ | Dataclasses, `str \| None`, match | ✓ | Target py312 per ruff config | — |
| ruamel.yaml | Belief file round-trip | ✗ | — | Must `uv add ruamel.yaml>=0.19.0` — no viable fallback given MEM-03 comment-preservation requirement |
| cron / systemd timer | Daily retention sweep | Varies per environment | — | Manual invocation of `purge_expired_episodic.py` for v1 dev; operator sets up cron for prod. Acceptable since retention is operational, not correctness-critical. |
| `config/beliefs/` directory | Writable filesystem path | ✓ | — | — |

**Missing dependencies with no fallback:** `ruamel.yaml` must be added.

**Missing dependencies with fallback:** cron — planner should decide whether to provide a Makefile target / systemd service file or defer to operator runbook.

## Common Pitfalls

### Pitfall 1: Silent overwrite of human edits
**What goes wrong:** Self-critique rewrites `thesis` or `confidence` even though a human marked `human_edited=true`.
**Why it happens:** Writer takes patches blindly; no check for the `human_edited` flag or per-field lock.
**How to avoid:** `write_belief` is the SOLE mutation entry point and enforces the check. All machine writers go through it.
**Warning sign:** A test asserts `human_edited=true` survives a critique cycle; failing that test = regression.

### Pitfall 2: Temporal leakage in recall
**What goes wrong:** `memory_recall_node` returns episodic records dated AFTER `state["as_of_date"]` — analyst sees future data, violates look-ahead-free contract (DATA-07).
**Why it happens:** Query forgets the `as_of_date <= state["as_of_date"]` filter.
**How to avoid:** Recall query always includes `.where(EpisodicMemory.as_of_date <= as_of)`. Unit test: seed a hit with a FUTURE `as_of_date`, assert recall with an earlier cutoff returns zero rows.
**Warning sign:** Integration test `test_recall_no_lookahead` (see Testing Strategy).

### Pitfall 3: Unbounded `critique_history` growth
**What goes wrong:** After 3 years of daily trades, each belief has ~1000 critique events → file grows to megabytes, slow to load, unreadable by humans.
**Why it happens:** No cap, no rollup.
**How to avoid:** Cap `critique_history` to last N (e.g., 50); archive older events to a sibling `beliefs/tickers/AAPL.history.yaml`. Humans see the recent history in the main file; auditors see the full log in the history file.
**Warning sign:** Belief file exceeds ~200 lines; belief load time >50ms.

### Pitfall 4: Unknown YAML keys silently accepted
**What goes wrong:** Human adds a typoed key (`confidance: 72`) thinking they updated confidence; machine updates the real `confidence` field, human's correction is lost.
**Why it happens:** Belief loader doesn't `extra="forbid"`.
**How to avoid:** `Belief` model uses `ConfigDict(extra="forbid")`. Unknown key → `ValidationError` at load; operator catches the typo before a critique cycle overwrites.
**Warning sign:** Test asserts a belief with `confidance: 72` raises `ValidationError`.

### Pitfall 5: Confidence drift from machine-only updates
**What goes wrong:** Over months, a sequence of mixed outcomes drifts confidence toward a fixed point (50) regardless of thesis quality.
**Why it happens:** The update rule `old ± k*|outcome|*10` has no reversion anchor.
**How to avoid:** Cap updates per event (`|new − old| <= 10`) so drift is bounded; require a human-marked belief reset if confidence saturates at 0 or 100 for N events.
**Warning sign:** A belief's `confidence` enters a 40-60 attractor over 10 events with mixed outcomes.

### Pitfall 6: JSONB payload schema evolution breaks recall
**What goes wrong:** Thesis schema gains a field in Phase 8; old episodic rows have the old shape; `memory_recall_node` passes the payload to an analyst that expects the new shape.
**Why it happens:** JSONB = flexible but versionless.
**How to avoid:** Include `schema_version: int` in every payload. Recall returns records with the current schema version by default; legacy records are loaded through a version migrator (pure Python) before presenting to agents.
**Warning sign:** Analyst sees a KeyError on a Phase 7 payload field.

### Pitfall 7: Belief writer race condition
**What goes wrong:** Two self-critique processes write the same belief simultaneously; one clobbers the other's update.
**Why it happens:** No file lock; `replace()` is atomic but two writers can still race.
**How to avoid:** Self-critique is offline and serial per ticker (the outcome-ingest script processes one ticker at a time). If parallelism is ever added, use `filelock`. For v1, document the serial-per-ticker assumption in `critique.py` docstring.
**Warning sign:** In a stress test, two concurrent `write_belief` calls produce a final file missing one of the updates.

### Pitfall 8: Recall returns too many hits, blowing the LLM's context window
**What goes wrong:** After 6 months, a popular ticker has dozens of episodic records. `memory_recall_node` returns them all; analyst prompt balloons past the input-tokens-limit.
**Why it happens:** No `limit` on the recall query.
**How to avoid:** `MemoryDeps.recall_limit: int = 10` default; queries always `LIMIT`. Include the most-recent AND highest-signal hits (e.g., largest `|outcome_pct|`).
**Warning sign:** Per-run token cost creeps up over months of pipeline runs.

### Pitfall 9: Belief file path traversal / injection
**What goes wrong:** An operator passes `ticker="../../etc/passwd"` to an `ingest_outcome` script; `beliefs_path / f"{ticker}.yaml"` resolves outside `beliefs/`.
**Why it happens:** No ticker validation.
**How to avoid:** Validate ticker with `re.fullmatch(r"[A-Z0-9.\-]{1,10}", ticker)` before joining to the path. Same contract the project already uses for SEC ticker fields.
**Warning sign:** Test that `ingest_outcome --ticker "../foo"` raises ValueError.

## Code Examples

### Episodic Store on Pipeline End

```python
# src/ai_hedge_fund/graph/nodes.py (new node)
# Source: [CITED] mirrors episodic patterns from Phase 6's risk_manager_node
async def episodic_store_node(
    state: DebatePipelineState, deps: MemoryDeps
) -> dict:
    """Append a new episodic_memory row at pipeline end.

    Runs even on VETOED decisions for audit — we learn more from vetoes than
    from approvals.
    """
    thesis = state.get("thesis") or {}
    signal = state.get("signal")
    risk = state.get("risk_assessment") or {}
    meta = state.get("candidate_metadata") or {}

    row = EpisodicMemory(
        ticker=state["ticker"],
        sector=meta.get("sector", "Unknown"),
        record_type="analysis",
        signal_direction=(signal or {}).get("direction"),
        confidence=thesis.get("confidence"),
        outcome_pct=None,
        linked_analysis_id=None,
        policy_sha=risk.get("policy_sha"),
        as_of_date=state["as_of_date"],
        payload={
            "schema_version": 1,
            "thesis": thesis,
            "signal": signal,
            "risk_assessment": risk,
            "episodic_hits_count": len(state.get("episodic_hits") or []),
            "beliefs_consulted_count": len(state.get("beliefs_consulted") or []),
        },
    )
    deps.db_session.add(row)
    deps.db_session.commit()
    return {"episodic_stored_id": row.id}
```

### Offline Outcome Ingest + Self-Critique

```python
# src/ai_hedge_fund/scripts/ingest_outcome.py
# Source: [CITED] follows Pattern 2 from Phase 6

async def ingest_outcome(
    session, beliefs_dir: Path, ticker: str, outcome_pct: float, as_of_date: date
) -> None:
    # 1. Append the outcome row (append-only)
    analysis = session.scalars(
        select(EpisodicMemory)
        .where(EpisodicMemory.ticker == ticker)
        .where(EpisodicMemory.record_type == "analysis")
        .order_by(EpisodicMemory.as_of_date.desc())
        .limit(1)
    ).one_or_none()

    session.add(EpisodicMemory(
        ticker=ticker, sector=analysis.sector if analysis else "Unknown",
        record_type="outcome", outcome_pct=outcome_pct,
        linked_analysis_id=analysis.id if analysis else None,
        signal_direction=(analysis.signal_direction if analysis else None),
        as_of_date=as_of_date, payload={"schema_version": 1},
    ))
    session.commit()

    # 2. Run self-critique
    belief_path = beliefs_dir / "tickers" / f"{ticker}.yaml"
    belief, raw = load_belief(belief_path)
    new_conf = compute_new_confidence(
        old_confidence=belief.confidence,
        outcome_pct=outcome_pct,
        signal_direction=analysis.signal_direction if analysis else "neutral",
    )

    prompt = format_critique_context(belief, outcome_pct, new_conf, analysis)
    result = await self_critique_agent.run(prompt, usage_limits=get_self_critique_limits())

    # 3. Write — writer enforces human-edit guard
    outcome = write_belief(
        belief_path, raw,
        patches={
            "confidence": new_conf,
            "critique_history": (raw.get("critique_history") or []) + [
                {
                    "as_of_date": as_of_date.isoformat(),
                    "outcome_pct": outcome_pct,
                    "old_confidence": belief.confidence,
                    "new_confidence": new_conf,
                    "rationale": result.output.rationale,
                    "source": "self_critique",
                }
            ],
        },
    )
    logger.info("self_critique_applied", ticker=ticker, **outcome)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Long-term memory inside LangGraph checkpointer | Dedicated BaseStore + LangMem SDK for semantic memory | LangGraph 1.x (2025) | [CITED: https://docs.langchain.com/oss/python/langgraph/memory] Checkpointer is thread-scoped; Store is cross-thread. We need neither for domain memory — our SQLAlchemy layer is the right primitive. |
| Pure vector store for episodic recall | Hybrid: structured columns + JSONB + optional pgvector | 2024→2026 | [CITED: https://aws.amazon.com/blogs/database/build-persistent-memory-for-agentic-ai-applications-with-mem0-open-source-amazon-elasticache-for-valkey-and-amazon-neptune-analytics/] Hybrid + temporal filter is the consensus for financial agents; pure vector loses on "available as of" semantics. |
| Deleting rows for retention | Partition dropping via pg_partman | Scale inflection | [CITED: https://www.crunchydata.com/blog/auto-archiving-and-data-retention-management-in-postgres-with-pg_partman] Premature for v1; revisit at ~1M episodic rows. |
| PyYAML for human-editable config | ruamel.yaml for round-trip + comments | ~2020→current | [CITED: https://pypi.org/project/ruamel.yaml/] PyYAML still fine for read-only and policy files; ruamel.yaml is mandatory when machine writes must preserve human annotations. |

**Deprecated / outdated:**
- PyYAML-only workflow for human-edited config that a machine also writes back. Does not preserve comments. [CITED: https://copyprogramming.com/howto/python-yaml-update-preserving-order-and-comments]
- Opaque embedding-only belief memory. Violates CLAUDE.md "belief memory is human-readable" invariant.

## Validation Architecture

Project config: `workflow.nyquist_validation = true` — this section is required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (already in `[dependency-groups]`) |
| Config file | `pyproject.toml` → `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/memory tests/graph/test_memory_nodes.py -q` |
| Full suite command | `uv run pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| MEM-01 | Episodic row is appended after pipeline run | integration | `uv run pytest tests/integration/test_phase7_e2e.py::test_episodic_row_appended_after_approved_run -x` | ❌ Wave 0 |
| MEM-01 | Recall filters by `as_of_date <= query` (no look-ahead) | unit | `uv run pytest tests/memory/test_episodic_recall.py::test_recall_excludes_future_rows -x` | ❌ Wave 0 |
| MEM-01 | Recall returns ticker-matched and sector-matched hits sorted by date | unit | `uv run pytest tests/memory/test_episodic_recall.py::test_recall_ticker_or_sector_match -x` | ❌ Wave 0 |
| MEM-01 | 90-day retention sweep deletes expired rows only | unit | `uv run pytest tests/memory/test_episodic_model.py::test_purge_respects_cutoff -x` | ❌ Wave 0 |
| MEM-01 | policy_sha from Phase 6 is persisted in episodic row | integration | `uv run pytest tests/integration/test_phase7_e2e.py::test_episodic_row_carries_policy_sha -x` | ❌ Wave 0 |
| MEM-02 | Valid YAML round-trips through Pydantic `Belief` | unit | `uv run pytest tests/memory/test_belief_schema.py::test_roundtrip_valid_belief -x` | ❌ Wave 0 |
| MEM-02 | Unknown YAML key raises `ValidationError` | unit | `uv run pytest tests/memory/test_belief_schema.py::test_extra_forbid_rejects_typo -x` | ❌ Wave 0 |
| MEM-02 | ruamel.yaml preserves comments across write | unit | `uv run pytest tests/memory/test_belief_writer.py::test_comment_preserved_after_write -x` | ❌ Wave 0 |
| MEM-03 | `human_edited=true` blocks thesis + confidence overwrite | unit | `uv run pytest tests/memory/test_belief_writer.py::test_human_edited_blocks_machine_write -x` | ❌ Wave 0 |
| MEM-03 | `field_locks.{field}=true` blocks that field only | unit | `uv run pytest tests/memory/test_belief_writer.py::test_field_lock_blocks_targeted_field -x` | ❌ Wave 0 |
| MEM-03 | Writer NEVER clears `human_edited` | unit | `uv run pytest tests/memory/test_belief_writer.py::test_writer_never_clears_human_edited -x` | ❌ Wave 0 |
| MEM-03 | Next analysis after edit reads the human-edited confidence | integration | `uv run pytest tests/integration/test_phase7_e2e.py::test_next_run_respects_human_edit -x` | ❌ Wave 0 |
| MEM-04 | `compute_new_confidence` is deterministic (agreed outcome → +) | unit | `uv run pytest tests/memory/test_critique_math.py::test_agreement_raises_confidence -x` | ❌ Wave 0 |
| MEM-04 | `compute_new_confidence` disagreed outcome → lower | unit | `uv run pytest tests/memory/test_critique_math.py::test_disagreement_lowers_confidence -x` | ❌ Wave 0 |
| MEM-04 | `compute_new_confidence` neutral + big move → lower | unit | `uv run pytest tests/memory/test_critique_math.py::test_neutral_with_big_move_lowers -x` | ❌ Wave 0 |
| MEM-04 | `compute_new_confidence` clamps to [0, 100] | property | `uv run pytest tests/memory/test_critique_math.py::test_bounds_always_valid -x` | ❌ Wave 0 |
| MEM-04 | `self_critique_agent` output is `RationaleOnly` (schema-unreachable number) | unit | `uv run pytest tests/memory/test_self_critique_agent.py::test_rationale_only_schema -x` | ❌ Wave 0 |
| MEM-04 | End-to-end: outcome → critique → belief file shows new_conf + rationale + outcome | integration | `uv run pytest tests/integration/test_phase7_e2e.py::test_outcome_updates_belief -x` | ❌ Wave 0 |
| MEM-04 | Self-critique is skipped when `human_edited=true` (recorded in return value) | integration | `uv run pytest tests/integration/test_phase7_e2e.py::test_critique_skipped_for_human_edited -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/memory -q` (target <20s)
- **Per wave merge:** `uv run pytest tests/memory tests/graph tests/integration -q` (target <60s)
- **Phase gate:** Full `uv run pytest -q` green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/memory/__init__.py`, `tests/memory/conftest.py` — fixtures: `seeded_episodic`, `sample_belief_dir`, `sample_belief_human_edited`
- [ ] `tests/memory/fixtures/belief_aapl.yaml` — golden belief with comments
- [ ] `tests/memory/fixtures/belief_aapl_human_edited.yaml` — `human_edited: true` variant
- [ ] `tests/memory/fixtures/seeded_episodic.csv` — 10-row seed covering ticker + sector + outcome rows
- [ ] `tests/memory/test_episodic_model.py`, `test_episodic_recall.py`, `test_belief_schema.py`, `test_belief_writer.py`, `test_critique_math.py`, `test_self_critique_agent.py`
- [ ] `tests/graph/test_memory_nodes.py` — memory_recall_node + episodic_store_node under TestModel stubs
- [ ] `tests/integration/test_phase7_e2e.py` — full pipeline with `with_memory=True` + offline critique loop
- [ ] `alembic/versions/003_create_episodic_memory.py` — migration (consumed by fixtures)
- [ ] Add `ruamel.yaml>=0.19.0` to `pyproject.toml` dependencies

### Validation Detail — How Each Contract is Proven

- **Episodic recall (MEM-01):** Seed the table with rows at as_of_date = (D-10, D-5, D+5). Query with `as_of_date=D`. Assert result set contains D-10 and D-5 ONLY. No D+5 row ever.
- **Belief schema (MEM-02):** Round-trip via `ruamel.yaml.load(file) → Belief.model_validate(dict) → Belief.model_dump()` on a golden fixture. Assert key set + values preserved. Separate test: `Belief.model_validate({"confidance": 72, ...})` raises `ValidationError`.
- **Comment preservation (MEM-02):** Load fixture with `# flagged by Max` comment, patch `confidence`, write, re-read raw file text, assert `"# flagged by Max"` substring present.
- **Human-edit preservation (MEM-03):** Load `belief_aapl_human_edited.yaml`, invoke `write_belief(patches={"confidence": 99, "thesis": "bogus"})`, reload, assert original confidence + thesis unchanged, `applied=[]`, `skipped={"thesis": "human_edited_global_flag_set", "confidence": "human_edited_global_flag_set"}`.
- **Self-critique math (MEM-04):** Table-driven parametrize test: `[(old=50, out=+2.0, dir="long") → new > 50, (old=50, out=-2.0, dir="long") → new < 50, (old=50, out=+5.0, dir="neutral") → new < 50, (old=0, out=-10, dir="long") → new == 0]`. All pure function, no mocking.
- **End-to-end (MEM-01 + MEM-04):** Run `build_debate_pipeline(with_memory=True, with_risk=True)` under TestModel stubs against seeded fixtures → assert `episodic_memory` row appended. Then call `ingest_outcome(ticker, outcome_pct=+3)` → assert belief file reload shows `confidence` bumped and `critique_history` has one new entry with source=`self_critique`.

## Security Domain

`security_enforcement` is enabled (absent config key = enabled).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | No user-facing auth surface in Phase 7. |
| V3 Session Management | no | LangGraph session is PostgreSQL checkpointer; not user-authenticated. |
| V4 Access Control | partial | Operator-only CLI scripts (`ingest_outcome.py`, `purge_expired_episodic.py`). File-system permissions on `beliefs/` directory. |
| V5 Input Validation | yes | Ticker regex on CLI inputs; Pydantic `extra="forbid"` on belief YAML; Pydantic validation on operator-supplied outcome_pct bounds. |
| V6 Cryptography | no | No new crypto surface; `policy_sha` is already in Phase 6. |
| V8 Data Protection | yes | Belief files are plain text; if they ever contain nonpublic material (e.g., specific broker relationships), the operator places `beliefs/` on encrypted storage. |
| V10 Malicious Code | yes | YAML loader MUST use ruamel.yaml safe defaults or `yaml.safe_load` equivalent — never `yaml.load()` which can instantiate arbitrary Python. [CITED: `src/ai_hedge_fund/risk/policy.py` line 132 comment] |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via ticker-as-filename | Tampering | Ticker regex `[A-Z0-9.\-]{1,10}` before `beliefs_path / f"{ticker}.yaml"`. Enforce in `load_belief` AND in `ingest_outcome` CLI. |
| YAML deserialization RCE | Elevation of Privilege | Use `ruamel.yaml.YAML()` (safe mode by default) or PyYAML's `yaml.safe_load`. NEVER plain `yaml.load(data)`. |
| Silent belief tampering | Tampering | Every write records a `CritiqueEvent` with `source` field (`self_critique` vs `human`). Operator-visible audit trail. |
| SQL injection in recall filters | Tampering | SQLAlchemy parameterized queries only. No string-concatenated SQL anywhere. |
| Outcome poisoning (fake trade result) | Tampering | CLI-operator-only path; `ingest_outcome.py` refuses if not run from controlled env (read config-loaded operator allowlist). v2 concern — document as a known limitation for v1. |
| Unbounded LLM output cost | DoS | `RationaleOnly(max_length=2000)` + `get_self_critique_limits()` with `output_override=4000`. Dual bound matches Phase 6. |
| Context window blowup on recall | DoS | `recall_limit` on `MemoryDeps` (default 10); query `LIMIT`. |
| Belief-file race condition | Tampering | `Path.replace()` atomic rename + documented serial-per-ticker offline-only execution. |

## Assumptions Log

Every `[ASSUMED]` claim below needs planner or user confirmation before becoming a locked decision.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 90-day retention is a hard cutoff (no soft-delete window, no archive tier). | Pattern 5 | If regulators require longer retention, we need an archive table or S3 dump; adding later means migrating data out. |
| A2 | `compute_new_confidence` uses k=0.3 and linear adjustment bounded by [0, 100] with per-event cap of 10. | Pattern 6 | These are placeholder numbers. A real quant would want to calibrate against historical outcomes. Revisit after first 50 critique events. |
| A3 | One belief file per ticker is the right granularity (not per strategy, not per holding period). | Project Structure | If the same ticker has two distinct theses (long-term hold + short-term catalyst), a single file collapses them. Recommend a `thesis_id` per file and multiple files per ticker if this emerges. |
| A4 | Store VETOED decisions in episodic memory (recommended). | Pattern 7 composition note | If we exclude vetoes, we lose the richest learning signal. Planner should confirm. |
| A5 | `recall_limit=10` is the right default for `MemoryDeps`. | Pitfall 8 | Too few → poor recall; too many → token blowup. Measure at first integration test. |
| A6 | Offline serial-per-ticker execution is acceptable for self-critique (no parallel-writer protection). | Pitfall 7 | Fine for v1 operator workflow; if automated outcome ingestion happens at scale, add `filelock`. |
| A7 | `ruamel.yaml` is still maintained and the canonical choice (last release Jan 2025). | Standard Stack | Verified via `curl pypi.org` in Version verification step; planner should re-run before adding dep. |
| A8 | `pgvector` stays deferred — SQL-filter recall is sufficient for the v1 ticker universe (<200 tickers). | Alternatives Considered | If hit rate is demonstrably poor, upgrade path is documented but not scoped to this phase. |
| A9 | `beliefs/` lives at project root, tracked in git, seeded by operator/first-run, with history available via git log. | Project Structure | If operator prefers beliefs outside git (to avoid merge conflicts on machine-written fields), we move to an external path with an audit log + config-controlled `beliefs_path`. |
| A10 | Schema version 1 is the starting `payload.schema_version`; migrations live in Python (not SQL) in `src/ai_hedge_fund/memory/episodic_payload_v1_to_v2.py`. | Pitfall 6 | If Phase 8 extends the payload, plan the migrator there; not a Phase 7 concern. |
| A11 | Retention sweep is idempotent and cron-scheduled; no distributed lock needed because a single operator runs cron. | Pattern 5 | Fine in a single-host prod topology. In Kubernetes / multi-node deploys, use a CronJob with concurrencyPolicy: Forbid. |

## Open Questions

1. **Do we want to persist VETOED decisions in episodic_memory?**
   - What we know: Vetoes are the richest learning signal; the schema supports them naturally.
   - What's unclear: Whether the planner wants `episodic_store` to run after a veto (architecturally a new conditional edge from `risk_manager`).
   - Recommendation: YES — store them. Planner adds the conditional edge `risk_manager --VETOED--> episodic_store_vetoed`.

2. **Should `memory_recall_node` run for every pipeline invocation or only when the ticker has prior records?**
   - What we know: The cost is one indexed query (<1ms), so there's no reason to skip it.
   - Recommendation: Always run it. Let the node return `episodic_hits=[]` when the query is empty.

3. **Where does the operator's initial belief come from?**
   - What we know: The self-critique loop UPDATES beliefs; it doesn't CREATE them.
   - What's unclear: Do we seed `beliefs/tickers/X.yaml` from the first pipeline run automatically, or does a human write the first one?
   - Recommendation: First pipeline run auto-creates with `confidence=thesis.confidence`, `source="bootstrap"`, `human_edited=false`. Humans MAY rewrite it afterward. Document this bootstrap behavior so operators don't wonder where files came from.

4. **How does `memory_recall_node` rank hits when there are more than `recall_limit` candidates?**
   - What we know: `ORDER BY as_of_date DESC LIMIT N` is simple and deterministic.
   - What's unclear: Does the planner want a hybrid "N most recent + M largest |outcome|" ranker?
   - Recommendation: Start with pure recency. Add outcome-magnitude weighting as a follow-up if recall quality is poor.

5. **Should `ingest_outcome.py` also update sector-level and pattern-level beliefs, or only ticker-level?**
   - What we know: Sector beliefs (`beliefs/sectors/Technology.yaml`) and pattern beliefs (`beliefs/patterns/insider_cluster_alpha.yaml`) are part of the belief-memory contract (MEM-02).
   - What's unclear: Does a single trade outcome for AAPL update Technology sector confidence? If yes, how do we attribute the signal?
   - Recommendation: Ship ticker-only for v1. Sector/pattern critique is a follow-up that needs a separate attribution design. Document the gap.

## Sources

### Primary (HIGH confidence)
- `CLAUDE.md` — project conventions (append-only, immutability, tool-first, human-readable belief memory, temporal correctness)
- `.planning/phases/07-memory-and-learning/07-CONTEXT.md` — phase boundary + invariants + deferred ideas
- `.planning/phases/06-risk-management/06-CONTEXT.md` + `06-06-SUMMARY.md` — Phase 6 final state (policy_sha audit, Pattern 2)
- `src/ai_hedge_fund/graph/pipeline.py` — `build_debate_pipeline(with_risk=...)` precedent
- `src/ai_hedge_fund/graph/risk_deps.py` — frozen dataclass deps bundle precedent
- `src/ai_hedge_fund/graph/nodes.py` lines 857-997 — `risk_manager_node` + `route_after_risk` (Pattern 2 canonical example)
- `src/ai_hedge_fund/schemas/state.py` — `DebatePipelineState` TypedDict precedent
- `src/ai_hedge_fund/schemas/risk.py` — `RiskAssessment` + `Violation` schemas (policy_sha contract)
- `src/ai_hedge_fund/db/base.py` — `DualTimestampMixin` + `AppendOnlyMixin`
- `src/ai_hedge_fund/db/models.py` — `PortfolioPosition` (Phase 6) table pattern
- `src/ai_hedge_fund/risk/policy.py` — `RiskPolicy` (`extra="forbid"`, `yaml.safe_load`, SHA-256 fingerprint)
- `src/ai_hedge_fund/agents/risk_manager.py` — `RationaleOnly` schema + rationale-only system prompt
- `src/ai_hedge_fund/agents/research.py` — `ResearchDeps` frozen dataclass + `RunContext` pattern
- `src/ai_hedge_fund/data/temporal.py` — `enforce_as_of_date` decorator contract
- `src/ai_hedge_fund/models.py` — `ModelTier` + `UsageLimits` per tier
- `alembic/versions/002_create_portfolio_positions.py` — Alembic migration pattern for Phase 7 migration 003
- `tests/integration/test_phase6_e2e.py` — TestModel stubbing pattern for all 11 agents
- `tests/risk/conftest.py` + `tests/risk/fixtures/` — fixture layout precedent
- `pyproject.toml` + `uv.lock` — verified dependency versions (pydantic 2.12, pydantic-ai 1.0, langgraph 1.1, sqlalchemy 2.0, pyyaml 6.0.3)

### Secondary (MEDIUM confidence)
- [ruamel.yaml PyPI](https://pypi.org/project/ruamel.yaml/) — canonical round-trip YAML library, maintained; v0.19.0 (Jan 2025)
- [LangGraph memory overview](https://docs.langchain.com/oss/python/langgraph/memory) — Store vs Checkpointer distinction; confirms they are NOT domain memory substitutes
- [PostgreSQL JSONB vs columns performance](https://sqlpad.io/tutorial/postgresql-jsonb-vs-columns-performance-guide/) — hot-path filter columns + JSONB payload is the consensus
- [pg_partman retention guide](https://www.crunchydata.com/blog/auto-archiving-and-data-retention-management-in-postgres-with-pg_partman) — partitioning is the scale answer, premature here
- [Python YAML round-trip with comments](https://copyprogramming.com/howto/python-yaml-update-preserving-order-and-comments) — confirms PyYAML strips comments; ruamel.yaml preserves them
- [AWS blog: persistent agent memory architecture](https://aws.amazon.com/blogs/database/build-persistent-memory-for-agentic-ai-applications-with-mem0-open-source-amazon-elasticache-for-valkey-and-amazon-neptune-analytics/) — hybrid episodic/semantic memory is standard

### Tertiary (LOW confidence, flagged for validation)
- [Ruamel Yaml - Blue Book](https://lyz-code.github.io/blue-book/coding/python/ruamel_yaml/) — community notes on round-trip patterns
- [Choosing Between ruamel.yaml and PyYAML](https://www.oreateai.com/blog/choosing-between-ruamelyaml-and-pyyaml-a-comprehensive-comparison/2ca85e856751622588a46a00a9a8e664) — comparison article; corroborates primary claim

## Metadata

**Confidence breakdown:**
- Standard stack (ruamel.yaml addition, SQLAlchemy reuse): HIGH — direct precedent + PyPI verification
- Schema design (episodic table, belief YAML): HIGH — mirrors Phase 6's `RiskPolicy` + `PortfolioPosition` patterns exactly
- Pipeline integration (`with_memory` switch): HIGH — mirrors Phase 6's `with_risk` pattern verbatim
- Pattern 2 for self-critique: HIGH — direct translation of Phase 6's `risk_manager_agent` + `risk_manager_node` contract
- Confidence-update math: MEDIUM — k=0.3, linear, bounded; placeholder numbers, needs calibration after 50 events
- 90-day retention cadence (cron vs in-process): LOW — cron is simple but needs operator buy-in; documented as open question
- pgvector deferral: HIGH — explicitly called out in CONTEXT.md `<deferred>`

**Research date:** 2026-04-22
**Valid until:** 2026-05-22 (30 days — stable Python/SQLAlchemy ecosystem; LangGraph and PydanticAI versions pinned in pyproject.toml)
