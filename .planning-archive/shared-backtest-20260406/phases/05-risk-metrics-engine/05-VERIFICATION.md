---
phase: 05-risk-metrics-engine
verified: 2026-03-29T05:50:00Z
status: passed
score: 6/6 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Supply SPY and Russell 2000 return Series to MetricsEngine.compute() and confirm alpha/beta values are plausible vs. live market data"
    expected: "Alpha near 0 for a market-neutral strategy; beta < 0.3 for a short-heavy strategy"
    why_human: "No SPY/Russell data loader exists in Phase 5. The engine accepts any pd.Series benchmark, but the success criterion says 'runs against SPY and Russell 2000'. This requires a real data source (yfinance or price DB) to fully satisfy the criterion — not yet wired in this phase. Phase 6/8 is expected to supply benchmark data. The computation is correct; only the data sourcing is deferred."
---

# Phase 5: Risk Metrics Engine Verification Report

**Phase Goal:** A MetricsBundle containing the full institutional metric suite can be computed from any PortfolioResult, including benchmark comparison and rolling statistics
**Verified:** 2026-03-29T05:50:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | MetricsBundle is a frozen Pydantic model with all 10 scalar and rolling Series fields | VERIFIED | `metrics/types.py`: `model_config = {"frozen": True, "arbitrary_types_allowed": True}` with 8 float fields + 2 pd.Series fields; mutation raises `ValidationError` confirmed by test |
| 2 | MetricsConfig is defined in config.py with load_metrics_config() factory | VERIFIED | `config.py` lines 165-207: `class MetricsConfig` with `rolling_window=252`, `periods_per_year=252`, `risk_free_rate=0.0` and `def load_metrics_config()` confirmed importable |
| 3 | MetricsEngine.compute() returns a MetricsBundle with all 10 fields populated from PortfolioResult | VERIFIED | `metrics/engine.py`: `compute()` returns `MetricsBundle(...)` with all 10 fields; smoke test confirms `sharpe=0.152, max_dd=-0.116, cagr=0.012` from synthetic 300-day series |
| 4 | Sharpe, Sortino, Calmar, CAGR use periods=252 — never the quantstats default of 365 | VERIFIED | 8 occurrences of `periods=` in engine.py; `grep -r "periods=365"` returns empty; all `qs.stats.*` calls pass `periods=config.periods_per_year` |
| 5 | Rolling drawdown is always <= 0; rolling Sharpe has NaN before window fills | VERIFIED | `test_rolling_drawdown_values_non_positive` and `test_rolling_sharpe_nan_before_window_fills` pass; smoke test: `rolling_sharpe NaN count=251 out of 300` with default window=252 |
| 6 | alpha=0.0 and beta=0.0 when benchmark is None; valid floats when benchmark is supplied | VERIFIED | `compute()` at lines 166-184: explicit `alpha=0.0, beta=0.0` on `None`; smoke test with benchmark: `alpha=0.0214, beta=0.0248` |

