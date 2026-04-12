# Phase 5: Risk Metrics Engine - Research

**Researched:** 2026-03-29
**Domain:** Portfolio analytics, risk-adjusted return metrics, benchmark comparison
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Claude's Discretion
All implementation choices (file structure, API design, MetricsBundle schema, module layout) are discretionary.

### Deferred Ideas (OUT OF SCOPE)
None — discuss phase skipped.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RISK-01 | Compute Sharpe ratio, Sortino ratio, max drawdown, and Calmar ratio | quantstats-lumi `qs.stats.sharpe(periods=252)`, `qs.stats.sortino(periods=252)`, `qs.stats.max_drawdown()`, `qs.stats.calmar(periods=252)` — all accept a daily returns Series |
| RISK-02 | Compute hit rate, win/loss ratio, and portfolio turnover | `qs.stats.win_rate()`, `qs.stats.win_loss_ratio()` for hit rate and win/loss; turnover must be computed from `PortfolioResult.trade_log` (no qs built-in) |
| RISK-03 | Compare strategy returns against SPY and Russell 2000 benchmarks | `qs.stats.greeks(returns, benchmark, periods=252)` returns alpha and beta; benchmark Series must be synthetic in tests (no network access) |
| RISK-04 | Compute rolling Sharpe and rolling drawdown at configurable windows (default 252 days) | `qs.stats.rolling_sharpe(periods_per_year=252, rolling_period=window)` for rolling Sharpe; rolling drawdown requires custom pandas implementation (no qs built-in `rolling_drawdown`) |
</phase_requirements>

---

## Summary

Phase 5 builds a `MetricsBundle` by computing the full institutional risk metric suite from a `PortfolioResult`. The `PortfolioResult.net_returns` is a `pd.Series` with a `DatetimeIndex` — the exact format quantstats-lumi expects. All required metrics are computable with quantstats-lumi plus a small amount of custom pandas for metrics the library does not provide (rolling drawdown, portfolio turnover).

The key pitfall is quantstats-lumi's default `periods=365` (calendar days). This project uses daily trading bars, so every quantstats function call must explicitly pass `periods=252`. Using the default produces Sharpe/Sortino ratios that are ~20% higher than the correct values, which would mislead investors.

There is no `rolling_drawdown` function in quantstats-lumi. Rolling drawdown must be implemented with pandas: compute the cumulative drawdown series, then apply `.rolling(window).min()`. Similarly, portfolio `turnover` is not in quantstats-lumi and must be derived from the `PortfolioResult.trade_log` (already produced by the simulator in Phase 4).

**Primary recommendation:** Install `quantstats-lumi>=1.1.3` into the backtest venv, build a `MetricsEngine` class in `src/fund_backtest/metrics/`, expose a `MetricsBundle` Pydantic model, and implement a `MetricsConfig` for the rolling window default. Follow the established Phase 4 pattern (types.py, engine.py, config).

---

## Project Constraints (from CLAUDE.md)

The following directives apply to all work in this project:

- **Immutability:** Return new objects, never mutate inputs. `MetricsBundle` must be frozen (`model_config = {"frozen": True}` or `@dataclass(frozen=True)`).
- **File size:** 200–400 lines typical, 800 max. Split metrics, types, and config into separate files.
- **Functions:** Target <50 lines per function. Private helpers for each metric category.
- **Naming:** snake_case files, PascalCase classes, UPPER_CASE constants.
- **Type hints:** Required on all params and return values. `from __future__ import annotations` at top.
- **Docstrings:** Google-style on every public function/class and module.
- **Error handling:** Return sensible defaults on error; log with structlog. Fail fast on invalid input (raise `ValueError` with clear message).
- **Constants:** `_TRADING_DAYS_PER_YEAR: int = 252` — must not be hardcoded inline.
- **Logging:** `logger = structlog.get_logger(__name__)`, bind with `.bind(component="metrics_engine")`.
- **Tests:** TDD (RED first, GREEN second), 80%+ coverage, no network or DB access in unit tests.
- **Linting:** `ruff check src/ tests/ --fix` and `ruff format src/ tests/` before marking work complete.
- **Config pattern:** `MetricsConfig(BaseModel)` with `load_metrics_config(config_path)` factory — mirrors `CostConfig`/`load_cost_config()` pattern from Phase 4.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| quantstats-lumi | 1.1.3 | Sharpe, Sortino, Calmar, max drawdown, CAGR, hit rate, win/loss, alpha, beta, rolling Sharpe | Active fork of quantstats; accepts plain `pd.Series` of returns; all required v1 metrics present except rolling drawdown and turnover |
| pandas | 3.0.1 | Rolling drawdown computation, turnover from trade_log | Already installed; rolling window operations are first-class |
| numpy | 2.4.3 | Numerical operations | Already installed; required by quantstats-lumi |
| pydantic | 2.12.5 | `MetricsBundle` (frozen model), `MetricsConfig` | Already installed; established project pattern |
| structlog | 25.5.0 | Structured logging | Already installed; project standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| seaborn | (transitive) | quantstats-lumi dependency for report generation | Installed automatically with quantstats-lumi; not used directly in Phase 5 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| quantstats-lumi | pyfolio-reloaded | pyfolio is Zipline-centric; requires a specific TearsheetBacktest object format, not a plain returns Series |
| quantstats-lumi | custom numpy formulas | More code to maintain; quantstats-lumi already implements edge cases (annualization, RF subtraction, compounding) correctly |
| quantstats-lumi | empyrical | empyrical is less maintained; quantstats-lumi has more metrics out of the box |

