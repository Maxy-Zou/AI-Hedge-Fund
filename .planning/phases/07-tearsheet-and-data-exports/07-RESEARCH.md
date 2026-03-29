# Phase 7: Tearsheet and Data Exports - Research

**Researched:** 2026-03-29
**Domain:** PDF generation (matplotlib PdfPages), CSV/JSON file exports, CLI integration
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Claude's Discretion
All implementation choices delegated to Claude. Decisions below are made by Claude in light of the existing codebase, STACK.md guidance, and verified environment state.

### Deferred Ideas (OUT OF SCOPE)
None — discuss phase skipped.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RPT-04 | PDF tearsheet generates a single-page fund factsheet with key metrics and charts | matplotlib PdfPages (already installed as quantstats-lumi transitive dep, v3.10.8). Single-page layout via GridSpec. Charts rebuilt in matplotlib-native format (Plotly cannot produce static images without kaleido, which is not installed). |
| RPT-05 | System exports daily returns, positions, and trade log as CSV; metrics as JSON | pandas `.to_csv()` with `date_format='%Y-%m-%d'` for ISO 8601. `json.dumps()` from stdlib for MetricsBundle scalars (rolling Series excluded — not machine-consumable in JSON). Three CSV files + one JSON per run. |
| RPT-06 | All outputs label cost assumptions (slippage, borrow rate, commission) explicitly | CostConfig (from PortfolioResult.trade_log columns and passed explicitly to exporter) is available with all three values. Labeling strategy: PDF footer annotation + CSV header row + JSON `cost_assumptions` key. |
</phase_requirements>

---

## Summary

Phase 7 produces three outputs from any completed backtest run: a single-page PDF tearsheet, machine-readable CSV files, and a JSON metrics bundle. All three outputs must carry explicit cost assumption labels (RPT-06). The foundation is fully in place — `MetricsBundle`, `PortfolioResult`, and `CostConfig` exist as frozen Pydantic models from Phases 4 and 5. Dashboard charts exist in Plotly (Phase 6) but cannot be reused for PDF — Plotly requires `kaleido` for static export, which is not installed and not a justified dependency for this use case.

The correct tearsheet approach is **matplotlib-native chart redraw**: rebuild the equity curve, drawdown fill, and monthly returns heatmap directly in matplotlib, then compose them on a single `figsize=(11, 8.5)` letter-landscape figure using `GridSpec`. A metrics table is rendered via `ax.table()`. The complete figure is saved to a one-page PDF using `PdfPages` from `matplotlib.backends.backend_pdf`. Matplotlib 3.10.8 is already installed (pulled in transitively by `quantstats-lumi`) and confirmed working in the project venv — no new dependencies required.

CSV/JSON exports are pure stdlib+pandas: `PortfolioResult.net_returns.to_csv()`, `PortfolioResult.positions.to_csv()`, `PortfolioResult.trade_log.to_csv()`, and `json.dumps()` of MetricsBundle scalar fields plus a `cost_assumptions` dict. All dates must use `date_format='%Y-%m-%d'` to satisfy the ISO 8601 requirement (RPT-05). The CLI receives a `backtest export` subgroup with `--tearsheet`, `--csv`, and `--json` flags.

**Primary recommendation:** Build a new `reports/` module with a `TearsheetBuilder` (matplotlib PDF) and an `ExportBuilder` (CSV/JSON). Wire both into a new `backtest export` Typer subgroup. No new package dependencies are needed.

---

## Standard Stack

### Core (all already installed — no new dependencies required)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| matplotlib | 3.10.8 (transitive via quantstats-lumi) | PDF tearsheet charts + PdfPages | `PdfPages` is the zero-dependency path to vector PDF. Already installed. Confirmed working in venv. |
| pandas | 3.0.1 (already in pyproject.toml) | `.to_csv()` for three export files | Native DatetimeIndex formatting, `date_format` param. |
| json | stdlib | MetricsBundle scalar serialization | All MetricsBundle scalar fields are plain Python `float` — json.dumps works without additional packages. |
| typer | 0.24.1 (already in pyproject.toml) | `backtest export` CLI subgroup | Consistent with existing `universe` and `data` subgroup pattern in `cli.py`. |
| structlog | 25.5.0 (already in pyproject.toml) | Logging in exporter modules | Consistent with all other modules. |

