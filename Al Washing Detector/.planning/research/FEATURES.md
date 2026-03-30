# Feature Landscape

**Domain:** AI Washing Detection / Alternative Data Signal Generation for Autonomous Hedge Fund
**Researched:** 2026-03-27
**Overall Confidence:** MEDIUM-HIGH

This module produces daily AI Washing Risk Scores (0-100) consumed by automated trading systems with zero human review. Every feature decision is evaluated through that lens: does it increase signal reliability, reduce false positives, or prevent silent failures that would poison downstream trading decisions?

---

## Table Stakes

Features the downstream automated trading modules expect. Missing any of these = system is unreliable or unusable in production.

### Data Ingestion

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| SEC EDGAR filing ingestion (10-K, 10-Q, 8-K) | Foundation signal -- AI keyword frequency vs. R&D spending is the most robust public data source for AI washing detection. EDGAR is free, authoritative, and structured. | Medium | Use edgartools library. Must handle XBRL for financial facts and full-text for keyword analysis. Rate limit: 10 req/sec with mandatory User-Agent header (company name + email -- legal requirement). |
| XBRL financial data extraction | R&D spending, CapEx, and revenue are the denominators in the core ratio: AI_mention_growth / R&D_spend_growth. Without financial facts, keyword counting is meaningless -- you need the actions-vs-words comparison. | Low | edgartools standardizes across 32K+ filings. Map to us-gaap:ResearchAndDevelopmentExpense taxonomy. Handle missing data: not all companies report R&D as a separate line item. |
| USPTO PatentsView integration | Patent gap is a strong corroborating signal (15% weight). Free API, no auth needed, structured JSON. Zero AI patents + loud AI claims = unambiguous red flag. | Low | Simple REST calls. CPC codes G06N (ML) and G06F18 (pattern recognition) for classification. Weekly refresh is sufficient -- patents move slowly. |
| GitHub organization activity analysis | Technical reality check -- does the company actually ship ML code? Free API (5,000 req/hr with token). Reveals ground truth that filings and earnings calls can obscure. | Medium | Must map company names to GitHub orgs (entity resolution). Need repo analysis beyond just counts: language breakdown, commit recency, ML framework imports (PyTorch, TensorFlow, scikit-learn in requirements.txt). |
| Job posting ingestion (free sources) | Primary signal (25% weight) per research framework. Hiring intent is a leading indicator of genuine AI investment. University of California, Irvine research confirms hiring data leads financial disclosures by weeks. v1 uses free LinkedIn scraping via JobSpy. | High | JobSpy or linkedin-jobs-api for ingestion. Ghost posting detection, deduplication, and role classification are all required for signal quality. Fragile -- scraping targets change layouts frequently. Highest-weight signal but noisiest data source. |
| Earnings call transcript ingestion | Vagueness scoring is a 20% weight signal. Executive language reveals the gap between marketing narrative and technical reality. Research shows executives systematically sugarcoat bad news -- general sentiment models underperform without financial domain training. | Medium | EarningsCall Python library for S&P 500 coverage (free). Quarterly cadence triggered by earnings calendar. Must store raw transcripts for reprocessing as NLP improves. |
| Target universe builder | Without knowing which mid-cap companies are making AI claims, there is nothing to score. This is the entry point for the entire pipeline. | Medium | EDGAR full-text search (efts.sec.gov) for AI/ML keywords in recent filings, filtered by market cap ($2B-$10B). Cross-reference sector: non-tech companies claiming AI deserve higher scrutiny. Must handle entity resolution (CIK to ticker to company name). |

