# Phase 1: Foundation - Research

**Researched:** 2026-04-02
**Domain:** Project scaffolding, Kalshi API authentication, PostgreSQL schema with SQLAlchemy 2.0, typed domain contracts
**Confidence:** HIGH (fund stack verified from sibling project; Kalshi SDK verified by downloading and inspecting kalshi-python 2.1.4 wheel)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None — all implementation choices are at Claude's discretion for this pure infrastructure phase.

### Claude's Discretion
All implementation choices. Use ROADMAP phase goal, success criteria, and fund-wide conventions:
- Python 3.11+, SQLAlchemy 2.0, Pydantic, structlog, immutable patterns
- Use kalshi-python SDK (not raw httpx) for API calls
- PostgreSQL + SQLAlchemy (not SQLite) for consistency with fund stack
- Append-only tables for signal/trade data (fund-wide immutability convention)
- Rate limiting built into the API client layer from day one
- Politics/policy market filtering at the API client level

### Deferred Ideas (OUT OF SCOPE)
None — infrastructure phase stayed within scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | System authenticates with Kalshi API using API key/RSA key pair | kalshi-python 2.1.4 `ApiClient.set_kalshi_auth(key_id, private_key_path)` — RSA-PSS signing built into SDK |
| DATA-03 | System filters to politics/policy markets only | `get_markets(series_ticker=...)` + `SeriesApi.get_series()` — no `category` param exists; must filter by `series_ticker` or post-fetch by series metadata |
| DATA-05 | System enforces Kalshi API rate limits (conservative default, tunable) | `tenacity` retry on 429; hard rate-limit constant in client layer; SDK does not enforce limits itself |
| LOG-03 | All signal and trade data is append-only (never updated or deleted) | `AppendOnlyMixin` from sibling project enforces via SQLAlchemy ORM — no `update()`/`delete()` methods compiled against these tables |
</phase_requirements>

---

## Summary

Phase 1 is a pure scaffolding phase: set up the Python package, configure Alembic migrations, wire the Kalshi API client, define typed domain objects, and prove authentication works end-to-end. No business logic — just the skeleton that all subsequent phases depend on.

The fund stack is well-established from the Al Washing Detector sibling project. The pyproject.toml layout, Pydantic settings pattern, structlog configuration, SQLAlchemy 2.0 `mapped_column()` style, `AppendOnlyMixin`, and Alembic migration structure can all be copied and adapted directly. This substantially reduces the research and implementation burden.

The key new element is Kalshi API authentication. The `kalshi-python` 2.1.4 SDK was verified by downloading and inspecting the wheel: authentication uses `ApiClient.set_kalshi_auth(key_id, private_key_path)` which loads an RSA private key PEM file and signs every request with RSA-PSS (SHA256), attaching `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-SIGNATURE`, and `KALSHI-ACCESS-TIMESTAMP` headers automatically. This is not bearer token auth — it is per-request RSA signature. The SDK handles this internally through the `KalshiAuth` class in `api_client.py`.

**Critical discovery on category filtering:** The `MarketsApi.get_markets()` method has no `category` parameter. Filtering to politics/policy markets must be done via `series_ticker` (filtering markets within a specific series) or via `SeriesApi.get_series()` to discover series tickers for the politics/policy category, then using those tickers to filter market fetches.

**Primary recommendation:** Scaffold with hatchling, copy fund patterns from Al Washing Detector, wire Kalshi auth via `set_kalshi_auth()`, design schema with `AppendOnlyMixin` on signal and trade tables, and verify auth with a smoke test against the demo API (`https://demo-api.kalshi.co/trade-api/v2`).

---

## Standard Stack

### Core (Phase 1 scope only)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| kalshi-python | 2.1.4 (latest) | Kalshi REST API client with RSA auth | Official SDK from Kalshi; handles RSA-PSS signing automatically; verified 2.1.4 on PyPI |
| cryptography | >=42.0 | RSA key loading (required by kalshi-python) | kalshi-python `api_client.py` imports `cryptography.hazmat`; pulled in transitively |
| SQLAlchemy | >=2.0.48 | ORM, `mapped_column()` 2.0 style | Fund standard; verified in sibling pyproject.toml |
| psycopg[binary] | >=3.2 | Sync PostgreSQL driver | Fund standard; verified in sibling pyproject.toml |
| Alembic | >=1.18.4 | Schema migrations | Fund standard; verified in sibling pyproject.toml |
| Pydantic | >=2.12.5 | Config validation, typed domain contracts | Fund standard; verified in sibling pyproject.toml |
| pydantic-settings | >=2.13.1 | Environment config loading with prefix | Fund standard; verified in sibling pyproject.toml |
| structlog | >=25.5.0 | Structured logging | Fund standard; verified in sibling pyproject.toml |
| tenacity | >=9.1.4 | Retry on 429/network errors | Fund standard; verified in sibling pyproject.toml |
| Typer | >=0.24.1 | CLI entry point (`tracker start`, etc.) | Fund standard; verified in sibling pyproject.toml |
| rich | >=14.0 | CLI output formatting | Fund standard; verified in sibling pyproject.toml |

