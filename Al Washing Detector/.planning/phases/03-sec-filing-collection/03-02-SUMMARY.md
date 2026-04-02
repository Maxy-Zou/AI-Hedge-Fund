---
phase: 03-sec-filing-collection
plan: 02
subsystem: ingestion
tags: [edgartools, sec-edgar, filing-client, 10-K, 10-Q, 8-K, sha256, structlog]

# Dependency graph
requires:
  - phase: 03-sec-filing-collection
    plan: 01
    provides: "FilingData, FilingSections, FilingCollectionSettings Pydantic types"
provides:
  - "FilingClient class wrapping edgartools for SEC filing retrieval"
  - "Section extraction (business, risk_factors, mda) from 10-K/10-Q filings"
  - "Content hashing (SHA-256) for deduplication"
  - "Package-level exports for FilingClient and all types"
affects: [03-sec-filing-collection, 04-sec-signal-scoring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "edgartools Company/TenK/TenQ bracket notation for section access"
    - "Content hash via SHA-256 of concatenated sections"
    - "Section length validation with full_text_excerpt fallback for Pitfall 1"

key-files:
  created:
    - src/ai_washer/ingestion/filing_client.py
    - tests/unit/test_filing_client.py
  modified:
    - src/ai_washer/ingestion/__init__.py
    - docs/PROGRESS.md

key-decisions:
  - "edgartools bracket notation for TenK/TenQ section access (Item 1, Item 1A, Item 7)"
  - "SHA-256 content hash of concatenated section text for deduplication"
  - "500-char minimum for section validation with full_text_excerpt fallback"

patterns-established:
  - "FilingClient follows same context manager pattern as EdgarFactsClient/EFTSClient"
  - "Section extraction via filing.obj() then bracket notation on typed object"
  - "Graceful degradation: errors return empty list, never crash"

requirements-completed: [SEC-01, SEC-05]

# Metrics
duration: 19min
completed: 2026-03-28
---

# Phase 3 Plan 2: SEC Filing Client Summary

**FilingClient wrapping edgartools for 10-K/10-Q/8-K retrieval with section extraction, content hashing, and Pitfall 1 validation**

## Performance

- **Duration:** 19 min
- **Started:** 2026-03-28T08:31:52Z
- **Completed:** 2026-03-28T08:50:52Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- FilingClient retrieves 10-K, 10-Q, 8-K filings for any CIK via edgartools with section extraction
- Section text validated (>= 500 chars) with full_text_excerpt fallback when sections are suspiciously short
- Content hash computed as SHA-256 of concatenated section text for deduplication
- All 15 new unit tests passing (359 total), mocked edgartools for isolation

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement FilingClient with edgartools wrapper and section extraction** - `07c2abe` (test: failing tests) + `02e6eed` (feat: implementation)
2. **Task 2: Update ingestion __init__.py exports** - `53f0f6a` (feat)

## Files Created/Modified
- `src/ai_washer/ingestion/filing_client.py` - FilingClient class wrapping edgartools for filing retrieval and section extraction
- `tests/unit/test_filing_client.py` - 15 unit tests with mocked edgartools objects
- `src/ai_washer/ingestion/__init__.py` - Added FilingClient, FilingData, FilingSections, XBRLFactRecord, XBRL_TAG_GROUPS, CollectionResult exports
- `docs/PROGRESS.md` - Updated with Phase 3 Plan 2 entry

## Decisions Made
- Used edgartools bracket notation (`tenk["Item 1"]`, `tenk["Item 1A"]`, `tenk["Item 7"]`) for TenK section access -- maps directly to SEC filing item numbers
- SHA-256 of concatenated section text as content_hash -- deterministic, fast, and sufficient for deduplication
- 500-character minimum for section validation -- shorter text is likely a table-of-contents stub, not real content (Pitfall 1 from research)
- Used `filing_date` (string) and `report_date` (string) directly from CompanyFiling init params -- avoids calling `period_of_report` property which triggers network calls via `sgml()`
- `_to_iterable` detects single filing by checking for `accession_no` and `obj` attributes -- edgartools `latest(1)` returns single object, `latest(n>1)` returns iterable

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed MagicMock __getitem__ signature for test mocks**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** MagicMock passes the mock instance as first arg to `__getitem__`, so bracket_access function needed `(self, key)` not just `(key)`
- **Fix:** Added `_self: object` parameter to bracket_access functions in test helpers
- **Files modified:** tests/unit/test_filing_client.py
- **Verification:** All 15 tests pass
- **Committed in:** 02e6eed (part of Task 1 GREEN commit)

**2. [Rule 1 - Bug] Fixed _to_iterable detection for single filing vs collection**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** `hasattr(latest, "__iter__")` check failed because MagicMock always has `__iter__`, and real CompanyFiling does not. Caused single filing to be iterated incorrectly.
- **Fix:** Changed detection to check for `accession_no` and `obj` attributes (unique to individual filings) instead of `__iter__`
- **Files modified:** src/ai_washer/ingestion/filing_client.py
- **Verification:** All 15 tests pass including single and multi-filing scenarios
- **Committed in:** 02e6eed (part of Task 1 GREEN commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both auto-fixes necessary for correctness of mock testing and edgartools API handling. No scope creep.

## Issues Encountered
- edgartools `CompanyFiling.period_of_report` property calls `self.sgml()` which triggers network calls. Used `report_date` from init params instead to avoid real EDGAR calls in production code.
- Test collection appeared stuck during one run (edgartools import warming up on first load). Resolved by retrying -- subsequent runs completed in ~2 seconds.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- FilingClient ready for use by the FilingCollector orchestrator (Plan 04)
- All types and exports in place for downstream consumption
- Combined with Plan 01 (types + DB models) and Plan 03 (XBRL extractor), the collection layer has all building blocks for the orchestrator

## Self-Check: PASSED

- [x] src/ai_washer/ingestion/filing_client.py exists
- [x] tests/unit/test_filing_client.py exists
- [x] src/ai_washer/ingestion/__init__.py exists
- [x] .planning/phases/03-sec-filing-collection/03-02-SUMMARY.md exists
- [x] Commit 07c2abe found (test: failing tests)
- [x] Commit 02e6eed found (feat: implementation)
- [x] Commit 53f0f6a found (feat: exports)

---
*Phase: 03-sec-filing-collection*
*Completed: 2026-03-28*
