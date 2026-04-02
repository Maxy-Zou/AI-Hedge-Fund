---
phase: 07-earnings-call-signal
plan: 04
subsystem: analysis
tags: [finbert, earnings, vagueness, scoring, sigmoid, sentiment]

requires:
  - phase: 07-02
    provides: EarningsCollector, EarningsTranscript ORM model, transcript_text JSONB contract
  - phase: 07-03
    provides: FinBERTAnalyzer, SentimentResult, EARNINGS_VAGUE_TERMS, EARNINGS_SUBSTANTIVE_TERMS
provides:
  - Pure earnings vagueness scorer (compute_earnings_vagueness_score)
  - ScoringOrchestrator with 5th signal (earnings_vagueness)
  - 19 new unit tests (13 scorer + 6 orchestrator earnings integration)
affects: [scoring, composite-score, pipeline-automation]

tech-stack:
  added: []
  patterns: [pure-scorer-with-evidence-dict, lazy-finbert-loading, ai-claim-intensity-none-default]

key-files:
  created:
    - src/ai_washer/analysis/earnings_vagueness_scorer.py
    - tests/unit/test_earnings_vagueness_scorer.py
    - tests/unit/test_scoring_orchestrator_earnings.py
  modified:
    - src/ai_washer/analysis/scoring_orchestrator.py
    - tests/unit/test_scoring_orchestrator.py

key-decisions:
  - "ai_claim_intensity=None defaults to 0.5 (SEC data unavailable = assume claims present, score transcript alone)"
  - "ai_claim_intensity=0.0 returns None (no AI claims = earnings vagueness irrelevant, skip signal)"
  - "Lazy FinBERTAnalyzer creation in orchestrator to avoid model loading unless earnings data exists"

patterns-established:
  - "ai_claim_intensity None-default pattern: scorer treats None as 'assume claims present' not 'no claims'"
  - "Lazy heavy-model loading: FinBERTAnalyzer created on first use, reused thereafter"

requirements-completed: [EARN-04, EARN-02, EARN-03]

duration: 11min
completed: 2026-03-29
---

# Phase 7 Plan 4: Earnings Vagueness Scorer and Orchestrator Integration Summary

**Pure earnings vagueness scorer combining buzzword density (70%) and sentiment mismatch (30%) with sigmoid normalization, integrated as 5th signal in ScoringOrchestrator**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-29T14:56:02Z
- **Completed:** 2026-03-29T15:06:51Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Pure scorer function produces 0-100 vagueness score: buzzword_density_ratio * 0.70 + sentiment_mismatch * 0.30
- ScoringOrchestrator.score_company includes earnings_vagueness as 5th signal with lazy FinBERT loading
- ai_claim_intensity=None defaults to 0.5 (SEC data unavailable); 0.0 returns None (no AI claims = skip)
- Evidence JSONB contains full audit trail: buzzword_density_ratio, vague/substantive counts, sentiment breakdown, scoring params, ai_claim_intensity_defaulted flag
- 19 new tests (13 scorer + 6 orchestrator), all passing; existing test suite updated for 6th query

## Task Commits

Each task was committed atomically:

1. **Task 1: Pure earnings vagueness scorer function** - `6144a4a` (feat)
2. **Task 2: Extend ScoringOrchestrator with earnings signal** - `1dded9d` (feat)

## Files Created/Modified
- `src/ai_washer/analysis/earnings_vagueness_scorer.py` - Pure scorer: buzzword density + sentiment mismatch -> sigmoid -> 0-100
- `tests/unit/test_earnings_vagueness_scorer.py` - 13 tests covering all scorer behaviors
- `tests/unit/test_scoring_orchestrator_earnings.py` - 6 tests for orchestrator earnings integration
- `src/ai_washer/analysis/scoring_orchestrator.py` - Added _load_earnings_transcripts, _ensure_finbert, earnings scoring block
- `tests/unit/test_scoring_orchestrator.py` - Updated mock side_effects for 6th query (earnings transcripts)

## Decisions Made
- ai_claim_intensity=None defaults to 0.5 in scorer (SEC data unavailable = assume claims present) -- prevents silently skipping all companies lacking SEC filing data
- ai_claim_intensity=0.0 returns None (company makes no AI claims = earnings vagueness is irrelevant)
- Lazy FinBERTAnalyzer creation via _ensure_finbert() -- model only loaded when earnings transcripts exist
- Test sigmoid params (midpoint=0.5, steepness=5.0) used in boundary tests for meaningful score differentiation since raw scores are in [0,1] range

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated existing orchestrator tests for 6th DB query**
- **Found during:** Task 2 (orchestrator extension)
- **Issue:** Existing test_scoring_orchestrator.py tests set up mock session with 5 query side_effects; adding earnings transcript query caused StopIteration
- **Fix:** Added mock_earnings_result (empty transcript list) as 6th side_effect in all 5 affected tests
- **Files modified:** tests/unit/test_scoring_orchestrator.py
- **Verification:** All 9 existing orchestrator tests pass
- **Committed in:** 1dded9d (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary fix for existing test compatibility with new DB query. No scope creep.

## Issues Encountered
- Pre-existing test failure in test_github_client.py::TestBuildOrgSnapshot::test_aggregates_repos (unrelated to this plan's changes) -- out of scope, not addressed

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data paths are wired end-to-end from EarningsTranscript DB rows through FinBERT analysis to SignalDetail persistence.

## Next Phase Readiness
- All 5 signals now operational: sec_filing, compute_spending, patent_gap, github_activity, earnings_vagueness
- Phase 7 (earnings call signal) is complete -- all 4 plans delivered
- Ready for Phase 8 (job posting signal) or Phase 9 (composite scoring / pipeline automation)

---
*Phase: 07-earnings-call-signal*
*Completed: 2026-03-29*