### Dev/Test (Phase 1 scope)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=9.0.2 | Test framework | All tests |
| pytest-cov | >=7.0 | Coverage reporting | CI gate |
| testcontainers[postgres] | >=4.14 | Real PostgreSQL for integration tests | Alembic migration tests |
| ruff | >=0.15 | Linting + formatting | Pre-commit |

**Installation (Phase 1 subset):**
```bash
uv add kalshi-python>=2.1.4 \
       sqlalchemy>=2.0.48 \
       "psycopg[binary]>=3.2" \
       alembic>=1.18.4 \
       pydantic>=2.12.5 \
       "pydantic-settings>=2.13.1" \
       structlog>=25.5.0 \
       tenacity>=9.1.4 \
       typer>=0.24.1 \
       rich>=14.0

uv add --dev pytest>=9.0.2 \
              pytest-cov>=7.0 \
              "testcontainers[postgres]>=4.14" \
              ruff>=0.15
```

**Version verification (confirmed 2026-04-02):**
- `kalshi-python`: 2.1.4 (latest) — confirmed via `pip index versions kalshi-python`
- `uv`: 0.11.2 — confirmed installed
- Python: 3.12.11 — confirmed installed
- All fund stack versions: confirmed from `Al Washing Detector/pyproject.toml`

---

## Architecture Patterns

### Recommended Project Structure

```
src/kalshi_tracker/
├── __init__.py          # Package root
├── __main__.py          # python -m kalshi_tracker
├── cli.py               # Typer CLI (tracker start, status, signals)
├── config.py            # AppSettings (KALSHI_ prefix), KalshiSettings
├── logging.py           # configure_logging() — copy from sibling
├── db/
│   ├── __init__.py      # exports Base
│   ├── base.py          # DeclarativeBase, AppendOnlyMixin, SnapshotMixin
│   ├── models.py        # ORM models: Market, MarketSnapshot, Signal, Trade
│   ├── session.py       # create_engine_from_settings(), get_session_factory()
│   └── migrations/      # Alembic migration versions
│       ├── env.py
│       └── versions/
│           └── 0001_initial_schema.py
├── kalshi/
│   ├── __init__.py
│   ├── client.py        # KalshiClient wrapper (auth, rate limit, pagination)
│   └── types.py         # Typed domain contracts (MarketSnapshot, etc.)
tests/
├── unit/
│   ├── test_config.py
│   ├── test_client.py   # Mock Kalshi API responses
│   └── test_models.py   # Append-only enforcement tests
└── integration/
    └── test_migrations.py  # testcontainers[postgres]
config/
alembic.ini
pyproject.toml
.env.example
```

### Pattern 1: Kalshi API Client Initialization

The SDK uses `ApiClient` + per-API class (`MarketsApi`, `SeriesApi`, etc.). Wrap these behind a single `KalshiClient` facade that handles auth, rate limit enforcement, and pagination internally.

```python
# Source: kalshi_python/api_client.py line 181 (verified from SDK wheel)
from kalshi_python import ApiClient, Configuration
from kalshi_python.api import MarketsApi, SeriesApi, PortfolioApi

class KalshiClient:
    """Kalshi API client with RSA auth and rate limiting."""

    def __init__(self, settings: KalshiSettings) -> None:
        config = Configuration(host=settings.api_base_url)
        self._api_client = ApiClient(configuration=config)
        # RSA-PSS auth: loads PEM, signs per-request
        self._api_client.set_kalshi_auth(
            key_id=settings.api_key_id,
            private_key_path=str(settings.private_key_path),
        )
        self._markets = MarketsApi(self._api_client)
        self._series = SeriesApi(self._api_client)
        self._portfolio = PortfolioApi(self._api_client)
```

