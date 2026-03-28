# Domain Pitfalls — Backtesting Infrastructure

**Domain:** Vectorized backtesting for daily equity signals (short-biased, mid-cap universe)
**Researched:** 2026-03-28
**Confidence:** HIGH — findings corroborated across academic literature, practitioner blogs, and official library documentation

---

## Critical Pitfalls

Mistakes that cause rewrites, make results meaningless to investors, or expose the fund to embarrassment
during due diligence.

---

### Pitfall 1: Look-Ahead Bias — Signal Executed on the Same Bar It Was Generated

**What goes wrong:** The backtest computes a score on day T using day T's closing price and then
immediately trades at that same close. In reality, a daily close signal cannot be acted on until the
*next* trading day's open or close.

**Why it happens:** Vectorized code makes it trivially easy to align signal and price on the same
timestamp. `signal_df * returns_df` with no shift is the most natural expression and the most
wrong one.

**Consequences:** Equity curves that look impossibly smooth. Sharpe ratios above 2. Results that
collapse entirely when the 1-day shift is added. Investors who ask the right question will catch it
immediately and lose all trust.

**Prevention:**
- Enforce a mandatory `signal.shift(1)` before multiplying by forward returns. Name the convention
  explicitly in code comments: "signals are always trade-date-shifted — we trade the open/close on
  T+1 using the signal computed at T's close."
- Write a unit test that verifies the shift: given a known signal spike on date T, assert that the
  position does not appear until T+1.
- Add a `validate_no_lookahead()` function that checks the signal DataFrame's effective date is
  strictly before the corresponding return date.

**Warning signs:**
- Annualized return > 30% on a long/short strategy with no obvious edge
- Sharpe > 2.0 on a daily rebalancing strategy
- Performance degrades 50%+ when you add a 1-day execution lag

**Phase:** Must be addressed in Phase 1 (backtesting engine core). Non-negotiable before any results
are shown to investors.

---

### Pitfall 2: Look-Ahead Bias — SEC Filing Data Available Before Announcement Date

**What goes wrong:** The AI Washing Detector reads SEC filings and scores companies. If the backtest
assumes a filing's score is usable on its *filing date* rather than the *date it became publicly
visible*, it is using future information.

**Why it happens:** SEC EDGAR stores filing dates. Researchers assume `filing_date == available_date`.
In reality, 10-K/10-Q filings are often filed after market close, or on a Friday. The price effect
doesn't materialize until the next trading day. Additionally, the AI Washing Detector must have
finished processing the filing before a score can be used — pipeline latency matters.

**Consequences:** Slightly inflated results that are hard to detect without checking the filing
timestamp distribution. Could represent 1-3% annualized return inflation from timing alone.

**Prevention:**
- Always record `available_date = max(filing_date + 1 business day, pipeline_completion_date)` in the
  signal DataFrame. Never use raw `filing_date` as the signal timestamp.
- Enforce this in the signal ingestion interface contract — require `available_date` not `filing_date`.
- In tests, verify that signals from filings filed after 4 PM ET are not usable until T+1.

**Warning signs:** Signal DataFrame has a column named `filing_date` being used directly as the index
without any offset applied.

**Phase:** Integration interface design (Phase 1) and signal ingestion validation layer.

---

### Pitfall 3: Survivorship Bias — Universe Contains Only Currently Existing Tickers

**What goes wrong:** The universe of mid-cap tickers is built from today's list of $2B-$10B companies.
Companies that were mid-cap from 2021-2024 but subsequently went bankrupt, were acquired, or dropped
below $2B market cap are silently excluded. Short strategies are *especially* vulnerable because
many of the best short targets end up failing — and excluding failures makes short returns look worse.

**Why it happens:** yfinance can only return data for tickers that exist today or existed long enough
to have a historical record. It silently returns empty DataFrames for delisted tickers with no error.
Fetching "today's mid-cap universe" is trivial; fetching the *historical* mid-cap universe at each
point in time is hard.

**Consequences:** Research shows survivorship bias can overstate returns by 1-3% annually for long
strategies. For short strategies, the effect is reversed — survivorship bias *understates* short
returns because you can't short the companies that actually failed.

**Prevention:**
- Acknowledge the bias explicitly in all investor-facing materials for v1.
- Store a snapshot of the universe list with each daily run, including the `as_of_date`. Do not
  retroactively update historical universe snapshots.
- Treat delisted-ticker errors from yfinance as a data quality event, log them, and preserve the
  last known data rather than dropping the ticker entirely.
