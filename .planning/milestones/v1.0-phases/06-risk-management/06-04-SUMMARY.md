---
phase: 06
plan: 04
wave: 3
status: complete
completed: 2026-04-22
---

# Plan 06-04 — Risk Manager Agent SUMMARY

## What was built

RATIONALE-ONLY PydanticAI agent for the Phase 6 risk layer. The agent cannot author the APPROVED/VETOED decision because its output schema (`RationaleOnly`) has no status field — Pattern 2 from research, schema-level enforcement of Pitfall 1 prevention.

### Module

| File | LOC | Provides |
|------|-----|----------|
| `src/ai_hedge_fund/agents/risk_manager.py` | 147 | `RationaleOnly`, `RISK_MANAGER_SYSTEM_PROMPT`, `risk_manager_agent`, `get_risk_manager_limits`, `format_risk_context_for_rationale` |
| `src/ai_hedge_fund/agents/__init__.py` | modified | +5 names re-exported (alphabetised) |

### Tests

`tests/risk/test_risk_manager_agent.py` — 11 tests covering:
1-2. Agent wiring + output type is `RationaleOnly`
3. RationaleOnly validator rejects empty strings
4. Zero registered tools (verbatim idiom from `tests/unit/test_manager_agent.py::test_agent_no_tools`)
5-6. Limits: `output_override=4_000`, REASONING tier input budget
7. System prompt uses "explain"
8. System prompt lacks forbidden decision verbs (`you decide`, `you judge`, `you must decide`, `your veto`)
9-10. Format helper: APPROVED/VETOED context strings include ticker, status, constraint name, observed, limit
11. TestModel stub end-to-end (no real LLM call)

## Commits

| Hash | Message |
|------|---------|
| `8f4cf40` | test(06-04): add failing risk_manager_agent wiring and RationaleOnly tests |
| `d694271` | feat(06-04): add risk_manager_agent with RationaleOnly output schema |

## Test results

- `uv run pytest tests/risk/test_risk_manager_agent.py -q` → **11 passed** in 1.62s
- `uv run pytest tests/risk -q` (06-01 + 06-02 + 06-03 + 06-04 combined) → **65 passed** in 1.47s (no regressions)
- `uv run ruff format/check src/ai_hedge_fund/agents/risk_manager.py` → exit 0

## Acceptance criteria

- `grep -q "risk_manager_agent: Agent" risk_manager.py` ✓
- `grep -q "class RationaleOnly(BaseModel):" risk_manager.py` ✓
- `grep -q "output_override=4_000" risk_manager.py` ✓
- `grep -q "ModelTier.REASONING" risk_manager.py` ✓
- `RationaleOnly.model_fields == {"rationale"}` ✓ (exactly one field)
- Forbidden-verb absence verified ✓
- Top-level import works: `from ai_hedge_fund.agents import risk_manager_agent, RationaleOnly` ✓
- Zero-tool idiom uses `_function_toolset.tools` (matches `tests/unit/test_manager_agent.py`) ✓
- File 147 lines (<300 limit), every function <50 lines ✓
- 11/11 tests pass ✓

## Requirements completion

- **RISK-01**: Agent layer complete. The agent CANNOT emit a VETOED/APPROVED decision (schema-enforced). Full RISK-01 completion requires 06-05 (node wiring overwrites status via Python) and 06-06 (integration tests prove the end-to-end).

## Deviations from plan

None. Plan action block executed verbatim except for a small prompt text cleanup (the plan's draft "You DO NOT decide approval. You DO NOT judge." was tightened to "You DO NOT author the outcome. You EXPLAIN the outcome already computed by Python." — preserves the no-decide semantics without the word "decide" appearing in the prompt at all, which is a stricter interpretation of Pitfall 1 warning signs). Forbidden-verb test still passes.

## Notes for downstream plans

- **06-05 (risk_manager_node)**: Call `risk_manager_agent.run(format_risk_context_for_rationale(...))` with `usage_limits=get_risk_manager_limits()`. Construct `RiskAssessment` with Python-authored `status` (do NOT use `result.output.model_copy` — the agent doesn't have `status` in its output).
- Pattern follows `manager_agent` exactly — see `src/ai_hedge_fund/agents/manager.py` for the template and `tests/unit/test_manager_agent.py` for the test idioms.
