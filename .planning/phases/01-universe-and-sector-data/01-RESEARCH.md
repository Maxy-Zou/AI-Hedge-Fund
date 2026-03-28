# Phase 1: Universe and Sector Data - Research

**Researched:** 2026-03-28
**Domain:** Mid-cap equity universe management with GICS sector classification
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None — discuss phase was skipped per `workflow.skip_discuss`. All implementation choices are at Claude's discretion.

### Claude's Discretion
All implementation decisions — package structure, data acquisition strategy, CLI command naming, database schema, test architecture, and file organization.

### Deferred Ideas (OUT OF SCOPE)
None specified.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-05 | System manages a universe of mid-cap tickers ($2B-$10B market cap) with refresh capability | Wikipedia S&P 400 as seed + yfinance `Ticker.info.marketCap` for real-time filtering; universe snapshot pattern supports incremental refresh |
| DATA-07 | System stores GICS sector classification for each ticker (required for sector exposure reporting) | Wikipedia S&P 400 table has `GICS Sector` column directly; yfinance `Ticker.info['sector']` provides the same field for any ticker not on the list |
</phase_requirements>

---

## Summary

This phase creates the **Shared Backtesting Infrastructure** package — a new pip-installable Python package separate from the AI Washing Detector. Its first deliverable is a refreshable mid-cap ticker universe (~200-500 tickers) with GICS sector classification stored in PostgreSQL and exposed via a Typer CLI.

The universe sourcing strategy is two-stage: seed from Wikipedia's `List_of_S&P 400 companies` page (which already includes GICS Sector in its table) via `pandas.read_html()`, then validate and refresh market caps via yfinance `Ticker.info`. This avoids sequential per-ticker HTTP calls for the initial seed since Wikipedia provides the sector in one table fetch, while yfinance handles ongoing market cap validation and sector caching for any ticker not covered by the initial seed.

The new package (`fund-backtest` or similar) lives at the repo root alongside `Al Washing Detector/` and reuses the shared PostgreSQL instance. It does **not** reuse or import from the `ai_washer` package — it is an independent module with its own ORM models, config, and CLI. This matches the project's stated constraint of module independence.

**Primary recommendation:** Seed from Wikipedia S&P 400 table, validate/refresh via yfinance, store in PostgreSQL with a `universe_snapshots` table tracking refresh history. Rate-limit yfinance calls to ~1/sec with tenacity backoff.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| yfinance | >=1.2.0 | Fetch real-time market cap and sector info per ticker | Free, no API key, confirmed v1.2.0 on PyPI (Feb 2026), provides `Ticker.info['marketCap']` and `Ticker.info['sector']` |
| pandas | >=3.0.1 | `pd.read_html()` for Wikipedia S&P 400 scrape; DataFrame operations | Already in the fund stack; `read_html` makes one-liner index scraping trivial |
| SQLAlchemy | >=2.0.48 | ORM for universe tables | Fund-standard, shared with AI Washing Detector conventions |
| Alembic | >=1.18.4 | Database migrations | Fund-standard, consistent pattern |
| Typer | >=0.24.1 | CLI (`universe refresh`, `universe status`) | Fund-standard, consistent with `ai-washer` CLI pattern |
| Pydantic | >=2.12.5 | Settings validation, typed data contracts | Fund-standard |
| pydantic-settings | >=2.13.1 | Environment variable loading | Fund-standard |
| structlog | >=25.5.0 | Structured logging | Fund-standard |
| tenacity | >=9.1.4 | Retry + exponential backoff for yfinance | Fund-standard; yfinance rate-limit (429) errors are well-documented |
| lxml | >=5.0 | HTML parser backend for `pd.read_html()` | pandas requires lxml for robust HTML table parsing; already a transitive dep of edgartools |
| psycopg[binary] | >=3.2 | PostgreSQL sync driver | Fund-standard |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rich | >=14.0 | CLI table/progress output for `universe status` | Fund-standard; already in AI Washing Detector |
| freezegun | >=1.5.5 | Mock `date.today()` in tests | Required for deterministic testing of daily refresh logic |
| factory-boy | >=3.3 | Test data factories | Generate test ticker and snapshot fixtures |
| pytest | >=9.0.2 | Test framework | Fund-standard |
| pytest-cov | >=7.0 | Coverage reporting | Fund-standard, target 80%+ |
| testcontainers[postgres] | >=4.14 | PostgreSQL in integration tests | Fund-standard |
| ruff | >=0.15.7 | Linting/formatting | Fund-standard |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Wikipedia S&P 400 seed | yfinance bulk info for 5,000+ tickers | Wikipedia gives GICS sector upfront in one HTTP call; scanning thousands of tickers via yfinance for market cap would trigger rate limits and take hours |
| yfinance for sector | Hardcoded GICS mapping | yfinance covers any ticker not on S&P 400; hardcoded map goes stale as constituents change |
| yfinance for sector | EDGAR/XBRL sector data | EDGAR doesn't reliably surface GICS sector in XBRL; yfinance returns it from Yahoo Finance's data feed |
| pandas.read_html | requests + BeautifulSoup | `read_html` is 3 lines vs. 20+ for bs4; both use lxml; `read_html` is idiomatic for tables |

