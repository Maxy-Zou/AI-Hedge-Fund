---
phase: 02-data-ingestion
plan: 02
subsystem: sec-edgar-xbrl-tools
tags: [edgar, xbrl, filing-tools, financial-tools, temporal-controls, tenacity]
dependency_graph:
  requires: [02-01]
  provides: [edgar-client, xbrl-client, filing-tools, financial-tools]
  affects: [02-03, 02-04, 03-fundamental-agents]
tech_stack:
  added: []
  patterns: [EdgarClient-with-retry, XbrlClient-tag-fallback, filing-date-filtering, cents-conversion, section-extraction]
key_files:
  created:
    - src/ai_hedge_fund/data/clients/__init__.py
    - src/ai_hedge_fund/data/clients/edgar_client.py
    - src/ai_hedge_fund/data/clients/xbrl_client.py
    - src/ai_hedge_fund/data/tools/__init__.py
    - src/ai_hedge_fund/data/tools/filing_tools.py
    - src/ai_hedge_fund/data/tools/financial_tools.py
    - tests/unit/test_filing_tools.py
    - tests/unit/test_financial_tools.py
  modified: []
decisions:
  - Used MockFiling class instead of SimpleNamespace for test mocks (Python dunder __getitem__ requires class-level definition)
  - Operating margin computed from operating_income / revenue in cents (avoids separate XBRL tag for margin)
  - Non-monetary XBRL values (EPS, shares) stored as int(value * 100) for consistent XbrlFact model usage
metrics:
  duration: 7m
  completed: "2026-04-12T07:02:32Z"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 22
  files_created: 8
  files_modified: 0
---

# Phase 02 Plan 02: SEC EDGAR & XBRL Tools Summary

EdgarClient and XbrlClient wrapping edgartools with retry logic, filing_date filtering for look-ahead bias prevention, section extraction for 10-K/10-Q, XBRL tag fallback across 12 financial concepts, and NL summary generation via format_financial_summary.

## Completed Tasks

| # | Name | Commit | Tests |
|---|------|--------|-------|
| 1 | EDGAR filing client and filing retrieval tools | 9814fb2 | 12 |
| 2 | XBRL financial extraction client and financial summary tools | cddc42f | 10 |

## Key Artifacts

### EdgarClient (`src/ai_hedge_fund/data/clients/edgar_client.py`)
- `EdgarClient(edgar_identity)` -- sets SEC EDGAR identity, uses structlog
- `get_filings(ticker, form_type, max_filings)` -- retrieves filing metadata sorted by filing_date descending, tenacity retry
- `get_filing_sections(ticker, form_type, filing_date_cutoff, max_filings)` -- extracts named sections, filters by filing_date
  - 10-K: business (Item 1), risk_factors (Item 1A), mda (Item 7)
  - 10-Q: mda (part1item2)
  - Fallback to truncated full text (50k chars) when all sections None
- `_safe_section(filing, key)` -- safe bracket-notation access returning None on failure

### XbrlClient (`src/ai_hedge_fund/data/clients/xbrl_client.py`)
- `XBRL_TAG_GROUPS` -- 12 concept groups with fallback tag lists per concept
- `MONETARY_CONCEPTS` -- frozenset of concepts requiring cents conversion
- `XbrlClient(edgar_identity)` -- sets identity, tenacity retry
- `get_facts(ticker, concepts)` -- resolves tags via priority-order fallback, returns raw facts
- `get_financial_metrics(ticker, as_of_date)` -- filters by filed_date, groups by fiscal_year, converts monetary values to cents
- `_resolve_concept_facts(facts_df, tags)` -- tries XBRL tags in order, returns first match

### Filing Tools (`src/ai_hedge_fund/data/tools/filing_tools.py`)
- `get_filing_sections(ticker, as_of_date, form_type, db_session, settings)` -- @enforce_as_of_date decorated, validates edgar_identity, caches to SecFiling model

### Financial Tools (`src/ai_hedge_fund/data/tools/financial_tools.py`)
- `get_financial_summary(ticker, as_of_date, db_session, settings)` -- @enforce_as_of_date decorated, calls format_financial_summary for NL output, caches to XbrlFact model
- `_build_summary_text(ticker, fiscal_year, fiscal_period, metrics)` -- computes operating margin from raw metrics, calls format_financial_summary
- `_cache_xbrl_facts(db_session, ticker, fiscal_year, fiscal_period, metrics)` -- INSERT with duplicate check

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] MockFiling class for bracket-notation support**
- **Found during:** Task 1 TDD GREEN
- **Issue:** SimpleNamespace with instance-level `__getitem__` assignment doesn't support Python's bracket notation (`filing["Item 1"]`) because dunder methods must be defined at the class level
- **Fix:** Created `MockFiling` class with proper `__getitem__` method at class level
- **Files modified:** `tests/unit/test_filing_tools.py`

## Verification Results

- 22 unit tests passing (12 filing + 10 financial)
- ruff check clean on all new files
- All acceptance criteria from plan verified (14/14 grep checks pass)
- All tools use @enforce_as_of_date decorator
- All SEC queries filter on filing_date (not period end date)

## Threat Mitigations

| Threat ID | Status | Implementation |
|-----------|--------|----------------|
| T-02-04 | Mitigated | EdgarClient filters by filing_date via filing_date_cutoff parameter |
| T-02-05 | Mitigated | XbrlClient converts monetary values to cents; filed_date filtering in get_financial_metrics |
| T-02-06 | Mitigated | tenacity @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10)) on all external calls |
| T-02-08 | Mitigated | _resolve_concept_facts validates tag exists in us-gaap namespace before using |

## Self-Check: PASSED

- All 8 created files verified on disk
- Commit 9814fb2 (Task 1) verified in git log
- Commit cddc42f (Task 2) verified in git log
