# Phase 1: Foundation - Research

**Researched:** 2026-04-11
**Domain:** LangGraph orchestration, PydanticAI typed agents, Claude model routing, Langfuse observability, token budget enforcement
**Confidence:** HIGH

## Summary

Phase 1 builds the instrumented, budget-aware infrastructure that every subsequent phase depends on. The core challenge is integrating four distinct systems -- LangGraph (orchestration + checkpointing), PydanticAI (typed agent logic), langchain-anthropic (Claude model routing), and Langfuse (observability) -- into a cohesive pipeline where each agent run is traced, cost-tracked, and budget-capped.

All four core libraries have undergone major version bumps since the project was initially specified. LangGraph is now at 1.1.6 (was >=0.3), PydanticAI at 1.80.0 (was >=1.0), langchain-anthropic at 1.4.0 (was >=0.3), and Langfuse at 4.2.0 (was >=2.0). The Claude model lineup has also changed: current models are claude-opus-4-6, claude-sonnet-4-6, and claude-haiku-4-5-20251001. The project's CLAUDE.md references need updating to these current versions and model names.

The integration pattern is: LangGraph defines the graph (nodes, edges, state, checkpointing), each node wraps a PydanticAI agent call (typed I/O, usage limits), models are initialized via langchain-anthropic's ChatAnthropic for LangGraph nodes or directly via PydanticAI's model string syntax for standalone agents, and Langfuse's CallbackHandler is passed to every graph invocation for end-to-end tracing.

**Primary recommendation:** Use LangGraph for graph orchestration + PostgreSQL checkpointing, PydanticAI agents wrapped as LangGraph node functions for type-safe agent logic, per-agent UsageLimits for token budget enforcement, and Langfuse CallbackHandler for observability. Pin to current stable versions.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None explicitly locked -- all implementation choices are at Claude's discretion (infrastructure phase).

### Claude's Discretion
All implementation choices are at Claude's discretion -- pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints from PROJECT.md and CLAUDE.md:
- Python 3.11+, uv for package management
- LangGraph for orchestration with PostgreSQL checkpointing
- PydanticAI for typed agent definitions
- langchain-anthropic for Claude model integration
- Langfuse for observability (open-source, self-hosted)
- Dual-model routing: Haiku for extraction, Sonnet for analysis, Opus for complex reasoning
- Token budget enforcement per agent and per pipeline run
- Immutable data patterns, type hints required, functions under 50 lines, files under 800 lines
- ruff for formatting and linting

### Deferred Ideas (OUT OF SCOPE)
None -- infrastructure phase, no discussion occurred.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FOUND-01 | LangGraph orchestration graph with checkpointing and state persistence to PostgreSQL | LangGraph 1.1.6 StateGraph + langgraph-checkpoint-postgres 3.0.5 PostgresSaver; setup pattern verified via official docs |
| FOUND-02 | PydanticAI agent base with typed schemas for hypotheses, evidence, signals, and theses | PydanticAI 1.80.0 Agent with `output_type` parameter accepting Pydantic BaseModel subclasses; validated output or descriptive ValidationError |
| FOUND-03 | Claude model integration with dual-model routing (Haiku/Sonnet/Opus by task type) | langchain-anthropic 1.4.0 ChatAnthropic + PydanticAI model strings; current model IDs: claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4-6 |
| FOUND-04 | Langfuse observability integration for agent traces, cost tracking, and latency monitoring | Langfuse Python SDK 4.2.0 with CallbackHandler for LangGraph + @observe() decorator for custom spans; traces model, tokens, latency per step |
| FOUND-05 | Token budget enforcement per agent and per pipeline run with configurable caps | PydanticAI UsageLimits with input_tokens_limit, output_tokens_limit, total_tokens_limit; raises UsageLimitExceeded exception when exceeded |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

**Mandatory directives extracted from CLAUDE.md and global rules:**

