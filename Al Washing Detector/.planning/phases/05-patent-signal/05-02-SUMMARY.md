---
phase: 05-patent-signal
plan: 02
subsystem: ingestion
tags: [httpx, tenacity, patentsview, patents, cpc, pagination, rate-limiting]

# Dependency graph
requires:
  - phase: 05-01
    provides: PatentRecord, PatentForScoring, PatentCollectionResult types, CPC_AI_PREFIXES, Patent ORM model, PatentGapScoringConfig
provides:
  - PatentSearchClient for querying PatentSearch API with CPC filters
  - PatentCollector for incremental patent collection with assignee alias expansion
  - Full ingestion __init__.py exports for patent modules
affects: [05-03, scoring-orchestrator, cli]

# Tech tracking
tech-stack:
  added: []
  patterns: [cursor-based pagination, lazy API key validation, cross-assignee deduplication]

key-files:
  created:
    - src/ai_washer/ingestion/patent_client.py
    - src/ai_washer/ingestion/patent_collector.py
    - tests/unit/test_patent_client.py
    - tests/unit/test_patent_collector.py
  modified:
    - src/ai_washer/ingestion/__init__.py

key-decisions:
  - "Lazy API key validation: PatentSearchClient accepts empty key at construction but raises PatentClientError on search, matching orchestrator skip pattern"
  - "Cursor-based pagination using last patent_id from full pages, capped at 10 pages for safety"
  - "Cross-assignee deduplication by patent_id before persistence, not after DB insert"

patterns-established:
  - "PatentSearchClient pattern: httpx GET with X-Api-Key header, tenacity retry on 429/5xx, cursor pagination"
  - "PatentCollector pattern: search all assignee aliases, deduplicate, persist incrementally with collection metadata"
  - "Lazy validation pattern: construct client without key, raise on actual use (enables orchestrator skip logic)"

requirements-completed: [PAT-01, PAT-03]

# Metrics
duration: 11min
completed: 2026-03-28
---

# Phase 5 Plan 02: Patent Client and Collector Summary

**PatentSearch API client with CPC _begins filters, cursor pagination, and tenacity retries, plus PatentCollector with assignee alias expansion and incremental collection**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-28T22:13:34Z
- **Completed:** 2026-03-28T22:25:30Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- PatentSearchClient queries PatentSearch API with correct _begins CPC filters (G06N, G06F18) and _contains assignee filter
- Cursor-based pagination handles large patent portfolios with 10-page safety cap
- Rate limiting via tenacity retries 429/5xx with exponential backoff (min=0.1s, max=60s)
- PatentCollector searches all patent_assignee aliases from entity resolution table
- Incremental collection via MAX(patent_date) per company avoids refetching old patents
- Cross-assignee deduplication by patent_id before persistence
- 24 unit tests passing with pytest-httpx mocks and mock sessions

## Task Commits

Each task was committed atomically:

1. **Task 1: PatentSearch API client with pagination and rate limiting** - `c96716b` (test) + `6ecf969` (feat)
2. **Task 2: Patent collector with incremental collection and assignee alias expansion** - `9945a60` (test) + `06fb28f` (feat)

_TDD tasks have separate test and implementation commits_

## Files Created/Modified
- `src/ai_washer/ingestion/patent_client.py` - PatentSearchClient with search_by_assignee, _build_query, _fetch_page, tenacity retry
- `src/ai_washer/ingestion/patent_collector.py` - PatentCollector with collect_for_company, collect_all, incremental logic, alias expansion
- `src/ai_washer/ingestion/__init__.py` - Added exports for PatentSearchClient, PatentClientError, PatentCollector, PatentRecord, PatentForScoring, PatentCollectionResult, CPC_AI_PREFIXES, PATENT_SIGNAL_VERSION
- `tests/unit/test_patent_client.py` - 16 unit tests for API client query construction, pagination, error handling
- `tests/unit/test_patent_collector.py` - 8 unit tests for collector alias expansion, incremental logic, deduplication, error handling

## Decisions Made
- Lazy API key validation: PatentSearchClient accepts empty key at construction but raises PatentClientError on search. This allows the orchestrator to construct the client and skip the patent signal gracefully when no key is configured.
- Cursor-based pagination uses the last patent_id from a full page as the "after" cursor, capped at 10 pages (1000 patents) for safety.
- Cross-assignee deduplication happens in-memory by patent_id before any DB persistence, avoiding unnecessary DB existence checks for duplicates found across name variations.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required

None - no external service configuration required. PatentsView API key should be set in .env as PATENTSVIEW_API_KEY when available.

## Next Phase Readiness
- Patent client and collector ready for Plan 03 (patent gap scorer and orchestrator integration)
- PatentSearchClient provides clean interface for scoring orchestrator to consume
- All patent types exported from ingestion package for downstream use

## Self-Check: PASSED

All files and commits verified:
- 5 files: all FOUND
- 4 commits: all FOUND (c96716b, 6ecf969, 9945a60, 06fb28f)

---
*Phase: 05-patent-signal*
*Completed: 2026-03-28*
