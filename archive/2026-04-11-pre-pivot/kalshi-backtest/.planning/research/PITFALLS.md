# Domain Pitfalls

**Domain:** Kalshi prediction market backtesting engine
**Researched:** 2026-04-04
**Confidence:** MEDIUM (Kalshi-specific data from official docs + community sources; general backtesting from HIGH-confidence quant literature)

---

## Critical Pitfalls

Mistakes that cause strategy performance to be fundamentally invalid — results look good in backtest but collapse in live trading.

---

### Pitfall 1: Resolution Look-Ahead Bias

**What goes wrong:**
A signal fires at time T, and the backtest evaluates entry/exit using the contract's final settlement value — which is only known after the event resolves (hours to days later). The engine "knows" at entry time whether the contract will settle at $1 or $0.

**Why it happens:**
When building the signal replay loop, it's tempting to join the signal timestamp against the nearest contract row, and the nearest row after close is the settlement row. If `contract.result` or `contract.close_price == 1.0` is visible in the entry context, the backtest is contaminated.

**Consequences:**
Win rates of 80-95%+ that are pure fiction. Every "entry" is retroactively placed knowing the outcome. Strategy appears to have massive edge. No amount of parameter tuning will reveal this until live trading starts.

**Prevention:**
- At signal time T, only expose price data from rows where `observed_at <= T`. The settlement row must be excluded from any feature visible at entry.
- Represent the contract result as a separate table populated only after `close_time + settlement_delay`. Never join signal context against settled rows.
- Add an explicit assertion in the replay engine: `assert signal.timestamp < contract.close_time` for any signal that is supposed to enter before resolution.
- In integration tests, verify that flipping a contract's result in the DB changes the backtest P&L for that trade.

**Detection (warning signs):**
- Win rate > 70% on any strategy that doesn't already have a proven edge
- Perfect P&L on markets you know were uncertain
- Performance disappears when you add a 1-hour lag to signal timestamps

**Phase to address:** Data ingestion schema design (Phase 1) and replay engine architecture (Phase 2). This cannot be retrofitted cheaply.

---

### Pitfall 2: Survivorship Bias from Settled-Only Market Queries

**What goes wrong:**
The data ingestion pipeline only fetches markets that are already resolved (`status=settled`). Markets that were open during the backtest window but cancelled, delisted, or had resolution disputed are silently excluded. The surviving markets skew toward "clean" events.

**Why it happens:**
Kalshi's API makes it easy to list settled markets and paginate through them. Fetching markets by date range regardless of settlement status requires a different query pattern and more storage complexity.

**Consequences:**
Overstated win rates because cancelled markets (where the strategy would have earned zero, or had capital tied up) are invisible. Strategy appears to work on a universe that was cherry-picked by history.

**Prevention:**
- Ingest ALL markets that were open during the target date range, not just settled ones. Store `status` as a column that can be `open`, `settled`, `cancelled`, `voided`.
- Model cancelled/voided markets explicitly: capital is returned but opportunity cost applies.
- When paginating the Kalshi API for historical markets, use `min_close_time` / `max_close_time` filters rather than only querying `status=settled`.

**Detection (warning signs):**
- Historical market count seems suspiciously round or clean
- All markets in DB have `status=settled`
- No cancelled or voided markets appear in data even though Kalshi occasionally voids markets for data source failure

**Phase to address:** Data ingestion schema (Phase 1). Requires explicit handling of non-settled states from day one.

---

### Pitfall 3: Treating the Midpoint Price as the Execution Price

**What goes wrong:**
The replay engine fills orders at the midpoint of the bid-ask spread (or at the last trade price), ignoring that in thin Kalshi markets the spread can be 5-20 cents wide. A strategy that looks profitable at midpoint is unprofitable when filled at the ask (for buys) or bid (for sells).

**Why it happens:**
Candlestick data from the Kalshi API gives OHLCV but not real-time order book depth. It's tempting to use `close_price` as the fill price. Kalshi is also not equities — analysts used to equity microstructure underestimate how wide prediction market spreads can be.

