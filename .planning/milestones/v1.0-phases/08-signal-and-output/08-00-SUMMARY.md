---
phase: 08-signal-and-output
plan: 00
subsystem: testing
tags: [phase-8, wave-0, scaffold, fixtures, langfuse-audit, sig-04, structlog, testmodel]

# Dependency graph
requires:
  - phase: 07-memory-and-learning
    provides: tests/memory/conftest.py fixture set, memory_recall + episodic_store nodes, Phase-7 composed pipeline
  - phase: 06-risk-governance
    provides: RiskPolicy schema + load_policy + compute_policy_sha (template for ReviewPolicy)
provides:
  - tests/review/ test package with valid + malformed ReviewPolicy YAML fixtures
  - tests/output/ test package scaffold with portfolio_db_session alias
  - tests/integration/conftest.py re-export shim extended for Phase-8 fixtures
  - scripts/verify_langfuse_spans.py Wave-0 audit-coverage smoke
  - tests/output/test_langfuse_span_coverage.py pytest twin (slow-marked)
  - Empirical discharge of RESEARCH.md Assumption A7 (Langfuse/structlog SIG-04 coverage)
affects: [08-01, 08-02, 08-03, 08-04, 08-05, signal-output, human-review-gate, portfolio-view, audit-reconstruct]

# Tech tracking
tech-stack:
  added: []  # scaffold plan -- no new libraries
  patterns:
    - "Wave-0 fixture-first scaffold so Wave-1 plans can run in parallel without fixture duplication"
    - "Audit-coverage smoke via structlog.testing.capture_logs + all-12-agent TestModel stubs"
    - "Dual-scenario (APPROVED + VETOED) runs so both risk paths are exercised in a single smoke"

key-files:
  created:
    - "tests/review/__init__.py"
    - "tests/review/conftest.py"
    - "tests/review/fixtures/review_policy_sample.yaml"
    - "tests/review/fixtures/review_policy_malformed.yaml"
    - "tests/output/__init__.py"
    - "tests/output/conftest.py"
    - "scripts/verify_langfuse_spans.py"
    - "tests/output/test_langfuse_span_coverage.py"
    - ".planning/phases/08-signal-and-output/deferred-items.md"
  modified:
    - "tests/integration/conftest.py  -- added Phase-8 review fixture re-exports"
    - "pyproject.toml  -- registered the 'slow' pytest marker"

key-decisions:
  - "Wave-0 scaffold ships fixtures + smoke BEFORE any Phase-8 production code lands, so Plans 08-01 and 08-02 can run in parallel in Wave 1 without duplicating fixture work"
  - "ReviewPolicy fixture shape matches RESEARCH.md Pattern 3 (conviction_threshold, review_prompt_template, reviewer_id_default) so Plan 08-01 can consume the YAML verbatim via yaml.safe_load"
  - "review_policy fixture lazy-imports load_review_policy so the conftest module collects cleanly before Plan 08-01 ships the production schema"
  - "Langfuse span coverage verified by running the Phase-7 composed pipeline TWICE (APPROVED via a wide-open RiskPolicy; VETOED via OTC instrument_type exclusion) so both risk_manager_complete and risk_manager_veto are exercised in one smoke run"
  - "A7 assumption DISCHARGED: all 13 required events (fundamental/sentiment/technical/manager/bull/bear/rebuttal/final_arguments/debate_synthesis/risk_manager/multi_agent_signal/memory_recall/episodic_store) emit the SIG-04 fields without any production gap-fill -- Plan 08-05 no longer needs a Langfuse instrumentation subtask"

patterns-established:
  - "Phase-8 integration tests inherit review fixtures via tests/integration/conftest.py re-export -- same F811-avoidance pattern Phase 7 Plan 05 used for memory fixtures"
  - "Wave-0 smoke tests are gated behind @pytest.mark.slow and excluded from the default subsuite via -m 'not slow'; run explicitly before phase gate"
  - "Per-agent REQUIRED_FIELDS_PER_AGENT dict documents the SIG-04 contract in a single place so a future refactor that drops an audit field fails loudly in the smoke, not in a live compliance review"

