# Feature Landscape: Kalshi Prediction Market Backtesting Engine

**Domain:** Binary event contract backtesting engine (prediction markets)
**Researched:** 2026-04-04
**Confidence:** MEDIUM-HIGH — multiple ecosystem sources verified; some nuances specific to Kalshi binary contracts extrapolated from comparable tools

---

## Table Stakes

Features users expect. Missing = product feels incomplete or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Historical contract data ingestion | No backtest without data — Kalshi API is the sole source | Medium | Kalshi partitions live vs. historical tiers; candlesticks (1m/1h/1d) and trades both available. Historical endpoint: `GET /historical/markets/{ticker}/candlesticks`. |
| Binary P&L calculation | Core accounting — yes/no contracts settle to $1.00 or $0.00 | Low | Two modes: (1) pre-resolution exit (buy @ X, sell @ Y → (Y-X) × qty), (2) hold-to-settlement (pay entry price, receive $1.00 if correct, $0.00 if wrong). Both required. |
| Append-only data storage | Fund-wide invariant; historical data must not be overwritten | Low | Snapshots keyed by (ticker, timestamp). Fits existing PostgreSQL append-only pattern from stock backtest module. |
| Trade log | Auditable record of every simulated entry/exit | Low | Each record: contract ticker, event name, category, side (YES/NO), entry price, exit price/resolution, qty, gross P&L, fees, net P&L, timestamps. |
| Equity curve | Primary visual output — shows growth/decline over time | Low | Cumulative portfolio value over time. Total equity + per-market breakdowns are both standard. |
| Total return metric | Headline result — "did the strategy make money?" | Low | Annualized return and absolute return both required. |
| Sharpe ratio | Industry-standard risk-adjusted return | Low | Risk-free rate configurable. Rolling Sharpe (30/60/90 day windows) shows consistency. |
| Max drawdown | Critical risk metric — how bad did it get? | Low | Both percentage and absolute dollar drawdown. Drawdown duration (how long to recover) is a secondary standard. |
| Win rate | Intuitive performance signal for event traders | Low | Win rate alone is misleading without avg win/loss — show both. |
| Strategy plugin interface | Core architecture requirement from PROJECT.md | Medium | Python Protocol/ABC with `generate_signals(market_data) -> List[Signal]`. Strategies are interchangeable without modifying the engine. |
| Contract resolution handling | Binary markets expire — engine must account for it | Medium | At expiry, open positions close at $1.00 (correct) or $0.00 (wrong). Must ingest resolution outcome from Kalshi API. |
| Event category filtering | Kalshi has many categories (politics, weather, crypto, sports, econ) | Low | Backtest a strategy only against relevant event types. Required for any targeted signal strategy. |
| Date range selection | Standard backtest configuration | Low | Configurable start/end date. Default: 1-year lookback per PROJECT.md. |
| Fee modeling | Kalshi charges maker/taker fees — ignoring them inflates returns | Low | Kalshi fee structure: configurable flat or percentage fee per trade. Without fees, results are unrealistic. |

---

## Differentiators

