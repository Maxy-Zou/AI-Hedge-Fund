# Financial Data Sources for AI-Native Hedge Fund

**Domain:** Multi-agent AI equity/options research system
**Researched:** 2026-04-11
**Overall confidence:** MEDIUM-HIGH (free tier ecosystem well-documented; paid tier pricing changes frequently)

---

## Data Source Comparison Table

### SEC Filings & Regulatory Data

| Source | Data Type | Cost | Rate Limit | Quality | LLM-Friendly | Confidence | Notes |
|--------|-----------|------|------------|---------|---------------|------------|-------|
| **SEC EDGAR (data.sec.gov)** | XBRL facts, submissions, company data | FREE | 10 req/sec per IP | HIGH | Structured JSON | HIGH | CompanyFacts API is the single most useful endpoint -- returns every XBRL fact a company has filed in one request. No auth required, just User-Agent header. |
| **EDGAR EFTS** | Full-text search of all filings since 2001 | FREE | 10 req/sec per IP | HIGH | Text (needs chunking) | HIGH | Boolean search, no NLP. Good for finding specific disclosures. Prior codebase already used this. |
| **edgartools** (Python) | 10-K, 10-Q, 8-K parsing, XBRL, insider trades | FREE (OSS) | N/A (wraps EDGAR) | HIGH | Parsed Python objects | HIGH | Already in repo's stack. v5.26+. Handles Form 4 insider transactions, financial statements, fund holdings. Best OSS EDGAR client. |
| **sec-api.io** | 18M+ filings, full-text search, XBRL-to-JSON | Freemium ($0-$249/mo) | Varies by plan | HIGH | JSON/structured | MEDIUM | Commercial wrapper around EDGAR. Free tier limited. Not needed if using edgartools + direct EDGAR APIs. |
| **SEC Form 4** (insider trades) | Insider buy/sell transactions | FREE via EDGAR | 10 req/sec | HIGH | Structured XML | HIGH | edgartools parses these directly. Critical alternative data signal. |

### Market Data (Equities)

| Source | Data Type | Cost | Rate Limit | Quality | LLM-Friendly | Confidence | Notes |
|--------|-----------|------|------------|---------|---------------|------------|-------|
| **yfinance** | Daily/intraday OHLCV, fundamentals | FREE (unofficial) | Undocumented, aggressive 429s | MEDIUM | DataFrames | HIGH | **Fragile.** Not an official API -- scrapes Yahoo Finance. Rate limiting tightened significantly in 2024-2025. Blocks IPs after ~950 tickers. Fine for initial data load with aggressive caching/backoff. NOT suitable for production pipelines. Already in repo. |
| **Polygon.io** | Stocks, options, forex, crypto | Free: $0, Stocks Starter: $29/mo | Free: 5 req/min | HIGH | JSON/REST | HIGH | Free tier is 5 calls/min with delayed data (15-min). Paid unlocks real-time + options. Official Python client. Best quality-to-price ratio for a bootstrapped fund. |
| **Tiingo** | EOD stock prices, fundamentals, news | FREE tier available | 50 symbols/hr free | HIGH | JSON/REST | MEDIUM | 30+ years of historical stock data on free tier. Excellent data quality with proprietary EOD Price Engine validation. Good yfinance replacement for historical backtesting. |
| **Alpaca** | Stocks, options, crypto + paper trading | Free (basic) / Paid (Algo Trader Plus) | 10,000 calls/min (paid) | HIGH | JSON/REST + WebSocket | HIGH | Free tier: IEX exchange only for equities, indicative feed only for options. Paper trading is free and unlimited. 7+ years history. Best for eventual live trading integration. |
| **Alpha Vantage** | Stocks, forex, crypto, technicals | FREE: 25 req/day | 5 req/min free | MEDIUM | JSON/CSV | HIGH | **Gutted free tier.** Was 500/day, then 100/day, now 25/day. Effectively unusable for bulk operations without paying. Skip. |
| **Finnhub** | Real-time prices, fundamentals, news, alt data | FREE: 60 req/min | 30 req/sec internal cap | HIGH | JSON/REST | HIGH | Most generous free tier for real-time US market data. 1 year of historical candles per call on free tier. Earnings transcripts included. Good all-rounder. |
| **FMP (Financial Modeling Prep)** | Stocks, fundamentals, financials, earnings | FREE: 250 calls/day | 500MB/30 days bandwidth | HIGH | JSON/REST | HIGH | Good free tier for fundamentals and financial statements. Earnings transcripts on Ultimate plan ($56/mo). 5-year history on free. |
| **FRED (Federal Reserve)** | Macro economic data (rates, CPI, GDP, etc.) | FREE | Generous | HIGH | JSON/CSV | HIGH | Essential for macro context. Free API key. Multiple Python clients (fredapi, fedfred). 800K+ time series. |
| **OpenBB Platform** | Meta-aggregator across ~100 data sources | FREE (OSS) | Depends on underlying sources | Varies | Pandas DataFrames | MEDIUM | Unified interface to many sources. v4.7+ (March 2026). Python >=3.10. Could simplify multi-source data fetching but adds abstraction complexity. Consider as convenience layer, not primary. |

