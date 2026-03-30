# Project Research Summary

**Project:** AI Washing Detector
**Domain:** Autonomous Financial Signal Generation (AI Washing Detection for Quantitative Hedge Fund)
**Researched:** 2026-03-27
**Confidence:** HIGH

## Executive Summary

The AI Washing Detector is a batch-oriented signal generation pipeline that scores mid-cap US equities ($2B-$10B market cap) on the gap between their public AI claims and verifiable AI investment. It produces a daily composite AI Washing Risk Score (0-100) consumed by automated trading modules with zero human review. The domain is well-served by mature, free data sources -- SEC EDGAR filings via edgartools, USPTO patents via the new PatentSearch API at data.uspto.gov, GitHub REST API, and job postings via JobSpy. The Python NLP ecosystem provides FinBERT for financial sentiment and regex/lexicon-based keyword analysis for the initial vagueness detection layer. The recommended stack is Python 3.11+, PostgreSQL 16+, SQLAlchemy 2.0, Prefect 3.6+ for orchestration, and Pydantic 2.12+ for data validation -- all verified on PyPI as of March 2026.

The architecture follows a layered pipeline with isolated collectors, directly modeled on how quantitative hedge fund factor pipelines are structured. Each of the 5-6 data sources gets its own collector with independent error handling, rate limiting, and scheduling cadence. Collectors feed a shared analysis layer (keyword frequency, patent gap calculation, FinBERT sentiment, etc.), which feeds an immutable append-only scoring layer in PostgreSQL. Prefect 3's Python-native decorator API (`@flow`, `@task`) provides orchestration with built-in retries, caching, and event-driven automations -- without the operational overhead of Airflow or the distributed complexity of Celery. The system stores dual timestamps (event time and observation time) on every record from day one, which is non-negotiable for avoiding look-ahead bias in downstream backtesting.

The primary risks are not in the technology stack but in data quality and signal design. Three issues stand above the rest. First, ghost job postings (27-30% of LinkedIn jobs are fake) can invert the highest-weighted signal, making AI washers appear to be genuine investors. Second, FinBERT measures sentiment polarity (positive/negative/neutral) but the core detection task is vagueness-vs-specificity -- a fundamentally different NLP capability that FinBERT was not designed for. Third, silent pipeline failures in an autonomous system (API format changes, scraper breakage, token expiry) are the most dangerous operational risk because stale data propagates to trade execution with nobody watching. The PatentsView API completed its migration to data.uspto.gov on March 20, 2026 -- any code targeting the legacy api.patentsview.org endpoint is already dead and must target the new PatentSearch API.

## Key Findings

### Recommended Stack

The stack is Python-centric, leveraging Rust-accelerated tooling (uv, ruff, Pydantic v2) for developer speed and mature, battle-tested libraries for each concern. The system is batch-oriented (daily runs on approximately 200-500 companies), so async-first design is unnecessary complexity -- sync-by-default with targeted async for parallel API calls within a signal is the right approach. Prefect replaces both APScheduler (too simple for multi-step pipelines) and Celery (too complex for single-server batch).

**Core technologies:**
- **edgartools 5.23+**: SEC EDGAR filing access and parsing -- free, no API keys, parses 20+ filing types with XBRL standardization. Clear market leader for free SEC data access.
- **Prefect 3.6+**: Pipeline orchestration -- Python-native `@flow`/`@task` decorators with built-in retries, caching, and event-driven automations. Replaces APScheduler (no retry/caching) and Airflow (heavy operational footprint).
- **ProsusAI/FinBERT via transformers 5.3+**: Financial sentiment classification -- 89% accuracy on financial text. CPU-only inference is sufficient at this scale. Use for sentiment supplementary signal, NOT for primary vagueness detection.
- **PostgreSQL 16+ with SQLAlchemy 2.0**: Primary data store -- ACID compliance, JSONB for semi-structured filing content, native table partitioning for time-series score history. Append-only writes enforced at the application layer.
- **Pydantic 2.12+**: Data validation and settings -- Rust-core validation for all ingested data from untrusted external APIs. Schema enforcement at system boundaries.
- **httpx 0.28+**: HTTP client for non-EDGAR API calls -- sync and async in one library, HTTP/2 support, connection pooling. Future-proof replacement for requests.
- **python-jobspy**: Multi-board job scraping -- aggregates 8+ job boards in one call. Free but fragile (LinkedIn rate-limiting is a known issue). Design for source replaceability.
- **uv + ruff**: Package management and linting -- 10-100x faster than pip/poetry and flake8/black respectively. Standard for new Python projects in 2026.

