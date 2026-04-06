---
phase: 02-simulation-engine
verified: 2026-04-06T00:24:50Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 2: Simulation Engine Verification Report

**Phase Goal:** Any strategy implementing the Strategy Protocol can be replayed bar-by-bar against historical data with correct P&L, fees, and fill prices — and look-ahead bias is structurally impossible.
**Verified:** 2026-04-06T00:24:50Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Any class with generate_signals() satisfies Strategy without importing engine internals | ✓ VERIFIED | `@runtime_checkable Strategy(Protocol)` in protocol.py; spot-check confirmed `isinstance(MyStrategy(), Strategy)` returns True |
| 2 | Look-ahead bias is structurally impossible — result=None for all bars where ts < close_time | ✓ VERIFIED | `suppress_result = ts < close_time` in BarIterator.__iter__; test_lookahead_not_possible in test_runner.py asserts no snapshot exposes result before close_time |
| 3 | Fee formula matches ceil(0.07 * C * P * (1-P)) exactly | ✓ VERIFIED | calculate_fee_cents in fill_engine.py; spot-check confirmed (100, 0.50)==2 and (1, 0.50)==1; 33 unit tests in test_fill_engine.py |
| 4 | Fill price for YES buy is mid + half_spread; for NO buy is mid - half_spread | ✓ VERIFIED | simulate_fill_price() in fill_engine.py; YES: `fill_yes = min(100, mid + half_spread)`, NO: `fill_yes = max(0, mid - half_spread)` |
| 5 | Settlement P&L for YES win is (100-entry)*contracts, for YES loss is -entry*contracts | ✓ VERIFIED | calculate_settlement_pnl() in fill_engine.py; spot-check confirmed win=600, loss=-400 for entry=40, contracts=10 |
| 6 | BacktestRunner produces BacktestResult with complete trade log and daily P&L Series | ✓ VERIFIED | runner.py full implementation; BacktestResult has trade_log (DataFrame) + daily_pnl (Series); 18 integration tests pass |
| 7 | Settlement fires exactly once per market when result becomes non-None | ✓ VERIFIED | `settled_tickers: set[str]` in BacktestRunner.run() prevents double-settlement; test_settlement_fires_exactly_once confirmed |
| 8 | Grid sweep with N params × M values produces N^M BacktestResult objects sorted by Sharpe | ✓ VERIFIED | ParameterSweeper uses itertools.product; 8 sweep tests confirm 2×2 grid → 4 runs, results sorted descending |
| 9 | Walk-forward with n_splits=3 produces 3 non-overlapping folds, train_end <= test_start | ✓ VERIFIED | WalkForwardValidator expanding-window design; spot-check and 11 tests confirm fold count, non-overlap, no look-ahead in splits |

**Score:** 9/9 truths verified

---

### Required Artifacts