**Installation (into backtest venv):**
```bash
cd /Users/maxzou/Documents/projects/AI\ Hedgefund/backtest
uv add quantstats-lumi>=1.1.3
```

quantstats-lumi 1.1.3 is the current PyPI release (verified 2026-03-29). Its dependencies (seaborn, matplotlib, scipy) will be added transitively.

**Verify:**
```bash
.venv/bin/python -c "import quantstats_lumi as qs; print(qs.__version__)"
```

---

## Architecture Patterns

### Recommended Project Structure
```
src/fund_backtest/
├── metrics/
│   ├── __init__.py          # empty barrel (explicit imports only)
│   ├── types.py             # MetricsBundle, RollingMetrics
│   └── engine.py            # MetricsEngine class
└── config.py                # MetricsConfig + load_metrics_config() added here

tests/unit/
├── test_metrics_types.py    # RED state: MetricsBundle schema, frozen invariant
└── test_metrics_engine.py   # RED state: all metric computation behaviors
```

**No new top-level config file:** Following the pattern of `CostConfig` in `config.py`, add `MetricsConfig` and `load_metrics_config()` to the existing `src/fund_backtest/config.py` file.

### Pattern 1: MetricsBundle — Frozen Pydantic Model
**What:** A Pydantic BaseModel with `frozen=True` holding all scalar metrics and rolling Series.
**When to use:** Output type of `MetricsEngine.compute()`.

```python
# Source: established project pattern from simulator/types.py
class MetricsBundle(BaseModel):
    """Full institutional metric suite computed from a PortfolioResult."""

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    # Scalar metrics (RISK-01)
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float       # negative fraction, e.g. -0.25
    cagr: float               # annualized, e.g. 0.15

    # Trade metrics (RISK-02)
    hit_rate: float           # fraction of profitable days, e.g. 0.54
    win_loss_ratio: float     # avg win / avg loss magnitude
    annual_turnover: float    # sum(abs(weight_changes)) / n_days * 252

    # Benchmark metrics (RISK-03)
    alpha: float              # annualized alpha vs benchmark
    beta: float               # beta vs benchmark

    # Rolling Series (RISK-04)
    rolling_sharpe: pd.Series         # DatetimeIndex, NaN before window fills
    rolling_drawdown: pd.Series       # DatetimeIndex, NaN before window fills
```

### Pattern 2: MetricsEngine — Single Public Method
**What:** Stateless class with one public `compute()` method. Internal helpers for each metric family.
**When to use:** Called by Phase 6 dashboard and Phase 7 tearsheet.

```python
# Source: established project pattern from simulator/engine.py
class MetricsEngine:
    def __init__(self, config: MetricsConfig | None = None) -> None:
        self._config = config or MetricsConfig()
        self._log = logger.bind(component="metrics_engine")

    def compute(
        self,
        result: PortfolioResult,
        benchmark: pd.Series | None = None,
    ) -> MetricsBundle:
        """Compute full MetricsBundle from a PortfolioResult.

        Args:
            result: PortfolioResult from PortfolioSimulator.simulate().
            benchmark: Optional daily returns Series aligned to result.net_returns.
                       If None, alpha and beta are set to 0.0.
        Returns:
            Frozen MetricsBundle.
        """
```

