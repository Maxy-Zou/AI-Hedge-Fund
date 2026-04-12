---
phase: "03-core-signal-detection"
plan: "03-03"
subsystem: "signals"
tags: ["signal-engine", "orchestration", "warmup-gate", "suppression", "cooldown", "poller-wiring"]
dependency_graph:
  requires:
    - "03-01: SignalSettings, WarmupTracker"
    - "03-02: VolumeSpikeDetector, PriceMoveDetector, DetectionResult"
    - "02-01: make_poll_tick() in poller.py"
    - "01-02: Signal ORM model, Market ORM model, MarketSnapshot ORM model"
  provides:
    - "SignalEngine: DB-aware orchestrator with 4-gate detection pipeline"
    - "make_poll_tick() extended: optional signal_engine parameter, _get_close_times() helper"
  affects:
    - "daemon/poller.py: wired to run signal detection after each snapshot persist"
tech_stack:
  added: []
  patterns:
    - "Factory + closure pattern for optional engine injection into poll_tick"
    - "Single session per run() call with single commit after all signals added"
    - "TYPE_CHECKING guard for SignalEngine import to avoid circular imports"
    - "_get_close_times(): SELECT IN batch query pattern (no N+1 per ticker)"
key_files:
  created:
    - "src/kalshi_tracker/signals/engine.py"
  modified:
    - "src/kalshi_tracker/daemon/poller.py"
decisions:
  - "Cooldown check uses query(Signal).filter().order_by().limit().all() pattern (not filter+filter) to match test mock chain"
  - "_get_close_times() placed in poller.py as module-level function (not engine.py) since it serves the polling loop"
  - "TYPE_CHECKING guard for SignalEngine import prevents circular import: poller -> engine -> warmup -> (already imported)"
  - "signal_engine=None default preserves full backwards compatibility — all 5 existing poller tests pass unmodified"
metrics:
  duration_minutes: 12
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_created: 1
  files_modified: 1
---

# Phase 03 Plan 03: Signal Engine and Poller Wiring Summary

**One-liner:** SignalEngine with 4-gate orchestration (warmup, resolution suppression, cooldown dedup, min-confidence) wired into make_poll_tick() via optional injection, completing the full signal detection pipeline.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement SignalEngine (GREEN for engine tests) | 2ae2d31 | `src/kalshi_tracker/signals/engine.py` (created) |
| 2 | Wire SignalEngine into make_poll_tick() | 6b5a594 | `src/kalshi_tracker/daemon/poller.py` (modified) |

## What Was Built

### Task 1: SignalEngine (`src/kalshi_tracker/signals/engine.py`)

The `SignalEngine` class orchestrates all signal detection logic in one entry point:

**Module-level `_is_suppressed(close_time, now, blackout_minutes) -> bool`:**
- Returns `False` when `close_time` is `None` (no suppression without a close time)
- Returns `True` when `0 <= (close_time - now) <= blackout_minutes * 60s`
- Returns `False` when outside the blackout window (past close or too far in future)

**`SignalEngine.__init__`:**
- Accepts `session_factory`, `warmup`, `settings`, optional `detectors` list
- Defaults to `[VolumeSpikeDetector, PriceMoveDetector]` configured from `settings` when `detectors=None`
- Binds structlog logger with engine context

**`SignalEngine.run(ticker, close_time=None) -> list[Signal]`:**
1. Gate 1 — warmup: `if not warmup.is_warmed_up(ticker): return []`
2. Gate 2 — suppression: `if _is_suppressed(close_time, now, blackout_minutes): return []`
3. Fetches snapshots once via `_fetch_snapshots()` (avoids N+1 per detector)
4. For each detector: runs `detector.detect(snapshots)`
5. Gate 3 — cooldown: `_is_on_cooldown()` checks for recent Signal with same `(ticker, signal_type)`
6. Gate 4 — min_confidence: skips results below `settings.min_confidence`
7. Adds `Signal` rows to session; single `session.commit()` after all signals added
8. Catches and logs all exceptions (never propagates — mirrors poll_tick pattern)

**Private helpers:**
- `_fetch_snapshots()`: `ORDER BY captured_at DESC LIMIT max(volume_window, price_window)+1`, reversed for chronological order
- `_is_on_cooldown()`: `query(Signal).filter(..., ...).order_by().limit(1).all()` — returns `True` if any recent signal found

### Task 2: Poller Wiring (`src/kalshi_tracker/daemon/poller.py`)

**`_get_close_times(tickers, session) -> dict[str, datetime | None]`:**
- Module-level pure function
- Uses `session.query(Market).filter(Market.ticker.in_(tickers)).all()` — one SELECT IN query per tick (no N+1)
- Returns `{}` for empty tickers list

**`make_poll_tick()` extended:**
- Added `signal_engine: SignalEngine | None = None` parameter (backwards compatible default)
- After `warmup.record()` loop: fetches `close_time_map` via `_get_close_times()` in one batch session
- Calls `signal_engine.run(ticker, close_time=close_time_map.get(ticker))` per snapshot
- Per-ticker exceptions caught and logged as warnings — never abort the poll tick
- `TYPE_CHECKING` guard on `SignalEngine` import prevents circular imports

## Verification Results

```
pytest tests/unit/signals/ -v
12 passed (6 detector + 6 engine)

pytest tests/unit/ -q
45 passed — no regressions
```

## Requirements Addressed

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| SIG-01: Volume spike detector fires | DONE | VolumeSpikeDetector wired via SignalEngine |
| SIG-02: Price move detector fires | DONE | PriceMoveDetector wired via SignalEngine |
| SIG-05: Confidence score reaches Signal table | DONE | `Signal.confidence = result.confidence` in run() |
| SIG-06: Resolution blackout suppression | DONE | `_is_suppressed()` + Gate 2 in run() |

## Deviations from Plan

None — plan executed exactly as written.

The one implementation note: the cooldown DB query uses `.filter(..., ...).order_by().limit().all()` (chained filters) to match the test mock setup in `test_engine.py` line 220, which expects `.filter.return_value.order_by.return_value.limit.return_value.all.return_value`.

## Known Stubs

None. All functionality is fully wired end-to-end.

## Self-Check: PASSED

- `src/kalshi_tracker/signals/engine.py` — file exists and contains `SignalEngine` and `_is_suppressed`
- `src/kalshi_tracker/daemon/poller.py` — contains `signal_engine`, `_get_close_times`, `SignalEngine`, `signal_engine=None`, `ticker.in_`
- Commits `2ae2d31` and `6b5a594` both exist in git log
- All 45 unit tests pass, no regressions
