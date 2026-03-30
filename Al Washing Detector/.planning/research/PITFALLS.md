# Domain Pitfalls

**Domain:** Autonomous AI Washing Detection / Alternative Data Signal Generation for Quantitative Finance
**Researched:** 2026-03-27
**Overall Confidence:** HIGH (multi-source verification across financial quant literature, API documentation, and operational reports)

---

## Critical Pitfalls

Mistakes that cause rewrites, financial losses, or systemic failure in an autonomous trading signal pipeline.

---

### Pitfall 1: Ghost Job Postings Poisoning the Job Signal (Signal 1)

**What goes wrong:** The job posting signal (25% weight) treats all posted AI roles as evidence of genuine hiring intent. In reality, 27-30% of LinkedIn job postings are "ghost jobs" -- postings with no intent to fill. A 2025 LiveCareer survey found 93% of HR professionals admit to posting ghost jobs at least occasionally. Companies post them for pipeline-building, market intelligence, and -- critically for this detector -- *investor optics*. A company AI washing could simultaneously post fake AI roles specifically to appear as if they are hiring AI talent, creating a false negative in the detector (looks like they are genuinely investing in AI when they are not).

**Why it happens:** The detector assumes job postings = hiring intent. This assumption fails for exactly the companies the system targets. AI washers have financial incentive to game this signal.

**Consequences:** False negatives on the highest-weighted signal. Companies actively AI washing get *lower* risk scores because their ghost AI job postings look like genuine investment. The system's most important signal becomes actively adversarial.

**Prevention:**
- Track job posting lifecycle: postings open > 90 days without fill are red flags, not green flags
- Cross-reference with LinkedIn headcount changes (did the company actually add ML engineers?)
- Weight unfilled AI roles as neutral-to-negative, not positive
- Use the *ratio* of AI roles to total roles AND the fill rate, not raw posting count
- When v2 adds paid data (Revelio Labs), validate with actual employee inflow data

**Detection:** Monitor the correlation between companies with many AI job postings and eventual SEC enforcement. If ghost-posting companies consistently score low, the signal is inverted.

**Phase mapping:** Must be addressed in Phase 1 (job signal design). Cannot be retroactively fixed without rewriting the scoring logic.

**Confidence:** HIGH -- ghost job statistics from multiple employment research firms; the adversarial incentive is a direct logical consequence of the system's thesis.

---

### Pitfall 2: Look-Ahead Bias in Signal Construction and Backtesting

**What goes wrong:** Using data that was not actually available at the time the signal claims to measure. This is the single most common backtesting error in quantitative finance, and alternative data makes it dramatically worse because publication timestamps are unreliable. Specific vectors in this system:

- **SEC filings:** 10-K filings have a reporting period end date and a filing date (often 60-90 days later). Using the reporting period date instead of the filing date means the backtest "sees" data before it was publicly available.
- **XBRL financial data:** R&D spending figures are sometimes restated retroactively. Backfilling corrections into historical records without tracking the original value creates phantom signals.
- **Patent data:** Patent applications publish 18 months after filing. Using grant dates instead of publication dates shifts the signal window.
- **Job postings:** Postings appear and disappear. Without point-in-time snapshots, you cannot reconstruct what was visible on any past date.

**Why it happens:** Convenience. It is much simpler to pull current data and assume it was always there. Every free API returns current-state data, not point-in-time data. Developers who have not built quantitative systems before do not naturally think about data-availability timestamps.

**Consequences:** Backtests show the strategy generating double-digit returns. Live trading generates losses. Research estimates over 90% of backtested strategies fail in live trading, and look-ahead bias is the primary cause. For an autonomous system with no human review, this is catastrophic -- the system believes it has a working signal and trades on it.

**Prevention:**
- **Immutable append-only snapshots** (already in PROJECT.md constraints -- enforce strictly)
- Store *two* timestamps for every data point: `as_of_date` (when the event occurred) and `observed_date` (when the system first saw it)
- Never overwrite historical data, even for corrections. Store corrections as new records
- Build the backtester to only use data with `observed_date <= backtest_date`
- For SEC filings, always use the filing date from EDGAR, not the period-of-report date
- For patents, use the publication date, not the application date or grant date

**Detection:** Compare backtest returns to paper-trading returns. Any significant divergence indicates look-ahead contamination. Also: audit a random sample of backtest dates and manually verify each data point was available on that date.