**Critical version note:** PatentsView migrated to data.uspto.gov on March 20, 2026. Any PatentsView integration must target the new PatentSearch API, not the discontinued legacy endpoint.

### Expected Features

**Must have (table stakes):**
- SEC EDGAR filing ingestion (10-K, 10-Q, 8-K) with XBRL financial extraction (R&D spending, CapEx)
- AI keyword frequency analysis across filing sections with year-over-year growth tracking
- Buzzword density scoring (vague vs. specific AI claims using lexicon-based classification)
- FinBERT sentiment analysis on earnings call segments
- USPTO patent integration with AI-related CPC code classification (G06N, G06F18)
- GitHub organization activity analysis (repo language breakdown, ML framework detection)
- Job posting ingestion with deduplication (two-stage: deterministic hash + embedding similarity)
- Composite AI Washing Risk Score (0-100) with configurable signal weights
- Per-signal sub-scores with evidence attribution
- Historical score tracking via immutable append-only snapshots
- Company entity resolution across CIK, patent assignee, GitHub org, and job posting employer
- Target universe builder (EDGAR full-text search filtered by market cap)
- Graceful degradation (produce partial scores when sources are unavailable)
- Retry logic with exponential backoff per data source
- Structured JSON logging with correlation IDs per pipeline run
- PostgreSQL shared database output with Python package API for downstream modules

**Should have (differentiators):**
- Signal confidence levels propagated to downstream position sizing
- Cross-signal correlation analysis (convergent multi-signal cases as strongest candidates)
- Industry-relative scoring (sector-peer benchmarks for AI mention frequency)
- Filing section-aware NLP (MD&A vs. Risk Factors vs. Business Description weighting)
- Signal decay / temporal weighting (exponential decay with per-signal half-life tuning)
- Ghost posting detection (posting lifecycle tracking, repost frequency, time-to-close)
- Score change anomaly detection (distinguish legitimate catalysts from data artifacts)
- Pipeline run auditing with full traceability

**Defer (v2+):**
- Web dashboard / UI (consumer is automated modules, not humans)
- Paid API integrations (prove thesis with free sources first)
- LLM-based claim analysis (expensive, non-deterministic -- add after deterministic baselines established)
- Custom ML model training (no labeled data exists yet -- collect from v1 operation)
- Speaker-level earnings call analysis (CEO vs. CTO language gap detection)
- Regulatory catalyst monitoring (SEC enforcement action tracking)
- Real-time streaming / event-driven architecture (AI washing is a slow-moving signal)
- Multi-asset class support (focus on US mid-cap equities until thesis is validated)

### Architecture Approach

The system uses a layered pipeline with isolated collectors, following the Medallion Architecture pattern (Bronze = raw ingested data, Silver = analyzed/scored data, Gold = composite scores). Each of the 5 data source collectors operates independently with its own rate limiting, retry logic, and scheduling cadence. Collectors write raw data to PostgreSQL JSONB tables. The analysis layer reads raw data and produces per-signal scores. The scoring engine combines signal scores into a weighted composite with confidence adjustment for missing signals. All score tables are append-only and partitioned by month.

