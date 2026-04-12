---
phase: 03-single-agent-research
plan: 01
subsystem: agent-logic
tags:
  - pydantic-ai
  - tool-augmentation
  - dependency-injection
  - schema-validation
  - thesis
  - research-agent

requires:
  - phase: 01-agent-infrastructure
    provides: create_agent factory, ModelTier routing, UsageLimits, existing ThesisOutput schema
  - phase: 02-data-tools
    provides: get_filing_sections, get_financial_summary, get_price_history, get_insider_clusters, get_news_sentiment, get_macro_context (all @enforce_as_of_date)
provides:
  - ThesisPoint sub-model enforcing non-empty claim/evidence/source_tool citations
  - Tightened ThesisOutput (list[ThesisPoint] min_length=3 for bull/bear, min_length=2 for risk_factors)
  - ResearchDeps frozen dataclass carrying ticker/as_of_date pipeline context
  - research_agent Agent[ResearchDeps, ThesisOutput] with dynamic system prompt
  - 6 registered tool wrappers delegating to Phase 2 data tools
  - get_research_limits helper returning ANALYSIS-tier UsageLimits
affects:
  - 03-02 (research node + LangGraph pipeline integration will consume research_agent)
  - 03-03 (observability/verification leverages registered tool names)
  - 04-multi-agent-specialization (bull/bear agents will follow the ResearchDeps DI pattern)

tech-stack:
  added: []
  patterns:
    - PydanticAI RunContext[ResearchDeps] dependency injection for agent tools
    - Dynamic system prompt via @agent.system_prompt decorator (injects ticker/as_of_date)
    - ThesisPoint citation sub-model enforcing tool-first principle at schema boundary
    - Thin tool-wrapper pattern: @agent.tool functions delegating to Phase 2 data tools while hiding infrastructure params from the LLM

key-files:
  created:
    - src/ai_hedge_fund/agents/research.py
    - tests/unit/test_research_agent.py
  modified:
    - src/ai_hedge_fund/schemas/agents.py
    - src/ai_hedge_fund/schemas/__init__.py
    - src/ai_hedge_fund/agents/__init__.py
    - tests/unit/test_schemas.py

key-decisions:
  - Modified ThesisOutput in place (not a new schema) since prior version was a placeholder and no consumers yet
  - Used dynamic @research_agent.system_prompt decorator to inject as_of_date/ticker per-run (not static prompt)
  - Tool wrappers return summary_text only (not raw data dicts) to stay within ANALYSIS budget (T-03-04)
  - ThesisPoint.source_tool required as explicit schema field (makes the tool-first rule auditable, not only prompt-enforced)
  - retries=2 on research_agent to recover from output schema validation failures without user intervention

patterns-established:
  - "ResearchDeps DI pattern: frozen dataclass + PydanticAI RunContext for injecting pipeline context"
  - "Tool wrapper thin-layer pattern: LLM controls selection and optional lookback params, deps control ticker/as_of_date/session"
  - "Dynamic system prompt via @agent.system_prompt decorator for per-run context injection"
  - "Citation-schema pattern: ThesisPoint forces source_tool attribution, making tool-first principle schema-enforced not only prompt-enforced"

requirements-completed:
  - AGENT-01
  - AGENT-02
  - AGENT-03

duration: 6min
completed: 2026-04-12
---

# Phase 03 Plan 01: Research agent foundation Summary

**Tool-augmented research agent on Claude Sonnet: 6 Phase-2 data tools wired via PydanticAI RunContext DI, ThesisPoint-cited ThesisOutput enforcing 3+ bull/bear points + 2+ risks, dynamic system prompt injecting ticker/as_of_date to prevent temporal leakage.**

## Performance

- **Duration:** 6 min (341 s)
- **Started:** 2026-04-12T17:40:20Z
- **Completed:** 2026-04-12T17:46:01Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments

- Added `ThesisPoint` sub-model with non-empty `claim`/`evidence`/`source_tool` fields — every thesis point now carries an explicit tool citation, enforcing the tool-first principle at the schema boundary (AGENT-03).
- Tightened `ThesisOutput` to `list[ThesisPoint]` with `min_length=3` for bull/bear cases and `min_length=2` for `risk_factors`, matching the AGENT-03 acceptance criteria for structured investment theses.
- Created `ResearchDeps` frozen dataclass that carries `ticker`, `as_of_date`, optional `db_session`, and optional `settings` through the agent's `RunContext`.
- Built `research_agent: Agent[ResearchDeps, ThesisOutput]` on `ModelTier.ANALYSIS` with `retries=2`, a dynamic system prompt that injects per-run ticker and `as_of_date`, and 6 registered tool wrappers (`fetch_filings`, `get_financials`, `get_price_data`, `get_insider_activity`, `get_sentiment`, `get_macro_environment`).
- Added `get_research_limits()` helper returning Sonnet-tier `UsageLimits` (50K input / 8K output / 58K total) for callers that invoke `research_agent.run`.
- 41 new unit tests covering `ThesisPoint` constraints, tightened `ThesisOutput`, `ResearchDeps` immutability, tool registration, and usage limits. Full unit suite: 253 passed, 0 regressions.

## Task Commits

Each task was executed test-first (RED) and then implemented (GREEN):

1. **Task 1 RED (schema tests)** — `14ef4dc` (test)
2. **Task 1 GREEN (schema impl)** — `ba67453` (feat)
3. **Task 2 RED (research agent tests)** — `bb2e2e5` (test)
4. **Task 2 GREEN (research agent impl)** — `ae5ad7f` (feat)

## Files Created/Modified

