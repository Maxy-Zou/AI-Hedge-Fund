---
phase: 08-job-posting-signal
plan: 04
subsystem: analysis
tags: [scoring-orchestrator, job-mismatch, ghost-ratio, signal-integration]

requires:
  - phase: 08-job-posting-signal-03
    provides: "compute_job_mismatch_score pure function and JobMismatchScoringConfig"
  - phase: 08-job-posting-signal-02
    provides: "JobPosting ORM model with lifecycle tracking columns"
provides:
  - "ScoringOrchestrator.score_company produces 6 signals including job_mismatch"
  - "_load_job_postings helper with ghost_ratio calculation from lifecycle data"
affects: [scoring, pipeline-automation, composite-score]

tech-stack:
  added: []
  patterns: ["Ghost ratio from lifecycle columns (first_seen + is_active + threshold)"]

key-files:
  created:
    - tests/unit/test_scoring_orchestrator_job.py
  modified:
    - src/ai_washer/analysis/scoring_orchestrator.py
    - tests/unit/test_scoring_orchestrator.py
    - tests/unit/test_scoring_orchestrator_earnings.py

key-decisions:
  - "Ghost ratio uses configurable ghost_days_threshold (default 90) from JobMismatchScoringConfig"
  - "ai_claim_intensity for job scoring uses 0.0 default (not None like earnings) since job mismatch has no fallback behavior"

patterns-established:
  - "7-query side_effect chain in score_company mock tests (was 6 before job postings)"

requirements-completed: [JOB-05, JOB-03]

duration: 6min
completed: 2026-03-29
---

# Phase 08 Plan 04: Job Mismatch Orchestrator Integration Summary

**Job mismatch scorer wired into ScoringOrchestrator as 6th signal with ghost_ratio from lifecycle tracking and shared ai_keyword_counts**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-29T15:49:26Z
- **Completed:** 2026-03-29T15:55:26Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments
- Extended ScoringOrchestrator.score_company to produce job_mismatch as the 6th signal
- Added _load_job_postings helper that computes ghost_ratio from is_active + first_seen lifecycle columns
- Graceful skip on missing job data (logged as signal_skipped with reason="no_job_data")
- Updated existing test infrastructure to handle 7-query side_effect chain

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend ScoringOrchestrator with _load_job_postings and job_mismatch scoring** - `54d35bb` (feat)

## Files Created/Modified
- `src/ai_washer/analysis/scoring_orchestrator.py` - Added _load_job_postings, job mismatch scoring block, import for compute_job_mismatch_score and JobPosting
- `tests/unit/test_scoring_orchestrator_job.py` - 7 tests covering load, score, skip, ghost_ratio scenarios
- `tests/unit/test_scoring_orchestrator.py` - Updated 4 mock side_effect chains to include job postings query
- `tests/unit/test_scoring_orchestrator_earnings.py` - Updated helper to include job postings mock

## Decisions Made
- Ghost ratio uses configurable ghost_days_threshold (default 90) from JobMismatchScoringConfig
- ai_claim_intensity for job scoring uses 0.0 default when SEC data missing (not None like earnings scorer), since job mismatch scorer returns None on zero intensity anyway

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing orchestrator test mock chains**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** 3 tests in test_scoring_orchestrator.py and 6 tests in test_scoring_orchestrator_earnings.py ran out of side_effect entries because score_company now makes 7 queries instead of 6
- **Fix:** Added job_postings mock entry to all side_effect chains in both test files
- **Files modified:** tests/unit/test_scoring_orchestrator.py, tests/unit/test_scoring_orchestrator_earnings.py
- **Verification:** All 746 unit tests pass
- **Committed in:** 54d35bb (part of task commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary fix for test compatibility with the new query. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data paths are fully wired.

## Next Phase Readiness
- All 6 signals now produce scores through ScoringOrchestrator
- Phase 08 (job-posting-signal) is complete
- Ready for composite scoring / pipeline automation phases

---
*Phase: 08-job-posting-signal*
*Completed: 2026-03-29*