### Options Data

| Source | Data Type | Cost | Rate Limit | Quality | LLM-Friendly | Confidence | Notes |
|--------|-----------|------|------------|---------|---------------|------------|-------|
| **yfinance (options)** | Current options chains, IV, Greeks | FREE | Same 429 issues | LOW-MEDIUM | DataFrames | HIGH | Only available during market hours (9:30am-4pm ET). 15-min delay. No historical options data. Greeks calculated client-side. |
| **ThetaData** | Full options data, IV, Greeks, historical | FREE (EOD) / $25/mo (real-time) | Varies by tier | HIGH | Python SDK | HIGH | Best value for options data. Free tier gives historical EOD data. $25/mo Standard plan is the cheapest real-time options data available. Python SDK well-maintained. |
| **philippdubach/options-data** | Historical options chains (104 US equities/ETFs) | FREE (open dataset) | N/A (static download) | MEDIUM | Parquet files | MEDIUM | 2008-2025 data on Cloudflare R2. Polars-compatible. Limited to 104 tickers. Good for backtesting but not comprehensive. |
| **CBOE DataShop** | Official exchange options data, IV, Greeks | Paid ($$$) | N/A | HIGHEST | CSV downloads | LOW | The gold standard but expensive. Livevol Pro/Core for analytics. Not bootstrapper-friendly. |
| **Polygon.io (options)** | Options chains, trades, quotes | $79/mo (Options Starter) | Higher on paid | HIGH | JSON/REST | HIGH | Need paid tier for options. Good if already paying for stocks. |
| **ORATS** | IV, Greeks, historical options analytics | Paid ($76+/mo) | Varies | HIGHEST | JSON/REST | MEDIUM | Deep historical data with pre-calculated Greeks. Expensive but professional-grade. |

### Earnings Call Transcripts

| Source | Data Type | Cost | Rate Limit | Quality | LLM-Friendly | Confidence | Notes |
|--------|-----------|------|------------|---------|---------------|------------|-------|
| **FMP (Ultimate plan)** | Full earnings call transcripts | $56/mo | Per plan | HIGH | JSON text | HIGH | Best programmatic source for transcripts. API returns full text by symbol/quarter. The most LLM-friendly format. |
| **Finnhub** | Earnings transcripts | FREE (limited) | 60 req/min | HIGH | JSON text | MEDIUM | Some transcript access on free tier. Coverage may not be comprehensive. |
| **Seeking Alpha** | 4,500+ company transcripts/quarter | FREE to read | N/A (web scraping) | HIGH | HTML (needs parsing) | MEDIUM | **Copyright-protected.** Cannot use commercially. Scraping violates ToS. For reading only. |
| **SEC EDGAR 8-K** | Earnings-related disclosures | FREE | 10 req/sec | MEDIUM | HTML/XBRL | HIGH | Not actual transcripts but material event disclosures. Useful for detecting earnings surprises, management changes, etc. |