**Installation:**
```bash
# From the new backtesting package root
uv add yfinance pandas lxml sqlalchemy "psycopg[binary]" alembic pydantic "pydantic-settings[yaml]" typer rich structlog tenacity
uv add --dev pytest pytest-cov freezegun factory-boy "testcontainers[postgres]" ruff
```

**Version verification (PyPI confirmed 2026-03-28):**
- yfinance: 1.2.0 (Feb 2026)
- pandas: 3.0.1 (Feb 2026)
- SQLAlchemy: 2.0.48
- Alembic: 1.18.4
- Typer: 0.24.1
- Pydantic: 2.12.5
- tenacity: 9.1.4

---

## Architecture Patterns

### New Package Location

This phase creates a new package at the repo root level, **not** inside `Al Washing Detector/`:

```
AI Hedgefund/
├── Al Washing Detector/     # Existing — AI Washing signal module
├── backtest/                # NEW — Shared backtesting infrastructure
│   ├── pyproject.toml       # pip-installable as "fund-backtest"
│   ├── alembic.ini
│   ├── .python-version
│   ├── config/
│   │   └── universe.yaml    # Universe config (market cap range, refresh cadence)
│   ├── src/fund_backtest/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── cli.py           # Typer CLI entry point
│   │   ├── config.py        # Pydantic settings
│   │   ├── logging.py       # structlog setup
│   │   ├── db/
│   │   │   ├── base.py      # DeclarativeBase, AppendOnlyMixin
│   │   │   ├── models.py    # UniverseTicker, UniverseSnapshot
│   │   │   ├── session.py   # Engine + session factory
│   │   │   └── migrations/
│   │   │       ├── env.py
│   │   │       └── versions/
│   │   └── universe/
│   │       ├── __init__.py
│   │       ├── types.py     # UniverseEntry, SectorBreakdown, RefreshResult
│   │       ├── seeder.py    # Wikipedia S&P 400 scrape
│   │       ├── enricher.py  # yfinance market cap + sector per ticker
│   │       └── builder.py   # UniverseBuilder orchestrator
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       └── integration/
└── CLAUDE.md
```

### Recommended Project Structure (Phase 1 scope)

```
src/fund_backtest/
├── __init__.py          # __version__
├── __main__.py          # python -m fund_backtest
├── cli.py               # universe subcommands
├── config.py            # AppSettings, UniverseSettings
├── logging.py           # configure_logging()
├── db/
│   ├── base.py          # DeclarativeBase + AppendOnlyMixin
│   ├── models.py        # UniverseTicker, UniverseSnapshot
│   ├── session.py       # create_engine_from_settings, get_session_factory
│   └── migrations/
│       ├── env.py
│       └── versions/
│           └── 001_universe_schema.py
└── universe/
    ├── __init__.py
    ├── types.py         # Pydantic contracts
    ├── seeder.py        # Wikipedia fetch
    ├── enricher.py      # yfinance enrichment
    └── builder.py       # orchestrator
```

