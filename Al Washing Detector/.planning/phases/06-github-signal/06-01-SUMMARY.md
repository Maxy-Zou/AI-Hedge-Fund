---
phase: 06-github-signal
plan: 01
subsystem: database
tags: [github, pydantic, sqlalchemy, alembic, type-contracts]

requires:
  - phase: 05-patent-signal
    provides: Patent model pattern, AppendOnlyMixin, config patterns
provides:
  - GitHubRepoRecord, GitHubOrgSnapshot, GitHubCollectionResult type contracts
  - GitHubRepo ORM model with append-only mixin
  - Alembic migration 005 for github_repos table
  - GitHubActivityScoringConfig in ScoringConfig
  - ML_FRAMEWORK_PATTERNS and ML_LANGUAGES domain constants
affects: [06-02, 06-03, 06-04]

tech-stack:
  added: []
  patterns: [github-type-contracts, github-repo-orm-model]

key-files:
  created:
    - src/ai_washer/ingestion/github_types.py
    - src/ai_washer/db/migrations/versions/005_add_github_repos.py
    - tests/unit/test_github_types.py
  modified:
    - src/ai_washer/db/models.py
    - src/ai_washer/config.py

key-decisions:
  - "ML_FRAMEWORK_PATTERNS and ML_LANGUAGES are domain constants, not user-configurable"
  - "GITHUB_SIGNAL_VERSION = 0.6.0 matching phase numbering convention"
  - "Idempotent daily collection via unique constraint on (company_id, repo_full_name, observed_date)"

patterns-established:
  - "GitHub type contracts follow patent_types.py pattern: API schema, snapshot, collection result"
  - "GitHubRepo ORM model follows Patent model pattern with AppendOnlyMixin"

requirements-completed: [GH-01]

duration: 2min
completed: 2026-03-29
---

# Phase 6 Plan 01: GitHub Signal Foundation Summary

**GitHub type contracts (GitHubRepoRecord/OrgSnapshot/CollectionResult), ORM model with idempotent collection, Alembic migration, and GitHubActivityScoringConfig**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-29T08:10:29Z
- **Completed:** 2026-03-29T08:12:50Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments
- GitHubRepoRecord, GitHubOrgSnapshot, GitHubCollectionResult type contracts with full validation
- ML_FRAMEWORK_PATTERNS dict covering 7 framework families and ML_LANGUAGES tuple for 6 languages
- GitHubRepo ORM model with append-only mixin and idempotent unique constraint on (company_id, repo_full_name, observed_date)
- Alembic migration 005 creates github_repos table with compound indexes
- GitHubActivityScoringConfig added to ScoringConfig with max_repos_per_org, recency_decay_days, sigmoid params

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for GitHub types** - `2d46ff9` (test)
2. **Task 1 (GREEN): GitHub type contracts, ORM, migration, config** - `edbfb84` (feat)

## Files Created/Modified
- `src/ai_washer/ingestion/github_types.py` - Type contracts for GitHub signal (GitHubRepoRecord, GitHubOrgSnapshot, GitHubCollectionResult, ML constants)
- `src/ai_washer/db/models.py` - Added GitHubRepo ORM model (eighth table)
- `src/ai_washer/db/migrations/versions/005_add_github_repos.py` - Alembic migration for github_repos table
- `src/ai_washer/config.py` - Added GitHubActivityScoringConfig to ScoringConfig
- `tests/unit/test_github_types.py` - 9 unit tests covering all type contracts and config

## Decisions Made
- ML_FRAMEWORK_PATTERNS and ML_LANGUAGES are domain constants (not user-configurable) since they represent well-known ML ecosystem facts
- GITHUB_SIGNAL_VERSION = "0.6.0" following established phase numbering convention
- Idempotent daily collection via unique constraint on (company_id, repo_full_name, observed_date) -- same pattern as Patent and Filing models

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Type contracts ready for Plans 02-04 to build against
- GitHubRepo model ready for persistence in GitHub collector
- GitHubActivityScoringConfig ready for scorer configuration
- All 7 ML framework patterns defined for dependency scanning

---
*Phase: 06-github-signal*
*Completed: 2026-03-29*
