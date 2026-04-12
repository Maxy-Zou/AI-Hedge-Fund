---
phase: "06"
plan: "01"
subsystem: signals
tags: [tdd, red-tests, timing-cluster, win-streak, signal-engine]
dependency_graph:
  requires: []
  provides: [test-contracts-for-TimingClusterDetector, test-contracts-for-WinStreakDetector]
  affects: [tests/unit/signals/test_detectors.py, tests/unit/signals/test_engine.py]
tech_stack:
  added: []
  patterns: [TDD-RED, module-level-import-for-RED-state]
key_files:
  created: []
  modified:
    - tests/unit/signals/test_detectors.py
    - tests/unit/signals/test_engine.py
decisions:
  - "Module-level import of TimingClusterDetector/WinStreakDetector blocks entire test_detectors.py — correct RED behavior per TDD plan"
  - "WinStreakDetector infeasibility documented inline in test: SDK v2.0.0 Trade model lacks account identifier"
metrics:
  duration_seconds: 87
  completed_date: "2026-04-03"
  tasks_completed: 1
  files_modified: 2
---

# Phase 06 Plan 01: Phase 6 RED Tests (TimingClusterDetector + WinStreakDetector) Summary

**One-liner:** 7 RED TDD tests defining TimingClusterDetector (burst concentration), WinStreakDetector (infeasibility stub), and engine registration contracts.

## What Was Built

Added 7 new failing tests (RED state) to define the interface for two Phase 6 signal detectors before any implementation exists:

### tests/unit/signals/test_detectors.py — 6 new tests

**Helper added:** `_make_cluster_snapshots()` — module-level helper (not a fixture) that builds volume-configurable snapshot lists using the existing `snapshot_factory` from conftest.

**TimingClusterDetector tests (5 cases):**
1. `test_timing_cluster_fires_on_burst` — 720 snapshots, 180 burst (vol=100) + 540 baseline (vol=10), concentration ≈ 0.77 > threshold=0.6 → DetectionResult with signal_type='timing_cluster'
2. `test_timing_cluster_none_on_insufficient_snapshots` — only 5 snapshots → None (guard required)
3. `test_timing_cluster_none_on_dead_market` — 720 snapshots all vol=0 → None (zero-division guard required)
4. `test_timing_cluster_none_on_uniform_volume` — 720 snapshots all vol=100 → concentration ≈ 0.25 < 0.6 → None
5. `test_timing_cluster_confidence_clamped_to_one` — 710 vol=0 + 10 vol=1000 → extreme concentration → confidence == 1.0

**WinStreakDetector test (1 case):**
6. `test_win_streak_always_returns_none` — `WinStreakDetector().detect([])` returns None. Docstring explicitly cites: "SIG-04 infeasible — Trade model has no account identifier (SDK v2.0.0). Kalshi Python SDK v2.0.0 Trade model exposes: ticker, count, taker_side, yes_price, no_price, trade_id, created_time. No account_id or user_id field exists."

### tests/unit/signals/test_engine.py — 2 new tests

7. `test_timing_cluster_registered_in_default_detectors` — `SignalEngine(...)` with no explicit detectors → `any(isinstance(d, TimingClusterDetector) for d in engine._detectors)` must be True
8. `test_fetch_snapshots_limit_covers_cluster_lookback` — `SignalSettings(cluster_lookback_minutes=120)` → `_fetch_snapshots` must call `.limit(n)` where `n >= 721` (120 min × 6 snapshots/min at 10s polling)

## RED State Verification

- All 7 new tests fail with `ImportError: cannot import name 'TimingClusterDetector' from 'kalshi_tracker.signals.detectors'`
- Module-level import in test_detectors.py blocks collection of the entire file (correct — tests define the contract before the class exists)
- Existing engine tests (6 cases in test_engine.py) all pass when filtered with `-k "not cluster and not fetch_snapshots"`

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None introduced by this plan. WinStreakDetector is itself a planned permanent stub (SIG-04 infeasibility), but the stub implementation is in Plan 06-02 scope.

## Self-Check: PASSED

- Modified files exist: tests/unit/signals/test_detectors.py, tests/unit/signals/test_engine.py
- Commit hash 4131c13 verified in git log
- 7 new tests present (6 in test_detectors.py, 2 in test_engine.py)
- All fail with ImportError (RED)
- Existing engine tests pass (GREEN)
