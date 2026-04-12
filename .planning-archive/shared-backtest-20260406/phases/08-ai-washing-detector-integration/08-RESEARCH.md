# Phase 8: AI Washing Detector Integration - Research

**Researched:** 2026-03-29
**Domain:** Cross-module PostgreSQL signal loading, SQLAlchemy raw queries, Typer CLI wiring
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting.
Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Claude's Discretion
All implementation decisions are discretionary.

### Deferred Ideas (OUT OF SCOPE)
None — discuss phase skipped.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INT-02 | AI Washing Detector scores can be loaded and converted to the signal contract format | `AiWashingLoader` queries `daily_scores JOIN companies` via raw SQLAlchemy text, pivots to SignalFrame; graceful degradation if table is empty/missing |
| INT-03 | End-to-end pipeline runs from signal input to dashboard output without manual steps | `backtest run --signal ai-washing` CLI command wires all 5 stages: load → adapt → simulate → metrics → export; existing infrastructure (adapter, simulator, metrics, tearsheet) reused without change |
</phase_requirements>

---

## Summary

Phase 8 is the final integration milestone. Its scope is narrow and well-defined: one new loader module (`signal/loaders/ai_washing.py`), one new CLI command (`backtest run --signal ai-washing`), and tests covering both the happy path and the empty-table failure mode. No new libraries are required — all dependencies are already in the lockfile and all five downstream stages (adapt, simulate, metrics, export) are complete from Phases 3-7.

The integration boundary is a shared PostgreSQL database. The Detector writes to `daily_scores JOIN companies`; the backtester reads via a raw SQL query using its own SQLAlchemy session (`FUND_BACKTEST_DATABASE_URL`). No Python-level cross-package imports exist now and none will be introduced. The query result is pivoted into a `SignalFrame` (date x ticker, float values 0-100) and handed to the existing `SignalAdapter`, which normalizes it into a `WeightFrame` exactly as it would any other signal.

The only non-trivial design decision is the `available_date` offset convention: because `scored_at` is a `DateTime(timezone=True)` (not a date), the loader must cast it to a date and shift forward by 1 business day so the signal appears on the day after scoring. The existing `SignalAdapter.adapt()` applies a `shift(1)` internally, which means the loader must NOT apply a second shift — it should produce raw scores for the score date and let the adapter handle temporal safety. This is already documented as a Phase 3 invariant.

**Primary recommendation:** Implement a thin `AiWashingLoader` class in `fund_backtest/signal/loaders/ai_washing.py` that executes a JOIN query, pivots the result into a SignalFrame, and raises a descriptive `SignalLoadError` if the table is empty. Wire it behind `backtest run --signal ai-washing` in `cli.py`.

---

## Standard Stack

### Core (already in project lockfile — no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.48+ | Raw SQL query via `text()` + `Session.execute()` | Already the project ORM; `text()` is the correct pattern for cross-schema raw queries with no ORM model on the reader side |
| pandas | 3.0.1+ | `pivot_table()` to build SignalFrame from query result | Already in project; pivot is the canonical transformation for (date, ticker, score) rows |
| structlog | 25.5.0+ | Structured logging in loader | Already used everywhere in the project |
| pytest | 9.0.2+ | Unit + integration tests | Project standard |
| testcontainers[postgres] | 4.14+ | Integration test with real PostgreSQL | Already in dev deps; pattern established in Phases 1-2 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `sqlalchemy.text()` raw query | ORM model mirroring Detector's `DailyScore` | ORM model requires importing Detector schema or duplicating it; raw SQL is simpler for a read-only cross-module query and matches the project constraint "no Python imports between packages" |
| `pandas.pivot_table()` | Manual loop building dict | `pivot_table` is vectorized and handles missing (ticker, date) combinations with `fill_value=None` automatically |

**Installation:** No new packages required.

---

## Architecture Patterns

### Recommended Project Structure

