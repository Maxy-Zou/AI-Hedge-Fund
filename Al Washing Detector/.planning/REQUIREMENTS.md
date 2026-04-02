# Requirements: AI Washing Detector

**Defined:** 2026-03-27
**Core Value:** Accurately quantify the gap between what companies say about AI and what they do — producing reliable, machine-consumable signals that an automated trading system can act on without human review.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Foundation

- [x] **FNDN-01**: System initializes with PostgreSQL database using append-only schema with dual timestamps (as_of_date, observed_date) for all financial data
- [x] **FNDN-02**: Company entity resolution maps companies across data sources (CIK, patent assignee, GitHub org, job posting employer) into a unified master table with aliases
- [x] **FNDN-03**: Target universe builder identifies mid-cap companies ($2B-$10B market cap) making AI claims via EDGAR full-text search, filtered by sector
- [x] **FNDN-04**: Project is structured as an installable Python package with CLI entry points and importable public API
- [x] **FNDN-05**: All configuration (signal weights, thresholds, API identities, refresh cadences) is externalized in YAML/env files, not hardcoded
- [x] **FNDN-06**: Database migrations are managed via Alembic with version-controlled migration scripts

### SEC Filing Signal

- [x] **SEC-01**: System ingests 10-K, 10-Q, and 8-K filings from SEC EDGAR using edgartools for target universe companies
- [x] **SEC-02**: AI keyword frequency analyzer counts AI/ML mentions across filing sections (MD&A, Risk Factors, Business Description) over 3-5 year windows
- [x] **SEC-03**: XBRL financial data extractor retrieves R&D spending, CapEx, and revenue from company facts
- [x] **SEC-04**: Filing mismatch score (0-100) computes ratio of AI_mention_growth to R&D_spend_growth, flagging divergence
- [x] **SEC-05**: SEC data respects EDGAR rate limits (10 req/sec) with mandatory User-Agent header containing identity

### Patent Signal

- [x] **PAT-01**: System queries USPTO PatentsView API (data.uspto.gov — new endpoint) for AI-related patents by company using CPC codes G06N and G06F18
- [x] **PAT-02**: Patent gap score (0-100) measures AI patent filing trend against AI claim intensity from filings
- [x] **PAT-03**: Patent data refreshes weekly (patents move slowly)

### Job Posting Signal

- [x] **JOB-01**: System ingests AI-related job postings for target companies using free scraping sources (JobSpy or linkedin-jobs-api)
- [x] **JOB-02**: Job role classifier distinguishes AI/ML engineering roles from marketing/strategy roles based on title and description keywords
- [x] **JOB-03**: Job posting deduplication removes syndicated duplicates using deterministic hash matching (company + title + location)
- [x] **JOB-04**: Job posting lifecycle tracking records first_seen, last_seen, and time_to_fill for flagging stale postings (90+ days open)
- [x] **JOB-05**: Job mismatch score (0-100) compares AI claim intensity to actual AI hiring activity and role quality

### Earnings Call Signal

- [x] **EARN-01**: System ingests earnings call transcripts for target companies using free sources (EarningsCall Python library)
- [x] **EARN-02**: Buzzword density scorer distinguishes vague AI claims ("AI-powered") from substantive claims ("deployed transformer model") using dual lexicons
- [x] **EARN-03**: FinBERT sentiment analysis runs on earnings call segments producing positive/negative/neutral classification
- [x] **EARN-04**: Vagueness score (0-100) combines buzzword density ratio with sentiment-vs-metrics mismatch
- [x] **EARN-05**: Transcripts refresh quarterly, triggered by earnings calendar

### GitHub Signal

- [x] **GH-01**: System checks GitHub organization repos for target companies, analyzing repo count, language breakdown, commit recency, and ML framework imports
- [x] **GH-02**: GitHub activity score (0-100) measures genuine ML code activity vs. absence/abandonment
- [x] **GH-03**: GitHub data respects API rate limits (5,000 req/hr with token)

### Compute Spending Signal