### News & Sentiment

| Source | Data Type | Cost | Rate Limit | Quality | LLM-Friendly | Confidence | Notes |
|--------|-----------|------|------------|---------|---------------|------------|-------|
| **GDELT Project** | Global news events, tone, sentiment | FREE | Google BigQuery free tier | HIGH | CSV/BigQuery | MEDIUM | 2.5TB+/year. Covers global news from 2015+. Use FinBERT for financial sentiment on top. Requires BigQuery or bulk downloads. Steep learning curve but immense data. |
| **Finnhub (news)** | Company & market news, sentiment scores | FREE: 60 req/min | Included in free tier | MEDIUM | JSON | HIGH | Includes pre-computed sentiment. Easiest news API to get started with. |
| **NewsAPI.org** | General news aggregation | FREE: 250 req/12hr | 1 month history only | MEDIUM | JSON | MEDIUM | Only 1 month of historical data on free tier. Not useful for backtesting. Development use only. |
| **Benzinga (Basic)** | Financial news headlines + teasers | FREE (AWS Marketplace) | Not disclosed | HIGH | JSON | MEDIUM | Free tier gives headlines + teaser, not full body. Links to full articles on Benzinga.com. Good for headline sentiment analysis. |
| **Alpaca (news)** | Market news via Benzinga | Included with Alpaca account | Per plan | HIGH | JSON | HIGH | News data included with Alpaca paper/live trading accounts. Powered by Benzinga. |

### Alternative Data

| Source | Data Type | Cost | Rate Limit | Quality | LLM-Friendly | Confidence | Notes |
|--------|-----------|------|------------|---------|---------------|------------|-------|
| **SEC Form 4** (insider trades) | Insider buy/sell transactions | FREE via EDGAR | 10 req/sec | HIGH | XML (structured) | HIGH | Strongest free alternative data signal. edgartools parses natively. Academic evidence of predictive power for cluster buys. |
| **USPTO Open Data Portal** | Patent filings, grants, applications | FREE | Generous | HIGH | XML/JSON | MEDIUM | Transitioning APIs (old retired end of 2025, new ODP rolling out 2026). Python clients: pyUSPTO, patentpy. Useful for tech company R&D signals. |
| **FRED** | Macro indicators | FREE | Generous | HIGH | JSON/CSV | HIGH | Essential macro context: interest rates, CPI, unemployment, GDP. fredapi Python package. |
| **SEC Schedule 13D/13G** | Activist investor positions (5%+ ownership) | FREE via EDGAR | 10 req/sec | HIGH | HTML/XML | HIGH | Detect activist campaigns early. edgartools can parse. |
| **SEC Form S-1** | IPO prospectuses | FREE via EDGAR | 10 req/sec | HIGH | HTML | HIGH | IPO pipeline analysis. LLM-friendly narrative text. |
| **BLS (Bureau of Labor Stats)** | Employment data, wages, CPI components | FREE | Generous | HIGH | JSON | HIGH | Sector-level employment for company analysis. |
| **GitHub API** | Open-source activity (for tech companies) | FREE: 5K req/hr authenticated | Generous | MEDIUM | JSON | LOW | Already in prior codebase (AI_WASHER_GITHUB_TOKEN). Measures dev activity. Niche signal. |

---

## Free Tier Stack (Best Free-Only Combination)

Use this combination to build a complete research system at zero cost:

### Tier 0: Zero Cost, Start Today

