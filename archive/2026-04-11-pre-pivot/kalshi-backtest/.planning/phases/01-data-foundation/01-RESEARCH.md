# Phase 1: Data Foundation - Research

**Researched:** 2026-04-04
**Domain:** Kalshi API ingestion, DuckDB schema design, CLI scaffold (Typer), append-only time-series storage
**Confidence:** HIGH (stack verified against live SDK introspection; DuckDB patterns verified with running code)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Kalshi API live/historical tier split — must call `GET /historical/cutoff` at runtime
- `kalshi-python` SDK as primary client with `httpx` fallback for historical endpoints
- DuckDB for local analytical storage (append-only, no server, columnar)
- Settlement `result` column physically separated or NULL-enforced for bars before `close_time`
- All timestamps UTC, with Eastern Time awareness for Kalshi event times
- Fee formula `ceil(0.07 * C * P * (1-P))` — store raw price data for accurate fee calculation

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | Ingest historical market and contract data from Kalshi API (all event categories) | SDK covers live markets; historical markets need httpx directly to `/trade-api/v2/historical/*` endpoints |
| DATA-02 | Handle live/historical API tier split with runtime cutoff resolution | `GET /trade-api/v2/historical/cutoff` not in SDK — must call via httpx; route based on `market_settled_ts` cutoff |
| DATA-03 | Store contract snapshots in append-only DuckDB with lookahead-safe schema | DuckDB `PRIMARY KEY(ticker, ts)` + `ON CONFLICT DO NOTHING` verified working; result column NULL-enforced until close_time passes |
| DATA-04 | Support incremental sync — only fetch new data on subsequent runs | Idempotent insert pattern verified: `ON CONFLICT DO NOTHING`; track `last_ingested_ts` per ticker |
| DATA-05 | Validate ingested data — gap detection, anomaly alerting, coverage reporting | DuckDB window functions enable gap detection; print Rich table report post-ingestion |
| DATA-06 | All timestamps stored in UTC with Eastern Time conversion for Kalshi event times | Store as DuckDB `TIMESTAMP` (naive UTC); use `zoneinfo.ZoneInfo("America/New_York")` for ET display |
| CLI-01 | CLI entry point for running backtests, data ingestion, and viewing results | Typer pattern from Insider Tracker — `app = typer.Typer(name="kalshi-backtest")`; `ingest` command in Phase 1 |
</phase_requirements>

---

## Summary

This phase builds the DuckDB-backed data store and ingestion pipeline that every subsequent phase depends on. The most critical design decision is the physical separation of settlement results from price observations — this cannot be retrofitted cheaply and must be correct from day one.

The `kalshi-python` SDK (v2.1.0 installed, >=2.1.4 required) provides the live endpoints: `get_market_candlesticks` at `/series/{ticker}/markets/{market_ticker}/candlesticks`, `get_markets` with date filters, and `get_events`. **Critical finding from SDK introspection:** there are no historical API classes or methods in the SDK — the entire `/trade-api/v2/historical/*` endpoint family requires direct `httpx` calls. This is the key blocker from STATE.md and is now confirmed.

DuckDB 1.5.1 is available globally. The `ON CONFLICT DO NOTHING` idiom for idempotent inserts was verified working against live DuckDB. The `TIMESTAMP` (naive UTC) type is the safest approach — `TIMESTAMPTZ` requires `pytz` and returns offset-aware datetimes that complicate downstream processing.

