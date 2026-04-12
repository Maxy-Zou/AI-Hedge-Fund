---
phase: 02-simulation-engine
plan: "04"
subsystem: simulation
tags: [python, itertools, grid-search, walk-forward, backtest, sharpe, parameter-optimization]

# Dependency graph
requires:
  - phase: 02-03
    provides: BacktestRunner.run() and BacktestResult used as execution engine by both new classes

provides:
  - ParameterSweeper: grid search over strategy configurations using itertools.product
  - SweepResult: immutable dataclass holding params dict, BacktestResult, and Sharpe ratio
  - WalkForwardValidator: expanding-window train/test splits to detect overfitting
  - WalkForwardResult: immutable dataclass holding all 4 date bounds plus train/test BacktestResult
  - simulation __init__.py: all 4 new names exported and importable from kalshi_backtest.simulation

affects:
  - 02-05 (CLI integration will expose sweep and walk-forward as commands)
  - 03-metrics (Sharpe calculation in sweep duplicates; metrics layer may centralise)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ParameterSweeper as thin loop over BacktestRunner — no ML libraries, pure stdlib itertools.product"
    - "WalkForwardValidator expanding-window design — train_start fixed, train_end grows each fold"
    - "_compute_sharpe() = mean/std of daily_pnl, returns 0.0 on edge cases (no division-by-zero)"
    - "Frozen dataclasses for all result types (SweepResult, WalkForwardResult) — fund-wide immutability"

key-files:
  created:
    - src/kalshi_backtest/simulation/sweep.py
    - src/kalshi_backtest/simulation/walkforward.py
    - tests/test_sweep.py
    - tests/test_walkforward.py
  modified:
    - src/kalshi_backtest/simulation/__init__.py

key-decisions:
  - "Sharpe computed as daily_pnl.mean()/daily_pnl.std() returning 0.0 when std==0 or <2 observations — avoids division-by-zero at sweep level; Phase 3 metrics layer may replace with annualised calculation"
  - "WalkForwardValidator calls runner.run() twice per fold (train window + test window) — same strategy instance passed to both; caller is responsible for using train_result to tune before evaluating test_result"
  - "Expanding-window design (train_start always fixed at global start) — simplest approach that prevents look-ahead; anchored train window grows fold-by-fold"

patterns-established:
  - "Strategy factory pattern: strategy_factory(params) -> Strategy — keeps ParameterSweeper decoupled from any concrete strategy implementation"
  - "min_fold_days validation: raises ValueError before any runner.run() calls — fail-fast before expensive computation"

requirements-completed:
  - SIM-06
  - SIM-07

# Metrics
duration: 3min
completed: 2026-04-06
---

# Phase 2 Plan 4: Parameter Sweep and Walk-Forward Validation Summary

**ParameterSweeper (itertools.product grid search) and WalkForwardValidator (expanding-window overfitting detection), both as thin wrappers over BacktestRunner**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-06T00:12:17Z
- **Completed:** 2026-04-06T00:15:19Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- ParameterSweeper iterates all param combinations with itertools.product, computes Sharpe per run, returns list sorted descending — best config always at index 0
- WalkForwardValidator produces n_splits expanding-window folds with strict train_end <= test_start guarantee; raises ValueError when date range is too short
- simulation package now exports all 4 new types: ParameterSweeper, SweepResult, WalkForwardValidator, WalkForwardResult
- 19 new TDD tests added (8 sweep + 11 walk-forward); full suite grows from 181 to 200 passing

## Task Commits

Each task was committed atomically:

1. **Task 1: ParameterSweeper grid sweep** - `f7e2cdc` (feat)
2. **Task 2: WalkForwardValidator + __init__.py exports** - `9c2ab3e` (feat)

_Note: TDD tasks — RED (ModuleNotFoundError confirmed) before GREEN on each task_

## Files Created/Modified

- `src/kalshi_backtest/simulation/sweep.py` - ParameterSweeper and SweepResult; grid search via itertools.product
- `src/kalshi_backtest/simulation/walkforward.py` - WalkForwardValidator and WalkForwardResult; expanding-window splits
- `src/kalshi_backtest/simulation/__init__.py` - Added 4 new exports to __all__
- `tests/test_sweep.py` - 8 tests covering combinatorics, sorting, result contract, immutability
- `tests/test_walkforward.py` - 11 tests covering fold count, date ordering, validation, result contract

## Decisions Made

- Sharpe computed as `daily_pnl.mean() / daily_pnl.std()` returning 0.0 when std==0 or series has fewer than 2 observations — avoids division-by-zero; Phase 3 metrics layer may replace with an annualised calculation
- WalkForwardValidator calls `runner.run()` twice per fold (train window + test window); the same strategy instance is passed to both — caller is responsible for using `train_result` to tune before evaluating `test_result`
- Expanding-window design chosen over rolling-window — train_start stays fixed at global start, giving the validator a growing training set per fold; simplest approach preventing look-ahead

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- All Phase 2 simulation building blocks now complete: Protocol, BarIterator, FillEngine, PositionTracker, BacktestRunner, ParameterSweeper, WalkForwardValidator
- Phase 2 Plan 5 (CLI integration) can now wire `backtest sweep` and `backtest walkforward` commands
- Phase 3 (metrics layer) can consume BacktestResult from both sweep and walk-forward outputs

---
*Phase: 02-simulation-engine*
*Completed: 2026-04-06*