- [x] **COMP-01**: System extracts CapEx and IT spending indicators from XBRL financial data (shares infrastructure with SEC-03)
- [x] **COMP-02**: Earnings call transcript analysis checks for cloud/compute partnership mentions (AWS, Azure, GCP, NVIDIA)
- [x] **COMP-03**: Compute spending gap score (0-100) flags flat CapEx/cloud spend despite AI narrative growth

### Composite Scoring

- [x] **SCORE-01**: Composite AI Washing Risk Score (0-100) computed as weighted average of 6 sub-scores with configurable weights (default: Jobs 25%, SEC 20%, Earnings 20%, Patents 15%, GitHub 10%, Compute 10%)
- [x] **SCORE-02**: Per-signal sub-scores stored alongside composite for explainability and audit
- [x] **SCORE-03**: Score interpretation thresholds classify companies: 0-30 (genuine), 30-60 (mixed), 60-80 (significant risk), 80-100 (strong short candidate)
- [x] **SCORE-04**: Graceful degradation produces scores from available signals with re-normalized weights when a data source is unavailable, attaching reduced confidence
- [x] **SCORE-05**: All scores are immutable — each daily run produces new snapshot rows, never updates existing records

### Data Quality

- [x] **DQ-01**: All ingested data passes Pydantic schema validation before processing — malformed records are rejected and logged
- [x] **DQ-02**: Data source availability monitoring tracks last-successful-fetch per source and flags staleness exceeding expected cadence
- [x] **DQ-03**: Input validation enforces types, ranges, and required fields at all system boundaries

### Operations

- [x] **OPS-01**: Retry logic with exponential backoff on all external API calls using tenacity, configured per data source
- [x] **OPS-02**: Structured JSON logging via structlog with correlation IDs per pipeline run
- [x] **OPS-03**: Daily batch pipeline orchestration runs ingestion, analysis, scoring, and output in sequence with per-stage error handling
- [x] **OPS-04**: Pipeline run status tracking records start_time, end_time, status (succeeded/partially_failed/failed), companies_processed, errors per run

### Integration

- [x] **INT-01**: PostgreSQL shared database with well-defined schema (companies, daily_scores, signal_details, pipeline_runs) serves as primary integration point
- [x] **INT-02**: Python package API exposes get_score(ticker, date), get_latest_scores(), get_score_history(ticker, start, end) returning immutable dataclasses
- [x] **INT-03**: Structured score output includes composite, sub-scores, confidence level, data freshness per signal, and pipeline_run_id for traceability

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced NLP

- **NLP-01**: Earnings call speaker-level analysis detecting CEO vs. CTO language gap
- **NLP-02**: Filing section-aware NLP weighting (MD&A vs. Risk Factors vs. Business Description)
- **NLP-03**: Temporal keyword trajectory analysis (3-5 year trend shapes)
- **NLP-04**: Granular vagueness-to-specificity ratio scoring per individual AI claim

### Advanced Scoring

- **ADV-01**: Signal confidence levels (0-1 float) based on data freshness, signal availability, entity resolution quality
- **ADV-02**: Signal decay with exponential temporal weighting (half-life per signal type)
- **ADV-03**: Cross-signal correlation analysis flagging convergent vs. divergent signals
- **ADV-04**: Industry-relative scoring normalized against sector peers

### Advanced Data Quality

- **ADQ-01**: Ghost job posting detection using lifecycle tracking and embedding similarity
- **ADQ-02**: Automated data quality scoring per record propagating into confidence
- **ADQ-03**: Score change anomaly detection distinguishing real catalysts from data artifacts

### Operational Enhancements

