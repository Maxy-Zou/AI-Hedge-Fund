# Phase 6: Streamlit Dashboard - Research

**Researched:** 2026-03-29
**Domain:** Streamlit + Plotly interactive financial dashboard
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None — discuss phase was skipped. All implementation choices at Claude's discretion.

### Claude's Discretion
All implementation choices: module structure, chart library API usage, layout design, testing approach, launch mechanism.

### Deferred Ideas (OUT OF SCOPE)
None — discuss phase skipped.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RPT-01 | Interactive Streamlit dashboard displays equity curve and drawdown chart | Plotly `make_subplots` with `shared_xaxes=True`; equity curve as `go.Scatter` cumulative returns; drawdown as filled area (`fill='tozeroy'`, red); benchmark overlays via additional `go.Scatter` traces |
| RPT-02 | Dashboard displays monthly returns heatmap (calendar table) | `px.imshow()` on a pivoted DataFrame (year x month); `color_continuous_scale='RdYlGn'`; `text_auto=".1%"` for cell labels; `color_continuous_midpoint=0` to anchor red/green at zero |
| RPT-03 | Dashboard displays sector exposure breakdown | `go.Bar` (horizontal) grouped by GICS sector from `positions` DataFrame joined to `UniverseTicker.gics_sector`; sector weights summed from `PortfolioResult.positions` |
</phase_requirements>

---

## Summary

Phase 6 adds an investor-facing Streamlit dashboard (`backtest/src/fund_backtest/dashboard/`) that consumes a `MetricsBundle` and `PortfolioResult` from Phases 4 and 5. The dashboard renders four visualizations required by RPT-01 through RPT-03: an equity curve with SPY/Russell 2000 benchmark overlays, a drawdown chart with episode labels, a monthly returns heatmap, and a sector exposure bar chart.

Streamlit 1.50.0 and Plotly 6.3.1 are already installed in the system Python environment (confirmed via `python3 -c "import X; print(X.__version__)"`). They are NOT yet in the `backtest/pyproject.toml` dependencies — they must be added. The dashboard is a standalone Streamlit app launched via `streamlit run backtest/src/fund_backtest/dashboard/app.py` rather than a Typer CLI command (Streamlit's own server runtime conflicts with Typer's event loop).

The architecture follows the established phase patterns: a `dashboard/` subpackage with `app.py` as the Streamlit entry point, `charts.py` as a pure-function chart factory module, and unit tests that validate chart construction without launching a browser.

**Primary recommendation:** Use Plotly `make_subplots` for the equity+drawdown panel (shared x-axis), `px.imshow` for the monthly heatmap, and `go.Bar` for sector exposure. Keep chart construction in pure functions (`charts.py`) so they are testable without Streamlit.

---

## Standard Stack

### Core (already in backtest/pyproject.toml)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | >=3.0.1 | Data manipulation for pivots and aggregations | Already in use across all phases |
| quantstats-lumi | >=1.1.3 | Provides `MetricsBundle` data already computed | Phase 5 dependency |
| structlog | >=25.5.0 | Structured logging | Fund-wide convention |
| pydantic | >=2.12.5 | Type-safe data contracts | Fund-wide convention |

### To Add to backtest/pyproject.toml
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| streamlit | >=1.50.0 | Dashboard framework | Already installed (1.50.0 confirmed); investor-facing UI standard for Python data apps |
| plotly | >=6.3.1 | Interactive chart library | Already installed (6.3.1 confirmed); `st.plotly_chart` is the canonical Streamlit + Plotly integration |

### Confirmed Installed Versions (system Python 3.12)
```
streamlit  1.50.0  (python3 -c "import streamlit; print(streamlit.__version__)")
plotly     6.3.1   (python3 -c "import plotly; print(plotly.__version__)")
```

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `px.imshow` for heatmap | `go.Heatmap` directly | `px.imshow` is higher-level and handles DataFrame indexing automatically; `go.Heatmap` offers more manual control but requires constructing z/x/y manually |
| `st.plotly_chart` | `st.pyplot` (matplotlib) | Plotly charts are interactive (hover, zoom, pan); matplotlib is static |
| `streamlit run app.py` launch | Typer CLI command | Streamlit's own server/event loop cannot be embedded inside Typer without subprocess gymnastics |