- Plan a v2 upgrade path: Wikipedia historical S&P 400 constituents (free), or Norgate Data (paid,
  survivorship-bias-free back to 1991) for production use.

**Warning signs:** Universe list is regenerated fresh each day with no historical record kept. Delisted
ticker errors are silently swallowed.

**Phase:** Universe management (Phase 1) and data collection. Document limitation in the tearsheet.

---

### Pitfall 4: Unrealistic Fill Assumptions — Closing Price Without Market Impact

**What goes wrong:** Every trade fills at exactly the closing price with no slippage, no market impact,
and no partial fill risk. The strategy may assume it can trade 10% of a stock's daily volume at the
close price.

**Why it happens:** Vectorized backtesting returns the arithmetic of signal × returns. Price impact
modeling requires knowing position sizes relative to average daily volume, which adds significant
complexity.

**Consequences:** Research shows that daily rebalancing strategies with even modest transaction cost
assumptions (5 bps commission + 5 bps slippage) can lose 6%+ annually cumulatively over a decade.
For a short strategy, slippage is asymmetric: getting in is easy, but covering (buying back) during
a squeeze is extremely expensive.

**Prevention:**
- Model a flat slippage assumption of 10-15 bps round-trip (5-7.5 bps each way) as a minimum for
  mid-cap equities. This is conservative but defensible.
- Add a commission model: $0.005/share or 1 bp minimum.
- Cap position size at 1-2% of the ticker's 20-day average daily volume (ADV). Positions larger than
  this are unrealistic.
- Label all tearsheet results with the assumed cost model. Include a sensitivity table showing
  performance at 5 bps, 10 bps, and 20 bps round-trip.

**Warning signs:** Cost model is 0. Strategy turns over more than 20% of portfolio per day. No ADV
cap on position sizes.

**Phase:** Backtesting engine (Phase 1 or Phase 2). Transaction cost model must be present before
investor presentations.

---

### Pitfall 5: Unrealistic Short-Selling Assumptions — Zero Borrow Cost

**What goes wrong:** Short positions are assumed to be freely borrowable at 0% borrow rate. In
reality, borrowing shares to short costs between 25-75 bps/year for easy-to-borrow names, and can
reach 10-99% annually for hard-to-borrow names. The stocks that score highest on the AI Washing
Detector (companies making the most exaggerated AI claims) are likely to be the most heavily shorted
and thus the hardest to borrow.

**Why it happens:** Borrow costs are not included in standard price data. They require a separate
data source (Interactive Brokers, Bloomberg) or realistic assumptions.

**Consequences:** A strategy showing 15% gross returns before borrow costs might show only 8% after
realistic borrow costs. For truly hard-to-borrow names (the best short targets), borrow costs alone
can exceed 30%/year, making the trade uneconomical even if the thesis is correct.

**Prevention:**
- Apply a tiered borrow cost model based on short interest as a proxy for borrow difficulty:
  - Low short interest (< 5% of float): 0.5% annual borrow cost
  - Medium short interest (5-15% of float): 2-3% annual borrow cost
  - High short interest (> 15% of float): 5-10% annual borrow cost
- Short interest data is available free from FINRA (bi-monthly) and can be cached.
- Report gross returns and net-of-borrow returns separately in the tearsheet.
- Flag positions where estimated borrow cost exceeds the signal strength threshold.

**Warning signs:** Short portfolio shows > 15% gross annual returns with no friction — almost
certainly borrow costs are missing.

**Phase:** Transaction cost modeling phase. Document assumptions prominently.

---

### Pitfall 6: Overfitting — Parameter Tuning on the Full Historical Dataset

**What goes wrong:** The team tunes signal weights (scoring.yaml), thresholds, and backtest
parameters against the full 5-year history. The backtest looks excellent. In live trading, the
strategy fails to replicate. Academic research shows that with only 10-20 strategy variations
tested on the same data, it is possible to find a Sharpe > 1.5 from pure chance with no real edge.

**Why it happens:** The optimization loop is invisible — even "one-shot" parameter choices are
informed by seeing the outcome of previous choices. Looking at results and adjusting is overfitting
even without a formal grid search.

**Consequences:** Research shows 30-50% degradation from backtest to live is typical. Purely
statistical patterns see 50%+ decay. Presenting overfitted results to investors is fraudulent
misrepresentation.

**Prevention:**
- Reserve the most recent 12-18 months of data as a held-out test set. Never look at it during
  development. Only evaluate on it once, when the strategy is "done."
- Use walk-forward validation: train on rolling 3-year windows, test on the next 6 months.
  Report the *distribution* of out-of-sample Sharpe ratios, not the best single window.