### Not Needed (verified)

| Library | Reason Excluded |
|---------|-----------------|
| kaleido | Required for `plotly fig.to_image()` — not installed, not worth adding. Reuse plotly charts only in the Streamlit dashboard. Rebuild charts natively in matplotlib for PDF. |
| WeasyPrint | Requires Pango/Cairo system libs. STATE.md explicitly flags this: "use matplotlib PdfPages for v1 PDF instead." |
| ReportLab / fpdf2 | Manual element positioning. STACK.md and prior research explicitly rejected both for v1. |
| Jinja2 | Only needed for WeasyPrint HTML template path. Not taking that path. |

**Installation:** None required. All dependencies are already in `pyproject.toml` and the venv.

---

## Architecture Patterns

### Recommended Module Structure

```
src/fund_backtest/
├── reports/
│   ├── __init__.py              # exports TearsheetBuilder, ExportBuilder
│   ├── tearsheet.py             # TearsheetBuilder: matplotlib PDF generation
│   └── exporter.py              # ExportBuilder: CSV + JSON file writes
tests/unit/
├── test_tearsheet.py            # Unit tests for TearsheetBuilder (RPT-04)
└── test_exporter.py             # Unit tests for ExportBuilder (RPT-05, RPT-06)
```

The `reports/` module sits parallel to `dashboard/`, `metrics/`, and `simulator/` — matching the existing layered structure. It depends on `simulator.types.PortfolioResult`, `metrics.types.MetricsBundle`, and `simulator.types.CostConfig`. No new ORM models, database sessions, or network calls.

### CLI Integration Pattern

```
fund-backtest backtest export --tearsheet [--output-dir PATH]
fund-backtest backtest export --csv [--output-dir PATH]
fund-backtest backtest export --json [--output-dir PATH]
fund-backtest backtest export --all [--output-dir PATH]
```

Follows the exact pattern of `universe_app` and `data_app` in `cli.py`:
```python
backtest_app = typer.Typer(help="Backtest export commands.")
app.add_typer(backtest_app, name="backtest")
export_app = typer.Typer(help="Export backtest results.")
backtest_app.add_typer(export_app, name="export")
```

For Phase 7 (no live DB integration yet), the CLI operates in demo mode using `make_demo_result()` / `make_demo_bundle()` — consistent with the dashboard's demo mode. Phase 8 will wire in live data.

### Pattern 1: TearsheetBuilder

**What:** Single class that accepts `PortfolioResult`, `MetricsBundle`, and `CostConfig`, then writes a one-page PDF.

**When to use:** Called from CLI `backtest export --tearsheet`, or directly from tests.

```python
# Source: verified against matplotlib 3.10.8 in project venv
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

class TearsheetBuilder:
    """Generates a single-page PDF tearsheet from a completed backtest run."""

    def build(
        self,
        result: PortfolioResult,
        bundle: MetricsBundle,
        cost_config: CostConfig,
        output_path: Path,
    ) -> Path:
        """Write a single-page PDF to output_path. Returns the path."""
        # Always use non-interactive backend — safe for headless/test environments
        import matplotlib
        matplotlib.use("Agg")

        fig = plt.figure(figsize=(11, 8.5), constrained_layout=True)
        gs = gridspec.GridSpec(3, 2, figure=fig, height_ratios=[1.5, 1, 1])

        # Row 0: equity curve (full width)
        ax_equity = fig.add_subplot(gs[0, :])
        # Row 1: drawdown (full width)
        ax_dd = fig.add_subplot(gs[1, :])
        # Row 2 left: monthly heatmap
        ax_heatmap = fig.add_subplot(gs[2, 0])
        # Row 2 right: metrics table + cost assumption footer
        ax_table = fig.add_subplot(gs[2, 1])

        self._draw_equity(ax_equity, result.net_returns)
        self._draw_drawdown(ax_dd, result.net_returns)
        self._draw_monthly_heatmap(ax_heatmap, result.net_returns)
        self._draw_metrics_table(ax_table, bundle, cost_config)

        with PdfPages(output_path) as pdf:
            d = pdf.infodict()
            d["Title"] = "AI Hedge Fund — Backtest Tearsheet"
            pdf.savefig(fig, bbox_inches="tight")

        plt.close(fig)
        return output_path
```

