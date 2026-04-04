# Project Research Summary

**Project:** Kalshi Prediction Market Backtesting Engine
**Domain:** Binary event contract backtesting (prediction markets)
**Researched:** 2026-04-04
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a specialized backtesting engine for Kalshi binary event contracts — instruments that settle at exactly $1.00 (win) or $0.00 (loss), priced in cents as a probability percentage. No existing backtesting framework (VectorBT, backtesting.py, NautilusTrader) handles this contract type cleanly: binary resolution mechanics, probability-weighted fees, and a live/historical API tier split all require custom handling. The recommended approach is a layered pipeline: a dedicated ingestion layer that handles Kalshi's API quirks, DuckDB for local analytical storage, a custom ~300-line vectorized simulation engine, and quantstats plus Plotly for reporting. All components are built to the fund's existing conventions (uv, Pydantic, Typer, structlog, pytest).

The critical design decision is strict enforcement of the append-only, lookahead-free data model from day one. Kalshi's settlement results must never be visible to the strategy at signal time — this is the single most invalidating bug in backtesting binary contracts, and it cannot be retrofitted cheaply. The recommended architecture separates ingestion, storage, simulation, metrics, and reporting into discrete layers with typed contracts at each boundary, following the same layered pattern used by the Kalshi Insider Tracker.

The primary risk is data quality: Kalshi's live/historical API tier boundary moves forward over time and silently returns empty results when queried incorrectly; ingesting only settled markets introduces survivorship bias; and probability-weighted fees (7% taker, 1.75% maker) can consume the entire edge of a strategy with small price moves. All three of these must be addressed in Phase 1 before any simulation work begins. The upside: once the data foundation is correct, the simulation engine is relatively straightforward — daily-bar binary contracts are simpler than continuous equity instruments.

---

## Key Findings

### Recommended Stack

The stack is almost entirely drawn from the fund's existing dependency set, with two new additions: `duckdb` for local analytical storage (8x faster than SQLite for time-series range queries) and `quantstats` for tearsheet generation (the active replacement for deprecated pyfolio). The official `kalshi-python` SDK (v2.1.4) handles authentication and standard endpoints, but historical endpoints may require direct `httpx` calls since the SDK's `/historical/*` coverage is not fully verified. The custom backtest engine is ~300 lines of pandas/numpy — the recommendation against existing frameworks is firm.

**Core technologies:**
- `kalshi-python` 2.1.4 + `httpx`: Kalshi API access — official SDK for auth/standard endpoints, httpx fallback for historical endpoints
- `duckdb` 1.x: Local analytical store — columnar, zero-server, append-only, 8x faster than SQLite for time-series queries
- `pandas` + `numpy`: Simulation engine backbone — vectorized data load with chronological replay loop
- `pydantic` 2.x: API response validation + inter-layer data contracts — fund-wide standard
- `quantstats`: P&L tearsheet (Sharpe, drawdown, CAGR) — active successor to deprecated pyfolio
- `plotly` 5.x: Interactive equity curve and performance charts — CLI + local HTML output, no web server
- `typer` 0.24.1+: CLI commands (ingest, run, compare, report) — fund-wide standard
- `tenacity` 9.1.4+: Retry/backoff for Kalshi API rate limits — fund-wide standard

### Expected Features

See FEATURES.md for full dependency graph and MVP breakdown.

**Must have (table stakes):**
- Historical contract data ingestion (candlesticks + resolution outcomes) — no backtest without it
- Binary P&L calculation — both pre-resolution exit and hold-to-settlement modes
- Append-only storage with (ticker, ts) uniqueness enforcement
- Strategy plugin interface as `typing.Protocol` — core architecture requirement
- Contract resolution handling — markets settle at $1.00 or $0.00; engine must process expiry
- Fee modeling using exact Kalshi formula: `ceil(0.07 * C * P * (1-P))` for takers
- Trade log with per-trade auditable record
- Core metrics: total return, Sharpe, Sortino, max drawdown, win rate, profit factor
- HTML tearsheet with equity curve and monthly returns heatmap
- Event category filtering (politics, economics, crypto, weather, sports)

**Should have (differentiators):**
- Brier score / Brier skill score — prediction-market-native calibration metric, unique to this domain
- Insider Tracker adapter — first concrete Strategy plugin, proves the interface end-to-end
- Per-category performance breakdown — exposes where edge actually lives
- Market liquidity filter — excludes contracts below minimum daily volume
- Fixed-spread slippage model — conservative ask/bid fill, not midpoint fill
- Strategy comparison runner — side-by-side N-strategy result table

