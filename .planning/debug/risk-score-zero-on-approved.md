---
slug: risk-score-zero-on-approved
status: resolved
trigger: End-to-end run on AAPL (2026-04-18) returned risk_score=0/100 on an APPROVED signal, which is obviously wrong. Root cause already triaged before session spawn (see Evidence). User has approved the full fix approach.
created: 2026-04-24
updated: 2026-04-24
---

# Debug Session: risk-score-zero-on-approved

## Symptoms

<!-- DATA_START -->
- **expected**: `run_analysis` final signal carries a non-zero `risk_score` in [0,100] that actually reflects the proposed trade's utilization of the policy limits (position size, correlation, drawdown, sector) — per `08-RESEARCH.md` A9 resolution: `max(size / max_single_position_pct, corr_frac, dd_frac) * 100` clamped to 100.
- **actual**: AAPL run on 2026-04-18 produced an APPROVED risk assessment but the final signal shows `risk_score: 0/100`. Observed across APPROVED cases generally, not AAPL-specific.
- **errors**: No exception. Silent misbehavior — the field serializes as `0` in the `FinalSignalOutput` markdown.
- **timeline**: First real end-to-end v1.0 run after phase-8 integration. Bug has existed since Phase 8 SIG-01 shipped; no prior real-data run exercised it.
- **repro**:
    ```
    cd /Users/maxzou/Documents/projects/AI\ Hedgefund
    echo y | uv run python -m ai_hedge_fund.scripts.run_analysis \
        --ticker AAPL --as-of 2026-04-18 --sector Technology
    # final signal block shows: risk_score: 0/100
    ```
<!-- DATA_END -->

## Root Cause (pre-triaged)

`src/ai_hedge_fund/output/signal.py::derive_risk_score` (lines 28–56) reads `observed`/`limit` off the `RiskAssessment` dict. Those fields are only populated when a check returned a `Violation` — i.e. only when the assessment is VETOED. On APPROVED, both are `None`, and the `or 0.0` / `or 1.0` fallbacks collapse the ratio to 0 → `risk_score = 0`.

Supporting evidence:
- `src/ai_hedge_fund/graph/nodes.py:972-980` — `RiskAssessment` built with `observed=violation.observed if violation else None`.
- `src/ai_hedge_fund/schemas/risk.py:100-107` — `observed` / `limit` documented as "None if APPROVED".
- `src/ai_hedge_fund/risk/checks.py`, `risk/correlation.py`, `risk/drawdown.py` — each check returns `Violation | None`; the ratio on the passing branch is discarded.
- Design intent (08-RESEARCH.md A9, line 924): utilization is a Python-derived `max(...)` clamped to [0,1], not a single breach's observed/limit.

## Fix Plan (approved by user)

1. **Schema** — add `utilization: float = Field(ge=0.0, le=1.0)` as a required field on `RiskAssessment` (`src/ai_hedge_fund/schemas/risk.py`). Document semantics: max ratio across all checked constraints, computed both on APPROVED and VETOED.
2. **Checks** — change each check function in `risk/checks.py`, `risk/correlation.py`, `risk/drawdown.py` to return a `(ratio: float, violation: Violation | None)` tuple (or a small named-tuple / dataclass) so callers can see the utilization even when no violation fires. Keep "first violation wins" short-circuit semantics for the veto decision, but always collect ratios for utilization aggregation.
3. **Node** — in `risk_manager_node` (`src/ai_hedge_fund/graph/nodes.py`), after running all checks, compute `utilization = min(1.0, max(size_ratio, sector_ratio, corr_ratio, dd_ratio))`. Pass into `RiskAssessment`. On VETOED, utilization naturally ≥ 1.0 → clamps to 1.0.
4. **Output** — simplify `derive_risk_score` in `src/ai_hedge_fund/output/signal.py` to `int(round(assessment["utilization"] * 100))`. Keep the 50 fallback only for unknown/missing-status anomalies.
5. **Tests** — update `tests/risk/test_*.py` for new check signatures, `tests/risk/test_risk_assessment_schema.py` for the new required field, `tests/output/test_formatter.py` + `tests/output/test_final_signal.py` + `tests/graph/test_risk_node.py` for new assessment shape. Add unit tests for the utilization aggregation.
6. **Fix-as-you-find** — if other incidental drift surfaces (bad imports, stale docstrings, leftover TODOs in this area), fix inline but group them into a separate atomic commit per CLAUDE.md.