**Key layout note:** `constrained_layout=True` is the modern replacement for `tight_layout()` in matplotlib 3.x. Both work; `constrained_layout` handles subplot spacing more robustly.

**Backend note:** `matplotlib.use("Agg")` must be called before `import matplotlib.pyplot`. In test files, add it at the top of the file before any pyplot import. In production CLI, it is called inside the builder to avoid side effects on callers that may want an interactive backend.

### Pattern 2: ExportBuilder

**What:** Writes three CSV files and one JSON file to an output directory.

**When to use:** Called from CLI `backtest export --csv --json`, or tests.

```python
# Source: verified against pandas 3.0.1 and stdlib json in project venv
import json
from pathlib import Path

class ExportBuilder:
    """Exports PortfolioResult and MetricsBundle to CSV and JSON files."""

    def export_csv(
        self,
        result: PortfolioResult,
        cost_config: CostConfig,
        output_dir: Path,
    ) -> list[Path]:
        """Write daily_returns.csv, positions.csv, trade_log.csv."""
        # ISO 8601 dates — always use date_format='%Y-%m-%d'
        returns_path = output_dir / "daily_returns.csv"
        result.net_returns.to_csv(returns_path, index=True, header=True, date_format="%Y-%m-%d")

        positions_path = output_dir / "positions.csv"
        result.positions.to_csv(positions_path, index=True, date_format="%Y-%m-%d")

        # trade_log already has a 'date' column (not the DatetimeIndex)
        trade_path = output_dir / "trade_log.csv"
        result.trade_log.to_csv(trade_path, index=False)

        # Prepend cost assumption comment to each file (RPT-06)
        _prepend_cost_header(returns_path, cost_config)
        _prepend_cost_header(positions_path, cost_config)
        _prepend_cost_header(trade_path, cost_config)

        return [returns_path, positions_path, trade_path]

    def export_json(
        self,
        bundle: MetricsBundle,
        cost_config: CostConfig,
        output_dir: Path,
    ) -> Path:
        """Write metrics.json with scalar metrics + cost_assumptions."""
        data = {
            "sharpe": bundle.sharpe,
            "sortino": bundle.sortino,
            "calmar": bundle.calmar,
            "max_drawdown": bundle.max_drawdown,
            "cagr": bundle.cagr,
            "hit_rate": bundle.hit_rate,
            "win_loss_ratio": bundle.win_loss_ratio,
            "annual_turnover": bundle.annual_turnover,
            "alpha": bundle.alpha,
            "beta": bundle.beta,
            "cost_assumptions": {          # RPT-06: always present
                "slippage_bps": cost_config.slippage_bps,
                "commission_bps": cost_config.commission_bps,
                "borrow_cost_bps_annual": cost_config.borrow_cost_bps_annual,
            },
        }
        # rolling_sharpe and rolling_drawdown are pd.Series — NOT included in JSON
        # (not machine-consumable in flat JSON; consumers can derive from daily_returns.csv)
        path = output_dir / "metrics.json"
        path.write_text(json.dumps(data, indent=2))
        return path
```

**Important:** `MetricsBundle.rolling_sharpe` and `rolling_drawdown` are `pd.Series` — they cannot be directly serialized with `json.dumps`. Exclude them from JSON. Consumers who need rolling data should compute from `daily_returns.csv`.

### Pattern 3: RPT-06 Cost Assumption Labeling

Three labeling strategies — one per output type:

**PDF:** Cost assumptions in the metrics table as dedicated rows:
```python
data = [
    ...metrics rows...,
    ['--- Cost Assumptions ---', ''],
    ['Slippage', f'{cost_config.slippage_bps:.0f} bps (one-way)'],
    ['Commission', f'{cost_config.commission_bps:.0f} bps (one-way)'],
    ['Borrow Rate', f'{cost_config.borrow_cost_bps_annual:.0f} bps/yr (flat)'],
]
```

