---
phase: 02-entity-resolution-and-universe-builder
plan: 03
subsystem: entity-resolution
tags: [rapidfuzz, fuzzy-matching, nlp, entity-resolution, sec-edgar]

requires:
  - phase: 02-entity-resolution-and-universe-builder
    plan: 01
    provides: "Pydantic type contracts (AliasesSchema, EntityResolutionResult, ResolutionMetadata), UniverseSettings with fuzzy_match_threshold"

provides:
  - "normalize_company_name function stripping legal suffixes for cross-source name matching"
  - "LEGAL_SUFFIXES constant with 20 legal suffix variants"
  - "EntityResolver class with configurable fuzzy threshold using rapidfuzz token_sort_ratio"
  - "resolve_entity convenience function for single entity resolution"
  - "resolve_batch for batch processing with structlog progress logging"
  - "Partial resolution support (null fields for missing sources per D-03)"
  - "Resolution metadata with confidence scoring and needs_review flagging"

affects: [02-04-universe-builder, 03-sec-filing-collection, 05-patent-signal, 08-job-posting-signal]

tech-stack:
  added: []
  patterns:
    - "Fuzzy matching via rapidfuzz token_sort_ratio + process.extractOne"
    - "Name normalization pipeline: upper -> strip punctuation -> collapse whitespace -> strip suffix"
    - "Exact match for short identifiers (GitHub org), fuzzy for long names (patent assignee, employer)"
    - "Longest-suffix-first ordering for correct greedy matching"

key-files:
  created:
    - src/ai_washer/entity/normalizer.py
    - src/ai_washer/entity/resolver.py
    - tests/unit/test_normalizer.py
    - tests/unit/test_entity_resolver.py
  modified:
    - src/ai_washer/entity/__init__.py

key-decisions:
  - "GitHub org uses exact match (lowered first word) instead of fuzzy -- short slugs produce too many false positives with fuzzy"
  - "Normalizer strips periods and commas before suffix matching so CORP. and CORP both work"
  - "Guard: name that equals a suffix (e.g., 'INC') is preserved, not stripped to empty"
  - "High confidence (>=95) sets needs_review=False; lower matches get flagged for review"
  - "Each data source resolved independently -- partial resolution is valid output per D-03"

patterns-established:
  - "Name normalization before fuzzy matching: always normalize both sides"
  - "Suffix stripping with longest-first ordering to prevent partial matches"
  - "Confidence-based review flagging with configurable thresholds"

requirements-completed: [FNDN-02]

duration: 3min
completed: 2026-03-27
---

# Phase 02 Plan 03: Entity Resolution Engine Summary

**Company name normalizer with legal suffix stripping + fuzzy entity resolver using rapidfuzz token_sort_ratio for cross-source identity mapping**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-27T22:52:03Z
- **Completed:** 2026-03-27T22:55:25Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Company name normalizer strips 20 legal suffix variants (Inc, Corp, LLC, Ltd, LP, etc.) with case/whitespace/punctuation normalization
- Entity resolver maps SEC names to patent assignees, employers, and GitHub orgs using rapidfuzz fuzzy matching
- Partial resolution accepted: null fields for missing data sources per D-03, enabling incremental enrichment
- Confidence scoring with review flagging: high confidence (>=95) auto-approved, lower matches flagged for review
- 61 unit tests covering all suffix variants, edge cases, fuzzy matching, batch resolution, and partial resolution

## Task Commits

Each task was committed atomically:

1. **Task 1: Build company name normalizer with legal suffix stripping** - `353f791` (feat)
2. **Task 2: Build entity resolver with fuzzy matching for cross-source identity mapping** - `6b94c63` (feat)

_Both tasks followed TDD red/green cycle._

## Files Created/Modified
- `src/ai_washer/entity/normalizer.py` - Company name normalization with LEGAL_SUFFIXES and normalize_company_name
- `src/ai_washer/entity/resolver.py` - EntityResolver class, resolve_entity, resolve_batch, fuzzy matching internals
- `src/ai_washer/entity/__init__.py` - Updated exports: EntityResolver, resolve_entity, normalize_company_name, all types
- `tests/unit/test_normalizer.py` - 37 parametrized tests for name normalization edge cases
- `tests/unit/test_entity_resolver.py` - 24 tests for entity resolution, partial resolution, confidence scoring

## Decisions Made
- GitHub org uses exact match (lowered first word) instead of fuzzy -- short slugs produce too many false positives with fuzzy matching
- Normalizer strips periods and commas before suffix matching so "CORP." and "CORP" both work without separate suffix entries
- Guard prevents stripping name to empty when entire name is a suffix word (e.g., "INC" stays "INC")
- High confidence (>=95) sets needs_review=False; matches between threshold and 95 get flagged for human review
- Each data source resolved independently -- patent_assignee and employer_names can succeed/fail independently

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Entity resolution engine ready for Plan 04 (universe builder) to use when populating Company.aliases
- normalize_company_name and EntityResolver exported from ai_washer.entity for direct import
- Fuzzy threshold configurable via UniverseSettings.fuzzy_match_threshold (default 85, from Plan 01)
- All downstream signal plans (SEC, patents, jobs, GitHub) can use entity resolution for name matching

## Self-Check: PASSED

- All 6 files verified present on disk
- Both task commits (353f791, 6b94c63) verified in git history
- 61 tests passing (37 normalizer + 24 resolver)
- Entity module importable: `from ai_washer.entity import EntityResolver, normalize_company_name`

---
*Phase: 02-entity-resolution-and-universe-builder*
*Completed: 2026-03-27*
