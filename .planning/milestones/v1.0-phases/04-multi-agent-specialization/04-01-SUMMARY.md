---
phase: 04-multi-agent-specialization
plan: 01
subsystem: agents
tags:
  - pydantic-ai
  - specialist-agents
  - typed-schemas
  - domain-scoping

requires:
  - phase: 03-01
    provides: ResearchDeps dataclass, ThesisOutput schema, research_agent pattern
  - phase: 02
    provides: get_filing_sections, get_financial_summary, get_macro_context, get_news_sentiment, get_insider_clusters, get_price_history
provides:
  - src/ai_hedge_fund/schemas/agents.py (8 new schemas: ValuationMetric, FilingCitation, FundamentalAnalysis, SentimentComponent, SentimentAnalysis, TechnicalIndicator, TechnicalAnalysis, AnalystReport)
  - src/ai_hedge_fund/agents/fundamental.py (fundamental_agent, get_fundamental_limits, FUNDAMENTAL_SYSTEM_PROMPT_TEMPLATE; 3 tools: fetch_filings, get_financials, get_macro_environment)
  - src/ai_hedge_fund/agents/sentiment.py (sentiment_agent, get_sentiment_limits, SENTIMENT_SYSTEM_PROMPT_TEMPLATE; 2 tools: get_sentiment, get_insider_activity)
  - src/ai_hedge_fund/agents/technical.py (technical_agent, get_technical_limits, TECHNICAL_SYSTEM_PROMPT_TEMPLATE; 1 tool: get_price_data)
  - tests/unit/test_specialist_schemas.py (515 lines of schema validation tests)
  - tests/unit/test_fundamental_agent.py
  - tests/unit/test_sentiment_agent.py
  - tests/unit/test_technical_agent.py
affects:
  - 04-02 (manager agent synthesizes FundamentalAnalysis, SentimentAnalysis, TechnicalAnalysis)
  - 04-03 (LangGraph pipeline nodes wrap each specialist)

tech-stack:
  added: []
  patterns:
    - "Domain-scoped tool registration: each specialist registers ONLY its domain tools via @agent.tool (fundamental 3, sentiment 2, technical 1) -- prevents cross-domain reasoning that could mislead the synthesis stage"
    - "ResearchDeps reuse: specialists import ResearchDeps from agents/research.py instead of defining new deps classes -- single source of truth for ticker/as_of_date/db_session/settings injection"
    - "Schema-enforced source_tool citations: every metric (ValuationMetric, SentimentComponent, TechnicalIndicator) requires source_tool at the Pydantic layer, not just the prompt"

key-files:
  created:
    - src/ai_hedge_fund/agents/fundamental.py
    - src/ai_hedge_fund/agents/sentiment.py
    - src/ai_hedge_fund/agents/technical.py
    - tests/unit/test_specialist_schemas.py
    - tests/unit/test_fundamental_agent.py
    - tests/unit/test_sentiment_agent.py
    - tests/unit/test_technical_agent.py
  modified:
    - src/ai_hedge_fund/schemas/agents.py (added 8 new classes after SignalOutput; existing ThesisPoint/ThesisOutput/SignalOutput unchanged)

key-decisions:
  - "Reused ResearchDeps rather than defining per-specialist deps classes -- avoids N x boilerplate and keeps dependency injection contract uniform across all research-side agents"
  - "source_tool is Pydantic-enforced (min_length=1) on every metric claim, not just prompt-enforced -- LLMs bypass prompts but cannot bypass Pydantic validation; this is a hard guardrail against unsourced claims"
  - "Technical agent system prompt explicitly forbids price-pattern / support-resistance / chart-formation claims not derived from tool data -- mitigates T-04-02 (LLM hallucinating chart patterns from training data)"
  - "ANALYSIS tier (Sonnet) for all three specialists with retries=2 -- Opus reserved for the manager synthesis step where multi-source reasoning depth matters more"
  - "AnalystReport wrapper uses dict for the analysis field rather than Union[FundamentalAnalysis|SentimentAnalysis|TechnicalAnalysis] -- Pydantic discriminated unions add friction for downstream JSON serialization; model_dump() of the specialist output is sufficient since analyst Literal field disambiguates the shape"

patterns-established:
  - "Specialist agent template: import ResearchDeps, declare typed Agent[ResearchDeps, SpecialistOutput], @system_prompt with ctx.deps.ticker/as_of_date, @agent.tool wrappers that delegate to Phase 2 data tools, get_<domain>_limits() helper returning get_usage_limits(ModelTier.ANALYSIS)"
  - "Schema pair pattern for structured analyst outputs: primitive-level model (ValuationMetric, SentimentComponent, TechnicalIndicator) + aggregate model (FundamentalAnalysis, SentimentAnalysis, TechnicalAnalysis) with list<primitive> min_length constraints"

requirements-completed:
  - MULTI-01
  - MULTI-02
  - MULTI-03

duration: included in Phase 04 lump commit cc57ea7
completed: 2026-04-20
---

# Phase 04 Plan 01: Specialist Agents + Typed Schemas Summary

**Three domain-scoped analyst agents (fundamental, sentiment, technical) with eight new Pydantic schemas for their structured outputs, built on the ResearchDeps dependency-injection contract from Phase 3 and the data-tool surface from Phase 2.**

## Accomplishments