| Artifact | Min Lines | Actual Lines | Exports | Status |
|----------|-----------|-------------|---------|--------|
| `src/kalshi_backtest/simulation/__init__.py` | — | 56 | Strategy, Signal, Position, MarketSnapshot, build_snapshot, BarIterator, FillEngine, Fill, PositionTracker, ClosedPosition, BacktestRunner, BacktestResult, ParameterSweeper, SweepResult, WalkForwardValidator, WalkForwardResult | ✓ VERIFIED |
| `src/kalshi_backtest/simulation/protocol.py` | 60 | 122 | Strategy, Signal, Position | ✓ VERIFIED |
| `src/kalshi_backtest/simulation/snapshot.py` | 40 | 132 | MarketSnapshot, build_snapshot | ✓ VERIFIED |
| `src/kalshi_backtest/simulation/bar_iterator.py` | 80 | 95 | BarIterator | ✓ VERIFIED |
| `src/kalshi_backtest/simulation/fill_engine.py` | 100 | 292 | FillEngine, Fill, calculate_fee_cents, simulate_fill_price, calculate_settlement_pnl, calculate_exit_pnl | ✓ VERIFIED |
| `src/kalshi_backtest/simulation/position_tracker.py` | 80 | 291 | PositionTracker, ClosedPosition | ✓ VERIFIED |
| `src/kalshi_backtest/simulation/runner.py` | 120 | 276 | BacktestRunner, BacktestResult | ✓ VERIFIED |
| `src/kalshi_backtest/simulation/sweep.py` | 60 | 129 | ParameterSweeper, SweepResult | ✓ VERIFIED |
| `src/kalshi_backtest/simulation/walkforward.py` | 60 | 165 | WalkForwardValidator, WalkForwardResult | ✓ VERIFIED |
| `tests/test_simulation_types.py` | 80 | 308 | 23 tests | ✓ VERIFIED |
| `tests/test_bar_iterator.py` | 60 | 213 | 9 tests | ✓ VERIFIED |
| `tests/test_fill_engine.py` | 80 | 353 | 33 tests | ✓ VERIFIED |
| `tests/test_position_tracker.py` | 60 | 371 | 27 tests | ✓ VERIFIED |
| `tests/test_runner.py` | 80 | 443 | 18 tests | ✓ VERIFIED |
| `tests/test_sweep.py` | 50 | 257 | 8 tests | ✓ VERIFIED |
| `tests/test_walkforward.py` | 50 | 252 | 11 tests | ✓ VERIFIED |
| `src/kalshi_backtest/cli.py` | — | modified | `run` command with @app.command() | ✓ VERIFIED |
| `tests/test_cli.py` | — | modified | 6 run command tests (test_run_*) | ✓ VERIFIED |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| simulation/protocol.py | simulation/snapshot.py | Strategy.generate_signals() accepts MarketSnapshot | ✓ WIRED | TYPE_CHECKING import in protocol.py; MarketSnapshot in generate_signals() signature |
| simulation/__init__.py | protocol.py + snapshot.py | re-exports all public types | ✓ WIRED | All 5+ names imported and in __all__ |
| bar_iterator.py | simulation/snapshot.py | build_snapshot(market, candle, suppress_result=True\|False) | ✓ WIRED | `from kalshi_backtest.simulation.snapshot import MarketSnapshot, build_snapshot`; called in __iter__ |
| fill_engine.py | simulation/protocol.py | Signal consumed to produce Fill; Position consumed by close_position | ✓ WIRED | `from kalshi_backtest.simulation.protocol import Position, Signal` |
| runner.py | bar_iterator.py | BacktestRunner constructs BarIterator from repo data and iterates it | ✓ WIRED | `bar_iterator = BarIterator(markets, candles_by_ticker)` in run() |
| runner.py | fill_engine.py | BacktestRunner calls FillEngine.try_fill() for each Signal | ✓ WIRED | `fill = self._fill_engine.try_fill(signal, snapshot)` in run() loop |
| runner.py | position_tracker.py | Fills open positions; settlement closes via PositionTracker.settle() | ✓ WIRED | `tracker.open(fill)` and `tracker.settle(ticker, result, ts)` in run() |
| runner.py | db/repository.py | get_markets() + get_candles() bulk-load before loop | ✓ WIRED | `self._repo.get_markets(...)` and `self._repo.get_candles(...)` in run() |
| sweep.py | runner.py | ParameterSweeper calls BacktestRunner.run() for each param combo | ✓ WIRED | `self._runner.run(strategy=strategy, ...)` in ParameterSweeper.run() |
| walkforward.py | runner.py | WalkForwardValidator calls BacktestRunner.run() with sliced dates per fold | ✓ WIRED | `self._runner.run(start_date=start_date, end_date=train_end)` and test window run() |
| cli.py run command | simulation/runner.py | constructs BacktestRunner(repo, fill_engine) and calls run() | ✓ WIRED | Lazy import `from kalshi_backtest.simulation.runner import BacktestRunner`; `runner_obj.run(...)` called |
| cli.py run command | db/repository.py | opens DuckDB via get_or_create_db() and wraps in MarketRepository | ✓ WIRED | `con = get_or_create_db(settings.db_path); repo = MarketRepository(con)` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| BacktestRunner.run() | markets, candles_by_ticker | repo.get_markets(), repo.get_candles() — DuckDB queries | Yes — real DB queries via MarketRepository | ✓ FLOWING |
| PositionTracker.to_trade_log() | _closed list | ClosedPosition records built from real Fill events | Yes — from actual signal fills and settlement | ✓ FLOWING |
| PositionTracker.to_daily_pnl_series() | daily dict | Aggregated from ClosedPosition.pnl_cents | Yes — from real P&L calculations | ✓ FLOWING |
| BacktestResult.trade_log | tracker.to_trade_log() | PositionTracker state after full bar loop | Yes — populated from real simulation run | ✓ FLOWING |
| CLI run command | result | BacktestRunner.run() return value | Yes — real execution path (stub strategy noted) | ✓ FLOWING |

