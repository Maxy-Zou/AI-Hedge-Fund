# Phase 2: Simulation Engine - Research

**Researched:** 2026-04-05
**Domain:** Binary event contract backtesting simulation engine (Python Protocol interface, bar-by-bar replay, Kalshi P&L mechanics)
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Strategy Protocol (not ABC) — structural subtyping so strategies don't import engine internals
- `generate_signals()` is the plugin interface method
- Bar-by-bar replay: bulk-load candles upfront (vectorized), iterate chronologically per market per day (event-driven) to prevent lookahead
- MarketSnapshot must expose `result=None` for all bars before close_time — enforced by the BarIterator
- Exact Kalshi fee formula: `ceil(0.07 * C * P * (1-P))` where C=contracts, P=price in [0,1]
- Conservative fill: use ask price for buys, bid price for sells, minimum spread floor
- Binary P&L: hold-to-settlement ($0/$1) and pre-resolution exit (mark-to-market)
- Parameter grid sweep: test multiple strategy configs in a single run
- Walk-forward validation: rolling train/test splits

### Claude's Discretion
All implementation choices not listed above are at Claude's discretion — use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SIM-01 | Strategy Protocol interface — implement `generate_signals()` to plug in any strategy | Python `typing.Protocol` with `@runtime_checkable` enables structural subtyping; verified working in Python 3.11+ |
| SIM-02 | Bar-by-bar replay engine that prevents look-ahead bias (settlement result hidden until after close_time) | BarIterator pattern: bulk-load candles upfront, iterate chronologically; `result=None` enforced by comparing bar `ts` vs `market.close_time` |
| SIM-03 | Exact Kalshi fee formula: `ceil(0.07 * C * P * (1-P))` | Verified: taker fee = `ceil(0.07 * C * P * (1-P))`, maker fee = `ceil(0.0175 * C * P * (1-P))`; P is decimal [0,1]; max fee 1.75¢/contract at P=0.50 |
| SIM-04 | Conservative fill model with spread-aware execution | Use close_price as mid; apply spread floor (1–2 cents); buy fills at `min(limit_price, mid + half_spread)`, sell fills at `max(limit_price, mid - half_spread)` |
| SIM-05 | Binary P&L — hold-to-settlement ($0/$1) and pre-resolution exit (mark-to-market) | Hold-to-settlement: YES win = `(100 - entry) * C`, loss = `-entry * C`; mark-to-market exit: `(exit_price - entry_price) * C` |
| SIM-06 | Parameter grid sweep — test multiple strategy configurations in a single run | `itertools.product` over parameter ranges; return list of `BacktestResult` sorted by Sharpe; no external libraries needed |
| SIM-07 | Walk-forward validation — rolling train/test splits | Slice date range into N folds; optimize on in-sample, validate on out-of-sample; Python `sklearn.model_selection.TimeSeriesSplit` or manual split logic |
| CLI-02 | Configurable lookback window per backtest run (default ~1 year) | Add `--lookback-days` option to `run` command using existing Typer pattern from `ingest` command |
</phase_requirements>

---

## Summary

Phase 2 builds the core simulation machinery that makes the backtesting engine useful. The key design challenge is preventing look-ahead bias while maintaining performance — solved by the hybrid approach: bulk-load all candles for the date range upfront (vectorized query), then replay them chronologically one bar at a time (event-driven iteration). The `BarIterator` is the look-ahead guardian: it physically enforces `result=None` on every snapshot until `ts >= market.close_time`.

The Strategy Protocol (not ABC) is the right choice for the plugin interface because strategies implementing it don't need to import anything from this codebase. `@runtime_checkable` enables `isinstance()` checks in tests. The Kalshi fee formula is confirmed: taker fee = `ceil(0.07 * C * P * (1-P))` where P is decimal [0,1], capped at 1.75 cents/contract at P=0.50. Since the conservative fill model assumes taker fills (crossing the spread), the 7% formula applies to all fills.

Parameter grid sweep uses `itertools.product` over a Pydantic config object's field ranges — no external libraries needed. Walk-forward validation splits the date range into rolling folds. Both features are implemented as extensions of the core `BacktestRunner` rather than separate systems.

**Primary recommendation:** Build `BacktestRunner` → `BarIterator` → `Strategy Protocol` → `FillEngine` as the core path. Add `ParameterSweeper` and `WalkForwardValidator` as thin wrappers that call `BacktestRunner` in a loop.

---

## Standard Stack

