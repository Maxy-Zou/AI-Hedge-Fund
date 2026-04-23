---
phase: 05-adversarial-critique
plan: 02
subsystem: adversarial-critique
tags: [phase-05, debate, rebuttal, final-arguments, debate-synthesis, quality-score, debate-state, tdd]
requires:
  - ai_hedge_fund.schemas.debate.RebuttalAct
  - ai_hedge_fund.schemas.debate.FinalArguments
  - ai_hedge_fund.schemas.debate.DebateSynthesis
  - ai_hedge_fund.schemas.agents.ThesisOutput
  - ai_hedge_fund.schemas.state.MultiAgentPipelineState
  - ai_hedge_fund.agents.base.get_usage_limits
  - ai_hedge_fund.agents.manager.manager_agent
  - ai_hedge_fund.models.ModelTier
provides:
  - ai_hedge_fund.agents.rebuttal.rebuttal_agent
  - ai_hedge_fund.agents.rebuttal.REBUTTAL_SYSTEM_PROMPT
  - ai_hedge_fund.agents.rebuttal.get_rebuttal_limits
  - ai_hedge_fund.agents.rebuttal.format_debate_for_rebuttal
  - ai_hedge_fund.agents.final_arguments.final_arguments_agent
  - ai_hedge_fund.agents.final_arguments.FINAL_ARGUMENTS_SYSTEM_PROMPT
  - ai_hedge_fund.agents.final_arguments.get_final_arguments_limits
  - ai_hedge_fund.agents.final_arguments.format_debate_for_final
  - ai_hedge_fund.agents.debate_synthesis.debate_synthesis_agent
  - ai_hedge_fund.agents.debate_synthesis.DEBATE_SYNTHESIS_SYSTEM_PROMPT
  - ai_hedge_fund.agents.debate_synthesis.get_debate_synthesis_limits
  - ai_hedge_fund.agents.debate_synthesis.format_debate_for_synthesis
  - ai_hedge_fund.agents.debate_synthesis.compute_quality_score
  - ai_hedge_fund.agents.debate_synthesis.EVIDENCE_WEIGHT
  - ai_hedge_fund.agents.debate_synthesis.LOGIC_WEIGHT
  - ai_hedge_fund.agents.debate_synthesis.RISK_WEIGHT
  - ai_hedge_fund.schemas.state.DebatePipelineState
affects:
  - src/ai_hedge_fund/agents/__init__.py
  - src/ai_hedge_fund/schemas/__init__.py
tech-stack:
  added: []
  patterns:
    - "Zero-tools REASONING-tier Agent[None, <ActSchema>] clones of manager/bull/bear (retries=2)"
    - "output_override=8_000 on rebuttal + final_arguments per RESEARCH.md Pitfall 6 (cost guardrail)"
    - "Default REASONING cap (no override) on debate_synthesis -- synthesis emits full ThesisOutput + 3 sub-scores + notes"
    - "Pure-function weighted mean (compute_quality_score) as the DEBATE-04 tool-first enforcement -- CLAUDE.md: LLMs never compute financial ratios"
    - "Module-level weight constants (EVIDENCE_WEIGHT=0.4, LOGIC_WEIGHT=0.3, RISK_WEIGHT=0.3) for testability + auditability (RESEARCH.md A1)"
    - "TypedDict field duplication instead of multi-inheritance for DebatePipelineState (RESEARCH.md Pattern 5)"
    - "Single-writer semantics on debate-act fields (NO operator.add reducer) -- contract-tested via typing.get_args"
    - "TDD RED/GREEN per task: failing-test commit precedes implementation commit"
key-files:
  created:
    - src/ai_hedge_fund/agents/rebuttal.py
    - src/ai_hedge_fund/agents/final_arguments.py
    - src/ai_hedge_fund/agents/debate_synthesis.py
    - tests/unit/test_rebuttal_agent.py
    - tests/unit/test_final_arguments_agent.py
    - tests/unit/test_debate_synthesis_agent.py
    - tests/unit/test_quality_score.py
    - tests/unit/test_debate_state.py
  modified:
    - src/ai_hedge_fund/schemas/state.py
    - src/ai_hedge_fund/schemas/__init__.py
    - src/ai_hedge_fund/agents/__init__.py