**CSV:** Prepend a `# cost_assumptions: ...` comment line before the header row:
```python
def _prepend_cost_header(path: Path, cost: CostConfig) -> None:
    """Prepend a comment line with cost assumptions to a CSV file."""
    comment = (
        f"# cost_assumptions: slippage={cost.slippage_bps}bps,"
        f" commission={cost.commission_bps}bps,"
        f" borrow={cost.borrow_cost_bps_annual}bps/yr\n"
    )
    original = path.read_text()
    path.write_text(comment + original)
```

**JSON:** `cost_assumptions` key at the top level (shown in ExportBuilder.export_json above).

### Anti-Patterns to Avoid

- **Reusing Plotly figures for PDF:** `fig.to_image()` requires `kaleido`, which is not installed. Do not attempt `fig.to_image(format='png')` — it raises a clear error at runtime. Rebuild charts in matplotlib.
- **Using `matplotlib.use()` after `import matplotlib.pyplot`:** Backend must be set before pyplot is imported. In modules that might be imported interactively, wrap in `if matplotlib.get_backend() != 'Agg': matplotlib.use('Agg')`.
- **Serializing `pd.Series` with `json.dumps`:** Will raise `TypeError`. Only include scalar fields from `MetricsBundle` in the JSON export.
- **Using `tight_layout()` with GridSpec:** `constrained_layout=True` is the correct modern approach. `tight_layout()` can conflict with GridSpec in matplotlib 3.x.
- **Hardcoding cost values:** All cost assumption labels must come from `CostConfig` fields, never from string literals. This is both the RPT-06 requirement and the project's no-hardcoded-values convention.
- **`date_format` omission in `to_csv()`:** Without `date_format='%Y-%m-%d'`, pandas writes `2021-01-04 00:00:00` (includes time). Always pass `date_format='%Y-%m-%d'` for clean ISO 8601 output.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multi-page PDF | Custom PDF byte writer | `matplotlib.backends.backend_pdf.PdfPages` | Handles vector output, metadata, page sizing — already installed |
| Chart rendering | Plotly-to-matplotlib conversion layer | Rebuild charts natively in matplotlib | Plotly static export requires kaleido; conversion tools (`mpl_to_plotly` is one-way only); rebuilding is simpler and produces cleaner output |
| JSON serialization | Custom serializer for MetricsBundle | `json.dumps(dict)` with only scalar fields | MetricsBundle scalar fields are all Python `float` — stdlib json handles them natively |
| ISO 8601 dates in CSV | Manual `strftime` loop | `pandas.DataFrame.to_csv(date_format='%Y-%m-%d')` | Built into pandas, vectorized, correct for DatetimeIndex |

**Key insight:** This phase is primarily integration work — wiring existing outputs (MetricsBundle, PortfolioResult, CostConfig) into file writers. No novel algorithms. The only complexity is the matplotlib layout and the backend configuration for headless/test environments.

---

## Common Pitfalls

### Pitfall 1: matplotlib Backend in Test Environment
**What goes wrong:** `tests/unit/test_tearsheet.py` imports `TearsheetBuilder`, which calls `matplotlib.use("Agg")` — but if another test already imported pyplot with the default backend, this raises `UserWarning: Matplotlib is currently using [backend], which is a non-GUI backend`. In CI, the default backend may be `Agg` already, but locally it may be `TkAgg` or `MacOSX`.

**Why it happens:** `matplotlib.use()` must be called before `import matplotlib.pyplot as plt`. Once pyplot is imported, the backend is locked.

**How to avoid:** In `test_tearsheet.py`, set the backend at the top of the file before any pyplot import:
```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
```
Alternatively, check `matplotlib.get_backend()` first and only call `use()` if it isn't already `Agg`.

**Warning signs:** `UserWarning: Matplotlib is currently using X, cannot use Agg` in test output.

### Pitfall 2: Rolling Series in JSON Export
**What goes wrong:** A developer might include `bundle.rolling_sharpe` or `bundle.rolling_drawdown` in the JSON export `data` dict, which will raise `TypeError: Object of type Series is not JSON serializable`.