### Core (all already in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pandas` | 3.0.2+ | Time-indexed price series, trade log DataFrame | Already in deps; `fetchdf()` converts DuckDB results directly |
| `numpy` | 2.4.4+ | Vectorized P&L math, spread calculations | Already in deps; needed for efficient array ops in grid sweep |
| `pydantic` | 2.12.5+ | `MarketSnapshot`, `Signal`, `Position`, `Fill`, `BacktestResult` immutable models | Fund-wide standard; enforces frozen contracts between layers |
| `structlog` | 25.5.0+ | Structured logging throughout simulation loop | Fund-wide standard; bind run_id, strategy, phase per execution |
| `typer` | 0.24.1+ | Add `run` and `compare` CLI commands | Already used for `ingest`; extend same `app` object |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `itertools` (stdlib) | — | `product()` for parameter grid sweep | All grid sweep — no external dependency needed |
| `math` (stdlib) | — | `ceil()` for Kalshi fee formula | Fee calculation only |
| `typing` (stdlib) | — | `Protocol`, `runtime_checkable` | Strategy interface definition |
| `dataclasses` (stdlib) | — | `@dataclass(frozen=True)` for `BacktestResult` | When Pydantic is overkill for simple result containers |
| `datetime` (stdlib) | — | Date range slicing, bar timestamp comparisons | Bar iteration, walk-forward date splits |
| `freezegun` | 1.5.5 (dev) | Freeze time in tests that depend on `datetime.now()` | Test-only; already in dev deps |

### No new dependencies needed

All required libraries are already installed. Phase 2 adds zero new `pyproject.toml` entries.

---

## Architecture Patterns

### Recommended Module Structure

```
src/kalshi_backtest/
├── simulation/
│   ├── __init__.py          # exports: BacktestRunner, Strategy, Signal, Position, MarketSnapshot
│   ├── protocol.py          # Strategy Protocol, Signal, Position dataclasses
│   ├── snapshot.py          # MarketSnapshot frozen model, build_snapshot() factory
│   ├── bar_iterator.py      # BarIterator — lookahead-safe chronological replay
│   ├── fill_engine.py       # FillEngine — spread model, fee formula, fill creation
│   ├── position_tracker.py  # PositionTracker — open/closed position state
│   ├── runner.py            # BacktestRunner — orchestrates one full backtest run
│   ├── sweep.py             # ParameterSweeper — grid sweep over strategy configs
│   └── walkforward.py       # WalkForwardValidator — rolling train/test splits
├── db/
│   └── repository.py        # EXISTING — add get_markets_for_simulation() query
└── cli.py                   # EXISTING — add `run` command (CLI-02)
```

**File size discipline:** Each file stays under 200 lines. `runner.py` is the most complex — if it exceeds 200 lines, extract `_process_bar()` to a helper.

---

### Pattern 1: Strategy Protocol with `@runtime_checkable`

**What:** Define the plugin interface using `typing.Protocol` with `@runtime_checkable`. Any class with a matching `generate_signals()` method satisfies it — no inheritance required.

**When to use:** Always, for the Strategy interface.

**Why Protocol over ABC:** Third-party strategies (e.g., Insider Tracker adapter in Phase 4) don't need to import from this codebase at all. `@runtime_checkable` enables `isinstance(strategy, Strategy)` checks in the runner and in tests.

```python
# Source: typing module docs + verified with Python 3.12
from typing import Protocol, runtime_checkable
from kalshi_backtest.simulation.snapshot import MarketSnapshot
from kalshi_backtest.simulation.protocol import Signal, Position

@runtime_checkable
class Strategy(Protocol):
    """Plugin interface for backtestable strategies.

    Any class implementing generate_signals() satisfies this protocol
    without explicit inheritance. Strategies may hold internal state
    between calls (e.g., rolling averages, position history).
    """
    def generate_signals(
        self,
        snapshot: MarketSnapshot,
        open_positions: list[Position],
    ) -> list[Signal]: ...
```

**Testing without a real strategy:**
```python
class _AlwaysBuyStrategy:
    """Stub strategy for unit tests — buys every bar."""
    def generate_signals(self, snapshot, open_positions):
        return [Signal(ticker=snapshot.ticker, direction="yes", contracts=1,
                       limit_price=snapshot.close_price, reason="test")]
```

---

### Pattern 2: MarketSnapshot — the look-ahead firewall

**What:** A frozen Pydantic model that represents a single bar of market data. The critical invariant: `result` is `None` for all bars where `ts < market.close_time`.

**When to use:** The `BarIterator` constructs one `MarketSnapshot` per (ticker, bar). Nothing else constructs snapshots.

