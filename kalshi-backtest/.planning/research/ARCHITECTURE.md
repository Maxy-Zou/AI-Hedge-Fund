# Architecture Patterns

**Domain:** Prediction market backtesting engine (Kalshi binary event contracts)
**Researched:** 2026-04-04

---

## Recommended Architecture

A layered pipeline architecture with five discrete layers. Data flows strictly downward: ingestion feeds storage, storage feeds the simulation engine, the engine emits events to the metrics layer, and the reporting layer consumes metrics to produce output. The Strategy plugin sits alongside the simulation engine, receiving market snapshots and emitting signals back in.

```
┌─────────────────────────────────────────────────────────┐
│                    CLI / Entrypoint                     │
│         typer commands: ingest | run | compare          │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│               Ingestion Layer                           │
│  KalshiAPIClient → EventFetcher → CandlestickFetcher   │
│  Handles: live/historical tier split, rate limits,      │
│           pagination, append-only writes                │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│               Storage Layer                             │
│  SQLAlchemy ORM + SQLite (dev) / PostgreSQL (prod)      │
│  Tables: Event, Market, MarketCandle, Resolution        │
│  Invariant: all writes are append-only                  │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│          Simulation Engine                              │
│  BacktestRunner → BarIterator → OrderBook (simulated)  │
│           │                                             │
│           ▼                                             │
│    Strategy (Protocol)                                  │
│    generate_signals(snapshot) → Signal list             │
│    Strategies: InsiderTrackerAdapter, future plugins    │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│           Metrics Layer                                 │
│  TradeLog → PortfolioSimulator → MetricsCalculator      │
│  Outputs: equity curve, P&L, Sharpe, drawdown,         │
│           win rate, avg trade, per-contract breakdown   │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│           Reporting Layer                               │
│  DashboardBuilder (Plotly) → HTML/PNG export            │
│  ComparisonReport → side-by-side strategy table         │
└─────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

### 1. CLI / Entrypoint

**Responsibility:** Parse commands, load config, dispatch to the correct layer. No business logic lives here.

**Communicates with:** Ingestion layer (ingest commands), Simulation engine (run commands), Reporting layer (report commands).

**Key commands:**
- `backtest ingest` — pull and store historical Kalshi data
- `backtest run --strategy InsiderTracker --start 2024-01-01` — run a backtest
- `backtest compare --strategies A,B` — side-by-side comparison
- `backtest report` — regenerate dashboard from stored results

---

### 2. Ingestion Layer

**Responsibility:** Fetch Kalshi data, normalize it, persist it with append-only semantics. Owns all knowledge of Kalshi API quirks.

**Communicates with:** Kalshi REST API (outbound), Storage layer (writes only).

**Key sub-components:**

| Sub-component | Role |
|---------------|------|
| `KalshiAPIClient` | HTTP client with auth, retry (tenacity), rate-limit compliance |
| `HistoricalCutoffResolver` | Calls `GET /historical/cutoff` to determine live vs historical tier boundary |
| `EventFetcher` | Pages through `GET /events` and `GET /historical/events` |
| `MarketFetcher` | Fetches markets per event; maps `event_ticker` → `ticker` |
| `CandlestickFetcher` | Fetches 1-day candles per market; batches up to 10,000 candles |
| `ResolutionFetcher` | Reads `result` field (`yes`/`no`/`null`) from settled markets |

**Critical invariant:** Kalshi partitions data into a live tier and a historical tier at a cutoff timestamp. The ingestion layer must query the cutoff at runtime and route requests to the correct endpoint set. This is not optional — the live endpoints return 404 for data that has crossed the cutoff.

---

### 3. Storage Layer

**Responsibility:** Persist normalized Kalshi data with append-only semantics. Provide efficient read access for the simulation engine.

**Communicates with:** Ingestion layer (writes), Simulation engine (reads).

**Schema (Kalshi-specific):**

```
Event
  event_ticker      TEXT PK
  title             TEXT
  category          TEXT        -- politics, weather, economics, crypto, sports
  mutually_exclusive BOOLEAN
  created_time      TIMESTAMP
  ingested_at       TIMESTAMP   -- when we collected this record

