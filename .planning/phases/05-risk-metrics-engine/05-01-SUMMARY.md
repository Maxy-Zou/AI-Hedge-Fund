---
phase: 05-risk-metrics-engine
plan: "01"
subsystem: testing
tags: [quantstats-lumi, pydantic, pandas, metrics, tdd, risk-metrics]

# Dependency graph
requires:
  - phase: 04-cost-model-and-portfolio-simulator
    provides: PortfolioResult type contract (net_returns, trade_log) consumed by MetricsEngine tests

provides:
  - MetricsBundle frozen Pydantic model with 10 fields (5 scalar, 3 trade, 2 benchmark, 2 rolling Series)
  - MetricsConfig and load_metrics_config() in config.py following CostConfig pattern
  - quantstats-lumi 1.1.3 installed in backtest venv
  - TDD RED scaffolds: test_metrics_types.py (GREEN, 4 tests) and test_metrics_engine.py (RED, 15 tests, 4 classes)

affects: [05-02-PLAN.md (MetricsEngine implementation must make test_metrics_engine.py GREEN)]

# Tech tracking
tech-stack:
  added: [quantstats-lumi==1.1.3, scipy==1.17.1, seaborn==0.13.2]
  patterns:
    - "MetricsBundle follows simulator/types.py frozen Pydantic pattern with arbitrary_types_allowed=True for pd.Series fields"
    - "MetricsConfig + load_metrics_config() mirrors CostConfig + load_cost_config() in config.py"
    - "TDD RED state: test_metrics_engine.py imports MetricsEngine which does not exist yet — RED by design"

key-files:
  created:
    - backtest/src/fund_backtest/metrics/__init__.py
    - backtest/src/fund_backtest/metrics/types.py
    - backtest/tests/unit/test_metrics_types.py
    - backtest/tests/unit/test_metrics_engine.py
  modified:
    - backtest/src/fund_backtest/config.py
    - backtest/pyproject.toml
    - backtest/uv.lock

key-decisions:
  - "arbitrary_types_allowed=True required in MetricsBundle model_config for pd.Series rolling fields (Pitfall 5 in RESEARCH.md)"
  - "max_drawdown stored as negative float (e.g. -0.25) — convention matches quantstats-lumi output, do not flip sign at storage"
  - "periods=252 hardcoded as _TRADING_DAYS_PER_YEAR constant — quantstats default is 365 which inflates Sharpe by ~20%"
  - "alpha=0.0 and beta=0.0 default when benchmark=None — avoids requiring benchmark for every compute() call"

patterns-established:
  - "Pattern: MetricsBundle stores pd.Series in frozen Pydantic model — requires model_config = {'frozen': True, 'arbitrary_types_allowed': True}"
  - "Pattern: rolling_sharpe and rolling_drawdown use same DatetimeIndex as net_returns — NaN before window fills"
  - "Pattern: test_metrics_engine.py RED state persists until engine.py is created in Plan 02"

requirements-completed: [RISK-01, RISK-02, RISK-03, RISK-04]

# Metrics
duration: 4min
completed: 2026-03-29
---

# Phase 05 Plan 01: Risk Metrics Engine — Type Contracts and TDD Scaffolds Summary

**quantstats-lumi 1.1.3 installed; MetricsBundle (10-field frozen Pydantic model), MetricsConfig, and full TDD scaffold written with 4 GREEN type tests and 15 RED engine tests across RISK-01 through RISK-04**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-29T09:33:27Z
- **Completed:** 2026-03-29T09:37:43Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Installed quantstats-lumi 1.1.3 (with scipy, seaborn) into the backtest venv
- Created `metrics/types.py` with `MetricsBundle` (frozen, arbitrary_types_allowed) holding 10 fields: sharpe, sortino, calmar, max_drawdown, cagr, hit_rate, win_loss_ratio, annual_turnover, alpha, beta, rolling_sharpe, rolling_drawdown
- Added `MetricsConfig` and `load_metrics_config()` to `config.py` following the `CostConfig`/`load_cost_config()` pattern
- Wrote 4 GREEN type tests in `test_metrics_types.py` and 15 RED engine tests in `test_metrics_engine.py` (4 test classes covering all 4 requirement groups)

## Task Commits

Each task was committed atomically:

1. **Task 1: Install quantstats-lumi and create metrics/types.py + MetricsConfig** - `faa8d09` (feat)
2. **Task 2: Write RED test scaffolds for all 4 requirement groups** - `218f16a` (test)

## Files Created/Modified

- `backtest/src/fund_backtest/metrics/__init__.py` - Package docstring; barrel imports are explicit (project convention)
- `backtest/src/fund_backtest/metrics/types.py` - MetricsBundle frozen Pydantic model with 10 typed fields + _TRADING_DAYS_PER_YEAR constant
- `backtest/src/fund_backtest/config.py` - Added MetricsConfig (rolling_window, periods_per_year, risk_free_rate) and load_metrics_config() factory
- `backtest/tests/unit/test_metrics_types.py` - 4 GREEN tests: construction, frozen invariant, field types, max_drawdown convention
- `backtest/tests/unit/test_metrics_engine.py` - 15 RED tests: TestScalarMetrics (4), TestTradeMetrics (3), TestBenchmarkMetrics (3), TestRollingMetrics (5)
- `backtest/pyproject.toml` - quantstats-lumi>=1.1.3 dependency added
- `backtest/uv.lock` - Lock file updated with quantstats-lumi and transitive deps

## Decisions Made

- `arbitrary_types_allowed=True` in MetricsBundle model_config — Pydantic v2 rejects pd.Series by default; this mirrors the `PortfolioResult` pattern already in `simulator/types.py`
- `max_drawdown` stored as negative float (e.g. -0.25) — matches quantstats-lumi output convention; do not flip sign at storage, let display layer render as "25%"
- `_TRADING_DAYS_PER_YEAR: int = 252` module constant — quantstats default is `periods=365` which inflates Sharpe/Sortino by ~20.35% on daily equity data; must pass `periods=252` explicitly
- `alpha=0.0, beta=0.0` when `benchmark=None` — sensible default avoids forcing benchmark argument for every compute() call

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff B017 violation in test_frozen_mutation_raises**
- **Found during:** Task 2 (linting test_metrics_types.py)
- **Issue:** `pytest.raises(Exception)` triggers ruff B017 "Do not assert blind exception" — the project's ruff config enforces this rule
- **Fix:** Changed to `pytest.raises((ValidationError, TypeError))` following the exact pattern in `test_simulator_types.py::TestCostConfigFrozen`
- **Files modified:** `backtest/tests/unit/test_metrics_types.py`
- **Verification:** `ruff check` exits 0 on both test files
- **Committed in:** `218f16a` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Minimal — ruff convention fix only. No scope creep. Aligned test with existing pattern.

## Issues Encountered

None — plan executed smoothly. All verification assertions passed on first run.

## Known Stubs

None — this plan establishes type contracts and TDD scaffolds only. No data-wiring or UI rendering involved.

## Next Phase Readiness

- `test_metrics_types.py` is GREEN (4/4 passing) — MetricsBundle type contract is correct
- `test_metrics_engine.py` is in RED state — ready for Plan 02 implementation (MetricsEngine.compute())
- quantstats-lumi 1.1.3 is installed and importable in backtest venv
- `MetricsConfig` is wired into `config.py` — MetricsEngine can consume it via `load_metrics_config()`
- No blockers for Plan 02 — all type imports, fixtures, and test structure are ready

---
*Phase: 05-risk-metrics-engine*
*Completed: 2026-03-29*