| Layer | Source | Why This One |
|-------|--------|-------------|
| **SEC Filings** | EDGAR APIs + edgartools | Already in repo. CompanyFacts for structured financials, EFTS for full-text search, edgartools for parsing 10-K/10-Q/8-K/Form 4. Zero cost, high quality. |
| **Equity Prices** | yfinance (with aggressive caching) | Already in repo. Download once, cache to PostgreSQL, never re-fetch same date range. Use tenacity retry with exponential backoff. Accept the fragility for initial data load. |
| **Equity Prices (backup)** | Tiingo free tier | When yfinance gets rate-limited, fall back to Tiingo. 50 symbols/hr is slow but reliable. 30+ years of history. |
| **Real-time Quotes** | Finnhub free tier | 60 req/min is generous. Real-time US prices (slight delay for free users). Company news with sentiment scores included. |
| **Fundamentals** | FMP free tier | 250 calls/day covers daily research needs. Financial statements, ratios, company profiles. 5-year history. |
| **Macro Data** | FRED | Free API key. Essential for interest rates, CPI, GDP context. Use fredapi Python package. |
| **Insider Trades** | SEC Form 4 via edgartools | Free, high-quality, proven alpha signal. Detect insider cluster buys. Already architected in prior codebase. |
| **Patent Data** | USPTO Open Data Portal | Free. Monitor tech company R&D pipeline. pyUSPTO or patentpy Python packages. |
| **News Sentiment** | Finnhub (news endpoint) | Included in free tier. Pre-computed sentiment scores. Simplest integration path. |
| **Options (basic)** | yfinance | Current chains during market hours. No historical. Enough for LLM agents to reason about options positioning. |
| **Options (historical)** | ThetaData free EOD | Historical end-of-day options data for backtesting. Free account required. |

**Total cost: $0/month**

### What This Stack CAN Do
- LLM agents analyze SEC filings (10-K, 10-Q, 8-K) for qualitative insights
- Structured XBRL financial data for quantitative screening
- Daily OHLCV prices for backtesting (5+ years)
- Insider trading signal detection
- Basic news sentiment
- Macro environment context
- Current options chains for volatility analysis

### What This Stack CANNOT Do
- Real-time intraday trading signals (yfinance delays, rate limits)
- Historical options backtesting at scale (limited to 104 tickers on philippdubach dataset)
- Comprehensive earnings call transcript analysis (no free full-transcript API)
- High-frequency data (tick-level, sub-second)
- Survivorship-bias-free historical universes (need Norgate or similar)

---

## Recommended Paid Upgrades (Priority Order)

When budget allows, add these in order of impact-per-dollar:

### Priority 1: Polygon.io Stocks Starter ($29/mo) -- FIRST UPGRADE

**Why:** Replaces yfinance's fragility with a real, official API. Unlimited historical daily OHLCV. 15-min delayed real-time. Corporate actions properly adjusted. No IP blocking. Python client library.

**What it unlocks:**
- Reliable data pipeline that does not break randomly
- Proper split/dividend adjustments
- All US exchanges (not just IEX)
- REST + WebSocket

### Priority 2: FMP Ultimate ($56/mo) -- EARNINGS TRANSCRIPTS

**Why:** Full earnings call transcripts via API. This is the single highest-value dataset for LLM agents -- earnings calls contain forward-looking management commentary that LLMs excel at analyzing.

**What it unlocks:**
- Full earnings call transcripts (programmatic, LLM-ready)
- ETF/mutual fund/13F holdings data
- 1-minute intraday candles
- Global market coverage

### Priority 3: ThetaData Standard ($25/mo) -- OPTIONS RESEARCH

**Why:** Real-time options data with IV and Greeks. Cheapest professional-grade options data available. Well-maintained Python SDK.

**What it unlocks:**
- Real-time options chains with Greeks
- Historical options data for backtesting
- Volatility surface construction
- Options flow analysis for LLM agents

### Priority 4: Polygon.io Options Starter ($79/mo) -- FULL OPTIONS

**Why:** If already on Polygon for stocks, adding options keeps everything in one API. Or use ThetaData if options-focused and Polygon for stocks.