### NLP Analysis

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| AI keyword frequency analysis | Core metric: count "AI," "artificial intelligence," "machine learning," "deep learning" mentions across filing sections over 3-5 year windows. Simple but essential -- the numerator in the core ratio. | Low | Regex-based counting with section awareness. Normalize by document length. Track year-over-year growth rate, not absolute counts. A company going from 2 mentions to 200 in one year is the signal. |
| Buzzword density scoring | Distinguish vague AI claims ("AI-powered," "leveraging AI," "AI-driven solutions") from substantive claims ("deployed transformer model," "reduced error by 15%," "PyTorch-based pipeline"). The CFA Institute framework explicitly flags buzzword usage without substantiation as a primary indicator. | Medium | Build two lexicons: (1) vague/marketing terms, (2) specific/technical terms. Ratio of vague-to-specific is the signal. Apply to both filings and earnings transcripts. |
| FinBERT sentiment analysis | Financial-domain sentiment model outperforms general-purpose NLP on financial text. FinBERT achieves 57-58% classification accuracy on PEAD-relevant signals. Sentiment alone is not the signal -- the mismatch between positive sentiment and flat/declining metrics is the signal. | Medium | HuggingFace transformers library, ProsusAI/finBERT model. Run on earnings call segments and filing sections. Three-class output (positive, negative, neutral). |

### Scoring and Signal

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Composite AI Washing Risk Score (0-100) | The primary output consumed by downstream modules. Without a single composite score, the trading system cannot act on multi-dimensional analysis. | Medium | Weighted average with per-signal normalization to 0-100. Default weights: Job Postings 25%, SEC Filings 20%, Earnings Vagueness 20%, Patents 15%, GitHub 10%, Compute 10%. Weights must be configurable -- they will be tuned via backtesting. |
| Per-signal sub-scores | Trading modules need the composite, but debugging and monitoring need the breakdown. When a composite score spikes, operators must know which signal drove it. Also enables downstream modules to apply their own weighting. | Low | Each of the 6 signals produces its own 0-100 score stored alongside the composite. Essential for explainability and audit. |
| Historical score tracking (immutable snapshots) | Financial data must never be overwritten (project constraint). Append-only snapshots enable backtesting, audit trails, and regulatory compliance (SEC Rule 17a-4 spirit). Prevents silent data corruption from poisoning live scoring. | Medium | Each daily scoring run produces a new snapshot with timestamp. Never UPDATE, only INSERT. Store raw inputs alongside derived scores for full reproducibility. All monetary values as integers (cents). |
| Score interpretation thresholds | Raw 0-100 is useless without context. The trading system needs actionable categories: 0-30 (genuine), 30-60 (mixed signals), 60-80 (significant AI washing risk), 80-100 (strong short candidate). | Low | Configurable threshold boundaries stored as config. Thresholds will shift as the system is calibrated against actual outcomes (SEC enforcement actions, earnings misses). |

### Data Quality

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Job posting deduplication | Without dedup, job posting counts are inflated 2-5x due to syndication, reposting, and aggregator mirroring. Lightcast methodology shows up to 80% of raw collected jobs are duplicates. Inflated counts = false signals = bad trades. | High | Two-stage approach: (1) deterministic matching on company + title + location hash, (2) embedding similarity for near-duplicates with different wording. Research shows this approach handles most syndication noise. |
| Input validation at system boundaries | External data (API responses, scraped HTML, XBRL) is untrusted. Schema validation catches data format changes before they propagate into scoring. In an autonomous system, garbage-in = garbage-out with nobody watching. | Medium | Pydantic models for all ingested data. Validate types, ranges, required fields. Reject and log malformed records rather than silently processing bad data. |
| Company entity resolution | The same company appears as different strings across sources: "Alphabet Inc" vs "ALPHABET INC." vs "Google LLC" (subsidiary). Without resolution, signals from different sources cannot be joined, and the composite score is broken. | High | Map across CIK (SEC), assignee name (USPTO), GitHub org name, job posting employer name. Build a company master table with aliases. Handle subsidiaries (map to parent). Start with exact + fuzzy matching, improve over time. This is a known hard problem. |
| Data source availability monitoring | When EDGAR is down or LinkedIn blocks scrapers, the system must know immediately -- not discover it 3 days later when scores drift. In an autonomous system, silent data staleness is the most dangerous failure mode. | Medium | Health checks per data source on each pipeline run. Track last-successful-fetch timestamp per source. Flag when any source exceeds its expected refresh cadence. |

