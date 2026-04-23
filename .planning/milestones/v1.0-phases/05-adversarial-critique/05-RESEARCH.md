# Phase 5: Adversarial Critique — Research

**Researched:** 2026-04-21
**Domain:** Multi-agent adversarial debate over a pre-existing thesis, using PydanticAI + LangGraph
**Confidence:** HIGH

## Summary

Phase 5 adds a structured bull/bear debate to the multi-agent pipeline built in Phase 4. The debate consumes the `ThesisOutput` produced by `manager_node` plus the underlying `analyst_reports`, runs it through a strictly sequential 5-act protocol (Bull Case → Bear Case → Rebuttal → Final Arguments → Debate Synthesis), and emits a revised thesis plus a `quality_score` derived from three sub-scores (evidence strength, logical consistency, risk coverage).

The architecture is fully determined by constraints already in the codebase: REASONING tier for each debate agent (same justification already used for `manager_agent` — Opus for argument quality); zero tools per debate agent (same pattern as `manager_agent` and `signal_agent`, since every input is already in state); schema-enforced act outputs with `min_length` constraints (same pattern as `ThesisOutput.bull_case: list[ThesisPoint] = Field(min_length=3)`); and thin async node wrappers over each agent (same pattern as the five Phase-4 nodes in `src/ai_hedge_fund/graph/nodes.py`). The only genuinely new decision is whether to extend `MultiAgentPipelineState` or define a separate `DebatePipelineState` — research below recommends extension.

The 5-act protocol is not speculative — it is the exact protocol documented in the SAS paper (Sadhu/Patra/Basu, EMNLP FinNLP 2025), which is already cited in `.planning/research/MULTI_AGENT_TRADING_SYSTEMS.md` as the source of the "structured debate, not free-form" decision. SAS's protocol used a GPT-4o judge to prefer its output over single-agent and free-form-debate baselines. TradingAgents (arxiv 2412.20138) validated the bull/bear pattern but uses natural-language dialogue rather than structured acts — we are deliberately choosing SAS's structured form over TradingAgents' free-form form because our schema-validation success criterion requires it.

**Primary recommendation:** Flat sequential LangGraph extension over `MultiAgentPipelineState`, five new debate nodes chained manager → bull → bear → rebuttal → final → synthesis → signal, five new PydanticAI agents at REASONING tier with zero tools, deterministic `quality_score` computed in a Python helper (not LLM), and one new `TestModel`-driven integration test that extends the existing Phase-4 integration test's `override(...)` context manager to cover all 10 agents in the full pipeline.

## User Constraints (from CONTEXT.md)

### Locked Decisions

All implementation choices are at Claude's discretion — discuss phase was skipped per `workflow.skip_discuss=true`. Planner should use:

- ROADMAP phase 5 goal, success criteria, and 4 DEBATE-XX requirement definitions as the spec.
- Phase 4 patterns (specialist agent template, MultiAgentPipelineState with operator.add reducer, fan-out/fan-in topology, error-propagation-not-crash) as the architectural baseline to extend.
- Existing codebase conventions (ResearchDeps dep injection, get_<domain>_limits pattern, schema-enforced source_tool, thin node wrappers).
- The CLAUDE.md agent-development rules (tool-first for quant, structured debate only — no free-form chat, token budgets from day one).

### Architecturally likely choices (planner should validate)

- Bull and Bear are PydanticAI `Agent[None, ActOutput]` agents with zero tools — they read analyst reports + prior-act outputs from state, not from external tools. Debate is pure synthesis, like manager.
- Debate uses REASONING tier (Opus) — bull/bear argument quality is the highest-reasoning step after manager synthesis. Matches the justification already used for manager in 04-02.
- Each act produces its own Pydantic schema with `min_length` constraints on claims/rebuttals/risks — so missing content causes a validation error, satisfying success criterion 3.
- The 5-act flow is sequential (not parallel) because each act reads the previous act's output. This is a different graph shape from Phase 4's fan-out/fan-in.
- The new state extends `MultiAgentPipelineState` with debate-specific fields.

### Claude's Discretion

Everything above that isn't explicitly locked by ROADMAP requirements or CLAUDE.md rules.

### Deferred Ideas (OUT OF SCOPE)

