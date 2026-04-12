# Architecture Patterns

**Domain:** Multi-agent LLM financial research and trading system
**Researched:** 2026-04-11

## Recommended Architecture

### High-Level: Directed Graph Pipeline

```
                         [Trigger: Daily batch or on-demand]
                                      |
                                      v
                        +---------------------------+
                        |   LangGraph Orchestrator   |
                        |  (state, checkpoints, flow) |
                        +---------------------------+
                                      |
                    +-----------------+-----------------+
                    |                 |                 |
                    v                 v                 v
            +-------------+  +-------------+  +-------------+
            | Hypothesis  |  | Hypothesis  |  | Hypothesis  |
            | Agent (A)   |  | Agent (B)   |  | Agent (C)   |
            +-------------+  +-------------+  +-------------+
                    |                 |                 |
                    +-----------------+-----------------+
                                      |
                                      v
                        +---------------------------+
                        |    Evidence Gatherer       |
                        | (SEC, earnings, market)    |
                        +---------------------------+
                                      |
                                      v
                        +---------------------------+
                        |    Critique Agent          |
                        | (adversarial evaluation)   |
                        +---------------------------+
                                      |
                                      v
                        +---------------------------+
                        |    Signal Generator        |
                        | (typed quantitative output)|
                        +---------------------------+
                                      |
                                      v
                        +---------------------------+
                        |    Risk Manager            |
                        | (position limits, sizing)  |
                        +---------------------------+
                                      |
                            [Optional: Human Review]
                                      |
                                      v
                        +---------------------------+
                        |    Output: Signals DB      |
                        | (PostgreSQL, append-only)  |
                        +---------------------------+
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| LangGraph Orchestrator | Graph execution, state management, checkpointing, parallel dispatch | All agents (invokes them as graph nodes) |
| Hypothesis Agent | Generate investment thesis from data analysis | Orchestrator (receives ticker/sector, returns hypothesis) |
| Evidence Gatherer | Collect supporting/contradicting data from multiple sources | Orchestrator (receives hypothesis, returns evidence bundle) |
| Critique Agent | Adversarial evaluation of thesis against evidence | Orchestrator (receives hypothesis + evidence, returns critique with confidence) |
| Signal Generator | Convert surviving thesis into typed quantitative signal | Orchestrator (receives hypothesis + critique, returns signal schema) |
| Risk Manager | Assess signal against portfolio context, set position size | Orchestrator (receives signal + portfolio state, returns risk-adjusted signal) |
| Tool Layer | External API calls (SEC EDGAR, yfinance, news) | Individual agents via LangGraph tool nodes |
| State Store (PostgreSQL) | Persist checkpoints, agent states, signals | Orchestrator (read/write), Backtest system (read) |
| Observability (Langfuse) | Trace logging, cost tracking, debugging | All agents (automatic via LangGraph integration) |

### Data Flow

1. **Input:** Ticker(s) or sector to analyze (from CLI or scheduler)
2. **Hypothesis phase:** Multiple hypothesis agents run in PARALLEL, each generating an independent thesis
3. **Evidence phase:** Evidence gatherer runs SEQUENTIALLY per hypothesis (shared tool calls, rate-limited APIs)
4. **Critique phase:** Critique agent evaluates each hypothesis SEQUENTIALLY against gathered evidence
5. **Signal phase:** Surviving hypotheses converted to typed signals
6. **Risk phase:** Risk manager evaluates signals against current portfolio context
7. **Output:** Risk-adjusted signals persisted to PostgreSQL (append-only)

### State Schema (LangGraph)

```python
from typing import TypedDict
from pydantic import BaseModel

class Hypothesis(BaseModel):
    ticker: str
    direction: str  # "long" | "short"
    thesis: str
    confidence: float  # 0.0 - 1.0
    timeframe_days: int
    data_sources: list[str]

class Evidence(BaseModel):
    hypothesis_id: str
    supporting: list[str]
    contradicting: list[str]
    data_quality: float  # 0.0 - 1.0

class Critique(BaseModel):
    hypothesis_id: str
    survives: bool
    revised_confidence: float
    weaknesses: list[str]
    strengths: list[str]

class Signal(BaseModel):
    ticker: str
    direction: str
    confidence: float
    position_size_pct: float
    stop_loss_pct: float
    timeframe_days: int
    reasoning_summary: str

class PipelineState(TypedDict):
    tickers: list[str]
    hypotheses: list[Hypothesis]
    evidence: list[Evidence]
    critiques: list[Critique]
    signals: list[Signal]
    token_budget_remaining: int
    iteration: int
```

## Patterns to Follow

### Pattern 1: Parallel Fan-Out / Fan-In

**What:** Multiple analyst agents run concurrently on the same input, then results are collected.
**When:** Hypothesis generation (multiple independent theses), evidence gathering from independent sources.
**Example:**
```python
# LangGraph parallel node execution
from langgraph.graph import StateGraph

graph = StateGraph(PipelineState)

# Fan-out: parallel hypothesis generation
graph.add_node("hypothesis_a", generate_value_thesis)
graph.add_node("hypothesis_b", generate_momentum_thesis)
graph.add_node("hypothesis_c", generate_sentiment_thesis)

# Fan-in: collect all hypotheses
graph.add_node("collect_hypotheses", merge_hypotheses)

