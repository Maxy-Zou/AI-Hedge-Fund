# Phase 8: Signal and Output - Research

**Researched:** 2026-04-22
**Domain:** LangGraph human-in-the-loop interrupts, investor-ready output formatting, portfolio aggregation over append-only memory, compliance-grade audit trail
**Confidence:** HIGH

## Summary

Phase 8 is the capstone layer. It does NOT introduce new LLM agents. It wires four pure-Python + config-driven capabilities onto the already-composed Phase 5/6/7 pipeline: (1) a Pydantic `SignalOutput` with no nullable required fields, (2) a query-function portfolio view over `episodic_memory`, (3) a conditional LangGraph `interrupt()` human review gate backed by a `ReviewPolicy` YAML with `review_policy_sha`, and (4) verification that Langfuse + structlog already capture the per-agent metadata SIG-04 requires (the current instrumentation does — gap is in the reconstruction tool, not the spans).

Every architectural primitive needed already exists in the codebase — `RiskPolicy` + `compute_policy_sha` is the template for `ReviewPolicy` + `compute_review_policy_sha`; `RiskDeps` / `MemoryDeps` is the template for `ReviewDeps`; `route_after_risk` + `add_conditional_edges` is the template for routing high-conviction signals to the review node; `episodic_store_node`'s append-only pattern is the template for persisting the review decision as a new `record_type='review'` row; and `langgraph.types.interrupt` + `Command(resume=...)` (verified installed at langgraph 1.1.6) is the exact primitive for SIG-03. Phase 8 is composition, not invention.

**Primary recommendation:** Ship Phase 8 as four narrowly-scoped subsystems that mirror Phase 6/7 shapes exactly. Add `with_output` + `with_review` kwargs to `build_debate_pipeline` (backcompat preserved byte-for-byte when both are False). Make the human review gate a REAL `langgraph.types.interrupt()` call inside a conditional node — gate fires only when conviction crosses `ReviewPolicy.conviction_threshold`, and the `ReviewDecision` (APPROVED/REJECTED + reviewer_note + review_policy_sha) is persisted as a new append-only `EpisodicMemory` row with `record_type='review'` and `linked_analysis_id` pointing at the stored analysis. SignalOutput is REPLACED (not wrapped) with a no-nulls schema that embeds a `thesis_link` referencing `episodic_stored_id`. CLI entry point (`scripts/run_analysis.py`) is the first user-facing surface; it uses `asyncio.run` + blocking stdin prompt for the review decision (deferred fancier UI per CONTEXT.md). Audit reconstruction is a new `scripts/audit_reconstruct.py` that, given an `episodic_id`, joins the row + its `record_type='review'` follow-up + its Langfuse trace (by `thread_id`).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SignalOutput contract (SIG-01) | Schemas (`src/ai_hedge_fund/schemas/`) | — | Pydantic validation is where "no null" is enforced. Mirrors Phase 6 `RiskAssessment` scope (pure schema; zero I/O). |
| Portfolio view (SIG-02) | Output module (`src/ai_hedge_fund/output/`) | DB (`episodic_memory`) | Pure SQL query + Python aggregation. No LLM. Fresh-by-construction because read-time over append-only table. |
| Human review gate (SIG-03) | Graph (`src/ai_hedge_fund/graph/nodes.py` + `pipeline.py`) | Review policy (`src/ai_hedge_fund/review/`) | LangGraph `interrupt()` lives in a node; the policy + sha + loader lives in a sibling subpackage mirroring `src/ai_hedge_fund/risk/`. |
| ReviewPolicy + review_policy_sha | Review module (`src/ai_hedge_fund/review/policy.py`) | — | Exact mirror of `risk/policy.py`. Frozen Pydantic + `extra="forbid"` + SHA-256 over canonical JSON. |
| ReviewDecision persistence | DB (`episodic_memory` via `review_store_node`) | Graph | Append-only: new row with `record_type='review'` + `linked_analysis_id`. No mutation of the analysis row (CLAUDE.md invariant). |
| Audit trail (SIG-04) | Observability (`src/ai_hedge_fund/observability/langfuse.py`) + new `scripts/audit_reconstruct.py` | structlog | Spans already exist per-node (see `logger.info(...input_tokens=, output_tokens=, total_tokens=...)` pattern in every Phase 1-7 node). The gap is a reconstruction tool that, given an `episodic_id`, walks spans + DB rows. |
| CLI entry point | Scripts (`src/ai_hedge_fund/scripts/run_analysis.py`) | Graph | Thin async wrapper around `build_debate_pipeline(..., with_output=True, with_review=True)`. Uses blocking stdin for reviewer input in v1. Mirrors `scripts/ingest_outcome.py` shape. |

## User Constraints (from CONTEXT.md)

### Locked Decisions (Non-Negotiable Invariants)

1. **Human review gate is a REAL interrupt** — LangGraph `interrupt()` primitive (or `interrupt_before=[...]` compile flag). A log message "please review" is not enough. **This is non-negotiable per CLAUDE.md and founder's AI-washing aversion.**
2. **Every agent step logged** — Langfuse is the primary audit store (open-source, self-hosted). structlog is belt-and-braces. All Phase 1-7 nodes already emit structlog events with `input_tokens`/`output_tokens`/`total_tokens`/`ticker`/policy_sha where applicable.
3. **Schema validation at the output boundary** — `SignalOutput` is Pydantic with NO optional/null required fields on the SIG-01 contract (direction, conviction, thesis_summary, risk_score, thesis_link). Nulls violate SIG-01.
4. **Portfolio view is a QUERY, not a materialized table** — derived from `episodic_memory` + latest-analysis-per-ticker. Freshness follows writes automatically (append-only table; read always returns current truth).
5. **Threshold is configurable** — YAML-loaded `ReviewPolicy` (mirrors Phase 6 `RiskPolicy`) with integer `conviction_threshold` (default 70 per CONTEXT.md). Reuses `policy_sha`-style SHA-256 audit fingerprint concept → `review_policy_sha`.
6. **Backcompat** — `build_debate_pipeline()` (no kwargs), `build_debate_pipeline(with_risk=True)`, `build_debate_pipeline(with_memory=True)`, and the 2-way composition all remain byte-for-byte identical behaviourally. Phase 8 adds `with_output=True` + `with_review=True` (opt-in only).
7. **CLAUDE.md invariants still apply** — append-only for episodic financial records (new rows, not mutations); tool-first (no LLM computes risk_score or derives the decision); structured debate only; token budgets from day one; belief memory human-readable; honest positioning ("LLM-powered research at scale", not "AI beats the market").

### Claude's Discretion

- Exact shape of `SignalOutput` — whether to replace Phase 5's `SignalOutput` or add a new `FinalSignalOutput`. **Research recommends REPLACE** (see §Standard Stack §SignalOutput).
- Whether `with_output` implies `with_review` — **Research recommends: `with_output` and `with_review` are separate kwargs; `with_review` requires `with_output=True` (ValueError if not).**
- Whether `ReviewDecision` is a new `record_type='review'` row in `episodic_memory` or a new table. **Research recommends: `record_type='review'` row** (append-only invariant + already-existing `linked_analysis_id` column + already-indexed path).
- CLI UI: blocking stdin vs. async prompt. **Research recommends: blocking stdin via `input()` in a thread executor for the async pipeline** (fancier UI deferred per CONTEXT.md).
- Where the reviewer actually sees the thesis / debate transcript: formatted markdown in terminal vs. file-write vs. both. **Research recommends: both — print formatted markdown to stdout AND write to a temp file whose path is printed (so reviewer can inspect in an editor).**

### Deferred Ideas (OUT OF SCOPE)

- Interactive CLI / TUI / web UI for human review (v1: plain stdin prompt)
- Multi-reviewer consensus / approval workflow (v1: single reviewer)
- Real-time portfolio rebalancing suggestions (Phase 8 delivers per-ticker signals + a portfolio VIEW, not portfolio ACTIONS)
- Broker integration / live order submission (explicitly out of scope for v1)
- Automated compliance report generation (SIG-04 ships the audit substrate; report generation is a later deliverable)
- Email/Slack/Teams notifications of pending reviews (v2)

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SIG-01 | Signal output schema: direction (long/short/neutral), conviction (0-100), one-paragraph thesis summary, risk_score, thesis link. All populated, no nulls. | §Standard Stack → `SignalOutput` design. Pydantic `extra="forbid"` + no default None on required fields + min_length on string fields. Test: round-trip + `ValidationError` on any missing field. |
| SIG-02 | Portfolio-level view: ranks analyzed tickers by conviction, shows thesis summaries, groups by sector. Ranking updates when new analyses complete. | §Standard Stack → `query_portfolio_view` over `episodic_memory` with `record_type='analysis'`, ordered by `confidence DESC, as_of_date DESC`, grouped by `sector`. Freshness follows writes because `episodic_memory` is append-only (no cache, no trigger). |
| SIG-03 | Human review gate: signals with conviction above threshold pause pipeline, present thesis + debate transcript, do not finalize until human approves/rejects. | §Standard Stack → `human_review_node` calls `langgraph.types.interrupt(review_request)`, paired with `add_conditional_edges` route `route_before_review` that skips the node when `conviction < threshold`. Resume via `graph.ainvoke(Command(resume=review_decision), config)`. |
| SIG-04 | Full audit trail: every agent step logged with inputs, outputs, reasoning, model used, tokens consumed, timestamp. Compliance reviewer can trace backward. | §Audit Completeness — current Langfuse instrumentation + structlog in every node already captures this. Phase 8 adds `scripts/audit_reconstruct.py` that, given `episodic_id`, pulls the stored row + its review follow-up + its Langfuse trace by `thread_id`. |

