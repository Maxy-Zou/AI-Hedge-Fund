---
phase: 03-core-signal-detection
plan: "01"
subsystem: signal-detection
tags: [tdd, red-tests, config, numpy, factory-boy]
dependency_graph:
  requires: []
  provides:
    - SignalSettings in config.py
    - RED test contracts for VolumeSpikeDetector, PriceMoveDetector
    - RED test contracts for SignalEngine (warmup gate, suppression, persistence, cooldown)
  affects:
    - "03-02-PLAN.md: must implement detectors to turn 6 RED tests GREEN"
    - "03-03-PLAN.md: must implement SignalEngine to turn 6 RED tests GREEN"
tech_stack:
  added:
    - numpy==2.4.4 (runtime)
    - factory-boy==3.3.3 (dev)
  patterns:
    - SignalSettings uses KALSHI_SIGNAL_ prefix following AppSettings/KalshiSettings pattern
    - snapshot_factory() builds ORM-like MagicMock objects with sequential timestamps
    - RED import-fail pattern: tests import from non-existent kalshi_tracker.signals module
key_files:
  created:
    - src/kalshi_tracker/config.py (modified: added SignalSettings + load_signal_settings)
    - tests/unit/signals/__init__.py
    - tests/unit/signals/conftest.py
    - tests/unit/signals/test_detectors.py
    - tests/unit/signals/test_engine.py
  modified:
    - pyproject.toml (numpy added to dependencies, factory-boy added to dev deps)
    - uv.lock (updated with numpy 2.4.4, factory-boy 3.3.3, faker 40.12.0)
decisions:
  - "SignalSettings uses 7 fields (not 6 as originally specified): added signal_cooldown_seconds"
  - "snapshot_factory() returns MagicMock objects (not ORM instances) — avoids DB setup in unit tests"
  - "freezegun used in engine tests for deterministic time-based suppression assertions"
  - "warmup fixture (warmed_warmup) defaults to ticker TEST-1 for consistency across engine tests"
metrics:
  duration_seconds: 180
  completed_date: "2026-04-02"
  tasks_completed: 2
  tasks_total: 2
  files_created: 5
  files_modified: 3
---

# Phase 03 Plan 01: Signal Detection RED Tests Summary

**One-liner:** numpy + factory-boy installed, SignalSettings with 7 thresholds added to config.py, 12 RED test contracts written for VolumeSpikeDetector, PriceMoveDetector, and SignalEngine.

## What Was Built

### Task 1: Dependencies + SignalSettings

Installed `numpy==2.4.4` (runtime) and `factory-boy==3.3.3` (dev). Added `SignalSettings` class to `src/kalshi_tracker/config.py` following the same `BaseSettings` pattern as `AppSettings` and `KalshiSettings`, using the `KALSHI_SIGNAL_` prefix. Added `load_signal_settings()` factory function.

Fields added:
- `volume_z_threshold: float = 2.5` — z-score threshold for volume spike detection
- `volume_window: int = 60` — rolling window size for volume baseline
- `price_move_threshold: float = 0.15` — move percentage threshold for price detection
- `price_window: int = 60` — rolling window size for price baseline
- `resolution_blackout_minutes: int = 30` — suppress signals within 30min of close
- `min_confidence: float = 0.0` — minimum confidence to emit a signal
- `signal_cooldown_seconds: int = 300` — deduplication window per (ticker, signal_type)

### Task 2: RED Test Scaffolding

Created 4 files under `tests/unit/signals/`:

**conftest.py** — shared fixtures:
- `snapshot_factory(ticker, volumes, prices, base_time)` — returns MagicMock objects with `.volume_24h`, `.last_price`, `.captured_at` attributes at 10s intervals
- `mock_session` — MagicMock with `.add()`, `.commit()`, and a chainable `.query().filter().order_by().limit().all()` setup
- `warmed_warmup` — WarmupTracker(threshold=1) with TEST-1 already recorded
- `cold_warmup` — WarmupTracker(threshold=100), never warm

**test_detectors.py** — 6 tests for VolumeSpikeDetector and PriceMoveDetector:
1. `test_volume_spike_fires_above_threshold` — 60 baseline + 1 spike (5x), expects DetectionResult
2. `test_volume_no_signal_below_threshold` — all volumes near mean, expects None
3. `test_volume_zero_std_guard` — all volumes identical, expects None (no crash)
4. `test_price_move_fires_above_threshold` — baseline 45-46, spike 99, expects DetectionResult
5. `test_price_move_zero_range_guard` — all prices identical, expects None (no crash)
6. `test_confidence_clamped` — extreme 1000x spike, expects confidence == 1.0 (not > 1.0)

**test_engine.py** — 6 tests for SignalEngine:
1. `test_engine_skips_unwarmed_market` — cold warmup → returns [], no DB write
2. `test_resolution_suppression` — close_time 20min away, blackout 30min → returns []
3. `test_no_suppression_without_close_time` — close_time=None → suppression skipped
4. `test_no_suppression_outside_blackout` — close_time 60min away, blackout 30min → not blocked
5. `test_engine_persists_signal` — warmed + firing detector → session.add() called
6. `test_engine_cooldown_skips_duplicate` — recent Signal in DB → returns [], no add

## RED State Confirmed

```
ModuleNotFoundError: No module named 'kalshi_tracker.signals'
```

Both test files fail at import — correct RED state. The `signals/` module does not exist yet (created in Plans 02 and 03).

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. This plan produces test files only (no implementation stubs).

## Self-Check: PASSED

Files exist:
- FOUND: /Users/maxzou/Documents/projects/AI Hedgefund/Kalshi Insider Tracker/tests/unit/signals/__init__.py
- FOUND: /Users/maxzou/Documents/projects/AI Hedgefund/Kalshi Insider Tracker/tests/unit/signals/conftest.py
- FOUND: /Users/maxzou/Documents/projects/AI Hedgefund/Kalshi Insider Tracker/tests/unit/signals/test_detectors.py
- FOUND: /Users/maxzou/Documents/projects/AI Hedgefund/Kalshi Insider Tracker/tests/unit/signals/test_engine.py

Commits exist:
- d143c97: feat(03-01): install numpy+factory-boy, add SignalSettings to config.py
- 3f6b77a: test(03-01): add RED test scaffolding for signal detection
