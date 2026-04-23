# Phase 5: Adversarial Critique — Pattern Map

**Mapped:** 2026-04-21
**Files analyzed:** 17 new/modified files
**Analogs found:** 17 / 17 (one deterministic-helper file has a weaker analog — see "No Analog Found")

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/ai_hedge_fund/agents/bull.py` | agent (LLM) | request-response, zero-tool synthesis | `src/ai_hedge_fund/agents/manager.py` | exact |
| `src/ai_hedge_fund/agents/bear.py` | agent (LLM) | request-response, zero-tool synthesis | `src/ai_hedge_fund/agents/manager.py` | exact |
| `src/ai_hedge_fund/agents/rebuttal.py` | agent (LLM) | request-response, zero-tool synthesis | `src/ai_hedge_fund/agents/manager.py` | exact |
| `src/ai_hedge_fund/agents/final_arguments.py` | agent (LLM) | request-response, zero-tool synthesis | `src/ai_hedge_fund/agents/manager.py` | exact |
| `src/ai_hedge_fund/agents/debate_synthesis.py` | agent (LLM) + pure helper | request-response + transform | `src/ai_hedge_fund/agents/manager.py` + new helper | exact / new-primitive |
| `src/ai_hedge_fund/schemas/debate.py` | schema (Pydantic output models) | validation/transform | `src/ai_hedge_fund/schemas/agents.py` (ThesisPoint / ThesisOutput) | exact |
| `src/ai_hedge_fund/schemas/state.py` (MODIFIED) | state schema (TypedDict) | LangGraph state transport | `src/ai_hedge_fund/schemas/state.py` (MultiAgentPipelineState) | exact (same file) |
| `src/ai_hedge_fund/graph/nodes.py` (MODIFIED; +5 nodes) | graph node (async wrapper) | event-driven (LangGraph), request-response per node | `src/ai_hedge_fund/graph/nodes.py` (manager_node) | exact (same file) |
| `src/ai_hedge_fund/graph/pipeline.py` (MODIFIED; +build_debate_pipeline) | graph builder | topology / orchestration | `src/ai_hedge_fund/graph/pipeline.py` (build_multi_agent_pipeline) | exact (same file) |
| `src/ai_hedge_fund/agents/__init__.py` (MODIFIED) | re-exports | — | `src/ai_hedge_fund/agents/__init__.py` (existing) | exact (same file) |
| `src/ai_hedge_fund/graph/__init__.py` (MODIFIED) | re-exports | — | `src/ai_hedge_fund/graph/__init__.py` (existing) | exact (same file) |
| `src/ai_hedge_fund/schemas/__init__.py` (MODIFIED) | re-exports | — | `src/ai_hedge_fund/schemas/__init__.py` (existing) | exact (same file) |
| `tests/unit/test_debate_schemas.py` | test (unit, schema) | validation assertions | `tests/unit/test_specialist_schemas.py` | exact |
| `tests/unit/test_bull_agent.py` (+4 more per-agent files) | test (unit, agent wiring) | TestModel override | `tests/unit/test_manager_agent.py` | exact |
| `tests/unit/test_debate_nodes.py` | test (unit, node wiring) | async contract + TestModel override | `tests/unit/test_multi_agent_nodes.py` | exact |
| `tests/unit/test_quality_score.py` | test (pure function) | arithmetic unit test | `tests/unit/test_budget.py` (frozen-dataclass pure-logic tests) | role-match |
| `tests/integration/test_debate_pipeline.py` | test (integration, pipeline) | compiled-graph TestModel end-to-end | `tests/integration/test_multi_agent_pipeline.py` | exact |

## Pattern Assignments

### `src/ai_hedge_fund/agents/bull.py` (agent, request-response)

**Analog:** `src/ai_hedge_fund/agents/manager.py` (zero-tools REASONING-tier synthesis agent; retries=2).

**Imports pattern** (manager.py lines 14-23):
```python
from __future__ import annotations

import json  # bull/bear/rebuttal/final all need json.dumps for analyst-report formatting

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.base import get_usage_limits
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.debate import BullCase  # <-- new schema module
```

**Module docstring + threat-mitigation header** (manager.py lines 1-12): every agent file opens with a short purpose paragraph and a `Threat mitigations:` block naming T-05-XX IDs (bull/bear get T-05-DoS via UsageLimits; T-05-Tampering via retries=2 and schema constraints). Phase 5 should pick T-05-01 through T-05-NN.

**System-prompt constant pattern** (manager.py lines 25-52): module-level uppercase constant `BULL_SYSTEM_PROMPT`, multi-line parenthesised string, numbered "YOUR TASK" steps, explicit "IMPORTANT:" disclaimer at the end. The planner-authored prompt from RESEARCH.md Example 1 (bear) and Pattern 1 (bull) slot in verbatim.

**Agent instantiation pattern** (manager.py lines 55-60):
```python
bull_agent: Agent[None, BullCase] = Agent(
    ModelTier.REASONING.value,   # Opus -- argument quality is high-reasoning work.
    output_type=BullCase,
    system_prompt=BULL_SYSTEM_PROMPT,
    retries=2,
)
```

Key deltas from manager:
- `output_type` swapped per agent (`BullCase` / `BearCase` / `RebuttalAct` / `FinalArguments` / `DebateSynthesis`).
- System-prompt constant renamed to match (`BULL_SYSTEM_PROMPT`, `BEAR_SYSTEM_PROMPT`, ...).
- Everything else identical: ModelTier.REASONING, retries=2, zero tools.

**Usage-limits helper pattern** (manager.py lines 63-65):
```python
def get_bull_limits() -> UsageLimits:
    """Return UsageLimits for the bull advocate (REASONING tier, Opus)."""
    return get_usage_limits(ModelTier.REASONING)
