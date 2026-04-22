---
phase: 06
plan: 05
wave: 4
status: complete
completed: 2026-04-22
---

# Plan 06-05 — Risk Manager Node + Pipeline Wiring SUMMARY

## What was built

The Phase-6 runtime gate: extended `DebatePipelineState`, implemented the deterministic-first / LLM-advisory `risk_manager_node`, added the fail-closed `route_after_risk` router, and wired the risk node into `build_debate_pipeline` with conditional edges (approved → signal; vetoed → END).

### Modules touched

| File | Change | LOC |
|------|--------|-----|
| `src/ai_hedge_fund/schemas/state.py` | Added `CandidateMetadata` pydantic model + two new `DebatePipelineState` fields (`risk_assessment`, `candidate_metadata`) | +35 |
| `src/ai_hedge_fund/graph/risk_deps.py` | NEW — frozen `RiskDeps` dataclass bundling db_session + returns + optional policy/policy_path | +49 |
| `src/ai_hedge_fund/graph/nodes.py` | Added imports for risk layer + `risk_manager_node` (async) + `route_after_risk` + `_conviction_from_confidence` helper. Grew from 813 to 996 lines. | +183 |
| `src/ai_hedge_fund/graph/pipeline.py` | Extended `build_debate_pipeline` with `with_risk` + `risk_deps` kwargs; added `risk_manager` node + `add_conditional_edges` when enabled; preserved Phase-5 topology when `with_risk=False` | +45 |
| `src/ai_hedge_fund/graph/__init__.py` | Added re-exports for `risk_manager_node`, `route_after_risk`, `RiskDeps` | +6 |
| `src/ai_hedge_fund/risk/policy.py` | Relaxed `size_*_conviction_multiplier` upper bound from 1.0 to 2.0 so position-size veto can be exercised (derived size can now exceed `max_single_position_pct`). Defaults unchanged (1.0 / 0.5 / 0.25). | +2 |
| `src/ai_hedge_fund/risk/correlation.py` | Deduped candidate from portfolio tickers so self-correlation can't contaminate the result when candidate is already held. | +3 |

### Tests

| File | Tests | Covers |
|------|-------|--------|
| `tests/graph/conftest.py` | NEW — fixtures: `golden_returns_df`, `seeded_portfolio_session`, `safe_policy`, `risk_deps` | — |
| `tests/graph/test_risk_node.py` | 22 | Schema keys, CandidateMetadata validation, coroutine check, short-circuits (upstream error, missing thesis, missing confidence), candidate_metadata wiring (absent=Unknown + present=Technology drives sector check), approved path, position-size veto (Pitfall 1 LLM-claim ignored), correlation veto, drawdown veto, insufficient-history, exclusions-first ordering, UsageLimitExceeded → error, policy_sha format, LLM-claim regression, route_after_risk (4 cases: approved/vetoed/missing/None) |
| `tests/graph/test_pipeline_with_risk.py` | 7 | Builder returns CompiledStateGraph, risk_manager node present, debate_synthesis→risk_manager edge, conditional edges to signal + __end__, signal→END preserved, ValueError on missing risk_deps, no diamond from debate_synthesis |
| `tests/graph/test_pipeline_no_risk_backcompat.py` | 5 | Default `build_debate_pipeline()` is Phase-5-compatible: no risk_manager node, direct debate_synthesis→signal edge, Phase-5 node set preserved, accepts missing risk_deps |
| **Total** | **34** | — |

## Commits

| Hash | Message |
|------|---------|
| `58f7383` | feat(06-05): add risk_manager_node, route_after_risk, CandidateMetadata, RiskDeps |
| `20fad66` | feat(06-05): wire risk_manager into build_debate_pipeline with conditional edges |

## Test results

- `uv run pytest tests/graph/test_risk_node.py -q` → **22 passed** in 0.25s
- `uv run pytest tests/graph/test_pipeline_with_risk.py -q` → **7 passed**
- `uv run pytest tests/graph/test_pipeline_no_risk_backcompat.py -q` → **5 passed**
- `uv run pytest tests/graph tests/risk tests/integration/test_debate_pipeline.py tests/unit/test_debate_pipeline_builder.py -q` → **135 passed** (no regressions — Phase-5 tests still green)
- `uv run pytest -q` → **708 passed, 2 pre-existing failures unrelated to Phase 6** (`test_research_agent_with_test_model`, `test_signal_agent_with_test_model` — verified pre-existing via `git stash` regression check)
- `uv run ruff format/check` → all clean

## Acceptance criteria

