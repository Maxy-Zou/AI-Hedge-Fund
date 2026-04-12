---
phase: 04-first-strategy-consumer
verified: 2026-04-04T00:00:00Z
status: gaps_found
score: 6/7 must-haves verified
re_verification: false
gaps:
  - truth: "CLI run command accepts --strategy flag and dispatches to STRATEGY_REGISTRY"
    status: partial
    reason: "The --strategy flag exists and dispatches to STRATEGY_REGISTRY correctly for pass-through and example. However, the insider-tracker dispatch path in both `run` and `compare` commands calls strategy_cls(database_url=tracker_db_url) but InsiderTrackerAdapter.__init__() takes db_url as its first positional parameter. This would raise TypeError at runtime when --strategy insider-tracker is used with a valid KALSHI_TRACKER_DATABASE_URL set."
    artifacts:
      - path: "kalshi-backtest/src/kalshi_backtest/cli.py"
        issue: "Line 341: strategy_cls(database_url=tracker_db_url) — wrong kwarg name. InsiderTrackerAdapter expects db_url=, not database_url=. Same bug at line 484 in compare command."
      - path: "kalshi-backtest/src/kalshi_backtest/strategies/insider_tracker.py"
        issue: "Constructor parameter is db_url (line 78), not database_url"
    missing:
      - "Fix cli.py lines 341 and 484: change database_url=tracker_db_url to db_url=tracker_db_url"
      - "Add a test that exercises the insider-tracker dispatch path with a mock KALSHI_TRACKER_DATABASE_URL to catch this class of wiring bug"
human_verification:
  - test: "Run kalshi-backtest run --strategy insider-tracker --dry-run without KALSHI_TRACKER_DATABASE_URL set"
    expected: "Prints clear error message about missing KALSHI_TRACKER_DATABASE_URL and exits 1"
    why_human: "The dry-run guard exits before reaching strategy dispatch, so this path cannot be fully validated by the automated test suite without a live DB or integration test"
  - test: "Run kalshi-backtest compare --strategy-a pass-through --strategy-b example --dry-run"
    expected: "Prints comparison table with 'Brier Score' row showing 'N/A'"
    why_human: "dry-run exits before Brier Score is computed — visual confirmation of terminal table formatting needed"
---

# Phase 4: First Strategy Consumer Verification Report

**Phase Goal:** The Insider Tracker's signals drive a complete end-to-end backtest, proving the Strategy Protocol works with a real signal source, and a template plugin makes adding future strategies trivial
**Verified:** 2026-04-04
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ExampleStrategy returns a Signal when close_price is below threshold | ✓ VERIFIED | `test_example_strategy_buys_cheap` passes; `example.py` line 80 strict `< self._threshold` check |
| 2 | ExampleStrategy returns [] when ticker is already held | ✓ VERIFIED | `test_example_strategy_skips_held` passes; `example.py` line 72–78 held-set guard |
| 3 | ExampleStrategy satisfies the Strategy Protocol (isinstance check passes) | ✓ VERIFIED | `test_example_strategy_satisfies_protocol` passes; structural subtyping via `generate_signals()` |
| 4 | InsiderTrackerAdapter queries only signals strictly before snapshot.ts (no look-ahead) | ✓ VERIFIED | `test_insider_adapter_no_lookahead` passes; SQL uses `detected_at < :end` (line 46 of insider_tracker.py) |
| 5 | InsiderTrackerAdapter returns [] and logs a warning on DB error — never raises | ✓ VERIFIED | `test_insider_adapter_db_error` passes; try/except Exception block at line 135–141 |
| 6 | InsiderTrackerAdapter filters out signals below min_confidence threshold | ✓ VERIFIED | `test_insider_adapter_confidence_filter` passes; SQL WHERE `confidence >= :min_conf` (line 47) |
| 7 | CLI run command accepts --strategy flag and dispatches to STRATEGY_REGISTRY | ✗ FAILED | `--strategy` flag exists and test passes for `pass-through`, but insider-tracker dispatch uses wrong kwarg (`database_url=` instead of `db_url=`) in both `run` (line 341) and `compare` (line 484) — would TypeError at runtime |