**Installation (add to backtest/pyproject.toml):**
```toml
dependencies = [
    # ...existing deps...,
    "streamlit>=1.50.0",
    "plotly>=6.3.1",
]
```

Then: `cd backtest && uv sync`

---

## Architecture Patterns

### Recommended Module Structure
```
backtest/
  src/
    fund_backtest/
      dashboard/
        __init__.py          # empty — makes it a package
        app.py               # Streamlit entry point (st.* calls here)
        charts.py            # Pure Plotly figure factories (no st.* calls)
        demo_data.py         # Synthetic PortfolioResult + MetricsBundle for demo mode
  tests/
    unit/
      test_dashboard_charts.py  # Tests for charts.py pure functions
```

**Why separate `charts.py`:** Streamlit functions (`st.plotly_chart`, `st.metric`) require an active Streamlit session to run. By keeping Plotly figure construction in pure functions, unit tests can validate chart data/layout without importing Streamlit at all. This is the standard pattern for testable Streamlit dashboards.

### Pattern 1: Equity Curve + Drawdown (RPT-01)

**What:** Two-row subplot with shared x-axis. Row 1: cumulative return lines (strategy + benchmarks). Row 2: drawdown as a filled-to-zero negative area.

**When to use:** Any multi-panel time-series financial chart requiring synchronized x-axis panning.

```python
# Source: https://plotly.com/python/subplots/ + https://plotly.com/python/filled-area-plots/
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pandas as pd

def build_equity_drawdown_chart(
    net_returns: pd.Series,
    drawdown: pd.Series,
    benchmark_returns: dict[str, pd.Series] | None = None,
) -> go.Figure:
    """Build a two-panel equity curve + drawdown figure.

    Args:
        net_returns: Daily net return Series with DatetimeIndex.
        drawdown: Drawdown Series (values <= 0) with DatetimeIndex.
        benchmark_returns: Dict of name -> daily return Series for benchmark overlays.

    Returns:
        Plotly Figure with two subplots sharing the x-axis.
    """
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.65, 0.35],
        vertical_spacing=0.03,
    )

    # Equity curve — cumulative returns (1 + r).cumprod() - 1
    equity = (1 + net_returns).cumprod() - 1
    fig.add_trace(
        go.Scatter(x=equity.index, y=equity.values, name="Strategy",
                   line={"color": "#1f77b4", "width": 2}),
        row=1, col=1,
    )

    # Benchmark overlays
    if benchmark_returns:
        for name, bm_ret in benchmark_returns.items():
            bm_eq = (1 + bm_ret).cumprod() - 1
            fig.add_trace(
                go.Scatter(x=bm_eq.index, y=bm_eq.values, name=name,
                           line={"dash": "dash"}),
                row=1, col=1,
            )

    # Drawdown — filled area to zero (red shading)
    fig.add_trace(
        go.Scatter(
            x=drawdown.index, y=drawdown.values,
            fill="tozeroy", fillcolor="rgba(220,50,50,0.3)",
            line={"color": "rgba(220,50,50,0.8)", "width": 1},
            name="Drawdown",
        ),
        row=2, col=1,
    )

    fig.update_layout(
        title="Equity Curve & Drawdown",
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
    )
    fig.update_yaxes(tickformat=".1%", row=1, col=1, title_text="Cumulative Return")
    fig.update_yaxes(tickformat=".1%", row=2, col=1, title_text="Drawdown")
    return fig
```

**Drawdown episode labels:** Use `fig.add_annotation()` to mark the deepest point of each major episode. Identify episodes by finding contiguous segments where `drawdown < threshold` (e.g., -5%).

### Pattern 2: Monthly Returns Heatmap (RPT-02)

**What:** Calendar-style heatmap with years as rows and months as columns, colour-coded red (negative) to green (positive).

**When to use:** Standard return visualization in any investor-grade backtest report.