- Multi-round debate (more than 1 rebuttal exchange): out of scope for v1. Single rebuttal act is sufficient for the "differs in 30% of runs" success criterion.
- Dynamic debate depth (stop early when agents converge): out of scope. Static 5-act flow per success criterion 3.
- Human-in-the-loop debate review: reserved for Phase 8 (Signal and Output) which is where human approval gates live.
- Jury / third-party judge agent: not needed — success criterion 4 is a `quality_score`, not a win/lose judgment.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEBATE-01 | Bull Advocate agent presents investment case using analyst evidence | `bull_agent` section below; schema `BullCase` with `list[BullClaim]` each requiring `source_analyst` citation (mirrors `ThesisPoint.source_tool`); system prompt requires references to specific analyst data points. |
| DEBATE-02 | Bear Advocate agent presents opposing case with counter-evidence | `bear_agent` section below; schema `BearCase` with `list[BearClaim]` AND a separate `addressed_bull_claims: list[str] = Field(min_length=2)` — the min_length=2 IS the enforcement mechanism for success criterion 2. |
| DEBATE-03 | Structured 5-act debate protocol (thesis → counter-thesis → rebuttal → final arguments → synthesis) with each act producing a structured output | Sequential LangGraph chain of 5 nodes, each wrapping a typed `Agent[Deps, ActOutput]`; min_length constraints on every substantive field guarantee "skipping or empty act" → `ValidationError` from PydanticAI's output validator. |
| DEBATE-04 | Thesis quality scoring based on evidence strength, logical consistency, and risk coverage | `DebateSynthesis` schema has `evidence_strength`, `logical_consistency`, `risk_coverage` sub-scores (int 0-100 each, LLM-produced), plus a `quality_score` computed deterministically in Python (weighted mean) in a helper function — NOT by the LLM, per CLAUDE.md tool-first rule. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Bull advocacy (turn the thesis into a maximally-supported buy case) | **Agent Logic (PydanticAI)** | — | Pure synthesis over already-validated state inputs. No data retrieval needed; no tier crossing. |
| Bear advocacy (counter the bull case by rebutting specific claims) | **Agent Logic (PydanticAI)** | — | Same as above. `addressed_bull_claims` min_length=2 is a schema constraint, not an orchestration concern. |
| Rebuttal (bidirectional address of opponent's strongest points) | **Agent Logic (PydanticAI)** | — | Pure synthesis; reads bull + bear from state. |
| Final arguments (each side's closing with citation counts) | **Agent Logic (PydanticAI)** | — | Pure synthesis; reads bull/bear/rebuttal from state. |
| Debate synthesis (produce revised ThesisOutput + sub-scores) | **Agent Logic (PydanticAI)** | — | Pure synthesis; reads all prior acts. Sub-scores are LLM-produced qualitative judgments. |
| `quality_score` computation from sub-scores | **Tools (pure Python)** | — | CLAUDE.md: "Tool-first for quantitative work. LLMs NEVER compute financial ratios, run backtests, or calculate position sizes directly." A weighted mean is a quantitative computation and MUST be a Python function. |
| 5-act ordering and state passing | **Orchestration (LangGraph)** | — | Sequential `add_edge` chain in `build_debate_pipeline` / extended `build_multi_agent_pipeline`. |
| Budget enforcement per debate agent | **Agent Logic (PydanticAI)** via `UsageLimits` | Orchestration-layer total cap | Per-agent caps via `get_<debate_role>_limits()`; pipeline-total cap via existing `PipelineBudgetTracker` (Phase 1). |
| Error propagation (budget exceeded mid-debate) | **Orchestration (LangGraph)** — set `error` field, short-circuit downstream nodes | — | Same idiom as Phase-4 `manager_node` / `multi_agent_signal_node`: node catches `UsageLimitExceeded`, returns `{"error": "..."}`, downstream nodes see `state.get("error")` and return `{}`. |

## Standard Stack

### Core

| Library | Version (verified) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-ai | 1.80.0 | Debate agents with typed act-output schemas | [VERIFIED: `uv pip show pydantic-ai`] Already the stack's agent layer; Phase 4 uses `Agent[None, ThesisOutput]` for the manager — bull/bear/rebuttal/final/synthesis follow the same shape. |
| langgraph | 1.1.6 | Sequential 5-node chain for debate orchestration | [VERIFIED: `uv pip show langgraph`] Already the stack's orchestration layer; pattern is `builder.add_edge("bull","bear")` five times. |
| pydantic | 2.12.0 | `min_length` constraints on act output fields | [VERIFIED: pyproject.toml] Enforces "skipping an act causes ValidationError" — success criterion 3. |
| langchain-anthropic | 1.4.0 | Claude Opus provider for REASONING tier | [VERIFIED: pyproject.toml] Already used by `manager_agent`; no new deps. |
| anthropic | 0.94.0 | Direct SDK | [VERIFIED: pyproject.toml] Already in stack. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | 25.0.0+ | Per-agent structured logging | Every debate node logs `{role}_complete` with input/output tokens, mirroring `manager_node`'s `manager_complete` event [CITED: `src/ai_hedge_fund/graph/nodes.py:421-427`]. |
| pytest-asyncio | 1.0+ | Async test fixtures | Already configured via `asyncio_mode = "auto"` in `pyproject.toml` [VERIFIED: pyproject.toml]. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Sequential chain of 5 nodes in the parent `StateGraph` | LangGraph subgraph (nested `StateGraph` for the debate acts, invoked as one node) | [CITED: docs.langchain.com/oss/python/langgraph/use-subgraphs] Subgraphs add value when you need independent teams, schema isolation, or reusability. We have none of those — a flat sequential chain has lower complexity overhead and makes the debate topology directly inspectable via `graph.get_graph().nodes` (same test pattern as `test_multi_agent_pipeline_has_all_five_nodes`). Recommendation: flat. |
| Separate `DebatePipelineState` | Extend `MultiAgentPipelineState` with optional debate fields | A separate state forces a subgraph or a manual state transform at the boundary. Extending MultiAgentPipelineState matches the Phase-4 pattern where `thesis` and `signal` are optional fields that get populated at different stages. Recommendation: extend. |
| TradingAgents natural-language debate dialogue | SAS 5-act structured protocol | TradingAgents paper says "natural language dialogue for n rounds" with a facilitator that "selects the prevailing perspective" [CITED: arxiv 2412.20138] — this directly violates success criterion 3 (schema-validated acts). SAS's structured protocol is the documented approach we committed to in PROJECT.md and `.planning/research/MULTI_AGENT_TRADING_SYSTEMS.md`. |
| LLM-computed `quality_score` as a single number | Deterministic weighted mean of three LLM-produced sub-scores | CLAUDE.md forbids LLMs computing quantitative scores. Sub-scores are qualitative judgments (LLM-appropriate); the aggregation is arithmetic (tool-only). |
| Multi-round rebuttal | Single rebuttal act | Explicitly deferred in CONTEXT.md. Single round is sufficient per success criterion 4 (just need confidence to differ in 30% of runs). |

**Installation:** No new dependencies. Everything is already in the lockfile.

**Version verification:**
```bash
uv pip show pydantic-ai      # 1.80.0 [VERIFIED 2026-04-21]
uv pip show langgraph         # 1.1.6 [VERIFIED 2026-04-21]
uv pip show langchain-anthropic  # 1.4.0 [VERIFIED 2026-04-21]
```

## Architecture Patterns

### System Architecture Diagram

```
MultiAgentPipelineState
       |
       v
  START (ticker, as_of_date)
       |
       +---> fundamental_node  --+
       |                         |
       +---> sentiment_node    --+--> [operator.add on analyst_reports]
       |                         |
       +---> technical_node    --+
                                 |
                                 v
                            manager_node
                         (produces thesis: ThesisOutput)
                                 |
                                 v        <-- NEW: Phase 5 begins here
                            bull_node
                         (produces bull_case: BullCase)
                                 |
                                 v
                            bear_node
                         (reads thesis + analyst_reports + bull_case;
                          produces bear_case: BearCase with
                          addressed_bull_claims min_length=2)
                                 |
                                 v
                            rebuttal_node
                         (reads bull_case + bear_case;
                          produces rebuttal: RebuttalAct with
                          bull_rebuttals + bear_rebuttals)
                                 |
                                 v
                          final_arguments_node
                         (reads all prior acts; produces
                          final_arguments: FinalArguments with
                          bull_closing + bear_closing)
                                 |
                                 v
                       debate_synthesis_node
                         (reads all prior acts; produces
                          debate_synthesis: DebateSynthesis with
                          revised_thesis + 3 sub-scores + computed
                          quality_score)
                                 |
                                 v        <-- Phase 5 ends here
                            signal_node
                         (reads REVISED thesis, not original)
                                 |
                                 v
                               END
```

Key data-flow notes:
- The post-Phase-4 `thesis` field is now an **input** to the debate, not the final output. After synthesis, the signal node reads `debate_synthesis.revised_thesis` (or a top-level `thesis` field overwritten by synthesis — see State Design).
- `analyst_reports` stays in state and is read by bull/bear for evidence grounding. Bull/bear do NOT re-fetch any data — they cite what's already in state.
- `operator.add` reducer applies only to `analyst_reports` (fan-in). Debate fields are single-writer, overwrite semantics — no reducer.

### Component Responsibilities

| File | New / Modified | Responsibility |
|------|----------------|----------------|
| `src/ai_hedge_fund/schemas/debate.py` | NEW | `BullCase`, `BearCase`, `RebuttalAct`, `FinalArguments`, `DebateSynthesis`, and their nested claim/rebuttal sub-models. Keep separate from `agents.py` (already 360+ lines) per "files under 800 lines, many small files" rule. |
| `src/ai_hedge_fund/schemas/state.py` | MODIFIED | Add `DebatePipelineState` extending or composing `MultiAgentPipelineState` — see State Design. |
| `src/ai_hedge_fund/agents/bull.py` | NEW | `bull_agent: Agent[None, BullCase]`, `BULL_SYSTEM_PROMPT`, `get_bull_limits() -> UsageLimits`, `format_analyst_evidence(reports, thesis) -> str` helper. |
| `src/ai_hedge_fund/agents/bear.py` | NEW | `bear_agent: Agent[None, BearCase]`, `BEAR_SYSTEM_PROMPT` (includes "you MUST directly address at least 2 specific bull claims by quoting their claim text"), `get_bear_limits()`, `format_bull_case_for_bear()` helper. |
| `src/ai_hedge_fund/agents/rebuttal.py` | NEW | `rebuttal_agent: Agent[None, RebuttalAct]`, system prompt requires balanced rebuttals (N bull-side rebuttals AND N bear-side rebuttals), `get_rebuttal_limits()`. |
| `src/ai_hedge_fund/agents/final_arguments.py` | NEW | `final_arguments_agent: Agent[None, FinalArguments]`, `get_final_arguments_limits()`. |
| `src/ai_hedge_fund/agents/debate_synthesis.py` | NEW | `debate_synthesis_agent: Agent[None, DebateSynthesis]` + `compute_quality_score(evidence_strength, logical_consistency, risk_coverage) -> int` pure Python helper. |
| `src/ai_hedge_fund/graph/nodes.py` | MODIFIED | Add 5 new async nodes: `bull_node`, `bear_node`, `rebuttal_node`, `final_arguments_node`, `debate_synthesis_node`. Each is a thin wrapper following the `manager_node` template (same try/except for `UsageLimitExceeded`, same immutable `return {field: model_dump()}` pattern). |
| `src/ai_hedge_fund/graph/pipeline.py` | MODIFIED | Option A: replace the `manager → signal` edge in `build_multi_agent_pipeline` with `manager → bull → bear → rebuttal → final → synthesis → signal`. Option B: add a new `build_debate_pipeline` alongside, keep `build_multi_agent_pipeline` as the pre-debate pipeline. Recommendation: Option B so Phase 4 tests are not forced to account for debate. |
| `src/ai_hedge_fund/agents/__init__.py` | MODIFIED | Re-export all 5 new agents + limit functions + helpers (same pattern as Phase 4). |
| `src/ai_hedge_fund/graph/__init__.py` | MODIFIED | Re-export 5 new nodes + `build_debate_pipeline`. |
| `src/ai_hedge_fund/schemas/__init__.py` | MODIFIED | Re-export 5 new debate schemas + nested types + `DebatePipelineState`. |
| `tests/unit/test_debate_schemas.py` | NEW | Validation tests: min_length enforcement, sub-score range enforcement, every field required. |
| `tests/unit/test_bull_agent.py` etc. (5 files) | NEW | Per-agent wiring tests (mirrors `test_manager_agent.py`). |
| `tests/unit/test_debate_nodes.py` | NEW | Per-node happy-path + error-propagation tests (mirrors `test_multi_agent_nodes.py`). |
| `tests/unit/test_quality_score.py` | NEW | Pure-function tests for `compute_quality_score` — boundary cases (all 0, all 100, weighted mean math). |
| `tests/integration/test_debate_pipeline.py` | NEW | Pipeline compilation / topology / TestModel end-to-end — mirrors `test_multi_agent_pipeline.py`. |

### Recommended Project Structure

```
src/ai_hedge_fund/
├── agents/
│   ├── __init__.py            # modified
│   ├── base.py
│   ├── manager.py             # UNTOUCHED
│   ├── bull.py                # NEW
│   ├── bear.py                # NEW
│   ├── rebuttal.py            # NEW
│   ├── final_arguments.py     # NEW
│   └── debate_synthesis.py    # NEW (includes compute_quality_score)
├── graph/
│   ├── __init__.py            # modified (re-exports)
│   ├── nodes.py               # modified (+5 async nodes)
│   └── pipeline.py            # modified (+build_debate_pipeline)
└── schemas/
    ├── __init__.py            # modified (re-exports)
    ├── agents.py              # UNTOUCHED
    ├── debate.py              # NEW (5 schemas + nested sub-models)
    └── state.py               # modified (+DebatePipelineState)
```

### Pattern 1: Debate Agent Template (cloned from manager.py)

**What:** Every debate agent follows the exact template in `src/ai_hedge_fund/agents/manager.py:55-65` — REASONING tier, typed output schema, retries=2, zero tools, dedicated system prompt requiring citations.

**When to use:** All 5 debate agents.

**Example:**
```python
# Source: clone of src/ai_hedge_fund/agents/manager.py lines 55-65
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.debate import BullCase

BULL_SYSTEM_PROMPT = (
    "You are the Bull Advocate. Your task: argue for this company as a buy.\n"
    "\n"
    "STRICT RULES:\n"
    "1. You are given analyst reports AND a preliminary thesis. Build your case "
    "ONLY from evidence in those inputs. Do not invent facts or reference data "
    "outside what you are given.\n"
    "2. Every claim you make MUST cite its source_analyst -- one of "
    "'fundamental', 'sentiment', or 'technical'. Claims without source_analyst "
    "will be rejected.\n"
    "3. Cite specific data points (numbers, dates, filing sections) -- vague "
    "claims like 'strong fundamentals' are forbidden.\n"
    "4. Produce at least 3 bull claims.\n"
    "5. You are advocating, not synthesizing -- present the strongest possible "
    "buy case. The Bear Advocate will counter you.\n"
)

bull_agent: Agent[None, BullCase] = Agent(
    ModelTier.REASONING.value,  # Opus — argument quality is high-reasoning work.
    output_type=BullCase,
    system_prompt=BULL_SYSTEM_PROMPT,
    retries=2,  # Retry on schema validation errors (missing source_analyst etc.)
)

def get_bull_limits() -> UsageLimits:
    """Return UsageLimits for the bull advocate (REASONING tier, Opus)."""
    return get_usage_limits(ModelTier.REASONING)
```

### Pattern 2: Debate Schema Template

**What:** Each act has its own top-level Pydantic model. Every substantive list field has `min_length`. Every "citation" field has `min_length=1` on the string, ensuring "empty citation" fails validation.

**When to use:** All 5 debate schemas.

**Example:**
```python
# Source: clone of src/ai_hedge_fund/schemas/agents.py ThesisPoint + ThesisOutput pattern

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

AnalystName = Literal["fundamental", "sentiment", "technical", "manager"]

class BullClaim(BaseModel):
    """One bull-side claim, grounded in a specific analyst's evidence."""
    claim: str = Field(min_length=1, description="The investment argument")
    evidence: str = Field(min_length=1, description="Specific data point supporting the claim")
    source_analyst: AnalystName = Field(description="Which analyst produced the evidence")

class BullCase(BaseModel):
    """DEBATE-01: the positive investment case."""
    ticker: str = Field(description="Stock ticker")
    claims: list[BullClaim] = Field(min_length=3, description="Bull claims (minimum 3)")
    headline: str = Field(min_length=1, description="One-sentence bull headline")

class BearClaim(BaseModel):
    """One bear-side claim — either counter-evidence or a rebuttal of a specific bull claim."""
    claim: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    source_analyst: AnalystName
    addresses_bull_claim: str | None = Field(
        default=None,
        description="The text of the bull claim this bear claim rebuts (None if independent)",
    )

class BearCase(BaseModel):
    """DEBATE-02: the opposing case, MUST rebut >= 2 bull claims."""
    ticker: str
    claims: list[BearClaim] = Field(min_length=3)
    addressed_bull_claims: list[str] = Field(
        min_length=2,
        description=(
            "Verbatim (or near-verbatim) text of bull claims that this bear case "
            "directly rebuts. Min 2 -- per DEBATE-02."
        ),
    )
    headline: str = Field(min_length=1)

# ... RebuttalAct, FinalArguments, DebateSynthesis follow the same pattern ...

class DebateSynthesis(BaseModel):
    """DEBATE-04: final output with revised thesis and decomposed quality score."""
    ticker: str
    revised_thesis: ThesisOutput = Field(
        description="Post-debate thesis -- may be identical to pre-debate or revised"
    )
    pre_debate_confidence: int = Field(ge=0, le=100)
    post_debate_confidence: int = Field(ge=0, le=100)
    evidence_strength: int = Field(ge=0, le=100, description="How strong is the evidence?")
    logical_consistency: int = Field(ge=0, le=100, description="How internally consistent?")
    risk_coverage: int = Field(ge=0, le=100, description="How well are risks covered?")
    quality_score: int = Field(
        ge=0, le=100,
        description=(
            "Computed (not LLM-generated) weighted mean of the three sub-scores. "
            "Populated by compute_quality_score() before this schema is written to state."
        ),
    )
    synthesis_notes: str = Field(min_length=1, description="Rationale for the revised thesis")
```

### Pattern 3: Deterministic Quality Score (tool-first)

**What:** `compute_quality_score` is a pure Python function. The LLM produces three sub-scores (qualitative judgments); Python produces the final number (arithmetic).

**When to use:** In `debate_synthesis_node`, AFTER the agent returns. Not inside the agent.

**Example:**
```python
# Source: new in src/ai_hedge_fund/agents/debate_synthesis.py

def compute_quality_score(
    evidence_strength: int,
    logical_consistency: int,
    risk_coverage: int,
) -> int:
    """Compute thesis quality_score as a weighted mean of three sub-scores.

    Weights reflect relative importance for downstream signal generation:
        - evidence_strength: 0.4 (citations and data grounding matter most)
        - logical_consistency: 0.3 (internal coherence)
        - risk_coverage: 0.3 (risk-factor completeness)

    All inputs must be in [0, 100]. Output is rounded to int in [0, 100].

    CLAUDE.md: "LLMs NEVER compute financial ratios, run backtests, or
    calculate position sizes directly." Weighted-mean aggregation is a
    quantitative computation; this function is the tool the LLM does not
    have access to.
    """
    if not (0 <= evidence_strength <= 100):
        raise ValueError(f"evidence_strength out of range: {evidence_strength}")
    if not (0 <= logical_consistency <= 100):
        raise ValueError(f"logical_consistency out of range: {logical_consistency}")
    if not (0 <= risk_coverage <= 100):
        raise ValueError(f"risk_coverage out of range: {risk_coverage}")
    score = (
        0.4 * evidence_strength
        + 0.3 * logical_consistency
        + 0.3 * risk_coverage
    )
    return round(score)
```

**Node integration:**
```python
# Source: new in src/ai_hedge_fund/graph/nodes.py

async def debate_synthesis_node(state: DebatePipelineState) -> dict:
    # ... agent.run(...) ...
    synthesis = result.output  # DebateSynthesis with quality_score=0 placeholder
    # Recompute quality_score deterministically -- NEVER trust the LLM's value.
    synthesis = synthesis.model_copy(update={
        "quality_score": compute_quality_score(
            synthesis.evidence_strength,
            synthesis.logical_consistency,
            synthesis.risk_coverage,
        )
    })
    # Overwrite thesis with revised_thesis so signal_node sees the debated version.
    return {
        "debate_synthesis": synthesis.model_dump(),
        "thesis": synthesis.revised_thesis.model_dump(),
    }
```

### Pattern 4: Sequential LangGraph Chain (already used; just extend)

**What:** Five new `add_edge` calls chain the debate nodes. No conditional routing, no parallel fan-out inside the debate.

**When to use:** `build_debate_pipeline` (new builder).

**Example:**
```python
# Source: new in src/ai_hedge_fund/graph/pipeline.py, cloned from build_multi_agent_pipeline

def build_debate_pipeline(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    builder = StateGraph(DebatePipelineState)  # state extends MultiAgentPipelineState

    # Phase 4 topology (analysts -> manager) -- unchanged.
    builder.add_node("fundamental", fundamental_node)
    builder.add_node("sentiment", sentiment_node)
    builder.add_node("technical", technical_node)
    builder.add_node("manager", manager_node)

    # Phase 5 new nodes.
    builder.add_node("bull", bull_node)
    builder.add_node("bear", bear_node)
    builder.add_node("rebuttal", rebuttal_node)
    builder.add_node("final_arguments", final_arguments_node)
    builder.add_node("debate_synthesis", debate_synthesis_node)

    # Tail signal node uses a NEW adapter bound to DebatePipelineState.
    builder.add_node("signal", debate_signal_node)

    # Fan-out START -> 3 analysts (same as Phase 4).
    builder.add_edge(START, "fundamental")
    builder.add_edge(START, "sentiment")
    builder.add_edge(START, "technical")

    # Fan-in -> manager (same as Phase 4).
    builder.add_edge("fundamental", "manager")
    builder.add_edge("sentiment", "manager")
    builder.add_edge("technical", "manager")

    # NEW: sequential debate chain.
    builder.add_edge("manager", "bull")
    builder.add_edge("bull", "bear")
    builder.add_edge("bear", "rebuttal")
    builder.add_edge("rebuttal", "final_arguments")
    builder.add_edge("final_arguments", "debate_synthesis")
    builder.add_edge("debate_synthesis", "signal")
    builder.add_edge("signal", END)

    return builder.compile(checkpointer=checkpointer)
```

### Pattern 5: State Design — Extend MultiAgentPipelineState

**What:** Add debate fields directly; no reducer needed for the single-writer fields.

**When to use:** For `DebatePipelineState`.

**Example:**
```python
# Source: new in src/ai_hedge_fund/schemas/state.py, extending MultiAgentPipelineState

class DebatePipelineState(TypedDict, total=False):
    """State for the Phase-5 debate pipeline.

    Extends MultiAgentPipelineState fields without inheritance (TypedDict
    doesn't support multiple-inheritance cleanly for composition; repeat
    the fields). Reducer on analyst_reports is still operator.add because
    the fan-out is unchanged.

    Debate fields are single-writer (one node writes each). No reducer.
    Semantic: overwrite on write, absent until written.
    """
    ticker: Required[str]
    as_of_date: Required[str]
    analyst_reports: Annotated[list[dict], operator.add]
    thesis: dict | None  # written by manager; OVERWRITTEN by debate_synthesis_node.
    bull_case: dict | None
    bear_case: dict | None
    rebuttal: dict | None
    final_arguments: dict | None
    debate_synthesis: dict | None
    signal: dict | None
    error: str | None
```

**Why not separate pipeline state / subgraph:** See "Alternatives Considered" above. Flat + extended is lower complexity; sequential execution doesn't gain organization from subgraph boundaries [CITED: docs.langchain.com/oss/python/langgraph/use-subgraphs].

### Anti-Patterns to Avoid

- **Free-form debate chat.** [CITED: `.planning/research/MULTI_AGENT_TRADING_SYSTEMS.md` and CLAUDE.md "Structured debate only"] TradingAgents uses natural language dialogue; that directly violates success criterion 3. Our choice is SAS's structured form.
- **Bull/bear with tools.** They have zero reason to fetch data — evidence is already in `analyst_reports` and `thesis`. Giving them tools would let them re-derive metrics, risking inconsistency with the analysts' numbers. Same design as `manager_agent` and `signal_agent`.
- **LLM-computed `quality_score`.** Violates CLAUDE.md. LLMs are unreliable at arithmetic and will produce a number that doesn't actually correspond to the sub-scores they wrote. Use `compute_quality_score` and OVERWRITE the LLM's value.
- **Reducers on debate fields.** Each debate field is single-writer. Using `operator.add` on `bull_case` would accidentally let multiple writes accumulate and silently break the state contract.
- **Conditional early-exit based on "convergence."** Explicitly deferred in CONTEXT.md — the 5-act flow is static per success criterion 3.
- **`manager` → `signal` edge kept alongside `manager` → `bull` → … → `signal`.** Creates a diamond in the graph; LangGraph will see two paths to `signal` and the parallel-execution semantics will break sequencing. Either remove the direct edge (Option A) or create a NEW builder (Option B). Recommendation: Option B.
- **Reading pre-debate `confidence` from the synthesis-agent's own output.** Pre-debate confidence MUST be read from `state["thesis"]["confidence"]` (the manager's output) BEFORE `debate_synthesis_node` runs. Otherwise the agent could lie or copy the post-debate number, defeating success criterion 4.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Output schema validation | Custom `validate_bull_case(dict)` function | Pydantic `BaseModel` with `min_length=N` Field constraint | Pydantic raises `ValidationError` automatically on `agent.run()` output — this is what gives us success criterion 3 for free. [CITED: docs.pydantic.dev/latest/errors/validation_errors/] |
| Sequential node retry | Custom retry loop on `agent.run()` | `Agent(..., retries=2)` (already used by `manager_agent`) | PydanticAI's built-in retry loop hands the model back its own validation error so it can self-correct. [VERIFIED: `src/ai_hedge_fund/agents/manager.py:60`] |
| Token budget enforcement | Homemade token counter | `UsageLimits` + `agent.run(..., usage_limits=limits)` + `UsageLimitExceeded` handler (all already in use) | Same pattern as all Phase 1-4 nodes. [CITED: `src/ai_hedge_fund/agents/base.py:82-115`, `src/ai_hedge_fund/graph/nodes.py:423-431`] |
| "Did the agent skip an act?" check | Post-hoc assertions in the node | Pydantic `min_length` constraints on the agent's output_type | If the LLM produces a `BullCase` with 2 claims instead of 3, PydanticAI rejects the output at validation, triggers a retry (up to `retries=2`), and if still invalid raises `UnexpectedModelBehavior`. This is exactly success criterion 3's "causes a validation error." |
| "Did the bear rebut at least 2 bull claims?" check | Semantic NLP matching or string-similarity code | `addressed_bull_claims: list[str] = Field(min_length=2)` on `BearCase` | Force the bear agent to _list_ the bull claims it addresses. System prompt instructs the bear to literally copy the claim text. Validation catches "fewer than 2" as a schema error. |
| Deterministic-enough integration tests of the full debate | Real LLM calls | `TestModel` overrides on all 10 agents, `call_tools=[]` on the 3 analysts | Phase 4 integration test already uses this pattern [VERIFIED: `tests/integration/test_multi_agent_pipeline.py:181-189`]. TestModel produces schema-valid outputs (min_length satisfied with placeholder strings) — I verified this empirically: `BullCase(min_length=3)` → exactly 3 `BullClaim`s with all fields = "a". [VERIFIED: live repro in .venv on 2026-04-21] |

**Key insight:** Schema constraints + PydanticAI's retry + structured Agent outputs + TestModel is a closed system. You don't need any custom validation code for DEBATE-01 through DEBATE-03. Every enforcement mechanism is already in the framework — writing your own would be redundant and more fragile.

## Common Pitfalls

### Pitfall 1: Sycophancy / Debate Collapse
**What goes wrong:** Bear agent agrees with bull agent after seeing the bull case, especially if both are the same model (Opus). Documented in MAD literature [CITED: arxiv 2509.05396 "Talk Isn't Always Cheap" and arxiv 2509.23055 "Peacemaker or Troublemaker"] — agents have measurable conformity bias, and disagreement rate DECREASES as debate progresses.
**Why it happens:** Both agents share training data and tend toward consensus. Same-model debate has documented conformity.
**How to avoid:**
- Strong role priming in system prompts: "You are advocating, not synthesizing. The other side will counter you." Make the adversarial stance explicit.
- Hard schema constraints: `addressed_bull_claims: list[str] = Field(min_length=2)` forces the bear to actively rebut specific claims, not offer independent agreement.
- Consider: different role framings ("hedge-fund short seller" for bear; "growth-equity PM" for bull) give the model different personas that encourage disagreement.
- Evaluate: in phase UAT, sample 10 real-LLM debates and check that the bear case is actually contradicting the bull case, not restating it.
**Warning signs:** `post_debate_confidence == pre_debate_confidence` in 100% of runs (the debate isn't changing the assessment — this is exactly what success criterion 4 exists to detect). `bear_case.addressed_bull_claims` contains text that agrees with bull claims rather than rebuts them.

### Pitfall 2: Bull/Bear Inventing Data Outside the Analysts' Evidence
**What goes wrong:** Debate agent cites "market share of 32%" that no analyst reported.
**Why it happens:** Opus has strong priors from training data; without tool constraints it may pattern-match to what it "knows" about the ticker.
**How to avoid:**
- System prompt repeats CLAUDE.md's "strict temporal controls" and "every claim cites source_analyst" rules.
- Schema: `source_analyst: Literal["fundamental","sentiment","technical","manager"]` — enumerated, so the agent cannot cite a fake source.
- Give the agent the analyst reports verbatim in the user prompt via a helper like `format_analyst_reports()` (clone from manager.py).
- UAT sampling: cross-check a real-LLM debate's bull claims against the analyst reports — if a bull claim cites "fundamental" but the fundamental analyst didn't say it, that's a bug.
**Warning signs:** `evidence` text that doesn't appear in any analyst report. `source_analyst` always set to the same analyst regardless of what the evidence supports.

### Pitfall 3: Post-Debate Confidence = Pre-Debate Confidence (Success Criterion 4 Failure)
**What goes wrong:** Debate runs, sub-scores look reasonable, but `post_debate_confidence` is copy-pasted from `pre_debate_confidence`. 0% of runs change the assessment.
**Why it happens:** If the debate_synthesis agent is just asked "produce a revised thesis," and the debate was sycophantic (pitfall 1), the LLM defaults to the status-quo number.
**How to avoid:**
- System prompt explicitly: "You MUST re-evaluate confidence from scratch based on the debate. Do NOT default to the pre-debate value. If the debate strengthened the case, increase; if it exposed risk, decrease; if it was balanced, you may keep it but note that explicitly in synthesis_notes."
- Schema: `pre_debate_confidence` and `post_debate_confidence` are both required, different fields. Forces them to be typed separately — the LLM cannot merge them.
- Monitoring: log `post - pre` per run. If the distribution is 100% zeros, the debate is performative theater and success criterion 4 fails.
**Warning signs:** `abs(post_debate_confidence - pre_debate_confidence) == 0` in every real-LLM test run.

### Pitfall 4: LangGraph Diamond (Manager → Signal AND Manager → Bull)
**What goes wrong:** Developer keeps the Phase-4 `manager → signal` edge AND adds `manager → bull → … → signal`. LangGraph now sees two paths into `signal`; the signal node may run twice, or run before the debate completes, or both.
**Why it happens:** Incremental extension of the existing builder.
**How to avoid:**
- Option A: remove the `manager → signal` edge from `build_multi_agent_pipeline` (breaking change to Phase 4 tests).
- Option B (recommended): create a separate `build_debate_pipeline` that owns its own topology. Leave `build_multi_agent_pipeline` untouched so Phase-4 tests keep passing.
**Warning signs:** `signal_complete` fires twice per run. Topology test shows > 1 incoming edge to `signal` from `{manager, debate_synthesis}`.

### Pitfall 5: TestModel Passes All Tests, Real LLM Fails on min_length
**What goes wrong:** `TestModel` auto-generates `list[BullClaim]` with exactly `min_length=3` placeholder items — tests are green. In prod, real LLM produces 2 items because Opus under-fills the list → `ValidationError` → retry → `ValidationError` → `UnexpectedModelBehavior` at runtime.
**Why it happens:** TestModel is a schema-filler, not a realism-checker.
**How to avoid:**
- System prompt is explicit: "Provide AT LEAST 3 bull claims. Lists shorter than 3 will be rejected."
- `retries=2` on the agent — gives Pydantic's retry loop a chance to say "your previous output had 2 claims, min is 3; fix it."
- Include a real-LLM UAT script (deferred to phase UAT, gated behind env flag per Phase-4 precedent) that runs the full debate on a real ticker once and sanity-checks shapes.
**Warning signs:** `UnexpectedModelBehavior` at runtime on the `bull` node. Retry count stats show many retries on bull_node specifically.

### Pitfall 6: Budget Blowout on the Reasoning-Tier Debate
**What goes wrong:** Five Opus calls per debate run at REASONING tier (116k tokens each cap). Even at 20-30k tokens realized per call, that's 100-150k tokens per debate — significant cost. Pipeline-level budget tracker (`PipelineBudgetTracker` total_limit=500_000 [CITED: `src/ai_hedge_fund/agents/base.py:146`]) could be breached by debate alone.
**Why it happens:** Debate naturally generates long, argumentative text; REASONING tier has an `output_tokens_limit=16_000` that each act can approach.
**How to avoid:**
- Consider reducing `output_tokens_limit` for debate roles. Rebuttal and final_arguments could plausibly run at 4-8k output tokens each. Override via `get_usage_limits(ModelTier.REASONING, output_override=8_000)`.
- System prompts set explicit brevity: "Cap your response at 3-5 claims. Brevity is a feature."
- Raise `PipelineBudgetTracker.total_limit` for the debate pipeline to 1M (conservative given 10 agents at REASONING + ANALYSIS caps); or track usage per-pipeline and make the limit a per-pipeline config.
- Consider batch API for the 5 debate calls (50% cost discount) [CITED: anthropic pricing 2026] — but this is async and changes the latency profile; defer to Phase 8.
**Warning signs:** `BudgetExceededError` fires mid-debate. Langfuse cost trace shows one run > $1.

## Token Cost Estimate (for sizing `get_<role>_limits` and PipelineBudgetTracker)

Rough per-debate cost estimate based on Claude Opus 4.6 pricing [CITED: platform.claude.com/docs/en/about-claude/pricing, verified 2026-04-21]: **$5/Mtok input, $25/Mtok output**.

| Agent | Est. input tokens | Est. output tokens | Est. cost |
|-------|-------------------|--------------------|-----------|
| bull | 8-15k (thesis + 3 analyst reports) | 1-2k | ~$0.10 |
| bear | 10-18k (thesis + analysts + bull case) | 1-2k | ~$0.12 |
| rebuttal | 12-20k (all above + bear) | 1-2k | ~$0.13 |
| final_arguments | 15-25k (all prior acts) | 1-2k | ~$0.17 |
| debate_synthesis | 20-30k (all prior + revised-thesis draft) | 2-3k | ~$0.22 |
| **Debate total** | **65-108k** | **6-11k** | **~$0.75 per debate** |

Plus the pre-debate pipeline (3 analysts ANALYSIS + manager REASONING + signal ANALYSIS), Phase 4's cost estimate was "$1-3 per run" [CITED: `.planning/phases/04-multi-agent-specialization/04-03-SUMMARY.md` key decision]. Total with debate: **$1.75-3.75 per run**.

This matches the CLAUDE.md warning: "naive multi-agent costs $2-5/analysis." We are at the upper end. Mitigations above (output_override, brevity prompts) can pull this below $2.

**Note:** Anthropic introduced a new tokenizer with Opus 4.7 that can increase effective costs by up to 35% for the same apparent text [CITED: finout.io Claude Opus 4.7 Pricing 2026]. Stack currently uses Opus 4.6 [VERIFIED: `src/ai_hedge_fund/models.py:26`] so not affected yet — but when the project upgrades, re-estimate.

## Code Examples

### Example 1: Bear agent system prompt requiring >=2 rebuttals (DEBATE-02)

```python
# Source: new in src/ai_hedge_fund/agents/bear.py
BEAR_SYSTEM_PROMPT = (
    "You are the Bear Advocate. Your task: argue against buying this company.\n"
    "\n"
    "STRICT RULES:\n"
    "1. You will be given analyst reports, a preliminary thesis, AND the Bull "
    "Advocate's case. Build your case from that evidence.\n"
    "2. Every claim MUST cite source_analyst (one of 'fundamental', 'sentiment', "
    "'technical', 'manager').\n"
    "3. You MUST directly address and rebut AT LEAST 2 of the bull's specific "
    "claims. For each bull claim you rebut, quote the bull's claim text "
    "verbatim into your `addressed_bull_claims` list and produce at least one "
    "BearClaim whose `addresses_bull_claim` field contains that exact text.\n"
    "4. Produce at least 3 bear claims. You are advocating — do not soften to "
    "agree with the bull. If you genuinely see no counter-evidence, say so in "
    "your headline and present the weakest parts of the bull case as your "
    "strongest points.\n"
    "5. Cite specific data points. Vague 'market is bad' claims are forbidden.\n"
)
```

### Example 2: Deterministic quality_score in the synthesis node

```python
# Source: new in src/ai_hedge_fund/graph/nodes.py
async def debate_synthesis_node(state: DebatePipelineState) -> dict:
    if state.get("error"):
        return {}
    # Pre-debate confidence is read from state BEFORE the agent runs -- this
    # guarantees success-criterion 4 uses the manager's original number, not
    # whatever the synthesis agent fabricates.
    pre_debate_confidence = state.get("thesis", {}).get("confidence", 0)
    prompt = format_debate_for_synthesis(state, pre_debate_confidence)
    try:
        limits = get_debate_synthesis_limits()
        result = await debate_synthesis_agent.run(prompt, usage_limits=limits)
    except UsageLimitExceeded as e:
        logger.error("debate_synthesis_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {"error": f"Debate synthesis budget exceeded: {e}"}
    synthesis = result.output
    # OVERWRITE whatever the LLM put in quality_score with the deterministic value.
    quality_score = compute_quality_score(
        synthesis.evidence_strength,
        synthesis.logical_consistency,
        synthesis.risk_coverage,
    )
    synthesis = synthesis.model_copy(update={
        "quality_score": quality_score,
        "pre_debate_confidence": pre_debate_confidence,  # source of truth is state, not LLM.
    })
    usage = result.usage()
    logger.info(
        "debate_synthesis_complete",
        ticker=state["ticker"],
        pre_conf=pre_debate_confidence,
        post_conf=synthesis.post_debate_confidence,
        quality=quality_score,
        total_tokens=usage.total_tokens,
    )
    return {
        "debate_synthesis": synthesis.model_dump(),
        "thesis": synthesis.revised_thesis.model_dump(),  # signal_node sees revised.
    }
```

### Example 3: TestModel-based integration test (mirrors Phase 4)

```python
# Source: new in tests/integration/test_debate_pipeline.py, cloned from
# tests/integration/test_multi_agent_pipeline.py:155-215

def test_full_debate_pipeline_with_test_model() -> None:
    graph = build_debate_pipeline()
    initial_state = {"ticker": "AAPL", "as_of_date": "2024-01-02"}

    async def _invoke() -> dict:
        with (
            fundamental_agent.override(model=TestModel(call_tools=[])),
            sentiment_agent.override(model=TestModel(call_tools=[])),
            technical_agent.override(model=TestModel(call_tools=[])),
            manager_agent.override(model=TestModel()),
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            rebuttal_agent.override(model=TestModel()),
            final_arguments_agent.override(model=TestModel()),
            debate_synthesis_agent.override(model=TestModel()),
            signal_agent.override(model=TestModel()),
        ):
            return await graph.ainvoke(initial_state)

    final_state = asyncio.run(_invoke())
    assert final_state.get("error") is None
    assert final_state["bull_case"]["claims"]  # len >= 3 enforced by schema.
    assert final_state["bear_case"]["addressed_bull_claims"]  # len >= 2.
    assert final_state["rebuttal"]
    assert final_state["final_arguments"]
    synth = final_state["debate_synthesis"]
    assert "quality_score" in synth
    assert 0 <= synth["quality_score"] <= 100
    # quality_score is the deterministic weighted mean of sub-scores.
    expected = round(
        0.4 * synth["evidence_strength"]
        + 0.3 * synth["logical_consistency"]
        + 0.3 * synth["risk_coverage"]
    )
    assert synth["quality_score"] == expected
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Free-form LLM chat debate (TradingAgents, TradingGPT, most 2023 papers) | Structured multi-act protocol (SAS, EMNLP FinNLP 2025) | Nov 2025 (SAS paper publication) | Structured debate produces higher-quality output per GPT-4o judge in SAS. Required for schema-validated success criterion 3. |
| LLM-produced composite quality/confidence scores | Decomposed sub-scores (LLM) + deterministic aggregation (tool) | Ongoing best practice; aligns with CLAUDE.md "tool-first" rule | LLMs reliably rank things qualitatively but unreliably compute weighted means. Split reduces hallucinated-math errors. |
| Single-model adversarial debate (same GPT/Claude on both sides) | Mixed-role framing or different models for bull/bear | 2025 — peacemaker paper (arxiv 2509.23055) | Sycophancy is real and measurable in same-model MAD. Different personas partially mitigate. In our phase 5 we use same-model with strong role priming — phase UAT should measure if this is sufficient. |
| Langchain agents with free output | PydanticAI agents with typed output schemas | 2024 — PydanticAI launch | We already committed to PydanticAI; this phase amplifies that bet: five new typed Agent[Deps, Output] definitions. |

**Deprecated / not used:**
- `create_react_agent` from langgraph.prebuilt: reactive tool-use agent pattern is unsuitable here (no tools; sequential flow, not a ReAct loop).
- Custom retry loops: superseded by `Agent(..., retries=2)` built-in.
- Subgraph wrapper for the debate: considered and rejected — flat is simpler, matches codebase pattern [CITED: docs.langchain.com/oss/python/langgraph/use-subgraphs].

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Weights of 0.4 / 0.3 / 0.3 for (evidence, consistency, risk) in `compute_quality_score` | Pattern 3 | Moderate. If the user wants equal weighting (0.33 each) or evidence-dominant (0.5 / 0.25 / 0.25), the number changes. Recommendation: expose the weights as module-level constants with a comment; plan can surface them for discussion. No correctness impact on success criteria — any valid weighting satisfies DEBATE-04. |
| A2 | Single rebuttal act (one node) rather than two directional rebuttals | Pattern 4 | Low. ROADMAP says "rebuttal" singular. `RebuttalAct` schema can hold both `bull_rebuttals` (bull rebuts bear) AND `bear_rebuttals` (bear rebuts bull) in one LLM call — one node, two sub-fields. This is simpler than two nodes and still satisfies "rebuttal" as an act. |
| A3 | Bear's `addressed_bull_claims` can be enforced by `min_length=2` on a `list[str]` | Pattern 2 | Low. Pydantic enforces length [CITED: docs.pydantic.dev/latest/errors/validation_errors/]. We cannot enforce that the strings are *verbatim copies* of bull claims — a real-LLM check at UAT time is needed for that. System prompt instructs the agent to copy verbatim; validation catches absence-of-rebuttal, not semantic-mismatch. |
| A4 | `post_debate_confidence != pre_debate_confidence` in ≥30% of runs is testable at UAT, not in unit tests | Pattern 5, Pitfall 3 | Low. TestModel is deterministic (seed=0 default) — the same placeholders come out every time, so `post == pre` deterministically in unit tests. The 30% criterion is a statistical claim over real-LLM runs. See Validation Architecture below for the split. |
| A5 | `build_debate_pipeline` as a new builder (Option B) vs replacing `build_multi_agent_pipeline` | Component Responsibilities | Low. New builder preserves Phase 4 tests; planner can validate. |
| A6 | No mandatory connection between `thesis.confidence` and `debate_synthesis.pre_debate_confidence` at the schema level — it is only enforced by `debate_synthesis_node` reading from state | Pitfall 3, Example 2 | Medium. If the planner deviates and lets the LLM fill `pre_debate_confidence` from the prompt, the field can be silently wrong. Recommend the node-level override AND a unit test that asserts `pre_debate_confidence == state_thesis_confidence` in the returned dict. |
| A7 | 5 new agent files (one per role) rather than one `debate.py` with all 5 | Component Responsibilities | Low. Matches Phase 4's per-role file pattern (`fundamental.py`, `sentiment.py`, `technical.py`, `manager.py`). Cohesion + files under 800 lines rule. |

**Risk summary:** No `[ASSUMED]` claim above is load-bearing for a success criterion. All assumptions concern implementation taste (file organization, weighting constants, option A vs B) — the criteria themselves are supported by verified facts about the stack.

## Open Questions (RESOLVED)

1. **Quality-score weights** — Evidence-weighted (0.4/0.3/0.3) is my default. User may prefer equal weights (0.33) or a risk-first weighting (0.25/0.25/0.5). *Recommendation: default per A1, expose as named constants, planner flags for user sign-off.* **RESOLVED:** adopt 0.4/0.3/0.3 (A1). Plan 05-02 Task 2 exposes `EVIDENCE_WEIGHT=0.4`, `LOGIC_WEIGHT=0.3`, `RISK_WEIGHT=0.3` as module constants in `src/ai_hedge_fund/tools/quality_score.py` so they can be tuned without code search.
2. **How strict should "addressed_bull_claims must be verbatim" be?** Schema can only enforce `len >= 2` and non-empty strings. Verbatim-ness is system-prompt-only. *Recommendation: at UAT, sample a debate run and eyeball the `addressed_bull_claims` strings against the bull case.* **RESOLVED:** schema enforces count (`min_length=2`); semantic-alignment check deferred to UAT per `05-VALIDATION.md` Manual-Only Verifications row 2. No `@field_validator` added in Phase 5; revisit after UAT sampling.
3. **Should `debate_synthesis` or a separate `debate_signal_node` read `revised_thesis`?** *Recommendation: overwrite `state["thesis"]` and add an `original_thesis` field that `manager_node` writes alongside. Planner to decide.* **RESOLVED:** `debate_synthesis_node` overwrites `state["thesis"]` with `revised_thesis.model_dump()` (Plan 05-03 Task 1) so the unchanged `multi_agent_signal_node` consumes the post-debate thesis unchanged. `pre_debate_confidence` captures the pre-debate value from `state["thesis"]["confidence"]` before overwrite; no separate `original_thesis` field introduced in v1.
4. **Batch API for cost reduction** — 50% cost savings with 24-hour batching. Worth it once daily research cycle (PAPER-03) is in place; premature for Phase 5. **DEFERRED** to Phase 8+ once a daily research cadence exists.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pydantic-ai | Debate agents | ✓ | 1.80.0 | — |
| langgraph | Debate pipeline | ✓ | 1.1.6 | — |
| langchain-anthropic | Opus provider | ✓ | 1.4.0 | — |
| anthropic SDK | Opus API | ✓ | 0.94.0 | — |
| pydantic | Schema validation | ✓ | 2.12.0 | — |
| pytest / pytest-asyncio | Tests | ✓ | 9.0 / 1.0 | — |
| `ANTHROPIC_API_KEY` env var | Real-LLM UAT only | Required at UAT time | — | TestModel for unit + integration; real LLM gated to UAT scripts per Phase-4 precedent |
| `DATABASE_URL` / PostgreSQL | Optional checkpointer | ✓ (Docker Compose) | 16+ | `MemorySaver` for tests; no hard dep for Phase 5 functionality |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None meaningful — UAT requires ANTHROPIC_API_KEY but all automated tests use TestModel.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0+ with pytest-asyncio 1.0+ (`asyncio_mode = "auto"`) [VERIFIED: pyproject.toml] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — testpaths=`tests` |
| Quick run command | `uv run pytest tests/unit/test_bull_agent.py tests/unit/test_bear_agent.py tests/unit/test_rebuttal_agent.py tests/unit/test_final_arguments_agent.py tests/unit/test_debate_synthesis_agent.py tests/unit/test_debate_schemas.py tests/unit/test_debate_nodes.py tests/unit/test_quality_score.py -x` |
| Full suite command | `uv run pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEBATE-01 | `bull_agent` is `Agent[None, BullCase]`, REASONING tier, zero tools, retries=2 | unit | `pytest tests/unit/test_bull_agent.py -x` | ❌ Wave 0 |
| DEBATE-01 | BullCase schema: min_length=3 on claims; source_analyst required | unit | `pytest tests/unit/test_debate_schemas.py::TestBullCase -x` | ❌ Wave 0 |
| DEBATE-01 | `bull_node` happy path with TestModel; error propagation on UsageLimitExceeded | unit | `pytest tests/unit/test_debate_nodes.py::TestBullNode -x` | ❌ Wave 0 |
| DEBATE-02 | `bear_agent` wiring + BearCase schema with `addressed_bull_claims: min_length=2` | unit | `pytest tests/unit/test_debate_schemas.py::TestBearCase -x` | ❌ Wave 0 |
| DEBATE-02 | `bear_node` happy path + error | unit | `pytest tests/unit/test_debate_nodes.py::TestBearNode -x` | ❌ Wave 0 |
| DEBATE-03 | 5-act protocol with sequential topology | integration | `pytest tests/integration/test_debate_pipeline.py::test_full_debate_pipeline_with_test_model -x` | ❌ Wave 0 |
| DEBATE-03 | Compiled graph has all 10 nodes (3 analysts + manager + 5 debate + signal + START + END = 12 total incl. markers) in correct order | integration | `pytest tests/integration/test_debate_pipeline.py::test_debate_pipeline_topology -x` | ❌ Wave 0 |
| DEBATE-03 | Schema validation error on act with empty claims (happens automatically via Pydantic) | unit | `pytest tests/unit/test_debate_schemas.py::TestEmptyActRaisesValidationError -x` | ❌ Wave 0 |
| DEBATE-04 | `compute_quality_score` is a pure function, correct weighted mean | unit | `pytest tests/unit/test_quality_score.py -x` | ❌ Wave 0 |
| DEBATE-04 | `debate_synthesis_node` overwrites LLM-produced quality_score with computed value | unit | `pytest tests/unit/test_debate_nodes.py::TestDebateSynthesisNode::test_quality_score_is_recomputed -x` | ❌ Wave 0 |
| DEBATE-04 | `pre_debate_confidence` is sourced from `state["thesis"]["confidence"]`, not the LLM | unit | `pytest tests/unit/test_debate_nodes.py::TestDebateSynthesisNode::test_pre_confidence_from_state -x` | ❌ Wave 0 |
| DEBATE-04 | post_debate_confidence differs from pre_debate_confidence in ≥30% of runs | **manual UAT** | Not automated. Phase UAT script: run debate on 10 real tickers, record `post - pre` per run, assert ≥3 differ. | N/A — deferred |

### Sampling Rate

- **Per task commit:** Quick run (all new unit test files + debate integration test with TestModel) — ~10-20 seconds expected.
- **Per wave merge:** Full suite (`pytest -x` in full repo) — ~60-90 seconds expected based on Phase 4 test counts (~200 tests).
- **Phase gate:** Full suite green + phase UAT script that runs one real-LLM debate end-to-end AND the 10-ticker 30%-delta check.

### Wave 0 Gaps

- [ ] `tests/unit/test_bull_agent.py` — covers DEBATE-01 wiring (mirror of `test_manager_agent.py`)
- [ ] `tests/unit/test_bear_agent.py` — covers DEBATE-02 wiring
- [ ] `tests/unit/test_rebuttal_agent.py` — covers DEBATE-03 rebuttal act wiring
- [ ] `tests/unit/test_final_arguments_agent.py` — covers DEBATE-03 final_arguments act wiring
- [ ] `tests/unit/test_debate_synthesis_agent.py` — covers DEBATE-04 synthesis agent wiring
- [ ] `tests/unit/test_debate_schemas.py` — covers DEBATE-01/02/03 schema min_length constraints; should include an explicit "empty act raises ValidationError" test class per success criterion 3
- [ ] `tests/unit/test_debate_nodes.py` — covers all 5 node wrappers' async contract, happy path, error propagation, pre_debate_confidence sourcing, quality_score recomputation (mirror of `test_multi_agent_nodes.py`)
- [ ] `tests/unit/test_quality_score.py` — pure-function tests for `compute_quality_score` (boundary cases, weighting, type errors, range errors)
- [ ] `tests/integration/test_debate_pipeline.py` — covers DEBATE-03 integration, full 10-agent TestModel flow, topology assertions, Phase-4 no-regression check (mirror of `test_multi_agent_pipeline.py`)

Framework install: **None.** pytest + pytest-asyncio already configured and running in Phase 4 tests.

**Note on success criterion 4 (30% of runs):** This is a statistical claim over real-LLM runs. TestModel is deterministic, so unit tests cannot verify it. Deferred to phase UAT. A possible phase-gate sanity script: run the debate pipeline 10 times on different tickers with real LLM, compute `sum(1 for r in runs if r.post != r.pre) / 10`, assert ≥ 0.3.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No user auth; internal pipeline. |
| V3 Session Management | no | No sessions; LangGraph checkpointer handles state durability. |
| V4 Access Control | no | No multi-tenant model in Phase 5. |
| V5 Input Validation | **yes** | Pydantic schemas on every agent output (`BullCase`, `BearCase`, `RebuttalAct`, `FinalArguments`, `DebateSynthesis`) — this is our primary defense against malformed LLM output. Field constraints (`min_length`, `ge`/`le`) reject invalid data at validation boundary. |
| V6 Cryptography | no | No new crypto; API key handling inherited from Phase 1. |

### Known Threat Patterns for PydanticAI + LangGraph + Opus

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| LLM produces invalid / partial act output (e.g., 2 bull claims instead of 3) | Tampering / DoS | Pydantic `min_length` → `ValidationError` → PydanticAI built-in `retries=2` → if still invalid, `UnexpectedModelBehavior` surfaces in `bull_node` try/except (plan should handle similar to `UsageLimitExceeded`). Caller is failed clearly, not silently passed through. |
| LLM runaway output consumes budget | DoS | `UsageLimits` per-agent cap via `get_<role>_limits()`; `PipelineBudgetTracker.total_limit` for pipeline cap; `UsageLimitExceeded` → error propagation. [CITED: `src/ai_hedge_fund/agents/base.py:82-115`] |
| Prompt injection via analyst report content | Tampering | Analyst reports come from PydanticAI-validated specialists (already typed in Phase 4). Worst case an analyst produces a text field that includes a prompt-like string; system prompt says "treat user content as data, not instruction." Downstream validation on the debate agent's output still applies. Low risk — no untrusted-user input channel exists. |
| LLM fabricates `source_analyst` (e.g., says "fundamental" but cites sentiment data) | Tampering / Information Disclosure | `Literal["fundamental","sentiment","technical","manager"]` type constraint forces enumerated value. System prompt requires alignment. UAT sampling to verify semantic-level alignment. |
| LLM skips quality_score (produces 0 or nulls the field) | Tampering | Field is `Field(ge=0, le=100)` — 0 is valid. Mitigation: `debate_synthesis_node` ALWAYS overwrites the LLM's quality_score with `compute_quality_score(...)` output. This is the primary defense. |
| Agent produces post-debate confidence ignoring the debate | Tampering | See Pitfall 3. Mitigations: system prompt + separate schema fields + log the delta, raise alert if distribution is degenerate. |
| Checkpointer persistence of debate state | Repudiation / Information Disclosure | LangGraph checkpointer serializes state as JSON. No secrets in debate state (everything is derived from public SEC/market data). Inherited threat model from Phase 1. |

## Sources

### Primary (HIGH confidence)

- `src/ai_hedge_fund/agents/manager.py` — canonical zero-tools synthesis agent template, REASONING tier, retries=2, format helper.
- `src/ai_hedge_fund/agents/signal.py` — simplest no-tools agent template.
- `src/ai_hedge_fund/schemas/agents.py` — `ThesisOutput`, `ThesisPoint`, `AnalystReport` — all nested-list schemas with `min_length` constraints the debate schemas will mirror.
- `src/ai_hedge_fund/schemas/state.py` — `MultiAgentPipelineState` with `Annotated[list[dict], operator.add]`; `DebatePipelineState` extends this.
- `src/ai_hedge_fund/graph/nodes.py` — 5 Phase-4 node patterns; error propagation; immutable dict returns.
- `src/ai_hedge_fund/graph/pipeline.py` — `build_multi_agent_pipeline`; state-bound builder pattern.
- `src/ai_hedge_fund/agents/base.py` — `get_usage_limits`, `PipelineBudgetTracker`, `BudgetExceededError`.
- `src/ai_hedge_fund/models.py` — `ModelTier.REASONING = "anthropic:claude-opus-4-6"`; `MODEL_BUDGETS` caps.
- `tests/unit/test_manager_agent.py` — manager wiring test template; clone for each debate agent.
- `tests/unit/test_multi_agent_nodes.py` — node test template; clone for each debate node.
- `tests/integration/test_multi_agent_pipeline.py` — TestModel full-pipeline test template; clone and extend for 10 agents.
- [Pydantic Validation Errors](https://docs.pydantic.dev/latest/errors/validation_errors/) — `too_short` for list min_length.
- [PydanticAI Multi-Agent Patterns](https://pydantic.dev/docs/ai/guides/multi-agent-applications/) — programmatic hand-off vs delegation vs graph-based; programmatic via prompts is idiomatic for sequential chains.
- [LangGraph Subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs) — when to use subgraph vs flat; recommendation: flat for our case.
- [SAS paper (EMNLP FinNLP 2025)](https://aclanthology.org/2025.finnlp-2.21/) — 3-phase framework (Intelligence Distillation / Adversarial Debate 5-act / Final Synthesis); provenance of the 5-act protocol. ACL Anthology listing verified; PDF is in binary form but abstract confirmed in search result.
- [TradingAgents paper (arxiv 2412.20138v3)](https://arxiv.org/html/2412.20138v3) — bull/bear pattern; natural-language dialogue with facilitator; we deliberately DIVERGE (structured > free-form) for schema enforceability.
- [Anthropic Pricing 2026](https://platform.claude.com/docs/en/about-claude/pricing) — Opus 4.6/4.7 $5/$25 per Mtok; batch 50% discount; prompt cache 90% discount.
- [Empirical repro (2026-04-21)](N/A) — verified in project's `.venv` that `TestModel` produces exactly `min_length` nested items with placeholder strings; `asyncio.run` executes agent override cleanly. Verified as part of research.

### Secondary (MEDIUM confidence)

- [Talk Isn't Always Cheap (arxiv 2509.05396)](https://arxiv.org/pdf/2509.05396) — multi-agent debate failure modes (sycophancy, persuasion override, debate collapse, repetition, agent dominance). PDF unreadable but outline confirmed via search.
- [Peacemaker or Troublemaker (arxiv 2509.23055)](https://www.arxiv.org/pdf/2509.23055) — sycophancy quantified in MAD: disagreement rate drops over debate progression, correlated with performance degradation.
- [Claude Opus 4.6 model ID](https://milvus.io/ai-quick-reference/whats-the-claude-opus-46-model-id-in-the-api) — model-ID format `claude-opus-4-6` matches project's current config.
- `.planning/research/MULTI_AGENT_TRADING_SYSTEMS.md` — project-internal research noting structured > free-form debate as a decision already made.
- `.planning/phases/04-multi-agent-specialization/04-03-SUMMARY.md` — Phase 4 summary with $1-3/run cost estimate, `operator.add` reducer rationale, TestModel `call_tools=[]` rationale.

### Tertiary (LOW confidence)

- [finout.io Claude Opus 4.7 Pricing](https://www.finout.io/blog/claude-opus-4.7-pricing-the-real-cost-story-behind-the-unchanged-price-tag) — claim that new tokenizer increases effective costs by up to 35%. Single source; flagged for re-verification when project upgrades from 4.6.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — all dependencies verified installed; all patterns exist in codebase and are referenced by file path + line number.
- Architecture: **HIGH** — every recommended pattern is a clone of a Phase-4 pattern that is working in prod. The only new architectural element is the 5-act schema + quality_score helper, both of which are direct applications of codebase conventions.
- Pitfalls: **MEDIUM-HIGH** — sycophancy/conformity is well-documented in 2025 literature but hasn't been empirically measured on Opus 4.6 specifically for financial debate; phase UAT required to confirm the 30%-delta criterion is achievable without mitigation. All other pitfalls map to concrete code-level defenses.
- Quality-score weights (A1): **LOW-MEDIUM** — weighted-mean approach is correct per CLAUDE.md; the specific weights are author's best guess and should be surfaced for user review.
- Token cost estimate: **MEDIUM** — based on token counts of analyst reports/manager outputs from Phase 4 (estimated, not measured). Phase UAT can measure actual costs and adjust `get_<role>_limits`.

**Research date:** 2026-04-21
**Valid until:** 2026-05-21 (30 days) — stable stack, but refresh when Opus 4.7 migration or PydanticAI 2.x comes up.