- **Package management:** uv (not pip, not poetry)
- **Linting/formatting:** ruff (line-length=100, target-version=py312): `ruff format . && ruff check . --fix`
- **Testing:** pytest, TDD workflow (RED-GREEN-IMPROVE), 80%+ coverage target
- **Immutability:** Return new objects, never mutate in place
- **Type hints:** Required on all function params and return values; use `str | None` union syntax
- **File size limits:** Functions under 50 lines, files under 800 lines
- **Secrets:** All API keys in `.env` files, never committed
- **Agent development:** LLMs NEVER compute financial ratios directly -- tool-first for quantitative work
- **Token budgets from day one:** Every agent has a per-run token cap, every pipeline has a total cost cap
- **Timestamps in UTC:** All timestamps
- **Financial precision:** Preserve source precision, don't round prematurely
- **Append-only:** Financial time-series data never overwritten
- **Structured logging:** structlog for structured JSON logging
- **Error handling:** Handle errors explicitly, provide clear messages, never silently swallow
- **Input validation:** Validate at system boundaries with schema-based validation

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | 1.1.6 | Graph-based orchestration, state machines, conditional routing | Production standard for multi-agent systems; used by S&P Global/Kensho; native PostgreSQL checkpointing, human-in-the-loop, parallel nodes [VERIFIED: PyPI registry] |
| pydantic-ai | 1.80.0 | Type-safe agent definitions, structured output validation, usage limits | Stable 1.x API since Sep 2025; generic Agent[DepsType, OutputType]; built-in UsageLimits for budget enforcement [VERIFIED: PyPI registry] |
| langchain-anthropic | 1.4.0 | ChatAnthropic model wrapper for LangGraph nodes | Official Anthropic adapter for LangChain/LangGraph; supports claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5 [VERIFIED: PyPI registry] |
| langchain-core | 1.2.28 | Base abstractions (messages, tool calls) for LangGraph | Required dependency for LangGraph; provides ChatMessage types, RunnableConfig [VERIFIED: PyPI registry] |
| langfuse | 4.2.0 | LLM tracing, cost tracking, latency monitoring | Open-source, self-hostable; v4 observation-centric model; CallbackHandler for LangGraph + @observe() for custom spans [VERIFIED: PyPI registry] |
| anthropic | 0.94.0 | Direct Claude API access for advanced features | Prompt caching (90% cost reduction), extended thinking; use alongside langchain-anthropic for features not exposed through LangGraph [VERIFIED: PyPI registry] |
| pydantic | 2.12.5 | Data validation, schema definitions | Foundation for PydanticAI output schemas; Rust-core validation [VERIFIED: PyPI registry] |
| pydantic-settings | 2.13.1 | Environment-aware configuration | Loads from .env with type validation; used in prior project (archive reference pattern) [VERIFIED: PyPI registry] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| langgraph-checkpoint-postgres | 3.0.5 | PostgreSQL-backed state persistence | Production: persist graph state across restarts, resume from checkpoints [VERIFIED: PyPI registry] |
| psycopg[binary] | 3.3.3 | PostgreSQL driver (sync) | Required by PostgresSaver and SQLAlchemy for sync operations [VERIFIED: PyPI registry] |
| psycopg-pool | latest | Connection pooling for PostgreSQL | Required for langgraph-checkpoint-postgres connection management [ASSUMED] |
| sqlalchemy | 2.0.49 | ORM for data layer | Append-only table patterns, session management; established in prior project [VERIFIED: PyPI registry] |
| alembic | 1.18.4 | Database migrations | Schema versioning for PostgreSQL tables [VERIFIED: PyPI registry] |
| structlog | 25.5.0 | Structured JSON logging | Agent-level log binding; structured output for debugging autonomous systems [VERIFIED: PyPI registry] |
| httpx | 0.28.1 | Async/sync HTTP client | External API calls in agent tools [VERIFIED: PyPI registry] |
| tenacity | 9.1.4 | Retry with exponential backoff | Transient failures in LLM calls and API tools [VERIFIED: PyPI registry] |

### Development

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.3 | Test framework | All testing [VERIFIED: PyPI registry] |
| pytest-cov | 7.1.0 | Coverage reporting | Target 80%+ [VERIFIED: PyPI registry] |
| pytest-asyncio | 1.3.0 | Async test support | Testing async agent runs and graph invocations [VERIFIED: PyPI registry] |
| ruff | 0.15.10 | Linting + formatting | Replace black, flake8, isort in one tool [VERIFIED: PyPI registry] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| LangGraph + PydanticAI hybrid | PydanticAI only | PydanticAI lacks graph-based checkpointing, conditional routing, and parallel node execution needed for the manager-analyst pipeline |
| LangGraph + PydanticAI hybrid | LangGraph only | LangGraph nodes lack built-in type-safe output validation and UsageLimits budget enforcement |
| langchain-anthropic | anthropic SDK directly | Direct SDK lacks LangGraph integration (RunnableConfig, callbacks); use both -- langchain-anthropic for graph nodes, anthropic SDK for advanced features later |
| Langfuse self-hosted | LangSmith | LangSmith is paid; Langfuse is open-source with data sovereignty for financial data |

**Installation:**
```bash
# Core orchestration + agent logic
uv add langgraph langchain-core langchain-anthropic pydantic-ai anthropic

# State persistence
uv add langgraph-checkpoint-postgres "psycopg[binary,pool]"

# Observability
uv add langfuse

# Data layer (established patterns from prior project)
uv add sqlalchemy alembic pydantic-settings

# Already expected in stack
uv add structlog httpx tenacity

# Development
uv add --dev pytest pytest-cov pytest-asyncio ruff
```

## Architecture Patterns

### Recommended Project Structure

