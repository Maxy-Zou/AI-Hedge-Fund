# Technology Stack: Backtesting Infrastructure

**Project:** Shared Backtesting Infrastructure
**Researched:** 2026-03-28
**Overall confidence:** MEDIUM-HIGH

---

## Recommended Stack

### Backtesting Engine

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| vectorbt | >=0.28.5 | Vectorized backtesting engine | pandas/NumPy-native, Numba-accelerated. `Portfolio.from_signals()` accepts signal DataFrames directly — maps perfectly to the fund's "date x ticker → score" contract. Simulates 1M orders in 70-100ms on Apple M1. Open-source, no subscription. Version 0.28.5 released March 2026. |

**NOT** vectorbt PRO: PRO is invite-only, paid ($20/month), closed-source. The open-source version covers all requirements — `from_signals`, short positions, transaction costs, borrow costs, frequency='d'. PRO is only needed for parameter grid searches at massive scale, which is not a requirement here.

**NOT** backtesting.py (0.6.5): Single-asset oriented, event-loop based under the hood, not designed for 200-500 ticker universes. Good for prototyping a single strategy, wrong for a multi-ticker daily portfolio simulation.

**NOT** Zipline-Reloaded: Requires a Zipline data bundle (non-trivial setup), tightly coupled to Quantopian-era patterns, harder to feed arbitrary signal DataFrames into. Overkill for a custom signal interface.

### Market Data

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| yfinance | >=1.2.0 | Daily OHLCV price data for mid-cap universe | Free, no API key, daily OHLCV for any equity. Version 1.0 released stable (no breaking changes from 0.2.x). v1.2.0 is current as of February 2026. `yf.download()` bulk API handles multi-ticker downloads in one call. |

**yfinance known limitations (MEDIUM confidence):**
- Rate-limited by Yahoo Finance's undocumented limits — bulk requests beyond ~100 tickers in a single call can trigger 429 errors
- Mitigation: chunk downloads to ~80 tickers, add 1-2s jitter between chunks, cache to PostgreSQL on first pull (incremental updates daily)
- Not an official API — Yahoo could restrict access at any time; no SLA
- Corporate actions adjustment is "best effort" — verify split-adjusted data on ingestion

**NOT** paid providers (Alpha Vantage, Polygon, Tiingo) for v1: project constraint is free data only.

### Data Caching and Storage

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | >=16 | Persistent OHLCV cache + score history + backtest results | Shared with AI Washing Detector (same instance). ACID compliance for append-only financial data. JSONB for flexible backtest metadata. Already in the fund's infrastructure. |
| SQLAlchemy | >=2.0.48 | ORM for price data, backtest runs, trade log | 2.0-style with type annotations. Same version as the Detector — no new dependency. `mapped_column()` declarative models, repository pattern. |
| pandas | >=3.0.1 | DataFrame manipulation for OHLCV and signal matrices | PyArrow backend by default in 3.0. Used as the primary data structure passed between yfinance, vectorbt, and the scoring engine. Same version as the Detector. |

**Partitioning note:** Native PostgreSQL range partitioning on `date` is sufficient for OHLCV at 200-500 tickers x 5 years (~500K rows). TimescaleDB would add value at >10M rows but adds an extension dependency — defer to v2 if query performance degrades.

### Analytics and Metrics

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| quantstats-lumi | >=1.1.0 | Portfolio analytics, risk metrics, HTML tearsheet | Active fork of quantstats, maintained by Lumiwealth. Version 1.1.0 released March 17, 2026. Computes Sharpe, Sortino, max drawdown, Calmar, hit rate, win/loss from a returns Series. `qs.reports.html()` generates a complete HTML tearsheet. Original `quantstats` (0.0.77) has maintenance gaps — use the lumi fork. |
| numpy | >=2.0 | Numerical computation for custom metrics | Required by pandas and vectorbt. Use for score normalization, borrow cost modeling, and statistical operations not covered by quantstats. |

**NOT** pyfolio or pyfolio-reloaded: pyfolio is tightly coupled to Zipline's return format. pyfolio-reloaded is better but still Zipline-centric. quantstats-lumi accepts a plain pandas Series of daily returns — simpler integration.

