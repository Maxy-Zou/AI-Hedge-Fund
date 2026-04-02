---
phase: 05-patent-signal
plan: 03
subsystem: analysis
tags: [patent-gap, cagr, sigmoid, scoring, cli, orchestrator]

# Dependency graph
requires:
  - phase: 05-patent-signal (plans 01, 02)
    provides: Patent ORM model, PatentSearchClient, PatentCollector, PatentGapScoringConfig
  - phase: 04-sec-scoring-and-compute-signal
    provides: ScoringOrchestrator, compute_cagr, sigmoid_normalize, SignalResult, ai_keyword_counts sharing pattern
provides:
  - compute_patent_gap_score pure function (CAGR-based divergence scorer)
  - ScoringOrchestrator extended with patent_gap signal production
  - CLI patent collect and patent collect-all commands
  - analysis package export of compute_patent_gap_score
affects: [06-github-signal, 07-earnings-call, 09-composite-scoring, 10-pipeline-automation]

# Tech tracking
tech-stack:
  added: []
  patterns: [pure-function-scorer, shared-keyword-counts-reuse, 4-query-orchestrator]

key-files:
  created:
    - src/ai_washer/analysis/patent_gap_scorer.py
    - tests/unit/test_patent_gap_scorer.py
  modified:
    - src/ai_washer/analysis/scoring_orchestrator.py
    - src/ai_washer/analysis/__init__.py
    - src/ai_washer/cli.py
    - tests/unit/test_scoring_orchestrator.py

key-decisions:
  - "Signal version 0.5.0 for patent gap scorer matching phase numbering"
  - "Reuses shared ai_keyword_counts from compute scorer (no recomputation)"
  - "Patent factor clamped to 0.01 minimum to prevent division by zero"

patterns-established:
  - "Pure function scorer pattern: typed inputs, SignalResult output, no DB access"
  - "Shared keyword counts reuse: SEC, compute, and patent scorers all consume same ai_keyword_counts dict"

requirements-completed: [PAT-01, PAT-02, PAT-03]

# Metrics
duration: 4min
completed: 2026-03-28
---

# Phase 5 Plan 3: Patent Gap Scoring and CLI Summary

**CAGR-based patent gap scorer comparing AI claim intensity growth to patent filing trends, wired into orchestrator and CLI**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-28T22:28:29Z
- **Completed:** 2026-03-28T22:32:29Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Pure function compute_patent_gap_score produces 0-100 divergence scores using CAGR ratios and sigmoid normalization
- ScoringOrchestrator.score_company now produces 3 signals: sec_filing, compute_spending, and patent_gap
- CLI patent collect and patent collect-all commands with dry-run support
- 21 total tests passing (11 scorer + 10 orchestrator)

## Task Commits

Each task was committed atomically:

1. **Task 1: Patent gap scorer pure function** - `e21562b` (test) + `1926d77` (feat) [TDD]
2. **Task 2: Orchestrator extension, analysis exports, CLI commands** - `fcf2289` (feat)

## Files Created/Modified
- `src/ai_washer/analysis/patent_gap_scorer.py` - Pure function scorer: CAGR divergence ratio with sigmoid normalization
- `src/ai_washer/analysis/scoring_orchestrator.py` - Extended with _load_patent_counts and patent_gap scoring in score_company
- `src/ai_washer/analysis/__init__.py` - Exports compute_patent_gap_score
- `src/ai_washer/cli.py` - patent_app Typer group with collect and collect-all commands
- `tests/unit/test_patent_gap_scorer.py` - 11 unit tests covering scoring logic, edge cases, evidence
- `tests/unit/test_scoring_orchestrator.py` - Updated existing tests + 2 new patent gap integration tests

## Decisions Made
- Signal version 0.5.0 for patent gap scorer to match phase numbering convention
- Reuses shared ai_keyword_counts dict already computed for compute spending scorer (no recomputation)
- Patent factor clamped to minimum 0.01 to prevent division by zero when patent growth is strongly negative
- Zero-value floors: claims use 0.1, patents use 1 as CAGR start value floors

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Patent signal pipeline complete end-to-end: API client -> collector -> DB -> scorer -> orchestrator -> CLI
- Phase 5 fully complete (all 3 plans delivered)
- Ready for Phase 6 (GitHub signal) or Phase 7 (earnings call)

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 05-patent-signal*
*Completed: 2026-03-28*