**Defer to v2+:**
- Walk-forward / out-of-sample validation — correct but high complexity; get signal validation working first
- Parameter grid sweep — useful only after single-run path is proven
- Portfolio-level position sizing (Kelly criterion)
- PDF tearsheet export
- Correlation matrix across strategies (needs 3+ strategies first)
- Live trading execution — explicitly out of scope per PROJECT.md

### Architecture Approach

A five-layer pipeline where data flows strictly downward: Ingestion → Storage → Simulation Engine (with Strategy plugin injected sideways) → Metrics → Reporting. Each layer communicates through typed immutable contracts (frozen dataclasses or Pydantic models). The Strategy plugin uses `typing.Protocol` for structural subtyping — third-party strategies satisfy the interface without importing from this codebase. The simulation loop uses a hybrid approach: bulk vectorized data load at run start, then chronological bar-by-bar iteration to prevent lookahead bias.

**Major components:**
1. **CLI / Entrypoint** (Typer) — parse commands, load config, dispatch; no business logic
2. **Ingestion Layer** — KalshiAPIClient + fetchers; owns all API quirks (tier routing, pagination, rate limits)
3. **Storage Layer** (DuckDB) — Event, Market, MarketCandle tables; append-only with `UNIQUE(ticker, ts)` guard
4. **Simulation Engine** — BacktestRunner + BarIterator + SimulatedOrderBook + PositionTracker; Strategy injected via Protocol
5. **Metrics Layer** — accumulates FillEvents, computes equity curve and all performance statistics
6. **Reporting Layer** — DashboardBuilder (Plotly) → `dashboard.html`; ComparisonReport for multi-strategy

Key data contracts: `MarketSnapshot` (frozen dataclass — bridge between storage and strategy), `Signal` (frozen dataclass — strategy output), `MetricsResult` (bridge between metrics and reporting).

### Critical Pitfalls

See PITFALLS.md for full detail on 12 identified pitfalls. The top 5 are all Phase 1-2 concerns.

1. **Resolution look-ahead bias** — `MarketSnapshot.result` must be `None` for any bar before `close_time`; `BarIterator` enforces this. Cannot be retrofitted — design the data model correctly in Phase 1 or rebuild.
2. **Survivorship bias from settled-only ingestion** — ingest all markets open during the date range, not just settled ones; store `status` as `open/settled/cancelled/voided`.
3. **Midpoint pricing as fill price** — Kalshi spreads run 5-20 cents wide; fills must use ask (buys) or bid (sells) with a minimum 3-5 cent spread floor and a liquidity volume filter.
4. **Missing Kalshi fee formula** — implement `ceil(0.07 * C * P * (1-P))` taker fee and `ceil(0.0175 * C * P * (1-P))` maker fee; report gross and net-of-fees P&L side by side; unit test the formula.
5. **Kalshi live/historical API tier confusion** — query `GET /historical/cutoff` at every ingestion run; route requests dynamically; assert plausible market counts per calendar month after ingestion.

Additional important pitfalls:
- Dollar P&L must be the primary metric (not percentage return) — percentage distortion inflates Sharpe for low-probability binary bets
- UTC-only storage with timezone-aware datetimes; use `zoneinfo.ZoneInfo("America/New_York")` for display only
- Flag any backtest with N < 30 settled markets as statistically unreliable

---

## Implications for Roadmap

Based on combined research, a 4-phase structure is strongly recommended. The first phase is entirely data; nothing else can be built correctly without it.

### Phase 1: Data Foundation
**Rationale:** All other layers depend on correct, lookahead-free, survivorship-bias-free historical data. The live/historical API tier routing and UTC-only timestamp discipline cannot be retrofitted — they must be enforced from the first ingestion run. This phase has the highest density of critical pitfalls.
**Delivers:** DuckDB schema with Event/Market/MarketCandle tables; KalshiAPIClient with tier routing; full ingestion of 1-year candlestick + resolution history; ingestion CLI command.
**Addresses:** Historical contract data ingestion, append-only storage, contract resolution handling, event category filtering (stored as `category` column).
**Avoids:** Pitfalls 1 (look-ahead bias via `result` column separation), 2 (survivorship bias via date-range ingestion), 7 (timezone mishandling via UTC enforcement), 8 (live/historical tier confusion via cutoff routing).
**Research flag:** NEEDS DEEPER RESEARCH — Kalshi SDK historical endpoint coverage is unverified; exact API pagination behavior and rate limit specifics need hands-on validation.

