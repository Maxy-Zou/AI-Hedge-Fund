# Phase 2: Price Data Pipeline - Research

**Researched:** 2026-03-28
**Domain:** yfinance bulk download, PostgreSQL OHLCV storage, incremental data pipeline
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None — discuss phase was skipped per `workflow.skip_discuss`. All implementation choices are at Claude's discretion.

### Claude's Discretion
All implementation choices: data model design, chunking strategy, anomaly storage approach, CLI command names, module structure, test organization.

### Deferred Ideas (OUT OF SCOPE)
None specified.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | Download daily OHLCV price data via yfinance for all tickers in mid-cap universe | yfinance 1.2.0 `download()` confirmed in venv; multi-ticker bulk call returns MultiIndex DataFrame; `auto_adjust=True` handles split-adjusted prices |
| DATA-02 | Cache price data in PostgreSQL to avoid redundant API calls | `price_bars` table with `UNIQUE(ticker, bar_date)`; `ON CONFLICT DO NOTHING` for idempotent inserts; pandas `to_sql(if_exists='append')` for efficient bulk load |
| DATA-03 | Incremental daily updates — append new bars, never overwrite historical | Query `MAX(bar_date)` per ticker; download only from `last_date + 1 day`; PostgreSQL UNIQUE constraint enforces immutability at DB level |
| DATA-04 | Validate downloaded data: gap detection, ±50% daily return anomaly, missing ticker alert | `pct_change().abs() > 0.50` flags anomalies; `pd.date_range(freq='B').difference(actual_dates)` detects gaps; separate `price_anomalies` table stores flags for downstream exclusion |
| DATA-06 | Chunk yfinance downloads (~80 tickers/batch) with retry logic for rate limits | `itertools.batched` (or manual slicing) for 80-ticker batches; `yfinance.exceptions.YFRateLimitError` confirmed in v1.2.0; `tenacity` with `retry_if_exception_type(YFRateLimitError)` + `wait_exponential` |
</phase_requirements>

---

## Summary

Phase 2 builds the OHLCV price data pipeline on top of the Phase 1 foundation. The existing `fund-backtest` package has all the scaffolding needed: SQLAlchemy 2.0, Alembic migrations, tenacity retry decorators, structlog, and the Typer CLI. This phase follows the same structural patterns as the `universe/` module — a `price/` module with types, downloader, validator, repository, and builder components, plus a new `data` CLI subcommand group.

The core technical challenge is safe bulk data ingestion. yfinance 1.2.0 (confirmed installed) supports `download()` for multi-ticker batches returning a MultiIndex DataFrame keyed by `(field, ticker)`. At ~80 tickers per batch, Yahoo Finance rate limits are avoided. The `YFRateLimitError` exception class exists in yfinance 1.2.0 and is the correct target for tenacity retry. Failed tickers appear as all-NaN columns in the multi-ticker DataFrame — detection is straightforward.

PostgreSQL storage uses cents integers (BIGINT, consistent with `market_cap_cents` convention) and a composite UNIQUE constraint on `(ticker, bar_date)` with `ON CONFLICT DO NOTHING` to guarantee append-only immutability. The initial 5-year load is ~252,000 rows (~24 MB) — no partitioning needed. Anomalous bars (±50% single-day return) are stored in a separate `price_anomalies` table so downstream queries can exclude flagged tickers without modifying the immutable `price_bars` table.