## Standard Stack

### Core (all already in `pyproject.toml`)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | 1.1.6 (installed) | `interrupt()` + `Command(resume=...)` primitive, `add_conditional_edges`, `InMemorySaver` for tests | [VERIFIED: .venv + Context7 `/websites/langchain_oss_python_langgraph` docs] — `langgraph.types.interrupt` is the canonical HITL primitive; calling it inside a node raises `GraphInterrupt`, surfaces `value` to caller via `result["__interrupt__"]`, resumes by `graph.ainvoke(Command(resume=V), config)`. Requires a checkpointer. |
| pydantic | 2.12+ (installed) | `SignalOutput` + `ReviewPolicy` + `ReviewDecision` schemas with `extra="forbid"` | [VERIFIED: `src/ai_hedge_fund/risk/policy.py`] — this is the codebase pattern already validated in Phase 6. |
| pyyaml | (transitive via existing) | Load `config/review_policy.yaml` via `yaml.safe_load` | [CITED: `src/ai_hedge_fund/risk/policy.py::load_policy`] — exact pattern; never use `yaml.load` (RCE). |
| ruamel.yaml | >=0.19 (installed) | **NOT used in Phase 8** — only Phase 7 beliefs need round-trip | Decision: review policy is machine-only (no human comments); `yaml.safe_load` is sufficient and matches `risk/policy.py`. |
| sqlalchemy | 2.0+ (installed) | Query `episodic_memory` for portfolio view + append `record_type='review'` row | [VERIFIED: `src/ai_hedge_fund/db/models.py::EpisodicMemory`] — the table already exists; Phase 8 adds a query function and a single write call. |
| structlog | 25.0+ (installed) | Per-node `logger.info(...tokens...)` events | [VERIFIED: every node in `src/ai_hedge_fund/graph/nodes.py`] — already present. |
| langfuse | 4.0+ (installed) | Per-agent span capture via `CallbackHandler` (already wired in Phase 1) | [VERIFIED: `src/ai_hedge_fund/observability/langfuse.py`] — graceful-degradation pattern already in place. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| argparse | stdlib | `scripts/run_analysis.py` CLI flags | First-pass CLI (mirror `scripts/ingest_outcome.py`). |
| asyncio | stdlib | `asyncio.run(pipeline.ainvoke(...))` in CLI | The pipeline is async; CLI wraps with blocking `asyncio.run`. |
| hashlib + json | stdlib | `compute_review_policy_sha(policy)` | Canonical-JSON + SHA-256 hex digest. Mirrors `compute_policy_sha`. |
| pytest | 9.0+ (installed) | Unit + integration tests | Mirrors existing test layout. |
| pytest-asyncio | 1.0+ (installed, auto mode) | Async pipeline tests | `asyncio_mode = "auto"` is already set in `pyproject.toml`. |
| TestModel from pydantic_ai.models.test | installed | Stub all 12 agents in integration tests | [VERIFIED: `tests/integration/test_phase7_e2e.py`] — identical pattern. |
| InMemorySaver from langgraph.checkpoint.memory | 1.1.6 | Test-only checkpointer for interrupt scenarios | [CITED: LangGraph `/oss/python/langgraph/interrupts`] — `interrupt()` requires a checkpointer; tests use `InMemorySaver` to avoid the Postgres dep. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `langgraph.types.interrupt()` primitive | `interrupt_before=["signal_node"]` compile-flag | Compile-flag pauses unconditionally. Phase 8 needs CONDITIONAL pause (only above threshold). Easiest way: conditional edge routes to `human_review_node` which calls `interrupt()`. If below threshold, edge bypasses the node → no pause. Tried-and-true pattern per LangGraph docs. |
| Replace Phase-5 `SignalOutput` | Add new `FinalSignalOutput` wrapping it | Replace is cleaner: one schema, no indirection. Phase 5 `SignalOutput` is already returned by `signal_agent`; the new shape extends it with `risk_score` + `thesis_link` + changes `conviction` from `Literal["low","medium","high"]` to `int [0,100]`. **Decision:** replace, because conviction-as-integer is required by SIG-01 and by `ReviewPolicy.conviction_threshold` comparison. Update `signal_agent`'s `output_type`. |
| `record_type='review'` row in `episodic_memory` | New `review_decisions` table | New table means a new Alembic migration + new query layer. `episodic_memory` already has `linked_analysis_id` + `policy_sha` + `payload` JSONB; a `record_type='review'` row fits natively and stays append-only (CLAUDE.md invariant). |
| Blocking `input()` for CLI review | Rich/Textual TUI | Deferred per CONTEXT.md. v1 = stdin prompt; v2 = richer UI. |
| ruamel.yaml for review policy | PyYAML `safe_load` | ruamel.yaml is for round-trip preservation (Phase 7 beliefs need human comments preserved). Review policy is machine-authored + loaded once at startup; `yaml.safe_load` is sufficient and matches `risk/policy.py`. |

### Installation

**Nothing to install.** All dependencies are already in `pyproject.toml`. Verified via:

```bash
.venv/bin/python -c "from langgraph.types import interrupt, Command; from langgraph.checkpoint.memory import InMemorySaver; print('OK')"
# OK
.venv/bin/python -c "import importlib.metadata as m; print(m.version('langgraph'))"
# 1.1.6
```

**Version verification — 2026-04-22:**

| Package | Installed | Phase-8 minimum | Source |
|---------|-----------|-----------------|--------|
| langgraph | 1.1.6 | 1.0+ (for stable `interrupt`) | [VERIFIED: project venv + Context7 docs] |
| langfuse | (per lock) | 4.0 (installed) | [CITED: `pyproject.toml`] |
| pydantic-ai | 1.0+ | 1.0 | [CITED: `pyproject.toml`] |

### `SignalOutput` Design (SIG-01) — authoritative schema

**Decision: REPLACE the Phase-5 `SignalOutput`** (in `src/ai_hedge_fund/schemas/agents.py`). This is NOT a breaking change for Phase 6-7 integration tests IF the new field names are handled at the boundary; the research-pipeline tests (Phase 3) that assert `conviction == "high"` will need updating. Scope the rename carefully.

**Better recommendation:** Keep Phase-5 `SignalOutput` as-is (used by `signal_agent.output_type`) and introduce NEW `FinalSignalOutput` in `src/ai_hedge_fund/schemas/signal_output.py` that is ASSEMBLED by a Python function at the end of the pipeline. This assembler reads `state['signal']` (Phase-5 form) + `state['risk_assessment']` + `state['episodic_stored_id']` and produces the investor-facing `FinalSignalOutput`. Benefits:
- Phase 3/5 integration tests stay green byte-for-byte.
- SIG-01 fields are produced from authoritative sources (risk_score from `state['risk_assessment']`, thesis_link from `state['episodic_stored_id']`, conviction as integer from `state['thesis']['confidence']`) — not re-asked from the LLM.
- Tool-first invariant preserved: the LLM does not author risk_score.

```python
# src/ai_hedge_fund/schemas/signal_output.py (NEW)
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class FinalSignalOutput(BaseModel):
    """Investor-facing signal contract (SIG-01). No nullable required fields.

    Assembled in Python at the end of the pipeline (output_node) from
    authoritative state sources. The LLM never writes to this schema;
    conviction comes from state['thesis']['confidence'], risk_score from
    state['risk_assessment']['observed' or derived], thesis_link from
    state['episodic_stored_id'].
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str = Field(min_length=1, max_length=10)
    as_of_date: str = Field(min_length=10, max_length=10,
                             description="ISO YYYY-MM-DD")
    direction: Literal["long", "short", "neutral"]
    conviction: int = Field(ge=0, le=100,
                             description="Integer 0-100 from ThesisOutput.confidence")
    thesis_summary: str = Field(min_length=1, max_length=2000,
                                 description="One-paragraph (<=2000 char) thesis summary")
    risk_score: int = Field(ge=0, le=100,
                             description="Derived risk score; 0=no risk, 100=maximum")
    thesis_link: str = Field(min_length=1,
                              description="Reference to the stored thesis (episodic://<id> URI)")

    # Audit metadata (required, not nullable)
    policy_sha: str = Field(min_length=64, max_length=64,
                             description="Risk policy SHA-256 at decision time")
    review_policy_sha: str = Field(min_length=64, max_length=64,
                                    description="Review policy SHA-256 at decision time")
    episodic_id: int = Field(ge=1,
                              description="Primary key of the stored analysis row")
    review_status: Literal["NOT_REQUIRED", "APPROVED", "REJECTED"] = Field(
        description="NOT_REQUIRED when below threshold; APPROVED/REJECTED when human reviewed"
    )
```

**`risk_score` derivation** (tool-first):

```python
def derive_risk_score(risk_assessment: dict) -> int:
    """Map RiskAssessment into a 0-100 risk score.

    APPROVED: returns the derived-size-relative-to-cap * 100 (higher size
              relative to max_single_position_pct = higher risk).
    VETOED:   returns 100 (maximum risk — constraint violated).

    Pure Python, deterministic, zero-LLM. Must be unit-tested.
    """
```

