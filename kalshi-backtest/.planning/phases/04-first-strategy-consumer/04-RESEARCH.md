# Phase 4: First Strategy Consumer - Research

**Researched:** 2026-04-04
**Domain:** Strategy plugin implementation, Brier score metrics, Insider Tracker signal format
**Confidence:** HIGH

## Summary

Phase 4 wires the Kalshi Insider Tracker's anomaly signals into the backtesting engine as
the first real Strategy plugin, proves the Strategy Protocol works end-to-end with a live
signal source, adds Brier score calibration measurement, and delivers a template strategy
for future onboarding.

The Insider Tracker stores detected anomalies as `Signal` ORM rows in a PostgreSQL database
(table: `signals`). Each row carries `ticker`, `signal_type` ('volume_spike' | 'price_move' |
'timing_cluster'), `confidence` (float 0–1), `details` (JSONB), and `detected_at` (UTC
timestamp). The adapter must bridge this PostgreSQL store to the backtesting engine's DuckDB
store — the two databases are independent and must remain so (independence constraint in
CLAUDE.md). The adapter's `generate_signals()` method receives a `MarketSnapshot` (bar
timestamp, close_price in cents) and returns `list[Signal]` using the backtest Signal model.

Brier score is the canonical calibration metric for binary predictions: BS = mean((p - o)^2)
where `p` is the predicted probability (entry price / 100 for a YES position, or
(100 - entry_price) / 100 for a NO position) and `o` is the actual outcome (1=YES settled,
0=NO settled). Lower is better; a random 50% guesser achieves BS = 0.25. The score is
computable from the existing `trade_log` DataFrame (columns: `direction`, `entry_price`,
`exit_reason`, `exit_price` with settlement value of 100 or 0). Only settlement trades
(exit_reason == 'settlement') contribute to Brier score — mark-to-market exits have no
ground-truth outcome.

The `_PassThroughStrategy` stub in `cli.py` (both `run` and `compare` commands) must be
replaced with a `--strategy` flag that selects a named strategy. The two strategies for
Phase 4 are: `insider-tracker` (InsiderTrackerAdapter) and `pass-through` (the existing
stub, kept for baseline comparison). Strategy selection can be a simple string-to-class
dispatch dictionary — a full plugin registry with entry_points is unnecessary for v1.

**Primary recommendation:** Build InsiderTrackerAdapter as a standalone class in
`src/kalshi_backtest/strategies/insider_tracker.py`, add brier_score to BacktestMetrics and
MetricsCalculator, wire --strategy flag in cli.py, and add ExampleStrategy to
`src/kalshi_backtest/strategies/example.py`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None — all implementation choices are at Claude's discretion.

### Claude's Discretion
- InsiderTrackerAdapter must implement the Strategy Protocol (generate_signals())
- It consumes signals from the Kalshi Insider Tracker's output — understand what that output looks like
- Brier score: measures calibration quality of probability predictions, computed alongside standard P&L metrics
- Example template: copy-and-implement pattern for future strategies
- The _PassThroughStrategy stub in cli.py should be replaced by a proper strategy selection mechanism

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STRAT-01 | Insider Tracker adapter — consume signals from the Kalshi Insider Tracker as the first strategy plugin | Insider Tracker Signal ORM schema fully read; adapter design documented in Architecture Patterns |
| STRAT-02 | Example/template strategy — demo plugin for onboarding future strategies | Strategy Protocol confirmed as structural; template design documented |
| MET-04 | Brier score — prediction calibration quality metric | Formula verified; implementation path through existing trade_log confirmed |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.48+ | Query Insider Tracker's PostgreSQL `signals` table | Already in Insider Tracker's stack; adapter needs read-only queries |
| psycopg[binary] | 3.2+ | PostgreSQL driver for Insider Tracker DB connection | Same driver the Insider Tracker uses; sync query only |
| pydantic | 2.12.5+ | InsiderSignalRow — typed wrapper for raw DB row from Insider Tracker | Fund-wide validation convention |
| numpy | 2.4.4+ | Brier score vectorized computation (mean square) | Already a project dependency |
| pandas | 3.0.2+ | trade_log access for Brier score; already in project | Already a project dependency |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | 25.5.0+ | Logging inside adapter (no signals found, confidence threshold) | Every module in the fund stack uses structlog |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Direct SQLAlchemy query to Insider Tracker DB | Import kalshi_tracker package | Direct import violates independence constraint in CLAUDE.md — no hard deps on Insider Tracker internals |
| Brier score in quantstats | Custom numpy implementation | quantstats has no Brier score function; binary prediction market specific |
| Entry_points plugin registry | Simple string dispatch dict | Entry_points is the "real" plugin system but is heavyweight for v1 with 2 strategies |