### Operational

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Retry logic with exponential backoff | External APIs fail transiently. Without retries, a single network blip causes a full pipeline failure. Standard practice in every production data pipeline. | Low | Use tenacity library. Configure per-source: EDGAR (conservative, respect 10 req/sec), GitHub (standard 3x retry), LinkedIn scraping (aggressive backoff due to anti-bot measures). Idempotent operations only. |
| Graceful degradation per signal | If one data source is unavailable, produce scores using available signals with re-normalized weights rather than failing entirely. A 5-signal score is better than no score. The autonomous trading system needs daily output even during partial outages. | Medium | Compute composite from available signals, adjust weights proportionally. Flag which signals were missing and attach reduced confidence. The downstream consumer must know when scores are partial. |
| Structured logging (JSON) | In an autonomous system, logs are the only debugging interface. Unstructured print statements are useless when investigating why scores changed at 3 AM. | Low | Use structlog with JSON output. Include: timestamp, company, signal, data_source, latency, errors. Correlation IDs per pipeline run for tracing. |
| Daily batch pipeline orchestration | The system must run daily without human intervention. Cron or scheduler triggers ingestion, analysis, scoring, and output in sequence with proper error handling at each stage. | Medium | APScheduler or Prefect for orchestration. Each stage independently retriable. Track pipeline run status (started, succeeded, partially_failed, failed) in the database. |

### Integration

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| PostgreSQL shared database output | Primary integration pattern per PROJECT.md. Downstream modules (portfolio management, execution, risk) query scores directly. The schema is the contract. | Medium | Well-defined schema: companies, daily_scores (append-only), signal_details, pipeline_runs. Indexes on (company_id, scored_at) for fast lookups. SQLAlchemy + Alembic for migrations. |
| Python package API | Secondary integration pattern. Other fund modules import as a library for programmatic score access without raw SQL. | Medium | Clean public API: `get_score(ticker, date)`, `get_latest_scores()`, `get_score_history(ticker, start, end)`. Return immutable dataclasses or Pydantic models. Never expose internals. |
| Structured score output format | Downstream consumers need a predictable, stable schema. Composite score, sub-scores, confidence level, data freshness per signal, timestamp -- all in a single queryable record. | Low | Define the schema once, enforce it everywhere. Include metadata: which signals contributed, which were unavailable, pipeline_run_id for traceability. |

---

## Differentiators

Features that create competitive advantage for the fund. Not expected in v1, but significantly increase signal quality or reliability when added.

### NLP Analysis (Advanced)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Earnings call speaker-level analysis | Detect CEO vs. CTO language gap: CEO hypes AI while CTO is vague or absent from AI discussion. Research shows this divergence is a strong AI washing indicator that transcript-level sentiment analysis misses entirely. | High | Requires speaker diarization (transcripts must attribute text to speakers by role). Compare sentiment and specificity between C-suite roles. Flag when CEO AI optimism is not echoed by technical leadership. |
| Filing section-aware NLP | AI mentioned in "Risk Factors" (defensive/CYA language) vs. "Business Description" (claims) vs. "MD&A" (operational reality) carries different weight. Section context changes signal meaning substantially. | Medium | edgartools supports section extraction from 10-K filings. Build section-specific scoring: Risk Factors mentions are defensive; MD&A mentions carry highest weight as closest to operational reality. |
| Temporal keyword trajectory analysis | Track AI keyword frequency across 3-5 years of filings. A company going from 2 mentions to 200 in one year with flat R&D is a very different signal than one gradually increasing alongside R&D growth. The trajectory shape matters as much as the current level. | Medium | Time-series analysis of per-filing keyword counts. Compute growth rate, acceleration, inflection points. Normalize against industry peers for context. |
| Vagueness-to-specificity ratio (granular) | Go beyond buzzword counting: score each individual AI-related claim on a vagueness scale. "AI-powered" scores high vagueness; "deployed BERT-based classifier achieving 92% precision on contract extraction" scores low. CFA Institute framework explicitly recommends this. | High | Requires a claim extraction pipeline: identify AI-related sentences, classify each as vague vs. specific using pattern matching + FinBERT. Aggregate ratio becomes a signal input. Good candidate for Claude API in v2. |