### Priority 5: Alpaca Algo Trader Plus ($TBD/mo) -- LIVE TRADING

**Why:** When ready for live trading. Full market data + brokerage in one API. Paper trading is already free. Options trading supported.

### Total Recommended Paid Stack: ~$110/mo
(Polygon Stocks $29 + FMP Ultimate $56 + ThetaData Standard $25)

This gives you: reliable equity data, earnings transcripts, options data, and everything free from Tier 0.

---

## Data Quality Gotchas

### Critical: Will Cause Wrong Backtest Results

**1. Survivorship Bias**
- **Problem:** yfinance, FMP free tier, and most free sources only return currently-listed tickers. Delisted companies (bankruptcies, acquisitions) disappear from the data. In North America, 75% of stocks trading 10 years ago are no longer listed.
- **Impact:** Backtest returns are artificially inflated because you never hold the losers that got delisted.
- **Mitigation:** Use SEC EDGAR's submissions history to build a universe of all companies that WERE listed during the backtest period. Cross-reference with Wikipedia historical S&P constituent lists. For production-grade work, Norgate Data ($TBD) provides survivorship-bias-free databases.
- **Detection:** If your backtest only contains companies that are currently successful, you have survivorship bias.

**2. Look-Ahead Bias in SEC Filings**
- **Problem:** Filing dates vs. period end dates vs. when the filing was actually available to the market.
- **Impact:** Using Q4 earnings data filed in March to make a "January" trading decision.
- **Mitigation:** Always use the filing date (filed_at / acceptedDate), not the period end date (period_of_report). edgartools exposes both. EDGAR's accepted_date field is the correct "market availability" timestamp.
- **Detection:** If your strategy seems to "predict" earnings, you have look-ahead bias.

**3. Corporate Actions (Splits & Dividends)**
- **Problem:** Raw close prices are misleading after stock splits. AAPL at $150 in 2013 is not the same as $150 today (4:1 split in 2020, 7:1 in 2014).
- **Impact:** Return calculations are wildly wrong without adjustment.
- **Mitigation:** yfinance returns adjusted close by default. Polygon and Tiingo also adjust. Always use adjusted prices for returns. Store both raw and adjusted.
- **Detection:** Look for sudden 50%+ daily price changes -- those are likely unadjusted splits.

**4. Point-in-Time Financial Data**
- **Problem:** Financial statement data gets restated. The numbers available today may differ from what was available at the time of trading.
- **Impact:** Backtest uses restated numbers that were not available to trade on.
- **Mitigation:** EDGAR's XBRL data preserves filing dates. Use the CompanyFacts API and filter by filing date, not period date. Prefer the earliest filing version, not restated versions.

### Moderate: Will Cause Inaccurate Analysis

**5. yfinance Reliability**
- **Problem:** Not an official API. Yahoo rate-limits aggressively (429 errors after ~950 tickers). IP blocks can last hours. Any Yahoo website change can break the library.
- **Impact:** Data pipelines break unpredictably. Bulk downloads fail mid-run.
- **Mitigation:** Cache everything to PostgreSQL. Never depend on yfinance for runtime queries. Download in small batches with 3-5 second delays. Use tenacity retry with exponential backoff. Have Tiingo as fallback.

**6. Delayed vs. Real-Time Data**
- **Problem:** Free tiers typically have 15-minute delays. yfinance has undocumented delays.
- **Impact:** For intraday signals, 15-min delay makes the signal stale.
- **Mitigation:** For daily strategies (which this fund targets), delayed data is fine. For intraday, need Polygon/Alpaca paid tiers.

**7. Options Data Staleness**
- **Problem:** yfinance options data only available during market hours. Greeks/IV calculated client-side with unknown models.
- **Impact:** Weekend/after-hours analysis uses stale data. Greek calculations may differ from exchange-reported values.
- **Mitigation:** Use ThetaData for reliable options data. For yfinance, only query during market hours and cache results.