```
src/fund_backtest/
├── signal/
│   ├── types.py          # SignalFrame, WeightFrame (existing)
│   ├── validator.py      # validate_signal_frame (existing)
│   ├── adapter.py        # SignalAdapter (existing)
│   └── loaders/          # NEW subdirectory for signal source loaders
│       ├── __init__.py   # NEW — exports AiWashingLoader, SignalLoadError
│       └── ai_washing.py # NEW — AiWashingLoader
├── cli.py                # MODIFIED — add `backtest run` command
tests/
├── unit/
│   └── test_ai_washing_loader.py   # NEW — unit tests (mocked session)
└── integration/
    └── test_ai_washing_integration.py  # NEW — full pipeline (testcontainer)
```

### Pattern 1: Cross-Module Signal Loader (raw SQL)

**What:** `AiWashingLoader` executes a single JOIN query over `daily_scores` and `companies`, returns a pandas DataFrame, then pivots to SignalFrame shape.

**When to use:** Any time the backtest package reads from a table owned by another module. No ORM model import, no cross-package dependency, no migration needed in `fund_backtest`.

**The query (from additional_context):**
```python
# Source: additional_context + Detector models.py inspection
from sqlalchemy import text
from sqlalchemy.orm import Session
import pandas as pd

_SCORE_QUERY = text("""
    SELECT
        companies.ticker,
        daily_scores.scored_at::date AS signal_date,
        daily_scores.composite_score
    FROM daily_scores
    JOIN companies ON daily_scores.company_id = companies.id
    ORDER BY signal_date, ticker
""")

def _load_raw(session: Session) -> pd.DataFrame:
    result = session.execute(_SCORE_QUERY)
    return pd.DataFrame(result.fetchall(), columns=["ticker", "signal_date", "composite_score"])
```

**Pivot to SignalFrame:**
```python
def _pivot_to_signal_frame(df: pd.DataFrame) -> pd.DataFrame:
    # pivot: rows = signal_date, columns = ticker, values = composite_score
    pivoted = df.pivot_table(
        index="signal_date",
        columns="ticker",
        values="composite_score",
        aggfunc="last",  # if multiple scores same day, take latest
    )
    pivoted.index = pd.DatetimeIndex(pd.to_datetime(pivoted.index), tz=None)
    pivoted.columns.name = None  # strip "ticker" label from columns
    return pivoted.astype(float)  # SignalFrame values must be float
```

### Pattern 2: SignalLoadError for graceful degradation

**What:** A module-specific exception raised when the Detector's scores table is empty, unavailable, or the query returns no rows. The CLI catches it and exits with code 1 and a descriptive message.

```python
class SignalLoadError(RuntimeError):
    """Raised when signal data cannot be loaded from the source database.

    Always includes a descriptive message so the pipeline exits with a
    meaningful error rather than a silent empty backtest.
    """
```

**When to use:** Any failure condition in `AiWashingLoader.load()` — empty result set, table missing (OperationalError), zero rows after filter.

### Pattern 3: `backtest run --signal ai-washing` CLI command

**What:** A new `run` subcommand on `backtest_app` that:
1. Loads settings and initializes session
2. Calls `AiWashingLoader(session).load()` → `SignalFrame`
3. Loads price bars via `PriceBarRepository` → `PriceFrame`
4. Calls `SignalAdapter().adapt(signal_frame)` → `WeightFrame`
5. Calls `PortfolioSimulator().simulate(weight_frame, price_frame)` → `PortfolioResult`
6. Calls `MetricsEngine().compute(result)` → `MetricsBundle`
7. Optionally exports (tearsheet/CSV/JSON) or launches dashboard

**Pattern from existing commands (cli.py):**
```python
@backtest_app.command(name="run")
def run(
    signal: str = typer.Option(..., "--signal", help="Signal source: 'ai-washing'"),
    export_dir: Path = typer.Option(Path("."), "--output-dir", help="Export output directory"),
) -> None:
    """Run full end-to-end backtest pipeline from signal source."""
    settings = load_app_settings()
    configure_logging(settings.log_level)

    try:
        engine = create_engine_from_settings(settings)
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            signal_frame = _load_signal(signal, session)  # dispatches to loader
            ...
    except SignalLoadError as exc:
        console.print(f"[red]Signal load failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]Pipeline error: {exc}[/red]")
        raise typer.Exit(code=1) from exc
```

### Pattern 4: PriceFrame from PriceBarRepository