**`thesis_link` format:** `episodic://<episodic_id>` — dereferences through the DB. CLI-side expansion is trivial (look up the row). Keeps the schema self-contained (no filesystem paths to serialise).

## Architecture Patterns

### System Architecture Diagram

```
INPUT (CLI):  ticker + as_of_date
      |
      v
[build_debate_pipeline(with_memory=True, with_risk=True,
                       with_output=True, with_review=True,
                       memory_deps, risk_deps, review_deps)]
      |
      | compile-time-static topology (NEW edges in CAPS):
      |
      v
START -> memory_recall -> [3 analysts fan-out/in] -> manager
       -> bull -> bear -> rebuttal -> final_arguments -> debate_synthesis
       -> risk_manager --[route_after_risk]-->
              |                                  |
              | APPROVED                         | VETOED
              v                                  v
          signal                            episodic_store (persist VETOED)
              |                                  |
              v                                  v
          OUTPUT_NODE (NEW)                      END
              |                 (VETOED signals never reach review —
              |                  they are rejected by risk, not by human)
              |
              | assembles FinalSignalOutput from
              | state['signal'] + state['risk_assessment'] + state['episodic_stored_id']
              v
    ROUTE_BEFORE_REVIEW (NEW conditional):
        if signal.conviction >= policy.conviction_threshold:
              -> HUMAN_REVIEW_NODE
        else:
              -> episodic_store (review_status=NOT_REQUIRED)
                  -> END
              |
              v
    HUMAN_REVIEW_NODE (NEW, calls langgraph.types.interrupt):
        interrupt({
           "ticker": ..., "signal": FinalSignalOutput, "thesis": ...,
           "debate_transcript": {bull, bear, rebuttal, final, synthesis},
           "risk_assessment": ..., "episodic_hits": ..., "beliefs_consulted": ...
        })
        ---- PAUSES ---- (GraphInterrupt raised; caller sees result["__interrupt__"])
        ---- caller resumes with Command(resume={"status": "APPROVED" | "REJECTED",
                                                  "reviewer_id": "...", "reviewer_note": "..."})
        validate -> return {"review_decision": {...}}
              |
              v
    REVIEW_STORE_NODE (NEW):
        append EpisodicMemory(record_type='review',
                              linked_analysis_id=episodic_stored_id,
                              payload={decision, review_policy_sha, reviewer_id, reviewer_note})
              |
              v
    EPISODIC_STORE (existing, already wired by Phase 7)
              |
              v
            END (final_state['signal_output'] = FinalSignalOutput dict)

OUTPUT (CLI): pretty-print FinalSignalOutput (markdown) + --json flag
```

Key observations:
- **Conditional pause**: `interrupt()` only fires when conviction >= threshold (routed by `route_before_review`). Below-threshold signals flow straight through (review_status=NOT_REQUIRED) — no pause, no prompt.
- **VETOED signals are NEVER reviewed**: the risk router already ends the graph. A human cannot override a risk veto (Phase 6 `route_after_risk` is fail-closed; RISK-01 non-negotiable).
- **Two separate store steps**: `review_store_node` writes the decision row BEFORE `episodic_store_node` writes the analysis row (or after — order is not required; both are append-only). Simplest: one new `record_type='review'` row linked by `linked_analysis_id` to the analysis row written by the existing `episodic_store_node`.
- **checkpointer required**: `interrupt()` requires a checkpointer. For production, reuse the existing PostgresSaver wiring. For tests, `InMemorySaver`.

### Recommended Project Structure (additions only)

```
src/ai_hedge_fund/
├── review/                       # NEW subpackage (mirror of src/ai_hedge_fund/risk/)
│   ├── __init__.py
│   ├── policy.py                 # ReviewPolicy + load_review_policy + compute_review_policy_sha
│   └── decision.py               # ReviewDecision schema
├── output/                       # NEW subpackage
│   ├── __init__.py
│   ├── signal.py                 # assemble_final_signal() — pure assembler
│   ├── portfolio_view.py         # query_portfolio_view() — SIG-02
│   └── formatter.py              # format_signal_md(), format_review_request_md()
├── schemas/
│   └── signal_output.py          # NEW — FinalSignalOutput (SIG-01)
├── graph/
│   ├── review_deps.py            # NEW — ReviewDeps frozen dataclass
│   ├── nodes.py                  # ADD: output_node, human_review_node, review_store_node,
│   │                             #      route_before_review
│   └── pipeline.py               # EXTEND: with_output, with_review, review_deps kwargs
├── scripts/
│   ├── run_analysis.py           # NEW CLI (first user-facing deliverable)
│   └── audit_reconstruct.py      # NEW CLI — SIG-04 trace reconstruction
config/
├── risk_policy.yaml              # existing
└── review_policy.yaml            # NEW — conviction_threshold + review_prompt_template
tests/
├── review/                       # NEW — mirrors tests/risk/
│   ├── test_review_policy.py     # sha + YAML + extra="forbid"
│   └── fixtures/
│       └── review_policy_sample.yaml
├── output/                       # NEW
│   ├── test_final_signal.py      # SIG-01 no-null + assembler
│   ├── test_portfolio_view.py    # SIG-02 ranking + grouping + freshness
│   └── test_formatter.py
├── graph/
│   ├── test_review_node.py       # interrupt fires / does not fire at threshold
│   └── test_output_node.py       # assembly correctness + state-update immutability
└── integration/
    ├── test_phase8_e2e.py        # end-to-end: above-threshold pauses, below passes through,
    │                             #             VETOED never reaches review, backcompat regression
    └── test_audit_reconstruction.py # SIG-04: given episodic_id, can we rebuild trace?
```

### Pattern 1: LangGraph `interrupt()` — the canonical HITL primitive

**What:** `langgraph.types.interrupt(value: Any) -> Any` — inside a node, raises `GraphInterrupt`, halts execution, surfaces `value` to caller as `result["__interrupt__"]`. Caller resumes via `graph.ainvoke(Command(resume=V), config)`. Node re-executes from its start; `interrupt(...)` returns `V`.

**When to use:** Every time we need a human decision mid-graph. Phase 8 SIG-03 is the textbook example.

**Example (verified from Context7 `/websites/langchain_oss_python_langgraph`):**

```python
# Source: https://docs.langchain.com/oss/python/langgraph/interrupts
from langgraph.types import interrupt, Command

def human_review_node(state):
    review_request = {
        "ticker": state["ticker"],
        "signal": state["final_signal"],  # FinalSignalOutput dict
        "thesis": state["thesis"],
        "debate": {
            "bull_case": state["bull_case"],
            "bear_case": state["bear_case"],
            "rebuttal": state["rebuttal"],
            "final_arguments": state["final_arguments"],
            "synthesis": state["debate_synthesis"],
        },
        "risk_assessment": state["risk_assessment"],
        "episodic_hits": state.get("episodic_hits", []),
        "beliefs_consulted": state.get("beliefs_consulted", []),
    }
    decision = interrupt(review_request)  # PAUSES HERE — raises GraphInterrupt
    # When resumed with Command(resume={"status": "APPROVED", ...}),
    # `decision` holds that dict.
    return {"review_decision": decision}

# Caller:
config = {"configurable": {"thread_id": "analysis-aapl-2026-04-22"}}
initial = await graph.ainvoke({"ticker": "AAPL", "as_of_date": "2026-04-22"}, config=config)
# initial["__interrupt__"] -> [Interrupt(value=review_request)]

# Reviewer decides:
final = await graph.ainvoke(
    Command(resume={"status": "APPROVED", "reviewer_id": "maxzou",
                    "reviewer_note": "thesis holds; cleared."}),
    config=config,
)
# final["review_decision"] -> {"status": "APPROVED", ...}
```

**Critical requirements:** a checkpointer MUST be attached (`builder.compile(checkpointer=saver)`); without one, `interrupt()` raises at runtime. The same `thread_id` links the initial invoke and the resume — this is the persistent cursor.

[VERIFIED: .venv install + Context7 docs + `src/langgraph/types.py::interrupt`]

### Pattern 2: Conditional route — pause only above threshold

`route_before_review` is a `Callable[[State], Literal[...]]` wired via `add_conditional_edges`:

```python
def route_before_review(state: DebatePipelineState) -> Literal["human_review", "review_store"]:
    """Pause-or-skip router. When conviction < threshold, bypass the review node
    entirely — no interrupt fires, signal is finalized with review_status=NOT_REQUIRED.
    Fails CLOSED when review_policy or signal missing (routes to review_store with
    a stamped error, never silently auto-approves).
    """
    signal = state.get("final_signal") or {}  # assembled by output_node
    threshold = state.get("_review_threshold")  # closure-bound by pipeline builder
    conviction = signal.get("conviction")
    if threshold is None or conviction is None:
        # Fail-closed: do NOT auto-approve when we can't compare
        return "human_review"
    return "human_review" if conviction >= threshold else "review_store"

# In build_debate_pipeline (new branch when with_review=True):
builder.add_edge("output", "_route_before_review")
builder.add_conditional_edges(
    "output",
    route_before_review,
    {"human_review": "human_review", "review_store": "review_store"},
)
builder.add_edge("human_review", "review_store")
builder.add_edge("review_store", "episodic_store")
```

Mirror of `route_after_risk` in `nodes.py` — fail-closed. Pitfall 7 from Phase 6 applies verbatim.

### Pattern 3: `ReviewPolicy` + SHA — byte-for-byte mirror of `RiskPolicy`