Market
  ticker            TEXT PK
  event_ticker      TEXT FK → Event
  subtitle          TEXT        -- "Yes" outcome description
  open_time         TIMESTAMP
  close_time        TIMESTAMP
  expiration_time   TIMESTAMP
  status            TEXT        -- open / closed / settled
  result            TEXT NULL   -- 'yes' | 'no' | NULL (unsettled)
  ingested_at       TIMESTAMP

MarketCandle
  id                BIGINT PK (autoincrement)
  ticker            TEXT FK → Market
  ts                TIMESTAMP   -- candle start (1-day resolution)
  open_yes_price    NUMERIC(5,2) -- cents (0-100)
  high_yes_price    NUMERIC(5,2)
  low_yes_price     NUMERIC(5,2)
  close_yes_price   NUMERIC(5,2)
  volume            INTEGER
  ingested_at       TIMESTAMP
  UNIQUE (ticker, ts)           -- idempotent upsert key
```

**Why cents not dollars:** Kalshi internally prices in cents (0–100). Storing as cents preserves precision and avoids float errors. The API returns `yes_bid_dollars` but the canonical internal representation should be integer cents.

**Append-only enforcement:** `MarketCandle` rows are never updated. New ingestion runs skip rows where `(ticker, ts)` already exists. `Market` metadata (status, result) is the exception — these are overwritten on re-ingestion because resolution is a state transition, not a new observation.

---

### 4. Simulation Engine

**Responsibility:** Replay stored market data bar-by-bar, feed each snapshot to the active Strategy, convert signals to simulated fills, and emit trade events to the Metrics layer.

**Communicates with:** Storage layer (read), Strategy (bidirectional — sends snapshot, receives signals), Metrics layer (emits fills).

**Key sub-components:**

| Sub-component | Role |
|---------------|------|
| `BacktestRunner` | Orchestrates a full backtest run for one strategy over a date range |
| `MarketUniverse` | Loads the set of markets in scope (by category, date range, min volume) |
| `BarIterator` | Emits `MarketSnapshot` objects in chronological order across all markets |
| `SimulatedOrderBook` | Converts a signal's desired price into a fill price using the candle's bid/ask spread |
| `PositionTracker` | Maintains open/closed positions across all markets for the run |
| `FillEngine` | Records fills, validates that a market is still open, rejects signals on settled markets |

**MarketSnapshot (the bridge between storage and strategy):**

```python
@dataclass(frozen=True)
class MarketSnapshot:
    ticker: str
    event_ticker: str
    ts: datetime
    yes_price: Decimal       # close price of current candle (0-100 cents)
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    volume: int
    days_to_expiry: int
    result: str | None       # None if still open, 'yes'/'no' after settlement
    category: str
    subtitle: str            # human-readable outcome description
```

**Strategy Protocol — the plugin interface:**

```python
from typing import Protocol
from dataclasses import dataclass

@dataclass(frozen=True)
class Signal:
    ticker: str
    direction: str           # 'yes' | 'no'
    size: Decimal            # position size in dollars
    limit_price: Decimal     # max price willing to pay (cents)
    reason: str              # human-readable label for trade log

class Strategy(Protocol):
    """
    Implement this protocol to plug a strategy into the backtest engine.
    generate_signals() is called once per bar per market with the current snapshot.
    Return [] to pass. Return one or more Signals to take a position.
    """
    def generate_signals(
        self,
        snapshot: MarketSnapshot,
        open_positions: list[Position],
    ) -> list[Signal]: ...
```

**Why Protocol over ABC:** Python's `typing.Protocol` enables structural subtyping — any class with the right method signature satisfies the interface without explicit inheritance. This is strictly better for plugins because third-party strategies don't need to import from this engine's codebase at all.

**Simulation loop:**

```
for each trading day (chronological):
    for each market in universe:
        snapshot = build_snapshot(market, day)
        signals = strategy.generate_signals(snapshot, open_positions)
        for signal in signals:
            if market_is_open(snapshot) and no_existing_position(snapshot.ticker):
                fill = simulate_fill(signal, snapshot)
                position_tracker.open(fill)
        
        # Check for settled markets and close positions
        if snapshot.result is not None:
            settled_positions = position_tracker.get_open(snapshot.ticker)
            for pos in settled_positions:
                pnl = calculate_binary_pnl(pos, snapshot.result)
                position_tracker.close(pos, pnl)
                emit FillEvent(pos, pnl)