**Installation:**
```bash
# No new runtime deps needed — SQLAlchemy and psycopg already in Insider Tracker's uv.lock
# For kalshi-backtest, add sqlalchemy and psycopg as optional/adapter deps:
uv add --optional adapter sqlalchemy psycopg[binary]
# Or simply document that KALSHI_TRACKER_DATABASE_URL is needed and add to .env.example
```

Note: The cleanest approach is to add `sqlalchemy` and `psycopg[binary]` to
kalshi-backtest's pyproject.toml `dependencies` (they are already needed transitively via
the Insider Tracker) or as an optional extra. The adapter imports them directly; no Insider
Tracker package import is needed.

## Architecture Patterns

### Recommended Project Structure
```
src/kalshi_backtest/
├── strategies/
│   ├── __init__.py          # exports STRATEGY_REGISTRY dict
│   ├── insider_tracker.py   # InsiderTrackerAdapter (STRAT-01)
│   └── example.py           # ExampleStrategy (STRAT-02)
├── simulation/
│   └── protocol.py          # Strategy Protocol — unchanged
├── metrics/
│   ├── calculator.py        # BacktestMetrics + brier_score field (MET-04)
│   └── ...
└── cli.py                   # --strategy flag wired to STRATEGY_REGISTRY
```

### Pattern 1: InsiderTrackerAdapter — Read-Only DB Query

**What:** The adapter connects to the Insider Tracker's PostgreSQL database (separate from
the backtest DuckDB) at construction time, using a connection URL from environment config.
On each `generate_signals()` call, it queries for Signal rows with `ticker == snapshot.ticker`
and `detected_at` within a lookback window of the current bar's timestamp. It converts
matching rows into backtest `Signal` objects.

**When to use:** Every bar in the simulation loop where the adapter is the active strategy.

**Key design constraints:**
- Independence: The adapter queries the Insider Tracker DB via SQLAlchemy ORM — it does NOT
  import `kalshi_tracker` or any of its modules. It reconstructs only the minimal SQL query
  needed (select from `signals` table by ticker and timestamp range).
- Look-ahead safety: `detected_at` must be strictly BEFORE `snapshot.ts`. The simulation
  engine provides look-ahead protection for settlement results, but the adapter is responsible
  for its own temporal discipline on signal timestamps.
- No active polling: The adapter is read-only. It never writes to the Insider Tracker DB.

