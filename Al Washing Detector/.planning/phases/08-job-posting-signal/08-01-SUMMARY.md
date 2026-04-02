---
phase: 08-job-posting-signal
plan: 01
subsystem: ingestion, database, config
tags: [python-jobspy, job-postings, role-classification, dedup-hash, lifecycle-tracking]

requires:
  - phase: 01-skeleton
    provides: Base ORM, AppendOnlyMixin, ScoringConfig, Alembic migrations
  - phase: 06-github-signal
    provides: Signal types module pattern (github_types.py)

provides:
  - python-jobspy dependency installed for job board scraping
  - job_types.py with JobRecord, JobCollectionResult, classify_role, compute_job_hash
  - JobPosting ORM model with lifecycle tracking (first_seen, last_seen, is_active)
  - Alembic migration 007 creating job_postings table
  - JobMismatchScoringConfig in ScoringConfig with ghost job detection parameters

affects: [08-02, 08-03, 08-04]

tech-stack:
  added: [python-jobspy]
  patterns: [lifecycle-tracked ORM model (not append-only), keyword-based role classification]

key-files:
  created:
    - src/ai_washer/ingestion/job_types.py
    - src/ai_washer/db/migrations/versions/007_add_job_postings.py
    - tests/unit/test_job_types.py
  modified:
    - pyproject.toml
    - uv.lock
    - src/ai_washer/db/models.py
    - src/ai_washer/config.py
    - config/scoring.yaml
    - config/scoring.example.yaml

key-decisions:
  - "JobPosting NOT append-only: lifecycle tracking requires updates to last_seen and is_active"
  - "Engineering keywords (15) vs marketing keywords (10) with engineering-wins-ties policy"
  - "SHA-256 dedup hash on company+title+location, case/whitespace insensitive"
  - "JOB_SIGNAL_VERSION=0.8.0 matching Phase 8 numbering convention"

patterns-established:
  - "Lifecycle-tracked ORM model: first_seen/last_seen/is_active/updated_at for mutable entity tracking"
  - "Keyword-based role classifier: engineering/marketing/ambiguous classification via substring matching"

requirements-completed: [JOB-02, JOB-03]

duration: 4min
completed: 2026-03-29
---

# Phase 8 Plan 01: Job Posting Foundation Summary

**python-jobspy installed with role classifier, dedup hash, JobPosting ORM model, and JobMismatchScoringConfig**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-29T19:35:56Z
- **Completed:** 2026-03-29T19:40:12Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Installed python-jobspy for multi-board job scraping (Indeed, LinkedIn, Glassdoor)
- Created job_types.py with role classifier (engineering/marketing/ambiguous), SHA-256 dedup hash, and Pydantic type contracts
- Added JobPosting ORM model with lifecycle columns (first_seen, last_seen, is_active, updated_at) -- NOT append-only
- Created Alembic migration 007 with unique dedup_hash constraint and company+date index
- Extended ScoringConfig with JobMismatchScoringConfig (ghost_days_threshold, engineering_weight, hiring_intensity_weight)

## Task Commits

Each task was committed atomically:

1. **Task 1: Install python-jobspy, create job_types.py with type contracts, role classifier, and dedup hash** - `43f4260` (feat)
2. **Task 2: JobPosting ORM model, Alembic migration 007, JobMismatchScoringConfig, scoring.yaml update** - `864fd7b` (feat)

## Files Created/Modified
- `src/ai_washer/ingestion/job_types.py` - Type contracts, constants, role classifier, dedup hash
- `src/ai_washer/db/models.py` - Added JobPosting ORM model (tenth table)
- `src/ai_washer/db/migrations/versions/007_add_job_postings.py` - Migration creating job_postings table
- `src/ai_washer/config.py` - Added JobMismatchScoringConfig to ScoringConfig
- `config/scoring.yaml` - Added job_mismatch section with defaults
- `config/scoring.example.yaml` - Added job_mismatch section
- `tests/unit/test_job_types.py` - 18 unit tests for role classifier, dedup hash, and type validation
- `pyproject.toml` - Added python-jobspy dependency
- `uv.lock` - Updated lockfile

## Decisions Made
- JobPosting NOT append-only: lifecycle tracking requires updates to last_seen and is_active (unlike all other financial data tables)
- Engineering keywords (15 terms) vs marketing keywords (10 terms) with engineering-wins-ties policy for role classification
- SHA-256 dedup hash on normalized company+title+location for idempotent collection
- JOB_SIGNAL_VERSION=0.8.0 matching Phase 8 numbering convention (consistent with prior phases)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all types, models, and config are fully wired.

## Next Phase Readiness
- Foundation types and database schema ready for 08-02 (JobSpy client/collector)
- JobMismatchScoringConfig ready for 08-04 (job mismatch scorer)
- All 25 tests passing (18 job_types + 7 config)

---
*Phase: 08-job-posting-signal*
*Completed: 2026-03-29*
