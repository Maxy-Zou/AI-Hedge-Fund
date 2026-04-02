<!-- GSD:project-start source:PROJECT.md -->
## Project

**Kalshi Insider Tracker**

An automated system that monitors Kalshi politics/policy prediction markets for abnormal trading activity suggestive of insider knowledge, then copies those trades in real-time. It detects volume spikes, sharp price moves, win streaks, and suspicious timing clusters — then auto-executes the same directional bet with conservative position limits.

**Core Value:** Detect and copy insider-like trades on Kalshi politics/policy markets before the event resolves — turning information asymmetry detection into profit.

### Constraints

- **Data source**: Kalshi public API only — no scraping, no third-party data providers for v1
- **Polling**: 5-10 second intervals — not WebSocket (simpler, sufficient for politics markets which don't move sub-second)
- **Stack**: Python 3.11+ — consistent with the rest of the AI Hedge Fund
- **Risk**: Hard limits on position sizing ($50/trade, $500 total) enforced at the system level, not just config
- **Independence**: Self-contained strategy module — no hard dependencies on AI Washing Detector or other strategies
- **Rate limits**: Must respect Kalshi API rate limits
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Kalshi API Client
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| kalshi-python (official) | >=2.0.0 | Kalshi REST API client | Kalshi publishes an official Python SDK on PyPI (`kalshi-python`). It wraps their v2 REST API with typed models for markets, orders, positions, and fills. Use this instead of raw httpx to avoid reimplementing auth, signature logic, and pagination. |
| httpx | >=0.28.1 | Fallback HTTP client for endpoints not in SDK | The official SDK may lag behind API additions. httpx is already in the fund stack (AI Washing Detector) and provides sync/async in one library. Use for any raw REST calls needed beyond the SDK. |
### Polling & Scheduling
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| APScheduler | >=3.11.0 | Interval-based polling at 5-10 second cadence | APScheduler is the right choice here — NOT Prefect. Prefect is designed for batch pipelines with minutes-to-hours cadence. APScheduler handles sub-minute intervals natively with its `IntervalTrigger`. No broker, no worker process, single in-process scheduler. The AI Washing Detector uses Prefect for daily batch; this project needs a live polling loop, which is a fundamentally different pattern. |
| asyncio | stdlib | Async event loop for concurrent polling | Run multiple market polls concurrently without threads. Python 3.11+ asyncio is fast enough for 5-10 second polling of 10-50 politics markets. Use `asyncio.gather()` for parallel market fetches. |
### Signal Detection & Anomaly Analysis
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pandas | >=3.0.1 | Rolling statistics, baseline computation | Already in the fund stack (backtest module). Rolling volume means, standard deviations, and z-scores are natural pandas operations on time-series market data. pandas 3.0 with PyArrow backend is fast enough for in-memory analysis of 50-100 markets. |
| numpy | >=2.0 | Z-score computation, threshold math | Already required by pandas. Use for the core anomaly math: `(current - rolling_mean) / rolling_std`. |
| scipy | >=1.15 | Statistical tests for win streak significance | `scipy.stats.binom_test` for assessing whether a win streak on a given market is statistically significant vs. random chance. Not in existing stack — add it. |
### Order Execution
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| kalshi-python (official SDK) | >=2.0.0 | Order placement, position tracking | The official SDK's `create_order()`, `get_positions()`, and `get_balance()` endpoints are the only correct interface. Do not reimplement order placement in raw httpx — the SDK handles idempotency keys and request signing correctly. |
| tenacity | >=9.1.4 | Retry logic for order placement | Already in the fund stack. Retry on network errors but NOT on Kalshi 4xx errors (insufficient balance, market closed) — those are logic errors, not transient failures. |
### Data Persistence
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | >=16 | Primary store for market snapshots, signals, trades, P&L | Consistent with the entire fund stack. ACID compliance for trade records. JSONB for flexible market metadata. |
| SQLAlchemy | >=2.0.48 | ORM | Consistent with fund stack. Use `mapped_column()` 2.0 style. |
| psycopg[binary] | >=3.2 | Sync PostgreSQL driver | Consistent with fund stack. Use sync for simplicity — the polling loop's I/O is dominated by Kalshi API latency, not DB writes. |
| Alembic | >=1.18.4 | Schema migrations | Consistent with fund stack. |
### Dashboard
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Streamlit | >=1.50.0 | Live monitoring dashboard | Already in the fund stack (backtest module uses it). Streamlit's `st.rerun()` with `time.sleep()` provides adequate auto-refresh for a politics market dashboard (5-30 second refresh is fine). No need for a full React/FastAPI app for an internal monitoring tool. |
| plotly | >=6.3.1 | Interactive charts for price/volume history | Already in the fund stack. Use for market price timelines and volume spike visualizations. |
### Core Framework & CLI
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Typer | >=0.24.1 | CLI for starting/stopping the tracker, manual signal inspection | Consistent with fund stack. Commands: `tracker start`, `tracker status`, `tracker positions`, `tracker signals`. |
| Pydantic | >=2.12.5 | Config validation, signal schema, order schema | Consistent with fund stack. All signal events and trade requests are typed Pydantic models. |
| pydantic-settings | >=2.13.1 | Environment config loading | Consistent with fund stack. |
| structlog | >=25.5.0 | Structured logging | Consistent with fund stack. Critical for an auto-trading system — every signal detection and order placement must be logged with full context. |
| tenacity | >=9.1.4 | Retry logic | Consistent with fund stack. |
| rich | >=14.0 | CLI output formatting | Consistent with fund stack. |
### Package Management & Tooling
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| uv | >=0.11.2 | Package manager | Consistent with fund stack. Fastest Python package manager. |
| ruff | >=0.15.7 | Linting + formatting | Consistent with fund stack. |
| Python | >=3.11, <3.14 | Runtime | Consistent with fund stack. |
### Testing
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pytest | >=9.0.2 | Test framework | Consistent with fund stack. |
| pytest-cov | >=7.0 | Coverage (target 80%+) | Consistent with fund stack. |
| pytest-asyncio | >=1.0 | Async test support | Required for testing async polling loop and order execution paths. |
| pytest-httpx | latest | Mock Kalshi API calls | Prevent real API calls in tests. All Kalshi client calls must be mockable. |
| factory-boy | >=3.3 | Test data factories | Generate realistic market snapshots, signal events, trade records. |
| freezegun | >=1.5.5 | Time mocking | Critical for testing rolling-window statistics (z-scores require consistent timestamps). |
| testcontainers[postgres] | >=4.14 | Integration test database | Consistent with fund stack. Spin up real PostgreSQL for integration tests. |
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Kalshi client | kalshi-python (official SDK) | Raw httpx | SDK handles RSA signing, pagination, and typed responses. Reimplementing this is wasted effort. Only use raw httpx for SDK gaps. |
| Polling scheduler | APScheduler | Prefect | Prefect is a batch pipeline tool, not a real-time event loop scheduler. Sub-minute intervals are unsupported and fragile in Prefect. APScheduler was built for exactly this use case. |
| Polling scheduler | APScheduler | `asyncio.sleep()` loop | No drift correction, no error isolation, no clean shutdown. APScheduler provides all three with minimal overhead. |
| Anomaly detection | Rules (z-score thresholds) | scikit-learn IsolationForest | ML anomaly detection requires labeled training data. You have none on day one. Start with interpretable rules; add ML in v2 once you have signal/noise data from production. |
| Anomaly detection | Rules (z-score thresholds) | statsmodels ARIMA | ARIMA is for forecasting, not spike detection. Overkill for volume anomaly detection. Z-scores on rolling windows are sufficient and transparent. |
| Dashboard | Streamlit | FastAPI + React | 10x more development cost for a single-user internal tool. Streamlit is already in the fund stack. |
| Dashboard | Streamlit | Grafana | Grafana requires a metrics ingestion pipeline (Prometheus, InfluxDB). This project stores data in PostgreSQL and Grafana's PostgreSQL datasource integration is less flexible than Streamlit for custom visualizations. |
| Database | PostgreSQL | SQLite | No concurrent writes from polling loop + dashboard reader. Cannot handle the append volume of 5-10 second market snapshots. |
| Database | PostgreSQL | TimescaleDB | TimescaleDB is a PostgreSQL extension for high-volume time-series. At 5-10 second polling of 10-50 markets, vanilla PostgreSQL with a BRIN index on `snapshot_time` is sufficient. Add TimescaleDB only if query performance degrades. |
## Installation
# Core
# Dev dependencies
## Confidence Assessment
| Component | Confidence | Basis |
|-----------|------------|-------|
| kalshi-python SDK | MEDIUM | Known to exist on PyPI from training data; version number not verified with live docs. Verify before first install. |
| Kalshi RSA auth | MEDIUM | Community knowledge from training data. Official docs should be checked at implementation time. |
| Kalshi rate limits | LOW | Not publicly documented with a specific number. Empirical tuning required in production. |
| APScheduler | HIGH | Mature library (3.x), widely used for interval jobs, well-documented, consistent with stated use case. |
| pandas/numpy/scipy | HIGH | All verified in sibling projects or standard ecosystem. scipy.stats.binom_test is a stable API. |
| PostgreSQL + SQLAlchemy stack | HIGH | Directly verified from sibling project pyproject.toml files. |
| Streamlit + plotly | HIGH | Directly verified from backtest/pyproject.toml. |
| Typer/Pydantic/structlog/tenacity | HIGH | Directly verified from sibling project pyproject.toml files. |
| Risk enforcement approach | HIGH | Fund-wide convention for financial invariants is well-established. |
## Sources
- Sibling project `Al Washing Detector/pyproject.toml` — verified versions for core stack (sqlalchemy, psycopg, alembic, pydantic, typer, structlog, tenacity, rich, httpx, pytest ecosystem)
- Sibling project `backtest/pyproject.toml` — verified versions for streamlit, plotly, pandas
- Fund CLAUDE.md — established Python 3.11+, PostgreSQL, immutability, append-only financial data conventions
- Training knowledge (August 2025 cutoff) — Kalshi API structure, APScheduler, signal detection patterns
- **Flag for verification at implementation:** kalshi-python SDK version, Kalshi API v2 auth mechanism, actual rate limits
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