# Parallel edges from start to each hypothesis agent
graph.add_edge("start", "hypothesis_a")
graph.add_edge("start", "hypothesis_b")
graph.add_edge("start", "hypothesis_c")
graph.add_edge("hypothesis_a", "collect_hypotheses")
graph.add_edge("hypothesis_b", "collect_hypotheses")
graph.add_edge("hypothesis_c", "collect_hypotheses")
```

### Pattern 2: Budget-Gated Agent Execution

**What:** Each agent checks remaining token budget before executing. Pipeline halts gracefully if budget exhausted.
**When:** Every agent invocation. Non-negotiable for cost control.
**Example:**
```python
def budget_gate(state: PipelineState) -> str:
    """Conditional edge: continue or halt based on budget."""
    if state["token_budget_remaining"] <= 0:
        return "budget_exceeded"
    return "continue"

graph.add_conditional_edges(
    "evidence_gatherer",
    budget_gate,
    {"continue": "critique_agent", "budget_exceeded": "emergency_signal"}
)
```

### Pattern 3: Typed Agent Boundaries (PydanticAI)

**What:** Each agent declares its input/output schema as Pydantic models. LLM output is validated against schema at runtime.
**When:** Every agent definition. Prevents schema drift and hallucinated output formats.
**Example:**
```python
from pydantic_ai import Agent

hypothesis_agent = Agent[Hypothesis](
    model="anthropic:claude-sonnet-4-20250514",
    instructions="Generate an investment thesis...",
    result_type=Hypothesis,  # Output validated against this schema
)
```

### Pattern 4: Model Routing by Task Complexity

**What:** Route different tasks to different Claude models based on complexity.
**When:** After measuring baseline costs. Apply to all agents.
**Example:**
```python
MODEL_ROUTING = {
    "data_extraction": "anthropic:claude-haiku",      # Simple: extract numbers from filings
    "evidence_synthesis": "anthropic:claude-sonnet-4-20250514",  # Medium: synthesize multiple sources
    "adversarial_critique": "anthropic:claude-opus-4-20250514",    # Complex: deep adversarial reasoning
    "signal_generation": "anthropic:claude-sonnet-4-20250514",  # Medium: structured output from analysis
    "risk_assessment": "anthropic:claude-sonnet-4-20250514",    # Medium: rule-based with context
}
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Accumulated Context in Agent Debates

**What:** Passing full conversation history between agents in a debate loop.
**Why bad:** Token costs grow quadratically with debate rounds. A 4-agent x 5-round debate is 20+ LLM calls, each with growing context. AutoGen's GroupChat exhibits this problem.
**Instead:** Each agent receives only the structured output of the previous agent (Hypothesis, Evidence, Critique models), not raw conversation. Summarize before passing.

### Anti-Pattern 2: Shared Mutable State Between Agents

**What:** Agents modifying the same state object concurrently.
**Why bad:** Race conditions, non-deterministic results, impossible to debug.
**Instead:** LangGraph's state is immutable per node. Each node returns a new state dict. Use reducers for merging parallel results.

### Anti-Pattern 3: Unbounded Agent Loops

**What:** Agent retry/reasoning loops without iteration caps or token budgets.
**Why bad:** A confused agent can loop indefinitely, burning tokens. One runaway analysis could cost hundreds of dollars.
**Instead:** Max iterations per agent (3-5), token budget per pipeline run, emergency signal generation if budget exceeded.

### Anti-Pattern 4: Fine-Grained Agent Decomposition Too Early

**What:** Creating 15+ specialized agents from the start (separate agents for P/E analysis, revenue growth, margin trends, etc.).
**Why bad:** Coordination overhead exceeds benefit. Each agent adds latency, token cost, and failure surface.
**Instead:** Start with 5 agents (hypothesis, evidence, critique, signal, risk). Decompose only when a single agent is measurably struggling with task complexity.

### Anti-Pattern 5: Persistent Agent Memory Across Sessions

**What:** Agents remembering past analyses and building on accumulated "knowledge."
**Why bad:** Stale context causes hallucination drift. Agent confidently references a market condition from 3 months ago.
**Instead:** Each analysis pipeline is stateless. Persistent data lives in PostgreSQL (prices, filings, historical signals). Agents receive fresh context each run.

## Scalability Considerations

| Concern | 10 tickers/day | 100 tickers/day | 500 tickers/day |
|---------|---------------|-----------------|-----------------|
| Token cost | ~$3-8/day (optimized) | ~$30-80/day | ~$150-400/day |
| Latency | ~2-5 min total | ~20-50 min (parallelized) | ~2-4 hours (parallelized) |
| PostgreSQL load | Negligible | Moderate (checkpoint writes) | High (batch checkpoint writes) |
| API rate limits | Not an issue | Monitor SEC EDGAR limits | Need rate limiting layer for all APIs |
| LLM rate limits | Not an issue | Monitor Anthropic RPM limits | May need multiple API keys or tier upgrade |
| Observability data | ~100 traces/day | ~1,000 traces/day | ~5,000 traces/day (Langfuse self-hosted handles this) |

## Sources

- [TradingAgents 5-phase architecture](https://github.com/TauricResearch/TradingAgents)
- [virattt/ai-hedge-fund 3-stage pipeline (parallel analysts, risk, portfolio)](https://github.com/virattt/ai-hedge-fund)
- [LangGraph parallel node execution](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Hierarchical architecture cost-accuracy tradeoffs for financial documents](https://arxiv.org/html/2603.22651)
- [Multi-agent cost management patterns](https://apxml.com/courses/multi-agent-llm-systems-design-implementation/chapter-6-system-evaluation-debugging-tuning/managing-llm-agent-costs)
