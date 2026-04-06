# Phase 3: Metrics and Reporting - Research

**Researched:** 2026-04-04
**Domain:** Portfolio analytics, interactive visualization, CLI reporting
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- quantstats for standard tearsheet metrics (Sharpe, Sortino, Calmar, drawdown, CAGR)
- Plotly for interactive dashboard (equity curve, trade markers, per-category breakdown)
- Strategy comparison: side-by-side metrics table in terminal via Rich
- Sample size warnings: flag N<30 settled contracts as statistically unreliable
- Trade log: CSV/DataFrame with timestamp, prices, contract ticker, fees paid
- Dashboard output as interactive HTML file (dashboard.html)
- BacktestResult from Phase 2 is the input — daily returns Series + trade log DataFrame

### Claude's Discretion
All implementation choices are at Claude's discretion. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MET-01 | Core metrics — total return, Sharpe, Sortino, max drawdown, win rate, avg trade P&L, CAGR | quantstats.stats functions accept daily returns Series (decimal fractions); custom helpers needed to convert cents-based P&L |
| MET-02 | Trade log — every entry/exit with timestamps, prices, contract details, fees paid | PositionTracker.to_trade_log() already produces the DataFrame; metrics layer writes it to CSV via pandas |
| MET-03 | Equity curve visualization | Plotly go.Scatter with cumsum of daily pnl; write_html() for single-file output |
| MET-05 | Strategy comparison — run multiple strategies side-by-side with comparative metrics | Rich Table with one column per strategy; BacktestMetrics frozen Pydantic objects for each run |
| MET-06 | Interactive Plotly dashboard with per-category performance breakdown | make_subplots with 4 panels: equity curve, drawdown, monthly bar chart, per-category bar chart |
| MET-07 | Sample size warnings — flag results with N<30 events as statistically unreliable | settled_contracts field on BacktestResult; compare against threshold at metric computation time |
</phase_requirements>

---

## Summary

Phase 3 builds the reporting layer that consumes `BacktestResult` from Phase 2 and produces investor-useful output. The input contract is already frozen: `BacktestResult.daily_pnl` is a `pd.Series` of integer cents indexed by `datetime.date`, and `BacktestResult.trade_log` is a DataFrame with the columns `ticker, direction, contracts, entry_price, entry_ts, exit_price, exit_ts, pnl_cents, fee_cents, exit_reason`.

The key translation challenge is that quantstats expects **decimal fractional returns** (e.g., 0.02 for 2% gain) but the engine produces **integer cents P&L** per day. The metrics layer must convert: divide daily `pnl_cents` by an assumed starting capital (e.g., 10000 cents = $100) to produce a fractional return Series before passing to quantstats. This is a critical data-shaping step — getting it wrong silently corrupts every metric.

The phase breaks into four modules: `metrics/calculator.py` (quantstats-based core metrics), `metrics/trade_log.py` (CSV export), `metrics/dashboard.py` (Plotly HTML), and CLI wiring in `cli.py` (a new `compare` command and output path options for `run`).

**Primary recommendation:** Build a thin `BacktestMetrics` frozen Pydantic model that holds all computed scalars (Sharpe, Sortino, etc.) plus a reference to the equity Series. Let `MetricsCalculator` produce it from a `BacktestResult`. Dashboard and CLI consume the `BacktestMetrics` object — never re-compute from raw results.

---

## Project Constraints (from CLAUDE.md)

