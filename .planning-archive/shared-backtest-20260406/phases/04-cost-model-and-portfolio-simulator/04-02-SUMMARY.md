---
phase: 04-cost-model-and-portfolio-simulator
plan: "02"
subsystem: simulator
tags: [pandas, vectorized, portfolio-simulator, tdd, cost-model]

# Dependency graph
requires:
  - phase: 04-cost-model-and-portfolio-simulator
    plan: "01"
    provides: CostConfig, PortfolioResult type contracts and 11 RED test stubs
  - phase: 03-signal-adapter-and-integration-contract
    provides: WeightFrame shift(1) invariant
provides:
  - PortfolioSimulator class with simulate() method in simulator/engine.py
  - Fully vectorized gross/net returns, borrow costs, transaction costs
  - Per-trade cost log (trade_log) with direction, weight_before/after, cost_bps
  - All 11 RED tests from plan 01 turned GREEN (13 tests total pass)
affects:
  - Phase 5 (Risk Metrics Engine consumes PortfolioResult.net_returns)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - future_stack=True with explicit .dropna() for pandas 2.x stack compatibility
    - fillna(0.0) before diff() to capture entry trades from NaN initial weights
    - structlog bound logger with component key in orchestrator classes

key-files:
  created:
    - backtest/src/fund_backtest/simulator/engine.py
  modified:
    - .planning/ROADMAP.md

key-decisions:
  - "future_stack=True does not drop NaN values in pandas 2.x — must call .dropna() explicitly after stack()"
  - "Entry trades (NaN->value transition) captured by filling weights NaN as 0.0 before diff(); weight_before=0 for entry day"
  - "Trade log direction set by weight_change sign (positive=long, negative=short) not weight_after sign"

# Metrics
duration: 8min
completed: 2026-03-29
---

# Phase 4 Plan 02: PortfolioSimulator Engine Summary

**Vectorized PortfolioSimulator with borrow/transaction cost model turning 11 RED TDD stubs GREEN; 97% simulator coverage across 106 unit tests**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-29T09:14:44Z
- **Completed:** 2026-03-29T09:22:30Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created `simulator/engine.py` with `PortfolioSimulator` class implementing fully vectorized `simulate()` method
- Gross returns via `prices.pct_change() * weights` (no date loops)
- Transaction costs via `weights.fillna(0).diff()` capturing entry trades from flat
- Borrow costs via `weights.clip(upper=0).abs() * daily_rate`
- Trade log via `future_stack=True` + `.dropna()` (pandas 2.x compatibility fix)
- Phase 3 shift invariant preserved with `# DO NOT apply .shift(1) here` comment
- All 13 `test_simulator_engine.py` tests GREEN; full 106-test unit suite passes
- Simulator coverage at 97% (requirement: 80%)
- ROADMAP.md updated: Phase 4 marked complete (2/2 plans, 2026-03-29)

## Task Commits

1. **Task 1: Implement simulator/engine.py** - `89b244e` (feat)
2. **Task 2: Verify full unit suite and update ROADMAP** - `4e088ca` (chore)

**Plan metadata:** _(final docs commit follows)_

## Files Created/Modified

- `backtest/src/fund_backtest/simulator/engine.py` - PortfolioSimulator class (269 lines)
- `.planning/ROADMAP.md` - Phase 4 marked complete, 04-02-PLAN.md checked off

## Decisions Made

- `future_stack=True` in pandas 2.x does NOT drop NaN values (unlike the legacy `stack(dropna=True)` default). Must call `.dropna()` explicitly after `.stack(future_stack=True)` to filter non-trade rows.
- Entry trades (signal goes from NaN to a value) are captured by filling weights with 0.0 before `diff()`. This sets `weight_before=0` on entry day, which correctly represents "entering from flat".
- Trade log `direction` is set by `weight_change` sign (positive delta = long entry/add, negative delta = short entry/add), not by `weight_after` sign.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pandas future_stack NaN retention**
- **Found during:** Task 1 verification (1 test failing)
- **Issue:** `future_stack=True` (pandas 2.x) retains NaN values after stack, unlike the deprecated `stack(dropna=True)` behavior. The plan's trade log approach assumed NaN would be dropped automatically.
- **Fix:** Added `.dropna()` call after `.stack(future_stack=True)` in both `wc_masked` and `wb_masked` stacks.
- **Files modified:** `backtest/src/fund_backtest/simulator/engine.py`
- **Commit:** `89b244e`

**2. [Rule 1 - Bug] Fixed entry trade detection**
- **Found during:** Task 1 verification (1 test failing after Fix 1)
- **Issue:** `weights.diff()` produces NaN for the first row where weights transition from NaN to a real value (the entry day). This caused the NVDA short entry trade to be missing from the trade log, making `test_short_tickers_appear_in_trade_log_with_short_direction` fail.
- **Fix:** Fill weights NaN with 0.0 before `diff()` so the entry transition (NaN→0.5) is captured as a 0.5 weight change. `weight_before` on entry day is set to 0.0 (flat before entry).
- **Files modified:** `backtest/src/fund_backtest/simulator/engine.py`
- **Commit:** `89b244e`

## Known Stubs

None — all values computed from real formulas. No placeholder data.

## Self-Check: PASSED

- engine.py: FOUND at backtest/src/fund_backtest/simulator/engine.py
- SUMMARY.md: FOUND at .planning/phases/04-cost-model-and-portfolio-simulator/04-02-SUMMARY.md
- Commit 89b244e: FOUND (feat: PortfolioSimulator engine)
- Commit 4e088ca: FOUND (chore: ROADMAP update)
