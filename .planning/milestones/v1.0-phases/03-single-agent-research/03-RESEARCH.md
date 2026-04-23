# Phase 3: Single-Agent Research - Research

**Researched:** 2026-04-12
**Domain:** PydanticAI agent tool orchestration, LangGraph state extension, investment thesis generation
**Confidence:** HIGH

## Summary

Phase 3 builds a single research agent that proves the core research loop: read SEC filings via Phase 2 data tools, compute financial metrics via deterministic tool calls, and produce a structured investment thesis with quantitative signal. This is the first time an LLM meets the data tools, and the critical design challenge is bridging PydanticAI's tool/dependency injection system with the 6 existing data tool functions from Phase 2.

The codebase already has all necessary infrastructure: `create_agent()` factory with ModelTier routing, `PipelineBudgetTracker` for cost control, `ThesisOutput`/`SignalOutput` Pydantic schemas (though these need constraint tightening), 6 data tools with `@enforce_as_of_date` temporal enforcement, and a LangGraph pipeline with checkpointing. The research agent will use PydanticAI's `RunContext[ResearchDeps]` dependency injection to pass `ticker`, `as_of_date`, and `db_session` to thin tool wrappers that call the underlying Phase 2 data functions. PydanticAI 1.80.0 (installed) supports both `tools=` on the Agent constructor and `FunctionToolset` for grouping tools.

**Primary recommendation:** Create a `ResearchDeps` dataclass carrying `ticker`, `as_of_date`, and optional `db_session`/`settings`. Define 6 thin tool wrappers using `@agent.tool` that extract deps from `RunContext` and call the existing Phase 2 data tool functions. Tighten `ThesisOutput` constraints (min_length=3 for bull/bear, min_length=2 for risk_factors). Add a `research_node` to the LangGraph pipeline that wraps the research agent and records usage to `PipelineBudgetTracker`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- infrastructure phase with all implementation choices at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion -- infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints from PROJECT.md and CLAUDE.md:
- Tool-first for quantitative work -- LLMs NEVER compute financial ratios, run backtests, or calculate position sizes directly
- Strict temporal controls -- every data input timestamped, RAG filtered by "available as of analysis date"
- Thesis output must include: bull case (3+ points with filing citations), bear case (3+ citations), confidence score (0-100), risk factors
- Signal output must include: direction (long/short/neutral), conviction level, time horizon, position size suggestion
- All fields validated against Pydantic schemas with no missing values
- Token budgets enforced per agent via PydanticAI UsageLimits (from Phase 1)
- Langfuse trace must show tool invocations for every financial metric
- PydanticAI agents with typed I/O and dependency injection (from Phase 1)
- Data tools from Phase 2: get_filing_sections, get_financial_summary, get_price_history, get_insider_clusters, get_news_sentiment, get_macro_context

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase, no discussion occurred.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AGENT-01 | Hypothesis Generator agent can produce a structured investment thesis from SEC filing analysis | ResearchDeps + @agent.tool wrappers call get_filing_sections and get_financial_summary; ThesisOutput schema captures thesis; ModelTier.ANALYSIS (Sonnet) for thesis generation |
| AGENT-02 | Agent uses tool augmentation for all financial calculations (ratios, growth rates, valuation metrics) | All 6 data tools produce natural language summaries with pre-computed metrics; system prompt explicitly forbids LLM number generation; Langfuse traces verify tool invocation |
| AGENT-03 | Thesis output includes: bull case, bear case, evidence citations, confidence score (0-100), risk factors | ThesisOutput schema extended with min_length=3 for bull/bear cases, min_length=2 for risk factors; new ThesisPoint sub-model with claim + citation fields |
| AGENT-04 | Signal output includes: direction (long/short/neutral), conviction level, time horizon, position size suggestion | SignalOutput schema already has all required fields; signal generation node takes ThesisOutput and produces SignalOutput |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Language:** Python 3.12, `uv` for packages
- **Linter/formatter:** ruff (line-length=100, target-version=py312): `ruff format . && ruff check . --fix`
- **Testing:** pytest with asyncio_mode="auto", 80%+ coverage target
- **Immutability:** All dataclasses frozen, return new objects never mutate
- **Tool-first:** LLMs NEVER compute financial ratios directly -- orchestrate tools
- **Temporal controls:** Every data input timestamped, `@enforce_as_of_date` on all tools
- **Token budgets:** Every agent has UsageLimits, pipeline has PipelineBudgetTracker
- **File limits:** Functions under 50 lines, files under 800 lines
- **Type hints:** Required on all function params and return values
- **Error handling:** Handle errors explicitly at every level, never silently swallow

