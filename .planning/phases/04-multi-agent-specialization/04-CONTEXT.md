# Phase 4: Multi-Agent Specialization - Context

**Gathered:** 2026-04-20
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Three specialized analyst agents (Fundamental, Sentiment, Technical/Quant) each contribute domain-specific analysis, and a Research Manager synthesizes their outputs into a unified thesis with explicit conflict resolution. Replaces the single generalist research agent from Phase 3 with a team of specialists.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints from PROJECT.md and CLAUDE.md:
- Manager-Analyst Hierarchy pattern (validated by FinCon NeurIPS 2024, TradingAgents, AlphaAgents/BlackRock)
- Fundamental Analyst: SEC filing RAG + XBRL financial data, valuation metrics — cites specific filing sections
- Sentiment Analyst: news sentiment + insider trading activity + (where available) earnings call tone — composite sentiment score with component breakdown
- Technical/Quant Analyst: momentum, volatility indicators via computed tools — no LLM price pattern descriptions without tool backing
- Research Manager: receives all 3 reports, produces unified thesis with agreement/conflict identification and resolution
- Tool-first principle continues — LLMs orchestrate tools, never compute financial metrics directly
- PydanticAI agents with typed I/O (Phase 1 pattern), data tools from Phase 2
- Dual-model routing: analysts on Sonnet, manager potentially on Opus for complex synthesis
- Token budgets enforced per agent

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Architecture
- `CLAUDE.md` — Agent development rules, debate protocol, data handling
- `.planning/REQUIREMENTS.md` — MULTI-01 through MULTI-04
- `.planning/ROADMAP.md` — Phase 4 success criteria

### Phase 3 (Pattern to Extend)
- `src/ai_hedge_fund/agents/research.py` — ResearchDeps, research_agent pattern, tool wrappers
- `src/ai_hedge_fund/agents/signal.py` — signal_agent pattern (no tools, typed output)
- `src/ai_hedge_fund/schemas/agents.py` — ThesisOutput, ThesisPoint, SignalOutput
- `src/ai_hedge_fund/schemas/state.py` — ResearchPipelineState
- `src/ai_hedge_fund/graph/nodes.py` — research_node, signal_node pattern
- `src/ai_hedge_fund/graph/pipeline.py` — build_research_pipeline

### Phase 2 Data Tools (Agents will call these)
- `src/ai_hedge_fund/data/tools/` — All 6 data tools

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- ResearchDeps pattern from Phase 3 — reuse for all specialist agents (ticker/as_of_date DI)
- ThesisOutput/ThesisPoint schema — extend or reuse for analyst reports
- Agent factory create_agent() — use for all 4 new agents
- All 6 data tools ready for specialist agent consumption

### Established Patterns
- PydanticAI tool wrappers (thin functions calling data tools with ResearchDeps context)
- LangGraph parallel node execution for independent analysts
- Graph state as TypedDict with typed intermediate outputs

### Integration Points
- Specialist agents replace/extend the single research_agent from Phase 3
- Manager agent consumes analyst outputs and produces ThesisOutput (same schema)
- Pipeline feeds into existing signal_node from Phase 3

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>

---

*Phase: 04-multi-agent-specialization*
*Context gathered: 2026-04-20 via autonomous mode (infrastructure skip)*