**RSA signing details (verified from SDK source):**
- `KalshiAuth.__init__` loads the PEM file via `serialization.load_pem_private_key`
- Per-request signing: `timestamp_str + method.upper() + path` (path without query string)
- Algorithm: RSA-PSS with SHA256, `salt_length=PSS.DIGEST_LENGTH`
- Headers added: `KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-SIGNATURE`, `KALSHI-ACCESS-TIMESTAMP`

### Pattern 2: Politics/Policy Market Filtering

There is NO `category` parameter in `get_markets()`. The SDK's `MarketsApi.get_markets()` accepts: `limit`, `cursor`, `event_ticker`, `series_ticker`, `max_close_ts`, `min_close_ts`, `status`, `tickers`.

Filtering strategy for Phase 1:
1. Call `SeriesApi.get_series(status="open")` to get all series
2. Filter series whose ticker matches known politics/policy prefixes (e.g., `PRES`, `PRES24`, `GOV`, `SENATE`, `HOUSE`) — this requires empirical verification against live API
3. Store allowed series tickers in config
4. Pass `series_ticker=ticker` to `get_markets()` per series

```python
# Phase 1: Smoke test — fetch markets for a known politics series
markets_response = self._markets.get_markets(
    series_ticker="PRES",   # example — verify against live API
    status="open",
    limit=200,
)
markets = markets_response.markets or []
```

**Important:** The exact series tickers for politics/policy must be verified against the live demo API during implementation. Store allowed tickers as config, not hardcoded strings.

### Pattern 3: AppendOnlyMixin for Signal and Trade Tables

Copy the `AppendOnlyMixin` from Al Washing Detector verbatim. It provides UUID PK, `created_at` (server default `now()`), `as_of_date`, and `observed_date`. No `update()` or `delete()` methods — enforcement is at the ORM design level, not via a database trigger.

```python
# Source: Al Washing Detector src/ai_washer/db/base.py (verified)
class AppendOnlyMixin(DualTimestampMixin):
    """UUID PK + created_at + dual timestamps. No update/delete by design."""
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

Apply to: `Signal`, `Trade` tables. `MarketSnapshot` also append-only (high-volume time-series, never corrected).

### Pattern 4: Pydantic Settings with KALSHI_ Prefix

```python
# Source: Al Washing Detector src/ai_washer/config.py (verified pattern)
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KALSHI_TRACKER_",
        extra="ignore",
    )
    database_url: str
    log_level: str = "INFO"

class KalshiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KALSHI_",
        extra="ignore",
    )
    api_key_id: str
    private_key_path: Path        # path to .pem file on disk
    api_base_url: str = "https://api.elections.kalshi.com/trade-api/v2"
    demo_mode: bool = False       # set True → use demo-api.kalshi.co
    rate_limit_rpm: int = 60      # conservative default, tunable
```

**Two separate settings classes** — one for infrastructure (DB), one for Kalshi credentials. This follows the sibling project's pattern of multiple cohesive settings objects.

### Pattern 5: Structlog Configuration

Copy `logging.py` from Al Washing Detector exactly. DEBUG → ConsoleRenderer, INFO+ → JSONRenderer. Bind context at the client level.

### Pattern 6: Typed Domain Contracts (Frozen Dataclasses)

Phase 1 defines the contracts that later phases consume. Use `@dataclass(frozen=True)` per ARCHITECTURE.md.

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class MarketSnapshot:
    """Normalized view of a Kalshi market at a point in time."""
    market_id: str          # same as ticker
    ticker: str
    series_ticker: str
    yes_bid: int            # cents (0-99)
    yes_ask: int            # cents (0-99)
    no_bid: int             # cents (0-99)
    no_ask: int             # cents (0-99)
    last_price: int         # cents
    volume: int             # total lifetime contracts
    volume_24h: int         # 24-hour volume
    status: str             # 'active' | 'closed' | 'settled'
    captured_at: datetime
```

**Note on price representation:** Kalshi's SDK returns prices as `Union[StrictFloat, StrictInt]` (from `market.py` inspection). Prices are in cents (0-99), not decimals. Store as integers.

### Anti-Patterns to Avoid

