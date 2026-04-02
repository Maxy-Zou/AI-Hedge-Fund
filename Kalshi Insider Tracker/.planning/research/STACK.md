# Technology Stack

**Project:** Kalshi Insider Tracker
**Researched:** 2026-04-02
**Confidence:** MEDIUM overall (Kalshi-specific details from training data; fund conventions from verified sibling projects)

## Recommended Stack

### Kalshi API Client

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| kalshi-python (official) | >=2.0.0 | Kalshi REST API client | Kalshi publishes an official Python SDK on PyPI (`kalshi-python`). It wraps their v2 REST API with typed models for markets, orders, positions, and fills. Use this instead of raw httpx to avoid reimplementing auth, signature logic, and pagination. |
| httpx | >=0.28.1 | Fallback HTTP client for endpoints not in SDK | The official SDK may lag behind API additions. httpx is already in the fund stack (AI Washing Detector) and provides sync/async in one library. Use for any raw REST calls needed beyond the SDK. |

**Kalshi API authentication (MEDIUM confidence):** Kalshi v2 API uses RSA key-pair authentication (private key signs each request). The official SDK handles signature generation. The user already has an API key, so this is a credential-passing concern, not an implementation concern. Store the RSA private key path and key ID in `.env`.

**Kalshi rate limits (MEDIUM confidence):** Kalshi's public REST API does not publish a hard rate limit number, but the community norm is ~10 requests/second on market data endpoints, stricter on order placement. The project's 5-10 second polling interval is well within safe limits. Use tenacity for retry with exponential backoff on 429 responses.

### Polling & Scheduling

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| APScheduler | >=3.11.0 | Interval-based polling at 5-10 second cadence | APScheduler is the right choice here — NOT Prefect. Prefect is designed for batch pipelines with minutes-to-hours cadence. APScheduler handles sub-minute intervals natively with its `IntervalTrigger`. No broker, no worker process, single in-process scheduler. The AI Washing Detector uses Prefect for daily batch; this project needs a live polling loop, which is a fundamentally different pattern. |
| asyncio | stdlib | Async event loop for concurrent polling | Run multiple market polls concurrently without threads. Python 3.11+ asyncio is fast enough for 5-10 second polling of 10-50 politics markets. Use `asyncio.gather()` for parallel market fetches. |

**Why not Prefect here:** Prefect's minimum practical scheduling granularity is ~1 minute (sub-minute triggers are possible but unsupported and fragile). For 5-10 second polling, APScheduler's `AsyncScheduler` with `IntervalTrigger(seconds=10)` is the correct tool.

**Why not a pure `while True` loop:** APScheduler provides drift correction (if a poll takes 3s, the next fires 7s later, not 10s after the previous starts), error isolation per job, and clean shutdown. A `while True` loop with `asyncio.sleep()` is brittle.

### Signal Detection & Anomaly Analysis

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pandas | >=3.0.1 | Rolling statistics, baseline computation | Already in the fund stack (backtest module). Rolling volume means, standard deviations, and z-scores are natural pandas operations on time-series market data. pandas 3.0 with PyArrow backend is fast enough for in-memory analysis of 50-100 markets. |
| numpy | >=2.0 | Z-score computation, threshold math | Already required by pandas. Use for the core anomaly math: `(current - rolling_mean) / rolling_std`. |
| scipy | >=1.15 | Statistical tests for win streak significance | `scipy.stats.binom_test` for assessing whether a win streak on a given market is statistically significant vs. random chance. Not in existing stack — add it. |

**Anomaly detection approach (HIGH confidence for simplicity):** This project does NOT need scikit-learn or ML-based anomaly detection for v1. The four signal types (volume spike, price move, win streak, timing cluster) are all expressible as threshold rules on rolling statistics. Start with z-score thresholds (e.g., volume > mean + 2.5*std) tuned in production. Add ML later if heuristics prove insufficient.