### Pattern 1: Wikipedia S&P 400 Seed

**What:** Fetch the S&P 400 constituent table from Wikipedia in a single HTTP call. The table already includes `Symbol`, `Security`, and `GICS Sector` columns. This gives both the seed ticker list and GICS sectors without any per-ticker API calls.

**When to use:** Initial universe seed and full refresh cycles. Falls back to yfinance `Ticker.info['sector']` for any ticker not in the S&P 400 (e.g., S&P 500 large-caps that temporarily dip into mid-cap range).

**Example:**
```python
# Source: https://en.wikipedia.org/wiki/List_of_S%26P_400_companies
import pandas as pd

def fetch_sp400_seed() -> pd.DataFrame:
    """Fetch S&P 400 constituents with GICS sector from Wikipedia.

    Returns:
        DataFrame with columns: ticker, name, gics_sector, gics_sub_industry
    """
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
    tables = pd.read_html(url, flavor="lxml")
    df = tables[0]
    return df.rename(columns={
        "Symbol": "ticker",
        "Security": "name",
        "GICS Sector": "gics_sector",
        "GICS Sub-Industry": "gics_sub_industry",
    })[["ticker", "name", "gics_sector", "gics_sub_industry"]]
```

### Pattern 2: yfinance Market Cap Validation and Sector Enrichment

**What:** For each ticker in the seed list, fetch `Ticker.info` via yfinance to get current `marketCap`. Apply the $2B-$10B filter. Also fetch `sector` for any ticker where GICS sector is missing (not on S&P 400 list). Cache all results in PostgreSQL on first access.

**When to use:** After seeding from Wikipedia; also for incremental refresh cycles.

**Rate limit strategy:** yfinance `Ticker.info` makes individual HTTP requests to Yahoo Finance. With ~400 tickers, fetching sequentially at ~1 req/sec takes ~7 minutes. Acceptable for a daily batch. Chunking batches is for `yf.download()` (OHLCV), not for `.info` — `.info` must be fetched per-ticker.

**Example:**
```python
# Source: yfinance docs https://ranaroussi.github.io/yfinance/
import time
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_ticker_info(ticker: str) -> dict:
    """Fetch market cap and sector for a single ticker with retry.

    Returns:
        dict with marketCap (int | None) and sector (str | None)
    """
    info = yf.Ticker(ticker).info
    return {
        "market_cap": info.get("marketCap"),
        "sector": info.get("sector"),
    }

def enrich_universe(tickers: list[str], delay_secs: float = 1.0) -> dict[str, dict]:
    """Fetch market cap + sector for a list of tickers.

    Rate-limited to ~1 req/sec to avoid Yahoo Finance 429 errors.
    """
    results: dict[str, dict] = {}
    for ticker in tickers:
        results[ticker] = fetch_ticker_info(ticker)
        time.sleep(delay_secs)
    return results
```

### Pattern 3: Database Schema — Universe Snapshot Pattern

**What:** Two tables: `universe_tickers` (one row per ticker, mutable) and `universe_snapshots` (append-only log of each refresh run). This satisfies success criterion 3 — "appends new entrants and marks delisted tickers without deleting historical snapshots."

**When to use:** Implement exactly this pattern. The `universe_tickers` table mirrors the AI Washing Detector's `Company` table pattern (mutable entity with `is_active`). The `universe_snapshots` table records the state at each refresh.