```

**Binary P&L calculation:**

Unlike stocks, Kalshi contracts always settle at 100 cents (win) or 0 cents (loss). This simplifies P&L:

```
If bought YES at 30 cents:
  Win (result = 'yes'):  P&L = (100 - 30) * contracts = +70 cents per contract
  Loss (result = 'no'):  P&L = (0 - 30) * contracts   = -30 cents per contract

If bought NO at 70 cents:
  Win (result = 'no'):   P&L = (100 - 70) * contracts = +30 cents per contract
  Loss (result = 'yes'): P&L = (0 - 70) * contracts   = -70 cents per contract
```

There is no partial exit mid-contract in v1 — positions are held until resolution. This is intentional: it matches Kalshi Insider Tracker's signal style (binary conviction bets) and simplifies the simulation.

---

### 5. Metrics Layer

**Responsibility:** Accumulate trade events from the simulation engine and compute strategy performance statistics.

**Communicates with:** Simulation engine (receives FillEvents), Reporting layer (sends MetricsResult).

**Key computations:**

| Metric | Formula / Notes |
|--------|-----------------|
| Total return | Sum of all P&L / initial capital |
| Win rate | Wins / total settled trades |
| Avg win / avg loss | Mean P&L of winning / losing trades |
| Profit factor | Sum of wins / abs(sum of losses) |
| Sharpe ratio | (Annualized return - risk-free rate) / annualized daily P&L std |
| Max drawdown | Max peak-to-trough drop in equity curve |
| Calmar ratio | CAGR / max drawdown |
| Per-category breakdown | Above metrics grouped by `category` (politics, crypto, etc.) |
| Trade log | Every entry/exit with ticker, direction, entry price, exit price, P&L, result |

**Equity curve construction:** Accumulate daily P&L from settled positions. Days with no settlements contribute 0. This creates a step-function equity curve that is appropriate for binary event strategies (not continuous mark-to-market).

**Daily P&L note:** Because positions only resolve on settlement, there is no intermediate mark-to-market P&L. The equity curve advances only when contracts settle. This is correct for binary event contracts — unrealized P&L for open positions is not reported.

---

### 6. Reporting Layer

**Responsibility:** Transform MetricsResult into human-readable output. Has no business logic — it only formats and renders.

**Communicates with:** Metrics layer (reads MetricsResult), filesystem (writes HTML/PNG).

**Outputs:**

| Output | Format | Contents |
|--------|--------|----------|
| Equity curve chart | Plotly HTML / PNG | Cumulative P&L over time |
| Trade log table | CSV + HTML table | Every fill with details |
| Summary metrics card | CLI table (rich) + HTML | All headline numbers |
| Category breakdown | Bar chart per category | Sharpe, win rate per category |
| Strategy comparison | HTML table | Multi-strategy side-by-side |

**Dashboard is HTML-first:** A single `dashboard.html` file with embedded Plotly charts is the primary output. PNG screenshots are secondary (for investor decks). No web server required — open in browser locally.

---

## Data Flow Summary

```
Kalshi REST API
    │
    ▼  (KalshiAPIClient — HTTP, auth, retry)
Ingestion Layer
    │
    ▼  (SQLAlchemy ORM — append-only writes)
Storage Layer (SQLite / PostgreSQL)
    │
    ▼  (MarketUniverse + BarIterator — read queries)
Simulation Engine
    │ ◄──── Strategy.generate_signals(MarketSnapshot) ────►
    │
    ▼  (FillEvent stream)
Metrics Layer
    │
    ▼  (MetricsResult)
Reporting Layer
    │
    ▼
dashboard.html / equity_curve.png / trade_log.csv
```

---

## Patterns to Follow

### Pattern 1: Structural Typing for Strategy Plugins

**What:** Define Strategy as a `typing.Protocol`, not an ABC. Any class with `generate_signals()` satisfies it automatically.

**When:** Always — for the Strategy interface and any future plugin interfaces.

**Why:** Third-party strategies can be written in isolation without importing from this codebase. Enables duck-typed testing with simple mock classes.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Strategy(Protocol):
    def generate_signals(
        self,
        snapshot: MarketSnapshot,
        open_positions: list[Position],
    ) -> list[Signal]: ...
```

