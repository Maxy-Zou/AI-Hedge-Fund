---
phase: 03-metrics-and-reporting
verified: 2026-04-04T00:00:00Z
status: passed
score: 6/6 must-haves verified
re_verification: false
---

# Phase 3: Metrics and Reporting Verification Report

**Phase Goal:** After any backtest run, an investor-useful performance summary and interactive dashboard are generated automatically
**Verified:** 2026-04-04
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                 | Status     | Evidence                                                                                                         |
|----|---------------------------------------------------------------------------------------|------------|------------------------------------------------------------------------------------------------------------------|
| 1  | Core metrics (Sharpe, Sortino, CAGR, drawdown, win rate, total return, avg P&L) computed from BacktestResult | ✓ VERIFIED | `MetricsCalculator.compute()` in calculator.py lines 191–274 calls all quantstats functions; 6/6 unit tests pass |
| 2  | Trade log CSV exported with pnl_usd and fee_usd columns                               | ✓ VERIFIED | `export_trade_log()` in trade_log.py adds both columns (cents/100); 3/3 unit tests pass                          |
| 3  | Interactive Plotly HTML dashboard generated with equity curve and category breakdown  | ✓ VERIFIED | `build_dashboard()` and `DashboardBuilder.write_html()` in dashboard.py; `include_plotlyjs="cdn"`; 3/3 tests pass |
| 4  | Sample size warning fires when N<30 distinct settled markets                          | ✓ VERIFIED | `_count_settled_markets()` uses `ticker.nunique()` on settlement rows; `sample_size_warning = settled_markets < 30` |
| 5  | `run` command prints metrics summary and writes reports to `--output-dir`             | ✓ VERIFIED | cli.py lines 327–343: `MetricsCalculator().compute()`, `print_metrics_summary()`, `export_trade_log()`, `DashboardBuilder.write_html()` |
| 6  | `compare` command prints side-by-side Rich table for two strategies                   | ✓ VERIFIED | cli.py lines 348–463; `compare --dry-run` outputs "Strategy Comparison" table; 3/3 CLI compare tests pass        |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact                                                          | Expected                                        | Status     | Details                              |
|-------------------------------------------------------------------|-------------------------------------------------|------------|--------------------------------------|
| `kalshi-backtest/pyproject.toml`                                  | quantstats and plotly dependency declarations   | ✓ VERIFIED | Lines 19–20: `quantstats>=0.0.81`, `plotly>=5.0` |
| `kalshi-backtest/src/kalshi_backtest/metrics/__init__.py`         | Public exports for all 6 symbols                | ✓ VERIFIED | 24 lines; exports BacktestMetrics, MetricsCalculator, export_trade_log, build_dashboard, compute_category_breakdown, DashboardBuilder |
| `kalshi-backtest/src/kalshi_backtest/metrics/calculator.py`       | BacktestMetrics model + MetricsCalculator       | ✓ VERIFIED | 274 lines (>120 minimum); all scalar fields present; `STARTING_CAPITAL_CENTS = 10_000`; `_count_settled_markets`, `_to_fractional_returns` present |
| `kalshi-backtest/src/kalshi_backtest/metrics/trade_log.py`        | export_trade_log function                       | ✓ VERIFIED | 52 lines (>40 minimum); accepts BacktestResult; adds pnl_usd, fee_usd; never mutates input |
| `kalshi-backtest/src/kalshi_backtest/metrics/dashboard.py`        | build_dashboard, compute_category_breakdown, DashboardBuilder | ✓ VERIFIED | 352 lines (>120 minimum); 4-panel layout; CDN JS; sample_size_warning annotation wired |
| `kalshi-backtest/src/kalshi_backtest/cli.py`                      | Enriched run + new compare command              | ✓ VERIFIED | 463 lines; `compare` command present; MetricsCalculator wired into run; --output-dir flag exists |
| `kalshi-backtest/tests/test_metrics_calculator.py`                | RED then GREEN tests for MET-01 and MET-07      | ✓ VERIFIED | 195 lines (>60 minimum); 6 tests, all pass                |
| `kalshi-backtest/tests/test_trade_log.py`                         | RED then GREEN tests for MET-02                 | ✓ VERIFIED | 138 lines (>30 minimum); 3 tests, all pass                |
| `kalshi-backtest/tests/test_dashboard.py`                         | RED then GREEN tests for MET-03 and MET-06      | ✓ VERIFIED | 148 lines (>40 minimum); 3 tests, all pass                |