- Count every parameter choice as a "trial" — if you've tried 5 weight combinations, discount the
  Sharpe accordingly.
- Compute the Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014) to correct for multiple testing.
- Prefer hypothesis-driven parameters (weights derived from first principles, not optimization) over
  grid-searched parameters.

**Warning signs:** Backtest Sharpe > 2.0 on mid-cap short strategy with daily signals. Parameters
were tuned after seeing results. No walk-forward results available.

**Phase:** Validation methodology must be established in Phase 1 before any metrics are published.
Walk-forward test set discipline must be codified as a project convention.

---

## Moderate Pitfalls

---

### Pitfall 7: yfinance Data Quality — Adjusted Price Inconsistency

**What goes wrong:** yfinance changed the default value of `auto_adjust` from `False` to `True`
in a non-breaking release. Code written before the change silently produces different results after
updating yfinance. Additionally, the adjusted close calculation uses an incorrect dividend value
(Yahoo includes capital gain distributions in the dividend column, inflating adjustments).

**Why it happens:** yfinance is an unofficial scraper; Yahoo Finance changes its API without notice
and yfinance must reverse-engineer the adjustments.

**Consequences:** Price series that look correct but are off by small amounts, causing spurious
returns near dividend/split dates. Difficult to detect without cross-referencing a second data source.

**Prevention:**
- Always pin the yfinance version in `pyproject.toml` and test before upgrading.
- Always explicitly pass `auto_adjust=True` — never rely on defaults.
- After downloading, run a data sanity check: flag any single-day return > ±50% as a potential
  bad adjustment (unless a real event explains it).
- Cross-validate OHLCV for 5-10 liquid tickers against a second free source (Alpha Vantage free
  tier, Stooq) on a monthly basis to catch systematic drift.
- Store raw downloaded data immutably — if Yahoo's adjustments change retroactively, you can detect
  the discrepancy by comparing against the cached version.

**Warning signs:** Periodic extreme return spikes near known dividend dates. Equity curve step-changes
that don't correspond to real news. Results change after upgrading yfinance.

**Phase:** Data collection pipeline (Phase 1). Implement validation immediately after first download.

---

### Pitfall 8: yfinance Rate Limiting and Missing Data — Silent Failures

**What goes wrong:** yfinance bulk-downloading 200-500 tickers hits Yahoo Finance's rate limiter
(HTTP 429). Some tickers return empty DataFrames with no error when they are delisted or temporarily
unavailable. The backtest silently drops those companies, introducing selection bias.

**Why it happens:** yfinance does not raise exceptions for missing data — it returns empty DataFrames.
Bulk downloads without throttling trigger 429s that result in corrupted partial datasets.

**Consequences:** Universe coverage drops without any logging. If 20 tickers fail silently per run,
results are quietly biased by which tickers happened to succeed.

**Prevention:**
- Use `yf.download()` with `threads=True` and chunk size of 50-80 tickers with 1-2 second delays
  between chunks.
- After each download batch, assert that the returned DataFrame has rows for at least 90% of
  requested tickers. Log a warning for any ticker that returned empty.
- Track a "coverage ratio" metric per daily run: `tickers_with_data / tickers_requested`. Alert if
  it falls below 95%.
- Cache downloaded data immediately so rate limit failures don't force a full re-download.
- Use exponential backoff with tenacity on 429 responses.

**Warning signs:** No logging around yfinance calls. `tickers_received != tickers_requested` never
checked. Empty DataFrame returned for delisted ticker treated identically to valid data.

**Phase:** Data collection pipeline (Phase 1).

---

### Pitfall 9: yfinance Currency Mixing and 100x Price Errors

**What goes wrong:** For some tickers (particularly non-US exchanges, ADRs, and occasionally US
tickers after corporate actions), Yahoo Finance mixes up the currency unit — reporting prices in
cents when the rest of the data is in dollars, or vice versa. This produces prices 100x higher or
lower than actual.

**Why it happens:** yfinance includes a `repair=True` option to detect and fix these, but repair
has false positives and false negatives. The underlying issue is Yahoo Finance's own data pipeline.

**Consequences:** A 100x price error on a single ticker inflates or deflates that ticker's weight
in the portfolio and produces absurd return spikes.

**Prevention:**
- Enable `repair=True` on all yfinance downloads as a first pass.
- Add a secondary validation: compare each ticker's price against the prior day's close. Flag
  single-day price changes > ±75% as requiring manual review.
