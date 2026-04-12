---
phase: 03-signal-adapter-and-integration-contract
plan: "02"
subsystem: signal-adapter
tags: [tdd, signal, adapter, normalization, look-ahead-bias, weights]
dependency_graph:
  requires:
    - fund_backtest.signal.validator.SignalValidationError
    - fund_backtest.signal.validator.validate_signal_frame
    - fund_backtest.signal.types.SignalFrame
    - fund_backtest.signal.types.WeightFrame
    - fund_backtest.config.SignalAdapterConfig
  provides:
    - fund_backtest.signal.adapter.SignalAdapter
    - fund_backtest.signal.adapter.SignalAdapter.adapt
  affects:
    - backtest/src/fund_backtest/signal/adapter.py
    - backtest/tests/unit/test_signal_adapter.py
tech_stack:
  added: []
  patterns:
    - TDD (RED then GREEN) for SignalAdapter behavioral contracts
    - Cross-sectional rank normalization via DataFrame.rank(axis=1, pct=True)
    - Look-ahead bias guard via shift(1) at end of pipeline
    - Private helper methods to keep adapt() < 50 lines
    - Immutable pandas: .copy() before any mutation, no inplace ops
key_files:
  created:
    - backtest/src/fund_backtest/signal/adapter.py
    - backtest/tests/unit/test_signal_adapter.py
  modified: []
decisions:
  - "shift(1) is the final step in SignalAdapter.adapt() — Phase 4 must NOT shift again"
  - "min_coverage zeroing uses .loc[mask] = 0.0 on a copy (not drop) to preserve DatetimeIndex alignment"
  - "gross_exposure scaling: scale_factor = limit / abs_sum.where(needs_scaling, 1.0) — avoids division by zero on zero-sum rows"
  - "Test fixture uses min_coverage=1 override for look-ahead bias and weight range tests to isolate behaviors from coverage logic (4 tickers < default min_coverage=5)"
metrics:
  duration: "5 minutes"
  completed_date: "2026-03-29"
  tasks_completed: 2
  files_created: 2
  files_modified: 0
---

# Phase 03 Plan 02: SignalAdapter Implementation Summary

**One-liner:** SignalAdapter with 8-step normalization pipeline (validate, drop NaN cols, rank, weight map, clip, min_coverage zero-out, gross exposure scale, shift(1)) — 9 TDD tests, all green, no regressions.

## What Was Built

Implemented the Phase 3 deliverable: `SignalAdapter.adapt()` is the boundary between raw strategy scores and the portfolio simulation engine. Any strategy module (AI Washing Detector or future modules) feeds a `SignalFrame` into `adapt()` and receives a temporally safe `WeightFrame` ready for vectorbt.

### Files Created

- `backtest/src/fund_backtest/signal/adapter.py` — `SignalAdapter` class with `adapt()` and four private helpers
- `backtest/tests/unit/test_signal_adapter.py` — 9 TDD tests covering all behavioral contracts

## Pipeline

The `adapt()` method applies steps in this order:

| Step | Operation | Notes |
|------|-----------|-------|
| 1 | `validate_signal_frame(signal)` | Raises `SignalValidationError` on invalid input |
| 2 | Drop all-NaN columns | structlog warning per dropped column |
| 3 | Cross-sectional rank | `DataFrame.rank(axis=1, pct=True)` → [0, 1] |
| 4 | Map to weights | `2 * ranks - 1` → (-1, +1] |
| 5 | Clip | `.clip(-1.0, 1.0)` handles float edge cases |
| 6 | Zero low-coverage rows | Rows with `non-NaN count < min_coverage` → 0.0 |
| 7 | Scale gross exposure | Rows where `abs().sum() > limit` scaled proportionally |
| 8 | `shift(1)` | **Look-ahead bias guard — Phase 4 must NOT shift again** |

## TDD Execution

**RED commit:** `68c9fc4` — 9 failing tests (ImportError on `fund_backtest.signal.adapter`)

**GREEN commit:** `5ef691a` — `adapter.py` implemented; all 9 tests pass

**Full unit suite:** 85 tests passed, 0 regressions

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test fixture min_coverage mismatch**

- **Found during:** Task 2 (GREEN), test `test_look_ahead_bias_guard` failing with `0.0 > 0.0`
- **Issue:** The 4-ticker fixture (`_make_signal_frame`) has only 4 non-NaN values per row, but `SignalAdapterConfig` defaults to `min_coverage=5`. The `_zero_low_coverage_rows` step zeroed all rows before `shift(1)` could demonstrate the look-ahead bias behavior. Tests `test_adapt_returns_dataframe`, `test_weight_values_in_minus_one_to_one`, `test_look_ahead_bias_guard`, and `test_first_row_is_nan_after_shift` were all affected.
- **Fix:** Added `SignalAdapterConfig(min_coverage=1)` override in these four tests to isolate the behavior under test. The `test_low_coverage_row_is_zeroed` test correctly uses `min_coverage=10` to verify coverage zeroing in isolation.
- **Files modified:** `backtest/tests/unit/test_signal_adapter.py`
- **Commit:** `5ef691a`

## Known Stubs

None — `SignalAdapter.adapt()` is fully implemented. No hardcoded returns, placeholders, or mock data sources. The adapter is wired to the real validator and config objects.

## Self-Check: PASSED

Files created:
- `backtest/src/fund_backtest/signal/adapter.py` — FOUND
- `backtest/tests/unit/test_signal_adapter.py` — FOUND

Commits verified:
- `68c9fc4` — test(03-02) RED phase
- `5ef691a` — feat(03-02) GREEN phase
