---
phase: 08-ai-washing-detector-integration
verified: 2026-03-29T00:00:00Z
status: passed
score: 8/8 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Run `backtest run --signal ai-washing` against a live database populated with real AI Washing Detector scores"
    expected: "Pipeline completes, prints 'Pipeline complete — Sharpe: X.XX, CAGR: X.XX%' to stdout, exits 0"
    why_human: "Requires a running PostgreSQL instance with real AI Washing Detector scores ingested — cannot simulate in automated checks"
---

# Phase 8: AI Washing Detector Integration — Verification Report

**Phase Goal:** Live AI Washing Risk Scores from the Detector's PostgreSQL output can be loaded, adapted to the SignalFrame contract, and run through the full backtesting pipeline without manual steps
**Verified:** 2026-03-29
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                                      | Status     | Evidence                                                                                                     |
|----|-------------------------------------------------------------------------------------------------------------|------------|--------------------------------------------------------------------------------------------------------------|
| 1  | AiWashingLoader.load() returns a valid SignalFrame (DatetimeIndex, ticker columns, float values)            | VERIFIED   | 5 unit tests pass; integration test `test_loader_returns_signal_frame_from_real_db` passes against real PG   |
| 2  | AiWashingLoader.load() raises SignalLoadError with "empty" in message when table is empty                   | VERIFIED   | `test_load_raises_on_empty` and `test_loader_raises_on_empty_table` both pass                                |
| 3  | AiWashingLoader.load() raises SignalLoadError with "unavailable" in message on OperationalError             | VERIFIED   | `test_load_raises_on_missing_table` passes; message text confirmed in ai_washing.py line 108                 |
| 4  | Multiple scores for the same (company, date) are deduplicated using aggfunc='last'                          | VERIFIED   | `test_dedup_same_day_scores` passes; pivot_table(aggfunc="last") in ai_washing.py line 139                   |
| 5  | composite_score integers are cast to float; DatetimeIndex is tz-naive                                       | VERIFIED   | `test_signal_frame_contract` passes; `.astype(float)` line 150, pd.DatetimeIndex at line 144                 |
| 6  | `backtest run --signal ai-washing` exits 0 and prints "complete" when pipeline succeeds                     | VERIFIED   | `test_backtest_run_ai_washing_exits_zero` passes; CLI help shows `run` command on backtest_app              |
| 7  | `backtest run --signal ai-washing` exits 1 with error message containing SignalLoadError description        | VERIFIED   | `test_backtest_run_exits_1_on_signal_load_error` passes; exception caught at cli.py line 335                 |
| 8  | Full pipeline (load -> adapt -> simulate -> metrics) completes without manual steps on real PostgreSQL DB   | VERIFIED   | `test_full_pipeline_load_adapt_simulate_metrics` passes; finite sharpe/cagr/max_drawdown asserted           |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact                                                                 | Provides                                              | Status     | Details                                        |
|--------------------------------------------------------------------------|-------------------------------------------------------|------------|------------------------------------------------|
| `backtest/src/fund_backtest/signal/loaders/__init__.py`                  | Public re-exports: AiWashingLoader, SignalLoadError   | VERIFIED   | 14 lines; `__all__` includes both exports      |
| `backtest/src/fund_backtest/signal/loaders/ai_washing.py`                | AiWashingLoader class and SignalLoadError exception   | VERIFIED   | 151 lines; substantive implementation          |
| `backtest/tests/unit/test_ai_washing_loader.py`                          | 5 unit tests for INT-02 behaviors (mocked session)    | VERIFIED   | 5 tests defined, all passing                   |
| `backtest/src/fund_backtest/cli.py`                                       | `backtest run` command on backtest_app Typer subapp   | VERIFIED   | @backtest_app.command(name="run") at line 268  |
| `backtest/tests/unit/test_cli.py`                                         | 3 CLI unit tests for backtest run (success + failure) | VERIFIED   | 3 new test functions added, all passing        |
| `backtest/tests/integration/test_ai_washing_integration.py`              | Full pipeline integration test (PostgreSQL testcontainer) | VERIFIED | 3 integration tests, all passing               |

### Key Link Verification

| From                                      | To                                           | Via                                          | Status     | Details                                                  |
|-------------------------------------------|----------------------------------------------|----------------------------------------------|------------|----------------------------------------------------------|
| signal/loaders/ai_washing.py              | fund_backtest.signal.types.SignalFrame        | `from fund_backtest.signal.types import SignalFrame` | VERIFIED | Line 30 in ai_washing.py; return type annotated         |
| signal/loaders/ai_washing.py              | daily_scores JOIN companies (raw SQL)         | `_SCORE_QUERY = text(...)` at module level   | VERIFIED   | Lines 41-51; no ORM import from ai_washer                |
| cli.py (run command)                      | fund_backtest.signal.loaders.AiWashingLoader  | Module-level import at line 33               | VERIFIED   | `from fund_backtest.signal.loaders import AiWashingLoader, SignalLoadError` |
| cli.py (run command)                      | fund_backtest.signal.adapter.SignalAdapter    | Module-level import; adapt() call at line 313 | VERIFIED  | `from fund_backtest.signal.adapter import SignalAdapter` at line 34 |
| tests/integration/test_ai_washing_integration.py | PostgreSQL testcontainer             | db_session fixture from conftest.py           | VERIFIED   | `pytestmark = pytest.mark.integration`; db_session used in all 3 tests |