**What:** Reuse the existing `PriceBarRepository.get_bars()` to load close prices for the tickers present in the SignalFrame, for the date range of the signal.

```python
# Get tickers from signal frame columns
tickers = list(signal_frame.columns)
start_date = signal_frame.index.min().date()
end_date = signal_frame.index.max().date()

bars = repo.get_bars(tickers=tickers, start=start_date, end=end_date)
# Convert cents -> dollars, pivot to PriceFrame
```

Note: `get_bars` returns `PriceBar` objects with `close_cents`. The PriceFrame needs USD float values. The conversion pattern (`close_cents / 100`) is already established in Phase 2.

### Anti-Patterns to Avoid

- **Importing from `ai_washer` package:** The constraint is explicit — no Python-level cross-package imports. Use raw SQL only.
- **Duplicating DailyScore ORM model:** Don't create a `DailyScoreORM` in `fund_backtest`. Raw SQL is simpler and avoids schema drift.
- **Applying shift(1) in the loader:** `SignalAdapter.adapt()` already applies `shift(1)` as the final step (documented Phase 3 invariant). The loader must return raw scores for the score date. A second shift would create a 2-day lag.
- **Silently returning an empty DataFrame:** The success criteria requires the pipeline to "exit with a non-zero status code and a descriptive error message" if scores are unavailable. Empty result must raise `SignalLoadError`, not return silently.
- **Hardcoding table names:** The query targets `daily_scores` and `companies`. Document these as constants in the loader to make schema changes explicit.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Signal normalization | Custom rank/weight logic | `SignalAdapter.adapt()` (existing, Phase 3) | Already handles rank normalization, look-ahead bias, min_coverage, gross exposure |
| Portfolio simulation | Custom return calculation | `PortfolioSimulator.simulate()` (existing, Phase 4) | Handles transaction + borrow costs vectorized |
| Risk metrics computation | Custom Sharpe/drawdown | `MetricsEngine.compute()` (existing, Phase 5) | Full institutional metric suite, benchmark comparison |
| PDF/CSV/JSON export | Custom file writers | `TearsheetBuilder` + `ExportBuilder` (existing, Phase 7) | Already labeled with cost assumptions |
| Database session | New session factory | `create_engine_from_settings()` + `get_session_factory()` (existing) | Already handles `FUND_BACKTEST_DATABASE_URL` with pool_pre_ping |
| Date range for price data | Custom date calculation | `signal_frame.index.min()` / `.max()` → pass to `PriceBarRepository.get_bars()` | Avoids hardcoding history length |

**Key insight:** Phases 1-7 built all the infrastructure. Phase 8 is a thin wiring layer — the loader (~60 lines), the CLI command (~50 lines), and tests.

---

## Common Pitfalls

### Pitfall 1: scored_at timezone stripping on pivot
**What goes wrong:** `scored_at` is `DateTime(timezone=True)` in the Detector's schema. After `::date` cast in SQL, PostgreSQL returns a Python `datetime.date`. But if the query is executed via SQLAlchemy `text()` without the `::date` cast, it returns a `datetime` with timezone. `pd.DatetimeIndex(tz=None)` will raise if fed mixed tz-aware/tz-naive values.
**Why it happens:** SQLAlchemy `text()` returns raw Python types from psycopg3; timezone-aware datetimes don't auto-convert.
**How to avoid:** Use `::date` in the SQL query (already shown in the integration query from additional_context). Then `pd.to_datetime(pivoted.index)` works cleanly.
**Warning signs:** `TypeError: Cannot convert tz-naive and tz-aware DatetimeIndex` during pivot.

### Pitfall 2: Partitioned table requires PostgreSQL — SQLite testcontainer fallback will fail
**What goes wrong:** `daily_scores` is `RANGE`-partitioned on `scored_at`. SQLite does not support table partitioning. The existing unit tests for universe/price use SQLite-compatible fallbacks, but integration tests for the loader must use a real PostgreSQL testcontainer.
**Why it happens:** Partition DDL is PostgreSQL-specific (`postgresql_partition_by` in models.py).
**How to avoid:** Integration tests use `testcontainers[postgres]` (already in dev deps). Unit tests mock the session entirely (as in `test_cli.py` pattern).
**Warning signs:** `OperationalError: no such table: daily_scores` during tests that use SQLite.