requirements-completed: []
# NOTE: This Wave-0 scaffold plan TOUCHES all four SIG requirements (fixture + audit
# verification work underpins each) but does NOT close any of them on its own.
# Plans 08-01..08-05 do the production-code close-outs. The plan frontmatter lists
# [SIG-01..04] as in-scope, but only touch-only; close-outs tracked via the
# Requirement Traceability table below.

# Metrics
duration: 9min
completed: 2026-04-23
---

# Phase 08 Plan 00: Wave-0 Scaffold + Langfuse Audit Discharge Summary

**Wave-0 test-package scaffold (tests/review, tests/output), ReviewPolicy YAML fixtures, integration conftest re-export shim, and a composed-pipeline structlog smoke that discharges RESEARCH.md Assumption A7 with all 13 Phase-1-7 nodes emitting SIG-04 audit fields.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-04-23T04:36:57Z
- **Completed:** 2026-04-23T04:46:16Z
- **Tasks:** 3 / 3
- **Files created:** 9 (8 code/config + 1 deferred-items log)
- **Files modified:** 2 (integration conftest + pyproject.toml)

## Accomplishments

- tests/review/ and tests/output/ packages collect cleanly; ReviewPolicy YAML fixtures (valid threshold=70 + malformed with unknown_key for extra='forbid' regression) on disk.
- Integration conftest re-exports three Phase-8 review fixtures alongside the seven Phase-7 memory fixtures; downstream Plans 08-03..08-05 declare them as test parameters without direct imports (F811 avoided).
- Langfuse/structlog span-coverage smoke runs the Phase-7 composed pipeline twice (APPROVED + VETOED) and captures 25 events; all 13 required events emit the SIG-04 audit fields. **A7 assumption DISCHARGED** -- Plan 08-05 no longer needs a Langfuse instrumentation gap-fill subtask.

## Task Commits

1. **Task 1: scaffold tests/review + tests/output packages** -- `9a09f0d` (test)
2. **Task 2: extend integration conftest for Phase-8 fixtures** -- `9b37a79` (test)
3. **Task 3: Wave-0 Langfuse span-coverage smoke discharges A7** -- `0206a24` (test)

Plan metadata commit: captured in the same branch history; this SUMMARY + STATE update follow.

## Files Created/Modified

### Created

- `tests/review/__init__.py` -- Python package marker.
- `tests/review/conftest.py` -- review_policy_sample_path + review_policy_malformed_path + review_policy fixtures. Lazy-imports load_review_policy so collection works before Plan 08-01 lands.
- `tests/review/fixtures/review_policy_sample.yaml` -- conviction_threshold=70 + prompt template + reviewer_id_default="test".
- `tests/review/fixtures/review_policy_malformed.yaml` -- same shape plus unknown_key to trigger Pydantic extra='forbid' ValidationError.
- `tests/output/__init__.py` -- package marker.
- `tests/output/conftest.py` -- re-exports memory_db_session as portfolio_db_session for Plan 08-02 portfolio_view tests.
- `scripts/verify_langfuse_spans.py` -- Wave-0 one-shot audit. Runs the composed Phase-7 pipeline twice (APPROVED wide-open RiskPolicy + VETOED via OTC exclusion) with all 12 agents stubbed via TestModel, captures structlog events, asserts each of 13 events emits its SIG-04 field set. Exit 0 = A7 discharged.
- `tests/output/test_langfuse_span_coverage.py` -- pytest twin gated behind @pytest.mark.slow; asserts audit_coverage returns an empty gap dict.
- `.planning/phases/08-signal-and-output/deferred-items.md` -- logs the pre-existing test_checkpointer.py ANTHROPIC_API_KEY collection error (out of scope for this plan).

### Modified

- `tests/integration/conftest.py` -- appended `from tests.review.conftest import (review_policy, review_policy_malformed_path, review_policy_sample_path)` plus a docstring note. All Phase-7 memory re-exports preserved byte-for-byte.
- `pyproject.toml` -- added `[tool.pytest.ini_options] markers = ["slow: ..."]` so `@pytest.mark.slow` is a registered marker (no more PytestUnknownMarkWarning).

## Verification

