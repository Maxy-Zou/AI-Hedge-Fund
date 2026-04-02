---
phase: 06-github-signal
plan: 02
subsystem: ingestion
tags: [github, rest-api, httpx, tenacity, rate-limiting, ml-detection]

requires:
  - phase: 06-github-signal-01
    provides: "GitHubRepoRecord, GitHubOrgSnapshot types, ML_FRAMEWORK_PATTERNS, ML_LANGUAGES constants"
provides:
  - "GitHubClient with list_org_repos, get_repo_languages, get_file_content, scan_ml_frameworks, build_org_snapshot"
  - "GitHubClientError exception class"
  - "Rate limit tracking via x-ratelimit-remaining header"
  - "Tenacity retry on 429/5xx responses"
affects: [06-github-signal-03, 06-github-signal-04]

tech-stack:
  added: []
  patterns: ["GitHub REST API v3 Bearer token auth with API version header", "Lazy token validation pattern (accept empty at construction, raise on use)"]

key-files:
  created:
    - src/ai_washer/ingestion/github_client.py
    - tests/unit/test_github_client.py
  modified: []

key-decisions:
  - "Lazy token validation: GitHubClient accepts empty token at construction, raises GitHubClientError on first API call (consistent with PatentSearchClient pattern)"
  - "Fork filtering at client level: list_org_repos excludes forked repos before returning results"
  - "Raw content header for file fetching: uses Accept: application/vnd.github.raw+json to get decoded file content directly"

patterns-established:
  - "GitHub API client pattern: Bearer token auth, X-GitHub-Api-Version header, pagination via page parameter"
  - "ML framework detection: scan 4 dependency files (requirements.txt, pyproject.toml, setup.py, setup.cfg) for ML_FRAMEWORK_PATTERNS matches"

requirements-completed: [GH-01, GH-03]

duration: 3min
completed: 2026-03-29
---

# Phase 06 Plan 02: GitHub API Client Summary

**GitHubClient wrapping REST API v3 with Bearer auth, pagination, rate limit tracking, and ML framework detection from dependency files**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-29T08:14:42Z
- **Completed:** 2026-03-29T08:18:00Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- GitHubClient with 6 public methods: list_org_repos, get_repo_languages, get_file_content, scan_ml_frameworks, build_org_snapshot, close
- Rate limit tracking via x-ratelimit-remaining response header
- Tenacity retry on 429/5xx with exponential backoff (0.1s-60s, 5 attempts)
- 17 unit tests passing with pytest-httpx mocking and freezegun date control

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for GitHubClient** - `9a94a66` (test)
2. **Task 1 (GREEN): Implement GitHubClient** - `f710a0d` (feat)

## Files Created/Modified
- `src/ai_washer/ingestion/github_client.py` - GitHub REST API v3 client with auth, pagination, rate limiting, ML detection (340 lines)
- `tests/unit/test_github_client.py` - 17 unit tests covering all client methods (446 lines)

## Decisions Made
- Lazy token validation: consistent with PatentSearchClient pattern from Phase 5
- Fork filtering at client level in list_org_repos (not deferred to caller)
- Raw content Accept header (application/vnd.github.raw+json) for direct file text retrieval
- 404 on get_file_content returns None (no exception) for clean dependency file scanning

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all methods fully implemented and wired.

## Next Phase Readiness
- GitHubClient ready for use by Plan 03 (GitHub data collector/orchestrator)
- All types from Plan 01 (GitHubRepoRecord, GitHubOrgSnapshot) consumed correctly
- build_org_snapshot provides complete org-level ML activity snapshot

---
*Phase: 06-github-signal*
*Completed: 2026-03-29*