**Score:** 6/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `kalshi-backtest/src/kalshi_backtest/strategies/example.py` | ExampleStrategy implementing Strategy Protocol | ✓ VERIFIED | 97 lines, substantive, imported and used |
| `kalshi-backtest/src/kalshi_backtest/strategies/insider_tracker.py` | InsiderTrackerAdapter with SQLAlchemy text() | ✓ VERIFIED | 205 lines, substantive, look-ahead safe SQL |
| `kalshi-backtest/src/kalshi_backtest/strategies/__init__.py` | STRATEGY_REGISTRY dict with all three keys | ✓ VERIFIED | Exports STRATEGY_REGISTRY with pass-through, example, insider-tracker keys; lazy ImportError guard for SQLAlchemy |
| `kalshi-backtest/src/kalshi_backtest/metrics/calculator.py` | brier_score field + _compute_brier_score() | ✓ VERIFIED | Line 80: `brier_score: float | None = None`; lines 158–193: full implementation with numpy vectorization |
| `kalshi-backtest/src/kalshi_backtest/cli.py` | --strategy flag dispatching to STRATEGY_REGISTRY + Brier Score in _SCALAR_ROWS | ⚠️ PARTIAL | --strategy flag exists, _SCALAR_ROWS has Brier Score entry (line 53), STRATEGY_REGISTRY dispatch implemented — but insider-tracker kwarg mismatch (database_url vs db_url) |
| `kalshi-backtest/tests/test_strategies.py` | 11 tests for STRAT-01 and STRAT-02 | ✓ VERIFIED | 11 tests all GREEN |
| `kalshi-backtest/tests/conftest.py` | sqlite_signals_db fixture | ✓ VERIFIED | Lines 78–102: temp-file SQLite fixture with signals table |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tests/test_strategies.py` | `kalshi_backtest.strategies.insider_tracker` | import | ✓ WIRED | Import at line 19, all 6 InsiderTrackerAdapter tests pass |
| `tests/test_strategies.py` | `kalshi_backtest.strategies.example` | import | ✓ WIRED | Import at line 20, all 5 ExampleStrategy tests pass |
| `strategies/insider_tracker.py` | signals table | SQLAlchemy text() query | ✓ WIRED | `from sqlalchemy import create_engine, text` at line 28; _SIGNAL_QUERY defined at lines 39–50 |
| `strategies/__init__.py` | STRATEGY_REGISTRY | dict with string keys | ✓ WIRED | Lines 54–65: dict populated with lazy InsiderTrackerAdapter guard |
| `cli.py run command` | STRATEGY_REGISTRY | dict lookup on --strategy value | ✓ WIRED | Lines 318–327: dispatch via `STRATEGY_REGISTRY[strategy_name]` |
| `cli.py insider-tracker path` | InsiderTrackerAdapter constructor | keyword argument | ✗ NOT_WIRED | Line 341 calls `strategy_cls(database_url=tracker_db_url)` but constructor uses `db_url` param name — TypeError at runtime |
| `MetricsCalculator.compute()` | `_compute_brier_score()` | direct call | ✓ WIRED | Lines 297–298: `brier_score = _compute_brier_score(result.trade_log)` |
| `_SCALAR_ROWS in cli.py` | `BacktestMetrics.brier_score` | lambda formatter | ✓ WIRED | Line 53: `("Brier Score", lambda m: f"{m.brier_score:.4f}" if m.brier_score is not None else "N/A")` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `strategies/example.py` | `snapshot.close_price` | MarketSnapshot (passed in by runner) | Real bar price from DuckDB | ✓ FLOWING |
| `strategies/insider_tracker.py` | `rows` from DB query | SQLAlchemy text() over signals table | Real rows from Insider Tracker PostgreSQL (or SQLite in tests) | ✓ FLOWING |
| `metrics/calculator.py` `brier_score` | `result.trade_log["exit_reason"]` | BacktestResult trade_log DataFrame | Real trade log from BacktestRunner | ✓ FLOWING |
| `cli.py` _SCALAR_ROWS Brier Score | `m.brier_score` | BacktestMetrics from MetricsCalculator.compute() | Live computed value | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All strategy tests pass | `uv run pytest tests/test_strategies.py -v` | 11/11 PASSED | ✓ PASS |
| Brier score tests pass | `uv run pytest tests/test_metrics_calculator.py -k brier -v` | 4/4 PASSED | ✓ PASS |
| CLI strategy flag test | `uv run pytest tests/test_cli.py -k strategy_flag -v` | 1/1 PASSED | ✓ PASS |
| Full test suite | `uv run pytest tests/ -v` | 237/237 PASSED | ✓ PASS |
| Code coverage | `uv run pytest --cov=kalshi_backtest` | 84% TOTAL | ✓ PASS (>80%) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| STRAT-01 | 04-01, 04-02 | Insider Tracker adapter — consume signals from Kalshi Insider Tracker as first strategy plugin | ✓ SATISFIED | InsiderTrackerAdapter fully implemented; 6 tests GREEN; look-ahead safe SQL; independence constraint met (0 kalshi_tracker imports) |
| STRAT-02 | 04-01, 04-02 | Example/template strategy — demo plugin for onboarding future strategies | ✓ SATISFIED | ExampleStrategy implemented; 5 tests GREEN; satisfies Strategy Protocol; serves as onboarding template |
| MET-04 | 04-01, 04-03 | Brier score — prediction calibration quality metric | ✓ SATISFIED | `brier_score: float | None` field in BacktestMetrics; `_compute_brier_score()` with numpy vectorization; 4 tests GREEN; N/A displayed when no settlement trades |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/kalshi_backtest/cli.py` | 341 | `strategy_cls(database_url=tracker_db_url)` — wrong kwarg name | 🛑 Blocker | insider-tracker strategy non-functional at runtime when DB URL is set; would raise TypeError |
| `src/kalshi_backtest/cli.py` | 484 | Same `database_url=` mismatch in `compare` command | 🛑 Blocker | compare --strategy-a/b insider-tracker path also broken |