| Directive | Source |
|-----------|--------|
| Python 3.11+, uv, ruff (line-length=100) | CLAUDE.md / fund-wide |
| Immutable data — frozen Pydantic / frozen dataclasses for contracts | CLAUDE.md |
| Append-only data semantics (do not mutate historical price rows) | CLAUDE.md |
| structlog for all logging; use `logger.bind(component=...)` | CLAUDE.md |
| Rich for terminal output (already used in validator.py) | CLAUDE.md codebase pattern |
| No hard imports from Kalshi Insider Tracker internals | CLAUDE.md |
| Functions < 50 lines; files 200-400 lines max (800 hard cap) | global CLAUDE.md |
| TDD: write tests first (RED), implement (GREEN), 80% coverage minimum | global CLAUDE.md |
| Validate all inputs at system boundaries | global CLAUDE.md |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| quantstats | 0.0.81 | Sharpe, Sortino, CAGR, max drawdown, win rate, profit factor | Locked decision; active successor to deprecated pyfolio; battle-tested |
| plotly | 6.3.1 (already installed globally; add to pyproject.toml) | Interactive equity curve, drawdown, category breakdown, HTML export | Locked decision; `fig.write_html()` produces self-contained dashboard |
| pandas | 3.0.2 (already in deps) | Trade log DataFrame, date-indexed returns Series | Already a dependency |
| rich | 14.0+ (already in deps) | Side-by-side strategy comparison table in terminal | Already used in validator.py; consistent DX |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | 2.4.4 (already in deps) | Vectorized equity curve, drawdown series construction | Complement to pandas for array operations |
| typer | 0.24.1+ (already in deps) | `compare` CLI command wiring | Already the project CLI framework |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| quantstats | pyfolio | pyfolio unmaintained since 2021; quantstats is the active maintained successor |
| quantstats | Manual numpy formulas | Error-prone; quantstats is well-validated; no reason to hand-roll standard metrics |
| plotly write_html | Dash web app | Dash adds web server complexity; single-file HTML is sufficient for v1 CLI tool |

**Installation (to add to pyproject.toml):**
```bash
uv add quantstats plotly
```

**Version verification (confirmed 2026-04-04):**
```bash
pip index versions quantstats   # 0.0.81 is latest
python3 -c "import plotly; print(plotly.__version__)"  # 6.3.1 available on system
```

---

## Architecture Patterns

### Recommended Project Structure
```
src/kalshi_backtest/
├── metrics/
│   ├── __init__.py          # exports BacktestMetrics, MetricsCalculator
│   ├── calculator.py        # BacktestMetrics model + MetricsCalculator (quantstats)
│   ├── dashboard.py         # Plotly HTML dashboard builder
│   └── trade_log.py         # CSV export, trade log enrichment
└── cli.py                   # updated: report/compare commands wired in
```

### Pattern 1: BacktestMetrics as Frozen Pydantic Contract
**What:** A frozen Pydantic model that holds all computed scalar metrics plus the equity Series. Computed once by `MetricsCalculator.compute()` and passed to dashboard/CLI consumers.
**When to use:** Any time a downstream consumer needs metrics — never let them re-derive from raw BacktestResult.
**Example:**
```python
# Source: codebase convention (frozen Pydantic models at layer boundaries)
from pydantic import BaseModel
import pandas as pd

class BacktestMetrics(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    run_id: str
    strategy_name: str
    start_date: str
    end_date: str

    # Scalar metrics
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    win_rate_pct: float
    avg_trade_pnl_cents: float
    profit_factor: float
    total_trades: int
    settled_contracts: int

    # Warnings
    sample_size_warning: bool  # True when settled_contracts < 30

    # Time series (for dashboard)
    equity_curve: pd.Series    # cumulative dollar value over time
    daily_returns: pd.Series   # fractional daily returns (for quantstats)
```

### Pattern 2: Daily P&L Cents → Fractional Returns Conversion
**What:** quantstats requires fractional daily returns (e.g., 0.02 for 2%), but `BacktestResult.daily_pnl` is integer cents. The conversion requires an assumed starting capital.
**When to use:** Always before calling any quantstats function.
**Example:**
```python
# Source: quantstats stats.py — expects decimal fraction returns
STARTING_CAPITAL_CENTS = 10_000  # $100 starting capital assumption

def _to_fractional_returns(daily_pnl: pd.Series) -> pd.Series:
    """Convert integer cents P&L series to fractional daily returns.

    Reindexes over full date range (fills missing days as 0 P&L),
    then divides by running capital to produce decimal fractions.
    Returns decimal fractions suitable for quantstats (e.g. 0.02 = 2%).
    """
    if daily_pnl.empty:
        return pd.Series(dtype=float)
    # Fill sparse trade days with zero pnl
    full_idx = pd.date_range(daily_pnl.index.min(), daily_pnl.index.max(), freq="D")
    filled = daily_pnl.reindex(full_idx, fill_value=0)
    return (filled / STARTING_CAPITAL_CENTS).astype(float)
```