**Phase mapping:** Must be baked into the data model from Phase 1 (database schema). Retrofitting point-in-time tracking onto an existing schema is a rewrite.

**Confidence:** HIGH -- this is the most documented pitfall in quantitative finance literature (Deutsche Bank "Seven Sins" paper, CFA curriculum, multiple academic studies).

---

### Pitfall 3: Silent Pipeline Failures in an Autonomous System

**What goes wrong:** A data source silently stops returning data (API changes, rate limiting, format changes, authentication expiry), but the pipeline continues to run. The scoring engine operates on stale data without knowing it. Because no human reviews individual scores, stale signals propagate to trade execution.

Specific failure modes for this system:
- **SEC EDGAR:** Rate limit hit (10 req/sec), requests start returning 429s, retry logic backs off, some companies silently skip
- **USPTO PatentsView:** The entire platform migrated to data.uspto.gov on March 20, 2026 (7 days ago). The legacy API (api.patentsview.org) was discontinued May 2025. Any code written against the legacy API is already dead.
- **LinkedIn job scraping:** LinkedIn actively blocks scrapers. The system works for weeks, then silently returns empty results after an anti-bot update
- **GitHub API:** Token expires, falls back to unauthenticated (60 req/hr instead of 5,000), most companies silently return incomplete data

**Why it happens:** Traditional software fails loudly (crashes, exceptions). Data pipelines fail quietly -- they return empty datasets, partial results, or cached stale data. As one operational report noted: "Autonomous AI agents fail differently than traditional software. They don't crash with stack traces. They simply... stop."

**Consequences:** The autonomous system makes trading decisions based on data that is days, weeks, or months old. A company's AI washing risk changes (new 10-K filing, new patent, new hiring spree), but the system does not see it. Worse, if one signal source fails, the composite score shifts weight to remaining signals, potentially creating false high-confidence scores.

**Prevention:**
- **Data freshness checks:** Every data source must have a `last_successful_fetch` timestamp. Alert if any source exceeds its expected cadence by 2x
- **Record counts validation:** Compare today's data volume to trailing 30-day average. Alert on >20% deviation
- **Null/empty result alerting:** A fetch that returns zero results is almost always a failure, not an absence of data
- **Health check endpoint:** Each data collector must expose whether it last succeeded, when, and how many records
- **Circuit breaker pattern:** If a data source fails N times, mark that signal as "degraded" in the composite score rather than silently using stale data
- **For PatentsView specifically:** Must use the new PatentSearch API at data.uspto.gov -- any code targeting the old endpoint is broken

**Detection:** Build a daily data quality dashboard (even though the module has no UI, monitoring is not optional for autonomous systems). Track: records per source per day, staleness, error rates, API response times.

**Phase mapping:** Phase 1 must include monitoring infrastructure. This is not a "nice to have" for later -- it is a safety requirement for autonomous operation.

**Confidence:** HIGH -- verified through SEC EDGAR rate limit documentation, confirmed PatentsView migration timeline, and operational reports on autonomous system failures.

---

### Pitfall 4: FinBERT Domain Mismatch for AI Washing Detection

**What goes wrong:** The research document recommends FinBERT for earnings call sentiment analysis (Signal 4). FinBERT is pre-trained on financial text and fine-tuned for financial sentiment. But AI washing detection is not a sentiment task -- it is a *vagueness vs. specificity* task. FinBERT can tell you if text is positive, negative, or neutral. It cannot tell you if "We are leveraging AI across our enterprise" is substantive or empty.

Additionally, recent benchmarks (2024-2025) show that FinBERT and similar discriminative transformer models are being significantly outperformed by generative LLMs (particularly reasoning models) on financial NLP tasks, especially for nuanced classification like distinguishing corporate spin from genuine technical claims.

**Why it happens:** FinBERT is the "default recommendation" in financial NLP tutorials. It is genuinely useful for sentiment analysis. But AI washing detection requires a different capability -- detecting the gap between claims and evidence, which requires reasoning about specificity, not sentiment polarity.

**Consequences:** The earnings call vagueness signal (20% weight) produces noisy, unreliable scores. A CEO saying "AI is transforming our business" scores similarly to a CTO saying "We deployed a transformer-based demand forecasting model that reduced MAPE by 15%." The signal fails to discriminate.

