---
phase: 07-earnings-call-signal
plan: 02
subsystem: ingestion
tags: [earningscall, transcript, cli, tenacity, pydantic]

# Dependency graph
requires:
  - phase: 07-earnings-call-signal/07-01
    provides: TranscriptRecord, EarningsCollectionResult types, EarningsTranscript ORM model, EarningsVaguenessScoringConfig
provides:
  - EarningsClient wrapper with lazy key validation and retry
  - EarningsCollector orchestrator with idempotent transcript persistence
  - CLI earnings company/all commands
affects: [07-earnings-call-signal/07-03, 07-earnings-call-signal/07-04]

# Tech tracking
tech-stack:
  added: []
  patterns: [earningscall library integration, transcript_text JSONB string-only contract]

key-files:
  created:
    - src/ai_washer/ingestion/earnings_client.py
    - src/ai_washer/ingestion/earnings_collector.py
    - tests/unit/test_earnings_client.py
    - tests/unit/test_earnings_collector.py
  modified:
    - src/ai_washer/cli.py

key-decisions:
  - "transcript_text JSONB stores only string values (full_text, prepared_remarks, qa); speakers dict goes in collection_metadata"
  - "EarningsClient uses tenacity retry on ConnectionError (3 attempts, 0.1-10s exponential backoff)"
  - "Default 8 quarters (2 years) of transcript history per company"

patterns-established:
  - "transcript_text string-only contract: downstream scorer concatenates all non-None values expecting strings"
  - "earningscall module-level api_key: set before each call since library uses global state"

requirements-completed: [EARN-01, EARN-05]

# Metrics
duration: 5min
completed: 2026-03-29
---

# Phase 7 Plan 02: Earnings Client & Collector Summary

**EarningsClient wrapping earningscall library with lazy key validation, EarningsCollector with idempotent quarterly transcript persistence, and CLI earnings commands**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-29T18:28:44Z
- **Completed:** 2026-03-29T18:33:48Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- EarningsClient wraps earningscall library with lazy API key validation, tenacity retry, and TranscriptRecord output
- EarningsCollector orchestrates idempotent transcript collection for single company or all active companies
- Critical data contract: transcript_text JSONB stores only string sections; speakers dict stored in collection_metadata
- CLI commands: `ai-washer earnings company TICKER` and `ai-washer earnings all`
- 12 unit tests passing (6 client + 6 collector) with fully mocked external calls

## Task Commits

Each task was committed atomically:

1. **Task 1: EarningsClient API wrapper with lazy validation and retry** - `7af22ee` (feat)
2. **Task 2: EarningsCollector orchestrator with idempotent persistence and CLI commands** - `4eba3c5` (feat)

_Note: TDD tasks with test-first RED/GREEN flow_

## Files Created/Modified
- `src/ai_washer/ingestion/earnings_client.py` - EarningsClient wrapper with lazy key validation, retry, TranscriptRecord output
- `src/ai_washer/ingestion/earnings_collector.py` - EarningsCollector orchestrator with idempotent DB persistence
- `src/ai_washer/cli.py` - Added earnings_app Typer group with company/all commands
- `tests/unit/test_earnings_client.py` - 6 tests: lazy validation, transcript retrieval, quarter enumeration, error handling
- `tests/unit/test_earnings_collector.py` - 6 tests: persistence, idempotency, counts, error handling, collect_all, JSONB contract

## Decisions Made
- transcript_text JSONB stores only string values (full_text, prepared_remarks, qa); speakers dict goes in collection_metadata -- enforces downstream scorer contract
- EarningsClient uses tenacity retry on ConnectionError (3 attempts, 0.1-10s exponential backoff) -- consistent with project retry pattern
- Default 8 quarters (2 years) of transcript history per company -- matches scoring window needs
- earningscall module-level api_key set before each call since library uses global state

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed MagicMock .name attribute issue in tests**
- **Found during:** Task 1 (test GREEN phase)
- **Issue:** MagicMock has a special `.name` attribute that cannot be set via constructor kwargs; speaker_info.name returned a mock object instead of "Tim Cook"
- **Fix:** Created mock_speaker_info separately and set `.name` attribute via assignment
- **Files modified:** tests/unit/test_earnings_client.py
- **Verification:** All 6 tests pass
- **Committed in:** 7af22ee (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor test fix, no scope change.

## Issues Encountered
None beyond the MagicMock name attribute quirk documented above.

## Known Stubs
None - all data flows are wired. prepared_remarks and qa fields in transcript_text are set to None because the earningscall library returns these as separate transcript attributes (text, prepared_remarks, questions_and_answers) which will be populated when the library provides them.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- EarningsClient and EarningsCollector ready for use by scoring pipeline (Plan 04)
- FinBERT sentiment analysis (Plan 03) can import transcripts from the database
- CLI commands available for manual testing with real API key

---
*Phase: 07-earnings-call-signal*
*Completed: 2026-03-29*
