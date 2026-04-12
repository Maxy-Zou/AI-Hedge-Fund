---
phase: 02-simulation-engine
plan: 01
subsystem: simulation
tags: [pydantic, protocol, typing, frozen-models, tdd, structural-subtyping]

# Dependency graph
requires:
  - phase: 01-data-foundation
    provides: MarketRecord and CandlestickRecord types; _to_naive_utc datetime pattern
provides:
  - Strategy @runtime_checkable Protocol for plugin interface (structural subtyping)
  - Signal frozen Pydantic model (direction, contracts, limit_price, reason)
  - Position frozen Pydantic model (entry_price, entry_ts, fill_id)
  - MarketSnapshot frozen Pydantic model with build_snapshot() factory
  - kalshi_backtest.simulation public API (__init__.py)
affects:
  - 02-02 (BarIterator consumes MarketSnapshot, calls build_snapshot with suppress_result)
  - 02-03 (FillEngine consumes Signal and produces Position)
  - 02-04 (BacktestRunner uses Strategy Protocol, Signal, Position, MarketSnapshot)
  - 02-05 (CLI adapter uses Strategy as plugin interface)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "typing.Protocol with @runtime_checkable for structural subtyping plugin interfaces"
    - "frozen Pydantic BaseModel for immutable trade data contracts"
    - "suppress_result flag pattern for look-ahead firewall in factory functions"
    - "_to_naive_utc intentionally duplicated across layers to avoid cross-layer coupling"

key-files:
  created:
    - src/kalshi_backtest/simulation/__init__.py
    - src/kalshi_backtest/simulation/protocol.py
    - src/kalshi_backtest/simulation/snapshot.py
    - tests/test_simulation_types.py
  modified: []

key-decisions:
  - "Strategy uses typing.Protocol (not ABC) — strategies implement generate_signals() without importing engine internals"
  - "MarketSnapshot does not enforce result=None itself — BarIterator controls suppress_result flag"
  - "_to_naive_utc duplicated from ingestion/types.py intentionally to keep simulation layer decoupled"
  - "Snapshot tests (suppress_result behavior) placed in test_simulation_types.py as interface design preview — actual BarIterator enforcement tested in plan 02-02"

patterns-established:
  - "Protocol pattern: @runtime_checkable Strategy Protocol for plugin interface — future strategies follow same pattern"
  - "Factory pattern: build_snapshot(market, candle, *, suppress_result) — keyword-only flag for safety"
  - "Frozen models: all simulation data contracts use model_config = {'frozen': True}"

requirements-completed: [SIM-01, SIM-02]

# Metrics
duration: 15min
completed: 2026-04-06
---

# Phase 2 Plan 1: Simulation Type Contracts Summary

**@runtime_checkable Strategy Protocol with frozen Pydantic Signal/Position models and MarketSnapshot look-ahead firewall — all downstream simulation modules now have stable, validated type contracts**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-06
- **Completed:** 2026-04-06
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Strategy Protocol with `@runtime_checkable` enables structural subtyping — any class with `generate_signals()` satisfies the protocol without inheritance
- Signal and Position are frozen Pydantic models with validated direction (Literal["yes","no"]), contracts (>=1), and price fields ([0,100])
- MarketSnapshot frozen model with `build_snapshot()` factory; `suppress_result=True` flag is the look-ahead firewall BarIterator will use
- All 5 public names importable from `kalshi_backtest.simulation` with no circular imports
- TDD: 23 tests written RED first, then GREEN implementations — full test suite grows from 71 to 94 tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Strategy Protocol, Signal, and Position contracts** - `794bafe` (feat)
2. **Task 2: MarketSnapshot look-ahead firewall model** - `8e544af` (feat)
3. **Task 3: Wire simulation/__init__.py public exports** - `0d85438` (feat)

_Note: TDD tasks — tests written in Task 1 RED phase, GREEN confirmed after each implementation_

## Files Created/Modified

- `src/kalshi_backtest/simulation/__init__.py` - Public API re-exporting Strategy, Signal, Position, MarketSnapshot, build_snapshot
- `src/kalshi_backtest/simulation/protocol.py` - Strategy @runtime_checkable Protocol, Signal frozen model, Position frozen model (122 lines)
- `src/kalshi_backtest/simulation/snapshot.py` - MarketSnapshot frozen model, build_snapshot() factory, _to_naive_utc helper (132 lines)
- `tests/test_simulation_types.py` - 23 TDD tests covering all type contracts (308 lines)

## Decisions Made

- **Strategy Protocol not ABC:** Structural subtyping means strategies don't import engine internals. Strategies remain fully decoupled.
- **MarketSnapshot is passive:** The model does not enforce `result=None`. BarIterator controls `suppress_result` flag. This keeps the model simple and testable in isolation.
- **_to_naive_utc duplicated intentionally:** Copying the helper from `ingestion/types.py` avoids a cross-layer import that would couple simulation to ingestion internals.
- **Snapshot suppress_result tests in this plan:** Tests preview the BarIterator interface contract so signal semantics are locked before implementation begins in plan 02-02.

## Deviations from Plan

None - plan executed exactly as written.

The only minor adaptation: Task 2 imports in the test file are at module level, which required creating a stub `snapshot.py` before running Task 1 RED tests. This was necessary for pytest collection, not a plan deviation.

## Issues Encountered

None.

## Known Stubs

None — all types are fully implemented with real validation. No placeholder data, hardcoded empty values, or TODO fields.

## Next Phase Readiness

- Plan 02-02 (BarIterator): `MarketSnapshot` and `build_snapshot(suppress_result=...)` are the primary inputs — ready
- Plan 02-03 (FillEngine): `Signal` and `Position` contracts are locked — ready
- Plan 02-04 (BacktestRunner): `Strategy` Protocol is defined — any class with `generate_signals()` satisfies it
- No blockers

---
*Phase: 02-simulation-engine*
*Completed: 2026-04-06*
