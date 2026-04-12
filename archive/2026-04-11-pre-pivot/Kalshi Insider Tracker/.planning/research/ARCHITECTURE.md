# Architecture Patterns

**Project:** Kalshi Insider Tracker
**Researched:** 2026-04-02
**Confidence:** MEDIUM — core patterns are well-established; Kalshi-specific API surface derived from known v2 REST API structure and project constraints

---

## Recommended Architecture

### Overview

A single-process Python daemon built around a synchronous polling loop. The process has six internal layers that form a strict dependency hierarchy — upper layers call downward, never upward. There is no message queue, no microservices, and no async I/O for v1; the 5-10 second poll interval and single-account constraint make this unnecessary complexity.

```
┌─────────────────────────────────────────────────┐
│                  CLI / Entry Point               │
│          (start daemon, run backfill)            │
└───────────────────┬─────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────┐
│               Polling Orchestrator               │
│   (tick loop, coordinates all layers per tick)  │
└──┬──────────┬──────────┬──────────┬─────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Ingest│ │Signal  │ │Trade   │ │Risk    │
│Layer │ │Engine  │ │Executor│ │Guard   │
└──┬───┘ └───┬────┘ └───┬────┘ └───┬────┘
   │         │          │          │
   └────┬────┘          └────┬─────┘
        │                   │
        ▼                   ▼
   ┌─────────┐        ┌──────────┐
   │Persist- │        │ Kalshi   │
   │ence     │        │ API      │
   │(SQLite) │        │(orders)  │
   └─────────┘        └──────────┘
        │
        ▼
   ┌─────────┐
   │Dashboard│
   │(Streamlit│
   └─────────┘
```

---

## Component Boundaries

| Component | Responsibility | Inputs | Outputs | Communicates With |
|-----------|---------------|--------|---------|-------------------|
| **CLI / Entry Point** | Start daemon, trigger one-off commands (historical backfill, position query) | CLI args | Process lifecycle | Polling Orchestrator |
| **Polling Orchestrator** | Tick loop every 5-10s; sequences all per-tick work; no business logic | Tick timer | Ordered calls to each layer | All layers |
| **Ingest Layer** | Call Kalshi REST API; normalize responses into typed Python dataclasses; cache last N snapshots in memory | Kalshi API responses | `MarketSnapshot`, `TradeEvent` objects | Kalshi API (out), Signal Engine + Persistence (in) |
| **Signal Engine** | Compute rolling baselines; evaluate four anomaly detectors; emit scored `Signal` objects when thresholds exceeded | `MarketSnapshot`, `TradeEvent`, historical baselines | `Signal` objects with type, confidence, market_id | Ingest Layer (reads), Trade Executor + Persistence (writes) |
| **Risk Guard** | Enforce hard position limits; check per-trade cap ($50) and total exposure cap ($500); block execution if limits breached | `Signal` + current portfolio state | `approved: bool`, adjusted position size | Signal Engine (reads signal), Trade Executor (gates execution) |
| **Trade Executor** | Place market orders on Kalshi; record outcome; never executes without Risk Guard approval | Approved `Signal` + order params | `OrderResult` | Kalshi API (out), Risk Guard (in), Persistence (writes) |
| **Persistence Layer** | SQLite database; write market snapshots, signals, orders, P&L; read baselines and positions | Domain objects from all layers | SQL rows; reads for baseline queries | All internal layers |
| **Dashboard** | Streamlit read-only view; queries DB directly; never writes | SQLite reads | HTML/browser UI | Persistence Layer only |

---

## Data Flow

### Per-Tick Flow (every 5-10 seconds)

```
1. Orchestrator fires tick
   │
2. Ingest Layer calls Kalshi REST API
   ├── GET /markets?category=politics  → active market list
   ├── GET /markets/{ticker}/orderbook → bid/ask depth
   └── GET /markets/{ticker}/trades    → recent trade history
   │
3. Ingest Layer emits: List[MarketSnapshot], List[TradeEvent]
   ├── Persists raw snapshots to DB (time-series table)
   └── Passes to Signal Engine
   │
4. Signal Engine evaluates each market:
   ├── VolumeDetector:  current_volume vs. rolling_30min_baseline
   ├── PriceDetector:   delta from open / volatility-normalized move
   ├── WinStreakDetector: per-account win rate on thin markets (DB query)
   └── TimingDetector:  trade cluster density in narrow pre-resolution windows
   │
5. Signal Engine emits: List[Signal] (may be empty most ticks)
   └── Persists each Signal to DB regardless of execution decision
   │
6. For each Signal:
   ├── Risk Guard checks: per_trade_limit, total_exposure_limit, duplicate_guard
   └── If approved → Trade Executor places order via Kalshi REST API
       └── Persists OrderResult to DB
   │
7. Dashboard queries DB independently (any time, not on tick schedule)
```