decisions:
  - "Quality-score weights locked to 0.4/0.3/0.3 as module-level constants EVIDENCE_WEIGHT/LOGIC_WEIGHT/RISK_WEIGHT per RESEARCH.md A1 (resolved Open Question 1)."
  - "compute_quality_score is a pure Python function that raises ValueError for any sub-score outside [0,100] -- the DEBATE-04 tool-first enforcement site per CLAUDE.md's 'LLMs NEVER compute financial ratios' rule."
  - "rebuttal_agent + final_arguments_agent use output_override=8_000 (Pitfall-6 cost guardrail); debate_synthesis_agent uses the DEFAULT REASONING output cap (16k) because it emits a full ThesisOutput + 3 sub-scores + synthesis_notes. TestDebateSynthesisLimits::test_uses_default_reasoning_cap checks BOTH total_tokens_limit AND output_tokens_limit to defend against a future refactor accidentally applying output_override to synthesis."
  - "DebatePipelineState duplicates MultiAgentPipelineState fields rather than inheriting -- TypedDict multi-inheritance with Annotated reducers is fragile (RESEARCH.md Pattern 5). analyst_reports keeps operator.add; the 5 debate fields carry no reducer (single-writer overwrite semantics enforced by TestDebatePipelineStateReducers::test_debate_fields_have_no_reducer)."
  - "DEBATE_SYNTHESIS_SYSTEM_PROMPT explicitly requires re-evaluating post_debate_confidence FROM SCRATCH and documents that pre_debate_confidence + quality_score will be overwritten by the pipeline -- Pitfall-3 mitigation (stops LLM from defaulting post to pre, and stops LLM from fighting the pipeline over the two overwritten fields)."
  - "TDD RED/GREEN committed per task (6 commits: 3 test-first + 3 implementation). Verifies every test pre-dates its implementation and genuinely fails first."
metrics:
  duration: 8m
  completed: 2026-04-22T00:35:18Z
---

# Phase 05 Plan 02: Rebuttal, Final Arguments, Debate Synthesis + Quality Score + State Summary

Landed the remaining three debate agents (Rebuttal, Final Arguments, Debate Synthesis), the deterministic `compute_quality_score` helper that enforces DEBATE-04's tool-first scoring, and the `DebatePipelineState` TypedDict that Plan 05-03's pipeline builder will consume. After this plan, every agent and state primitive needed to wire the full 5-act debate graph is in place.

## What Was Built

**1. Rebuttal agent (`src/ai_hedge_fund/agents/rebuttal.py`)** -- Act 3 of the 5-act debate:

- `rebuttal_agent: Agent[None, RebuttalAct]` at `ModelTier.REASONING.value`, `retries=2`, zero tools.
- `REBUTTAL_SYSTEM_PROMPT` -- enforces the symmetric "at least 2 per side" requirement (DEBATE-03 Act 3), names `bull_rebuttals`/`bear_rebuttals`/`source_analyst`/`targets_claim`, caps at 3 rebuttals per side (brevity per Pitfall 6).
- `get_rebuttal_limits()` -- REASONING tier with `output_override=8_000` per Pitfall 6 cost guardrail.
- `format_debate_for_rebuttal(bull_case, bear_case)` -- pure two-section helper (BULL CASE / BEAR CASE) with "None available" fallback on missing/empty inputs.

**2. Final Arguments agent (`src/ai_hedge_fund/agents/final_arguments.py`)** -- Act 4:

- `final_arguments_agent: Agent[None, FinalArguments]` -- identical wiring shape (REASONING tier, retries=2, zero tools).
- `FINAL_ARGUMENTS_SYSTEM_PROMPT` -- names `bull_closing`/`bear_closing`/`citation_count`, forbids introducing new evidence (closings are syntheses, not new arguments).
- `get_final_arguments_limits()` -- `output_override=8_000` per Pitfall 6.
- `format_debate_for_final(bull_case, bear_case, rebuttal)` -- pure three-section helper.

