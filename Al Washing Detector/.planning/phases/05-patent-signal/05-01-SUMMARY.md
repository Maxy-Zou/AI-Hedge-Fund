---
phase: 05-patent-signal
plan: 01
subsystem: database, ingestion
tags: [pydantic, sqlalchemy, alembic, patents, uspto, cpc-codes]

requires:
  - phase: 01-skeleton
    provides: AppendOnlyMixin, Base ORM class, ScoringConfig infrastructure
  - phase: 04-sec-scoring-and-compute-signal
    provides: Frozen dataclass pattern (FilingForScoring), scoring config pattern

provides:
  - PatentRecord Pydantic schema for API response validation
  - PatentForScoring frozen dataclass for immutable scoring inputs
  - PatentCollectionResult for operational tracking
  - CPC_AI_PREFIXES constant for AI patent classification
  - PATENT_SIGNAL_VERSION constant for audit traceability
  - Patent ORM model with append-only design
  - Alembic migration 004 for patents table
  - PatentGapScoringConfig in scoring config
  - AppSettings with patentsview_api_key and patentsview_base_url

affects: [05-patent-signal, scoring-orchestrator]

tech-stack:
  added: []
  patterns: [frozen-dataclass-for-scoring-input, cpc-prefix-constant-for-ai-classification]

key-files:
  created:
    - src/ai_washer/ingestion/patent_types.py
    - src/ai_washer/db/migrations/versions/004_add_patent_table.py
    - tests/unit/test_patent_types.py
  modified:
    - src/ai_washer/db/models.py
    - src/ai_washer/config.py
    - config/scoring.yaml

key-decisions:
  - "CPC_AI_PREFIXES as tuple constant (G06N, G06F18) for AI patent identification per PatentSearch API _begins filter"
  - "Patent model uses String(20) for patent_id, String(500) for title/assignee, JSONB for cpc_codes array"
  - "PatentGapScoringConfig uses same sigmoid normalization pattern as SEC and compute scoring"

patterns-established:
  - "Patent type contracts follow ingestion/types.py CollectionResult pattern"
  - "PatentForScoring follows analysis/types.py FilingForScoring frozen dataclass pattern"

requirements-completed: [PAT-01, PAT-03]

duration: 3min
completed: 2026-03-28
---

# Phase 5 Plan 01: Patent Signal Types and Schema Summary

**Patent type contracts with Pydantic validation, frozen scoring dataclass, Patent ORM model with append-only design, Alembic migration 004, and PatentGapScoringConfig**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-28T22:07:04Z
- **Completed:** 2026-03-28T22:10:52Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- PatentRecord Pydantic schema validates USPTO API responses at ingestion boundary with min_length constraints
- PatentForScoring frozen dataclass provides immutable scoring inputs with tuple-based cpc_codes
- Patent ORM model follows AppendOnlyMixin pattern with unique constraint on (company_id, patent_id) for idempotent collection
- Alembic migration 004 creates patents table with date and uniqueness indexes
- PatentGapScoringConfig extends ScoringConfig with window_years and sigmoid parameters
- AppSettings extended with patentsview_api_key and patentsview_base_url for API configuration

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Patent type tests** - `bf94d76` (test)
2. **Task 1 (GREEN): Patent type contracts** - `757d5d5` (feat)
3. **Task 2: Patent ORM model, migration, config** - `ec1addc` (feat)

_TDD task had separate RED and GREEN commits._

## Files Created/Modified
- `src/ai_washer/ingestion/patent_types.py` - PatentRecord, PatentForScoring, PatentCollectionResult, CPC_AI_PREFIXES, PATENT_SIGNAL_VERSION
- `src/ai_washer/db/models.py` - Patent ORM model with AppendOnlyMixin
- `src/ai_washer/db/migrations/versions/004_add_patent_table.py` - Alembic migration for patents table
- `src/ai_washer/config.py` - PatentGapScoringConfig, patentsview_api_key/base_url in AppSettings
- `config/scoring.yaml` - patent_gap section with default parameters
- `tests/unit/test_patent_types.py` - 14 unit tests covering all type contracts

## Decisions Made
- CPC_AI_PREFIXES defined as tuple constant (G06N, G06F18) matching PatentSearch API _begins filter values
- Patent model uses String(20) for patent_id to accommodate USPTO format (e.g., US-12345678-A1)
- PatentGapScoringConfig uses same sigmoid normalization pattern as SEC and compute scoring for consistency
- PATENT_SIGNAL_VERSION set to 0.5.0 following Phase 5 numbering convention (matching 0.4.0 from Phase 4)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Patent type contracts ready for Plan 02 (patent client and collector)
- Patent ORM model ready for persistence layer
- PatentGapScoringConfig ready for Plan 03 (scorer and orchestrator)
- All 14 unit tests passing, no regressions in existing 85 config/model tests

## Self-Check: PASSED

All 7 files verified present. All 3 commit hashes verified in git log.

---
*Phase: 05-patent-signal*
*Completed: 2026-03-28*