```python
# Source: verified from kalshi_tracker/db/models.py and simulation/protocol.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from kalshi_backtest.simulation.protocol import Signal

if TYPE_CHECKING:
    from kalshi_backtest.simulation.snapshot import MarketSnapshot
    from kalshi_backtest.simulation.protocol import Position

logger = structlog.get_logger(__name__)

_SIGNAL_TABLE = "signals"
_LOOKBACK_HOURS = 24  # how far back to look for Insider Tracker signals


class InsiderTrackerAdapter:
    """Strategy that replays Insider Tracker signals as backtest trades.

    Reads from the Insider Tracker's PostgreSQL `signals` table directly.
    No kalshi_tracker package import — independence constraint preserved.

    Args:
        database_url: PostgreSQL connection string for Insider Tracker DB.
        min_confidence: Minimum signal confidence threshold (0.0–1.0).
        lookback_hours: How many hours before snapshot.ts to search for signals.
        contracts_per_signal: Fixed contracts per trade (default: 1).
    """

    def __init__(
        self,
        database_url: str,
        min_confidence: float = 0.5,
        lookback_hours: int = _LOOKBACK_HOURS,
        contracts_per_signal: int = 1,
    ) -> None:
        engine = create_engine(database_url, pool_pre_ping=True)
        self._session_factory: sessionmaker[Session] = sessionmaker(engine)
        self._min_confidence = min_confidence
        self._lookback_hours = lookback_hours
        self._contracts = contracts_per_signal
        self._log = logger.bind(strategy="InsiderTrackerAdapter")

    def generate_signals(
        self,
        snapshot: MarketSnapshot,
        open_positions: list[Position],
    ) -> list[Signal]:
        """Query Insider Tracker signals for snapshot.ticker near snapshot.ts.

        Args:
            snapshot: Current bar — ticker and ts used for DB query.
            open_positions: Currently held positions (avoid double-entry).

        Returns:
            List of Signal objects derived from Insider Tracker detections.
        """
        # Don't re-enter a market we already hold
        held_tickers = {p.ticker for p in open_positions}
        if snapshot.ticker in held_tickers:
            return []

        window_start = snapshot.ts - timedelta(hours=self._lookback_hours)
        window_end = snapshot.ts  # strictly before current bar — no look-ahead

        try:
            with self._session_factory() as session:
                rows = session.execute(
                    text(
                        "SELECT signal_type, confidence, details "
                        "FROM signals "
                        "WHERE ticker = :ticker "
                        "  AND detected_at >= :start "
                        "  AND detected_at < :end "
                        "  AND confidence >= :min_conf "
                        "ORDER BY detected_at DESC "
                        "LIMIT 1"
                    ),
                    {
                        "ticker": snapshot.ticker,
                        "start": window_start,
                        "end": window_end,
                        "min_conf": self._min_confidence,
                    },
                ).fetchall()
        except Exception:
            self._log.warning("insider_adapter_db_error", ticker=snapshot.ticker, exc_info=True)
            return []

        if not rows:
            return []

        row = rows[0]
        signal_type = row[0]
        confidence = row[1]

        # Price move signal → bet YES (price moved up); volume spike → YES bet
        # Strategy logic: copy the direction implied by the signal
        direction: str
        if signal_type == "price_move":
            details = row[2] or {}
            last_price = details.get("last_price", snapshot.close_price)
            prev_price = details.get("prev_price", last_price)
            direction = "yes" if last_price > prev_price else "no"
        else:
            # volume_spike, timing_cluster: bet YES (bullish momentum)
            direction = "yes"

        return [
            Signal(
                ticker=snapshot.ticker,
                direction=direction,
                contracts=self._contracts,
                limit_price=snapshot.close_price,
                reason=f"insider_tracker:{signal_type}:confidence={confidence:.2f}",
            )
        ]
```

### Pattern 2: Brier Score Computation

**What:** Brier score measures how well predicted probabilities match binary outcomes.
For Kalshi YES contracts: predicted probability = `entry_price / 100`. For NO contracts:
predicted probability = `(100 - entry_price) / 100`. Outcome o = 1 if the bet won
(settlement aligned with direction), 0 if it lost.

**When to use:** Added to `BacktestMetrics` model and computed in `MetricsCalculator.compute()`.
Only settlement trades contribute (exit_reason == 'settlement').

**Formula:** `BS = mean((p_i - o_i)^2)` over all settled trades. Lower = better calibrated.
Reference: BS = 0.25 for a random 50% guesser on binary events (theoretical worst-case
for a calibrated predictor). Perfect calibration = 0.0.