### Pattern 3: MetricsConfig — YAML-loadable Config
**What:** Pydantic BaseModel with defaults, loadable from `config/metrics.yaml`.
**When to use:** Controls rolling window size and annualization period.

```python
# Source: established project pattern from config.py (SignalAdapterConfig, CostConfig)
class MetricsConfig(BaseModel):
    """Metrics engine configuration."""

    rolling_window: int = 252
    """Rolling window in trading days for rolling_sharpe and rolling_drawdown."""

    periods_per_year: int = 252
    """Trading days per year for annualization. Use 252, NOT 365."""

    risk_free_rate: float = 0.0
    """Daily risk-free rate (0.0 = no RF subtraction for simplicity)."""
```

### Pattern 4: periods=252 Enforcement
**What:** Every quantstats function call must pass `periods=252` explicitly.
**When to use:** Always — quantstats-lumi defaults to `periods=365`, producing inflated Sharpe/Sortino by ~20%.

```python
# Source: verified locally 2026-03-29 — sqrt(365)/sqrt(252) = 1.2035
import quantstats_lumi as qs

# CORRECT
sharpe = qs.stats.sharpe(returns, rf=rf, periods=periods_per_year)

# WRONG — do not use default
sharpe = qs.stats.sharpe(returns)  # uses periods=365, wrong for trading data
```

### Pattern 5: Rolling Drawdown (custom — no qs built-in)
**What:** Compute drawdown series, then apply rolling min.
**Verified:** Working implementation tested locally.

```python
# Source: verified locally 2026-03-29
def _rolling_drawdown(returns: pd.Series, window: int) -> pd.Series:
    """Rolling maximum drawdown over a sliding window."""
    prices = (1 + returns).cumprod()
    drawdown = prices / prices.expanding().max() - 1
    return drawdown.rolling(window).min()
```

### Pattern 6: Turnover from trade_log (custom — no qs built-in)
**What:** Sum absolute weight changes per day from the existing trade_log, average, annualize.
**Verified:** Working implementation tested locally.

```python
# Source: verified locally 2026-03-29
def _portfolio_turnover(result: PortfolioResult) -> float:
    """Annualized portfolio turnover from the simulator trade_log."""
    if result.trade_log.empty:
        return 0.0
    tl = result.trade_log
    daily_turnover = tl.groupby("date")["weight_change"].apply(
        lambda x: x.abs().sum()
    )
    # Reindex to all trading days to include zero-turnover days in the average
    all_dates = result.net_returns.index
    avg_daily = daily_turnover.reindex(all_dates).fillna(0.0).mean()
    return avg_daily * _TRADING_DAYS_PER_YEAR
```

### Anti-Patterns to Avoid
- **Using `periods=365` (the qs default):** Inflates Sharpe/Sortino by 20.35% — wrong for daily trading bar data. Always pass `periods=252`.
- **Computing turnover from positions diff instead of trade_log:** The trade_log from Phase 4 already applies the `_TRADE_THRESHOLD=1e-8` filter to ignore float noise. Re-diffing positions would include noise trades.
- **Fetching live benchmark data in tests:** Benchmark data for tests must come from synthetic Series. No `yf.download()` calls in `metrics/`.
- **Storing rolling Series in a frozen Pydantic model without `arbitrary_types_allowed=True`:** Pydantic rejects `pd.Series` fields by default. Set `model_config = {"frozen": True, "arbitrary_types_allowed": True}`.
- **Calling `qs.stats.max_drawdown()` with a returns Series directly:** The function internally calls `_prepare_prices()` which converts returns to a price index — this is fine. But verify the return is a negative float (e.g. `-0.25`), not a positive one.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sharpe ratio | Custom `mean/std * sqrt(252)` | `qs.stats.sharpe(returns, periods=252)` | qs handles RF subtraction, edge cases, zero-std returns gracefully |
| Sortino ratio | Custom downside-deviation formula | `qs.stats.sortino(returns, periods=252)` | qs computes downside deviation correctly (only negative returns in denominator) |
| Calmar ratio | Custom `CAGR / max_drawdown` | `qs.stats.calmar(returns, periods=252)` | qs handles sign conventions and zero-drawdown edge cases |
| CAGR | Custom `(1+r).cumprod()[-1]^(252/n) - 1` | `qs.stats.cagr(returns, periods=252)` | qs uses actual calendar length, not assumed 252/yr |
| Alpha/Beta | Custom OLS regression | `qs.stats.greeks(returns, benchmark, periods=252)` | qs covariance matrix approach; handles alignment and NaN fill |
| Win rate | Custom `(returns > 0).mean()` | `qs.stats.win_rate(returns)` | qs handles `prepare_returns` normalization edge cases |
| Win/loss ratio | Custom `avg_win / avg_loss` | `qs.stats.win_loss_ratio(returns)` | qs handles zero-loss edge case gracefully |
| Rolling Sharpe | Custom implementation | `qs.stats.rolling_sharpe(returns, rolling_period=window, periods_per_year=252)` | qs handles insufficient-window leading NaN correctly |