```
src/
  ai_hedge_fund/
    __init__.py              # Package root
    config.py                # Pydantic settings (env + defaults)
    logging.py               # structlog configuration
    models.py                # Claude model definitions + routing config
    db/
      __init__.py
      base.py                # DeclarativeBase, AppendOnlyMixin, DualTimestampMixin
      session.py             # Engine + session factory
      migrations/            # Alembic migrations
        env.py
        versions/
    schemas/
      __init__.py
      state.py               # LangGraph state schemas (TypedDict)
      agents.py              # PydanticAI output schemas (BaseModel)
    agents/
      __init__.py
      base.py                # Base agent factory with budget enforcement
      extraction.py          # Haiku-routed extraction agent
      analysis.py            # Sonnet-routed analysis agent
    graph/
      __init__.py
      pipeline.py            # LangGraph StateGraph definition
      nodes.py               # Node functions wrapping PydanticAI agents
      checkpointer.py        # PostgresSaver setup and management
    observability/
      __init__.py
      langfuse.py            # Langfuse client init, CallbackHandler factory
      budget.py              # Token budget tracking and enforcement
tests/
  __init__.py
  conftest.py                # Shared fixtures (db session, mock agents)
  unit/
    __init__.py
    test_config.py
    test_schemas.py
    test_agents.py
    test_budget.py
  integration/
    __init__.py
    test_graph.py
    test_checkpointer.py
    test_observability.py
```

### Pattern 1: PydanticAI Agent Wrapped as LangGraph Node

**What:** Each LangGraph node wraps a PydanticAI agent call, providing type-safe I/O at graph boundaries.
**When to use:** Every agent step in the research pipeline.

```python
# Source: https://www.dotzlaw.com/insights/combining-the-power-of-langgraph-with-pydantic-ai-agents/
# Pattern verified via PydanticAI docs + LangGraph docs [VERIFIED: official docs]

from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from langgraph.graph import StateGraph, END, START

# LangGraph state (TypedDict for graph compatibility)
class PipelineState(TypedDict):
    ticker: str
    raw_data: str
    analysis: dict | None
    error: str | None

# PydanticAI output schema (BaseModel for validation)
class AnalysisOutput(BaseModel):
    summary: str = Field(description="Executive summary of analysis")
    confidence: float = Field(ge=0.0, le=1.0)
    key_findings: list[str] = Field(min_length=1)

# PydanticAI agent with budget cap
analysis_agent = Agent(
    "anthropic:claude-sonnet-4-6",
    output_type=AnalysisOutput,
    system_prompt="You are a financial analyst. Analyze the provided data.",
)

# LangGraph node wrapping the PydanticAI agent
async def analyze_node(state: PipelineState) -> dict:
    """Wrap PydanticAI agent as a LangGraph node."""
    limits = UsageLimits(
        input_tokens_limit=50_000,
        output_tokens_limit=4_000,
        total_tokens_limit=54_000,
    )
    result = await analysis_agent.run(
        f"Analyze this data for {state['ticker']}: {state['raw_data']}",
        usage_limits=limits,
    )
    return {"analysis": result.output.model_dump()}

# Graph assembly
builder = StateGraph(PipelineState)
builder.add_node("analyze", analyze_node)
builder.add_edge(START, "analyze")
builder.add_edge("analyze", END)
graph = builder.compile()
```

### Pattern 2: Dual-Model Routing via Model Configuration

**What:** Different LangGraph nodes use different Claude models based on task complexity.
**When to use:** Every node that calls an LLM -- route to appropriate model tier.

```python
# Source: Anthropic model docs + LangGraph init_chat_model docs
# [VERIFIED: platform.claude.com/docs/en/about-claude/models/overview]

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelTier(Enum):
    """Claude model tiers for dual-model routing."""
    EXTRACTION = "anthropic:claude-haiku-4-5"      # $1/$5 per MTok -- fast, cheap
    ANALYSIS = "anthropic:claude-sonnet-4-6"        # $3/$15 per MTok -- best balance
    REASONING = "anthropic:claude-opus-4-6"         # $5/$25 per MTok -- deepest reasoning


@dataclass(frozen=True)
class AgentBudget:
    """Immutable token budget configuration per agent."""
    input_tokens_limit: int
    output_tokens_limit: int
    total_tokens_limit: int


# Budget presets by model tier (conservative defaults)
MODEL_BUDGETS: dict[ModelTier, AgentBudget] = {
    ModelTier.EXTRACTION: AgentBudget(
        input_tokens_limit=20_000,
        output_tokens_limit=2_000,
        total_tokens_limit=22_000,
    ),
    ModelTier.ANALYSIS: AgentBudget(
        input_tokens_limit=50_000,
        output_tokens_limit=8_000,
        total_tokens_limit=58_000,
    ),
    ModelTier.REASONING: AgentBudget(
        input_tokens_limit=100_000,
        output_tokens_limit=16_000,
        total_tokens_limit=116_000,
    ),
}
```

### Pattern 3: PostgreSQL Checkpointing with Resume

**What:** LangGraph graph persists state to PostgreSQL, enabling resume after interruption.
**When to use:** Graph compilation -- always use PostgresSaver in non-test environments.