**3. Debate Synthesis agent (`src/ai_hedge_fund/agents/debate_synthesis.py`)** -- Act 5 + tool-first quality-score aggregator:

- `debate_synthesis_agent: Agent[None, DebateSynthesis]` at REASONING tier, `retries=2`, zero tools.
- `DEBATE_SYNTHESIS_SYSTEM_PROMPT` -- Pitfall-3 mitigation: explicitly requires re-evaluating `post_debate_confidence` FROM SCRATCH and documents that `pre_debate_confidence` and `quality_score` will be overwritten by the pipeline.
- `get_debate_synthesis_limits()` -- **DEFAULT** REASONING cap (NO `output_override`). Synthesis emits a full `ThesisOutput` (bull_case + bear_case + risk_factors) plus three sub-scores plus notes and needs the 16k output budget. `TestDebateSynthesisLimits::test_uses_default_reasoning_cap` checks both `total_tokens_limit` AND `output_tokens_limit` to defend against a future refactor applying an override to synthesis.
- `compute_quality_score(evidence, logic, risk) -> int` -- pure Python, `round(0.4*e + 0.3*l + 0.3*r)`. Raises `ValueError` for any sub-score outside `[0, 100]`. **This is the DEBATE-04 tool-first enforcement site.** CLAUDE.md: "Tool-first for quantitative work. LLMs NEVER compute financial ratios." Weighted-mean aggregation is arithmetic, not LLM judgment. Plan 05-03's `debate_synthesis_node` will overwrite the LLM-produced `quality_score` value with this function's output via `DebateSynthesis.model_copy(update={'quality_score': ...})`.
- Module constants `EVIDENCE_WEIGHT=0.4`, `LOGIC_WEIGHT=0.3`, `RISK_WEIGHT=0.3` (RESEARCH.md A1 -- surfaced for testability + auditability; weights sum to 1.0, verified in test).
- `format_debate_for_synthesis(state, pre_debate_confidence)` -- pure six-section helper (PRE-DEBATE CONFIDENCE / PRE-DEBATE THESIS / BULL CASE / BEAR CASE / REBUTTAL / FINAL ARGUMENTS); pre_debate_confidence is always printed (sourced from pipeline, not LLM) so the LLM sees the baseline it must re-evaluate.

**4. DebatePipelineState (`src/ai_hedge_fund/schemas/state.py`)** -- the state the Plan 05-03 graph will run on:

- `TypedDict(total=False)` with `ticker: Required[str]`, `as_of_date: Required[str]`.
- Optional fields: `analyst_reports: Annotated[list[dict], operator.add]` (fan-in reducer PRESERVED -- same as `MultiAgentPipelineState`), `thesis` (written by manager, overwritten by synthesis), `bull_case`, `bear_case`, `rebuttal`, `final_arguments`, `debate_synthesis`, `signal`, `error`.
- **The 5 debate fields carry NO reducer metadata** -- single-writer overwrite semantics, enforced by `TestDebatePipelineStateReducers::test_debate_fields_have_no_reducer` (T-05-15). Silent accumulation via `operator.add` would break the 5-act protocol on retries.
- Field duplication instead of TypedDict multi-inheritance per RESEARCH.md Pattern 5 (multi-inheritance with `Annotated` reducers is fragile).

**5. Package re-exports:**

- `agents/__init__.py` -- added 14 new symbols across `rebuttal`, `final_arguments`, `debate_synthesis` modules; imports and `__all__` alphabetized.
- `schemas/__init__.py` -- added `DebatePipelineState`; imports and `__all__` alphabetized.

**6. Unit tests (65 new tests, all passing):**