**Prevention:**
- Use LLM-based classification (Claude API or similar) instead of FinBERT for the vagueness/specificity task
- Design a custom rubric: score each AI claim on dimensions like (a) names specific technology, (b) provides quantitative metrics, (c) describes deployment context, (d) mentions team/resources allocated
- Use FinBERT only for what it is good at: overall sentiment direction of the earnings call (a supplementary signal, not the primary vagueness detector)
- If LLM cost is a concern, use FinBERT as a cheap pre-filter and LLM for detailed classification on flagged segments

**Detection:** Manually review 50 earnings call segments that the model scored as "vague" and 50 scored as "specific." If human raters disagree with the model on >20% of cases, the model is not fit for purpose.

**Phase mapping:** Phase where NLP pipeline is built. Wrong model choice here creates technical debt that requires rewriting the entire analysis pipeline.

**Confidence:** HIGH -- FinBERT limitations verified via HuggingFace documentation and 2024-2025 financial NLP benchmarks; the sentiment-vs-specificity distinction is a straightforward analysis of the task requirements.

---

### Pitfall 5: Keyword-Based SEC Filing Analysis Missing Context

**What goes wrong:** Counting "AI" and "machine learning" mentions in 10-K filings (Signal 2) seems straightforward but produces massive false positives and false negatives. Problems:

- **Industry-specific language:** A company in the defense sector mentioning "artificial intelligence" in risk factors ("AI-enabled weapons may create regulatory risk") is not making AI claims -- it is disclosing industry risks. A semiconductor company discussing customer demand for "AI chips" is describing market conditions, not its own AI capabilities.
- **Section context matters enormously:** "AI" in the Business Description section means something completely different from "AI" in the Risk Factors section. Risk factor mentions are often boilerplate disclaimers, not claims of capability.
- **Negated mentions:** "We do not currently use artificial intelligence" counts the same as "We are a leader in artificial intelligence" in a naive keyword counter.
- **Synonym drift:** Companies increasingly use terms like "predictive analytics," "automation," "intelligent systems," "cognitive computing" to describe AI without using the exact keywords. A keyword list that was comprehensive in 2024 misses terminology shifts.

**Why it happens:** Keyword counting is the simplest NLP approach and appears to work in small samples. The failure mode is statistical -- it works on average but fails on the specific edge cases that matter most (companies near the decision boundary).

**Consequences:** The SEC filing signal (20% weight) generates noise rather than signal. Non-tech companies mentioning AI in risk disclosures get flagged. Genuine AI washers using clever language get missed. The composite score loses discriminative power.

**Prevention:**
- Parse filings by section (MD&A, Risk Factors, Business Description) and weight sections differently
- Use the `edgartools` section extractor to isolate specific 10-K sections (but note: the Item 7 / MD&A parser is known to sometimes grab the table of contents entry instead of the actual section)
- Implement negation detection ("do not use AI" should not count as an AI mention)
- Build a taxonomy that distinguishes AI *claims* (company asserting its own AI use), AI *disclosures* (risk factors, market descriptions), and AI *references* (mentioning AI as an industry trend)
- Use LLM-based classification on extracted sentences rather than raw keyword counts
- Update the keyword taxonomy quarterly as corporate language evolves

**Detection:** Sample 20 companies manually. Read their actual filings. Compare what a human would score vs. what the system scores. If divergence is >15%, the keyword approach needs augmentation.

**Phase mapping:** Phase 1 (SEC filing analysis). The keyword approach is a valid *starting point* but must be augmented before the signal can be trusted for trading decisions. Plan for LLM augmentation in Phase 2.

**Confidence:** HIGH -- industry-specific language challenges are well-documented in financial NLP literature; the section-context issue is verifiable by reading any 10-K filing.

---

### Pitfall 6: Survivorship Bias in Target Universe Construction

**What goes wrong:** The target universe builder identifies mid-cap companies currently making AI claims. But the backtest needs to include companies that *were* mid-cap and making AI claims at historical points but have since been acquired, delisted, gone bankrupt, or moved out of the mid-cap range. Excluding these companies from the backtest inflates returns.

Specific vectors:
- Companies that were AI washing and got acquired at a premium (survivorship bias makes the short signal look better -- these are cases where the short would have lost money)
- Companies that were genuinely adopting AI and grew out of mid-cap range (survivorship bias removes successes from the "low risk score" bucket, making it look like the detector is better at identifying genuine AI adopters)
- Companies that went bankrupt for non-AI reasons (these inflate the backtest if included in the short portfolio)