```python
# src/ai_hedge_fund/review/policy.py
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_REVIEW_POLICY_PATH: Path = Path("config/review_policy.yaml")

class ReviewPolicy(BaseModel):
    """Human-editable review gating rules.

    Frozen + extra='forbid': policy instances immutable; unknown YAML keys
    raise ValidationError before the pipeline runs (T-08-01 analogue).
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    conviction_threshold: int = Field(
        ge=0, le=100, default=70,
        description="Signals with conviction >= this value require human review",
    )
    review_prompt_template: str = Field(
        default="Review required: {ticker} conviction {conviction}. Approve (y) or reject (n)?",
        min_length=1,
        description="stdin prompt shown to the reviewer",
    )
    reviewer_id_default: str | None = Field(
        default=None,
        description="Optional default reviewer id (falls back to OS user on CLI)",
    )

def load_review_policy(path: Path | str = DEFAULT_REVIEW_POLICY_PATH) -> ReviewPolicy:
    text = Path(path).read_text()
    data = yaml.safe_load(text)
    return ReviewPolicy.model_validate(data)

def compute_review_policy_sha(policy: ReviewPolicy) -> str:
    canonical = json.dumps(policy.model_dump(mode="json"),
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

Audit properties identical to `RiskPolicy` — three-way SHA equality test replicated with `review_policy_sha`.

### Pattern 4: `ReviewDeps` — byte-for-byte mirror of `MemoryDeps` / `RiskDeps`

```python
# src/ai_hedge_fund/graph/review_deps.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.orm import Session
    from ai_hedge_fund.review.policy import ReviewPolicy

@dataclass(frozen=True)
class ReviewDeps:
    """Immutable deps for human_review_node + review_store_node.

    Attributes:
        db_session: SQLAlchemy session for the review-decision append.
        policy: Pre-loaded ReviewPolicy (preferred — computed SHA cached).
        policy_path: Alternative to `policy` when the loader should read YAML
            on pipeline build. Either-or: ValueError if both or neither.
        reviewer_io: Callable[[dict], dict] invoked by human_review_node to
            obtain the reviewer's decision. Default: CLI stdin prompt.
            Tests inject a stub returning {'status': 'APPROVED', ...}.
    """
    db_session: Session
    policy: ReviewPolicy | None = None
    policy_path: Path | None = None
    # reviewer_io is actually NOT used directly — human_review_node uses
    # interrupt() which pauses the graph. reviewer_io is for the CLI-side
    # resumer, not for the node itself. See CLI Entry Point section.
```

**IMPORTANT clarification:** `human_review_node` does NOT read stdin. It calls `interrupt()` and PAUSES. The CLI caller handles stdin read and calls `ainvoke(Command(resume=...))`. This keeps the node pure and testable (tests skip stdin entirely — they resume with a stub decision dict).

### Pattern 5: Portfolio view — pure query, always fresh

```python
# src/ai_hedge_fund/output/portfolio_view.py
from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from ai_hedge_fund.db.models import EpisodicMemory
from ai_hedge_fund.memory.episodic import _normalise_as_of

def query_portfolio_view(
    db_session: Session,
    *,
    as_of_date: str | date | datetime,
    sector: str | None = None,
    limit_per_sector: int = 50,
) -> dict[str, list[dict[str, Any]]]:
    """Return a ranked portfolio view as {sector: [entry, entry, ...]}.

    For each ticker, takes the LATEST record_type='analysis' row visible
    as of as_of_date. Ranks within each sector by confidence DESC,
    as_of_date DESC. No caching — the append-only table means each call
    reflects current truth (SIG-02 freshness invariant).

    Args:
        db_session: Open SQLAlchemy session.
        as_of_date: Temporal cutoff; rows after this are not returned
            (SIG-02 must never leak future data).
        sector: Optional sector filter.
        limit_per_sector: Max tickers per sector (DoS cap).

    Returns:
        Sector-keyed dict; each value is a list of entries
        {ticker, conviction, direction, thesis_summary, as_of_date,
         episodic_id, policy_sha}.
    """
    target = _normalise_as_of(as_of_date)
    # Latest-per-ticker via window function or max-group-by; for SQLite
    # compatibility use the simple approach: select all relevant rows,
    # then pick the latest per ticker in Python (DB has O(100-1000) rows
    # for v1; premature optimization not needed).
    q = (
        select(EpisodicMemory)
        .where(EpisodicMemory.record_type == "analysis")
        .where(EpisodicMemory.as_of_date <= target)
        .order_by(EpisodicMemory.ticker, EpisodicMemory.as_of_date.desc())
    )
    if sector is not None:
        q = q.where(EpisodicMemory.sector == sector)
    rows = db_session.scalars(q).all()

    # Pick latest row per ticker
    latest_by_ticker: dict[str, EpisodicMemory] = {}
    for row in rows:
        if row.ticker not in latest_by_ticker:
            latest_by_ticker[row.ticker] = row

    # Group by sector, rank by confidence DESC, as_of_date DESC
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in latest_by_ticker.values():
        payload = row.payload or {}
        entry = {
            "ticker": row.ticker,
            "sector": row.sector,
            "conviction": row.confidence or 0,
            "direction": row.signal_direction,
            "thesis_summary": (payload.get("thesis") or {}).get("bull_case"),
            # Use one-paragraph derived summary; formatter builds this
            "as_of_date": row.as_of_date.isoformat() if hasattr(row.as_of_date, "isoformat") else str(row.as_of_date),
            "episodic_id": row.id,
            "policy_sha": row.policy_sha,
        }
        grouped[row.sector].append(entry)

    # Rank within each sector
    for s, entries in grouped.items():
        entries.sort(key=lambda e: (e["conviction"], e["as_of_date"]), reverse=True)
        grouped[s] = entries[:limit_per_sector]

    return dict(grouped)
```

**Freshness property (SIG-02):** after `build_debate_pipeline(...).ainvoke(...)` completes, a subsequent call to `query_portfolio_view(db_session, as_of_date=...)` returns the new analysis row. Zero cache invalidation — the append-only table IS the cache.

### Pattern 6: `human_review_node` — calls interrupt, node itself is testable without stdin

```python
# src/ai_hedge_fund/graph/nodes.py (NEW function)
from langgraph.types import interrupt

async def human_review_node(state: DebatePipelineState) -> dict:
    """Pause the pipeline and present the review request to the caller.

    The caller (CLI or test harness) resumes with Command(resume=decision),
    where `decision` is a ReviewDecision dict. This node does NOT read
    stdin — stdin handling is the CLI's job. The node's only responsibility
    is to package the review request + validate the resume value.
    """
    if state.get("error"):
        return {}
    signal = state.get("final_signal")
    if signal is None:
        return {"error": "No final_signal available for review"}

    # Package the review request — this is what the caller sees
    review_request = {
        "ticker": state["ticker"],
        "as_of_date": state["as_of_date"],
        "signal": signal,
        "thesis": state.get("thesis"),
        "debate": {
            "bull_case": state.get("bull_case"),
            "bear_case": state.get("bear_case"),
            "rebuttal": state.get("rebuttal"),
            "final_arguments": state.get("final_arguments"),
            "synthesis": state.get("debate_synthesis"),
        },
        "risk_assessment": state.get("risk_assessment"),
        "episodic_hits": state.get("episodic_hits", []),
        "beliefs_consulted": state.get("beliefs_consulted", []),
    }

    decision_raw = interrupt(review_request)  # <-- PAUSES HERE

    # Validate the resumed decision via Pydantic (no silent fallthrough)
    from ai_hedge_fund.review.decision import ReviewDecision
    decision = ReviewDecision.model_validate(decision_raw)
    logger.info("human_review_decision_received",
                ticker=state["ticker"], status=decision.status,
                reviewer_id=decision.reviewer_id)
    return {"review_decision": decision.model_dump()}
```

Where `ReviewDecision` is:

```python
# src/ai_hedge_fund/review/decision.py
from __future__ import annotations
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