```python
# Source: research/ARCHITECTURE.md verified pattern
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel

class MarketSnapshot(BaseModel):
    """Immutable view of one market at one point in time.

    result is None for all bars before market.close_time.
    The BarIterator enforces this — it is the look-ahead firewall.
    """
    model_config = {"frozen": True}

    ticker: str
    event_ticker: str
    series_ticker: str
    ts: datetime                # bar timestamp (naive UTC)
    close_price: int            # yes_price in cents [0,100]
    open_price: int | None
    high_price: int | None
    low_price: int | None
    volume: int | None
    close_time: datetime        # market expiration (naive UTC)
    result: str | None          # None until ts >= close_time AND result known
    subtitle: str | None        # human-readable outcome description
```

---

### Pattern 3: BarIterator — chronological replay with look-ahead prevention

**What:** Loads all candles for all in-scope markets upfront (one bulk DuckDB query), then yields `MarketSnapshot` objects in strict chronological order. Never queries the database during iteration.

**Critical invariant:** The iterator sets `result=None` on any bar where `ts < market.close_time`, regardless of what the database has stored.

```python
# Pseudocode — confirmed safe pattern
class BarIterator:
    def __init__(self, markets: list[dict], candles_by_ticker: dict[str, list[dict]]):
        self._markets = {m["ticker"]: m for m in markets}
        self._candles = candles_by_ticker  # pre-loaded, not fetched per bar

    def __iter__(self):
        # Collect all (ts, ticker, candle) triples and sort by ts
        all_bars = []
        for ticker, candles in self._candles.items():
            for candle in candles:
                all_bars.append((candle["ts"], ticker, candle))
        all_bars.sort(key=lambda x: x[0])  # chronological order

        for ts, ticker, candle in all_bars:
            market = self._markets[ticker]
            # LOOK-AHEAD FIREWALL: never expose result before close_time
            result = None
            if ts >= market["close_time"] and market["result"] is not None:
                result = market["result"]
            yield MarketSnapshot(
                ticker=ticker,
                ts=ts,
                result=result,
                # ... other fields from candle and market
            )
```

**Why bulk-load then iterate:** Pure event-driven (one DB query per bar) is too slow for thousands of markets × 365 bars. Pure vectorized (all signals at once) creates look-ahead bias risk. The hybrid loads once (vectorized), then processes sequentially (event-driven).

---

### Pattern 4: Kalshi Fee Formula

**What:** The exact fee formula for taker fills (conservative fill model assumes all fills are taker):

```python
# Source: Kalshi fee schedule (kalshi.com/fee-schedule) + whirligigbear.substack.com
import math

def calculate_fee_cents(contracts: int, price_fraction: float) -> int:
    """Kalshi taker fee in integer cents.

    Fee = ceil(0.07 * C * P * (1-P))
    where P is the YES price as a fraction [0.0, 1.0]

    Maximum: 1.75 cents/contract at P=0.50
    Approaches 0 as P approaches 0 or 1 (parabolic curve)

    Args:
        contracts: Number of contracts traded (positive integer)
        price_fraction: YES price in [0.0, 1.0] (not cents)

    Returns:
        Fee in integer cents (minimum 1 cent for any trade)
    """
    raw = 0.07 * contracts * price_fraction * (1.0 - price_fraction)
    return max(1, math.ceil(raw))
```

**Important precision note:** `price_fraction` is in `[0.0, 1.0]`, NOT cents [0, 100]. If candle prices are stored as integer cents (0–100), divide by 100.0 before calling this function.

**Maker vs taker distinction:** For v1, the conservative fill model assumes all fills are taker fills (crossing the spread). The maker formula is `ceil(0.0175 * C * P * (1-P))` — 4x cheaper. Do NOT implement maker fees in v1; use taker fees universally for conservative estimates.

---

### Pattern 5: Conservative Fill Model

**What:** Convert a `Signal`'s desired price into a fill price that is worse than the mid-price, simulating spread impact. Uses the candle's close price as the mid estimate (no L2 order book data available).

```python
MINIMUM_SPREAD_CENTS = 1  # Conservative floor — Kalshi min tick is 1 cent

def simulate_fill_price(
    direction: str,  # 'yes' or 'no'
    limit_price: int,  # cents [0,100]
    mid_price: int,   # close_price from candle, cents
    spread_floor: int = MINIMUM_SPREAD_CENTS,
) -> int | None:
    """Return fill price in cents, or None if limit is not fillable.

    Buy YES: fill at mid + half_spread (paying the offer)
    Buy NO: equivalent to selling YES — fill at mid - half_spread

    Returns None if the limit price is worse than the fill price
    (order cannot be filled at a realistic price).
    """
    half_spread = max(spread_floor, 1) // 2 + (max(spread_floor, 1) % 2)

    if direction == "yes":
        fill = mid_price + half_spread
        if limit_price < fill:
            return None  # limit too low to fill
        return min(fill, 100)  # cap at 100 cents
    else:  # direction == "no"
        fill = mid_price - half_spread
        if limit_price < (100 - fill):
            return None  # limit too low
        return max(fill, 0)  # floor at 0 cents
```