```python
# Source: https://plotly.com/python/heatmaps/ (px.imshow section)
import plotly.express as px
import pandas as pd

def build_monthly_heatmap(net_returns: pd.Series) -> go.Figure:
    """Build a year x month heatmap of monthly returns.

    Args:
        net_returns: Daily net return Series with DatetimeIndex.

    Returns:
        Plotly Figure with RdYlGn heatmap. color_continuous_midpoint=0
        ensures zero is the colour midpoint, not the data mean.
    """
    # Resample to monthly compound returns using "ME" (month-end, pandas 3.x)
    monthly = (1 + net_returns).resample("ME").prod() - 1

    # Pivot: index = year (int), columns = month abbreviation
    pivot = monthly.groupby(
        [monthly.index.year, monthly.index.month]
    ).first().unstack(level=1)

    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    pivot.columns = [month_labels[m - 1] for m in pivot.columns]
    pivot.index = pivot.index.astype(str)

    fig = px.imshow(
        pivot,
        labels={"x": "Month", "y": "Year", "color": "Return"},
        color_continuous_scale="RdYlGn",
        color_continuous_midpoint=0.0,  # CRITICAL: zero anchors red/green split
        text_auto=".1%",               # annotate each cell with return %
        aspect="auto",                 # fill space, not square tiles
    )
    fig.update_layout(title="Monthly Returns Heatmap")
    fig.update_coloraxes(colorbar_tickformat=".0%")
    return fig
```

**CRITICAL:** `color_continuous_midpoint=0.0` is mandatory. Without it, `px.imshow` centres the diverging colorscale on the mean return — positive months appear red when all returns are positive.

### Pattern 3: Sector Exposure Chart (RPT-03)

**What:** Horizontal bar chart showing average absolute portfolio weight per GICS sector, aggregated from `PortfolioResult.positions` joined to sector data.

```python
# Source: https://plotly.com/python/ (bar charts)
import plotly.graph_objects as go
import pandas as pd

def build_sector_exposure_chart(
    positions: pd.DataFrame,
    ticker_sectors: dict[str, str],  # ticker -> gics_sector
) -> go.Figure:
    """Build a horizontal bar chart of portfolio sector exposure.

    Args:
        positions: Date x ticker weight DataFrame from PortfolioResult.
        ticker_sectors: Mapping from ticker symbol to GICS sector name.

    Returns:
        Plotly Figure with horizontal bar chart sorted ascending by weight.
    """
    sector_map = pd.Series(ticker_sectors)
    valid = positions.columns.intersection(sector_map.index)
    sector_weights = (
        positions[valid]
        .abs()
        .mean()  # time-average of absolute weights per ticker
        .groupby(sector_map[valid])
        .sum()
        .sort_values(ascending=True)
    )

    fig = go.Figure(go.Bar(
        x=sector_weights.values,
        y=sector_weights.index,
        orientation="h",
        marker_color="#1f77b4",
        text=[f"{v:.1%}" for v in sector_weights.values],
        textposition="outside",
    ))
    fig.update_layout(
        title="Sector Exposure (Mean Absolute Weight)",
        xaxis_tickformat=".0%",
        xaxis_title="Portfolio Weight",
        yaxis_title="GICS Sector",
        margin={"l": 200},
    )
    return fig
```

### Pattern 4: KPI Metrics Row

**What:** Row of `st.metric` cards showing scalar values from `MetricsBundle`.

```python
# Source: https://docs.streamlit.io/develop/api-reference/data/st.metric
import streamlit as st

def render_kpi_row(bundle: MetricsBundle) -> None:
    """Render a row of five key performance metric cards."""
    cols = st.columns(5)
    cols[0].metric("Sharpe", f"{bundle.sharpe:.2f}")
    cols[1].metric("Sortino", f"{bundle.sortino:.2f}")
    cols[2].metric("Max DD", f"{bundle.max_drawdown:.1%}")
    cols[3].metric("CAGR", f"{bundle.cagr:.1%}")
    cols[4].metric("Calmar", f"{bundle.calmar:.2f}")
```

### Pattern 5: Caching with st.cache_data

**What:** Cache expensive computations (running backtest pipeline, DB queries) across Streamlit reruns.

```python
# Source: https://docs.streamlit.io/develop/concepts/architecture/caching
import streamlit as st

@st.cache_data
def load_and_run_backtest(config_hash: str) -> tuple[PortfolioResult, MetricsBundle]:
    """Run full backtest pipeline. Cached so reruns do not re-execute.

    st.cache_data is correct here — returns serializable DataFrames and
    Pydantic models. st.cache_resource is for non-serializable objects
    like DB connections and ML models.
    """
    ...
    return result, bundle
```

