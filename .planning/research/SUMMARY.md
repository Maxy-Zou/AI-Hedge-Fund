# Project Research Summary

**Project:** AI Washing Detector — Shared Backtesting Infrastructure
**Domain:** Vectorized backtesting engine for daily equity short signals (mid-cap universe)
**Researched:** 2026-03-28
**Confidence:** HIGH

---

## Executive Summary

This module is a vectorized backtesting framework purpose-built to evaluate the AI Washing Detector's short signal. The research consensus is clear: use `vectorbt` (open-source, Numba-accelerated) feeding from `yfinance` price data, with `quantstats-lumi` for risk metrics, Streamlit for dashboards, and matplotlib PdfPages for tearsheets. All dependencies either already exist in the fund's stack (PostgreSQL, SQLAlchemy, Prefect, tenacity, structlog) or are lightweight additions. The entire stack is free-tier for v1 — no paid data providers needed at 200-ticker scale.

The recommended architecture is a strict five-layer pipeline: Data Layer → Signal Adapter → Portfolio Simulator → Risk Engine → Reporting. Each layer has a single responsibility and communicates via typed DataFrame contracts (SignalFrame, WeightFrame, PriceFrame, PortfolioResult, MetricsBundle). The Signal Adapter is the integration boundary between the AI Washing Detector and the backtester — it accepts raw 0-100 AI Washing Risk Scores, normalizes them cross-sectionally, and converts them into portfolio weights. This clean separation allows both modules to evolve independently.

The dominant risk is bias that inflates backtest results to meaninglessness. Look-ahead bias (signal executed on the same bar it was generated) is the most dangerous — a single missing `.shift(1)` can produce a Sharpe above 2.0 from a strategy with zero real edge. Survivorship bias, unrealistic fill assumptions, and zero borrow cost modeling are close behind. For a short strategy specifically, omitting borrow cost modeling (25bps–100%+ annually) is a credibility-killer with allocators. The mitigation strategy is systematic: mandatory signal shift enforcement with unit tests, tiered borrow cost model baked into CostConfig, holdout test set reserved from day one, and all tearsheets reporting net-of-cost returns with explicit cost assumptions.

---

## Key Findings

### Recommended Stack

The backtesting stack slots cleanly alongside the existing AI Washing Detector dependencies. `vectorbt` (v0.28.5) is the clear winner for the simulation engine — its `Portfolio.from_signals()` API accepts signal DataFrames directly, supports short positions with borrow costs, and runs 200-ticker 5-year simulations in sub-second time on CPU. `yfinance` (v1.2.0) is the only viable free OHLCV source; it requires chunked downloads (50-80 tickers per call), exponential backoff via tenacity, and post-download validation to catch silent failures and 100x price errors. `quantstats-lumi` (v1.1.0, the Lumiwealth fork) replaces unmaintained `quantstats` and computes the full suite of institutional metrics from a plain pandas returns Series.

**Core technologies:**

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| vectorbt | >=0.28.5 | Vectorized backtesting engine | `from_signals()` maps directly to SignalFrame contract; Numba-accelerated; open-source |
| yfinance | >=1.2.0 | OHLCV price data | Free, no API key, bulk multi-ticker download; requires rate-limit handling |
| quantstats-lumi | >=1.1.0 | Risk metrics and tearsheet statistics | Active fork; accepts plain returns Series; computes all 15+ standard quant metrics |
| Streamlit | >=1.55.0 | Interactive dashboard | Already in fund stack; fast to build; proven with vectorbt + Plotly |
| plotly | >=6.6.0 | Interactive charts | Native Streamlit integration; time-series financial charts |
| matplotlib | >=3.10 | PDF tearsheet rendering | PdfPages, zero system dependencies, vector output |
| WeasyPrint | >=65.0 | (Optional) CSS-styled PDF | Upgrade path for investor-facing factsheets; requires Pango/Cairo |
| PostgreSQL + SQLAlchemy | >=16 / >=2.0.48 | Price cache + backtest results | Shared with Detector; same stack, no new infra |
| Prefect | >=3.6.23 | Pipeline orchestration | Already in stack; daily refresh + backtest flow |
| tenacity | >=9.1.4 | Retry logic for yfinance | Already in stack; exponential backoff for 429 errors |