```

RESEARCH.md Pitfall 6 recommends per-role `output_override` to cut cost (e.g., `get_usage_limits(ModelTier.REASONING, output_override=8_000)` for rebuttal/final). Planner should decide per-role.

**Formatting helper pattern** (manager.py lines 68-100): `format_analyst_reports(reports: list[dict]) -> str` is a module-level pure function that folds dicts into a human-readable string for the user prompt. Bull/bear/rebuttal/final/synthesis each need an analogous helper (`format_analyst_evidence`, `format_bull_case_for_bear`, `format_debate_for_rebuttal`, `format_debate_for_synthesis`). Each follows the same shape:
1. Early-return for empty input.
2. Build `formatted_sections: list[str]`.
3. Join with `"\n\n---\n\n".join(...)`.
4. Use `json.dumps(..., indent=2)` for nested dicts.

---

### `src/ai_hedge_fund/agents/bear.py` (agent, request-response)

**Analog:** `src/ai_hedge_fund/agents/manager.py` (same template as bull).

**Delta from bull.py:**
- `output_type=BearCase`.
- `BEAR_SYSTEM_PROMPT` (RESEARCH.md Example 1, lines 594-611) — key difference is rule 3 requiring `addressed_bull_claims` with verbatim bull-claim text on AT LEAST 2 entries.
- `format_bull_case_for_bear(bull_case: dict) -> str` helper clones `format_analyst_reports` body but emits bull claims as a numbered list so the bear can quote them back.

**Follow the exact retries=2 / zero-tools / REASONING tier shape** from manager.py lines 55-60.

---

### `src/ai_hedge_fund/agents/rebuttal.py` / `final_arguments.py` / `debate_synthesis.py`

**Analog:** `src/ai_hedge_fund/agents/manager.py` (same template).

**Per-file deltas:**

| File | output_type | Helper(s) | System-prompt focus |
|------|-------------|-----------|---------------------|
| `rebuttal.py` | `RebuttalAct` | `format_debate_for_rebuttal(bull_case, bear_case) -> str` | Balanced N-bull-rebuttals AND N-bear-rebuttals (RESEARCH.md assumption A2). |
| `final_arguments.py` | `FinalArguments` | `format_debate_for_final(bull, bear, rebuttal) -> str` | Closing arguments, explicit evidence-citation count. |
| `debate_synthesis.py` | `DebateSynthesis` | `format_debate_for_synthesis(state, pre_debate_confidence) -> str` + **`compute_quality_score(...)` pure helper** | Produce revised_thesis + sub-scores; system prompt must say "do NOT default to pre-debate confidence" (Pitfall 3). |

**`compute_quality_score` (new pure function, lives in `debate_synthesis.py`):** Full reference in RESEARCH.md Pattern 3 (lines 342-375). Weighted mean: 0.4 * evidence_strength + 0.3 * logical_consistency + 0.3 * risk_coverage → `round()` → int. Raises `ValueError` on out-of-range inputs. Module-level constants for weights (A1 flag in RESEARCH.md).

No direct in-repo analog for `compute_quality_score` (see "No Analog Found"); follow the "many small files, pure-function, no side effects" convention from `ai_hedge_fund/data/summary.py` — a docstring-heavy, parameterised, `from __future__ import annotations` pure helper. Frozen-dataclass style (`PipelineBudgetTracker` in `agents/base.py`) is also in-scope if weights become a dataclass rather than module constants.

---

### `src/ai_hedge_fund/schemas/debate.py` (schema, validation)

**Analog:** `src/ai_hedge_fund/schemas/agents.py` — specifically `ThesisPoint` (lines 59-79) and `ThesisOutput` (lines 82-110).

**Module header pattern** (agents.py lines 1-11):
```python
"""PydanticAI output schemas for agent responses.

Each schema defines the typed, validated output for a specific agent type.
Pydantic Field constraints enforce data quality at the validation boundary:
- min_length prevents empty or under-populated lists
- ge/le constraints enforce numeric ranges
- Literal types restrict categorical values

These schemas are used as PydanticAI Agent output_type parameters and
are serialized via model_dump() for storage in LangGraph state dicts.
"""
```

**Imports pattern** (agents.py lines 13-17):
```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
```

**Nested "claim-with-citation" sub-model pattern** (agents.py lines 59-79, `ThesisPoint`):
```python
class ThesisPoint(BaseModel):
    """A single bull or bear case point with evidence citation.

    Each ThesisPoint forces the agent to cite both the data that supports
    its claim (``evidence``) and the tool that produced that data
    (``source_tool``), enforcing the tool-first principle at the schema
    boundary (AGENT-02, AGENT-03).
    """

    claim: str = Field(
        min_length=1,
        description="The investment argument",
    )
    evidence: str = Field(
        min_length=1,
        description="Specific data supporting the claim",
    )
    source_tool: str = Field(
        min_length=1,
        description="Which tool provided the evidence (e.g., 'get_financials')",
    )
```

**Top-level act-output pattern** (agents.py lines 82-110, `ThesisOutput`):
```python
class ThesisOutput(BaseModel):
    """Output from thesis synthesis (investment research agent)."""

    ticker: str = Field(description="Stock ticker symbol")
    bull_case: list[ThesisPoint] = Field(
        min_length=3,
        description="Bull case arguments with evidence citations (minimum 3)",
    )
    bear_case: list[ThesisPoint] = Field(
        min_length=3,
        description="Bear case arguments with evidence citations (minimum 3)",
    )
    confidence: int = Field(
        ge=0, le=100,
        description="Confidence score 0-100 in the thesis direction",
    )
    risk_factors: list[str] = Field(
        min_length=2,
        description="Named risk factors that could invalidate the thesis (minimum 2)",
    )