**Primary recommendation:** Use `kalshi-python` SDK for all live-tier endpoints; implement a `HistoricalKalshiClient` using `httpx` for historical endpoints. The `KalshiSettings` config pattern from the Insider Tracker (RSA PEM key path + `KALSHI_` env prefix) is the reference implementation to follow.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `kalshi-python` | >=2.1.4 (2.1.0 in tracker venv) | Live-tier Kalshi API client | Official SDK with RSA-PSS auth wired in; covers MarketsApi, EventsApi, SeriesApi |
| `httpx` | >=0.28.1 | Historical-tier API calls + REST fallback | Live endpoints available in SDK; historical endpoints require direct httpx — CONFIRMED |
| `tenacity` | >=9.1.4 | Retry with exponential backoff | Kalshi imposes rate limits; mandatory from day one |
| `duckdb` | 1.5.1 (latest stable) | Local analytical storage | Columnar, zero-server, verified idempotent insert support |
| `pydantic` | >=2.12.5 | API response validation + config schema | Fund-wide standard; validates Kalshi response shapes at ingestion boundary |
| `pydantic-settings` | >=2.13.1 | Config loading from `.env` | Fund-wide standard; `KALSHI_BACKTEST_` env prefix convention |
| `typer` | >=0.24.1 | CLI commands | Fund-wide standard; already in Insider Tracker — copy `app = typer.Typer()` pattern |
| `structlog` | >=25.5.0 | Structured logging | Fund-wide standard |
| `rich` | >=14.0 | CLI table output for validation report | Fund-wide standard; data validation report printed as Rich table |
| `zoneinfo` | stdlib (Python 3.9+) | Eastern Time conversion | No extra dependency; `ZoneInfo("America/New_York")` for ET display only |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | >=9.0.2 | Test framework | All tests |
| `pytest-cov` | >=7.0 | Coverage reporting | 80% gate enforcement |
| `ruff` | >=0.15 | Lint + format | All code quality checks |
| `freezegun` | >=1.5.5 | Time mocking in tests | Testing DST transitions, ingestion timestamps |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| DuckDB TIMESTAMP (naive UTC) | TIMESTAMPTZ | TIMESTAMPTZ requires pytz and returns offset-aware datetimes — adds complexity with no benefit if all storage is UTC-disciplined at application layer |
| httpx for historical tier | kalshi-python SDK | SDK has zero coverage of /historical/* — not a choice |
| Pydantic v2 for response validation | dataclasses | Pydantic catches API shape changes at the boundary; dataclasses don't validate |

**Installation:**
```bash
uv add kalshi-python httpx tenacity duckdb pydantic pydantic-settings typer structlog rich
uv add --dev pytest pytest-cov ruff freezegun
```

**Version verification (run before coding):**
```bash
uv run python -c "import kalshi_python; print(kalshi_python.__version__)"
uv run python -c "import duckdb; print(duckdb.__version__)"
```

---

## Architecture Patterns

### Recommended Project Structure
```
kalshi-backtest/
├── pyproject.toml           # uv project config
├── .env.example             # required env vars template
├── src/
│   └── kalshi_backtest/
│       ├── __init__.py
│       ├── __main__.py      # python -m kalshi_backtest entry
│       ├── cli.py           # Typer app with ingest command (Phase 1)
│       ├── config.py        # KalshiBacktestSettings (pydantic-settings)
│       ├── logging.py       # configure_logging() — copy Insider Tracker pattern
│       ├── db/
│       │   ├── __init__.py
│       │   ├── schema.py    # CREATE TABLE DDL and connection factory
│       │   └── repository.py # MarketRepository — query methods for simulation
│       └── ingestion/
│           ├── __init__.py
│           ├── client.py    # KalshiLiveClient (SDK) + KalshiHistoricalClient (httpx)
│           ├── cutoff.py    # HistoricalCutoffResolver
│           ├── fetcher.py   # EventFetcher, MarketFetcher, CandlestickFetcher
│           ├── pipeline.py  # IngestionPipeline orchestrator
│           ├── types.py     # Pydantic models: CandlestickRecord, MarketRecord
│           └── validator.py # DataValidator — gap detection + report generation
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── markets.json     # recorded API responses
    │   └── candlesticks.json
    ├── test_schema.py
    ├── test_client.py
    ├── test_fetcher.py
    ├── test_pipeline.py
    └── test_validator.py
```

### Pattern 1: Dual-Client Architecture (Live + Historical)

**What:** Two separate client classes handle the live-tier and historical-tier API surfaces. A router decides which to call based on the cutoff timestamp.

**When to use:** Always — the SDK has zero historical endpoint coverage; this split is mandatory.

**Verified finding:** `kalshi-python` SDK's `MarketsApi` provides: `get_market_candlesticks` (live, `/series/{series_ticker}/markets/{market_ticker}/candlesticks`), `get_markets`, `get_trades`. There are **no** historical API classes in `kalshi_python.api`. All `/trade-api/v2/historical/*` calls must go through httpx.

```python
# Source: SDK introspection (confirmed 2026-04-04 against kalshi-python 2.1.0)
class KalshiLiveClient:
    """Wraps kalshi_python SDK for live-tier endpoints."""
    def get_candlesticks(
        self, series_ticker: str, market_ticker: str,
        start_ts: int, end_ts: int, period_interval: int = 1440
    ) -> list[Candlestick]:
        self._rate_bucket.consume()
        return self._markets_api.get_market_candlesticks(
            ticker=series_ticker,       # NOTE: first param is series_ticker
            market_ticker=market_ticker,
            start_ts=start_ts,
            end_ts=end_ts,
            period_interval=period_interval,
        ).candlesticks or []

class KalshiHistoricalClient:
    """Direct httpx calls to /trade-api/v2/historical/* endpoints."""
    BASE = "https://api.elections.kalshi.com/trade-api/v2"

    def get_historical_candlesticks(
        self, market_ticker: str, start_ts: int, end_ts: int
    ) -> list[dict]:
        resp = self._http.get(
            f"{self.BASE}/historical/markets/{market_ticker}/candlesticks",
            params={"start_ts": start_ts, "end_ts": end_ts, "period_interval": 1440},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        return resp.json().get("candlesticks", [])
```

**IMPORTANT:** `get_market_candlesticks` takes `ticker` (series_ticker) as first param, then `market_ticker`. This is counterintuitive — confirmed from SDK source.

### Pattern 2: Idempotent DuckDB Inserts

**What:** Use `ON CONFLICT DO NOTHING` on the `PRIMARY KEY (ticker, ts)` for candlestick inserts. Re-running `ingest` safely skips already-stored rows.

**When to use:** All candlestick writes. Market metadata writes use `INSERT OR REPLACE` (mutable — settlement result can change).

**Verified working against DuckDB 1.5.1:**

```python
# Source: verified locally 2026-04-04
def insert_candles(con: duckdb.DuckDBPyConnection, rows: list[tuple]) -> int:
    """Insert candlestick rows, skipping duplicates. Returns count inserted."""
    con.executemany(
        """INSERT INTO candles (ticker, ts, open_price, high_price, low_price, 
           close_price, volume, ingested_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT DO NOTHING""",
        rows,
    )
    # DuckDB doesn't return rows_affected from executemany — query for count separately
    return len(rows)  # approximation; exact count needs pre/post COUNT query
```

### Pattern 3: Lookahead-Safe Schema — Null-Enforced Result

**What:** The `result` column on the `markets` table is `NULL` for unsettled markets. The simulation engine queries only `(ticker, ts)` pairs from the candles table — it must never see a non-NULL result for a candle whose `ts < close_time`.

**When to use:** This schema invariant is enforced at TWO layers:
1. **Ingestion layer:** Only populate `result` when the market `status = 'settled'` AND Kalshi returns a non-empty result string.
2. **Simulation layer (Phase 2):** `BarIterator` must filter result to NULL for any snapshot where `ts < close_time`.

```python
# Source: PITFALLS.md (Pitfall 1 — lookahead bias)
# WRONG — exposes result at bar time:
# SELECT c.close_price, m.result FROM candles c JOIN markets m ON c.ticker = m.ticker

# CORRECT — result gated behind close_time:
# SELECT c.close_price,
#        CASE WHEN c.ts >= m.close_time THEN m.result ELSE NULL END as result
# FROM candles c JOIN markets m ON c.ticker = m.ticker
```

### Pattern 4: DuckDB TIMESTAMP (Naive UTC) Storage

**What:** Store all timestamps as DuckDB `TIMESTAMP` columns (not `TIMESTAMPTZ`). All Python datetime values written are naive UTC (no tzinfo). All Python datetime values read are treated as UTC.

**Why NOT TIMESTAMPTZ:** `TIMESTAMPTZ` in DuckDB 1.5.1 requires `pytz` to be installed and returns offset-aware datetimes (e.g., `2024-11-05 16:00:00-05:00`) rather than UTC, which creates confusion. The simpler approach: store naive UTC + document the convention.

**Eastern Time handling:**
```python
# Source: PITFALLS.md (Pitfall 7) + Python stdlib
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

ET = ZoneInfo("America/New_York")

def kalshi_et_to_utc(dt_str: str) -> datetime:
    """Convert Kalshi ET timestamp string to UTC naive datetime for DB storage."""
    # Kalshi SDK returns datetime objects already TZ-aware (UTC) in the Market model
    # For display-only ET conversion:
    # dt_utc.astimezone(ET)  → use at presentation layer only
    pass
```

**Key note:** The Kalshi SDK's `Market` model returns `open_time`, `close_time`, `expiration_time` as Python `datetime` objects from the API. Confirm whether these are TZ-aware (UTC) or naive at first API call — strip tzinfo before storing in DuckDB TIMESTAMP column.

### Pattern 5: Config Pattern (Insider Tracker Reference)

**What:** `pydantic-settings` `BaseSettings` with env prefix, RSA key path (not content), demo URL default.

```python
# Source: Insider Tracker src/kalshi_tracker/config.py (verified)
class KalshiBacktestSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="KALSHI_BACKTEST_", extra="ignore"
    )
    api_key_id: str
    private_key_path: Path  # path to RSA .pem file — NOT the key content
    api_base_url: str = "https://demo-api.kalshi.co/trade-api/v2"  # DEMO default
    db_path: Path = Path("kalshi_backtest.duckdb")
    rate_limit_rpm: int = 60
```

### Pattern 6: CLI Structure (Insider Tracker Reference)

```python
# Source: Insider Tracker src/kalshi_tracker/cli.py (verified)
import typer
app = typer.Typer(name="kalshi-backtest", help="Kalshi prediction market backtesting engine")

@app.command()
def ingest(
    lookback_days: int = typer.Option(365, help="Days of history to ingest"),
    categories: list[str] = typer.Option([], help="Event categories to ingest"),
) -> None:
    """Ingest historical Kalshi contract data into local DuckDB store."""
    ...
```

### Anti-Patterns to Avoid

- **Joining result into every candle query:** The result column exists on markets, not candles. Never join it into a candle query unless gating behind `ts >= close_time`. The simulation engine will do this gating in Phase 2, but the schema must make it possible.
- **Fetching only settled markets:** Kalshi's `status` filter on `get_markets` defaults to returning all statuses. Do NOT add `status='settled'` filter — that introduces survivorship bias (Pitfall 2).
- **Hardcoding the historical cutoff date:** The cutoff moves forward over time. Always call `GET /trade-api/v2/historical/cutoff` at runtime.
- **Using `TIMESTAMPTZ` without pytz installed:** DuckDB 1.5.1 raises `ModuleNotFoundError: pytz` on insert. Use `TIMESTAMP` + naive UTC convention instead, or include pytz as a dependency.
- **Calling `get_market_candlesticks(ticker=market_ticker, ...)` directly:** The first `ticker` param is the **series_ticker** (e.g., `"KXBTC"`), not the market ticker. Verified from SDK source. Calling with market_ticker in the wrong position will silently return empty results.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RSA-PSS request signing | Custom auth header builder | `kalshi_python.ApiClient.set_kalshi_auth()` | SDK handles per-request RSA signing; reimplementing is error-prone |
| Retry with backoff | `while True: try/except` loop | `tenacity @retry` decorator | Handles jitter, max attempts, wait strategies, exception filtering |
| Config from env | Manual `os.environ.get()` | `pydantic-settings BaseSettings` | Validation, type coercion, .env file support built in |
| CLI argument parsing | `argparse` / `sys.argv` | `typer` | Already fund-wide standard; less boilerplate |
| Candlestick data parsing | Custom JSON deserializer | `kalshi_python.models.Candlestick` (live) / Pydantic model (historical) | Type validation at API boundary catches schema changes |
| Gap detection queries | Python loop over timestamps | DuckDB window functions (`LAG()`, `DATE_DIFF()`) | Vectorized scan over millions of rows; 10x faster than Python iteration |

**Key insight:** The RSA auth is the most complex part of Kalshi API integration. The SDK handles it correctly — the Insider Tracker's `client.py` is the verified reference implementation. Copy the auth setup, don't reinvent it.

---

## Common Pitfalls

### Pitfall 1: Wrong Parameter Order for `get_market_candlesticks`

**What goes wrong:** The SDK method signature is `get_market_candlesticks(self, ticker: str, market_ticker: str, ...)`. The first `ticker` parameter is the **series_ticker** (e.g., `"KXBTC"`), not the market ticker (e.g., `"KXBTCD-24NOV06-T65999"`). Passing market_ticker as the first arg returns an empty response.

**Why it happens:** The method name says "market candlesticks" so developers pass the market ticker first.

**How to avoid:** Always use keyword args: `get_market_candlesticks(ticker=series_ticker, market_ticker=market_ticker, ...)`. Verified from SDK source: URL built as `/series/{ticker}/markets/{market_ticker}/candlesticks`.

**Warning signs:** Empty candlestick arrays returned even for known active markets.

### Pitfall 2: Silent 200 with Empty Data on Wrong Tier

**What goes wrong:** Querying the live endpoint for a market that has crossed the historical cutoff returns HTTP 200 with an empty `candlesticks` array — not a 404. The ingestion pipeline appears to succeed but stores no data.

**Why it happens:** Kalshi partitions data at a rolling cutoff. Markets settled before `market_settled_ts` from `GET /historical/cutoff` are only in the historical tier.

**How to avoid:** Always call `GET /trade-api/v2/historical/cutoff` first. After ingestion, assert that market counts per calendar month are plausible (0 markets for any month in a busy category is a red flag).

**Warning signs:** Ingestion completes without error but DB has months with zero candle rows.

### Pitfall 3: DuckDB TIMESTAMPTZ Requires pytz

**What goes wrong:** `INSERT INTO t VALUES (?, ?, ?)` with a `datetime(tzinfo=timezone.utc)` value into a `TIMESTAMPTZ` column raises `Invalid Input Error: Required module 'pytz' failed to import`.

**Why it happens:** DuckDB's Python integration uses pytz for timezone-aware datetime handling.

**How to avoid:** Either add `pytz` as a dependency, or use `TIMESTAMP` columns and store naive UTC datetimes (strip `tzinfo` before insert).

**Warning signs:** Runtime errors on first insert of timezone-aware datetime.

### Pitfall 4: Kalshi API Category Field Does Not Exist

**What goes wrong:** `get_events` and `get_markets` SDK methods have no `category` parameter. Attempting to filter by category at the API level fails silently or raises a validation error.

**Why it happens:** Kalshi organizes markets by `series_ticker` (e.g., `KXBTC`, `PRES`, `KXINFL`), not by a `category` string. Category is a derived/display concept, not an API field.

**How to avoid:** Filter by `series_ticker` at the API level. Build a mapping from `series_ticker` prefixes to category names (e.g., `KXBTC*` → crypto, `PRES*` → politics). Store `series_ticker` in the markets table for downstream category grouping.

**Warning signs:** Empty response from `get_events(category="crypto")` — that parameter doesn't exist.

### Pitfall 5: Survivorship Bias from Status Filter

**What goes wrong:** Passing `status='settled'` to `get_markets` only returns resolved markets, silently omitting cancelled, voided, or still-open markets from the historical window. The backtest universe is cherry-picked.

**Why it happens:** It seems logical to only want "completed" markets for backtesting.

**How to avoid:** Fetch markets with `min_close_ts`/`max_close_ts` date range filters. Ingest ALL markets that were open in the target period. Store `status` column — let the simulation engine decide what to include.

**Warning signs:** No cancelled or voided markets in the DB; round numbers of markets per month.

### Pitfall 6: Timezone Handling During DST Transitions

**What goes wrong:** Kalshi event close times are Eastern Time. A market that closes at "4 PM Eastern" on the day of DST change is off by 1 hour if computed with a fixed UTC offset (-5 vs -4).

**Why it happens:** Using hardcoded UTC offset arithmetic (`close_time - timedelta(hours=5)`) instead of proper timezone library.

**How to avoid:** Use `zoneinfo.ZoneInfo("America/New_York")` from Python stdlib (3.9+). Never use manual UTC offset arithmetic for ET conversion.

**Warning signs:** Occasional signal-after-expiry errors that cluster in March and November.

---

## Code Examples

Verified patterns from official sources:

### DuckDB Schema (Verified Working — DuckDB 1.5.1)
```python
# Source: verified locally 2026-04-04 against DuckDB 1.5.1
SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS markets (
    ticker          VARCHAR NOT NULL PRIMARY KEY,
    event_ticker    VARCHAR NOT NULL,
    series_ticker   VARCHAR NOT NULL,
    subtitle        TEXT,
    open_time       TIMESTAMP NOT NULL,    -- UTC, naive
    close_time      TIMESTAMP NOT NULL,    -- UTC, naive
    expiration_time TIMESTAMP,             -- UTC, naive
    status          VARCHAR NOT NULL,      -- initialized|active|closed|settled|determined
    result          VARCHAR,               -- 'yes'|'no'|'' — NULL until settled
    ingested_at     TIMESTAMP NOT NULL     -- UTC, naive
);

CREATE TABLE IF NOT EXISTS candles (
    ticker          VARCHAR NOT NULL,
    ts              TIMESTAMP NOT NULL,    -- candle start UTC, naive (daily = midnight UTC)
    open_price      INTEGER,               -- yes price in cents (0-100)
    high_price      INTEGER,
    low_price       INTEGER,
    close_price     INTEGER NOT NULL,      -- yes price in cents (0-100)
    volume          INTEGER,               -- contracts traded in period
    ingested_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (ticker, ts)               -- idempotent upsert key
);

CREATE INDEX IF NOT EXISTS idx_candles_ticker ON candles(ticker);
CREATE INDEX IF NOT EXISTS idx_candles_ts ON candles(ts);
CREATE INDEX IF NOT EXISTS idx_markets_event ON markets(event_ticker);
CREATE INDEX IF NOT EXISTS idx_markets_series ON markets(series_ticker);
CREATE INDEX IF NOT EXISTS idx_markets_close_time ON markets(close_time);
"""
```

### Idempotent Insert (Verified DuckDB 1.5.1)
```python
# Source: verified locally 2026-04-04
# Candles — insert-only, skip duplicates
con.execute("""
    INSERT INTO candles (ticker, ts, open_price, high_price, low_price, close_price, volume, ingested_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT DO NOTHING
""", [ticker, ts, open_p, high_p, low_p, close_p, volume, now_utc])

# Markets — upsert (result/status can update on re-ingestion)
con.execute("""
    INSERT INTO markets (ticker, event_ticker, series_ticker, subtitle, open_time, close_time,
                         expiration_time, status, result, ingested_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (ticker) DO UPDATE SET
        status = excluded.status,
        result = excluded.result,
        ingested_at = excluded.ingested_at
""", [ticker, event_ticker, series_ticker, subtitle, open_t, close_t, exp_t, status, result, now])
```

### DuckDB Gap Detection Query
```python
# Source: DuckDB documentation — window functions
GAP_QUERY = """
WITH daily AS (
    SELECT ticker, ts,
           LAG(ts) OVER (PARTITION BY ticker ORDER BY ts) AS prev_ts
    FROM candles
    WHERE ticker = ?
),
gaps AS (
    SELECT ticker, ts, prev_ts,
           DATE_DIFF('day', prev_ts, ts) AS gap_days
    FROM daily
    WHERE DATE_DIFF('day', prev_ts, ts) > 1
)
SELECT ticker, prev_ts AS gap_start, ts AS gap_end, gap_days
FROM gaps
ORDER BY gap_days DESC
"""
```

### RSA Auth Setup (From Insider Tracker — Verified)
```python
# Source: Insider Tracker src/kalshi_tracker/kalshi/client.py (verified)
from kalshi_python import ApiClient, Configuration
from kalshi_python.api import MarketsApi

config = Configuration(host=settings.api_base_url)
api_client = ApiClient(configuration=config)
api_client.set_kalshi_auth(
    key_id=settings.api_key_id,
    private_key_path=str(settings.private_key_path),  # path string, NOT key content
)
markets_api = MarketsApi(api_client)
```

### Incremental Sync — Fetch Only New Data
```python
# Source: architecture pattern derived from PITFALLS.md + SDK introspection
def get_last_ingested_ts(con: duckdb.DuckDBPyConnection, ticker: str) -> int | None:
    """Return Unix epoch of last candle for ticker, or None if no data exists."""
    row = con.execute(
        "SELECT MAX(EPOCH(ts))::BIGINT FROM candles WHERE ticker = ?", [ticker]
    ).fetchone()
    return row[0] if row and row[0] is not None else None

# Use as start_ts for next fetch:
# start_ts = last_ts + 86400  # next day after last candle
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Kalshi served all historical data from live endpoint | Live/historical tier split enforced at rolling cutoff | ~2024-2025 migration | All historical fetches must route through `/historical/*` endpoints |
| kalshi-python v1.x with HTTP basic auth | v2.x with RSA-PSS per-request signing | 2024 | Auth setup requires PEM key file, not username/password |
| SQLite for local analytical storage | DuckDB preferred for columnar workloads | 2022-2024 | 8x faster time-series range queries |
| `TIMESTAMPTZ` in DuckDB with pytz | `TIMESTAMP` (naive UTC) + application convention | DuckDB 1.x | Avoids pytz dependency and offset-aware confusion |

---

## Open Questions

1. **Historical candlestick endpoint URL and auth**
   - What we know: The SDK does not wrap `/trade-api/v2/historical/*`. These need direct httpx calls.
   - What's unclear: The exact URL pattern for historical candlesticks — likely `GET /trade-api/v2/historical/markets/{ticker}/candlesticks` but must be confirmed against official docs at implementation time.
   - Recommendation: Fetch `GET /trade-api/v2/historical/cutoff` response first to understand the data model; then check the response format for historical candlestick response vs live candlestick response.

2. **Kalshi Candlestick price units (cents vs cents/100)**
   - What we know: SDK `Candlestick` fields are `Union[StrictFloat, StrictInt]`. Market `yes_bid` is in the 0-100 range (cents).
   - What's unclear: Whether candlestick `open/high/low/close` values are 0-100 (cents) or 0-1 (fractional probability). Kalshi documentation sometimes uses "cents" loosely.
   - Recommendation: Log the raw values from the first real API call and assert range 0-100. Store as INTEGER cents in DuckDB (multiply by 100 if API returns fractions).

3. **Rate limits for bulk historical ingestion**
   - What we know: Insider Tracker uses 60 RPM default. Official docs exist at `docs.kalshi.com/getting_started/rate_limits`.
   - What's unclear: Whether historical endpoint rate limits differ from live endpoint limits.
   - Recommendation: Start with 60 RPM default + tenacity backoff. Add a configurable `KALSHI_BACKTEST_RATE_LIMIT_RPM` env var.

4. **Historical data depth available**
   - What we know: Project targets 1 year lookback; success criterion requires "at least 1 year of contract snapshots."
   - What's unclear: Whether Kalshi's historical API has full daily candlestick coverage back to 2021 or if coverage starts later.
   - Recommendation: Call `GET /historical/cutoff` in development to see the earliest available date before committing to the 1-year target.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | ✓ | 3.12.11 | — |
| uv | Package management | ✓ | 0.11.2 | — |
| git | Version control | ✓ | 2.50.1 | — |
| DuckDB | Data storage | ✓ | 1.5.1 (global) | — |
| kalshi-python >=2.1.4 | API client | ✓ | 2.1.0 in tracker venv; must `uv add` to backtest project | uv add kalshi-python |
| httpx | Historical API calls | Not yet in backtest project | — | uv add httpx |
| KALSHI_API_KEY_ID env var | Kalshi auth | Unknown | — | Requires user to create API key at kalshi.com |
| KALSHI_PRIVATE_KEY_PATH env var | Kalshi auth | Unknown | — | Requires RSA PEM file from Kalshi account |

**Missing dependencies with no fallback:**
- Kalshi API credentials (API key ID + RSA private key PEM) — required for any live data fetch. User must create these at kalshi.com before ingest can run. Tests should use fixture-based mocks so CI works without credentials.

**Missing dependencies with fallback:**
- kalshi-python, httpx, duckdb: not yet installed in the backtest project venv; install via `uv add` as part of Wave 0.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.x |
| Config file | `pyproject.toml` [tool.pytest.ini_options] — Wave 0 |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ --cov=src/kalshi_backtest --cov-report=term-missing` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | Markets + candlesticks ingested from API fixture | unit | `pytest tests/test_fetcher.py -x` | ❌ Wave 0 |
| DATA-02 | Cutoff resolver routes live vs historical correctly | unit | `pytest tests/test_client.py::test_cutoff_routing -x` | ❌ Wave 0 |
| DATA-03 | Schema allows NULL result for open markets; non-NULL only after settled | unit | `pytest tests/test_schema.py::test_lookahead_safe_schema -x` | ❌ Wave 0 |
| DATA-04 | Re-running ingest on already-stored data produces no duplicates | unit | `pytest tests/test_pipeline.py::test_idempotent_ingest -x` | ❌ Wave 0 |
| DATA-05 | Gap detection identifies missing dates; report printed after ingestion | unit | `pytest tests/test_validator.py -x` | ❌ Wave 0 |
| DATA-06 | DST transition date stored as correct UTC; no off-by-1-hour error | unit | `pytest tests/test_schema.py::test_dst_timestamp_roundtrip -x` | ❌ Wave 0 |
| CLI-01 | `kalshi-backtest ingest --help` exits 0; dry-run mode prints plan | integration | `pytest tests/test_cli.py::test_ingest_help -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ --cov=src/kalshi_backtest --cov-report=term-missing`
- **Phase gate:** Full suite green + coverage >= 80% before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `pyproject.toml` — project scaffold with dependencies listed above
- [ ] `src/kalshi_backtest/__init__.py` — package init
- [ ] `tests/conftest.py` — shared fixtures (DuckDB in-memory connection, fixture JSON loader)
- [ ] `tests/fixtures/markets.json` — recorded Kalshi API market response
- [ ] `tests/fixtures/candlesticks.json` — recorded Kalshi API candlestick response
- [ ] Framework install: `uv add kalshi-python httpx tenacity duckdb pydantic pydantic-settings typer structlog rich && uv add --dev pytest pytest-cov ruff freezegun`

---

## Project Constraints (from CLAUDE.md)

Directives from `kalshi-backtest/CLAUDE.md` that the planner must verify compliance with:

| Constraint | Implication for Phase 1 |
|------------|------------------------|
| Data source: Kalshi API only | No yfinance, no third-party data — all data from Kalshi REST API |
| Stack: Python 3.11+, uv | `requires-python = ">=3.11,<3.14"` in pyproject.toml; `uv add` for all deps |
| Immutability: append new snapshots only | `ON CONFLICT DO NOTHING` on candles; never `UPDATE` or `DELETE` candle rows |
| Independence: standalone module | No `from kalshi_tracker import ...` anywhere in this module |
| History: 1 year lookback | Default `lookback_days=365` in CLI; verify API has sufficient depth |
| DuckDB for storage | Confirmed — columnar, zero-server, append-only fits perfectly |
| All timestamps UTC | All DuckDB `TIMESTAMP` columns store naive UTC; no local time in DB |
| No hardcoded secrets | API key ID and private key path via `.env` + pydantic-settings |
| ruff for lint/format | `uv add --dev ruff`; `ruff check` and `ruff format` in CI |
| 80% test coverage | `pytest-cov` in dev dependencies; enforced at phase gate |
| Immutable data patterns | Frozen Pydantic models for API response types; no mutation after parse |

---

## Sources

### Primary (HIGH confidence)
- `kalshi-python` SDK introspection (2026-04-04, v2.1.0) — verified API classes, method signatures, URL patterns, Candlestick/Market model fields
- DuckDB 1.5.1 local execution (2026-04-04) — verified `ON CONFLICT DO NOTHING`, `PRIMARY KEY`, `TIMESTAMP` column behavior
- Insider Tracker `src/kalshi_tracker/kalshi/client.py` — verified RSA auth setup, token bucket rate limiting, SDK usage pattern
- Insider Tracker `src/kalshi_tracker/config.py` — verified pydantic-settings pattern with `KALSHI_` prefix, PEM path convention
- `kalshi-backtest/CLAUDE.md` — authoritative project constraints

### Secondary (MEDIUM confidence)
- `kalshi-backtest/.planning/research/STACK.md` — stack research with source citations
- `kalshi-backtest/.planning/research/ARCHITECTURE.md` — architecture patterns
- `kalshi-backtest/.planning/research/PITFALLS.md` — domain pitfalls with sources

### Tertiary (LOW confidence — verify at implementation time)
- Kalshi historical endpoint URL patterns — assumed from PITFALLS.md/ARCHITECTURE.md; must verify against live `GET /historical/cutoff` response
- Historical API rate limits — not confirmed; assume same as live (60 RPM) until tested

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified against live SDK version 2.1.0 and DuckDB 1.5.1
- Architecture: HIGH — SDK introspection confirmed dual-client requirement; DuckDB patterns verified with running code
- Pitfalls: HIGH for SDK pitfalls (verified); MEDIUM for rate limit / historical endpoint specifics (untested)

**Research date:** 2026-04-04
**Valid until:** 2026-05-04 (DuckDB and kalshi-python stable; Kalshi API may change historical endpoint behavior)