### Dashboard

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Streamlit | >=1.55.0 | Interactive backtesting dashboard | Already in the fund's stack. Fast to build investor-facing UIs. Version 1.55.0 (March 2026) added dynamic containers. Proven combination with vectorbt and Plotly for equity curves and drawdown charts. |
| plotly | >=6.6.0 | Interactive charts (equity curve, drawdown, rolling metrics) | Version 6.6.0 (March 2026). Native Streamlit integration via `st.plotly_chart()`. Handles time-series financial charts well — hover tooltips, zoom, range selectors. |

**NOT** Dash: More complex setup than Streamlit, no advantage for internal/investor demo tooling. Overkill when Streamlit integration already exists in the project.

### PDF Tearsheet Generation

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| matplotlib | >=3.10 | Chart rendering for PDF tearsheet | `PdfPages` from `matplotlib.backends.backend_pdf` is the lowest-friction path to a multi-page PDF. Each figure becomes a page. Vector output — prints cleanly. No system-level dependencies. |
| WeasyPrint | >=65.0 | (Optional) HTML-to-PDF for polished layout | If the tearsheet needs CSS-styled tables, branding, and complex layout, render Jinja2 HTML template → WeasyPrint → PDF. Requires Pango/Cairo system libraries (Linux install needed). Use this path if the matplotlib-only output looks too plain. |

**Recommended tearsheet approach — two-stage decision:**

1. **Start with matplotlib PdfPages**: Generate charts with matplotlib (equity curve, drawdown, rolling Sharpe, sector breakdown), use `fig.text()` for metric tables, save multi-page PDF. Zero system dependencies, ships fast.
2. **Upgrade to WeasyPrint if branding matters**: Investor-facing factsheets benefit from CSS layout. Render metrics into an HTML template, embed matplotlib PNGs, convert with WeasyPrint. Worth the system dependency if visual polish is required.

**NOT** ReportLab for v1: Low-level PDF drawing API requires positioning every element manually — high implementation cost for modest visual payoff at this stage. Use ReportLab only if layout precision requirements exceed what matplotlib + WeasyPrint can deliver.

### Templating (for WeasyPrint path)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Jinja2 | >=3.1 | HTML templates for WeasyPrint tearsheet | Already a transitive dependency of many packages. Separates data from presentation. Simple variable substitution for metrics tables and chart embedding. |

### Workflow Orchestration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Prefect | >=3.6.23 | Daily data refresh + backtest pipeline scheduling | Already in the fund's stack (AI Washing Detector). Same `@flow`/`@task` pattern. Handles retry logic, caching, and monitoring. The backtester's daily data refresh and signal-to-tearsheet pipeline maps cleanly to a Prefect flow. |

### Resilience

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| tenacity | >=9.1.4 | Retry logic for yfinance downloads | Already in the fund's stack. Exponential backoff with jitter for 429 rate-limit errors from Yahoo Finance. Essential given the documented rate-limit issues with bulk yfinance downloads. |

### Tooling

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| uv | >=0.11.2 | Package management | Consistent with the fund's existing toolchain. |
| ruff | >=0.15.7 | Linting and formatting | Consistent with the fund's existing toolchain. |
| pytest + pytest-cov | >=9.0.2 / >=7.1.0 | Testing | Consistent with the fund's existing toolchain. |
| freezegun | latest | Time mocking in tests | Mock "today's date" for testing daily batch logic and incremental data refresh. Essential for deterministic backtesting tests. |
| factory-boy | latest | Test data factories | Generate realistic OHLCV DataFrames and signal matrices for unit tests without hitting yfinance. |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Backtesting | vectorbt (open-source) | vectorbt PRO | PRO is invite-only, paid, closed-source. Open-source covers all requirements. |
| Backtesting | vectorbt | backtesting.py | Single-asset focus, not designed for multi-ticker portfolio simulation. |
| Backtesting | vectorbt | Zipline-Reloaded | Complex data bundle setup, Zipline-centric signal format, harder integration. |
| Market data | yfinance | Polygon, Tiingo | Paid — project constraint is free data only for v1. |
| Market data | yfinance | pandas-datareader | Unmaintained, Yahoo backend was removed, EOL. |
| Analytics | quantstats-lumi | pyfolio-reloaded | Zipline-centric return format, heavier dependency surface. |
| Analytics | quantstats-lumi | original quantstats | Maintenance gaps, open PRs neglected. Use lumi fork. |
| PDF | matplotlib PdfPages | ReportLab | High implementation cost — manual element positioning for every table/chart. Not worth it for v1. |
| PDF | matplotlib PdfPages | fpdf2 | Similar manual positioning burden as ReportLab without the ecosystem. |
| Dashboard | Streamlit | Plotly Dash | More complex setup, no advantage for internal/investor demo tooling. |
| Storage | plain PostgreSQL | TimescaleDB | Adds extension dependency. At 200-500 tickers x 5 years, native PG is sufficient. Revisit at v2. |