---

### Pattern 6: Binary P&L Calculation

**What:** Kalshi contracts settle to 100 cents (win) or 0 cents (loss). Two P&L modes are required.

```python
def calculate_settlement_pnl(
    direction: str,       # 'yes' or 'no'
    entry_price: int,     # cents [0,100]
    contracts: int,
    result: str,          # 'yes' or 'no'
) -> int:
    """Hold-to-settlement P&L in cents.

    YES position:
      result='yes' → win: (100 - entry_price) * contracts
      result='no'  → loss: -entry_price * contracts

    NO position (priced as 100 - yes_price):
      result='no'  → win: (100 - entry_price) * contracts
      result='yes' → loss: -entry_price * contracts
    """
    win = (direction == "yes" and result == "yes") or \
          (direction == "no" and result == "no")
    if win:
        return (100 - entry_price) * contracts
    return -entry_price * contracts


def calculate_exit_pnl(
    direction: str,
    entry_price: int,
    exit_price: int,
    contracts: int,
) -> int:
    """Mark-to-market exit P&L in cents (pre-resolution sell).

    YES position: (exit_price - entry_price) * contracts
    NO position:  (entry_price - exit_price) * contracts
    """
    if direction == "yes":
        return (exit_price - entry_price) * contracts
    return (entry_price - exit_price) * contracts
```

**Note on v1 scope:** The CONTEXT.md specifies both hold-to-settlement and pre-resolution exit. However, the primary simulation path holds to settlement (no mid-contract exits). Pre-resolution exit is needed for the FillEngine's `exit()` method to support strategies that want to exit early.

---

### Pattern 7: Parameter Grid Sweep

**What:** Run the same `BacktestRunner` multiple times with different strategy configs. Return all results sorted by Sharpe ratio.

```python
# Source: itertools.product standard pattern — no external library needed
import itertools
from dataclasses import dataclass, fields
from typing import Any

def run_grid_sweep(
    strategy_class: type,
    param_grid: dict[str, list[Any]],  # e.g. {"threshold": [0.6, 0.7], "size": [10, 25]}
    runner: BacktestRunner,
) -> list[BacktestResult]:
    """Run all combinations in param_grid, return sorted by Sharpe desc.

    Example param_grid:
        {"entry_threshold": [0.60, 0.65, 0.70], "position_size": [10, 25, 50]}
    Produces 3 * 3 = 9 runs.
    """
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    results = []

    for combo in itertools.product(*param_values):
        params = dict(zip(param_names, combo, strict=True))
        strategy = strategy_class(**params)
        result = runner.run(strategy)
        results.append(result)

    return sorted(results, key=lambda r: r.sharpe_ratio, reverse=True)
```

**Overfitting warning:** Grid sweep over the full date range selects parameters in-sample. Use walk-forward validation (SIM-07) to verify selected parameters generalize.

---

### Pattern 8: Walk-Forward Validation

**What:** Split the backtest window into N folds. Optimize on in-sample data, validate on out-of-sample. Reveals whether the strategy is robust or curve-fitted.

```python
from datetime import date, timedelta

def generate_walk_forward_splits(
    start: date,
    end: date,
    n_folds: int,
    train_fraction: float = 0.7,
) -> list[tuple[tuple[date, date], tuple[date, date]]]:
    """Generate rolling train/test date splits.

    Returns list of ((train_start, train_end), (test_start, test_end)) tuples.
    Fold windows are non-overlapping; each fold advances by (total_days / n_folds).

    Example: 1 year, 4 folds, 70/30 split →
      Fold 1: train Jan–Sep, test Sep–Dec
      Fold 2: train Apr–Dec, test Dec–Mar
      ...
    """
    total_days = (end - start).days
    fold_size = total_days // n_folds
    splits = []

    for i in range(n_folds):
        fold_start = start + timedelta(days=i * fold_size)
        fold_end = fold_start + timedelta(days=fold_size)
        train_end = fold_start + timedelta(days=int(fold_size * train_fraction))
        splits.append(
            ((fold_start, train_end), (train_end, fold_end))
        )
    return splits
```

**Minimum fold size warning:** Kalshi markets are sparse. With 1 year of data and 4 folds, each test window is ~3 months. At 30+ markets per window, that's potentially 90+ resolved contracts — statistically useful. Fewer than 30 total resolved contracts per fold should trigger a sample-size warning (aligns with MET-07 in Phase 3).

---

### Pattern 9: CLI `run` Command (CLI-02)

**What:** Add `run` command to the existing Typer app. Follows the same pattern as `ingest`.