## Standard Stack

### Core (Already Installed -- No New Dependencies)

| Library | Version (Installed) | Purpose | Why Standard |
|---------|---------------------|---------|--------------|
| pydantic-ai | 1.80.0 | Agent definitions, tool registration, RunContext DI | Already in stack; `FunctionToolset`, `@agent.tool`, `RunContext[T]` provide exact patterns needed | [VERIFIED: uv pip list]
| langgraph | 1.1.6 | Pipeline graph, state management, checkpointing | Already in stack; `StateGraph` with `PipelineState` TypedDict | [VERIFIED: uv pip list]
| pydantic | 2.12.5 | Schema validation for ThesisOutput, SignalOutput | Already in stack; Field constraints enforce AGENT-03/04 | [VERIFIED: uv pip list]
| langfuse | 4.2.0 | Observability -- trace tool invocations for AGENT-02 verification | Already in stack; `CallbackHandler` integration | [VERIFIED: uv pip list]
| structlog | 25.5.0 | Structured logging for agent nodes | Already in stack | [VERIFIED: uv pip list]
| anthropic | 0.94.0 | Claude model API | Already in stack | [VERIFIED: uv pip list]

### Supporting (Already Installed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.3 | Unit tests for agent, tools, schemas | All test phases | [VERIFIED: uv run pytest --version]
| pytest-asyncio | installed | Async test support for agent.run() | All async agent tests | [VERIFIED: pyproject.toml]

**No new packages needed.** All required libraries are installed. This phase is purely about wiring existing infrastructure together.

## Architecture Patterns

### Recommended Project Structure for Phase 3

```
src/ai_hedge_fund/
├── agents/
│   ├── base.py                    # EXISTING: create_agent, PipelineBudgetTracker
│   ├── extraction.py              # EXISTING: Haiku extraction agent
│   ├── analysis.py                # EXISTING: Sonnet analysis agent
│   └── research.py                # NEW: Research agent with tool wrappers
├── schemas/
│   ├── agents.py                  # MODIFY: Tighten ThesisOutput constraints
│   └── state.py                   # MODIFY: Extend PipelineState for research
├── graph/
│   ├── pipeline.py                # MODIFY: Add research + signal nodes
│   └── nodes.py                   # MODIFY: Add research_node, signal_node
└── data/tools/                    # EXISTING: All 6 data tools (no changes)
```

### Pattern 1: Dependency Injection for Agent Tools

**What:** Use PydanticAI `RunContext[ResearchDeps]` to inject pipeline context (ticker, as_of_date, db_session) into tool functions, so the LLM only controls tool selection -- not infrastructure parameters.

**When to use:** Every tool the research agent calls.

**Example:**

```python
# Source: verified against PydanticAI 1.80.0 (pydantic.dev/docs/ai/tools-toolsets/tools/)
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic_ai import Agent, RunContext
from sqlalchemy.orm import Session

from ai_hedge_fund.agents.base import create_agent, get_usage_limits
from ai_hedge_fund.config import AppSettings
from ai_hedge_fund.data.tools import get_filing_sections, get_financial_summary
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.agents import ThesisOutput


@dataclass(frozen=True)
class ResearchDeps:
    """Immutable dependency container for the research agent."""
    ticker: str
    as_of_date: date
    db_session: Session | None = None
    settings: AppSettings | None = None


research_agent: Agent[ResearchDeps, ThesisOutput] = Agent(
    ModelTier.ANALYSIS.value,
    output_type=ThesisOutput,
    deps_type=ResearchDeps,
    system_prompt=RESEARCH_SYSTEM_PROMPT,
)


@research_agent.tool
def fetch_filing_sections(
    ctx: RunContext[ResearchDeps],
    form_type: str = "10-K",
    max_filings: int = 3,
) -> str:
    """Retrieve SEC filing sections for the company being analyzed.

    Args:
        form_type: SEC form type -- "10-K" for annual, "10-Q" for quarterly.
        max_filings: Maximum number of recent filings to retrieve.
    """
    result = get_filing_sections(
        ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date,
        form_type=form_type,
        max_filings=max_filings,
        db_session=ctx.deps.db_session,
        settings=ctx.deps.settings,
    )
    # Return text for LLM consumption
    return _format_filings_for_llm(result)
```

