# Phase 8: Signal and Output - Pattern Map

**Mapped:** 2026-04-22
**Files analyzed:** 15 new/modified files
**Analogs found:** 15 / 15 (all high-quality direct analogs from Phase 6/7)

## Summary

Phase 8 is 100% composition of Phase 6/7 patterns plus one new LangGraph primitive (`interrupt()`). Every new file has a direct byte-for-byte analog in the codebase — the new subpackages `src/ai_hedge_fund/review/` and `src/ai_hedge_fund/output/` mirror `src/ai_hedge_fund/risk/` + `src/ai_hedge_fund/memory/`; the two new nodes mirror `risk_manager_node` + `episodic_store_node`; the new CLIs mirror `ingest_outcome.py` + `purge_expired_episodic.py`; the new tests mirror `test_phase7_e2e.py` + `test_pipeline_with_memory.py`. The only genuinely-new primitive is `langgraph.types.interrupt()`, which is documented in 08-RESEARCH.md §Pattern 1.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/ai_hedge_fund/output/__init__.py` | package | n/a | `src/ai_hedge_fund/risk/__init__.py` | exact |
| `src/ai_hedge_fund/review/__init__.py` | package | n/a | `src/ai_hedge_fund/risk/__init__.py` | exact |
| `src/ai_hedge_fund/review/policy.py` | config-loader | file-I/O + transform | `src/ai_hedge_fund/risk/policy.py` | exact (byte-for-byte mirror) |
| `src/ai_hedge_fund/review/decision.py` | schema | transform | `src/ai_hedge_fund/schemas/risk.py::RiskAssessment` | exact |
| `src/ai_hedge_fund/schemas/signal_output.py` | schema | transform | `src/ai_hedge_fund/schemas/risk.py::RiskAssessment` | exact |
| `src/ai_hedge_fund/output/signal.py` | assembler | transform (pure Python) | `src/ai_hedge_fund/graph/nodes.py::_conviction_from_confidence` + risk derivation helpers | role-match |
| `src/ai_hedge_fund/output/portfolio_view.py` | query | CRUD (read) | `src/ai_hedge_fund/memory/recall.py::query_episodic` | exact (read-path sibling) |
| `src/ai_hedge_fund/output/formatter.py` | utility | transform | (no direct analog — new concern) | no analog |
| `src/ai_hedge_fund/graph/review_deps.py` | deps-container | n/a | `src/ai_hedge_fund/graph/memory_deps.py` | exact (byte-for-byte mirror) |
| `src/ai_hedge_fund/graph/nodes.py` (add `output_node`) | node | transform | `debate_synthesis_node` (deterministic overwrite pattern) | role-match |
| `src/ai_hedge_fund/graph/nodes.py` (add `human_review_node`) | node | event-driven (interrupt) | `risk_manager_node` (structure) + NEW primitive `interrupt()` | role-match |
| `src/ai_hedge_fund/graph/nodes.py` (add `review_store_node`) | node | CRUD (write, append-only) | `episodic_store_node` | exact |
| `src/ai_hedge_fund/graph/nodes.py` (add `route_before_review`) | router | event-driven | `route_after_risk` | exact |
| `src/ai_hedge_fund/graph/pipeline.py` (modify) | config/builder | request-response | `build_debate_pipeline` (self — extend with new kwargs) | exact (same function) |
| `src/ai_hedge_fund/schemas/state.py` (modify) | schema | transform | `DebatePipelineState` (self — add keys) | exact |
| `src/ai_hedge_fund/scripts/run_analysis.py` | CLI | request-response | `src/ai_hedge_fund/scripts/ingest_outcome.py` | exact (CLI shape) |
| `src/ai_hedge_fund/scripts/audit_reconstruct.py` | CLI | CRUD (read) | `src/ai_hedge_fund/scripts/ingest_outcome.py` + `purge_expired_episodic.py` | exact (CLI shape) |
| `config/review_policy.yaml` | config | n/a | `tests/risk/fixtures/risk_policy_sample.yaml` + `config/risk_policy.yaml` | exact |
| `tests/review/test_review_policy.py` | test | n/a | `tests/risk/test_policy_schema.py` | exact |
| `tests/output/test_final_signal.py` | test | n/a | `tests/risk/test_risk_assessment_schema.py` | exact |
| `tests/output/test_portfolio_view.py` | test | n/a | `tests/risk/test_portfolio_loader.py` | role-match |
| `tests/graph/test_review_node.py` | test | n/a | `tests/graph/test_risk_node.py` | exact |
| `tests/graph/test_output_node.py` | test | n/a | `tests/graph/test_memory_nodes.py` | role-match |
| `tests/graph/test_pipeline_review.py` | test | n/a | `tests/graph/test_pipeline_with_memory.py` | exact |
| `tests/integration/test_phase8_e2e.py` | test | n/a | `tests/integration/test_phase7_e2e.py` | exact |
| `tests/integration/test_audit_reconstruction.py` | test | n/a | `tests/integration/test_phase7_policy_sha_linkage.py` | role-match |

## Pattern Assignments

### `src/ai_hedge_fund/review/policy.py` (config-loader, file-I/O + transform)

**Analog:** `src/ai_hedge_fund/risk/policy.py` — BYTE-FOR-BYTE mirror (rename `Risk*` → `Review*`, swap fields).

**Imports pattern** (lines 20-27):
```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field
```

**Default path constant** (line 29):
```python
DEFAULT_POLICY_PATH: Path = Path("config/risk_policy.yaml")
# For Phase 8: DEFAULT_REVIEW_POLICY_PATH: Path = Path("config/review_policy.yaml")
```

**Frozen + extra="forbid" Pydantic pattern** (lines 32-42):
```python
class RiskPolicy(BaseModel):
    """Human-editable risk limits for the paper portfolio.

    Frozen + ``extra="forbid"`` so policy instances are immutable and unknown
    YAML keys surface as ``ValidationError`` (T-06-01).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_single_position_pct: float = Field(
        ge=0.0, le=100.0,
        description="Hard cap on any one position as percent of portfolio",
    )
```

**YAML safe_load + Pydantic validate** (lines 129-148):
```python
def load_policy(path: Path | str = DEFAULT_POLICY_PATH) -> RiskPolicy:
    """Uses ``yaml.safe_load`` exclusively (T-06-01)."""
    text = Path(path).read_text()
    data = yaml.safe_load(text)
    return RiskPolicy.model_validate(data)
```

**SHA-256 canonical fingerprint** (lines 151-170):
```python
def compute_policy_sha(policy: RiskPolicy) -> str:
    """Return the SHA-256 fingerprint of a ``RiskPolicy`` (T-06-04)."""
    canonical = json.dumps(
        policy.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

**For Phase 8 translate to:** `ReviewPolicy(conviction_threshold: int Field(ge=0, le=100, default=70), review_prompt_template: str, reviewer_id_default: str | None)` + `load_review_policy()` + `compute_review_policy_sha()`.

---

### `src/ai_hedge_fund/schemas/signal_output.py` + `src/ai_hedge_fund/review/decision.py` (schemas, transform)

**Analog:** `src/ai_hedge_fund/schemas/risk.py::RiskAssessment`.

**Imports + ConfigDict pattern** (risk.py lines 25-29):
```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
```

**Required-field-with-validation pattern** (risk.py lines 75-121):
```python
class RiskAssessment(BaseModel):
    """Authoritative decision record for a (ticker, signal) pair."""

    ticker: str = Field(
        min_length=1,
        max_length=10,
        description="Stock ticker symbol evaluated",
    )
    status: Literal["APPROVED", "VETOED"] = Field(
        description="Deterministic outcome of the risk check chain. ...",
    )
    rationale: str = Field(
        min_length=1,
        description="Advisory LLM-authored explanation. ...",
    )
    policy_sha: str = Field(
        min_length=64,
        max_length=64,
        description="SHA-256 hex of the RiskPolicy used for this assessment. Mandatory for audit (T-06-04).",
    )
```

**Copy patterns:**
- No `| None` on any required SIG-01 field (direction / conviction / thesis_summary / risk_score / thesis_link).
- Use `min_length` / `ge,le` / `Literal[...]` for validation — NOT `Optional`.
- Add `model_config = ConfigDict(extra="forbid", frozen=True)` to both `FinalSignalOutput` and `ReviewDecision`.
- `policy_sha` / `review_policy_sha` are `Field(min_length=64, max_length=64)` — exactly 64 hex chars.

Full target schemas are pre-specified in 08-RESEARCH.md §`SignalOutput Design` (lines 135-170) and §`ReviewDecision` (lines 619-633) — planner should reference those verbatim.

---

### `src/ai_hedge_fund/graph/review_deps.py` (deps-container)

**Analog:** `src/ai_hedge_fund/graph/memory_deps.py` — BYTE-FOR-BYTE mirror.

**Full file pattern** (memory_deps.py lines 15-46):
```python
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
        db_session: Open SQLAlchemy session used by episodic queries ...
        beliefs_path: Root directory containing belief YAML files. ...
        recall_limit: Max episodic_memory rows to load per recall ...
    """

    db_session: Session
    beliefs_path: Path
    recall_limit: int = 10
