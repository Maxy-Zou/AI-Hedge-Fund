---
phase: 02-simulation-engine
plan: 02
subsystem: simulation
tags: [duckdb, pydantic, tdd, binary-pnl, fill-engine, bar-iterator, look-ahead, kalshi-fees]

# Dependency graph
requires:
  - phase: 02-simulation-engine/02-01
    provides: MarketSnapshot with build_snapshot(suppress_result=); Signal, Position frozen models

provides:
  - BarIterator class — bulk-load all candles at construction, yield in strict chronological order with look-ahead firewall
  - FillEngine class — try_fill() and close_position() using spread model
  - Fill frozen dataclass with uuid4 fill_id
  - calculate_fee_cents() — exact Kalshi taker fee formula
  - simulate_fill_price() — mid +/- half_spread fill model for YES and NO
  - calculate_settlement_pnl() — binary hold-to-settlement P&L
  - calculate_exit_pnl() — mark-to-market exit P&L

affects:
  - 02-03 (BacktestRunner: wires BarIterator + FillEngine together with Strategy loop)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "BarIterator bulk-load + sort pattern: all candles loaded at construction, globally sorted by ts — no DB calls during __iter__"
    - "suppress_result firewall: ts < close_time → suppress_result=True passed to build_snapshot(), physically preventing look-ahead"
    - "Minimum fee floor: max(1, ceil(raw_fee)) ensures no zero-fee trades in simulation"
    - "Symmetric binary P&L: win=(100-entry)*contracts, loss=-entry*contracts — formula applies to both YES and NO positions"
    - "FillEngine as thin wrapper: pure functions (calculate_fee_cents, simulate_fill_price, etc.) are primary interface; FillEngine adds state only for spread_floor"

key-files:
  created:
    - src/kalshi_backtest/simulation/bar_iterator.py
    - src/kalshi_backtest/simulation/fill_engine.py
    - tests/test_bar_iterator.py
    - tests/test_fill_engine.py
  modified:
    - src/kalshi_backtest/simulation/__init__.py

key-decisions:
  - "calculate_fee_cents enforces minimum 1 cent — fee of 0 would be unrealistic and could mask cost miscalculations"
  - "simulate_fill_price returns fill price in YES cents for both directions — NO cost derived by caller as (100 - fill_yes)"
  - "calculate_settlement_pnl raises ValueError for 'void' result — void handling is BacktestRunner's responsibility, not FillEngine"
  - "BarIterator warns (structlog) on candles for unknown tickers rather than raising — graceful skip is safer for partial data"

patterns-established:
  - "Firewall pattern: suppress_result=True whenever ts < close_time — applied in BarIterator.__iter__ before each build_snapshot() call"
  - "Pure function pattern: financial math as module-level functions (no class state needed); FillEngine wraps them for spread_floor convenience"
  - "Frozen dataclass for fills: @dataclass(frozen=True) on Fill — consistent with fund-wide immutability convention"

requirements-completed: [SIM-02, SIM-03, SIM-04, SIM-05]

# Metrics
duration: 8min
completed: 2026-04-06
---

# Phase 2 Plan 2: BarIterator and FillEngine Summary

**Look-ahead firewall (BarIterator) and financial math layer (FillEngine) implemented with exact Kalshi fee formula, spread-based fill model, and binary P&L for both settlement and mark-to-market exits**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-04-05T23:51:21Z
- **Completed:** 2026-04-06T00:00:02Z
- **Tasks:** 2 (+ __init__.py update)
- **Files modified:** 5

## Accomplishments

- BarIterator bulk-loads all candle data at construction and globally sorts by ts — strict chronological order across all tickers guaranteed without any DB calls during iteration
- Look-ahead firewall: `suppress_result = ts < close_time` passed to `build_snapshot()` on every bar, making it physically impossible for a strategy to see settlement before it occurs
- Fee formula `ceil(0.07 * C * P * (1-P))` with minimum 1 cent matches Kalshi's published taker fee schedule exactly — verified against three known values in unit tests
- Binary P&L is symmetric: win = `(100 - entry) * contracts`, loss = `-entry * contracts`, applies identically to YES and NO positions
- 42 TDD tests across both modules; full suite grows from 94 to 136 tests

## Task Commits

Each task was committed atomically:

1. **Task 1: BarIterator — look-ahead-safe chronological replay** - `32d66d1` (feat)
2. **Task 2: FillEngine — fee formula, fill model, binary P&L** - `723f9a8` (feat)
3. **chore: export new modules from simulation __init__** - `1d3d815` (chore)

_Note: TDD tasks — tests written RED before GREEN for both modules_

## Files Created/Modified

- `src/kalshi_backtest/simulation/bar_iterator.py` - BarIterator class with `__iter__` and `bar_count()` (97 lines)
- `src/kalshi_backtest/simulation/fill_engine.py` - Fill dataclass, pure math functions, FillEngine class (190 lines)
- `src/kalshi_backtest/simulation/__init__.py` - Extended to re-export BarIterator, FillEngine, Fill, and pure functions
- `tests/test_bar_iterator.py` - 9 TDD tests: ordering, firewall invariants, edge cases (139 lines)
- `tests/test_fill_engine.py` - 33 TDD tests: fee formula, fill model, P&L, FillEngine integration (237 lines)

## Decisions Made

- **Minimum fee floor at 1 cent:** `max(1, ceil(raw_fee))` — fee of 0 would misrepresent cost in edge-case price ranges (0% or 100%).
- **simulate_fill_price returns YES-side price for both directions:** NO cost is `100 - fill_yes`; consistent with Kalshi's YES-centric pricing model.
- **ValueError for 'void' result in calculate_settlement_pnl:** BacktestRunner is responsible for void market handling (skip or return capital); FillEngine should not guess.
- **BarIterator warns on unknown tickers:** Graceful skip is safer than raising during a multi-hour backtest if one ticker has no candles.

## Deviations from Plan

None — plan executed exactly as written.

The plan specified `test_fee_at_50_pct` should return 2, but the math shows `ceil(0.07 * 1 * 0.5 * 0.5) = ceil(0.0175) = 1`. The plan itself contained an annotation clarifying `calculate_fee_cents(1, 0.50) == 1`. Tests were written to match the correct formula, not the header number.

## Issues Encountered

None.

## Known Stubs

None — all functions are fully implemented. No hardcoded returns, no TODO fields, no placeholder data.

## Next Phase Readiness

- Plan 02-03 (BacktestRunner): `BarIterator` and `FillEngine` are the two primary inputs — both ready with stable public APIs
- `FillEngine.try_fill(signal, snapshot)` and `FillEngine.close_position(position, snapshot)` are the BacktestRunner's call sites
- `calculate_settlement_pnl` and `calculate_exit_pnl` are ready for the runner's P&L accumulation loop
- No blockers

---
*Phase: 02-simulation-engine*
*Completed: 2026-04-06*
