# Phase 4: Multi-Agent Specialization - Research

**Researched:** 2026-04-20
**Domain:** Multi-agent PydanticAI specialization + LangGraph parallel orchestration
**Confidence:** HIGH

## Summary

Phase 4 replaces the single generalist research agent (Phase 3) with three domain-specialist analyst agents (Fundamental, Sentiment, Technical/Quant) and a Research Manager that synthesizes their outputs. The existing codebase provides a clean extension path: the `ResearchDeps` dataclass, PydanticAI `Agent` pattern, tool wrappers, and LangGraph node/pipeline patterns are all reusable. The primary technical challenge is (a) designing the fan-out/fan-in LangGraph topology where analysts run in parallel and the manager consumes their combined outputs, and (b) defining new Pydantic schemas for each specialist's domain-specific output that enable the manager to identify conflicts.

The 6 data tools from Phase 2 map cleanly to 3 specialist domains: Fundamental gets `get_filing_sections` + `get_financial_summary`, Sentiment gets `get_news_sentiment` + `get_insider_clusters`, and Technical/Quant gets `get_price_history`. The `get_macro_context` tool is cross-cutting context -- it should be available to the Fundamental analyst (macro impacts valuation) and optionally the manager. Each specialist agent follows the exact same PydanticAI `Agent[ResearchDeps, SpecialistOutput]` pattern established in Phase 3, using `@agent.tool` decorators with `RunContext[ResearchDeps]` for dependency injection.

**Primary recommendation:** Use LangGraph's static fan-out pattern (multiple edges from a single node) to run analysts in parallel, with an `Annotated[list, operator.add]` reducer on the state to collect analyst reports, then fan-in to a manager node that receives all reports and produces the unified `ThesisOutput`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- infrastructure phase with all choices at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion -- infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints from PROJECT.md and CLAUDE.md:
- Manager-Analyst Hierarchy pattern (validated by FinCon NeurIPS 2024, TradingAgents, AlphaAgents/BlackRock)
- Fundamental Analyst: SEC filing RAG + XBRL financial data, valuation metrics -- cites specific filing sections
- Sentiment Analyst: news sentiment + insider trading activity + (where available) earnings call tone -- composite sentiment score with component breakdown
- Technical/Quant Analyst: momentum, volatility indicators via computed tools -- no LLM price pattern descriptions without tool backing
- Research Manager: receives all 3 reports, produces unified thesis with agreement/conflict identification and resolution
- Tool-first principle continues -- LLMs orchestrate tools, never compute financial metrics directly
- PydanticAI agents with typed I/O (Phase 1 pattern), data tools from Phase 2
- Dual-model routing: analysts on Sonnet, manager potentially on Opus for complex synthesis
- Token budgets enforced per agent

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MULTI-01 | Fundamental Analyst agent -- RAG over SEC filings, financial statement analysis, valuation | Specialist agent with `get_filing_sections` + `get_financial_summary` + `get_macro_context` tools; `FundamentalAnalysis` output schema with valuation metrics and filing citations |
| MULTI-02 | Sentiment Analyst agent -- news sentiment, earnings call tone, insider activity signals | Specialist agent with `get_news_sentiment` + `get_insider_clusters` tools; `SentimentAnalysis` output schema with composite sentiment score and component breakdown |
| MULTI-03 | Technical/Quant Analyst agent -- price patterns, momentum, volatility indicators via computed tools | Specialist agent with `get_price_history` tool only; `TechnicalAnalysis` output schema with momentum/volatility metrics; system prompt forbids LLM price pattern descriptions |
| MULTI-04 | Research Manager agent synthesizes analyst outputs into unified thesis with conflict resolution | Manager agent on REASONING tier (Opus); receives all 3 specialist outputs; produces `ThesisOutput` (existing schema); explicit conflict identification in system prompt |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tool-first for quantitative work.** LLMs NEVER compute financial ratios, run backtests, or calculate position sizes directly. They orchestrate tools that do this deterministically.
- **Strict temporal controls.** Every data input must have a timestamp. RAG retrieval must filter by "available as of analysis date." This prevents look-ahead bias.
- **Token budgets from day one.** Every agent has a per-run token cap. Every pipeline has a total cost cap. Use Langfuse to track.
- **Immutable data patterns.** Return new objects, don't mutate in place. Frozen dataclasses, tuple records.
- **Type hints required** on all function params and return values.
- **Functions under 50 lines, files under 800 lines.**
- **ruff** for formatting and linting: `ruff format . && ruff check . --fix`
- **pytest with asyncio_mode = "auto"** for async tests.
- All timestamps in UTC. Financial data preserves source precision.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Fundamental analysis (SEC filings, financials, valuation) | Agent Logic (PydanticAI) | Data Layer (tools) | Agent orchestrates tool calls; tools fetch/compute data deterministically |
| Sentiment analysis (news, insider activity) | Agent Logic (PydanticAI) | Data Layer (tools) | Agent interprets sentiment signals from tool-provided summaries |
| Technical/Quant analysis (momentum, volatility) | Agent Logic (PydanticAI) | Data Layer (tools) | Agent derives conclusions from tool-computed indicators only |
| Research synthesis and conflict resolution | Agent Logic (PydanticAI) | -- | Manager agent is pure reasoning -- no tools, only analyst inputs |
| Parallel analyst execution | Orchestration (LangGraph) | -- | LangGraph fan-out/fan-in handles concurrent execution and state merging |
| Pipeline state management | Orchestration (LangGraph) | Database (PostgreSQL) | State flows through graph; checkpointer persists for durability |
| Output validation | Schema Layer (Pydantic) | -- | Typed output schemas enforce data quality at validation boundary |
| Token budget enforcement | Agent Logic (PydanticAI) | Orchestration (LangGraph) | PydanticAI UsageLimits per agent; PipelineBudgetTracker per pipeline |