- **No `category` query param:** `get_markets()` does not accept category. Do not attempt to pass `category=politics` — it will be silently ignored or raise a pydantic validation error.
- **Do not store RSA private key content in env var:** Store the file path (`KALSHI_PRIVATE_KEY_PATH`), not the PEM content. The SDK's `set_kalshi_auth()` takes a file path and reads it at startup.
- **Do not use SQLite:** Architecture research confirmed PostgreSQL is required for concurrent write safety and fund stack consistency.
- **Do not mix append-only and mutable tables in the same mixin:** `Market` (entity table) is mutable; `MarketSnapshot`, `Signal`, `Trade` are append-only. Apply `AppendOnlyMixin` only to the latter three.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RSA-PSS request signing | Custom `sign_request()` function | `ApiClient.set_kalshi_auth()` | SDK already implements this in `KalshiAuth`; reimplementing introduces signature bugs |
| Kalshi API response parsing | Raw `httpx` + manual dict parsing | `kalshi-python` typed models | SDK generates typed Pydantic models for every response; `Market`, `GetMarketsResponse`, etc. |
| Database session management | Custom context manager | `sessionmaker` + `with Session()` pattern | SQLAlchemy session factory pattern is established and tested |
| Schema migration runner | Manual `CREATE TABLE` scripts | Alembic | Alembic handles transactional migrations, upgrade/downgrade, autogenerate from models |
| UUID primary key generation | `str(uuid.uuid4())` in application code | `mapped_column(primary_key=True, default=uuid.uuid4)` | Server-side default ensures consistency; sibling project established this pattern |
| Pagination cursor handling | Manual loop over `cursor` | SDK's pagination pattern | `get_markets()` returns `cursor` in response; SDK handles serialization |

**Key insight:** The kalshi-python SDK is auto-generated from OpenAPI spec. Every API response has a corresponding Pydantic model. Never parse response dicts manually — always use the typed model.

---

## Common Pitfalls

### Pitfall 1: No Category Filter in Markets API
**What goes wrong:** Developer passes `category="politics"` to `get_markets()` expecting filtered results. Pydantic validation may reject the unexpected kwarg, or it is silently dropped.
**Why it happens:** The REST API v2 does not expose a category query parameter on the markets endpoint. Categories are part of the Series/Event hierarchy above markets.
**How to avoid:** Filter at the Series level using `SeriesApi.get_series()`, identify series with politics/policy content, then query markets by `series_ticker`.
**Warning signs:** Getting all markets (100+ results including sports, finance, etc.) instead of only politics markets.

### Pitfall 2: RSA Key File Path vs. Content
**What goes wrong:** Developer sets `KALSHI_PRIVATE_KEY=<pem_content>` in env, but `set_kalshi_auth()` expects a file path string, not PEM content.
**Why it happens:** Confusion between bearer token auth (pass token string) and RSA auth (pass file path, SDK reads file).
**How to avoid:** Set `KALSHI_PRIVATE_KEY_PATH=/path/to/key.pem` in `.env`. The `KalshiSettings.private_key_path: Path` field enforces this with Pydantic type coercion.
**Warning signs:** `FileNotFoundError` with a path that looks like PEM content.

### Pitfall 3: Price Units — Cents vs. Probabilities
**What goes wrong:** Developer treats `yes_bid=45` as 0.45 probability and uses it in floating point math, or stores it as a float in the DB.
**Why it happens:** Kalshi displays prices as percentages (45¢ = 45%) but the API returns integers (45, not 0.45).
**How to avoid:** Store all prices as `SmallInteger` in the DB (0-99 range). Never divide by 100 before storage. Add a comment in models: `# Kalshi prices are integer cents (0-99), not probabilities`.
**Warning signs:** Seeing values like 0.45 in `yes_bid` — the SDK returns `Union[StrictFloat, StrictInt]`, so floats are possible for some endpoints; normalize to `int` in the Ingest Layer.

### Pitfall 4: Alembic autogenerate with JSONB
**What goes wrong:** `alembic revision --autogenerate` does not detect JSONB type changes in PostgreSQL — it may generate empty migrations or incorrect ones for JSONB columns.
**Why it happens:** SQLAlchemy's generic `JSON` type and PostgreSQL's `JSONB` dialect type are separate; autogenerate does not always diff them correctly.
**How to avoid:** Import from `sqlalchemy.dialects.postgresql import JSONB` (not `from sqlalchemy import JSON`). Verify generated migration SQL before applying. The sibling project uses this pattern correctly.
**Warning signs:** Migration generates `ALTER TABLE` for a JSONB column that hasn't changed, or generates a `JSON` type instead of `JSONB`.