### Minor: Good to Know

**8. SEC EDGAR Rate Limits**
- **Problem:** 10 req/sec is generous but can be hit during bulk downloads. First-run data collection for ~400 mid-cap companies takes 4-10 hours.
- **Mitigation:** Already handled in repo with tenacity + inter-request delays. Plan for long initial runs.

**9. Earnings Transcript Quality**
- **Problem:** Free transcripts (Seeking Alpha scraping) violate copyright. FMP free tier does not include transcripts.
- **Mitigation:** Budget for FMP Ultimate ($56/mo) when transcripts become critical. Use 8-K filings as a free proxy for material events.

**10. XBRL Taxonomy Inconsistencies**
- **Problem:** Different companies use different XBRL tags for the same concept. "Revenue" might be tagged as us-gaap:Revenues, us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax, or custom extensions.
- **Mitigation:** edgartools normalizes common concepts. For custom analysis, build a tag mapping dictionary. The CompanyFacts API groups by concept but check for alternative tags.

---

## LLM Ingestion Patterns

### Pattern 1: SEC Filing Analysis (Most LLM-Friendly)

SEC filings are the most naturally LLM-friendly financial data source. 10-K and 10-Q filings contain narrative text that LLMs analyze extremely well.

**Optimal pipeline:**
```
EDGAR EFTS (find filings) -> edgartools (parse to sections) -> Chunk by section -> LLM analysis
```

**Section-level chunking:**
- **Item 1:** Business description (analyze competitive position)
- **Item 1A:** Risk factors (identify new/removed risks vs prior filing)
- **Item 7:** MD&A (management discussion -- most predictive section)
- **Item 8:** Financial statements (extract to structured data, not LLM text)

**Chunk size:** 1,024-2,048 characters with overlap. MD&A sections are typically 15K-50K characters -- too large for single-pass analysis.

**Multi-period analysis:** Compare Item 1A risk factors between quarterly filings. New risk factors or removed risk factors are strong signals. LLMs excel at diff-style comparison.

**Confidence:** HIGH -- this pattern is well-established in production systems.

### Pattern 2: Structured Financial Data (Pre-Process for LLM)

XBRL/CompanyFacts data should NOT be fed raw to LLMs. Pre-process into summaries.

**Optimal pipeline:**
```
CompanyFacts API -> Extract key metrics -> Calculate ratios/trends -> Format as natural language summary -> LLM analysis
```

**Example natural language summary for LLM:**
```
Company: AAPL | Period: Q4 2025
Revenue: $95.4B (+8.2% YoY, +3.1% QoQ)
Gross Margin: 46.2% (vs 45.5% prior year)
Free Cash Flow: $28.1B (29.4% of revenue)
Net Debt: -$48.2B (net cash position)
R&D Spend: $7.8B (8.2% of revenue, up from 7.5%)
Trend: Revenue accelerating, margins expanding, R&D investment increasing.
```

LLMs reason much better about "revenue grew 8.2%" than about raw XBRL JSON.

**Confidence:** HIGH -- context engineering (structuring data before LLM input) is the emerging best practice, replacing raw document dumping.

### Pattern 3: Earnings Call Transcripts (Highest Alpha Potential)

Earnings calls contain forward-looking statements, management tone, analyst questions, and hedging language that LLMs are uniquely suited to analyze.

**Optimal pipeline:**
```
FMP API (transcript text) -> Split into Q&A pairs -> LLM analysis per pair -> Aggregate signals
```

**Key LLM tasks on transcripts:**
1. **Tone shift detection:** Compare management tone vs. prior quarter
2. **Hedging language:** Detect "approximately," "challenges," "uncertainty" frequency changes
3. **Forward guidance parsing:** Extract specific revenue/earnings guidance
4. **Analyst concern mapping:** What are analysts worried about?
5. **Non-answer detection:** When management deflects a question, that IS the answer

