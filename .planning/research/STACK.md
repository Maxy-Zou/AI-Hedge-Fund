# Technology Stack

**Project:** AI Hedge Fund Multi-Agent System
**Researched:** 2026-04-11

## Recommended Stack

### Core Orchestration
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| LangGraph | >=0.3 | Multi-agent orchestration, state management, checkpointing | Dominant in financial agent systems; used by S&P Global/Kensho, TradingAgents; best production features (durable execution, human-in-the-loop, parallel nodes) |
| langchain-core | >=0.3 | Base abstractions for LangGraph | Required dependency; provides chat message types, tool abstractions |
| langchain-anthropic | >=0.3 | Claude model integration for LangGraph | Official Anthropic adapter for LangChain/LangGraph ecosystem |

### Agent Logic
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PydanticAI | >=1.0 | Type-safe agent definitions, dependency injection | 8/10 developer experience score; type safety catches agent logic errors at dev time; matches existing codebase Pydantic patterns |
| Pydantic | >=2.0 | Data validation, schema definitions | Already in stack; financial data schemas need runtime validation |

### LLM Provider
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| anthropic | >=0.40 | Direct Claude API access for advanced features | Prompt caching (90% cost reduction), extended thinking, streaming; use alongside langchain-anthropic for features not exposed through LangGraph |

### Observability
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Langfuse | >=2.0 | LLM tracing, cost tracking, debugging | Open-source, self-hosted (data sovereignty for financial data); MIT license; integrates with LangGraph |

### Database
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | 16+ | Agent state checkpointing, market data, signals | Already in stack via Docker Compose; LangGraph has native PostgreSQL checkpointer |
| SQLAlchemy | >=2.0 | ORM for data layer | Already in stack; append-only patterns established |

### Infrastructure
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker Compose | latest | PostgreSQL, Langfuse, development environment | Already in stack; add Langfuse container |
| uv | latest | Package management | Already in stack; fast, reliable |

## Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| langgraph-checkpoint-postgres | >=0.2 | PostgreSQL-backed state persistence | Production: persist agent state across restarts |
| structlog | >=25.0 | Structured logging | Already in stack; agent-level log binding |
| httpx | >=0.28 | Async HTTP for tool calls (SEC EDGAR, news APIs) | Already in stack; agents making external API calls |
| tenacity | >=9.0 | Retry logic for LLM calls and API tools | Already in stack; handle transient failures in agent tool calls |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Orchestration | LangGraph | CrewAI | Reliability issues (cascading failures), basic memory, security concerns, less fine-grained control |
| Orchestration | LangGraph | AutoGen/AG2 | Fragmented ecosystem, token-expensive group chat, neither fork production-ready |
| Orchestration | LangGraph | Claude Agent SDK | Pre-1.0, lighter orchestration (no graph/checkpointing), Claude-only lock-in |
| Orchestration | LangGraph | OpenAI Agents SDK | GPT model lock-in; we want Claude as primary |
| Orchestration | LangGraph | Custom build | 6+ months building infrastructure; $600k-$1.5M per agent estimated cost |
| Agent logic | PydanticAI | Raw functions | No type safety, no dependency injection, no output validation |
| Agent logic | PydanticAI | LangChain agents | More abstraction layers, less type safety, harder to test |
| Observability | Langfuse | LangSmith | Paid service; Langfuse is open-source, self-hostable (data sovereignty for financial data) |
| Observability | Langfuse | Helicone | Less LangGraph integration; Langfuse has better trace visualization |

## Installation

```bash
# Core orchestration
uv add langgraph langchain-core langchain-anthropic

# Agent logic
uv add pydantic-ai pydantic

# Direct LLM access (for advanced features)
uv add anthropic

# State persistence
uv add langgraph-checkpoint-postgres

# Observability
uv add langfuse

# Already in stack (verify versions)
# uv add sqlalchemy psycopg[binary] structlog httpx tenacity
```

## Sources

- [LangGraph GitHub (126k stars)](https://github.com/langchain-ai/langgraph)
- [PydanticAI Documentation](https://ai.pydantic.dev/)
- [Langfuse (open-source LLM observability)](https://langfuse.com/)
- [Kensho/S&P Global LangGraph deployment](https://blog.langchain.com/tag/case-studies/)
- [LangGraph PostgreSQL checkpointer](https://docs.langchain.com/oss/python/langgraph/persistence)
