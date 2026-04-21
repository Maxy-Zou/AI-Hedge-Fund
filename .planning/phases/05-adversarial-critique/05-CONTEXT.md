# Phase 5: Adversarial Critique — Context

**Gathered:** 2026-04-21
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Every thesis produced by the multi-agent research pipeline (Phase 4) is stress-tested through a structured bull/bear debate before becoming a signal — so the system's output reflects adversarial scrutiny, not confirmation bias. The debate follows the 5-act protocol (initial thesis → counter-thesis → rebuttal → final arguments → synthesis) and ends with a revised thesis that includes a thesis quality score.

**Success Criteria (from ROADMAP):**
1. The Bull Advocate constructs a positive investment case using evidence from analyst reports — its arguments reference specific data points (not vague assertions) and each claim cites its source analyst.
2. The Bear Advocate constructs a negative investment case with counter-evidence — it directly addresses and rebuts at least 2 specific bull claims rather than presenting an independent negative thesis.
3. The debate follows the 5-act protocol with each act producing a structured output — skipping an act or producing an empty act causes a validation error.
4. The final synthesis includes a thesis quality score based on evidence strength, logical consistency, and risk coverage — and the post-debate confidence score differs from the pre-debate score in at least 30% of runs (demonstrating the debate actually changes the assessment).

**Requirements covered:** DEBATE-01, DEBATE-02, DEBATE-03, DEBATE-04.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — discuss phase was skipped per `workflow.skip_discuss=true`. Planner should use:

- ROADMAP phase 5 goal, success criteria, and 4 DEBATE-XX requirement definitions as the spec.
- Phase 4 patterns (specialist agent template, MultiAgentPipelineState with operator.add reducer, fan-out/fan-in topology, error-propagation-not-crash) as the architectural baseline to extend.
- Existing codebase conventions (ResearchDeps dep injection, get_<domain>_limits pattern, schema-enforced source_tool, thin node wrappers).
- The CLAUDE.md agent-development rules (tool-first for quant, structured debate only — no free-form chat, token budgets from day one).

### Architecturally likely choices (planner should validate)

- Bull and Bear are PydanticAI Agent[None, ActOutput] agents with zero tools — they read analyst reports + prior-act outputs from state, not from external tools. Debate is pure synthesis, like manager.
- Debate uses REASONING tier (Opus) — bull/bear argument quality is the highest-reasoning step after manager synthesis. Matches the justification already used for manager in 04-02.
- Each act produces its own Pydantic schema with min_length constraints on claims/rebuttals/risks — so missing content causes a validation error, satisfying success criterion 3.
- The 5-act flow is sequential (not parallel) because each act reads the previous act's output. This is a different graph shape from Phase 4's fan-out/fan-in.
- The new state extends MultiAgentPipelineState with debate-specific fields: `bull_case`, `bear_case`, `rebuttals`, `final_arguments`, `debate_synthesis`, each Annotated with a reducer that preserves history (likely `operator.add` on a list[dict] if each act writes append-only).

</decisions>

<code_context>
## Existing Code Insights

**Phase 4 is the direct predecessor — study its patterns first.**

Key files the planner should read before producing the plan:

- `src/ai_hedge_fund/agents/manager.py` — zero-tools synthesis agent pattern; REASONING tier justification; system prompt that forbids unsupported claims; format_analyst_reports helper signature.
- `src/ai_hedge_fund/agents/signal.py` — simplest no-tools agent pattern (single input → single typed output); signal_agent decorator layout.
- `src/ai_hedge_fund/graph/nodes.py` — all 5 Phase-4 node patterns (fundamental_node, sentiment_node, technical_node, manager_node, multi_agent_signal_node); error-propagation idiom; async agent.run invocation with usage_limits.
- `src/ai_hedge_fund/graph/pipeline.py` — build_multi_agent_pipeline showing fan-out/fan-in topology with operator.add reducer.
- `src/ai_hedge_fund/schemas/state.py` — MultiAgentPipelineState TypedDict with Annotated reducer pattern; this is what Phase 5 state should extend or compose with.
- `src/ai_hedge_fund/schemas/agents.py` — all existing Pydantic schemas (ThesisOutput is the manager's output and the natural input to bull/bear); FundamentalAnalysis/SentimentAnalysis/TechnicalAnalysis shapes that bull/bear will cite.
- `tests/unit/test_multi_agent_nodes.py` and `tests/integration/test_multi_agent_pipeline.py` — patterns for unit-testing node wiring and integration-testing compiled graphs with TestModel.

**Reusable primitives:**
- `ModelTier.REASONING.value` → Opus, already justified and used by manager.
- `get_usage_limits(ModelTier.REASONING)` → per-agent token budget.
- `format_analyst_reports(reports)` → bull/bear likely need an analogous helper that formats prior debate acts for downstream prompts.
- `operator.add` reducer on `Annotated[list[dict], operator.add]` → works for acts that append (rebuttals, final arguments) but probably NOT for the single-act outputs (bull_case, bear_case) which are overwrite semantics.

**Anti-patterns to avoid (from CLAUDE.md and Phase 4 learnings):**
- Do NOT give bull/bear agents tools — they must debate from analyst evidence already in state, not re-fetch data.
- Do NOT produce free-form debate text — every act output must be a Pydantic schema with min_length constraints on the substantive fields.
- Do NOT couple debate state onto the existing ResearchPipelineState — create a separate DebatePipelineState or extend MultiAgentPipelineState with debate-specific optional fields.
- Do NOT rewrite Phase 4 code — this phase adds new agents/nodes/state; existing research → manager → signal flow stays intact.

</code_context>

<specifics>
## Specific Ideas

### Likely plan decomposition (planner to finalize)

**Plan 05-01:** Bull/Bear agent schemas + Bull Advocate + Bear Advocate agents.
- New Pydantic schemas: BullCase, BearCase, RebuttalAct, FinalArgument, DebateSynthesis (with quality_score). Each with min_length constraints on substantive fields.
- bull_agent: Agent[None, BullCase], REASONING tier, zero tools, retries=2, system prompt requires source_analyst citation on every claim.
- bear_agent: Agent[None, BearCase], REASONING tier, zero tools, retries=2, system prompt requires that at least 2 bull-case claims are addressed by name.

**Plan 05-02:** Debate orchestration — 5-act flow with rebuttal/final/synthesis agents + debate state.
- DebatePipelineState TypedDict extending MultiAgentPipelineState (or standalone with a thesis input field).
- rebuttal_agent, final_arguments_agent, debate_synthesis_agent — all REASONING tier, zero tools, sequential read of prior-act state.
- quality_score calculation: likely a tool or deterministic scoring function (per CLAUDE.md: "Tool-first for quantitative work. LLMs NEVER compute financial ratios, run backtests, or calculate position sizes directly."). Synthesis agent inputs evidence strength + logical consistency + risk coverage scores; deterministic weighted sum produces quality_score.

**Plan 05-03:** LangGraph wiring — 5 debate nodes + build_debate_pipeline + integration tests.
- Sequential topology: manager_output → bull → bear → rebuttal → final → synthesis → END (or returns to signal node).
- Each node is a thin async wrapper following the Phase 4 node pattern.
- Integration tests with TestModel: verify all 5 acts execute in order, each produces valid schema output, skipped act raises validation error.
- Success criterion 4 check: test that post-debate confidence differs from pre-debate in at least 30% of TestModel-seeded runs (could be relaxed to "differs in at least 1 of 3 runs" for unit-test determinism, with the real 30%-of-runs check captured as a phase UAT item).

### Testing strategy (inherit from Phase 4)

- Unit tests for each schema (field constraints, min_length enforcement).
- Unit tests for each agent (wiring: model tier, output_type, retries, zero-tool count, system prompt contents).
- Unit tests for each debate node (async contract, happy path, error propagation).
- Integration tests for the compiled debate pipeline with TestModel (call_tools=[] everywhere — even though bull/bear have zero tools, TestModel's default behavior is safe here).
- Real-LLM tests deferred to phase UAT (4 agent runs per debate = significant cost).

</specifics>

<deferred>
## Deferred Ideas

- Multi-round debate (more than 1 rebuttal exchange): out of scope for v1. Single rebuttal act is sufficient for the "differs in 30% of runs" success criterion.
- Dynamic debate depth (stop early when agents converge): out of scope. Static 5-act flow per success criterion 3.
- Human-in-the-loop debate review: reserved for Phase 8 (Signal and Output) which is where human approval gates live.
- Jury / third-party judge agent: not needed — success criterion 4 is a quality_score, not a win/lose judgment.

</deferred>