```python
# Source: standard probability scoring rule, verified against Wikipedia/literature
import numpy as np
import pandas as pd

def _compute_brier_score(trade_log: pd.DataFrame) -> float | None:
    """Compute Brier score for settled binary prediction market trades.

    Only settlement exits have a deterministic ground truth outcome.
    Mark-to-market exits are excluded.

    Args:
        trade_log: BacktestResult.trade_log DataFrame.
            Required columns: direction, entry_price, exit_price, exit_reason.

    Returns:
        Float Brier score in [0.0, 1.0], or None if no settlement trades exist.
    """
    settled = trade_log[trade_log["exit_reason"] == "settlement"]
    if settled.empty:
        return None

    # exit_price == 100 means YES won (contract settled YES); 0 means NO won
    yes_won = (settled["exit_price"] == 100).astype(float)  # outcome for YES direction
    no_won = (settled["exit_price"] == 0).astype(float)     # outcome for NO direction

    # predicted probability of the HELD direction being correct
    predicted = np.where(
        settled["direction"] == "yes",
        settled["entry_price"] / 100.0,        # YES: price = prob of YES
        (100 - settled["entry_price"]) / 100.0, # NO: (1-price) = prob of NO
    )

    # outcome = 1 if the direction we held was the winning direction
    outcome = np.where(
        settled["direction"] == "yes",
        yes_won.values,
        no_won.values,
    )

    return float(np.mean((predicted - outcome) ** 2))
```

**Adding to BacktestMetrics:**
```python
# In metrics/calculator.py — BacktestMetrics gains one optional field:
brier_score: float | None = None  # None when no settlement trades

# In MetricsCalculator.compute(), after existing metric computation:
brier_score = _compute_brier_score(result.trade_log)
# Pass to BacktestMetrics constructor
```

### Pattern 3: Strategy Registry and --strategy CLI Flag

**What:** A simple module-level dict maps strategy names to factory callables. The CLI
`run` and `compare` commands gain a `--strategy` option that looks up the factory.

```python
# strategies/__init__.py
from kalshi_backtest.strategies.example import ExampleStrategy
from kalshi_backtest.strategies.insider_tracker import InsiderTrackerAdapter

STRATEGY_REGISTRY: dict[str, type] = {
    "pass-through": _PassThroughStrategy,    # baseline stub (moved here from cli.py)
    "insider-tracker": InsiderTrackerAdapter,
    "example": ExampleStrategy,
}
```

**CLI wiring:**
```python
# cli.py run command — add --strategy option
strategy_name: str = typer.Option(
    "pass-through",
    "--strategy",
    help="Strategy to run: pass-through, insider-tracker, example",
)
```

InsiderTrackerAdapter requires `database_url` at construction time. The CLI should read
`KALSHI_TRACKER_DATABASE_URL` from env/settings and pass it when constructing the adapter.
If the env var is absent and `insider-tracker` is requested, the CLI should fail fast with
a clear message (consistent with existing credential-validation pattern in cli.py).

### Pattern 4: ExampleStrategy Template

**What:** A minimal but fully functional strategy that demonstrates the plugin interface.
Buys YES on any market where the current price is below a configurable threshold (a simple
"cheap contract" momentum signal).

```python
# strategies/example.py
from __future__ import annotations
from typing import TYPE_CHECKING
from kalshi_backtest.simulation.protocol import Signal

if TYPE_CHECKING:
    from kalshi_backtest.simulation.snapshot import MarketSnapshot
    from kalshi_backtest.simulation.protocol import Position


class ExampleStrategy:
    """Minimal example strategy for onboarding documentation.

    Buys YES whenever the market price is below `entry_threshold` cents.
    Demonstrates the two-method Protocol interface with no dependencies.

    Args:
        entry_threshold: Max yes_price to buy at (cents, 0-100). Default: 40.
        contracts: Contracts per trade. Default: 1.
    """

    def __init__(self, entry_threshold: int = 40, contracts: int = 1) -> None:
        self._threshold = entry_threshold
        self._contracts = contracts

    def generate_signals(
        self,
        snapshot: MarketSnapshot,
        open_positions: list[Position],
    ) -> list[Signal]:
        held = {p.ticker for p in open_positions}
        if snapshot.ticker in held:
            return []
        if snapshot.close_price <= self._threshold:
            return [
                Signal(
                    ticker=snapshot.ticker,
                    direction="yes",
                    contracts=self._contracts,
                    limit_price=snapshot.close_price,
                    reason=f"example:price_below_{self._threshold}",
                )
            ]
        return []
```

