# Multi-Agent LLM Framework Research

**Domain:** Agent orchestration for financial multi-agent systems
**Researched:** 2026-04-11
**Overall confidence:** MEDIUM-HIGH (fast-moving space; rankings shift quarterly)

---

## Framework Comparison Table

| Framework | Architecture | GitHub Stars | Maturity | Model Lock-in | Finance Fit | Production Ready |
|-----------|-------------|-------------|----------|---------------|-------------|-----------------|
| **LangGraph** | Directed graph / state machine | ~126k | High (2+ yrs) | None | HIGH | YES |
| **PydanticAI** | Type-safe agent objects | ~16k | Medium (1 yr stable) | None | HIGH | YES |
| **CrewAI** | Role-based crews | ~28k | Medium | None | MEDIUM | Partial |
| **OpenAI Agents SDK** | Handoff-based delegation | ~18k | Medium (1 yr) | OpenAI models | MEDIUM | YES |
| **Claude Agent SDK** | Tool-use loop + sub-agents | ~40k+ | Medium (early) | Claude models | MEDIUM-HIGH | Partial |
| **Microsoft Agent Framework** | SK + AutoGen merged | ~25k | Medium (v1.0 Apr 2026) | None | MEDIUM | YES (just GA) |
| **AutoGen / AG2** | Group chat + event-driven | ~75k | Fragmented | None | LOW-MEDIUM | Partial |
| **Google ADK** | Hierarchical agent tree | ~15k | Early | Gemini-optimized | LOW | Partial |
| **Haystack** | DAG pipeline components | ~42k | High (3+ yrs) | None | MEDIUM | YES |

### Detailed Framework Profiles

#### LangGraph -- RECOMMENDED PRIMARY FRAMEWORK

**Architecture:** Agents modeled as nodes in a directed graph. State flows along edges (including conditional and cyclic edges). Each node is a reasoning step, tool call, or sub-agent invocation. The graph is compiled into a runnable with built-in checkpointing.

**Strengths:**
- Most production-proven framework for multi-agent systems (used by Klarna, Replit, Elastic, Kensho/S&P Global)
- Durable execution with automatic checkpoint/resume -- critical for long-running financial analysis
- Human-in-the-loop via `interrupt()` pauses with state inspection -- essential for high-stakes trading decisions
- LangSmith observability is best-in-class: step-by-step execution traces, cost tracking, latency monitoring
- Model-agnostic: works with Claude, GPT, Gemini, open-source models
- PostgreSQL and SQLite checkpointers for persistent state
- Supports parallel node execution (multiple analysts running concurrently)
- Time-travel debugging: rewind agent state to any checkpoint

**Weaknesses:**
- Steep learning curve; assumes familiarity with graph/state-machine concepts
- Verbose for simple use cases (overkill for single-agent tasks)
- LangChain ecosystem dependency (though lighter than full LangChain)
- LangSmith is a paid service for production observability (open-source Langfuse is an alternative)