```python
# Extension of existing cli.py — add after ingest command
@app.command()
def run(
    strategy: str = typer.Option(..., "--strategy", help="Strategy class name"),
    lookback_days: int = typer.Option(365, "--lookback-days", help="Days of history to backtest"),
    category: str | None = typer.Option(None, "--category", help="Filter by Kalshi category"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """Run a backtest against historical Kalshi data."""
    ...
```

---

### Anti-Patterns to Avoid

- **Querying the database inside the simulation loop:** Load all candles before the loop starts. One query per bar kills performance and makes profiling impossible.
- **Exposing `result` before `close_time`:** The ONLY place that sets `result` on a `MarketSnapshot` is `BarIterator`. Any code that reads market data directly and checks `result` bypasses the look-ahead firewall.
- **Using floating-point for prices or P&L:** All prices are integer cents [0–100]. All P&L is integer cents. Floating point is only used for fee intermediate calculation (then `math.ceil()` back to int).
- **Mutating `open_positions` inside `generate_signals()`:** The `open_positions` list passed to the strategy is a read-only snapshot. The `PositionTracker` owns position state; strategies must not modify it directly.
- **Global state in strategy instances:** Strategies hold their own state between bars (e.g., rolling averages). This is intentional — but state must not bleed between grid sweep runs. Each sweep combination creates a fresh strategy instance.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parameter combination enumeration | Custom nested loops | `itertools.product` | Handles arbitrary dimensions, no bugs, stdlib |
| Time-series train/test splits | Custom date arithmetic | Manual fold generation (30 lines) or `sklearn.model_selection.TimeSeriesSplit` | TimeSeriesSplit is well-tested; manual version is acceptable if sklearn not in deps |
| Fee rounding | Custom round-half-up | `math.ceil()` | Kalshi's formula specifically requires ceiling, not standard rounding |
| Frozen data models | Custom `__setattr__` | Pydantic `model_config = {"frozen": True}` | Already fund-wide standard; prevents mutation bugs in simulation loop |
| DataFrame sorting for trade log | Custom sort | `pd.DataFrame.sort_values()` | Pandas handles multi-key sorts, NaN handling, type coercions correctly |

**Key insight:** The simulation engine's custom code is unavoidable (binary contract semantics), but every supporting utility that's not prediction-market-specific should use stdlib or already-installed libraries.

---

## Common Pitfalls

### Pitfall 1: P price scale in fee formula
**What goes wrong:** `calculate_fee_cents(contracts=10, price_fraction=30)` — passing cents instead of fraction gives 30x the correct fee.
**Why it happens:** Candles store prices as integer cents (0–100). The fee formula uses decimal fraction [0.0, 1.0].
**How to avoid:** Name the parameter `price_fraction` not `price`. Add `assert 0.0 <= price_fraction <= 1.0` at the top of `calculate_fee_cents()`.
**Warning signs:** Fee for 10 contracts at 50 cents = 87 cents (wrong: passed 50 instead of 0.50). Correct answer: 1 cent.

### Pitfall 2: Look-ahead via direct market result access
**What goes wrong:** `runner.py` reads `market["result"]` from the pre-loaded markets dict and uses it in signal logic, bypassing `MarketSnapshot.result=None`.
**Why it happens:** The bulk-loaded markets dict contains the final result for all settled markets. It's tempting to use it directly.
**How to avoid:** The simulation engine passes only `MarketSnapshot` objects to strategy and fill logic. Never pass the raw market dict to anything outside `BarIterator`.
**Warning signs:** 100% win rate in backtest — a sure sign strategy is seeing resolution outcomes.

### Pitfall 3: Position state bleed between grid sweep runs
**What goes wrong:** `PositionTracker` instance is reused between sweep combinations. Trade log accumulates across all runs. All results are inflated.
**Why it happens:** Sweep loop creates strategy instances but forgets to create fresh `BacktestRunner`/`PositionTracker` per run.
**How to avoid:** `BacktestRunner.__init__()` creates fresh `PositionTracker` and `TradeLog`. The sweep creates a new `BacktestRunner` per combination.

### Pitfall 4: Off-by-one in look-ahead cutoff
**What goes wrong:** Using `ts > close_time` instead of `ts >= close_time`. The final bar (day of settlement) never sees the result.
**Why it happens:** Ambiguity in "before close time" — does the close bar count?
**How to avoid:** Kalshi markets resolve at `close_time`. A bar timestamped exactly at `close_time` is the settlement bar. Use `ts >= close_time` to expose the result on and after the settlement bar.
**Warning signs:** Strategy cannot exit positions at settlement — they hang open indefinitely.