## Standard Stack

### Core (already installed)
| Library | Installed Version | Purpose | Why Standard |
|---------|------------------|---------|--------------|
| langgraph | 1.1.6 | Parallel fan-out/fan-in orchestration, state management | Already in stack; fan-out via multiple edges from same node is a core feature [VERIFIED: pip list + Context7 docs] |
| pydantic-ai | 1.80.0 | Typed specialist agents with `Agent[ResearchDeps, Output]`, tool registration, TestModel for testing | Already in stack; `@agent.tool` + `RunContext[Deps]` pattern established in Phase 3 [VERIFIED: codebase + Context7 docs] |
| pydantic | 2.12.5 | Output schema validation with Field constraints (min_length, ge/le) | Already in stack; ThesisPoint, ThesisOutput patterns reused [VERIFIED: codebase] |
| structlog | (installed) | Structured logging per agent node | Already in stack; used in nodes.py for per-agent token logging [VERIFIED: codebase] |

### Supporting (already installed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic-ai TestModel | (bundled) | Test specialist agents without LLM calls | Unit and integration tests; `agent.override(model=TestModel(call_tools=[]))` pattern [VERIFIED: Context7 docs + codebase] |
| langgraph MemorySaver | (bundled) | In-memory checkpointing for tests | Test pipeline compilation and flow without PostgreSQL [VERIFIED: codebase] |

### No New Dependencies Required
This phase requires no new pip packages. All patterns are achievable with the existing stack.

## Architecture Patterns

### System Architecture Diagram

```
                    [Pipeline Input]
                    ticker + as_of_date
                           |
                    [Fan-Out Node]
                   /       |        \
    [Fundamental]   [Sentiment]   [Technical]
    (Sonnet)        (Sonnet)      (Sonnet)
    filing+fin+     news+insider  price tools
    macro tools     tools         only
         |              |              |
    FundamentalAn  SentimentAna   TechnicalAna
    alysis output  lysis output   lysis output
                   \       |        /
              [State Reducer: list.append]
                           |
                   [Research Manager]
                   (Opus -- REASONING tier)
                   Receives all 3 reports
                   Identifies agreements/conflicts
                           |
                   [ThesisOutput]
                   (existing schema)
                           |
                   [Signal Node]
                   (existing Phase 3)
                           |
                   [SignalOutput]
```

### Recommended Project Structure

```
src/ai_hedge_fund/
  agents/
    research.py            # KEEP: Phase 3 generalist (backward compat)
    signal.py              # KEEP: Unchanged
    base.py                # KEEP: create_agent, get_usage_limits, PipelineBudgetTracker
    fundamental.py         # NEW: Fundamental analyst agent + tool wrappers
    sentiment.py           # NEW: Sentiment analyst agent + tool wrappers
    technical.py           # NEW: Technical/Quant analyst agent + tool wrappers
    manager.py             # NEW: Research Manager agent (no tools)
  schemas/
    agents.py              # EXTEND: Add FundamentalAnalysis, SentimentAnalysis, TechnicalAnalysis, AnalystReport
    state.py               # EXTEND: Add MultiAgentPipelineState
  graph/
    nodes.py               # EXTEND: Add analyst nodes + manager node
    pipeline.py            # EXTEND: Add build_multi_agent_pipeline
  data/tools/              # UNCHANGED: All 6 tools reused as-is
```

### Pattern 1: Specialist Agent with Domain-Scoped Tools

**What:** Each specialist agent is a PydanticAI `Agent[ResearchDeps, SpecialistOutput]` with only the tools relevant to its domain registered via `@agent.tool`.
**When to use:** Every specialist agent (fundamental, sentiment, technical).
**Example:**

