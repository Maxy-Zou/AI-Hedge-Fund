---
phase: 07-memory-and-learning
plan: 00
subsystem: testing
tags: [pytest, ruamel.yaml, fixtures, scaffold, phase-7, memory]

# Dependency graph
requires:
  - phase: 06-risk-management
    provides: "RiskAssessment.policy_sha audit key referenced by episodic CSV rows"
provides:
  - "tests/memory/ importable pytest package with 7 shared fixtures (memory_db_session, beliefs_tmp_dir, sample_belief_yaml_path, sample_belief_human_edited_path, sample_belief_field_locked_path, sample_episodic_csv_path, sample_outcomes_yaml_path)"
  - "Three belief YAML golden fixtures (plain, human-edited, field-locked) matching the Phase 7 Belief schema"
  - "10-row episodic CSV seed with future-dated temporal-leakage regression row"
  - "Outcomes YAML fixture with 3 events for Plan 07-04 self-critique tests"
  - "Wave-0 smoke test (6 assertions) that gates downstream Wave-1 plans"
  - "ruamel.yaml>=0.19.0 dependency (comment-preserving YAML for MEM-03)"
affects: [07-01-episodic-memory, 07-02-belief-memory, 07-03-human-override, 07-04-self-critique, 07-05-pipeline-integration]

# Tech tracking
tech-stack:
  added:
    - "ruamel.yaml>=0.19.0 (round-trip YAML; comment preservation for MEM-03)"
  patterns:
    - "tests/<domain>/conftest.py inheriting project-wide db_session fixture, aliasing it as <domain>_db_session for readability"
    - "FIXTURES_DIR = Path(__file__).parent / 'fixtures' pattern (established by tests/risk/, extended to tests/memory/)"
    - "beliefs_tmp_dir: tmp_path-based writable seed that copies golden fixtures so originals remain immutable"
    - "Temporal-leakage regression seed pattern: one FUTURE-dated row in the episodic CSV so recall tests can prove cutoff filters work"

key-files:
  created:
    - "tests/memory/__init__.py"
    - "tests/memory/conftest.py (7 fixtures)"
    - "tests/memory/fixtures/__init__.py"
    - "tests/memory/fixtures/belief_aapl.yaml (golden with '# flagged' comment)"
    - "tests/memory/fixtures/belief_aapl_human_edited.yaml (human_edited=true, confidence=20)"
    - "tests/memory/fixtures/belief_aapl_field_locked.yaml (confidence field-lock)"
    - "tests/memory/fixtures/seeded_episodic.csv (10 rows, 4 sectors, future row)"
    - "tests/memory/fixtures/outcomes_sample.yaml (3 outcome events)"
    - "tests/memory/test_wave0_scaffold.py (6-assertion smoke test)"
    - ".planning/phases/07-memory-and-learning/deferred-items.md"
  modified:
    - "pyproject.toml (append ruamel.yaml>=0.19.0 to [project].dependencies)"

key-decisions:
  - "Scaffold-only plan: no production code ships in Wave 0; Wave-1/2 plans consume these fixtures"
  - "ruamel.yaml chosen (vs PyYAML) because MEM-03 requires round-trip preservation of human comments in belief files"
  - "10-row episodic CSV covers 4 sectors (Technology, Healthcare, Financials, Consumer Staples) and both record_types (analysis, outcome) — one FUTURE-dated row (2099-01-01, FUTUREX) is the MEM-01 temporal-leakage regression seed"
  - "beliefs_tmp_dir fixture uses shutil.copy2 from golden fixtures into tmp_path/tickers/ so write tests cannot mutate the golden files"
  - "memory_db_session is a thin alias for db_session (not a new fixture) — keeps memory tests self-documenting without duplicating the SQLite setup"