### Scoring and Signal (Advanced)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Signal confidence levels | Not all scores are equally reliable. A score from 6 fresh signals is more trustworthy than one from 3 stale signals. Downstream trading modules can size positions proportionally to confidence -- higher confidence = larger position. | Medium | Compute from: number of available signals, data freshness per signal, entity resolution quality, sample size (filings/postings analyzed). Output as 0-1 float alongside the composite score. |
| Signal decay / temporal weighting | Research shows US market alpha decays at 5.6% annually. AI washing signals are slow-moving but older data still loses predictive power. Weight recent observations higher using exponential decay. | Medium | Exponential decay function per observation. Half-life tuned per signal: job postings (weeks), filings (quarters), patents (years). Prevents stale data from dominating the composite. |
| Cross-signal correlation analysis | When multiple independent signals converge (job postings AND patents AND filings all red), confidence is significantly higher than any single signal. Multi-source confirmation is a core alternative data best practice. | Medium | Compute pairwise signal agreement. Flag "convergent" (3+ signals agree) vs. "divergent" (signals contradict). Convergent high-risk companies are the strongest short candidates with lowest false positive rates. |
| Industry-relative scoring | A tech company mentioning AI 500 times is normal. A regional bank mentioning AI 500 times is deeply suspicious. Industry context changes the baseline for what constitutes "AI washing." | Medium | Compute sector-peer benchmarks: average AI mention frequency, R&D spending, patent filing rate by SIC/NAICS code. Score relative to peers, not in absolute terms. Requires sector classification from XBRL or reference data. |

### Data Quality (Advanced)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Ghost posting detection | Research indicates 30-40% of job postings may be ghost jobs (posted with no intent to fill). If not detected, the job posting signal is systematically inflated, generating false short signals. Embedding similarity + repost tracking are the best detection methods per recent research. | High | Track posting lifecycle: first_seen, last_seen, repost_count, time_to_close. Flag postings open 90+ days, repeatedly reposted, or with unrealistic requirement combinations. Significantly improves job signal quality. |
| Automated data quality scoring per record | Assign a quality score to each data point: primary source or aggregator? How fresh? Did it pass all validation checks? Propagate data quality into signal confidence computations. | Medium | Per-record quality metadata. Aggregate into per-signal quality scores. Feed into confidence level computation. Enables the system to self-assess its own reliability -- critical for autonomous operation. |
| Score change anomaly detection | When a company's score jumps 30+ points overnight, is it real (new filing revealed something) or a data artifact (scraper broke, returned empty results)? Autonomous systems must distinguish signal from noise without human review. | High | Track score change velocity. Flag anomalous changes with root-cause attribution: "legitimate catalyst" (new 10-K filed, earnings call) vs. "data issue" (source returned empty, parsing error). Simple statistical thresholds initially, ML-based detection later. |

### Operational (Advanced)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Pipeline run auditing | Full traceability: which data was ingested, what analysis ran, what scores were produced, for each pipeline run. Essential for debugging autonomous systems and for regulatory compliance if the fund is ever audited. | Medium | Pipeline_runs table: run_id, start_time, end_time, status, companies_processed, signals_computed, errors_encountered. Link every score record to its pipeline run via foreign key. |
| Data freshness metadata (machine-readable) | Expose per-signal data freshness as queryable metadata. The risk module downstream needs to know: "are today's scores based on fresh data or are we running on stale inputs?" | Low | Per-company, per-signal: last_data_update timestamp, data_age_days, is_stale boolean. Queryable via Python API. No UI needed -- consumer is other modules. |
| Regulatory catalyst monitoring | SEC CETU enforcement actions, FTC investigations, analyst downgrades -- these are the events that cause AI washing to translate into stock price impact. Monitoring catalysts alongside scores improves trade timing. | High | Track SEC press releases and 8-K filings mentioning enforcement actions. Not essential for scoring, but valuable for the broader fund thesis. Better as a v2 addition or separate module. |

---

## Anti-Features

