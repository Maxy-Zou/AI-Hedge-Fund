# Architecture Patterns: Vectorized Backtesting Infrastructure

**Domain:** Vectorized backtesting engine with data pipeline and reporting
**Researched:** 2026-03-28
**Confidence:** HIGH (cross-validated via VectorBT docs, QuantStart, IBKR campus, O'Reilly)

---

## Recommended Architecture

The architecture separates into five layers. Each layer has exactly one responsibility and exposes a typed interface to adjacent layers. No layer skips a boundary.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  EXTERNAL SIGNALS  (AI Washing Detector, future strategy modules)        │
│  Input: date-indexed, ticker-indexed DataFrame of raw scores             │
└────────────────────────────┬────────────────────────────────────────────┘
                             │  SignalFrame (date x ticker → float score)
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  SIGNAL ADAPTER                                                          │
│  Normalises, validates, and ranks raw scores into [-1, +1] weights       │
└────────────────────────────┬────────────────────────────────────────────┘
                             │  WeightFrame (date x ticker → float weight)
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PORTFOLIO SIMULATOR                                                     │
│  Applies position sizing, transaction costs, and produces daily P&L      │
└──────────┬──────────────────────────────────────┬───────────────────────┘
           │ PriceFrame                           │ PortfolioResult
           │ (date x ticker → OHLCV)              │ (daily returns, positions,
           ▼                                      │  trades, turnover)
┌──────────────────────────┐                      │
│  DATA LAYER              │                      ▼
│  yfinance → PostgreSQL   │   ┌──────────────────────────────────────────┐
│  OHLCV + universe cache  │   │  RISK ENGINE                             │
└──────────────────────────┘   │  Computes Sharpe, Sortino, drawdown,     │
                               │  Calmar, hit rate, turnover, borrow cost  │
                               └───────────────────┬──────────────────────┘
                                                   │ MetricsBundle
                                                   ▼
                               ┌──────────────────────────────────────────┐
                               │  REPORTING LAYER                          │
                               │  Streamlit dashboard + PDF tearsheet +    │
                               │  CSV/JSON export                          │
                               └──────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Input | Output | Communicates With |
|-----------|---------------|-------|--------|-------------------|
| Data Layer | Fetch, cache, and serve daily OHLCV for the mid-cap universe | yfinance API, PostgreSQL | `PriceFrame` (MultiIndex DataFrame: date x ticker) | Portfolio Simulator (provides prices), Universe Manager |
| Universe Manager | Maintain and refresh the list of in-scope tickers by market cap | Screener or static list, PostgreSQL | `universe: list[str]` of tickers | Data Layer (controls which tickers to fetch) |
| Signal Adapter | Accept raw strategy scores, validate schema, normalize to weights | `SignalFrame` from external module | `WeightFrame` (date x ticker, values in [-1, +1]) | Portfolio Simulator (provides weights) |
| Portfolio Simulator | Core vectorized engine — apply weights to prices, subtract costs, compute daily portfolio P&L | `WeightFrame`, `PriceFrame`, `CostConfig` | `PortfolioResult` (returns series, positions frame, trade log) | Risk Engine (provides result), Data Layer (reads prices) |
| Cost Model | Encapsulate slippage, commission, and short-borrow cost logic | `CostConfig` (dataclass), trade direction/size | Per-trade cost scalars | Portfolio Simulator (called internally) |
| Risk Engine | Compute all performance and risk statistics from daily returns | `PortfolioResult`, benchmark returns series | `MetricsBundle` (dict of named metrics) | Reporting Layer (provides metrics) |
| Reporting Layer | Render dashboard and tearsheet; export raw data | `MetricsBundle`, `PortfolioResult` | Streamlit UI, PDF file, CSV/JSON files | Risk Engine (reads metrics), Portfolio Simulator (reads raw results) |

---

## Data Flow

```
yfinance.download(tickers, start, end)
        │
        │ raw MultiIndex DataFrame (date x ticker x OHLCV)
        ▼
Data Layer: validate, deduplicate, store in PostgreSQL price_ohlcv table
        │
        │ SELECT * FROM price_ohlcv WHERE date >= ? AND ticker IN (?)
        ▼
PriceFrame: pd.DataFrame, index=DatetimeIndex, columns=MultiIndex(ticker, field)
        │
        │  (joined by aligned date index)
        │
SignalFrame enters from AI Washing Detector:
  pd.DataFrame, index=DatetimeIndex, columns=ticker list, values=float scores
        │
        ▼
Signal Adapter:
  1. Assert index alignment with PriceFrame date range
  2. Clip/reject out-of-universe tickers
  3. Normalise scores: rank within cross-section → map to [-1, +1]
  4. Apply rebalance frequency mask (e.g., weekly rebalance on daily data)
        │
        ▼
WeightFrame: same shape as SignalFrame but values are portfolio weights
        │
        ▼
Portfolio Simulator (fully vectorized — no Python loops over dates):
  1. Shift weights by 1 period (trade at next-day open, avoid lookahead)
  2. Compute weight_changes → identify turnover
  3. Apply CostModel to turnover rows: subtract slippage + commission
  4. Apply borrow_cost_bps to short positions (negative weights) daily
  5. Compute daily gross_returns = (close[t] / close[t-1] - 1) * weight[t-1]
  6. Compute daily net_returns = gross_returns - costs
  7. Compute portfolio_returns = weighted sum across tickers
  8. Compute cumulative NAV series
        │
        ▼
PortfolioResult:
  - returns: pd.Series (daily portfolio net returns)
  - positions: pd.DataFrame (date x ticker, daily weight held)
  - trade_log: pd.DataFrame (date, ticker, direction, size, cost)
  - gross_returns: pd.Series
        │
        ▼
Risk Engine (vectorized):
  - Sharpe ratio (annualized, 252-day)
  - Sortino ratio (downside deviation only)
  - Max drawdown (peak-to-trough on NAV series)
  - Calmar ratio (CAGR / max drawdown)
  - Hit rate (% of profitable days)
  - Win/loss ratio (avg win / avg loss)
  - Annualized turnover
  - Benchmark comparison (alpha, beta, information ratio vs S&P 500 / Russell 2000)
        │
        ▼
MetricsBundle: dict[str, float | pd.Series] — all scalar metrics + rolling metrics
        │
        ▼
Reporting Layer:
  - Streamlit: equity curve, drawdown chart, rolling Sharpe, sector exposure
  - PDF tearsheet via WeasyPrint or reportlab: single-page fund factsheet
  - CSV export: daily_returns.csv, positions.csv, trade_log.csv
  - JSON export: metrics.json (machine-readable for downstream consumers)
```

---

## Signal Contract

This is the critical interface between strategy modules and the backtester.

### Input: SignalFrame

```python
# Type definition
SignalFrame = pd.DataFrame
# index: pd.DatetimeIndex, UTC, daily frequency
# columns: list[str] — ticker symbols (e.g. "AAPL", "NVDA")
# values: float — raw strategy scores, arbitrary scale
# NaN: allowed — interpreted as "no position" for that ticker/date
# Range: unrestricted — Signal Adapter normalizes internally
```

**Contract rules enforced by Signal Adapter:**
1. Index must be a `DatetimeIndex` with `freq='B'` (business days) or daily.
2. All column values must be ticker strings present in the active universe or they are silently dropped with a warning log.
3. A NaN value means no signal — the position for that ticker/date is zeroed.
4. The adapter does NOT require the strategy to normalize scores. Raw scores (e.g., AI Washing Risk Score 0–100) are accepted and ranked cross-sectionally.
5. The adapter enforces a `min_coverage` threshold: if fewer than N tickers have non-NaN scores on a given date, that date is skipped (no rebalance).

### Normalization Pipeline (inside Signal Adapter)

```
raw_score (float, arbitrary scale)
    → cross_section_rank (percentile 0–100 within date)
    → map to weight_direction: top decile → short (-1 side), bottom → no position
    → scale by position_sizing_rule (equal weight / score-proportional)
    → clip to max_position_size (e.g., 5% per ticker)
    → result: weight in [-max_gross_exposure, +max_gross_exposure]
```

For the AI Washing Detector specifically: high AI Washing Risk Score → short candidate → negative weight.

### Output: WeightFrame

```python
WeightFrame = pd.DataFrame
# index: pd.DatetimeIndex — same as SignalFrame after alignment
# columns: list[str] — tickers (universe-filtered)
# values: float in [-1.0, +1.0]
# Invariant: abs(weights).sum(axis=1) <= gross_exposure_limit (default 1.0)
# Sign convention: negative = short, positive = long, zero = flat
```

### Configuration Contract (CostConfig)

```python
@dataclass(frozen=True)
class CostConfig:
    commission_bps: float = 5.0          # one-way, basis points
    slippage_bps: float = 10.0           # half-spread estimate, basis points
    borrow_cost_bps_annual: float = 50.0 # annualized short borrow, basis points
    rebalance_freq: str = "W-FRI"        # pandas offset alias for rebalance
    max_position_size: float = 0.05      # per-ticker cap as fraction of NAV
    gross_exposure_limit: float = 1.0    # total abs(weights) cap
```

All cost and sizing parameters are external configuration — never hardcoded in the simulator.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Lookahead Bias
**What:** Using today's close price to compute a signal, then immediately trading at today's close.
**Why bad:** Impossible in practice — you don't know today's close until the day ends.
**Prevention:** Always shift weights by 1 period. Signals computed on day T execute at open/close of day T+1. This is a single `.shift(1)` call in the Portfolio Simulator — easy to get right once, catastrophic if missed.

### Anti-Pattern 2: Survivorship Bias
**What:** Only backtesting on tickers that still exist today.
**Why bad:** Removes companies that went bankrupt or were acquired — inflates strategy performance.
**Prevention:** Universe snapshot table must store historical composition (which tickers were in-scope on each date). The Data Layer joins against the snapshot, not the current universe. Point-in-time universe is a separate architectural concern.
**Phase impact:** This is a medium-complexity problem. V1 can use current universe with a documented caveat. Full survivorship-bias correction is a Phase 2+ concern.

### Anti-Pattern 3: Signal Leakage Through Shared State
**What:** Strategy module writes directly to the backtester's internal state instead of passing through the SignalFrame interface.
**Why bad:** Couples modules together; makes testing impossible; causes subtle data ordering bugs.
**Prevention:** The Signal Adapter is the single entry point. Strategy modules produce a SignalFrame file or DataFrame and call `BacktestRunner.run(signal_frame, cost_config)`. No shared mutable state.

### Anti-Pattern 4: Python Loop Over Dates
**What:** Iterating `for date in dates: portfolio[date] = compute(...)` instead of vectorized operations.
**Why bad:** 200 tickers x 1,250 days (5 years) = 250,000 iterations. Python loop is 100-1,000x slower than vectorized pandas/numpy.
**Prevention:** All portfolio math uses `.mul()`, `.shift()`, `.cumsum()`, `.rolling()` — pandas vectorized methods operating on entire DataFrames at once. Cost model applies via masked array operations on turnover frames.

### Anti-Pattern 5: Overwriting Historical Price Data
**What:** `UPDATE price_ohlcv SET close = new_value WHERE date = ? AND ticker = ?`
**Why bad:** Violates the fund-wide immutability convention; destroys audit trail; breaks reproducibility of historical backtests.
**Prevention:** Data Layer is append-only. New fetches use `INSERT ... ON CONFLICT DO NOTHING`. Corrections are tracked as separate entries with a `source_revision` column.

---

## Build Order

Components have strict dependency ordering. Build bottom-up: data before simulation, simulation before risk, risk before reporting.

```
Phase 1: Data Foundation
├── Universe Manager (which tickers to track)
└── Data Layer (yfinance fetch + PostgreSQL cache)
    Dependency: nothing external
    Deliverable: populated price_ohlcv table, universe snapshots

Phase 2: Backtesting Core
├── Signal Adapter (validates + normalizes incoming SignalFrames)
├── Cost Model (transaction cost dataclass + calculation functions)
└── Portfolio Simulator (vectorized engine)
    Dependency: Data Layer (prices), Signal Adapter (weights)
    Deliverable: PortfolioResult from any valid SignalFrame

Phase 3: Risk Engine
└── Risk Engine (all performance metrics from PortfolioResult)
    Dependency: Portfolio Simulator output
    Deliverable: MetricsBundle with all standard quant metrics

Phase 4: Reporting
├── Streamlit dashboard
├── PDF tearsheet
└── CSV/JSON export
    Dependency: Risk Engine (MetricsBundle), Portfolio Simulator (PortfolioResult)
    Deliverable: investor-ready outputs

Phase 5: Integration
└── Wire AI Washing Detector's scores into SignalFrame format
    Dependency: All above layers, plus Detector's score output
    Deliverable: first end-to-end backtest run
```

**Why this order:**
- The Signal Adapter and Portfolio Simulator are the core. Everything else is input (Data Layer) or output (Risk Engine, Reporting).
- The Risk Engine depends only on `returns: pd.Series` — it can be built and tested independently with synthetic data.
- The Reporting Layer depends only on `MetricsBundle` and `PortfolioResult` — can be built with hardcoded fixtures.
- Integration (Phase 5) is last because it tests the contract between two independently-developed modules.

---

## Scalability Considerations

| Concern | At 200 tickers (v1) | At 500 tickers | At 2,000 tickers |
|---------|---------------------|----------------|------------------|
| Price storage | Single table, fine | Single table, fine | Partition by year |
| yfinance download | Batched requests, ~2 min | ~5 min | Need async batching |
| Portfolio simulation | Sub-second (vectorized) | Sub-second | May need Numba for cost loops |
| Memory (5yr daily data) | ~50MB DataFrame | ~125MB | ~500MB — consider chunked reads |
| Risk computation | Instantaneous | Instantaneous | Rolling windows get heavy |
| Reporting render | Streamlit, <5s | <5s | May need cached pre-computation |

V1 (200 tickers) is fully covered by pure pandas/numpy. No Numba, no chunking, no async downloads needed at this scale.

---

## Key Libraries for Each Layer

| Layer | Primary Library | Purpose |
|-------|----------------|---------|
| Data Layer | yfinance | OHLCV fetch |
| Data Layer | SQLAlchemy + psycopg | PostgreSQL persistence |
| Signal Adapter | pandas | DataFrame normalization, ranking |
| Portfolio Simulator | pandas + numpy | Vectorized P&L computation |
| Cost Model | Plain Python dataclass | Cost parameter container |
| Risk Engine | quantstats | Sharpe, Sortino, drawdown, tearsheet metrics |
| Reporting | Streamlit | Interactive dashboard |
| Reporting | WeasyPrint or reportlab | PDF tearsheet generation |

**On quantstats:** The `quantstats.stats` module computes all standard quant metrics from a daily returns series. Use it as a computation library inside the Risk Engine rather than as a reporting framework — keep the Risk Engine output as a plain `dict` / `MetricsBundle` so reporting is decoupled from metric computation.

**On pyfolio:** Pyfolio is Quantopian-origin and minimally maintained. quantstats is the actively maintained successor for pure Python reporting. Use quantstats.

---

## Sources

- [VectorBT documentation](https://vectorbt.dev/) — vectorized architecture and NumPy/Numba patterns (HIGH confidence)
- [IBKR: Vector-Based vs Event-Based Backtesting](https://www.interactivebrokers.com/campus/ibkr-quant-news/a-practical-breakdown-of-vector-based-vs-event-based-backtesting/) — paradigm comparison (HIGH confidence)
- [QuantStart: Research Backtesting in Python with pandas](https://www.quantstart.com/articles/Research-Backtesting-Environments-in-Python-with-pandas/) — component design patterns (HIGH confidence)
- [QuantStart: Backtesting Systematic Strategies — Considerations](https://www.quantstart.com/articles/backtesting-systematic-trading-strategies-in-python-considerations-and-open-source-frameworks/) — anti-patterns and pitfalls (HIGH confidence)
- [O'Reilly: Python for Algorithmic Trading — Ch4 Vectorized Backtesting](https://www.oreilly.com/library/view/python-for-algorithmic/9781492053347/ch04.html) — signal matrix and cross-sectional portfolio construction (HIGH confidence)
- [QuantStats GitHub](https://github.com/ranaroussi/quantstats) — reporting module architecture (MEDIUM confidence — verify active maintenance before use)
- [pyfolio (Quantopian)](https://quantopian.github.io/pyfolio/) — tearsheet pattern (LOW confidence — minimally maintained, use quantstats instead)
- [Hudson & Thames backtest tutorial](https://github.com/hudson-and-thames/backtest_tutorial) — transaction cost notebook (MEDIUM confidence)
- [yfinance API reference](https://ranaroussi.github.io/yfinance/reference/index.html) — bulk download and caching (HIGH confidence)