**Critical:** quantstats `periods=252` assumes daily returns for annualization. Prediction markets don't observe weekends but the daily_pnl Series may have sparse entries (only trade days). Filling zeros for non-trade days is necessary for correct annualization.

### Pattern 3: Plotly make_subplots Dashboard
**What:** A 4-panel interactive HTML dashboard using `plotly.subplots.make_subplots`.
**When to use:** After any completed backtest run, or as a standalone `dashboard` CLI command.
**Example:**
```python
# Source: plotly.com/python/subplots/ (verified 2026-04-04)
from plotly.subplots import make_subplots
import plotly.graph_objects as go

def build_dashboard(metrics: BacktestMetrics, trade_log: pd.DataFrame) -> go.Figure:
    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=(
            "Equity Curve",
            "Drawdown",
            "Monthly P&L (cents)",
            "P&L by Category",
            "Win Rate by Category",
            "",  # empty cell
        ),
        row_heights=[0.4, 0.3, 0.3],
        vertical_spacing=0.10,
    )
    # Equity curve — row 1, col 1
    fig.add_trace(
        go.Scatter(x=metrics.equity_curve.index,
                   y=metrics.equity_curve.values,
                   name="Equity"),
        row=1, col=1,
    )
    fig.write_html("dashboard.html")
    return fig
```

### Pattern 4: Rich Strategy Comparison Table
**What:** For the `compare` CLI command, run N strategies and print a metrics table where each column is one strategy.
**When to use:** `kalshi-backtest compare` command.
**Example:**
```python
# Source: rich.readthedocs.io/en/stable/tables.html (verified via project use in validator.py)
from rich.table import Table
from rich.console import Console

def print_comparison_table(
    results: list[BacktestMetrics],
    console: Console,
) -> None:
    table = Table(title="Strategy Comparison", show_header=True)
    table.add_column("Metric", style="cyan")
    for m in results:
        table.add_column(m.strategy_name, justify="right")
    rows = [
        ("Total Return %", lambda m: f"{m.total_return_pct:.1f}%"),
        ("CAGR %",         lambda m: f"{m.cagr_pct:.1f}%"),
        ("Sharpe",         lambda m: f"{m.sharpe:.2f}"),
        ("Sortino",        lambda m: f"{m.sortino:.2f}"),
        ("Max Drawdown %", lambda m: f"{m.max_drawdown_pct:.1f}%"),
        ("Win Rate %",     lambda m: f"{m.win_rate_pct:.1f}%"),
        ("Profit Factor",  lambda m: f"{m.profit_factor:.2f}"),
        ("Total Trades",   lambda m: str(m.total_trades)),
    ]
    for label, fmt in rows:
        table.add_row(label, *[fmt(m) for m in results])
    console.print(table)
```

### Pattern 5: Per-Category Breakdown
**What:** Group the `trade_log` DataFrame by the event category (derived from the ticker prefix) and compute win rate and aggregate P&L per category.
**When to use:** Displayed in the Plotly dashboard and optionally in the Rich terminal summary.
**Example:**
```python
# Source: FEATURES.md — per-category performance breakdown
def _extract_category(ticker: str) -> str:
    """Extract series prefix from Kalshi ticker (e.g. 'KXBTC-241231-B60000' → 'KXBTC')."""
    return ticker.split("-")[0]

def compute_category_breakdown(trade_log: pd.DataFrame) -> pd.DataFrame:
    """Group trade log by ticker prefix; return win rate and net P&L per category."""
    if trade_log.empty:
        return pd.DataFrame(columns=["category", "trades", "win_rate_pct", "net_pnl_cents"])
    df = trade_log.copy()
    df["category"] = df["ticker"].map(_extract_category)
    df["win"] = df["pnl_cents"] > 0
    grouped = df.groupby("category").agg(
        trades=("pnl_cents", "count"),
        win_rate_pct=("win", lambda x: round(100 * x.mean(), 1)),
        net_pnl_cents=("pnl_cents", "sum"),
    ).reset_index()
    return grouped
```