### Key Link Verification

| From                                  | To                                | Via                              | Status     | Details                                                                          |
|---------------------------------------|-----------------------------------|----------------------------------|------------|----------------------------------------------------------------------------------|
| `tests/test_metrics_calculator.py`    | `kalshi_backtest.metrics.calculator` | import                        | ✓ WIRED    | `from kalshi_backtest.metrics.calculator import MetricsCalculator, BacktestMetrics` |
| `tests/test_trade_log.py`             | `kalshi_backtest.metrics.trade_log`  | import                        | ✓ WIRED    | `from kalshi_backtest.metrics.trade_log import export_trade_log`                  |
| `tests/test_dashboard.py`             | `kalshi_backtest.metrics.dashboard`  | import                        | ✓ WIRED    | `from kalshi_backtest.metrics.dashboard import build_dashboard, compute_category_breakdown` |
| `metrics/calculator.py`               | `quantstats.stats`                   | `import quantstats as qs`     | ✓ WIRED    | Line 21: `import quantstats as qs`; used in sharpe/sortino/cagr/drawdown/win_rate calls |
| `MetricsCalculator.compute`           | `_to_fractional_returns`             | internal helper call          | ✓ WIRED    | Line 227: `returns = _to_fractional_returns(result.daily_pnl)` |
| `BacktestMetrics.sample_size_warning` | `_count_settled_markets`             | comparison < 30               | ✓ WIRED    | Lines 253–254: `settled_markets = _count_settled_markets(...); sample_size_warning = settled_markets < 30` |
| `metrics/dashboard.py`                | `plotly.subplots.make_subplots`      | import                        | ✓ WIRED    | Line 18: `from plotly.subplots import make_subplots`; called in `build_dashboard` |
| `dashboard.py`                        | `BacktestMetrics`                    | type annotation               | ✓ WIRED    | Line 20: `from kalshi_backtest.metrics.calculator import BacktestMetrics`; used in `build_dashboard` signature |
| `build_dashboard`                     | `compute_category_breakdown`         | internal call for per-category panel | ✓ WIRED | Line 257: `breakdown = compute_category_breakdown(trade_log)` |
| `cli.py run command`                  | `MetricsCalculator.compute`          | call after runner_obj.run()   | ✓ WIRED    | Lines 327–328: `metrics = MetricsCalculator().compute(result); print_metrics_summary(metrics, _console)` |
| `cli.py run command`                  | `DashboardBuilder.write_html`        | conditional on --output-dir   | ✓ WIRED    | Line 342: `DashboardBuilder(metrics, result.trade_log).write_html(output_dir / "dashboard.html")` |
| `cli.py compare command`              | `print_comparison_table`             | call after running both strategies | ✓ WIRED | Lines 394 and 453: `print_comparison_table([...], _console)` |

### Data-Flow Trace (Level 4)

| Artifact                  | Data Variable    | Source                            | Produces Real Data | Status      |
|---------------------------|------------------|-----------------------------------|--------------------|-------------|
| `calculator.py`           | `returns`        | `_to_fractional_returns(result.daily_pnl)` | Yes — from BacktestResult.daily_pnl, fills sparse calendar range | ✓ FLOWING |
| `calculator.py`           | `equity_curve`   | `_build_equity_curve(result.daily_pnl)` | Yes — cumulative sum of daily_pnl/100 | ✓ FLOWING |
| `dashboard.py`            | `metrics.equity_curve` | `BacktestMetrics.equity_curve` passed in from caller | Yes — populated by MetricsCalculator | ✓ FLOWING |
| `cli.py run`              | `metrics`        | `MetricsCalculator().compute(result)` | Yes — result comes from BacktestRunner.run() | ✓ FLOWING |
| `cli.py compare --dry-run`| `metrics_a/b`    | `BacktestMetrics(strategy_name=...)` | Zero-valued — correct behavior for dry-run mode | ✓ FLOWING (by design) |

### Behavioral Spot-Checks