- Cross-reference market cap from the downloaded price against the known target range ($2B-$10B).
  A price 100x wrong will produce an obviously impossible market cap.
- Log all flagged tickers and exclude them from the backtest until manually confirmed or
  automatically corrected by `repair=True`.

**Warning signs:** No validation step after download. Any single position shows > ±50% one-day return
without a corresponding news event.

**Phase:** Data collection and validation pipeline (Phase 1).

---

### Pitfall 10: Cherry-Picked Backtest Period — Single Favorable Regime

**What goes wrong:** The backtest is run on a period that happens to be favorable to the strategy —
e.g., a period of AI hype inflating valuations, followed by a correction. The strategy looks great
on 2021-2023 but would look different on 2015-2017. Investors conducting diligence will ask for
results across multiple regimes.

**Why it happens:** The natural instinct is to start from "when the data is most relevant" — but
this is also when the researcher knows (consciously or not) that the strategy should perform well.

**Consequences:** Results that don't generalize. Reputational damage if investors discover the period
selection was biased.

**Prevention:**
- Require a minimum of 5 years of history including at least one high-volatility period (COVID
  March 2020, or 2022 rate rise) and one low-volatility bull period.
- Explicitly run sub-period analysis in the tearsheet: show rolling 12-month Sharpe ratios.
  A valid strategy should show positive Sharpe in most rolling windows, not just the aggregate.
- Report all periods, not just the best ones.

**Warning signs:** Backtest start date is suspiciously close to a market bottom that benefits
the strategy. No rolling Sharpe analysis. No regime breakdown.

**Phase:** Reporting/tearsheet phase and validation methodology.

---

## Minor Pitfalls

---

### Pitfall 11: Integer Shares Assumption Creates Unrealistic Rebalancing Behavior

**What goes wrong:** Position sizing rounds to integer shares. For a $100K portfolio and a $200 stock,
that's only 500 shares — meaning small weight adjustments produce 0 trades (can't buy 0.3 shares),
and rebalancing is much coarser than the model assumes.

**Prevention:** Use dollar-weighted (fractional share) position sizing internally in the backtest.
Only convert to integer shares if simulating a real brokerage account. Report results in dollar terms,
not share counts.

**Phase:** Portfolio construction logic.

---

### Pitfall 12: Ignoring Corporate Actions — Mergers, Spin-offs, Index Changes

**What goes wrong:** A company in the mid-cap universe is acquired. The ticker disappears. The backtest
treats the last price as a permanent position with no return, or silently drops the ticker.

**Prevention:** When a ticker goes missing, check if it was acquired (positive outcome for the
position if it was a long, negative for a short at acquisition premium). Log all detected delistings
with their reason code. Treat M&A as a forced close at the last traded price, not a data error.

**Phase:** Universe management and data validation.

---

### Pitfall 13: Reporting Gross Returns Without Benchmark-Relative Risk

**What goes wrong:** The tearsheet shows "20% annual return" but does not show that the S&P 500
returned 25% in the same period, and the strategy had twice the drawdown. Investors expect
risk-adjusted, benchmark-relative metrics.

**Prevention:** Always report:
- Net-of-cost returns (after slippage, commission, borrow)
- Benchmark-relative returns (alpha vs. Russell 2000, equal-weight mid-cap)
- Information ratio (not just Sharpe)
- Maximum drawdown as a calendar event (when it happened, how long recovery took)
- Calmar ratio (return / max drawdown)

**Phase:** Tearsheet and reporting phase.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Data collection (yfinance bulk download) | Silent failures and rate limiting | Coverage ratio checks, exponential backoff, chunk size 50-80 |
| Universe management | Survivorship bias from using today's universe | Store historical universe snapshots with `as_of_date` |
| Signal ingestion interface | Look-ahead bias via incorrect timestamp alignment | Enforce `available_date` not `filing_date`; mandatory shift(1) |
| Backtesting engine (vectorized) | Signal executed same bar it was generated | Unit test for shift; validate_no_lookahead() |
| Transaction cost modeling | Zero slippage / zero borrow cost | Flat 10-15 bps slippage; tiered borrow cost model |
| Portfolio construction | Position sizing without ADV cap | Cap at 1-2% of 20-day ADV |
| Parameter tuning / scoring weights | Overfitting to full history | Reserve 12-18 month holdout; walk-forward validation |
| Tearsheet generation | Cherry-picked period, no benchmark | Rolling Sharpe; sub-period breakdown; risk-adjusted metrics |
| yfinance data validation | 100x price errors, bad adjustments | Repair=True + secondary sanity checks on daily returns |
| Reporting to investors | Gross returns without cost model | Always report net-of-cost with explicit cost assumptions |