### Pitfall 3: composite_score is SmallInteger (0-100), not float
**What goes wrong:** `composite_score` is stored as `SmallInteger`. After pivot, pandas infers int dtype for the column. `validate_signal_frame()` does not check dtype, but downstream rank computation in `SignalAdapter` works on float values.
**Why it happens:** pandas `pivot_table` preserves source dtypes.
**How to avoid:** Call `.astype(float)` on the pivoted DataFrame before returning from the loader. Already shown in the pattern above.
**Warning signs:** `TypeError` or unexpected integer arithmetic in rank normalization.

### Pitfall 4: Empty result set vs table missing
**What goes wrong:** Two different failure modes both trigger `SignalLoadError` but need different messages: (a) the table exists but has zero rows; (b) the table doesn't exist at all (OperationalError from PostgreSQL).
**Why it happens:** The Detector may not have run yet (empty table) or the database may not have the Detector's schema applied (missing table).
**How to avoid:** Catch `sqlalchemy.exc.OperationalError` separately from empty DataFrame — both raise `SignalLoadError` but with different descriptive messages.
**Warning signs:** Cryptic psycopg3 errors in CLI output.

### Pitfall 5: PriceFrame ticker mismatch
**What goes wrong:** The Detector scores companies by `ticker` from the `companies` table, but the `price_bars` table uses tickers from the `universe_tickers` table. A company in the Detector's universe may not be in the backtester's price universe (or vice versa).
**Why it happens:** The two modules maintain separate universe tables — no FK linkage.
**How to avoid:** `PortfolioSimulator._align_frames()` already handles this gracefully (logs a warning, drops mismatched tickers). No special handling needed in the loader. Document this as expected behavior in the CLI output.
**Warning signs:** `simulator_tickers_dropped` warning in logs — normal and expected when universes diverge.

### Pitfall 6: Multiple scores per company per day
**What goes wrong:** If the Detector runs multiple times in one day (re-runs), `daily_scores` may have multiple rows for the same `(company_id, scored_at::date)`. `pivot_table` without an aggregation function will raise.
**Why it happens:** `daily_scores` is append-only — no upsert constraint on `(company_id, scored_at::date)`.
**How to avoid:** Use `aggfunc="last"` in `pivot_table()` to take the most recent score per (date, ticker). Already shown in the pattern above.
**Warning signs:** `DataError: Index contains duplicate entries` from pivot without aggfunc.

---

## Code Examples

### AiWashingLoader full structure

```python
# Source: research synthesis from Detector models.py + backtest patterns
from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session
import pandas as pd

from fund_backtest.signal.types import SignalFrame

logger = structlog.get_logger(__name__)

_SCORE_QUERY = text("""
    SELECT
        companies.ticker,
        daily_scores.scored_at::date AS signal_date,
        daily_scores.composite_score
    FROM daily_scores
    JOIN companies ON daily_scores.company_id = companies.id
    ORDER BY signal_date, ticker
""")


class SignalLoadError(RuntimeError):
    """Raised when signal data cannot be loaded from the source database."""


class AiWashingLoader:
    """Loads AI Washing composite scores from shared PostgreSQL and converts to SignalFrame.

    Reads from the AI Washing Detector's daily_scores and companies tables via
    raw SQL. No Python imports from the ai_washer package — database is the
    integration boundary.

    Args:
        session: SQLAlchemy Session bound to the shared PostgreSQL database.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._log = logger.bind(component="ai_washing_loader")

    def load(self) -> SignalFrame:
        """Load all available AI washing scores as a SignalFrame.

        Returns:
            SignalFrame: DatetimeIndex (tz-naive) x ticker columns, float values 0-100.
            NaN where no score exists for a (date, ticker) pair.

        Raises:
            SignalLoadError: If the scores table is empty, missing, or unreachable.
        """
        import sqlalchemy.exc

        try:
            result = self._session.execute(_SCORE_QUERY)
            rows = result.fetchall()
        except sqlalchemy.exc.OperationalError as exc:
            raise SignalLoadError(
                "AI Washing Detector scores table is unavailable. "
                "Ensure the Detector database schema is applied and the table exists. "
                f"Original error: {exc}"
            ) from exc

        if not rows:
            raise SignalLoadError(
                "AI Washing Detector scores table is empty. "
                "Run the Detector pipeline to generate scores before backtesting."
            )

        df = pd.DataFrame(rows, columns=["ticker", "signal_date", "composite_score"])
        signal_frame = self._pivot(df)
        self._log.info(
            "ai_washing_loader_complete",
            n_dates=len(signal_frame),
            n_tickers=len(signal_frame.columns),
        )
        return signal_frame

    def _pivot(self, df: pd.DataFrame) -> SignalFrame:
        pivoted = df.pivot_table(
            index="signal_date",
            columns="ticker",
            values="composite_score",
            aggfunc="last",
        )
        pivoted.index = pd.DatetimeIndex(pd.to_datetime(pivoted.index))
        pivoted.columns.name = None
        return pivoted.astype(float)
```