### Phase 2: Simulation Engine Core
**Rationale:** The simulation engine is the most novel component (no existing framework handles binary contracts). Build and test it in isolation before adding strategy logic. Lookahead prevention, fill model, and fee formula are all implemented here.
**Delivers:** BacktestRunner + BarIterator + SimulatedOrderBook + PositionTracker + FillEngine; `Strategy` Protocol definition; `MarketSnapshot`/`Signal`/`Fill` data contracts; fee calculation with exact Kalshi formula; conservative bid/ask fill model with liquidity filter.
**Addresses:** Strategy plugin interface, binary P&L calculation (both modes), fee modeling, slippage model, market liquidity filter, trade log.
**Avoids:** Pitfalls 3 (midpoint pricing), 4 (missing fees), 5 (percentage return distortion), 10 (settlement delay modeling).
**Research flag:** STANDARD PATTERNS — bar-by-bar simulation loop is well-documented; the only Kalshi-specific novelty is binary P&L math and fee formula, both fully specified in research.

### Phase 3: Metrics and Reporting
**Rationale:** Once the simulation engine emits a reliable FillEvent stream, metrics computation and reporting are straightforward. quantstats handles standard metrics; custom code covers Kalshi-specific metrics (Brier score, per-category breakdown). HTML dashboard follows existing `backtest/` module pattern.
**Delivers:** MetricsCalculator (Sharpe, Sortino, drawdown, win rate, profit factor, Calmar); equity curve construction; monthly returns heatmap; HTML tearsheet via Plotly; CLI `report` command; sample size N < 30 warning flag.
**Addresses:** All core metrics (table stakes), HTML tearsheet export, per-category performance breakdown.
**Avoids:** Pitfall 6 (overfitting warning via N < 30 flag), Pitfall 11 (regime blindness disclosure).
**Research flag:** STANDARD PATTERNS — quantstats and Plotly are well-documented; custom binary contract metrics (Brier score, per-category) are straightforward numpy/pandas computations.

### Phase 4: First Strategy Consumer (Insider Tracker Adapter)
**Rationale:** The Insider Tracker adapter is what makes this engine immediately valuable to the fund. It proves the Strategy Protocol works end-to-end with a real signal source and delivers investor-useful backtest results. Brier score is included here because it requires a working end-to-end backtest to be meaningful.
**Delivers:** `InsiderTrackerAdapter` Strategy plugin; Brier score / Brier skill score metrics; strategy comparison CLI command; verified end-to-end backtest with real signals.
**Addresses:** Insider Tracker adapter (differentiator), Brier score (differentiator), strategy comparison runner (partial — single vs. baseline comparison is enough for v1).
**Avoids:** N/A — this phase is a consumer of the engine, not new engine infrastructure.
**Research flag:** NEEDS DEEPER RESEARCH — the Insider Tracker's signal output format needs to be reviewed to design the adapter's input contract correctly.

### Phase Ordering Rationale

- Storage before ingestion before simulation is dictated by hard dependency direction — cannot simulate without data, cannot store without schema.
- Metrics before reporting is dictated by the MetricsResult contract — the dashboard is a pure consumer of MetricsResult; defining that contract first enables parallel development of reporting layer.
- Insider Tracker adapter is last because it is a consumer of a stable interface, not infrastructure — building it before the Protocol is proven would require rework.
- All critical pitfalls (1-5) are addressed in Phases 1-2 before any output is produced, ensuring that when results first appear in Phase 3 they are trustworthy.

### Research Flags

Phases needing deeper research during planning:
- **Phase 1:** Kalshi SDK historical endpoint coverage — verify which `/historical/*` endpoints `kalshi-python` 2.1.4 actually wraps before writing ingestion code; may need full `httpx` implementation for historical candlesticks and trades
- **Phase 1:** Kalshi rate limit specifics — exact request-per-second limits not confirmed; implement tenacity retry conservatively from the start
- **Phase 4:** Insider Tracker signal output format — review actual signal schema before designing the adapter input contract