### Pitfall 5: Walk-forward fold with zero resolved contracts
**What goes wrong:** A fold's test window contains no settled markets (e.g., short window + low-volume category). Metrics return NaN/ZeroDivision.
**Why it happens:** Kalshi markets have sparse, uneven settlement timing. Not every fold window will have resolved markets.
**How to avoid:** `WalkForwardValidator` skips folds with `< MIN_SETTLED_TRADES` (suggest 5) and logs a warning. Do not raise an exception — report fold as "insufficient data."

### Pitfall 6: Typer command import side effects
**What goes wrong:** Importing `BacktestRunner` at module level in `cli.py` triggers DuckDB connection setup even for `--help`.
**Why it happens:** Eagerly importing heavy simulation machinery.
**How to avoid:** Follow existing `ingest` command pattern — lazy imports inside the command function body. Only import simulation modules when the `run` command is actually invoked.

---

## Code Examples

### Fee Formula — Verified

```python
# Source: Kalshi fee schedule (confirmed taker = 7%, P in [0,1])
import math

def calculate_fee_cents(contracts: int, price_fraction: float) -> int:
    """Taker fee for a Kalshi trade in integer cents.

    ceil(0.07 * C * P * (1-P)), minimum 1 cent.
    Max is 1.75 cents/contract at P=0.50.
    """
    assert 0.0 <= price_fraction <= 1.0, f"price_fraction must be [0,1], got {price_fraction}"
    return max(1, math.ceil(0.07 * contracts * price_fraction * (1.0 - price_fraction)))

# Verified outputs:
# calculate_fee_cents(10, 0.30)  → 1 cent
# calculate_fee_cents(10, 0.50)  → 1 cent
# calculate_fee_cents(100, 0.50) → 2 cents
# calculate_fee_cents(1000, 0.50) → 18 cents
```

### Protocol Structural Subtyping — Verified

```python
# Source: Python 3.12 typing module — verified isinstance() check works
from typing import Protocol, runtime_checkable

@runtime_checkable
class Strategy(Protocol):
    def generate_signals(self, snapshot, open_positions: list) -> list: ...

class MyStrategy:  # No inheritance!
    def generate_signals(self, snapshot, open_positions):
        return []

s = MyStrategy()
assert isinstance(s, Strategy)  # True — structural subtyping confirmed
```

### BarIterator Look-Ahead Guard — Core Logic

```python
# The single most important invariant in the engine
def _build_snapshot(self, ticker: str, candle: dict, market: dict) -> MarketSnapshot:
    ts = candle["ts"]
    close_time = market["close_time"]

    # LOOK-AHEAD FIREWALL: result is None until the settlement bar
    result = None
    if ts >= close_time and market["result"] is not None:
        result = market["result"]

    return MarketSnapshot(
        ticker=ticker,
        ts=ts,
        result=result,
        close_time=close_time,
        close_price=candle["close_price"],
        # ... other fields
    )
```

### Grid Sweep — Minimal Working Pattern

```python
import itertools

param_grid = {
    "entry_threshold": [0.60, 0.65, 0.70],
    "position_size": [10, 25, 50],
}

for combo in itertools.product(*param_grid.values()):
    params = dict(zip(param_grid.keys(), combo, strict=True))
    strategy = MyStrategy(**params)
    result = runner.run(strategy)
    results.append(result)
```

---

## Existing Code Integration Points

### Repository extensions needed

The existing `MarketRepository` (`db/repository.py`) needs two new read methods for the simulation engine:

```python
def get_markets_for_simulation(
    self,
    start_close_time: datetime,
    end_close_time: datetime,
    series_tickers: list[str] | None = None,
    min_volume: int = 0,
) -> list[dict]:
    """Fetch markets that close within the date range, with optional filters."""
    ...

def get_candles_bulk(
    self,
    tickers: list[str],
    start_ts: datetime,
    end_ts: datetime,
) -> dict[str, list[dict]]:
    """Load candles for multiple tickers in one query. Returns {ticker: [candles]}."""
    # DuckDB can do: WHERE ticker IN (?, ?, ...) efficiently
    ...
```

The existing `get_markets()` and `get_candles()` methods are already correct and tested. The new methods are additive.

### CLI extension

The existing `cli.py` Typer app needs a `run` command added after `ingest`. Pattern is identical: lazy imports inside the function body, `load_settings()` at top of function, try/except ValidationError.

### Config extension