**Major components:**
1. **Scheduler (Prefect)** -- triggers collection and scoring runs on configured cadences (SEC daily, patents weekly, earnings quarterly, scoring daily after collectors complete)
2. **Collectors (5 independent modules)** -- SEC, USPTO, GitHub, Jobs, Earnings -- each with BaseCollector ABC providing retry, rate limiting, and circuit breaker logic
3. **Analysis Layer (6 analyzers)** -- SEC filing keyword frequency + R&D gap, patent gap, GitHub activity, job mismatch, earnings vagueness, compute spending -- each with BaseAnalyzer ABC and registry pattern for extensibility
4. **Scoring Engine** -- weighted composite calculation with configurable weights, graceful degradation, and confidence computation from signal availability
5. **Database Layer (PostgreSQL)** -- append-only tables with monthly partitioning: companies, raw_collections, signal_scores, composite_scores, pipeline_runs
6. **Python API** -- thin wrapper exposing `get_latest_scores()`, `get_score_history()`, `get_high_risk_companies()` for downstream module consumption

**Key patterns to follow:**
- Immutable append-only records for all financial data (never UPDATE/DELETE score rows)
- Collector base class with template method pattern (shared retry/rate-limit logic, subclasses implement data fetching)
- Registry pattern for analyzers (self-registration enables adding new signals without modifying the scoring engine)
- Run-based pipeline tracking (every execution gets a unique run_id linking all produced records)
- Dual timestamps on every record: `as_of_date` (when event occurred) and `observed_date` (when system first saw it)

### Critical Pitfalls

1. **Ghost job postings poison the highest-weighted signal (25%)** -- 27-30% of LinkedIn posts are fake. Companies actively AI washing have financial incentive to post ghost AI roles. Prevention: track posting lifecycle (open >90 days = red flag), use fill rate ratios instead of raw counts, cross-reference with actual headcount changes. Design the job signal to treat unfilled roles as neutral-to-negative, not positive.

2. **Look-ahead bias in signal construction** -- Using SEC filing report-period dates instead of filing dates, or backfilling XBRL corrections, creates phantom signals that produce unrealistically good backtests. Prevention: store dual timestamps from day one (event time + observation time), never overwrite historical data, use filing dates not report-period dates. This must be baked into the data model in Phase 1 -- retrofitting is a rewrite.

3. **Silent pipeline failures in autonomous operation** -- APIs silently stop returning data (format changes, rate limiting, token expiry). The scoring engine operates on stale data with nobody watching. Prevention: data freshness checks per source, record count validation against trailing 30-day average, circuit breaker pattern marking degraded signals in the composite score, null/empty result alerting.

4. **FinBERT domain mismatch for vagueness detection** -- FinBERT measures sentiment polarity, not claim specificity. "AI is transforming our business" and "We deployed a transformer model reducing MAPE by 15%" score similarly on sentiment. Prevention: use FinBERT only for sentiment supplementary signal, not as the primary vagueness detector. Use lexicon-based vagueness scoring (vague-to-specific term ratio) in v1, upgrade to LLM-based classification in v2.

5. **Keyword-based SEC filing analysis missing context** -- Naive keyword counting produces massive false positives (risk factor boilerplate, industry descriptions) and false negatives (synonym drift, negated mentions). Prevention: section-aware parsing (weight MD&A highest, Risk Factors lowest), negation detection, taxonomy distinguishing AI claims vs. disclosures vs. references. Plan for LLM augmentation.

6. **PatentsView API migration (time-critical)** -- The legacy API at api.patentsview.org was discontinued May 2025. The platform migrated to data.uspto.gov on March 20, 2026. Any patent integration code must target the new PatentSearch API. This is not a future risk -- it is a current reality that any tutorial or library targeting the old endpoint will fail.

## Implications for Roadmap

Based on combined research across stack, features, architecture, and pitfalls, the following phase structure is recommended. The ordering reflects hard dependency constraints (entity resolution blocks everything, database schema is foundational), the principle of proving the full pipeline end-to-end before expanding signals, and the strategic decision to build on the most reliable data sources first.