- **OPE-01**: Regulatory catalyst monitoring (SEC enforcement, FTC actions, analyst downgrades)
- **OPE-02**: Paid API integrations (TheirStack, Revelio Labs, FMP) for higher-quality data
- **OPE-03**: LLM-based claim analysis (Claude API) for nuanced vagueness detection
- **OPE-04**: Streamlit dashboard for team monitoring and debugging

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Trade execution / position sizing | Separate module in the fund — this module produces scores only |
| Backtesting engine | Belongs in portfolio management module, not signal generation |
| Real-time streaming / event-driven | AI washing is slow-moving; daily batch is sufficient |
| Web dashboard / UI | Consumer is automated systems; team uses CLI + SQL for debugging |
| REST API gateway | Premature — only one consumer exists (shared DB pattern) |
| Mobile app | No human on a phone consumes this module's output |
| Multi-language NLP | All SEC filings are in English; international markets are future scope |
| Custom ML model training | No labeled data exists yet; rule-based v1 collects training data for v2 |
| Real-time alerting (SMS/email/Slack) | Contradicts autonomous design; structured logs suffice for small team |
| Multi-asset class support | Focus on US mid-cap equities to prove thesis first |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FNDN-01 | Phase 1: Project Skeleton and Database | Complete |
| FNDN-02 | Phase 2: Entity Resolution and Universe Builder | Complete |
| FNDN-03 | Phase 2: Entity Resolution and Universe Builder | Complete |
| FNDN-04 | Phase 1: Project Skeleton and Database | Complete |
| FNDN-05 | Phase 1: Project Skeleton and Database | Complete |
| FNDN-06 | Phase 1: Project Skeleton and Database | Complete |
| SEC-01 | Phase 3: SEC Filing Collection | Complete |
| SEC-02 | Phase 4: SEC Scoring and Compute Signal | Complete |
| SEC-03 | Phase 3: SEC Filing Collection | Complete |
| SEC-04 | Phase 4: SEC Scoring and Compute Signal | Complete |
| SEC-05 | Phase 3: SEC Filing Collection | Complete |
| PAT-01 | Phase 5: Patent Signal | Complete |
| PAT-02 | Phase 5: Patent Signal | Complete |
| PAT-03 | Phase 5: Patent Signal | Complete |
| JOB-01 | Phase 8: Job Posting Signal | Complete |
| JOB-02 | Phase 8: Job Posting Signal | Complete |
| JOB-03 | Phase 8: Job Posting Signal | Complete |
| JOB-04 | Phase 8: Job Posting Signal | Complete |
| JOB-05 | Phase 8: Job Posting Signal | Complete |
| EARN-01 | Phase 7: Earnings Call Signal | Complete |
| EARN-02 | Phase 7: Earnings Call Signal | Complete |
| EARN-03 | Phase 7: Earnings Call Signal | Complete |
| EARN-04 | Phase 7: Earnings Call Signal | Complete |
| EARN-05 | Phase 7: Earnings Call Signal | Complete |
| GH-01 | Phase 6: GitHub Signal | Complete |
| GH-02 | Phase 6: GitHub Signal | Complete |
| GH-03 | Phase 6: GitHub Signal | Complete |
| COMP-01 | Phase 4: SEC Scoring and Compute Signal | Complete |
| COMP-02 | Phase 4: SEC Scoring and Compute Signal | Complete |
| COMP-03 | Phase 4: SEC Scoring and Compute Signal | Complete |
| SCORE-01 | Phase 9: Composite Scoring and Integration API | Complete |
| SCORE-02 | Phase 4: SEC Scoring and Compute Signal | Complete |
| SCORE-03 | Phase 9: Composite Scoring and Integration API | Complete |
| SCORE-04 | Phase 9: Composite Scoring and Integration API | Complete |
| SCORE-05 | Phase 9: Composite Scoring and Integration API | Complete |
| DQ-01 | Phase 10: Data Quality and Pipeline Automation | Complete |
| DQ-02 | Phase 10: Data Quality and Pipeline Automation | Complete |
| DQ-03 | Phase 10: Data Quality and Pipeline Automation | Complete |
| OPS-01 | Phase 10: Data Quality and Pipeline Automation | Complete |
| OPS-02 | Phase 10: Data Quality and Pipeline Automation | Complete |
| OPS-03 | Phase 10: Data Quality and Pipeline Automation | Complete |
| OPS-04 | Phase 10: Data Quality and Pipeline Automation | Complete |
| INT-01 | Phase 1: Project Skeleton and Database | Complete |
| INT-02 | Phase 9: Composite Scoring and Integration API | Complete |
| INT-03 | Phase 9: Composite Scoring and Integration API | Complete |

**Coverage:**
- v1 requirements: 45 total
- Mapped to phases: 45
- Unmapped: 0

---
*Requirements defined: 2026-03-27*
*Last updated: 2026-03-27 after roadmap creation*