### PriceFrame construction from PriceBarRepository

```python
# Source: fund_backtest/price/repository.py pattern + price/types.py PriceBar
from fund_backtest.price.repository import PriceBarRepository

def load_price_frame(session, signal_frame):
    repo = PriceBarRepository(session)
    tickers = list(signal_frame.columns)
    start = signal_frame.index.min().date()
    end = signal_frame.index.max().date()
    bars = repo.get_bars(tickers=tickers, start=start, end=end)

    records = [
        {"date": b.bar_date, "ticker": b.ticker, "close": b.close_cents / 100}
        for b in bars
    ]
    price_df = pd.DataFrame(records)
    price_frame = price_df.pivot_table(
        index="date", columns="ticker", values="close"
    )
    price_frame.index = pd.DatetimeIndex(pd.to_datetime(price_frame.index))
    price_frame.columns.name = None
    return price_frame
```

### CLI backtest run command (mock-friendly pattern)

```python
# Source: fund_backtest/cli.py existing command patterns
@backtest_app.command(name="run")
def run(
    signal: str = typer.Option(..., "--signal", help="Signal source (e.g. 'ai-washing')"),
    output_dir: Path = typer.Option(Path("."), "--output-dir", help="Output directory for exports"),
    export_all: bool = typer.Option(False, "--export-all", help="Generate all exports after run"),
) -> None:
    """Run full end-to-end backtest from signal load through export."""
    from fund_backtest.signal.loaders import AiWashingLoader, SignalLoadError
    ...
    try:
        engine = create_engine_from_settings(settings)
        session_factory = get_session_factory(engine)
        with session_factory() as session:
            loader = AiWashingLoader(session)
            signal_frame = loader.load()
            ...
    except SignalLoadError as exc:
        console.print(f"[red]Signal unavailable: {exc}[/red]")
        log.error("signal_load_failed", error=str(exc))
        raise typer.Exit(code=1) from exc
```

---

## Runtime State Inventory

> This section is skipped — Phase 8 is not a rename/refactor/migration phase. No stored data, live service config, OS-registered state, secrets, or build artifacts require updating.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|---------|
| Python 3.12 | All code | ✓ | 3.12.11 | — |
| uv | Package management | ✓ | 0.11.2 | — |
| Docker | testcontainers for integration tests | ✓ | 29.0.1 (running) | — |
| PostgreSQL (via testcontainer) | Integration tests | ✓ | 16 (Docker image) | — |
| psycopg[binary] | SQLAlchemy driver | ✓ | already in lockfile | — |
| pandas | SignalFrame pivot | ✓ | already in lockfile | — |

**Missing dependencies with no fallback:** None

**Missing dependencies with fallback:** None — all dependencies already in the project lockfile.

