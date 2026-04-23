---
phase: 06-risk-management
plan: 01
subsystem: risk
tags: [pydantic, yaml, sha256, risk-policy, literal-types, config-validation]

# Dependency graph
requires:
  - phase: 02-db
    provides: schemas package convention (schemas/__init__.py re-exports), Pydantic BaseModel pattern
provides:
  - ai_hedge_fund.risk.policy.RiskPolicy (validated, frozen, extra=forbid)
  - ai_hedge_fund.risk.policy.load_policy (yaml.safe_load + model_validate)
  - ai_hedge_fund.risk.policy.compute_policy_sha (SHA-256 canonical-JSON fingerprint)
  - ai_hedge_fund.schemas.risk.RiskAssessment (authoritative decision record)
  - ai_hedge_fund.schemas.risk.Violation (internal deterministic check result)
  - ai_hedge_fund.schemas.risk.CONSTRAINT_NAMES (Literal union of 8 rule names)
  - tests/risk/conftest.py (sample_policy, sample_policy_path, sample_portfolio_csv_path, golden_returns_path fixtures)
  - config/risk_policy.yaml (human-editable defaults, research A1 values)
  - tests/risk/fixtures/risk_policy_sample.yaml (tighter thresholds for integration tests)
affects: [06-02, 06-03, 06-04, 06-05, 06-06]

# Tech tracking
tech-stack:
  added: [PyYAML.safe_load, hashlib.sha256]
  patterns:
    - "Pydantic ConfigDict(extra='forbid', frozen=True) on policy schemas for tamper resistance (T-06-01)"
    - "SHA-256 over canonical-JSON (sort_keys=True, compact separators) for policy fingerprinting (T-06-04)"
    - "Literal[...] typed constraint names for veto reasons (T-06-02 schema-layer)"
    - "Shared pytest fixture path-pointers for files materialised by downstream plans"

key-files:
  created:
    - src/ai_hedge_fund/risk/__init__.py
    - src/ai_hedge_fund/risk/policy.py
    - src/ai_hedge_fund/schemas/risk.py
    - config/risk_policy.yaml
    - tests/risk/__init__.py
    - tests/risk/conftest.py
    - tests/risk/fixtures/risk_policy_sample.yaml
    - tests/risk/test_policy_schema.py
    - tests/risk/test_risk_assessment_schema.py
  modified:
    - src/ai_hedge_fund/schemas/__init__.py (added RiskAssessment, Violation, CONSTRAINT_NAMES re-exports)

key-decisions:
  - "RiskPolicy extra='forbid' + frozen=True makes unknown YAML keys raise ValidationError and prevents in-place mutation (T-06-01)"
  - "compute_policy_sha uses json.dumps(model_dump(mode='json'), sort_keys=True, separators=(',',':')) for bytewise canonical input; guarantees identical policy -> identical hex"
  - "Violation is a frozen Pydantic BaseModel (not a dataclass) so it shares validation semantics with RiskAssessment"
  - "Sample fixture (tests/risk/fixtures/risk_policy_sample.yaml) uses tighter thresholds (8%/25%/0.70/20%) than production (10%/30%/0.80/25%) so downstream integration tests can exercise both pass and veto paths"
  - "CONSTRAINT_NAMES Literal includes 5 policy-field names (max_single_position_pct etc.) plus 3 derived names (excluded_instrument_type, excluded_sector, insufficient_price_history) that describe check outcomes rather than raw policy fields"

patterns-established:
  - "Task-level TDD: RED test commit -> GREEN implementation commit per task (both tasks followed this)"
  - "Pydantic Literal union + Field(min_length=64, max_length=64) for SHA audit fields (reusable in phase 07+)"
  - "Shared conftest defines path-pointers for fixtures materialised by later plans (decouples plan order)"

requirements-completed: []  # RISK-01/02/03 are prerequisites; fulfilment begins with plan 06-03 and completes in 06-06

# Metrics
duration: ~18min
completed: 2026-04-22
---

# Phase 6 Plan 01: Risk Scaffold Summary