**Schema:**
```python
# Source: Based on existing ai_washer/db/models.py pattern
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, BigInteger, Boolean, DateTime, Date, func
from sqlalchemy.dialects.postgresql import JSONB

class UniverseTicker(Base):
    """Mutable registry of tracked mid-cap tickers with GICS sector.

    One row per ticker. Updated in-place on each refresh.
    is_active = False when ticker exits mid-cap range.
    """
    __tablename__ = "universe_tickers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    gics_sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gics_sub_industry: Mapped[str | None] = mapped_column(String(200), nullable=True)
    market_cap_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    deactivation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sector_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # "wikipedia_sp400" | "yfinance" | "manual"
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UniverseSnapshot(Base):
    """Append-only log of each universe refresh run.

    One row per refresh. Records total count, new/removed tickers,
    and sector breakdown as JSONB for historical analysis.
    """
    __tablename__ = "universe_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    active_count: Mapped[int] = mapped_column(nullable=False)
    new_count: Mapped[int] = mapped_column(nullable=False)
    removed_count: Mapped[int] = mapped_column(nullable=False)
    sector_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

### Pattern 4: CLI Command Structure

**What:** A `fund-backtest` CLI with a `universe` subcommand group. This mirrors the `ai-washer universe` pattern from the existing codebase.

**Commands required by success criteria:**
- `fund-backtest universe refresh` — run full universe refresh (DATA-05)
- `fund-backtest universe status` — display current size and sector breakdown (success criterion 4)

**Example:**
```python
# Source: mirrors ai_washer/cli.py pattern
import typer

app = typer.Typer(name="fund-backtest", no_args_is_help=True)
universe_app = typer.Typer(help="Manage mid-cap ticker universe.")
app.add_typer(universe_app, name="universe")

@universe_app.command()
def refresh(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show changes without writing to DB"),
):
    """Refresh the mid-cap universe: seed S&P 400, validate market caps, update sector data."""
    ...

@universe_app.command()
def status():
    """Display current universe size and sector breakdown."""
    ...
```

### Anti-Patterns to Avoid

- **Reusing `ai_washer` package internals:** Never import from `ai_washer` in the backtest package. They share a DB schema convention but are independent code modules. Cross-imports create a hard dependency the project constraints forbid.
- **Per-ticker concurrent yfinance calls:** Threading/asyncio for `.info` calls hits Yahoo Finance rate limits aggressively. Sequential with 1s delay is safer for ~400 tickers in a daily batch.
- **Fetching market cap from SEC EDGAR:** The AI Washing Detector uses `EntityPublicFloat` (public float, a proxy). For the backtester, use `yfinance.Ticker.info['marketCap']` — more accurate real-time market cap.
- **Storing market cap in dollars (float):** Fund-wide convention is integer cents. Store `marketCap * 100` as `BigInteger`.
- **Deleting or overwriting historical universe rows:** Immutability convention — mark `is_active=False`, never delete. The `universe_snapshots` table captures the historical state.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Mid-cap ticker seed list | Custom scraper or hardcoded list | `pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_400_companies')` | One line, returns GICS sector in the same table, Wikipedia is maintained by S&P |
| GICS sector lookup | Hardcoded sector map or custom API | yfinance `Ticker.info['sector']` | Yahoo Finance sources from S&P directly; no key required |
| Retry on 429 errors | Custom sleep/retry loop | `@tenacity.retry` with exponential backoff | Fund-standard, tested, handles jitter; already in the stack |
| Database migrations | Manual SQL scripts | Alembic with autogenerate | Fund-standard, already versioned in AI Washing Detector; same pattern here |
| Market cap filtering | Custom threshold logic | Simple comparison in enricher with Pydantic-validated config | Threshold is configurable via Pydantic settings, not hardcoded |

**Key insight:** The S&P 400 Wikipedia table does the heavy lifting — it gives both the ticker list *and* GICS sector in one HTTP call. The main work is validating market caps via yfinance (to filter out stale constituents) and building the refresh loop.

---

## Common Pitfalls

### Pitfall 1: yfinance `.info` sector Field Returns None or Partial Data

**What goes wrong:** `yf.Ticker('XYZ').info.get('sector')` returns `None` for some tickers, especially ETFs, ADRs, or recently-listed companies. This breaks the "every ticker has a GICS sector" requirement.

**Why it happens:** Yahoo Finance's backend doesn't always return sector data via the `.info` endpoint. The field existed in 0.2.12, was briefly broken in 0.2.14, and was fixed, but occasional gaps persist especially after Yahoo Finance backend changes.

**How to avoid:** Use the Wikipedia S&P 400 table as the primary source of GICS sector. The `sector_source` field on `UniverseTicker` records where the sector came from ("wikipedia_sp400" vs. "yfinance"). For tickers not in the S&P 400 seed, fall back to `yf.Ticker.info['sector']`, but if that also returns None, store as `None` and log a warning rather than failing the refresh.

