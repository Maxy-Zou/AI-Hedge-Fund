---
phase: 04-cost-model-and-portfolio-simulator
verified: 2026-03-29T10:00:00Z
status: passed
score: 15/15 must-haves verified
re_verification: false
---

# Phase 4: Cost Model and Portfolio Simulator Verification Report

**Phase Goal:** A fully vectorized portfolio simulator produces daily returns and a trade log from a WeightFrame, with realistic short borrow and transaction costs built in
**Verified:** 2026-03-29
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                                     | Status     | Evidence                                                                                         |
|----|-----------------------------------------------------------------------------------------------------------|------------|--------------------------------------------------------------------------------------------------|
| 1  | CostConfig is a frozen Pydantic BaseModel with slippage_bps, commission_bps, borrow_cost_bps_annual fields | VERIFIED  | `model_config = {"frozen": True}` in types.py:54; all three float fields with `ge=0.0` validator  |
| 2  | PortfolioResult holds gross_returns, net_returns, positions, and trade_log                                 | VERIFIED  | types.py:67-93; `arbitrary_types_allowed=True`; 4 pd.Series/DataFrame fields                    |
| 3  | load_cost_config() factory in config.py returns CostConfig with correct defaults                          | VERIFIED  | config.py:143-162; reads `"cost"` YAML key, defaults to CostConfig() on None or error            |
| 4  | PortfolioSimulator.simulate() returns PortfolioResult with all four fields                                 | VERIFIED  | engine.py:57-103; all four fields populated and returned                                          |
| 5  | Short positions appear in trade_log with direction="short" and borrow cost deducted                        | VERIFIED  | engine.py:261 direction logic; engine.py:187-201 borrow cost; TestShortPositions: 2 PASS         |
| 6  | Slippage and commission charged only on days with abs(weight_change) > threshold; zero on no-change days  | VERIFIED  | engine.py:171-185 txn cost via diff().abs(); _TRADE_THRESHOLD=1e-8; TestTransactionCosts: 2 PASS |
| 7  | All cost parameters come from CostConfig — no hardcoded numeric constants in engine.py                    | VERIFIED  | No bare numeric cost values found in engine.py; all reference self._config or module constants    |
| 8  | WeightFrame is NOT shifted again in the simulator (Phase 3 shift invariant preserved)                     | VERIFIED  | engine.py:61 explicit comment "DO NOT apply .shift(1) here"; TestNoDoubleShift: PASS             |
| 9  | Input WeightFrame and PriceFrame are not mutated by simulate()                                            | VERIFIED  | engine.py returns new aligned DataFrames; TestImmutableInputs: 2 PASS                            |
| 10 | Leading NaN row is dropped before returning net_returns and gross_returns                                  | VERIFIED  | engine.py:86 `valid_idx = net.dropna().index`; TestNaNFirstRowDropped: 2 PASS                    |
| 11 | Hand-calculated reference test passes within floating-point tolerance                                     | VERIFIED  | TestHandCalculatedReference::test_net_return_matches_hand_calc_day2 PASS; tolerance 1e-6         |
| 12 | No Python loops over dates in engine.py                                                                   | VERIFIED  | grep for `for.*in.*index` returned no matches; all ops are pandas vectorized                     |
| 13 | test_simulator_types.py: all type contract tests GREEN                                                    | VERIFIED  | 8 tests PASS (defaults, validation, frozen enforcement, PortfolioResult construction)             |
| 14 | test_simulator_engine.py: all engine behavior tests GREEN                                                 | VERIFIED  | 13 tests PASS (all RED stubs turned GREEN in plan 02)                                             |
| 15 | Full unit suite (106 tests) passes with no regressions                                                    | VERIFIED  | `106 passed in 1.31s`; prior phase tests unaffected                                              |

**Score:** 15/15 truths verified

### Required Artifacts

| Artifact                                                           | Expected                                         | Status     | Details                                              |
|--------------------------------------------------------------------|--------------------------------------------------|------------|------------------------------------------------------|
| `backtest/src/fund_backtest/simulator/__init__.py`                 | Package marker with module docstring             | VERIFIED   | Exists; 12-line module docstring                     |
| `backtest/src/fund_backtest/simulator/types.py`                    | CostConfig, PortfolioResult, PriceFrame          | VERIFIED   | 93 lines; all three exports present and substantive  |
| `backtest/src/fund_backtest/simulator/engine.py`                   | PortfolioSimulator with simulate() method        | VERIFIED   | 269 lines (>80 min); PortfolioSimulator class found  |
| `backtest/src/fund_backtest/config.py`                             | load_cost_config() factory added                 | VERIFIED   | load_cost_config at line 143; CostConfig imported    |
| `backtest/tests/unit/test_simulator_types.py`                      | 8 passing type contract tests                    | VERIFIED   | 8 tests GREEN                                        |
| `backtest/tests/unit/test_simulator_engine.py`                     | 13 passing engine behavior tests                 | VERIFIED   | 13 tests GREEN; TestHandCalculatedReference present  |

### Key Link Verification