```

**Key deltas for Phase 5 schemas (copy from RESEARCH.md Pattern 2 lines 268-332):**
- Replace `source_tool: str` with `source_analyst: Literal["fundamental", "sentiment", "technical", "manager"]` — enumerated (mirrors `AnalystReport.analyst` at agents.py line 346). This is the key DEBATE-01 enforcement for "each claim cites its source analyst".
- `BullCase`: `claims: list[BullClaim] = Field(min_length=3)` + `headline: str`.
- `BearCase`: adds `addressed_bull_claims: list[str] = Field(min_length=2)` — the schema-level enforcement of DEBATE-02.
- `BearClaim`: optional `addresses_bull_claim: str | None = Field(default=None, ...)`.
- `RebuttalAct`: symmetric `bull_rebuttals: list[...]` + `bear_rebuttals: list[...]` with `min_length=2` each (assumption A2).
- `FinalArguments`: `bull_closing: str` + `bear_closing: str` with `min_length=1`.
- `DebateSynthesis`: nests `revised_thesis: ThesisOutput` (reuse, don't re-define) + `pre_debate_confidence` / `post_debate_confidence` as separate `int = Field(ge=0, le=100)` fields + three sub-scores + `quality_score: int = Field(ge=0, le=100)`.

**Existing schema to reuse (don't duplicate):** `from ai_hedge_fund.schemas.agents import ThesisOutput` — `DebateSynthesis.revised_thesis` is a `ThesisOutput` so the downstream signal node keeps working unchanged.

---

### `src/ai_hedge_fund/schemas/state.py` (MODIFIED: add `DebatePipelineState`)

**Analog:** `MultiAgentPipelineState` (same file, lines 75-107).

**Existing pattern to clone** (state.py lines 75-107):
```python
class MultiAgentPipelineState(TypedDict, total=False):
    """State flowing through the Phase-4 multi-agent pipeline.

    Uses ``Annotated[list, operator.add]`` on ``analyst_reports`` so each
    parallel analyst node can append its single-element list without
    overwriting peers -- LangGraph concatenates the lists returned from
    all parallel nodes before the manager node executes.
    """

    ticker: Required[str]
    as_of_date: Required[str]
    analyst_reports: Annotated[list[dict], operator.add]
    thesis: dict | None
    signal: dict | None
    error: str | None
```

**New `DebatePipelineState` (from RESEARCH.md Pattern 5 lines 462-484):**
- Same `Required[str]` / `Annotated[list[dict], operator.add]` / `dict | None` imports (file already has all three).
- `total=False` same as MultiAgentPipelineState.
- Repeat the MultiAgentPipelineState fields (TypedDict + multiple inheritance is fragile — just duplicate).
- Add single-writer `dict | None` fields: `bull_case`, `bear_case`, `rebuttal`, `final_arguments`, `debate_synthesis`.
- **No reducer on debate fields** (RESEARCH.md anti-pattern line 493) — each is overwrite-semantics, single-writer.
- Module docstring (state.py lines 1-19) gets a fourth paragraph describing DebatePipelineState.

---

### `src/ai_hedge_fund/graph/nodes.py` (MODIFIED: +5 async nodes)

**Analog:** `manager_node` (same file, lines 389-431) is the canonical zero-tools node. `fundamental_node` (lines 216-275) is the canonical analyst-with-deps node. Use manager_node's shape for bull/bear/rebuttal/final_arguments/debate_synthesis (no deps, no tools).

**Imports pattern** (nodes.py lines 27-54):
```python
from __future__ import annotations

from datetime import date  # only needed if any debate node parses as_of_date; probably not.

import structlog
from pydantic_ai.exceptions import UsageLimitExceeded

from ai_hedge_fund.agents.bull import bull_agent, get_bull_limits, format_analyst_evidence
from ai_hedge_fund.agents.bear import bear_agent, get_bear_limits, format_bull_case_for_bear
from ai_hedge_fund.agents.rebuttal import (
    rebuttal_agent, get_rebuttal_limits, format_debate_for_rebuttal,
)
from ai_hedge_fund.agents.final_arguments import (
    final_arguments_agent, get_final_arguments_limits, format_debate_for_final,
)
from ai_hedge_fund.agents.debate_synthesis import (
    debate_synthesis_agent, get_debate_synthesis_limits,
    compute_quality_score, format_debate_for_synthesis,
)
from ai_hedge_fund.schemas.state import DebatePipelineState

