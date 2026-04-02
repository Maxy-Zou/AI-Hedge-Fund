---
phase: 08-job-posting-signal
plan: 02
subsystem: ingestion
tags: [python-jobspy, job-scraping, lifecycle-tracking, tenacity, cli]

# Dependency graph
requires:
  - phase: 08-job-posting-signal/01
    provides: JobRecord, classify_role, compute_job_hash, JobPosting ORM, JobCollectionResult
provides:
  - JobClient wrapper around python-jobspy with retry logic
  - JobCollector orchestrator with lifecycle tracking (insert/update/deactivate)
  - CLI commands for job collection (collect, collect-all)
affects: [08-job-posting-signal/03, 08-job-posting-signal/04]

# Tech tracking
tech-stack:
  added: [python-jobspy (scrape_jobs)]
  patterns: [lifecycle-tracking (first_seen/last_seen/is_active), NaN-to-None normalization]

key-files:
  created:
    - src/ai_washer/ingestion/job_client.py
    - src/ai_washer/ingestion/job_collector.py
    - tests/unit/test_job_client.py
    - tests/unit/test_job_collector.py
  modified:
    - src/ai_washer/cli.py

key-decisions:
  - "Default sites indeed+google (no LinkedIn due to rate-limit risk)"
  - "NaN-to-None normalization for pandas DataFrame optional columns"
  - "Stale postings deactivated by comparing last_seen < collection_date"

patterns-established:
  - "Lifecycle tracking pattern: first_seen/last_seen/is_active with stale deactivation"
  - "JobClient follows GitHubClient pattern: error class, retry decorator, typed returns"
  - "JobCollector follows GitHubCollector pattern: __init__, collect_for_company, collect_all"

requirements-completed: [JOB-01, JOB-04]

# Metrics
duration: 5min
completed: 2026-03-29
---

# Phase 8 Plan 2: Job Ingestion Pipeline Summary

**JobClient wrapping python-jobspy with tenacity retry, JobCollector orchestrating scrape-classify-dedup-persist with lifecycle tracking, and CLI job commands**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-29T19:43:15Z
- **Completed:** 2026-03-29T19:47:45Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- JobClient wraps python-jobspy scrape_jobs() returning typed list[JobRecord] with retry logic
- JobCollector implements full lifecycle: insert new, update last_seen, deactivate stale postings
- CLI job commands (collect, collect-all) registered and callable
- 17 unit tests with mocked external dependencies, all passing

## Task Commits

Each task was committed atomically:

1. **Task 1: JobClient wrapper around python-jobspy with tests** - `709a1ad` (feat)
2. **Task 2: JobCollector orchestrator with lifecycle tracking, CLI job commands** - `af2e01d` (feat)

## Files Created/Modified
- `src/ai_washer/ingestion/job_client.py` - Thin wrapper around python-jobspy with tenacity retry and NaN normalization
- `src/ai_washer/ingestion/job_collector.py` - Orchestrator with lifecycle tracking (insert/update/deactivate)
- `src/ai_washer/cli.py` - Added job_app Typer group with collect and collect-all commands
- `tests/unit/test_job_client.py` - 10 tests covering search, config, NaN handling, error wrapping
- `tests/unit/test_job_collector.py` - 7 tests covering lifecycle tracking, collect_all, error handling

## Decisions Made
- Default search sites: indeed + google (not LinkedIn due to rate-limit risk at page 10)
- NaN-to-None normalization using math.isnan for pandas DataFrame optional columns
- Stale postings deactivated by comparing last_seen < collection_date (postings not seen in current scrape)
- JobCollector follows GitHubCollector pattern exactly: __init__ with DI, collect_for_company, collect_all

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data flows are wired end-to-end.

## Next Phase Readiness
- JobClient and JobCollector ready for Plan 03 (scoring) to consume job posting data
- Lifecycle tracking (first_seen, last_seen, is_active) enables ghost job detection in scorer
- CLI commands available for manual testing against real job boards

---
*Phase: 08-job-posting-signal*
*Completed: 2026-03-29*