**Key insight:** The LLM controls `form_type` and `max_filings` (what to look up). The `ticker`, `as_of_date`, `db_session`, and `settings` come from `ResearchDeps` via `RunContext` (infrastructure the LLM should never control).

### Pattern 2: Two-Phase Agent Pipeline (Research -> Signal)

**What:** Split the research process into two distinct agent calls: (1) ThesisOutput generation via research agent with all tools, (2) SignalOutput generation from the thesis via a lighter signal agent.

**When to use:** AGENT-03 and AGENT-04 require different output schemas.

**Example:**

```python
# Research node produces ThesisOutput
async def research_node(state: ResearchPipelineState) -> dict:
    deps = ResearchDeps(
        ticker=state["ticker"],
        as_of_date=state["as_of_date"],
    )
    result = await research_agent.run(
        f"Produce an investment thesis for {state['ticker']}",
        deps=deps,
        usage_limits=get_usage_limits(ModelTier.ANALYSIS),
    )
    return {"thesis": result.output.model_dump()}

# Signal node takes thesis, produces SignalOutput
async def signal_node(state: ResearchPipelineState) -> dict:
    result = await signal_agent.run(
        f"Generate a trade signal from this thesis: {state['thesis']}",
        usage_limits=get_usage_limits(ModelTier.ANALYSIS),
    )
    return {"signal": result.output.model_dump()}
```

### Pattern 3: LangGraph State Extension

**What:** Extend `PipelineState` with research-specific fields (as_of_date, thesis, signal) without breaking the existing extract -> analyze flow.

**Example:**

```python
# Source: existing codebase pattern in schemas/state.py
class ResearchPipelineState(TypedDict, total=False):
    """Extended state for the research pipeline."""
    ticker: Required[str]
    as_of_date: Required[str]  # ISO format date string
    thesis: dict | None        # ThesisOutput.model_dump()
    signal: dict | None        # SignalOutput.model_dump()
    error: str | None
```

### Anti-Patterns to Avoid

- **Letting LLM control ticker/as_of_date:** These must come from pipeline state via deps injection, not from LLM tool call arguments. If the LLM picks a different ticker or date, temporal correctness is broken.
- **Passing raw JSON/XBRL to LLM:** All data tools already produce NL summaries (`summary_text` field). Pass those, not raw metric dicts.
- **Single monolithic agent:** Don't make one agent produce both ThesisOutput and SignalOutput. Two separate agents with separate schemas keeps the output types clean and testable.
- **Skipping UsageLimits:** Every agent.run() call MUST pass usage_limits per project conventions. The ANALYSIS tier budget is 58,000 tokens total.
- **Mutating state:** Nodes must return new dicts, never modify the `state` parameter.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Agent tool registration | Custom tool dispatch | PydanticAI `@agent.tool` + `RunContext` | Automatic JSON schema generation, docstring extraction, type-safe DI | [VERIFIED: PydanticAI 1.80.0]
| Financial metric computation | LLM-generated ratios | Phase 2 data tools (`get_financial_summary`, etc.) | Tool-first principle: deterministic, auditable, no hallucination | [VERIFIED: codebase]
| Pipeline state management | Custom state passing | LangGraph `StateGraph` + `TypedDict` | Already in stack, checkpointing built in | [VERIFIED: codebase]
| Budget enforcement | Custom token counting | `PipelineBudgetTracker` + `UsageLimits` | Already built in Phase 1 with audit trail | [VERIFIED: codebase]
| Observability/tracing | Custom logging | Langfuse `CallbackHandler` via `create_langfuse_config()` | Already built in Phase 1, traces tool calls automatically | [VERIFIED: codebase]
| NL summary generation | LLM summarization of raw data | `format_financial_summary()`, `format_price_summary()`, etc. | Already built in Phase 2, deterministic formatting | [VERIFIED: codebase]
| Temporal enforcement | Manual date checks | `@enforce_as_of_date` decorator | Already built in Phase 2, validates + normalizes dates | [VERIFIED: codebase]

