---
phase: 05-adversarial-critique
plan: 01
subsystem: adversarial-critique
tags: [phase-05, debate, schemas, bull-agent, bear-agent, tdd]
requires:
  - ai_hedge_fund.schemas.agents.ThesisOutput
  - ai_hedge_fund.schemas.agents.ThesisPoint
  - ai_hedge_fund.agents.base.get_usage_limits
  - ai_hedge_fund.agents.manager.manager_agent
  - ai_hedge_fund.models.ModelTier
provides:
  - ai_hedge_fund.schemas.debate.BullClaim
  - ai_hedge_fund.schemas.debate.BullCase
  - ai_hedge_fund.schemas.debate.BearClaim
  - ai_hedge_fund.schemas.debate.BearCase
  - ai_hedge_fund.schemas.debate.RebuttalPoint
  - ai_hedge_fund.schemas.debate.RebuttalAct
  - ai_hedge_fund.schemas.debate.FinalArguments
  - ai_hedge_fund.schemas.debate.DebateSynthesis
  - ai_hedge_fund.schemas.debate.AnalystName
  - ai_hedge_fund.agents.bull.bull_agent
  - ai_hedge_fund.agents.bull.BULL_SYSTEM_PROMPT
  - ai_hedge_fund.agents.bull.get_bull_limits
  - ai_hedge_fund.agents.bull.format_analyst_evidence
  - ai_hedge_fund.agents.bear.bear_agent
  - ai_hedge_fund.agents.bear.BEAR_SYSTEM_PROMPT
  - ai_hedge_fund.agents.bear.get_bear_limits
  - ai_hedge_fund.agents.bear.format_bull_case_for_bear
affects:
  - src/ai_hedge_fund/schemas/__init__.py
  - src/ai_hedge_fund/agents/__init__.py
tech-stack:
  added: []
  patterns:
    - "Zero-tools REASONING-tier Agent[None, OutputType] cloned from manager_agent"
    - "Pydantic min_length on substantive list/string fields as the DEBATE-01/02/03 enforcement mechanism"
    - "Literal[\"fundamental\",\"sentiment\",\"technical\",\"manager\"] for source_analyst citations"
    - "ThesisOutput reused (not redefined) inside DebateSynthesis.revised_thesis"
    - "TDD RED/GREEN per task: failing test commit precedes implementation commit"
key-files:
  created:
    - src/ai_hedge_fund/schemas/debate.py
    - src/ai_hedge_fund/agents/bull.py
    - src/ai_hedge_fund/agents/bear.py
    - tests/unit/test_debate_schemas.py
    - tests/unit/test_bull_agent.py
    - tests/unit/test_bear_agent.py
  modified:
    - src/ai_hedge_fund/schemas/__init__.py
    - src/ai_hedge_fund/agents/__init__.py
decisions:
  - "AnalystName Literal includes 'manager' so bull/bear can cite manager synthesis (not only the three analysts) -- matches PATTERNS.md delta."
  - "BearCase.addressed_bull_claims: list[str] = Field(min_length=2) is the schema-level DEBATE-02 enforcement; verbatim-ness is prompt-only (RESEARCH.md assumption A3)."
  - "Model-tier test compares bull_agent.model.model_name against manager_agent.model.model_name so the assertion is robust to REASONING-tier version bumps (no hardcoded 'claude-opus-4-6' string)."
  - "Both agents use retries=2 (cloned from manager_agent) so PydanticAI's retry loop can hand schema validation errors back to the LLM for self-correction."
  - "quality_score weights (0.4/0.3/0.3) deferred to Plan 05-02 Task 2 (DEBATE-04 synthesis) where compute_quality_score lives; schema field is declared here with the semantic description but not populated."
  - "No output_override on get_bull_limits / get_bear_limits in v1 -- both inherit the REASONING-tier default (100k/16k/116k). Per-role overrides are a post-UAT cost-optimization lever (RESEARCH.md Pitfall 6)."
metrics:
  duration: 9m
  completed: 2026-04-22T00:23:15Z
---