- `tests/unit/test_rebuttal_agent.py` (16 tests) -- 5 wiring tests, 4 prompt-content tests, 2 limits tests (incl. `output_override=8_000`), 5 format-helper branch tests.
- `tests/unit/test_final_arguments_agent.py` (13 tests) -- 5 wiring + 3 prompt + 2 limits + 3 format tests.
- `tests/unit/test_debate_synthesis_agent.py` (17 tests) -- 5 wiring + 4 prompt (re-evaluate mandate, sub-score names, overwritten warning, revised_thesis) + 2 limits (symmetric check on BOTH total and output caps -- NO override) + 4 format helper tests.
- `tests/unit/test_quality_score.py` (13 tests) -- 2 weight-constant tests (sum-to-one, evidence-dominant) + 7 arithmetic cases (all-zero, all-hundred, 0.4\*80+0.3\*60+0.3\*40=62, evidence-only=40, logic-only=30, risk-only=30, half-up rounding) + 6 range-check ValueError tests.
- `tests/unit/test_debate_state.py` (6 tests) -- 3 field-presence tests (required, Phase-4, debate), 2 reducer-contract tests (`analyst_reports` keeps `operator.add`, 5 debate fields have none), 1 importable-from-schemas test.

## Files Created / Modified

### Created

- `src/ai_hedge_fund/agents/rebuttal.py` (104 lines)
- `src/ai_hedge_fund/agents/final_arguments.py` (115 lines)
- `src/ai_hedge_fund/agents/debate_synthesis.py` (210 lines)
- `tests/unit/test_rebuttal_agent.py` (133 lines, 16 tests)
- `tests/unit/test_final_arguments_agent.py` (125 lines, 13 tests)
- `tests/unit/test_debate_synthesis_agent.py` (167 lines, 17 tests)
- `tests/unit/test_quality_score.py` (118 lines, 13 tests)
- `tests/unit/test_debate_state.py` (92 lines, 6 tests)

### Modified

- `src/ai_hedge_fund/schemas/state.py` -- appended `DebatePipelineState` TypedDict + extended module docstring with 4th paragraph describing the single-writer debate contract.
- `src/ai_hedge_fund/schemas/__init__.py` -- re-exported `DebatePipelineState`; `__all__` alphabetized.
- `src/ai_hedge_fund/agents/__init__.py` -- re-exported 14 new symbols across three debate modules; imports and `__all__` alphabetized.

## Commits

| Step | Hash | Message |
|------|------|---------|
| Task 1 RED | `1912d77` | `test(05-02): add failing wiring tests for rebuttal_agent and final_arguments_agent` |
| Task 1 GREEN | `0ae698f` | `feat(05-02): add rebuttal_agent and final_arguments_agent (Act 3 + Act 4 debate agents)` |
| Task 2 RED | `3f6f26d` | `test(05-02): add failing tests for debate_synthesis_agent + compute_quality_score` |
| Task 2 GREEN | `b70caff` | `feat(05-02): add debate_synthesis_agent + compute_quality_score pure-function aggregator` |
| Task 3 RED | `63e5831` | `test(05-02): add failing contract tests for DebatePipelineState TypedDict` |
| Task 3 GREEN | `9cf4352` | `feat(05-02): add DebatePipelineState TypedDict with single-writer debate fields` |

## Test Counts

- 65 new tests added: 16 rebuttal + 13 final_arguments + 17 debate_synthesis agent + 13 quality_score (pure) + 6 debate_state (contract).
- Subset verification: `uv run pytest tests/unit/test_rebuttal_agent.py tests/unit/test_final_arguments_agent.py tests/unit/test_debate_synthesis_agent.py tests/unit/test_quality_score.py tests/unit/test_debate_state.py -x` -> 65 passed.
- Full `tests/unit/` suite: **537 passed** (up from 472 before this plan; delta = 65 -- matches).
- `uv run ruff check` on all 11 new/modified files -> `All checks passed!`.

## Key Decisions Locked In

