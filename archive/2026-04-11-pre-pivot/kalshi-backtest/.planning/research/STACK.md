# Technology Stack

**Project:** Kalshi Prediction Market Backtesting Engine
**Researched:** 2026-04-04
**Mode:** Ecosystem research

---

## Recommended Stack

### Kalshi API Client

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `kalshi-python` (official) | 2.1.4 | Primary REST API client for market data, historical trades, event resolution | Official Kalshi-maintained SDK. Uses RSA-PSS authentication. Covers `/markets`, `/events`, `/historical/*` endpoints. Requires Python >=3.9. Released Sep 2025. |

**Confidence:** MEDIUM — PyPI listing confirmed version 2.1.4 (Sep 2025). Official docs at `docs.kalshi.com` confirm SDK existence. However, the SDK's historical endpoint coverage was not directly verified since WebFetch was unavailable; rely on the REST endpoints directly if the SDK lags.

**Important caveat on the SDK:** Kalshi is migrating all data older than a cutoff date to dedicated `/historical/*` endpoints (removal of historical data from live API targeted for March 2026 per search results). The `kalshi-python` package may not yet have full wrappers for these endpoints. Plan to call the historical REST endpoints directly via `httpx` where the SDK falls short.

**Why NOT `aiokalshi` or community wrappers:** These are unmaintained or experimental. For a backtesting engine that calls the API in bulk during data ingestion (not real-time), the async advantage of `aiokalshi` is marginal. Stick with the official sync SDK and fall back to `httpx` for gaps.

**Why NOT `KalshiPythonClient` (AndrewNolte):** Useful reference implementation but not published to PyPI as a stable package. Use official SDK instead.

---

### HTTP Client (Fallback for Raw API Calls)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `httpx` | 0.28.1+ | Direct REST calls to Kalshi historical endpoints not yet in SDK | Already in fund's dependency set (used by Insider Tracker). Supports both sync and async. Clean interface, good timeout/retry support. |
| `tenacity` | 9.1.4+ | Retry logic with exponential backoff on rate-limited API calls | Already in fund's dependency set. Kalshi imposes rate limits — retries are mandatory. |

**Confidence:** HIGH — Both are battle-tested and already in the fund's uv.lock.

---

### Data Storage

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `duckdb` | 1.x (latest stable) | Local analytical store for historical Kalshi contract snapshots | Columnar storage ideal for time-series analytical queries (aggregations, window functions, slicing by event/date). Outperforms SQLite 8x on analytical workloads. Zero-copy integration with pandas DataFrames. Single-file database — no server to spin up. Append-only inserts trivially enforced: never UPDATE or DELETE rows. |

**Confidence:** MEDIUM-HIGH — DuckDB's superiority for analytical/OLAP workloads over SQLite is well-documented across multiple 2025 sources. However, we are NOT using PostgreSQL here (unlike the equities module) because this engine is standalone and local. DuckDB eliminates server infrastructure entirely, which is correct for a local backtesting tool.

**Why NOT PostgreSQL:** The equities backtest uses PostgreSQL for multi-user, production-grade storage. This engine is explicitly standalone and local — PostgreSQL adds operational overhead for no benefit. DuckDB is the right embedded analytical database.

**Why NOT SQLite:** SQLite is row-oriented (OLTP). Querying 1 year of tick-level Kalshi data with time-range slices and aggregations will be substantially slower than DuckDB's columnar scans.

**Why NOT Parquet files directly:** Parquet is excellent for archival but lacks transactional semantics for append tracking and is harder to query interactively without a query engine layer. DuckDB can query Parquet natively if needed — treat Parquet as an optional export format.

**Schema notes for Kalshi binary contracts:**
- Markets table: `ticker`, `event_ticker`, `series_ticker`, `market_type`, `yes_sub_title`, `no_sub_title`, `open_time`, `close_time`, `expiration_time`, `result` (YES/NO/VOID), `status`
- Candlesticks/prices table: `ticker`, `ts` (UTC), `yes_price_cents`, `no_price_cents`, `volume`, `open_interest` — append-only, never overwrite
- Trades table: `ticker`, `trade_id`, `ts`, `yes_price_cents`, `count`, `taker_side` — append-only

---

### Backtesting Engine

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Custom vectorized engine (pandas + numpy) | — | Signal replay against historical Kalshi price series | No existing framework handles binary event contract semantics out of the box. VectorBT and backtesting.py assume continuous instruments with OHLCV bars and fractional positions. Kalshi contracts: binary payoffs ($0 or $1), minimum tick $0.01, position is integer contracts, P&L is either full price gain or total loss. Custom engine is ~300 lines and gives full control over contract resolution logic. |
| `pandas` | 2.x | Time-indexed price series, signal alignment, trade log construction | Industry standard. DuckDB outputs to pandas DataFrames directly. |
| `numpy` | 1.x / 2.x | Vectorized P&L computation, metric calculations | Fast array operations for large backtests. |

**Confidence:** HIGH for the "build custom" recommendation. MEDIUM for the specific approach.

**Why NOT VectorBT:** VectorBT is excellent for equities. For Kalshi, the contract lifecycle is: buy at price P, then either (a) sell before expiration at Q (P&L = Q - P per contract) or (b) hold to resolution (P&L = 1.0 - P if YES wins, -P if NO wins). This binary resolution mechanic does not map cleanly onto VectorBT's continuous position model. Forcing it creates fragile workarounds that are harder to maintain than a custom 300-line engine.

**Why NOT NautilusTrader (evan-kolberg fork):** NautilusTrader is production-grade but extremely heavy. The fork is pre-release, unstable, and requires Rust compilation. For a backtesting research tool on ~1 year of daily data, this is massive over-engineering. The signal-based strategy interface this project needs (implement `generate_signals()`) is simpler to design cleanly from scratch.