**Finance-specific evidence:**
- Kensho (S&P Global's AI lab) built their Grounding framework on LangGraph for enterprise-scale financial data retrieval
- Captide uses LangGraph Platform for investment research and equity modeling agents
- Both TradingAgents and virattt/ai-hedge-fund (43k+ stars, 7.5k forks combined) use LangGraph as their orchestration layer
- Hierarchical architecture on LangGraph achieves 98.5% of best F1 at 60.7% of cost for financial document processing (per arXiv benchmarks)

**Confidence:** HIGH -- multiple production deployments, academic validation, dominant community adoption

#### PydanticAI -- RECOMMENDED FOR AGENT LOGIC LAYER

**Architecture:** Each agent is a typed Python object with declared model, instructions, output schema, and tool functions. Dependencies injected via dataclass. Outputs validated against Pydantic models at runtime and type-checked by mypy/pyright at dev time.

**Strengths:**
- Type-safe inputs/outputs catch agent logic errors at development time before production
- Five lines to define a basic agent; decorated Python functions as tools
- Model-agnostic across 25+ providers (trivially swap Claude for GPT for local models)
- Dependency injection makes testing straightforward (mock data sources, mock LLM calls)
- Scored 8/10 for developer experience in Nextbuild 90-day benchmark (highest of five frameworks tested)
- 1.x stable API since late 2025; A2A support, durable execution, human-in-the-loop
- Built by the Pydantic team -- same validation layer that powers OpenAI, Anthropic, LangChain SDKs

**Weaknesses:**
- Less mature multi-agent orchestration (single-agent focus; multi-agent patterns are manual)
- No built-in graph/workflow engine (you write the orchestration yourself or pair with LangGraph)
- Smaller ecosystem than LangGraph/LangChain
- Limited built-in observability (no equivalent to LangSmith)

**Finance-specific fit:**
- Type safety is critical for financial data -- prevents silent schema drift in market data, signals, positions
- Pydantic models already used throughout this codebase (AppSettings, FilingData, XBRLFact)
- Dependency injection pattern matches fund's existing client injection approach (EFTSClient, EdgarFactsClient)
- Immutable frozen dataclasses align with fund's append-only data philosophy

**Confidence:** MEDIUM-HIGH -- stable release, strong design principles, but less production evidence at scale for multi-agent specifically

#### CrewAI

**Architecture:** Role-based agents organized into "crews." Each agent has a role, goal, and backstory. Tasks assigned to agents and executed sequentially, hierarchically, or consensually.

**Strengths:**
- Lowest learning curve; role-based DSL needs ~20 lines to start
- Natural mapping to team metaphors (analyst, risk manager, portfolio manager)
- Good for prototyping multi-agent workflows quickly

**Weaknesses:**
- Observability limited in open-source version; debugging which agent broke requires detective work
- If one agent fails, entire crew can stop; manual retry logic required
- Hierarchical process produces circular delegation or off-topic tangents
- Memory management basic; long-running crews accumulate context that slows performance
- SSRF and RCE risks flagged in tool configurations (security concern for financial systems)
- Complex crews take minutes per execution -- fine for batch, not real-time
- Less fine-grained control than LangGraph for stateful workflows

**Finance fit:** MEDIUM -- good metaphor for analyst teams, but reliability and security concerns are dealbreakers for production financial systems

**Confidence:** MEDIUM -- widely used for demos/prototypes, fewer production financial deployments

#### OpenAI Agents SDK

**Architecture:** Core abstraction is the "handoff" -- agents transfer control to each other explicitly, carrying conversation context. Each agent defined with instructions, model reference, tools, and handoff targets.

**Strengths:**
- Very lightweight; working multi-agent system in under 20 lines
- Strong voice support (not relevant for finance)
- Clean handoff semantics for agent delegation
- Built-in guardrails and safety rails

**Weaknesses:**
- Optimized for OpenAI models; can configure others but loses advantages
- Less flexible than LangGraph for complex workflows with cycles/branching
- No durable execution or checkpointing
- Relatively new (March 2025); less battle-tested

**Finance fit:** MEDIUM -- clean handoff pattern works for analyst-to-risk-to-portfolio workflows, but model lock-in to GPT is undesirable when Claude models are primary

**Confidence:** MEDIUM

#### Claude Agent SDK (Anthropic)

**Architecture:** Tool-use-first approach where agents are Claude models equipped with tools, including ability to invoke other agents as tools. Central Harness manages agent loop (when to call tools, handle context, recover from errors). Sub-agent orchestration via sequential, concurrent, handoff, and group chat patterns.

**Strengths:**
- Native MCP (Model Context Protocol) integration -- agents discover tools at runtime
- 84% task success benchmark; best error handling of any framework
- Ideal for safety-critical applications (healthcare, finance, legal)
- Deep OS access capability (computer use, file system, terminal)
- First-class MCP server support means connecting to databases, Slack, GitHub without custom tool code
- Claude models are strong at reasoning over long financial documents (200k+ context)

**Weaknesses:**
- Locked to Claude models entirely -- no fallback to GPT/Gemini
- Lighter orchestration compared to LangGraph (no graph-based workflows, no built-in checkpointing)
- v0.1.48 as of March 2026 (pre-1.0; API may shift)
- Multi-agent patterns less mature than LangGraph or even OpenAI Agents SDK
- Originally designed for code agents (Claude Code); financial agent patterns less proven

**Finance fit:** MEDIUM-HIGH -- excellent for individual analyst agents doing deep document analysis with MCP tool integration, but orchestrating a team of agents is where it falls short vs LangGraph

**Confidence:** MEDIUM -- strong model, immature framework

#### Microsoft Agent Framework (Semantic Kernel + AutoGen)

**Architecture:** Combines AutoGen's simple agent abstractions with Semantic Kernel's enterprise features (session-based state management, type safety, middleware, telemetry). Graph-based workflows for multi-agent orchestration.

**Strengths:**
- v1.0 GA just released (April 3, 2026) with long-term support commitment
- Enterprise-grade: telemetry, middleware, session management built in
- .NET and Python support
- Azure integration for teams in Microsoft ecosystem
- Can orchestrate agents across different SDKs (including Claude Agent SDK)

**Weaknesses:**
- Brand new v1.0; limited production track record
- Microsoft ecosystem bias (Azure-optimized)
- Complex migration path from SK or AutoGen 0.2
- Python support historically lagged .NET

**Finance fit:** MEDIUM -- enterprise features are appealing, but no financial domain evidence yet

**Confidence:** LOW-MEDIUM -- just released; insufficient production evidence

#### AutoGen / AG2

**Architecture:** AG2 (community fork) uses event-driven MemoryStream pub/sub bus. Microsoft AutoGen 0.4 is an async event-driven rewrite. Both diverging from AutoGen 0.2's group chat model.

**Strengths:**
- Largest star count (~75k) due to early mover advantage
- Group chat model intuitive for multi-agent debate/discussion

**Weaknesses:**
- Fragmented: Microsoft AutoGen vs AG2 vs original 0.2 -- confusing ecosystem
- Every agent turn in GroupChat is a full LLM call with accumulated history; 4-agent x 5-round debate = 20+ LLM calls minimum
- Extremely expensive for high-volume use cases
- Neither fork is fully production-ready in 2026
- Memory management issues in long conversations

**Finance fit:** LOW-MEDIUM -- debate/discussion model is interesting for thesis critique, but token costs are prohibitive and reliability is insufficient

**Confidence:** MEDIUM (well-documented limitations)

#### Haystack (deepset)

**Architecture:** DAG pipeline with modular components (retrievers, readers, generators, routers). Agent behavior via conditional routing and tool calling within pipelines.

**Strengths:**
- Mature framework (3+ years); battle-tested for RAG and retrieval
- Excellent for document processing, search, and Q&A
- Enterprise support available
- Clean modular design

**Weaknesses:**
- Designed for RAG/retrieval pipelines, not multi-agent orchestration
- DAG structure (no cycles) limits iterative agent reasoning
- Agent features added later; not agent-first design
- Less suited for multi-agent debate/critique patterns

**Finance fit:** MEDIUM -- excellent for the document retrieval/analysis layer (SEC filings, earnings transcripts), but not the right tool for the multi-agent orchestration layer

**Confidence:** HIGH (well-established, clear use case boundaries)

---

## Finance-Specific Frameworks

### TradingAgents (Tauric Research)
- **Built on:** LangGraph
- **Architecture:** 5-phase workflow -- parallel analysis, team discussion, trading decision, risk assessment, fund manager approval
- **Agent roles:** Fundamentals Analyst, Sentiment Analyst, News Analyst, Technical Analyst, Researcher, Trader, Risk Manager
- **LLM support:** Claude 4.x, GPT-5.x, Gemini 3.x, Grok 4.x (multi-provider)
- **Status:** v0.2.0, research-quality (not production-hardened)
- **Relevance to us:** HIGH -- directly validates our architecture of specialized analyst agents with adversarial critique. Demonstrates that LangGraph is the de facto standard for financial multi-agent systems.
- **Limitation:** Research framework, not production-grade. No backtesting integration, no portfolio management, no risk limits enforcement.

### virattt/ai-hedge-fund
- **Built on:** LangGraph
- **Architecture:** 18 specialized agents, 3-stage pipeline (parallel analysts, risk assessment, portfolio decisions)
- **Agent personas:** Modeled after famous investors (Damodaran, Graham, Ackman, Munger, Burry, etc.)
- **Status:** 43k+ stars, educational/research only
- **Relevance to us:** MEDIUM -- demonstrates agent persona patterns and LangGraph integration, but the "famous investor persona" approach is gimmicky. The 3-stage architecture pattern (parallel analysis -> risk -> portfolio) is sound.

### FinRobot (AI4Finance Foundation)
- **Architecture:** 4-layer platform (Financial AI Agents, Financial LLM Algorithms, LLMOps/DataOps, Multi-source LLM Foundation)
- **Focus:** Financial Chain-of-Thought (CoT) for equity research and valuation
- **Academic paper:** arXiv:2405.14767
- **Status:** Academic research platform; not production-ready
- **Relevance to us:** LOW -- academic framework focused on LLM fine-tuning for finance, not on multi-agent orchestration. Interesting for CoT prompting patterns but not as an infrastructure choice.

### HedgeAgents
- **Focus:** Multi-agent hedging across Stocks, Forex, Bitcoin
- **Claims:** 70% annualized return, 400% total return over 3 years
- **Status:** Research paper; no production deployment
- **Relevance to us:** LOW -- interesting as validation of multi-agent approach for portfolio construction, but unverified claims and no open-source implementation to evaluate.

### Assessment

No finance-specific framework is production-ready. The pattern is clear: serious financial multi-agent systems are built on general-purpose frameworks (overwhelmingly LangGraph) with domain-specific agents, tools, and data sources layered on top. Building on a financial-specific framework would mean inheriting research-quality code with no production support.

---

## Build vs Buy Analysis

### The Case for Building from Scratch

**Arguments for:**
- Total control over orchestration logic, error handling, and token budget enforcement
- No framework version churn or breaking changes to track
- No abstraction overhead -- every LLM call is explicit and auditable
- Financial compliance requirements may demand full auditability of decision paths
- Minimal dependency surface (just `anthropic` or `openai` SDK + your code)

**Arguments against:**
- Estimated $600k-$1.5M development cost for a single robust agent; $5M+ for multi-agent system
- Solving infrastructure problems (checkpointing, state management, retry logic, observability) instead of building trading signals
- You will rebuild 70% of what LangGraph already provides, but worse
- Maintenance burden: $350k-$820k annually per agent for custom infrastructure

### The Case for Using a Framework

**Arguments for:**
- LangGraph alone handles: checkpointing, state persistence, human-in-the-loop, parallel execution, streaming, observability integration, error recovery
- Battle-tested by companies processing millions of agent runs
- Community support, tutorials, and patterns for common problems
- Time to first working multi-agent system: weeks vs months

**Arguments against:**
- Framework abstractions can obscure what the LLM is actually doing (debugging black boxes)
- Version churn in a fast-moving ecosystem (LangGraph's API has changed multiple times)
- May not map perfectly to your mental model of how agents should work
- Vendor risk if framework maintainer pivots or abandons project

### The Middle Path -- RECOMMENDED

**Use a framework for orchestration infrastructure, build custom for domain logic.**

Concretely:
1. **LangGraph** for the orchestration layer: graph definition, state management, checkpointing, parallel execution, human-in-the-loop
2. **PydanticAI** (or raw Pydantic models) for individual agent logic: typed inputs/outputs, tool definitions, prompt templates, output validation
3. **Raw Anthropic/OpenAI SDK** for the actual LLM calls when you need full control (prompt caching, streaming, specific API features)
4. **Custom code** for domain logic: signal generation, backtesting integration, risk rules, position sizing

This gives you production-grade infrastructure where it matters (orchestration, state, observability) while keeping full control where it matters most (financial logic, LLM prompting, signal generation).

---

## Claude/Anthropic Native Options

### Using Claude with LangGraph (Recommended Approach)

LangGraph is fully model-agnostic. Claude models integrate via:
- `ChatAnthropic` from `langchain-anthropic` package
- Direct Anthropic SDK calls wrapped in LangGraph tool nodes
- MCP server connections for tool discovery

**Advantages of Claude for financial agents:**
- 200k token context window handles full 10-K filings, earnings transcripts, and multi-document analysis
- Strong structured output via tool use (reliable JSON extraction from financial documents)
- Extended thinking for complex reasoning over financial data
- Prompt caching reduces cost by up to 90% on repeated document analysis

### Claude Agent SDK Directly

Best for: single-agent tasks requiring deep document analysis with MCP tool integration.
NOT best for: multi-agent orchestration, which is our primary need.

If using Claude Agent SDK, it would be as a component: individual analyst agents built with Claude Agent SDK, orchestrated by LangGraph. But this adds complexity without clear benefit over just using Claude models through LangGraph directly.

### MCP (Model Context Protocol) Integration

MCP is framework-agnostic and can be used with LangGraph:
- Database connections (PostgreSQL for market data, signals)
- File system access (cached SEC filings, earnings transcripts)
- API integrations (Bloomberg, SEC EDGAR, news feeds)
- Custom tool servers for proprietary analysis

MCP is valuable regardless of framework choice. Both LangGraph and PydanticAI support MCP tool discovery.

### Cost Control with Claude

For a multi-agent financial system, token costs are a primary concern:

| Strategy | Cost Reduction | Implementation |
|----------|---------------|----------------|
| Prompt caching | Up to 90% on cached inputs | Anthropic API `cache_control` parameter |
| Model routing | 60-87% via task-appropriate models | Haiku for summarization, Sonnet for analysis, Opus for complex reasoning |
| Context compression | Up to 20x input reduction | Summarize long documents before passing to agents |
| Budget caps per trace | Prevents runaway loops | Max token budget per agent turn + max iterations |
| Parallel execution | Latency reduction (not cost) | LangGraph parallel node execution |

Estimated cost profile for a 5-agent analysis pipeline analyzing one equity:
- Naive approach: ~$2-5 per analysis (200k+ tokens across agents)
- Optimized (caching + routing + compression): ~$0.30-0.80 per analysis
- At 500 equities/day: ~$150-400/day optimized vs $1,000-2,500 naive

---

## Recommendation for Our Use Case

### Primary Recommendation: LangGraph + PydanticAI + Claude Models

**Architecture:**

```
                    LangGraph Orchestration Layer
                    (graph, state, checkpoints)
                              |
        +---------+-----------+-----------+---------+
        |         |           |           |         |
   Hypothesis  Evidence   Critique    Signal    Risk
    Agent      Gatherer    Agent     Generator  Manager
   (Claude)   (Claude)   (Claude)   (Claude)   (Claude)
        |         |           |           |         |
   PydanticAI  PydanticAI  PydanticAI  PydanticAI  PydanticAI
   (typed I/O) (typed I/O) (typed I/O) (typed I/O) (typed I/O)
        |         |           |           |         |
      Tools     Tools       Tools      Tools     Tools
   (SEC API)  (yfinance)  (debate)  (backtest) (limits)
```

**Why this combination:**

1. **LangGraph** handles what's hard to build yourself:
   - State machine for the analysis pipeline (hypothesis -> evidence -> critique -> signal -> risk)
   - Checkpoint/resume for long-running analyses
   - Parallel execution of independent analyst agents
   - Human-in-the-loop for high-conviction trade review
   - Observability via LangSmith or Langfuse

2. **PydanticAI** handles what needs to be reliable:
   - Type-safe agent inputs/outputs (market data schemas, signal schemas, position schemas)
   - Dependency injection for data sources (matches existing codebase patterns)
   - Runtime validation of LLM outputs against financial schemas
   - Easy testing via mocked dependencies

3. **Claude models** handle what needs intelligence:
   - Long-context analysis of SEC filings and earnings transcripts
   - Structured reasoning over financial data
   - Adversarial critique between thesis and anti-thesis agents
   - Model routing: Haiku for data extraction, Sonnet for analysis, Opus for complex reasoning

**Why not the alternatives:**

| Alternative | Why Not |
|-------------|---------|
| CrewAI | Reliability issues (crew failures cascade), security concerns, basic memory management -- unacceptable for financial systems |
| OpenAI Agents SDK | Model lock-in to GPT; we want Claude as primary |
| Claude Agent SDK alone | Immature multi-agent orchestration; pre-1.0 API; would need to build graph/state/checkpoint infrastructure ourselves |
| AutoGen/AG2 | Fragmented ecosystem, token-expensive group chat model, neither fork production-ready |
| Microsoft Agent Framework | Just hit v1.0; no track record; enterprise/Azure bias |
| Build from scratch | 6+ months building infrastructure instead of trading signals; LangGraph already solves the hard orchestration problems |
| Finance-specific (TradingAgents, FinRobot) | Research-quality only; no production support; better to use proven general framework with custom financial agents |

### Implementation Phases

**Phase 1: Foundation**
- LangGraph graph definition for the analysis pipeline
- PydanticAI agent definitions with typed schemas for market data, hypotheses, signals
- Claude model integration via langchain-anthropic
- Basic observability with Langfuse (open-source, self-hosted)

**Phase 2: Agent Development**
- Hypothesis Generator agent (Claude Sonnet, SEC filing tools)
- Evidence Gatherer agent (Claude Haiku for extraction, Sonnet for synthesis)
- Critique Agent (Claude Opus for adversarial reasoning)
- Signal Generator (Claude Sonnet, quantitative output validation)
- Risk Manager (Claude Sonnet, position limit enforcement)

**Phase 3: Production Hardening**
- Checkpointing with PostgreSQL (already in stack)
- Token budget enforcement per agent and per pipeline run
- Human-in-the-loop for trades above confidence threshold
- Cost monitoring and model routing optimization
- Backtesting integration with existing framework

### Key Dependencies

```
# Core orchestration
langgraph>=0.3
langchain-anthropic>=0.3
langchain-core>=0.3

# Agent logic
pydantic-ai>=1.0
pydantic>=2.0

# Observability (choose one)
langfuse>=2.0          # Open-source, self-hosted
# OR langsmith         # Paid, best integration with LangGraph

# LLM providers
anthropic>=0.40        # Direct SDK for advanced features (caching, streaming)
```

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| LangGraph as orchestration layer | HIGH | Multiple production deployments in finance (Kensho/S&P, Captide), dominant in open-source financial agent projects |
| PydanticAI for agent logic | MEDIUM-HIGH | Strong design, stable API, but less multi-agent production evidence specifically |
| Claude models for financial reasoning | HIGH | Well-documented strength in long-context document analysis, structured output |
| Token cost estimates | MEDIUM | Based on published benchmarks and pricing; actual costs depend on prompt engineering |
| Finance-specific framework landscape | HIGH | Thoroughly surveyed; clear conclusion that none are production-ready |
| Build vs buy tradeoff | MEDIUM-HIGH | Cost estimates from multiple sources; middle-path recommendation is well-supported |

## Gaps to Address in Phase-Specific Research

- **Prompt engineering patterns** for financial chain-of-thought reasoning (learn from FinRobot's CoT approach)
- **Adversarial debate protocols** -- how to structure thesis/antithesis agent interactions efficiently (minimize token waste)
- **Backtest integration architecture** -- how LangGraph agents feed signals into the existing backtesting framework
- **Model routing rules** -- empirical testing of which financial tasks work with Haiku vs Sonnet vs Opus
- **MCP server design** for proprietary data sources (market data, SEC filings, news feeds)
- **Compliance and auditability** -- how to create decision audit trails from agent traces

## Sources

### Framework Comparisons
- [Best Multi-Agent Frameworks in 2026 (GuruSup)](https://gurusup.com/blog/best-multi-agent-frameworks-2026)
- [CrewAI vs LangGraph vs AutoGen vs OpenAgents (OpenAgents)](https://openagents.org/blog/posts/2026-02-23-open-source-ai-agent-frameworks-compared)
- [OpenAI Agents SDK vs LangGraph vs AutoGen vs CrewAI (Composio)](https://composio.dev/blog/openai-agents-sdk-vs-langgraph-vs-autogen-vs-crewai)
- [2026 AI Agent Framework Decision Guide (DEV Community)](https://dev.to/linou518/the-2026-ai-agent-framework-decision-guide-langgraph-vs-crewai-vs-pydantic-ai-b2h)
- [14 AI Agent Frameworks Compared (Softcery)](https://softcery.com/lab/top-14-ai-agent-frameworks-of-2025-a-founders-guide-to-building-smarter-systems)
- [Comparing Open-Source AI Agent Frameworks (Langfuse)](https://langfuse.com/blog/2025-03-19-ai-agent-comparison)

### Claude / Anthropic
- [Claude Agent SDK Overview (Anthropic)](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Claude Agent SDK MCP Integration (Anthropic)](https://platform.claude.com/docs/en/agent-sdk/mcp)
- [Claude Agents SDK vs OpenAI vs Google ADK (Composio)](https://composio.dev/content/claude-agents-sdk-vs-openai-agents-sdk-vs-google-adk)
- [OpenAI Agents SDK vs Claude Agent SDK (AgentPatch)](https://agentpatch.ai/blog/openai-agents-sdk-vs-claude-agent-sdk/)

### Financial Agent Systems
- [TradingAgents Framework (GitHub)](https://github.com/TauricResearch/TradingAgents)
- [TradingAgents Paper (arXiv)](https://arxiv.org/abs/2412.20138)
- [virattt/ai-hedge-fund (GitHub)](https://github.com/virattt/ai-hedge-fund)
- [FinRobot Platform (GitHub)](https://github.com/AI4Finance-Foundation/FinRobot)
- [FinRobot Paper (arXiv)](https://arxiv.org/abs/2405.14767)
- [HedgeAgents Paper (arXiv)](https://arxiv.org/html/2502.13165v1)
- [Financial Document Processing Benchmarks (arXiv)](https://arxiv.org/html/2603.22651)

### Production & Cost
- [LangGraph Production Guide (Use Apify)](https://use-apify.com/blog/langgraph-agents-production)
- [Kensho/S&P Global LangGraph Case Study (LangChain Blog)](https://blog.langchain.com/tag/case-studies/)
- [Multi-Agent Cost Optimization (APXML)](https://apxml.com/courses/multi-agent-llm-systems-design-implementation/chapter-6-system-evaluation-debugging-tuning/managing-llm-agent-costs)
- [Build vs Buy AI Agents (Insoftex)](https://insoftex.com/build-vs-buy-ai-agents/)

### Framework-Specific
- [LangGraph GitHub](https://github.com/langchain-ai/langgraph)
- [PydanticAI Documentation](https://ai.pydantic.dev/)
- [PydanticAI Type-Safe Framework (DecisionCrafters)](https://www.decisioncrafters.com/pydanticai-type-safe-ai-agent-framework-with-16k-github-stars/)
- [Microsoft Agent Framework v1.0 (Visual Studio Magazine)](https://visualstudiomagazine.com/articles/2026/04/06/microsoft-ships-production-ready-agent-framework-1-0-for-net-and-python.aspx)
- [AutoGen Split (DEV Community)](https://dev.to/maximsaplin/microsoft-autogen-has-split-in-2-wait-3-no-4-parts-2p58)
- [Haystack by deepset](https://haystack.deepset.ai/)

### Observability
- [LangSmith Alternatives for Agent Observability (Latitude)](https://latitude.so/blog/langsmith-alternatives-agent-observability-2026)
- [Best LLM Observability Tools 2026 (Firecrawl)](https://www.firecrawl.dev/blog/best-llm-observability-tools)