### Anti-Patterns to Avoid
- **Importing kalshi_tracker directly:** Violates independence constraint. Always query the
  Insider Tracker DB via raw SQLAlchemy `text()` queries, not by importing ORM models.
- **Mutating Signal objects:** Signal is a frozen Pydantic model — never modify fields.
  Create a new Signal instead.
- **Look-ahead in adapter:** Do not use `detected_at <= snapshot.ts` (inclusive). Use
  strictly less-than (`< snapshot.ts`) to prevent the adapter from seeing signals generated
  at exactly the same instant as the bar.
- **Including non-settlement exits in Brier score:** Mark-to-market exits have no ground
  truth — filter to `exit_reason == 'settlement'` only.
- **Hardcoding brier_score = 0.0 on empty:** Use `None` (Optional[float]) to distinguish
  "no settlement trades" from "perfectly calibrated" (which would also be 0.0).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PostgreSQL query execution | Custom HTTP client or file reader | SQLAlchemy `text()` query via existing engine | SQLAlchemy already in Insider Tracker stack; handles connection pooling, reconnects, parameter escaping |
| Brier score | Look up a stats library | Custom 3-line numpy formula | No library has this for binary prediction markets; the formula is 3 lines and well-understood |
| Strategy discovery/loading | importlib-based dynamic loading | Simple dict registry in strategies/__init__.py | 2 strategies in v1 — full plugin registry is over-engineering |
| CLI argument validation | Manual isinstance checks | Typer options with choices + ValidationError pattern | Consistent with existing cli.py pattern |

**Key insight:** The most complex part of this phase is the cross-database adapter design
(PostgreSQL → DuckDB via Strategy Protocol). Everything else is additive and straightforward.

## Common Pitfalls

### Pitfall 1: Look-Ahead Leak in Adapter Timestamp Query
**What goes wrong:** Using `detected_at <= snapshot.ts` (inclusive) means signals generated
in the same candlestick bar the adapter is evaluating are visible. In a low-frequency
backtest this is subtle — the Insider Tracker might have detected a signal at 14:00 and
the backtest bar is also 14:00.
**Why it happens:** Natural inclusive-range thinking.
**How to avoid:** Always use strictly-less-than: `detected_at < snapshot.ts`.
**Warning signs:** Anomalously high win rates in the first bar after signal generation.

### Pitfall 2: Brier Score on Mark-to-Market Exits
**What goes wrong:** Including exits where `exit_reason != 'settlement'` corrupts the
Brier score because there's no ground-truth outcome — the position was closed at a price,
not at settlement.
**Why it happens:** Computing BS over all trade_log rows without filtering.
**How to avoid:** Filter `trade_log[trade_log["exit_reason"] == "settlement"]` before
computing BS. Return `None` (not 0.0) if no settlement rows exist.
**Warning signs:** BS of exactly 0.0 with many trades — means all filtered out or bug.

### Pitfall 3: Direction-Probability Inversion for NO Contracts
**What goes wrong:** Computing Brier score as `entry_price / 100` for both YES and NO
contracts. A NO contract bought at 40 cents implies the buyer thinks NO has 60% probability
(not 40%).
**Why it happens:** Forgetting that NO contracts are the complement.
**How to avoid:** YES direction: p = entry_price/100. NO direction: p = (100 - entry_price)/100.
**Warning signs:** Brier scores > 0.25 on a strategy that should be better than random.