```python
# Source: Codebase pattern from src/ai_hedge_fund/agents/research.py
# Applied to fundamental specialist

from pydantic_ai import Agent, RunContext
from ai_hedge_fund.agents.research import ResearchDeps  # REUSE existing deps
from ai_hedge_fund.schemas.agents import FundamentalAnalysis
from ai_hedge_fund.models import ModelTier

fundamental_agent: Agent[ResearchDeps, FundamentalAnalysis] = Agent(
    ModelTier.ANALYSIS.value,
    output_type=FundamentalAnalysis,
    deps_type=ResearchDeps,
    retries=2,
)

@fundamental_agent.system_prompt
def fundamental_system_prompt(ctx: RunContext[ResearchDeps]) -> str:
    return FUNDAMENTAL_SYSTEM_PROMPT.format(
        ticker=ctx.deps.ticker,
        as_of_date=ctx.deps.as_of_date.isoformat(),
    )

# Only register domain-relevant tools
@fundamental_agent.tool
def fetch_filings(ctx: RunContext[ResearchDeps], form_type: str = "10-K", max_filings: int = 3) -> str:
    """Retrieve SEC filing sections."""
    results = get_filing_sections(ctx.deps.ticker, as_of_date=ctx.deps.as_of_date, ...)
    return _format_filings_for_llm(results)

@fundamental_agent.tool
def get_financials(ctx: RunContext[ResearchDeps]) -> str:
    """Get XBRL financial summary."""
    result = get_financial_summary(ctx.deps.ticker, as_of_date=ctx.deps.as_of_date, ...)
    return result["summary_text"]

@fundamental_agent.tool
def get_macro_environment(ctx: RunContext[ResearchDeps]) -> str:
    """Get macroeconomic context."""
    result = get_macro_context(as_of_date=ctx.deps.as_of_date, ...)
    return result["summary_text"]
```

### Pattern 2: LangGraph Fan-Out / Fan-In for Parallel Analysts

**What:** Use LangGraph's static edge fan-out from a single start point to run 3 analyst nodes in parallel, with an `Annotated[list, operator.add]` reducer to collect outputs, then fan-in to the manager node.
**When to use:** The multi-agent pipeline where analysts are independent.
**Example:**

```python
# Source: LangGraph official docs (Context7 /websites/langchain_oss_python_langgraph)
import operator
from typing import Annotated, Required
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

class MultiAgentPipelineState(TypedDict, total=False):
    ticker: Required[str]
    as_of_date: Required[str]
    # Annotated reducer: each analyst node appends to this list
    analyst_reports: Annotated[list[dict], operator.add]
    thesis: dict | None
    signal: dict | None
    error: str | None

def build_multi_agent_pipeline(checkpointer=None):
    builder = StateGraph(MultiAgentPipelineState)

    builder.add_node("fundamental", fundamental_node)
    builder.add_node("sentiment", sentiment_node)
    builder.add_node("technical", technical_node)
    builder.add_node("manager", manager_node)
    builder.add_node("signal", signal_node)

    # Fan-out: START -> all 3 analysts in parallel
    builder.add_edge(START, "fundamental")
    builder.add_edge(START, "sentiment")
    builder.add_edge(START, "technical")

    # Fan-in: all 3 analysts -> manager
    builder.add_edge("fundamental", "manager")
    builder.add_edge("sentiment", "manager")
    builder.add_edge("technical", "manager")

    # Manager -> signal -> END
    builder.add_edge("manager", "signal")
    builder.add_edge("signal", END)

    return builder.compile(checkpointer=checkpointer)
```

### Pattern 3: Manager Agent with No Tools (Pure Synthesis)

**What:** The Research Manager receives structured analyst outputs as part of its prompt, not as tools. It synthesizes a unified thesis by identifying agreements, conflicts, and applying weighted resolution.
**When to use:** The manager node that produces the final ThesisOutput.
**Example:**

```python
# Source: Codebase pattern from src/ai_hedge_fund/agents/signal.py
# Signal agent is the existing "no-tools" pattern
from pydantic_ai import Agent
from ai_hedge_fund.models import ModelTier
from ai_hedge_fund.schemas.agents import ThesisOutput

MANAGER_SYSTEM_PROMPT = """You are a Research Manager synthesizing analyst reports into a unified investment thesis.

You will receive reports from three specialist analysts:
1. Fundamental Analyst: valuation, financial metrics, SEC filing evidence
2. Sentiment Analyst: news sentiment, insider activity, market mood
3. Technical/Quant Analyst: momentum, volatility, price patterns

YOUR TASK:
- Identify where analysts AGREE (convergent signals strengthen confidence)
- Identify where analysts CONFLICT (e.g., bullish fundamentals vs bearish sentiment)
- For each conflict, explain which signal you weight more heavily and why
- Produce a unified thesis with explicit citations to each analyst's evidence
- Confidence score should reflect evidence quality, not just vote-counting
"""

manager_agent: Agent[None, ThesisOutput] = Agent(
    ModelTier.REASONING.value,  # Opus for complex synthesis
    output_type=ThesisOutput,
    system_prompt=MANAGER_SYSTEM_PROMPT,
    retries=2,
)
```