**Note on live Detector database:** The live AI Washing Detector PostgreSQL is not required for tests. Unit tests mock the session; integration tests seed a testcontainer with synthetic `daily_scores` and `companies` rows.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2+ |
| Config file | `backtest/pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `cd /Users/maxzou/Documents/projects/AI\ Hedgefund/backtest && uv run pytest tests/unit/test_ai_washing_loader.py -x` |
| Full suite command | `cd /Users/maxzou/Documents/projects/AI\ Hedgefund/backtest && uv run pytest tests/ --cov=src/fund_backtest --cov-report=term-missing` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INT-02 | AiWashingLoader.load() returns valid SignalFrame from DB rows | unit | `pytest tests/unit/test_ai_washing_loader.py::test_load_returns_signal_frame -x` | ❌ Wave 0 |
| INT-02 | AiWashingLoader.load() raises SignalLoadError on empty table | unit | `pytest tests/unit/test_ai_washing_loader.py::test_load_raises_on_empty -x` | ❌ Wave 0 |
| INT-02 | AiWashingLoader.load() raises SignalLoadError on missing table (OperationalError) | unit | `pytest tests/unit/test_ai_washing_loader.py::test_load_raises_on_missing_table -x` | ❌ Wave 0 |
| INT-02 | SignalFrame has DatetimeIndex, ticker columns, float values | unit | `pytest tests/unit/test_ai_washing_loader.py::test_signal_frame_contract -x` | ❌ Wave 0 |
| INT-02 | Multiple scores per day: aggfunc="last" picks most recent | unit | `pytest tests/unit/test_ai_washing_loader.py::test_dedup_same_day_scores -x` | ❌ Wave 0 |
| INT-03 | `backtest run --signal ai-washing` exits 0 with mocked loader | unit | `pytest tests/unit/test_cli.py::test_backtest_run_ai_washing_exits_zero -x` | ❌ Wave 0 |
| INT-03 | `backtest run --signal ai-washing` exits 1 with descriptive message when SignalLoadError | unit | `pytest tests/unit/test_cli.py::test_backtest_run_exits_1_on_signal_load_error -x` | ❌ Wave 0 |
| INT-03 | End-to-end: load → adapt → simulate → metrics runs without error on synthetic data | integration | `pytest tests/integration/test_ai_washing_integration.py -m integration -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_ai_washing_loader.py -x`
- **Per wave merge:** `uv run pytest tests/ --cov=src/fund_backtest --cov-report=term-missing`
- **Phase gate:** Full suite green with coverage ≥ 80% before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_ai_washing_loader.py` — covers INT-02 (all loader behaviors)
- [ ] `tests/integration/test_ai_washing_integration.py` — covers INT-03 (full pipeline, testcontainer)
- [ ] `src/fund_backtest/signal/loaders/__init__.py` — exports `AiWashingLoader`, `SignalLoadError`
- [ ] `src/fund_backtest/signal/loaders/ai_washing.py` — loader implementation

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| CLI `backtest export` uses demo data | `backtest run --signal ai-washing` uses live DB | Phase 8 | First live data flowing end-to-end |
| No `signal/loaders/` directory | `signal/loaders/` introduced with `ai_washing.py` | Phase 8 | Establishes pattern for future strategy loaders |

**Noted in cli.py (line 271):** The existing `export` command has a comment: "Live data wired in Phase 8." This confirms the planner should update that comment to point to the new `run` command.

---

## Open Questions

1. **Does `PriceBarRepository.get_bars()` accept a ticker list and date range?**
   - What we know: The method exists and is used in `PriceBuilder`. Its signature is not shown in the files read.
   - What's unclear: Exact signature — whether it accepts `tickers: list[str]`, `start: date`, `end: date`.
   - Recommendation: Read `price/repository.py` fully during planning to confirm the exact call signature. If it doesn't support filtering by ticker+date, add a `get_bars_for_signal` helper.

2. **Should `backtest run` also launch the Streamlit dashboard or just export?**
   - What we know: Success criteria says "dashboard render" completes without manual steps; but also lists "metrics computation" as a milestone. The dashboard is a separate `streamlit run` process.
   - What's unclear: Whether the `run` command should launch `streamlit` as a subprocess or just generate the exports.
   - Recommendation: For INT-03 compliance, the command should complete the full pipeline through `MetricsEngine.compute()` and optionally run exports (via `--export-all`). Launching the Streamlit dashboard as a subprocess is optional and not required for the success criteria. Dashboard can be launched separately with existing `streamlit run` invocation.