### Dashboard App Entry Point Structure
```python
# backtest/src/fund_backtest/dashboard/app.py

"""Streamlit dashboard entry point for fund-backtest.

Launch with:
    streamlit run backtest/src/fund_backtest/dashboard/app.py

Requires FUND_BACKTEST_DATABASE_URL environment variable or .env file.
Demo mode (no DB) uses synthetic data from dashboard/demo_data.py.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st
import yfinance as yf

from fund_backtest.dashboard.charts import (
    build_equity_drawdown_chart,
    build_monthly_heatmap,
    build_sector_exposure_chart,
)

st.set_page_config(
    page_title="AI Hedge Fund — Backtest Dashboard",
    layout="wide",
)

@st.cache_data
def _fetch_benchmark_returns(start: str, end: str) -> dict[str, pd.Series]:
    """Fetch SPY and IWM (Russell 2000 proxy) daily returns via yfinance."""
    tickers = {"SPY": "SPY", "Russell 2000": "IWM"}
    result: dict[str, pd.Series] = {}
    for name, ticker in tickers.items():
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if not df.empty:
            result[name] = df["Close"].pct_change().dropna()
    return result
```

### Streamlit Layout — Tabs Pattern
```python
# Source: https://docs.streamlit.io/develop/api-reference/layout
tab_perf, tab_returns, tab_sector = st.tabs([
    "Performance", "Monthly Returns", "Sector Exposure"
])

with tab_perf:
    st.plotly_chart(equity_fig, width="stretch")   # width="stretch" not use_container_width

with tab_returns:
    st.plotly_chart(heatmap_fig, width="stretch")

with tab_sector:
    st.plotly_chart(sector_fig, width="stretch")
```