### Phase 1: Foundation and Data Model
**Rationale:** Every other phase depends on the database schema, entity resolution system, configuration, and project structure. Dual timestamps, immutable append-only design, and table partitioning cannot be retrofitted -- they must be designed in from the start. Entity resolution is the single most critical dependency: without it, signals from different sources cannot be joined.
**Delivers:** PostgreSQL schema (companies, raw_collections, signal_scores, composite_scores, pipeline_runs), Alembic migration framework, Pydantic settings configuration, src-layout package structure with pyproject.toml, company entity resolution table (CIK as primary key with mappings to ticker, patent assignee, GitHub org, job posting employer), structured logging infrastructure, base classes for collectors and analyzers.
**Addresses features:** Company entity resolution, input validation at system boundaries, structured logging, PostgreSQL shared database output, historical score tracking (schema only).
**Avoids pitfalls:** Look-ahead bias (#2 -- dual timestamps from day one), storage growth (#16 -- partitioning from day one), entity matching failures (#7 -- mapping table as first-class data structure).

### Phase 2: SEC Signal End-to-End
**Rationale:** SEC EDGAR is the most reliable, best-documented data source with free programmatic access. Building one signal end-to-end (collect, analyze, score, store, query) proves the full pipeline architecture before investing in four more collectors. The SEC signal combines two of the six sub-scores (filing mismatch + compute spending from XBRL), providing the richest single-source value. The target universe builder also depends on SEC data (EDGAR full-text search for AI keywords).
**Delivers:** Target universe builder, SEC collector (10-K/10-Q/8-K filing ingestion, XBRL financial extraction), SEC analyzer (keyword frequency, buzzword density, R&D spending gap), compute spending analyzer (CapEx from XBRL), scoring engine (composite calculation with configurable weights), Python API (get_latest_scores, get_score_history), CLI interface for manual runs.
**Addresses features:** Target universe builder, SEC filing ingestion, XBRL financial data extraction, AI keyword frequency analysis, buzzword density scoring, composite AI Washing Risk Score, per-signal sub-scores, score interpretation thresholds, Python package API.
**Avoids pitfalls:** XBRL inconsistencies (#10 -- multi-tag R&D extraction, SEC CompanyFacts API), keyword false positives (#5 -- section-aware parsing from the start), EDGAR rate limiting (#12 -- tenacity-based backoff with proper User-Agent).
**Stack used:** edgartools, SQLAlchemy, Alembic, Pydantic, Typer, Rich, tenacity, structlog.

### Phase 3: Patent and GitHub Signals
**Rationale:** USPTO and GitHub are the next most reliable free APIs after SEC EDGAR. Both are well-documented with predictable rate limits. Patent data (15% weight) and GitHub activity (10% weight) are independent signals that can be built in parallel. This phase expands the composite from 2 signals to 4, significantly improving score reliability.
**Delivers:** USPTO collector targeting new PatentSearch API at data.uspto.gov, patent gap analyzer (AI-related CPC code classification), GitHub collector, GitHub analyzer (repo activity, ML framework detection in requirements.txt/pyproject.toml), enhanced scoring engine with 4-signal composite and confidence adjustment.
**Addresses features:** USPTO PatentsView integration, patent gap analysis, GitHub organization activity analysis, signal confidence levels (initial implementation).
**Avoids pitfalls:** PatentsView API migration (#15 -- must use new data.uspto.gov endpoint), company name matching across patent assignees (#7 -- subsidiary-aware matching), GitHub signal weakness for non-tech companies (#11 -- conditional weighting by sector, asymmetric scoring).
**Stack used:** httpx, Pydantic, tenacity.

### Phase 4: NLP, Earnings, and Job Posting Signals
**Rationale:** These three signals require the most complex data processing. Earnings calls need NLP (FinBERT sentiment + lexicon-based vagueness scoring). Job postings are the highest-weighted signal (25%) but also the noisiest and most fragile. Grouping them in Phase 4 allows Phase 2-3 to establish a working, tested pipeline that these more complex signals integrate into. The earnings and jobs collectors should be built in parallel, followed by sequential integration with the scoring engine.
**Delivers:** Earnings call transcript collector, earnings vagueness analyzer (FinBERT for sentiment, vague-to-specific lexicon ratio for specificity), jobs collector (JobSpy integration), jobs analyzer (role classification, deduplication pipeline), full 6-signal composite scoring with graceful degradation, data source availability monitoring, freshness tracking.
**Addresses features:** Earnings call transcript ingestion, FinBERT sentiment analysis, buzzword density scoring on transcripts, job posting ingestion, job posting deduplication, graceful degradation per signal, data source availability monitoring, data freshness metadata.
**Avoids pitfalls:** FinBERT domain mismatch (#4 -- use for sentiment only, lexicon for vagueness), ghost job postings (#1 -- lifecycle tracking, fill rate ratios), LinkedIn scraping fragility (#13 -- abstract behind interface for source replaceability), silent pipeline failures (#3 -- freshness checks, circuit breakers).
**Stack used:** transformers (FinBERT), torch (CPU), python-jobspy, httpx, beautifulsoup4.

### Phase 5: Automation, Hardening, and Production Readiness
**Rationale:** Automation should only be applied to a pipeline that works correctly when run manually. This phase takes the validated 6-signal pipeline and makes it autonomous: scheduled runs, comprehensive monitoring, circuit breakers, and pipeline run auditing. This is also when cross-signal correlation analysis and anomaly detection are added, since they require real data from all 6 signals to calibrate.
**Delivers:** Prefect-based scheduling (daily/weekly/quarterly cadences per source), pipeline run auditing (full traceability per run), circuit breaker pattern across all collectors, cross-signal correlation analysis, score change anomaly detection, golden dataset test fixtures from real API responses, integration test suite against live APIs.
**Addresses features:** Daily batch pipeline orchestration, retry logic with exponential backoff (hardened), pipeline run auditing, cross-signal correlation analysis, score change anomaly detection.
**Avoids pitfalls:** Silent pipeline failures (#3 -- comprehensive monitoring), weight overfitting (#8 -- correlation analysis before finalizing weights), correlated signals producing false confidence (#14 -- factor decorrelation, claim-vs-evidence grouping), testing with mocked data (#17 -- golden dataset).
**Stack used:** Prefect, structlog, pytest (golden dataset).

### Phase Ordering Rationale

- **Phase 1 is non-negotiable first:** The database schema, dual timestamps, immutable design, entity resolution, and project structure are foundational. Every subsequent phase depends on them. Retrofitting dual timestamps or append-only semantics is a full rewrite.
- **Phase 2 proves the pipeline with the most reliable source:** SEC EDGAR is free, well-documented, rate-limited predictably, and serves the richest data (filings + financial facts). Building the full ingest-analyze-score-store-query pipeline for one source validates the architecture before investing in four more.
- **Phase 3 adds the next-most-reliable signals:** Government APIs (USPTO) and well-documented APIs (GitHub) are stable and predictable. Expanding to 4 signals significantly improves composite score reliability with moderate implementation effort.
- **Phase 4 tackles the hardest signals together:** NLP and job scraping are the most complex and fragile. Grouping them ensures the pipeline is solid before adding the noisiest components. FinBERT's limitation (sentiment, not vagueness) is mitigated by pairing it with lexicon-based scoring.
- **Phase 5 automates last:** Automation magnifies both good and bad behavior. Automating a broken pipeline creates silent failures. Automating a validated pipeline creates reliable autonomous operation.

### Research Flags

**Phases likely needing deeper research during planning:**
- **Phase 2 (SEC Signal):** XBRL taxonomy mapping is company-specific. Need to identify which tags map to R&D expense across different filing styles. The edgartools inline XBRL parser is "not completely developed" per its own docs -- validate extraction quality on 20+ real filings before trusting it.
- **Phase 3 (Patent Signal):** Must investigate the new PatentSearch API at data.uspto.gov. The API format, query syntax, and response structure may differ from the legacy endpoint. No Python client library confirmed for the new API -- may need raw httpx calls.
- **Phase 4 (Job Signal):** Ghost job detection strategy needs validation. The proposed lifecycle tracking (days open, repost frequency) is theoretically sound but untested. Need to determine what "normal" fill time looks like across industries before flagging outliers.
- **Phase 4 (Earnings Signal):** Need to identify a free earnings call transcript source for v1. The EarningsCall Python library covers S&P 500 but may not cover mid-cap companies. If no free source exists, this signal may need to be deferred or limited to companies with publicly available transcripts.

**Phases with standard, well-documented patterns (skip additional research):**
- **Phase 1 (Foundation):** PostgreSQL partitioning, SQLAlchemy 2.0 ORM, Alembic migrations, Pydantic settings, src-layout packaging -- all have extensive official documentation and established patterns.
- **Phase 5 (Automation):** Prefect scheduling, structlog, circuit breaker pattern, retry logic -- all well-documented with clear implementation guides.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All library versions verified on PyPI as of March 2026. edgartools, transformers, SQLAlchemy, Prefect are mature with active maintenance. httpx at 0.28 (pre-1.0) is the only minor uncertainty but is widely adopted in production. |
| Features | MEDIUM-HIGH | Signal categories and weights are well-defined from the research framework (CFA Institute, alternative data literature). The feature dependency graph is clear. Uncertainty is in the earnings transcript source for v1 (free coverage of mid-cap companies unconfirmed). |
| Architecture | HIGH | Layered pipeline with isolated collectors is the standard pattern for quant factor modeling pipelines. Immutable append-only storage is canonical for financial time series. PostgreSQL partitioning, JSONB storage, and the Medallion Architecture pattern are all extensively documented. |
| Pitfalls | HIGH | 17 pitfalls catalogued with multi-source verification. The critical pitfalls (ghost jobs, look-ahead bias, silent failures, FinBERT mismatch) are each supported by 2+ independent sources. PatentsView migration timeline confirmed via official USPTO announcement. |

**Overall confidence:** HIGH

The stack and architecture decisions are well-supported by verified sources and established industry patterns. The primary uncertainty is in data quality (XBRL consistency, job posting noise, entity resolution accuracy) which will only be fully resolved during implementation with real data.

### Gaps to Address

- **Earnings call transcript source for v1:** Research identified EarningsCall library for S&P 500 coverage, but mid-cap coverage is unconfirmed. Need to validate during Phase 4 planning whether a free source exists for the target universe, or whether this signal should be limited/deferred.
- **XBRL tag mapping specifics:** Which XBRL tags map to "R&D expense" varies by company. The multi-tag search approach (ResearchAndDevelopmentExpense + 3 variants) is documented but needs empirical validation against the target universe during Phase 2.
- **Company-to-entity manual curation:** The mapping table approach is architecturally sound, but populating it for 200-500 mid-cap companies requires manual work (especially GitHub org and patent assignee mappings). Budget this effort into Phase 1.
- **FinBERT vs. LLM reconciliation:** STACK.md recommends FinBERT. PITFALLS.md correctly flags it as wrong for vagueness detection. Resolution: FinBERT for sentiment (supplementary signal), lexicon-based scoring for vagueness (v1 primary), LLM-based classification for vagueness (v2 upgrade). This is a design decision, not a gap.
- **Signal weight validation:** Initial weights (25/20/20/15/10/10) are economically motivated, not statistically optimized. This is the correct approach for v1 given the tiny sample of SEC enforcement actions. Validation requires 2+ quarters of live scoring data. Do not optimize weights prematurely.
- **New PatentSearch API client:** No confirmed Python wrapper exists for the new data.uspto.gov PatentSearch API. May require direct httpx calls with manual response parsing. Needs investigation in Phase 3 planning.

## Sources

### Primary (HIGH confidence)
- [SEC EDGAR Accessing Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) -- Rate limits, User-Agent requirements, data access patterns
- [EdgarTools Documentation](https://edgartools.readthedocs.io/) -- SEC filing parsing, XBRL extraction, section support
- [EdgarTools PyPI](https://pypi.org/project/edgartools/) -- v5.23.2 (March 2026), actively maintained
- [ProsusAI/finBERT](https://huggingface.co/ProsusAI/finbert) -- Financial sentiment model, pre-trained on SEC filings
- [CFA Institute: AI Washing Signs, Symptoms, and Suggested Solutions](https://rpc.cfainstitute.org/research/reports/2025/ai-washing) -- Detection framework, red flag indicators
- [PostgreSQL Documentation: Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) -- Official partitioning guidance
- [Python Packaging Guide: src Layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/) -- Official packaging recommendation
- [PatentsView Migration Notice](https://www.uspto.gov/subscription-center/2026/patentsview-migrating-uspto-open-data-portal-march-20) -- USPTO official migration announcement
- [Seven Sins of Quantitative Investing](https://bookdown.org/palomar/portfoliooptimizationbook/8.2-seven-sins.html) -- Backtesting bias catalog
- [Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/overfit-tools-at.pdf) -- Bailey & Lopez de Prado paper
- [EDGAR XBRL Guide March 2026](https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide.pdf) -- SEC XBRL validation specifications
- [GitHub API Rate Limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) -- Official rate limit documentation

### Secondary (MEDIUM confidence)
- [Paradox Intelligence: Alternative Data for Hedge Funds 2026](https://www.paradoxintelligence.com/blog/alternative-data-for-hedge-funds-complete-guide-2026) -- Signal construction patterns, data quality requirements
- [Potent Pages: Labor Market Signals for Hedge Funds](https://potentpages.com/web-crawler-development/web-crawlers-and-hedge-funds/labor-market-signals-job-posts-hiring-velocity-role-mix) -- Job posting signal metrics
- [MicroAlphas: Signal Decay Patterns](https://microalphas.com/signal-decay-patterns/) -- Alpha decay rates, half-life modeling
- [EDGAR-CRAWLER: ACM Web Conference 2025](https://dl.acm.org/doi/10.1145/3701716.3715289) -- SEC filing NLP pipeline patterns
- [Arxiv: Advanced Deep Learning for Earnings Call Transcripts](https://arxiv.org/html/2503.01886v1) -- FinBERT vs. BERT comparative analysis
- [Lightcast Job Posting Analytics Methodology](https://kb.lightcast.io/en/articles/6957446-job-posting-analytics-jpa-methodology) -- Deduplication methodology, 80% dedup rate
- [AWS: GenAI in Factor Modeling Data Pipelines](https://aws.amazon.com/blogs/industries/genai-in-factor-modeling-data-pipelines-a-hedge-fund-workflow-on-aws/) -- Hedge fund pipeline architecture
- [Hedgeweek: Man Group deploys agentic AI](https://www.hedgeweek.com/man-group-deploys-agentic-ai-for-quant-signal-discovery/) -- Industry signal generation architecture
- [Ghost Jobs Report](https://www.entrepreneur.com/business-news/one-quarter-of-jobs-posted-online-are-fake-ghost-jobs-study/496683) -- 27.4% ghost job rate
- [FinBERT NLP Benchmarks](https://caia.org/blog/2024/03/12/comparative-analysis-nlp-approaches-chatgpt-edition) -- CAIA comparative analysis

### Tertiary (LOW confidence)
- [Saber: GitHub Activity Signals](https://www.saber.app/glossary/github-activity-signals) -- Corporate GitHub analysis as investment signal
- [CSET Georgetown: Global GitHub Mapping](https://cset.georgetown.edu/publication/global-github-mapping-the-utilization-of-open-source-software-by-organizations/) -- Limited organizational GitHub presence outside tech

---
*Research completed: 2026-03-27*
*Ready for roadmap: yes*