### Pitfall 4: InsiderTrackerAdapter Requires a Separate DB Connection
**What goes wrong:** Passing `KALSHI_BACKTEST_DATABASE_URL` (the DuckDB path) as the
adapter's database_url instead of `KALSHI_TRACKER_DATABASE_URL` (PostgreSQL).
**Why it happens:** Two databases in the system — easy to confuse env vars.
**How to avoid:** The adapter constructor should take `database_url` explicitly; the CLI
reads it from a distinct env var (`KALSHI_TRACKER_DATABASE_URL`). Fail fast if absent when
`--strategy insider-tracker` is selected.
**Warning signs:** SQLAlchemy raises `DuckDB not supported` or connection error immediately.

### Pitfall 5: cli.py _SCALAR_ROWS Missing brier_score
**What goes wrong:** Adding `brier_score` to BacktestMetrics but forgetting to add it to
`_SCALAR_ROWS` in cli.py — the metric is computed but never displayed.
**Why it happens:** Two display sites (print_metrics_summary and _SCALAR_ROWS) both need
updating.
**How to avoid:** Search cli.py for all metric display callsites when adding to BacktestMetrics.

## Code Examples

Verified patterns from official sources:

### Existing Signal constructor (from protocol.py)
```python
# Source: kalshi-backtest/src/kalshi_backtest/simulation/protocol.py
Signal(
    ticker="KXBTC-24DEC-T50000",
    direction="yes",       # "yes" or "no"
    contracts=1,           # must be >= 1
    limit_price=45,        # cents [0, 100]
    reason="my_strategy:reason_string",
)
```

### Existing BacktestMetrics model_copy pattern (from cli.py line 450)
```python
# Source: kalshi-backtest/src/kalshi_backtest/cli.py
metrics = metrics.model_copy(update={"strategy_name": strat.name})
```

### Existing empty-guard pattern in MetricsCalculator (from calculator.py lines 205-224)
```python
# Source: kalshi-backtest/src/kalshi_backtest/metrics/calculator.py
if result.trade_log.empty:
    return BacktestMetrics(
        run_id=result.run_id,
        strategy_name=result.strategy_name,
        # ... all fields with defaults
        brier_score=None,  # ADD THIS
    )
```

### Insider Tracker Signal ORM schema (from kalshi_tracker/db/models.py)
```
Table: signals (PostgreSQL)
  id          UUID PK (from AppendOnlyMixin)
  ticker      VARCHAR(50)     — Kalshi market ticker
  signal_type VARCHAR(50)     — 'volume_spike' | 'price_move' | 'timing_cluster'
  confidence  FLOAT           — [0.0, 1.0]
  details     JSONB           — raw stats dict (z_score, move_pct, concentration, etc.)
  detected_at DATETIME(tz)    — UTC timestamp of detection
  created_at  DATETIME(tz)    — row insertion time (from AppendOnlyMixin)
```

