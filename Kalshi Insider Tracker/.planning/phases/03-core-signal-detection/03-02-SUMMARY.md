---
phase: 03-core-signal-detection
plan: "02"
subsystem: signals
tags: [signal-detection, volume-spike, price-move, z-score, detectors]
dependency_graph:
  requires:
    - 03-01  # RED test scaffolding for signal detection
  provides:
    - signals package with DetectionResult, VolumeSpikeDetector, PriceMoveDetector
  affects:
    - 03-03  # SignalEngine (next plan) imports from signals.detectors
tech_stack:
  added:
    - numpy (z-score computation on volume_24h rolling window)
  patterns:
    - frozen dataclass for immutable result contract (DetectionResult)
    - stateless detector class pattern (no DB I/O, no side effects)
    - duck-typing on snapshot objects (works with ORM rows and MagicMock)
key_files:
  created:
    - src/kalshi_tracker/signals/__init__.py
    - src/kalshi_tracker/signals/types.py
    - src/kalshi_tracker/signals/detectors.py
  modified: []
decisions:
  - "Flat-baseline (std=0) with spike fires at confidence=1.0 — when baseline is uniformly flat but current differs, it is a maximum anomaly rather than an undefined signal"
  - "z_score sentinel 999.0 used in details dict for flat-baseline spikes (JSON-safe, avoids float('inf'))"
  - "window guard requires window+1 total snapshots (window baselines + 1 current) — the plan formula used window but that caused all baselines to be sliced to window-1 elements"
metrics:
  duration_seconds: 205
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_created: 3
  files_modified: 0
---

# Phase 03 Plan 02: Signal Detectors — Summary

**One-liner:** VolumeSpikeDetector (z-score on volume_24h) and PriceMoveDetector (% move vs recent range) implemented as stateless classes with confidence clamped to [0.0, 1.0].

## What Was Built

The `kalshi_tracker.signals` package delivers SIG-01 (volume spike detection), SIG-02 (price movement detection), and SIG-05 (confidence scoring) at the pure computation layer — no DB I/O, stateless, duck-typed.

**Task 1: signals package with DetectionResult**
- `src/kalshi_tracker/signals/__init__.py` — empty package marker
- `src/kalshi_tracker/signals/types.py` — `DetectionResult` frozen dataclass with `signal_type`, `confidence`, `details`

**Task 2: VolumeSpikeDetector and PriceMoveDetector**
- `src/kalshi_tracker/signals/detectors.py` — both detector classes
- All 6 RED tests turned GREEN

## Algorithms

**VolumeSpikeDetector:**
- Requires `window + 1` total snapshots (60 baseline + 1 current)
- `baseline = arr[:-1]`, `current = arr[-1]` from `volume_24h`
- `z_score = (current - mean) / std` when `std > 0`
- When `std == 0` and `current != mean` → confidence=1.0 (extreme anomaly)
- When `std == 0` and `current == mean` → None (no spike)
- `confidence = clamp((z_score - z_threshold) / z_threshold, 0.0, 1.0)`

**PriceMoveDetector:**
- Requires at least 2 snapshots
- `recent = prices[:-1]`, `price_range = max(recent) - min(recent)`
- `move_pct = abs(current - prev) / price_range`
- `confidence = clamp(move_pct / move_pct_threshold, 0.0, 1.0)`

## Test Results

```
tests/unit/signals/test_detectors.py::test_volume_spike_fires_above_threshold PASSED
tests/unit/signals/test_detectors.py::test_volume_no_signal_below_threshold  PASSED
tests/unit/signals/test_detectors.py::test_volume_zero_std_guard              PASSED
tests/unit/signals/test_detectors.py::test_price_move_fires_above_threshold  PASSED
tests/unit/signals/test_detectors.py::test_price_move_zero_range_guard       PASSED
tests/unit/signals/test_detectors.py::test_confidence_clamped                PASSED
6 passed in 0.14s (all previously RED, now GREEN)
```

No regressions: 39 passed across all unit tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed window guard off-by-one causing zero-std false negative**
- **Found during:** Task 2 (first GREEN attempt)
- **Issue:** Plan specified `if len(volumes) < window` guard, then `arr = volumes[-window:]`. With exactly `window+1` snapshots (60 baseline + 1 spike), the slice `volumes[-60:]` discards the oldest baseline, leaving 59 baselines (all identical = std 0) + 1 spike. The zero-std guard then returned None, suppressing a valid spike.
- **Fix:** Changed guard to `< window + 1` and slice to `volumes[-(window+1):]` so baseline always has exactly `window` elements.
- **Files modified:** `src/kalshi_tracker/signals/detectors.py`
- **Commit:** d920b4d

**2. [Rule 1 - Bug] Flat-baseline spike correctly fires instead of returning None**
- **Found during:** Task 2 (std=0 guard analysis)
- **Issue:** Plan's "zero std guard" meant to protect against division-by-zero, but test 1 (`test_volume_spike_fires_above_threshold`) has a perfectly flat baseline (all 300) with a spike (1500). Returning None for all std=0 cases would make test 1 fail.
- **Fix:** Split the std=0 branch: if `current == mean` → None (genuinely flat); if `current != mean` → confidence=1.0 (maximum anomaly on flat baseline). Used sentinel z_score=999.0 in details dict (JSON-safe, avoids `float('inf')`).
- **Files modified:** `src/kalshi_tracker/signals/detectors.py`
- **Commit:** d920b4d

## Known Stubs

None — detectors are complete and fully tested.

## Self-Check: PASSED

- [x] `src/kalshi_tracker/signals/__init__.py` exists
- [x] `src/kalshi_tracker/signals/types.py` exists with `class DetectionResult`
- [x] `src/kalshi_tracker/signals/detectors.py` exists with `class VolumeSpikeDetector` and `class PriceMoveDetector`
- [x] Commits b0a7462 and d920b4d exist
- [x] 6 tests GREEN, 39 total unit tests GREEN, no regressions
