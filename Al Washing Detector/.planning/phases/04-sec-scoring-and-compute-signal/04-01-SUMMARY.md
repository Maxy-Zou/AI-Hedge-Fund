---
phase: 04-sec-scoring-and-compute-signal
plan: 01
subsystem: analysis
tags: [pydantic, dataclass, regex, keyword-lexicon, cagr, sigmoid, scoring]

# Dependency graph
requires:
  - phase: 03-sec-filing-collection
    provides: FilingSections model, XBRL_TAG_GROUPS, Filing/XBRLFact ORM models
provides:
  - FilingForScoring frozen dataclass (shared input type for both SEC and compute scorers)
  - KeywordLexicon, KeywordFrequencyResult, SectionKeywordCounts Pydantic models
  - GrowthRateResult, SignalResult Pydantic models
  - Two-tier keyword lexicon with 27 vague, 28 substantive, 21 cloud/compute terms
  - compile_lexicon with word-boundary regex for false-positive prevention
  - compute_section_weighted_frequency with None-section handling and weight renormalization
  - compute_cagr with full edge case handling
  - build_yearly_series for XBRL fact aggregation (FY preference, Q1-Q4 summing)
  - sigmoid_normalize for deterministic 0-100 score mapping
affects: [04-02-sec-filing-scorer, 04-03-compute-spending-scorer]

# Tech tracking
tech-stack:
  added: []
  patterns: [frozen-dataclass-for-scoring-inputs, two-tier-keyword-classification, section-weighted-frequency, sigmoid-normalization]

key-files:
  created:
    - src/ai_washer/analysis/__init__.py
    - src/ai_washer/analysis/types.py
    - src/ai_washer/analysis/keywords.py
    - src/ai_washer/analysis/growth.py
    - src/ai_washer/analysis/normalization.py
    - tests/unit/test_analysis_types.py
    - tests/unit/test_keywords.py
    - tests/unit/test_growth.py
    - tests/unit/test_normalization.py
  modified:
    - pyproject.toml

key-decisions:
  - "pythonpath=[src] added to pytest config to fix .pth file processing issue in stdlib venv worktree"
  - "KeywordMatch as frozen dataclass (not Pydantic) for lightweight immutable match results"
  - "500-char minimum for section text validation (consistent with Phase 3 rule)"
  - "Sigmoid clamp at +/-500 to prevent math.exp overflow without affecting scoring range"
  - "build_yearly_series prefers FY, sums Q1-Q4 if all present, falls back to max quarterly"

patterns-established:
  - "Frozen dataclass for scoring inputs: FilingForScoring is immutable, shared across scorers"
  - "Two-tier keyword classification: vague buzzwords vs substantive technical terms"
  - "Section-weighted frequency: skip missing/short sections, renormalize remaining weights"
  - "Sigmoid normalization: midpoint maps to 50, bounded [0, max_score], deterministic"
  - "Module-level tuple constants for immutable keyword lists"

requirements-completed: [SEC-02, COMP-02]

# Metrics
duration: 6min
completed: 2026-03-28
---

# Phase 4 Plan 01: Analysis Foundation Summary

**Two-tier keyword lexicon with section-weighted counting, CAGR growth utilities, and sigmoid normalization for SEC and compute scoring engines**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-28T20:57:56Z
- **Completed:** 2026-03-28T21:04:00Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Analysis package with 5 Pydantic type contracts plus FilingForScoring frozen dataclass as the canonical shared type for both Wave 2 scorers
- Two-tier keyword lexicon: 27 vague buzzwords, 28 substantive terms, 21 cloud/compute keywords, all as immutable tuples with word-boundary regex matching
- Section-weighted keyword frequency computation that handles missing/short sections with automatic weight renormalization
- CAGR computation with robust edge case handling (zero, negative, flat, total decline)
- build_yearly_series aggregating XBRL facts with FY preference and Q1-Q4 summing
- Sigmoid normalization mapping ratios to deterministic 0-100 integer scores

## Task Commits

Each task was committed atomically:

1. **Task 1: Analysis types and keyword lexicon with counting**
   - `af637cc` (test: RED -- failing tests for types and keywords)
   - `c0d2d16` (feat: GREEN -- implementation passing 39 tests)
2. **Task 2: Growth rate computation and sigmoid normalization**
   - `b593635` (test: RED -- failing tests for growth and normalization)
   - `540d0dc` (feat: GREEN -- implementation passing 67 total tests)

## Files Created/Modified
- `src/ai_washer/analysis/__init__.py` - Package exports for all analysis types and functions
- `src/ai_washer/analysis/types.py` - Pydantic type contracts: FilingForScoring, KeywordLexicon, SectionKeywordCounts, KeywordFrequencyResult, GrowthRateResult, SignalResult
- `src/ai_washer/analysis/keywords.py` - Two-tier lexicon constants, compile_lexicon, count_keywords_in_text, compute_section_weighted_frequency
- `src/ai_washer/analysis/growth.py` - compute_cagr and build_yearly_series
- `src/ai_washer/analysis/normalization.py` - sigmoid_normalize
- `tests/unit/test_analysis_types.py` - 14 tests for Pydantic models and FilingForScoring dataclass
- `tests/unit/test_keywords.py` - 25 tests for keyword constants, lexicon compilation, counting, section weighting
- `tests/unit/test_growth.py` - 17 tests for CAGR and yearly series building
- `tests/unit/test_normalization.py` - 11 tests for sigmoid normalization
- `pyproject.toml` - Added pythonpath=["src"] to pytest config

## Decisions Made
- Added `pythonpath=["src"]` to pytest.ini_options in pyproject.toml to fix .pth file not being processed in stdlib venv worktree environment
- Used frozen dataclass for KeywordMatch (lightweight, immutable) rather than Pydantic model
- Maintained 500-char minimum section length threshold from Phase 3 for consistency
- Sigmoid clamp at +/-500 prevents math.exp overflow while covering entire practical scoring range

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added pythonpath to pytest config**
- **Found during:** Task 1 (test execution)
- **Issue:** Python .pth file not processed by stdlib venv in git worktree, causing all imports to fail
- **Fix:** Added `pythonpath = ["src"]` to `[tool.pytest.ini_options]` in pyproject.toml
- **Files modified:** pyproject.toml
- **Verification:** All 67 tests pass with `pytest`
- **Committed in:** c0d2d16 (part of Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential for test execution in worktree environment. No scope creep.

## Issues Encountered
None beyond the pytest path issue documented above.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all functions are fully implemented with complete logic.

## Next Phase Readiness
- Analysis foundation complete: types, keywords, growth, normalization all tested and exported
- Wave 2 plans (04-02 SEC filing scorer, 04-03 compute spending scorer) can now import all shared types and utilities from `ai_washer.analysis`
- FilingForScoring is the canonical shared input type defined in types.py

---
*Phase: 04-sec-scoring-and-compute-signal*
*Completed: 2026-03-28*