Features to explicitly NOT build in v1. Each has a clear reason for exclusion.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Real-time streaming / event-driven architecture | AI washing is a slow-moving signal (weekly/monthly cadence). Real-time adds massive complexity (Kafka, Redis Streams, state management) for zero signal improvement. Daily batch is sufficient and dramatically simpler to build, test, and debug. | Daily batch pipeline with cron/APScheduler/Prefect. Revisit only if a faster signal (SEC enforcement action alert) is added in v2. |
| Web dashboard / UI | The consumer is automated trading modules, not humans. Building a UI before the scoring engine is validated is premature optimization. The 2-5 person team can query PostgreSQL directly or use CLI tools for debugging. | PostgreSQL queries + Python API + CLI (Typer + Rich) for ad-hoc inspection. Streamlit dashboard is a post-validation add-on, not a v1 concern. |
| Paid API integrations (TheirStack, Revelio Labs, FMP) | v1 must prove the thesis using free data sources before committing to paid subscriptions ($500-$5,000/month). Paid APIs add vendor dependencies and recurring cost before the system has any track record. | Free sources only: SEC EDGAR, USPTO PatentsView, GitHub REST API, JobSpy. Build clean adapter interfaces (abstract base classes) so paid sources slot in later without changing the scoring engine. |
| REST API gateway | Premature service mesh. With one producer module and a shared database pattern, a gateway adds latency, operational burden, and failure modes for zero benefit. | Direct PostgreSQL access + Python package import. Add API gateway only when multiple independent services or non-Python consumers need score access. |
| LLM-based claim analysis (Claude API / GPT) | LLM inference is expensive at scale (hundreds of companies x thousands of filings), introduces non-deterministic scoring (same input can produce different output on different runs), and creates dependency on external API availability. For an autonomous system, deterministic scoring is safer and more auditable. | FinBERT (local, deterministic, free) for sentiment. Regex + lexicon for keyword and buzzword analysis. Rule-based vagueness scoring. LLM analysis is a v2 enhancement once deterministic baselines are established and labeled data exists. |
| Custom ML model training | Requires labeled training data that does not exist yet. Training vagueness classifiers or claim detectors on insufficient data produces unreliable models that are worse than rule-based systems. | Use pre-trained models (FinBERT) and rule-based systems (lexicons, regex patterns) in v1. Collect labeled data as a byproduct of v1 operation. Train custom models in v2 when sufficient labeled examples exist (100+ per class minimum). |
| Multi-asset class support | The thesis targets mid-cap US equities ($2B-$10B market cap). Expanding to other asset classes (crypto, international ADRs, bonds) dilutes focus without proving the core signal works. | Hard-code focus on US mid-cap equities. The scoring framework is portable, but adaptation to other universes is a future concern after thesis validation. |
| Position sizing / trade execution | Explicitly out of scope per PROJECT.md. This module produces scores; other modules decide what to do with them. Mixing signal generation with execution creates tight coupling and makes both harder to test, validate, and evolve independently. | Output scores + confidence to shared database. Portfolio management and execution modules (separate repos) handle position sizing and trade execution. |
| Backtesting engine | A full backtesting framework (simulating historical trading with scores) is a separate concern belonging to the portfolio management module. This module only needs to produce and store historical scores, not simulate trades or calculate P&L. | Store immutable historical snapshots that the portfolio module's backtester can consume. Do not build backtesting logic here. |
| Real-time alerting (SMS, email, Slack) | No human reviews individual trade decisions. Alerts imply human review, which contradicts the autonomous design. For a 2-5 person team, structured logs and database queries cover system health monitoring. | Structured logging with ERROR/WARNING levels. Pipeline run status in database. Team queries database or reads logs for operational monitoring. Add Slack alerts for critical system failures only if the team grows. |
| Mobile app | No user of this module is a human on a phone. The system is fully autonomous. | Nothing. This is permanently out of scope for this module. |
| Multi-language NLP | All target companies file with SEC in English. No international filing analysis needed for v1 US mid-cap focus. | English-only FinBERT and English lexicons. Multi-language is only relevant if the universe expands to non-US markets. |

---

