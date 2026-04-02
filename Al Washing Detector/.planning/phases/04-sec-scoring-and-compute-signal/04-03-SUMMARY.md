---
phase: 04-sec-scoring-and-compute-signal
plan: 03
subsystem: analysis
tags: [scoring, capex, xbrl, cloud-compute, sigmoid, cagr, nlp]

# Dependency graph
requires:
  - phase: 04-01
    provides: "Shared analysis types (FilingForScoring, SignalResult), keyword lexicon (CLOUD_COMPUTE_KEYWORDS), growth utilities (compute_cagr, build_yearly_series), sigmoid normalization"
  - phase: 03
    provides: "SEC filing collection with sections and XBRL CapEx facts"
provides:
  - "Compute spending gap scorer (count_cloud_mentions_by_year, compute_capex_keyword_gap, compute_compute_spending_score)"
  - "COMP-01: CapEx trend extraction from XBRL facts over 3-year window"
  - "COMP-02: Cloud/compute partnership mention detection in filing text"
  - "COMP-03: Compute spending gap score (0-100) with sigmoid normalization"
affects: [04-04, composite-scoring, pipeline-automation]

# Tech tracking
tech-stack:
  added: []
  patterns: [weighted-gap-metric, cloud-mention-detection-in-filings]

key-files:
  created:
    - src/ai_washer/analysis/compute_spending_scorer.py
    - tests/unit/test_compute_spending_scorer.py
  modified:
    - src/ai_washer/analysis/__init__.py
    - docs/PROGRESS.md

key-decisions:
  - "70/30 CapEx/cloud-mention weighting for combined investment growth metric per D-05"
  - "Cloud mention detection uses filing text (mda, risk_factors, business) not transcripts per Pitfall 6 -- transcripts added in Phase 7"
  - "Signal version 0.4.0 for compute spending scorer audit trail"

patterns-established:
  - "Weighted gap metric: narrative growth / investment growth where investment is weighted composite of CapEx and cloud mentions"
  - "Filing-text-based cloud detection as interim for transcript-based detection (Phase 7)"

requirements-completed: [COMP-01, COMP-02, COMP-03]

# Metrics
duration: 4min
completed: 2026-03-28
---

# Phase 4 Plan 3: Compute Spending Gap Scorer Summary

**Pure-function compute spending gap scorer detecting flat CapEx despite growing AI narrative via 70/30 weighted CapEx-cloud gap metric with sigmoid normalization**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-28T21:07:26Z
- **Completed:** 2026-03-28T21:11:18Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 4

## Accomplishments
- Compute spending gap scorer produces 0-100 scores detecting divergence between AI narrative growth and actual investment
- Three pure functions: count_cloud_mentions_by_year, compute_capex_keyword_gap, compute_compute_spending_score
- Flat CapEx + growing AI keywords scores > 70 (gap detected); growing CapEx matching keywords scores < 40 (genuine investment)
- Cloud mentions in filing text partially offset flat CapEx (30% weight) per D-05
- Full evidence audit trail with signal_version, capex_data, cloud_mentions, scoring params, data_quality

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for compute spending gap scorer** - `ee0dbc2` (test)
2. **Task 1 (GREEN): Implement compute spending gap scorer** - `28e5d27` (feat)

_TDD task with RED/GREEN commits._

## Files Created/Modified
- `src/ai_washer/analysis/compute_spending_scorer.py` - Three pure scoring functions (303 lines)
- `tests/unit/test_compute_spending_scorer.py` - 25 unit tests covering all scenarios (483 lines)
- `src/ai_washer/analysis/__init__.py` - Added 3 new exports
- `docs/PROGRESS.md` - Updated with Phase 4 Plan 03 entry

## Decisions Made
- 70/30 CapEx/cloud-mention weighting for combined investment growth metric per D-05 research decision
- Cloud mention detection searches filing text sections (mda, risk_factors, business) instead of earnings transcripts per Pitfall 6 -- transcripts not available until Phase 7
- Signal version "0.4.0" matches phase numbering for audit traceability
- FilingForScoring imported from shared types.py (no local ComputeFilingInput) for type consistency with Plan 02

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Compute spending scorer ready for integration in Plan 04 (score orchestrator)
- Shares FilingForScoring type and growth utilities with SEC filing scorer (Plan 02)
- ai_keyword_counts_by_year passed from SEC scoring pipeline (not recomputed)
- Cloud mention detection uses filing_text data source -- evidence documents this for Phase 7 transcript enhancement

## Self-Check: PASSED
- All 3 created files exist on disk
- Both commits (ee0dbc2, 28e5d27) found in git history
- All 25 unit tests pass (0.68s)