### InsiderTrackerAdapter min SQLAlchemy query (no ORM import from kalshi_tracker)
```python
# Source: derived from kalshi_tracker/db/models.py schema + SQLAlchemy text() pattern
from sqlalchemy import text

rows = session.execute(
    text(
        "SELECT signal_type, confidence, details "
        "FROM signals "
        "WHERE ticker = :ticker "
        "  AND detected_at >= :start "
        "  AND detected_at < :end "
        "  AND confidence >= :min_conf "
        "ORDER BY detected_at DESC "
        "LIMIT 1"
    ),
    {"ticker": ticker, "start": start_ts, "end": bar_ts, "min_conf": min_confidence},
).fetchall()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| _PassThroughStrategy inline in cli.py | Strategies module with registry | Phase 4 | Strategies are discoverable and testable in isolation |
| BacktestMetrics with no calibration score | BacktestMetrics + brier_score field | Phase 4 | Investors can see calibration quality, not just P&L |

**No deprecated patterns identified for this phase.**

## Open Questions

1. **Lookback window for adapter signal query**
   - What we know: Insider Tracker fires signals at 5–10 second intervals with a cooldown
     of 300 seconds (5 min). Backtest bars are daily candlesticks (one bar per day per market).
   - What's unclear: Is a 24-hour lookback window appropriate, or should it be shorter to
     avoid stale signals? A daily bar at 14:00 UTC with a 24h lookback would pick up signals
     from the previous day, which may be valid for a slow-moving politics market.
   - Recommendation: Default to 24h lookback; make it a configurable constructor parameter
     so the planner can tune it at test time.

2. **Confidence threshold for the adapter**
   - What we know: Insider Tracker defaults to `min_confidence = 0.0` in SignalSettings,
     but the ExecutionSettings threshold for live trading is 0.6.
   - What's unclear: What threshold produces backtest signal density worth measuring?
   - Recommendation: Default the adapter to 0.5 (midpoint) as a reasonable starting value;
     expose as constructor parameter for parameter sweep compatibility.

3. **Multi-signal handling per bar**
   - What we know: The adapter query uses `LIMIT 1` (most recent signal in the window).
   - What's unclear: Should the adapter return signals from all detectors that fired in the
     window (volume_spike AND price_move both present) or just the most recent one?
   - Recommendation: Start with LIMIT 1 (most recent). Multiple simultaneous positions on
     the same ticker are prevented by the `held_tickers` check. This keeps v1 simple.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Package runtime | yes | 3.12 | — |
| uv | Package management | yes | — | — |
| kalshi-backtest package | All phase code | yes | 0.1.0 | — |
| PostgreSQL (Insider Tracker DB) | InsiderTrackerAdapter live tests | unknown | — | Adapter unit tests use SQLite in-memory DB via SQLAlchemy |
| DuckDB | Backtest simulation | yes (in package) | 1.5.0+ | — |

**Missing dependencies with no fallback:**
- None that block core implementation. PostgreSQL is only needed for integration tests
  of the adapter against a live Insider Tracker DB.

**Missing dependencies with fallback:**
- PostgreSQL for InsiderTrackerAdapter integration tests: use SQLite in-memory database
  with a `signals` table created in a pytest fixture — SQLAlchemy's text() queries work
  identically on both backends.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_strategies.py tests/test_metrics_calculator.py -x -q` |
| Full suite command | `uv run pytest --cov=kalshi_backtest --cov-report=term-missing` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STRAT-01 | InsiderTrackerAdapter.generate_signals() returns correct Signal given DB rows | unit | `uv run pytest tests/test_strategies.py::test_insider_adapter_generates_signal -x` | No — Wave 0 |
| STRAT-01 | Adapter filters signals by ticker and timestamp (no look-ahead) | unit | `uv run pytest tests/test_strategies.py::test_insider_adapter_no_lookahead -x` | No — Wave 0 |
| STRAT-01 | Adapter returns empty list when no matching signals in DB | unit | `uv run pytest tests/test_strategies.py::test_insider_adapter_no_signals -x` | No — Wave 0 |
| STRAT-01 | Adapter returns empty list when ticker already held | unit | `uv run pytest tests/test_strategies.py::test_insider_adapter_skips_held -x` | No — Wave 0 |
| STRAT-01 | Adapter returns empty on DB error (logs warning, no raise) | unit | `uv run pytest tests/test_strategies.py::test_insider_adapter_db_error -x` | No — Wave 0 |
| STRAT-02 | ExampleStrategy returns Signal when close_price below threshold | unit | `uv run pytest tests/test_strategies.py::test_example_strategy_buys_cheap -x` | No — Wave 0 |
| STRAT-02 | ExampleStrategy returns empty when price above threshold | unit | `uv run pytest tests/test_strategies.py::test_example_strategy_skips_expensive -x` | No — Wave 0 |
| STRAT-02 | ExampleStrategy satisfies Strategy Protocol (isinstance check) | unit | `uv run pytest tests/test_strategies.py::test_example_strategy_satisfies_protocol -x` | No — Wave 0 |
| MET-04 | brier_score computed correctly for YES settlement trades | unit | `uv run pytest tests/test_metrics_calculator.py::test_brier_score_yes_settlement -x` | No — add to existing file |
| MET-04 | brier_score computed correctly for NO settlement trades | unit | `uv run pytest tests/test_metrics_calculator.py::test_brier_score_no_settlement -x` | No — add to existing file |
| MET-04 | brier_score is None when no settlement trades | unit | `uv run pytest tests/test_metrics_calculator.py::test_brier_score_none_when_no_settlement -x` | No — add to existing file |
| MET-04 | brier_score excluded from Brier calc for mark-to-market exits | unit | `uv run pytest tests/test_metrics_calculator.py::test_brier_score_excludes_mtm -x` | No — add to existing file |
| STRAT-01+02 | CLI --strategy flag selects correct strategy class | unit | `uv run pytest tests/test_cli.py::test_run_strategy_flag -x` | No — add to existing file |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_strategies.py tests/test_metrics_calculator.py -x -q`
- **Per wave merge:** `uv run pytest --cov=kalshi_backtest --cov-report=term-missing`
- **Phase gate:** Full suite green (221 existing + new tests) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_strategies.py` — all STRAT-01 and STRAT-02 unit tests (new file)
- [ ] `tests/conftest.py` — add `sqlite_signals_db` fixture: in-memory SQLite with `signals`
  table for adapter tests (no PostgreSQL required)