logger = structlog.get_logger(__name__)
```

**Canonical zero-tools node template** (nodes.py lines 389-431, `manager_node`):
```python
async def manager_node(state: MultiAgentPipelineState) -> dict:
    reports = state.get("analyst_reports", [])
    if not reports:
        logger.error("manager_no_reports", ticker=state.get("ticker"))
        return {"error": "No analyst reports available for synthesis"}

    reports_text = format_analyst_reports(reports)
    prompt = (
        f"Synthesize these analyst reports for {state['ticker']} as of "
        f"{state['as_of_date']}:\n\n{reports_text}"
    )

    try:
        limits = get_manager_limits()
        result = await manager_agent.run(prompt, usage_limits=limits)
        usage = result.usage()
        logger.info(
            "manager_complete",
            ticker=state["ticker"],
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
        return {"thesis": result.output.model_dump()}
    except UsageLimitExceeded as e:
        logger.error("manager_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {"error": f"Manager budget exceeded: {e}"}
```

**Error-propagation short-circuit pattern** (nodes.py lines 105-106, `analyze_node`; also lines 186-187 `signal_node`):
```python
if state.get("error"):
    return {}  # Skip if prior node errored -- do not overwrite error.
```

Every Phase-5 debate node EXCEPT `bull_node` (the first debate node) MUST start with this short-circuit. `bull_node`'s upstream is `manager_node`, which either sets `thesis` or `error`; if `error`, bull skips.

**Per-debate-node deltas (5 new nodes, each ~25 lines):**

| Node | Reads from state | Writes to state | Upstream-required precondition |
|------|------------------|-----------------|--------------------------------|
| `bull_node` | `analyst_reports`, `thesis` | `{"bull_case": ...}` | `state.get("thesis")` exists; else return `{"error": "No thesis available for bull"}` (mirrors `signal_node` lines 188-190). |
| `bear_node` | `analyst_reports`, `thesis`, `bull_case` | `{"bear_case": ...}` | `state.get("bull_case")` exists. |
| `rebuttal_node` | `bull_case`, `bear_case` | `{"rebuttal": ...}` | both cases present. |
| `final_arguments_node` | all prior acts | `{"final_arguments": ...}` | rebuttal present. |
| `debate_synthesis_node` | all prior acts + `thesis` | `{"debate_synthesis": ..., "thesis": ...}` (overwrites thesis with `revised_thesis`) | final_arguments present; MUST read `pre_debate_confidence = state.get("thesis", {}).get("confidence", 0)` BEFORE the agent runs (Pitfall 3). |

**`debate_synthesis_node` unique shape** — from RESEARCH.md Example 2 (lines 617-655): after `result = await debate_synthesis_agent.run(...)`, do:
```python
synthesis = result.output
synthesis = synthesis.model_copy(update={
    "quality_score": compute_quality_score(
        synthesis.evidence_strength,
        synthesis.logical_consistency,
        synthesis.risk_coverage,
    ),
    "pre_debate_confidence": pre_debate_confidence,  # authoritative state value
})
return {
    "debate_synthesis": synthesis.model_dump(),
    "thesis": synthesis.revised_thesis.model_dump(),  # signal_node reads revised
}
```

The `model_copy(update=...)` pattern is the immutable-object idiom required by CLAUDE.md global rules ("return new objects, don't mutate"). `return {"thesis": ...}` alongside `"debate_synthesis"` lets the existing `multi_agent_signal_node` (nodes.py line 434) consume the revised thesis with zero changes.

**Log-event naming pattern** (nodes.py lines 80-85, 115-121, 155-162, 198-204, etc.): `logger.info("<node_name>_complete", ticker=..., input_tokens=..., output_tokens=..., total_tokens=...)`. Phase 5: `"bull_complete"`, `"bear_complete"`, `"rebuttal_complete"`, `"final_arguments_complete"`, `"debate_synthesis_complete"` (the last one adds `pre_conf`, `post_conf`, `quality`).

---

### `src/ai_hedge_fund/graph/pipeline.py` (MODIFIED: add `build_debate_pipeline`)

**Analog:** `build_multi_agent_pipeline` (same file, lines 102-158).

**Imports pattern** (pipeline.py lines 20-41): add imports for the 5 new nodes + `DebatePipelineState`.

**Canonical builder template** (pipeline.py lines 102-158):
```python
def build_multi_agent_pipeline(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    builder = StateGraph(MultiAgentPipelineState)

    # Nodes -- three parallel analysts, one manager, one signal adapter.
    builder.add_node("fundamental", fundamental_node)
    builder.add_node("sentiment", sentiment_node)
    builder.add_node("technical", technical_node)
    builder.add_node("manager", manager_node)
    builder.add_node("signal", multi_agent_signal_node)

    # Fan-out: START -> all 3 analysts in parallel.
    builder.add_edge(START, "fundamental")
    builder.add_edge(START, "sentiment")
    builder.add_edge(START, "technical")

    # Fan-in: all 3 analysts -> manager (LangGraph barriers on the reducer).
    builder.add_edge("fundamental", "manager")
    builder.add_edge("sentiment", "manager")
    builder.add_edge("technical", "manager")

    # Manager -> signal -> END (sequential tail).
    builder.add_edge("manager", "signal")
    builder.add_edge("signal", END)

    return builder.compile(checkpointer=checkpointer)
```

**Deltas for `build_debate_pipeline` (RESEARCH.md Pattern 4, lines 406-449):**
- `StateGraph(DebatePipelineState)` instead of `MultiAgentPipelineState`.
- `builder.add_node("signal", multi_agent_signal_node)` is kept — the signal adapter already reads `state["thesis"]` and will see the revised thesis after debate_synthesis_node overwrites it.
- Add 5 new `builder.add_node(...)` calls for debate nodes.
- Replace the `manager -> signal` edge with `manager -> bull -> bear -> rebuttal -> final_arguments -> debate_synthesis -> signal`.
- **Critical: do NOT keep `("manager", "signal")` alongside the new chain** (RESEARCH.md Pitfall 4 lines 542-548). Creates a diamond; LangGraph will run signal twice or prematurely.
- **Recommended: NEW builder (Option B), not modification of build_multi_agent_pipeline** (RESEARCH.md line 182). Preserves all Phase-4 topology tests.

**Docstring shape** (pipeline.py lines 105-133): description + topology diagram in docstring + `Args:` + `Returns:` block with threat-model ID. Follow verbatim — Phase 5 replaces "T-04-09" with "T-05-09" for runtime graph mod threat.

---

### `src/ai_hedge_fund/agents/__init__.py` / `schemas/__init__.py` / `graph/__init__.py` (MODIFIED: re-exports)

**Analog:** each corresponding `__init__.py` in the same directory.

**Pattern** (agents/__init__.py lines 26-76): one `from ai_hedge_fund.agents.X import (agent, limits_helper, format_helper)` per agent module, sorted; `__all__` list also sorted alphabetically. Phase 5 adds:

```python
# agents/__init__.py additions
from ai_hedge_fund.agents.bull import bull_agent, get_bull_limits, format_analyst_evidence
from ai_hedge_fund.agents.bear import bear_agent, get_bear_limits, format_bull_case_for_bear
from ai_hedge_fund.agents.rebuttal import (
    rebuttal_agent, get_rebuttal_limits, format_debate_for_rebuttal,
)
from ai_hedge_fund.agents.final_arguments import (
    final_arguments_agent, get_final_arguments_limits, format_debate_for_final,
)
from ai_hedge_fund.agents.debate_synthesis import (
    debate_synthesis_agent, get_debate_synthesis_limits,
    compute_quality_score, format_debate_for_synthesis,
)
```

Add all new symbols to `__all__` (agents/__init__.py lines 52-76) in alphabetical order.

**schemas/__init__.py** (schemas/__init__.py lines 1-43): add `from ai_hedge_fund.schemas.debate import (BullCase, BullClaim, BearCase, BearClaim, RebuttalAct, FinalArguments, DebateSynthesis)` and add `DebatePipelineState` to the state import block.

**graph/__init__.py** (graph/__init__.py lines 25-40): extend the `from ai_hedge_fund.graph.nodes import (...)` block with the 5 new node names and add `build_debate_pipeline` to the pipeline import.

---

### `tests/unit/test_debate_schemas.py` (test, schema validation)

**Analog:** `tests/unit/test_specialist_schemas.py` (entire file).

**Imports pattern** (test_specialist_schemas.py lines 1-11):
```python
"""Tests for specialist analyst output schemas (Phase 4, Plan 01, Task 1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
```

**Sub-model + top-level test class pattern** (test_specialist_schemas.py lines 14-114):
- One `Test<SchemaName>` class per schema.
- Helper methods `_valid_metrics`, `_valid_citations` (lines 66-81) that build minimum-length valid input.
- `test_valid_<schema>` happy path.
- `test_rejects_empty_<field>` (lines 30-35) + `test_rejects_zero_<field>` / `test_rejects_one_<field>` (lines 101-120) for each `min_length=N`.
- `with pytest.raises(ValidationError):` for every constraint violation.

**Phase 5 test classes (one per schema):**
- `TestBullClaim` — rejects empty claim/evidence; rejects invalid source_analyst.
- `TestBullCase` — rejects <3 claims; happy path with exactly 3.
- `TestBearClaim` — rejects empty; accepts optional `addresses_bull_claim=None`.
- `TestBearCase` — **`test_rejects_fewer_than_two_addressed_bull_claims`** — the DEBATE-02 enforcement test. Rejects `addressed_bull_claims=[]` AND `addressed_bull_claims=["only one"]`.
- `TestRebuttalAct` — rejects empty bull_rebuttals AND empty bear_rebuttals (both directions enforced).
- `TestFinalArguments` — rejects empty closings.
- `TestDebateSynthesis` — rejects out-of-range confidence/sub-scores; accepts full happy path.
- `TestEmptyActRaisesValidationError` — the DEBATE-03 success-criterion-3 explicit test class (RESEARCH.md line 775).

---

### `tests/unit/test_bull_agent.py` (and 4 peer files)

**Analog:** `tests/unit/test_manager_agent.py` (entire file).

**Imports + dummy-API-key pattern** (test_manager_agent.py lines 1-29):
```python
"""Tests for the Bull Advocate agent..."""

from __future__ import annotations

import os

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from ai_hedge_fund.agents.bull import (
    BULL_SYSTEM_PROMPT,
    bull_agent,
    format_analyst_evidence,
    get_bull_limits,
)
from ai_hedge_fund.schemas.debate import BullCase
```

**Agent-wiring test class pattern** (test_manager_agent.py lines 32-54):
```python
class TestBullAgent:
    def test_agent_exists(self) -> None:
        assert isinstance(bull_agent, Agent)

    def test_agent_model(self) -> None:
        assert bull_agent.model.model_name == "claude-opus-4-6"

    def test_agent_output_type(self) -> None:
        assert bull_agent._output_type is BullCase

    def test_agent_has_retries(self) -> None:
        assert bull_agent._max_result_retries == 2

    def test_agent_no_tools(self) -> None:
        tools = bull_agent._function_toolset.tools
        assert len(tools) == 0
```

Copy verbatim with symbol substitution for each of the 5 agent test files (`test_bull_agent.py`, `test_bear_agent.py`, `test_rebuttal_agent.py`, `test_final_arguments_agent.py`, `test_debate_synthesis_agent.py`).

**System-prompt content test pattern** (test_manager_agent.py lines 57-85):
```python
class TestBullSystemPrompt:
    def test_prompt_requires_source_analyst_citation(self) -> None:
        assert "source_analyst" in BULL_SYSTEM_PROMPT.lower() or "source analyst" in BULL_SYSTEM_PROMPT.lower()

    def test_prompt_forbids_vague_claims(self) -> None:
        assert "vague" in BULL_SYSTEM_PROMPT.lower() or "specific" in BULL_SYSTEM_PROMPT.lower()
```

**Bear-specific prompt test** (enforcement of DEBATE-02 "addresses at least 2 bull claims"):
```python
class TestBearSystemPrompt:
    def test_prompt_requires_addressing_two_bull_claims(self) -> None:
        assert "at least 2" in BEAR_SYSTEM_PROMPT.lower() or "addressed_bull_claims" in BEAR_SYSTEM_PROMPT
```

**Limits test pattern** (test_manager_agent.py lines 88-101): verify REASONING-tier caps (100_000 input, 16_000 output, 116_000 total). If a role uses `output_override`, assert the override value.

**Format-helper test pattern** (test_manager_agent.py lines 104-194): one test per branch (empty, single, multiple, error-branch, mixed-success-and-error).

---

### `tests/unit/test_debate_nodes.py` (test, async node wiring)

**Analog:** `tests/unit/test_multi_agent_nodes.py` (entire file).

**Imports pattern** (test_multi_agent_nodes.py lines 23-52):
```python
from __future__ import annotations

import asyncio
import inspect
import operator
import os
import typing

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai.models.test import TestModel  # noqa: E402

from ai_hedge_fund.agents.bull import bull_agent  # noqa: E402
# ... etc. all 5 debate agents ...
from ai_hedge_fund.graph.nodes import (  # noqa: E402
    bull_node, bear_node, rebuttal_node, final_arguments_node,
    debate_synthesis_node,
)
from ai_hedge_fund.schemas.state import DebatePipelineState  # noqa: E402
```

**TypedDict-reducer test class pattern** (test_multi_agent_nodes.py lines 54-93):
```python
class TestDebatePipelineStateSchema:
    def test_state_has_debate_fields(self) -> None:
        hints = typing.get_type_hints(DebatePipelineState, include_extras=True)
        for field in ("bull_case", "bear_case", "rebuttal", "final_arguments", "debate_synthesis"):
            assert field in hints

    def test_debate_fields_have_no_reducer(self) -> None:
        """Single-writer fields must NOT have operator.add (overwrite semantics)."""
        hints = typing.get_type_hints(DebatePipelineState, include_extras=True)
        for field in ("bull_case", "bear_case", "rebuttal", "final_arguments", "debate_synthesis"):
            hint = hints[field]
            metadata = typing.get_args(hint)
            assert operator.add not in metadata, (
                f"{field} must NOT carry operator.add reducer -- single-writer semantics"
            )
```

**Async-contract class pattern** (test_multi_agent_nodes.py lines 96-112):
```python
class TestDebateNodesAreAsync:
    def test_bull_node_is_async(self) -> None:
        assert inspect.iscoroutinefunction(bull_node)
    # ... etc for all 5 ...
```

**Happy-path node test pattern** (test_multi_agent_nodes.py lines 131-186):
```python
class TestBullNodeHappyPath:
    def test_returns_bull_case_dict(self) -> None:
        state: DebatePipelineState = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "analyst_reports": [{"analyst": "fundamental", "analysis": {"ticker": "AAPL"}, "tokens_used": 100}],
            "thesis": {"ticker": "AAPL", "bull_case": [], "bear_case": [], "confidence": 60, "risk_factors": []},
        }
        with bull_agent.override(model=TestModel()):
            result = asyncio.run(bull_node(state))

        assert "bull_case" in result
        assert isinstance(result["bull_case"], dict)
```

**Error-propagation test pattern** (test_multi_agent_nodes.py lines 290-321, `TestMultiAgentSignalNodeShortCircuits`):
```python
class TestDebateNodesShortCircuit:
    def test_bull_skips_when_error_in_state(self) -> None:
        state: DebatePipelineState = {"ticker": "AAPL", "as_of_date": "2024-01-02", "error": "upstream"}
        result = asyncio.run(bull_node(state))
        assert result == {}
```

**Phase-5-specific tests (DEBATE-04 enforcement):**
```python
class TestDebateSynthesisNode:
    def test_quality_score_is_recomputed(self) -> None:
        """LLM-produced quality_score is overwritten by compute_quality_score."""
        # Seed state with all prior acts present; override debate_synthesis_agent with TestModel.
        # Assert result["debate_synthesis"]["quality_score"] == round(
        #     0.4 * evidence_strength + 0.3 * logical_consistency + 0.3 * risk_coverage
        # )

    def test_pre_confidence_from_state(self) -> None:
        """pre_debate_confidence is sourced from state['thesis']['confidence'], not LLM output."""
        # state["thesis"]["confidence"] = 42
        # Override synthesis agent to return pre_debate_confidence=99 (wrong)
        # Assert result["debate_synthesis"]["pre_debate_confidence"] == 42

    def test_thesis_overwritten_with_revised_thesis(self) -> None:
        """Returned dict has both `debate_synthesis` and `thesis` keys; thesis is the revised one."""
```

---

### `tests/unit/test_quality_score.py` (test, pure function)

**Analog (closest):** `tests/unit/test_budget.py` (pure-logic tests of frozen-dataclass arithmetic).

**Pattern:**
- One `TestComputeQualityScore` class.
- Happy-path tests (all-0, all-100, middle values, known weighted mean).
- Boundary tests: `ValueError` for inputs outside `[0, 100]` (negative, 101).
- Explicit weight-verification test: given `(100, 0, 0)`, expect `round(0.4 * 100) == 40`.
- `pytest.raises(ValueError)` for every out-of-range input.

Example shape:
```python
class TestComputeQualityScore:
    def test_all_zero(self) -> None:
        assert compute_quality_score(0, 0, 0) == 0

    def test_all_hundred(self) -> None:
        assert compute_quality_score(100, 100, 100) == 100

    def test_weighted_mean(self) -> None:
        # 0.4 * 80 + 0.3 * 60 + 0.3 * 40 = 32 + 18 + 12 = 62
        assert compute_quality_score(80, 60, 40) == 62

    def test_rejects_negative_evidence(self) -> None:
        with pytest.raises(ValueError):
            compute_quality_score(-1, 50, 50)
    # ... etc for each sub-score and the >100 upper bound ...
```

---

### `tests/integration/test_debate_pipeline.py` (test, integration)

**Analog:** `tests/integration/test_multi_agent_pipeline.py` (entire file).

**Dummy-API-key + imports pattern** (test_multi_agent_pipeline.py lines 29-51):
```python
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.graph.state import CompiledStateGraph  # noqa: E402
from pydantic_ai.models.test import TestModel  # noqa: E402

# Import all 10 agents for override context manager.
from ai_hedge_fund.agents.fundamental import fundamental_agent
from ai_hedge_fund.agents.sentiment import sentiment_agent
from ai_hedge_fund.agents.technical import technical_agent
from ai_hedge_fund.agents.manager import manager_agent
from ai_hedge_fund.agents.bull import bull_agent
from ai_hedge_fund.agents.bear import bear_agent
from ai_hedge_fund.agents.rebuttal import rebuttal_agent
from ai_hedge_fund.agents.final_arguments import final_arguments_agent
from ai_hedge_fund.agents.debate_synthesis import debate_synthesis_agent
from ai_hedge_fund.agents.signal import signal_agent
from ai_hedge_fund.graph.pipeline import build_debate_pipeline, build_multi_agent_pipeline
```

**Compilation + topology tests** (test_multi_agent_pipeline.py lines 58-122): clone each function and substitute `build_debate_pipeline` / expected node set. Phase-5 node set: `{"fundamental","sentiment","technical","manager","bull","bear","rebuttal","final_arguments","debate_synthesis","signal","__start__","__end__"}` → 12 total nodes.

**Fan-out / fan-in / tail edge test** (test_multi_agent_pipeline.py lines 93-116):
```python
def test_debate_pipeline_edges() -> None:
    graph = build_debate_pipeline()
    edge_pairs = {(e.source, e.target) for e in graph.get_graph().edges}
    # Phase 4 fan-out/fan-in preserved
    assert ("__start__", "fundamental") in edge_pairs
    assert ("fundamental", "manager") in edge_pairs
    # Phase 5 debate chain
    assert ("manager", "bull") in edge_pairs
    assert ("bull", "bear") in edge_pairs
    assert ("bear", "rebuttal") in edge_pairs
    assert ("rebuttal", "final_arguments") in edge_pairs
    assert ("final_arguments", "debate_synthesis") in edge_pairs
    assert ("debate_synthesis", "signal") in edge_pairs
    assert ("signal", "__end__") in edge_pairs
    # Critical: manager -> signal direct edge MUST NOT exist (Pitfall 4)
    assert ("manager", "signal") not in edge_pairs
```

**Phase-4 no-regression tests** (test_multi_agent_pipeline.py lines 130-147): preserve `test_phase3_research_pipeline_still_compiles`, `test_phase1_pipeline_still_compiles`, and add a new `test_phase4_multi_agent_pipeline_still_compiles` (Option B: build_multi_agent_pipeline unchanged).

**TestModel end-to-end pattern** (test_multi_agent_pipeline.py lines 155-215): clone and extend the `with (... override, ... override, ...):` block to 10 agents. From RESEARCH.md Example 3 lines 661-699:
```python
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
```

Assertions extend Phase-4 asserts: `bull_case`, `bear_case` (with `addressed_bull_claims` non-empty), `rebuttal`, `final_arguments` all present; `debate_synthesis.quality_score` == deterministic weighted mean of sub-scores; Phase-4's `thesis` and `signal` dicts still present (signal node unchanged).

---

## Shared Patterns

### Module header + threat-model docstring
**Source:** every `src/ai_hedge_fund/agents/*.py` file (e.g., `manager.py` lines 1-12, `signal.py` lines 1-18).
**Apply to:** all 5 new agent files + `src/ai_hedge_fund/schemas/debate.py`.

```python
"""<Role> agent -- <one-line responsibility>.

<Paragraph on what the agent does, its tier, and its inputs/outputs.>

Threat mitigations:
    T-05-XX: <STRIDE category> -- <mitigation>.
    T-05-YY: DoS -- UsageLimits via get_<role>_limits() on every run.
"""
```

### `from __future__ import annotations`
**Source:** every file in `src/ai_hedge_fund/` (e.g., `manager.py:14`, `agents.py:13`, `state.py:21`, `nodes.py:27`, `pipeline.py:20`).
**Apply to:** ALL new files. Required by CLAUDE.md (`str | None` union syntax via `from __future__ import annotations`).

### Structlog per-node logger
**Source:** `src/ai_hedge_fund/graph/nodes.py:56`:
```python
logger = structlog.get_logger(__name__)
```
**Apply to:** no change needed for nodes.py (logger already exists); ensure any debate helper that logs uses the same `__name__`-scoped logger.

### Usage-limits + try/except UsageLimitExceeded idiom
**Source:** `src/ai_hedge_fund/graph/nodes.py:417-431` (`manager_node`):
```python
try:
    limits = get_manager_limits()
    result = await manager_agent.run(prompt, usage_limits=limits)
    usage = result.usage()
    logger.info(
        "manager_complete",
        ticker=state["ticker"],
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )
    return {"thesis": result.output.model_dump()}
except UsageLimitExceeded as e:
    logger.error("manager_budget_exceeded", ticker=state["ticker"], error=str(e))
    return {"error": f"Manager budget exceeded: {e}"}
```
**Apply to:** all 5 new debate node functions in `nodes.py`. Every node MUST catch `UsageLimitExceeded`, log the error event, and return `{"error": "..."}` — never raise. Downstream nodes short-circuit via `if state.get("error"): return {}`.

### Immutable-state return (NEVER mutate `state`)
**Source:** CLAUDE.md global rule ("return new objects, don't mutate in place") + `nodes.py:86, 122, 163, 205, 257, 428` — every node returns a NEW dict with only the keys it writes.
**Apply to:** all 5 new debate nodes. Planner: never do `state["bull_case"] = ...` or `state.update(...)`; always `return {"bull_case": ...}`. For `debate_synthesis_node`, use `.model_copy(update={...})` on the Pydantic output before `.model_dump()`.

### Pydantic `min_length` as the enforcement mechanism for DEBATE-01/02/03
**Source:** `src/ai_hedge_fund/schemas/agents.py:94-109` (`ThesisOutput`), and enforcement is verified in `tests/unit/test_specialist_schemas.py:101-120`.
**Apply to:** every substantive list field in `src/ai_hedge_fund/schemas/debate.py`. This IS the mechanism that causes "skipping or empty act → ValidationError" per success criterion 3 — no custom validator code needed.

### `Literal["fundamental","sentiment","technical","manager"]` for source_analyst
**Source:** `src/ai_hedge_fund/schemas/agents.py:346-348` (`AnalystReport.analyst`):
```python
analyst: Literal["fundamental", "sentiment", "technical"] = Field(
    description="Which specialist produced this report",
)
```
**Apply to:** every `BullClaim.source_analyst`, `BearClaim.source_analyst`, `RebuttalPoint.source_analyst`, etc. Phase 5 extends the Literal to include `"manager"` since bull/bear can cite manager's synthesis too.

### Dummy-API-key in tests
**Source:** `tests/unit/test_manager_agent.py:17-18`, `tests/unit/test_multi_agent_nodes.py:32`, `tests/integration/test_multi_agent_pipeline.py:36`:
```python
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")
```
**Apply to:** all new test files (`test_bull_agent.py`, `test_bear_agent.py`, ..., `test_debate_pipeline.py`). MUST be set BEFORE importing agents (PydanticAI validates the key at `Agent(...)` construction).

### `asyncio.run(_invoke())` sync-wrapper in tests
**Source:** `tests/integration/test_multi_agent_pipeline.py:180-190`, `tests/unit/test_multi_agent_nodes.py:141`.
**Apply to:** all new async-node tests. Keeps tests compatible with the project's `asyncio_mode = "auto"` pytest config without needing `async def` functions.

### `TestModel(call_tools=[])` for tool-holding agents
**Source:** `tests/integration/test_multi_agent_pipeline.py:182-184` (analyst overrides):
```python
fundamental_agent.override(model=TestModel(call_tools=[])),  # analysts have tools
```
**Apply to:** the 3 analyst agents in `test_debate_pipeline.py`. The 5 debate agents and signal agent have zero tools so `TestModel()` (no argument) is fine for them.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `compute_quality_score` helper inside `src/ai_hedge_fund/agents/debate_synthesis.py` | pure transform / computation | input → output | No existing pure-math scoring helper in the codebase. Closest analog in style is `src/ai_hedge_fund/data/summary.py` (natural-language formatter) or `PipelineBudgetTracker.total_used` (frozen-dataclass arithmetic). Pattern to apply: (1) module-level constants for weights with docstring explaining the rationale and surfacing Assumption A1 (RESEARCH.md line 719) for user sign-off; (2) `from __future__ import annotations` + explicit `int` type hints; (3) explicit `ValueError` raises for out-of-range inputs; (4) one-line `round(...)` return; (5) paired unit-test file `tests/unit/test_quality_score.py` covering boundary cases. |

Note: although the file has no direct code analog, the *location* (`agents/debate_synthesis.py`) and *interface shape* are fully specified by RESEARCH.md Pattern 3 (lines 342-397), and the *testing shape* mirrors `tests/unit/test_budget.py`.

## Metadata

**Analog search scope:**
- `src/ai_hedge_fund/agents/` (all files) — agent templates
- `src/ai_hedge_fund/schemas/` (all files) — schema templates
- `src/ai_hedge_fund/graph/` (all files) — node & pipeline templates
- `tests/unit/` — unit-test templates (manager, specialist schemas, multi-agent nodes)
- `tests/integration/` — integration-test templates (multi-agent pipeline)
- `src/ai_hedge_fund/data/` — pure-helper style references (summary.py)
- `src/ai_hedge_fund/models.py` and `src/ai_hedge_fund/agents/base.py` — tier + limits conventions

**Files scanned:** 15 source files + 5 test files (all with targeted non-overlapping reads; no re-reads).

**Pattern extraction date:** 2026-04-21

**Key reuse primitives the planner can pull directly:**
- `ModelTier.REASONING.value` (models.py:26) → Opus model string for all 5 debate agents.
- `get_usage_limits(ModelTier.REASONING, output_override=...)` (agents/base.py:82-115) → per-role token cap; `output_override` is the cost-control lever for rebuttal/final (RESEARCH.md Pitfall 6).
- `format_analyst_reports` (manager.py:68-100) → clonable template for each debate-prompt formatter.
- `manager_node`'s try/except block (nodes.py:417-431) → canonical debate-node template.
- `build_multi_agent_pipeline`'s builder structure (pipeline.py:102-158) → clone verbatim, swap state type, replace manager→signal edge with the debate chain.
- `ThesisOutput` schema (agents.py:82-110) → reused directly inside `DebateSynthesis.revised_thesis`; DO NOT redefine.
- `AnalystReport.analyst` Literal (agents.py:346) → pattern for `source_analyst` Literal in every debate claim.
- `tests/unit/test_specialist_schemas.py` (entire file) → template for every Phase-5 schema test.
- `tests/unit/test_manager_agent.py` (entire file) → template for each of the 5 per-agent wiring test files.
- `tests/unit/test_multi_agent_nodes.py` (entire file) → template for `test_debate_nodes.py` (include the `operator.add`-not-present assertion for single-writer debate fields).
- `tests/integration/test_multi_agent_pipeline.py` (entire file) → template for `test_debate_pipeline.py` (extend override block to 10 agents; assert no `manager→signal` direct edge).