**Consequences:**
A strategy with 3-4 cent edge (very good in prediction markets) is completely wiped out if fills assume midpoint but actual execution costs 8-10 cents in spread. Sharpe ratios collapse. The strategy looks marginally profitable in backtest and is a consistent loser live.

**Prevention:**
- Model fills conservatively: buys fill at `ask` (or `close + half_spread`), sells fill at `bid` (or `close - half_spread`).
- For thin markets, apply a minimum spread floor of 3-5 cents even when the API shows a tighter spread — historical order book depth is not available, so conservative assumptions are required.
- Apply a per-contract liquidity filter: skip markets where the 7-day average daily volume is below a minimum threshold (e.g., 500 contracts/day).
- Store `volume` and `open_interest` in the candlestick table for liquidity filtering during replay.

**Detection (warning signs):**
- Strategy performs well on high-volume markets (elections, Fed rate decisions) but the aggregate backtest masks poor results on thin markets
- Fill price == close price in all trade log entries (realistic execution would rarely hit exactly close)

**Phase to address:** Replay engine fill model (Phase 2). Liquidity data must be stored in Phase 1.

---

### Pitfall 4: Ignoring Kalshi Fees in P&L Calculation

**What goes wrong:**
P&L is calculated as `(exit_price - entry_price) * contracts` without subtracting Kalshi's taker fee. The fee is probability-weighted: `fee = ceil(0.07 * C * P * (1 - P))` for takers. At a 50-cent contract price, this is 1.75 cents per contract. On a short-duration trade with a 3-cent price move, fees consume 58% of gross profit.

**Why it happens:**
The formula is non-intuitive (probability-weighted, not flat percentage). Developers model fees as a flat 1-2% or skip them entirely.

**Consequences:**
Gross P&L looks positive; net P&L is negative. Particularly severe for high-frequency or short-duration strategies. Strategies that "work" in backtest are consistently unprofitable live.

**Prevention:**
- Implement the exact Kalshi fee formula: `ceil(0.07 * contracts * price * (1 - price))` for taker orders. Apply on both entry AND exit legs.
- For limit (maker) orders, apply the maker fee: `ceil(0.0175 * contracts * price * (1 - price))`.
- P&L output must always report both gross and net-of-fees figures side by side.
- Include a "fee drag" metric in the strategy report: total fees paid as a percentage of gross profit.
- Add a test: assert that a round-trip trade at 50 cents deducts exactly `2 * ceil(0.07 * C * 0.5 * 0.5)` from P&L.

**Detection (warning signs):**
- Net P&L == Gross P&L in the trade log
- Sharpe looks good but average trade P&L is very small (< 5 cents) — fees will dominate
- Strategy works on high-edge markets but appears to barely break even overall

**Phase to address:** P&L engine (Phase 2). Fee formula must be in a named constant, not inlined.

---

### Pitfall 5: Binary Contract P&L Expressed as Percentage Return (Not Dollar Return)

**What goes wrong:**
A trade that buys YES at $0.05 and holds to settlement at $1.00 reports a "1900% return." Meanwhile a trade that buys YES at $0.90 and holds to settlement reports "11% return." Aggregating percentage returns across contracts with wildly different probability levels produces meaningless statistics.

**Why it happens:**
Standard finance P&L frameworks express returns as percentage of position value. For binary contracts, the implied leverage of low-probability contracts distorts every aggregate metric (CAGR, Sharpe, max drawdown).

**Consequences:**
One lucky low-probability win inflates aggregate Sharpe. Drawdown calculations are misleading. Risk-adjusted metrics become incomparable across different probability tiers.

**Prevention:**
- Primary P&L metric is always dollar P&L, not percentage return.
- When computing aggregate metrics (total return, Sharpe), use dollar-weighted returns against the total capital allocated, not per-trade percentage returns.
- Separate performance reporting by probability tier: low (< 20%), mid (20-80%), high (> 80%). Report Sharpe within each tier independently.
- Capital allocation model must normalize position size by dollar risk, not by contract count.

**Detection (warning signs):**
- Sharpe ratio > 3.0 in initial results — almost certainly a single extreme outlier inflating the metric
- Average percentage return column shows 300%+ while the equity curve is flat

**Phase to address:** Metrics calculation (Phase 2). Establish the dollar-P&L convention in the trade log schema before any metrics are built.