```python
# Source: https://docs.langchain.com/oss/python/langgraph/add-memory
# [VERIFIED: official LangGraph docs]

from langgraph.checkpoint.postgres import PostgresSaver

DB_URI = "postgresql://hedge:hedge@localhost:5432/ai_hedge_fund"

# Sync pattern
with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()  # Creates required tables on first run
    graph = builder.compile(checkpointer=checkpointer)

    # Invoke with thread_id for state persistence
    config = {"configurable": {"thread_id": "analysis-AAPL-2026-04-11"}}
    result = graph.invoke(initial_state, config)

    # Resume from checkpoint (same thread_id)
    result = graph.invoke({"messages": [new_input]}, config)


# Async pattern (for production)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
    await checkpointer.setup()
    graph = builder.compile(checkpointer=checkpointer)
    result = await graph.ainvoke(initial_state, config)
```

### Pattern 4: Langfuse Observability Integration

**What:** Every graph invocation is traced with model, tokens, latency, and cost per step.
**When to use:** All graph invocations (pass CallbackHandler in config).

```python
# Source: https://langfuse.com/integrations/frameworks/langchain
# [VERIFIED: official Langfuse docs]

from langfuse import get_client
from langfuse.langchain import CallbackHandler

# Initialize (reads LANGFUSE_* env vars automatically)
langfuse_handler = CallbackHandler()

# Pass to every graph invocation
config = {
    "configurable": {"thread_id": "analysis-AAPL-2026-04-11"},
    "callbacks": [langfuse_handler],
    "metadata": {
        "langfuse_session_id": "session-AAPL-2026-04-11",
        "langfuse_user_id": "pipeline-v1",
        "langfuse_tags": ["phase-1", "foundation"],
    },
}
result = await graph.ainvoke(initial_state, config)

# Flush traces before shutdown
get_client().flush()
```

### Pattern 5: Token Budget Enforcement with UsageLimits

**What:** PydanticAI raises UsageLimitExceeded when an agent exceeds its configured token budget mid-run.
**When to use:** Every PydanticAI agent.run() call.

```python
# Source: https://pydantic.dev/docs/ai/api/pydantic-ai/usage/
# [VERIFIED: official PydanticAI docs]

from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits

agent = Agent("anthropic:claude-sonnet-4-6", output_type=str)

limits = UsageLimits(
    input_tokens_limit=50_000,
    output_tokens_limit=4_000,
    total_tokens_limit=54_000,
)

try:
    result = await agent.run("Analyze this data...", usage_limits=limits)
    # Access usage stats
    print(f"Input tokens: {result.usage.input_tokens}")
    print(f"Output tokens: {result.usage.output_tokens}")
except UsageLimitExceeded as e:
    # Pipeline halts with budget-exceeded error
    print(f"Budget exceeded: {e}")
    # Log to Langfuse as error span
```

### Anti-Patterns to Avoid

- **Mutating LangGraph state directly:** Always return a new dict from node functions; never modify the state dict parameter in place. This aligns with the project's immutability convention.
- **Hardcoding model names:** Use an enum or config for model IDs (ModelTier pattern above). Model names change with each generation.
- **Skipping checkpointer.setup():** First-time PostgresSaver use requires calling `.setup()` to create tables. Forgetting this causes runtime errors.
- **Using result_type instead of output_type:** PydanticAI renamed `result_type` to `output_type` in the 1.x stable API. Old name is deprecated. [VERIFIED: PydanticAI changelog]
- **Importing from langfuse.decorators:** Langfuse v4 reorganized its module structure. Use `from langfuse import observe, get_client` and `from langfuse.langchain import CallbackHandler`. [VERIFIED: Langfuse v3-to-v4 migration guide]
- **Passing autocommit=False to psycopg connections for checkpointer:** PostgresSaver requires `autocommit=True` and `row_factory=dict_row` when manually creating connections. [VERIFIED: LangGraph docs]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Graph state persistence | Custom checkpoint serialization | langgraph-checkpoint-postgres PostgresSaver | Handles versioned channel storage, differential writes, connection pooling |
| Token budget enforcement | Custom token counting middleware | PydanticAI UsageLimits + UsageLimitExceeded | Pre-request counting (Anthropic-supported), automatic enforcement, exception-based control flow |
| LLM output validation | Custom JSON parsing + manual validation | PydanticAI output_type with Pydantic BaseModel | Native structured output mode, automatic retry on validation failure, descriptive errors |
| Agent tracing | Custom logging + manual cost calculation | Langfuse CallbackHandler | Automatic trace tree, token counting, cost calculation, latency tracking per step |
| Model routing config | if/else model selection logic | Enum-based ModelTier + config mapping | Centralized, testable, easy to update when model names change |
| PostgreSQL connection pooling | Manual connection management | psycopg_pool ConnectionPool or PostgresSaver.from_conn_string | Handles connection lifecycle, health checks, pool sizing |
| Retry logic for LLM calls | Custom retry loops | tenacity @retry decorator | Exponential backoff, jitter, configurable stop conditions, sync+async |