### Drawdown Episode Annotation
```python
def _annotate_drawdown_episodes(
    fig: go.Figure,
    drawdown: pd.Series,
    threshold: float = -0.05,
    row: int = 2,
) -> None:
    """Add text annotations for major drawdown episodes on the subplot."""
    in_episode = drawdown < threshold
    episode_start: int | None = None
    indices = list(range(len(drawdown)))
    dates = list(drawdown.index)
    values = list(drawdown.values)

    for i in indices:
        if in_episode.iloc[i] and episode_start is None:
            episode_start = i
        elif not in_episode.iloc[i] and episode_start is not None:
            episode_slice = drawdown.iloc[episode_start:i]
            min_idx = episode_slice.idxmin()
            min_val = episode_slice.min()
            duration = i - episode_start
            fig.add_annotation(
                x=min_idx, y=min_val,
                text=f"{min_val:.1%} ({duration}d)",
                showarrow=True, arrowhead=2,
                row=row, col=1,
            )
            episode_start = None
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Diverging red/green colorscale | Custom colour array | `color_continuous_scale='RdYlGn'` in `px.imshow` | Built-in diverging scale; `color_continuous_midpoint=0` anchors zero correctly |
| Monthly return aggregation | Custom loop over dates | `(1 + net_returns).resample("ME").prod() - 1` | pandas resample handles all edge cases (partial months, missing days) |
| Chart subplot linking | Separate figures | `make_subplots(shared_xaxes=True)` | Built-in Plotly subplot with shared pan/zoom for equity+drawdown |
| Streamlit caching | Module-level globals | `@st.cache_data` | Module-level variables reset on every Streamlit rerun; `st.cache_data` is session-aware |
| KPI number display | Custom HTML `<div>` | `st.metric(label, value, delta)` | Built-in Streamlit component with delta arrows and consistent styling |

**Key insight:** All four chart types have battle-tested Plotly patterns. The only custom logic needed is computing sector weights from `positions` + ticker sector mapping — everything else is Plotly and Streamlit API calls.

---

## Common Pitfalls

### Pitfall 1: `color_continuous_midpoint` Omission
**What goes wrong:** Monthly heatmap shows positive return months as red because `px.imshow` defaults midpoint to the mean of the data, not zero.
**Why it happens:** `px.imshow` centres the diverging colorscale on `(min + max) / 2` when `color_continuous_midpoint` is not set.
**How to avoid:** Always pass `color_continuous_midpoint=0.0` when plotting returns.
**Warning signs:** All months appear the same colour; green months appear orange.

### Pitfall 2: Deprecated `use_container_width` in Streamlit 1.45+
**What goes wrong:** `DeprecationWarning` logged for every `st.plotly_chart` call; will raise an error in a future Streamlit release.
**Why it happens:** Streamlit 1.45 introduced the `width` parameter and deprecated `use_container_width`.
**How to avoid:** Use `st.plotly_chart(fig, width="stretch")` instead of `use_container_width=True`.
**Warning signs:** Log output contains "use_container_width is deprecated".

### Pitfall 3: Streamlit App Launched Inside Typer
**What goes wrong:** `streamlit run` must be called from the shell, not programmatically from inside a Typer CLI handler — Streamlit starts its own server, which conflicts with Typer's event loop.
**Why it happens:** Streamlit spawns a server process; embedding it in Typer produces either a hanging process or a crash.
**How to avoid:** Launch with `streamlit run backtest/src/fund_backtest/dashboard/app.py` directly. Optionally add a thin shell script `scripts/dashboard.sh` as a convenience wrapper.
**Warning signs:** Typer command hangs or raises `RuntimeError: This event loop is already running`.

### Pitfall 4: `resample("M")` FutureWarning in pandas 3.x
**What goes wrong:** `net_returns.resample("M")` emits `FutureWarning` about deprecated frequency alias.
**Why it happens:** pandas 3.0 renamed `"M"` to `"ME"` (month end).
**How to avoid:** Use `resample("ME")` for month-end resampling throughout.
**Warning signs:** Warning in console during heatmap build.

### Pitfall 5: No Benchmark Data in Demo Mode
**What goes wrong:** RPT-01 requires benchmark overlays (SPY, Russell 2000) but no benchmark price series is stored in the backtest database. If yfinance fetch fails in demo mode, the equity chart has no benchmark lines.
**Why it happens:** Phases 1-5 built universe data for mid-cap tickers only; benchmarks were passed as externally supplied Series to `MetricsEngine`.
**How to avoid:** In `app.py`, fetch benchmark OHLCV with yfinance directly at startup using `@st.cache_data`. Handle `yf.download` failure gracefully — if it returns empty, render chart without benchmark traces and log a warning.
**Warning signs:** Equity curve shows only strategy line with no benchmark.

### Pitfall 6: Calling `st.*` Inside `charts.py`
**What goes wrong:** Importing `streamlit` in `charts.py` makes chart functions untestable without a live Streamlit session. `st.write`, `st.plotly_chart`, and `st.metric` raise `StreamlitAPIException` when called outside a session.
**Why it happens:** Developers add display calls inside chart builders for convenience.
**How to avoid:** Keep `charts.py` as pure Python/Plotly with zero Streamlit imports. All `st.*` calls live only in `app.py`.
**Warning signs:** `StreamlitAPIException: `st.xxx()` can only be called from within a running Streamlit app.` during tests.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `use_container_width=True` | `width="stretch"` | Streamlit 1.45 | Old parameter deprecated; use `width="stretch"` in all `st.plotly_chart` calls |
| `resample("M")` | `resample("ME")` | pandas 2.2+ | FutureWarning in pandas 3.x; will break in future pandas |
| `**kwargs` in `st.plotly_chart` | `config={...}` named parameter | Streamlit 1.x | `**kwargs` deprecated; pass Plotly config dict as `config` |
| `@st.cache` | `@st.cache_data` / `@st.cache_resource` | Streamlit 1.18 | Old `@st.cache` is removed — do not use |

**Deprecated/outdated:**
- `use_container_width` in `st.plotly_chart`: use `width="stretch"` (confirmed in Streamlit 1.50 docs)
- `resample("M")`: use `"ME"` for month-end in pandas 3.x

---

## Open Questions

1. **Synthetic data for dashboard demo without a live PostgreSQL run**
   - What we know: Phases 4 and 5 provide `PortfolioSimulator` and `MetricsEngine`; tests already use synthetic `PortfolioResult` factory helpers
   - What's unclear: Should `app.py` generate synthetic data for a demonstration mode (no DB), or always require a real simulation run?
   - Recommendation: Add a `demo_data.py` module in `dashboard/` that generates a synthetic `PortfolioResult` + `MetricsBundle` using the same helper pattern as unit tests. This allows visual validation of the dashboard without a database, and Phase 8 will wire in real data.

2. **Sector data source for RPT-03**
   - What we know: `UniverseTicker.gics_sector` is in PostgreSQL (Phase 1); `PortfolioResult.positions` has ticker columns
   - What's unclear: The dashboard needs a ticker→sector mapping. In demo mode there is no DB connection.
   - Recommendation: In demo mode, build a hardcoded `dict[str, str]` using the synthetic ticker list. In production mode, query `SELECT ticker, gics_sector FROM universe_tickers WHERE is_active = true` once at startup, cached.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| streamlit | Dashboard rendering | Yes | 1.50.0 | None — required for phase |
| plotly | Interactive charts | Yes | 6.3.1 | None — required for phase |
| yfinance | Benchmark data (SPY, IWM) | Yes | in pyproject.toml | Skip benchmark overlay if fetch fails (graceful degradation) |
| pandas | Data manipulation | Yes | 3.0.1 in venv | None — already in pyproject.toml |
| PostgreSQL | Production data | Optional for Phase 6 | N/A | Demo mode with synthetic data covers Phase 6 verification |

**Missing dependencies with no fallback:** None — all required libraries are available.

**Missing dependencies with fallback:**
- PostgreSQL: Phase 6 can be verified entirely with synthetic/demo data. Real DB queries are exercised in Phase 8.

**Note:** Streamlit and Plotly are in the system Python (confirmed) but NOT yet in `backtest/pyproject.toml`. Wave 0 of the plan must add them and run `uv sync`.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `backtest/pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `cd backtest && uv run pytest tests/unit/test_dashboard_charts.py -x` |
| Full suite command | `cd backtest && uv run pytest tests/unit/ -x --cov=src/fund_backtest --cov-fail-under=80` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RPT-01 | `build_equity_drawdown_chart` returns 2-row Figure with equity and drawdown traces | unit | `cd backtest && uv run pytest tests/unit/test_dashboard_charts.py::TestEquityChart -x` | No — Wave 0 |
| RPT-01 | Benchmark overlay traces appear when `benchmark_returns` dict is provided | unit | `cd backtest && uv run pytest tests/unit/test_dashboard_charts.py::TestEquityChart::test_benchmark_overlay -x` | No — Wave 0 |
| RPT-01 | Drawdown episode annotations appear for episodes below threshold | unit | `cd backtest && uv run pytest tests/unit/test_dashboard_charts.py::TestDrawdownAnnotations -x` | No — Wave 0 |
| RPT-02 | `build_monthly_heatmap` returns Figure with correct year/month pivot shape | unit | `cd backtest && uv run pytest tests/unit/test_dashboard_charts.py::TestMonthlyHeatmap -x` | No — Wave 0 |
| RPT-02 | Heatmap `color_continuous_midpoint=0` is applied (not mean-centred) | unit | `cd backtest && uv run pytest tests/unit/test_dashboard_charts.py::TestMonthlyHeatmap::test_zero_midpoint -x` | No — Wave 0 |
| RPT-03 | `build_sector_exposure_chart` returns Figure with all sectors from `ticker_sectors` dict | unit | `cd backtest && uv run pytest tests/unit/test_dashboard_charts.py::TestSectorChart -x` | No — Wave 0 |
| RPT-03 | Sector weights use absolute values (long and short positions both count as positive exposure) | unit | `cd backtest && uv run pytest tests/unit/test_dashboard_charts.py::TestSectorChart::test_absolute_weights -x` | No — Wave 0 |