### Pattern 2: Frozen Dataclasses for Immutable Data Objects

**What:** All objects that cross component boundaries are `@dataclass(frozen=True)` or Pydantic models.

**When:** MarketSnapshot, Signal, Fill, Position, MetricsResult — every inter-layer contract.

**Why:** Prevents subtle mutation bugs in the simulation loop. Follows fund-wide immutability convention.

### Pattern 3: Vectorized Storage Reads, Event-Driven Simulation

**What:** Load all required market data for a backtest run in bulk at the start (vectorized), then iterate chronologically in the simulation loop (event-driven).

**When:** Always — this is the recommended hybrid approach.

**Why:** Pure event-driven (one DB query per bar) is too slow for a year of daily data across thousands of markets. Pure vectorized (process all signals at once) creates lookahead bias risk. The hybrid loads data once, then processes it sequentially to prevent lookahead.

### Pattern 4: Repository Pattern for Storage Access

**What:** All storage access goes through a `MarketRepository` class with typed methods. The simulation engine never writes raw SQL or ORM expressions.

**When:** All database reads in the simulation engine.

**Why:** Enables swapping SQLite (dev) for PostgreSQL (prod) without touching simulation logic. Simplifies testing with in-memory substitutes.

```python
class MarketRepository:
    def get_candles(
        self,
        tickers: list[str],
        start: date,
        end: date,
    ) -> dict[str, list[MarketCandle]]: ...

    def get_markets_by_category(
        self,
        category: str | None,
        min_volume: int,
    ) -> list[Market]: ...
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Lookahead Bias via Settlement Result

**What goes wrong:** The simulation accesses `Market.result` (the resolution outcome) at bar time before settlement.

**Why bad:** The strategy would be using information that wasn't available when the signal was generated — all signals would be perfectly calibrated in backtest but fail live.

**Prevention:** `MarketSnapshot.result` must be `None` for any bar before the market's `close_time`. Only set `result` once `ts >= close_time` and the market is settled. The `BarIterator` is responsible for enforcing this.

### Anti-Pattern 2: Mutating Historical Candle Data

**What goes wrong:** Re-ingestion overwrites existing `MarketCandle` rows with "corrected" prices.

**Why bad:** Destroys the historical record. Makes it impossible to know what data was used for past backtests.

**Prevention:** `MarketCandle` rows are insert-only. The `UNIQUE (ticker, ts)` constraint on the table enforces this — re-ingestion simply skips rows that already exist.

### Anti-Pattern 3: Mixing Ingestion and Simulation in One Pass

**What goes wrong:** Fetching from the Kalshi API during the simulation loop ("online" simulation).

**Why bad:** Introduces network latency into the backtest loop, makes runs non-reproducible, and risks hitting rate limits.

**Prevention:** Ingestion is a separate CLI command that runs before backtesting. The simulation engine only reads from local storage.

### Anti-Pattern 4: One-Shot Strategy Execution

**What goes wrong:** Strategy receives the entire market history at once and computes signals in one vectorized pass.

**Why bad:** Creates subtle lookahead bias — the strategy can accidentally condition on future prices even with careful coding. Very hard to audit.

**Prevention:** Strategy receives one `MarketSnapshot` at a time with no knowledge of future bars. All state the strategy needs to maintain between bars must be held in the Strategy instance's own attributes.

---

## Suggested Build Order

This order respects dependency direction: each layer can be built and tested before the layer above it depends on it.

| Step | Component | Why This Order |
|------|-----------|----------------|
| 1 | Storage Layer (schema + models) | Everything depends on storage. Define the data contracts first. |
| 2 | Ingestion Layer (API client + fetchers) | Needs storage to write to. Produces the dataset all other layers consume. |
| 3 | Strategy Protocol + MarketSnapshot | Define the interface before writing either side of it. |
| 4 | Simulation Engine (core loop, no strategy) | Reads from storage. Strategy is injected — can test with a stub strategy. |
| 5 | InsiderTracker adapter (first Strategy impl) | First real consumer of the simulation engine. Validates the protocol design. |
| 6 | Metrics Layer | Consumes fills emitted by simulation engine. |
| 7 | Reporting Layer (dashboard) | Consumes metrics. Can be built independently once MetricsResult schema is fixed. |
| 8 | Strategy Comparison | Requires simulation engine + metrics layer to be stable first. |
| 9 | Parameter optimization sweep | Extension of backtest runner — add after single-run path is proven. |

**Critical path:** Storage → Ingestion → Simulation core → Metrics. These four must be sequential. Reporting and comparison can be developed in parallel with later simulation work once the MetricsResult contract is defined.

---

## Kalshi-Specific Data Model Notes

### Event / Market / Contract Hierarchy

```
Event (event_ticker: "KXBTCD-24NOV06")
  └── Market (ticker: "KXBTCD-24NOV06-T65999")   -- "BTC above $66k by Nov 6"
        └── MarketCandle (daily OHLCV for yes-price)
        └── result: "yes" | "no" | null