| Behavior                                             | Command                                          | Result                                                         | Status  |
|------------------------------------------------------|--------------------------------------------------|----------------------------------------------------------------|---------|
| `compare --dry-run` prints "Strategy Comparison"     | `uv run kalshi-backtest compare --dry-run`       | Table with "Strategy Comparison" title, StrategyA and StrategyB columns, exits 0 | ✓ PASS |
| All 12 Phase 3 unit tests pass                       | `uv run pytest tests/test_metrics_calculator.py tests/test_trade_log.py tests/test_dashboard.py -q` | 12 passed in 1.55s | ✓ PASS |
| Full suite (221 tests) — no regressions              | `uv run pytest -q`                               | 221 passed, 15 warnings (all pre-existing DeprecationWarnings) | ✓ PASS |
| CLI compare tests pass (3 compare-specific tests)   | `uv run pytest tests/test_cli.py -q`             | 12 passed                                                      | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description                                                            | Status       | Evidence                                                              |
|-------------|-------------|------------------------------------------------------------------------|--------------|-----------------------------------------------------------------------|
| MET-01      | 03-01, 03-02 | Core metrics — total return, Sharpe, Sortino, max drawdown, win rate, avg trade P&L, CAGR | ✓ SATISFIED | All computed in `MetricsCalculator.compute()`; 6 unit tests green    |
| MET-02      | 03-01, 03-02 | Trade log — every entry/exit with timestamps, prices, contract details, fees paid | ✓ SATISFIED | `export_trade_log()` writes all original columns + pnl_usd, fee_usd; 3 unit tests green |
| MET-03      | 03-01, 03-03 | Equity curve visualization                                             | ✓ SATISFIED | Panel (1,1) in `build_dashboard()` is a `go.Scatter` trace named "Equity"; test_equity_curve_trace_present passes |
| MET-05      | 03-04        | Strategy comparison — run multiple strategies side-by-side with comparative metrics | ✓ SATISFIED | `compare` command runs two strategies and prints Rich comparison table; 3 compare CLI tests pass |
| MET-06      | 03-01, 03-03 | Interactive Plotly dashboard with per-category performance breakdown   | ✓ SATISFIED | 4-panel Plotly HTML with `compute_category_breakdown` panels; CDN JS; `DashboardBuilder.write_html()` confirmed |
| MET-07      | 03-01, 03-02 | Sample size warnings — flag results with N<30 events as statistically unreliable | ✓ SATISFIED | `_count_settled_markets()` counts distinct settled tickers; `sample_size_warning = settled_markets < 30`; dashboard annotation + CLI warning wired |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `dashboard.py` | 182 | Comment: "Provide an empty placeholder so the subplot still renders" | Info | Not a stub — this is the intentional fallback for empty equity_curve (renders an empty trace, not fake data) |

No blocking or warning-level anti-patterns found. The single "placeholder" mention is a legitimate code comment explaining an intentional empty-trace fallback.

### Human Verification Required

None. All phase goal behaviors are verifiable programmatically:

- Metrics computation: unit tests exercise all 7 scalar metrics against a fixture with known values.
- Dashboard generation: `test_write_html_creates_file` confirms a non-empty HTML file is produced.
- CLI compare table: behavioral spot-check confirmed output contains "Strategy Comparison" with two strategy columns.
- CDN Plotly JS: `include_plotlyjs="cdn"` confirmed at source (dashboard.py line 352) — no human needed to inspect HTML.

The one item that would benefit from optional human review is visual quality of the dashboard (layout aesthetics, colors, chart readability) — but this is not a blocker for goal achievement and was explicitly out of scope for automated verification.

### Gaps Summary

No gaps. All 6 requirements are satisfied, all 9 artifact checks pass at all four levels (exists, substantive, wired, data-flowing), and the full 221-test suite passes with no regressions.

The phase goal — "After any backtest run, an investor-useful performance summary and interactive dashboard are generated automatically" — is achieved:

- The `run` command automatically calls `MetricsCalculator().compute()` and `print_metrics_summary()` after every non-dry-run execution (no flag required).
- The `--output-dir` flag on `run` writes `trade_log.csv` and `dashboard.html` automatically.
- The `compare` command provides side-by-side comparison for multiple strategies.
- All outputs (metrics table, CSV, HTML dashboard) are wired to real data from `BacktestResult`, not hardcoded values.

---

_Verified: 2026-04-04_
_Verifier: Claude (gsd-verifier)_