### Anti-Patterns to Avoid
- **Re-running quantstats on every render:** Compute `BacktestMetrics` once; pass the frozen object to all consumers. quantstats is slow on large Series.
- **Using quantstats HTML tearsheet directly:** `qs.reports.html()` produces matplotlib-based output with a hardcoded layout; it won't match the Plotly-based interactive dashboard. Use individual `qs.stats.*` functions instead.
- **Calling `qs.stats.sharpe()` on un-filled sparse Series:** If the daily_pnl has gaps (only trade exit days), annualization will be wrong. Always fill non-trade days with 0.0 before passing to quantstats.
- **Mutating BacktestResult:** BacktestResult is frozen. Metrics layer never modifies it.
- **Embedding the starting capital constant deep in functions:** Define `STARTING_CAPITAL_CENTS` as a module-level constant so callers can override it for different portfolio sizes.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sharpe / Sortino / CAGR / max drawdown | Custom numpy formulas | `quantstats.stats.sharpe()`, `.sortino()`, `.cagr()`, `.max_drawdown()` | Edge cases: annualization periods, compounding, risk-free rate subtraction — quantstats handles all of these correctly |
| Win rate / profit factor | Manual groupby sums | `quantstats.stats.win_rate()`, `.profit_factor()` | Handles zero-trade edge case; consistent with tearsheet output |
| Interactive HTML output | Manual HTML templating | `plotly_fig.write_html(output_path)` | Single-call produces fully self-contained interactive HTML with embedded JS |
| Monthly returns heatmap | Custom calendar grid | `plotly.express.imshow` over a pivot table or `quantstats.plots.monthly_returns` | Calendar-grid heatmap is non-trivial to implement correctly; standard output looks professional |
| CSV export | Custom file writer | `trade_log_df.to_csv(path, index=False)` | One-liner; pandas handles quoting, encoding, and newline edge cases |

**Key insight:** quantstats functions accept a `pd.Series` with a `DatetimeIndex` and produce a scalar. The only custom code needed is the cents-to-fraction conversion and the sparse-day fill.

---

## Common Pitfalls

### Pitfall 1: quantstats Receives Integer Cents (Not Fractions)
**What goes wrong:** If `daily_pnl` (integer cents) is passed directly to `qs.stats.sharpe()`, the library interprets values like `+5` as a +500% daily return. The resulting Sharpe ratio will be astronomically large and meaningless.
**Why it happens:** quantstats assumes fractional returns — values between roughly -1.0 and +1.0. There is no type error at runtime.
**How to avoid:** Always pass through `_to_fractional_returns()` before any quantstats call. Assert that the converted Series has no values outside `[-1.0, 1.0]` before proceeding (warn if exceeded — Kalshi binary contracts can have outsized daily moves, but anything > 100% daily gain signals a bug).
**Warning signs:** Sharpe > 10 or CAGR > 1000% in test output.

### Pitfall 2: quantstats `periods=252` on Sparse Prediction Market Data
**What goes wrong:** If the trade log has only 15 entries spread over 90 calendar days, the daily_pnl Series has 15 non-zero dates. quantstats counts only those 15 points and annualizes them as if the strategy traded 15 days per year, producing an inflated CAGR.
**Why it happens:** quantstats uses `len(returns)` to determine the number of observation periods for annualization.
**How to avoid:** Reindex the daily_pnl Series over the full calendar range (`start_date` to `end_date`) with `fill_value=0` before conversion. This makes every non-trade day show as 0% return, giving quantstats the correct denominator.
**Warning signs:** CAGR value does not match manual calculation of `(1 + total_return)^(365/days_in_window) - 1`.

### Pitfall 3: Empty BacktestResult (No Trades)
**What goes wrong:** When the strategy generates zero fills (e.g., a stub strategy or no matching markets), `trade_log` is an empty DataFrame and `daily_pnl` is an empty Series. Passing an empty Series to quantstats raises a `ZeroDivisionError` or returns `NaN`.
**Why it happens:** quantstats does not gracefully handle empty input for all metrics.
**How to avoid:** Guard at the top of `MetricsCalculator.compute()`: if `len(result.trade_log) == 0`, return a `BacktestMetrics` with all scalar metrics set to 0.0 and `sample_size_warning=True`.
**Warning signs:** `ZeroDivisionError` or `NaN` values appearing in metric output during test runs.

