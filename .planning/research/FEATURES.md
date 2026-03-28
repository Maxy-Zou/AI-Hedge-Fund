# Feature Landscape: Backtesting Infrastructure

**Domain:** Quantitative fund backtesting framework (vectorized, daily signals, long/short equity)
**Researched:** 2026-03-28
**Overall confidence:** HIGH

---

## Table Stakes

Features investors expect. Missing = product feels incomplete or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Equity curve (cumulative returns) | First thing every allocator asks for — visualizes compounding over time | Low | Line chart, log and linear scale options |
| Sharpe ratio | Universal risk-adjusted return metric. Institutional baseline since 1966. A fund without a Sharpe number is not a serious fund. | Low | Annualized, excess over risk-free rate (use 3-month T-bill or 0% for simplicity) |
| Maximum drawdown | Tells investors the worst case they would have experienced. Required for any risk conversation. | Low | Peak-to-trough, absolute value, recovery date optional |
| Sortino ratio | Variant of Sharpe that only penalizes downside volatility. Preferred by many allocators for short-focused strategies. | Low | Uses downside deviation in denominator |
| Calmar ratio | Annual return / max drawdown. Required for commodity trading advisor and short-strategy presentations. | Low | Standard 36-month calculation |
| Annualized return (CAGR) | Baseline "what did this make" metric — cannot omit. | Low | Compound annual growth rate |
| Annual volatility | Risk magnitude alongside returns. Required context for Sharpe. | Low | Annualized standard deviation of daily returns |
| Benchmark comparison | S&P 500 at minimum. Investors need to see whether this adds alpha over a passive strategy. | Medium | SPY or ^GSPC. Add Russell 2000 (IWM) for mid-cap relevance. |
| Alpha and Beta vs. benchmark | Jensen's alpha measures skill beyond systematic exposure. Beta tells investors market sensitivity. | Medium | Requires regression against benchmark returns series |
| Monthly returns table / heatmap | Industry-standard presentation format. Allocators read this table first before diving into other metrics. | Medium | Calendar table: rows = years, columns = months. Heat-mapped red/green. |
| Drawdown chart | Visualizes underwater periods — how long, how deep. Paired with equity curve on every tearsheet. | Low | Plot daily drawdown from peak as negative percentage |
| Transaction cost modeling | Backtests that ignore costs are toys. Any serious allocator asks "what are your cost assumptions?" | Medium | Commission per trade (flat or bps) + slippage model (fixed or price-impact) |
| Short borrow cost modeling | Absolutely required for a short strategy. Hard-to-borrow stocks can cost 50bps–100%+ annually. Ignoring this overstates returns significantly. | Medium | Per-position daily cost accrual; configurable rate (default 50bps easy-to-borrow, configurable for hard-to-borrow) |
| Win rate / hit rate | Percentage of trades (or days) with positive returns. Investors use this to assess consistency. | Low | Count of positive return periods / total periods |
| Position count / turnover | High turnover = high costs and implementation risk. Investors ask this early. | Low | Average daily positions held, one-way turnover rate |
| Trade log / position history | Audit trail showing what the strategy held and when. Required for due diligence. | Medium | CSV export of date, ticker, direction, entry, exit, PnL |
| Out-of-sample split | Investors who know quant expect in-sample vs. out-of-sample presentation. Shows overfitting discipline. | Medium | Train/test split by date; display both periods separately in tearsheet |

---

## Differentiators

Features that elevate investor conversations beyond baseline. Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Rolling Sharpe (12-month or 24-month) | Shows whether the edge is persistent or concentrated in one lucky period. Sophisticated allocators weight this heavily. | Medium | Rolling window Sharpe plotted over time |
| Sector exposure breakdown | Demonstrates the strategy is not just a disguised sector bet. Key for a signal derived from SEC filings (tech-heavy). | Medium | Requires ticker-to-sector mapping (GICS). Bar chart of average long/short exposure per sector. |
| Signal quantile analysis (IC / factor returns by quintile) | Alphalens-style: shows whether the signal ranks stocks well, not just produces absolute returns. Proves the signal has real predictive power. | High | Information Coefficient (IC) and cumulative returns by signal quintile. Borrowed from Quantopian's Alphalens pattern. |
| Regime analysis | Shows performance in different market regimes (bull, bear, crisis). Investors want to know if short alpha survives in rising markets. | High | Classify periods by market return; compare strategy metrics per regime |
| Underwater recovery analysis | Table of all drawdown episodes: start, trough, recovery date, depth. More informative than just "max drawdown." | Medium | Ranked table of top N drawdown periods |
| Best/worst period analysis | Table of best and worst months/quarters. Reveals tail behavior beyond summary statistics. | Low | Sort monthly returns; display top/bottom N |
| Excess return vs. benchmark decomposition | Breaks alpha into: (1) stock selection, (2) short premium, (3) market timing. Differentiates skill from luck. | High | Requires attribution framework; expensive to build correctly |
| PDF tearsheet generation | A polished, branded PDF is a credibility multiplier in allocator meetings. HTML dashboards stay on your machine; PDFs travel. | High | Single-page fund factsheet. Use matplotlib/reportlab for PDF rendering. |
| Configurable position sizing methods | Shows framework sophistication. Allows sensitivity analysis: does the signal work with equal weight, signal-proportional, or risk parity? | Medium | Three modes: equal-weight, score-proportional, inverse-volatility weighting |
| Signal correlation with future returns | Spearman rank IC at multiple forward horizons (1d, 5d, 21d). Validates that the signal has real predictive content. | Medium | Requires aligned signal/return dataframes |