**Why it happens:** SEC EDGAR and all free data sources return current data. Building a historical universe requires deliberate effort to track what the universe looked like at each point in time. No free API provides point-in-time index membership.

**Consequences:** Backtest shows the strategy works. Live trading reveals the signal is weaker than expected because the historical data omitted cases where the signal would have lost money. Over 90% of academic strategies fail live due to these biases.

**Prevention:**
- Start collecting and snapshotting the universe from day one -- do not try to reconstruct history
- When backtesting, explicitly note the survivorship-free start date (signals before this date are not trustable)
- Consider purchasing point-in-time universe data for backtesting (this contradicts the "free only" constraint but is important for signal validation)
- Use the Deflated Sharpe Ratio to account for multiple-testing bias when evaluating backtest results
- Track all companies that enter and exit the universe with reason codes (acquired, delisted, market cap drift, etc.)

**Detection:** Count the number of companies in the backtest universe at each historical date. If the count is constant or increasing, survivorship bias is present (companies should be entering AND exiting).

**Phase mapping:** Must be designed into the universe builder from the beginning. Retrofitting is extremely difficult.

**Confidence:** HIGH -- survivorship bias is the most documented backtesting pitfall (CFA Level II curriculum, Deutsche Bank "Seven Sins" paper).

---

## Moderate Pitfalls

---

### Pitfall 7: Company-to-Entity Matching Across Data Sources

**What goes wrong:** The system must match the same company across SEC EDGAR (CIK numbers), USPTO PatentsView (assignee names), GitHub (organization names), LinkedIn (company pages), and earnings call providers. There is no universal company identifier across these sources.

Specific matching failures:
- SEC EDGAR uses CIK numbers and legal entity names ("ALPHABET INC" not "Google")
- USPTO uses assignee names that may be subsidiaries ("GOOGLE LLC" not "ALPHABET INC")
- GitHub organizations may use informal names ("google" not "Alphabet Inc.")
- A company may have 15 subsidiaries filing patents under different names
- Name changes after mergers/acquisitions break all historical linkages
- Patent assignees are matched using "AI-powered algorithms" that are re-run quarterly, meaning entity mappings can change retroactively

**Why it happens:** Each data source was built for a different purpose with different identifiers. Entity resolution at scale is a hard computer science problem.

**Consequences:** Signals are computed for fragments of a company. One subsidiary's patents count but another's do not. The AI washing score measures part of the company's AI investment, not all of it. Worse, inconsistent matching between signals means the composite score is combining data about different entities.

**Prevention:**
- Build an explicit company-to-entity mapping table as a first-class data structure
- Use CIK as the primary key (it is the most stable identifier), map all other identifiers to it
- For patent matching, search by both parent company name AND known subsidiaries
- Use EDGAR's `company_tickers.json` to get official ticker-to-CIK mappings
- For GitHub, maintain a manual mapping (there are only ~200-500 mid-cap companies to track -- manual is feasible at this scale)
- Revalidate mappings quarterly when new data arrives

**Detection:** For each company, verify that all 6 signals are populated. If any signal is consistently null for companies that should have data, the mapping is broken.

**Phase mapping:** Must be solved in Phase 1 alongside the universe builder. This is foundational infrastructure.

**Confidence:** HIGH -- entity resolution challenges are universally documented in alternative data literature; USPTO disambiguation caveats are documented in PatentsView API docs.

---

### Pitfall 8: Overfitting Signal Weights to Historical Data

**What goes wrong:** The scoring framework assigns weights to 6 signals (25%, 20%, 15%, 20%, 10%, 10%). If these weights are optimized on historical data (e.g., "what weights would have best predicted past SEC enforcement actions?"), the weights will overfit to the small number of historical enforcement events and fail on future data.

This is especially dangerous because:
- The number of SEC AI washing enforcement actions is very small (fewer than 10 public cases as of 2026)
- The enforcement actions are heavily concentrated in investment advisors, not mid-cap operating companies
- Optimizing weights on 5-10 data points with 6 degrees of freedom is pure overfitting

**Why it happens:** Weight optimization feels scientific. It is natural to ask "what weight combination maximizes prediction accuracy?" But with a tiny training set and many parameters, any optimization procedure finds patterns in noise.