### Pitfall 4: Sample Size Warning Fires on Wrong Threshold
**What goes wrong:** The spec says N<30 settled contracts. But `BacktestResult.settled_contracts` counts individual contracts (e.g., 50 contracts settled across only 10 markets). Using contract count instead of settled market count can mask low-sample results.
**Why it happens:** Ambiguity between "contracts" (position size) and "events/markets".
**How to avoid:** For the MET-07 warning, count distinct tickers in `trade_log` where `exit_reason == 'settlement'` — not the sum of the `contracts` column. The warning caption should say "N=X distinct settled markets" not "N=X contracts".
**Warning signs:** Strategy with 2 contracts per market * 50 markets = 100 settled contracts, but the warning never fires.

### Pitfall 5: plotly write_html with Large Trade Logs
**What goes wrong:** If the backtest has thousands of trades, embedding all trade marker data in the HTML produces a 50MB+ file that browsers struggle to open.
**Why it happens:** `fig.write_html()` embeds all data inline as JSON.
**How to avoid:** Limit trade markers on the equity curve to the top-N trades by `abs(pnl_cents)` (default: 200 most significant trades). Use `full_html=True, include_plotlyjs='cdn'` to use a CDN-hosted Plotly bundle instead of inlining the 3MB Plotly JS.
**Warning signs:** dashboard.html file size exceeds 5MB.

### Pitfall 6: Category Extraction from Tickers
**What goes wrong:** Kalshi tickers like `KXBTC-241231-B60000` have a dash-delimited structure, but not all series tickers follow this format. Splitting on `-` and taking index 0 works for most but may produce misleading category names.
**Why it happens:** Kalshi ticker format is not formally documented as a parsing contract.
**How to avoid:** Use the `series_ticker` from the markets table (available via `MarketRepository`) rather than parsing the contract ticker. The `trade_log` only has `ticker` (contract ticker) but the dashboard builder can JOIN against the DuckDB markets table to get `series_ticker`.
**Warning signs:** All trades grouped under a single category like "KXBTC" when there are many distinct event types.

---

## Code Examples

### Compute All Core Metrics from BacktestResult

```python
# Source: quantstats README + verified function signatures (github.com/ranaroussi/quantstats)
import quantstats as qs

def compute(result: BacktestResult) -> BacktestMetrics:
    # Guard: no trades
    if result.trade_log.empty:
        return BacktestMetrics(
            run_id=result.run_id,
            strategy_name=result.strategy_name,
            # ... all scalars = 0.0
            sample_size_warning=True,
        )

    returns = _to_fractional_returns(result.daily_pnl)

    sharpe      = float(qs.stats.sharpe(returns, periods=252))
    sortino     = float(qs.stats.sortino(returns, periods=252))
    cagr        = float(qs.stats.cagr(returns, periods=252)) * 100      # as pct
    max_dd      = float(qs.stats.max_drawdown(returns)) * 100           # as pct
    win_rate    = float(qs.stats.win_rate(returns)) * 100               # as pct
    profit_fac  = float(qs.stats.profit_factor(returns))

    total_return_pct = float(returns.add(1).prod() - 1) * 100

    sample_warning = _count_settled_markets(result.trade_log) < 30

    equity_curve = _build_equity_curve(result.daily_pnl)

    return BacktestMetrics(
        run_id=result.run_id,
        strategy_name=result.strategy_name,
        sharpe=sharpe,
        sortino=sortino,
        cagr_pct=cagr,
        max_drawdown_pct=max_dd,
        win_rate_pct=win_rate,
        profit_factor=profit_fac,
        total_return_pct=total_return_pct,
        avg_trade_pnl_cents=result.total_pnl_cents / len(result.trade_log),
        total_trades=len(result.trade_log),
        settled_contracts=result.settled_contracts,
        sample_size_warning=sample_warning,
        equity_curve=equity_curve,
        daily_returns=returns,
    )
```

### Trade Log CSV Export

```python
# Source: pandas docs — to_csv is the standard approach
def export_trade_log(trade_log: pd.DataFrame, output_path: str) -> None:
    """Write trade log to CSV. Converts cent values to dollars for readability."""
    if trade_log.empty:
        return
    df = trade_log.copy()
    df["pnl_usd"]  = df["pnl_cents"] / 100
    df["fee_usd"]  = df["fee_cents"] / 100
    df["entry_price_pct"] = df["entry_price"]  # already in cents [0-100]
    df["exit_price_pct"]  = df["exit_price"]
    df.to_csv(output_path, index=False)
```