**Note on app.py testing:** The Streamlit entry point (`app.py`) is excluded from unit tests — Streamlit session functions raise `StreamlitAPIException` when called outside a running server. Visual correctness is validated by running `streamlit run backtest/src/fund_backtest/dashboard/app.py` as a smoke check during phase gate verification.

### Sampling Rate
- **Per task commit:** `cd backtest && uv run pytest tests/unit/test_dashboard_charts.py -x`
- **Per wave merge:** `cd backtest && uv run pytest tests/unit/ -x --cov=src/fund_backtest --cov-fail-under=80`
- **Phase gate:** Full suite green + manual smoke check of dashboard in browser before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Add `"streamlit>=1.50.0"` and `"plotly>=6.3.1"` to `backtest/pyproject.toml` dependencies, then run `cd backtest && uv sync`
- [ ] `backtest/src/fund_backtest/dashboard/__init__.py` — empty package marker
- [ ] `backtest/src/fund_backtest/dashboard/charts.py` — stub module (import-only, no implementation) for RED state
- [ ] `backtest/src/fund_backtest/dashboard/demo_data.py` — stub for synthetic PortfolioResult factory
- [ ] `backtest/tests/unit/test_dashboard_charts.py` — all RED test stubs for RPT-01, RPT-02, RPT-03