**Why not scikit-learn IsolationForest/DBSCAN:** ML anomaly detection requires labeled training data and feature engineering. You have neither on day one. Rule-based heuristics are easier to tune, debug, and explain — critical for a system that auto-executes real money trades.

### Order Execution

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| kalshi-python (official SDK) | >=2.0.0 | Order placement, position tracking | The official SDK's `create_order()`, `get_positions()`, and `get_balance()` endpoints are the only correct interface. Do not reimplement order placement in raw httpx — the SDK handles idempotency keys and request signing correctly. |
| tenacity | >=9.1.4 | Retry logic for order placement | Already in the fund stack. Retry on network errors but NOT on Kalshi 4xx errors (insufficient balance, market closed) — those are logic errors, not transient failures. |

**Hard position limit enforcement (CRITICAL):** The `$50/trade, $500 total` limits must be enforced in a dedicated `RiskGate` class that wraps all order placement calls. No code path may call the Kalshi order API without passing through `RiskGate.check_and_place()`. This is not a config value — it is a hard assertion that raises an exception if violated. This mirrors the fund's convention of enforcing financial invariants at the system level.

### Data Persistence

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | >=16 | Primary store for market snapshots, signals, trades, P&L | Consistent with the entire fund stack. ACID compliance for trade records. JSONB for flexible market metadata. |
| SQLAlchemy | >=2.0.48 | ORM | Consistent with fund stack. Use `mapped_column()` 2.0 style. |
| psycopg[binary] | >=3.2 | Sync PostgreSQL driver | Consistent with fund stack. Use sync for simplicity — the polling loop's I/O is dominated by Kalshi API latency, not DB writes. |
| Alembic | >=1.18.4 | Schema migrations | Consistent with fund stack. |

**Immutability rule (fund-wide convention):** Market snapshots, signal firings, and trade records are append-only. Never update a trade row after insertion — use status columns (`placed`, `filled`, `expired`, `cancelled`) that only move forward. P&L is always computed from the raw trade log, never cached in a mutable field.

### Dashboard

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Streamlit | >=1.50.0 | Live monitoring dashboard | Already in the fund stack (backtest module uses it). Streamlit's `st.rerun()` with `time.sleep()` provides adequate auto-refresh for a politics market dashboard (5-30 second refresh is fine). No need for a full React/FastAPI app for an internal monitoring tool. |
| plotly | >=6.3.1 | Interactive charts for price/volume history | Already in the fund stack. Use for market price timelines and volume spike visualizations. |

**Dashboard refresh pattern:** Use `st.rerun()` at the bottom of the Streamlit script with a configurable sleep (default 10s). Read from PostgreSQL on each refresh. This is simpler than Streamlit's `st_autorefresh` component and avoids WebSocket state complexity.

**Why not a custom React dashboard:** This is an internal monitoring tool used by one person. Streamlit with PostgreSQL read-through gives 80% of the value at 10% of the development cost. Move to a proper frontend only if you need to share it with investors.

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

```bash
# Core
uv add kalshi-python>=2.0.0 \
       httpx>=0.28.1 \
       apscheduler>=3.11.0 \
       pandas>=3.0.1 \
       numpy>=2.0 \
       scipy>=1.15 \
       sqlalchemy>=2.0.48 \
       psycopg[binary]>=3.2 \
       alembic>=1.18.4 \
       pydantic>=2.12.5 \
       "pydantic-settings[yaml]>=2.13.1" \
       typer>=0.24.1 \
       rich>=14.0 \
       structlog>=25.5.0 \
       tenacity>=9.1.4 \
       streamlit>=1.50.0 \
       plotly>=6.3.1

# Dev dependencies
uv add --dev pytest>=9.0.2 \
              pytest-cov>=7.0 \
              pytest-asyncio>=1.0 \
              pytest-httpx \
              factory-boy>=3.3 \
              freezegun>=1.5.5 \
              "testcontainers[postgres]>=4.14" \
              ruff>=0.15.7
```

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