## Feature Dependencies

```
Company Entity Resolution + Target Universe Builder
    |
    | (must identify and disambiguate companies before anything else)
    |
    v
[Data Ingestion Layer -- all 6 signals can run in parallel]
    |                       |                    |
    v                       v                    v
SEC Filing Ingestion    Job Posting Ingestion   Patent Ingestion
  + XBRL Extraction       + Deduplication         + CPC Classification
    |                       |                    |
    v                       v                    v
AI Keyword Frequency    Role Classification     Patent Gap
R&D Spend Extraction    (AI vs non-AI roles)    Analysis
    |                       |                    |
    v                       v                    v
Filing Mismatch Score   Job Mismatch Score      Patent Gap Score

Earnings Transcript     GitHub Activity         Compute Spending
Ingestion               Analysis                Analysis (from XBRL)
    |                       |                    |
    v                       v                    v
Buzzword Scoring        Repo Analysis           CapEx vs Claims
FinBERT Sentiment       ML Code Detection       Score
    |                       |                    |
    v                       v                    v
Vagueness Score         GitHub Score            Compute Score
    |                       |                    |
    +------- all 6 ---------+--------------------+
                            |
                            v
                  Composite Scoring Engine
                  (weighted combination + graceful degradation)
                            |
                            v
                  Immutable Score Snapshots --> Pipeline Run Auditing
                  (PostgreSQL append-only)
                            |
                            v
                  Python Package API
                  (downstream consumption)
                            |
                            v
                  Daily Batch Pipeline Orchestration
                  (wraps everything above with retry + logging)
```

### Critical Path Dependencies

1. **Company Entity Resolution** blocks all signal joining. Without it, SEC data cannot be matched to patent data, GitHub data, or job postings. Must be built first.
2. **Target Universe Builder** blocks all ingestion. Must identify which companies to score before scoring them. Depends on entity resolution.
3. **XBRL Financial Extraction** blocks both the SEC Filing Mismatch signal (R&D spending) and the Compute Spending signal (CapEx). Shared infrastructure serving two signals.
4. **Immutable Score Storage** blocks the Python Package API. Must store before you can query.
5. **Pipeline Orchestration** blocks daily autonomous operation. Individual signals can be tested manually, but production requires automated sequencing with error handling.

### Parallelizable Work

- All 6 data ingestion adapters can be built independently (after entity resolution + universe builder exist)
- All 6 signal scoring algorithms can be built independently (after their data adapter is available)
- Database schema and Python API can be built in parallel with signal development
- Deduplication and validation logic can be built alongside ingestion adapters
- Structured logging is independent of everything and can be set up at any time

---

## MVP Recommendation

### Phase 1: Foundation + Government API Signals

Build the infrastructure and the most reliable signals first. Government APIs (SEC, USPTO) are free, stable, well-documented, and rate-limited predictably.

1. **Company entity resolution + target universe builder** -- unblocks everything
2. **SEC filing ingestion + AI keyword analysis + R&D extraction (XBRL)** -- most robust signal, 20% weight
3. **USPTO patent integration + gap analysis** -- simplest API, 15% weight, quick win
4. **Composite scoring engine + immutable storage + PostgreSQL schema** -- the integration layer downstream modules need
5. **Pipeline orchestration + retry logic + structured logging** -- autonomous daily operation
6. **Python package API** -- enables downstream module development to begin

### Phase 2: NLP + Remaining Signals

Add the signals that require NLP or more complex data sources.

7. **Earnings call transcript ingestion + buzzword density scoring + FinBERT sentiment** -- 20% weight, moderate NLP complexity
8. **GitHub activity analysis** -- 10% weight, requires GitHub org entity resolution
9. **Compute spending analysis (from XBRL)** -- 10% weight, leverages infrastructure from Phase 1
10. **Graceful degradation** -- produce partial scores when sources are unavailable
11. **Data source availability monitoring + freshness tracking** -- operational maturity for autonomous reliability

### Phase 3: Job Signal + Signal Quality

Add the highest-weight but noisiest signal, plus quality-of-signal features.

