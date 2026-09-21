# AI Hedge Fund

AI-native quantitative hedge fund. Multi-agent research system where LLM agents generate investment hypotheses, gather evidence from SEC filings and financial data, adversarially critique each other's theses, and produce quantitative signals backed by structured thesis documents.

## Project Structure

```
AI Hedgefund/
├── CLAUDE.md                # This file — project-wide conventions
├── src/                     # Main application source code
├── tests/                   # Test suite
├── archive/                 # Archived pre-pivot strategies and backtest code
├── docs/                    # Project documentation
├── docker-compose.yml       # PostgreSQL for shared data persistence
└── .planning/               # GSD workflow artifacts and research
```

## Stack

- **Language:** Python 3.11+ (3.12 recommended)
- **Package management:** uv
- **Database:** PostgreSQL 16+ (via Docker Compose)
- **Orchestration:** LangGraph — graph-based state machines for multi-agent pipelines, checkpointing, human-in-the-loop
- **Agent logic:** PydanticAI — type-safe agent definitions with validated I/O
- **LLM provider:** Claude models via Anthropic API (langchain-anthropic for LangGraph integration)
- **Observability:** Langfuse (open-source, self-hosted) for agent traces, cost tracking, latency monitoring
- **Linter/formatter:** ruff (line-length=100, target-version=py312)
- **Testing:** pytest

## Architecture

### Multi-Agent Research Pipeline

```
                    [Research Manager]
                    /       |        \
         [Fundamental]  [Sentiment]  [Technical/Quant]
                    \       |        /
                  [Bull Advocate Agent]
                          vs.
                  [Bear Advocate Agent]
                          |
                   [Thesis Synthesis]
                          |
                   [Risk Manager] (veto power)
                          |
                   [Human Review] ← NON-NEGOTIABLE
                          |
                   [Signal Output]
```

**Pattern:** Manager-Analyst Hierarchy + Adversarial Bull/Bear Debate — validated independently by FinCon (NeurIPS 2024), TradingAgents, and AlphaAgents (BlackRock).

### Layers

- **Orchestration (LangGraph):** Directed graph defining the analysis pipeline. Nodes are agent steps, edges carry state. Handles checkpointing, parallel execution, human-in-the-loop interrupts.
- **Agent Logic (PydanticAI):** Each agent is a typed Python object with declared model, instructions, output schema, and tools. Dependency injection for data sources.
- **Tools:** Deterministic functions for financial calculations, data retrieval, technical indicators. LLMs orchestrate tools — they never compute financial ratios directly.
- **Memory:** Three-tier architecture:
  - Session memory (LLM context window) — current analysis, discarded after
  - Episodic memory (PostgreSQL + embeddings) — recent analyses, trade outcomes, 90-day retention
  - Belief memory (structured YAML/JSON) — investment theses, sector models, learned patterns. Human-readable and human-editable.
- **Data Layer:** PostgreSQL for persistent storage, append-only for financial time-series

### Dual-Model Routing

| Task | Model | Rationale |
|------|-------|-----------|
| Data extraction, formatting, classification | Claude Haiku | Fast, cheap, sufficient for structured tasks |
| Analysis, thesis generation, synthesis | Claude Sonnet | Best coding/analysis model, good cost ratio |
| Complex reasoning, adversarial debate | Claude Opus | Deepest reasoning for high-stakes decisions |

### Debate Protocol (5-Act Structure)

Structured adversarial debate, not free-form (SAS paper evidence):
1. **Initial thesis** — Bull agent presents investment case
2. **Counter-thesis** — Bear agent presents opposing case
3. **Rebuttal** — Each side addresses the other's strongest points
4. **Final arguments** — Each side makes closing case with evidence citations
5. **Synthesis** — Manager agent resolves into final recommendation with confidence

## Data Sources

Priority order for agent consumption:

