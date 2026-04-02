---
phase: 03-sec-filing-collection
plan: 03
subsystem: ingestion
tags: [xbrl, edgar, sec, httpx, tenacity, pydantic, financial-data]

# Dependency graph
requires:
  - phase: 03-sec-filing-collection
    plan: 01
    provides: "XBRL_TAG_GROUPS, XBRLFactRecord types, EdgarFactsClient patterns (pad_cik, _is_retryable_error, XBRL_FACTS_URL)"
provides:
  - "XBRLExtractor class for fetching XBRL companyfacts from EDGAR API"
  - "extract_facts_for_concept pure function with fallback tag lists"
  - "deduplicate_by_period pure function for amended filing dedup"
  - "extract_all_facts pure function for all 3 financial concepts"
  - "Dollar-to-cents conversion for all monetary XBRL values"
affects: [04-sec-signal-scoring, compute-spending-gap]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure function + class separation: stateless extraction logic in module-level functions, HTTP in class"
    - "Tag fallback pattern: try ordered tag list, stop at first with USD entries"
    - "Deduplication by (end, fp) key with latest-filed-date wins"

key-files:
  created:
    - src/ai_washer/ingestion/xbrl_extractor.py
    - tests/unit/test_xbrl_extractor.py
  modified:
    - src/ai_washer/ingestion/__init__.py
    - docs/PROGRESS.md

key-decisions:
  - "Pure function + class pattern: extraction logic is testable without HTTP mocking; class only handles network"
  - "int(val * 100) for dollar-to-cents conversion matching EdgarFactsClient existing pattern"
  - "Monotonic clock for rate limiting (_last_request_time) avoids system clock jumps"

patterns-established:
  - "Pure function extraction: extract_facts_for_concept, deduplicate_by_period are stateless and HTTP-free"
  - "XBRLExtractor follows same context manager + tenacity retry pattern as EdgarFactsClient"

requirements-completed: [SEC-03, SEC-05]

# Metrics
duration: 8min
completed: 2026-03-28
---

# Phase 3 Plan 03: XBRL Extraction Summary

**XBRL financial fact extractor with fallback tag lists, period deduplication, and dollar-to-cents conversion for R&D, CapEx, and revenue from EDGAR companyfacts API**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-28T08:31:46Z
- **Completed:** 2026-03-28T08:39:48Z
- **Tasks:** 1 (TDD: RED -> GREEN)
- **Files modified:** 4

## Accomplishments
- Built XBRLExtractor class that fetches companyfacts JSON from EDGAR API with tenacity retry, rate limiting, and 404 graceful handling
- Implemented extract_facts_for_concept with ordered XBRL_TAG_GROUPS fallback -- tries each tag and uses first with USD entries
- Built deduplicate_by_period to handle amended filings (10-K/A): keeps latest filed date per (end, fp) pair
- Dollar-to-cents conversion via int(val * 100) preserves integer precision for financial data
- 23 new tests all passing (344 total), full TDD cycle

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing tests for XBRL extraction** - `b0e8e21` (test)
2. **Task 1 (GREEN): Implement XBRL fact extraction** - `757a319` (feat)

_TDD task: test commit followed by implementation commit._

## Files Created/Modified
- `src/ai_washer/ingestion/xbrl_extractor.py` - XBRLExtractor class + pure extraction functions (319 lines)
- `tests/unit/test_xbrl_extractor.py` - 23 tests covering tag fallback, dedup, conversion, HTTP, retry (488 lines)
- `src/ai_washer/ingestion/__init__.py` - Added XBRLExtractor, extract_facts_for_concept, extract_all_facts, deduplicate_by_period exports
- `docs/PROGRESS.md` - Updated with Phase 3 Plan 03 progress entry

## Decisions Made
- **Pure function + class pattern:** Extraction logic (extract_facts_for_concept, deduplicate_by_period, extract_all_facts) kept as module-level pure functions for testability without HTTP mocking. XBRLExtractor class handles only HTTP concerns.
- **int(val * 100) conversion:** Matches existing EdgarFactsClient.get_entity_public_float pattern for dollar-to-cents.
- **Monotonic clock for rate limiting:** Uses time.monotonic() instead of time.time() to avoid system clock jumps affecting SEC rate limit compliance.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- XBRL extraction ready for Phase 4 compute spending gap and R&D divergence scoring
- XBRLExtractor can be used in FilingCollector (Plan 04) for per-company XBRL data collection
- All pure functions are independently usable for offline analysis of cached companyfacts JSON

## Self-Check: PASSED

All files and commits verified:
- src/ai_washer/ingestion/xbrl_extractor.py: FOUND
- tests/unit/test_xbrl_extractor.py: FOUND
- .planning/phases/03-sec-filing-collection/03-03-SUMMARY.md: FOUND
- Commit b0e8e21 (test): FOUND
- Commit 757a319 (feat): FOUND

---
*Phase: 03-sec-filing-collection*
*Completed: 2026-03-28*
