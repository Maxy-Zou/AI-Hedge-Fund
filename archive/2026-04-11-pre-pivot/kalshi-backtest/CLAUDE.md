<!-- GSD:project-start source:PROJECT.md -->
## Project

**Kalshi Backtesting Engine**

A strategy-agnostic backtesting engine for Kalshi prediction markets. Pulls historical contract data from the Kalshi API, replays trading signals against actual price movements, and produces P&L metrics, trade logs, visual dashboards, and strategy comparisons. Designed with a plugin interface so any future Kalshi strategy — not just insider tracking — can be backtested by implementing a simple Strategy protocol.

**Core Value:** Accurately simulate any Kalshi trading strategy against historical data so you can validate signal quality and optimize parameters before risking real capital.

### Constraints

- **Data source**: Kalshi API only — no third-party data providers for v1
- **Stack**: Python 3.11+, uv — consistent with existing fund infrastructure
- **Immutability**: Historical contract data must never be overwritten — append new snapshots only (fund-wide convention)
- **Independence**: Must work as a standalone module — no hard dependency on Insider Tracker internals (communicate via the Strategy plugin interface)
- **History**: ~1 year lookback (configurable per backtest run)
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Kalshi API Client
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `kalshi-python` (official) | 2.1.4 | Primary REST API client for market data, historical trades, event resolution | Official Kalshi-maintained SDK. Uses RSA-PSS authentication. Covers `/markets`, `/events`, `/historical/*` endpoints. Requires Python >=3.9. Released Sep 2025. |
### HTTP Client (Fallback for Raw API Calls)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `httpx` | 0.28.1+ | Direct REST calls to Kalshi historical endpoints not yet in SDK | Already in fund's dependency set (used by Insider Tracker). Supports both sync and async. Clean interface, good timeout/retry support. |
| `tenacity` | 9.1.4+ | Retry logic with exponential backoff on rate-limited API calls | Already in fund's dependency set. Kalshi imposes rate limits — retries are mandatory. |
### Data Storage
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `duckdb` | 1.x (latest stable) | Local analytical store for historical Kalshi contract snapshots | Columnar storage ideal for time-series analytical queries (aggregations, window functions, slicing by event/date). Outperforms SQLite 8x on analytical workloads. Zero-copy integration with pandas DataFrames. Single-file database — no server to spin up. Append-only inserts trivially enforced: never UPDATE or DELETE rows. |
- Markets table: `ticker`, `event_ticker`, `series_ticker`, `market_type`, `yes_sub_title`, `no_sub_title`, `open_time`, `close_time`, `expiration_time`, `result` (YES/NO/VOID), `status`
- Candlesticks/prices table: `ticker`, `ts` (UTC), `yes_price_cents`, `no_price_cents`, `volume`, `open_interest` — append-only, never overwrite
- Trades table: `ticker`, `trade_id`, `ts`, `yes_price_cents`, `count`, `taker_side` — append-only
### Backtesting Engine
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Custom vectorized engine (pandas + numpy) | — | Signal replay against historical Kalshi price series | No existing framework handles binary event contract semantics out of the box. VectorBT and backtesting.py assume continuous instruments with OHLCV bars and fractional positions. Kalshi contracts: binary payoffs ($0 or $1), minimum tick $0.01, position is integer contracts, P&L is either full price gain or total loss. Custom engine is ~300 lines and gives full control over contract resolution logic. |
| `pandas` | 2.x | Time-indexed price series, signal alignment, trade log construction | Industry standard. DuckDB outputs to pandas DataFrames directly. |
| `numpy` | 1.x / 2.x | Vectorized P&L computation, metric calculations | Fast array operations for large backtests. |
### Metrics and Analytics
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `quantstats` | 0.0.x (latest) | P&L tearsheet generation — Sharpe, Sortino, max drawdown, win rate, CAGR, Calmar | Battle-tested portfolio analytics library for Python quants. Generates HTML tearsheets and matplotlib plots. Sharpe/drawdown computations are well-validated. |
| Custom metrics module | — | Prediction-market-specific metrics: edge per contract, Kelly fraction, expected value, contract resolution rate | These do not exist in quantstats. Binary contract math: EV = p_true × (1 - entry_price) - (1 - p_true) × entry_price. Must be implemented in the project. |
### Visualization
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `plotly` | 5.x | Interactive equity curve, trade markers, performance charts | Gold standard for interactive Python trading dashboards. Works in Jupyter and can export static HTML. Better interactivity than matplotlib for time-series inspection. |
| `plotly.express` | (bundled with plotly) | Quick-build performance charts (monthly returns heatmap, P&L histogram) | 3-line charts vs 30-line matplotlib equivalents. |
### Data Validation
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pydantic` | 2.x | Contract data models, API response validation, strategy config schema | Already in fund's dependency set. Type-safe deserialization of Kalshi API responses. Catches API shape changes at the boundary before corrupt data reaches the store. |
### CLI
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `typer` | 0.24.1+ | CLI commands: `ingest`, `backtest`, `compare`, `dashboard` | Already in fund's dependency set (Insider Tracker uses Typer). Consistent DX across the fund. |
### Testing
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pytest` | 9.x | Test framework | Already in fund's dependency set. |
| `pytest-cov` | latest | Coverage reporting | Enforce 80% coverage gate per fund-wide rules. |
| Fixture-based mock API responses | — | Test data ingestion without hitting Kalshi API | Record real API responses as JSON fixtures; replay in tests. No live API needed for CI. |
### Package Management
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `uv` | latest | Dependency management and virtual env | Fund-wide standard. `pyproject.toml` + `uv.lock` for reproducibility. |
| `ruff` | 0.15+ | Linting and formatting | Fund-wide standard. |
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| API client | `kalshi-python` 2.1.4 (official) | `aiokalshi`, `kalshi-py`, `KalshiPythonClient` | Community wrappers have no maintenance guarantees; official SDK is Kalshi-backed |
| Data storage | DuckDB | PostgreSQL, SQLite, Parquet | Postgres overkill for standalone local tool; SQLite is OLTP-oriented and slower for analytics; Parquet lacks query interface |
| Backtesting | Custom vectorized engine | VectorBT, NautilusTrader, backtesting.py | None handle binary contract resolution semantics; custom engine is ~300 lines and gives full control |
| Visualization | Plotly | Matplotlib, Bokeh, Dash | Matplotlib is static; Bokeh is declining; Dash adds web server complexity unnecessary for v1 |
| Metrics | quantstats + custom | pyfolio (deprecated) | pyfolio unmaintained since 2021; quantstats is the active successor |
## Installation
# Core runtime dependencies
# Analytics and visualization
# Dev/test
## Key Constraints From Project.md
- Python 3.11+ (use 3.12 to match existing fund infrastructure)
- `uv` package manager
- Append-only data semantics — DuckDB enforced by never running UPDATE/DELETE on price tables
- Standalone module — no hard imports from `Kalshi Insider Tracker/` internals
- Kalshi API only — no yfinance or third-party data providers
## Open Questions (Needs Verification at Implementation Time)
## Sources
- [kalshi-python on PyPI](https://pypi.org/project/kalshi-python/) — version 2.1.4, Sep 2025
- [Kalshi Historical Data API docs](https://docs.kalshi.com/getting_started/historical_data) — partition into live/historical tiers, cutoff endpoint
- [Kalshi Python SDK Quickstart](https://docs.kalshi.com/sdks/python/quickstart) — official SDK docs
- [Kalshi API Rate Limits](https://docs.kalshi.com/getting_started/rate_limits) — official rate limit docs
- [evan-kolberg/prediction-market-backtesting](https://github.com/evan-kolberg/prediction-market-backtesting) — NautilusTrader fork with Kalshi adapter (pre-release, not recommended for use but confirms the ecosystem gap)
- [VectorBT docs](https://vectorbt.dev/) — confirms strong equity focus, custom workarounds needed for binary contracts
- [DuckDB vs SQLite comparison (BetterStack)](https://betterstack.com/community/guides/scaling-python/duckdb-vs-sqlite/) — 8x analytical performance advantage
- [DuckDB for Time Series (Medium)](https://medium.com/@shouke.wei/duckdb-for-time-series-is-it-a-good-open-source-tsdb-ff76bc1c71d9) — confirms DuckDB window functions, append-only patterns
- [quantstats on GitHub](https://github.com/ranaroussi/quantstats) — actively maintained, Apache license
- [Plotly Dash trading dashboards (PyQuantNews)](https://www.pyquantnews.com/free-python-resources/building-interactive-trading-dashboards-with-python) — 2025 best practices
- [Kelly Criterion in Prediction Markets (arXiv)](https://arxiv.org/html/2412.14144v1) — confirms custom metric implementation needed
- [Kalshi binary contract mechanics (Medium)](https://medium.com/@mgoelzer/kalshi-market-mechanics-9f4bdec45e84) — YES/NO pricing, $1 settlement
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