Note: The `_PassThroughStrategy` inline stub in `cli.py run` generates zero signals. This is an intentional, documented scaffold — the infrastructure is fully wired; only the real strategy is deferred to Phase 4. The data flow path is proven via test_runner.py's buying-strategy integration tests.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All simulation types importable from single import | `from kalshi_backtest.simulation import Strategy, ... WalkForwardResult` | "All imports OK" | ✓ PASS |
| Strategy structural subtyping (no inheritance) | `isinstance(MyStrategy(), Strategy)` | True | ✓ PASS |
| Fee formula ceil(0.07 * C * P * (1-P)) | `calculate_fee_cents(100, 0.50)` | 2; `calculate_fee_cents(1, 0.50)` → 1 | ✓ PASS |
| Signal frozen — mutation raises | `s.ticker = 'Y'` on frozen Signal | ValidationError | ✓ PASS |
| Settlement P&L binary formula | calculate_settlement_pnl('yes', 40, 10, 'yes') | 600; ('no') → -400 | ✓ PASS |
| build_snapshot look-ahead firewall | suppress_result=True → result None; suppress_result=False → 'yes' | Correct | ✓ PASS |
| CLI run --dry-run exits 0 | `runner.invoke(app, ['run', '--dry-run'])` | exit_code=0, output contains '365' | ✓ PASS |
| CLI run --lookback-days 90 --dry-run | output contains '90' | Confirmed | ✓ PASS |
| Walk-forward 3 folds non-overlapping | WalkForwardValidator(runner, n_splits=3).run(...) | 3 folds, train_end<=test_start, non-overlapping | ✓ PASS |
| Full test suite | pytest tests/ (138 phase-2 tests) | 138 passed in 0.71s | ✓ PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SIM-01 | 02-01 | Strategy Protocol interface — implement generate_signals() to plug in any strategy | ✓ SATISFIED | @runtime_checkable Strategy Protocol in protocol.py; structural subtyping confirmed |
| SIM-02 | 02-01, 02-02, 02-03 | Bar-by-bar replay engine that prevents look-ahead bias | ✓ SATISFIED | BarIterator suppress_result firewall; test_lookahead_not_possible in test_runner.py |
| SIM-03 | 02-02 | Exact Kalshi fee formula: ceil(0.07 * C * P * (1-P)) | ✓ SATISFIED | calculate_fee_cents() with max(1, math.ceil(raw)); 3 formula-verification tests |
| SIM-04 | 02-02 | Conservative fill model with spread-aware execution | ✓ SATISFIED | simulate_fill_price() using mid +/- half_spread; FillEngine.try_fill() returns None when unfillable |
| SIM-05 | 02-02, 02-03 | Binary P&L — hold-to-settlement and pre-resolution exit | ✓ SATISFIED | calculate_settlement_pnl() and calculate_exit_pnl() pure functions; PositionTracker.settle() and close() |
| SIM-06 | 02-04 | Parameter grid sweep — test multiple strategy configurations | ✓ SATISFIED | ParameterSweeper with itertools.product; 8 tests confirm combinatorics and Sharpe sorting |
| SIM-07 | 02-04 | Walk-forward validation — rolling train/test splits | ✓ SATISFIED | WalkForwardValidator expanding-window; 11 tests confirm fold count, non-overlap, date ordering |
| CLI-02 | 02-05 | Configurable lookback window per backtest run (default ~1 year) | ✓ SATISFIED | `run` command with --lookback-days (default 365), --series, --dry-run; 6 TDD CLI tests pass |

All 8 Phase 2 requirements satisfied. No orphaned requirements.

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `src/kalshi_backtest/cli.py` ~line 228 | `_PassThroughStrategy` — generates zero signals | ℹ️ Info | Documented intentional stub. CLI run command wires all infrastructure (BacktestRunner, FillEngine, MarketRepository) end-to-end but defers real signal generation to Phase 4 strategy. Zero trades produced in live mode. NOT a phase 2 gap — CLI-02 only requires the command exist with configurable lookback. |

No blockers. No unexpected stubs or hardcoded empty returns in simulation logic.

---

### Human Verification Required

None. All phase 2 goals are verifiable programmatically.

For completeness, future human checks when real data is available:
1. **Live run produces realistic P&L** — run `kalshi-backtest run --lookback-days 90` with actual credentials and a real strategy; verify trade log is non-empty and fee amounts match Kalshi's published schedule.
2. **Chronological ordering across event categories** — with real Kalshi API data, confirm BarIterator correctly interleaves bars from KXBTC, KXINX, and other series.

---

### Gaps Summary

No gaps found. All 9 observable truths verified, all 18 artifacts substantive and wired, all 12 key links confirmed, all 8 requirements satisfied, and 138 TDD tests pass in 0.71s.

The only noted item is the documented `_PassThroughStrategy` stub in cli.py — this is an expected Phase 4 handoff, explicitly called out in the 02-05 SUMMARY, and does not affect CLI-02 requirement satisfaction.

---

_Verified: 2026-04-06T00:24:50Z_
_Verifier: Claude (gsd-verifier)_
