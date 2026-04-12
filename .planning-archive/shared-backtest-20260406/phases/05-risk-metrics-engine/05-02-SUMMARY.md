---
phase: 05-risk-metrics-engine
plan: "02"
subsystem: metrics
tags: [quantstats-lumi, pydantic, pandas, metrics, risk-metrics, tdd-green]

# Dependency graph
requires:
  - phase: 05-risk-metrics-engine plan 01
    provides: MetricsBundle type contract, MetricsConfig, RED test scaffolds (test_metrics_engine.py)
  - phase: 04-cost-model-and-portfolio-simulator
    provides: PortfolioResult type contract (net_returns, trade_log) consumed by MetricsEngine

provides:
  - MetricsEngine class in metrics/engine.py with compute() returning frozen MetricsBundle
  - All 15 RED tests in test_metrics_engine.py turned GREEN (19 total in metrics test suite)
  - 97.75% coverage on src/fund_backtest/metrics/ (well above 80% threshold)

affects:
  - 06-PLAN.md (Streamlit Dashboard): consumes MetricsBundle.rolling_sharpe, rolling_drawdown, max_drawdown, cagr
  - 07-PLAN.md (Tearsheet): consumes full MetricsBundle for PDF and CSV/JSON exports

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "MetricsEngine wraps quantstats-lumi with periods=252 explicitly on every call (never default 365)"
    - "Private module-level helpers _rolling_drawdown() and _annual_turnover() (not class methods) follow simulator/engine.py structlog pattern"
    - "Guard: qs.stats.greeks() checked for near-zero benchmark variance before calling to avoid numerical instability"
    - "Guard: win_loss_ratio() result checked for math.isfinite() since it returns inf with no losing days"
    - "Guard: rolling_sharpe may return DataFrame — squeeze() applied before reindex to returns.index"

key-files:
  created:
    - backtest/src/fund_backtest/metrics/engine.py
  modified:
    - backtest/tests/unit/test_metrics_engine.py (ruff lint fix — blank line)
    - .planning/ROADMAP.md (Phase 5 marked complete)

key-decisions:
  - "qs.stats.greeks() guarded against near-zero benchmark variance: var < 1e-12 returns alpha=0.0, beta=0.0 instead of numerically unstable result"
  - "win_loss_ratio guarded against inf (no losing days edge case): math.isfinite() fallback to 0.0"
  - "rolling_sharpe squeeze: qs.stats.rolling_sharpe may return DataFrame on some inputs; squeeze() normalizes to Series"
  - "All private helpers are module-level functions not class methods — matches simulator/engine.py pattern and keeps MetricsEngine class focused"

# Metrics
duration: 4min
completed: 2026-03-29
---

# Phase 05 Plan 02: Risk Metrics Engine — MetricsEngine Implementation Summary

**MetricsEngine.compute() implemented in metrics/engine.py: all 15 RED tests turned GREEN (19 total), 97.75% coverage on metrics/, with periods=252 enforced throughout and three numerical guard cases added**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-29T09:40:31Z
- **Completed:** 2026-03-29T09:44:29Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Created `backtest/src/fund_backtest/metrics/engine.py` with `MetricsEngine` class and `compute()` method
- Implemented all 4 requirement groups: RISK-01 (5 scalar metrics), RISK-02 (3 trade metrics), RISK-03 (alpha/beta), RISK-04 (2 rolling Series)
- Turned all 15 RED engine tests GREEN; 4 pre-existing type tests remain GREEN (19 total)
- Achieved 97.75% coverage on `src/fund_backtest/metrics/` (threshold: 80%)
- All 125 unit tests pass (full suite including previous phases)
- ROADMAP.md updated: Phase 5 marked complete (2/2 plans)

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement MetricsEngine and turn RED tests GREEN** - `1da6f62` (feat)
   - Ruff lint fix follow-up: `1d6acbb` (chore)
2. **Task 2: Coverage gate and full unit suite + ROADMAP update** - `ec8eced` (chore)

## Files Created/Modified

- `backtest/src/fund_backtest/metrics/engine.py` - MetricsEngine class: compute(), _rolling_drawdown(), _annual_turnover() helpers; 97% coverage
- `backtest/tests/unit/test_metrics_engine.py` - Ruff E302 blank-line fix only (no logic changes)
- `.planning/ROADMAP.md` - Phase 5 plan checklist and progress table updated to Complete

## Decisions Made

- `qs.stats.greeks()` guarded against zero-variance benchmark: when `benchmark.var() < 1e-12`, alpha and beta default to 0.0 instead of letting the division-by-near-zero in `matrix[0,1] / matrix[1,1]` produce a numerically meaningless large value
- `win_loss_ratio` guarded with `math.isfinite()`: returns 0.0 (not inf) when no losing days exist — prevents MetricsBundle construction from storing non-finite floats
- `rolling_sharpe` squeezed: `qs.stats.rolling_sharpe()` returns a DataFrame on some quantstats-lumi builds; `.squeeze()` normalizes to Series before `.reindex()`
- All private helpers (`_rolling_drawdown`, `_annual_turnover`) are module-level functions, not class methods — consistent with `simulator/engine.py` pattern

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed qs.stats.greeks() numerical instability with constant-return benchmark**
- **Found during:** Task 1 (RED→GREEN run)
- **Issue:** `test_beta_near_zero_for_uncorrelated_benchmark` failed with beta=-13.65 for a constant (0.0001) benchmark Series. The test expects `abs(beta) < 0.5` since a constant benchmark has zero variance, making OLS regression undefined (not large-negative).
- **Root cause:** `qs.stats.greeks()` computes `matrix[0,1] / matrix[1,1]` where `matrix[1,1]` is the benchmark variance. A constant series produces near-zero floating-point variance (~1e-28), causing division-by-near-zero and a numerically meaningless beta of -13.65.
- **Fix:** Added variance check before calling `qs.stats.greeks()`: if `bm_var < 1e-12`, skip the call and return `alpha=0.0, beta=0.0` directly. This matches the plan's intent (alpha=0.0, beta=0.0 as the "undefined" sentinel value) and is analogous to the `benchmark=None` path.
- **Files modified:** `backtest/src/fund_backtest/metrics/engine.py`
- **Verification:** All 19 metrics tests pass including `test_beta_near_zero_for_uncorrelated_benchmark`
- **Committed in:** `1da6f62`

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Minimal — numerical guard only. No scope creep. Behavior matches plan intent: zero-variance benchmark produces alpha=0.0, beta=0.0.

## Issues Encountered

None beyond the auto-fixed numerical guard.

## Known Stubs

None — MetricsEngine fully wired with no placeholder values. All 10 MetricsBundle fields populated from real computation.

## Next Phase Readiness

- `MetricsEngine.compute(result)` and `MetricsEngine.compute(result, benchmark=bm)` work correctly
- MetricsBundle with all 10 fields (5 scalar, 3 trade, 2 rolling Series) ready for Phase 6 dashboard consumption
- Rolling Series fields have correct DatetimeIndex alignment and NaN-before-window behavior confirmed
- 97.75% coverage; no ruff errors; all 125 unit tests green

## Self-Check: PASSED