**Score:** 6/6 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backtest/src/fund_backtest/metrics/__init__.py` | Package docstring; barrel imports explicit | VERIFIED | Exists, 9 lines, module docstring present |
| `backtest/src/fund_backtest/metrics/types.py` | MetricsBundle frozen Pydantic model with all 10 fields | VERIFIED | 116 lines; `class MetricsBundle` with `frozen=True`, `arbitrary_types_allowed=True`, `_TRADING_DAYS_PER_YEAR=252` constant |
| `backtest/src/fund_backtest/metrics/engine.py` | MetricsEngine class with compute() method | VERIFIED | 227 lines; `class MetricsEngine` with `compute()`, `_rolling_drawdown()`, `_annual_turnover()` helpers; structlog bound with `component="metrics_engine"` |
| `backtest/src/fund_backtest/config.py` | MetricsConfig and load_metrics_config() | VERIFIED | Lines 165-207; `class MetricsConfig(BaseModel)` with 3 fields; `def load_metrics_config()` factory pattern matches CostConfig |
| `backtest/tests/unit/test_metrics_types.py` | 4 passing tests for MetricsBundle schema | VERIFIED | 4 tests in `TestMetricsBundle`; all pass |
| `backtest/tests/unit/test_metrics_engine.py` | 15 passing tests across 4 requirement groups | VERIFIED | 15 tests in 4 classes: `TestScalarMetrics` (4), `TestTradeMetrics` (3), `TestBenchmarkMetrics` (3), `TestRollingMetrics` (5); all 19 metrics tests pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `metrics/engine.py` | `quantstats_lumi.stats` | `import quantstats_lumi as qs; qs.stats.sharpe(returns, rf=rf, periods=252)` | WIRED | Line 28: `import quantstats_lumi as qs`; lines 151-155: all qs.stats calls with `periods=periods` |
| `metrics/engine.py` | `metrics/types.py` | `return MetricsBundle(...)` | WIRED | Line 213: `return MetricsBundle(...)` with all 10 fields; import at line 32 |
| `metrics/engine.py` | `simulator/types.py` | `result: PortfolioResult` | WIRED | Line 33: `from fund_backtest.simulator.types import PortfolioResult`; line 117: `result: PortfolioResult` type annotation |
| `config.py` | `metrics/types.py` | `MetricsConfig.rolling_window` consumed by `MetricsEngine` | WIRED | `MetricsEngine.__init__` at line 110-112 stores `self._config = config or MetricsConfig()`; `window = self._config.rolling_window` at line 145 |

Note: Plan 05-01 listed the `types.py -> simulator/types.py` link, but `PortfolioResult` is correctly imported in `engine.py` (not `types.py`). `MetricsBundle` is the output contract only; it need not import its input type. The link is satisfied at the engine layer.

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `engine.py` | `returns` | `result.net_returns` (PortfolioResult input) | Yes — caller supplies real pd.Series from simulator | FLOWING |
| `engine.py` | `sharpe, sortino, calmar, cagr, max_dd` | `qs.stats.*()` calls on `returns` | Yes — quantstats-lumi computes from returns series | FLOWING |
| `engine.py` | `hit_rate, win_loss` | `qs.stats.win_rate()`, `qs.stats.win_loss_ratio()` | Yes — computed from returns; guarded against inf | FLOWING |
| `engine.py` | `turnover` | `_annual_turnover(result)` using `result.trade_log` | Yes — groupby weight_change from actual trade_log rows | FLOWING |
| `engine.py` | `alpha, beta` | `qs.stats.greeks()` or 0.0 default | Yes — 0.0 explicit when None; computed from benchmark when supplied; guarded against near-zero variance | FLOWING |
| `engine.py` | `roll_sharpe, roll_dd` | `qs.stats.rolling_sharpe()`, `_rolling_drawdown()` | Yes — computed from returns with configurable window; NaN-before-fill confirmed | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| MetricsEngine importable | `python -c "from fund_backtest.metrics.engine import MetricsEngine; print('OK')"` | OK | PASS |
| quantstats-lumi installed | `python -c "import quantstats_lumi as qs; print(qs.__version__)"` | 1.1.3 | PASS |
| MetricsConfig defaults correct | `load_metrics_config()` returns `rolling_window=252, periods_per_year=252, risk_free_rate=0.0` | Confirmed | PASS |
| End-to-end smoke test | `MetricsEngine().compute(result)` on 300-day synthetic series | `sharpe=0.152, max_dd=-0.116, cagr=0.012` | PASS |
| max_drawdown <= 0 | `bundle.max_drawdown <= 0` assertion | -0.116 <= 0 | PASS |
| rolling_sharpe NaN before window | 251 NaN out of 300 with window=252 | 251 NaN confirmed | PASS |
| No hardcoded periods=365 | `grep -r "periods=365" metrics/` | empty | PASS |
| No network access in metrics | `grep -r "yf.\|requests.\|httpx." metrics/` | empty | PASS |
| Full 19 metrics tests green | `pytest test_metrics_engine.py test_metrics_types.py -q` | 19 passed | PASS |
| Full 125 unit tests green | `pytest tests/unit/ -x -q` | 125 passed | PASS |
| Coverage >= 80% on metrics/ | `pytest --cov=src/fund_backtest/metrics` | 97.75% (engine: 97%, types: 100%, __init__: 100%) | PASS |
| ruff clean on metrics/ | `ruff check src/fund_backtest/metrics/` | All checks passed | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| RISK-01 | 05-01, 05-02 | Compute Sharpe ratio, Sortino ratio, max drawdown, and Calmar ratio | SATISFIED | `engine.py` lines 151-155: `qs.stats.sharpe`, `qs.stats.sortino`, `qs.stats.calmar`, `qs.stats.max_drawdown`, `qs.stats.cagr` all called with `periods=252`; 4 tests in `TestScalarMetrics` pass |
| RISK-02 | 05-01, 05-02 | Compute hit rate, win/loss ratio, and portfolio turnover | SATISFIED | `engine.py` lines 158-163: `qs.stats.win_rate`, `qs.stats.win_loss_ratio` (guarded against inf), `_annual_turnover()` from `trade_log`; 3 tests in `TestTradeMetrics` pass including empty trade_log edge case |
| RISK-03 | 05-01, 05-02 | Compare strategy returns against S&P 500 and Russell 2000 benchmarks | PARTIALLY SATISFIED | Engine implements alpha/beta computation via `qs.stats.greeks()`; `alpha=0.0, beta=0.0` when `benchmark=None`; 3 tests in `TestBenchmarkMetrics` pass. However, no SPY/Russell data loader exists — the engine accepts any caller-supplied `pd.Series`. The specific benchmark *data* sourcing is deferred to Phase 6/8. See human verification. |
| RISK-04 | 05-01, 05-02 | Compute rolling Sharpe and rolling drawdown over configurable windows | SATISFIED | `engine.py` lines 187-204: `qs.stats.rolling_sharpe(rolling_period=window, periods_per_year=periods)` and `_rolling_drawdown(returns, window)`; DataFrame squeeze guard applied; 5 tests in `TestRollingMetrics` pass including configurable window test |

**Requirements status:** 3 fully satisfied, 1 partially satisfied (RISK-03 deferred benchmark data sourcing)

**Orphaned requirements check:** No additional RISK-* requirements map to Phase 5 beyond RISK-01 through RISK-04 per REQUIREMENTS.md traceability table.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

Checked files: `metrics/engine.py`, `metrics/types.py`, `metrics/__init__.py`, `config.py` (MetricsConfig section), `test_metrics_engine.py`, `test_metrics_types.py`.

No TODO/FIXME/placeholder comments, no empty implementations, no hardcoded empty data passed to rendering, no `return null` stubs. The `win_loss` guard (`if not math.isfinite(win_loss): win_loss = 0.0`) is a correct production guard, not a stub.

---

### Human Verification Required

#### 1. SPY and Russell 2000 Benchmark Sourcing

**Test:** Load SPY and IWM (Russell 2000 ETF) daily return Series via yfinance or the price DB, then call `MetricsEngine().compute(result, benchmark=spy_returns)` and `MetricsEngine().compute(result, benchmark=iwm_returns)` with a real PortfolioResult from the simulator.

**Expected:** Alpha and beta values should be plausible: beta close to -1.0 for a pure short strategy, beta near 0 for a market-neutral strategy. Alpha should be non-zero for strategies with genuine edge.

**Why human:** No SPY/Russell data loader exists in the metrics module. The RISK-03 success criterion says "runs against SPY and Russell 2000" which implies data integration. Phase 6 will provide benchmark data via yfinance. The engine is correctly implemented (computation verified), but real-data validation requires running the full pipeline with actual market data — not testable programmatically in isolation.

---

### Gaps Summary

No blocking gaps found. All 10 MetricsBundle fields are populated from real computation (no stubs, no placeholders, no hardcoded values). The one partial item (RISK-03 benchmark data sourcing) is a scope deferral documented in RESEARCH.md and does not block Phase 6 consumption of MetricsBundle.

The RISK-03 partial status is a known design decision: the metrics engine is intentionally generic (accepts any `pd.Series` benchmark). Phase 6 (Streamlit Dashboard) will supply SPY/Russell data from the price DB when rendering benchmark overlays.

---

_Verified: 2026-03-29T05:50:00Z_
_Verifier: Claude (gsd-verifier)_