**Primary recommendation:** Follow the `universe/` module pattern exactly — same file layout, same testing approach (mock external calls in unit tests, PostgreSQL testcontainer for integration tests), same tenacity decorator pattern.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| yfinance | 1.2.0 (installed) | Daily OHLCV download | Free, no API key, bulk multi-ticker in one call, already in pyproject.toml |
| SQLAlchemy | 2.0.48 (installed) | ORM + bulk insert | Already in stack; `pg_insert().on_conflict_do_nothing()` for idempotent inserts |
| pandas | 3.0.1 (installed) | DataFrame manipulation | Returned directly by yfinance; `to_sql(if_exists='append')` for bulk DB insert |
| tenacity | 9.1.4 (installed) | Retry on rate limit | Already used in `universe/enricher.py`; `YFRateLimitError` is the exact exception |
| Alembic | 1.18.4 (installed) | Schema migration | Next migration: `002_price_bars_schema.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | 25.5.0 (installed) | Structured logging | Already used project-wide; log anomaly flags and coverage alerts |
| rich | 14.0+ (installed) | CLI output tables | Already used in CLI; coverage report table |
| freezegun | 1.5.5 (installed) | Date mocking in tests | Mock "today" for incremental update logic |
| factory-boy | 3.3+ (installed) | Test data factories | Generate OHLCV DataFrames for unit tests without hitting yfinance |
| unittest.mock | stdlib | Mock yfinance in tests | pytest-httpx won't work (yfinance uses requests, not httpx); use `patch('yfinance.download')` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| cents (BIGINT) for price | FLOAT/NUMERIC | Project already uses cents integers for `market_cap_cents`; consistent convention; avoids FP precision issues |
| separate `price_anomalies` table | `is_flagged` column on `price_bars` | Separate table is cleaner: anomaly records are their own entity with `is_reviewed` state; doesn't pollute immutable bar rows |
| `ON CONFLICT DO NOTHING` | check-then-insert | Atomic, no race condition; idempotent; correct for append-only semantics |
| `pandas.to_sql()` for bulk insert | SQLAlchemy Core bulk insert | `to_sql()` is simpler for DataFrame-native data; Core is marginally faster but complexity not justified at 252K rows |

**No new packages needed.** All dependencies are already installed in the venv.

---

## Architecture Patterns

### Recommended Project Structure

```
backtest/src/fund_backtest/
├── price/                   # New module (mirrors universe/ pattern)
│   ├── __init__.py
│   ├── types.py             # PriceBar, ValidationResult, DownloadSummary, CoverageReport
│   ├── downloader.py        # download_batch() with chunking + tenacity retry
│   ├── validator.py         # validate_bars(): anomaly detection, gap detection, coverage
│   ├── repository.py        # PriceBarRepository: get_last_dates(), insert_bars(), get_bars()
│   └── builder.py           # PriceBuilder: download() and update() orchestration
├── db/
│   └── migrations/versions/
│       └── 002_price_bars_schema.py   # NEW: price_bars + price_anomalies tables
├── config.py                # Add PriceSettings (batch_size=80, lookback_years=5, ...)
└── cli.py                   # Add data_app Typer subgroup with download/update/coverage
```

```
backtest/tests/
├── unit/
│   ├── test_downloader.py   # chunking, retry behavior (mock yf.download)
│   ├── test_validator.py    # anomaly detection, gap detection, coverage math
│   └── test_price_types.py  # PriceBar validation, cents conversion
└── integration/
    └── test_price_pipeline.py  # full pipeline against PostgreSQL testcontainer
```

### Pattern 1: Chunked Download with Tenacity Retry

**What:** Split ~200 tickers into 80-ticker batches, retry each batch on `YFRateLimitError`.
**When to use:** Every call to yfinance for bulk price data.

```python
# Source: verified against yfinance 1.2.0 exceptions module
import time
import yfinance as yf
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from yfinance.exceptions import YFRateLimitError
import requests


