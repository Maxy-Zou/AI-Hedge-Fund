---
phase: 02-entity-resolution-and-universe-builder
plan: 02
subsystem: ingestion
tags: [httpx, sec-edgar, efts, xbrl, tenacity, structlog, pytest-httpx]

# Dependency graph
requires:
  - phase: 02-entity-resolution-and-universe-builder/01
    provides: "Pydantic type contracts (EFTSHit, EFTSResponse, MarketCapRange), AppSettings with edgar_identity, UniverseSettings"
provides:
  - "EFTSClient: paginated EFTS full-text search with truncation detection"
  - "EdgarFactsClient: XBRL EntityPublicFloat extraction in cents"
  - "CIK normalization utilities (pad_cik, strip_cik)"
  - "CIK-ticker mapping from SEC company_tickers.json"
  - "Convenience wrappers: search_filings(), get_entity_public_float(), get_cik_ticker_mapping()"
affects: [02-entity-resolution-and-universe-builder/04, 03-sec-filing-collection]

# Tech tracking
tech-stack:
  added: [structlog, pytest-httpx]
  patterns: [httpx-client-with-context-manager, tenacity-retry-with-predicate, tdd-with-pytest-httpx-mocks]

key-files:
  created:
    - src/ai_washer/ingestion/efts_client.py
    - src/ai_washer/ingestion/edgar_client.py
    - tests/unit/test_efts_client.py
    - tests/unit/test_edgar_client.py
  modified:
    - src/ai_washer/ingestion/__init__.py
    - docs/PROGRESS.md

key-decisions:
  - "tenacity retry min wait set to 0.1s (not 2s) for testability while keeping exponential backoff shape"
  - "CIK stored as stripped string internally, padded only at API call boundary"
  - "EntityPublicFloat conversion uses int(val * 100) for dollar-to-cents without intermediate float rounding"

patterns-established:
  - "HTTP client pattern: class with __enter__/__exit__, httpx.Client in __init__, tenacity-decorated _fetch method"
  - "SEC API pattern: edgar_identity param propagated to User-Agent header on every request"
  - "Retry predicate pattern: separate _is_retryable_error function checking status codes, only 429 + 5xx retried"

requirements-completed: [FNDN-03]

# Metrics
duration: 5min
completed: 2026-03-27
---

# Phase 2 Plan 02: EFTS and EDGAR HTTP Clients Summary

**Paginated EFTS search client and EDGAR XBRL company facts client with tenacity retry, SEC User-Agent compliance, and full pytest-httpx unit test coverage**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-27T22:52:05Z
- **Completed:** 2026-03-27T22:57:08Z
- **Tasks:** 2 (both TDD red/green)
- **Files created:** 4
- **Files modified:** 2

## Accomplishments
- EFTSClient paginates through all EFTS results using offset-based `from` parameter, stops at 10K cap, detects truncated results via total_relation='gte'
- EdgarFactsClient fetches EntityPublicFloat from XBRL company facts API, converts dollars to cents, selects most recent filing by end date
- CIK normalization (pad_cik/strip_cik) handles all SEC CIK format variations consistently
- Both clients include SEC-compliant User-Agent, tenacity retry on 429/5xx, structlog structured logging
- 33 unit tests with full HTTP mock coverage, 0 real API calls in tests

## Task Commits

Each task was committed atomically with TDD RED then GREEN commits:

1. **Task 1: EFTS paginated search client**
   - `c9f4530` (test: failing tests for EFTS client)
   - `b69ce42` (feat: implement EFTS client with pagination and truncation detection)
2. **Task 2: EDGAR company facts client**
   - `b26126b` (test: failing tests for EDGAR client)
   - `c985cc1` (feat: implement EDGAR client with CIK-ticker mapping)

## Files Created/Modified
- `src/ai_washer/ingestion/efts_client.py` - EFTS paginated search client (EFTSClient, search_filings)
- `src/ai_washer/ingestion/edgar_client.py` - EDGAR company facts client (EdgarFactsClient, pad_cik, strip_cik)
- `src/ai_washer/ingestion/__init__.py` - Updated exports for both clients
- `tests/unit/test_efts_client.py` - 13 tests: pagination, truncation, User-Agent, retry, date range, validation
- `tests/unit/test_edgar_client.py` - 20 tests: EntityPublicFloat, CIK normalization, ticker mapping, retry
- `docs/PROGRESS.md` - Updated with plan completion details

## Decisions Made
- tenacity retry min wait set to 0.1s instead of 2s for fast test execution while preserving exponential backoff behavior in production
- CIK values stored as stripped strings internally (no leading zeros), padded to 10 digits only at the API call boundary to avoid format mismatch bugs
- EntityPublicFloat dollar-to-cents conversion uses `int(val * 100)` directly from the SEC-reported float value

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing structlog and pytest-httpx dependencies**
- **Found during:** Task 1 (pre-implementation dependency check)
- **Issue:** structlog and pytest-httpx were not installed in the venv despite being declared in pyproject.toml
- **Fix:** Ran `uv add structlog` and `uv add --dev pytest-httpx` followed by `uv sync`
- **Files modified:** pyproject.toml, uv.lock (already tracked by parallel agent)
- **Verification:** `python -c "import structlog; import pytest_httpx"` succeeds
- **Committed in:** dependency changes tracked in pyproject.toml/uv.lock

---

**Total deviations:** 1 auto-fixed (blocking dependency)
**Impact on plan:** Minimal -- standard dependency installation. No scope creep.

## Issues Encountered
- The `.venv/bin/activate` shell source does not work correctly in the execution environment; used `.venv/bin/python` directly for all commands instead.

## Known Stubs
None -- both clients are fully functional with no placeholder data or TODO markers.

## User Setup Required
None - no external service configuration required. Both clients read edgar_identity from AppSettings at runtime.

## Next Phase Readiness
- EFTS and EDGAR clients ready for universe builder (Plan 04) to orchestrate
- Plan 03 (entity resolution) and Plan 04 (universe builder) can import from `ai_washer.ingestion`
- All 206 unit tests passing (173 pre-existing + 33 new)

## Self-Check: PASSED

All 5 created files exist on disk. All 4 commit hashes found in git log.

---
*Phase: 02-entity-resolution-and-universe-builder*
*Completed: 2026-03-27*