| Priority | Source | Type | Cost | Notes |
|----------|--------|------|------|-------|
| 1 | SEC EDGAR + edgartools | Filings (10-K, 10-Q, 8-K) + XBRL | Free | Most LLM-friendly financial data. CompanyFacts API for structured financials. |
| 2 | SEC Form 4 | Insider trades | Free | Strong alpha signal. Detect cluster buys. |
| 3 | FRED | Macro (rates, CPI, GDP) | Free | Essential context. 800K+ time series. |
| 4 | yfinance (cached to PostgreSQL) | Daily OHLCV prices | Free | Download once, never re-fetch. Fragile but sufficient with backoff. |
| 5 | Finnhub | News + sentiment + real-time quotes | Free (60 req/min) | Most generous free tier for real-time data. |
| 6 | FMP | Fundamentals, financial ratios | Free (250 calls/day) | Earnings transcripts on Ultimate plan ($56/mo). |
| 7 | ThetaData | Options chains, IV, Greeks | Free (EOD) / $25/mo | Best value for options data. |
| 8 | Polygon.io | Reliable equity data | $29/mo | First paid upgrade — replaces yfinance fragility. |

## Conventions

### Code Style
- All API keys and secrets go in `.env` files (never committed)
- Use immutable data patterns — return new objects, don't mutate in place
- Validate all external data at ingestion boundaries
- All timestamps in UTC
- Financial data preserves source precision (don't round prematurely)
- Type hints required on all function params and return values
- Use `str | None` union syntax (3.10+ via `from __future__ import annotations`)
- Functions under 50 lines, files under 800 lines
- ruff for formatting and linting: `ruff format . && ruff check . --fix`

### Dependency Policy
Vendor/library drift has broken this project three times (edgartools 5.x, then
pydantic-ai 1.x -> 2.x). The cause was open-ended `>=` floors with no committed
lockfile, so every clone resolved to whatever was newest on PyPI that day.

- **`uv.lock` is committed.** It is the source of truth for what actually works.
  Never add it back to `.gitignore`.
- **Install with `uv sync --frozen --extra dev`** for any reproducible context
  (CI, a fresh clone, debugging someone else's failure). Plain `uv sync` may
  re-resolve.
- **Every direct dependency carries an upper bound** (`>=floor,<next-major`) in
  `pyproject.toml`. A major bump must be a deliberate, reviewed change.
- **Upgrade deliberately:** `uv sync --upgrade-package <name>`, run the full
  suite, and commit the lockfile delta in its own commit so the diff is
  reviewable. Never blanket `uv sync --upgrade` as a side effect of other work.
- **Floors encode "known-good", not "whatever installed".** Raise a floor only
  when the code genuinely requires the newer API, and say why in a comment
  (see the `pydantic-ai` entry in `pyproject.toml`).

### Agent Development Rules
- **Tool-first for quantitative work.** LLMs NEVER compute financial ratios, run backtests, or calculate position sizes directly. They orchestrate tools that do this deterministically.
- **Strict temporal controls.** Every data input must have a timestamp. RAG retrieval must filter by "available as of analysis date." This prevents look-ahead bias.
- **Structured debate only.** Adversarial critique uses the 5-act protocol. No free-form agent chat.
- **Token budgets from day one.** Every agent has a per-run token cap. Every pipeline has a total cost cap. Use Langfuse to track.
- **Belief memory is human-readable.** Investment beliefs stored as structured documents (YAML/JSON), not opaque embeddings. Humans can read, edit, and override.

### Fix-as-you-find
When incidental errors or mistakes surface during unrelated work — a broken import, a stale library call, a failing assertion, a typo, a dead branch, drift between code and tests — fix them inline in the same session rather than just reporting them. Group the fixes into their own atomic commit (separate from the main task's commit) so history stays reviewable. If a discovered issue is large enough to warrant its own plan (>~50 LOC change, architectural, or crosses phase boundaries), file it as a `/gsd-debug` session instead of patching ad-hoc.

### Data Handling
- Raw data cached locally (PostgreSQL) to avoid redundant API calls
- Append-only for financial time-series data (never overwrite historical observations)
- Dual timestamps where relevant: business date (as_of_date) vs. collection date (observed_date)
- Always use filing date (not period end date) for SEC data — prevents look-ahead bias
- Always use adjusted close prices for return calculations
- Pre-process structured data into natural language summaries before LLM consumption (don't feed raw XBRL JSON)

### Honest Positioning
- Position as "LLM-powered research at scale" — not "AI that beats the market"
- FINSABER (KDD 2026) shows LLM strategies don't beat buy-and-hold on rigorous evaluation
- SEC fined Delphia and Global Predictions for AI washing (March 2024) — never claim AI does something it doesn't

## Environment Variables

```bash
# PostgreSQL
DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund

# Anthropic (Claude models)
ANTHROPIC_API_KEY=

# Data sources (free tier)
EDGAR_IDENTITY="YourCompany yourname@example.com"
FINNHUB_API_KEY=
FMP_API_KEY=
FRED_API_KEY=

# Data sources (paid, add when budget allows)
POLYGON_API_KEY=
THETADATA_API_KEY=

# Observability
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=

# Logging
LOG_LEVEL=INFO
```

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.

## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.

<!-- GSD:project-start source:PROJECT.md -->
## Project

**AI-Native Hedge Fund — Multi-Agent Research System**

A multi-agent LLM research system for an AI-native hedge fund targeting US equities and options. Agents generate investment hypotheses, gather evidence from SEC filings and financial data, adversarially critique each other's theses, and produce quantitative signals backed by structured thesis documents. The system is the core IP of a management company targeting YC and eventual LP capital.

**Core Value:** Produce institutional-quality investment research at scale — structured theses with quantitative signals that are rigorous enough to trade on and transparent enough to show investors.

### Constraints

- **Stack**: Python 3.11+, uv, PostgreSQL, LangGraph + PydanticAI — proven combination for financial multi-agent systems
- **LLM provider**: Claude models primary (Haiku/Sonnet/Opus routing) — 200k context handles full 10-K filings
- **Data budget**: Start at $0/mo (SEC EDGAR + yfinance + Finnhub + FMP free + FRED), upgrade to ~$110/mo (Polygon + FMP Ultimate + ThetaData) when budget allows
- **Immutability**: All financial time-series data is append-only (fund-wide convention from prior work)
- **Honest positioning**: Never claim autonomous alpha generation — SEC fined Delphia and Global Predictions for AI washing (March 2024)
- **Human oversight**: All trade-level decisions require human review — no production hedge fund runs fully autonomous LLM trading
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

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
# Core orchestration
# Agent logic
# Direct LLM access (for advanced features)
# State persistence
# Observability
# Already in stack (verify versions)
# uv add sqlalchemy psycopg[binary] structlog httpx tenacity
## Sources
- [LangGraph GitHub (126k stars)](https://github.com/langchain-ai/langgraph)
- [PydanticAI Documentation](https://ai.pydantic.dev/)
- [Langfuse (open-source LLM observability)](https://langfuse.com/)
- [Kensho/S&P Global LangGraph deployment](https://blog.langchain.com/tag/case-studies/)
- [LangGraph PostgreSQL checkpointer](https://docs.langchain.com/oss/python/langgraph/persistence)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

### Code Style
- All API keys and secrets go in `.env` files (never committed)
- Use immutable data patterns — return new objects, don't mutate in place
- Validate all external data at ingestion boundaries
- All timestamps in UTC
- Financial data preserves source precision (don't round prematurely)
- Type hints required on all function params and return values
- Use `str | None` union syntax (3.10+ via `from __future__ import annotations`)
- Functions under 50 lines, files under 800 lines
- ruff for formatting and linting: `ruff format . && ruff check . --fix`

### Agent Development Rules
- **Tool-first for quantitative work.** LLMs NEVER compute financial ratios, run backtests, or calculate position sizes directly. They orchestrate tools that do this deterministically.
- **Strict temporal controls.** Every data input must have a timestamp. RAG retrieval must filter by "available as of analysis date." This prevents look-ahead bias.
- **Structured debate only.** Adversarial critique uses the 5-act protocol. No free-form agent chat.
- **Token budgets from day one.** Every agent has a per-run token cap. Every pipeline has a total cost cap. Use Langfuse to track.
- **Belief memory is human-readable.** Investment beliefs stored as structured documents (YAML/JSON), not opaque embeddings. Humans can read, edit, and override.

### Data Handling
- Raw data cached locally (PostgreSQL) to avoid redundant API calls
- Append-only for financial time-series data (never overwrite historical observations)
- Dual timestamps where relevant: business date (as_of_date) vs. collection date (observed_date)
- Always use filing date (not period end date) for SEC data — prevents look-ahead bias
- Always use adjusted close prices for return calculations
- Pre-process structured data into natural language summaries before LLM consumption (don't feed raw XBRL JSON)

### Honest Positioning
- Position as "LLM-powered research at scale" — not "AI that beats the market"
- FINSABER (KDD 2026) shows LLM strategies don't beat buy-and-hold on rigorous evaluation
- SEC fined Delphia and Global Predictions for AI washing (March 2024) — never claim AI does something it doesn't
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

### Multi-Agent Research Pipeline

```
                    [Research Manager]
                    /       |        \
         [Fundamental]  [Sentiment]  [Technical/Quant]
                    \       |        /
                  [Bull Advocate Agent]
                          vs.
                  [Bear Advocate Agent]
                          |
                   [Thesis Synthesis]
                          |
                   [Risk Manager] (veto power)
                          |
                   [Human Review] <- NON-NEGOTIABLE
                          |
                   [Signal Output]
```

**Pattern:** Manager-Analyst Hierarchy + Adversarial Bull/Bear Debate — validated independently by FinCon (NeurIPS 2024), TradingAgents, and AlphaAgents (BlackRock).

### Layers

- **Orchestration (LangGraph):** Directed graph defining the analysis pipeline. Nodes are agent steps, edges carry state. Handles checkpointing, parallel execution, human-in-the-loop interrupts.
- **Agent Logic (PydanticAI):** Each agent is a typed Python object with declared model, instructions, output schema, and tools. Dependency injection for data sources.
- **Tools:** Deterministic functions for financial calculations, data retrieval, technical indicators. LLMs orchestrate tools — they never compute financial ratios directly.
- **Memory:** Three tiers:
  - Session memory (LLM context window) — current analysis, discarded after
  - Episodic memory (PostgreSQL + embeddings) — recent analyses, trade outcomes, 90-day retention
  - Belief memory (structured YAML/JSON) — investment theses, sector models, learned patterns. Human-readable and human-editable.
- **Data Layer:** PostgreSQL for persistent storage, append-only for financial time-series

### Dual-Model Routing

| Task | Model | Rationale |
|------|-------|-----------|
| Data extraction, formatting, classification | Claude Haiku | Fast, cheap, sufficient for structured tasks |
| Analysis, thesis generation, synthesis | Claude Sonnet | Best coding/analysis model, good cost ratio |
| Complex reasoning, adversarial debate | Claude Opus | Deepest reasoning for high-stakes decisions |

### Debate Protocol (5-Act Structure)

1. **Initial thesis** — Bull agent presents investment case
2. **Counter-thesis** — Bear agent presents opposing case
3. **Rebuttal** — Each side addresses the other's strongest points
4. **Final arguments** — Each side makes closing case with evidence citations
5. **Synthesis** — Manager agent resolves into final recommendation with confidence

### Data Sources (Priority Order)

| Priority | Source | Type | Cost |
|----------|--------|------|------|
| 1 | SEC EDGAR + edgartools | Filings (10-K, 10-Q, 8-K) + XBRL | Free |
| 2 | SEC Form 4 | Insider trades | Free |
| 3 | FRED | Macro (rates, CPI, GDP) | Free |
| 4 | yfinance (cached to PostgreSQL) | Daily OHLCV prices | Free |
| 5 | Finnhub | News + sentiment + real-time quotes | Free |
| 6 | FMP | Fundamentals, financial ratios | Free |
| 7 | ThetaData | Options chains, IV, Greeks | Free EOD / $25/mo |
| 8 | Polygon.io | Reliable equity data | $29/mo |
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