---

## Installation

```bash
# Backtesting + data
uv add vectorbt yfinance pandas numpy

# Database (already in Detector stack)
uv add sqlalchemy asyncpg "psycopg[binary]" alembic

# Analytics
uv add quantstats-lumi

# Dashboard
uv add streamlit plotly

# PDF tearsheet
uv add matplotlib
# Optional: uv add weasyprint jinja2  (if polished layout required)

# Orchestration + resilience (already in Detector stack)
uv add prefect tenacity

# Logging (already in Detector stack)
uv add structlog

# Dev/test
uv add --dev pytest pytest-cov pytest-asyncio factory-boy freezegun ruff
```

---

## Key Integration Contract

The backtester's core input interface:

```python
# Signal DataFrame: rows = dates, columns = tickers, values = AI Washing Risk Score (0-100)
# Higher score = stronger short signal
signals: pd.DataFrame  # shape (trading_days, n_tickers), dtype float64

# Entry: score > threshold → initiate short
# Exit: score < threshold → close short
# Position sizing: configurable (equal weight, score-proportional, risk-parity)
```

vectorbt's `Portfolio.from_signals()` accepts this directly with `short_entries` / `short_exits` boolean masks derived from the signal thresholds. This maps without transformation from the AI Washing Detector's output schema.

---

## Confidence Assessment

| Component | Confidence | Basis |
|-----------|------------|-------|
| vectorbt open-source | HIGH | PyPI v0.28.5 (March 2026), GitHub active, strong community, docs confirm `from_signals` short support |
| yfinance | MEDIUM | PyPI v1.2.0 (Feb 2026), but Yahoo rate limits are undocumented and tightening — 429 errors well-documented on GitHub issues |
| quantstats-lumi | MEDIUM | PyPI v1.1.0 (March 2026), Lumiwealth fork actively maintained, but smaller community than original |
| PostgreSQL + SQLAlchemy | HIGH | Same as Detector stack, verified, production-grade |
| Streamlit + Plotly | HIGH | Streamlit 1.55.0 + Plotly 6.6.0 both released March 2026, verified on PyPI, well-documented |
| matplotlib PdfPages (PDF) | HIGH | Matplotlib 3.10.x, official docs, zero system dependencies, vector output |
| WeasyPrint (optional PDF) | MEDIUM | Active library, but requires Pango/Cairo system libs — Linux CI setup adds friction |
| Prefect | HIGH | Same as Detector stack, verified |

---

## Sources

- [vectorbt PyPI](https://pypi.org/project/vectorbt/) — v0.28.5, March 26 2026
- [vectorbt GitHub](https://github.com/polakowo/vectorbt) — open-source, MIT-compatible
- [vectorbt docs: Portfolio.from_signals](https://vectorbt.dev/api/portfolio/base/) — signal-based simulation API
- [yfinance PyPI](https://pypi.org/project/yfinance/) — v1.2.0, February 2026
- [yfinance rate limit issues #2614](https://github.com/ranaroussi/yfinance/issues/2614) — documented 429 errors on bulk download
- [quantstats-lumi PyPI](https://pypi.org/project/quantstats-lumi/) — v1.1.0, March 17 2026
- [quantstats-lumi GitHub](https://github.com/Lumiwealth/quantstats_lumi) — Lumiwealth fork
- [Streamlit PyPI](https://pypi.org/project/streamlit/) — v1.55.0, March 2026
- [Plotly PyPI](https://pypi.org/project/plotly/) — v6.6.0, March 2026
- [Matplotlib multipage PDF docs](https://matplotlib.org/stable/gallery/misc/multipage_pdf.html) — official PdfPages guide
- [WeasyPrint vs ReportLab comparison](https://dev.to/claudeprime/generate-pdfs-in-python-weasyprint-vs-reportlab-ifi)
- [vectorbt + Streamlit backtesting app pattern](https://github.com/marketcalls/VectorBT-Streamlit) — community reference implementation