### Pattern 4: Analyst Node Returning Reports via Reducer

**What:** Each analyst node wraps its PydanticAI agent call and returns a dict that appends to the `analyst_reports` list in state via the `operator.add` reducer.
**When to use:** Every analyst node function.
**Example:**

```python
# Source: Codebase pattern from src/ai_hedge_fund/graph/nodes.py (research_node)
async def fundamental_node(state: MultiAgentPipelineState) -> dict:
    """Wrap fundamental analyst as LangGraph node."""
    try:
        deps = ResearchDeps(
            ticker=state["ticker"],
            as_of_date=date.fromisoformat(state["as_of_date"]),
        )
        limits = get_fundamental_limits()
        result = await fundamental_agent.run(
            f"Produce a fundamental analysis for {deps.ticker}",
            deps=deps,
            usage_limits=limits,
        )
        usage = result.usage()
        logger.info("fundamental_complete", ticker=deps.ticker,
                     input_tokens=usage.input_tokens, total_tokens=usage.total_tokens)
        report = {
            "analyst": "fundamental",
            "analysis": result.output.model_dump(),
            "tokens_used": usage.total_tokens,
        }
        return {"analyst_reports": [report]}  # list wrapping for operator.add reducer
    except UsageLimitExceeded as e:
        logger.error("fundamental_budget_exceeded", ticker=state["ticker"], error=str(e))
        report = {"analyst": "fundamental", "error": str(e)}
        return {"analyst_reports": [report]}
```

### Anti-Patterns to Avoid

- **Manager as concatenator.** The manager must NOT simply merge bull points from all analysts. It must identify conflicts, explain resolution rationale, and produce a coherent thesis. The system prompt must explicitly require conflict identification. [VERIFIED: MULTI-04 requirement + CONTEXT.md]
- **LLM computing financial metrics.** Technical analyst must NOT describe price patterns from its own knowledge. All momentum/volatility claims must cite `get_price_data` tool output. System prompt: "NEVER describe price patterns, support/resistance levels, or chart formations unless derived from tool-provided data." [VERIFIED: CLAUDE.md agent development rules]
- **Shared tool registration.** Do NOT register all 6 tools on every specialist. Each specialist gets only its domain tools. This enforces domain boundaries and prevents the fundamental analyst from reasoning about sentiment data. [VERIFIED: CONTEXT.md key constraints]
- **Mutating state in nodes.** Always return NEW dicts from nodes. Never modify the `state` parameter. [VERIFIED: codebase convention in nodes.py + CLAUDE.md immutability rules]
- **Skipping error propagation.** If an analyst node fails (budget exceeded), the error should be included in `analyst_reports` so the manager knows which domain is missing and can note it in the thesis. Do NOT silently drop failed analysts. [ASSUMED]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parallel execution of analysts | Custom asyncio.gather with manual state merging | LangGraph fan-out edges + `operator.add` reducer | LangGraph handles state merging, checkpointing, error isolation [VERIFIED: Context7 LangGraph docs] |
| Agent tool registration | Manual function dispatch | PydanticAI `@agent.tool` decorator with `RunContext[Deps]` | Handles DI, retries, output validation, TestModel support [VERIFIED: Context7 PydanticAI docs] |
| Token budget enforcement | Custom token counting | PydanticAI `UsageLimits` + `PipelineBudgetTracker` | Already built in Phase 1; proven pattern [VERIFIED: codebase base.py] |
| Output validation | Manual dict checking | Pydantic `BaseModel` with `Field` constraints | Schema-level enforcement (min_length, ge/le) catches issues at validation time [VERIFIED: codebase schemas/agents.py] |
| Agent testing without LLM | Manual mocking | PydanticAI `TestModel` with `agent.override()` | Schema-aware test model that generates valid outputs [VERIFIED: Context7 PydanticAI docs + codebase tests] |

**Key insight:** The entire specialist-agent-per-domain pattern is achievable by cloning the Phase 3 `research_agent` pattern 3 times with different tool subsets and output schemas. The manager follows the `signal_agent` pattern (no tools, receives data via prompt). No new libraries needed.

## Common Pitfalls

### Pitfall 1: State Key Collision in Fan-Out
**What goes wrong:** Multiple parallel nodes each return a key like `thesis` or `analysis`, and the last-to-finish overwrites the others.
**Why it happens:** LangGraph's default behavior for non-annotated keys is to overwrite.
**How to avoid:** Use `Annotated[list[dict], operator.add]` for the `analyst_reports` key. Each node returns `{"analyst_reports": [report_dict]}` (a single-element list). The reducer concatenates all lists.
**Warning signs:** Only one analyst report appears in the manager's input.