**Custom implementations required (not in qs):**
- `rolling_drawdown` — use `drawdown_series.rolling(window).min()` pattern (see Pattern 5 above)
- `annual_turnover` — use `trade_log` pattern (see Pattern 6 above)

**Key insight:** quantstats-lumi covers 90% of required metrics from a plain `pd.Series`. The 10% custom work (rolling drawdown, turnover) is pure pandas and straightforward.

---

## Common Pitfalls

### Pitfall 1: periods=365 Default Inflates Metrics
**What goes wrong:** Calling `qs.stats.sharpe(returns)` without `periods=252` computes `sqrt(365)` annualization. On daily trading data (252 bars/yr), this inflates Sharpe by ~20.35%. Investor presentations with inflated metrics create credibility risk.
**Why it happens:** quantstats was originally designed for calendar-day return data (crypto markets are 365 days/yr). The default was never changed when it became popular for equity backtesting.
**How to avoid:** Pass `periods=self._config.periods_per_year` to every qs function. Define `_TRADING_DAYS_PER_YEAR: int = 252` as a module constant. Never let the default flow through.
**Warning signs:** Sharpe > 3 on a strategy with modest signals — recalculate manually and check whether `sqrt(252)` vs `sqrt(365)` explains the gap.

### Pitfall 2: No rolling_drawdown in quantstats-lumi
**What goes wrong:** Searching quantstats-lumi API for `rolling_drawdown` and assuming it exists because `rolling_sharpe` exists. Calling `qs.stats.rolling_drawdown()` raises `AttributeError`.
**Why it happens:** The function was never added to quantstats or its fork. `to_drawdown_series()` exists but is not windowed.
**How to avoid:** Implement `_rolling_drawdown()` helper using the verified pattern (see Pattern 5). Test it explicitly in the TDD scaffold.
**Warning signs:** Any grep for `rolling_drawdown` in the qs source returns nothing.

### Pitfall 3: max_drawdown Returns Negative Float
**What goes wrong:** Expecting `max_drawdown()` to return a positive percentage (e.g. `0.25`) but receiving `-0.25`. Displaying "Max Drawdown: -25%" in a report is acceptable; storing it as positive and then negating in the display layer creates confusion.
**Why it happens:** quantstats follows the convention that drawdown is negative (it is a loss). `max_drawdown()` returns the minimum of the drawdown series, which is always <= 0.
**How to avoid:** Document in `MetricsBundle` that `max_drawdown` is a negative float. Accept the negative convention throughout — do not flip the sign at storage time. Let the display layer render it as "25%" with appropriate labeling.
**Warning signs:** Tests comparing `max_drawdown < 0` are passing — that is correct. Tests comparing `max_drawdown > 0` would indicate the convention was accidentally flipped.

### Pitfall 4: Benchmark Alignment for Tests
**What goes wrong:** Writing a test that calls `qs.stats.greeks(strategy_returns, benchmark)` where benchmark comes from `yf.download("SPY", ...)`. This introduces network access in unit tests, making them slow and non-deterministic.
**Why it happens:** The natural instinct is to test with real SPY data to get "realistic" results.
**How to avoid:** Use synthetic benchmark Series in tests — e.g., `pd.Series(np.random.randn(n) * 0.01, index=returns.index)`. Pass a `benchmark: pd.Series | None = None` parameter to `MetricsEngine.compute()` and set `alpha=0.0, beta=0.0` when None. RISK-04 success criteria explicitly states "no DB or network access needed."
**Warning signs:** Test duration > 2 seconds for any unit test — almost certainly a network call.