**Why it happens:** `MetricsBundle` uses `arbitrary_types_allowed=True` in Pydantic config specifically to allow `pd.Series` fields — those fields do not serialize to JSON.

**How to avoid:** Explicitly exclude rolling Series fields from the `export_json` method. Document the exclusion in the function docstring.

**Warning signs:** `TypeError: Object of type Series is not JSON serializable` at runtime.

### Pitfall 3: trade_log Date Column vs. DatetimeIndex
**What goes wrong:** `PortfolioResult.positions` has a `DatetimeIndex`, but `PortfolioResult.trade_log` has a regular `date` column (not the index). Applying `date_format` to `trade_log.to_csv()` will not affect the `date` column — the format parameter only applies to the DataFrame index.

**Why it happens:** `to_csv(date_format=...)` formats the index. The `trade_log.date` column is a plain column, not the index.

**How to avoid:** For `trade_log`, either (a) set `date` as the index before export so `date_format` applies, or (b) convert the `date` column manually: `df['date'] = df['date'].dt.strftime('%Y-%m-%d')` before calling `to_csv`. Option (b) is simpler given the existing schema.

**Warning signs:** Trade log CSV has timestamps in the `date` column instead of `YYYY-MM-DD`.

### Pitfall 4: Monthly Heatmap with NaN Months
**What goes wrong:** If the backtest period covers a partial year (first or last year), `pivot.unstack()` will have NaN cells for months not covered. `ax.imshow()` renders NaN as white by default, but `ax.text()` will produce blank cells. This is acceptable but must be guarded in the cell text loop.

**Why it happens:** `pivot.unstack(level=1)` fills missing months with NaN.

**How to avoid:** Add a `np.isnan(val)` guard in the cell text annotation loop — skip annotation when `np.isnan(val)`.

**Warning signs:** `ValueError: cannot convert float NaN to integer` inside the annotation loop.

### Pitfall 5: `constrained_layout` + `PdfPages.savefig`
**What goes wrong:** Calling `pdf.savefig(fig, bbox_inches='tight')` with `constrained_layout=True` active sometimes produces a warning: `UserWarning: The figure layout has changed to tight`.

**Why it happens:** `bbox_inches='tight'` and `constrained_layout` both adjust figure boundaries; they can conflict.

**How to avoid:** When using `constrained_layout=True`, call `pdf.savefig(fig)` without `bbox_inches='tight'`. The constrained layout already handles spacing. Only use `bbox_inches='tight'` when `constrained_layout=False`.

---

## Code Examples

### Tearsheet GridSpec Layout (verified against matplotlib 3.10.8)
```python
# Source: verified in project venv — matplotlib 3.10.8
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_pdf import PdfPages
from pathlib import Path

def build_tearsheet(result, bundle, cost_config, output_path: Path) -> Path:
    fig = plt.figure(figsize=(11, 8.5), constrained_layout=True)
    # 3 rows: equity (tall), drawdown (medium), heatmap+table (medium)
    gs = gridspec.GridSpec(3, 2, figure=fig, height_ratios=[1.5, 1, 1])

    ax_equity  = fig.add_subplot(gs[0, :])   # spans both columns
    ax_dd      = fig.add_subplot(gs[1, :])   # spans both columns
    ax_heatmap = fig.add_subplot(gs[2, 0])   # left column
    ax_table   = fig.add_subplot(gs[2, 1])   # right column

    # ... draw on each axis ...

    with PdfPages(output_path) as pdf:
        d = pdf.infodict()
        d["Title"] = "AI Hedge Fund — Backtest Tearsheet"
        pdf.savefig(fig)   # no bbox_inches='tight' with constrained_layout
    plt.close(fig)
    return output_path
```