@retry(
    retry=retry_if_exception_type((YFRateLimitError, requests.exceptions.HTTPError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=5, max=60),
    reraise=True,
)
def _download_batch(tickers: list[str], **kwargs) -> pd.DataFrame:
    """Download one batch with retry on rate limit."""
    return yf.download(tickers, **kwargs, progress=False, multi_level_index=True)


def download_in_chunks(
    tickers: list[str],
    batch_size: int = 80,
    batch_sleep_secs: float = 1.0,
    **kwargs,
) -> list[tuple[str, pd.DataFrame]]:
    """Download tickers in batches, return per-ticker DataFrames."""
    results = []
    batches = [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]
    for batch in batches:
        raw = _download_batch(batch, **kwargs)
        for ticker in batch:
            if ticker in raw.columns.get_level_values(1):
                ticker_df = raw.xs(ticker, level=1, axis=1).dropna(how='all')
                results.append((ticker, ticker_df))
            # else: ticker returned no data — tracked in coverage
        time.sleep(batch_sleep_secs)
    return results
```

### Pattern 2: Failed Ticker Detection

**What:** A ticker that yfinance cannot find appears as all-NaN columns in the multi-ticker DataFrame.
**When to use:** After every batch download.

```python
# Source: verified by live test — FAKEXXX999 returned all-NaN Close column
def get_failed_tickers(
    raw_df: pd.DataFrame, requested_tickers: list[str]
) -> list[str]:
    """Return tickers with no valid data (all NaN close)."""
    failed = []
    for ticker in requested_tickers:
        if ticker not in raw_df.columns.get_level_values(1):
            failed.append(ticker)
        elif raw_df['Close'][ticker].isna().all():
            failed.append(ticker)
    return failed
```

### Pattern 3: Float-to-Cents Conversion

**What:** yfinance returns adjusted prices as Python floats. Store as rounded integer cents.
**When to use:** At ingestion boundary, before any DB insert.

```python
# Source: verified — round() prevents floating-point truncation errors
def price_to_cents(price: float) -> int:
    """Convert float price to integer cents. Always use round(), not int()."""
    return round(price * 100)
```

### Pattern 4: ON CONFLICT DO NOTHING for Append-Only Safety

**What:** PostgreSQL's `INSERT ... ON CONFLICT DO NOTHING` prevents duplicate bars without raising an error. Enforces immutability at the DB level.
**When to use:** Every batch insert — makes the insert operation idempotent.

```python
# Source: SQLAlchemy 2.0 PostgreSQL dialect
from sqlalchemy.dialects.postgresql import insert as pg_insert

def insert_bars(session, rows: list[dict]) -> int:
    """Bulk insert bars; skip duplicates. Returns count inserted."""
    if not rows:
        return 0
    stmt = (
        pg_insert(PriceBar)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["ticker", "bar_date"])
    )
    result = session.execute(stmt)
    session.commit()
    return result.rowcount
```

### Pattern 5: Incremental Update Strategy

**What:** Query the max bar_date per ticker; download only from `max_date + 1 day`. Tickers with no bars at all get the full 5-year download.
**When to use:** `data update` command (daily).

```python
# Source: verified query pattern against SQLite proxy
def get_tickers_needing_update(
    session,
    active_tickers: list[str],
    lookback_years: int = 5,
) -> dict[str, date]:
    """
    Returns {ticker: start_date} — start_date is last_bar + 1 day,
    or today - lookback_years for tickers with no bars.
    """
    from datetime import date, timedelta
    from sqlalchemy import text

    result = session.execute(
        text("SELECT ticker, MAX(bar_date) AS last_date FROM price_bars GROUP BY ticker")
    )
    last_dates = {row.ticker: row.last_date for row in result}

    full_history_start = date.today() - timedelta(days=lookback_years * 365)
    needs_update = {}
    for ticker in active_tickers:
        if ticker in last_dates:
            needs_update[ticker] = last_dates[ticker] + timedelta(days=1)
        else:
            needs_update[ticker] = full_history_start
    return needs_update
```

### Pattern 6: Coverage Report Calculation

**What:** Count tickers that returned at least one valid bar; alert if below threshold.
**When to use:** After each download/update run.

```python
# Source: derived from requirements DATA-04, verified math
def compute_coverage(
    requested: list[str],
    successful: list[str],
    threshold: float = 0.95,
) -> dict:
    """Compute coverage ratio; flag alert if below threshold."""
    ratio = len(successful) / len(requested) if requested else 0.0
    return {
        "requested": len(requested),
        "successful": len(successful),
        "failed": len(requested) - len(successful),
        "coverage_pct": ratio * 100,
        "below_threshold": ratio < threshold,
    }