# Phase 05 Plan 01: Debate Schemas + Bull/Bear Agents Summary

Landed the Pydantic act-output schemas for the full 5-act adversarial debate protocol, plus the first two debate agents (Bull Advocate, Bear Advocate) with their zero-tools REASONING-tier wiring and format helpers. DEBATE-01 source-citation enforcement and DEBATE-02 "address >=2 bull claims" enforcement are now schema-level guarantees — every invalid act output fails validation at `agent.run()` time, no custom validator code required.

## What Was Built

**1. Debate act schemas (`src/ai_hedge_fund/schemas/debate.py`) — 8 Pydantic models + 1 Literal alias:**

- `AnalystName = Literal["fundamental", "sentiment", "technical", "manager"]` — extends the Phase-4 `AnalystReport.analyst` Literal to include `"manager"` so bull/bear can cite the manager's synthesis, not only the three analysts.
- `BullClaim`, `BullCase` — `BullCase.claims: list[BullClaim] = Field(min_length=3)` is the schema-level enforcement of "Bull produces at least 3 claims" (DEBATE-01 success criterion).
- `BearClaim`, `BearCase` — `BearCase.addressed_bull_claims: list[str] = Field(min_length=2)` is the schema-level enforcement of DEBATE-02 ("bear directly addresses at least 2 specific bull claims"). `BearClaim.addresses_bull_claim: str | None` is optional per-claim linkage to a bull claim (None for independent counter-evidence).
- `RebuttalPoint`, `RebuttalAct` — `bull_rebuttals` AND `bear_rebuttals` each carry `min_length=2` (DEBATE-03 Act 3).
- `FinalArguments` — non-empty bull/bear closings, non-negative citation counts (DEBATE-03 Act 4).
- `DebateSynthesis` — nests `ThesisOutput` as `revised_thesis` (imported, not redefined), carries pre/post confidence, three sub-scores (evidence_strength, logical_consistency, risk_coverage), and `quality_score` — all `ge=0, le=100`. `synthesis_notes: str = Field(min_length=1)`. `quality_score` is documented as computed (not LLM-generated) for Plan 05-02.

**2. Bull Advocate (`src/ai_hedge_fund/agents/bull.py`):**

- `bull_agent: Agent[None, BullCase]` at `ModelTier.REASONING.value` (Opus), `retries=2`, zero tools, `system_prompt=BULL_SYSTEM_PROMPT`.
- `BULL_SYSTEM_PROMPT` — requires `source_analyst` citations, forbids vague claims, demands at least 3 claims, primes the "advocate not synthesizer" role, caps at 3-5 claims for brevity (RESEARCH.md Pitfall 6).
- `get_bull_limits()` returns REASONING-tier `UsageLimits` (116k total).
- `format_analyst_evidence(reports, thesis)` — pure helper that emits two labelled sections (`PRELIMINARY THESIS:` + `ANALYST EVIDENCE:`) separated by `"\n\n---\n\n"`, with None/empty fallbacks and analyst-error-branch handling.

**3. Bear Advocate (`src/ai_hedge_fund/agents/bear.py`):**

- `bear_agent: Agent[None, BearCase]` — identical wiring to bull (REASONING tier, retries=2, zero tools).
- `BEAR_SYSTEM_PROMPT` — contains both the literal string `"addressed_bull_claims"` and the literal phrase `"at least 2"`, so PydanticAI's retries=2 loop can self-correct when the LLM under-fills the list. Prompt explicitly instructs verbatim quotation of bull-claim text into `addressed_bull_claims`, requires `source_analyst` citations, forbids vague claims, and primes the adversarial stance (Pitfall 1 mitigation).
- `get_bear_limits()` same shape as bull.
- `format_bull_case_for_bear(bull_case)` — pure helper that emits `BULL CASE TO REBUT:\n1. [source] claim -- evidence: ev\n2. ...\nHEADLINE: ...`. Handles `None` and empty-claims inputs.

**4. Package re-exports:**