- `src/ai_hedge_fund/schemas/agents.py` — Added `ThesisPoint` sub-model; replaced `list[str]` fields in `ThesisOutput` with `list[ThesisPoint]` (min_length=3) and raised `risk_factors` min_length to 2.
- `src/ai_hedge_fund/schemas/__init__.py` — Re-export `ThesisPoint`.
- `src/ai_hedge_fund/agents/research.py` — New module: `ResearchDeps` dataclass, `research_agent`, dynamic system prompt, 6 `@research_agent.tool` wrappers, `get_research_limits()`, `_format_filings_for_llm()` helper.
- `src/ai_hedge_fund/agents/__init__.py` — Re-export `ResearchDeps`, `research_agent`, `get_research_limits`.
- `tests/unit/test_schemas.py` — Rewrote `TestThesisOutput` for new constraints, added `TestThesisPoint`, added new tests for min_length=3 / min_length=2 rejections.
- `tests/unit/test_research_agent.py` — New test module covering `ResearchDeps` (frozen / defaults / required fields), `research_agent` (instance / model / output_type / retries / 6 tools / tool names), `RESEARCH_SYSTEM_PROMPT_TEMPLATE` (forbids numbers, injects date, references required tools), `get_research_limits` (ANALYSIS-tier defaults).

## Decisions Made

- **Modify `ThesisOutput` in place** rather than create a separate schema — original was a placeholder with no non-test consumers, so rewriting it avoids a parallel type hierarchy.
- **Dynamic system prompt via `@research_agent.system_prompt`** — PydanticAI's idiomatic pattern for per-run context injection. Chose this over a static prompt with post-hoc `.format()` so the `as_of_date` comes from pipeline state (via `ctx.deps`) rather than caller formatting discipline.
- **Tool wrappers return summary text only** — `get_price_data` drops the 252-row `prices` list and returns `summary_text + stats`; all other tools return `result["summary_text"]`. Keeps input-token consumption predictable and bounded (T-03-04 DoS mitigation).
- **`ThesisPoint.source_tool` as an explicit schema field** — makes the tool-first rule schema-enforced (not only prompt-enforced). Schema validation rejects thesis points that do not name a source tool, which is auditable in the stored `model_dump()` output.
- **`retries=2`** on `research_agent` — PydanticAI retries on output schema validation failures, which is cheap (retries only regenerate the final output, not tool calls). Prevents transient Pydantic validation failures from bubbling up as pipeline errors.
- **Macro tool has no ticker** — `get_macro_environment` calls `get_macro_context` with only `as_of_date`; macro data is market-wide by design.

## Deviations from Plan

Two trivial ruff line-length adjustments during Task 2 GREEN. Neither is a deviation in the Rules 1–4 sense (no new behavior, no new dependencies, no architectural change), but recording for completeness:

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Ruff E501 on system-prompt string literals**

- **Found during:** Task 2 (after initial implementation)
- **Issue:** `RESEARCH_SYSTEM_PROMPT_TEMPLATE` as a triple-quoted string pushed three lines past the project's 100-char limit, failing `ruff check`.
- **Fix:** Switched from a triple-quoted string to implicit string concatenation, splitting long sentences on word boundaries. Semantics preserved exactly.
- **Files modified:** `src/ai_hedge_fund/agents/research.py`
- **Verification:** `ruff check` clean; 41 research/schema tests still pass.
- **Committed in:** `ae5ad7f` (part of Task 2 GREEN)

---

**Total deviations:** 1 auto-fixed (1 blocking) — lint-only.
**Impact on plan:** None. Plan executed as written; only a cosmetic adjustment to satisfy the project's ruff line-length rule.

## Issues Encountered

- None. TDD RED/GREEN cycles ran cleanly for both tasks with no test-impl mismatch.

## Self-Check: PASSED

**Files verified present:**
- `src/ai_hedge_fund/schemas/agents.py` — FOUND (contains `class ThesisPoint`, two `min_length=3` fields, one `min_length=2` field)
- `src/ai_hedge_fund/agents/research.py` — FOUND (contains `class ResearchDeps`, `frozen=True`, 6 `@research_agent.tool` decorators, "NEVER state a financial figure" rule)
- `tests/unit/test_schemas.py` — FOUND (27 tests total, includes `TestThesisPoint`)
- `tests/unit/test_research_agent.py` — FOUND (14 tests total)

**Commits verified present:**
- `14ef4dc` — test(03-01): failing tests for ThesisPoint
- `ba67453` — feat(03-01): ThesisPoint + tightened ThesisOutput
- `bb2e2e5` — test(03-01): failing tests for research agent
- `ae5ad7f` — feat(03-01): research agent with 6 tool wrappers

**Test suite status:** 253 unit tests pass, 0 failures, 0 regressions. Ruff clean on all modified files.

## Next Plan Readiness

- `research_agent` is ready to be wrapped as a LangGraph node in Plan 03-02 (research node + signal node integration). Node code will pass `ResearchDeps(ticker=state["ticker"], as_of_date=...)` and call `research_agent.run(prompt, deps=deps, usage_limits=get_research_limits())`.
- All 6 tool wrappers delegate to the existing Phase-2 data tools — no further data-layer work needed before pipeline assembly.
- Schema constraints are strict enough that a malformed thesis output will fail `ThesisOutput` validation and trigger the agent's `retries=2`. If future runs show repeated validation failures, consider raising retries to 3 or extending the system prompt with a few-shot example.
- Token budget: ANALYSIS tier is 50K input / 8K output / 58K total. 6 NL summaries returning ~500-2K tokens each should fit. Monitor via Langfuse once Plan 03-02 wires the pipeline; tighten per-tool summary length if budget pressure appears.

---
*Phase: 03-single-agent-research*
*Completed: 2026-04-12*