```

### Anti-Patterns to Avoid

- **`int()` instead of `round()` for float-to-cents:** `int(183.73 * 100)` = 18372 (truncation error). Always use `round()`.
- **`threads=True` with DEBUG logging:** yfinance auto-disables threading when log level is DEBUG — log output becomes interleaved noise. Set `log_level="INFO"` for bulk downloads.
- **Assuming all tickers share the same last_date:** Newly added tickers have no bars; erroneously entering `date.today()` as start date would skip their 5-year history entirely.
- **Using `to_sql()` without `on_conflict` handling:** pandas `to_sql(if_exists='append')` does not deduplicate — use SQLAlchemy Core `pg_insert().on_conflict_do_nothing()` instead.
- **session.delete() or UPDATE on price_bars:** Project immutability convention (from STATE.md). Never modify historical bars. Anomalies live in `price_anomalies`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry on 429 | Custom sleep/retry loop | `tenacity` | Already installed; handles jitter, max attempts, re-raise semantics |
| Split-adjusted prices | Corporate action math | `yfinance auto_adjust=True` | yfinance applies Yahoo's split/dividend adjustments automatically |
| Trading day calendar | List of US market holidays | `pandas.bdate_range()` | Business-day frequency handles weekends; full market holiday calendar not needed for gap detection at daily granularity |
| Chunking list into batches | Custom slice logic | `[tickers[i:i+n] for i in range(0, len, n)]` | Simple one-liner; no library needed |
| DataFrame -> DB bulk insert | Manual INSERT loops | `pandas.to_sql()` + SQLAlchemy engine | Handles batching internally; `method='multi'` sends multi-row inserts |

**Key insight:** Every hard part of this phase is already solved by libraries already installed. The implementation is primarily wiring.

---

## Common Pitfalls

### Pitfall 1: Silent Data Gaps from 429 Without Retry

**What goes wrong:** A batch of 80 tickers gets a 429 mid-download. yfinance raises `YFRateLimitError`. Without retry, the entire batch is dropped silently if the exception is caught at the wrong level.
**Why it happens:** The batch loop catches the exception and logs a warning, but moves on — leaving those tickers with no bars.
**How to avoid:** Apply `@retry` at the batch level, not the ticker level. Let `tenacity` handle the wait and re-issue the entire batch.
**Warning signs:** Coverage report shows ~80 ticker-sized gaps; log shows a single WARNING for a batch at a specific time.

### Pitfall 2: Overwriting Historical Bars

**What goes wrong:** Re-running `data download` on a populated database performs UPDATE on existing rows instead of skip.
**Why it happens:** Using `pandas.to_sql(if_exists='replace')` or `if_exists='append'` without conflict handling.
**How to avoid:** Use `pg_insert().on_conflict_do_nothing()` exclusively. Test with a mock that verifies no UPDATE statements are issued.
**Warning signs:** Row count stays the same after re-run but `updated_at` timestamps change.

### Pitfall 3: Float Truncation in Price-to-Cents Conversion

**What goes wrong:** `int(183.73 * 100)` evaluates to `18372` due to floating-point representation.
**Why it happens:** Python float `183.73 * 100` = `18372.999...`, truncated to 18372 by `int()`.
**How to avoid:** Always `round(price * 100)`. Add unit test: `assert price_to_cents(183.73) == 18373`.
**Warning signs:** OHLC values are consistently 1 cent below expected.

### Pitfall 4: Anomaly Ticker vs Bar Exclusion Confusion

**What goes wrong:** Downstream code excludes the entire ticker's history when one bar is anomalous, rather than just excluding that specific bar.
**Why it happens:** `price_anomalies` table stores a flag per bar, but the query to exclude is incorrectly written as `WHERE ticker NOT IN (SELECT DISTINCT ticker FROM price_anomalies WHERE is_reviewed=false)`.
**How to avoid:** Downstream queries should join on `(ticker, bar_date)` — exclude the specific bar, not the whole ticker history. Document this in the repository's `get_bars()` method.
**Warning signs:** Tickers with a single historical anomaly disappear from the full 5-year return series.

### Pitfall 5: Multi-Level Column Indexing Confusion

**What goes wrong:** `df['Close']['AAPL']` works but `df['AAPL']['Close']` raises KeyError depending on `group_by` setting.
**Why it happens:** yfinance returns `(field, ticker)` for `group_by='column'` and `(ticker, field)` for `group_by='ticker'`.
**How to avoid:** Always use default `group_by='column'` (the yfinance default); use `df.xs(ticker, level=1, axis=1)` to extract per-ticker slices.
**Warning signs:** KeyError during per-ticker extraction; shape mismatch on single-ticker downloads.

### Pitfall 6: "Gaps" from Market Holidays

**What goes wrong:** Gap detection flags missing bars on US market holidays (e.g., Martin Luther King Day, Presidents Day).
**Why it happens:** `pd.bdate_range()` generates all business days including holidays; actual trading data has no bars on those days.
**How to avoid:** Gap detection should alert only when consecutive gaps exceed 3 trading days (accounts for holidays and long weekends). Single-day and 2-day gaps are expected.
**Warning signs:** Hundreds of spurious "missing bar" warnings on known holidays.

---

## Database Schema Design

### Table: `price_bars`

```sql
CREATE TABLE price_bars (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker      VARCHAR(10) NOT NULL,
    bar_date    DATE NOT NULL,
    open_cents  BIGINT NOT NULL,
    high_cents  BIGINT NOT NULL,
    low_cents   BIGINT NOT NULL,
    close_cents BIGINT NOT NULL,
    volume      BIGINT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_price_bars_ticker_date UNIQUE (ticker, bar_date)
);
CREATE INDEX ix_price_bars_ticker      ON price_bars (ticker);
CREATE INDEX ix_price_bars_bar_date    ON price_bars (bar_date);
CREATE INDEX ix_price_bars_ticker_date ON price_bars (ticker, bar_date);
```

**Notes:**
- `open_cents` through `close_cents`: BIGINT, consistent with `market_cap_cents` convention
- `volume`: BIGINT for safety (high-volume days)
- No `updated_at`: append-only — rows are never modified (TimestampMixin not used here)
- Composite UNIQUE constraint enforces immutability at DB level
- Triple index: by ticker (for `data update`), by date (for cross-sectional queries), composite (primary access pattern)

### Table: `price_anomalies`

```sql
CREATE TABLE price_anomalies (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker           VARCHAR(10) NOT NULL,
    bar_date         DATE NOT NULL,
    anomaly_type     VARCHAR(50) NOT NULL,  -- 'return_spike_plus' | 'return_spike_minus'
    daily_return_pct NUMERIC(10, 4) NOT NULL,
    is_reviewed      BOOLEAN NOT NULL DEFAULT false,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_price_anomalies_ticker_date_type UNIQUE (ticker, bar_date, anomaly_type)
);
CREATE INDEX ix_price_anomalies_ticker     ON price_anomalies (ticker);
CREATE INDEX ix_price_anomalies_reviewed   ON price_anomalies (is_reviewed) WHERE is_reviewed = false;
```

**Notes:**
- `is_reviewed = false` partial index speeds up the "get all unreviewed anomalies" query used by downstream modules
- `daily_return_pct` uses NUMERIC for precision (anomaly value is human-readable, not used in computation)
- Both tables go in migration `002_price_bars_schema.py`

---

## Code Examples

### PriceBar Pydantic Model

```python
# Source: follows UniverseEntry pattern from universe/types.py
from __future__ import annotations
from datetime import date
from pydantic import BaseModel, field_validator