1. **Quality-score weights: `EVIDENCE_WEIGHT=0.4`, `LOGIC_WEIGHT=0.3`, `RISK_WEIGHT=0.3`** as module-level constants in `debate_synthesis.py`. Resolves RESEARCH.md Open Question 1; surfaced as constants (not inline literals) so alternative weightings can be tested and audited without touching the compute function.
2. **`compute_quality_score` is pure Python, raises ValueError for any sub-score outside `[0, 100]`.** This is the DEBATE-04 tool-first enforcement site. CLAUDE.md mandates that LLMs never compute quantitative aggregates -- weighted means are arithmetic, not judgment. The LLM-produced `quality_score` field on `DebateSynthesis` is a placeholder; Plan 05-03's `debate_synthesis_node` overwrites it with the Python result.
3. **Rebuttal + final_arguments use `output_override=8_000`; debate_synthesis uses the default REASONING cap (16k).** The asymmetry is intentional: rebuttals and closings are structurally small (3 per side × 2 sentences; 1-2 paragraphs per side), so the Pitfall-6 cost guardrail applies. Synthesis emits a full `ThesisOutput` (bull_case + bear_case + risk_factors) + 3 sub-scores + `synthesis_notes` and needs the full output budget. `TestDebateSynthesisLimits::test_uses_default_reasoning_cap` verifies BOTH `total_tokens_limit` AND `output_tokens_limit` match the defaults -- a defensive symmetric check that catches a future refactor accidentally applying an override to synthesis.
4. **DebatePipelineState duplicates Phase-4 fields rather than inheriting from `MultiAgentPipelineState`.** TypedDict multi-inheritance with `Annotated` reducer metadata is fragile (per RESEARCH.md Pattern 5). Duplication is explicit and grep-able.
5. **The 5 debate-act fields on `DebatePipelineState` carry NO `operator.add` reducer -- single-writer overwrite semantics.** `analyst_reports` keeps its reducer (fan-in from parallel analysts). The debate fields must be single-writer because silent accumulation across retries would break the 5-act protocol. `TestDebatePipelineStateReducers::test_debate_fields_have_no_reducer` is the load-bearing contract test (T-05-15).
6. **`DEBATE_SYNTHESIS_SYSTEM_PROMPT` explicitly forbids defaulting `post_debate_confidence` to `pre_debate_confidence`** (Pitfall-3 mitigation; DEBATE-04 success criterion 4). It also documents that `pre_debate_confidence` and `quality_score` get overwritten by the pipeline, preventing the LLM from fighting the pipeline over those two fields.
7. **TDD RED/GREEN committed per task** (6 commits). Each task produced a failing-tests commit (`test(05-02): ...`) followed by an implementation commit (`feat(05-02): ...`), verifying that every test pre-dated its implementation and genuinely failed first.

## Deviations from Plan

Minor: `tests/unit/test_quality_score.py` required the same dummy `ANTHROPIC_API_KEY` setup used by the other agent tests. The plan's action block said "no async, no dummy API key needed since no Agent is constructed" -- but importing `ai_hedge_fund.agents.debate_synthesis` constructs `debate_synthesis_agent = Agent(...)` at module top level, which triggers PydanticAI's Anthropic provider factory and fails with `UserError: Set the ANTHROPIC_API_KEY environment variable ...`. Applied Rule 3 (auto-fix blocking issue): added `os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")` before the import, matching the existing Phase-4/5 agent-test convention. Updated the test-file docstring to explain the correction. No schema, no behavior change; purely a test bootstrap fix.

No other deviations. RESEARCH.md weights (0.4/0.3/0.3) landed as specified. Pitfall-6 output overrides applied exactly where prescribed. Single-writer contract tests match the Anti-Patterns guidance verbatim.

## Requirements Enforcement Status