### Pitfall 2: Manager Producing Low-Quality Synthesis
**What goes wrong:** The manager simply concatenates analyst findings without identifying conflicts or applying judgment. Output reads like "Fundamental says X. Sentiment says Y. Technical says Z."
**Why it happens:** System prompt does not explicitly require conflict identification and resolution.
**How to avoid:** System prompt must include explicit instructions: (1) List all agreement points with cross-analyst citations. (2) List all conflict points with which analysts disagree. (3) For each conflict, state which signal the manager weights more and why. (4) Final confidence must account for agreement/conflict ratio.
**Warning signs:** ThesisOutput bull/bear points all cite the same analyst, or no points mention disagreement.

### Pitfall 3: Technical Analyst Using LLM Knowledge Instead of Tools
**What goes wrong:** The Technical/Quant analyst describes "strong support at $150" or "head and shoulders pattern" without any tool call backing.
**Why it happens:** LLMs have training data about common stocks and can hallucinate plausible-sounding technical analysis.
**How to avoid:** (1) System prompt forbids price pattern descriptions not backed by tool data. (2) Only register `get_price_data` as a tool (no filing/sentiment tools to distract). (3) `TechnicalAnalysis` schema requires `source_tool` citation on every metric claim. (4) Unit test verifies the agent has exactly 1 tool registered.
**Warning signs:** TechnicalAnalysis output contains claims like "support level" or "resistance" without `source_tool = "get_price_data"`.

### Pitfall 4: Pipeline Budget Exhaustion from Parallel Agents
**What goes wrong:** Running 3 analysts + 1 manager + 1 signal agent on a single pipeline exceeds the 500K total token budget in `PipelineBudgetTracker`.
**Why it happens:** Each analyst uses ANALYSIS tier (58K limit) and manager uses REASONING tier (116K limit). Total theoretical max: 3*58K + 116K + 58K = 348K. Actual usage may vary, but the existing 500K pipeline cap has headroom. However, if tools return large filing texts, input tokens can spike.
**How to avoid:** (1) Verify per-agent budgets still fit within the 500K pipeline cap. (2) Tool wrappers continue to return `summary_text` only (not raw data) per T-03-04 pattern. (3) Consider reducing fundamental analyst filing count from 3 to 2 for the multi-agent pipeline to conserve budget.
**Warning signs:** `BudgetExceededError` during pipeline runs, especially on the manager node after analysts have consumed most of the budget.

### Pitfall 5: Broken Backward Compatibility
**What goes wrong:** Phase 3's `build_research_pipeline` (research -> signal) stops working because research.py was modified.
**Why it happens:** Refactoring the generalist agent or changing shared schemas.
**How to avoid:** (1) Keep `research.py` and `build_research_pipeline` unchanged. (2) Create NEW files for specialists. (3) New pipeline is `build_multi_agent_pipeline` alongside the existing one. (4) Existing tests must still pass.
**Warning signs:** `test_research_pipeline.py` tests fail after Phase 4 changes.

## Code Examples

### Specialist Output Schema: FundamentalAnalysis

```python
# Source: Extension of codebase pattern from schemas/agents.py
class ValuationMetric(BaseModel):
    """A single computed valuation metric with tool citation."""
    metric_name: str = Field(description="e.g., 'P/E Ratio', 'EV/EBITDA'")
    value: str = Field(description="The metric value as reported by the tool")
    source_tool: str = Field(min_length=1, description="Tool that produced this metric")

class FilingCitation(BaseModel):
    """Reference to a specific SEC filing section."""
    form_type: str = Field(description="e.g., '10-K', '10-Q'")
    section: str = Field(description="Section name from the filing")
    key_quote: str = Field(description="Relevant excerpt from the filing")
    filing_date: str = Field(description="Date the filing was made")

class FundamentalAnalysis(BaseModel):
    """Output from the Fundamental Analyst agent (MULTI-01)."""
    ticker: str
    valuation_assessment: str = Field(description="Overall valuation conclusion")
    valuation_metrics: list[ValuationMetric] = Field(
        min_length=2, description="Computed valuation metrics with tool citations"
    )
    filing_citations: list[FilingCitation] = Field(
        min_length=1, description="Specific SEC filing sections cited"
    )
    bull_factors: list[str] = Field(min_length=1, description="Positive fundamental factors")
    bear_factors: list[str] = Field(min_length=1, description="Negative fundamental factors")
    confidence: int = Field(ge=0, le=100, description="Confidence in fundamental assessment")
```

### Specialist Output Schema: SentimentAnalysis