- [ ] Add `brier_score` tests to `tests/test_metrics_calculator.py` (existing file, add cases)
- [ ] Add `--strategy` CLI flag test to `tests/test_cli.py` (existing file, add case)

## Sources

### Primary (HIGH confidence)
- Direct code read: `kalshi-backtest/src/kalshi_backtest/simulation/protocol.py` — Signal model fields, Strategy Protocol interface
- Direct code read: `kalshi-backtest/src/kalshi_backtest/simulation/snapshot.py` — MarketSnapshot fields (ticker, ts, close_price in cents)
- Direct code read: `kalshi-backtest/src/kalshi_backtest/metrics/calculator.py` — BacktestMetrics model, MetricsCalculator.compute() pattern
- Direct code read: `kalshi-backtest/src/kalshi_backtest/cli.py` — _PassThroughStrategy stub, _SCALAR_ROWS, print_metrics_summary
- Direct code read: `kalshi-backtest/src/kalshi_backtest/simulation/runner.py` — BacktestResult.trade_log schema (columns verified)
- Direct code read: `Kalshi Insider Tracker/src/kalshi_tracker/db/models.py` — Signal ORM table schema (ticker, signal_type, confidence, details JSONB, detected_at)
- Direct code read: `Kalshi Insider Tracker/src/kalshi_tracker/signals/types.py` — DetectionResult contract
- Direct code read: `Kalshi Insider Tracker/src/kalshi_tracker/signals/detectors.py` — signal_type values, details dict keys per detector
- Direct code read: `Kalshi Insider Tracker/src/kalshi_tracker/config.py` — KALSHI_TRACKER_DATABASE_URL env var pattern
- Direct code read: `kalshi-backtest/tests/conftest.py` — duckdb_con fixture pattern (template for sqlite_signals_db fixture)

### Secondary (MEDIUM confidence)
- Brier score formula: Wikipedia "Brier score" — standard probability scoring rule, BS = mean((f-o)^2), verified against multiple sources. Well-established since 1950.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already used in the project; no new dependencies needed
- Architecture: HIGH — derived directly from reading existing source files; no guesswork
- Pitfalls: HIGH — derived from code inspection (timestamp operators, Brier score formula, direction inversion)
- Signal format: HIGH — read directly from Insider Tracker ORM models and detector output

**Research date:** 2026-04-04
**Valid until:** 2026-05-04 (stable — no external API dependencies in this phase)