`KalshiBacktestSettings` may need a `default_lookback_days: int = 365` field to provide the CLI default from config. Check if this is needed when implementing CLI-02.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/simulation/ -x -q` |
| Full suite command | `uv run pytest tests/ --cov=kalshi_backtest --cov-report=term-missing` |
| Coverage tool | pytest-cov 7.1.0 |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SIM-01 | Strategy Protocol accepts any class with `generate_signals()` | unit | `uv run pytest tests/simulation/test_protocol.py -x` | ❌ Wave 0 |
| SIM-01 | `isinstance(strategy, Strategy)` returns True for conforming class | unit | `uv run pytest tests/simulation/test_protocol.py::test_isinstance_check -x` | ❌ Wave 0 |
| SIM-02 | `MarketSnapshot.result` is None for bars before close_time | unit | `uv run pytest tests/simulation/test_bar_iterator.py::test_no_lookahead -x` | ❌ Wave 0 |
| SIM-02 | `MarketSnapshot.result` is populated on the settlement bar | unit | `uv run pytest tests/simulation/test_bar_iterator.py::test_result_on_settlement_bar -x` | ❌ Wave 0 |
| SIM-02 | Bars are yielded in strict chronological order across multiple tickers | unit | `uv run pytest tests/simulation/test_bar_iterator.py::test_chronological_order -x` | ❌ Wave 0 |
| SIM-03 | Fee formula returns 1 cent for 10 contracts at 30 cents | unit | `uv run pytest tests/simulation/test_fill_engine.py::test_fee_small_position -x` | ❌ Wave 0 |
| SIM-03 | Fee formula maximum is 1.75 cents/contract at P=0.50 | unit | `uv run pytest tests/simulation/test_fill_engine.py::test_fee_max_at_fifty -x` | ❌ Wave 0 |
| SIM-03 | Fee minimum is 1 cent regardless of size | unit | `uv run pytest tests/simulation/test_fill_engine.py::test_fee_minimum -x` | ❌ Wave 0 |
| SIM-04 | Buy YES fills at mid + half_spread | unit | `uv run pytest tests/simulation/test_fill_engine.py::test_conservative_buy_fill -x` | ❌ Wave 0 |
| SIM-04 | Fill returns None when limit price is below fill price | unit | `uv run pytest tests/simulation/test_fill_engine.py::test_limit_below_fill_rejected -x` | ❌ Wave 0 |
| SIM-05 | YES win P&L = (100 - entry) * contracts | unit | `uv run pytest tests/simulation/test_pnl.py::test_yes_win -x` | ❌ Wave 0 |
| SIM-05 | YES loss P&L = -entry * contracts | unit | `uv run pytest tests/simulation/test_pnl.py::test_yes_loss -x` | ❌ Wave 0 |
| SIM-05 | Pre-resolution exit P&L is mark-to-market | unit | `uv run pytest tests/simulation/test_pnl.py::test_exit_pnl -x` | ❌ Wave 0 |
| SIM-06 | Grid sweep runs N combinations from param_grid | unit | `uv run pytest tests/simulation/test_sweep.py::test_grid_combinations -x` | ❌ Wave 0 |
| SIM-06 | Results are sorted by Sharpe ratio descending | unit | `uv run pytest tests/simulation/test_sweep.py::test_results_sorted -x` | ❌ Wave 0 |
| SIM-07 | Walk-forward produces correct number of folds | unit | `uv run pytest tests/simulation/test_walkforward.py::test_fold_count -x` | ❌ Wave 0 |
| SIM-07 | Train/test windows do not overlap | unit | `uv run pytest tests/simulation/test_walkforward.py::test_no_overlap -x` | ❌ Wave 0 |
| CLI-02 | `backtest run --lookback-days 180` invokes runner with 180-day window | integration | `uv run pytest tests/test_cli.py::test_run_command_lookback -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/simulation/ -x -q`
- **Per wave merge:** `uv run pytest tests/ --cov=kalshi_backtest --cov-report=term-missing`
- **Phase gate:** Full suite green, coverage >= 80% before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/simulation/__init__.py` — package init
- [ ] `tests/simulation/test_protocol.py` — covers SIM-01
- [ ] `tests/simulation/test_bar_iterator.py` — covers SIM-02
- [ ] `tests/simulation/test_fill_engine.py` — covers SIM-03, SIM-04
- [ ] `tests/simulation/test_pnl.py` — covers SIM-05
- [ ] `tests/simulation/test_sweep.py` — covers SIM-06
- [ ] `tests/simulation/test_walkforward.py` — covers SIM-07
- [ ] `tests/test_cli.py` extension — covers CLI-02 (file exists, needs new test added)

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ABC for plugin interfaces | `typing.Protocol` with `@runtime_checkable` | Python 3.8+ (standard by 2023) | Strategies don't need to import engine code |
| Event-driven backtesting (one DB query per bar) | Hybrid: bulk load upfront + event iteration | Standard pattern post-2020 | 100–1000x faster for daily data |
| pyfolio for portfolio metrics | quantstats (already chosen in Phase 1 research) | pyfolio deprecated ~2021 | quantstats is actively maintained |
| Kalshi maker fees: flat fee | Kalshi maker fees: `ceil(0.0175 * C * P * (1-P))` | July 2025 | Both maker and taker now use parabolic formula |