### Pitfall 5: Demo vs. Production Base URL
**What goes wrong:** Developer accidentally uses production URL (`https://api.elections.kalshi.com/trade-api/v2`) during development, executing real actions with real money.
**Why it happens:** Base URL defaults to production if not overridden.
**How to avoid:** Default `api_base_url` to demo (`https://demo-api.kalshi.co/trade-api/v2`) unless `KALSHI_DEMO_MODE=false` is explicitly set. Add a startup log warning when production is active.
**Warning signs:** Not seeing "demo" in the API URL during development.

### Pitfall 6: Append-Only Not Enforced at DB Level
**What goes wrong:** ORM-level append-only design can be bypassed by raw SQL or future code that doesn't know the convention. A developer writes `session.execute(update(Signal)...)` and it succeeds.
**Why it happens:** SQLAlchemy doesn't prevent `UPDATE` statements unless explicitly blocked.
**How to avoid:** The `AppendOnlyMixin` approach (no `update()`/`delete()` methods on the ORM class) is the fund convention. Phase 1 should also add a comment block in `models.py` explaining the append-only contract. Optional: add a PostgreSQL `RULE` or trigger to truly prevent updates — but this is overkill for v1.
**Warning signs:** Code that calls `session.merge()` on `Signal` or `Trade` objects.

---

## Code Examples

Verified patterns from official sources:

### Kalshi Client Setup (from SDK source, verified)
```python
# Source: kalshi_python/api_client.py lines 181-188 (wheel inspection)
from kalshi_python import ApiClient, Configuration
from kalshi_python.api import MarketsApi, SeriesApi

config = Configuration(host="https://demo-api.kalshi.co/trade-api/v2")
api_client = ApiClient(configuration=config)
api_client.set_kalshi_auth(
    key_id="your-key-id-here",
    private_key_path="/path/to/private_key.pem",
)
markets_api = MarketsApi(api_client)
```

### Markets Fetch with Pagination (from SDK method signatures, verified)
```python
# Source: kalshi_python/api/markets_api.py line 909 (wheel inspection)
def get_politics_markets(markets_api: MarketsApi, series_ticker: str) -> list:
    """Fetch all open markets for a given series, handling pagination."""
    all_markets = []
    cursor = None
    while True:
        resp = markets_api.get_markets(
            series_ticker=series_ticker,
            status="open",
            limit=200,
            cursor=cursor,
        )
        all_markets.extend(resp.markets or [])
        if not resp.cursor:
            break
        cursor = resp.cursor
    return all_markets
```

### AppendOnlyMixin (from sibling project, verified)
```python
# Source: Al Washing Detector src/ai_washer/db/base.py (verified)
class AppendOnlyMixin(DualTimestampMixin):
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    # No update() or delete() methods — append-only by design
```

### MarketSnapshot ORM Model
```python
# Pattern: append-only time-series table for raw market data
from sqlalchemy.dialects.postgresql import JSONB

class MarketSnapshot(AppendOnlyMixin, Base):
    """Append-only market state snapshot captured on each poll tick."""
    __tablename__ = "market_snapshots"
    __table_args__ = (
        Index("ix_market_snapshots_ticker_captured", "ticker", "captured_at"),
    )

    ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    series_ticker: Mapped[str] = mapped_column(String(50), nullable=False)
    yes_bid: Mapped[int] = mapped_column(SmallInteger, nullable=False)   # 0-99 cents
    yes_ask: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    no_bid: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    no_ask: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    last_price: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    volume_24h: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    raw_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
```