**Key insight:** The LangGraph + PydanticAI + Langfuse stack provides all the primitives needed for orchestration, validation, budget enforcement, and observability. The integration layer (wrapping PydanticAI agents as LangGraph nodes, passing Langfuse callbacks) is the only custom code needed.

## Common Pitfalls

### Pitfall 1: Langfuse Self-Hosted Infrastructure Complexity
**What goes wrong:** Langfuse v3+ self-hosted requires PostgreSQL + ClickHouse + Redis + MinIO (S3-compatible blob storage). This is 4 additional services beyond the application's own PostgreSQL.
**Why it happens:** Langfuse evolved from a simple PostgreSQL-only setup to a multi-service architecture for performance at scale.
**How to avoid:** For Phase 1 development, use Langfuse Cloud free tier (50K observations/month) instead of self-hosting. Switch to self-hosted when approaching production. Alternatively, configure docker-compose.yml with the full Langfuse stack but understand the resource requirements (ClickHouse alone wants ~2GB RAM). [VERIFIED: Langfuse docker-compose.yml on GitHub]
**Warning signs:** Docker Compose taking minutes to start, high memory usage, ClickHouse health check failures.

### Pitfall 2: LangGraph Version Mismatch with Checkpoint Library
**What goes wrong:** langgraph-checkpoint-postgres 3.x requires langgraph >=1.0. Using an older langgraph version causes import errors or silent data corruption.
**Why it happens:** The checkpoint protocol changed significantly between langgraph 0.x and 1.x. Major version bumps in the checkpoint library correspond to breaking protocol changes.
**How to avoid:** Pin compatible versions together: langgraph>=1.1.0, langgraph-checkpoint-postgres>=3.0.0. [VERIFIED: PyPI dependency metadata]
**Warning signs:** ImportError on checkpoint classes, unexpected schema in checkpoint database tables.

### Pitfall 3: PydanticAI API Naming (result_type vs output_type)
**What goes wrong:** Using deprecated `result_type` parameter on Agent constructor produces DeprecationWarnings or errors in recent versions.
**Why it happens:** PydanticAI renamed `result_type` to `output_type` (and `result_retries` to `output_retries`) as part of the 1.0 stable API cleanup.
**How to avoid:** Always use `output_type`, `output_retries`, `output_tool_name`. The attribute on RunResult is `.output` not `.data` or `.result`. [VERIFIED: PydanticAI changelog/upgrade guide]
**Warning signs:** DeprecationWarning in test output, AttributeError on result objects.

### Pitfall 4: Claude Model Name Changes
**What goes wrong:** Using old model IDs (e.g., `claude-3-5-sonnet-20241022`, `claude-3-haiku-20240307`) causes API errors or routes to deprecated/retired models.
**Why it happens:** Anthropic's model naming changed significantly with the Claude 4.x generation. Haiku 3 retires on April 19, 2026.
**How to avoid:** Use current model IDs: `claude-haiku-4-5` (or `claude-haiku-4-5-20251001`), `claude-sonnet-4-6`, `claude-opus-4-6`. Centralize model names in a config enum so updates are single-point. [VERIFIED: platform.claude.com model overview]
**Warning signs:** 404 errors on model endpoint, "model not found" API responses, unexpectedly high pricing.

### Pitfall 5: Langfuse v4 API Breaking Changes
**What goes wrong:** Code written for Langfuse v2/v3 breaks with v4 due to removed methods and reorganized modules.
**Why it happens:** Langfuse v4 moved to an observation-centric data model. `@observe()` decorator module path changed, `update_current_trace()` was replaced by `propagate_attributes()`, and several v2 API methods were removed.
**How to avoid:** Follow the v3-to-v4 migration guide. Use `from langfuse import observe, get_client` (not `from langfuse.decorators`). Use `propagate_attributes()` context manager instead of `update_current_trace()`. [VERIFIED: langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4]
**Warning signs:** ModuleNotFoundError on import, AttributeError on client methods.

### Pitfall 6: Token Budget Not Enforced Without UsageLimits
**What goes wrong:** PydanticAI agents run without any budget cap by default. Without explicit UsageLimits, a single agent can consume unbounded tokens.
**Why it happens:** UsageLimits defaults to None for all fields. Budget enforcement is opt-in, not opt-out.
**How to avoid:** Always pass `usage_limits=` to every `agent.run()` call. Create a factory function that attaches the appropriate budget based on model tier. Never call agent.run() without limits in production code. [VERIFIED: PydanticAI usage API docs]
**Warning signs:** Unexpectedly high Anthropic bills, single analysis run consuming >$1.

## Code Examples

### Complete Minimal Pipeline (FOUND-01 + FOUND-02 + FOUND-03)