### Pitfall 5: Pydantic Rejects pd.Series in Frozen Model
**What goes wrong:** Defining `rolling_sharpe: pd.Series` in a Pydantic BaseModel without `arbitrary_types_allowed=True`. Pydantic raises `PydanticUserError` at class definition time.
**Why it happens:** Pydantic v2 does not know how to validate `pd.Series` by default.
**How to avoid:** Set `model_config = {"frozen": True, "arbitrary_types_allowed": True}` in `MetricsBundle`. Matches the `PortfolioResult` pattern already in the codebase (`simulator/types.py` line 81).
**Warning signs:** Import of `types.py` raises `PydanticUserError` before any test runs.

---

## Code Examples

Verified patterns from official sources:

### Sharpe / Sortino / Calmar / CAGR
```python
# Source: quantstats-lumi GitHub verified 2026-03-29, periods=252 enforcement required
import quantstats_lumi as qs

returns: pd.Series  # PortfolioResult.net_returns

sharpe = qs.stats.sharpe(returns, rf=0.0, periods=252)
sortino = qs.stats.sortino(returns, rf=0.0, periods=252)
calmar = qs.stats.calmar(returns, periods=252)
cagr = qs.stats.cagr(returns, periods=252)
max_dd = qs.stats.max_drawdown(returns)  # negative float
```

### Hit Rate and Win/Loss Ratio
```python
# Source: quantstats-lumi GitHub verified 2026-03-29
hit_rate = qs.stats.win_rate(returns)         # fraction, e.g. 0.54
win_loss = qs.stats.win_loss_ratio(returns)   # float, e.g. 1.2
```

### Alpha and Beta (with benchmark)
```python
# Source: quantstats-lumi GitHub verified 2026-03-29
# greeks() returns pd.Series({"beta": ..., "alpha": ...})
greeks = qs.stats.greeks(returns, benchmark, periods=252)
beta = float(greeks["beta"])
alpha = float(greeks["alpha"])
```

### Rolling Sharpe
```python
# Source: quantstats-lumi GitHub verified 2026-03-29
# rolling_period must be int; periods_per_year=252 (not default 365)
rolling_sharpe = qs.stats.rolling_sharpe(
    returns,
    rf=0.0,
    rolling_period=window,       # e.g. 252
    periods_per_year=252,        # CRITICAL: not the default 365
)
```

### Rolling Drawdown (custom pandas)
```python
# Source: verified locally 2026-03-29 using backtest venv Python
def _rolling_drawdown(returns: pd.Series, window: int) -> pd.Series:
    prices = (1 + returns).cumprod()
    drawdown = prices / prices.expanding().max() - 1
    return drawdown.rolling(window).min()
```