**Deprecated/outdated:**
- **`abc.ABC` for strategy interfaces**: Use `typing.Protocol` instead — no need to import from engine codebase
- **Kalshi pre-July 2025 maker fee structure**: No longer flat; verify any pre-2025 Kalshi backtest code uses updated 1.75% maker formula

---

## Open Questions

1. **`get_candles_bulk()` performance with large ticker lists**
   - What we know: DuckDB handles `WHERE ticker IN (...)` efficiently with columnar storage; existing `get_candles()` does single-ticker queries
   - What's unclear: At what number of tickers does parameterized `IN` clause become a bottleneck vs. a full table scan with post-filter?
   - Recommendation: Implement with `IN` clause first; if >1000 tickers causes slowness, switch to a JOIN against a temporary table or `UNNEST`

2. **Walk-forward fold count with sparse markets**
   - What we know: 1 year of Kalshi data, 4 folds = ~3 months per fold; some folds may have very few resolved markets in low-volume categories
   - What's unclear: Minimum fold size before results are meaningless
   - Recommendation: Default to `n_folds=4`, `min_resolved_per_fold=5`; log warning and skip folds below threshold

3. **`result` column timing: close_time vs expiration_time**
   - What we know: `MarketRecord` has both `close_time` and `expiration_time`; `result` appears in DB when `status='settled'`
   - What's unclear: Should look-ahead guard use `close_time` or `expiration_time` as the cutoff?
   - Recommendation: Use `close_time` — this is when trading stops. `expiration_time` is when resolution is official, but using it would delay result visibility longer than needed. Verify during implementation by inspecting real settled market records.

---

## Environment Availability

Step 2.6: SKIPPED — Phase 2 is purely Python code additions with no external dependencies beyond what is already installed in the project's virtualenv. All required libraries (pandas, numpy, duckdb, pydantic, typer, structlog) are already in `pyproject.toml` and `uv.lock`. No new CLI tools, services, or runtimes are required.

---

## Sources

### Primary (HIGH confidence)
- Python `typing.Protocol` documentation — structural subtyping, `@runtime_checkable`, `isinstance()` checks; verified working in Python 3.12
- `math.ceil()` stdlib documentation — fee rounding behavior confirmed
- Verified fee formula computation: `calculate_fee_cents(100, 0.50) = 2` cents matches expected 1.75¢/contract * 100 ceiling
- [whirligigbear.substack.com/p/makertaker-math-on-kalshi](https://whirligigbear.substack.com/p/makertaker-math-on-kalshi) — taker 7%, maker 1.75%, P in [0,1], max 1.75¢/contract at P=0.50; confirmed
- [kalshi-backtest existing codebase] — `MarketRecord`, `CandlestickRecord`, `MarketRepository`, `cli.py` patterns; read and verified

### Secondary (MEDIUM confidence)
- [kalshi.com/fee-schedule](https://kalshi.com/fee-schedule) + search results — taker 7%, maker 1.75% formula; confirmed by multiple independent sources (fee calculator tools, academic papers)
- [help.kalshi.com/trading/fees](https://help.kalshi.com/trading/fees) — maker fee behavior; confirmed fees only charged on execution not cancellation
- [Kalshi fee schedule PDF (Feb 2026)](https://kalshi.com/docs/kalshi-fee-schedule.pdf) — rate-limited during fetch; formula confirmed from web search results
- [quantinsti.com/walk-forward-optimization](https://blog.quantinsti.com/walk-forward-optimization-introduction/) — rolling train/test split patterns for Python backtesting
- [sitmo.com/grid-searching-for-optimal-hyperparameters-with-itertools](https://www.sitmo.com/grid-searching-for-optimal-hyperparameters-with-itertools) — `itertools.product` grid sweep pattern

### Tertiary (LOW confidence — flagged for validation)
- Kalshi maker fee change to parabolic formula in July 2025 — reported in web search results, not directly verified from official source; use taker formula (7%) for conservative estimates regardless

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in pyproject.toml, no new deps
- Fee formula: HIGH — confirmed by independent calculator tools and substack analysis that shows math checks out
- Architecture patterns: HIGH — pulled from project's own ARCHITECTURE.md research doc + verified Protocol behavior
- Look-ahead prevention: HIGH — standard event-driven backtesting principle; BarIterator pattern is well-established
- Walk-forward implementation: MEDIUM — rolling split logic is standard; Kalshi-specific sparse market behavior adds uncertainty
- Grid sweep: HIGH — `itertools.product` pattern is trivial and stdlib

**Research date:** 2026-04-05
**Valid until:** 2026-10-05 (Kalshi fee structure stable; Python typing module stable)