```python
class SentimentComponent(BaseModel):
    """A single component of the composite sentiment score."""
    component: str = Field(description="e.g., 'news_sentiment', 'insider_activity'")
    score: float = Field(ge=-1.0, le=1.0, description="Score from -1 (bearish) to +1 (bullish)")
    summary: str = Field(description="Brief explanation of the score")
    source_tool: str = Field(min_length=1, description="Tool that produced this data")

class SentimentAnalysis(BaseModel):
    """Output from the Sentiment Analyst agent (MULTI-02)."""
    ticker: str
    composite_score: float = Field(ge=-1.0, le=1.0, description="Weighted composite sentiment")
    components: list[SentimentComponent] = Field(
        min_length=1, description="Component breakdown of sentiment score"
    )
    key_signals: list[str] = Field(min_length=1, description="Notable sentiment signals")
    confidence: int = Field(ge=0, le=100, description="Confidence in sentiment assessment")
```

### Specialist Output Schema: TechnicalAnalysis

```python
class TechnicalIndicator(BaseModel):
    """A single computed technical indicator with tool citation."""
    indicator: str = Field(description="e.g., 'RSI', '50-day SMA', 'Volatility'")
    value: str = Field(description="The indicator value")
    interpretation: str = Field(description="What this means (bullish/bearish/neutral)")
    source_tool: str = Field(min_length=1, description="Must be 'get_price_data'")

class TechnicalAnalysis(BaseModel):
    """Output from the Technical/Quant Analyst agent (MULTI-03)."""
    ticker: str
    momentum_assessment: str = Field(description="Overall momentum conclusion")
    volatility_assessment: str = Field(description="Overall volatility conclusion")
    indicators: list[TechnicalIndicator] = Field(
        min_length=2, description="Computed technical indicators with tool citations"
    )
    bull_factors: list[str] = Field(min_length=1, description="Positive technical factors")
    bear_factors: list[str] = Field(min_length=1, description="Negative technical factors")
    confidence: int = Field(ge=0, le=100, description="Confidence in technical assessment")
```

### AnalystReport Wrapper for State

```python
class AnalystReport(BaseModel):
    """Wrapper for an analyst's output in the pipeline state."""
    analyst: Literal["fundamental", "sentiment", "technical"]
    analysis: dict  # model_dump() of the specialist output
    tokens_used: int = Field(ge=0)
    error: str | None = None  # Set if the analyst failed
```

### MultiAgentPipelineState

```python
import operator
from typing import Annotated, Required
from typing_extensions import TypedDict

class MultiAgentPipelineState(TypedDict, total=False):
    ticker: Required[str]
    as_of_date: Required[str]
    analyst_reports: Annotated[list[dict], operator.add]
    thesis: dict | None
    signal: dict | None
    error: str | None
```

### Manager Node Receiving Analyst Reports