### Baseline Computation Flow

Baselines are not recomputed every tick — that would be expensive. Instead:

```
On startup (and every 30 minutes):
  Persistence Layer → query last 24h of MarketSnapshot rows
  Signal Engine → compute rolling averages, store in memory as baseline dict
  { market_id: BaselineStats(avg_volume, stddev_volume, ...) }
```

---

## Patterns to Follow

### Pattern 1: Typed Domain Objects at Every Layer Boundary

Pass typed Pydantic (frozen) or `@dataclass(frozen=True)` objects between layers. Never pass raw dicts from API responses deeper than the Ingest Layer.

```python
@dataclass(frozen=True)
class MarketSnapshot:
    market_id: str
    ticker: str
    yes_bid: int        # cents
    yes_ask: int        # cents
    volume_24h: int     # number of contracts
    open_interest: int
    captured_at: datetime

@dataclass(frozen=True)
class Signal:
    signal_type: SignalType   # VOLUME_SPIKE | PRICE_MOVE | WIN_STREAK | TIMING_CLUSTER
    market_id: str
    confidence: float         # 0.0 - 1.0
    direction: str            # "yes" | "no"
    detected_at: datetime
    metadata: dict            # signal-type-specific evidence
```

### Pattern 2: Risk Guard as a Hard Gate, Not Configuration

The Risk Guard must be a dedicated module that cannot be bypassed by the Trade Executor. The Executor only calls `risk_guard.approve(signal, portfolio_state)` and proceeds only on `True`. Limits are compiled-in constants, not config values that can be overridden at runtime.

```python
# Hard limits — not in config, not in .env
MAX_PER_TRADE_CENTS = 5_000     # $50
MAX_TOTAL_EXPOSURE_CENTS = 50_000  # $500

def approve(signal: Signal, portfolio: PortfolioState) -> ApprovalResult:
    if portfolio.total_exposure_cents + MAX_PER_TRADE_CENTS > MAX_TOTAL_EXPOSURE_CENTS:
        return ApprovalResult(approved=False, reason="total_exposure_cap")
    ...
```

### Pattern 3: Append-Only Persistence for All Signal and Trade Data

Every signal detected and every order placed is written as a new row. Nothing is updated or deleted. This creates an immutable audit trail and enables post-hoc signal tuning without data loss.

### Pattern 4: In-Memory Sliding Window for Baselines

Do not query the DB on every tick for baseline stats. Maintain a short in-memory rolling window (last N snapshots) per market. Refresh from DB on startup and every 30 minutes to catch market regime changes.

### Pattern 5: Single Thread, Sequential Execution

All six components run in the same thread, sequenced by the Orchestrator. There are no background threads, no async tasks, and no multiprocessing for v1. This eliminates concurrency bugs — the most common failure mode in trading systems. The 5-10 second poll interval is generous enough that synchronous execution completes well within budget.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Calling Trade Executor Directly from Signal Engine

**What:** Signal Engine detects anomaly → immediately fires trade order
**Why bad:** Bypasses Risk Guard. Any bug in Signal Engine logic can cause runaway position buildup.
**Instead:** Signal Engine → emit Signal → Orchestrator routes through Risk Guard → Risk Guard gates → Trade Executor

### Anti-Pattern 2: Mutable Global State for Portfolio Position

**What:** A global variable `current_exposure` incremented/decremented across ticks
**Why bad:** Off-by-one bugs on startup, no audit trail, race condition risk if threading added later
**Instead:** Derive current exposure by querying the orders table on every Risk Guard check. DB is the single source of truth.

### Anti-Pattern 3: Parsing API Responses Deep in Business Logic

**What:** Signal Engine receives raw `dict` from Kalshi API and calls `data["markets"][0]["yes_price"]`
**Why bad:** API shape changes break the signal logic; hard to test; no validation
**Instead:** Ingest Layer owns all API parsing and emits only typed dataclasses. Signal Engine never sees raw dicts.

### Anti-Pattern 4: Dashboard Writing to the Database