### Annual Turnover from trade_log
```python
# Source: verified locally 2026-03-29 using backtest venv Python
def _annual_turnover(result: PortfolioResult) -> float:
    if result.trade_log.empty:
        return 0.0
    daily = (
        result.trade_log
        .groupby("date")["weight_change"]
        .apply(lambda x: x.abs().sum())
        .reindex(result.net_returns.index)
        .fillna(0.0)
    )
    return daily.mean() * _TRADING_DAYS_PER_YEAR
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `quantstats` (original) | `quantstats-lumi` fork | 2023 | Active maintenance, bug fixes for pandas 3.x compatibility |
| `pyfolio` for portfolio analytics | `quantstats-lumi` | ~2022 | Zipline-free; accepts plain returns Series |
| Manual numpy Sharpe formula | `qs.stats.sharpe(periods=252)` | N/A | Edge cases handled (zero std, NaN handling) |

**Deprecated/outdated:**
- Original `quantstats` (0.0.81): Has maintenance gaps; open PRs neglected. Use `quantstats-lumi` fork.
- `pyfolio`: Tightly coupled to Zipline return format. Not suitable for this project's plain returns Series.

---

## Open Questions

1. **CAGR computation: actual calendar vs assumed 252/yr**
   - What we know: `qs.stats.cagr(returns, periods=252)` uses `periods` parameter for annualization
   - What's unclear: Whether `cagr()` uses actual calendar days (from index) or `periods` argument for total length
   - Recommendation: Verify with a hand-calculated fixture in tests. If `qs.stats.cagr()` behaves unexpectedly, fall back to `(1+returns).cumprod().iloc[-1] ** (252/len(returns)) - 1`.

2. **Benchmark input format for `greeks()`**
   - What we know: `greeks()` calls `_utils._prepare_benchmark(benchmark, returns.index)` internally
   - What's unclear: Whether the benchmark Series must be pre-aligned to `returns.index` or whether `_prepare_benchmark` handles alignment
   - Recommendation: Pre-align the benchmark to `returns.index` before passing (reindex + fillna(0)). Safer than relying on internal alignment behavior.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | Yes | 3.12.11 | — |
| pandas | Metrics computation | Yes (in venv) | 3.0.1 | — |
| numpy | Metrics computation | Yes (in venv) | 2.4.3 | — |
| pydantic | MetricsBundle model | Yes (in venv) | 2.12.5 | — |
| structlog | Logging | Yes (in venv) | 25.5.0 | — |
| quantstats-lumi | Sharpe/Sortino/etc. | NOT in venv | 1.1.3 available on PyPI | Must install before implementation (`uv add quantstats-lumi>=1.1.3`) |
| pytest | Testing | Yes (in venv) | 9.0.2 | — |

**Missing dependencies with no fallback:**
- `quantstats-lumi` must be installed via `uv add quantstats-lumi>=1.1.3` as a Wave 0 task.

**Missing dependencies with fallback:**
- None.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `backtest/pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `cd backtest && .venv/bin/pytest tests/unit/test_metrics_engine.py tests/unit/test_metrics_types.py -x` |
| Full suite command | `cd backtest && .venv/bin/pytest tests/unit/ -x --cov=src/fund_backtest/metrics --cov-report=term-missing` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RISK-01 | Sharpe, Sortino, Calmar, max_drawdown, CAGR from synthetic returns Series | unit | `pytest tests/unit/test_metrics_engine.py::TestScalarMetrics -x` | Wave 0 |
| RISK-02 | hit_rate, win_loss_ratio, annual_turnover from PortfolioResult | unit | `pytest tests/unit/test_metrics_engine.py::TestTradeMetrics -x` | Wave 0 |
| RISK-03 | alpha, beta vs synthetic benchmark; zero-alpha baseline; alpha=0 when benchmark=None | unit | `pytest tests/unit/test_metrics_engine.py::TestBenchmarkMetrics -x` | Wave 0 |
| RISK-04 | rolling_sharpe and rolling_drawdown at window=20 and window=252; NaN before window fills | unit | `pytest tests/unit/test_metrics_engine.py::TestRollingMetrics -x` | Wave 0 |
| RISK-01–04 | MetricsBundle is frozen (mutation raises error); arbitrary_types_allowed for pd.Series fields | unit | `pytest tests/unit/test_metrics_types.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backtest && .venv/bin/pytest tests/unit/test_metrics_engine.py tests/unit/test_metrics_types.py -x`
- **Per wave merge:** `cd backtest && .venv/bin/pytest tests/unit/ -x --cov=src/fund_backtest/metrics --cov-report=term-missing`
- **Phase gate:** Full suite green (`tests/unit/` + `tests/integration/`) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_metrics_types.py` — covers MetricsBundle schema, frozen invariant (RISK-01 to RISK-04)
- [ ] `tests/unit/test_metrics_engine.py` — covers all 4 requirement groups (RED state before implementation)

*(No new conftest.py needed — existing `tests/conftest.py` covers shared fixtures)*

---

## Sources

### Primary (HIGH confidence)
- quantstats-lumi PyPI — v1.1.3 verified 2026-03-29 (`pip3 index versions quantstats-lumi`)
- quantstats-lumi GitHub `stats.py` — function signatures and implementations fetched 2026-03-29
- `backtest/src/fund_backtest/simulator/types.py` — PortfolioResult schema (local codebase)
- `backtest/src/fund_backtest/simulator/engine.py` — trade_log column names (local codebase)
- `backtest/src/fund_backtest/config.py` — MetricsConfig pattern reference (local codebase)
- Local verification: rolling_drawdown pattern, turnover from trade_log, periods=252 vs 365 impact — all tested in backtest venv Python 2026-03-29

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` — documents quantstats-lumi as the chosen analytics library (project decision)

### Tertiary (LOW confidence)
- None.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — quantstats-lumi version verified on PyPI; all function signatures fetched from GitHub source; key behavior (periods=252, no rolling_drawdown, no turnover) confirmed
- Architecture: HIGH — follows established Phase 4 patterns directly (config.py, types.py, engine.py)
- Pitfalls: HIGH — periods=365 default verified by local computation (1.2035x inflation factor); rolling_drawdown absence confirmed by full function list scan; Pydantic arbitrary_types pattern confirmed from existing codebase

**Research date:** 2026-03-29
**Valid until:** 2026-04-29 (quantstats-lumi minor releases unlikely to break API; verify if >30 days old)
