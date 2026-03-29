---
phase: 04-cost-model-and-portfolio-simulator
plan: "01"
subsystem: testing
tags: [pydantic, pandas, portfolio-simulator, tdd, cost-model]

# Dependency graph
requires:
  - phase: 03-signal-adapter-and-integration-contract
    provides: WeightFrame type alias and shift(1) contract that simulator must not re-apply
provides:
  - CostConfig frozen Pydantic model (slippage_bps, commission_bps, borrow_cost_bps_annual)
  - PortfolioResult Pydantic model (gross_returns, net_returns, positions, trade_log)
  - PriceFrame type alias (pd.DataFrame, dollars)
  - load_cost_config() factory in config.py
  - test_simulator_types.py: 8 passing tests for type contracts
  - test_simulator_engine.py: 11 failing tests (RED) defining PortfolioSimulator behavior
affects:
  - 04-02 (implements PortfolioSimulator engine against these type contracts and RED tests)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Frozen Pydantic model for immutable cost config (model_config = {"frozen": True})
    - arbitrary_types_allowed for Pydantic models holding pandas objects
    - load_*_config() factory pattern: YAML optional, defaults on any error or None path

key-files:
  created:
    - backtest/src/fund_backtest/simulator/__init__.py
    - backtest/src/fund_backtest/simulator/types.py
    - backtest/tests/unit/test_simulator_types.py
    - backtest/tests/unit/test_simulator_engine.py
  modified:
    - backtest/src/fund_backtest/config.py

key-decisions:
  - "CostConfig defaults: slippage=10bps, commission=5bps, borrow=50bps/yr — flat-rate borrow, tiered is future"
  - "PortfolioResult uses arbitrary_types_allowed (not frozen) — mutable result container holding pandas objects"
  - "load_cost_config() reads from 'cost' YAML key, consistent with load_signal_adapter_config() reading 'signal_adapter'"
  - "test_simulator_engine.py fails with ImportError at collection time (module-level import) — confirms clean RED state"

patterns-established:
  - "Pattern: TDD RED scaffold — module-level import of non-existent class causes collection-time ImportError (not test-time failure)"
  - "Pattern: Hand-calculated reference test asserts formula inline (not hardcoded) so value derives from same math as implementation"

requirements-completed:
  - BT-02
  - BT-03
  - BT-04
  - BT-06
  - BT-07

# Metrics
duration: 12min
completed: 2026-03-29
---

# Phase 4 Plan 01: Cost Model and Portfolio Simulator Types Summary

**Frozen CostConfig and PortfolioResult type contracts with 8 passing type tests and 11 RED engine test stubs defining PortfolioSimulator behavior via hand-calculated references**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-29T09:08:26Z
- **Completed:** 2026-03-29T09:20:30Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Created `simulator/` package with `CostConfig` (frozen, 3 ge=0.0 float fields), `PortfolioResult` (arbitrary_types_allowed, 4 pandas fields), and `PriceFrame` type alias
- Added `load_cost_config()` factory to `config.py` following the established `load_signal_adapter_config()` pattern exactly
- Wrote 8 passing tests in `test_simulator_types.py` covering defaults, negative-bps validation, frozen enforcement, and PortfolioResult construction
- Wrote 11 RED test stubs in `test_simulator_engine.py` — fails with `ModuleNotFoundError` at collection time, confirming clean TDD RED state

## Task Commits

1. **Task 1: Create simulator/types.py and load_cost_config()** - `807b488` (feat)
2. **Task 2: Write failing test scaffolds (RED state)** - `dc291ac` (test)

**Plan metadata:** _(final docs commit follows)_

## Files Created/Modified

- `backtest/src/fund_backtest/simulator/__init__.py` - Package marker with module docstring
- `backtest/src/fund_backtest/simulator/types.py` - CostConfig, PortfolioResult, PriceFrame
- `backtest/src/fund_backtest/config.py` - Added CostConfig import and load_cost_config()
- `backtest/tests/unit/test_simulator_types.py` - 8 passing type contract tests (GREEN)
- `backtest/tests/unit/test_simulator_engine.py` - 11 engine behavior tests (RED — ImportError)

## Decisions Made

- CostConfig defaults: slippage=10bps, commission=5bps, borrow=50bps/yr. Flat-rate borrow model chosen for v1; tiered borrow (FINRA short interest data) deferred as future enhancement.
- `load_cost_config()` reads from `"cost"` YAML key to mirror the existing `"signal_adapter"` key pattern in `load_signal_adapter_config()`.
- `test_simulator_engine.py` uses a module-level import (not `pytest.importorskip` or try/except) so the RED failure manifests as a collection-time `ImportError` — the cleanest RED signal.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Direct `.venv/bin/python -c "from fund_backtest..."` invocation fails due to macOS path-with-spaces issue in the `.pth` file. Pytest resolves the import correctly via its own sys.path manipulation. Verification was done via `pytest` rather than the raw `-c` command. All tests pass and imports are correct.

## Known Stubs

None — no stub values or placeholder data. All types have real defaults and validators.

## Next Phase Readiness

- `simulator/types.py` provides the complete type surface for Plan 02
- `test_simulator_engine.py` provides the exact behavioral specification Plan 02 must satisfy
- 11 RED tests become the acceptance criteria for Plan 02 (PortfolioSimulator implementation)
- No blockers

---
*Phase: 04-cost-model-and-portfolio-simulator*
*Completed: 2026-03-29*