### Human Verification Required

#### 1. insider-tracker fail-fast behavior

**Test:** Set KALSHI_TRACKER_DATABASE_URL to empty/unset, then run `kalshi-backtest run --strategy insider-tracker --dry-run`
**Expected:** Prints "Configuration error: KALSHI_TRACKER_DATABASE_URL is not set" with instructions, exits with code 1. Note: dry-run currently exits before strategy dispatch — this path may not be reachable via --dry-run at all.
**Why human:** The dry-run guard at line 284 exits before strategy dispatch (line 317), meaning the insider-tracker URL check is unreachable via --dry-run. A non-dry-run test would require live credentials. Manual inspection needed.

#### 2. Brier Score display in metrics table

**Test:** Run `kalshi-backtest compare --strategy-a pass-through --strategy-b example --dry-run`
**Expected:** Prints comparison table with "Brier Score" row displaying "N/A" for both strategies
**Why human:** dry-run exits before MetricsCalculator runs, so Brier Score is never computed in automated tests — the display code needs visual confirmation that the table renders correctly in the terminal.

### Gaps Summary

One gap blocks full goal achievement:

**CLI insider-tracker wiring bug:** The CLI's `run` command (line 341) and `compare` command (line 484) both call `InsiderTrackerAdapter` with `database_url=tracker_db_url`, but the constructor defines the parameter as `db_url`. This would raise `TypeError: __init__() got an unexpected keyword argument 'database_url'` the moment a user provides `KALSHI_TRACKER_DATABASE_URL` and runs `--strategy insider-tracker`. The STRAT-01 requirement is satisfied by the adapter itself, but the integration path from the CLI to the adapter is broken for the insider-tracker strategy. The fix is a one-line change in two places.

**Coverage note:** All other paths (pass-through, example, Brier score, ExampleStrategy, InsiderTrackerAdapter logic) are fully wired and verified. The independence constraint is satisfied — zero `kalshi_tracker` imports in the backtest module. The template plugin pattern (STRAT-02) works correctly as an onboarding guide.

---

_Verified: 2026-04-04_
_Verifier: Claude (gsd-verifier)_