---

## Anti-Features

Features to explicitly NOT build for v1.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Event-driven backtesting | Tick-level simulation is 10–100x more complex for zero benefit on daily signals. The PROJECT.md explicitly excludes this. | Vectorized is correct for daily signal cadence. Revisit only if intraday signals emerge. |
| Live trading execution | Scope creep risk — turns a research tool into a regulated trading system. Enormous operational, legal, and testing burden. | Hard boundary: backtest only. Output is research artifact, not orders. |
| Jupyter notebook output | Notebooks are a maintenance liability — untested cells, kernel state issues, hard to automate. Dashboard + tearsheet cover the investor use case better. | Use Streamlit for interactive output and PDF/HTML for static tearsheets. |
| Monte Carlo simulation | Impressive but misleading for factor strategies. Path-dependence assumptions are arbitrary and sophisticated allocators distrust it. | Present out-of-sample results and regime analysis instead. |
| Walk-forward optimization | Tempting but creates meta-overfitting risk. If you can tune the walk-forward windows, you can still overfit. | Simple in-sample / out-of-sample split with fixed date boundary is more honest. |
| Multi-factor portfolio optimization | Black-Litterman, mean-variance optimization — complex, sensitive to estimation error, requires data the system doesn't have. | Equal-weight and signal-proportional sizing cover v1 investor conversations. |
| Intraday data | Not available from yfinance at scale for free. No signal operates at intraday frequency. | Daily bars are sufficient and explicitly in scope. |
| Paid data provider integration | Premature. yfinance covers the universe. Paid data adds cost, API complexity, and authentication overhead. | Re-evaluate after v1 if coverage gaps emerge. |
| Interactive portfolio construction UI | Building a portfolio optimizer UI shifts the product from "strategy backtest" to "platform" — scope explosion. | Streamlit dashboard visualizes fixed backtest output. Parameters are code/config, not UI sliders. |
| Statistical significance testing (p-values on returns) | Misleading — returns are non-IID, p-values misapplied to financial series create false confidence. | Use IC, regime analysis, and out-of-sample split to demonstrate robustness honestly. |

---

## Feature Dependencies

```
Equity curve
  requires: price data pipeline, portfolio simulation engine

Sharpe / Sortino / Calmar / Alpha / Beta
  requires: equity curve, benchmark price series, risk-free rate constant

Monthly returns heatmap
  requires: equity curve (daily returns aggregated to monthly)

Drawdown chart
  requires: equity curve

Transaction cost modeling
  requires: portfolio simulation engine (integrated, not post-hoc)

Short borrow cost modeling
  requires: transaction cost modeling, position direction tracking

Win rate / hit rate
  requires: trade log

Trade log
  requires: portfolio simulation engine with position tracking

Sector exposure breakdown
  requires: ticker-to-sector mapping (GICS), position history

Rolling Sharpe
  requires: equity curve

Signal quantile analysis
  requires: signal DataFrame, forward return computation

Out-of-sample split
  requires: date-indexed signal + price data, split configuration

PDF tearsheet
  requires: all metrics computed, chart rendering (matplotlib)

Configurable position sizing
  requires: portfolio simulation engine (parameterized)
```

---

## MVP Recommendation

**Prioritize for v1 (investor credibility minimum):**

1. Equity curve with benchmark overlay
2. Core metrics table: Sharpe, Sortino, Calmar, CAGR, max drawdown, alpha, beta, win rate, turnover
3. Monthly returns heatmap
4. Drawdown chart (underwater chart)
5. Short borrow cost modeling (non-negotiable for a short strategy — omitting this is a credibility killer)
6. Transaction cost modeling (commission + slippage)
7. Trade log export (CSV)
8. Out-of-sample split (in-sample / out-of-sample presentation)
9. Streamlit dashboard assembling the above
10. HTML tearsheet (export from Streamlit or generate directly via quantstats)