| Req ID | Status | Mechanism |
|--------|--------|-----------|
| DEBATE-03 | **Fully enforced at schema + agent + prompt levels** | `RebuttalAct` (`min_length=2` on both sides), `FinalArguments` (`min_length=1` on closings), `DebateSynthesis` (`min_length=1` on notes + `ge=0, le=100` on all scores) already in place from Plan 05-01. Plan 05-02 adds the agents that produce those outputs with prompts that enforce the schema requirements. Plan 05-03 will wire them into a LangGraph chain where skipping an act cannot happen (all 5 nodes are on the sequential edge path). |
| DEBATE-04 | **Quality-score enforcement locked in: `compute_quality_score` is a pure Python weighted mean with ValueError range checks; `DEBATE_SYNTHESIS_SYSTEM_PROMPT` demands re-evaluation of post_debate_confidence from scratch** | Pitfall-3 mitigation explicit in the system prompt; Plan 05-03's `debate_synthesis_node` will overwrite the LLM's `quality_score` field with the Python result (already planned in `DebateSynthesis` schema description: "Populated by compute_quality_score() in debate_synthesis_node before writing to state"). The "differs from pre-debate in at least 30% of runs" success check remains a real-LLM UAT item per `05-VALIDATION.md`. |

## Known Stubs

None. Every module-level constant is imported by at least one test. Every agent is fully wired (tier, output_type, retries, prompt, limits, format helper). `DebatePipelineState` is referenced only by `test_debate_state.py` in this plan -- it will be consumed by `build_debate_pipeline` in Plan 05-03.

## Next Plan

Plan 05-03 wires the 10-agent sequential debate graph: 5 debate nodes (`bull_node`, `bear_node`, `rebuttal_node`, `final_arguments_node`, `debate_synthesis_node`) + `debate_signal_node` + `build_debate_pipeline` + TestModel-driven integration tests. `debate_synthesis_node` overwrites `state["thesis"]` with the post-debate `revised_thesis` and overwrites the LLM-produced `quality_score` with `compute_quality_score(...)`. Every primitive that plan needs -- agents, schemas, state, compute helpers -- is now in place.

## Self-Check: PASSED

Verification commands run and outputs confirmed:

- `[ -f src/ai_hedge_fund/agents/rebuttal.py ]` -> FOUND
- `[ -f src/ai_hedge_fund/agents/final_arguments.py ]` -> FOUND
- `[ -f src/ai_hedge_fund/agents/debate_synthesis.py ]` -> FOUND
- `[ -f tests/unit/test_rebuttal_agent.py ]` -> FOUND
- `[ -f tests/unit/test_final_arguments_agent.py ]` -> FOUND
- `[ -f tests/unit/test_debate_synthesis_agent.py ]` -> FOUND
- `[ -f tests/unit/test_quality_score.py ]` -> FOUND
- `[ -f tests/unit/test_debate_state.py ]` -> FOUND
- `git log --oneline --all | grep 1912d77` -> FOUND (Task 1 RED)
- `git log --oneline --all | grep 0ae698f` -> FOUND (Task 1 GREEN)
- `git log --oneline --all | grep 3f6f26d` -> FOUND (Task 2 RED)
- `git log --oneline --all | grep b70caff` -> FOUND (Task 2 GREEN)
- `git log --oneline --all | grep 63e5831` -> FOUND (Task 3 RED)
- `git log --oneline --all | grep 9cf4352` -> FOUND (Task 3 GREEN)
- `uv run pytest tests/unit/test_rebuttal_agent.py tests/unit/test_final_arguments_agent.py tests/unit/test_debate_synthesis_agent.py tests/unit/test_quality_score.py tests/unit/test_debate_state.py -x` -> 65 passed
- Full `tests/unit/` suite -> 537 passed (no regressions; 472 + 65 = 537)
- `ruff check` on all 11 new/modified files -> All checks passed!
- `uv run python -c "from ai_hedge_fund.agents import rebuttal_agent, final_arguments_agent, debate_synthesis_agent, compute_quality_score, EVIDENCE_WEIGHT, LOGIC_WEIGHT, RISK_WEIGHT; from ai_hedge_fund.schemas import DebatePipelineState"` -> exits 0
- `uv run python -c "from ai_hedge_fund.agents.debate_synthesis import compute_quality_score; assert compute_quality_score(80, 60, 40) == 62; assert compute_quality_score(100, 100, 100) == 100; assert compute_quality_score(0, 0, 0) == 0"` -> exits 0
