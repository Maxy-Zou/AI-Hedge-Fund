# Phase 3: Single-Agent Research - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

A single research agent that reads SEC filings via the Phase 2 data tools, uses tool-augmented calculations for all financial metrics, and produces a structured investment thesis with quantitative signal. This proves the core research loop works end-to-end before adding multi-agent complexity in Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints from PROJECT.md and CLAUDE.md:
- Tool-first for quantitative work — LLMs NEVER compute financial ratios, run backtests, or calculate position sizes directly
- Strict temporal controls — every data input timestamped, RAG filtered by "available as of analysis date"
- Thesis output must include: bull case (3+ points with filing citations), bear case (3+ citations), confidence score (0-100), risk factors
- Signal output must include: direction (long/short/neutral), conviction level, time horizon, position size suggestion
- All fields validated against Pydantic schemas with no missing values
- Token budgets enforced per agent via PydanticAI UsageLimits (from Phase 1)
- Langfuse trace must show tool invocations for every financial metric
- PydanticAI agents with typed I/O and dependency injection (from Phase 1)
- Data tools from Phase 2: get_filing_sections, get_financial_summary, get_price_history, get_insider_clusters, get_news_sentiment, get_macro_context

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Architecture
- `CLAUDE.md` — Agent development rules, tool-first principle, debate protocol, data handling
- `.planning/PROJECT.md` — Core value, constraints, honest positioning
- `.planning/REQUIREMENTS.md` — AGENT-01 through AGENT-04 acceptance criteria
- `.planning/ROADMAP.md` — Phase 3 success criteria (4 verifiable conditions)

### Phase 1 Foundation (Agent Infrastructure)
- `src/ai_hedge_fund/agents/base.py` — Agent factory, UsageLimits, PipelineBudgetTracker
- `src/ai_hedge_fund/agents/extraction.py` — Extraction agent pattern (Haiku)
- `src/ai_hedge_fund/agents/analysis.py` — Analysis agent pattern (Sonnet)
- `src/ai_hedge_fund/schemas/agents.py` — ExtractionOutput, AnalysisOutput, ThesisOutput, SignalOutput schemas
- `src/ai_hedge_fund/schemas/state.py` — PipelineState TypedDict
- `src/ai_hedge_fund/models.py` — ModelTier enum, model routing
- `src/ai_hedge_fund/graph/pipeline.py` — LangGraph pipeline pattern
- `src/ai_hedge_fund/graph/nodes.py` — Graph node pattern wrapping PydanticAI agents

### Phase 2 Data Tools (Agent will call these)
- `src/ai_hedge_fund/data/tools/filing_tools.py` — get_filing_sections (SEC EDGAR)
- `src/ai_hedge_fund/data/tools/financial_tools.py` — get_financial_summary (XBRL)
- `src/ai_hedge_fund/data/tools/price_tools.py` — get_price_history
- `src/ai_hedge_fund/data/tools/insider_tools.py` — get_insider_clusters
- `src/ai_hedge_fund/data/tools/sentiment_tools.py` — get_news_sentiment
- `src/ai_hedge_fund/data/tools/macro_tools.py` — get_macro_context
- `src/ai_hedge_fund/data/temporal.py` — enforce_as_of_date decorator

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Agent factory in agents/base.py — create_agent() with model tier routing
- ThesisOutput and SignalOutput Pydantic schemas already defined in schemas/agents.py
- LangGraph pipeline builder in graph/pipeline.py
- All 6 data tools ready for agent consumption with NL summaries

### Established Patterns
- PydanticAI agents with typed output schemas and dependency injection
- LangGraph nodes wrapping agent.run() with UsageLimits
- Graph state as TypedDict (PipelineState)
- Langfuse tracing via CallbackHandler

### Integration Points
- Research agent will use data tools as PydanticAI tool functions
- Output schemas (ThesisOutput, SignalOutput) already exist — extend or reuse
- Pipeline will extend the existing LangGraph graph with research nodes
- All data tools enforce as_of_date — agent must pass it through

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase, no discussion occurred.

</deferred>

---

*Phase: 03-single-agent-research*
*Context gathered: 2026-04-12 via autonomous mode (infrastructure skip)*