### Data-Flow Trace (Level 4)

| Artifact                      | Data Variable  | Source                                      | Produces Real Data | Status     |
|-------------------------------|----------------|---------------------------------------------|--------------------|------------|
| signal/loaders/ai_washing.py  | rows           | `session.execute(_SCORE_QUERY).fetchall()`  | Yes — SQL JOIN from real PostgreSQL tables | FLOWING |
| cli.py run command            | signal_frame   | AiWashingLoader(session).load()             | Yes — loader produces real SignalFrame from DB rows | FLOWING |
| cli.py run command            | price_frame    | PriceBarRepository.get_bars() -> pivot      | Yes — queries price_bars table, pivots to DataFrame | FLOWING |
| cli.py run command            | bundle         | MetricsEngine().compute(portfolio_result)   | Yes — computed from real simulation result | FLOWING |

### Behavioral Spot-Checks

| Behavior                                               | Command                                                     | Result                          | Status  |
|--------------------------------------------------------|-------------------------------------------------------------|---------------------------------|---------|
| Unit tests for AiWashingLoader all pass                | `uv run pytest tests/unit/test_ai_washing_loader.py -v`     | 5 passed in 1.06s               | PASS    |
| CLI run tests (3 new) all pass                         | `uv run pytest tests/unit/test_cli.py -v -k "run"`          | 6 passed (3 new + 3 existing)   | PASS    |
| Integration tests against real PostgreSQL all pass     | `uv run pytest tests/integration/test_ai_washing_integration.py -v` | 3 passed in 5.51s       | PASS    |
| Full test suite passes with >=80% coverage             | `uv run pytest tests/ --cov=src/fund_backtest`              | 185 passed, 90.27% coverage     | PASS    |
| CLI `backtest run` command appears in help             | `uv run fund-backtest backtest --help`                      | `run` listed in Commands section | PASS    |
| No cross-package imports (no `from ai_washer import`)  | grep on backtest/src/                                       | Only doc comment strings found  | PASS    |
| ai_washing.py has 100% test coverage                   | coverage report                                             | signal/loaders/ai_washing.py: 100% | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description                                                                       | Status    | Evidence                                                                    |
|-------------|-------------|-----------------------------------------------------------------------------------|-----------|-----------------------------------------------------------------------------|
| INT-02      | 08-01-PLAN  | AI Washing Detector scores can be loaded and converted to the signal contract format | SATISFIED | AiWashingLoader.load() returns valid SignalFrame; 5 unit tests cover all behaviors |
| INT-03      | 08-02-PLAN  | End-to-end pipeline runs from signal input to dashboard output without manual steps  | SATISFIED | `backtest run --signal ai-washing` wires full pipeline; integration test proves load->adapt->simulate->metrics completes |

### Anti-Patterns Found

| File                               | Line | Pattern                             | Severity | Impact  |
|------------------------------------|------|-------------------------------------|----------|---------|
| cli.py — export command (line 357) | 357  | `make_demo_result()` / `make_demo_bundle()` — demo data in export command | Info | Outside Phase 8 scope; noted in 08-02-SUMMARY as a known pre-existing condition from Phase 7 |

No blockers found. The `export` command using demo data is pre-existing Phase 7 behavior outside this phase's scope.

### Human Verification Required

#### 1. Live Database End-to-End Run

**Test:** With a PostgreSQL instance running that has AI Washing Detector migrations applied and at least one day of `daily_scores` ingested, run: `fund-backtest backtest run --signal ai-washing`
**Expected:** Command completes, prints `Pipeline complete — Sharpe: X.XX, CAGR: X.XX%` to stdout, exits 0
**Why human:** Requires a live database populated by the real AI Washing Detector scoring pipeline. The integration tests cover the database contract with a testcontainer and synthetic data, but a live production run with real detector output cannot be automated in this environment.

### Gaps Summary

No gaps. All 8 observable truths are verified, all 6 required artifacts exist and are substantive, all key links are wired, data flows from real sources through to final output, all tests pass (185 total, 90.27% coverage), and both INT-02 and INT-03 requirements are satisfied.

The phase goal is fully achieved: live AI Washing Risk Scores from the Detector's PostgreSQL output can be loaded, adapted to the SignalFrame contract, and run through the full backtesting pipeline without manual steps.

---

_Verified: 2026-03-29_
_Verifier: Claude (gsd-verifier)_