class PriceBar(BaseModel):
    """A single OHLCV bar for one ticker on one date."""
    ticker: str
    bar_date: date
    open_cents: int
    high_cents: int
    low_cents: int
    close_cents: int
    volume: int

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        return v.upper().strip()

    @classmethod
    def from_yfinance_row(
        cls, ticker: str, bar_date: date, row: "pd.Series"
    ) -> "PriceBar":
        """Build PriceBar from a yfinance DataFrame row. Uses round() for float safety."""
        return cls(
            ticker=ticker,
            bar_date=bar_date,
            open_cents=round(float(row["Open"]) * 100),
            high_cents=round(float(row["High"]) * 100),
            low_cents=round(float(row["Low"]) * 100),
            close_cents=round(float(row["Close"]) * 100),
            volume=int(row["Volume"]),
        )
```

### PriceSettings Config Extension

```python
# Source: follows UniverseSettings pattern from config.py
class PriceSettings(BaseModel):
    """Price data configuration — loaded from config/price.yaml."""
    lookback_years: int = 5
    batch_size: int = 80
    batch_sleep_secs: float = 1.0
    coverage_alert_threshold: float = 0.95
    return_anomaly_threshold: float = 0.50
    max_gap_days: int = 3  # gaps > 3 business days trigger warning