3. **Schema stability of `daily_scores` partition structure**
   - What we know: The table uses `RANGE` partitioning on `scored_at`. Monthly partitions are created in the Detector's Plan 03 migration.
   - What's unclear: Whether the Detector's database is actually seeded with partition DDL in the test environment. The testcontainer for Phase 8 integration tests will need to create the `companies` and `daily_scores` tables (with partitioning) manually or via simplified DDL.
   - Recommendation: Integration test fixtures should create a simplified `daily_scores` without partitioning (using `CREATE TABLE daily_scores (...) WITHOUT PARTITION`), since the testcontainer won't have the Detector's Alembic migrations. This is the simplest approach and fully exercises the loader's query logic.

---

## Sources

### Primary (HIGH confidence)
- `/Users/maxzou/Documents/projects/AI Hedgefund/Al Washing Detector/src/ai_washer/db/models.py` — DailyScore ORM schema, Company ORM schema, column types confirmed directly
- `/Users/maxzou/Documents/projects/AI Hedgefund/backtest/src/fund_backtest/signal/adapter.py` — shift(1) final step confirmed, SignalAdapter pipeline documented
- `/Users/maxzou/Documents/projects/AI Hedgefund/backtest/src/fund_backtest/signal/validator.py` — SignalFrame contract invariants confirmed
- `/Users/maxzou/Documents/projects/AI Hedgefund/backtest/src/fund_backtest/cli.py` — CLI pattern (CliRunner, session mock pattern, error handling)
- `/Users/maxzou/Documents/projects/AI Hedgefund/backtest/src/fund_backtest/config.py` — AppSettings env prefix `FUND_BACKTEST_`, config loader patterns
- `/Users/maxzou/Documents/projects/AI Hedgefund/backtest/tests/conftest.py` — testcontainers session fixture, rollback isolation pattern
- `/Users/maxzou/Documents/projects/AI Hedgefund/backtest/tests/unit/test_cli.py` — mock pattern for session, CliRunner invocation

### Secondary (MEDIUM confidence)
- Phase 3 STATE.md decision: "shift(1) is the final step in SignalAdapter.adapt() — Phase 4 Portfolio Simulator must NOT apply an additional shift" — confirms loader must not pre-shift

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in lockfile, versions verified in pyproject.toml
- Architecture: HIGH — integration query confirmed from Detector models.py; adapter/simulator/metrics/export all inspected directly
- Pitfalls: HIGH — derived from direct schema inspection (partition structure, scored_at timezone, SmallInteger dtype) and existing codebase patterns

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (stable domain — no fast-moving libraries involved)

## Project Constraints (from CLAUDE.md)

Directives extracted from `/Users/maxzou/Documents/projects/AI Hedgefund/CLAUDE.md` and `/Users/maxzou/Documents/projects/AI Hedgefund/Al Washing Detector/CLAUDE.md`:

| Constraint | Source | Impact on Phase 8 |
|------------|--------|-------------------|
| No Python imports between packages | AI Hedgefund CLAUDE.md | Loader MUST use raw SQL only — no `from ai_washer.db.models import DailyScore` |
| Immutability: return new objects, don't mutate | Global coding-style.md | `_pivot()` returns a new DataFrame; never mutate input |
| Functions < 50 lines | Global coding-style.md | Loader methods should be short; pivot logic extracted to `_pivot()` helper |
| Files < 800 lines | Global coding-style.md | `ai_washing.py` will be ~80 lines; well within limit |
| Error handling at every level | Global coding-style.md | `OperationalError` and empty-result caught separately, both raise `SignalLoadError` |
| All monetary values stored as cents | Project CLAUDE.md | PriceFrame conversion: `close_cents / 100` to get USD float for simulator |
| structlog for logging | Project conventions | `logger = structlog.get_logger(__name__)`, bind `component="ai_washing_loader"` |
| `FUND_BACKTEST_` env prefix | backtest config.py | Database URL env var is `FUND_BACKTEST_DATABASE_URL` |
| Google-style docstrings | Project conventions | All public methods get Args/Returns/Raises docstrings |
| `from __future__ import annotations` | Project conventions | Top of every new .py file |
| Validate at system boundaries | Global coding-style.md | `validate_signal_frame()` called in `SignalAdapter.adapt()` already — loader output will be validated there |