Phases with standard patterns (skip research-phase):
- **Phase 2:** Simulation loop architecture — bar-by-bar event replay is a well-documented pattern; binary P&L math is fully specified
- **Phase 3:** Metrics and reporting — quantstats + Plotly are standard; Brier score formula is well-documented in prediction market literature

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Core stack (DuckDB, pandas, quantstats, Plotly) is well-validated; `kalshi-python` 2.1.4 exists on PyPI but historical endpoint coverage was not directly verified |
| Features | MEDIUM-HIGH | Binary contract P&L mechanics and standard backtesting metrics are HIGH confidence; Kalshi API data availability depth is MEDIUM (free-tier retention window unconfirmed) |
| Architecture | MEDIUM-HIGH | Layered pipeline pattern and Protocol-based strategy interface are HIGH confidence; Kalshi-specific tier routing pattern is MEDIUM confidence (official docs confirmed, internals inferred) |
| Pitfalls | MEDIUM-HIGH | Look-ahead bias, survivorship bias, fee formula, and timezone handling are HIGH confidence (academic sources + official docs); fill model and liquidity assumptions are MEDIUM confidence |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Kalshi SDK `/historical/*` endpoint coverage:** Verify at implementation time which methods `kalshi-python` 2.1.4 exposes. Fallback plan is direct `httpx` calls — no blocker, just need to confirm before writing ingestion code.
- **Kalshi rate limit specifics:** Rate limit tiers reference confirms limits exist but exact numbers (req/sec per tier) were not confirmed from research. Implement tenacity with conservative defaults; adjust after first real ingestion run.
- **Kalshi historical data retention depth:** PROJECT.md targets 1-year lookback. Actual free-tier retention window is unconfirmed. May need to validate how far back the historical endpoint actually serves data before committing to a 1-year backtest window.
- **DuckDB vs SQLite trade-off re-check:** Architecture.md lists SQLite for dev / PostgreSQL for prod, while STACK.md recommends DuckDB throughout. Resolve at Phase 1 planning: DuckDB is the correct choice for this standalone local tool (no migration to PostgreSQL needed).

---

## Sources

### Primary (HIGH confidence)
- [Kalshi API Historical Data docs](https://docs.kalshi.com/getting_started/historical_data) — live/historical tier split, cutoff endpoint
- [Kalshi API Rate Limits](https://docs.kalshi.com/getting_started/rate_limits) — official rate limit tiers
- [Kalshi Get Historical Candlesticks](https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks) — candlestick schema
- [Kalshi Fee Schedule](https://kalshi.com/fee-schedule) — taker/maker fee formula
- [Kalshi Market Life Cycle](https://news.kalshi.com/p/what-is-the-market-life-cycle) — settlement delay description
- [Application of Kelly Criterion to Prediction Markets (arXiv)](https://arxiv.org/html/2412.14144v1) — position sizing, binary contract math
- [The Economics of the Kalshi Prediction Market](https://www.karlwhelan.com/Papers/Kalshi.pdf) — settlement mechanics, favorite-longshot bias
- [Event-Driven Backtesting with Python (QuantStart)](https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-I/) — ABC/Protocol patterns

### Secondary (MEDIUM confidence)
- [kalshi-python on PyPI](https://pypi.org/project/kalshi-python/) — version 2.1.4, Sep 2025 release confirmed
- [DuckDB vs SQLite comparison (BetterStack)](https://betterstack.com/community/guides/scaling-python/duckdb-vs-sqlite/) — 8x analytical performance advantage
- [quantstats on GitHub](https://github.com/ranaroussi/quantstats) — actively maintained tearsheet library
- [Vectorized vs Event-Driven Backtesting (IBKR)](https://www.interactivebrokers.com/campus/ibkr-quant-news/a-practical-breakdown-of-vector-based-vs-event-based-backtesting/) — hybrid approach rationale
- [Calibration and Skill of Kalshi (CW Data Solutions)](https://www.cwdatasolutions.com/post/calibration-and-skill-of-the-kalshi-prediction-markets) — Brier score for prediction markets
- [Statistical Arbitrage on Kalshi (Medium)](https://medium.com/@colesussmeier/statistical-arbitrage-on-kalshi-2e8ca0470eb5) — overfitting on small sample sizes
- [Maker/Taker Math on Kalshi (Substack)](https://whirligigbear.substack.com/p/makertaker-math-on-kalshi) — fee formula community analysis
- [Prediction Market Backtesting (BSIC)](https://bsic.it/well-can-we-predict-backtesting-trading-strategies-on-prediction-markets-cryptocurrency-contracts/) — liquidity and spread observations

### Tertiary (LOW confidence — community projects, unverified internals)
- [evan-kolberg/prediction-market-backtesting](https://github.com/evan-kolberg/prediction-market-backtesting) — NautilusTrader fork with Kalshi adapter; confirms ecosystem gap for binary contracts
- [braedonsaunders/homerun](https://github.com/braedonsaunders/homerun) — open-source Kalshi/Polymarket platform with strategy protocol design
- [quantgalore/kalshi-trading](https://github.com/quantgalore/kalshi-trading) — reference backtest implementation

---
*Research completed: 2026-04-04*
*Ready for roadmap: yes*