**What:** Dashboard has a "force close position" button that writes directly to the orders table
**Why bad:** Bypasses Risk Guard and Trade Executor; inconsistent state
**Instead:** Dashboard is strictly read-only for v1. Any action capability must be routed through the CLI or Orchestrator.

### Anti-Pattern 5: Storing Baselines in Config Files

**What:** Hardcoded volume thresholds like `volume_spike_threshold = 3.0` in `config.yaml`
**Why bad:** Different markets have wildly different liquidity profiles; static thresholds produce many false positives on thin markets and miss spikes on liquid ones
**Instead:** Per-market rolling baselines computed dynamically from collected historical data. Config stores the Z-score multiplier, not the raw threshold.

---

## Component Build Order

Build order follows the strict dependency hierarchy — nothing can be tested without its dependencies.

```
Phase 1: Foundation
  └── Persistence Layer (SQLite schema, ORM models)
      └── No dependencies; everything else writes to DB

Phase 2: Data Collection
  └── Ingest Layer (Kalshi API client, normalization, snapshot writes)
      └── Depends on: Persistence Layer

Phase 3: Signal Detection
  └── Signal Engine (all four detectors, baseline computation)
      └── Depends on: Ingest Layer (MarketSnapshot, TradeEvent types)
      └── Depends on: Persistence Layer (baseline queries, signal writes)

Phase 4: Execution
  └── Risk Guard (exposure queries, hard limits)
      └── Trade Executor (Kalshi order API, order writes)
      └── Depends on: Signal Engine (Signal type), Persistence Layer

Phase 5: Orchestration
  └── Polling Orchestrator (tick loop, sequences phases 2-4)
      └── Depends on: all layers
  └── CLI / Entry Point
      └── Depends on: Orchestrator

Phase 6: Observability
  └── Dashboard (Streamlit, read-only DB queries)
      └── Depends on: Persistence Layer only
      └── Can be built/tested independently after Phase 1
```

Implication: The Dashboard can be developed in parallel with Phases 3-5, as it only requires the DB schema from Phase 1.

---

## Scalability Considerations

This system is explicitly scoped for single-account, single-market-category, 5-10 second polling. Scalability is not a current concern, but known extension points are:

| Concern | At current scale (v1) | If extended later |
|---------|----------------------|-------------------|
| Poll interval | 5-10s, synchronous | Switch to Kalshi WebSocket if sub-second needed |
| Market coverage | Politics/policy only | Add category filters in Ingest Layer config |
| Multi-account | Not needed | Trade Executor would need account routing layer |
| Signal throughput | In-memory baselines per market | Redis or time-series DB if 1000+ markets |
| Persistence | SQLite (single-file, no network) | PostgreSQL if multi-process or remote dashboard |

SQLite is recommended over PostgreSQL for v1 because: single process, no network overhead, zero operational burden, trivially portable. Migration to PostgreSQL is a one-layer change (Persistence Layer only) if needed.

---

## Key Kalshi API Surface (REST v2)

**Confidence: MEDIUM** — based on publicly known Kalshi API v2 structure as of knowledge cutoff (August 2025). Verify against official docs before implementation.

| Purpose | Method | Endpoint |
|---------|--------|----------|
| List active markets by category | GET | `/trade-api/v2/markets?category=politics&status=open` |
| Market orderbook snapshot | GET | `/trade-api/v2/markets/{ticker}/orderbook` |
| Recent trades for a market | GET | `/trade-api/v2/markets/{ticker}/trades` |
| Place an order | POST | `/trade-api/v2/portfolio/orders` |
| Get current positions | GET | `/trade-api/v2/portfolio/positions` |
| Get account balance | GET | `/trade-api/v2/portfolio/balance` |

Authentication: API key in `Authorization: Bearer {token}` header.
Rate limits: Not officially published as of research date; implement exponential backoff and stay under 60 requests/minute as a conservative starting point.

---

## Sources

- Kalshi API v2 REST structure: MEDIUM confidence (training data, August 2025 cutoff — verify at https://trading.kalshi.com/trade-api/v2/docs before implementation)
- Polling loop / append-only persistence patterns: HIGH confidence (standard financial data system patterns, independent of Kalshi)
- Risk Guard as hard gate pattern: HIGH confidence (established algorithmic trading risk management pattern)
- SQLite-first recommendation: HIGH confidence (well-validated for single-process, low-throughput use cases)
- In-memory rolling baseline pattern: HIGH confidence (standard streaming analytics pattern)