---

## Research Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Look-ahead bias (signal timing) | HIGH | Well-documented in academic literature and practitioner sources; standard shift(1) fix is universally agreed upon |
| Survivorship bias | HIGH | Well-documented; free mitigation strategies available via Wikipedia historical constituents |
| yfinance auto_adjust / currency bugs | HIGH | Verified against official yfinance GitHub issues and documentation |
| yfinance rate limiting | HIGH | Active GitHub issues from 2024-2025 confirm tightened rate limits |
| Short borrow costs | HIGH | Verified against Interactive Brokers pricing pages and academic literature |
| Overfitting / walk-forward | HIGH | Bailey & Lopez de Prado research is authoritative; deflated Sharpe is standard |
| Transaction cost magnitudes | MEDIUM | 10-15 bps slippage for mid-caps is conventional wisdom, but mid-cap liquidity varies significantly |

---

## Sources

- [Python Backtesting Pain Points: Data, Execution Assumptions, and Evaluation](https://www.thehansindia.com/tech/python-backtesting-pain-points-data-execution-assumptions-and-evaluation-1057056)
- [Backtesting Biases and How To Avoid Them — Auquan/Medium](https://medium.com/auquan/backtesting-biases-and-how-to-avoid-them-776180378335)
- [Look-Ahead Bias in Backtests and How to Detect It — Michael Harris/Medium](https://mikeharrisny.medium.com/look-ahead-bias-in-backtests-and-how-to-detect-it-ad5e42d97879)
- [Why Most Backtests Fail — Frontier Ledger](https://frontierledger.ai/foundations-core-concepts/why-most-backtests-fail-overfitting-look-ahead-bias-and-data-snooping)
- [Backtest Overfitting in Financial Markets — Bailey & Lopez de Prado (PDF)](https://www.davidhbailey.com/dhbpapers/overfit-tools-at.pdf)
- [The Deflated Sharpe Ratio — Bailey & Lopez de Prado (PDF)](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- [Walk-Forward Optimization — QuantInsti](https://blog.quantinsti.com/walk-forward-optimization-introduction/)
- [yfinance Price Repair Documentation](https://ranaroussi.github.io/yfinance/advanced/price_repair.html)
- [Why Adj Close Disappeared in yfinance — JosueMonte/Medium](https://medium.com/@josue.monte/why-adj-close-disappeared-in-yfinance-and-how-to-adapt-6baebf1939f6)
- [Understanding yfinance auto_adjust=True — SoftHints](https://softhints.com/understanding-yfinance-auto_adjust-true-what-changed-and-how-to-fix-it/)
- [yfinance Bulk Download Rate Limit Issue #2614](https://github.com/ranaroussi/yfinance/issues/2614)
- [yfinance Dividends Data Incorrect Issue #2666](https://github.com/ranaroussi/yfinance/issues/2666)
- [yfinance No Data Found / Delisted Issue #1268](https://github.com/ranaroussi/yfinance/issues/1268)
- [Survivorship Bias-Free S&P 500 Dataset with Python — Teddy Koker](https://teddykoker.com/2019/05/creating-a-survivorship-bias-free-sp-500-dataset-with-python/)
- [The Price of Transaction Costs — QuantPedia](https://quantpedia.com/the-price-of-transaction-costs/)
- [Borrow Fees for Short Selling — Verdad Capital](https://verdadcap.com/archive/costly-shorts)
- [The Risks of Shorting: Borrow Fees — IBKR Campus](https://www.interactivebrokers.com/campus/traders-insight/securities/short-selling/the-risks-of-shorting-series-part-ii-borrow-fees/)
- [Backtesting Timing Alignment: Signal Shift vs Return Shift — Quantra Community](https://quantra.quantinsti.com/community/t/backtesting-timing-alignment-signal-shift-vs-return-shift/26696)
- [Look-Ahead Bias Prevention and Signal Processing — Jakub Polec/Medium](https://medium.com/@jpolec_72972/look-ahead-bias-prevention-and-signal-processing-in-quantitative-trading-9def856db5a6)
- [The Seven Sins of Quantitative Investing — Portfolio Optimization Book](https://bookdown.org/palomar/portfoliooptimizationbook/8.2-seven-sins.html)
- [The Impact of Transaction Costs and Slippage — ResearchGate](https://www.researchgate.net/publication/384458498_The_impact_of_transactions_costs_and_slippage_on_algorithmic_trading_performance)