```

### Anomaly Detection

```python
# Source: verified with live data — pct_change().abs() > 0.50 is the correct check
def detect_return_anomalies(
    ticker: str,
    bars_df: pd.DataFrame,
    threshold: float = 0.50,
) -> list[dict]:
    """
    Detect single-day return spikes exceeding ±threshold.
    bars_df must have a 'Close' column (float) indexed by date.
    Returns list of dicts ready for price_anomalies insert.
    """
    returns = bars_df["Close"].pct_change()
    anomalies = returns[returns.abs() > threshold]
    result = []
    for bar_date, ret in anomalies.items():
        result.append({
            "ticker": ticker,
            "bar_date": bar_date.date() if hasattr(bar_date, "date") else bar_date,
            "anomaly_type": "return_spike_plus" if ret > 0 else "return_spike_minus",
            "daily_return_pct": round(ret * 100, 4),
        })
    return result
```

### CLI data Commands

```python
# Source: follows universe_app pattern from cli.py
data_app = typer.Typer(help="Manage OHLCV price data.")
app.add_typer(data_app, name="data")

@data_app.command()
def download(dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    """Download 5 years of daily OHLCV bars for all active universe tickers."""
    ...

@data_app.command()
def update() -> None:
    """Append new bars since last download — never modifies historical data."""
    ...

@data_app.command()
def coverage() -> None:
    """Show data coverage: tickers with bars, date range, anomaly flags."""
    ...
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `yfinance 0.2.x` — deprecated API | `yfinance 1.x` — stable API (v1.0 was breaking) | Feb 2026 | `yf.download()` signature unchanged; `YFRateLimitError` added in 1.x |
| `pandas_datareader` Yahoo backend | `yfinance.download()` directly | 2023 | pandas_datareader Yahoo backend removed; yfinance is the replacement |
| `period='5y'` in download | Explicit `start=` date | Always | `period='5y'` confirmed to return 1,256 bars (5y × 252 days) as of Mar 2026 |

**Deprecated/outdated:**
- `yfinance 0.2.x`: `download()` API changed in 1.0; `multi_level_index` parameter is new in v1.x
- `pandas_datareader`: Yahoo Finance backend removed — do not use

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| yfinance | DATA-01, DATA-06 | Yes | 1.2.0 | — |
| SQLAlchemy | DATA-02, DATA-03 | Yes | 2.0.48 | — |
| pandas | DATA-01, DATA-04 | Yes | 3.0.1 | — |
| tenacity | DATA-06 | Yes | 9.1.4 | — |
| PostgreSQL | DATA-02 | Yes (testcontainer) | 16 | SQLite for unit tests only |
| Alembic | Schema migration | Yes | 1.18.4 | — |
| freezegun | Tests | Yes | 1.5.5 | — |
| testcontainers | Integration tests | Yes | 4.14+ | — |

**Missing dependencies with no fallback:** None.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `backtest/pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `cd backtest && uv run pytest tests/unit/ -x -q` |
| Full suite command | `cd backtest && uv run pytest -x -q --cov=fund_backtest --cov-fail-under=80` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | yfinance download returns OHLCV rows | unit | `pytest tests/unit/test_downloader.py -x` | Wave 0 |
| DATA-02 | Bars inserted to PostgreSQL | integration | `pytest tests/integration/test_price_pipeline.py -x -m integration` | Wave 0 |
| DATA-03 | Re-insert does not modify historical bar | integration | `pytest tests/integration/test_price_pipeline.py::test_update_appends_only_new_bars -x` | Wave 0 |
| DATA-04 | ±50% return triggers anomaly record | unit | `pytest tests/unit/test_validator.py -x` | Wave 0 |
| DATA-04 | Coverage below 95% triggers alert | unit | `pytest tests/unit/test_validator.py::test_coverage_alert_below_threshold -x` | Wave 0 |
| DATA-06 | 200 tickers chunked into 80-batch groups | unit | `pytest tests/unit/test_downloader.py::test_chunk_tickers_into_batches -x` | Wave 0 |
| DATA-06 | YFRateLimitError triggers retry | unit | `pytest tests/unit/test_downloader.py::test_download_batch_retries_on_rate_limit -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backtest && uv run pytest tests/unit/ -x -q`
- **Per wave merge:** `cd backtest && uv run pytest -x -q --cov=fund_backtest --cov-fail-under=80`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

All test files are new (Phase 2 starts fresh for the price domain):

- [ ] `backtest/tests/unit/test_downloader.py` — covers DATA-01, DATA-06
- [ ] `backtest/tests/unit/test_validator.py` — covers DATA-04
- [ ] `backtest/tests/unit/test_price_types.py` — covers PriceBar cents conversion
- [ ] `backtest/tests/integration/test_price_pipeline.py` — covers DATA-02, DATA-03

Shared fixtures in `backtest/tests/conftest.py` already exist (`pg_container`, `db_engine`, `db_session`). The new integration tests inherit these fixtures — no conftest changes needed unless `db_engine` needs to be updated to run migration `002`.

---

## Open Questions

1. **Anomaly exclusion granularity — bar vs ticker-period**
   - What we know: requirement says "excluded from downstream use until manually reviewed"
   - What's unclear: does "downstream" mean exclude the single anomalous bar, or exclude the entire ticker from the backtest until reviewed?
   - Recommendation: Store flag per `(ticker, bar_date)` in `price_anomalies`. Downstream signal adapter (Phase 3) decides whether to exclude the bar or the ticker. For v1, excluding the specific bar is safest — document this decision.

2. **Gap detection vs market holiday awareness**
   - What we know: `pd.bdate_range()` does not know US market holidays; using it for gap detection will false-positive on MLK Day, Presidents Day, etc.
   - What's unclear: Should gap detection be holiday-aware?
   - Recommendation: Flag gaps > 3 consecutive business days only. Single and double-day gaps are expected (holidays, weekends). Avoids needing a US holiday calendar library (`pandas_market_calendars`) for v1.

3. **`data download` vs `data update` behavior on already-populated DB**
   - What we know: `data download` should do the full 5-year load; `data update` should be incremental
   - What's unclear: Should `data download` skip tickers that already have bars, or always attempt the 5y download?
   - Recommendation: `data download` uses `ON CONFLICT DO NOTHING` — it's safe to re-run on a populated DB. Tickers with existing bars get duplicate attempts silently skipped. Document this as intended behavior.

---

## Sources

### Primary (HIGH confidence)
- yfinance 1.2.0 installed in `.venv` — `YFRateLimitError`, `download()` signature, and MultiIndex column structure all verified by live execution
- SQLAlchemy 2.0.48 installed — `pg_insert().on_conflict_do_nothing()` documented in SQLAlchemy dialects
- Phase 1 codebase — migration numbering (001 exists → 002 next), conftest.py fixture reuse, tenacity pattern from `enricher.py`, CLI structure from `cli.py`
- `.planning/research/STACK.md` — yfinance rate limit mitigation (80 tickers/batch), tech stack decisions
- `.planning/STATE.md` — `market_cap_cents` as BigInteger convention, append-only immutability requirement

### Secondary (MEDIUM confidence)
- yfinance GitHub issues #2614 — documented 429 errors on bulk download; referenced in STACK.md
- pandas `bdate_range` docs — business-day frequency for gap detection; excludes weekends, not holidays

### Tertiary (LOW confidence)
- Gap detection threshold of 3 days — derived reasoning, not from an official source; treat as implementation recommendation subject to adjustment

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified installed in venv with version numbers
- Architecture: HIGH — mirrors verified Phase 1 universe/ module structure exactly
- yfinance API: HIGH — `download()` signature and exception types confirmed by live calls
- Pitfalls: HIGH — most verified by actual test execution (float truncation, NaN handling, column indexing)
- Gap detection holiday pitfall: MEDIUM — known behavior of `bdate_range`, threshold of 3 days is a judgment call

**Research date:** 2026-03-28
**Valid until:** 2026-06-28 (90 days — yfinance API is stable; Yahoo rate limits could change sooner)
