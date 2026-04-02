---
phase: 03-sec-filing-collection
plan: 01
subsystem: database
tags: [sqlalchemy, pydantic, alembic, xbrl, sec-filings, orm]

# Dependency graph
requires:
  - phase: 01-project-skeleton-and-database
    provides: "Base, AppendOnlyMixin, DualTimestampMixin, Company model, Alembic framework"
  - phase: 02-universe-builder-and-entity-resolution
    provides: "Company model with CIK, ingestion package structure, config.py patterns"
provides:
  - "FilingData, FilingSections, XBRLFactRecord, XBRLTagGroup, CollectionResult Pydantic schemas"
  - "XBRL_TAG_GROUPS constant with rd_expense, capex, revenue fallback tag lists"
  - "Filing ORM model (sec_filings table) with idempotency unique constraint"
  - "XBRLFact ORM model (xbrl_facts table) with dedup unique constraint"
  - "Alembic migration 003 creating both tables with indexes"
  - "FilingCollectionSettings for configurable collection parameters"
affects: [03-02-filing-client, 03-03-xbrl-extractor, 03-04-collector-orchestrator, 04-sec-signal-scoring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pydantic Literal type for constrained form_type field (10-K, 10-Q, 8-K)"
    - "XBRL tag fallback lists per financial concept (ordered, first-match wins)"
    - "Unique index for idempotent filing collection (company_id, form_type, accession_no)"
    - "Unique index for XBRL fact dedup (company_id, concept, end_date, fiscal_period)"

key-files:
  created:
    - "src/ai_washer/ingestion/types.py"
    - "src/ai_washer/db/migrations/versions/003_add_filing_tables.py"
    - "tests/unit/test_filing_types.py"
    - "tests/unit/test_filing_models.py"
  modified:
    - "src/ai_washer/db/models.py"
    - "src/ai_washer/config.py"

key-decisions:
  - "Literal type constraint on FilingData.form_type for compile-time safety"
  - "XBRL_TAG_GROUPS as module-level constant (not config) since tags are SEC standard, not user-configurable"
  - "BigInteger for XBRLFact.value_cents to handle large monetary values (trillions in cents)"
  - "Separate unique constraints for Filing (by accession) and XBRLFact (by concept+period) matching different dedup needs"

patterns-established:
  - "Ingestion types.py pattern: Pydantic schemas per subpackage for system-boundary validation"
  - "XBRL tag fallback pattern: ordered list of alternative us-gaap tags per financial concept"
  - "Idempotency via unique DB constraint: check-before-insert at DB level, not application level"

requirements-completed: [SEC-01, SEC-03, SEC-05]

# Metrics
duration: 17min
completed: 2026-03-28
---

# Phase 3 Plan 1: SEC Filing Data Contracts and Storage Layer Summary

**Pydantic type schemas (FilingData, XBRLFactRecord, CollectionResult) with XBRL tag fallback lists, Filing and XBRLFact ORM models with idempotency indexes, and Alembic migration 003**

## Performance

- **Duration:** 17 min
- **Started:** 2026-03-28T06:27:58Z
- **Completed:** 2026-03-28T08:28:39Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Defined complete Pydantic type contracts for SEC filing collection pipeline: FilingData, FilingSections, XBRLFactRecord, XBRLTagGroup, CollectionResult
- Created XBRL_TAG_GROUPS constant mapping 3 financial concepts (rd_expense, capex, revenue) to ordered fallback XBRL tag lists
- Added Filing and XBRLFact ORM models with AppendOnlyMixin, dual timestamps, and unique constraints for idempotent collection
- Created Alembic migration 003 chaining from 002, creating sec_filings and xbrl_facts tables with all indexes
- Added FilingCollectionSettings to config.py with configurable form types, section char limits, and filing count caps
- 79 new unit tests (41 for types + 38 for models), all 321 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Define Pydantic type contracts and FilingCollectionSettings** - `a6f9a8c` (feat)
2. **Task 2: Add Filing and XBRLFact ORM models with Alembic migration 003** - `a1620f1` (feat)

## Files Created/Modified
- `src/ai_washer/ingestion/types.py` - FilingData, FilingSections, XBRLFactRecord, XBRLTagGroup, CollectionResult, XBRL_TAG_GROUPS
- `src/ai_washer/config.py` - Added FilingCollectionSettings with form_types, section_max_chars, max filing counts
- `src/ai_washer/db/models.py` - Added Filing and XBRLFact ORM models with AppendOnlyMixin and indexes
- `src/ai_washer/db/migrations/versions/003_add_filing_tables.py` - Creates sec_filings and xbrl_facts tables
- `tests/unit/test_filing_types.py` - 41 tests for Pydantic types and settings validation
- `tests/unit/test_filing_models.py` - 38 tests for ORM model metadata and migration structure

## Decisions Made
- Used Literal["10-K", "10-Q", "8-K"] on FilingData.form_type for compile-time constraint instead of runtime validator
- XBRL_TAG_GROUPS defined as module constant (not YAML config) since XBRL tags are SEC standards, not user-tunable
- BigInteger for value_cents on XBRLFact to handle companies with trillion-dollar revenues in cents representation
- Filing idempotency keyed on (company_id, form_type, accession_no) since accession_no is globally unique per filing
- XBRLFact dedup keyed on (company_id, concept, end_date, fiscal_period) since same fact can appear in multiple filings

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- pytest subprocess execution hung consistently (background process output capture zero bytes); resolved by running pytest in-process via `pytest.main()` call instead of subprocess invocation. Root cause likely sandbox buffering interaction with pytest's output capture.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All type contracts and database models ready for Plan 02 (Filing Client) to implement edgartools wrapper
- XBRL_TAG_GROUPS ready for Plan 03 (XBRL Extractor) to use for multi-tag extraction
- FilingCollectionSettings ready for Plan 04 (Collector Orchestrator) to configure collection behavior
- Migration 003 ready for integration tests in downstream plans

## Self-Check: PASSED

All files verified present, all commits found in git log.

---
*Phase: 03-sec-filing-collection*
*Completed: 2026-03-28*