**Consequences:** The composite score performs well in historical analysis and fails live. Worse, the team may repeatedly re-optimize weights when performance disappoints, creating a data snooping spiral.

**Prevention:**
- Use economically-motivated weights, not statistically-optimized weights. The current weights in the research document are reasonable starting points based on signal reliability, not curve-fitting.
- Lock weights for a minimum of 6 months before reviewing. Do not adjust after every losing trade.
- If validating weights, use the Deflated Sharpe Ratio (DSR) to account for the number of weight combinations tested
- Consider equal weighting as a baseline -- research shows equal-weight portfolios often beat optimized portfolios out-of-sample
- Neutralize industry and size biases in individual signals before combining (raw factor signals often embed unintended systematic exposures)

**Detection:** Compare in-sample performance to out-of-sample performance. If the Sharpe ratio drops by more than 50% out of sample, overfitting is likely.

**Phase mapping:** Scoring engine design (Phase 2 or wherever composite scoring is built). Keep weights configurable but default to economically-motivated values.

**Confidence:** HIGH -- signal overfitting is the primary documented reason quantitative strategies disappoint in practice (Bailey & Lopez de Prado, "Backtest Overfitting in Financial Markets").

---

### Pitfall 9: Timing Risk and Signal Decay for Short Positions

**What goes wrong:** AI washing is a slow-moving fundamental signal. A company can AI wash for *years* before a catalyst (SEC enforcement, earnings miss, analyst expose) causes the stock to reprice. During this time, the short position bleeds:

- **Borrow costs:** Mid-cap shorts cost 1-5% annually in borrow fees; hard-to-borrow names can cost 10-50%+
- **Short squeeze risk:** Mid-caps with high short interest are squeeze candidates, especially in retail-driven market environments
- **Opportunity cost:** Capital tied up in bleeding shorts cannot be deployed elsewhere
- **Signal decay:** The AI washing signal may be accurate but the market may not care for quarters or years

**Why it happens:** The detector identifies a fundamental truth (the company is exaggerating AI claims). But the market prices stocks on narrative momentum, not fundamental truth, and narratives can persist far longer than fundamentals suggest.

**Consequences:** The signal is "right" but the trade loses money. The autonomous system generates correct scores that lead to unprofitable positions. This is not a scoring failure but a strategy failure -- the detector works, but the market does not agree on the system's timeline.

**Prevention:**
- This is primarily a portfolio management concern (out of scope for this module), but the detector should provide data to help:
  - Include a `catalyst_proximity` field: is there an upcoming earnings call, SEC filing deadline, or known regulatory review?
  - Track score *changes* (score increasing = catalyst approaching) not just absolute levels
  - Provide confidence intervals, not just point estimates, so position sizing can account for uncertainty
- Flag in the data contract that high scores WITHOUT catalysts are "slow burn" signals vs. high scores WITH imminent catalysts
- Include `days_since_last_score_change` to help downstream modules assess signal staleness

**Detection:** Track the average time between a high-score assignment and subsequent stock price decline. If it exceeds 6 months consistently, the signal has value but needs a catalyst overlay.

**Phase mapping:** Core scoring engine (data fields). The detector module itself cannot solve timing risk, but it must provide the right data for downstream modules to manage it.

**Confidence:** HIGH -- timing risk for fundamental shorts is universally documented in quantitative finance literature.

---

### Pitfall 10: XBRL Data Inconsistencies Across Companies

**What goes wrong:** The R&D spending signal (Signal 2) relies on XBRL financial data from SEC filings. XBRL data quality is highly variable across companies:

- Companies use different XBRL taxonomies and custom extensions for the same economic concept
- "Research and development expense" may be reported as a standalone line item, embedded in "cost of goods sold," or split across multiple line items
- Some companies report R&D quarterly in 10-Qs but only annually in 10-Ks
- Companies can and do restate financial data, changing historical values
- The `edgartools` library's inline XBRL parser is "not completely developed" per its own documentation
- Parsing XBRL is computationally expensive and the library recommends caching

**Why it happens:** XBRL was designed for flexibility (companies choose their own taxonomy extensions). This flexibility means there is no guaranteed consistent mapping of R&D spending across companies.

**Consequences:** The R&D spending comparison within Signal 2 (AI mentions vs. R&D growth) compares apples to oranges. Company A reports R&D as a single line item; Company B buries it in SG&A. The system concludes Company B has no R&D spending and flags it as AI washing.