---

## Moderate Pitfalls

Mistakes that degrade result quality but don't invalidate the entire backtest.

---

### Pitfall 6: Strategy Overfitting on Small Event Sample Sizes

**What goes wrong:**
A strategy is optimized on, say, 12 months of Fed rate decision markets (roughly 8 events per year). With 8-12 samples, optimizing 3+ parameters will find spurious parameter combinations that fit perfectly. The in-sample Sharpe looks excellent; the out-of-sample Sharpe is near zero.

**Why it happens:**
The Kalshi universe has many event categories but most individual event types (elections, FOMC meetings, specific economic releases) have very few instances per year. A 1-year backtest window is simply too few events for statistically meaningful optimization.

**Consequences:**
Parameters that seem optimal are data mined. The strategy does not generalize. Investors see a strong backtest and expect live performance to match.

**Prevention:**
- Track sample size (number of resolved markets) explicitly in every backtest report. Flag any result with N < 30 markets as "LOW SAMPLE — not statistically significant."
- Use walk-forward validation: train on months 1-9, test on months 10-12. Require that out-of-sample Sharpe is within 50% of in-sample Sharpe before accepting a parameter set.
- Prefer fewer, more robust parameters over many tuned parameters for small samples.
- When comparing strategies, report confidence intervals on Sharpe ratios, not just point estimates.

**Detection (warning signs):**
- N < 30 trades in a backtest result
- Sharpe ratio > 2.5 on any strategy that isn't a simple rule
- Out-of-sample performance drops > 60% vs in-sample

**Phase to address:** Optimization engine and reporting (Phase 3).

---

### Pitfall 7: Timezone Mishandling for Contract Expiration

**What goes wrong:**
Kalshi uses Eastern Time for all market close and expiration times. Historical data is stored with UTC timestamps. During replay, a market that closes at "4:00 PM" on November 5th is stored as `2024-11-05T21:00:00Z` (standard time) but becomes `2024-11-05T20:00:00Z` after DST changes. A naive UTC comparison places signals in the wrong window and causes off-by-one-day errors near daylight saving transitions.

**Why it happens:**
Python's naive datetime objects don't carry timezone info. Storing all timestamps as UTC integers (epoch) without converting correctly produces silent off-by-1-hour errors during DST transitions that are hard to detect.

**Consequences:**
Signals appear to enter after contract expiration (rejected), or an entry is incorrectly assigned to the wrong trading session. Errors cluster around March and November DST transitions.

**Prevention:**
- Store all timestamps as UTC in the database (ISO 8601 with Z suffix or `TIMESTAMPTZ` in PostgreSQL).
- All business logic comparisons use timezone-aware datetime objects (`datetime.timezone.utc`, not naive datetime).
- When displaying or logging times to humans, convert to Eastern at the presentation layer only, never in business logic.
- Use `zoneinfo.ZoneInfo("America/New_York")` (Python 3.9+ stdlib) for ET conversion — do not use manual UTC offset arithmetic.
- Add a test specifically covering a signal near a DST transition date (second Sunday in March, first Sunday in November).

**Detection (warning signs):**
- Trade counts are slightly off in March and November
- Occasional "signal after expiration" rejection errors that appear only once or twice per year
- Mixed use of naive and aware datetime objects in the codebase

**Phase to address:** Data ingestion schema (Phase 1). Enforce UTC-only storage before any data is loaded.

---

### Pitfall 8: Kalshi Live/Historical API Tier Confusion

**What goes wrong:**
The Kalshi API partitions data into a "live" tier and a "historical" tier. Markets that settled before the historical cutoff timestamp must be fetched from `GET /historical/markets/{ticker}/candlesticks`, not the standard live endpoint. Querying the wrong endpoint for old data returns empty results — silently, without error. The backtest window appears to have no trades, not because the strategy didn't fire, but because the data ingestion hit the wrong endpoint.

**Why it happens:**
Developers building ingestion pipelines use the live endpoint during development (which works for recent data) and don't notice the silent gap when data reaches the historical cutoff boundary. The cutoff timestamp moves forward over time, so a pipeline that worked correctly 6 months ago starts silently dropping old data.