### Rate-Limit Enforced API Call (tenacity pattern)
```python
# Source: tenacity pattern verified from sibling project
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

@retry(
    retry=retry_if_exception_type(Exception),   # narrow to 429 in implementation
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
def _fetch_markets_with_retry(self, series_ticker: str):
    return self._markets.get_markets(series_ticker=series_ticker, status="open")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Bearer token auth (Kalshi v1) | RSA-PSS per-request signing (Kalshi v2) | Kalshi v2 API | Must use SDK or implement RSA-PSS; no simple token header |
| SQLAlchemy 1.x `Column()` style | SQLAlchemy 2.0 `mapped_column()` + `Mapped[]` | SQLAlchemy 2.0 (2023) | Type-safe ORM models; full mypy compatibility |
| `psycopg2` | `psycopg[binary]` (psycopg3) | 2022-2023 | psycopg3 is faster, pure Python with optional C extension |
| `setup.py` / `setuptools` | `hatchling` build backend with `pyproject.toml` | 2022-2024 | Single-file project config; no `setup.py` needed |

**Deprecated/outdated:**
- Bearer token auth: Kalshi v2 uses RSA-PSS. Any tutorial using `Authorization: Bearer <token>` with a static token is outdated.
- kalshi-python 1.x: The 1.x line predates the v2 API. Use 2.x only.

---

## Open Questions

1. **Politics/policy series tickers**
   - What we know: No `category` filter exists in `get_markets()`. Series are the level above markets. `SeriesApi.get_series()` returns all series.
   - What's unclear: What are the exact series tickers that cover politics/policy markets? Are they stable across time?
   - Recommendation: In Phase 1 smoke test, call `get_series()` and print all series tickers. Choose a configurable allowlist (`KALSHI_POLITICS_SERIES=PRES,GOV,SENATE,HOUSE`) with a sensible default. This is empirical — must be validated against the live demo API.

2. **Rate limit behavior (429 responses)**
   - What we know: Kalshi does not publish a hard rate limit. Conservative starting point is 60 req/min. The polling loop makes ~5 API calls per tick per market.
   - What's unclear: Does the SDK itself throw a `kalshi_python.exceptions.ApiException` with status 429, or does it raise a different exception class?
   - Recommendation: Wrap calls in `try/except ApiException` and check `e.status == 429` for targeted retry logic. Inspect `kalshi_python.exceptions` in Phase 1.

3. **Market entity table vs. pure snapshot**
   - What we know: Kalshi markets have a ticker (stable ID) and metadata that changes over time (close_time, status). Signal and trade tables need to reference markets.
   - What's unclear: Whether to maintain a mutable `Market` entity table (like `Company` in sibling project) or just embed ticker strings in snapshot rows.
   - Recommendation: Add a lightweight mutable `Market` entity table (ticker, series_ticker, title, close_time, status, first_seen, last_updated). Snapshot rows FK to it. Mirrors the Company table pattern from the sibling project.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All code | ✓ | 3.12.11 | — |
| uv | Package management | ✓ | 0.11.2 | pip (slower) |
| PostgreSQL | Database | ✗ | — | testcontainers[postgres] for tests; Docker for dev |
| Docker | testcontainers integration tests | ✓ (client) | 29.0.1 (client) | — |
| psql CLI | DB inspection | ✗ | — | Use psql from Docker container |

**Missing dependencies with no fallback:**
- PostgreSQL server: Must be running for the integration test to pass (Alembic migration smoke test). testcontainers[postgres] handles this automatically in tests. For local development, the developer must run `docker run -p 5432:5432 -e POSTGRES_PASSWORD=password postgres:16` or equivalent.

**Missing dependencies with fallback:**
- psql CLI: Not needed — testcontainers and SQLAlchemy provide all programmatic DB access needed.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0+ |
| Config file | `pyproject.toml` [tool.pytest.ini_options] — see Wave 0 |
| Quick run command | `pytest tests/unit/ -x -q` |
| Full suite command | `pytest tests/ -x -q --cov=src/kalshi_tracker` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | `KalshiClient` initializes with RSA key without error | unit | `pytest tests/unit/test_client.py::test_client_init_with_rsa_key -x` | ❌ Wave 0 |
| DATA-01 | RSA auth adds correct headers to requests | unit (mock) | `pytest tests/unit/test_client.py::test_rsa_headers_present -x` | ❌ Wave 0 |
| DATA-03 | `get_politics_markets()` returns only markets with allowed series tickers | unit (mock) | `pytest tests/unit/test_client.py::test_markets_filtered_to_politics_series -x` | ❌ Wave 0 |
| DATA-05 | Client raises `RateLimitError` on consecutive rapid calls | unit | `pytest tests/unit/test_client.py::test_rate_limit_enforced -x` | ❌ Wave 0 |
| LOG-03 | `Signal` model has no `update()` or `delete()` methods | unit | `pytest tests/unit/test_models.py::test_signal_is_append_only -x` | ❌ Wave 0 |
| LOG-03 | Alembic migration creates all tables with expected columns | integration | `pytest tests/integration/test_migrations.py::test_all_tables_created -x -m integration` | ❌ Wave 0 |
| DATA-01 | Auth smoke test against demo API returns 200 | integration (manual) | manual — requires real API keys | — |

### Sampling Rate
- **Per task commit:** `pytest tests/unit/ -x -q`
- **Per wave merge:** `pytest tests/ -x -q --cov=src/kalshi_tracker --cov-fail-under=80`
- **Phase gate:** Full suite green (unit + integration with testcontainers) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/__init__.py` — package root
- [ ] `tests/unit/__init__.py`, `tests/unit/test_client.py`, `tests/unit/test_models.py`, `tests/unit/test_config.py`
- [ ] `tests/integration/__init__.py`, `tests/integration/test_migrations.py`
- [ ] `pyproject.toml` [tool.pytest.ini_options] — testpaths, pythonpath, markers
- [ ] Framework install: `uv add --dev pytest>=9.0.2 pytest-cov>=7.0 "testcontainers[postgres]>=4.14" ruff>=0.15`