Features that set this engine apart. Not universally expected, but create meaningful advantage.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Brier score / Brier skill score | Prediction-market-native accuracy metric — does the strategy express well-calibrated probabilities? | Medium | Brier score = mean squared error vs. resolution. BSS = calibration + confidence combined. Cumulative Brier advantage (vs. naive 50/50 baseline) is the most actionable chart. Unique to prediction markets; no stock backtest has this. |
| Strategy comparison runner | Run N strategies side-by-side; rank by Sharpe, win rate, total return | Medium | Requires consistent result schema across strategies. Critical for parameter optimization and strategy selection. PolySimulator and NautilusTrader fork both surface this. |
| Parameter grid sweep | Systematically test threshold/sizing variants without rewriting strategy | High | e.g., test insider-signal entry thresholds [0.60, 0.65, 0.70, 0.75] x sizing [10, 25, 50 contracts]. Outputs a ranked results table. |
| Monthly returns heatmap | Quickly identify regime-specific performance (election months, macro events) | Low | Calendar grid of monthly P&L. Standard in professional backtest reports (QuantConnect, Deeptest). Highly readable for investors. |
| Per-category performance breakdown | Which event categories (crypto/politics/weather) drive returns? | Low | Group trade log by Kalshi category; aggregate metrics per group. Exposes category-specific edge vs. noise. |
| Market liquidity filter | Exclude contracts below minimum volume — prevents simulating fills that couldn't happen | Low | Filter by avg daily volume or open interest at signal time. Essential for realistic results on low-liquidity Kalshi markets. |
| Slippage model | Simulate realistic fill prices, not just mid-price | Medium | For thin Kalshi order books, a fixed spread assumption (e.g., 1-2 cents) is pragmatic. Full order-book replay (PolyBackTest approach) is better but requires L2 data Kalshi may not expose. Fixed-spread model is the practical v1 choice. |
| Walk-forward / out-of-sample split | Avoid overfitting — optimize on in-sample, validate on holdout | High | Split backtest window into optimization and validation periods. Standard anti-overfitting practice. Best deferred to a later phase; get signal validation working first. |
| Insider Tracker adapter | First concrete strategy plugin — proves the interface works end-to-end | Medium | Adapter reads signals from Kalshi Insider Tracker's output and wraps them in the Strategy protocol. This is what makes the backtesting engine immediately valuable. |
| HTML / PDF tearsheet export | Investor-ready output — a single document with all charts and metrics | Medium | Borrowing the convention from `backtest/` module (daily dashboard). Plotly/matplotlib → HTML file. PDF via headless browser or weasyprint. |
| Sortino ratio | More accurate than Sharpe for asymmetric P&L (binary payoffs) | Low | Uses downside deviation only. Relevant for strategies with lottery-like payoffs ($0.05 → $1.00). |
| Profit factor | Gross winning trades / gross losing trades | Low | Ratio > 1.0 means more won than lost in dollar terms. More intuitive than Sharpe for many users. |

---

## Anti-Features

Features to explicitly NOT build in v1. Each deferred for a concrete reason.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Live trading execution | Scope explicitly out-of-bounds per PROJECT.md; adds regulatory/error risk | Simulation only — annotate results clearly as "simulated" |
| Market-making strategy support | Different problem domain; requires queue-position and spread modeling NautilusTrader handles | Signal-based strategies only for v1; market-making is a future module |
| Real-time streaming / websocket replay | Adds infrastructure complexity with no v1 benefit | Batch historical analysis only |
| Full order-book (L2/L3) replay | Kalshi's public API does not expose full L2 history; engineering cost is very high | Fixed-spread slippage model — sufficient for daily-signal strategies |
| Multi-exchange support (Polymarket, PredictIt) | Each exchange has different data models, fee structures, contract semantics | Kalshi-only for v1; abstraction layer can be added later if needed |
| Web UI / hosted dashboard | Adds deployment complexity; investor-grade web app is a different project | CLI + local HTML file output (same pattern as `backtest/` module) |
| Machine learning signal generation | Strategy generation is outside the engine's responsibility | Engine evaluates signals; signal generation belongs in each Strategy plugin |
| Walk-forward / rolling optimization | Correct and valuable, but high implementation complexity | Defer to v2; start with full-period static backtest |
| Portfolio-level position sizing (Kelly, etc.) | Premature optimization — need to validate signal quality first | Fixed contract qty or % of capital per trade; Kelly criterion is a v2 feature |
| Correlation matrix across strategies | Useful only once multiple strategies exist | Build when there are ≥ 3 strategies to compare |

---

## Feature Dependencies

```
Kalshi data ingestion
  → Contract resolution handling
  → Trade log
  → P&L calculation (both exit modes)
      → Equity curve
      → Total return
      → Sharpe ratio
      → Max drawdown
      → Win rate / profit factor / Sortino
          → Monthly returns heatmap
          → HTML tearsheet export

Strategy plugin interface
  → Insider Tracker adapter (first consumer)
  → Strategy comparison runner
      → Parameter grid sweep

Event category filtering
  → Per-category performance breakdown

Market liquidity filter (standalone, applied at signal replay time)

Slippage model (standalone, applied at fill simulation time)

Brier score (requires resolution outcome + entry price at signal time)
```

---

## MVP Recommendation

The minimum set that produces a credible, investor-useful result:

**Phase 1 — Data Foundation**
1. Kalshi data ingestion (candlesticks + resolution outcomes)
2. Append-only storage
3. Contract resolution handling