- `schemas/__init__.py` exposes the 8 new models + `AnalystName` is internal to `debate.py`.
- `agents/__init__.py` exposes `bull_agent`, `bear_agent`, `get_bull_limits`, `get_bear_limits`, `format_analyst_evidence`, `format_bull_case_for_bear`; both are added to `__all__` in alphabetical order.

**5. Unit tests (73 new tests, all passing):**

- `tests/unit/test_debate_schemas.py` — 37 tests across `TestBullClaim`, `TestBullCase`, `TestBearClaim`, `TestBearCase`, `TestRebuttalPoint`, `TestRebuttalAct`, `TestFinalArguments`, `TestDebateSynthesis`, and the explicit **`TestEmptyActRaisesValidationError`** class documenting DEBATE-03 success criterion 3.
- `tests/unit/test_bull_agent.py` — 19 tests: agent wiring (tier-equality vs manager, output_type, retries, zero tools), prompt content (source_analyst citation, minimum claims, advocate role, no-vague-claims), limits match REASONING tier, and 7 `format_analyst_evidence` branch tests.
- `tests/unit/test_bear_agent.py` — 17 tests: identical agent-wiring structure plus the DEBATE-02 prompt assertion that checks both `"addressed_bull_claims"` AND `"at least 2"` are present verbatim; 7 `format_bull_case_for_bear` branch tests including the numbered-list format and the `[source_analyst]` prefix.

## Files Created / Modified

### Created

- `src/ai_hedge_fund/schemas/debate.py` (210 lines)
- `src/ai_hedge_fund/agents/bull.py` (114 lines)
- `src/ai_hedge_fund/agents/bear.py` (116 lines)
- `tests/unit/test_debate_schemas.py` (551 lines, 37 tests)
- `tests/unit/test_bull_agent.py` (165 lines, 19 tests)
- `tests/unit/test_bear_agent.py` (222 lines, 17 tests)

### Modified

- `src/ai_hedge_fund/schemas/__init__.py` — added 8 debate schemas + re-sorted `__all__` alphabetically.
- `src/ai_hedge_fund/agents/__init__.py` — added bear/bull agents, limits helpers, format helpers to imports and `__all__` alphabetically.

## Commits

| Step | Hash | Message |
|------|------|---------|
| Task 1 RED | `df78894` | `test(05-01): add failing tests for debate act output schemas` |
| Task 1 GREEN | `1a9e037` | `feat(05-01): add debate act output schemas ...` |
| Task 2 RED | `f9ed98f` | `test(05-01): add failing wiring tests for bull_agent and bear_agent` |
| Task 2 GREEN | `b6be5ab` | `feat(05-01): add bull_agent and bear_agent with zero tools at REASONING tier` |

## Test Counts

- 73 new tests added (37 schema + 19 bull + 17 bear).
- Full `tests/unit/` suite: **472 passed** (up from 399 before this plan).
- Subset verification: `uv run pytest tests/unit/test_debate_schemas.py tests/unit/test_bull_agent.py tests/unit/test_bear_agent.py -x` → 73 passed in 2.4s.
- ruff check + ruff format --check both clean on all 6 new/modified files.

## Key Decisions Locked In

1. **`AnalystName` extends the Phase-4 analyst Literal to include `"manager"`.** Bull/bear can cite the manager's synthesis (e.g., a confidence or risk-factor assessment), not only the three analysts. Matches PATTERNS.md line 194 and RESEARCH.md Pitfall 2 mitigation.
2. **`BearCase.addressed_bull_claims: list[str] = Field(min_length=2)` is the DEBATE-02 enforcement site.** Verbatim-ness (did the bear actually quote the bull claim?) is enforced only by the system prompt; the schema enforces count. Semantic-alignment checking is deferred to UAT per `05-VALIDATION.md` Manual-Only Verifications row 2.
3. **Bull/bear use the REASONING-tier default UsageLimits unchanged.** No `output_override` in v1. Per-role output budget reductions (RESEARCH.md Pitfall 6) are a post-UAT cost-optimization lever. `PipelineBudgetTracker` total_limit remains the fleet-wide backstop.
4. **Model-tier assertion uses `== manager_agent.model.model_name`, not a hardcoded string.** The tests don't break when `ModelTier.REASONING` is bumped to a new Opus version — they only assert that bull/bear track manager at the same tier.
5. **`quality_score` weights (0.4/0.3/0.3) are deferred to Plan 05-02.** `DebateSynthesis.quality_score` is declared here as a plain `int = Field(ge=0, le=100)` with a description pointing at the future `compute_quality_score()` helper in `src/ai_hedge_fund/agents/debate_synthesis.py`. Weights will live as module-level constants in Plan 05-02 per RESEARCH.md Open Question 1 resolution.
6. **TDD RED/GREEN committed per task.** Each task produced two commits: a failing-tests commit (`test(05-01): ...`) followed by an implementation commit (`feat(05-01): ...`). Verifies that every test-file change pre-dates its implementation and genuinely fails first.