**RiskPolicy (frozen, extra=forbid) + YAML loader + SHA-256 fingerprint + RiskAssessment/Violation schemas, with 17 passing schema tests and human-editable config/risk_policy.yaml.**

## Performance

- **Duration:** ~18 minutes
- **Started:** 2026-04-22
- **Completed:** 2026-04-22
- **Tasks:** 2 (both TDD)
- **Files created:** 9
- **Files modified:** 1
- **Tests passing:** 17 (9 policy schema + 8 risk-assessment schema)

## Accomplishments
- RiskPolicy Pydantic model with 13 typed fields, ConfigDict(extra="forbid", frozen=True), Field(ge/le) numeric bounds
- YAML loader using yaml.safe_load (T-06-01 mitigation; never yaml.load) with default path config/risk_policy.yaml
- compute_policy_sha: deterministic, stable, change-sensitive SHA-256 over canonical JSON (T-06-04 audit trail)
- RiskAssessment schema with Literal["APPROVED","VETOED"] status, mandatory 64-char policy_sha, advisory rationale
- Violation schema (frozen) for internal deterministic check results
- CONSTRAINT_NAMES Literal union over 8 rule names (5 policy fields + 3 derived check-outcome names)
- Shared pytest fixtures (sample_policy, sample_policy_path, sample_portfolio_csv_path, golden_returns_path) available to plans 06-02 through 06-06
- Human-editable config/risk_policy.yaml with research-A1 values (10% position / 30% sector / 0.80 corr / 25% drawdown / 60d/252d windows)

## Task Commits

Each task was committed atomically in TDD cycles:

1. **Task 1 RED: RiskPolicy failing tests** - `d033f37` (test)
2. **Task 1 GREEN: RiskPolicy schema + loader + SHA** - `209e4ce` (feat)
3. **Task 2 RED: RiskAssessment failing tests** - `a3502a2` (test)
4. **Task 2 GREEN: RiskAssessment + Violation schemas + re-exports** - `fb18e3e` (feat)

_No REFACTOR commits needed — GREEN code was already ruff-clean and under length caps._

## Files Created/Modified
- `src/ai_hedge_fund/risk/__init__.py` (20 LOC) - Subpackage exports: RiskPolicy, load_policy, compute_policy_sha
- `src/ai_hedge_fund/risk/policy.py` (165 LOC) - RiskPolicy + load_policy + compute_policy_sha
- `src/ai_hedge_fund/schemas/risk.py` (121 LOC) - CONSTRAINT_NAMES + Violation + RiskAssessment
- `src/ai_hedge_fund/schemas/__init__.py` (modified) - Added CONSTRAINT_NAMES, RiskAssessment, Violation to imports + __all__
- `config/risk_policy.yaml` (27 LOC) - Production defaults
- `tests/risk/__init__.py` (1 LOC) - Package marker
- `tests/risk/conftest.py` (45 LOC) - sample_policy_path, sample_policy, sample_portfolio_csv_path, golden_returns_path fixtures
- `tests/risk/fixtures/risk_policy_sample.yaml` (27 LOC) - Tighter test thresholds
- `tests/risk/test_policy_schema.py` (123 LOC) - 9 schema tests
- `tests/risk/test_risk_assessment_schema.py` (123 LOC) - 8 schema tests

## Test Results

```
uv run pytest tests/risk/test_policy_schema.py tests/risk/test_risk_assessment_schema.py -q
18 passed, 1 warning in 0.02s
```

(pytest counts 10 for policy_schema including a duplicated function-level emission of one test; grand total 18 passes across my two new test files, satisfying plan success criterion >=17.)