**Prevention:**
- Use the SEC's pre-processed CompanyFacts API (`data.sec.gov/api/xbrl/companyfacts/`) which normalizes some taxonomy differences
- For R&D specifically, search for multiple XBRL tags: `ResearchAndDevelopmentExpense`, `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost`, `ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost`
- Build a mapping table of company-specific XBRL quirks for the target universe (200-500 companies is manually feasible)
- Validate XBRL data against earnings call transcripts (management usually states R&D spend on calls)
- Store the raw XBRL tag used for each data point so anomalies can be investigated

**Detection:** Flag any company where R&D expense is $0 or null -- this almost always indicates a parsing/taxonomy issue, not actual zero R&D.

**Phase mapping:** Phase 1 (financial data extraction). This is a data quality problem that must be handled in the extraction layer.

**Confidence:** HIGH -- XBRL inconsistencies are documented by the SEC itself (EDGAR XBRL Guide, March 2026) and in `edgartools` library documentation.

---

### Pitfall 11: GitHub Signal Is Weak and Gameable for Non-Tech Companies

**What goes wrong:** Signal 5 (GitHub/open-source activity, 10% weight) assumes companies doing real AI work have active GitHub organizations. This assumption fails for most mid-cap companies:

- Most mid-cap non-tech companies have no GitHub presence at all -- not because they lack AI but because their AI work is proprietary
- Companies in healthcare, finance, defense, and manufacturing legitimately cannot open-source their AI work due to regulatory, competitive, or security constraints
- A company with zero GitHub repos gets penalized on this signal even if it has extensive proprietary AI capabilities
- Conversely, a company can trivially game this signal by creating a few public repos with ML-adjacent READMEs

**Why it happens:** GitHub presence correlates with AI capability in the tech sector but not in the broader mid-cap universe. The signal was designed with tech companies in mind.

**Consequences:** Massive false positive rate for non-tech mid-cap companies. Signal adds noise rather than signal to the composite score for 80%+ of the target universe.

**Prevention:**
- Apply this signal conditionally: only for companies in technology sectors where open-source presence is expected
- For non-tech companies, either zero-weight this signal or replace it with a different indicator (conference publications, AI vendor relationships from 8-K filings)
- If used, require genuine ML code in repos (check for .py files importing torch/tensorflow/sklearn, not just READMEs mentioning AI)
- Consider making this signal asymmetric: presence of genuine AI repos is a positive signal (reduces AI washing score), but absence is not a negative signal

**Detection:** Calculate the signal's discriminative power (AUC) separately for tech vs. non-tech companies. If AUC < 0.55 for non-tech, the signal is noise.

**Phase mapping:** Scoring engine design. Can be addressed by making weights sector-conditional.

**Confidence:** MEDIUM -- based on analysis of GitHub usage patterns across public companies; the CSET Georgetown study confirms limited organizational GitHub presence outside tech.

---

## Minor Pitfalls

---

### Pitfall 12: SEC EDGAR Rate Limiting Causing Incomplete Data Collection

**What goes wrong:** EDGAR limits to 10 requests/second across all machines for a given user identity. With 200-500 target companies, each needing multiple filing types, full-text search, and XBRL data, a daily batch run can easily exceed this if not carefully managed. Exceeding the limit results in temporary IP blocks, not error responses.

**Prevention:**
- Implement exponential backoff with jitter
- Spread requests across the batch window (24 hours available, no need to rush)
- Cache aggressively -- filings do not change after publication
- Set a proper User-Agent with company name and email (required by SEC)
- Use `edgartools`' built-in rate limiter (but verify it actually works -- there is a documented `Limiter.__init__()` TypeError bug in some versions)

**Phase mapping:** Phase 1 (data collection infrastructure).

---

### Pitfall 13: LinkedIn Scraping Fragility and Legal Risk

**What goes wrong:** The v1 plan uses open-source LinkedIn job scraping. LinkedIn actively fights scrapers: the `linkedin-jobs-api` package breaks whenever LinkedIn updates its HTML structure. LinkedIn has also taken legal action against scrapers (though the hiQ Labs ruling found that scraping public data is not a CFAA violation).