**Key insight:** Phase 3 is primarily a *wiring* phase. All the hard infrastructure exists. The new code is thin wrappers (tool functions), schema tightening, and pipeline assembly.

## Common Pitfalls

### Pitfall 1: LLM Generates Financial Numbers Instead of Using Tools
**What goes wrong:** The research agent produces "revenue of $400B" without calling `get_financial_summary` -- hallucinating numbers.
**Why it happens:** LLMs are confident about well-known companies and will generate plausible-sounding numbers from training data.
**How to avoid:** (1) System prompt explicitly forbids number generation: "NEVER state a financial figure unless it came from a tool call." (2) Langfuse trace verification: every metric in the thesis must have a preceding tool invocation in the trace. (3) ThesisPoint schema requires `source_tool` field.
**Warning signs:** Thesis contains specific numbers but Langfuse trace shows zero tool calls.

### Pitfall 2: Temporal Leak via LLM Training Data
**What goes wrong:** Agent uses knowledge of events after `as_of_date` (e.g., analyzing AAPL as of 2024-01-01 but mentioning Q2 2024 results).
**Why it happens:** LLM training data contains future information relative to the analysis date.
**How to avoid:** (1) System prompt states "You are analyzing as of {as_of_date}. You have NO knowledge of events after this date." (2) All data tools already enforce `@enforce_as_of_date`. (3) Success criterion 4 tests temporal correctness: same ticker, different dates -> materially different theses.
**Warning signs:** Thesis references events/data that hadn't occurred yet as of `as_of_date`.

### Pitfall 3: Agent Doesn't Call Enough Tools
**What goes wrong:** Agent calls only `get_filing_sections` and skips financial summary, price history, etc., producing a one-dimensional thesis.
**Why it happens:** LLM decides the filing text is sufficient and stops calling tools.
**How to avoid:** (1) System prompt lists required data sources: "You MUST call get_financials, get_price_history, and at least one of [get_insider_clusters, get_news_sentiment, get_macro_context]." (2) Post-run validation checks that minimum tool call count was met.
**Warning signs:** ThesisOutput lacks quantitative data points, bull/bear cases are opinion-only.

### Pitfall 4: Tool Wrapper Returns Too Much Data
**What goes wrong:** Tool wrapper returns the full `get_price_history` output including 252 daily price records, consuming entire token budget.
**Why it happens:** Passing raw tool output (including `prices` list with 252 items) to the LLM.
**How to avoid:** Tool wrappers return only `summary_text` and `stats` -- not the raw `prices` list. The NL summaries from Phase 2 are specifically designed for LLM consumption.
**Warning signs:** Token budget exceeded on first tool call, or agent only makes one tool call before running out.

### Pitfall 5: Schema Validation Failures on Edge Cases
**What goes wrong:** Agent produces a ThesisOutput where bull_case has only 2 items (needs 3), or confidence is 101.
**Why it happens:** LLM doesn't always respect Pydantic constraints, especially under token pressure.
**How to avoid:** (1) PydanticAI automatically retries on validation failure (configurable via `retries` param). (2) Set `retries=2` on the agent for structured output retry. (3) System prompt reinforces the constraints: "Your bull case MUST have at least 3 points."
**Warning signs:** Agent runs succeed but produce partial/invalid schemas.

### Pitfall 6: Sync/Async Mismatch in Tool Calls
**What goes wrong:** PydanticAI agent.run() is async, but data tools (get_filing_sections, etc.) are sync.
**Why it happens:** Phase 2 data tools are synchronous functions (they use synchronous HTTP clients and SQLAlchemy sessions).
**How to avoid:** PydanticAI handles this correctly -- sync tool functions work fine with async agent.run(). The framework runs sync tools in a thread pool automatically. No special handling needed. [VERIFIED: PydanticAI docs confirm sync tools are supported]
**Warning signs:** N/A -- this is a non-issue but worth documenting to prevent premature async conversion.