```

A single Event can contain multiple Markets (scalar outcomes at different thresholds, or multiple candidates). Each Market is its own binary contract. Strategy signals target a specific `ticker` (Market), not an `event_ticker` (Event).

### Pricing Convention

Kalshi prices the YES side. The NO side is always `100 - yes_price`. Storing only the YES price is sufficient — NO price is derived. All prices are in cents (0–100), representing probability in percent.

### Live vs. Historical API Tier

The Kalshi API partitions data at a rolling cutoff timestamp. Markets settled before the cutoff are only queryable via `GET /historical/markets`. The ingestion layer must resolve this cutoff dynamically at runtime — hardcoding a date will break as the cutoff advances.

### Resolution Lag

Markets may remain in `status=closed` for hours or days before `result` is populated. The ingestion layer must handle markets with `result=null` on closed contracts and re-fetch them on subsequent runs until resolution appears.

---

## Scalability Considerations

This is a local CLI tool for a single user running ~1 year of daily data. Scale targets are low.

| Concern | At v1 scope (1 year, all categories) | If scope grows |
|---------|--------------------------------------|----------------|
| Storage volume | ~50K–500K candles — SQLite is fine | PostgreSQL already in fund stack |
| Ingestion time | Kalshi rate limits are the bottleneck, not compute | Parallel fetching by event category |
| Simulation speed | Daily bars over 1 year — vectorized data load makes this fast | Vectorized signal computation if needed |
| Reporting | Single HTML file, local browser — no server needed | Export to S3 or shared drive if multi-user |

---

## Sources

- [Kalshi API: Historical Data](https://docs.kalshi.com/getting_started/historical_data) — live/historical tier split, cutoff endpoint — MEDIUM confidence (verified pattern from API changelog)
- [Kalshi API: Get Market Candlesticks](https://docs.kalshi.com/api-reference/market/get-market-candlesticks) — candlestick schema, 1/60/1440 minute periods — MEDIUM confidence
- [Kalshi API: Get Market](https://docs.kalshi.com/api-reference/market/get-market) — market schema fields including result, status, yes/no pricing — MEDIUM confidence
- [evan-kolberg/prediction-market-backtesting](https://github.com/evan-kolberg/prediction-market-backtesting) — NautilusTrader fork with Kalshi adapter — LOW confidence (community project, unverified internals)
- [braedonsaunders/homerun](https://github.com/braedonsaunders/homerun) — open-source Kalshi/Polymarket platform with strategy protocol, event dispatcher, backtesting — LOW confidence (implementation details not fully verified)
- [Event-Driven Backtesting with Python (QuantStart)](https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-I/) — ABC/Protocol patterns for strategy interface — HIGH confidence (standard pattern, well-documented)
- [Vectorized vs Event-Driven Backtesting (IBKR)](https://www.interactivebrokers.com/campus/ibkr-quant-news/a-practical-breakdown-of-vector-based-vs-event-based-backtesting/) — hybrid approach rationale — HIGH confidence
- [0xrsydn/polymarket-crypto-toolkit](https://github.com/0xrsydn/polymarket-crypto-toolkit) — Protocol-based strategy plugin design — MEDIUM confidence