**Second priority (makes investor conversations materially better):**

- Rolling Sharpe (12-month window)
- Sector exposure breakdown (critical for SEC-filing-derived signal — proves it's not a tech bet)
- Best/worst period table
- Underwater recovery table (top drawdown episodes)

**Defer post-v1:**

- Signal quantile analysis (IC curves) — requires alphalens-style infrastructure
- Regime analysis — requires regime classification logic
- PDF tearsheet — HTML covers demos; PDF is polish
- Excess return decomposition — requires attribution framework

---

## Short Strategy Specific Notes

The AI Washing Detector is a short-only signal. This has specific feature implications that pure long-only frameworks miss:

1. **Short borrow cost is a P&L item, not optional**. Easy-to-borrow mid-caps run 25–100bps annually. Hard-to-borrow (heavily shorted names) can hit 5–20%+. Backtests that omit this systematically overstate net returns. Default assumption: 50bps/yr flat rate for mid-cap universe; expose as configurable parameter.

2. **Dividend liability on shorts**. When short, you owe dividends paid by the company to the lender. This is a cash outflow. Magnitude: small for growth mid-caps, but notable for value names. Requires corporate action data that yfinance provides inconsistently — note this as a known gap and use a dividend-stub estimate or ignore with documented assumption.

3. **Short squeeze risk is real but not modelable in backtest**. A squeeze causes realized losses that no historical simulation can replicate. Flag this in tearsheet assumptions section rather than attempting to model it.

4. **Market impact on entry/exit**. Short positions require locate + borrow before shorting. In practice, this creates execution lag. Model as 1-day delay between signal and execution (signal on date T, execute at open of T+1).

---

## Sources

- [Resonanz Capital: Quant Hedge Fund Due Diligence 2026](https://resonanzcapital.com/insights/quant-hedge-funds-in-2026-a-due-diligence-framework-by-strategy-type) — allocator expectations for quant strategies
- [Resonanz Capital: Hedge Fund Quantitative Metrics Cheatsheet](https://resonanzcapital.com/insights/understanding-hedge-fund-quantitative-metrics-a-handy-cheatsheet-for-investors) — alpha, beta, Sharpe, Sortino, Calmar definitions
- [Harvard Business School: Hedge Fund Analysis Metrics](https://online.hbs.edu/blog/post/hedge-fund-analysis) — four core metrics investors use
- [Visible.vc: How to Build Tearsheets for Your Fund in 2026](https://visible.vc/blog/tear-sheets/) — tearsheet design standards
- [Hedge Fund Law Blog: Tearsheets](https://hedgefundlawblog.com/hedge-fund-tearsheets.html) — standard tearsheet components
- [Gate 39 Media: 8 Tearsheet Design Mistakes to Avoid](https://www.gate39media.com/blog/8-hedge-fund-tear-sheet-design-mistakes-avoid) — common tearsheet errors
- [QuantStats GitHub](https://github.com/ranaroussi/quantstats) — full metrics list and tearsheet types
- [VectorBT Features](https://vectorbt.dev/getting-started/features/) — vectorized backtesting capabilities
- [Alphalens GitHub](https://github.com/quantopian/alphalens) — factor analysis tearsheet patterns
- [Acadian Asset Management: Incredible Cost of Short Selling](https://www.acadian-asset.com/investment-insights/owenomics/the-incredible-cost-of-short-selling) — borrow cost reality
- [Interactive Brokers: Risks of Shorting — Borrow Fees](https://www.interactivebrokers.com/campus/traders-insight/securities/short-selling/the-risks-of-shorting-series-part-ii-borrow-fees/) — borrow fee ranges (25bps to 100%+)
- [QuantRocket: Is There Alpha in Borrow Fees?](https://www.quantrocket.com/blog/borrow-fees-alpha/) — net vs. gross return impact on short strategies
- [QuantStart: Backtesting Frameworks in Python](https://www.quantstart.com/articles/backtesting-systematic-trading-strategies-in-python-considerations-and-open-source-frameworks/) — framework comparison
- [Frontier Ledger: Why Most Backtests Fail](https://frontierledger.ai/foundations-core-concepts/why-most-backtests-fail-overfitting-look-ahead-bias-and-data-snooping) — overfitting, lookahead bias, data snooping
- [Walk-Forward Analysis vs. Backtesting](https://surmount.ai/blogs/walk-forward-analysis-vs-backtesting-pros-cons-best-practices) — validation methodology tradeoffs
- [ML for Factor Investing: Chapter 12 Portfolio Backtesting](http://www.mlfactor.com/backtest.html) — institutional backtesting standards