**Confidence:** MEDIUM -- requires FMP Ultimate ($56/mo) for programmatic access. Free alternatives (scraping) are legally problematic.

### Pattern 4: News Sentiment Aggregation (Supplement, Not Primary)

News is noisy. LLMs should not analyze individual articles. Aggregate first.

**Optimal pipeline:**
```
Finnhub/Benzinga (headlines + pre-computed sentiment) -> Aggregate daily per ticker -> LLM receives summary
```

**Example aggregated input for LLM:**
```
AAPL News Summary (2026-04-10):
- 12 articles, avg sentiment: 0.62 (positive)
- Key themes: iPhone 17 supply chain, India manufacturing expansion
- Notable: 2 negative articles about EU regulatory fine ($2B)
- Unusual: 3x normal article volume (typically 4/day)
```

Do NOT feed raw article text to LLMs for routine analysis. Use pre-computed sentiment scores and surface only anomalies (unusual volume, sentiment shifts, theme changes).

**Confidence:** MEDIUM -- effectiveness depends heavily on signal extraction quality.

### Pattern 5: Alternative Data Signals (Structured, Not Text)

Insider trades, patent filings, and macro data are structured. Convert to signal scores before LLM reasoning.

**Optimal pipeline:**
```
SEC Form 4 -> Detect clusters (3+ insiders buying within 2 weeks) -> Score -> LLM receives score + context
USPTO -> Track filing velocity changes -> Score -> LLM receives score + context
FRED -> Detect regime changes (rate hikes, yield curve inversion) -> LLM receives macro context
```

**Example composite input for LLM agent:**
```
Insider Signal: STRONG BUY
- 4 insiders purchased $2.3M total in last 10 days
- CEO bought 50K shares (largest personal purchase in 3 years)
- CFO bought 15K shares (first purchase since joining)

Patent Signal: ACCELERATING
- 12 patent filings in Q1 2026 (vs 4 in Q1 2025)
- 3 filings in "autonomous driving" category (new area)

Macro Context: CAUTIOUS
- Fed Funds Rate: 4.75% (holding steady)
- Yield curve: Slightly inverted (-15bp 2y-10y)
- CPI: 2.8% (above 2% target, declining trend)
```

**Confidence:** HIGH for insider trades (well-studied signal). MEDIUM for patents (niche). HIGH for macro context.

### Anti-Pattern: Do NOT Do These

| Anti-Pattern | Why Bad | What To Do Instead |
|--------------|---------|-------------------|
| Feed raw XBRL JSON to LLM | LLMs waste context on schema noise, hallucinate numbers | Pre-compute metrics, format as natural language summary |
| Scrape Seeking Alpha transcripts | Copyright violation, ToS violation, breaks randomly | Pay for FMP Ultimate or use 8-K filings as proxy |
| Use yfinance for real-time trading decisions | Delayed, unreliable, may be blocked | Use Finnhub free or Polygon paid for real-time |
| Feed full 10-K (100+ pages) in one LLM call | Exceeds context, LLM attention degrades on long docs | Chunk by section, analyze sections independently, synthesize |
| Trust LLM-computed financial ratios | LLMs make arithmetic errors on financial calculations | Compute ratios in Python, give LLM the result to reason about |
| Use un-adjusted stock prices | Splits make returns calculations wrong | Always use adjusted close for return calculations |

---

## Source Priority for Agent Consumption

For the multi-agent research system, agents should access data in this priority:

```
1. SEC EDGAR (filings + XBRL)     -- Highest quality, most LLM-friendly, free
2. Insider trades (Form 4)         -- Strong alpha signal, free
3. FRED (macro context)            -- Essential background, free
4. Equity prices (cached)          -- From PostgreSQL, pre-downloaded
5. Finnhub (news + sentiment)      -- Real-time context, free tier generous
6. FMP (fundamentals)              -- Company profiles, financial ratios, free tier
7. Options data (ThetaData/yfinance) -- Volatility/positioning context
8. Earnings transcripts (FMP paid) -- Highest alpha but requires paid tier
```