**Consequences:**
Incomplete historical dataset. Backtests run on partial data without warning. Metrics are computed over fewer events than expected, distorting all statistics.

**Prevention:**
- At ingestion time, always query `GET /historical/cutoff` first to get the current `market_settled_ts` cutoff.
- Route requests: markets settled before cutoff go to historical endpoint; after cutoff go to live endpoint.
- After ingestion, assert that the market count per calendar month is plausible — a month with 0 or 1 markets is a red flag.
- Store ingestion metadata: which endpoint was used, cutoff timestamp at time of fetch, response status.

**Detection (warning signs):**
- Some date ranges in the DB have suspiciously few or zero markets
- Backtest results are "too clean" — no trades for months at a time in a busy category
- API returns 200 with empty `candlesticks` array (not an error code)

**Phase to address:** Data ingestion pipeline (Phase 1).

---

### Pitfall 9: Assuming Constant Liquidity Across All Market Categories

**What goes wrong:**
Performance metrics are computed over all markets uniformly. Elections and major economic events (FOMC, CPI) have deep order books and tight spreads. Weather markets, sports, and niche crypto contracts have 1-100 cent spreads with near-zero open interest. A strategy backtest "succeeds" on the liquid markets but is implicitly assuming the same fills are achievable in illiquid markets.

**Why it happens:**
It's natural to treat all binary contracts as interchangeable since they share the same settlement mechanics. The liquidity profile is invisible in candlestick data unless volume is tracked explicitly.

**Consequences:**
Aggregate metrics look good but are dominated by a few high-liquidity events. In live trading, the strategy fires on illiquid markets where the stated fill is not achievable.

**Prevention:**
- Store `volume` and `open_interest` for every candlestick period. These are available in the Kalshi candlestick API response.
- Implement a `min_avg_daily_volume` filter in the strategy config (default: 1000 contracts/day).
- Report backtest results segmented by category: separate Sharpe/win-rate/drawdown for politics, economics, crypto, weather, sports.
- In the trade log, include the volume at fill time so each trade's liquidity assumption is auditable.

**Detection (warning signs):**
- Strategy shows high win rate on sports markets which have extremely thin order books
- Average trade size assumptions are the same across all categories
- Volume data is NULL or zero in the DB for many contracts

**Phase to address:** Data ingestion (store volume, Phase 1) and replay filter config (Phase 2).

---

## Minor Pitfalls

Issues that reduce polish or create maintenance debt but don't invalidate results.

---

### Pitfall 10: Settlement Delay Not Modeled

**What goes wrong:**
Kalshi's settlement process takes "typically 3 hours after market resolution" but can take up to 12+ hours. If a strategy has a next-event entry rule ("enter new contract immediately after prior settles"), modeling settlement as instantaneous means the strategy enters positions before capital is actually returned.

**Prevention:**
Model a configurable `settlement_delay` parameter (default: 4 hours). Capital from a settled position is only available for redeployment after `close_time + settlement_delay`.

**Phase to address:** Replay engine cash/capital model (Phase 2).

---

### Pitfall 11: Regime Blindness Across Kalshi's Growth Phase

**What goes wrong:**
Kalshi received CFTC authorization in 2020 and has grown substantially. Markets in 2021-2022 had far fewer participants and much wider spreads than markets in 2024-2025 after mainstream adoption. A backtest treating 2021 and 2025 markets as identical will over-state historical fill quality in the early period.

**Prevention:**
- Note the regime boundary: ~2024 marks when Kalshi's liquidity meaningfully deepened (post-election cycle, post-legal victory over CFTC).
- Apply a stricter liquidity filter or higher spread assumption for data before 2024.
- Report backtest results with and without the pre-2024 period so the regime sensitivity is visible.

**Phase to address:** Reporting and documentation (Phase 3). This is a disclosure issue, not a code bug.

---

### Pitfall 12: Modeling Maker Orders Without Acknowledging Fill Uncertainty

**What goes wrong:**
The strategy places limit (maker) orders to capture the lower maker fee. The backtest assumes all limit orders fill at their stated price. In thin markets, limit orders may never fill or fill partially, and this is unmodeled.

