---
phase: 07-earnings-call-signal
plan: 03
subsystem: analysis
tags: [finbert, sentiment, nlp, keywords, earnings]

# Dependency graph
requires:
  - phase: 07-earnings-call-signal-01
    provides: EarningsTranscript model, earnings types, scoring config
provides:
  - FinBERTAnalyzer class with chunked 510-token inference and mean aggregation
  - SentimentResult Pydantic model (positive/negative/neutral probabilities)
  - EARNINGS_VAGUE_TERMS (17 earnings-call buzzwords)
  - EARNINGS_SUBSTANTIVE_TERMS (18 technical AI terms for earnings)
  - EARNINGS_SECTION_WEIGHTS (prepared_remarks 0.60, qa 0.40)
affects: [07-earnings-call-signal-04, scoring-orchestrator]

# Tech tracking
tech-stack:
  added: [transformers pipeline, AutoTokenizer]
  patterns: [lazy model loading, chunked BERT inference with mean aggregation, dual-lexicon per signal domain]

key-files:
  created:
    - src/ai_washer/analysis/finbert_analyzer.py
    - tests/unit/test_finbert_analyzer.py
    - tests/unit/test_earnings_keywords.py
  modified:
    - src/ai_washer/analysis/keywords.py
    - src/ai_washer/analysis/__init__.py

key-decisions:
  - "FinBERT top-label redistribution: remaining probability split equally across other two labels for aggregation"
  - "Lazy model loading: pipeline and tokenizer created on first analyze_text call, reused thereafter"

patterns-established:
  - "Chunked BERT inference: encode -> split token IDs -> decode chunks -> pipeline batch -> mean aggregate"
  - "Domain-specific lexicons alongside existing SEC lexicons (additive, not replacing)"

requirements-completed: [EARN-02, EARN-03]

# Metrics
duration: 3min
completed: 2026-03-29
---

# Phase 07 Plan 03: FinBERT Analyzer & Earnings Keywords Summary

**FinBERT chunked sentiment analyzer with lazy loading and 35 earnings-specific keyword terms for dual-lexicon classification**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-29T18:28:48Z
- **Completed:** 2026-03-29T18:31:50Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- FinBERTAnalyzer chunks text into 510-token segments, runs mocked pipeline, aggregates sentiment via arithmetic mean
- SentimentResult Pydantic model with model_validator ensuring probabilities sum to ~1.0
- 17 earnings-call vague buzzwords and 18 substantive technical terms added alongside existing SEC lexicons
- 20 new unit tests (9 FinBERT + 11 earnings keywords), all with mocked transformers (no model download)

## Task Commits

Each task was committed atomically:

1. **Task 1: FinBERT chunked sentiment analyzer with mocked tests** - `3d24890` (feat)
2. **Task 2: Earnings-specific dual-lexicon keyword constants and tests** - `709fded` (feat)
3. **Package exports update** - `131993a` (chore)

## Files Created/Modified
- `src/ai_washer/analysis/finbert_analyzer.py` - FinBERTAnalyzer, SentimentResult, chunk_text_for_bert
- `src/ai_washer/analysis/keywords.py` - Added EARNINGS_VAGUE_TERMS, EARNINGS_SUBSTANTIVE_TERMS, EARNINGS_SECTION_WEIGHTS
- `src/ai_washer/analysis/__init__.py` - Exports new symbols
- `tests/unit/test_finbert_analyzer.py` - 9 tests with mocked transformers pipeline
- `tests/unit/test_earnings_keywords.py` - 11 tests for earnings lexicons

## Decisions Made
- FinBERT returns only top label + score; remaining probability distributed equally across other two labels for mean aggregation
- Lazy model loading pattern: _pipe and _tokenizer set to None at init, loaded on first analyze_text call
- Earnings keywords are additive constants alongside existing SEC lexicons (no modification to VAGUE_BUZZWORDS or SUBSTANTIVE_TERMS)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all functionality is wired and tested.

## Next Phase Readiness
- FinBERTAnalyzer and earnings keyword lexicons ready for consumption by the vagueness scorer (Plan 04)
- analyze_segments method ready for prepared_remarks/qa section processing
- EARNINGS_SECTION_WEIGHTS ready for compute_section_weighted_frequency integration

---
*Phase: 07-earnings-call-signal*
*Completed: 2026-03-29*