## Code Examples

### Research Agent Definition (complete pattern)

```python
# Source: codebase patterns + PydanticAI 1.80.0 official docs
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic_ai import Agent, RunContext
from sqlalchemy.orm import Session

from ai_hedge_fund.config import AppSettings
from ai_hedge_fund.data.tools import (
    get_filing_sections,
    get_financial_summary,
    get_insider_clusters,
    get_macro_context,
    get_news_sentiment,
    get_price_history,
)
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.agents import ThesisOutput


@dataclass(frozen=True)
class ResearchDeps:
    """Immutable dependency container for the research agent.

    Carries pipeline context through to tool calls via RunContext.
    """
    ticker: str
    as_of_date: date
    db_session: Session | None = None
    settings: AppSettings | None = None


RESEARCH_SYSTEM_PROMPT = """\
You are a senior equity research analyst producing an investment thesis.

RULES:
1. NEVER state a financial figure unless it came from a tool call.
2. You are analyzing as of {as_of_date}. You have NO knowledge after this date.
3. You MUST call get_financials and get_price_history at minimum.
4. Call at least one of: get_insider_activity, get_sentiment, get_macro_environment.
5. Every bull/bear point MUST cite the specific tool and data that supports it.
6. Your bull case needs at least 3 points, bear case at least 3, risk factors at least 2.
"""


research_agent: Agent[ResearchDeps, ThesisOutput] = Agent(
    ModelTier.ANALYSIS.value,
    output_type=ThesisOutput,
    deps_type=ResearchDeps,
    system_prompt=RESEARCH_SYSTEM_PROMPT,
    retries=2,
)
```

### Tool Wrapper Pattern

```python
# Source: PydanticAI RunContext pattern (pydantic.dev/docs/ai/core-concepts/dependencies/)
@research_agent.tool
def get_financials(ctx: RunContext[ResearchDeps]) -> str:
    """Get XBRL financial summary (revenue, net income, margins, EPS with YoY changes).

    Returns a natural language summary of the most recent financial data.
    """
    result = get_financial_summary(
        ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date,
        db_session=ctx.deps.db_session,
        settings=ctx.deps.settings,
    )
    return result["summary_text"]


@research_agent.tool
def get_price_data(
    ctx: RunContext[ResearchDeps],
    lookback_days: int = 252,
) -> str:
    """Get historical price data with return, volatility, and 52-week range.

    Args:
        lookback_days: Number of calendar days to look back (default 252 ~ 1 year).
    """
    result = get_price_history(
        ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date,
        lookback_days=lookback_days,
        db_session=ctx.deps.db_session,
        settings=ctx.deps.settings,
    )
    # Return only summary + stats, NOT the full prices list (token budget)
    return f"{result['summary_text']}\n\nStats: {result['stats']}"
```

### Research Node (LangGraph integration)

```python
# Source: existing node pattern in graph/nodes.py
async def research_node(state: ResearchPipelineState) -> dict:
    """Wrap research agent as LangGraph node."""
    try:
        deps = ResearchDeps(
            ticker=state["ticker"],
            as_of_date=date.fromisoformat(state["as_of_date"]),
        )
        limits = get_usage_limits(ModelTier.ANALYSIS)
        result = await research_agent.run(
            f"Produce an investment thesis for {deps.ticker}",
            deps=deps,
            usage_limits=limits,
        )
        usage = result.usage()
        logger.info(
            "research_complete",
            ticker=deps.ticker,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            tool_calls=usage.tool_calls,
        )
        return {"thesis": result.output.model_dump()}
    except UsageLimitExceeded as e:
        logger.error("research_budget_exceeded", ticker=state["ticker"], error=str(e))
        return {"error": f"Research budget exceeded: {e}"}
```

### ThesisOutput Schema Enhancement