## Current Focus

- hypothesis: derive_risk_score always yields 0 on APPROVED because `observed`/`limit` in RiskAssessment are None on pass. Fix by computing a utilization ratio across all checks and storing it on the assessment.
- test: run `tests/risk/ tests/output/ tests/graph/` plus re-run the AAPL end-to-end and confirm `risk_score > 0` and correlates with candidate size + portfolio stretch.
- expecting: APPROVED AAPL with modest candidate size to show risk_score proportional to `candidate_size_pct / max_single_position_pct`.
- next_action: implementation complete; verify end-to-end re-run by hand.

## Evidence

- timestamp: 2026-04-24T22:30Z — traced derive_risk_score and RiskAssessment construction; confirmed observed/limit are None on APPROVED by design. Root cause localized.
- timestamp: 2026-04-24T23:50Z — implemented full Fix Plan. New `CheckResult` NamedTuple in `schemas/risk.py` carries `(ratio, violation | None)` from every check. All five check helpers (`check_position_size`, `check_sector_concentration`, `check_exclusions`, `check_correlation`, `check_drawdown`) updated to return `CheckResult`. `risk_manager_node` runs all checks unconditionally, walks the ordered list to preserve "first violation wins", and computes `utilization = min(1.0, max(ratios))`. `derive_risk_score` now reads `utilization` directly with a legacy fallback to observed/limit for backwards compatibility on stored audit payloads.
- timestamp: 2026-04-24T23:58Z — test results: 76 risk tests + 94 output tests + 105 graph tests = 275 tests, all green. `ruff format` reformatted 2 files (cosmetic). `ruff check` clean on every file touched. Integration suite shows 78 passing + 3 unrelated `pytest.mark.asyncio` plugin failures (pre-existing env issue, not from this fix).

## Resolution

- **root_cause**: `derive_risk_score` in `output/signal.py` read `observed` / `limit` off `RiskAssessment`, but those fields are only populated on VETOED. On APPROVED, the `or 0.0` / `or 1.0` fallbacks collapsed the ratio to 0, producing `risk_score=0` for every passing signal.
- **fix**: Added required `utilization: float` field on `RiskAssessment` populated by `risk_manager_node` from `min(1.0, max(...))` over per-check ratios. Each deterministic check now returns a `CheckResult(ratio, violation)` NamedTuple so utilization aggregation works even when no violation fires. `derive_risk_score` reads `utilization` directly; legacy observed/limit fallback retained for backwards compatibility with stored audit payloads.

## Files Modified

- `src/ai_hedge_fund/schemas/risk.py` — added `CheckResult` NamedTuple + `utilization` field on `RiskAssessment`.
- `src/ai_hedge_fund/risk/checks.py` — `check_position_size`, `check_sector_concentration`, `check_exclusions` return `CheckResult`.
- `src/ai_hedge_fund/risk/correlation.py` — `check_correlation` returns `CheckResult`.
- `src/ai_hedge_fund/risk/drawdown.py` — `check_drawdown` returns `CheckResult` (insufficient_history fail-closed -> ratio 1.0).
- `src/ai_hedge_fund/graph/nodes.py` — `risk_manager_node` runs all 5 checks, walks ordered list for first-violation-wins, aggregates utilization, logs it.
- `src/ai_hedge_fund/output/signal.py` — `derive_risk_score` reads `utilization` with legacy observed/limit fallback.
- `tests/risk/test_position_size.py`, `test_sector_check.py`, `test_correlation.py`, `test_drawdown.py`, `test_risk_assessment_schema.py` — updated for new return shape; added ratio assertions.
- `tests/output/test_final_signal.py` — added utilization-driven derivation tests + legacy-fallback tests + clamp tests.
- `tests/graph/test_risk_node.py` — added 3-test utilization aggregation regression suite.

## Eliminated

(none — root cause was pre-triaged correctly)