**Warning signs:** `sector` is None for more than 10% of active tickers after a refresh.

### Pitfall 2: Market Cap in `Ticker.info['marketCap']` vs. `EntityPublicFloat`

**What goes wrong:** The AI Washing Detector uses SEC EDGAR's `EntityPublicFloat` as a proxy for market cap (widened thresholds: $1.5B-$9B). The backtester uses yfinance's `marketCap` (which is shares * price). These are different numbers. A company at $1.8B EntityPublicFloat might have a $2.1B yfinance marketCap — it would pass one filter and fail the other.

**Why it happens:** `EntityPublicFloat` is self-reported by the company at SEC filing time (a lagging indicator). yfinance `marketCap` is computed from real-time price data (leading indicator).

**How to avoid:** The backtester uses yfinance `marketCap` with the nominal $2B-$10B bounds (no widening needed, since yfinance data is real-time). Document this difference from the AI Washing Detector's approach.

**Warning signs:** Large discrepancy in the number of tickers vs. the AI Washing Detector's universe.

### Pitfall 3: Wikipedia Table Structure Changes

**What goes wrong:** `pd.read_html()` returns tables indexed by position. If Wikipedia adds or reorders tables on the List_of_S&P_400_companies page, `tables[0]` may no longer be the constituents table.

**Why it happens:** Wikipedia page structure is maintained by volunteers and changes occasionally.

**How to avoid:** After fetching with `read_html`, validate the result: check that the returned DataFrame has `Symbol`, `Security`, `GICS Sector` as column names before proceeding. Raise a `ValueError` with a descriptive message if the expected columns are absent. This makes the failure loud and obvious.

**Warning signs:** `KeyError` on `tables[0]['Symbol']` during refresh.

### Pitfall 4: yfinance Rate Limiting on Refresh