12. **Job posting ingestion + deduplication** -- 25% weight, but deferred because free scraping is fragile and requires significant dedup infrastructure
13. **Ghost posting detection** -- advanced data quality critical for job signal accuracy
14. **Signal confidence levels** -- enables downstream position sizing based on score reliability
15. **Cross-signal correlation analysis** -- convergent multi-signal cases are the strongest short candidates

### Phase 4 (Post-Validation Differentiators)

Only after the thesis is validated with real trading outcomes:

16. **Industry-relative scoring** -- contextualizes raw scores against sector peers
17. **Section-aware filing NLP** -- MD&A vs. Risk Factors vs. Business Description weighting
18. **Speaker-level earnings call analysis** -- CEO vs. CTO language gap detection
19. **Signal decay / temporal weighting** -- weight recent data higher
20. **Regulatory catalyst monitoring** -- SEC enforcement action tracking

**Rationale for deferring job postings to Phase 3:** Despite being the highest-weighted signal (25%), job posting data from free sources is the most fragile (scraping breaks), noisiest (ghost postings, duplicates inflate counts 2-5x), and hardest to validate. SEC filings and patents from official government APIs are far more reliable foundations for proving the thesis. Build the scoring framework on solid ground first, then add the noisier-but-valuable job signal with proper dedup infrastructure in place.

---

## Sources

### HIGH Confidence
- [SEC EDGAR Accessing Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) -- Rate limits (10 req/sec), data access patterns, User-Agent requirements
- [EdgarTools Documentation](https://edgartools.readthedocs.io/en/stable/configuration/) -- SEC filing parsing, XBRL extraction, section support
- [ProsusAI/finBERT on GitHub](https://github.com/ProsusAI/finBERT) -- Financial sentiment analysis model, pre-trained on SEC filings
- [CFA Institute: AI Washing Signs, Symptoms, and Suggested Solutions](https://rpc.cfainstitute.org/research/reports/2025/ai-washing) -- Detection framework, due diligence questionnaire, red flag indicators

### MEDIUM Confidence
- [Paradox Intelligence: Alternative Data for Hedge Funds 2026](https://www.paradoxintelligence.com/blog/alternative-data-for-hedge-funds-complete-guide-2026) -- Signal construction patterns, data quality requirements, multi-source confirmation
- [Potent Pages: Labor Market Signals for Hedge Funds](https://potentpages.com/web-crawler-development/web-crawlers-and-hedge-funds/labor-market-signals-job-posts-hiring-velocity-role-mix) -- Job posting signal metrics, hiring velocity, role mix analytics
- [MicroAlphas: Signal Decay Patterns](https://microalphas.com/signal-decay-patterns/) -- Alpha decay rates (5.6% US annual), half-life modeling, signal freshness
- [SpiderMount: How Hedge Funds Use Job Posting Data](https://www.webspidermount.com/how-hedge-funds-use-job-posting-data-to-make-smarter-investment-decisions/) -- Job data as leading investment signal
- [EDGAR-CRAWLER: ACM Web Conference 2025](https://dl.acm.org/doi/10.1145/3701716.3715289) -- SEC filing NLP pipeline patterns
- [Arxiv: Advanced Deep Learning for Earnings Call Transcripts](https://arxiv.org/html/2503.01886v1) -- FinBERT vs. BERT vs. ULMFiT comparative analysis
- [Lightcast Job Posting Analytics Methodology](https://kb.lightcast.io/en/articles/6957446-job-posting-analytics-jpa-methodology) -- Deduplication methodology, 80% dedup rate
- [HubiFi: Immutable Audit Trails Guide](https://www.hubifi.com/blog/immutable-audit-log-basics) -- Append-only storage patterns for financial data

### LOW Confidence
- [Saber: GitHub Activity Signals](https://www.saber.app/glossary/github-activity-signals) -- Corporate GitHub analysis as investment signal
- [Man Group AlphaGPT deployment](https://www.hedgeweek.com/man-group-deploys-agentic-ai-for-quant-signal-discovery/) -- Agentic AI for quant signal discovery (context only, not directly applicable)