```python
# Source: Synthesized from LangGraph docs + PydanticAI docs + Anthropic model docs
# [VERIFIED: all three official doc sources]

from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.postgres import PostgresSaver


# --- Schemas ---

class PipelineState(TypedDict):
    """LangGraph state flowing between nodes."""
    ticker: str
    raw_text: str
    extraction: dict | None
    analysis: dict | None

class ExtractionOutput(BaseModel):
    """Typed output for extraction agent (Haiku)."""
    key_metrics: list[str] = Field(min_length=1)
    data_quality: float = Field(ge=0.0, le=1.0)

class AnalysisOutput(BaseModel):
    """Typed output for analysis agent (Sonnet)."""
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    key_findings: list[str] = Field(min_length=1)


# --- Agents (different model tiers) ---

extraction_agent = Agent(
    "anthropic:claude-haiku-4-5",
    output_type=ExtractionOutput,
    system_prompt="Extract key financial metrics from the provided text.",
)

analysis_agent = Agent(
    "anthropic:claude-sonnet-4-6",
    output_type=AnalysisOutput,
    system_prompt="Analyze the extracted financial data and provide insights.",
)


# --- Node Functions ---

async def extract_node(state: PipelineState) -> dict:
    limits = UsageLimits(input_tokens_limit=20_000, output_tokens_limit=2_000)
    result = await extraction_agent.run(
        f"Extract metrics from: {state['raw_text']}", usage_limits=limits,
    )
    return {"extraction": result.output.model_dump()}


async def analyze_node(state: PipelineState) -> dict:
    limits = UsageLimits(input_tokens_limit=50_000, output_tokens_limit=8_000)
    result = await analysis_agent.run(
        f"Analyze for {state['ticker']}: {state['extraction']}", usage_limits=limits,
    )
    return {"analysis": result.output.model_dump()}


# --- Graph Assembly ---

def build_pipeline(checkpointer: PostgresSaver | None = None) -> StateGraph:
    builder = StateGraph(PipelineState)
    builder.add_node("extract", extract_node)
    builder.add_node("analyze", analyze_node)
    builder.add_edge(START, "extract")
    builder.add_edge("extract", "analyze")
    builder.add_edge("analyze", END)
    return builder.compile(checkpointer=checkpointer)
```

### Langfuse Integration (FOUND-04)

```python
# Source: https://langfuse.com/integrations/frameworks/langchain
# [VERIFIED: official Langfuse docs]

from langfuse import get_client
from langfuse.langchain import CallbackHandler


def create_langfuse_config(
    thread_id: str,
    session_id: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Create LangGraph config with Langfuse tracing."""
    handler = CallbackHandler()
    return {
        "configurable": {"thread_id": thread_id},
        "callbacks": [handler],
        "metadata": {
            "langfuse_session_id": session_id or thread_id,
            "langfuse_user_id": "pipeline-v1",
            "langfuse_tags": tags or [],
        },
    }


# Usage
config = create_langfuse_config(
    thread_id="analysis-AAPL-2026-04-11",
    tags=["extraction", "haiku"],
)
result = await graph.ainvoke(initial_state, config)

# Flush before shutdown
get_client().flush()
```

### Settings Configuration (Reusing Archive Pattern)