---

## Project Constraints (from CLAUDE.md)

Directives that the planner must verify compliance against:

| Directive | Source | Constraint |
|-----------|--------|------------|
| Python 3.11+ | CLAUDE.md (project) | `requires-python = ">=3.11,<3.14"` in pyproject.toml |
| uv preferred | CLAUDE.md (project) | Use `uv add` not `pip install` |
| PostgreSQL only | CLAUDE.md (project) | No SQLite, even in tests (use testcontainers) |
| `$50/trade, $500 total` hard limits | CLAUDE.md (project) | Code-level constants, not config — Phase 4 concern but schema must not contradict |
| Immutability | CLAUDE.md (fund) | Return new objects, never mutate in place; frozen dataclasses for domain objects |
| append-only snapshots | CLAUDE.md (fund) | `MarketSnapshot`, `Signal`, `Trade` → `AppendOnlyMixin` |
| UTC timestamps | CLAUDE.md (fund) | All `DateTime` columns must use `timezone=True` |
| ruff line-length=100 | CLAUDE.md (project patterns) | `[tool.ruff] line-length = 100` in pyproject.toml |
| `from __future__ import annotations` | CLAUDE.md (project patterns) | First non-docstring import in every `.py` file |
| Google-style docstrings | CLAUDE.md (project patterns) | Every public function and class |
| `logger = structlog.get_logger(__name__)` | CLAUDE.md (project patterns) | Module-level logger in every module |
| hatchling build backend | CLAUDE.md (project patterns) | `[build-system] requires = ["hatchling"]` |
| No hardcoded secrets | Security (global CLAUDE.md) | RSA key path and key ID in `.env` only |
| Validate at boundaries | Coding style (global) | All API responses validated via SDK typed models before passing deeper |

---

## Sources

### Primary (HIGH confidence)
- `kalshi_python-2.1.4-py3-none-any.whl` — Downloaded and inspected locally; `api_client.py`, `api/markets_api.py`, `models/market.py`, `api/series_api.py`, `configuration.py` read directly
- `Al Washing Detector/pyproject.toml` — Verified fund stack versions
- `Al Washing Detector/src/ai_washer/db/base.py` — Verified `AppendOnlyMixin` implementation
- `Al Washing Detector/src/ai_washer/db/models.py` — Verified SQLAlchemy 2.0 `mapped_column()` patterns
- `Al Washing Detector/src/ai_washer/config.py` — Verified Pydantic settings pattern
- `Al Washing Detector/src/ai_washer/db/session.py` — Verified session factory pattern
- `Al Washing Detector/src/ai_washer/logging.py` — Verified structlog configuration

### Secondary (MEDIUM confidence)
- `https://docs.kalshi.com/getting_started/quick_start_authenticated_requests` — RSA-PSS auth mechanics confirmed (matches SDK source)
- `pip index versions kalshi-python` — Confirmed 2.1.4 is latest version on PyPI

### Tertiary (LOW confidence)
- WebSearch results for series ticker names (PRES, GOV, etc.) — training knowledge; must be validated against live demo API

---

## Metadata

**Confidence breakdown:**
- Kalshi SDK mechanics: HIGH — verified by inspecting downloaded wheel source
- Fund stack versions: HIGH — verified from sibling project pyproject.toml
- ORM patterns (AppendOnlyMixin, session factory): HIGH — verified from sibling project source
- Politics series tickers: LOW — must be validated against live demo API during Phase 1 smoke test
- Kalshi rate limits: LOW — not publicly documented; empirical tuning required

**Research date:** 2026-04-02
**Valid until:** 2026-07-02 (90 days — stable SDK; re-verify if Kalshi announces API changes)