patterns-established:
  - "Pattern 1: Wave-0 scaffold plan — new phases with >3 dependent plans ship fixtures+smoke-test first so downstream waves can run in parallel without duplicating fixture work"
  - "Pattern 2: Comment-preservation regression fixture — golden YAMLs carry a load-bearing inline comment ('# flagged') that downstream round-trip tests assert survives a read/write cycle"
  - "Pattern 3: Temporal-leakage regression seed — one deliberately future-dated row in any time-series fixture, consumed by recall tests that prove as_of_date cutoffs work"

requirements-completed: []  # Wave-0 scaffold only; MEM-01..04 are closed by plans 07-01 through 07-04

# Metrics
duration: 7m
completed: 2026-04-22
---

# Phase 7 Plan 00: Wave-0 Test Scaffold Summary

**ruamel.yaml dependency added, tests/memory/ package scaffolded with 7 shared fixtures, 5 golden fixtures (3 belief YAMLs, 1 episodic CSV, 1 outcomes YAML), and a 6-assertion smoke test that gates every downstream Phase 7 plan.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-04-22T20:35:07Z
- **Completed:** 2026-04-22T20:41:42Z
- **Tasks:** 3
- **Files modified:** 11 (10 created, 1 modified)

## Accomplishments

- Wave-0 smoke test green: all 6 assertions pass (`uv run --no-sync pytest tests/memory/test_wave0_scaffold.py -q` — see Deviations for the `--no-sync` workaround).
- Every downstream Wave-1 plan (07-01..07-05) can now import fixtures from `tests/memory/conftest.py` and consume the belief/episodic/outcomes golden files without duplicating fixture work.
- `ruamel.yaml>=0.19.0` is installed and verified at version 0.19.1 — this is the load-bearing dependency for MEM-03 comment preservation.
- Temporal-leakage regression seed present: `FUTUREX,Technology,analysis,2099-01-01,...` row in the episodic CSV forces Plan 07-01 to prove its `as_of_date` cutoff filter works.

## Task Commits

Each task was committed atomically:

1. **Task 1: ruamel.yaml dep + tests/memory package + conftest** — `c85fd7f` (chore)
2. **Task 2: Belief YAML fixtures (plain, human-edited, field-locked)** — `3063249` (test)
3. **Task 3: Episodic CSV + outcomes YAML + Wave-0 smoke test + deferred-items** — `c8e8755` (test)

## Files Created/Modified

- `pyproject.toml` — appended `ruamel.yaml>=0.19.0` to `[project].dependencies` (preserved existing order)
- `tests/memory/__init__.py` — package marker
- `tests/memory/conftest.py` — 7 shared pytest fixtures (memory_db_session alias, beliefs_tmp_dir, five fixture-path fixtures)
- `tests/memory/fixtures/__init__.py` — package marker
- `tests/memory/fixtures/belief_aapl.yaml` — golden belief with inline `# flagged` comment (MEM-03 round-trip regression)
- `tests/memory/fixtures/belief_aapl_human_edited.yaml` — human_edited=true, confidence pinned to 20
- `tests/memory/fixtures/belief_aapl_field_locked.yaml` — field_locks.confidence=true, human_edited=false
- `tests/memory/fixtures/seeded_episodic.csv` — 10-row seed, 4 sectors, both record_types, one future-dated row
- `tests/memory/fixtures/outcomes_sample.yaml` — 3 outcome events for Plan 07-04
- `tests/memory/test_wave0_scaffold.py` — 6-assertion smoke test
- `.planning/phases/07-memory-and-learning/deferred-items.md` — documents the upstream uv/macOS UF_HIDDEN bug

## Decisions Made

All decisions followed the plan as written. Two worth highlighting (both already captured in the plan):

1. `memory_db_session` is an alias (not a new fixture). Keeps memory-phase tests self-documenting without re-implementing the in-memory SQLite setup from the root `tests/conftest.py`.
2. The FUTUREX row uses a deliberately-invalid policy_sha (`ffff...zzzzz`). Harmless because policy_sha is a plain `str` column with no validator at the DB layer, and it doubles as a visible marker in test output when a temporal filter regression occurs.

## Deviations from Plan

