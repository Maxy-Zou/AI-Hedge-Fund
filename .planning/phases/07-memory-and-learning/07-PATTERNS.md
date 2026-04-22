# Phase 7: Memory and Learning - Pattern Map

**Mapped:** 2026-04-22
**Files analyzed:** 14 new/modified files
**Analogs found:** 14/14 (every new file has a direct Phase 1-6 precedent)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/ai_hedge_fund/memory/episodic.py` | model + query helper | CRUD + temporal filter | `src/ai_hedge_fund/risk/portfolio.py` (`PortfolioSnapshot` + `load_portfolio` + `seed_portfolio_from_csv`) + `src/ai_hedge_fund/db/models.py::PortfolioPosition` | exact |
| `src/ai_hedge_fund/memory/beliefs.py` | file-I/O service + human-edit guard | file-I/O + validation | `src/ai_hedge_fund/risk/policy.py` (YAML safe_load + Pydantic validate + writer contract) | role-match (extended with write path) |
| `src/ai_hedge_fund/memory/critique.py` | deterministic math utility | transform | `src/ai_hedge_fund/risk/sizing.py::derive_candidate_size_pct` (pure function, Literal input, bounded output) | exact |
| `src/ai_hedge_fund/memory/recall.py` | repository helper | CRUD + temporal filter | `src/ai_hedge_fund/risk/portfolio.py::load_portfolio` (SQL WHERE + as_of_date filter + limit) | exact |
| `src/ai_hedge_fund/schemas/memory.py` | Pydantic schema | validation | `src/ai_hedge_fund/risk/policy.py::RiskPolicy` + `src/ai_hedge_fund/schemas/risk.py::RiskAssessment` | exact |
| `src/ai_hedge_fund/agents/self_critique.py` | PydanticAI agent | request-response | `src/ai_hedge_fund/agents/risk_manager.py` (`RationaleOnly` + `REASONING` tier + `retries=2`) | exact |
| `src/ai_hedge_fund/db/models.py` (ADD `EpisodicMemory`) | SQLAlchemy model | CRUD | existing `PortfolioPosition` in same file (DualTimestampMixin + Index + JSONB) | exact |
| `src/ai_hedge_fund/graph/memory_deps.py` | frozen deps container | dependency injection | `src/ai_hedge_fund/graph/risk_deps.py` (`@dataclass(frozen=True)` with `db_session` + typing-guard imports) | exact |
| `src/ai_hedge_fund/graph/nodes.py` (ADD `memory_recall_node`, `episodic_store_node`, `self_critique_node`) | LangGraph node | event-driven | existing `risk_manager_node` in same file (async + deps + short-circuit on error + structlog) | exact |
| `src/ai_hedge_fund/graph/pipeline.py` (extend `build_debate_pipeline`) | graph builder | pipeline config | `build_debate_pipeline(with_risk=...)` in same file (kwarg + ValueError guard + closure bind) | exact |
| `src/ai_hedge_fund/schemas/state.py` (ADD keys) | TypedDict extension | state | `CandidateMetadata` + existing `DebatePipelineState` fields in same file | exact |
| `scripts/ingest_outcome.py` | CLI orchestrator | batch + request-response | (no precedent) - first CLI script in repo; derive structure from `src/ai_hedge_fund/risk/portfolio.py::seed_portfolio_from_csv` body shape | role-match |
| `alembic/versions/003_create_episodic_memory.py` | migration | schema | `alembic/versions/002_create_portfolio_positions.py` (revision chain + `op.create_table` + downgrade) | exact |
| `tests/memory/` + `tests/integration/test_phase7_e2e.py` | tests | — | `tests/risk/` + `tests/risk/conftest.py` + `tests/integration/test_phase6_e2e.py` + `tests/graph/test_risk_node.py` | exact |

## Pattern Assignments

### `src/ai_hedge_fund/db/models.py` — ADD `EpisodicMemory` (SQLAlchemy append-only model)

**Analog:** `src/ai_hedge_fund/db/models.py::PortfolioPosition` (lines 169-191, same file)

**Imports pattern** (from same file, lines 9-23):
```python
from sqlalchemy import (
    BigInteger, Date, DateTime, Float, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from ai_hedge_fund.db.base import Base, DualTimestampMixin
```
For Phase 7, **add** `Index` and `from sqlalchemy.dialects.postgresql import JSONB` (research §Pattern 1).

**Table pattern to copy** (lines 169-191):
```python
class PortfolioPosition(Base, DualTimestampMixin):
    """Paper-portfolio position snapshot for risk checks (Phase 6 RISK-03)."""

    __tablename__ = "portfolio_positions"
    __table_args__ = (
        UniqueConstraint("ticker", "as_of_date", name="uq_portfolio_positions_ticker_asof"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    sector: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ...
```

**Rules carried forward for `EpisodicMemory`:**
- Inherit `Base, DualTimestampMixin` so `as_of_date` + `observed_date` are automatic.
- Keep `id: int` primary key (not UUID — matches every other model).
- Hot-path filter columns (`ticker`, `sector`, `as_of_date`, `policy_sha`, `record_type`) as real columns; variable thesis payload in a JSONB column.
- Use `Index("ix_episodic_ticker_asof", "ticker", "as_of_date")` composite indexes (NOT `UniqueConstraint` — episodic records are append-only and duplicates are possible by design: multiple analyses of same ticker on same day are allowed).

---

### `src/ai_hedge_fund/memory/episodic.py` — NEW (SQLAlchemy model helpers + seed)

**Analog:** `src/ai_hedge_fund/risk/portfolio.py` (entire file, 177 lines)

**Imports + module docstring pattern** (lines 1-32):
```python
"""Portfolio state loading for the Phase 6 risk manager.

Provides the immutable :class:`PortfolioSnapshot` Pydantic model and two
pure-query helpers over the append-only ``portfolio_positions`` table:
- :func:`load_portfolio` filters rows by ``as_of_date <= target`` ...
"""
from __future__ import annotations

import csv
from datetime import UTC, date, datetime
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import PortfolioPosition
```

**Temporal-correct query pattern to copy** (lines 104-141, `load_portfolio`):
```python
def load_portfolio(db_session: Session, as_of_date: str | date | datetime) -> PortfolioSnapshot:
    """Load the portfolio snapshot visible *as of* ``as_of_date``."""
    target = _normalise_as_of(as_of_date)
    rows = (
        db_session.query(PortfolioPosition)
        .filter(PortfolioPosition.as_of_date <= target)
        .order_by(PortfolioPosition.as_of_date.desc())
        .all()
    )
    latest: dict[str, PortfolioPosition] = {}
    for row in rows:
        if row.ticker not in latest:
            latest[row.ticker] = row
    ...
```
**Required carry-over:** `_normalise_as_of` helper (lines 90-101) — converts `str | date | datetime` to UTC datetime. Phase 7 `query_episodic` MUST apply the same `as_of_date <= target` WHERE clause (Pitfall 2 temporal leakage).

**CSV seed pattern** (lines 144-177, `seed_portfolio_from_csv`): copy verbatim for `seed_episodic_from_csv` — DictReader + add_all + commit + return rowcount. Used by tests.

---

### `src/ai_hedge_fund/memory/critique.py` — NEW (deterministic confidence update)

**Analog:** `src/ai_hedge_fund/risk/sizing.py::derive_candidate_size_pct` (lines 29-53)

**Pure function pattern to copy** (lines 29-53):
```python
from __future__ import annotations
from typing import Literal
from ai_hedge_fund.risk.policy import RiskPolicy

Conviction = Literal["low", "medium", "high"]

def derive_candidate_size_pct(conviction: Conviction, policy: RiskPolicy) -> float:
    """Return the candidate position size percent for a conviction level.
    ...
    Raises:
        ValueError: If ``conviction`` is not one of the three expected literals.
    """
    if conviction == "high":
        return policy.max_single_position_pct * policy.size_high_conviction_multiplier
    if conviction == "medium":
        return policy.max_single_position_pct * policy.size_medium_conviction_multiplier
    if conviction == "low":
        return policy.max_single_position_pct * policy.size_low_conviction_multiplier
    raise ValueError(f"Unknown conviction {conviction!r}; expected one of 'low', 'medium', 'high'")
```

**Rules carried forward for `compute_new_confidence`:**
- Pure function, no I/O, no DB, no LLM.
- `Literal` input type for signal_direction (`"long" | "short" | "neutral"`).
- `from __future__ import annotations`.
- Full docstring with Args/Returns/Raises.
- Explicit `raise ValueError` on unknown inputs — never default silently.
- Return an `int` clamped to `[0, 100]`; follow research §Pattern 6 algorithm verbatim.

---

### `src/ai_hedge_fund/memory/beliefs.py` — NEW (ruamel.yaml round-trip + human-edit guard)

**Analog (read side):** `src/ai_hedge_fund/risk/policy.py::load_policy` (lines 129-148)
**Analog (writer contract):** `src/ai_hedge_fund/risk/policy.py::compute_policy_sha` (lines 151-170) and `src/ai_hedge_fund/graph/nodes.py::risk_manager_node` lines 954-966 (deterministic overwrite pattern).

**Loader pattern** (lines 129-148 of policy.py):
```python
def load_policy(path: Path | str = DEFAULT_POLICY_PATH) -> RiskPolicy:
    """Load and validate a ``RiskPolicy`` from a YAML file.

    Uses ``yaml.safe_load`` exclusively (T-06-01)...
    """
    text = Path(path).read_text()
    data = yaml.safe_load(text)
    return RiskPolicy.model_validate(data)
```

**Key differences in Phase 7 `load_belief`:**
- Swap `yaml.safe_load` for `ruamel.yaml.YAML().load(path)` (round-trip default preserves comments).
- Return BOTH `(Belief, raw)` — validated Pydantic object AND the round-trip raw object (needed for write).
- `Belief.model_validate(raw)` — same `extra="forbid"` contract as `RiskPolicy`.

**Writer contract pattern from `risk_manager_node` (Pitfall 1, deterministic overwrite):**
```python
# DETERMINISTIC OVERWRITE -- LLM status value is DISCARDED. The agent's
# RationaleOnly schema has no status field, so this is belt-and-braces:
# even if the agent were replaced with a wider schema, the node's
# Python-authored ``status`` is what ships.
assessment = RiskAssessment(
    ticker=candidate_ticker,
    status=status,  # <-- Python-authored, not LLM-authored
    ...
)
```
Phase 7 `write_belief` mirrors this contract: **machine NEVER overwrites `human_edited` or `field_locks`**. Every skip is recorded in the return dict and logged. Full function skeleton in research §Pattern 4.

**Atomic write idiom** (NEW for Phase 7, no precedent in Phase 1-6):
```python
tmp = path.with_suffix(path.suffix + ".tmp")
with tmp.open("w") as f:
    yaml.dump(raw, f)
tmp.replace(path)   # atomic rename on POSIX
```

**Security — YAML safety** (from policy.py docstring T-06-01 note, lines 9-14):
Use `ruamel.yaml.YAML()` which is safe by default; NEVER use `yaml.load(data)` (arbitrary Python instantiation).

---

### `src/ai_hedge_fund/schemas/memory.py` — NEW (Pydantic schemas)

**Analog:** `src/ai_hedge_fund/risk/policy.py::RiskPolicy` (lines 32-126) + `src/ai_hedge_fund/schemas/risk.py::Violation` (lines 49-72, frozen pattern)

**`extra="forbid"` + `frozen=True` pattern** (policy.py lines 41-44):
```python
class RiskPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_single_position_pct: float = Field(
        ge=0.0, le=100.0,
        description="Hard cap on any one position as percent of portfolio",
    )
```

**Rules carried forward for `Belief`:**
- `ConfigDict(extra="forbid")` — unknown YAML keys (e.g., typo `confidance: 72`) raise `ValidationError`. Research §Pitfall 4.
- `CritiqueEvent` is `frozen=True` (immutable per-event record, like `Violation`).
- `Belief` is NOT frozen — writer produces new instance on every update.
- Bounded string lengths (`max_length=2000` on rationale, `max_length=10_000` on thesis) to prevent DoS.

---

### `src/ai_hedge_fund/agents/self_critique.py` — NEW (PydanticAI rationale-only agent)

**Analog:** `src/ai_hedge_fund/agents/risk_manager.py` (entire file, 148 lines)

**Agent declaration pattern** (lines 93-98):
```python
risk_manager_agent: Agent[None, RationaleOnly] = Agent(
    ModelTier.REASONING.value,
    output_type=RationaleOnly,
    system_prompt=RISK_MANAGER_SYSTEM_PROMPT,
    retries=2,
)
```

**`RationaleOnly` schema pattern** (lines 42-61):
```python
class RationaleOnly(BaseModel):
    """The agent's only job: produce a rationale string. Nothing else."""

    rationale: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "One-paragraph human-readable explanation of the risk "
            "assessment. ... Advisory only -- does not affect the "
            "APPROVED/VETOED outcome."
        ),
    )
```

**UsageLimits dual-bound pattern** (lines 101-109):
```python
def get_risk_manager_limits() -> UsageLimits:
    """Return REASONING-tier limits with output capped at 4,000 tokens."""
    return get_usage_limits(ModelTier.REASONING, output_override=4_000)
```

**Context formatter pattern** (lines 112-147 — `format_risk_context_for_rationale`):
Deterministic 5-section prompt string (`THESIS`, `DETERMINISTIC STATUS`, `VIOLATION`, `PORTFOLIO`, `POLICY` separated by `\n\n---\n\n`). Phase 7 `format_critique_context` should mirror: `BELIEF`, `OUTCOME`, `OLD_CONFIDENCE`, `NEW_CONFIDENCE (DETERMINISTIC)`, `LINKED_ANALYSIS`.

**System-prompt rules — carry over the "STRICT RULES" block** (lines 64-90). Critical verbs: "EXPLAIN" (never "decide"/"judge") — enforced by the T-06-02b forbidden-verb test; Phase 7 must keep same invariant.

---

### `src/ai_hedge_fund/graph/memory_deps.py` — NEW (frozen deps bundle)

**Analog:** `src/ai_hedge_fund/graph/risk_deps.py` (entire file, 54 lines)

**Full file pattern to mirror:**
```python
"""Runtime dependencies for the Phase-7 memory nodes.

:class:`MemoryDeps` bundles the objects the memory nodes need: the
SQLAlchemy :class:`Session` used by episodic queries and the filesystem
path to the belief documents directory. The deps container is frozen
(immutable) and is bound to the node at ``build_debate_pipeline`` time.

Mirrors the ``RiskDeps`` pattern ...
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing-only
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class MemoryDeps:
    """Immutable dependency bundle for memory_recall_node + episodic_store_node.

    Attributes:
        db_session: Open SQLAlchemy session for episodic queries/writes.
        beliefs_path: Root directory containing belief YAML files.
        recall_limit: Max episodic_memory rows to load per recall (default 10).
    """
    db_session: Session
    beliefs_path: Path
    recall_limit: int = 10
```

**Rules carried forward:**
- `@dataclass(frozen=True)` — immutable bundle.
- `from __future__ import annotations` so forward refs work without circular imports.
- `TYPE_CHECKING` guard on heavy imports (SQLAlchemy Session).
- Explicit `recall_limit` default (Pitfall 8 — bound the return set).

---

### `src/ai_hedge_fund/graph/nodes.py` — ADD `memory_recall_node`, `episodic_store_node`, `self_critique_node`

**Analog:** `risk_manager_node` (lines 857-982) + `route_after_risk` (lines 985-997) in the SAME file.

**Node signature + short-circuit pattern** (lines 857-898):
```python
async def risk_manager_node(state: DebatePipelineState, deps: RiskDeps) -> dict:
    """Phase-6 Risk Manager node -- deterministic checks + advisory rationale.
    ...
    """
    if state.get("error"):
        return {}
    thesis = state.get("thesis")
    if thesis is None:
        logger.error("risk_no_thesis", ticker=state.get("ticker"))
        return {"error": "No thesis available for risk check"}
    ...
```

**LLM invocation + budget-error handling** (lines 943-952):
```python
try:
    limits = get_risk_manager_limits()
    result = await risk_manager_agent.run(prompt, usage_limits=limits)
except UsageLimitExceeded as e:
    logger.error(
        "risk_manager_budget_exceeded",
        ticker=state["ticker"],
        error=str(e),
    )
    return {"error": f"Risk manager budget exceeded: {e}"}
```

**structlog event + usage logging** (lines 968-981):
```python
usage = result.usage()
event_name = "risk_manager_complete" if status == "APPROVED" else "risk_manager_veto"
logger.info(
    event_name,
    ticker=state["ticker"],
    status=status,
    ...
    input_tokens=usage.input_tokens,
    output_tokens=usage.output_tokens,
    total_tokens=usage.total_tokens,
)
return {"risk_assessment": assessment.model_dump()}
```

**Rules carried forward for ALL new memory nodes:**
- `async def ..._node(state, deps)` signature.
- First line: `if state.get("error"): return {}` — short-circuits on upstream error.
- Never mutate `state`; return a NEW `dict` (immutable pattern T-03-03).
- Use `logger = structlog.get_logger(__name__)` at module scope (line 111).
- Log structured event `{node}_complete` on success, `{node}_error`/`{node}_budget_exceeded` on failure.
- For `memory_recall_node`: mirror the temporal-filter idiom from `load_portfolio` — `.filter(EpisodicMemory.as_of_date <= target)` is NOT optional (Pitfall 2).
- For `episodic_store_node`: write `deps.db_session.add(row); deps.db_session.commit()` and return `{"episodic_stored_id": row.id}`.
- `self_critique_node` runs OFFLINE (triggered by `ingest_outcome.py`), NOT in the live graph — include that as a docstring warning.

---

### `src/ai_hedge_fund/graph/pipeline.py` — EXTEND `build_debate_pipeline` with `with_memory=...`

**Analog:** `build_debate_pipeline(with_risk=..., risk_deps=...)` in the SAME file (lines 183-307).

**Signature + guard pattern** (lines 183-243):
```python
def build_debate_pipeline(
    checkpointer: BaseCheckpointSaver | None = None,
    *,
    with_risk: bool = False,
    risk_deps: RiskDeps | None = None,
) -> CompiledStateGraph:
    """Build the Phase-5 adversarial-debate pipeline (+ Phase-6 risk gate).
    ...
    """
    if with_risk and risk_deps is None:
        raise ValueError(
            "build_debate_pipeline(with_risk=True) requires risk_deps -- "
            "supply a RiskDeps instance with db_session and returns."
        )
```

**Closure-binding pattern for deps** (lines 265-270):
```python
if with_risk:
    assert risk_deps is not None  # for the type checker; enforced above

    async def _risk_manager_bound(state: DebatePipelineState) -> dict:
        return await risk_manager_node(state, risk_deps)

    builder.add_node("risk_manager", _risk_manager_bound)
```

**Conditional edge + backcompat branch** (lines 291-303):
```python
if with_risk:
    builder.add_edge("debate_synthesis", "risk_manager")
    builder.add_conditional_edges(
        "risk_manager",
        route_after_risk,
        {"signal": "signal", "__end__": END},
    )
else:
    # Phase-5 backcompat: debate_synthesis -> signal (no risk gate).
    builder.add_edge("debate_synthesis", "signal")
```

**Rules carried forward for Phase 7 `with_memory` switch:**
- Add keyword-only args `with_memory: bool = False, memory_deps: MemoryDeps | None = None`.
- Identical ValueError guard when `with_memory=True and memory_deps is None`.
- Closure-bind `_memory_recall_bound`, `_episodic_store_bound` with `deps` closed over.
- Compose with `with_risk`: when both True, topology becomes `START -> memory_recall -> [3 analysts] -> ... -> risk_manager -[cond]-> {signal -> episodic_store -> END | episodic_store_vetoed -> END}` (research §Pattern 7 "composition" note; confirm planner decision per Open Question 1).
- Keep **byte-for-byte backcompat** when `with_memory=False` — the Phase-5 and Phase-6 tests must stay green.

---

### `src/ai_hedge_fund/schemas/state.py` — ADD `episodic_hits`, `beliefs_consulted`

**Analog:** Existing `DebatePipelineState` + `CandidateMetadata` (same file, lines 38-205).

**TypedDict extension pattern** (lines 154-205) — add new optional keys:
```python
class DebatePipelineState(TypedDict, total=False):
    """..."""
    ticker: Required[str]
    as_of_date: Required[str]
    analyst_reports: Annotated[list[dict], operator.add]
    thesis: dict | None
    # ... existing Phase 5/6 fields ...
    risk_assessment: dict | None
    candidate_metadata: dict | None
    # --- Phase 7 additions ---
    episodic_hits: list[dict] | None
    beliefs_consulted: list[dict] | None
    episodic_stored_id: int | None   # returned by episodic_store_node for audit
    error: str | None
```

**Rules carried forward:**
- `total=False` preserved — new fields are optional.
- Each new field has a full docstring block explaining its writer and shape (see existing fields lines 179-189).
- NO `operator.add` reducer on memory keys — they are single-writer (written once by `memory_recall_node`).

---

### `scripts/ingest_outcome.py` — NEW CLI

**Analog (body shape):** `src/ai_hedge_fund/risk/portfolio.py::seed_portfolio_from_csv` (lines 144-177) — DB INSERT orchestration shape.
**Analog (CLI entry):** No existing CLI in repo; use `if __name__ == "__main__": asyncio.run(main())` idiom and `argparse` stdlib (no new deps).

**Function skeleton from research §"Offline Outcome Ingest + Self-Critique"** (lines 812-869 of 07-RESEARCH.md):
```python
async def ingest_outcome(
    session, beliefs_dir: Path, ticker: str, outcome_pct: float, as_of_date: date
) -> None:
    # 1. Append the outcome row (append-only)
    ...
    # 2. Run self-critique
    belief_path = beliefs_dir / "tickers" / f"{ticker}.yaml"
    belief, raw = load_belief(belief_path)
    new_conf = compute_new_confidence(...)
    result = await self_critique_agent.run(prompt, usage_limits=get_self_critique_limits())
    # 3. Write -- writer enforces human-edit guard
    outcome = write_belief(belief_path, raw, patches={...})
    logger.info("self_critique_applied", ticker=ticker, **outcome)
```

**Security pattern (ticker validation — Pitfall 9):**
```python
import re
if not re.fullmatch(r"[A-Z0-9.\-]{1,10}", ticker):
    raise ValueError(f"Invalid ticker {ticker!r}")
```

**Rules carried forward:**
- All DB writes go through the same `db_session.add(row); db_session.commit()` pattern (matches `seed_portfolio_from_csv`).
- No direct `yaml.dump` — must go through `write_belief` so human-edit guard cannot be bypassed.

---

### `alembic/versions/003_create_episodic_memory.py` — NEW migration

**Analog:** `alembic/versions/002_create_portfolio_positions.py` (entire file, 57 lines)

**Full file structure to mirror** (lines 1-57):
```python
"""Create <table> table.

Revision ID: 003
Revises: 002
Create Date: 2026-04-22
...
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "episodic_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        # ... columns from EpisodicMemory SQLAlchemy model ...
        sa.Column("as_of_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_date", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_episodic_ticker_asof", "episodic_memory", ["ticker", "as_of_date"])
    op.create_index("ix_episodic_sector_asof", "episodic_memory", ["sector", "as_of_date"])


def downgrade() -> None:
    op.drop_table("episodic_memory")
```

**Rules carried forward:**
- Revision chain: `revision = "003"`, `down_revision = "002"`.
- Include both `upgrade()` AND `downgrade()` — Phase 1/6 precedent.
- Use `sa.dialects.postgresql.JSONB` for the payload column (NOT generic `sa.JSON` — we need GIN-index-capable type; the model uses PG JSONB).
- Index creation is inside `upgrade()` via `op.create_index` (not inside `create_table` — follows 001-migration style for indexed columns).

---

### `tests/memory/` and `tests/integration/test_phase7_e2e.py`

**Analogs:**
- Directory layout: `tests/risk/` + `tests/risk/fixtures/` + `tests/risk/conftest.py`
- Unit test for a LangGraph node: `tests/graph/test_risk_node.py`
- Integration test for the full pipeline: `tests/integration/test_phase6_e2e.py`
- Integration test for audit/trail: `tests/integration/test_policy_sha_audit.py`

**Fixture conftest pattern** (from `tests/risk/conftest.py`, lines 1-46):
```python
from pathlib import Path
import pytest
from ai_hedge_fund.risk.policy import RiskPolicy, load_policy

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def sample_policy_path() -> Path:
    return FIXTURES_DIR / "risk_policy_sample.yaml"


@pytest.fixture()
def sample_policy(sample_policy_path: Path) -> RiskPolicy:
    return load_policy(sample_policy_path)
```

**CSV fixture format** (from `tests/risk/fixtures/portfolio_sample.csv`):
```csv
ticker,sector,quantity,cost_basis_cents,current_value_cents,instrument_type
AAPL,Technology,50,800000,900000,equity
```
Phase 7 `seeded_episodic.csv` schema: `ticker,sector,record_type,as_of_date,signal_direction,confidence,outcome_pct,policy_sha`.

**TestModel stubbing pattern** (from `tests/graph/test_risk_node.py` lines 109-112):
```python
STUB_RATIONALE = "stubbed rationale"

with risk_manager_agent.override(
    model=TestModel(custom_output_args={"rationale": STUB_RATIONALE})
):
    result = _run_node(state, risk_deps)
```

**Async node runner helper** (lines 70-71):
```python
def _run_node(state: DebatePipelineState, deps: RiskDeps) -> dict:
    return asyncio.run(risk_manager_node(state, deps))
```

**Integration e2e fixture pattern** (from `tests/integration/test_phase6_e2e.py` lines 55-69):
```python
@pytest.fixture()
def seeded_session(db_session: Session) -> Session:
    """Seed the sample portfolio with as_of_date 2026-03-01."""
    seed_portfolio_from_csv(db_session, FIXTURES_DIR / "portfolio_sample.csv", "2026-03-01")
    db_session.commit()
    return db_session
```

**Env-var-first pattern for stubbed LLM tests** (line 25):
```python
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")
```
Must come BEFORE any `pydantic_ai` import (or the import triggers a config error).

**Project-wide `db_session` fixture** (from `tests/conftest.py` lines 35-49): in-memory SQLite + `Base.metadata.create_all`. Phase 7 tests inherit this automatically — no new DB plumbing needed.

---

## Shared Patterns

### Shared Pattern A — Temporal-Correct Database Queries (MANDATORY)

**Source:** `src/ai_hedge_fund/risk/portfolio.py::load_portfolio` lines 104-118
**Apply to:** `memory_recall_node`, `episodic.py::query_episodic`, `ingest_outcome.py::get_prior_analysis`
```python
rows = (
    db_session.query(EpisodicMemory)  # or SQLAlchemy 2.0 style select()
    .filter(EpisodicMemory.as_of_date <= target)   # <-- THE CONTRACT
    .order_by(EpisodicMemory.as_of_date.desc())
    .limit(deps.recall_limit)
    .all()
)
```
Pitfall 2 regression test (`test_recall_no_lookahead`) seeds a future-dated row and asserts it is NEVER returned.

### Shared Pattern B — Pydantic Schema (`extra="forbid"` + optional `frozen=True`)

**Source:** `src/ai_hedge_fund/risk/policy.py::RiskPolicy` line 41 + `src/ai_hedge_fund/schemas/risk.py::Violation` line 62
**Apply to:** `schemas/memory.py::Belief`, `CritiqueEvent`, any new Pydantic type
```python
class Belief(BaseModel):
    model_config = ConfigDict(extra="forbid")   # NOT frozen — writer replaces it
    ...

class CritiqueEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)   # frozen — events immutable
    ...
```
Rejects YAML typos (Pitfall 4).

### Shared Pattern C — Node Short-Circuit on Upstream Error

**Source:** `src/ai_hedge_fund/graph/nodes.py::risk_manager_node` lines 893-894
**Apply to:** ALL new LangGraph nodes (`memory_recall_node`, `episodic_store_node`, `self_critique_node`)
```python
if state.get("error"):
    return {}
```
Research Anti-Pattern: never forward a broken state silently.

### Shared Pattern D — Frozen Deps Bundle Pattern

**Source:** `src/ai_hedge_fund/graph/risk_deps.py` (entire file)
**Apply to:** `graph/memory_deps.py`
```python
@dataclass(frozen=True)
class MemoryDeps:
    db_session: Session
    beliefs_path: Path
    recall_limit: int = 10
```
Immutability + TYPE_CHECKING import guard carried forward.

### Shared Pattern E — Pattern 2: Deterministic Python + LLM Rationale

**Source:** `risk_manager_node` lines 925-966 (deterministic checks FIRST, LLM rationale SECOND, Python-authored result OVERWRITES any LLM attempt)
**Apply to:** `self_critique_node` + `ingest_outcome.py`
```python
# 1. Python computes the number (compute_new_confidence)
new_conf = compute_new_confidence(old_conf, outcome_pct, signal_direction)
# 2. LLM writes rationale only (RationaleOnly schema)
result = await self_critique_agent.run(prompt, usage_limits=get_self_critique_limits())
# 3. Python-authored CritiqueEvent stamps the number — LLM cannot alter it
event = CritiqueEvent(
    ..., old_confidence=old_conf, new_confidence=new_conf,
    rationale=result.output.rationale,
)
```

### Shared Pattern F — Dual-Bound DoS Protection on LLM Output

**Source:** `src/ai_hedge_fund/agents/risk_manager.py::RationaleOnly.rationale` lines 51-52 (`max_length=2000`) + `get_risk_manager_limits` (`output_override=4_000`) lines 101-109
**Apply to:** `self_critique_agent.RationaleOnly.rationale` + `get_self_critique_limits`
Two independent bounds: Pydantic `max_length` AND PydanticAI `output_tokens_limit`. Defense-in-depth.

### Shared Pattern G — structlog Binding + Usage Logging

**Source:** `src/ai_hedge_fund/graph/nodes.py` line 111 (`logger = structlog.get_logger(__name__)`) + any node's `logger.info(event_name, ticker=..., input_tokens=..., ...)`
**Apply to:** every new node and script. Use lowercase_snake event names (e.g., `memory_recall_complete`, `self_critique_applied`, `belief_write_skipped`). NEVER use Python f-strings inside structlog — pass keyword args.

### Shared Pattern H — YAML Safe Loading

**Source:** `src/ai_hedge_fund/risk/policy.py::load_policy` lines 132 + T-06-01 comment (lines 9-14)
**Apply to:** `beliefs.py::load_belief`. Use `ruamel.yaml.YAML()` (safe default) or `yaml.safe_load`. **NEVER** plain `yaml.load(data)` (arbitrary Python instantiation = RCE).

---

## No Analog Found

All 14 files have a direct Phase 1-6 analog. Only minor novelties:

| File | Novelty | Resolution |
|------|---------|------------|
| `scripts/ingest_outcome.py` | First CLI script in repo; no other operator-facing CLI exists | Use stdlib `argparse` + `asyncio.run(main())`; body shape follows `seed_portfolio_from_csv`. No new deps. |
| `beliefs/tickers/*.yaml` root-level directory | First top-level human-editable content dir | Mirrors the `config/risk_policy.yaml` placement — checked into git, human-editable. Planner decides whether `beliefs/` is at repo root or inside `config/`. |
| `ruamel.yaml` dependency | First non-PyYAML YAML lib | Documented in 07-RESEARCH.md §"Standard Stack". Must `uv add ruamel.yaml>=0.19.0`. PyYAML stays for read-only risk policy. |
| `purge_expired_episodic.py` cron script | First cron-invoked script | Ship the Python; planner decides whether to add a Makefile target or defer to operator runbook (Open Question from 07-RESEARCH.md Environment Availability). |

---

## Metadata

**Analog search scope:**
- `src/ai_hedge_fund/risk/` (Phase 6 deterministic-first modules — top reference)
- `src/ai_hedge_fund/graph/` (LangGraph nodes + pipeline + deps containers)
- `src/ai_hedge_fund/agents/risk_manager.py` + `research.py` (PydanticAI agent patterns)
- `src/ai_hedge_fund/db/` (SQLAlchemy models + session factory + DualTimestampMixin)
- `src/ai_hedge_fund/schemas/` (TypedDict state + Pydantic schemas)
- `alembic/versions/` (migration style)
- `tests/risk/` + `tests/graph/` + `tests/integration/` (test and fixture layout)

**Files scanned:** ~25 source files + 2 migrations + 5 test files directly excerpted.

**Pattern extraction date:** 2026-04-22