**Prevention:**
For v1, either (a) model all fills as taker orders (conservative), or (b) implement a fill probability model where limit orders fill only when candlestick data shows a trade occurred at or through the limit price and volume was sufficient.

**Phase to address:** Replay engine (Phase 2). Document the simplification explicitly.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Data ingestion schema design | Look-ahead bias baked into data model (Pitfall 1) | Separate `settled_result` from price history table; enforce `observed_at` discipline |
| Data ingestion pipeline | Live/historical API tier confusion (Pitfall 8) | Query cutoff endpoint first; validate row counts per month |
| Data ingestion pipeline | Survivorship bias from settled-only queries (Pitfall 2) | Ingest by date range, not by settled status |
| Data ingestion schema | Timezone errors (Pitfall 7) | `TIMESTAMPTZ` in PostgreSQL; UTC-only in all DB writes |
| Replay engine fill model | Midpoint pricing (Pitfall 3) | Conservative ask/bid fill model with liquidity filter |
| P&L engine | Missing fees (Pitfall 4) | Kalshi fee formula as named constant; unit tested |
| P&L engine | Percentage return distortion (Pitfall 5) | Dollar P&L as primary metric from day one |
| Metrics and reporting | Small sample overfitting (Pitfall 6) | N < 30 flag; walk-forward validation required |
| Capital model | Settlement delay (Pitfall 10) | Configurable `settlement_delay` in replay config |

---

## Sources

- [Kalshi API Rate Limits and Tiers](https://docs.kalshi.com/getting_started/rate_limits) — MEDIUM confidence (official docs, rate limit tiers)
- [Kalshi Historical Data Documentation](https://docs.kalshi.com/getting_started/historical_data) — HIGH confidence (official docs, live/historical partition)
- [Kalshi Get Historical Candlesticks Endpoint](https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks) — HIGH confidence (official API reference)
- [Kalshi Fee Schedule](https://kalshi.com/fee-schedule) — HIGH confidence (official fee formula)
- [Maker/Taker Math on Kalshi](https://whirligigbear.substack.com/p/makertaker-math-on-kalshi) — MEDIUM confidence (community analysis of fee formula)
- [The Economics of the Kalshi Prediction Market](https://www.karlwhelan.com/Papers/Kalshi.pdf) — HIGH confidence (academic paper, settlement mechanics, favorite-longshot bias)
- [Statistical Arbitrage on Kalshi](https://medium.com/@colesussmeier/statistical-arbitrage-on-kalshi-2e8ca0470eb5) — MEDIUM confidence (practitioner post, overfitting on small samples)
- [Application of the Kelly Criterion to Prediction Markets](https://arxiv.org/html/2412.14144v1) — HIGH confidence (peer-reviewed, position sizing for binary contracts)
- [The Math of Prediction Markets: Binary Options, Kelly Criterion, and CLOB Pricing Mechanics](https://navnoorbawa.substack.com/p/the-math-of-prediction-markets-binary) — MEDIUM confidence (practitioner analysis)
- [Backtesting Traps: Common Errors to Avoid](https://www.luxalgo.com/blog/backtesting-traps-common-errors-to-avoid/) — MEDIUM confidence (general backtesting, survivorship bias, look-ahead)
- [Survivorship Bias in Backtesting Explained](https://www.luxalgo.com/blog/survivorship-bias-in-backtesting-explained/) — MEDIUM confidence (general quantitative finance)
- [Prediction Market Backtesting — Bocconi Students](https://bsic.it/well-can-we-predict-backtesting-trading-strategies-on-prediction-markets-cryptocurrency-contracts/) — MEDIUM confidence (domain-specific, liquidity and spread observations)
- [Kalshi Trading Hours](https://help.kalshi.com/trading/what-are-trading-hours) — HIGH confidence (official docs, Eastern Time confirmation)
- [Kalshi Market Life Cycle](https://news.kalshi.com/p/what-is-the-market-life-cycle) — HIGH confidence (official, settlement delay description)
- [Prediction Market Fees: Inside the Fee Wars](https://defirate.com/learn/prediction-market-fees/) — MEDIUM confidence (comparative fee analysis, spread vs. stated fee)
