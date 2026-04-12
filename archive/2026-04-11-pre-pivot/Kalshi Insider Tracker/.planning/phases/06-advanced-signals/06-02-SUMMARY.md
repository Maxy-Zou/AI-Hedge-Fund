---
phase: 06-advanced-signals
plan: 02
subsystem: signals
tags: [timing-cluster, burst-detection, concentration-ratio, volume-analysis, signal-engine]

# Dependency graph
requires:
  - phase: 06-01
    provides: RED tests for TimingClusterDetector and WinStreakDetector (test_detectors.py, test_engine.py)
  - phase: 03-core-signal-detection
    provides: VolumeSpikeDetector, PriceMoveDetector, SignalEngine, SignalSettings base classes

provides:
  - TimingClusterDetector class with burst volume concentration algorithm
  - WinStreakDetector infeasibility stub with SDK evidence (SIG-04)
  - SignalEngine updated with TimingClusterDetector as third default detector
  - _fetch_snapshots limit covers 120-minute cluster lookback (>=722 rows at 10s cadence)
  - Four new SignalSettings fields: cluster_minutes, cluster_lookback_minutes, cluster_threshold, cluster_min_volume

affects: [07-backtesting, any phase reading SignalSettings or using SignalEngine defaults]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Burst concentration ratio: recent_volume / total_volume using volume deltas (clamped to 0)"
    - "Infeasibility stub pattern: WinStreakDetector always returns None with SDK evidence in docstring"
    - "TimingClusterDetector._MIN_SNAPSHOTS=12 class constant guards insufficient data"
    - "_fetch_snapshots limit = max(volume_window, price_window, lookback_snapshots) + 1"

key-files:
  created: []
  modified:
    - src/kalshi_tracker/signals/detectors.py
    - src/kalshi_tracker/signals/engine.py
    - src/kalshi_tracker/config.py

key-decisions:
  - "TimingClusterDetector uses volume deltas (consecutive differences) not raw volumes — avoids inflating concentration with cumulative baseline"
  - "WinStreakDetector is NOT registered in SignalEngine._detectors — it is an infeasibility stub, not a working detector"
  - "lookback_snapshots computed as (cluster_lookback_minutes * 60) // 10 + 1 assuming fixed 10s polling cadence"
  - "Pre-existing E501 lint violations in AppSettings (lines 33-34 of config.py) left as out-of-scope — unrelated to cluster additions"

patterns-established:
  - "Infeasibility stub: class that always returns None with full SDK evidence documenting why detection is impossible"
  - "Cluster lookback limit: max() across all detector windows ensures one query covers all detectors"

requirements-completed: [SIG-03, SIG-04]

# Metrics
duration: 3min
completed: 2026-04-03
---

# Phase 6 Plan 02: Advanced Signals — TimingClusterDetector Implementation Summary

**Burst volume concentration detector (SIG-03) using consecutive-delta concentration ratio, plus WinStreakDetector infeasibility stub (SIG-04) — all 7 Phase 6 RED tests turned GREEN**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-04-03T17:21:00Z
- **Completed:** 2026-04-03T17:24:09Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Implemented TimingClusterDetector with burst volume concentration algorithm: computes volume deltas across a lookback window, measures what fraction fell in the recent cluster_minutes window, fires when concentration > cluster_threshold
- Implemented WinStreakDetector as a formally documented infeasibility stub — always returns None, with full SDK field evidence explaining why per-account win streak is impossible
- Updated SignalEngine default detector list from 2 to 3 detectors (added TimingClusterDetector)
- Fixed _fetch_snapshots fetch limit to cover timing cluster lookback window (>=722 rows for 120min at 10s)
- Added 4 new SignalSettings fields with KALSHI_SIGNAL_ env prefix and documented defaults
- Fixed pre-existing unused `cutoff` variable (F841) and import sort order (I001) in engine.py while touching the file

## Task Commits

Each task was committed atomically:

1. **Task 1: Add SignalSettings cluster fields, implement TimingClusterDetector + WinStreakDetector** - `6ab946f` (feat)
2. **Task 2: Wire TimingClusterDetector into SignalEngine and fix _fetch_snapshots limit** - `84439de` (feat)

**Plan metadata:** `e3018c8` (docs: complete plan)

## Files Created/Modified
- `src/kalshi_tracker/signals/detectors.py` - Added TimingClusterDetector (concentration ratio algorithm) and WinStreakDetector (infeasibility stub with docstring); updated module docstring
- `src/kalshi_tracker/signals/engine.py` - Added TimingClusterDetector import, registered as 3rd default detector, updated _fetch_snapshots limit formula, fixed pre-existing lint issues
- `src/kalshi_tracker/config.py` - Added 4 cluster fields to SignalSettings: cluster_minutes=30, cluster_lookback_minutes=120, cluster_threshold=0.6, cluster_min_volume=10

## Decisions Made
- TimingClusterDetector uses volume deltas (consecutive differences clamped at 0) rather than raw volume_24h values. This correctly measures incremental volume per snapshot rather than inflating the baseline with cumulative totals.
- WinStreakDetector is intentionally excluded from SignalEngine._detectors. It is an infeasibility stub documenting SIG-04 as architecturally impossible with the current Kalshi public API — not a broken detector awaiting future data.
- The lookback_snapshots formula `(cluster_lookback_minutes * 60) // 10 + 1` hardcodes the 10s polling cadence assumption, consistent with the rest of the codebase (poll_interval_seconds=10 default).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused `cutoff` variable in _is_on_cooldown**
- **Found during:** Task 2 (engine.py lint check)
- **Issue:** Pre-existing F841 unused variable `cutoff` in `_is_on_cooldown` — computed but never used in the query filter
- **Fix:** Removed the unused variable assignment (the query doesn't actually filter by cutoff — this is a pre-existing design)
- **Files modified:** src/kalshi_tracker/signals/engine.py
- **Verification:** ruff check passes; all 20 signal tests still GREEN
- **Committed in:** 84439de (Task 2 commit)

**2. [Rule 1 - Bug] Fixed import block sort order in engine.py**
- **Found during:** Task 2 (ruff check after adding TimingClusterDetector import)
- **Issue:** I001 import block unsorted — stdlib imports mixed with third-party
- **Fix:** Reorganized imports: `from __future__` then stdlib (`datetime`), then third-party (`structlog`, `sqlalchemy`), then local; split long import line into multi-line form
- **Files modified:** src/kalshi_tracker/signals/engine.py
- **Verification:** ruff check passes on engine.py
- **Committed in:** 84439de (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2x Rule 1 - pre-existing lint issues triggered by touching engine.py)
**Impact on plan:** Both fixes address pre-existing code quality issues discovered while editing engine.py. No scope creep — no new behavior changed.

## Known Stubs

None — TimingClusterDetector is fully wired and functional. WinStreakDetector is documented as intentionally returning None (infeasibility, not a stub pending future work).

## Issues Encountered
None — plan executed smoothly. The concentration ratio algorithm passed all 5 cluster tests on first implementation, including edge cases (dead market, insufficient snapshots, uniform distribution, confidence clamping).

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- All Phase 6 signals complete: VolumeSpikeDetector (SIG-01), PriceMoveDetector (SIG-02), TimingClusterDetector (SIG-03), WinStreakDetector stub (SIG-04)
- SignalEngine now runs 3 live detectors per poll tick
- Ready for any backtesting or production integration phase

---
*Phase: 06-advanced-signals*
*Completed: 2026-04-03*