**Phase 2 — Engine Core**
4. Strategy plugin interface (Protocol/ABC)
5. Signal replay engine (iterate over historical data, call strategy, simulate fills)
6. Fee modeling + fixed-spread slippage
7. Trade log

**Phase 3 — Metrics + Output**
8. P&L calculation (pre-resolution exit + hold-to-settlement)
9. Equity curve
10. Core metrics: total return, Sharpe, Sortino, max drawdown, win rate, profit factor
11. HTML tearsheet with equity curve + monthly returns heatmap

**Phase 4 — First Consumer**
12. Insider Tracker adapter (proves the plugin interface end-to-end)
13. Brier score / Brier skill score (prediction-market-native validation)
14. Event category filtering + per-category breakdown

**Defer to v2:**
- Strategy comparison runner with parameter grid sweep
- Walk-forward / out-of-sample validation
- PDF export
- Portfolio-level position sizing

---

## Confidence Notes

| Area | Confidence | Reason |
|------|------------|--------|
| P&L mechanics (binary contracts) | HIGH | YES + NO = $1.00 invariant is mathematically documented; pre-resolution and hold-to-settlement modes both observed in wild implementations |
| Core metrics (Sharpe, drawdown, etc.) | HIGH | Universal backtesting standards; multiple sources confirm |
| Brier score for prediction markets | HIGH | Well-documented in prediction market research (Brier.fyi, academic papers, NautilusTrader fork) |
| Kalshi API data availability | MEDIUM-HIGH | Confirmed: candlesticks (1m/1h/1d), trades, orderbook endpoints exist; historical partition is real. Exact retention depth for free-tier uncertain. |
| Slippage modeling complexity | MEDIUM | Kalshi L2 depth availability unclear; fixed-spread model is a practical default |
| Parameter optimization complexity | MEDIUM | Grid sweep patterns are well-understood; Kalshi-specific behavior under optimization not studied |

---

## Sources

- [GitHub — evan-kolberg/prediction-market-backtesting (NautilusTrader fork)](https://github.com/evan-kolberg/prediction-market-backtesting)
- [PredictBack — Prediction Markets Backtesting](https://www.predictback.com/)
- [PolySimulator — Polymarket & Kalshi Strategy Tester](https://polysimulator.com/backtesting)
- [PredictionMarketBench — SWE-bench-style prediction market backtesting framework](https://arxiv.org/html/2602.00133v1)
- [Kalshi API — Get Market Candlesticks](https://docs.kalshi.com/api-reference/market/get-market-candlesticks)
- [Kalshi API — Get Historical Market](https://docs.kalshi.com/api-reference/historical/get-historical-market)
- [Kalshi API — Historical Data Overview](https://docs.kalshi.com/getting_started/historical_data)
- [The Math of Prediction Markets: Binary Options, Kelly Criterion, and CLOB Pricing Mechanics](https://navnoorbawa.substack.com/p/the-math-of-prediction-markets-binary)
- [Backtesting Trading Strategies on Prediction Markets' Cryptocurrency Contracts — BSIC](https://bsic.it/well-can-we-predict-backtesting-trading-strategies-on-prediction-markets-cryptocurrency-contracts/)
- [quantgalore/kalshi-trading — Kalshi strategy backtest reference implementation](https://github.com/quantgalore/kalshi-trading/blob/main/kalshi-strategy-backtest.py)
- [Calibration and Skill of the Kalshi Prediction Markets — CW Data Solutions](https://www.cwdatasolutions.com/post/calibration-and-skill-of-the-kalshi-prediction-markets)
- [Event-Driven Backtesting with Python — QuantStart](https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-I/)
- [Top 7 Metrics for Backtesting Results — LuxAlgo](https://www.luxalgo.com/blog/top-7-metrics-for-backtesting-results/)
- [Complete Backtesting Dashboard: From Performance Metrics to Trade Visualization — Medium](https://medium.com/@cointesterio/complete-backtesting-dashboard-from-performance-metrics-to-trade-visualization-f1bf0c9e7c71)
- [Backtesting Traps: Common Errors to Avoid — LuxAlgo](https://www.luxalgo.com/blog/backtesting-traps-common-errors-to-avoid/)
- [The Python Backtesting Landscape (2026) — python.financial](https://python.financial/)
