# Phase 12: Bug Fixes and Wiring - Research

**Researched:** 2026-03-30
**Domain:** Backtest CLI wiring, Streamlit dashboard live mode, benchmark alpha/beta computation
**Confidence:** HIGH — all findings from direct codebase inspection; no estimation

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FIX-02 | `backtest run` intersects signal and price date indices before calling the simulator (no silent 0% returns) | Signal date range drives price query; price pivot result may have a different date index than the shifted WeightFrame; `_align_frames()` already exists in simulator but is called too late — the intersection must happen before `SignalAdapter.adapt()` to avoid a WeightFrame with all-zero rows on non-overlapping dates |
| FIX-03 | `backtest export` uses real backtest results instead of `make_demo_result()` demo stubs | `export` command unconditionally calls `make_demo_result()` / `make_demo_bundle()` instead of loading from DB or accepting a previous run's output |
| FIX-04 | Dashboard renders real backtest data instead of hardcoded demo data when results are available | `main()` always calls `_load_demo_data()`; DEMO_TICKER_SECTORS hardcoded instead of DB query; no live-mode code path exists yet |
| FIX-05 | Benchmark alpha/beta values are correctly computed and included in CLI exports | `backtest run` calls `MetricsEngine().compute(portfolio_result)` with no `benchmark=` argument — alpha/beta are permanently 0.0; yfinance benchmark fetch exists only in `dashboard/app.py:_fetch_benchmark_returns()` |
</phase_requirements>

---

## Summary

Phase 12 is a surgical wiring phase, not a feature-building phase. All four bugs were identified
during the v1.0 milestone audit (INTG-01, INTG-02, and two Phase 5/8 tech debt items). The complete
list of issues:

**FIX-02** — The `backtest run` command loads signal scores and price bars independently and then
passes both to `SignalAdapter.adapt()` and `PortfolioSimulator.simulate()` without first ensuring
the date indices overlap. `_align_frames()` inside the simulator does reduce to common dates, but
only after `SignalAdapter.adapt()` has already applied `shift(1)` — meaning the WeightFrame may
contain all-zero rows for signal dates that have no corresponding price data. With real AI Washing
scores starting in 2021 and price data covering the same period, a timezone mismatch or partial
coverage gap could silently produce a short window of near-zero returns.

**FIX-03** — The `backtest export` command was a Phase 7 placeholder. It still calls
`make_demo_result()` / `make_demo_bundle()` unconditionally. The `backtest run` command already
computes a real `PortfolioResult` and `MetricsBundle`, but `backtest export` has no way to receive
them. The fix requires either (a) running the full backtest pipeline inside `export` (the same
5-stage pipeline as `run`) or (b) persisting the run result to disk for later export. The simplest
approach is (a): add a `--signal` argument to `export`, run the full pipeline, then export all
artifacts in one pass.