### Wave-0 subsuite (`uv run --no-sync pytest tests/review tests/output -q`)

```
1 passed, 4 warnings in 1.85s
```

### Collection (`uv run --no-sync pytest tests/review tests/output --collect-only -q`)

```
1 test collected in 1.64s
```

### Span-coverage smoke (`uv run --no-sync python scripts/verify_langfuse_spans.py`)

```
Captured 25 structlog events during the Phase-7 composed pipeline run.
SIG-04 audit coverage: ALL REQUIRED FIELDS PRESENT.
A7 assumption discharged -- existing Phase 1-7 instrumentation is sufficient.
```

Exit 0.

### Ruff (`uv run --no-sync ruff check tests/review tests/output tests/integration/conftest.py scripts/verify_langfuse_spans.py`)

```
All checks passed!
```

### Full-suite regression (`uv run --no-sync pytest -q --ignore=tests/integration/test_checkpointer.py`)

```
2 failed, 922 passed, 6 skipped, 7 warnings in 19.50s
```

The 2 failures (`tests/integration/test_research_pipeline.py::test_research_agent_with_test_model` and `::test_signal_agent_with_test_model`) are pre-existing on main and documented in `.planning/phases/07-memory-and-learning/deferred-items.md` (pytest-asyncio not installed). Verified via `git stash` + re-run: identical failures. Not a regression from Plan 08-00.

Baseline grew from 921 to 922 (Plan 08-00 added `test_langfuse_span_coverage`).

## Requirement Traceability

| Requirement | Status after Plan 08-00 | Closed by |
|-------------|-------------------------|-----------|
| SIG-01 (SignalOutput schema, no nulls) | TOUCHED (fixture scaffold) | Plan 08-01 + 08-02 |
| SIG-02 (Portfolio view) | TOUCHED (portfolio_db_session alias) | Plan 08-02 |
| SIG-03 (Human review gate) | TOUCHED (ReviewPolicy YAML fixtures) | Plan 08-01 + 08-03 |
| SIG-04 (Compliance-grade audit) | **Span coverage discharged for A7**; audit_reconstruct production script still required | Plan 08-04 + 08-05 |

The frontmatter `requirements-completed` field lists all four IDs per template contract (copied from the plan). None of the four close at this point -- they close in Plans 08-01..08-05 as production code lands.

## Deviations from Plan

### Rule 1 (auto-fix bug) -- event-name correction

**Found during:** Task 3 smoke-script implementation.

**Issue:** The plan's `REQUIRED_FIELDS_PER_AGENT` uses the event name `signal_complete`, but the debate pipeline wires `multi_agent_signal_node` (per `src/ai_hedge_fund/graph/pipeline.py:300`), which emits `multi_agent_signal_complete`. Using the plan's literal name would have produced a spurious "EVENT NEVER EMITTED" gap.

**Fix:** Replaced the key with `multi_agent_signal_complete` in both the map and its docstring. Added an inline comment documenting the deviation.

**Files modified:** `scripts/verify_langfuse_spans.py`.

**Commit:** `0206a24`.

### Rule 3 (auto-fix blocking) -- RiskDeps instantiation

**Found during:** Task 3 first smoke-script execution.

**Issue:** The plan's sample code snippet (`RiskDeps(db_session=session, policy=policy)`) is missing the `returns` field. `RiskDeps` is a frozen dataclass with `returns: pd.DataFrame` as a required positional; the smoke failed to instantiate.

**Fix:** Added `returns=returns` with the `tests/risk/fixtures/returns_golden.csv` fixture loader (mirrors `tests/integration/test_phase7_e2e.py::_golden_returns`).

**Files modified:** `scripts/verify_langfuse_spans.py`.

**Commit:** `0206a24`.

### Rule 3 (auto-fix blocking) -- self_critique_agent import path

**Found during:** Task 3 first smoke-script execution.

**Issue:** The plan's sample code imports 12 agents via `from ai_hedge_fund.agents import (...)`, but `self_critique_agent` is NOT re-exported from the `ai_hedge_fund.agents` package `__init__.py` -- it is only importable from `ai_hedge_fund.agents.self_critique`. Using the plan literal produces ImportError.