```python
# Source: Archive pattern from archive/2026-04-11-pre-pivot/Al Washing Detector/src/ai_washer/config.py
# [VERIFIED: codebase archive]

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )

    # PostgreSQL
    database_url: str = "postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund"

    # Anthropic
    anthropic_api_key: str = ""

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Budget defaults (tokens per agent run)
    extraction_token_limit: int = Field(default=22_000)
    analysis_token_limit: int = Field(default=58_000)
    reasoning_token_limit: int = Field(default=116_000)
    pipeline_total_token_limit: int = Field(default=500_000)

    # Logging
    log_level: str = "INFO"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| langgraph 0.3.x | langgraph 1.1.6 | Sep 2025 (1.0 alpha) | Breaking changes in checkpoint protocol; 1.x required for checkpoint-postgres 3.x [VERIFIED: PyPI] |
| pydantic-ai result_type | pydantic-ai output_type | Sep 2025 (1.0 stable) | Renamed parameter; old name deprecated [VERIFIED: PydanticAI changelog] |
| langfuse 2.x @observe from langfuse.decorators | langfuse 4.x @observe from langfuse | Mar 2026 (v4.0) | Module restructure, observation-centric model, removed update_current_trace() [VERIFIED: Langfuse migration guide] |
| claude-3-haiku-20240307 | claude-haiku-4-5-20251001 | Oct 2025 | Old Haiku 3 retires April 19, 2026; new Haiku 4.5 costs $1/$5 MTok vs $0.25/$1.25 [VERIFIED: Anthropic docs] |
| claude-3-5-sonnet-20241022 | claude-sonnet-4-6 | 2026 | New generation; $3/$15 MTok pricing, 1M context, 64k output [VERIFIED: Anthropic docs] |
| Langfuse self-hosted (PG only) | Langfuse self-hosted (PG + ClickHouse + Redis + MinIO) | v3.0+ | Much heavier infrastructure; consider cloud free tier for development [VERIFIED: Langfuse GitHub] |

**Deprecated/outdated:**
- **claude-3-haiku-20240307:** Retiring April 19, 2026. Migrate to claude-haiku-4-5. [VERIFIED: Anthropic docs]
- **PydanticAI result_type parameter:** Use output_type. [VERIFIED: PydanticAI changelog]
- **langfuse.decorators module path:** Use `from langfuse import observe`. [VERIFIED: Langfuse v4 migration]
- **langfuse update_current_trace():** Use `propagate_attributes()` context manager. [VERIFIED: Langfuse v4 migration]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | psycopg-pool is required as a separate install for langgraph-checkpoint-postgres connection management | Standard Stack | LOW -- may be pulled in as transitive dependency; if not, easy to add |
| A2 | Langfuse Cloud free tier (50K observations/month) is sufficient for Phase 1 development | Pitfall 1 | LOW -- if exceeded, can self-host or upgrade; free tier well above development usage |
| A3 | PydanticAI UsageLimits count_tokens_before_request works with Anthropic provider for pre-request enforcement | Code Examples | MEDIUM -- if not supported, budget enforcement only works post-response; still catches overruns but after spending |
| A4 | LangGraph 1.1.6 is compatible with langgraph-checkpoint-postgres 3.0.5 without version conflicts | Standard Stack | LOW -- both are current latest versions from same org |

## Open Questions

1. **Langfuse Deployment Strategy for Development**
   - What we know: Self-hosted Langfuse v3+ requires PostgreSQL + ClickHouse + Redis + MinIO (heavy). Cloud free tier offers 50K observations/month.
   - What's unclear: Whether to self-host from day one (matches CLAUDE.md "self-hosted" guidance) or use cloud free tier for Phase 1 development.
   - Recommendation: Use Langfuse Cloud free tier for Phase 1 (zero ops overhead, sufficient volume). Add self-hosted config to docker-compose.yml as a deferred task. The Python SDK code is identical either way -- just different env vars.

2. **Pipeline-Level Budget Enforcement**
   - What we know: PydanticAI UsageLimits works per-agent-run. RunUsage.incr() can accumulate across runs.
   - What's unclear: Best pattern for enforcing a total pipeline budget across multiple sequential agent invocations within a single LangGraph graph execution.
   - Recommendation: Create a BudgetTracker that accumulates usage across nodes and checks against pipeline total before each node execution. Pass as part of graph state.

3. **LangGraph State Schema: TypedDict vs Pydantic BaseModel**
   - What we know: LangGraph accepts both TypedDict and Pydantic BaseModel for state schemas. PydanticAI uses BaseModel for output schemas.
   - What's unclear: Whether to use TypedDict (LangGraph standard) or BaseModel (more validation) for graph state.
   - Recommendation: Use TypedDict for LangGraph state (lower overhead, better LangGraph integration), BaseModel for PydanticAI output schemas (validation at agent boundaries). Validate at the boundary, not inside the graph.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | Yes | 3.12.11 | -- |
| uv | Package management | Yes | 0.11.2 | -- |
| Docker | PostgreSQL, Langfuse | Yes | 29.0.1 | -- |
| Docker Compose | Multi-service orchestration | Yes | v2.40.3 | -- |
| PostgreSQL (via Docker) | Checkpointing, data layer | No (not running) | 16-alpine (in docker-compose.yml) | Start with `docker compose up -d` |
| ruff | Linting/formatting | Yes (via uv) | 0.15.10 (PyPI latest) | Install via `uv add --dev ruff` |
| pytest | Testing | No (not installed locally) | 9.0.3 (PyPI latest) | Install via `uv add --dev pytest` |
| Langfuse (self-hosted) | Observability | No | Requires PG + ClickHouse + Redis + MinIO | Use Langfuse Cloud free tier |

**Missing dependencies with no fallback:**
- PostgreSQL must be running for checkpointing tests. Start with `docker compose up -d`.

**Missing dependencies with fallback:**
- Langfuse self-hosted requires heavy infrastructure. Use Langfuse Cloud free tier for Phase 1 development.
- pytest and ruff need to be installed via uv (expected -- greenfield project, no pyproject.toml yet).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.3.0 |
| Config file | none -- Wave 0 must create pyproject.toml with pytest config |
| Quick run command | `uv run pytest tests/unit -x -q` |
| Full suite command | `uv run pytest tests/ -x --cov=src/ai_hedge_fund --cov-report=term-missing` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FOUND-01 | LangGraph graph compiles, runs 2+ nodes, checkpoints to PG, resumes from checkpoint | integration | `uv run pytest tests/integration/test_graph.py -x` | No -- Wave 0 |
| FOUND-02 | PydanticAI agent accepts typed input, returns validated output; invalid output raises ValidationError | unit | `uv run pytest tests/unit/test_agents.py -x` | No -- Wave 0 |
| FOUND-03 | Pipeline routes 2+ tasks to different Claude models; Langfuse trace shows which model per step | integration | `uv run pytest tests/integration/test_model_routing.py -x` | No -- Wave 0 |
| FOUND-04 | Langfuse trace captures model, tokens, latency per graph step | integration | `uv run pytest tests/integration/test_observability.py -x` | No -- Wave 0 |
| FOUND-05 | Agent exceeding token budget raises UsageLimitExceeded; pipeline halts that agent | unit | `uv run pytest tests/unit/test_budget.py -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit -x -q`
- **Per wave merge:** `uv run pytest tests/ -x --cov=src/ai_hedge_fund --cov-report=term-missing`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `pyproject.toml` -- project config with pytest settings, ruff config, uv dependencies
- [ ] `src/ai_hedge_fund/__init__.py` -- package root
- [ ] `tests/conftest.py` -- shared fixtures (mock agents, test DB connection, Langfuse mock)
- [ ] `tests/unit/__init__.py` + `tests/integration/__init__.py` -- test packages
- [ ] `tests/unit/test_agents.py` -- covers FOUND-02, FOUND-05
- [ ] `tests/unit/test_budget.py` -- covers FOUND-05
- [ ] `tests/unit/test_schemas.py` -- covers FOUND-02
- [ ] `tests/integration/test_graph.py` -- covers FOUND-01
- [ ] `tests/integration/test_model_routing.py` -- covers FOUND-03
- [ ] `tests/integration/test_observability.py` -- covers FOUND-04
- [ ] Framework install: `uv init && uv add --dev pytest pytest-cov pytest-asyncio ruff`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A -- infrastructure phase, no user-facing auth |
| V3 Session Management | No | N/A -- no user sessions |
| V4 Access Control | No | N/A -- no multi-user access yet |
| V5 Input Validation | Yes | Pydantic BaseModel schemas for all LLM outputs; PydanticAI output_type validation |
| V6 Cryptography | No | N/A -- no crypto operations in Phase 1 |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key exposure in source code | Information Disclosure | pydantic-settings loads from .env; .gitignore excludes .env; validate keys present at startup |
| LLM prompt injection via tool outputs | Tampering | PydanticAI output schemas reject unexpected fields; structured output mode forces schema compliance |
| Unbounded token consumption (cost attack) | Denial of Service | PydanticAI UsageLimits per agent; pipeline-level budget tracker; Langfuse cost alerts |
| Database connection string in logs | Information Disclosure | structlog with filtered processors; never log raw connection strings |
| Checkpoint data tampering | Tampering | PostgreSQL access restricted to application user; no public endpoint; connection via Docker network |

## Sources

### Primary (HIGH confidence)
- [PyPI: langgraph 1.1.6](https://pypi.org/project/langgraph/) -- version verified 2026-04-11
- [PyPI: pydantic-ai 1.80.0](https://pypi.org/project/pydantic-ai/) -- version verified 2026-04-11
- [PyPI: langchain-anthropic 1.4.0](https://pypi.org/project/langchain-anthropic/) -- version verified 2026-04-11
- [PyPI: langfuse 4.2.0](https://pypi.org/project/langfuse/) -- version verified 2026-04-11
- [PyPI: langgraph-checkpoint-postgres 3.0.5](https://pypi.org/project/langgraph-checkpoint-postgres/) -- version verified 2026-04-11
- [Anthropic Model Overview](https://platform.claude.com/docs/en/about-claude/models/overview) -- model IDs and pricing verified 2026-04-11
- [PydanticAI Agent Docs](https://pydantic.dev/docs/ai/core-concepts/agent/) -- Agent constructor API verified 2026-04-11
- [PydanticAI Usage Limits Docs](https://pydantic.dev/docs/ai/api/pydantic-ai/usage/) -- UsageLimits API verified 2026-04-11
- [LangGraph Memory/Persistence Docs](https://docs.langchain.com/oss/python/langgraph/add-memory) -- PostgresSaver pattern verified 2026-04-11
- [Langfuse LangChain Integration](https://langfuse.com/integrations/frameworks/langchain) -- CallbackHandler pattern verified 2026-04-11
- [Langfuse v3-to-v4 Migration](https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4) -- breaking changes verified 2026-04-11
- [Langfuse Docker Compose](https://github.com/langfuse/langfuse/blob/main/docker-compose.yml) -- infrastructure requirements verified 2026-04-11

### Secondary (MEDIUM confidence)
- [LangGraph + PydanticAI Integration Pattern](https://www.dotzlaw.com/insights/combining-the-power-of-langgraph-with-pydantic-ai-agents/) -- node wrapper pattern
- [Langfuse LangGraph Cookbook](https://langfuse.com/guides/cookbook/integration_langgraph) -- agent tracing examples

### Tertiary (LOW confidence)
- None -- all critical claims verified against primary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions verified on PyPI registry, all APIs verified against official docs
- Architecture: HIGH -- integration pattern verified across official docs from LangGraph, PydanticAI, and Langfuse; model IDs verified on Anthropic platform
- Pitfalls: HIGH -- version mismatches, API renames, and infrastructure requirements all verified against official sources

**Research date:** 2026-04-11
**Valid until:** 2026-05-11 (30 days -- all libraries on active release cycles but core APIs stable)
