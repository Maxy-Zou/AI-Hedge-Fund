---
phase: 02-simulation-engine
plan: 03
subsystem: simulation
tags: [pandas, tdd, position-tracking, backtest-runner, settlement, binary-pnl, dataframe]

# Dependency graph
requires:
  - phase: 02-simulation-engine/02-01
    provides: Strategy Protocol, Signal, Position frozen models
  - phase: 02-simulation-engine/02-02
    provides: BarIterator (look-ahead firewall), FillEngine (fills, fees, P&L)

provides:
  - ClosedPosition frozen dataclass — entry + exit metadata, pnl_cents, fee_cents, exit_reason
  - PositionTracker — open/close/settle state machine with to_trade_log() and to_daily_pnl_series()
  - BacktestResult frozen dataclass — trade_log (DataFrame), daily_pnl (Series), summary metrics
  - BacktestRunner — full bar-by-bar orchestration loop using BarIterator + FillEngine + PositionTracker

affects:
  - 02-04 (CLI adapter: BacktestRunner.run() is the primary call site)
  - 03-xx (Metrics layer: BacktestResult.trade_log and .daily_pnl are the primary inputs)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Settlement firewall: settled_tickers set prevents double-settlement per ticker across multiple post-close bars"
    - "Entry fee carry: PositionTracker._entry_fees dict maps fill_id → fee_cents so settle() can include entry cost in ClosedPosition"
    - "Empty result guard: BacktestRunner._build_empty_result() handles no-markets case without entering the bar loop"
    - "Strategy name via type(strategy).__name__: no Strategy introspection needed beyond duck typing"

key-files:
  created:
    - src/kalshi_backtest/simulation/position_tracker.py
    - src/kalshi_backtest/simulation/runner.py
    - tests/test_position_tracker.py
    - tests/test_runner.py
  modified:
    - src/kalshi_backtest/simulation/__init__.py

key-decisions:
  - "ClosedPosition carries entry fee_cents (not exit fee): settlement has no exit fee; fee_cents represents the cost of entry carried forward for P&L accounting"
  - "BacktestResult uses custom __eq__ to handle DataFrame/Series fields — frozen dataclass default would fail on pandas equality semantics"
  - "Series_tickers filter loops get_markets() per ticker rather than OR query — simpler, avoids dynamic SQL, acceptable for small filter lists"
  - "Test data requires a settlement candle at ts == close_time — bars with ts < close_time have result suppressed by BarIterator; tests must include a close_time bar to exercise settlement"

patterns-established:
  - "PositionTracker pattern: open/close/settle state machine producing DataFrame and Series outputs for metrics consumption"
  - "BacktestRunner _process_bar inline pattern: strategy signals → fill loop → settle check — all within single for loop, no helper needed at <200 lines"
  - "Test data settlement bar pattern: always include one candle at ts == close_time to trigger settlement in integration tests"

requirements-completed: [SIM-02, SIM-05]

# Metrics
duration: 6min
completed: 2026-04-06
---

# Phase 2 Plan 3: PositionTracker and BacktestRunner Summary

**PositionTracker open/close/settle state machine with entry-fee carry, BacktestRunner bar-by-bar loop wiring all simulation components, and BacktestResult DataFrame/Series contract for Phase 3 metrics consumption**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-04-06T00:02:34Z
- **Completed:** 2026-04-06T00:07:46Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- PositionTracker manages the full position lifecycle: `open(fill)` → `Position`, `settle(ticker, result, ts)` → `list[ClosedPosition]`, `close(position, fill)` → `ClosedPosition`
- Entry fee carried from opening fill into ClosedPosition via `_entry_fees[fill_id]` dict — settlement has no exit fee but the cost of entry is preserved
- BacktestRunner wires all prior components: BarIterator → Strategy.generate_signals() → FillEngine.try_fill() → PositionTracker.open() → PositionTracker.settle()
- `settled_tickers` set ensures settlement fires exactly once per market even when multiple post-close bars exist
- BacktestResult is a frozen dataclass with trade_log (DataFrame) and daily_pnl (Series) — the primary inputs for Phase 3 metrics
- 45 TDD tests total across both modules; full suite grows from 136 to 181 tests

## Task Commits

Each task was committed atomically:

1. **Task 1: PositionTracker — open/close/settle lifecycle** - `3b00eb5` (feat)
2. **Task 2: BacktestRunner — full bar-by-bar orchestration** - `6a44e8f` (feat)

_Note: TDD tasks — tests written RED before GREEN for both modules_

## Files Created/Modified

- `src/kalshi_backtest/simulation/position_tracker.py` - PositionTracker class + ClosedPosition dataclass (220 lines)
- `src/kalshi_backtest/simulation/runner.py` - BacktestResult dataclass + BacktestRunner class (200 lines)
- `src/kalshi_backtest/simulation/__init__.py` - Extended to re-export PositionTracker, ClosedPosition, BacktestRunner, BacktestResult
- `tests/test_position_tracker.py` - 27 TDD tests: open/close/settle lifecycle, DataFrame/Series outputs (260 lines)
- `tests/test_runner.py` - 18 TDD integration tests: full loop, look-ahead invariant, date windowing, settlement once (310 lines)

## Decisions Made

- **Entry fee_cents carried on settle, not recalculated**: Settlement has no exit fee; the entry cost from the opening fill is stored in `_entry_fees[fill_id]` and transferred to `ClosedPosition.fee_cents` on settlement.
- **BacktestResult custom __eq__**: Frozen dataclasses cannot use default `__eq__` when fields contain DataFrames/Series (pandas equality returns arrays). Custom `__eq__` compares scalar fields only.
- **Series_tickers filter via repeated get_markets() calls**: Simpler than constructing an OR query dynamically. Acceptable because filter lists are typically small.
- **Settlement bar required in test data**: BarIterator suppresses result for all bars where ts < close_time. Integration tests must include at least one candle at ts == close_time to trigger settlement.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test data missing settlement candle**
- **Found during:** Task 2 (GREEN phase)
- **Issue:** `_make_candles()` generated candles for Jan 5–14 but `close_time` was Jan 15. BarIterator correctly suppressed result on all bars (ts < close_time), so settlement never fired. `test_result_with_buying_strategy_has_trades` failed with 0 trades despite 4 open positions.
- **Fix:** Extended `_make_candles()` to 11 candles (Jan 5–15) so the final bar has ts == close_time, triggering settlement exposure.
- **Files modified:** `tests/test_runner.py`
- **Verification:** All 18 runner tests pass; settled_contracts=4 confirmed.
- **Committed in:** `6a44e8f` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in test data design)
**Impact on plan:** Test data fix was necessary for correct behavior verification. The implementation itself was correct — the BarIterator's look-ahead firewall was working exactly as designed.

## Issues Encountered

- Test data design issue (documented above as deviation). No implementation bugs.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None — all methods are fully implemented. BacktestResult carries real DataFrame and Series data from PositionTracker. No hardcoded empty returns or placeholder fields.

## Next Phase Readiness

- Plan 02-04 (CLI adapter): `BacktestRunner.run()` is the primary call site — accepts `Strategy`, `start_date`, `end_date`, `series_tickers`; returns `BacktestResult`
- Plan 03-xx (Metrics layer): `BacktestResult.trade_log` (DataFrame) and `BacktestResult.daily_pnl` (Series) are the primary inputs — shapes are finalized
- All simulation types importable from `kalshi_backtest.simulation` via single import
- No blockers

---
*Phase: 02-simulation-engine*
*Completed: 2026-04-06*