**FIX-04** — `dashboard/app.py:main()` always calls `_load_demo_data()` and uses
`DEMO_TICKER_SECTORS`. The dashboard was designed with a clear seam (comment: "Phase 8 will wire
real DB data"), but the wiring never happened. The fix requires: (1) running the backtest pipeline
inside the dashboard on startup (or reading cached results), (2) querying `UniverseTicker.gics_sector`
from the DB instead of using `DEMO_TICKER_SECTORS`, and (3) switching the caption from "Demo mode"
to "Live mode". The DB connection check guards against environments with no `FUND_BACKTEST_DATABASE_URL`.

**FIX-05** — `backtest run` calls `MetricsEngine().compute(portfolio_result)` with `benchmark=None`.
This is intentional per Phase 5 design (alpha=0.0, beta=0.0 documented defaults), but the live path
should pass real benchmark returns. The fix: fetch SPY/IWM via yfinance inside `backtest run` (same
logic as `_fetch_benchmark_returns()` in `dashboard/app.py`) and pass the result as `benchmark=` to
`MetricsEngine.compute()`.

**Primary recommendation:** Fix all four bugs in a single plan. Each fix is < 20 lines. The natural
execution order is FIX-05 first (simplest, independent), then FIX-02, then FIX-03 (both touch
`cli.py:run`), then FIX-04 (touches `dashboard/app.py`).

---

## Bug Anatomy

### FIX-02: Signal-Price Date Intersection

**File:** `backtest/src/fund_backtest/cli.py` — `run()` command, lines 297–326

**Root cause:** The `run` command computes the signal's date range with `signal_frame.index.min()`
and `signal_frame.index.max()`, then queries `PriceBarRepository.get_bars()` with those dates.
This is correct for bounding the query. However, the returned `price_frame` is pivoted from actual
DB rows — if the DB is missing bars for some signal dates (e.g., non-trading days in the signal
index, or a date-format mismatch between `scored_at::date` and `bar_date`), the two indices will
not be identical.

`SignalAdapter.adapt()` is called on `signal_frame` (raw signal dates) before `price_frame` is
involved. `shift(1)` is applied inside the adapter on the signal's own date index. The resulting
`weight_frame` has `signal_frame`'s date index (shifted by one row). When `PortfolioSimulator._align_frames()` then intersects `weight_frame.index` with `price_frame.index`, any date in the
signal that has no corresponding price bar produces zero gross returns — not dropped, but present
as dead weight.

**The specific scenario that causes 0% returns:** If `signal_frame` contains dates that are not
business days (e.g., weekend-adjacent dates from `scored_at` being generated on a Saturday), and
`price_frame` only contains business days, the overlap is small. `_align_frames()` silently logs
a warning and drops dates, but the WeightFrame passed to the simulator may already have near-zero
coverage.

**Fix:** Intersect `signal_frame.index` and `price_frame.index` *before* calling
`SignalAdapter.adapt()`. Pass only the intersection's rows of `signal_frame` into `adapt()`. This
ensures the WeightFrame and PriceFrame share the same date spine from the start.

```python
# In cli.py run(), after building price_frame and before SignalAdapter.adapt():
common_dates = signal_frame.index.intersection(price_frame.index)
if len(common_dates) == 0:
    console.print("[red]Signal and price data share no common dates.[/red]")
    raise typer.Exit(code=1)
if len(common_dates) < len(signal_frame.index):
    _log.warning(
        "signal_price_date_mismatch",
        signal_dates=len(signal_frame.index),
        common_dates=len(common_dates),
    )
signal_frame = signal_frame.loc[common_dates]
# Then proceed with SignalAdapter().adapt(signal_frame)
```

**Impact:** Prevents silent all-zero simulation results from date mismatches. The existing
`_align_frames()` in the simulator remains as a secondary safety net.

---

### FIX-03: Export Command Uses Demo Stubs

**File:** `backtest/src/fund_backtest/cli.py` — `export()` command, lines 350–390

**Root cause:** The `export()` command was written in Phase 7 as a standalone demo-data exporter.
Lines 362–363 read:
```python
result = make_demo_result()
bundle = make_demo_bundle(result)
```

No `--signal` argument exists. No DB connection is made. The command always exports synthetic data
regardless of what's in the database.

**Fix approach:** Add a `--signal` option to the `export` command (matching `run`'s `--signal`).
When `--signal` is provided, execute the same 5-stage pipeline used by `run` to produce a real
`PortfolioResult` + `MetricsBundle`. When `--signal` is not provided, fall back to demo mode with
a deprecation warning. This preserves backward compatibility while enabling the live path.

The tearsheet wiring (INTG-01) is part of this same fix: add `TearsheetBuilder.build()` to the
live path's `do_tearsheet` branch. The `run --export-all` path in the `run()` command also needs
`TearsheetBuilder` added (one line).

**Approximate change:**
- Add `signal: str | None = typer.Option(None, "--signal")` to `export()` signature
- Add `if signal:` branch that runs the pipeline (extracted from `run()` into a shared helper)
- Add tearsheet call in both `export()` and `run()`'s export branch

---

### FIX-04: Dashboard Live Mode

**File:** `backtest/src/fund_backtest/dashboard/app.py` — `main()`, lines 139–205

**Root cause:** `main()` always calls `_load_demo_data()` (line 151) and passes `DEMO_TICKER_SECTORS`
to `build_sector_exposure_chart()` (line 182). There is no conditional live-mode path.

**Fix design:**

1. **Live mode detection:** Check if `FUND_BACKTEST_DATABASE_URL` is set in the environment. If
   set, attempt to run the backtest pipeline and query `UniverseTicker.gics_sector`. If not set (or
   if the pipeline fails), fall back to demo mode gracefully.

2. **Run the backtest in the dashboard:** Add a `@st.cache_data` function `_load_live_data()` that
   runs the same 5-stage pipeline as `backtest run`. Streamlit's `@st.cache_data` ensures this only
   runs once per session, not on every re-render.

3. **Load real sector data:** Query `UniverseTicker` for active tickers and build a
   `{ticker: sector}` dict to replace `DEMO_TICKER_SECTORS`.

4. **Update caption:** Change the banner from "Demo mode" to "Live mode — AI Washing signal,
   real SEC filing data" when real data is loaded.

**Fallback behavior:** If `FUND_BACKTEST_DATABASE_URL` is unset or pipeline raises `SignalLoadError`,
fall back to `_load_demo_data()` with the existing "Demo mode" banner and a warning toast.

**Key constraint from STATE.md:** `dashboard/app.py` is in the pytest coverage omit list — no unit
tests are expected for the dashboard. The live-mode path is verified by running `streamlit run`.

---

### FIX-05: Benchmark Alpha/Beta in CLI Run Path

**File:** `backtest/src/fund_backtest/cli.py` — `run()` command, line 325

**Root cause:** Line 325 reads:
```python
bundle = MetricsEngine().compute(portfolio_result)
```

No `benchmark=` argument is passed. The `MetricsEngine.compute()` docstring explicitly documents
this: "When None, alpha and beta are set to 0.0 (no silent failure)." This is correct behavior
given no benchmark data is available. The fix is to fetch benchmark data.

**Benchmark fetch logic:** `dashboard/app.py:_fetch_benchmark_returns()` already implements the
exact logic needed — download SPY and IWM via yfinance, return a `dict[str, pd.Series]`. The CLI
needs this same logic extracted or duplicated, then SPY's return series passed as `benchmark=` to
`MetricsEngine.compute()`.

**Implementation pattern:**
```python
# After Stage 4 (simulate), before Stage 5 (metrics):
start_str = str(portfolio_result.net_returns.index[0].date())
end_str = str(portfolio_result.net_returns.index[-1].date())
benchmark_returns: pd.Series | None = None
try:
    spy_df = yf.download("SPY", start=start_str, end=end_str,
                          progress=False, auto_adjust=True)
    if not spy_df.empty:
        benchmark_returns = spy_df["Close"].squeeze().pct_change().dropna()
except Exception:
    _log.warning("benchmark_fetch_failed", ticker="SPY")

# Stage 5: Compute risk metrics
bundle = MetricsEngine().compute(portfolio_result, benchmark=benchmark_returns)
```

**MetricsEngine alignment:** `MetricsEngine.compute()` already handles benchmark alignment via
`aligned_bm = benchmark.reindex(returns.index).fillna(0.0)`. No changes needed to the engine.

**Import:** Add `import yfinance as yf` to `cli.py` (it is not currently imported there; yfinance
is already a project dependency).

---

## Architecture Patterns

### Shared Pipeline Helper (for FIX-02, FIX-03)

Both `run()` and `export()` (after FIX-03) will execute the same 5-stage pipeline:
1. `AiWashingLoader.load()` — signal from DB
2. `PriceBarRepository.get_bars()` — price bars from DB
3. `SignalAdapter().adapt(signal_frame)` — weights
4. `PortfolioSimulator().simulate(weight_frame, price_frame)` — PortfolioResult
5. `MetricsEngine().compute(portfolio_result, benchmark=benchmark_returns)` — MetricsBundle

Extract this into a private helper function `_run_pipeline(session, _log) -> tuple[PortfolioResult, MetricsBundle]` in `cli.py`. Both `run()` and `export()` call it. This avoids code duplication and ensures the date-intersection fix (FIX-02) and benchmark fix (FIX-05) automatically apply to both commands.

### Dashboard Live Mode Seam

The dashboard's `main()` function should call a new helper `_load_data()` that dispatches to either
`_load_live_data()` or `_load_demo_data()` based on environment variable presence. This keeps the
demo-mode fallback intact and avoids making `main()` structurally complex.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Benchmark fetch | Custom HTTP client for SPY data | `yf.download("SPY", ...)` (already in `dashboard/app.py`) | Pattern already implemented and tested; yfinance is pinned dependency |
| Date intersection | Custom overlap algorithm | `signal_frame.index.intersection(price_frame.index)` | pandas Index.intersection is the idiomatic, vectorized approach |
| Dashboard caching | Manual module-level cache dict | `@st.cache_data` | Already used for `_load_demo_data()`; Streamlit session-scoped cache |
| Sector map from DB | ORM query scaffold | `session.query(UniverseTicker).filter_by(is_active=True)` | Pattern already in `universe_app.status()` command in `cli.py` |

---

## Common Pitfalls

### Pitfall 1: Double-Shift After Intersection
**What goes wrong:** If FIX-02 intersects `signal_frame.index` with `price_frame.index` and then
the intersected `signal_frame` is passed to `SignalAdapter.adapt()`, the shift(1) inside the
adapter is still applied exactly once. This is correct. The risk is accidentally re-applying
`shift(1)` manually before calling `adapt()` in the belief that the intersection removed the shift.
**Prevention:** Never apply `shift(1)` to the signal in `cli.py`. The adapter owns the shift.
`STATE.md` decision (Phase 3): "shift(1) is the final step in SignalAdapter.adapt() — Phase 4
Portfolio Simulator must NOT apply an additional shift."

### Pitfall 2: Streamlit @st.cache_data with SQLAlchemy Objects
**What goes wrong:** `@st.cache_data` cannot serialize SQLAlchemy `Session` objects or ORM model
instances. Passing a session into a cached function will raise a `CacheError`.
**Prevention:** Inside `_load_live_data()`, create a new engine and session inside the cached
function (not passed as argument). Use `load_app_settings()` and `create_engine_from_settings()`
the same way `backtest run` does. Return only plain Python objects (DataFrames, MetricsBundle,
dicts) from the cached function.

### Pitfall 3: Dashboard Crashes When DATABASE_URL Is Missing
**What goes wrong:** If `_load_live_data()` calls `load_app_settings()` and
`FUND_BACKTEST_DATABASE_URL` is not set, Pydantic raises `ValidationError` and the entire
dashboard fails to render.
**Prevention:** Wrap `load_app_settings()` in a try/except at the top of `_load_live_data()`.
On `ValidationError`, return `None` and let `_load_data()` fall back to demo mode.

### Pitfall 4: yfinance Import in cli.py Breaks Tests
**What goes wrong:** Adding `import yfinance as yf` at the module level in `cli.py` can cause
test failures if yfinance is not installed in the test environment or if tests mock `cli` imports.
**Prevention:** yfinance is already a project dependency in `pyproject.toml`; this is not a concern.
The existing test in `cli.py` already mocks at the `fund_backtest.cli.*` namespace. Adding yfinance
does not break any existing mock targets.

### Pitfall 5: FIX-03 export Runs the Pipeline Twice
**What goes wrong:** If `export` and `run` are both implemented with the full pipeline, a user who
runs `run --export-all` AND then `export --all` will run the pipeline twice. This is slow but
correct (idempotent).
**Prevention:** Document in the `export` command help text: "For efficiency, use `backtest run
--export-all` to generate all outputs in a single pass. The `export` command is for re-running
exports after the fact."

---

## Code Examples

### FIX-02: Date Intersection (verified pattern)
```python
# Source: pandas Index.intersection documentation + existing simulator._align_frames()
# Insert in cli.py run() after price_frame is built, before SignalAdapter().adapt()
common_dates = signal_frame.index.intersection(price_frame.index)
if len(common_dates) == 0:
    console.print("[red]Error: Signal and price data share no overlapping dates.[/red]")
    raise typer.Exit(code=1)
if len(common_dates) < len(signal_frame.index):
    _log.warning(
        "signal_price_date_mismatch",
        signal_dates=len(signal_frame.index),
        price_dates=len(price_frame.index),
        common_dates=len(common_dates),
    )
signal_frame = signal_frame.loc[common_dates]
```

### FIX-05: Benchmark Fetch in CLI (verified pattern — mirrors dashboard/app.py)
```python
# Source: backtest/src/fund_backtest/dashboard/app.py:_fetch_benchmark_returns()
import yfinance as yf  # add to cli.py imports

# In run() after Stage 4, before Stage 5:
benchmark_returns: pd.Series | None = None
try:
    spy_df = yf.download(
        "SPY",
        start=str(portfolio_result.net_returns.index[0].date()),
        end=str(portfolio_result.net_returns.index[-1].date()),
        progress=False,
        auto_adjust=True,
    )
    if not spy_df.empty:
        benchmark_returns = spy_df["Close"].squeeze().pct_change().dropna()
except Exception:
    _log.warning("benchmark_fetch_failed", ticker="SPY")

bundle = MetricsEngine().compute(portfolio_result, benchmark=benchmark_returns)
```

### FIX-04: Live Mode Detection (Streamlit pattern)
```python
# Source: existing _load_demo_data() pattern + STATE.md FUND_BACKTEST_DATABASE_URL convention
import os
from pydantic import ValidationError

@st.cache_data
def _load_live_data() -> tuple[PortfolioResult, MetricsBundle, dict[str, str]] | None:
    """Run the backtest pipeline and return real results + sector map.
    Returns None if DATABASE_URL is not configured or pipeline fails.
    """
    if not os.environ.get("FUND_BACKTEST_DATABASE_URL"):
        return None
    try:
        from fund_backtest.config import load_app_settings
        from fund_backtest.db.session import create_engine_from_settings, get_session_factory
        # ... run full 5-stage pipeline ...
        # ... query UniverseTicker for sector map ...
        return result, bundle, ticker_sectors
    except Exception as exc:
        logger.warning("live_data_load_failed", error=str(exc))
        return None
```

---

## Environment Availability

Step 2.6: All dependencies are existing project dependencies. No external tools required.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| yfinance | FIX-05 benchmark fetch | Already project dependency | Pinned in pyproject.toml | benchmark=None (alpha/beta=0.0) |
| PostgreSQL | FIX-03, FIX-04 | Managed by Phase 9/10 Docker Compose | 16 | demo mode fallback in dashboard |
| pandas | All fixes | Project dependency | 3.x (pinned) | — |

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0+ |
| Config file | `backtest/pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `cd backtest && uv run pytest tests/ -x -q` |
| Full suite command | `cd backtest && uv run pytest tests/ --cov=fund_backtest --cov-report=term-missing` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FIX-02 | Date intersection produces common-date-only signal_frame | unit | `pytest tests/test_cli.py -k "test_run_date_intersection" -x` | ❌ Wave 0 |
| FIX-03 | export --signal runs pipeline, not demo stubs | unit | `pytest tests/test_cli.py -k "test_export_live" -x` | ❌ Wave 0 |
| FIX-04 | Dashboard live mode: manual-only | manual | N/A — dashboard excluded from coverage omit | manual-only |
| FIX-05 | benchmark_returns passed to MetricsEngine | unit | `pytest tests/test_cli.py -k "test_run_benchmark" -x` | ❌ Wave 0 |

**FIX-04 manual-only justification:** `dashboard/app.py` is in the pytest coverage omit list per
Phase 7 decision. Streamlit UI cannot be unit-tested. Verification is a visual smoke test: run
`streamlit run backtest/src/fund_backtest/dashboard/app.py` with `FUND_BACKTEST_DATABASE_URL` set
and confirm "Live mode" banner appears with real equity curve.

### Sampling Rate
- **Per task commit:** `cd backtest && uv run pytest tests/ -x -q`
- **Per wave merge:** `cd backtest && uv run pytest tests/ --cov=fund_backtest --cov-report=term-missing`
- **Phase gate:** Full suite green + coverage >= 80% before phase completion

### Wave 0 Gaps
- [ ] `backtest/tests/test_cli.py` — add `test_run_date_intersection`, `test_export_live`,
  `test_run_benchmark` test cases. Existing `test_cli.py` may already have the file — new test
  functions to be added in Wave 0.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Demo-only `backtest export` | Add `--signal` to run real pipeline | Phase 12 | `export` becomes useful post-v1.0 |
| alpha=0.0, beta=0.0 in CLI | Fetch SPY benchmark in CLI run path | Phase 12 | Tearsheets show real benchmark comparison |
| Dashboard always demo mode | Live mode when DATABASE_URL set | Phase 12 | Investor dashboard shows real SEC-data results |

**Deprecated/outdated patterns after this phase:**
- `make_demo_result()` / `make_demo_bundle()` usage in `cli.py:export()`: replaced by real pipeline
- `DEMO_TICKER_SECTORS` usage in `dashboard/app.py:main()`: replaced by DB query (with demo fallback)

---

## Open Questions

1. **Should `backtest export` keep a demo fallback or always require `--signal`?**
   - What we know: Current `export` command works without DB connection (useful for testing tearsheet formatting)
   - What's unclear: Whether keeping the demo fallback creates confusion once live mode exists
   - Recommendation: Keep demo fallback when `--signal` is omitted; log a deprecation warning

2. **Which benchmark series to pass to MetricsEngine: SPY only, or combined SPY+IWM?**
   - What we know: `MetricsEngine.compute()` accepts a single `pd.Series` as `benchmark=`; dashboard fetches both SPY and IWM but uses them separately for chart overlays, not for greeks
   - What's unclear: Whether SPY (S&P 500) or IWM (Russell 2000) is the more appropriate benchmark for mid-cap short signals
   - Recommendation: Use SPY for alpha/beta (most standard for fund reporting); document the choice in CLI output

3. **Dashboard live mode: run the pipeline on every page load, or require a pre-computed artifact?**
   - What we know: The full pipeline takes < 15 seconds; `@st.cache_data` ensures it runs once per session
   - What's unclear: Whether 15-second first-load is acceptable for investor demos
   - Recommendation: Run pipeline in `_load_live_data()` with `@st.cache_data` — acceptable for v1.1; cached after first load

---

## Sources

### Primary (HIGH confidence)
- Direct inspection: `backtest/src/fund_backtest/cli.py` — `run()` and `export()` commands
- Direct inspection: `backtest/src/fund_backtest/dashboard/app.py` — `main()` and `_load_demo_data()`
- Direct inspection: `backtest/src/fund_backtest/metrics/engine.py` — `MetricsEngine.compute()`
- Direct inspection: `backtest/src/fund_backtest/simulator/engine.py` — `_align_frames()`
- Direct inspection: `backtest/src/fund_backtest/signal/adapter.py` — `adapt()` shift(1) location
- Direct inspection: `backtest/src/fund_backtest/signal/loaders/ai_washing.py` — `AiWashingLoader`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md` — INTG-01, INTG-02, tech debt items
- `.planning/research/FEATURES.md` — v1.1 live mode features and tech debt table
- `.planning/STATE.md` — Phase 3/5/8 decisions that constrain this phase

### Secondary (MEDIUM confidence)
- `.planning/REQUIREMENTS.md` — FIX-02 through FIX-05 requirement definitions
- `.planning/research/PITFALLS.md` — date alignment and look-ahead bias pitfalls

---

## Metadata

**Confidence breakdown:**
- Bug root causes: HIGH — found exact lines in source files
- Fix approaches: HIGH — patterns borrowed from existing working code in same codebase
- Test requirements: HIGH — existing test infrastructure identified; new test cases are additions
- Dashboard live mode: MEDIUM — design pattern is sound but Streamlit session caching behavior with SQLAlchemy needs care

**Research date:** 2026-03-30
**Valid until:** This research is based on a point-in-time snapshot of the codebase. Valid as long as
`cli.py`, `dashboard/app.py`, and `metrics/engine.py` have not been modified since the research date.
Estimate: stable for 30+ days given the phase is self-contained.