**Key integration contract:** The backtester accepts `signals: pd.DataFrame` (rows = dates, columns = tickers, values = AI Washing Risk Score 0-100). Higher score = stronger short signal. vectorbt's `Portfolio.from_signals()` receives boolean `short_entries`/`short_exits` masks derived by thresholding the normalized weight matrix.

### Expected Features

**Must-have (table stakes for investor credibility):**
- Equity curve with benchmark overlay (SPY + Russell 2000)
- Core metrics table: Sharpe, Sortino, Calmar, CAGR, max drawdown, alpha, beta, win rate, turnover
- Monthly returns heatmap (calendar-format, red/green heat-mapped)
- Drawdown underwater chart
- Short borrow cost modeling (non-negotiable — omission destroys credibility with any quant allocator)
- Transaction cost modeling: commission (5 bps) + slippage (10 bps round-trip)
- Trade log CSV export (due diligence audit trail)
- In-sample / out-of-sample split (overfitting discipline — investors who know quant will ask for it)
- Streamlit dashboard assembling the above
- HTML tearsheet export

**Should-have (differentiators for serious investor conversations):**
- Rolling Sharpe (12-month window) — proves edge is persistent, not one lucky period
- Sector exposure breakdown — critical for an SEC-filing signal (proves it's not just a tech bet)
- Underwater recovery table — ranked drawdown episodes with start, trough, recovery dates
- Best/worst period table — reveals tail behavior beyond summary stats
- Configurable position sizing (equal-weight, score-proportional, inverse-volatility)
- Signal-to-return correlation (Spearman IC at 1d, 5d, 21d horizons)

**Defer to v2+:**
- Signal quantile analysis (Alphalens-style IC curves) — requires additional infrastructure
- Regime analysis — requires regime classification logic, high complexity
- PDF branded tearsheet — HTML covers demos; PDF is a polish upgrade
- Excess return decomposition — attribution framework is expensive to build correctly
- Survivorship-bias-corrected universe — use Wikipedia historical S&P 400 constituents or Norgate Data

**Hard anti-features (explicitly exclude):**
- Event-driven / intraday backtesting — zero benefit for daily signals, 10-100x complexity
- Live trading execution — turns research tool into a regulated system; hard boundary
- Jupyter notebook output — maintenance liability; Streamlit + PDF cover the use case
- Monte Carlo simulation — misleading for factor strategies; sophisticated allocators distrust it
- Walk-forward parameter optimization — creates meta-overfitting risk; use fixed date holdout instead
- Paid data provider integration — premature for v1; yfinance covers the universe

### Architecture Approach

The recommended architecture is a strict five-layer pipeline with no cross-layer shortcuts. Data flows in one direction: external signal → Signal Adapter → Portfolio Simulator ← Data Layer → Risk Engine → Reporting Layer. Each layer communicates through typed, immutable DataFrame contracts. The Signal Adapter is the critical integration seam — it decouples the AI Washing Detector from the backtesting engine, accepting arbitrary-scale raw scores and normalizing them cross-sectionally before they touch the simulator.

**Major components:**

| Component | Responsibility | Key Interface |
|-----------|---------------|---------------|
| Universe Manager | Maintain historical ticker snapshots with `as_of_date` | `universe: list[str]` |
| Data Layer | yfinance fetch, PostgreSQL cache, OHLCV validation | `PriceFrame (date x ticker x OHLCV)` |
| Signal Adapter | Validate, normalize, rank raw scores into weights | `WeightFrame (date x ticker, values [-1, +1])` |
| Cost Model | Encapsulate slippage, commission, borrow cost parameters | `CostConfig` (frozen dataclass) |
| Portfolio Simulator | Fully vectorized P&L: apply weights, subtract costs | `PortfolioResult (returns, positions, trade_log)` |
| Risk Engine | Compute all performance/risk statistics | `MetricsBundle (dict[str, float | pd.Series])` |
| Reporting Layer | Streamlit dashboard + PDF tearsheet + CSV/JSON export | UI + files |

**Key patterns:**
- All portfolio math is vectorized (`.mul()`, `.shift()`, `.cumsum()`, `.rolling()`) — no Python loops over dates
- Weights shifted by 1 period before multiplying returns — enforced in Portfolio Simulator, unit-tested
- Data Layer is append-only — `INSERT ... ON CONFLICT DO NOTHING` (fund-wide immutability convention)
- All cost and sizing parameters externalized in `CostConfig` — never hardcoded in simulator

### Critical Pitfalls

1. **Look-ahead bias (signal timing)** — Mandatory `signal.shift(1)` before multiplying by returns; enforce via unit test that verifies a signal spike on date T produces no position until T+1; add `validate_no_lookahead()` function. Warning sign: Sharpe > 2.0 on daily rebalancing.

2. **Look-ahead bias (filing timestamp)** — Record `available_date = max(filing_date + 1 business day, pipeline_completion_date)` in SignalFrame; never use raw `filing_date` as the signal index. Enforce in Signal Adapter's ingestion contract.

3. **Zero borrow cost modeling** — Apply tiered borrow cost model: <5% short interest = 0.5% annual, 5-15% = 2-3%, >15% = 5-10%. FINRA publishes bi-monthly short interest data for free. Report gross and net-of-borrow returns separately. Default CostConfig: 50 bps annual for easy-to-borrow universe assumption.

4. **Survivorship bias** — Store universe snapshots with `as_of_date` on every daily run; never retroactively update historical snapshots; treat delisted-ticker empty DataFrames as data quality events, not silent drops; document limitation explicitly in tearsheet for v1.

5. **Overfitting via full-history tuning** — Reserve the most recent 12-18 months as a never-touched holdout from day one (even before any strategy parameters are set); codify this as a project convention in a `BACKTEST_CONVENTIONS.md`; count every parameter choice as a trial.

6. **yfinance silent failures** — After each bulk download, assert that returned DataFrame covers ≥90% of requested tickers; track `coverage_ratio = tickers_with_data / tickers_requested`; alert below 95%; chunk to 50-80 tickers with 1-2s jitter; enable `repair=True`; validate daily returns: flag any single-day return >±50%.

---

## Implications for Roadmap

The architecture's build-order dependency chain (Data → Simulation → Risk → Reporting) maps directly to a 4-phase implementation. Phase 5 (Integration) wires the AI Washing Detector's live scores into the completed backtester.

### Phase 1: Data Foundation and Universe Management

**Rationale:** Nothing can be built without a reliable, validated OHLCV cache. Universe management and data validation are prerequisites for every downstream phase. The most dangerous pitfalls (survivorship bias, yfinance silent failures, price errors) all manifest here.

**Delivers:** Populated `price_ohlcv` PostgreSQL table; historical universe snapshots with `as_of_date`; data quality validation pipeline (coverage ratio tracking, 100x price error detection, split-adjustment verification)

**Addresses:** Universe management (FEATURES: benchmark comparison depends on clean price data)

**Avoids:** Pitfall 3 (survivorship bias), Pitfall 7 (yfinance adjusted price inconsistency), Pitfall 8 (silent failures), Pitfall 9 (100x currency errors)

**Research flag:** SKIP — well-documented yfinance + SQLAlchemy patterns, no novel integration

---

### Phase 2: Signal Adapter and Portfolio Simulator

**Rationale:** The simulation core is the highest-value component. The Signal Adapter defines the integration contract with the AI Washing Detector and must be established early. The Portfolio Simulator is the engine everything else depends on.

**Delivers:** `SignalAdapter` (validates, normalizes, ranks raw scores); `CostConfig` dataclass; fully vectorized `PortfolioSimulator` (weights → returns, with transaction costs and borrow costs); `PortfolioResult` output contract

**Implements:** Signal Adapter + Cost Model + Portfolio Simulator from architecture

**Avoids:** Pitfall 1 (look-ahead bias via mandatory shift), Pitfall 2 (filing timestamp bias via `available_date` enforcement), Pitfall 4 (unrealistic fills via flat 15 bps slippage model), Pitfall 5 (zero borrow cost via tiered model in CostConfig), Pitfall 11 (integer shares via dollar-weighted positioning)

**Research flag:** RESEARCH-PHASE recommended — vectorbt API details, short position configuration, `Portfolio.from_signals()` parameter tuning for short-only strategies

---

### Phase 3: Risk Engine

**Rationale:** All performance statistics are derived from `PortfolioResult.returns: pd.Series` — this layer is fully independent and can be tested with synthetic data. Quantstats-lumi computes the full metric suite from a plain returns series.

**Delivers:** `MetricsBundle` with Sharpe, Sortino, Calmar, CAGR, max drawdown, alpha, beta, information ratio, hit rate, turnover, rolling Sharpe, drawdown episodes; benchmark comparison vs SPY and Russell 2000

**Uses:** quantstats-lumi for metric computation (treat as computation library, not reporting framework); pandas for rolling windows and benchmark regression

**Avoids:** Pitfall 13 (gross returns without benchmark context), Pitfall 10 (cherry-picked period — rolling Sharpe exposes period sensitivity)

**Research flag:** SKIP — quantstats-lumi API is straightforward; standard quant metrics have no ambiguous implementation

---

### Phase 4: Reporting Layer

**Rationale:** Reporting consumes the completed MetricsBundle and PortfolioResult from prior phases. Streamlit dashboard first (fast to iterate), then tearsheet exports. PDF is a polish upgrade on top of HTML.

**Delivers:** Streamlit dashboard (equity curve, drawdown chart, rolling Sharpe, monthly heatmap, sector exposure); HTML tearsheet (quantstats `qs.reports.html()`); CSV exports (daily_returns, positions, trade_log); JSON metrics export for downstream consumers; optional PDF tearsheet via matplotlib PdfPages

**Implements:** Table-stakes features (equity curve, core metrics table, drawdown chart, monthly heatmap, trade log) + differentiators (rolling Sharpe, sector exposure, underwater recovery table)

**Avoids:** Pitfall 13 (always show net-of-cost with explicit cost assumptions in tearsheet); Pitfall 10 (rolling Sharpe by construction)

**Research flag:** SKIP — Streamlit + Plotly + quantstats patterns are well-documented with community examples

---

### Phase 5: Integration with AI Washing Detector

**Rationale:** Integration is last because it tests the contract between two independently-developed modules. The SignalFrame format was designed in Phase 2 with this integration in mind. This phase validates the end-to-end backtest is credible before any investor presentation.

**Delivers:** First end-to-end backtest run using live AI Washing Risk Scores from the Detector's PostgreSQL output; `BacktestRunner.run(signal_frame, cost_config)` CLI entry point; in-sample/out-of-sample split enforcement; holdout validation run

**Avoids:** Pitfall 6 (overfitting — holdout set evaluated once, here, after all development complete)

**Research flag:** RESEARCH-PHASE recommended — signal schema alignment between Detector's DailyScore output and SignalFrame contract, available_date handling for SEC filing pipeline latency

---

### Phase Ordering Rationale

- Data precedes simulation because vectorbt needs clean, validated prices; data quality bugs discovered late are expensive to backfill
- Signal Adapter is built alongside the Simulator (Phase 2) because the normalization pipeline is inseparable from the simulation contract — they share the WeightFrame type
- Risk Engine (Phase 3) can be developed in parallel with Phase 2 using synthetic `PortfolioResult` fixtures — it depends only on a returns Series
- Reporting (Phase 4) can begin as soon as Phase 3 produces a MetricsBundle — Streamlit development is independent of simulator internals
- Integration (Phase 5) is strictly last: the contract must be stable before wiring live data across module boundaries

### Research Flags

Needs `research-phase` during planning:
- **Phase 2 (Simulator):** vectorbt `Portfolio.from_signals()` short position API details — borrow cost integration, position direction tracking, rebalance frequency configuration
- **Phase 5 (Integration):** Signal schema bridge — Detector's `DailyScore` ORM model → SignalFrame DataFrame; `available_date` vs `filing_date` offset logic

Standard patterns (skip `research-phase`):
- **Phase 1 (Data):** yfinance bulk download + PostgreSQL append-only cache is a well-worn pattern
- **Phase 3 (Risk Engine):** quantstats-lumi API is stable; Sharpe/Sortino/drawdown computation is textbook
- **Phase 4 (Reporting):** Streamlit + Plotly + quantstats HTML tearsheet has abundant community reference implementations

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All core libraries verified on PyPI (March 2026); vectorbt, quantstats-lumi, Streamlit, Plotly, matplotlib all current. yfinance MEDIUM due to undocumented rate limits and Yahoo's unofficial API status. |
| Features | HIGH | Sourced from institutional due diligence frameworks (Resonanz Capital 2026) and IBKR practitioner content; short-strategy-specific requirements (borrow costs) well-documented from academic and broker sources |
| Architecture | HIGH | Cross-validated via VectorBT docs, QuantStart, O'Reilly Python for Algorithmic Trading; five-layer pattern is standard for vectorized backtesting |
| Pitfalls | HIGH | Look-ahead bias, survivorship bias, and borrow cost omission are universally documented; yfinance-specific bugs verified against active GitHub issues |

**Overall confidence:** HIGH

### Gaps to Address

- **Borrow cost data for tiered model:** FINRA short interest (bi-monthly) is the recommended free source. Exact ingestion pipeline for FINRA data not yet researched — address in Phase 2 planning.
- **Dividend liability on shorts:** yfinance provides dividend data inconsistently for historical periods; may require a stub estimate (e.g., 0.5% annual blanket assumption for mid-cap universe). Document as a known limitation in the tearsheet rather than attempting to model precisely.
- **Sector mapping data source:** GICS sector classification for the mid-cap universe needed for sector exposure breakdown. Yahoo Finance provides sector via `yf.Ticker().info` but this is a per-ticker synchronous call — bulk fetching 200 tickers is slow. Consider caching in PostgreSQL on first fetch.
- **Historical universe (survivorship bias):** Wikipedia historical S&P 400 constituents is the free path for v2. Scraping methodology and data quality need validation before committing to that source.
- **WeasyPrint system dependencies:** Pango/Cairo required on Linux CI. If PDF tearsheet is prioritized before v2, CI pipeline configuration needs to be addressed.

---

## Sources

### Primary (HIGH confidence)

- [vectorbt PyPI v0.28.5](https://pypi.org/project/vectorbt/) + [vectorbt docs: Portfolio.from_signals](https://vectorbt.dev/api/portfolio/base/)
- [quantstats-lumi PyPI v1.1.0](https://pypi.org/project/quantstats-lumi/) / [Lumiwealth GitHub](https://github.com/Lumiwealth/quantstats_lumi)
- [VectorBT: Vector-Based vs Event-Based Backtesting (IBKR Campus)](https://www.interactivebrokers.com/campus/ibkr-quant-news/a-practical-breakdown-of-vector-based-vs-event-based-backtesting/)
- [QuantStart: Research Backtesting in Python with pandas](https://www.quantstart.com/articles/Research-Backtesting-Environments-in-Python-with-pandas/)
- [O'Reilly: Python for Algorithmic Trading — Ch4 Vectorized Backtesting](https://www.oreilly.com/library/view/python-for-algorithmic/9781492053347/ch04.html)
- [Bailey & Lopez de Prado: Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- [IBKR Campus: Risks of Shorting — Borrow Fees](https://www.interactivebrokers.com/campus/traders-insight/securities/short-selling/the-risks-of-shorting-series-part-ii-borrow-fees/)
- [Resonanz Capital: Quant Hedge Fund Due Diligence 2026](https://resonanzcapital.com/insights/quant-hedge-funds-in-2026-a-due-diligence-framework-by-strategy-type)
- [Streamlit v1.55.0 PyPI](https://pypi.org/project/streamlit/) / [Plotly v6.6.0 PyPI](https://pypi.org/project/plotly/)
- [Matplotlib multipage PDF docs](https://matplotlib.org/stable/gallery/misc/multipage_pdf.html)

### Secondary (MEDIUM confidence)

- [yfinance PyPI v1.2.0](https://pypi.org/project/yfinance/) — rate limit issues documented in [GitHub issue #2614](https://github.com/ranaroussi/yfinance/issues/2614)
- [Frontier Ledger: Why Most Backtests Fail](https://frontierledger.ai/foundations-core-concepts/why-most-backtests-fail-overfitting-look-ahead-bias-and-data-snooping) — overfitting and lookahead bias patterns
- [Acadian Asset Management: Incredible Cost of Short Selling](https://www.acadian-asset.com/investment-insights/owenomics/the-incredible-cost-of-short-selling) — borrow cost ranges
- [Hudson & Thames backtest tutorial](https://github.com/hudson-and-thames/backtest_tutorial) — transaction cost modeling
- [Visible.vc: How to Build Tearsheets for Your Fund in 2026](https://visible.vc/blog/tear-sheets/) — tearsheet design standards

### Tertiary (contextual)

- [Alphalens GitHub](https://github.com/quantopian/alphalens) — signal quantile analysis pattern (deferred to v2)
- [vectorbt + Streamlit community pattern](https://github.com/marketcalls/VectorBT-Streamlit) — reference implementation for dashboard architecture

---

*Research completed: 2026-03-28*
*Ready for roadmap: yes*
