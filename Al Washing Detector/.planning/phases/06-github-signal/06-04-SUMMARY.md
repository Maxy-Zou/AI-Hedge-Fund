---
phase: 06-github-signal
plan: 04
subsystem: ingestion, analysis, cli
tags: [github, rest-api, scoring, orchestrator, cli, typer]

# Dependency graph
requires:
  - phase: 06-github-signal/06-02
    provides: GitHubClient for API calls
  - phase: 06-github-signal/06-03
    provides: compute_github_activity_score pure function
provides:
  - GitHubCollector orchestrator with idempotent persistence
  - ScoringOrchestrator extended with github_activity signal (4 total signals)
  - CLI github collect and collect-all commands
  - Package __init__.py exports for all GitHub modules
affects: [07-earnings-call, 10-pipeline-automation]

# Tech tracking
tech-stack:
  added: []
  patterns: [collector-orchestrator pattern reused from PatentCollector]

key-files:
  created:
    - src/ai_washer/ingestion/github_collector.py
    - tests/unit/test_github_collector.py
    - tests/unit/test_cli_github.py
  modified:
    - src/ai_washer/analysis/scoring_orchestrator.py
    - src/ai_washer/cli.py
    - src/ai_washer/ingestion/__init__.py
    - src/ai_washer/analysis/__init__.py
    - tests/unit/test_scoring_orchestrator.py

key-decisions:
  - "GitHubCollector follows PatentCollector pattern: same __init__, collect_for_company, collect_all API shape"
  - "GitHub max_date query for most-recent snapshot: aggregates only latest observed_date repos for scoring"
  - "AI claim intensity for GitHub scoring sourced from shared kw_by_year dict (scoring_year key)"

patterns-established:
  - "Collector pattern: __init__ with settings/client/session_factory, collect_for_company, collect_all with inter-company delay"

requirements-completed: [GH-01, GH-02, GH-03]

# Metrics
duration: 5min
completed: 2026-03-29
---

# Phase 6 Plan 4: GitHub Signal End-to-End Wiring Summary

**GitHubCollector orchestrator with idempotent DB persistence, ScoringOrchestrator extended to 4 signals, CLI github collect/collect-all commands**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-29T08:20:00Z
- **Completed:** 2026-03-29T08:25:45Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- GitHubCollector orchestrates API collection and DB persistence with idempotent daily collection
- ScoringOrchestrator now produces github_activity scores alongside sec_filing, compute_spending, and patent_gap
- CLI github collect and collect-all commands exposed for manual runs
- All 627 existing unit tests remain green with new GitHub query mocks

## Task Commits

Each task was committed atomically:

1. **Task 1: GitHub collector orchestrator with idempotent persistence** - `5de7e2b` (feat, TDD)
2. **Task 2: Scoring orchestrator extension, CLI commands, and package exports** - `cd1a27a` (feat)

## Files Created/Modified
- `src/ai_washer/ingestion/github_collector.py` - GitHubCollector with collect_for_company and collect_all
- `src/ai_washer/analysis/scoring_orchestrator.py` - Extended with _load_github_snapshot and github_activity scoring
- `src/ai_washer/cli.py` - Added github_app Typer group with collect and collect-all commands
- `src/ai_washer/ingestion/__init__.py` - Added GitHub module exports
- `src/ai_washer/analysis/__init__.py` - Added compute_github_activity_score export
- `tests/unit/test_github_collector.py` - 7 unit tests for collector
- `tests/unit/test_cli_github.py` - 3 CLI registration tests
- `tests/unit/test_scoring_orchestrator.py` - Updated mocks for 5th query (github_max_date)

## Decisions Made
- GitHubCollector follows PatentCollector pattern for consistency: same init/collect_for_company/collect_all API
- GitHub snapshot aggregation queries most recent observed_date to avoid mixing data from different collection runs
- AI claim intensity for GitHub scoring uses the shared kw_by_year dict from SEC filing analysis (scoring_year key)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] github_app Typer group not pre-existing in CLI**
- **Found during:** Task 2
- **Issue:** Plan stated github_app "is already defined" but it was not present in cli.py
- **Fix:** Added github_app Typer group and registered with app.add_typer
- **Files modified:** src/ai_washer/cli.py
- **Verification:** CLI help shows github commands
- **Committed in:** cd1a27a

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Trivial addition, no scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- GitHub signal pipeline fully operational: collection -> persistence -> scoring -> CLI
- ScoringOrchestrator produces 4 signal types (sec_filing, compute_spending, patent_gap, github_activity)
- Phase 6 complete: all 4 plans delivered
- Ready for Phase 7 (earnings call vagueness) or Phase 10 (pipeline automation)

---
*Phase: 06-github-signal*
*Completed: 2026-03-29*