```python
# Source: existing schemas/agents.py pattern + AGENT-03 requirements
class ThesisPoint(BaseModel):
    """A single bull or bear case point with evidence citation."""
    claim: str = Field(description="The investment argument")
    evidence: str = Field(description="Specific data supporting the claim")
    source_tool: str = Field(description="Which tool provided the evidence")


class ThesisOutput(BaseModel):
    """Thesis output meeting AGENT-03 requirements."""
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
        description="Named risk factors that could invalidate the thesis",
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PydanticAI `tools=` (list of functions) | PydanticAI `FunctionToolset` + `@agent.tool` | PydanticAI 1.x (2025-2026) | Toolsets enable composition, filtering, prefixing; `@agent.tool` is simpler for single-agent use | [VERIFIED: PydanticAI 1.80.0]
| `ai.pydantic.dev` docs | `pydantic.dev/docs/ai/` (redirected) | 2026 | Old URLs redirect to new Pydantic unified docs site | [VERIFIED: 301 redirect observed]
| LangGraph 0.x | LangGraph 1.1.6 | 2025-2026 | Stable API, `StateGraph` pattern unchanged | [VERIFIED: installed version]

**Deprecated/outdated:**
- PydanticAI docs at `ai.pydantic.dev` now redirect to `pydantic.dev/docs/ai/` [VERIFIED: 301 redirect]
- PydanticAI `Tool` class for wrapping -- still works but `@agent.tool` decorator is the preferred pattern for single-agent use [CITED: pydantic.dev/docs/ai/tools-toolsets/tools/]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | System prompt with explicit "NEVER state a financial figure without a tool call" will be sufficient to prevent LLM number hallucination | Pitfalls, Code Examples | LOW -- Langfuse trace verification is the real guard; prompt is defense-in-depth |
| A2 | PydanticAI retries=2 is sufficient for ThesisOutput validation recovery | Pitfalls | LOW -- can increase if needed; PydanticAI retries are cheap (only retries the output generation, not tool calls) |
| A3 | ModelTier.ANALYSIS (Sonnet) is the right model tier for thesis generation | Architecture | LOW -- could upgrade to REASONING (Opus) if quality is insufficient, but Sonnet is much cheaper and should be tried first |
| A4 | Signal generation can be a separate lighter agent (not the same agent that produced the thesis) | Architecture Patterns | LOW -- if signal quality requires full thesis context, the signal agent just receives the full thesis dict |
| A5 | Returning only summary_text from data tools (not raw data) will provide enough information for thesis generation | Pitfalls | MEDIUM -- if the LLM needs specific numbers not in the summary, tool wrappers may need to include selected metrics |

## Open Questions

1. **Token budget adequacy for research agent**
   - What we know: ANALYSIS tier has 50K input / 8K output / 58K total budget. Research agent will call 3-6 tools, each returning NL summaries.
   - What's unclear: Whether 50K input tokens is enough for multiple tool responses + system prompt + thesis generation.
   - Recommendation: Start with ANALYSIS budget. If tool responses exceed budget, either (a) truncate individual tool responses, or (b) use `input_override` on `get_usage_limits()` to increase for research agent specifically.

2. **ThesisOutput backward compatibility**
   - What we know: ThesisOutput schema exists and is used by test files. Changing min_length from 1 to 3 and adding ThesisPoint sub-model will break existing tests.
   - What's unclear: Whether to modify in-place or create a new schema (e.g., `ResearchThesisOutput`).
   - Recommendation: Modify in-place -- the existing schema was a placeholder. Update tests to match new constraints.

3. **System prompt template vs static**
   - What we know: PydanticAI supports dynamic system prompts via `@agent.system_prompt` decorator that receives `RunContext`. The `as_of_date` needs to be in the prompt.
   - What's unclear: Whether to use a static prompt with {as_of_date} formatting or a dynamic prompt via decorator.
   - Recommendation: Use `@agent.system_prompt` decorator to inject `as_of_date` from `ResearchDeps` dynamically. This is the idiomatic PydanticAI pattern.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | Yes | 3.12.11 | -- | [VERIFIED]
| uv | Package management | Yes | 0.11.2 | -- | [VERIFIED]
| Docker | PostgreSQL (optional for tests) | Yes | 29.0.1 | SQLite in-memory (conftest.py) | [VERIFIED]
| pydantic-ai | Agent framework | Yes | 1.80.0 | -- | [VERIFIED]
| langgraph | Pipeline orchestration | Yes | 1.1.6 | -- | [VERIFIED]
| pytest | Testing | Yes | 9.0.3 | -- | [VERIFIED]
| pytest-asyncio | Async tests | Yes | installed | -- | [VERIFIED]

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

**Note:** `ANTHROPIC_API_KEY` is required at runtime for actual LLM calls but not for unit tests (use `TestModel` from pydantic_ai.models.test).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/ -x -q` |
| Full suite command | `uv run pytest tests/ -x -q --ignore=tests/integration/` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AGENT-01 | Research agent produces ThesisOutput from filing data | unit | `uv run pytest tests/unit/test_research_agent.py -x` | No -- Wave 0 |
| AGENT-02 | Agent uses tools for all financial metrics (no LLM-generated numbers) | unit | `uv run pytest tests/unit/test_research_agent.py::test_tool_invocations -x` | No -- Wave 0 |
| AGENT-03 | ThesisOutput has 3+ bull/bear points with citations, confidence 0-100, 2+ risks | unit | `uv run pytest tests/unit/test_schemas.py -x` | Partial -- schema tests exist but need constraint updates |
| AGENT-04 | SignalOutput has direction, conviction, time_horizon, position_size | unit | `uv run pytest tests/unit/test_schemas.py -x` | Yes -- SignalOutput tests exist |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q --ignore=tests/integration/`
- **Phase gate:** Full unit suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_research_agent.py` -- covers AGENT-01, AGENT-02 (agent creation, tool registration, tool invocation verification, ThesisOutput production)
- [ ] `tests/unit/test_signal_agent.py` -- covers AGENT-04 (signal generation from thesis)
- [ ] Update `tests/unit/test_schemas.py` -- covers AGENT-03 (tightened ThesisOutput constraints, ThesisPoint sub-model)
- [ ] `tests/unit/test_research_node.py` -- covers research_node + signal_node LangGraph integration

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A -- no user auth in this phase |
| V3 Session Management | No | N/A -- no user sessions |
| V4 Access Control | No | N/A -- single user system |
| V5 Input Validation | Yes | Pydantic schema validation on all agent outputs; `@enforce_as_of_date` on all tool inputs |
| V6 Cryptography | No | N/A -- no crypto operations |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| LLM prompt injection via filing text | Tampering | Tool outputs are treated as data, not instructions; structured output validation |
| Token budget exhaustion (DoS) | DoS | `UsageLimits` per agent + `PipelineBudgetTracker` per pipeline (existing) |
| Temporal data leakage (look-ahead) | Information Disclosure | `@enforce_as_of_date` on all tools + system prompt date restriction |
| API key exposure | Information Disclosure | Keys in `.env` only, validated at startup via `AppSettings`, never in code |
| LLM hallucinating financial numbers | Tampering | Tool-first principle: system prompt forbids, Langfuse traces verify |

## Sources

### Primary (HIGH confidence)
- PydanticAI tools documentation: [pydantic.dev/docs/ai/tools-toolsets/tools/](https://pydantic.dev/docs/ai/tools-toolsets/tools/) -- tool decorators, RunContext, Tool class
- PydanticAI dependencies documentation: [pydantic.dev/docs/ai/core-concepts/dependencies/](https://pydantic.dev/docs/ai/core-concepts/dependencies/) -- deps_type, RunContext injection pattern
- PydanticAI toolsets documentation: [pydantic.dev/docs/ai/tools-toolsets/toolsets/](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/) -- FunctionToolset, CombinedToolset
- Codebase verification: All existing patterns verified by reading source files directly

### Secondary (MEDIUM confidence)
- PydanticAI 1.80.0 runtime verification: FunctionToolset, Tool class, Agent constructor params all confirmed via Python import tests

### Tertiary (LOW confidence)
- None -- all claims verified against installed packages or official docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all packages already installed and version-verified
- Architecture: HIGH -- patterns verified against PydanticAI 1.80.0 API and existing codebase patterns
- Pitfalls: HIGH -- derived from codebase analysis and PydanticAI documentation

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (stable stack, no fast-moving dependencies)