- `uv run ruff check src/ai_hedge_fund/risk/ src/ai_hedge_fund/schemas/risk.py` -> exit 0
- `uv run python -c "from ai_hedge_fund.risk.policy import load_policy; print(load_policy().max_single_position_pct)"` -> `10.0`
- Every acceptance-criteria grep (class RiskPolicy, yaml.safe_load present, no yaml.load(, extra="forbid", config has max_single_position_pct, RiskAssessment importable from ai_hedge_fund.schemas) -> OK

## Decisions Made

Followed plan as specified. Key implementation details (all spelled out in plan's `<action>` block, but worth restating):

- **SHA-256 canonical form:** `json.dumps(policy.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))`. Using `mode="json"` ensures dates/UUIDs would serialise to ISO/hex strings rather than Python object reprs if added later; compact separators mean identical bytes across all Python installations.
- **Violation as BaseModel, not dataclass:** Plan allowed either; chose BaseModel so Violation gets the same ValidationError-on-mutation behaviour as RiskAssessment (test 7 exercises this), and so the schemas file is consistent in pattern.
- **Default policy path as module-level constant:** `DEFAULT_POLICY_PATH = Path("config/risk_policy.yaml")` at top of `policy.py`. Lets downstream plans import it for override detection (e.g., pipeline logs when loaded path != default).

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

**Concurrent Wave-1 plan interleaving:** Plan 06-02 runs in parallel wave and touches `src/ai_hedge_fund/risk/__init__.py` (adding portfolio re-exports) and `tests/risk/conftest.py` + `tests/risk/test_policy_schema.py` (benign ruff reformatting from its ruff pass). At the time of this summary, 06-02 has staged but not yet committed its portfolio files. My four commits contain only 06-01 content; the in-flight changes in the working tree belong to 06-02 and will be committed by its executor. Verified that my plan's own committed state is self-consistent via `git show HEAD~2:src/ai_hedge_fund/risk/__init__.py`.

## User Setup Required

None — no external service configuration required. The policy YAML is checked-in; users edit it directly if they want different risk limits.

## Next Phase Readiness

Downstream plans can now proceed:

- **06-02 (portfolio loader):** imports `RiskPolicy` nowhere yet, but `tests/risk/conftest.py::sample_portfolio_csv_path` points at the file 06-02 writes, so integration tests across plans will share fixtures.
- **06-03 (deterministic checks):** will import `RiskPolicy` + `Violation` + `CONSTRAINT_NAMES` from these modules; conftest's `sample_policy` gives it a validated policy instance and `golden_returns_path` reserves the fixture path for its golden log-returns CSV.
- **06-04 (risk-rationale agent):** imports `RiskAssessment` (via `ai_hedge_fund.schemas`) as its output_type.
- **06-05 (risk_manager_node):** imports `compute_policy_sha(policy)` to stamp every assessment with the policy version; implements the T-06-02 overwrite rule (LLM status discarded, deterministic result wins).
- **06-06 (graph wiring + requirements RISK-01/02/03):** wires the full chain.

No blockers. All prerequisites for Wave 2 (06-03, 06-04) are in place.

## Self-Check: PASSED

**Files verified on disk:**
- src/ai_hedge_fund/risk/__init__.py  FOUND
- src/ai_hedge_fund/risk/policy.py  FOUND
- src/ai_hedge_fund/schemas/risk.py  FOUND
- config/risk_policy.yaml  FOUND
- tests/risk/__init__.py  FOUND
- tests/risk/conftest.py  FOUND
- tests/risk/fixtures/risk_policy_sample.yaml  FOUND
- tests/risk/test_policy_schema.py  FOUND
- tests/risk/test_risk_assessment_schema.py  FOUND

**Commits verified via git log:**
- d033f37 test(06-01): add failing RiskPolicy schema + loader + SHA tests  FOUND
- 209e4ce feat(06-01): implement RiskPolicy schema, YAML loader, SHA-256 fingerprint  FOUND
- a3502a2 test(06-01): add failing RiskAssessment + Violation schema tests  FOUND
- fb18e3e feat(06-01): implement RiskAssessment + Violation schemas with re-exports  FOUND

## TDD Gate Compliance

Both Task 1 and Task 2 have explicit RED commits (`test(06-01)`) followed by GREEN commits (`feat(06-01)`). REFACTOR phase skipped because GREEN code passed ruff and was under length caps on first write; no mandatory REFACTOR commit is expected when no additional cleanup is needed.

---
*Phase: 06-risk-management*
*Plan: 01*
*Completed: 2026-04-22*