### Plotly HTML Write Pattern

```python
# Source: plotly.com/python/subplots/ + financial-charts docs
from plotly.subplots import make_subplots
import plotly.graph_objects as go

fig.write_html(
    output_path,
    full_html=True,
    include_plotlyjs="cdn",   # ~3MB inline JS saved by using CDN
)
```

### Sample Size Warning Check (Distinct Markets, Not Contract Count)

```python
def _count_settled_markets(trade_log: pd.DataFrame) -> int:
    """Count distinct tickers where exit_reason == 'settlement'.

    This is the correct N for sample size warnings — not the sum of
    the 'contracts' column which measures position size, not event count.
    """
    if trade_log.empty:
        return 0
    settled = trade_log[trade_log["exit_reason"] == "settlement"]
    return settled["ticker"].nunique()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pyfolio (Quantopian) | quantstats | 2021 (pyfolio abandoned) | quantstats is the active maintained fork; API is largely compatible |
| Matplotlib static PNGs | Plotly interactive HTML | ~2019 onwards | Single self-contained HTML file replaces multiple static image files |
| pandas-based custom Sharpe | quantstats.stats.sharpe() | Ongoing | Correct annualization, risk-free rate, and edge case handling |

**Deprecated/outdated:**
- `pyfolio`: Last meaningful commit 2021. Do not use — quantstats is the direct successor.
- `qs.reports.html()` for dashboard generation: This generates a matplotlib-based tearsheet, not a Plotly interactive. Useful for quick tearsheets but conflicts with the Plotly dashboard requirement.

---

## Open Questions

1. **Starting capital for fractional return conversion**
   - What we know: The engine tracks P&L in cents but has no explicit "portfolio value" concept; positions are sized by contracts, not by portfolio percentage.
   - What's unclear: What starting capital assumption gives the most meaningful Sharpe/CAGR for a prediction market strategy?
   - Recommendation: Default to `STARTING_CAPITAL_CENTS = 10_000` ($100) and make it a configurable constant. Document the assumption prominently in the output. A future phase can introduce proper portfolio-level sizing.

2. **Series ticker for per-category breakdown**
   - What we know: `trade_log` has `ticker` (contract-level) but not `series_ticker` (the category label). The markets table in DuckDB has `series_ticker`.
   - What's unclear: Should the dashboard builder accept a `duckdb.DuckDBPyConnection` to look up series_tickers, or should BacktestResult be extended to include the series_ticker?
   - Recommendation: Accept an optional `Dict[str, str]` (ticker → series_ticker) mapping as an argument to `build_dashboard()`. BacktestRunner can populate it from the markets list it already loads. This avoids a live DB dependency in the dashboard builder and keeps it testable.

3. **Drawdown Series for Plotly panel**
   - What we know: quantstats provides `qs.stats.to_drawdown_series(returns)` which returns a Series of drawdown values.
   - What's unclear: Whether the Plotly drawdown panel should show percentage drawdown or dollar drawdown.
   - Recommendation: Show percentage drawdown — consistent with quantstats output and investor convention.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | Runtime | ✓ | 3.13.5 (uv venv) | — |
| pandas | Data manipulation | ✓ | 3.0.2 (in pyproject.toml) | — |
| numpy | Vectorized ops | ✓ | 2.4.4 (in pyproject.toml) | — |
| rich | Terminal tables | ✓ | 14.0+ (in pyproject.toml) | — |
| plotly | Dashboard | ✓ (system 6.3.1) | 6.3.1 — NOT in pyproject.toml yet | Add `plotly>=5.0` to pyproject.toml |
| quantstats | Portfolio metrics | ✗ (not installed) | 0.0.81 on PyPI | None — must add to pyproject.toml |
| pytest | Testing | ✓ | 9.0.2 (dev dep) | — |

**Missing dependencies with no fallback:**
- `quantstats` — required for MET-01. Must be added: `uv add quantstats`

**Missing dependencies with fallback:**
- `plotly` — available on system (6.3.1) but not declared in pyproject.toml. Must add: `uv add plotly` so it is reproducible in CI and other environments.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_metrics*.py -x -q` |
| Full suite command | `uv run pytest --cov=kalshi_backtest --cov-report=term-missing -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MET-01 | Core metrics computed correctly from known BacktestResult | unit | `uv run pytest tests/test_metrics_calculator.py -x` | ❌ Wave 0 |
| MET-01 | Sample size warning fires when distinct settled markets < 30 | unit | `uv run pytest tests/test_metrics_calculator.py::test_sample_warning -x` | ❌ Wave 0 |
| MET-01 | Empty BacktestResult returns zero-metrics without error | unit | `uv run pytest tests/test_metrics_calculator.py::test_empty_result -x` | ❌ Wave 0 |
| MET-02 | Trade log CSV export has correct columns and dollar values | unit | `uv run pytest tests/test_trade_log.py -x` | ❌ Wave 0 |
| MET-03 | Equity curve trace is present in Plotly figure | unit | `uv run pytest tests/test_dashboard.py::test_equity_curve_trace -x` | ❌ Wave 0 |
| MET-05 | Comparison table renders without error for N strategies | unit | `uv run pytest tests/test_cli.py::test_compare_command -x` | ❌ Wave 0 |
| MET-06 | Dashboard HTML written to disk; file is non-empty | unit | `uv run pytest tests/test_dashboard.py::test_write_html -x` | ❌ Wave 0 |
| MET-06 | Per-category breakdown groups by series prefix correctly | unit | `uv run pytest tests/test_dashboard.py::test_category_breakdown -x` | ❌ Wave 0 |
| MET-07 | Warning present in BacktestMetrics when N<30 settled markets | unit | (covered by MET-01 test) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_metrics*.py tests/test_dashboard.py tests/test_trade_log.py -x -q`
- **Per wave merge:** `uv run pytest --cov=kalshi_backtest --cov-report=term-missing -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_metrics_calculator.py` — covers MET-01, MET-07
- [ ] `tests/test_trade_log.py` — covers MET-02
- [ ] `tests/test_dashboard.py` — covers MET-03, MET-06