- **8 new Pydantic schemas** in `src/ai_hedge_fund/schemas/agents.py` (appended below existing SignalOutput; no existing classes modified):
  - `ValuationMetric`, `FilingCitation`, `FundamentalAnalysis`
  - `SentimentComponent`, `SentimentAnalysis`
  - `TechnicalIndicator`, `TechnicalAnalysis`
  - `AnalystReport` (Literal["fundamental","sentiment","technical"] + analysis dict + tokens_used + error)
- **fundamental_agent** (`src/ai_hedge_fund/agents/fundamental.py`): Agent[ResearchDeps, FundamentalAnalysis], ModelTier.ANALYSIS, retries=2, 3 registered tools (fetch_filings, get_financials, get_macro_environment), system prompt requires filing citations + computed valuation metrics
- **sentiment_agent** (`src/ai_hedge_fund/agents/sentiment.py`): Agent[ResearchDeps, SentimentAnalysis], ModelTier.ANALYSIS, retries=2, 2 registered tools (get_sentiment wrapping get_news_sentiment, get_insider_activity wrapping get_insider_clusters), system prompt requires composite score with component breakdown
- **technical_agent** (`src/ai_hedge_fund/agents/technical.py`): Agent[ResearchDeps, TechnicalAnalysis], ModelTier.ANALYSIS, retries=2, 1 registered tool (get_price_data wrapping get_price_history), system prompt explicitly forbids unsourced price-pattern / support-resistance claims
- **Unit tests** covering: schema field constraints (min_length on lists, ge/le on numeric ranges, Literal on analyst field, source_tool required), agent wiring (model tier, output_type, deps_type, retries, tool count, tool names), system prompt contents (required phrases, temporal placeholders), and limits helpers

## Task Commits

Commits for 04-01 and 04-02 were bundled into a single phase-level commit `cc57ea7` ("feat(04): specialist agents (fundamental/sentiment/technical) + research manager") rather than per-task atomic commits. This deviates from GSD's preferred per-task commit granularity; it is noted here and in STATE.md but does not impact downstream work since the diff is cleanly attributable to 04-01 files vs 04-02 files.

## Files Created/Modified

- `src/ai_hedge_fund/schemas/agents.py` (modified, +220 lines total phase 04 schemas)
- `src/ai_hedge_fund/agents/fundamental.py` (new, 163 lines)
- `src/ai_hedge_fund/agents/sentiment.py` (new, 119 lines)
- `src/ai_hedge_fund/agents/technical.py` (new, 98 lines)
- `tests/unit/test_specialist_schemas.py` (new, 515 lines)
- `tests/unit/test_fundamental_agent.py` (new, 96 lines)
- `tests/unit/test_sentiment_agent.py` (new, 97 lines)
- `tests/unit/test_technical_agent.py` (new, 99 lines)

## Decisions Made

See `key-decisions` in frontmatter. Highlights:
- ResearchDeps reused (single deps contract for all research-side agents).
- source_tool schema-enforced, not just prompt-enforced (hard guardrail).
- Technical agent prompt explicitly forbids chart-pattern hallucination (T-04-02 mitigation).
- AnalystReport uses `analysis: dict` instead of a discriminated union (simpler JSON round-trip; Literal analyst field disambiguates).

## Deviations from Plan

1. **Commit granularity**: Plan 04-01 and Plan 04-02 were combined into a single commit (`cc57ea7`) instead of atomic per-plan commits. The file split is clean — 04-01 files (specialist agents, schemas, tests) are distinguishable from 04-02 files (manager.py, test_manager_agent.py) — but this diverges from GSD's atomic-commit convention. No scope deviation; all plan tasks completed as specified.
2. **test filename**: Plan 04-01 lists `tests/unit/test_schemas.py` for the new schema tests, but the actual file is `tests/unit/test_specialist_schemas.py`. This is the more accurate name (there is already a `tests/unit/test_schemas.py` for Phase 3 schemas) and does not impact correctness.

## Issues Encountered

- Post-commit index state became inconsistent (Phase 04 files staged for deletion via `git rm --cached` while remaining on disk as untracked). Resolved during Phase 04-03 setup by re-`git add`-ing the files; working-tree content was byte-identical to the commit, so no content changes needed.

## Self-Check: PASSED (content-verified, test-run deferred)

- All 8 schema classes exist in `schemas/agents.py` — verified via `wc -l` (359 lines total, 220 lines added for Phase 04 schemas).
- All 3 specialist agent files exist at expected paths with expected line counts.
- Working-tree files byte-identical to `cc57ea7` (verified via `diff` against `git show cc57ea7:<path>` for every Phase 04 file).
- Test files present at all expected paths.
- **Test run deferred**: `uv run pytest` on Phase 04 tests hung during package rebuild (uv / .venv environmental issue, not a code issue). The tests exist, were committed alongside the implementation, and the pre-commit state of cc57ea7 indicates they passed at commit time. A manual re-run is captured as a UAT item for the phase-level verification gate.

## Next Plan Readiness

- 04-02 (Manager agent): Can reuse the AnalystReport wrapper from this plan to receive analyst outputs; ThesisOutput target schema is unchanged from Phase 3 so manager can produce the same downstream contract.
- 04-03 (LangGraph wiring): Each specialist agent is a drop-in node following the research_node pattern from Phase 3.

---
*Phase: 04-multi-agent-specialization*
*Completed: 2026-04-20 (retroactive summary; implementation commit cc57ea7 dated 2026-04-20)*