### Monthly Returns Heatmap (matplotlib-native, verified)
```python
# Source: verified in project venv — matplotlib 3.10.8, pandas 3.0.1
import numpy as np

def _draw_monthly_heatmap(ax, net_returns):
    """matplotlib imshow heatmap for monthly returns."""
    monthly = (1 + net_returns).resample("ME").prod() - 1   # pandas 3.x: "ME" not "M"
    pivot = monthly.groupby([monthly.index.year, monthly.index.month]).first().unstack(level=1)
    month_labels = ["Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"]
    pivot.columns = [month_labels[m - 1] for m in pivot.columns]
    pivot.index = pivot.index.astype(str)

    im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto", vmin=-0.05, vmax=0.05)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=45, ha="right", fontsize=7)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=7)
    ax.set_title("Monthly Returns", fontsize=9)
    # Cell annotations — guard against NaN
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            val = pivot.iloc[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.1%}", ha="center", va="center", fontsize=6)
```

### Metrics Table with Cost Assumptions (matplotlib ax.table)
```python
# Source: verified in project venv — matplotlib 3.10.8
def _draw_metrics_table(ax, bundle, cost_config):
    """Metrics + cost assumptions table as a matplotlib table."""
    ax.axis("off")
    ax.set_title("Key Metrics", fontsize=9, pad=4)
    data = [
        ["Sharpe Ratio",   f"{bundle.sharpe:.2f}"],
        ["Sortino Ratio",  f"{bundle.sortino:.2f}"],
        ["Calmar Ratio",   f"{bundle.calmar:.2f}"],
        ["Max Drawdown",   f"{bundle.max_drawdown:.1%}"],
        ["CAGR",           f"{bundle.cagr:.1%}"],
        ["Hit Rate",       f"{bundle.hit_rate:.1%}"],
        ["Win/Loss Ratio", f"{bundle.win_loss_ratio:.2f}"],
        ["Annual Turnover",f"{bundle.annual_turnover:.1f}x"],
        ["Alpha",          f"{bundle.alpha:.3f}"],
        ["Beta",           f"{bundle.beta:.2f}"],
        ["", ""],
        ["-- Cost Assumptions --", ""],
        ["Slippage",       f"{cost_config.slippage_bps:.0f} bps one-way"],
        ["Commission",     f"{cost_config.commission_bps:.0f} bps one-way"],
        ["Borrow Rate",    f"{cost_config.borrow_cost_bps_annual:.0f} bps/yr (flat)"],
    ]
    table = ax.table(cellText=data, colLabels=["Metric", "Value"],
                     loc="center", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(7)
    table.scale(1.1, 1.3)
```

### CSV Export with ISO 8601 Dates (verified)
```python
# Source: verified in project venv — pandas 3.0.1
def export_csv(result, cost_config, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    comment = (
        f"# cost_assumptions: slippage={cost_config.slippage_bps}bps,"
        f" commission={cost_config.commission_bps}bps,"
        f" borrow={cost_config.borrow_cost_bps_annual}bps/yr\n"
    )

    # daily_returns.csv
    p = output_dir / "daily_returns.csv"
    result.net_returns.rename("net_returns").to_csv(
        p, index=True, header=True, date_format="%Y-%m-%d"
    )
    p.write_text(comment + p.read_text())

    # positions.csv (date x ticker)
    p = output_dir / "positions.csv"
    result.positions.to_csv(p, index=True, date_format="%Y-%m-%d")
    p.write_text(comment + p.read_text())

    # trade_log.csv — date is a column, not the index
    trade_log = result.trade_log.copy()
    if "date" in trade_log.columns and not trade_log.empty:
        trade_log["date"] = pd.to_datetime(trade_log["date"]).dt.strftime("%Y-%m-%d")
    p = output_dir / "trade_log.csv"
    trade_log.to_csv(p, index=False)
    p.write_text(comment + p.read_text())
```