### Environment-level Issues (documented, not fixed)

**1. [Rule 3 — Blocking, deferred as out-of-scope] `uv run pytest` fails due to upstream uv/macOS UF_HIDDEN bug**

- **Found during:** Task 3 verification (`uv run pytest tests/memory/test_wave0_scaffold.py -q`)
- **Issue:** When the project path contains a space (`/Users/maxzou/Documents/projects/AI Hedgefund`), `uv sync` installs the editable `.pth` files with the macOS `UF_HIDDEN` flag (32768) set. Python 3.13's `site.py` line 177-180 explicitly skips any `.pth` file whose `st_flags` has `UF_HIDDEN`, so `src/` is never added to `sys.path` and `ai_hedge_fund` is unimportable. This affects the pre-existing `_virtualenv.pth` too, confirming the bug is not caused by Plan 07-00 work.
- **Fix applied (workaround, not root-cause fix):** Run `chflags nohidden .venv/lib/python3.13/site-packages/*.pth` before invoking tests, then use `uv run --no-sync pytest ...` (or `.venv/bin/python -m pytest ...`). Under this workaround all 6 Wave-0 tests pass.
- **Why not root-caused:** This is an upstream uv regression on macOS with spaces in paths — outside the Phase 7 memory-and-learning scope. Three remediation options (rename project dir, pin older uv, add sitecustomize) are listed in `deferred-items.md` for user decision.
- **Files added:** `.planning/phases/07-memory-and-learning/deferred-items.md`
- **Committed in:** `c8e8755` (Task 3 commit)

---

**Total deviations:** 1 environment issue documented + deferred (not auto-fixed, out of scope).
**Impact on plan:** Zero — 6/6 Wave-0 tests pass under the documented workaround. Acceptance criteria satisfied.

## Issues Encountered

- Confirmed pre-existing uv/macOS environment bug (above). Ruff linting and formatting on the new Python files ran cleanly throughout.

## User Setup Required

None — no external services were configured. Note for downstream executors: if you see `ModuleNotFoundError: No module named 'ai_hedge_fund'` during `uv run pytest`, run `chflags nohidden .venv/lib/python3.13/site-packages/*.pth` then use `uv run --no-sync pytest ...` (see `deferred-items.md`).

## Next Phase Readiness

- Wave-1 plans (07-01 episodic memory, 07-02 belief memory) can now run **in parallel** — both consume only fixtures from this plan.
- Wave-2 plans (07-03 human override, 07-04 self-critique, 07-05 pipeline integration) wait on Wave-1 finalisation but inherit the same fixture surface.
- No blockers. One environment-level caveat (uv/macOS UF_HIDDEN) is documented in `deferred-items.md` with a deterministic workaround.

## Self-Check: PASSED

Verified on disk (2026-04-22T20:41:42Z):

- `pyproject.toml` contains `ruamel.yaml>=0.19.0`: FOUND
- `tests/memory/__init__.py`: FOUND
- `tests/memory/conftest.py` (7 fixtures): FOUND
- `tests/memory/fixtures/__init__.py`: FOUND
- `tests/memory/fixtures/belief_aapl.yaml` (`# flagged` present): FOUND
- `tests/memory/fixtures/belief_aapl_human_edited.yaml` (`human_edited: true`): FOUND
- `tests/memory/fixtures/belief_aapl_field_locked.yaml` (`confidence: true` under field_locks): FOUND
- `tests/memory/fixtures/seeded_episodic.csv` (11 lines = header + 10 data; 4 sectors; 2099 row): FOUND
- `tests/memory/fixtures/outcomes_sample.yaml` (3 entries): FOUND
- `tests/memory/test_wave0_scaffold.py` (6 assertions, all pass): FOUND
- `.planning/phases/07-memory-and-learning/deferred-items.md`: FOUND
- Commits `c85fd7f`, `3063249`, `c8e8755`: all present in `git log --oneline`.

---
*Phase: 07-memory-and-learning*
*Completed: 2026-04-22*