**Fix:** Import each of the 12 agents from its submodule directly (matches `tests/integration/test_phase7_e2e.py` line 36-47).

**Files modified:** `scripts/verify_langfuse_spans.py`.

**Commit:** `0206a24`.

### Rule 3 (auto-fix blocking) -- ANTHROPIC_API_KEY env var

**Found during:** Task 3 first smoke-script execution.

**Issue:** Importing `ai_hedge_fund.agents` triggers eager instantiation of `analysis_agent`, which requires `ANTHROPIC_API_KEY`. Without it, the Anthropic provider raises `UserError` at import time, making the smoke script un-runnable.

**Fix:** Added `os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-phase8-wave0-smoke")` at the top of the file BEFORE any `ai_hedge_fund.*` import (matches `tests/integration/test_phase7_e2e.py` line 30).

**Files modified:** `scripts/verify_langfuse_spans.py`.

**Commit:** `0206a24`.

### Rule 2 (auto-add missing critical functionality) -- dual-scenario run

**Found during:** Task 3 empirical validation of the single-scenario design.

**Issue:** A single pipeline run against the stock AAPL fixture vetoed on `max_projected_drawdown_pct` (23.5% vs 20% limit), so `risk_manager_complete` (APPROVED-branch) and `multi_agent_signal_complete` were never emitted. The script reported "EVENT NEVER EMITTED" gaps that were artifacts of the test setup, not real instrumentation gaps.

**Fix:** Run the pipeline twice:
1. **APPROVED scenario** -- build a wide-open `RiskPolicy` in Python (max_single_position_pct=10, max_sector_pct=50, drawdown cap=99%, etc.) so the deterministic checks pass on an empty portfolio, producing `risk_manager_complete` + `multi_agent_signal_complete`.
2. **VETOED scenario** -- keep the sample YAML policy and use an OTC instrument_type candidate so `check_exclusions` vetoes first, producing `risk_manager_veto` + skipping the signal node (conditional edge routes straight to `episodic_store`).

Union all events before the coverage check; both branches are now exercised in a single smoke.

**Files modified:** `scripts/verify_langfuse_spans.py`.

**Commit:** `0206a24`.

### Plan acceptance-criterion discrepancy (informational, not a deviation)

The plan's Task 1 acceptance criterion says `grep -c "def review_policy" tests/review/conftest.py` equals 2, but the plan's `<action>` defines THREE fixtures whose names all start with `review_policy`: `review_policy_sample_path`, `review_policy_malformed_path`, and `review_policy`. The actual grep count is 3. The action text is authoritative; the criterion was a minor plan-level arithmetic slip.

## Deferred Issues

See `.planning/phases/08-signal-and-output/deferred-items.md`:

- **08-00 deferred:** pre-existing `tests/integration/test_checkpointer.py` collection error (missing `ANTHROPIC_API_KEY` env setdefault). Documented; the canonical one-line fix pattern is in place in `tests/integration/test_phase7_e2e.py` and should be applied in a future chore commit.

## Threat Flags

None. The Wave-0 threat register (T-08-00-01 through T-08-00-04) is fully mitigated: `yaml.safe_load` is the only YAML loader we touch (`yaml.load` does not appear in any of the created files), the in-memory SQLite engines in the smoke script are throwaway, `@pytest.mark.slow` gates the smoke from the default subsuite, and the pytest smoke is the evidence of record for A7 discharge.

## Self-Check: PASSED

File existence:
- FOUND: tests/review/__init__.py
- FOUND: tests/review/conftest.py
- FOUND: tests/review/fixtures/review_policy_sample.yaml
- FOUND: tests/review/fixtures/review_policy_malformed.yaml
- FOUND: tests/output/__init__.py
- FOUND: tests/output/conftest.py
- FOUND: scripts/verify_langfuse_spans.py
- FOUND: tests/output/test_langfuse_span_coverage.py
- FOUND: .planning/phases/08-signal-and-output/deferred-items.md

Commit hashes:
- FOUND: 9a09f0d (Task 1)
- FOUND: 9b37a79 (Task 2)
- FOUND: 0206a24 (Task 3)