## Deviations from Plan

None — plan executed exactly as written. PATTERNS.md analogs matched the existing codebase (manager.py + specialist schemas) with no surprises. Every acceptance-criterion grep matched. Every executable check (pytest subset, ruff check, ruff format --check, full suite regression) passed on the first attempt after implementation.

## Requirements Enforcement Status

| Req ID | Status | Mechanism |
|--------|--------|-----------|
| DEBATE-01 | **Schema-level enforced (this plan)** | `BullCase.claims: list[BullClaim] = Field(min_length=3)` + `BullClaim.source_analyst: AnalystName` Literal + `BULL_SYSTEM_PROMPT` requires source_analyst citations. |
| DEBATE-02 | **Schema-level enforced (this plan)** | `BearCase.addressed_bull_claims: list[str] = Field(min_length=2)` + `BEAR_SYSTEM_PROMPT` explicitly names the field and the >=2 requirement. |
| DEBATE-03 | **Partially — schemas exist (this plan); agents + pipeline come in 05-02 and 05-03** | `RebuttalAct`, `FinalArguments`, `DebateSynthesis` schemas are defined with `min_length` constraints, so any empty-act output will raise `ValidationError`. `rebuttal_agent`, `final_arguments_agent`, `debate_synthesis_agent` and the sequential LangGraph chain are the remaining Wave 2/3 work. |
| DEBATE-04 | **Partially — schema field exists (this plan); computation comes in 05-02** | `DebateSynthesis.quality_score` field is declared; `compute_quality_score` helper and its tests are in Plan 05-02. |

## Known Stubs

None. Every declared schema field is used by at least one test assertion. Every agent is fully wired (tier, output_type, retries, system prompt, limits, format helper). `quality_score` is not a stub — it is a declared field whose *populator* lives in Plan 05-02; `DebateSynthesis` validates correctly today with a hand-provided value (verified in `TestDebateSynthesis::test_valid_happy_path`).

## Self-Check: PASSED

Verification commands run and outputs confirmed:

- `[ -f src/ai_hedge_fund/schemas/debate.py ]` → FOUND
- `[ -f src/ai_hedge_fund/agents/bull.py ]` → FOUND
- `[ -f src/ai_hedge_fund/agents/bear.py ]` → FOUND
- `[ -f tests/unit/test_debate_schemas.py ]` → FOUND
- `[ -f tests/unit/test_bull_agent.py ]` → FOUND
- `[ -f tests/unit/test_bear_agent.py ]` → FOUND
- `git log --oneline --all | grep df78894` → FOUND (Task 1 RED)
- `git log --oneline --all | grep 1a9e037` → FOUND (Task 1 GREEN)
- `git log --oneline --all | grep f9ed98f` → FOUND (Task 2 RED)
- `git log --oneline --all | grep b6be5ab` → FOUND (Task 2 GREEN)
- Final `uv run pytest tests/unit/test_debate_schemas.py tests/unit/test_bull_agent.py tests/unit/test_bear_agent.py` → 73 passed
- Full `tests/unit/` suite → 472 passed (no regressions)
- `ruff check` + `ruff format --check` on all 6 new/modified files → All checks passed