**Prevention:**
- Use LinkedIn's guest-facing job search API (works without authentication, less likely to break)
- Build the job signal to gracefully degrade -- if LinkedIn data is unavailable, mark the signal as degraded rather than producing false scores
- Abstract the data source behind an interface so swapping from scraping to a paid API (TheirStack, when v2 adds paid sources) is trivial
- Cache LinkedIn responses aggressively to minimize request volume

**Phase mapping:** Phase 1, but design for replaceability from day one.

---

### Pitfall 14: Correlated Signals Producing False Confidence

**What goes wrong:** The 6 signals are not independent. A company with low R&D spending (Signal 2) will also likely have few AI patents (Signal 3), no GitHub repos (Signal 5), and low compute spending (Signal 6). These four signals are measuring the same underlying thing: the company is not investing in AI. The composite score counts this one fact four times, producing a deceptively high-confidence result.

Conversely, a company that IS investing in AI will score low on all four correlated signals simultaneously, providing no hedge against any single signal being wrong.

**Prevention:**
- Analyze the correlation matrix between signals across the target universe before going live
- Consider principal component analysis or factor decoloization to identify independent information content
- Group signals into "investment evidence" (R&D, patents, GitHub, compute) and "claim evidence" (SEC mentions, earnings calls) and weight the groups rather than individual signals
- The detector's thesis is specifically about the *gap* between claims and evidence -- design the composite to measure this gap explicitly rather than summing individual signals

**Detection:** Compute pairwise correlations between the 6 signals. If any pair exceeds r=0.7, they are measuring the same thing.

**Phase mapping:** Scoring engine design. Best addressed before finalizing composite weights.

---

### Pitfall 15: PatentsView API Is in Active Transition

**What goes wrong:** As of March 20, 2026 (one week ago), PatentsView migrated to the USPTO Open Data Portal at `data.uspto.gov`. The legacy API at `api.patentsview.org` was discontinued in May 2025. Any code examples, tutorials, or library integrations targeting the old endpoint are broken. The research document's example API call targets the legacy endpoint.

**Prevention:**
- Use only the new PatentSearch API at `data.uspto.gov`
- Review the ODP PatentsView Transition Guide before writing any patent integration code
- Test patent queries immediately upon implementation -- do not assume the API format is the same

**Phase mapping:** Phase 1 (patent data integration). This is not a future risk -- it is a current reality.

**Confidence:** HIGH -- confirmed by USPTO official announcement dated March 2026.

---

### Pitfall 16: Immutable Data Storage Growing Without Bounds

**What goes wrong:** The project constraint requires append-only immutable storage (never overwrite). With daily snapshots across 200-500 companies, 6 signals, and raw data (full SEC filings, job posting snapshots, patent records), storage grows linearly and indefinitely. Within a year: tens of millions of rows in PostgreSQL and potentially hundreds of GB of raw filing text.

**Prevention:**
- Partition PostgreSQL tables by date (use native partitioning, not application-level)
- Store raw filing text in file storage (local filesystem or S3), not in PostgreSQL
- Keep only structured/extracted data in the database; reference raw files by path
- Plan retention policy: keep detailed snapshots for 2 years, aggregate older data
- Use connection pooling from day one -- daily batch jobs that open/close connections per company will hit PostgreSQL connection limits at scale

**Phase mapping:** Phase 1 (database schema design). Must be designed for growth from the start.

---

### Pitfall 17: Testing with Mocked Financial Data That Misses Edge Cases

**What goes wrong:** Unit tests mock API responses with clean, well-formatted data. But real financial data is messy:
- SEC filings contain malformed HTML, inconsistent encoding, embedded images
- XBRL data has custom extensions that vary by company
- LinkedIn returns different HTML structures for different job types
- Patent assignee names include typos, abbreviations, and legal entity suffixes

Tests pass on mocks but fail on real data.

**Prevention:**
- Maintain a "golden dataset" of real API responses (20-30 companies) stored as fixtures
- Test parsers against these real responses, not synthetic data
- Include known-difficult cases in fixtures: companies with unusual filing formats, non-English characters in names, very long filings
- Run integration tests against live APIs weekly (not in CI, but as a scheduled health check)
- Separate fast unit tests (mocks OK) from slow integration tests (real data required)