```python
async def manager_node(state: MultiAgentPipelineState) -> dict:
    """Research Manager synthesizes analyst reports into unified thesis."""
    reports = state.get("analyst_reports", [])
    if not reports:
        return {"error": "No analyst reports available for synthesis"}

    # Format reports for manager prompt
    reports_text = _format_analyst_reports(reports)
    prompt = f"Synthesize these analyst reports for {state['ticker']}:\n\n{reports_text}"

    try:
        limits = get_manager_limits()
        result = await manager_agent.run(prompt, usage_limits=limits)
        return {"thesis": result.output.model_dump()}
    except UsageLimitExceeded as e:
        return {"error": f"Manager budget exceeded: {e}"}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single generalist agent (Phase 3) | Domain-specialist agents with manager synthesis | Phase 4 (this phase) | Better domain coverage, parallel execution, explicit conflict resolution |
| Sequential pipeline (research -> signal) | Fan-out/fan-in parallel pipeline | Phase 4 (this phase) | ~3x faster wall-clock time for analysis (analysts run concurrently) |
| LangGraph `Send` for dynamic fan-out | Static `add_edge` fan-out from START | LangGraph 1.0+ | Static edges are simpler, compile-time verifiable, sufficient for fixed analyst count [VERIFIED: Context7 docs] |

**Deprecated/outdated:**
- LangGraph `Send` primitive: More powerful (dynamic fan-out) but unnecessary here since we have exactly 3 fixed analysts. Static edges are simpler and compile-time verifiable. Reserve `Send` for Phase 7+ if dynamic analyst count is needed. [VERIFIED: Context7 docs]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Error from one analyst should be included in `analyst_reports` (not block pipeline) so the manager knows which domain is missing | Anti-Patterns | If wrong, a single analyst failure kills the entire pipeline; recovery strategy needs rethinking |
| A2 | `get_macro_context` should be available to Fundamental analyst (not just shared context) | Tool Domain Mapping | If wrong, fundamental analyst lacks macro valuation context; could be cross-cutting instead |
| A3 | Manager agent should use REASONING tier (Opus) for complex multi-source synthesis | Pattern 3 | If wrong and Sonnet is sufficient, using Opus wastes ~2x the cost; budget may need adjustment |
| A4 | Existing 500K pipeline budget has sufficient headroom for 5 agents (3 analysts + manager + signal) | Pitfall 4 | If wrong, pipeline runs will fail with BudgetExceededError; need to either increase cap or reduce per-agent limits |
| A5 | Fundamental analyst should get `get_macro_context` in addition to filing+financial tools (3 tools total) | Tool mapping | If macro should be separate cross-cutting context injected into state instead, architecture changes |

## Open Questions

1. **Manager model tier: Opus vs Sonnet?**
   - What we know: CONTEXT.md suggests "manager potentially on Opus for complex synthesis." Opus (REASONING tier) has 116K token budget vs Sonnet's 58K. Opus is ~5x more expensive per token.
   - What's unclear: Whether the synthesis task is complex enough to justify Opus, or if Sonnet with a good system prompt is sufficient.
   - Recommendation: Start with Opus (REASONING tier) per CONTEXT.md guidance. Can downgrade to Sonnet later if cost is prohibitive and quality is acceptable.

2. **Should the Phase 3 research pipeline be deprecated or kept?**
   - What we know: Phase 3's `build_research_pipeline` works and has tests. Phase 4 adds `build_multi_agent_pipeline` alongside it.
   - What's unclear: Whether the old single-agent pipeline should remain accessible or be marked as deprecated.
   - Recommendation: Keep both pipelines. The single-agent pipeline is simpler, cheaper, and useful for quick analyses. Add the multi-agent pipeline as a separate function. Let the caller choose.

3. **Should failed analysts block the manager or proceed with partial data?**
   - What we know: The manager could work with 2 out of 3 analyst reports, noting the missing domain.
   - What's unclear: Whether partial synthesis produces acceptable quality or misleading results.
   - Recommendation: Proceed with partial data but inject the failure into the manager prompt (e.g., "Note: Technical analysis unavailable due to budget exhaustion. Thesis is based on fundamental and sentiment data only."). This is more resilient than blocking the entire pipeline.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0+ with pytest-asyncio |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `ANTHROPIC_API_KEY=test-key uv run pytest tests/unit/ -x -q` |
| Full suite command | `ANTHROPIC_API_KEY=test-key uv run pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MULTI-01 | Fundamental agent has filing+financial+macro tools, produces FundamentalAnalysis | unit | `pytest tests/unit/test_fundamental_agent.py -x` | Wave 0 |
| MULTI-01 | FundamentalAnalysis schema validates min_length on valuation_metrics, filing_citations | unit | `pytest tests/unit/test_schemas.py::TestFundamentalAnalysis -x` | Wave 0 |
| MULTI-02 | Sentiment agent has news+insider tools, produces SentimentAnalysis with composite score | unit | `pytest tests/unit/test_sentiment_agent.py -x` | Wave 0 |
| MULTI-02 | SentimentAnalysis schema validates score ranges and component breakdown | unit | `pytest tests/unit/test_schemas.py::TestSentimentAnalysis -x` | Wave 0 |
| MULTI-03 | Technical agent has price tool ONLY, produces TechnicalAnalysis | unit | `pytest tests/unit/test_technical_agent.py -x` | Wave 0 |
| MULTI-03 | TechnicalAnalysis schema validates indicator citations | unit | `pytest tests/unit/test_schemas.py::TestTechnicalAnalysis -x` | Wave 0 |
| MULTI-04 | Manager agent has NO tools, uses REASONING tier | unit | `pytest tests/unit/test_manager_agent.py -x` | Wave 0 |
| MULTI-04 | Manager produces ThesisOutput from analyst reports | unit | `pytest tests/unit/test_manager_agent.py::TestManagerOutput -x` | Wave 0 |
| MULTI-01/02/03 | All 3 analysts run in parallel via LangGraph fan-out | integration | `pytest tests/integration/test_multi_agent_pipeline.py -x` | Wave 0 |
| MULTI-04 | Pipeline: analysts -> manager -> signal produces valid SignalOutput | integration | `pytest tests/integration/test_multi_agent_pipeline.py -x` | Wave 0 |
| ALL | Phase 3 pipeline still works (no regression) | unit | `pytest tests/unit/test_research_node.py -x` | Exists |
| ALL | Phase 3 integration tests still pass | integration | `pytest tests/integration/test_research_pipeline.py -x` | Exists |