---

## Project Constraints (from CLAUDE.md)

Directives from the project CLAUDE.md that the planner must verify compliance with:

| Directive | Applies To Phase 6 |
|-----------|-------------------|
| **Immutability** — return new objects, never mutate | Chart factory functions must return new `go.Figure` objects; never mutate figures passed as arguments |
| **Many small files** (<800 lines, 200-400 typical) | `charts.py` should be ≤400 lines; split into `equity.py`, `heatmap.py`, `sector.py` if it grows beyond |
| **No hardcoded values** | Chart colours, episode threshold (-0.05), month labels, and axis titles must be constants or parameters — not inline literals |
| **Error handling** — never silently swallow | Chart functions must handle empty DataFrames gracefully (return minimal placeholder Figure, not raise) |
| **Validate at system boundaries** | yfinance benchmark data must be validated (not empty, not all-NaN) before passing to chart functions |
| **GSD workflow** — no direct edits outside GSD | All file changes through `/gsd:execute-phase` |
| **TDD** — write tests first (RED→GREEN) | Wave 0 creates test stubs; Wave 1 implements charts to GREEN |
| **80% test coverage** | `backtest/pyproject.toml` `fail_under = 80` — `charts.py` must be ≥80% covered by unit tests |
| **ruff** — lint and format | `ruff format src/fund_backtest/dashboard/` and `ruff check src/fund_backtest/dashboard/ --fix` |
| **structlog** — structured logging | `logger = structlog.get_logger(__name__)` in `app.py` for startup events |
| **Google-style docstrings** | All `build_*` functions in `charts.py` need `Args:`, `Returns:` sections |

---

## Sources

### Primary (HIGH confidence)
- Streamlit official docs — `st.plotly_chart` API: width, config, on_select parameters; confirmed `use_container_width` deprecated
- Streamlit official docs — layout components (st.columns, st.tabs, st.sidebar, st.metric with label/value/delta/delta_color)
- Streamlit official docs — caching: `st.cache_data` for serializable return values; `st.cache_resource` for connections/models
- Plotly official docs — `px.imshow`: text_auto, color_continuous_scale, color_continuous_midpoint, aspect parameters
- Plotly official docs — `go.Scatter` fill parameter: tozeroy, tonexty, toself with area charts
- `python3 -c "import streamlit; print(streamlit.__version__)"` — 1.50.0 (verified on target machine 2026-03-29)
- `python3 -c "import plotly; print(plotly.__version__)"` — 6.3.1 (verified on target machine 2026-03-29)

### Secondary (MEDIUM confidence)
- WebSearch + community examples: `make_subplots(shared_xaxes=True)` confirmed as standard for equity+drawdown panels
- WebSearch: Monthly returns heatmap via `px.imshow` on pivoted DataFrame — multiple sources confirm this as standard approach
- Streamlit community discussions: confirmed `use_container_width` deprecation in 1.45+, `width="stretch"` replacement

### Tertiary (LOW confidence — needs validation at execution time)
- `st.metric` `chart_data` and `format` parameters mentioned in docs: not confirmed in 1.50.0 live session. Stick to `label`, `value`, `delta`, `delta_color` (stable core API).
- `IWM` as Russell 2000 proxy: widely used but not officially listed as the standard proxy; confirm ticker is valid before hardcoding.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified on target machine via Python import
- Architecture: HIGH — follows established fund-backtest module patterns (metrics/, simulator/ subpackage structure)
- Chart APIs: HIGH — verified against official Plotly and Streamlit docs
- Pitfalls: HIGH — deprecation warnings verified against Streamlit 1.50 docs and pandas 3.x changelog
- Sector data join: MEDIUM — pattern derived from Phase 1 ORM models; exact query not executed against live DB

**Research date:** 2026-03-29
**Valid until:** 2026-04-29 (Streamlit releases frequently — verify no major API changes if planning is delayed >30 days)