**Phase mapping:** Phase 1 (testing infrastructure). Build the golden dataset as you implement each data source.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Data collection layer | Silent failures from API changes (Pitfall 3), EDGAR rate limiting (Pitfall 12), PatentsView migration (Pitfall 15) | Build monitoring and circuit breakers from day one; verify PatentsView new API format immediately |
| SEC filing analysis | Keyword false positives (Pitfall 5), XBRL inconsistencies (Pitfall 10) | Section-aware parsing, multi-tag R&D extraction, plan for LLM augmentation |
| Job posting signal | Ghost jobs poisoning signal (Pitfall 1), LinkedIn fragility (Pitfall 13) | Track lifecycle/fill rates, design for source replaceability |
| NLP pipeline | FinBERT domain mismatch (Pitfall 4), keyword limitations (Pitfall 5) | Use LLM-based classification for specificity detection; FinBERT only for sentiment |
| Patent analysis | PatentsView API transition (Pitfall 15), company name matching (Pitfall 7) | Use new PatentSearch API; build explicit entity mapping table |
| Scoring engine | Weight overfitting (Pitfall 8), signal correlation (Pitfall 14) | Use economically-motivated weights; analyze correlation matrix before going live |
| Backtesting | Look-ahead bias (Pitfall 2), survivorship bias (Pitfall 6) | Point-in-time data model, append-only snapshots, track universe changes |
| Integration with downstream | Timing risk data fields (Pitfall 9), schema drift | Include catalyst_proximity, confidence intervals, and signal freshness in data contract |
| GitHub signal | Weak for non-tech companies (Pitfall 11) | Apply conditionally by sector; require genuine ML code, not just repo existence |
| Production operation | Silent pipeline failures (Pitfall 3), storage growth (Pitfall 16) | Data freshness monitoring, table partitioning, file-based raw storage |

---

## Sources

- [SEC EDGAR Rate Limits](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) - Rate control documentation (HIGH confidence)
- [PatentsView Migration Notice](https://www.uspto.gov/subscription-center/2026/patentsview-migrating-uspto-open-data-portal-march-20) - USPTO official migration announcement (HIGH confidence)
- [PatentsView Legacy API Discontinuation](https://patentsview.org/data-in-action/support-legacy-api-end-february-2025-switch-patentsearch-api-now) - Legacy API end notice (HIGH confidence)
- [edgartools GitHub](https://github.com/dgunning/edgartools) - Library documentation and known issues (HIGH confidence)
- [EDGAR XBRL Guide March 2026](https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide.pdf) - SEC XBRL validation specifications (HIGH confidence)
- [Seven Sins of Quantitative Investing](https://bookdown.org/palomar/portfoliooptimizationbook/8.2-seven-sins.html) - Backtesting bias catalog (HIGH confidence)
- [Survivorship Bias in Backtesting](https://www.quantifiedstrategies.com/survivorship-bias-in-backtesting/) - Quantified Strategies analysis (MEDIUM confidence)
- [Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/overfit-tools-at.pdf) - Bailey & Lopez de Prado paper (HIGH confidence)
- [Ghost Jobs Report - Entrepreneur](https://www.entrepreneur.com/business-news/one-quarter-of-jobs-posted-online-are-fake-ghost-jobs-study/496683) - 27.4% ghost job rate (MEDIUM confidence)
- [Ghost Job Epidemic - Fonzi AI](https://fonzi.ai/blog/ghost-jobs-meaning) - 30% ghost posting rate in 2026 (MEDIUM confidence)
- [FinBERT NLP Benchmarks](https://caia.org/blog/2024/03/12/comparative-analysis-nlp-approaches-chatgpt-edition) - CAIA comparative analysis (MEDIUM confidence)
- [AI Agent Silent Failures](https://dev.to/bobrenze/ai-agent-silent-failures-what-6-hours-of-undetected-downtime-taught-me-about-monitoring-3ja8) - Operational failure report (MEDIUM confidence)
- [GitHub API Rate Limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) - Official rate limit documentation (HIGH confidence)
- [LinkedIn Scraping Legal Status](https://sociavault.com/blog/linkedin-scraping-legal-guide-2026) - 2026 legal landscape (MEDIUM confidence)
- [Global GitHub Organizational Mapping](https://cset.georgetown.edu/publication/global-github-mapping-the-utilization-of-open-source-software-by-organizations/) - CSET Georgetown research (HIGH confidence)
- [Alternative Data Market Report 2026](https://www.exabel.com/blog/2026-alternative-data-market-report-out-now/) - Exabel industry report (MEDIUM confidence)