**What goes wrong:** Fetching `Ticker.info` for 400 tickers sequentially without delay triggers Yahoo Finance rate limiting (HTTP 429). This is well-documented in yfinance GitHub issues (#2614, #2125).

**Why it happens:** Yahoo Finance's backend imposes per-IP request limits. yfinance does not implement rate limiting internally — the caller must manage it.

**How to avoid:** Add `time.sleep(1.0)` between per-ticker info calls. Use `@tenacity.retry` to handle occasional 429 responses. For a ~400-ticker universe, the total refresh takes ~7 minutes — acceptable for a daily batch. Document expected refresh duration.

**Warning signs:** `YFRateLimitError` in logs during refresh.

### Pitfall 5: New Package Not Isolated from AI Washing Detector

**What goes wrong:** The backtesting package is created inside `Al Washing Detector/` (e.g., as a new module in `src/ai_washer/`) rather than as a separate package.

**Why it happens:** It's tempting to reuse the existing ORM base, settings, and CLI infrastructure.

**How to avoid:** Create the backtesting package as `backtest/` at the repo root with its own `pyproject.toml`, `.venv`, and `src/fund_backtest/`. The shared database is a runtime concern — both packages connect to the same PostgreSQL instance via their own settings. No Python-level imports should cross package boundaries.

---

## Code Examples

### Validated Patterns from Official Sources

#### Wikipedia S&P 400 Table Fetch and Validate

```python
# Source: pandas.read_html official docs; Wikipedia table structure verified 2026-03-28
import pandas as pd

REQUIRED_COLUMNS = {"Symbol", "Security", "GICS Sector", "GICS Sub-Industry"}
SP400_WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"

def fetch_sp400_constituents() -> pd.DataFrame:
    """Fetch S&P 400 constituents from Wikipedia.

    Returns:
        DataFrame with ticker, name, gics_sector, gics_sub_industry columns.

    Raises:
        ValueError: If the expected columns are not found in the table.
    """
    tables = pd.read_html(SP400_WIKIPEDIA_URL, flavor="lxml")
    df = tables[0]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Wikipedia S&P 400 table structure changed. Missing columns: {missing}. "
            f"Found: {list(df.columns)}"
        )

    return df.rename(columns={
        "Symbol": "ticker",
        "Security": "name",
        "GICS Sector": "gics_sector",
        "GICS Sub-Industry": "gics_sub_industry",
    })[["ticker", "name", "gics_sector", "gics_sub_industry"]]
```

#### yfinance Market Cap + Sector with Tenacity

```python
# Source: yfinance PyPI docs; tenacity docs https://tenacity.readthedocs.io/
import time
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    retry=retry_if_exception_type(Exception),
)
def _fetch_one_ticker_info(ticker: str) -> dict:
    info = yf.Ticker(ticker).info
    return {
        "market_cap": info.get("marketCap"),    # int | None
        "sector": info.get("sector"),            # str | None
    }


def fetch_market_caps(tickers: list[str], delay_secs: float = 1.0) -> dict[str, dict]:
    """Sequential yfinance info fetch with rate limiting.

    Args:
        tickers: List of ticker symbols.
        delay_secs: Sleep between requests. Default 1.0s to avoid 429.

    Returns:
        dict mapping ticker -> {market_cap: int|None, sector: str|None}
    """
    results: dict[str, dict] = {}
    for ticker in tickers:
        try:
            results[ticker] = _fetch_one_ticker_info(ticker)
        except Exception:
            results[ticker] = {"market_cap": None, "sector": None}
        time.sleep(delay_secs)
    return results
```

#### Market Cap Filter ($2B-$10B)

```python
# Fund convention: store market cap as integer cents (BigInteger)
MARKET_CAP_MIN_CENTS = 200_000_000_000   # $2B
MARKET_CAP_MAX_CENTS = 1_000_000_000_000 # $10B

def is_midcap(market_cap_dollars: int | None) -> bool:
    """Return True if market_cap is in $2B-$10B range.

    Args:
        market_cap_dollars: Market cap from yfinance in dollars (integer).

    Returns:
        True if in mid-cap range, False if None or out of range.
    """
    if market_cap_dollars is None:
        return False
    market_cap_cents = int(market_cap_dollars) * 100
    return MARKET_CAP_MIN_CENTS <= market_cap_cents <= MARKET_CAP_MAX_CENTS
```

#### Sector Breakdown for CLI Status Command

```python
# Source: SQLAlchemy 2.0 docs + Typer docs
from collections import Counter
from rich.table import Table
import typer

def build_sector_breakdown(tickers: list[UniverseTicker]) -> dict[str, int]:
    """Count active tickers by GICS sector.

    Returns:
        dict mapping sector name -> count, sorted descending.
    """
    sectors = [t.gics_sector or "Unknown" for t in tickers if t.is_active]
    counts = Counter(sectors)
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pandas-datareader Yahoo backend | yfinance 1.x | 2023+ | pandas-datareader's Yahoo backend was removed; yfinance is the de facto free replacement |
| quantstats (original) | quantstats-lumi >=1.1.0 | 2024 | Original quantstats has maintenance gaps; Lumiwealth fork is actively maintained |
| APScheduler for scheduling | Prefect >=3.x | 2025 | APScheduler is single-process with no retry/monitoring; Prefect handles pipeline orchestration |

**Deprecated/outdated:**
- `pandas-datareader`: Yahoo Finance backend removed. Do not use for market data.
- `yfinance 0.2.x`: `.info` had sector breakage in 0.2.14. Use 1.2.0+.
- `quantstats` (original): Use `quantstats-lumi` fork.

---

## Open Questions

1. **Package name: `backtest` vs. `fund-backtest` vs. `hedge-backtest`**
   - What we know: The project is "Shared Backtesting Infrastructure" for the AI Hedge Fund
   - What's unclear: Whether the package name needs to be globally unique (if published to PyPI) or is internal only
   - Recommendation: Use `fund-backtest` as the project name and `fund_backtest` as the Python package name. Internal use only — no PyPI publishing needed.

2. **Shared database: same PostgreSQL instance or separate?**
   - What we know: PROJECT.md says "shared database (same instance as the Detector uses)"; ROADMAP Phase 8 integrates with the Detector's scores
   - What's unclear: Whether `universe_tickers` should live in the same DB as `companies` or a separate database
   - Recommendation: Same PostgreSQL instance, different table prefix (`universe_*`). The backtester connects via its own `DATABASE_URL` env var that points to the same DB.

3. **Should `backtest/` have its own Alembic migrations or share with `Al Washing Detector/`?**
   - What we know: Each package has its own `pyproject.toml`; Alembic is config-file based
   - What's unclear: Whether sharing migrations across packages creates conflicts
   - Recommendation: Independent Alembic setup per package. The backtester's `alembic.ini` points to its own migrations directory. Both run against the same PostgreSQL instance, but Alembic tracks versions independently. This is the standard multi-app pattern with a shared PostgreSQL database.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Package runtime | ✓ | 3.12.11 | — |
| uv | Package management | ✓ | 0.11.2 | pip |
| PostgreSQL | Database | ✗ | — | Must be running (shared with AI Washing Detector) |
| yfinance | Universe enrichment | ✗ (not installed) | — | Must install via `uv add yfinance` |
| lxml | Wikipedia HTML parsing | ✗ (not installed in new pkg) | — | Must install via `uv add lxml` |

**Missing dependencies with no fallback:**
- PostgreSQL: Must be running before `universe refresh` can write results. The plan must include a Wave 0 step to verify DB connectivity (or document that this is a prerequisite from the AI Washing Detector setup).

**Missing dependencies with fallback:**
- yfinance, lxml: Not installed yet — a Wave 0 task creates the new `backtest/pyproject.toml` and runs `uv sync`.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=9.0.2 |
| Config file | `backtest/pyproject.toml` [tool.pytest.ini_options] — Wave 0 |
| Quick run command | `cd backtest && uv run pytest tests/unit/ -x -q` |
| Full suite command | `cd backtest && uv run pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-05 | `universe refresh` filters tickers to $2B-$10B market cap | unit | `pytest tests/unit/test_enricher.py::test_midcap_filter -x` | ❌ Wave 0 |
| DATA-05 | `universe refresh` marks previously-active tickers as inactive (not deleted) when they exit range | unit | `pytest tests/unit/test_builder.py::test_refresh_marks_inactive -x` | ❌ Wave 0 |
| DATA-05 | `universe refresh` appends new entrants on second run | integration | `pytest tests/integration/test_universe_lifecycle.py -x -m integration` | ❌ Wave 0 |
| DATA-07 | GICS sector is populated from Wikipedia S&P 400 table | unit | `pytest tests/unit/test_seeder.py::test_sector_from_wikipedia -x` | ❌ Wave 0 |
| DATA-07 | GICS sector falls back to yfinance when ticker not in S&P 400 | unit | `pytest tests/unit/test_enricher.py::test_sector_fallback_yfinance -x` | ❌ Wave 0 |
| DATA-07 | GICS sector is stored in PostgreSQL and cached (no second yfinance call) | integration | `pytest tests/integration/test_universe_lifecycle.py::test_sector_cached -x -m integration` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backtest && uv run pytest tests/unit/ -x -q`
- **Per wave merge:** `cd backtest && uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `backtest/pyproject.toml` — new package scaffold (creates the package)
- [ ] `backtest/src/fund_backtest/__init__.py` — package version
- [ ] `backtest/tests/conftest.py` — shared fixtures (DB session, mock yfinance)
- [ ] `backtest/tests/unit/test_seeder.py` — covers DATA-07 Wikipedia path
- [ ] `backtest/tests/unit/test_enricher.py` — covers DATA-05 market cap filter and DATA-07 yfinance fallback
- [ ] `backtest/tests/unit/test_builder.py` — covers DATA-05 refresh and deactivation logic
- [ ] `backtest/tests/integration/test_universe_lifecycle.py` — covers DATA-05 persistence and DATA-07 caching
- [ ] Framework install: `cd backtest && uv add yfinance pandas lxml` — new package needs its own venv

---

## Project Constraints (from CLAUDE.md)

The following directives from `CLAUDE.md` (global + project) apply to this phase:

### From Global CLAUDE.md
- **Immutability (CRITICAL):** Always return new objects. Never mutate in-place. `UniverseTicker` updates must use SQLAlchemy assignment, not in-place dict modification.
- **File size:** 200-400 lines typical, 800 max. `builder.py` orchestrator should extract helpers to `seeder.py` and `enricher.py`.
- **Functions <50 lines:** Split fetch, filter, and persist into separate functions.
- **No hardcoded values:** Market cap bounds must live in Pydantic `UniverseSettings`, not in comparison logic.
- **Error handling:** All yfinance exceptions must be caught and logged. Never silently swallow 429 errors.
- **Input validation:** Validate Wikipedia DataFrame structure immediately after fetch. Raise `ValueError` with descriptive message on unexpected schema.
- **80% test coverage target.**

### From Project CLAUDE.md (AI Hedge Fund)
- **Language:** Python 3.11+
- **Package management:** `uv` preferred
- **API keys in `.env`:** `DATABASE_URL` must not be hardcoded
- **Immutable financial data:** Historical snapshots never overwritten — use `UniverseSnapshot` append-only table
- **Timestamps in UTC**
- **Preserve source precision:** Market cap from yfinance is in dollars (integer); convert to cents with `int(market_cap_dollars) * 100` — no rounding loss

### From Al Washing Detector CLAUDE.md (conventions reference)
- **ORM pattern:** `mapped_column()` with type hints (SQLAlchemy 2.0 style)
- **Logging:** `structlog.get_logger(__name__)`, bind contextual keys, log events not messages
- **Naming:** `snake_case` for files, functions, variables; `PascalCase` for classes; `UPPER_SNAKE_CASE` for constants
- **`@dataclass(frozen=True)` for result objects** (e.g., `RefreshResult`)
- **Pydantic for all data contracts at layer boundaries**
- **Type annotations:** `from __future__ import annotations` at top; `str | None` union syntax

---

## Sources

### Primary (HIGH confidence)
- [yfinance PyPI](https://pypi.org/project/yfinance/) — v1.2.0 verified (Feb 2026); `Ticker.info['sector']`, `Ticker.info['marketCap']` fields
- [Wikipedia List of S&P 400 companies](https://en.wikipedia.org/wiki/List_of_S%26P_400_companies) — Table structure verified 2026-03-28; contains Symbol, Security, GICS Sector, GICS Sub-Industry columns
- [yfinance Ticker/Tickers docs](https://ranaroussi.github.io/yfinance/reference/yfinance.ticker_tickers.html) — Tickers class API, per-ticker `.info` access
- [yfinance Sector/Industry docs](https://ranaroussi.github.io/yfinance/reference/yfinance.sector_industry.html) — Sector class for top companies (supplementary)
- Existing codebase — `Al Washing Detector/src/ai_washer/` — all patterns for ORM, CLI, config, logging directly applicable

### Secondary (MEDIUM confidence)
- [yfinance GitHub issue #2614](https://github.com/ranaroussi/yfinance/issues/2614) — Confirmed rate limit issues on bulk download; chunking to ~80 tickers recommended (for OHLCV; `.info` must be per-ticker)
- [yfinance GitHub issue #1471](https://github.com/ranaroussi/yfinance/issues/1471) — Confirmed prior `.info` sector field breakage in 0.2.14; resolved in later versions
- [Sling Academy: Rate Limiting Best Practices](https://www.slingacademy.com/article/rate-limiting-and-api-best-practices-for-yfinance/) — 1-3s sleep between info calls, random jitter

### Tertiary (LOW confidence — flagged for validation)
- Community reports that yfinance `.info` sector returns None occasionally — verified by GitHub issues; actual production reliability with 1.2.0 requires live testing

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all library versions verified on PyPI; fund-standard libraries confirmed in existing codebase
- Architecture: HIGH — new package pattern is clear from project constraints; universe snapshot schema is a known pattern
- Pitfalls: HIGH — yfinance rate limits and `.info` sector gaps are documented in official GitHub issues; Wikipedia table structure verified live
- Data sourcing: HIGH — Wikipedia S&P 400 table structure verified 2026-03-28 with GICS Sector column confirmed

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable: yfinance, pandas, Wikipedia table structure change slowly)