class ReviewDecision(BaseModel):
    """Human reviewer's approve/reject + note. Append-only; never mutated.

    `review_policy_sha` is stamped by the CLI resumer (not the reviewer) so
    every persisted decision is attributable to the exact policy version
    that gated it — compliance audit requirement.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["APPROVED", "REJECTED"]
    reviewer_id: str = Field(min_length=1, max_length=64)
    reviewer_note: str = Field(min_length=1, max_length=2000)
    reviewed_at: datetime
    review_policy_sha: str = Field(min_length=64, max_length=64)
```

### Pattern 7: `review_store_node` — mirror of `episodic_store_node`, append-only

```python
async def review_store_node(state: DebatePipelineState, deps: ReviewDeps) -> dict:
    """Append a record_type='review' row linking back to the analysis row.

    Fires in three cases:
        1. Review was required AND occurred (APPROVED or REJECTED).
        2. Review was NOT required (conviction below threshold) -> stamps
           a record_type='review' row with status='NOT_REQUIRED' so the
           audit trail is uniform.
        3. VETOED path never reaches here (risk router ends graph earlier).
    """
    if state.get("error"):
        return {}

    decision = state.get("review_decision")
    linked_id = state.get("episodic_stored_id")
    as_of_dt = _normalise_as_of(state["as_of_date"])
    status = (decision or {}).get("status") or "NOT_REQUIRED"

    row = EpisodicMemory(
        ticker=state["ticker"],
        sector=(state.get("candidate_metadata") or {}).get("sector") or "Unknown",
        record_type="review",
        signal_direction=(state.get("final_signal") or {}).get("direction"),
        confidence=(state.get("final_signal") or {}).get("conviction"),
        outcome_pct=None,
        linked_analysis_id=linked_id,
        policy_sha=(state.get("risk_assessment") or {}).get("policy_sha"),
        as_of_date=as_of_dt,
        payload={
            "schema_version": 1,
            "review_status": status,
            "review_decision": decision,            # full reviewer_note etc
            "review_policy_sha": (decision or {}).get("review_policy_sha"),
            "linked_analysis_id": linked_id,
        },
    )
    deps.db_session.add(row)
    deps.db_session.commit()
    logger.info("review_store_complete",
                ticker=state["ticker"], review_status=status,
                linked_analysis_id=linked_id, review_row_id=row.id)
    return {"review_stored_id": row.id}
```

### Anti-Patterns to Avoid

- **Human review gate that logs a message instead of pausing.** `logger.warning("please review")` is NOT a review gate. Compliance failure. Pattern: must call `langgraph.types.interrupt()` inside a node. Verified: that's why CONTEXT.md marks this non-negotiable.
- **Optional/nullable fields on `FinalSignalOutput`.** Violates SIG-01. Every required field must have NO default None and must validate via Pydantic `Field(...)` with min_length / ge / le constraints. Test with `model_validate({})` asserting `ValidationError` on each field name.
- **Mutating the analysis row with the review decision.** Violates append-only. Review is a NEW row (`record_type='review'`, `linked_analysis_id=<analysis_id>`). Test: after review, the analysis row's `payload` and `signal_direction` are byte-for-byte unchanged.
- **Caching the portfolio view.** Violates SIG-02 "ranking updates when new analyses complete." Read at call time; rely on the append-only table for freshness. Test: run pipeline twice, assert view reflects the second run.
- **Review threshold bypass race.** Pattern: the review gate runs AFTER some external side effect. Mitigation: review is BEFORE the final_signal is returned to caller. No external side effect (broker call, file write) happens after the interrupt. V1 has no such side effects — enforce by code review that no new node downstream of review_store writes externally.
- **LLM authoring `review_policy_sha` / `risk_score` / decision status.** Tool-first invariant. All three are computed in Python. Test: `grep -r "llm.*risk_score" src/` returns zero matches; `grep -r "signal_agent.run.*risk_score" src/` too.
- **Review policy mutable at runtime.** Mitigation: `ReviewPolicy` is `frozen=True`. The `compute_review_policy_sha` is computed ONCE at pipeline build (stored in `ReviewDeps`) and stamped on every persisted decision. Any policy hot-swap requires a new pipeline build + new SHA.
- **Silent fallthrough on malformed review input.** Mitigation: `ReviewDecision.model_validate(decision_raw)` raises on any missing/invalid field. Test: resume with `Command(resume={"status": "MAYBE"})` raises `ValidationError`.
- **Embedding-based anything.** Belief memory rule — Phase 7 — carries forward. Audit trail must be human-readable (structlog events + JSONB payloads + Langfuse spans). No vector-store retrieval for review context.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Human-in-the-loop pause | Sentinel state + external poller | `langgraph.types.interrupt()` + `Command(resume=V)` | Proven primitive; handles checkpointing, re-entry semantics, multi-interrupt dispatch. [CITED: Context7 `/websites/langchain_oss_python_langgraph/interrupts`] |
| YAML policy with schema validation | Hand-rolled parser | `yaml.safe_load` + Pydantic `model_validate` with `extra="forbid"` | Phase 6 already shipped this pattern — proven. |
| Policy fingerprint / audit hash | Custom hashing | `hashlib.sha256(json.dumps(dump, sort_keys=True, separators=(",",":")).encode())` | `compute_policy_sha` in Phase 6 is the template. Deterministic, change-sensitive, idempotent — all three properties are tested. |
| Portfolio-view ranking + grouping | Materialized table + trigger | Plain SQLAlchemy query + Python `sorted(..., key=...)` | Append-only `episodic_memory` is already the store; zero cache invalidation needed. |
| Per-agent audit span capture | Custom tracing | Existing Langfuse `CallbackHandler` + existing structlog `logger.info(...input_tokens=, output_tokens=)` in every node | Already implemented Phase 1-7. |
| Conditional graph routing | Mutating graph at runtime | `add_conditional_edges` | Threat model T-05-19 / T-06-08 / T-07-22: graph topology is compile-time static. The conditional edge selects AMONG pre-declared targets; it does not mutate the graph. |
| CLI arg parsing | Hand-rolled | `argparse` (stdlib) | `scripts/ingest_outcome.py` is the template. Zero new dep. |

**Key insight:** Phase 8 has zero genuinely-new technical problems. It is 100% composition of Phase 6-7 patterns with a new primitive (`interrupt`) that LangGraph ships natively and is installed.

## Runtime State Inventory

Phase 8 is additive. It does not rename or refactor existing strings or stored data. **This section is SKIPPED — greenfield additions only.**

**Verified by:**
- No module renames (new subpackages `review/`, `output/`).
- No DB column renames or data migrations (adds new `record_type='review'` values to an existing column; does NOT require an Alembic migration because the column is a free-form `String(20)`).
- No YAML key renames in `risk_policy.yaml` (touches neither the file nor the schema).
- No environment variable renames.

## Common Pitfalls

### Pitfall A: Review gate that is a log line
**What goes wrong:** A node emits `logger.warning("please review this signal")` and the pipeline completes. The signal is finalized without human approval.
**Why it happens:** Developer writes convenience code believing "the human will read the log later."
**How to avoid:** MUST call `langgraph.types.interrupt()` inside `human_review_node`. Test: run the pipeline without a checkpointer → `GraphInterrupt` raises (proves the primitive is wired). Run with a checkpointer → `result["__interrupt__"]` is populated (proves it pauses).
**Warning signs:** `human_review_node` returns a dict WITHOUT calling `interrupt(...)`. Grep acceptance: `grep -c "interrupt(" src/ai_hedge_fund/graph/nodes.py` must be >= 1 inside `human_review_node`.

### Pitfall B: `FinalSignalOutput` with Optional fields
**What goes wrong:** `thesis_link: str | None = None` — a field that was supposed to be required silently defaults to None. SIG-01 violated.
**Why it happens:** Copy-paste from a Phase-5 schema that uses `str | None`.
**How to avoid:** `FinalSignalOutput` uses ONLY `Field(min_length=1, ...)` or `Field(ge=, le=)`; no `| None` on any required field; `ConfigDict(extra="forbid")`.
**Warning signs:** Unit test `FinalSignalOutput(...)` with any field omitted must raise `ValidationError`. Grep acceptance: `grep -c "= None" src/ai_hedge_fund/schemas/signal_output.py` is 0 on required fields.

### Pitfall C: Portfolio view caches stale data
**What goes wrong:** Someone adds `@lru_cache` to `query_portfolio_view` for speed. The view returns yesterday's ranking after today's analyses complete. SIG-02 violated.
**Why it happens:** Premature optimization.
**How to avoid:** Explicit "no caching" docstring on `query_portfolio_view`. Integration test: run pipeline, call `query_portfolio_view`, assert new row present; mutate a seed row via a second pipeline run, call view again, assert new ranking reflects the second row.
**Warning signs:** `@lru_cache` decorator anywhere in `src/ai_hedge_fund/output/`.

### Pitfall D: Review decision mutates the analysis row
**What goes wrong:** `episodic_store_node` re-runs after review and overwrites the original analysis row with the review decision. Append-only invariant violated.
**Why it happens:** Dev reuses `episodic_store_node` thinking "one row per analysis."
**How to avoid:** Review is a NEW row, `record_type='review'`, `linked_analysis_id=<analysis_id>`. Integration test: after review, the original analysis row's `payload` + `signal_direction` + `confidence` are byte-for-byte unchanged; a new row with `record_type='review'` exists.

### Pitfall E: Threshold bypass — review runs AFTER external side effect
**What goes wrong:** Hypothetical: a downstream node writes to a broker API before `human_review_node` pauses. The review fires AFTER the trade. Compliance catastrophe.
**Why it happens:** Nodes added out of topological order.
**How to avoid:** The review node is placed BEFORE any external side-effect node. V1 has no broker integration (explicitly out of scope per CONTEXT.md deferred list), so the only "side effect" is `episodic_store_node` — which is internal and idempotent. Enforce by topology review in `plan-check`. Documented in `build_debate_pipeline` docstring.
**Warning signs:** Any new node added between `human_review_node` and `episodic_store_node` that does I/O.

### Pitfall F: Review policy mutable at runtime → SHA drift
**What goes wrong:** Someone edits `config/review_policy.yaml` mid-run. Decisions persisted before + after use different thresholds but no SHA distinguishes them.
**Why it happens:** Policy hot-swap attempt.
**How to avoid:** `ReviewPolicy` is `frozen=True`. The CLI computes `compute_review_policy_sha(policy)` ONCE at pipeline build and stamps it on every persisted `ReviewDecision`. Three-way SHA equality test (like Phase 7 policy_sha): `state['review_decision']['review_policy_sha'] == row.payload['review_policy_sha'] == compute_review_policy_sha(policy)`.
**Warning signs:** No `review_policy_sha` field on `ReviewDecision` → test fails.

### Pitfall G: Audit trail technically complete but impossible to reconstruct
**What goes wrong:** Spans are in Langfuse, rows are in Postgres, structlog events are in files. Given an `episodic_id`, a compliance reviewer cannot assemble the full trail in one place. SIG-04 effectively violated even though every piece exists.
**Why it happens:** Ship the primitives, forget the reconstruction.
**How to avoid:** Ship `scripts/audit_reconstruct.py` as a Phase 8 deliverable. Input: `--episodic-id <N>`. Output: JSON with (1) the analysis row, (2) the review row (if any), (3) the Langfuse trace URL (derivable from `thread_id`), (4) all structlog events for that thread_id. Integration test: `test_audit_reconstruction.py` asserts the output contains all four.
**Warning signs:** No `audit_reconstruct.py` script in `src/ai_hedge_fund/scripts/` or its test.

### Pitfall H: VETOED signal reaches review
**What goes wrong:** A VETOED signal is routed to `human_review_node`, asking the human to "approve a rejected trade." Logically incoherent; may trick humans into overriding risk.
**Why it happens:** `route_before_review` forgets the VETOED case.
**How to avoid:** VETOED path already ends at `episodic_store` (Phase 6). `route_before_review` is ONLY reached via the APPROVED branch. Integration test: VETOED run never surfaces an `__interrupt__` (no pause); final state has no `review_decision`; analysis row persisted with `record_type='analysis'`; no `record_type='review'` row exists.

### Pitfall I: Checkpointer missing when `with_review=True`
**What goes wrong:** Pipeline built without a checkpointer but `with_review=True`. `interrupt()` is called, raises at runtime, pipeline crashes.
**Why it happens:** Dev wires `with_review=True` but forgets to pass `checkpointer=`.
**How to avoid:** `build_debate_pipeline(with_review=True, checkpointer=None)` raises `ValueError("with_review=True requires a checkpointer")`. Unit test.

### Pitfall J: Thread-id collisions between pipeline runs
**What goes wrong:** Two pipeline runs share a `thread_id`; the second run's `interrupt()` sees the first run's checkpoint and resumes incorrectly.
**Why it happens:** CLI uses a fixed thread_id.
**How to avoid:** CLI derives `thread_id` from `f"{ticker}-{as_of_date}-{uuid4().hex[:8]}"`. Unit-level: `scripts/run_analysis.py` test asserts two runs in the same session use distinct thread_ids.

## Code Examples

### SIG-01: Assemble `FinalSignalOutput` from authoritative state

```python
# src/ai_hedge_fund/output/signal.py
from __future__ import annotations
from ai_hedge_fund.schemas.signal_output import FinalSignalOutput

def assemble_final_signal(
    state: dict, *, review_policy_sha: str, episodic_id: int,
) -> FinalSignalOutput:
    """Assemble FinalSignalOutput from authoritative pipeline state.

    NO LLM invocation. Tool-first: risk_score derived, conviction copied
    from thesis.confidence, thesis_link = episodic://<id>.

    Raises:
        ValidationError: any required field missing from state
            (fails fast before the graph proceeds).
    """
    signal = state["signal"]           # Phase-5 SignalOutput dict
    thesis = state["thesis"]           # Post-debate ThesisOutput dict
    risk = state.get("risk_assessment") or {}

    return FinalSignalOutput(
        ticker=state["ticker"],
        as_of_date=state["as_of_date"],
        direction=signal["direction"],
        conviction=int(thesis["confidence"]),  # 0-100 integer
        thesis_summary=signal["thesis_summary"],
        risk_score=derive_risk_score(risk),
        thesis_link=f"episodic://{episodic_id}",
        policy_sha=risk.get("policy_sha") or "",
        review_policy_sha=review_policy_sha,
        episodic_id=episodic_id,
        review_status="NOT_REQUIRED",  # Overwritten later if review fired
    )

def derive_risk_score(risk_assessment: dict) -> int:
    """Deterministic Python; zero LLM. 0-100 integer."""
    status = risk_assessment.get("status")
    if status == "VETOED":
        return 100
    if status != "APPROVED":
        return 50  # unknown state -> middle-ground
    observed = risk_assessment.get("observed") or 0
    limit = risk_assessment.get("limit") or 1
    # Higher observed-vs-limit = higher risk
    ratio = min(1.0, max(0.0, float(observed) / max(float(limit), 1e-9)))
    return int(round(ratio * 100))
```

### SIG-03: Run pipeline with interrupt + resume (test fixture)

```python
# tests/integration/test_phase8_e2e.py (illustrative, not final)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

async def run_with_review(ticker, as_of_date, reviewer_decision):
    saver = InMemorySaver()
    graph = build_debate_pipeline(
        checkpointer=saver,
        with_memory=True, memory_deps=memory_deps,
        with_risk=True,   risk_deps=risk_deps,
        with_output=True,
        with_review=True, review_deps=review_deps,
    )
    config = {"configurable": {"thread_id": f"test-{ticker}-{as_of_date}"}}
    initial = {"ticker": ticker, "as_of_date": as_of_date,
               "candidate_metadata": {"sector": "Technology"}}

    first = await graph.ainvoke(initial, config=config)
    if first.get("__interrupt__"):
        # High-conviction signal — review required
        final = await graph.ainvoke(Command(resume=reviewer_decision), config=config)
    else:
        final = first  # below threshold — no pause
    return final
```

### SIG-04: Audit reconstruction stub

```python
# src/ai_hedge_fund/scripts/audit_reconstruct.py (illustrative)
def reconstruct(session, episodic_id: int) -> dict:
    analysis = session.get(EpisodicMemory, episodic_id)
    if analysis is None or analysis.record_type != "analysis":
        raise ValueError(f"No analysis row at id {episodic_id}")
    review = session.scalars(
        select(EpisodicMemory).where(
            EpisodicMemory.record_type == "review",
            EpisodicMemory.linked_analysis_id == episodic_id,
        ).order_by(EpisodicMemory.id.desc())
    ).first()
    return {
        "analysis_row": {
            "id": analysis.id, "ticker": analysis.ticker,
            "as_of_date": str(analysis.as_of_date),
            "policy_sha": analysis.policy_sha,
            "payload": analysis.payload,
        },
        "review_row": {
            "id": review.id, "status": (review.payload or {}).get("review_status"),
            "review_policy_sha": (review.payload or {}).get("review_policy_sha"),
            "payload": review.payload,
        } if review else None,
        "langfuse_trace_hint": {
            "thread_id": f"analysis-{analysis.ticker}-{analysis.as_of_date}",
            "instruction": "Search Langfuse by thread_id for the full per-agent span trail.",
        },
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LangGraph `interrupt_before=["node"]` compile flag for ALL pauses | `langgraph.types.interrupt(value)` inside the node (conditional, payload-bearing) | LangGraph 0.2 (stable in 1.x) | Phase 8 uses the in-node primitive because we need a CONDITIONAL pause (only above threshold) AND a payload (the review request). The compile-flag is still valid for unconditional pauses. [CITED: Context7 `/websites/langchain_oss_python_langgraph/interrupts`] |
| `result["__interrupt__"]` access in 0.x | Same key; also `result.interrupts` on newer `GraphOutput` objects | 1.0 stabilization | We use `result["__interrupt__"]` for compatibility; 1.1.6 installed supports both. |

**Deprecated/outdated:**
- Nothing deprecated relevant to Phase 8. The stack is current.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `conviction_threshold` default should be 70 | §ReviewPolicy | Threshold value is a policy choice, not a technical constraint. Operator-overridable via YAML. Low risk: if founder wants 80 or 60, one-line YAML edit. |
| A2 | `record_type='review'` in `episodic_memory` is preferred over a new `review_decisions` table | §Architecture | MEDIUM risk. Advantage: zero migration, reuses `linked_analysis_id` and `policy_sha` columns. Disadvantage: `record_type` column becomes 3-valued (`analysis`/`outcome`/`review`) — a small schema semantic overload. If a new table is preferred, planner must add an Alembic migration. |
| A3 | Review decisions are single-reviewer for v1 | §Deferred | CONTEXT.md explicitly defers multi-reviewer; low risk. |
| A4 | CLI uses blocking `input()` read after seeing `__interrupt__` | §CLI | CONTEXT.md defers TUI; low risk. |
| A5 | `thesis_link` is `episodic://<id>` (DB-dereferenced) rather than a filesystem path or URL | §SignalOutput | Low risk. The link is conceptual — any renderer can expand it. Filesystem paths bring path-escaping concerns (T-07-40-style); DB ref is cleaner. |
| A6 | Replace `SignalOutput`'s `conviction` field from `Literal["low","medium","high"]` to an integer via a NEW `FinalSignalOutput` schema, leaving Phase-5 `SignalOutput` unchanged | §SignalOutput Design | Low risk. Preserves all Phase 3/5 test byte-compatibility. SIG-01 requires integer 0-100; source is `thesis['confidence']` which IS already `int`. |
| A7 | Langfuse already captures input/output/model/tokens/timestamp per agent | §Audit Completeness | MEDIUM risk. The Langfuse `CallbackHandler` is documented to capture these, but we have not independently verified the captured fields against SIG-04's five required fields. Planner should add a Wave 0 task: "run pipeline against live Langfuse + inspect a trace + verify all 5 fields present; gap-fill with `handler.event(...)` calls if missing." |
| A8 | VETOED signals must NEVER reach human review | §Architecture | Low risk per RISK-01 ("veto is final"). Phase-6 `route_after_risk` already ends the graph on VETO. Phase 8 integration test asserts no `__interrupt__` on VETOED runs. |
| A9 | `risk_score` can be derived from `risk_assessment.observed / risk_assessment.limit` ratio | §SignalOutput | MEDIUM risk. The exact mapping is a design choice; any monotone increasing function is defensible. Planner may want to confirm with the founder. Default in this research is a simple clamped ratio * 100. |
| A10 | `thread_id` format for the pipeline `config` uniquely identifies a run for Langfuse trace lookup (for audit reconstruction) | §Audit Completeness | Low risk. Current Langfuse integration already uses `thread_id` as the persistent cursor. |

**Post-research actions for the planner:**
1. Confirm A1 (threshold=70) and A9 (risk_score formula) with user. If user defers, document the choice as a locked decision in the plan.
2. Add a Wave 0 task to verify A7 — inspect a live Langfuse trace and assert all 5 SIG-04 fields are present per span.
3. Decide A2 (episodic_memory row vs new table) explicitly in the plan.

## Open Questions (RESOLVED)

1. **Should `risk_score` be a Python-derived ratio or an additional advisory LLM field?**
   - RESOLVED: Python-derived. The risk_manager_agent already produces a `rationale` (RationaleOnly) and asking it to also produce a `risk_score` breaks the tool-first invariant. Ship the clamped `max(size / max_single_position_pct, corr_frac, dd_frac) * 100` formula as the default (planner locks this in 08-01; see assumption A9). Future calibration is a later plan.

2. **Does Langfuse already capture `reasoning` per-agent or only `output`?**
   - RESOLVED: Verify in Wave 0 and gap-fill if needed. 08-00 Task 3 ships the Langfuse span-coverage smoke test covering input/output/model/tokens/duration/timestamp per span. If any agent span is missing a SIG-04 field, Wave 0 fails and 08-00 gap-fills structlog with `result.output.model_dump()` on each node (most nodes already do this).

3. **How long does a review interrupt wait before timing out?**
   - RESOLVED: No timeout in v1. The CLI is blocking and the reviewer is attended. If the reviewer walks away, the pipeline state sits in the checkpointer (PostgresCheckpointer in prod, InMemorySaver in tests) and can be resumed later with the same `thread_id`. Multi-reviewer / async approval workflow deferred per CONTEXT.md `<deferred>`.

4. **Should the CLI write the review request to a file so the reviewer can open it in an editor?**
   - RESOLVED: Print a 30-line Markdown summary to stdout AND write the full JSON to `/tmp/review-<thread_id>.json` with the path printed. Reviewer can open the JSON in an editor if they want full detail. Plan 08-04 specifies both paths in the CLI action.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| langgraph.types.interrupt | SIG-03 | ✓ | 1.1.6 | — |
| langgraph.types.Command | SIG-03 | ✓ | 1.1.6 | — |
| langgraph.checkpoint.memory.InMemorySaver | tests | ✓ | 1.1.6 | — |
| langgraph-checkpoint-postgres | production checkpointer | ✓ | 3.0+ (per `pyproject.toml`) | Falls back to InMemorySaver for dev (loses durability) |
| PostgreSQL (live) | production run (checkpointer + episodic_memory) | assumed ✓ (docker-compose in repo) | 16+ | In-memory SQLite for tests |
| pydantic | schemas | ✓ | 2.12+ | — |
| PyYAML (transitive via yaml.safe_load) | review_policy load | ✓ (transitive, same as risk policy) | — | — |
| pydantic_ai.models.test.TestModel | agent stubbing in tests | ✓ | 1.0+ | — |
| structlog | per-node events | ✓ | 25.0+ | — |
| langfuse | audit spans (SIG-04) | ✓ | 4.0+ | Graceful degradation: pipeline runs without Langfuse if env vars absent — structlog + DB still provide audit trail per `langfuse.py:create_langfuse_handler` pattern |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None (all deps present).

## Validation Architecture

Nyquist validation enabled (`workflow.nyquist_validation: true`, `workflow.nyquist_validation` default since absent = enabled).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0+ + pytest-asyncio 1.0+ (auto mode) |
| Config file | `pyproject.toml [tool.pytest.ini_options]` (`asyncio_mode = "auto"`, `testpaths = ["tests"]`) |
| Quick run command | `uv run --no-sync pytest tests/review tests/output tests/graph/test_review_node.py tests/graph/test_output_node.py -q` |
| Full suite command | `uv run --no-sync pytest -q` (920+ tests after Phase 8; should complete in ~20-30s) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SIG-01 | `FinalSignalOutput` rejects missing `thesis_link` | unit | `uv run --no-sync pytest tests/output/test_final_signal.py::test_rejects_missing_thesis_link -x` | ❌ Wave 0 |
| SIG-01 | `FinalSignalOutput` rejects `conviction=-1` and `conviction=101` | unit | `uv run --no-sync pytest tests/output/test_final_signal.py::test_conviction_range -x` | ❌ Wave 0 |
| SIG-01 | `FinalSignalOutput` rejects extra keys (`extra="forbid"`) | unit | `uv run --no-sync pytest tests/output/test_final_signal.py::test_rejects_extra_keys -x` | ❌ Wave 0 |
| SIG-01 | `assemble_final_signal` produces a valid `FinalSignalOutput` from realistic state | unit | `uv run --no-sync pytest tests/output/test_final_signal.py::test_assembler_happy_path -x` | ❌ Wave 0 |
| SIG-01 | `derive_risk_score` is deterministic and bounded to [0,100] | unit | `uv run --no-sync pytest tests/output/test_final_signal.py::test_derive_risk_score_bounds -x` | ❌ Wave 0 |
| SIG-02 | `query_portfolio_view` ranks by conviction DESC | unit | `uv run --no-sync pytest tests/output/test_portfolio_view.py::test_ranks_by_conviction -x` | ❌ Wave 0 |
| SIG-02 | `query_portfolio_view` groups by sector | unit | `uv run --no-sync pytest tests/output/test_portfolio_view.py::test_groups_by_sector -x` | ❌ Wave 0 |
| SIG-02 | `query_portfolio_view` reflects new analysis immediately (no cache) | integration | `uv run --no-sync pytest tests/output/test_portfolio_view.py::test_freshness_after_new_row -x` | ❌ Wave 0 |
| SIG-02 | `query_portfolio_view` respects `as_of_date` temporal filter | unit | `uv run --no-sync pytest tests/output/test_portfolio_view.py::test_temporal_cutoff -x` | ❌ Wave 0 |
| SIG-03 | Interrupt fires when conviction ≥ threshold | integration | `uv run --no-sync pytest tests/integration/test_phase8_e2e.py::test_interrupt_fires_above_threshold -x` | ❌ Wave 0 |
| SIG-03 | Interrupt does NOT fire when conviction < threshold | integration | `uv run --no-sync pytest tests/integration/test_phase8_e2e.py::test_no_interrupt_below_threshold -x` | ❌ Wave 0 |
| SIG-03 | Resume with APPROVED produces final state | integration | `uv run --no-sync pytest tests/integration/test_phase8_e2e.py::test_resume_approved -x` | ❌ Wave 0 |
| SIG-03 | Resume with REJECTED finalizes as rejected; signal not added to portfolio actions | integration | `uv run --no-sync pytest tests/integration/test_phase8_e2e.py::test_resume_rejected -x` | ❌ Wave 0 |
| SIG-03 | VETOED signals never reach review (no `__interrupt__`) | integration | `uv run --no-sync pytest tests/integration/test_phase8_e2e.py::test_vetoed_never_reaches_review -x` | ❌ Wave 0 |
| SIG-03 | Malformed resume (bad schema) raises ValidationError | unit | `uv run --no-sync pytest tests/graph/test_review_node.py::test_malformed_resume -x` | ❌ Wave 0 |
| SIG-03 | `ReviewPolicy` `extra="forbid"` + YAML round-trip + sha determinism | unit | `uv run --no-sync pytest tests/review/test_review_policy.py -x` | ❌ Wave 0 |
| SIG-03 | `compute_review_policy_sha` — same policy → same SHA; one-field change → different SHA | unit | `uv run --no-sync pytest tests/review/test_review_policy.py::test_policy_sha_deterministic -x` | ❌ Wave 0 |
| SIG-03 | Review-policy SHA three-way equality: `state['review_decision']['review_policy_sha'] == row.payload['review_policy_sha'] == compute_review_policy_sha(policy)` | integration | `uv run --no-sync pytest tests/integration/test_phase8_e2e.py::test_review_policy_sha_three_way -x` | ❌ Wave 0 |
| SIG-03 | Review decision persisted as `record_type='review'` row; analysis row unchanged | integration | `uv run --no-sync pytest tests/integration/test_phase8_e2e.py::test_review_appends_new_row -x` | ❌ Wave 0 |
| SIG-03 | Pipeline with `with_review=True` + no checkpointer raises ValueError | unit | `uv run --no-sync pytest tests/graph/test_pipeline_review.py::test_requires_checkpointer -x` | ❌ Wave 0 |
| SIG-04 | Every agent node emits a structlog event with `input_tokens`, `output_tokens`, `total_tokens`, `ticker` | integration | `uv run --no-sync pytest tests/integration/test_phase8_e2e.py::test_structlog_coverage -x` | ❌ Wave 0 |
| SIG-04 | `audit_reconstruct(episodic_id)` returns analysis_row + review_row (if any) + thread_id hint | integration | `uv run --no-sync pytest tests/integration/test_audit_reconstruction.py -x` | ❌ Wave 0 |
| Backcompat | `build_debate_pipeline()` (no kwargs) compiles + runs the Phase-5 10-node topology | regression | `uv run --no-sync pytest tests/integration/test_phase7_e2e.py::test_phase5_backcompat_no_kwargs_still_compiles -q` | ✅ exists |
| Backcompat | `build_debate_pipeline(with_risk=True)` still passes 6 Phase-6 scenarios | regression | `uv run --no-sync pytest tests/integration/test_phase6_e2e.py -q` | ✅ exists |
| Backcompat | `build_debate_pipeline(with_memory=True, with_risk=True)` still passes Phase-7 8 scenarios | regression | `uv run --no-sync pytest tests/integration/test_phase7_e2e.py -q` | ✅ exists |
| Backcompat | `build_debate_pipeline(with_review=True, checkpointer=None)` raises ValueError | unit | `uv run --no-sync pytest tests/graph/test_pipeline_review.py::test_requires_checkpointer -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run --no-sync pytest tests/review tests/output tests/graph/test_review_node.py tests/graph/test_output_node.py -q` — narrow subsuite (<5 s)
- **Per wave merge:** `uv run --no-sync pytest tests/review tests/output tests/graph tests/integration/test_phase8_e2e.py -q` — ~10-20 s
- **Phase gate:** Full `uv run --no-sync pytest -q` green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/review/__init__.py` — new package
- [ ] `tests/review/conftest.py` — fixture producing a validated `ReviewPolicy` + temp policy path
- [ ] `tests/review/fixtures/review_policy_sample.yaml` — sample with threshold=70, reviewer_id_default="test"
- [ ] `tests/review/test_review_policy.py` — SHA + YAML + extra="forbid"
- [ ] `tests/output/__init__.py` — new package
- [ ] `tests/output/test_final_signal.py` — SIG-01 no-null + `derive_risk_score` + assembler
- [ ] `tests/output/test_portfolio_view.py` — ranking + grouping + freshness + temporal cutoff
- [ ] `tests/output/test_formatter.py` — markdown render of signal + review request
- [ ] `tests/graph/test_review_node.py` — interrupt primitive wiring + malformed resume
- [ ] `tests/graph/test_output_node.py` — assembler wiring + immutable update
- [ ] `tests/graph/test_pipeline_review.py` — `with_review` kwarg validation + checkpointer requirement
- [ ] `tests/integration/test_phase8_e2e.py` — six scenarios: above-threshold interrupt, below-threshold pass-through, APPROVED resume, REJECTED resume, VETOED no review, three-way SHA + append-only preservation
- [ ] `tests/integration/test_audit_reconstruction.py` — SIG-04 reconstructor smoke
- [ ] `tests/integration/conftest.py` — extend existing re-export shim to include review fixtures
- [ ] `config/review_policy.yaml` — production default (threshold=70, reviewer_id_default=null)
- [ ] Framework install: none (all deps already present)

## Security Domain

Security enforcement enabled (absent in config → enabled).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single-operator CLI; OS-level auth. Multi-reviewer consensus (V2) deferred per CONTEXT.md. |
| V3 Session Management | partial | LangGraph `thread_id` is a session cursor. Tests use fresh thread_id per run. Production: CLI generates `thread_id = f"{ticker}-{as_of_date}-{uuid4().hex[:8]}"`. |
| V4 Access Control | no | V1 is single-user (founder). Multi-user RBAC deferred. |
| V5 Input Validation | **yes** | Pydantic `ReviewPolicy` + `ReviewDecision` + `FinalSignalOutput` with `extra="forbid"`; `yaml.safe_load` exclusively (never `yaml.load`). |
| V6 Cryptography | partial | SHA-256 for policy fingerprinting (`hashlib` stdlib). No secrets encrypted at rest in Phase 8; secrets (`LANGFUSE_SECRET_KEY`, `ANTHROPIC_API_KEY`) already in `.env` per `config.py`. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| T-08-01 YAML RCE via `yaml.load` on review policy | Tampering | `yaml.safe_load` exclusively; `ReviewPolicy` has `extra="forbid"`. Mirrors T-06-01. |
| T-08-02 Review policy drift (different SHAs produce different decisions, no audit) | Repudiation | `compute_review_policy_sha` stamped on every persisted decision; three-way equality test (state + row.payload + recomputed from YAML). Mirrors T-06-04. |
| T-08-03 Silent review bypass (gate never fires) | Elevation of Privilege | Integration test asserts `__interrupt__` is populated when `conviction >= threshold`; failing test = gate bypass. |
| T-08-04 Malformed resume input accepted (e.g., `status="MAYBE"`) | Spoofing | `ReviewDecision.model_validate(resume_payload)` in `human_review_node`; raises `ValidationError` on any malformed input. |
| T-08-05 Review decision mutates analysis row (history rewrite) | Repudiation | Review is a NEW `record_type='review'` row linked by `linked_analysis_id`. Integration test asserts analysis row byte-identical before/after review. |
| T-08-06 Human reviewer attempts to override VETOED signal (override risk) | Elevation of Privilege | VETOED path is architecturally unreachable from review node; `route_after_risk` ends graph on VETO. |
| T-08-07 Audit trail reconstruction leaks sensitive data (e.g., reviewer_note containing PII) | Information Disclosure | `reviewer_note` max_length=2000; log events use `structlog` which can be redacted. For v1 no PII expected; documented for v2 hardening. |
| T-08-08 `thread_id` collision leaks one run's interrupt state to another | Tampering | CLI derives `thread_id` with `uuid4().hex[:8]` suffix; unit test asserts uniqueness. |
| T-08-09 Path traversal in `thesis_link` when dereferenced | Tampering | `thesis_link` is `episodic://<id>` — integer-keyed DB lookup; no filesystem paths involved. |
| T-08-10 Checkpointer data exposure (interrupt state persisted in Postgres) | Information Disclosure | Same mitigation as Phase 1-7: PG lives in private docker-compose network; existing `LANGFUSE_SECRET_KEY`-style .env protection applies. |

## Sources

### Primary (HIGH confidence)
- **LangGraph Python docs (via Context7, `/websites/langchain_oss_python_langgraph`):**
  - `/interrupts` page: `interrupt()` primitive, `Command(resume=...)`, checkpointer requirement, full review-and-edit example, multi-interrupt resume-map
  - `/test` page: Partial execution + interrupt test pattern (InMemorySaver + `update_state` + `interrupt_after`)
  - `/thinking-in-langgraph` page: Test Agent with Human Review Interrupt example
- **LangGraph 1.1.6 source (installed):** `langgraph/types.py::interrupt` docstring confirming exact signature (verified at `.venv/lib/python3.13/site-packages/langgraph/types.py:705`). `langgraph/graph/state.py::compile(interrupt_before, interrupt_after)` verified at lines 1044-1110.
- **Project codebase (Phase 1-7, verified via Read):**
  - `src/ai_hedge_fund/graph/pipeline.py` — `build_debate_pipeline` shape and kwarg-only guards
  - `src/ai_hedge_fund/graph/nodes.py` — node patterns (`route_after_risk`, `episodic_store_node`, structlog events) and tool-first policy_sha stamping
  - `src/ai_hedge_fund/risk/policy.py` — exact mirror for `ReviewPolicy`
  - `src/ai_hedge_fund/graph/memory_deps.py` / `risk_deps.py` — frozen dataclass deps pattern
  - `src/ai_hedge_fund/db/models.py::EpisodicMemory` — append-only table already ready for `record_type='review'`
  - `src/ai_hedge_fund/schemas/state.py::DebatePipelineState` — TypedDict pattern
  - `src/ai_hedge_fund/observability/langfuse.py` — graceful-degradation pattern
  - `src/ai_hedge_fund/scripts/ingest_outcome.py` — CLI template
  - `tests/integration/test_phase7_e2e.py` — 12-agent TestModel stubbing pattern
  - `tests/integration/test_policy_sha_audit.py` — three-way SHA equality pattern
- **Previous phase research / SUMMARY:**
  - `.planning/phases/07-memory-and-learning/07-05-SUMMARY.md` — phase-gate pattern (test-only commit on already-wired code)
  - `.planning/phases/06-risk-management/06-06-SUMMARY.md` — policy_sha audit scaffolding

### Secondary (MEDIUM confidence)
- `pyproject.toml` version pins — verified against installed packages via `importlib.metadata`

### Tertiary (LOW confidence)
- None. All Phase-8 claims trace to either an installed binary, an official doc page, or an existing Phase-1..7 code pattern.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages installed and imports verified in venv
- Architecture: HIGH — direct mirror of Phase 6/7 patterns, same codebase, same idioms
- Pitfalls: HIGH — every pitfall traces to an existing Phase 1-7 precedent or a documented LangGraph behaviour
- `interrupt` primitive semantics: HIGH — verified via both Context7 docs and source inspection
- `risk_score` derivation formula: MEDIUM — algorithm choice is a design decision; default is defensible but not unique

**Research date:** 2026-04-22
**Valid until:** 2026-05-22 (30 days — stack is stable; LangGraph 1.x is stable; no upstream changes expected in 30d window)