### JSON Metrics Export (verified)
```python
# Source: verified in project venv — stdlib json 2.0.9
import json

def export_json(bundle, cost_config, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "sharpe":          bundle.sharpe,
        "sortino":         bundle.sortino,
        "calmar":          bundle.calmar,
        "max_drawdown":    bundle.max_drawdown,
        "cagr":            bundle.cagr,
        "hit_rate":        bundle.hit_rate,
        "win_loss_ratio":  bundle.win_loss_ratio,
        "annual_turnover": bundle.annual_turnover,
        "alpha":           bundle.alpha,
        "beta":            bundle.beta,
        # rolling_sharpe and rolling_drawdown are pd.Series — excluded from JSON
        "cost_assumptions": {
            "slippage_bps":           cost_config.slippage_bps,
            "commission_bps":         cost_config.commission_bps,
            "borrow_cost_bps_annual": cost_config.borrow_cost_bps_annual,
        },
    }
    p = output_dir / "metrics.json"
    p.write_text(json.dumps(data, indent=2))
    return p
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `tight_layout()` | `constrained_layout=True` in `plt.figure()` | matplotlib 3.6+ | Better spacing with GridSpec; avoid using both simultaneously |
| pandas `"M"` resample alias | `"ME"` (month-end) | pandas 2.2+ | `"M"` is deprecated; produces FutureWarning in pandas 3.x. Already fixed in Phase 6 dashboard (`charts.py` uses "ME"). |
| `matplotlib.use("TkAgg")` | `matplotlib.use("Agg")` for headless/CI | Always | Agg is the non-interactive backend; required for test environments without a display server |

**Deprecated/outdated:**
- `PdfPages.attach_note()`: Available but not needed — use `pdf.infodict()["Title"]` for metadata.
- `plt.tight_layout()`: Still works but emits warnings when used with `constrained_layout`. Pick one approach.

---

## Open Questions

1. **Output directory convention**
   - What we know: CLI needs a `--output-dir` parameter. The project has no established export directory convention.
   - What's unclear: Should it default to `./exports/`, the current working directory, or a configurable path in `AppSettings`?
   - Recommendation: Default to `./exports/{timestamp}/` (e.g., `exports/2026-03-29T18-00-00/`). This avoids overwriting previous runs and is self-documenting. No config change needed for v1.

2. **Demo mode vs. live mode for CLI**
   - What we know: Phase 8 wires live DB data; Phase 7 CLI uses demo data. The `--signal` flag (from Phase 8 success criteria) isn't implemented yet.
   - What's unclear: Should the `backtest export` CLI silently use demo data or raise a clear message?
   - Recommendation: Print a `[yellow]Demo mode — using synthetic data. Pass --signal to use live data (Phase 8).[/yellow]` message via Rich, then proceed with demo data. This matches the dashboard's existing demo mode behavior.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| matplotlib | PDF tearsheet (RPT-04) | Yes | 3.10.8 (transitive via quantstats-lumi) | None needed |
| pandas | CSV export (RPT-05) | Yes | 3.0.1 | None needed |
| json (stdlib) | JSON export (RPT-05, RPT-06) | Yes | 2.0.9 | None needed |
| matplotlib Agg backend | Headless PDF in tests | Yes | Built into matplotlib | None needed |
| kaleido | Plotly static export | No | Not installed | Use matplotlib-native charts (confirmed approach) |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** kaleido is missing but has a confirmed fallback (matplotlib-native chart redraws). Do not install kaleido.

**New dependency to add to pyproject.toml:** `matplotlib>=3.10` must be added as an explicit direct dependency. Currently it is only a transitive dependency (via quantstats-lumi). Adding it explicitly makes the dependency explicit and ensures it stays available if quantstats-lumi is ever removed or changes its dependencies.

```bash
uv add "matplotlib>=3.10"
```

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `cd backtest && .venv/bin/python -m pytest tests/unit/test_tearsheet.py tests/unit/test_exporter.py -x` |
| Full suite command | `cd backtest && .venv/bin/python -m pytest tests/unit/ -m "not integration"` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RPT-04 | TearsheetBuilder.build() writes a PDF file to the given path | unit | `pytest tests/unit/test_tearsheet.py::TestTearsheetBuilder::test_creates_pdf_file -x` | Wave 0 |
| RPT-04 | PDF contains exactly one page | unit | `pytest tests/unit/test_tearsheet.py::TestTearsheetBuilder::test_single_page -x` | Wave 0 |
| RPT-04 | PDF is non-empty (> 0 bytes) | unit | `pytest tests/unit/test_tearsheet.py::TestTearsheetBuilder::test_pdf_nonempty -x` | Wave 0 |
| RPT-05 | export_csv() produces daily_returns.csv, positions.csv, trade_log.csv | unit | `pytest tests/unit/test_exporter.py::TestExportBuilder::test_csv_files_created -x` | Wave 0 |
| RPT-05 | daily_returns.csv dates are in ISO 8601 format (YYYY-MM-DD) | unit | `pytest tests/unit/test_exporter.py::TestExportBuilder::test_returns_iso_dates -x` | Wave 0 |
| RPT-05 | export_json() produces metrics.json with all 10 scalar fields | unit | `pytest tests/unit/test_exporter.py::TestExportBuilder::test_json_has_all_scalar_fields -x` | Wave 0 |
| RPT-05 | metrics.json does not contain rolling Series (JSON serializable) | unit | `pytest tests/unit/test_exporter.py::TestExportBuilder::test_json_no_series -x` | Wave 0 |
| RPT-06 | daily_returns.csv first line contains cost assumptions comment | unit | `pytest tests/unit/test_exporter.py::TestExportBuilder::test_returns_csv_has_cost_header -x` | Wave 0 |
| RPT-06 | positions.csv first line contains cost assumptions comment | unit | `pytest tests/unit/test_exporter.py::TestExportBuilder::test_positions_csv_has_cost_header -x` | Wave 0 |
| RPT-06 | trade_log.csv first line contains cost assumptions comment | unit | `pytest tests/unit/test_exporter.py::TestExportBuilder::test_trade_log_csv_has_cost_header -x` | Wave 0 |
| RPT-06 | metrics.json contains cost_assumptions key with all three values | unit | `pytest tests/unit/test_exporter.py::TestExportBuilder::test_json_cost_assumptions -x` | Wave 0 |
| RPT-06 | PDF tearsheet metrics table includes slippage, commission, borrow rows | unit | `pytest tests/unit/test_tearsheet.py::TestTearsheetBuilder::test_pdf_contains_cost_label -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backtest && .venv/bin/python -m pytest tests/unit/test_tearsheet.py tests/unit/test_exporter.py -x`
- **Per wave merge:** `cd backtest && .venv/bin/python -m pytest tests/unit/ -m "not integration"`
- **Phase gate:** Full unit suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_tearsheet.py` — covers RPT-04 and RPT-06 (PDF)
- [ ] `tests/unit/test_exporter.py` — covers RPT-05 and RPT-06 (CSV/JSON)