*(Existing `tests/conftest.py` already provides `duckdb_con` and `load_fixture` — reusable. New fixtures needed: `minimal_backtest_result()` with known pnl_cents Series and trade_log DataFrame.)*

---

## Sources

### Primary (HIGH confidence)
- [github.com/ranaroussi/quantstats](https://github.com/ranaroussi/quantstats) — stats.py function signatures verified directly; version 0.0.81 confirmed as current
- [plotly.com/python/subplots](https://plotly.com/python/subplots/) — make_subplots API verified
- `kalshi-backtest/src/kalshi_backtest/simulation/runner.py` — BacktestResult contract (frozen dataclass, exact fields)
- `kalshi-backtest/src/kalshi_backtest/simulation/position_tracker.py` — to_trade_log() columns, to_daily_pnl_series() format
- `kalshi-backtest/pyproject.toml` — confirmed existing dependencies and versions

### Secondary (MEDIUM confidence)
- [plotly.com/python/financial-charts](https://plotly.com/python/financial-charts/) — verified write_html usage pattern
- [rich.readthedocs.io/en/stable/tables.html](https://rich.readthedocs.io/en/stable/tables.html) — Rich Table API, verified against existing validator.py usage in codebase
- `pip index versions quantstats` — verified 0.0.81 is latest PyPI release (2026-04-04)

### Tertiary (LOW confidence)
- Medium article on quantstats input format — describes decimal fraction requirement; consistent with source code reading but not official docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions confirmed via pip index and system Python; all libraries are locked decisions from CONTEXT.md
- Architecture: HIGH — BacktestResult contract is frozen and read directly from source; quantstats function signatures verified from GitHub source
- Pitfalls: HIGH — cents-to-fraction conversion and sparse-day fill are mathematically necessary, not speculative; verified against quantstats source
- Per-category breakdown: MEDIUM — ticker parsing from first dash segment is an implementation assumption; using series_ticker from DB is safer but adds a dependency

**Research date:** 2026-04-04
**Valid until:** 2026-05-04 (quantstats moves slowly; plotly API is stable)
