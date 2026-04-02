---
phase: 03-sec-filing-collection
plan: 04
subsystem: ingestion
tags: [sec, edgar, xbrl, filing-collector, cli, orchestrator, idempotent]

# Dependency graph
requires:
  - phase: 03-sec-filing-collection
    provides: "FilingClient (Plan 02), XBRLExtractor (Plan 03), Filing/XBRLFact ORM models (Plan 01)"
provides:
  - "FilingCollector orchestrator class for end-to-end filing collection pipeline"
  - "CLI collect company/all subcommands with --dry-run"
  - "Idempotent daily collection with dual timestamps"
affects: [04-sec-scoring-and-compute, 10-pipeline-automation]

# Tech tracking
tech-stack:
  added: []
  patterns: [orchestrator-pattern, idempotent-collection, dual-timestamp-persistence, cli-subcommand-group]

key-files:
  created:
    - src/ai_washer/ingestion/filing_collector.py
    - tests/unit/test_filing_collector.py
    - tests/unit/test_cli_filings.py
  modified:
    - src/ai_washer/cli.py
    - src/ai_washer/ingestion/__init__.py

key-decisions:
  - "Inter-company rate limit delay of 1.0s in collect_all to respect SEC 10 req/sec limit"
  - "Collector version string (0.3.0) embedded in collection_metadata for traceability"
  - "Session opened per collect_for_company call (not shared across companies) for isolation"

patterns-established:
  - "Orchestrator pattern: coordinates client + extractor + session in a single pipeline"
  - "Idempotent persistence: query-before-insert using unique constraint columns"
  - "CLI sub-typer groups: collect_app with company/all subcommands following universe_app pattern"

requirements-completed: [SEC-01, SEC-03, SEC-05]

# Metrics
duration: 5min
completed: 2026-03-28
---

# Phase 3 Plan 4: Filing Collection Orchestrator Summary

**FilingCollector orchestrator wiring FilingClient + XBRLExtractor into idempotent DB pipeline with CLI collect company/all commands**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-28T08:55:51Z
- **Completed:** 2026-03-28T09:01:41Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- FilingCollector orchestrates per-company filing retrieval and XBRL extraction with idempotent daily runs
- Dual timestamps on all persisted records: as_of_date (business date), observed_date (collection date)
- CLI provides `collect company <ticker>` and `collect all` with --dry-run for manual collection
- 376 total tests passing with 17 new tests (10 collector + 7 CLI), no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: FilingCollector orchestrator with idempotent persistence** - `39201e2` (feat)
2. **Task 2: CLI collect subcommands and ingestion exports** - `2b4d71a` (feat)

_Note: TDD tasks used red/green cycle (test file + implementation in single commit)_

## Files Created/Modified
- `src/ai_washer/ingestion/filing_collector.py` - FilingCollector orchestrator class (~280 lines)
- `tests/unit/test_filing_collector.py` - 10 unit tests for collector behaviors
- `tests/unit/test_cli_filings.py` - 7 unit tests for CLI collect commands
- `src/ai_washer/cli.py` - Added collect_app Typer group with company/all subcommands
- `src/ai_washer/ingestion/__init__.py` - Added FilingCollector to package exports

## Decisions Made
- Inter-company rate limit delay of 1.0s in collect_all (conservative vs SEC 10 req/sec limit, since each company makes multiple API calls)
- Collector version string (0.3.0) embedded in collection_metadata for audit traceability
- Session opened per collect_for_company call rather than shared across companies for isolation and error containment
- FilingClient and XBRLExtractor created as context managers within collect_for_company (not shared across calls) for clean resource lifecycle

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - all data paths are wired to real implementations.

## Next Phase Readiness
- Phase 3 SEC filing collection pipeline is complete end-to-end
- All four plans delivered: data contracts, filing client, XBRL extractor, and collection orchestrator
- Ready for Phase 4 SEC scoring which will consume the collected filings and XBRL facts
- CLI provides manual collection commands for testing and debugging

## Self-Check: PASSED

- All 5 created/modified files exist on disk
- Both task commits found in git log (39201e2, 2b4d71a)
- All 17 acceptance criteria verified via grep
- 376 unit tests passing, no regressions

---
*Phase: 03-sec-filing-collection*
*Completed: 2026-03-28*