---

## API Key Requirements Summary

| Source | Auth Method | Key Location | Notes |
|--------|------------|-------------|-------|
| SEC EDGAR | User-Agent header only | `EDGAR_IDENTITY` env var | Must be `"Name email@example.com"` format |
| yfinance | None (unofficial) | N/A | No auth, just rate limit respect |
| Finnhub | API key | `FINNHUB_API_KEY` | Free key at finnhub.io |
| FMP | API key | `FMP_API_KEY` | Free key at financialmodelingprep.com |
| FRED | API key | `FRED_API_KEY` | Free key at fred.stlouisfed.org |
| Tiingo | API key | `TIINGO_API_KEY` | Free key at tiingo.com |
| Polygon.io | API key | `POLYGON_API_KEY` | Free key, paid for higher tiers |
| ThetaData | Account + API key | `THETADATA_API_KEY` | Free account for EOD data |
| Alpaca | API key + secret | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Free paper trading account |
| USPTO | None | N/A | Open Data Portal, no auth |

---

## Sources

### Official Documentation (HIGH confidence)
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) -- Official API documentation
- [SEC EDGAR EFTS FAQ](https://www.sec.gov/edgar/search/efts-faq.html) -- Full-text search documentation
- [FRED API Documentation](https://fred.stlouisfed.org/docs/api/fred/) -- Federal Reserve Economic Data
- [USPTO Open Data Portal](https://developer.uspto.gov/api-catalog) -- Patent data APIs

### Library Documentation (HIGH confidence)
- [edgartools PyPI](https://pypi.org/project/edgartools/) -- v5.28+, SEC EDGAR Python client
- [edgartools XBRL docs](https://edgartools.readthedocs.io/en/latest/getting-xbrl/) -- XBRL data extraction
- [Finnhub API Documentation](https://finnhub.io/docs/api/rate-limit) -- Rate limits and endpoints
- [fredapi PyPI](https://pypi.org/project/fredapi/) -- FRED Python client
- [OpenBB GitHub](https://github.com/OpenBB-finance/OpenBB) -- Open-source financial data platform

### Pricing Pages (MEDIUM confidence -- changes frequently)
- [Polygon.io Pricing](https://polygon.io/pricing)
- [FMP Pricing Plans](https://site.financialmodelingprep.com/pricing-plans)
- [ThetaData Pricing](https://www.thetadata.net/pricing)
- [Tiingo Pricing](https://www.tiingo.com/about/pricing)
- [Alpha Vantage Premium](https://www.alphavantage.co/premium/)
- [Alpaca Data](https://alpaca.markets/data)

### Research & Analysis (MEDIUM confidence)
- [yfinance Rate Limiting Issues](https://github.com/ranaroussi/yfinance/issues/2128) -- GitHub issue tracker
- [LLMs for Financial Document Analysis](https://intuitionlabs.ai/articles/llm-financial-document-analysis) -- Best practices
- [GDELT Project Data](https://www.gdeltproject.org/data.html) -- Global news data
- [Historical Options Data (philippdubach)](https://github.com/philippdubach/options-data) -- Free options dataset
- [Survivorship Bias in Backtesting](https://www.quantrocket.com/blog/survivorship-bias/) -- Data quality primer

### Community Sources (LOW confidence -- verify before relying on)
- [Best Financial Data APIs 2026](https://www.nb-data.com/p/best-financial-data-apis-in-2026) -- Comparison article
- [Beyond yFinance](https://medium.com/@trading.dude/beyond-yfinance-comparing-the-best-financial-data-apis-for-traders-and-developers-06a3b8bc07e2) -- API comparison
- [Best Options Data APIs 2026](https://flashalpha.com/articles/best-options-data-apis-2026) -- Options data comparison