```

**For Phase 8 translate to:**
```python
@dataclass(frozen=True)
class ReviewDeps:
    db_session: Session
    policy: ReviewPolicy | None = None
    policy_path: Path | None = None
```

Same `TYPE_CHECKING` guard for `Session` and `ReviewPolicy`. Same "policy XOR policy_path" pattern as `RiskDeps` (risk_deps.py lines 52-53).

---

### `src/ai_hedge_fund/graph/nodes.py::review_store_node` (node, append-only write)

**Analog:** `src/ai_hedge_fund/graph/nodes.py::episodic_store_node` (lines 1100-1178) — exact structural mirror.

**Short-circuit guard + signature** (lines 1100-1132):
```python
async def episodic_store_node(state: DebatePipelineState, deps: MemoryDeps) -> dict:
    """..."""
    if state.get("error"):
        return {}

    thesis = state.get("thesis") or {}
    signal = state.get("signal")
    risk = state.get("risk_assessment") or {}
    meta = state.get("candidate_metadata") or {}

    as_of_dt = _normalise_as_of(state["as_of_date"])
```

**Append-only EpisodicMemory insert** (lines 1147-1167):
```python
    row = EpisodicMemory(
        ticker=state["ticker"],
        sector=meta.get("sector") or "Unknown",
        record_type="analysis",
        signal_direction=(signal or {}).get("direction"),
        confidence=thesis.get("confidence"),
        outcome_pct=None,
        linked_analysis_id=None,
        policy_sha=risk.get("policy_sha"),
        as_of_date=as_of_dt,
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
```

**structlog completion event** (lines 1169-1177):
```python
    logger.info(
        "episodic_store_complete",
        ticker=state["ticker"],
        as_of_date=state["as_of_date"],
        episodic_stored_id=row.id,
        policy_sha=risk.get("policy_sha"),
        signal_direction=(signal or {}).get("direction"),
        risk_status=risk.get("status"),
    )
    return {"episodic_stored_id": row.id}
```

**For Phase 8 review_store_node:** same shape with `record_type='review'`, `linked_analysis_id=state['episodic_stored_id']`, payload carrying `{review_status, review_decision, review_policy_sha}`. Event name: `review_store_complete`.

---

### `src/ai_hedge_fund/graph/nodes.py::human_review_node` (node, event-driven via interrupt)

**Partial analog:** `risk_manager_node` (lines 866-991) for the **shape** (short-circuit, thesis check, structlog, dict return). The `interrupt()` primitive itself is NEW — see 08-RESEARCH.md §Pattern 1 for full example.

**Short-circuit + error-guard pattern** (nodes.py lines 902-907):
```python
    if state.get("error"):
        return {}
    thesis = state.get("thesis")
    if thesis is None:
        logger.error("risk_no_thesis", ticker=state.get("ticker"))
        return {"error": "No thesis available for risk check"}
```

**For Phase 8 translate to:**
```python
async def human_review_node(state: DebatePipelineState) -> dict:
    if state.get("error"):
        return {}
    signal = state.get("final_signal")
    if signal is None:
        return {"error": "No final_signal available for review"}

    review_request = { ... }  # see 08-RESEARCH.md §Pattern 6
    decision_raw = interrupt(review_request)  # PAUSES the graph
    decision = ReviewDecision.model_validate(decision_raw)
    logger.info("human_review_decision_received",
                ticker=state["ticker"], status=decision.status,
                reviewer_id=decision.reviewer_id)
    return {"review_decision": decision.model_dump()}
```

**Critical contract:**
- `interrupt()` MUST be called inside the node (not a log line).
- `ReviewDecision.model_validate` ensures malformed resume values raise `ValidationError` (T-08-04).
- No stdin reading — the CLI is responsible for prompting and passing `Command(resume=...)`.

---

### `src/ai_hedge_fund/graph/nodes.py::route_before_review` (router, event-driven)

**Analog:** `src/ai_hedge_fund/graph/nodes.py::route_after_risk` (lines 994-1005) — exact fail-closed mirror.

**Full fail-closed router** (lines 994-1005):
```python
def route_after_risk(state: DebatePipelineState) -> Literal["signal", "__end__"]:
    """Fail-closed router: APPROVED -> signal; VETOED or missing -> __end__.

    Pitfall 7 mitigation: any state where ``risk_assessment`` is absent,
    ``None``, or lacks a ``status`` key routes to ``__end__``. A router
    that defaulted to ``signal`` would silently approve a broken
    upstream, bypassing the veto entirely.
    """
    assessment = state.get("risk_assessment")
    if assessment is None:
        return "__end__"
    return "signal" if assessment.get("status") == "APPROVED" else "__end__"
```

**For Phase 8 translate to:**
```python
def route_before_review(state: DebatePipelineState) -> Literal["human_review", "review_store"]:
    """Pause-or-skip router. Fails CLOSED on missing policy/signal."""
    signal = state.get("final_signal") or {}
    threshold = state.get("_review_threshold")  # closure-bound by pipeline builder
    conviction = signal.get("conviction")
    if threshold is None or conviction is None:
        return "human_review"  # fail closed — human must verify
    return "human_review" if conviction >= threshold else "review_store"
```

Same fail-closed philosophy: ambiguous state routes to the STRICTER branch (human review), never to auto-approve.

---

### `src/ai_hedge_fund/graph/pipeline.py` (modify — add `with_output` + `with_review` kwargs)

**Analog:** `src/ai_hedge_fund/graph/pipeline.py::build_debate_pipeline` (lines 186-385, this same function).

**Kwarg-only signature + ValueError guard** (lines 186-282):
```python
def build_debate_pipeline(
    checkpointer: BaseCheckpointSaver | None = None,
    *,
    with_risk: bool = False,
    risk_deps: RiskDeps | None = None,
    with_memory: bool = False,
    memory_deps: MemoryDeps | None = None,
) -> CompiledStateGraph:
    """..."""
    if with_risk and risk_deps is None:
        raise ValueError(
            "build_debate_pipeline(with_risk=True) requires risk_deps -- "
            "supply a RiskDeps instance with db_session and returns."
        )
    if with_memory and memory_deps is None:
        raise ValueError(
            "build_debate_pipeline(with_memory=True) requires memory_deps -- "
            "supply a MemoryDeps instance with db_session and beliefs_path."
        )
```

**Closure-bound node wiring** (lines 302-320):
```python
    if with_risk:
        assert risk_deps is not None  # for the type checker; enforced above

        async def _risk_manager_bound(state: DebatePipelineState) -> dict:
            return await risk_manager_node(state, risk_deps)

        builder.add_node("risk_manager", _risk_manager_bound)

    if with_memory:
        assert memory_deps is not None

        async def _memory_recall_bound(state: DebatePipelineState) -> dict:
            return await memory_recall_node(state, memory_deps)

        async def _episodic_store_bound(state: DebatePipelineState) -> dict:
            return await episodic_store_node(state, memory_deps)

        builder.add_node("memory_recall", _memory_recall_bound)
        builder.add_node("episodic_store", _episodic_store_bound)
```

**Conditional edges** (lines 359-365):
```python
    builder.add_conditional_edges(
        "risk_manager",
        route_after_risk,
        {"signal": "signal", "__end__": "episodic_store"},
    )
    builder.add_edge("signal", "episodic_store")
    builder.add_edge("episodic_store", END)
```

**For Phase 8 extend with:**
1. Add `with_output: bool = False`, `with_review: bool = False`, `review_deps: ReviewDeps | None = None` kwargs.
2. ValueError guards: `with_review=True` requires `with_output=True` AND `review_deps is not None` AND `checkpointer is not None` (Pitfall I).
3. Add three new nodes via closure: `output_node`, `_human_review_bound`, `_review_store_bound`.
4. Insert `output_node` AFTER `signal` (or instead of direct `signal → episodic_store` edge).
5. Add conditional edge from `output_node` via `route_before_review` to either `human_review_node` or `review_store_node`.
6. Both paths converge at `review_store_node → episodic_store → END`.
7. **Backcompat invariant:** all existing branches stay byte-for-byte identical when `with_output=False` and `with_review=False`.

Full target topology documented in 08-RESEARCH.md §Architecture lines 192-251.

---

### `src/ai_hedge_fund/schemas/state.py` (modify)

**Analog:** `src/ai_hedge_fund/schemas/state.py::DebatePipelineState` (lines 154-242, this same class).

**Existing Phase 7 key-addition pattern** (lines 221-240):
```python
    # --- Phase 7 additions: memory substrate ---
    episodic_hits: list[dict] | None
    """Prior episodic records loaded by ``memory_recall_node``. ..."""

    beliefs_consulted: list[dict] | None
    """..."""

    episodic_stored_id: int | None
    """Primary key of the EpisodicMemory row inserted by
    ``episodic_store_node`` at pipeline end. Single-writer
    (episodic_store_node); NO operator.add reducer."""

    error: str | None
```

**For Phase 8 add keys:**
```python
    # --- Phase 8 additions: signal output + human review ---
    final_signal: dict | None
    """FinalSignalOutput.model_dump() written by output_node. ..."""

    review_decision: dict | None
    """ReviewDecision.model_dump() written by human_review_node (only when
    conviction >= threshold). ..."""

    review_stored_id: int | None
    """Primary key of the record_type='review' EpisodicMemory row inserted
    by review_store_node. Single-writer; NO operator.add reducer."""
```

No `operator.add` reducers — all new keys are single-writer (same pattern as `episodic_stored_id`).

---

### `src/ai_hedge_fund/output/portfolio_view.py` (query, CRUD read)

**Analog:** `src/ai_hedge_fund/memory/recall.py::query_episodic` (lines 46-95) — exact read-path sibling.

**Function signature + temporal-filter contract** (lines 46-80):
```python
def query_episodic(
    db_session: Session,
    *,
    as_of_date: str | date | datetime,
    ticker: str | None = None,
    sector: str | None = None,
    limit: int = 10,
) -> list[EpisodicHit]:
    """Return episodic hits visible as of ``as_of_date``.
    Always filters by ``as_of_date <= target`` (Pitfall 2). Always orders
    by ``as_of_date DESC`` and bounds by ``limit``.
    """
    if ticker is None and sector is None:
        raise ValueError("query_episodic requires ticker or sector (Pitfall 8 DoS guard)")
    target = _normalise_as_of(as_of_date)
```

**SQLAlchemy query + temporal filter** (lines 81-94):
```python
    predicates: list[Any] = []
    if ticker is not None:
        predicates.append(EpisodicMemory.ticker == ticker)
    if sector is not None:
        predicates.append(EpisodicMemory.sector == sector)

    rows = (
        db_session.query(EpisodicMemory)
        .filter(EpisodicMemory.as_of_date <= target)
        .filter(or_(*predicates))
        .order_by(EpisodicMemory.as_of_date.desc())
        .limit(limit)
        .all()
    )
    return [_to_hit(row) for row in rows]
```

**For Phase 8 portfolio_view.py translate to:** `query_portfolio_view(db_session, *, as_of_date, sector=None, limit_per_sector=50)`. Same temporal filter (`as_of_date <= target`). Filter `record_type == 'analysis'`. Group by sector in Python (`collections.defaultdict`), rank by `confidence DESC, as_of_date DESC`. Full reference code in 08-RESEARCH.md §Pattern 5 (lines 474-556).

**Critical: NO `@lru_cache`.** Append-only table IS the cache — see Pitfall C in RESEARCH.md.

---

### `src/ai_hedge_fund/scripts/run_analysis.py` + `audit_reconstruct.py` (CLI, request-response)

**Analog:** `src/ai_hedge_fund/scripts/ingest_outcome.py` (full file, 276 lines) — exact CLI shape.

**Module docstring + imports** (lines 1-59):
```python
"""Ingest a trade outcome and run self-critique (MEM-04).

Called from the CLI as::

    uv run python -m ai_hedge_fund.scripts.ingest_outcome \\
        --ticker AAPL --outcome-pct 4.2 --as-of 2026-04-20 \\
        --beliefs-dir ./beliefs
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory
...

logger = structlog.get_logger(__name__)
```

**Async workhorse function** (lines 107-235):
```python
async def ingest_outcome(
    session: Session,
    beliefs_dir: Path,
    ticker: str,
    outcome_pct: float,
    as_of_date: date,
) -> dict[str, Any]:
    """Record an outcome and run the self-critique loop end-to-end."""
    # 1. Validate inputs
    # 2. Append DB row
    # 3. Call agent
    # 4. Commit + log
    logger.info("self_critique_applied", ticker=ticker, ...)
    return {...}
```

**_main() entry point with argparse** (lines 238-271):
```python
def _main() -> int:  # pragma: no cover - CLI entry
    from ai_hedge_fund.config import AppSettings
    from ai_hedge_fund.db.session import get_engine, get_session_factory

    parser = argparse.ArgumentParser(description="Ingest a trade outcome and run self-critique.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--outcome-pct", type=float, required=True)
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    parser.add_argument("--beliefs-dir", type=Path, required=True)
    parser.add_argument("--database-url", type=str, default=None)
    args = parser.parse_args()

    settings = AppSettings()
    url = args.database_url or settings.database_url
    engine = get_engine(url)
    factory = get_session_factory(engine)
    session = factory()
    try:
        result = asyncio.run(ingest_outcome(session=session, ...))
        print(f"applied={result['applied']} ...")
        return 0
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(_main())
```

**For Phase 8 run_analysis.py translate to:**
- Args: `--ticker`, `--as-of`, `--sector` (optional, default "Unknown"), `--json` (flag), `--review-policy`, `--risk-policy`, `--beliefs-dir`, `--database-url`.
- Async workhorse: `run_analysis(session, ticker, as_of, sector, policies) -> dict` that builds `memory_deps` + `risk_deps` + `review_deps`, calls `build_debate_pipeline(with_risk=True, with_memory=True, with_output=True, with_review=True, checkpointer=PostgresSaver())`, invokes it with a unique `thread_id`, handles `__interrupt__` by prompting via `input()` on stdin, then resumes with `Command(resume=...)`.
- `thread_id = f"{ticker}-{as_of_date}-{uuid4().hex[:8]}"` (Pitfall J).
- Print markdown by default, JSON with `--json` flag.

**For Phase 8 audit_reconstruct.py translate to:**
- Args: `--episodic-id N`, `--database-url`, `--json`.
- Sync workhorse: `reconstruct(session, episodic_id) -> dict` returning `{analysis_row, review_row, langfuse_trace_hint}`. Reference code in 08-RESEARCH.md §Code Examples lines 861-888.
- Simpler than `run_analysis.py`: no async, no pipeline build — just SQLAlchemy queries.

---

### `config/review_policy.yaml` (config file)

**Analog:** `tests/risk/fixtures/risk_policy_sample.yaml` (full file, 28 lines).

**Full YAML shape:**
```yaml
# tests/risk/fixtures/risk_policy_sample.yaml
max_single_position_pct: 8.0
max_sector_pct: 25.0
max_total_exposure_pct: 100.0
max_correlation_with_portfolio: 0.70
correlation_window_days: 60
max_projected_drawdown_pct: 20.0
drawdown_window_days: 252
min_history_days: 60
excluded_instrument_types: ["OTC", "SPAC"]
excluded_sectors: []
size_high_conviction_multiplier: 1.0
size_medium_conviction_multiplier: 0.5
size_low_conviction_multiplier: 0.25
```

**For Phase 8 translate to:**
```yaml
# config/review_policy.yaml
# Human review gating policy. Conviction values at or above threshold
# pause the pipeline for human approval.
conviction_threshold: 70
review_prompt_template: "Review required: {ticker} conviction {conviction}. Approve (y) or reject (n)?"
reviewer_id_default: null
```

Plus `tests/review/fixtures/review_policy_sample.yaml` with `reviewer_id_default: "test"` per 08-RESEARCH.md §Wave 0 Gaps.

---

### Test Patterns

#### `tests/integration/test_phase8_e2e.py`

**Analog:** `tests/integration/test_phase7_e2e.py` (lines 1-330+) — exact shape.

**Stubbing pattern** (lines 94-119):
```python
def _stubbed_stack(*, rationale: str = "stubbed risk rationale") -> ExitStack:
    """Return an ExitStack overriding every LLM agent used by the pipeline."""
    stack = ExitStack()
    stack.enter_context(fundamental_agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(sentiment_agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(technical_agent.override(model=TestModel(call_tools=[])))
    stack.enter_context(manager_agent.override(model=TestModel()))
    stack.enter_context(bull_agent.override(model=TestModel()))
    stack.enter_context(bear_agent.override(model=TestModel(custom_output_args=_valid_bear_case())))
    stack.enter_context(rebuttal_agent.override(model=TestModel()))
    stack.enter_context(final_arguments_agent.override(model=TestModel()))
    stack.enter_context(debate_synthesis_agent.override(model=TestModel()))
    stack.enter_context(
        risk_manager_agent.override(model=TestModel(custom_output_args={"rationale": rationale}))
    )
    stack.enter_context(signal_agent.override(model=TestModel()))
    stack.enter_context(
        self_critique_agent.override(
            model=TestModel(custom_output_args={"rationale": "stubbed MEM-04 rationale"})
        )
    )
    return stack
```

**Initial-state helper** (lines 122-131):
```python
def _initial_state(
    ticker: str = "AAPL",
    as_of: str = "2026-04-20",
    sector: str = "Technology",
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "as_of_date": as_of,
        "candidate_metadata": {"sector": sector, "instrument_type": "equity"},
    }
```

**Three-way SHA audit test** (test_phase7_e2e.py lines 184-217):
```python
def test_composed_with_risk_persists_episodic_with_policy_sha(...):
    """Phase 6 -> Phase 7 audit: stored row's policy_sha == state's policy_sha."""
    ...
    final_state = asyncio.run(graph.ainvoke(state))
    expected_sha = risk_assessment.get("policy_sha")
    assert expected_sha
    stored_id = final_state.get("episodic_stored_id")
    row = memory_db_session.query(EpisodicMemory).filter_by(id=stored_id).one()
    assert row.policy_sha == expected_sha
    assert row.payload["risk_assessment"]["policy_sha"] == expected_sha
```

**For Phase 8 integration tests scenarios (from 08-RESEARCH.md §Wave 0 Gaps):**
1. Above-threshold → `__interrupt__` fires
2. Below-threshold → no pause (review_status = NOT_REQUIRED)
3. APPROVED resume → final state has `review_decision.status='APPROVED'`
4. REJECTED resume → final state has `review_decision.status='REJECTED'`
5. VETOED → no `__interrupt__`, no `record_type='review'` row
6. Three-way SHA: `state['review_decision']['review_policy_sha'] == row.payload['review_policy_sha'] == compute_review_policy_sha(policy)` — mirror of Phase 7 policy_sha test above.
7. Append-only: after review, analysis row is byte-identical.
8. Phase-5 backcompat smoke (already green in test_phase7_e2e.py line N).

**Checkpointer** for interrupt tests: `InMemorySaver` from `langgraph.checkpoint.memory` (tests only — avoids Postgres dep).

#### `tests/graph/test_pipeline_review.py`

**Analog:** `tests/graph/test_pipeline_with_memory.py` (lines 55-138) — exact topology-inspection pattern.

**Compile-time topology inspection** (lines 55-82):
```python
def test_builder_no_kwargs_backcompat() -> None:
    """Test 16: the no-kwargs builder still compiles (Phase-5 topology)."""
    graph = build_debate_pipeline()
    assert isinstance(graph, CompiledStateGraph)
    nodes = set(graph.get_graph().nodes)
    assert "memory_recall" not in nodes
    assert "episodic_store" not in nodes
    assert "risk_manager" not in nodes


def test_with_memory_requires_memory_deps() -> None:
    """Test 17: with_memory=True and memory_deps=None -> ValueError."""
    with pytest.raises(ValueError, match="memory_deps"):
        build_debate_pipeline(with_memory=True)


def test_with_memory_nodes_registered(memory_db_session: Session, beliefs_tmp_dir: Path) -> None:
    """Test 18: with_memory=True registers both memory nodes (no risk)."""
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    graph = build_debate_pipeline(with_memory=True, memory_deps=deps)
    nodes = set(graph.get_graph().nodes)
    assert "memory_recall" in nodes
    assert "episodic_store" in nodes
```

**Edge inspection** (lines 112-138):
```python
def test_with_memory_start_fan_out_goes_through_memory_recall(...) -> None:
    graph = build_debate_pipeline(with_memory=True, memory_deps=deps)
    edges = {(e.source, e.target) for e in graph.get_graph().edges}

    assert ("__start__", "memory_recall") in edges
    assert ("memory_recall", "fundamental") in edges
```

**For Phase 8:** `test_builder_no_kwargs_backcompat` (verify `human_review`, `review_store`, `output` NOT in nodes when `with_output=False`). `test_with_review_requires_checkpointer` (verify ValueError when `with_review=True, checkpointer=None`). `test_with_output_nodes_registered`. Plus edge assertions for the new topology.

---

## Shared Patterns

### Pattern A: Frozen Pydantic with `extra="forbid"` + `ConfigDict`

**Source:** `src/ai_hedge_fund/risk/policy.py` line 41, `src/ai_hedge_fund/schemas/risk.py` line 62.

**Apply to:** `ReviewPolicy`, `ReviewDecision`, `FinalSignalOutput`.

```python
model_config = ConfigDict(extra="forbid", frozen=True)
```

### Pattern B: `from __future__ import annotations` + TYPE_CHECKING imports

**Source:** every module in `src/ai_hedge_fund/`. Lines 20 / 15 / 15 of policy.py / memory_deps.py / risk_deps.py.

**Apply to:** all new `src/ai_hedge_fund/output/` and `src/ai_hedge_fund/review/` modules.

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing-only
    from sqlalchemy.orm import Session
```

### Pattern C: Short-circuit on upstream error

**Source:** `episodic_store_node` line 1131, `risk_manager_node` line 902, `memory_recall_node` line 1036.

**Apply to:** `output_node`, `human_review_node`, `review_store_node`.

```python
if state.get("error"):
    return {}
```

### Pattern D: structlog completion event with full audit fields

**Source:** `episodic_store_node` lines 1169-1177, `risk_manager_node` lines 979-990.

**Apply to:** every new Phase 8 node.

```python
logger.info(
    "<node>_complete",
    ticker=state["ticker"],
    # include every audit-relevant field — policy_sha, review_policy_sha, tokens, status, ...
    input_tokens=usage.input_tokens,  # only if node calls an LLM
    output_tokens=usage.output_tokens,
    total_tokens=usage.total_tokens,
    policy_sha=policy_sha,
)
```

For `human_review_node` + `review_store_node` (no LLM call): omit token fields; keep ticker + status + policy_sha fields.

### Pattern E: Kwarg-only pipeline builder + ValueError guard

**Source:** `build_debate_pipeline` lines 186-281.

**Apply to:** all new kwargs on `build_debate_pipeline`.

```python
def build_debate_pipeline(
    checkpointer: BaseCheckpointSaver | None = None,
    *,  # kwarg-only from here — all Phase 6/7/8 options
    with_risk: bool = False,
    risk_deps: RiskDeps | None = None,
    ...
    with_output: bool = False,
    with_review: bool = False,
    review_deps: ReviewDeps | None = None,
) -> CompiledStateGraph:
    if with_review and not with_output:
        raise ValueError("with_review=True requires with_output=True")
    if with_review and review_deps is None:
        raise ValueError("with_review=True requires review_deps")
    if with_review and checkpointer is None:
        raise ValueError("with_review=True requires a checkpointer")
```

### Pattern F: Append-only DB write (never mutate)

**Source:** `episodic_store_node` lines 1147-1167, `ingest_outcome._append_outcome_row` lines 86-104.

**Apply to:** `review_store_node`.

```python
row = EpisodicMemory(
    ticker=state["ticker"],
    record_type="review",           # NEW record_type
    linked_analysis_id=state["episodic_stored_id"],  # CRITICAL: preserves linkage
    policy_sha=(state.get("risk_assessment") or {}).get("policy_sha"),
    as_of_date=as_of_dt,
    payload={ "schema_version": 1, ... },
)
deps.db_session.add(row)
deps.db_session.commit()
```

NEVER use `session.merge()` or `UPDATE`. NEVER overwrite the analysis row's `payload`.

### Pattern G: Temporal filter contract (`as_of_date <= target`)

**Source:** `query_episodic` line 89.

**Apply to:** `query_portfolio_view`.

```python
.filter(EpisodicMemory.as_of_date <= target)
```

SIG-02 must never leak future data. Integration test (07-RESEARCH.md Pitfall 2) seeds a future-dated row and asserts absence.

### Pattern H: CLI async wrapper with `asyncio.run` + try/finally session cleanup

**Source:** `ingest_outcome._main()` lines 238-271, `purge_expired_episodic._main()` lines 68-87.

**Apply to:** `run_analysis._main()` + `audit_reconstruct._main()`.

```python
def _main() -> int:  # pragma: no cover - CLI entry
    from ai_hedge_fund.config import AppSettings
    from ai_hedge_fund.db.session import get_engine, get_session_factory

    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--ticker", required=True)
    ...
    args = parser.parse_args()

    settings = AppSettings()
    url = args.database_url or settings.database_url
    engine = get_engine(url)
    factory = get_session_factory(engine)
    session = factory()
    try:
        result = asyncio.run(run_analysis(session=session, ...))
        print(...)
        return 0
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(_main())
```

### Pattern I: Three-way SHA equality test (policy audit)

**Source:** `tests/integration/test_phase7_e2e.py::test_composed_with_risk_persists_episodic_with_policy_sha` lines 208-217.

**Apply to:** `tests/integration/test_phase8_e2e.py::test_review_policy_sha_three_way`.

```python
final_state = asyncio.run(graph.ainvoke(state, config=config))
# Three-way equality:
recomputed_sha = compute_review_policy_sha(policy)
assert final_state["review_decision"]["review_policy_sha"] == recomputed_sha
review_row = session.query(EpisodicMemory).filter_by(id=final_state["review_stored_id"]).one()
assert review_row.payload["review_policy_sha"] == recomputed_sha
```

## No Analog Found

| File | Role | Data Flow | Reason | Planner Guidance |
|------|------|-----------|--------|------------------|
| `src/ai_hedge_fund/output/formatter.py` | utility | transform | No existing markdown/JSON formatter in the codebase | Use stdlib `json` + simple f-string for markdown. Reference: print output shape documented in 08-RESEARCH.md §Open Questions 4 (30-line markdown + /tmp/review-*.json dump). |
| LangGraph `interrupt()` primitive inside `human_review_node` | node call | event-driven | No existing node calls `interrupt()` (new primitive in Phase 8) | Use reference code from 08-RESEARCH.md §Pattern 1 (lines 311-346) + §Pattern 6 (lines 563-607) verbatim. |
| CLI stdin-prompt + `Command(resume=...)` | CLI | event-driven | No existing CLI handles a paused graph | Reference: 08-RESEARCH.md §CLI Entry Point + Pitfall I/J. Use `await graph.ainvoke(initial, config)`; if `result["__interrupt__"]`: prompt via `input()` (blocking, in a thread executor or sync block), build ReviewDecision dict, call `await graph.ainvoke(Command(resume=decision_dict), config)`. |

## Metadata

**Analog search scope:**
- `src/ai_hedge_fund/risk/` (policy + schema + checks)
- `src/ai_hedge_fund/memory/` (recall + episodic + beliefs)
- `src/ai_hedge_fund/graph/` (nodes + pipeline + deps)
- `src/ai_hedge_fund/schemas/` (state + risk + agents)
- `src/ai_hedge_fund/scripts/` (ingest_outcome + purge_expired_episodic)
- `src/ai_hedge_fund/observability/` (langfuse)
- `tests/integration/` (phase7_e2e + phase7_policy_sha_linkage)
- `tests/graph/` (pipeline_with_memory + pipeline_with_risk)
- `tests/risk/` (fixtures + policy_schema tests)

**Files scanned:** 19 analog source files + 4 test analog files + 2 config fixtures

**Pattern extraction date:** 2026-04-22