**Why NOT backtesting.py:** Designed for OHLCV bars with continuous instruments. No native support for binary resolution events.

---

### Metrics and Analytics

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `quantstats` | 0.0.x (latest) | P&L tearsheet generation — Sharpe, Sortino, max drawdown, win rate, CAGR, Calmar | Battle-tested portfolio analytics library for Python quants. Generates HTML tearsheets and matplotlib plots. Sharpe/drawdown computations are well-validated. |
| Custom metrics module | — | Prediction-market-specific metrics: edge per contract, Kelly fraction, expected value, contract resolution rate | These do not exist in quantstats. Binary contract math: EV = p_true × (1 - entry_price) - (1 - p_true) × entry_price. Must be implemented in the project. |

**Confidence:** HIGH for quantstats (well-established, actively maintained). HIGH for custom metrics (necessary gap given binary contract specifics).

---

### Visualization

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `plotly` | 5.x | Interactive equity curve, trade markers, performance charts | Gold standard for interactive Python trading dashboards. Works in Jupyter and can export static HTML. Better interactivity than matplotlib for time-series inspection. |
| `plotly.express` | (bundled with plotly) | Quick-build performance charts (monthly returns heatmap, P&L histogram) | 3-line charts vs 30-line matplotlib equivalents. |

**Confidence:** MEDIUM-HIGH — Plotly dominates the 2025 Python trading dashboard ecosystem per search results. Dash is the natural next step if an interactive web UI is ever needed (but out of scope for v1).

**Why NOT matplotlib alone:** Static plots only. Fine for tearsheets but inadequate for interactive exploration of trade timing vs. contract price. Use matplotlib indirectly via quantstats for tearsheets; use plotly for interactive dashboard.

**Why NOT Bokeh:** Plotly has overtaken Bokeh as the preferred interactive finance charting library. Larger community, better documentation.

---

### Data Validation

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pydantic` | 2.x | Contract data models, API response validation, strategy config schema | Already in fund's dependency set. Type-safe deserialization of Kalshi API responses. Catches API shape changes at the boundary before corrupt data reaches the store. |

**Confidence:** HIGH — Already fund-wide standard.

---

### CLI

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `typer` | 0.24.1+ | CLI commands: `ingest`, `backtest`, `compare`, `dashboard` | Already in fund's dependency set (Insider Tracker uses Typer). Consistent DX across the fund. |

**Confidence:** HIGH — Already fund-wide standard.

---

### Testing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pytest` | 9.x | Test framework | Already in fund's dependency set. |
| `pytest-cov` | latest | Coverage reporting | Enforce 80% coverage gate per fund-wide rules. |
| Fixture-based mock API responses | — | Test data ingestion without hitting Kalshi API | Record real API responses as JSON fixtures; replay in tests. No live API needed for CI. |

**Confidence:** HIGH — Already fund-wide standard.

---

### Package Management

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `uv` | latest | Dependency management and virtual env | Fund-wide standard. `pyproject.toml` + `uv.lock` for reproducibility. |
| `ruff` | 0.15+ | Linting and formatting | Fund-wide standard. |

**Confidence:** HIGH — Explicitly specified in PROJECT.md constraints.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| API client | `kalshi-python` 2.1.4 (official) | `aiokalshi`, `kalshi-py`, `KalshiPythonClient` | Community wrappers have no maintenance guarantees; official SDK is Kalshi-backed |
| Data storage | DuckDB | PostgreSQL, SQLite, Parquet | Postgres overkill for standalone local tool; SQLite is OLTP-oriented and slower for analytics; Parquet lacks query interface |
| Backtesting | Custom vectorized engine | VectorBT, NautilusTrader, backtesting.py | None handle binary contract resolution semantics; custom engine is ~300 lines and gives full control |
| Visualization | Plotly | Matplotlib, Bokeh, Dash | Matplotlib is static; Bokeh is declining; Dash adds web server complexity unnecessary for v1 |
| Metrics | quantstats + custom | pyfolio (deprecated) | pyfolio unmaintained since 2021; quantstats is the active successor |

---

## Installation

```bash
# Core runtime dependencies
uv add kalshi-python httpx tenacity duckdb pydantic typer structlog rich

# Analytics and visualization
uv add pandas numpy plotly quantstats

# Dev/test
uv add --dev pytest pytest-cov ruff
```

---

## Key Constraints From Project.md

- Python 3.11+ (use 3.12 to match existing fund infrastructure)
- `uv` package manager
- Append-only data semantics — DuckDB enforced by never running UPDATE/DELETE on price tables
- Standalone module — no hard imports from `Kalshi Insider Tracker/` internals
- Kalshi API only — no yfinance or third-party data providers

---

## Open Questions (Needs Verification at Implementation Time)

1. **Kalshi SDK historical endpoint coverage:** Verify which `/historical/*` endpoints `kalshi-python` 2.1.4 actually wraps. If coverage is incomplete, use `httpx` directly for `GET /historical/markets/{ticker}`, `GET /historical/trades`, and `GET /historical/candlesticks`.

2. **Kalshi historical data depth:** The API serves ~1 year of data per PROJECT.md goals. Verify actual date range available from `GET /historical/cutoff`. Data volume should be manageable in DuckDB on a laptop.

3. **Kalshi rate limits for bulk ingestion:** Rate limit specifics not confirmed from search results. Implement tenacity retry from the start. Expect to need `time.sleep()` between paginated requests.

4. **quantstats compatibility with binary contract equity curves:** quantstats expects a daily returns series (floating point). For Kalshi, compute daily portfolio value from open positions — this is straightforward but needs careful handling of contracts that expire mid-backtest.

---

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
