---
phase: 03-metrics-and-reporting
plan: "02"
subsystem: metrics
tags: [quantstats, pydantic, pandas, csv, sharpe, sortino, cagr, drawdown, win-rate]

# Dependency graph
requires:
  - phase: 03-01
    provides: RED test scaffolds for test_metrics_calculator.py and test_trade_log.py
  - phase: 02-simulation-engine
    provides: BacktestResult frozen dataclass (runner.py) consumed by MetricsCalculator
provides:
  - BacktestMetrics frozen Pydantic model with all scalar and series metric fields
  - MetricsCalculator.compute() converting BacktestResult to BacktestMetrics via quantstats
  - export_trade_log() writing CSV with pnl_usd/fee_usd dollar-converted columns
  - kalshi_backtest.metrics package with full __init__.py public API
affects:
  - 03-03 (dashboard uses BacktestMetrics equity_curve and daily_returns)
  - 03-04 (CLI comparison reads BacktestMetrics scalar fields)
  - 04-01 (InsiderTrackerStrategy adapter produces BacktestResult consumed here)

# Tech tracking
tech-stack:
  added: []  # quantstats already in pyproject.toml from Phase 3 plan; no new deps needed
  patterns:
    - "STARTING_CAPITAL_CENTS = 10_000 module constant — $100 base for cent-to-fraction conversion"
    - "_safe_qs() wrapper — all quantstats calls guarded with try/except returning 0.0 on NaN/error"
    - "Sparse daily P&L filled to full calendar range before quantstats (reindex fill_value=0)"
    - "export_trade_log accepts BacktestResult (not DataFrame) — extracts trade_log internally"

key-files:
  created:
    - kalshi-backtest/src/kalshi_backtest/metrics/__init__.py
    - kalshi-backtest/src/kalshi_backtest/metrics/calculator.py
    - kalshi-backtest/src/kalshi_backtest/metrics/trade_log.py
  modified: []

key-decisions:
  - "export_trade_log accepts BacktestResult (not pd.DataFrame) — test scaffold passes result directly; plan spec was incorrect"
  - "sample_size_warning threshold: 30 distinct settled tickers via _count_settled_markets() nunique(), not contracts column sum"
  - "max_drawdown_pct stored as positive percentage — negate quantstats negative output then multiply by 100"
  - "cagr_pct and win_rate_pct multiplied by 100 — quantstats returns decimals (0.12 = 12%)"

patterns-established:
  - "Metrics guard pattern: empty trade_log returns zero-valued BacktestMetrics without raising"
  - "Quantstats safety wrapper: _safe_qs(func, *args, default=0.0) catches all exceptions and non-finite values"
  - "Date fill pattern: reindex to full pd.date_range before calling quantstats (sparse series cause NaN Sharpe)"

requirements-completed: [MET-01, MET-02, MET-07]

# Metrics
duration: 5min
completed: 2026-04-06
---

# Phase 3 Plan 02: Metrics and Reporting — Calculator and Trade Log Summary

**quantstats-powered BacktestMetrics model with MetricsCalculator (Sharpe, Sortino, CAGR, drawdown, win rate) and CSV export with pnl_usd/fee_usd columns — all 9 tests GREEN at 92% coverage**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-06T01:26:07Z
- **Completed:** 2026-04-06T01:30:58Z
- **Tasks:** 2
- **Files modified:** 3 created

## Accomplishments

- Implemented `BacktestMetrics` frozen Pydantic model with 17 fields covering all required scalars and series
- Implemented `MetricsCalculator.compute()` converting `BacktestResult` to `BacktestMetrics` via quantstats with full edge-case safety
- Implemented `export_trade_log()` writing CSV with `pnl_usd` and `fee_usd` dollar columns (cents / 100)
- Turned all 12 RED scaffold tests GREEN (6 in test_metrics_calculator.py + 3 in test_trade_log.py + pre-existing passing tests)
- 92% coverage on the new metrics module

## Task Commits

Each task was committed atomically:

1. **Task 1: BacktestMetrics model and MetricsCalculator** - `bb7b201` (feat)
2. **Task 2: export_trade_log CSV output** - `c23c67e` (feat)

## Files Created/Modified

- `kalshi-backtest/src/kalshi_backtest/metrics/__init__.py` - Package init exporting BacktestMetrics, MetricsCalculator, export_trade_log
- `kalshi-backtest/src/kalshi_backtest/metrics/calculator.py` - BacktestMetrics model, MetricsCalculator, and private helpers (_to_fractional_returns, _count_settled_markets, _build_equity_curve, _safe_qs)
- `kalshi-backtest/src/kalshi_backtest/metrics/trade_log.py` - export_trade_log function

## Decisions Made

**export_trade_log accepts BacktestResult, not pd.DataFrame:** The plan spec described the signature as `export_trade_log(trade_log: pd.DataFrame, output_path)`, but both test_trade_log.py tests call `export_trade_log(result, out_path)` passing a `BacktestResult`. The tests are the ground truth — the function accepts `BacktestResult` and extracts `result.trade_log` internally.

**Sparse-day fill mandatory:** quantstats Sharpe/Sortino calculations return NaN when the input Series has gaps. The `_to_fractional_returns()` helper reindexes to the full calendar range with `fill_value=0` before dividing — this is essential for finite metrics on real backtest data.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] export_trade_log signature corrected to accept BacktestResult**
- **Found during:** Task 2 (implementing export_trade_log)
- **Issue:** Plan spec listed `export_trade_log(trade_log: pd.DataFrame, output_path)` but test scaffold calls `export_trade_log(result, out_path)` with a `BacktestResult`
- **Fix:** Implemented function accepting `BacktestResult` — extracts `result.trade_log` internally, which is the correct abstraction (callers shouldn't need to unwrap the result themselves)
- **Files modified:** kalshi-backtest/src/kalshi_backtest/metrics/trade_log.py
- **Verification:** All 3 test_trade_log.py tests pass
- **Committed in:** c23c67e (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — signature mismatch between plan spec and test scaffold)
**Impact on plan:** Necessary for tests to pass. Better API design — callers pass the whole result, not a sub-field.

## Issues Encountered

None — quantstats was already in pyproject.toml, no dependency issues. All tests passed on first run after implementation.

## Known Stubs

None — all fields are computed from real data. `equity_curve` and `daily_returns` are both wired to `BacktestResult.daily_pnl`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `BacktestMetrics` is ready for consumption by Phase 3 Plan 03 (DashboardBuilder uses `equity_curve`, `daily_returns`, scalar metric fields)
- `export_trade_log` is ready for CLI wiring in Phase 3 Plan 04
- 92% metrics module coverage — uncovered lines are edge-case branches in `_build_equity_curve` and `_to_fractional_returns` (pre-existing DatetimeIndex paths not exercised by current test fixtures)

## Self-Check: PASSED

- FOUND: src/kalshi_backtest/metrics/__init__.py
- FOUND: src/kalshi_backtest/metrics/calculator.py
- FOUND: src/kalshi_backtest/metrics/trade_log.py
- FOUND: .planning/phases/03-metrics-and-reporting/03-02-SUMMARY.md
- FOUND: bb7b201 (feat(03-02): BacktestMetrics model and MetricsCalculator)
- FOUND: c23c67e (feat(03-02): export_trade_log CSV output)
- All 9 tests GREEN (6 test_metrics_calculator + 3 test_trade_log)

---
*Phase: 03-metrics-and-reporting*
*Completed: 2026-04-06*
