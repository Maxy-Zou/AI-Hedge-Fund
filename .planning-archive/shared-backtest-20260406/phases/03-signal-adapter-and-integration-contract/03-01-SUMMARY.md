---
phase: 03-signal-adapter-and-integration-contract
plan: "01"
subsystem: signal-contract
tags: [tdd, signal, validation, types, config]
dependency_graph:
  requires: []
  provides:
    - fund_backtest.signal.validator.SignalValidationError
    - fund_backtest.signal.validator.validate_signal_frame
    - fund_backtest.signal.types.SignalFrame
    - fund_backtest.signal.types.WeightFrame
    - fund_backtest.config.SignalAdapterConfig
    - fund_backtest.config.load_signal_adapter_config
  affects:
    - backtest/src/fund_backtest/config.py
tech_stack:
  added: []
  patterns:
    - TDD (RED then GREEN) for all new contract code
    - SignalValidationError as ValueError subclass for contract enforcement
    - pd.DataFrame type aliases (SignalFrame, WeightFrame) with docstring schema contracts
    - BaseModel pattern mirroring existing PriceSettings for SignalAdapterConfig
key_files:
  created:
    - backtest/src/fund_backtest/signal/__init__.py
    - backtest/src/fund_backtest/signal/types.py
    - backtest/src/fund_backtest/signal/validator.py
    - backtest/tests/unit/test_signal_types.py
  modified:
    - backtest/src/fund_backtest/config.py
decisions:
  - "SignalFrame and WeightFrame are pd.DataFrame type aliases (not subclasses) — runtime enforcement done by validate_signal_frame() at adapter boundary"
  - "All-NaN columns log a warning but do NOT raise — adapter drops them downstream; prevents hard failures on sparse signals"
  - "SignalAdapterConfig min_coverage=5 (rows with fewer non-NaN tickers dropped before normalization)"
metrics:
  duration: "2 minutes"
  completed_date: "2026-03-29"
  tasks_completed: 2
  files_created: 4
  files_modified: 1
---

# Phase 03 Plan 01: Signal Contract Types and Validation Summary

**One-liner:** Typed SignalFrame/WeightFrame aliases, SignalValidationError contract enforcement, and SignalAdapterConfig Pydantic model with TDD (10 tests, all green).

## What Was Built

Established the typed signal contract for Phase 3. Any strategy module (e.g. AI Washing Detector adapter) must produce a SignalFrame that passes `validate_signal_frame()` before any normalization occurs.

### Files Created

- `backtest/src/fund_backtest/signal/__init__.py` — package marker
- `backtest/src/fund_backtest/signal/types.py` — `SignalFrame` and `WeightFrame` type aliases with full schema contracts in docstrings
- `backtest/src/fund_backtest/signal/validator.py` — `SignalValidationError(ValueError)` and `validate_signal_frame()` with four ordered checks
- `backtest/tests/unit/test_signal_types.py` — 10 TDD tests covering all validation paths

### Files Modified

- `backtest/src/fund_backtest/config.py` — appended `SignalAdapterConfig` (BaseModel, min_coverage=5, gross_exposure_limit=1.0) and `load_signal_adapter_config()` factory following `load_price_settings()` pattern

## Contracts Defined

### SignalFrame Contract

| Property | Requirement |
|----------|-------------|
| index | `pd.DatetimeIndex` (UTC or tz-naive) |
| columns | Non-empty strings (ticker symbols) |
| values | float, NaN allowed (partial) |
| All-NaN columns | Warning logged, not an error |

### WeightFrame Contract

| Property | Requirement |
|----------|-------------|
| values | float in `[-1.0, +1.0]` |
| first row | Always NaN (look-ahead prevention via `shift(1)`) |
| row sums | `abs(sum) <= gross_exposure_limit` |

### SignalAdapterConfig Defaults

| Field | Default | Purpose |
|-------|---------|---------|
| `min_coverage` | 5 | Minimum non-NaN tickers per row |
| `gross_exposure_limit` | 1.0 | Max absolute weight sum (no leverage) |

## TDD Execution

**RED commit:** `f13ed10` — 10 failing tests (ImportError on missing signal module)

**GREEN commit:** `fa6afda` — 4 files implementing the contract; all 10 tests pass

**Full unit suite:** 76 tests passed, 0 regressions

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — no data wiring or UI rendering in this plan. All contracts are structurally complete.

## Self-Check: PASSED

Files created:
- `backtest/src/fund_backtest/signal/__init__.py` — FOUND
- `backtest/src/fund_backtest/signal/types.py` — FOUND
- `backtest/src/fund_backtest/signal/validator.py` — FOUND
- `backtest/tests/unit/test_signal_types.py` — FOUND

Commits verified:
- `f13ed10` — test(03-01) RED phase FOUND
- `fa6afda` — feat(03-01) GREEN phase FOUND