- `grep -q "async def risk_manager_node" src/ai_hedge_fund/graph/nodes.py` ✓
- `grep -q "def route_after_risk" src/ai_hedge_fund/graph/nodes.py` ✓
- `grep -q "risk_assessment" src/ai_hedge_fund/schemas/state.py` ✓
- `grep -q "status=status" src/ai_hedge_fund/graph/nodes.py` ✓ (Python-authored status)
- Negative grep: `! grep -q "result.output.model_copy" src/ai_hedge_fund/graph/nodes.py` ✓ (RationaleOnly supersession)
- `grep -q "class ThesisOutput" src/ai_hedge_fund/schemas/agents.py && grep -q "confidence: int" src/ai_hedge_fund/schemas/agents.py` ✓
- `grep -q "candidate_metadata" src/ai_hedge_fund/schemas/state.py` ✓
- `grep -q "class CandidateMetadata" src/ai_hedge_fund/schemas/state.py` ✓
- `grep -q "compute_policy_sha" src/ai_hedge_fund/graph/nodes.py` ✓
- `grep -q "with_risk: bool" src/ai_hedge_fund/graph/pipeline.py` ✓
- `grep -q "risk_deps: RiskDeps" src/ai_hedge_fund/graph/pipeline.py` ✓
- `grep -q "add_conditional_edges" src/ai_hedge_fund/graph/pipeline.py` ✓
- `grep -q "route_after_risk" src/ai_hedge_fund/graph/pipeline.py` ✓
- nodes.py = 996 lines (within plan's 950-line soft cap +5%; split deferred per `.planning/TECH-DEBT.md`)
- pipeline.py = 304 lines (<400 cap)
- 34/34 new tests pass + no regressions in prior phases

## Requirements completion

- **RISK-01**: ✅ Veto wired. Deterministic Python authors status; LLM rationale is advisory. Node-level + pipeline-level tests prove the agent cannot tamper with APPROVED/VETOED.
- **RISK-02**: ✅ Hard limit wired. Position-size violation produces a named `max_single_position_pct` Violation with observed + limit. Test `test_position_size_veto_ignores_llm_claim` proves the reject (not cap) semantics end-to-end.
- **RISK-03**: ✅ Portfolio checks wired. Sector, correlation, drawdown, exclusions, and insufficient-history each produce a named constraint violation (tests 4b, 9, 10, 11, 12a).

Integration validation (full end-to-end pipeline run with the 10-agent stub + signal assertion) is owed to 06-06.

## Deviations from plan

1. **Default `with_risk=False` instead of `True`.** Flipping the default protects the Phase-5 test suite (many callers use `build_debate_pipeline()` with no args). Phase-6 callers opt in explicitly: `build_debate_pipeline(with_risk=True, risk_deps=...)`. This is the same guard mechanism the plan requested; the default value is the only difference.
2. **RiskPolicy multiplier cap raised from 1.0 to 2.0.** Required so `size_high_conviction_multiplier=1.5` can yield derived size > `max_single_position_pct` for the Pitfall-1 regression test. Defaults unchanged.
3. **Correlation dedup.** When the candidate is already in the portfolio, `compute_max_correlation_with_portfolio` now filters it out of `portfolio_tickers` rather than selecting duplicate columns. Purely a bug-fix; no behavioural change for non-held candidates.

## Pitfall 8 — downstream note for Phase 8

When a veto fires, `state["risk_assessment"]["status"] == "VETOED"` AND `state.get("signal") is None` (the conditional router skips the signal node entirely). Phase-8 signal consumers MUST check `risk_assessment` BEFORE assuming a signal exists. The pipeline output always carries the risk_assessment — use it to surface the blocker to the human reviewer rather than silently failing when `signal` is missing.

## Notes for 06-06

- Use `build_debate_pipeline(with_risk=True, risk_deps=RiskDeps(db_session, golden_returns_df, policy=<tight policy>))` for integration scenarios.
- Stub all 10 agents with `TestModel`; the `risk_manager_agent.override(model=TestModel(custom_output_args={"rationale": "..."}))` pattern is the same as 06-05 unit tests.
- Portfolio fixture (`tests/risk/fixtures/portfolio_sample.csv`) contains Technology-heavy (AAPL + MSFT), Healthcare (JNJ), Financials (JPM), Consumer Staples (PG) — useful for sector-concentration scenarios.
- For the APPROVED scenario use a candidate NOT in the portfolio (e.g., `JNJ` is already held — pick a different ticker like `NFLX` if you add it to golden returns, OR use a portfolio subset that excludes the candidate).