### Sampling Rate
- **Per task commit:** `ANTHROPIC_API_KEY=test-key uv run pytest tests/unit/ -x -q`
- **Per wave merge:** `ANTHROPIC_API_KEY=test-key uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_fundamental_agent.py` -- covers MULTI-01 (agent wiring, tool registration, system prompt)
- [ ] `tests/unit/test_sentiment_agent.py` -- covers MULTI-02 (agent wiring, tool registration)
- [ ] `tests/unit/test_technical_agent.py` -- covers MULTI-03 (agent wiring, EXACTLY 1 tool)
- [ ] `tests/unit/test_manager_agent.py` -- covers MULTI-04 (no tools, REASONING tier, output type)
- [ ] `tests/unit/test_schemas.py` extensions -- covers FundamentalAnalysis, SentimentAnalysis, TechnicalAnalysis, AnalystReport schema validation
- [ ] `tests/integration/test_multi_agent_pipeline.py` -- covers fan-out/fan-in, TestModel-based flow, pipeline compilation

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A -- internal pipeline, no user auth |
| V3 Session Management | No | N/A -- stateless agent calls |
| V4 Access Control | No | N/A -- all agents have same access level |
| V5 Input Validation | Yes | Pydantic `BaseModel` with `Field` constraints for all agent outputs; `ResearchDeps` frozen dataclass for agent inputs |
| V6 Cryptography | No | N/A -- no encryption in this phase |

### Known Threat Patterns for Multi-Agent Pipeline

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| LLM hallucinating financial figures | Tampering | `source_tool` required on every metric claim; system prompt forbids unsourced figures (T-03-01 pattern) [VERIFIED: codebase] |
| Temporal data leak (future knowledge) | Information Disclosure | `as_of_date` enforced via `ResearchDeps` DI + `@enforce_as_of_date` on every tool (T-03-02 pattern) [VERIFIED: codebase] |
| Token budget exhaustion (pipeline DoS) | DoS | `UsageLimits` per agent + `PipelineBudgetTracker` per pipeline (T-03-04 pattern) [VERIFIED: codebase] |
| Ticker/date injection via LLM | Tampering | Ticker and as_of_date come from `ResearchDeps` (RunContext), not LLM-controlled parameters (T-03-03 pattern) [VERIFIED: codebase] |
| Manager ignoring analyst conflicts | Elevation of Privilege | System prompt explicitly requires conflict identification; test asserts manager output references multiple analysts |

## Tool Domain Mapping

This is the canonical reference for which data tools each specialist agent receives.

| Tool Function | Fundamental | Sentiment | Technical | Rationale |
|--------------|:-----------:|:---------:|:---------:|-----------|
| `get_filing_sections` | Y | -- | -- | SEC filings are fundamental analysis [VERIFIED: MULTI-01] |
| `get_financial_summary` | Y | -- | -- | XBRL financials are fundamental analysis [VERIFIED: MULTI-01] |
| `get_macro_context` | Y | -- | -- | Macro context impacts valuation [ASSUMED: A5] |
| `get_news_sentiment` | -- | Y | -- | News sentiment is sentiment domain [VERIFIED: MULTI-02] |
| `get_insider_clusters` | -- | Y | -- | Insider activity is sentiment signal [VERIFIED: MULTI-02] |
| `get_price_history` | -- | -- | Y | Price data is technical analysis [VERIFIED: MULTI-03] |

## Sources

### Primary (HIGH confidence)
- Context7 `/websites/langchain_oss_python_langgraph` -- fan-out/fan-in pattern, `Annotated[list, operator.add]` reducer, `StateGraph` parallel edges
- Context7 `/pydantic/pydantic-ai` -- `Agent[Deps, Output]` pattern, `@agent.tool` with `RunContext`, `TestModel` for testing, `agent.override()`
- Codebase `src/ai_hedge_fund/agents/research.py` -- Phase 3 agent pattern (ResearchDeps, tool wrappers, system prompt)
- Codebase `src/ai_hedge_fund/agents/signal.py` -- No-tools agent pattern (manager template)
- Codebase `src/ai_hedge_fund/graph/pipeline.py` -- Pipeline builder pattern
- Codebase `src/ai_hedge_fund/graph/nodes.py` -- Node function pattern (immutable returns, error handling)

### Secondary (MEDIUM confidence)
- PyPI registry -- langgraph 1.1.6 installed (latest 1.1.8), pydantic-ai 1.80.0 installed (latest 1.84.1) [VERIFIED: pip list + pip index versions]

### Tertiary (LOW confidence)
- None -- all claims verified against codebase or Context7 documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and patterns established in Phases 1-3
- Architecture: HIGH -- fan-out/fan-in pattern verified in Context7 LangGraph docs; agent pattern verified in codebase
- Pitfalls: HIGH -- derived from codebase patterns and LangGraph documentation; state reducer behavior verified
- Schemas: MEDIUM -- specific field names and constraints are recommendations, not verified against external sources

**Research date:** 2026-04-20
**Valid until:** 2026-05-20 (stable stack, no fast-moving dependencies)