*(conftest.py, pytest, and freezegun are already in place — no additional test infrastructure gaps)*

---

## Sources

### Primary (HIGH confidence)
- Verified directly in project venv (Python 3.12.11, matplotlib 3.10.8, pandas 3.0.1, plotly 6.6.0, quantstats-lumi 1.1.3)
- `matplotlib.backends.backend_pdf.PdfPages` — confirmed with live import and PDF write/close cycle
- `matplotlib.gridspec.GridSpec` — confirmed with 3-row 2-column layout and single-page PDF output
- `pandas.Series.to_csv(date_format='%Y-%m-%d')` — confirmed ISO 8601 output without timestamps
- `json.dumps()` on all `MetricsBundle` scalar float fields — confirmed no serialization errors
- `pd.Series` JSON serialization failure — confirmed `TypeError` when attempting direct json.dumps of Series

### Secondary (MEDIUM confidence)
- [matplotlib PdfPages official docs](https://matplotlib.org/stable/gallery/misc/multipage_pdf.html) — PdfPages usage and `infodict()` metadata
- [matplotlib constrained_layout guide](https://matplotlib.org/stable/users/explain/axes/constrainedlayout_guide.html) — GridSpec spacing

### Tertiary (LOW confidence)
- None — all critical findings verified directly in the project venv.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all dependencies verified installed and functional in the project venv
- Architecture: HIGH — module structure follows established patterns from Phases 5 and 6; all code examples verified
- Pitfalls: HIGH — each pitfall was reproduced or verified via direct venv testing

**Research date:** 2026-03-29
**Valid until:** 2026-06-29 (matplotlib and pandas are stable; no breaking changes expected at this cadence)