| From                               | To                                         | Via                                         | Status   | Details                                                  |
|------------------------------------|--------------------------------------------|---------------------------------------------|----------|----------------------------------------------------------|
| simulator/types.py                 | config.py                                  | CostConfig imported into load_cost_config() | WIRED    | config.py:10 `from fund_backtest.simulator.types import CostConfig` |
| simulator/engine.py                | simulator/types.py                         | CostConfig, PortfolioResult, PriceFrame     | WIRED    | engine.py:25 `from fund_backtest.simulator.types import` |
| simulator/engine.py                | signal/types.py                            | WeightFrame type annotation                 | WIRED    | engine.py:24 `from fund_backtest.signal.types import WeightFrame` |
| engine._compute_gross_returns      | prices.pct_change()                        | pandas vectorized daily return              | WIRED    | engine.py:161 `daily_returns = prices.pct_change()`     |
| engine._compute_borrow_costs       | CostConfig.borrow_cost_bps_annual          | daily_rate = borrow_cost_bps_annual / 10_000 / 252 | WIRED | engine.py:199 exact formula present                |
| test_simulator_engine.py           | simulator/engine.py                        | import PortfolioSimulator                   | WIRED    | engine.py exists; import succeeds; 13 tests PASS         |

### Data-Flow Trace (Level 4)

The simulator is a pure computation module — it takes DataFrames in and produces a PortfolioResult out. There is no DB fetch or external data source. Data flow is: WeightFrame + PriceFrame -> vectorized pandas math -> PortfolioResult. Verified by test assertions on real computed values (not static returns), specifically TestHandCalculatedReference which validates the exact formula chain from prices to net_returns.

| Artifact            | Data Variable     | Source                        | Produces Real Data | Status    |
|---------------------|-------------------|-------------------------------|-------------------|-----------|
| engine.py simulate()| gross_returns     | prices.pct_change() * weights | Yes               | FLOWING   |
| engine.py simulate()| net_returns       | gross - txn_cost - borrow     | Yes               | FLOWING   |
| engine.py simulate()| trade_log         | weights.diff() via stack()    | Yes               | FLOWING   |
| engine.py simulate()| positions         | aligned_weights (sliced)      | Yes               | FLOWING   |

### Behavioral Spot-Checks

| Behavior                                              | Command                                                                    | Result         | Status  |
|-------------------------------------------------------|----------------------------------------------------------------------------|----------------|---------|
| All 21 simulator tests pass                           | pytest tests/unit/test_simulator_types.py tests/unit/test_simulator_engine.py | 21 passed 0.75s | PASS  |
| Full 106-test unit suite passes without regression    | pytest tests/unit/ -q                                                      | 106 passed 1.31s | PASS  |
| Simulator module coverage >= 80%                      | pytest tests/unit/ --cov=fund_backtest.simulator                           | 96.67% (97%)   | PASS    |
| No Python date loops in engine.py                     | grep "for.*in.*index" engine.py                                            | No matches     | PASS    |
| No hardcoded cost numerics in engine.py               | grep for bare float/int cost values                                        | No matches     | PASS    |

### Requirements Coverage

| Requirement | Source Plans  | Description                                                                | Status    | Evidence                                                     |
|-------------|---------------|----------------------------------------------------------------------------|-----------|--------------------------------------------------------------|
| BT-02       | 04-01, 04-02  | Engine supports short positions as a first-class operation                 | SATISFIED | trade_log with direction="short"; TestShortPositions PASS    |
| BT-03       | 04-01, 04-02  | Engine models transaction costs (slippage + commission, configurable bps)  | SATISFIED | CostConfig slippage_bps + commission_bps; TestTransactionCosts PASS |
| BT-04       | 04-01, 04-02  | Engine models short borrow costs (configurable flat rate, default 50bps/yr) | SATISFIED | borrow_cost_bps_annual field; daily rate formula; TestBorrowCosts PASS |
| BT-06       | 04-01, 04-02  | Engine uses equal-weight position sizing across all signal-selected tickers | SATISFIED | positions = aligned_weights unchanged; TestEqualWeight PASS  |
| BT-07       | 04-01, 04-02  | Engine produces a daily returns series and a trade log as output           | SATISFIED | PortfolioResult.net_returns (Series) + trade_log (DataFrame) |

All 5 phase requirement IDs (BT-02, BT-03, BT-04, BT-06, BT-07) are SATISFIED. No orphaned requirements found — REQUIREMENTS.md traceability table confirms all five map to Phase 4 and are marked Complete.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | -    | -       | -        | No anti-patterns detected in simulator package |

Scan for TODO/FIXME/placeholder returned no matches in `backtest/src/fund_backtest/simulator/`. The three uncovered lines in engine.py (134, 136, 241) are logging warning branches for dropped dates/tickers — defensive code paths that only fire on misaligned inputs. These are not stubs; they are reachable branches with real behavior.

### Human Verification Required

None. All phase behaviors are fully verifiable through the test suite. The simulator has no UI, no visual output, and no external service dependencies — all correctness properties are covered by the 21 automated tests including the hand-calculated reference test.

### Gaps Summary

No gaps. All 15 observable truths verified, all 6 artifacts substantive and wired, all 5 key links confirmed, all 5 requirement IDs satisfied, 106 tests pass with 97% simulator coverage.

---

_Verified: 2026-03-29_
_Verifier: Claude (gsd-verifier)_
