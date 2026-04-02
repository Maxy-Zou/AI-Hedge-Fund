# Roadmap: AI Washing Detector

## Overview

This roadmap delivers an autonomous AI washing detection module for a quantitative hedge fund. It starts with foundational infrastructure (database schema, entity resolution, universe builder), then proves the full pipeline end-to-end with the most reliable data source (SEC EDGAR) before expanding to additional signals (patents, GitHub, earnings calls, job postings). Each signal is a self-contained phase, ordered by data source reliability and dependency risk. Composite scoring and the integration API are built after all signals exist. Pipeline automation comes last -- only automate what works manually. The ordering reflects the research finding that entity resolution and universe building are critical path blockers, SEC should be proved end-to-end before expanding, and job postings (noisiest signal) should be deferred until the pipeline is proven.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Project Skeleton and Database** - Installable Python package with PostgreSQL append-only schema, configuration, and migration framework
- [x] **Phase 2: Entity Resolution and Universe Builder** - Company identity mapping across data sources and mid-cap AI-claiming universe identification
- [x] **Phase 3: SEC Filing Collection** - Ingest 10-K/10-Q/8-K filings and extract XBRL financial data from EDGAR with rate limiting
- [x] **Phase 4: SEC Scoring and Compute Signal** - Keyword frequency analysis, filing mismatch scoring, and compute spending gap detection from XBRL data *(completed 2026-03-28)*
- [x] **Phase 5: Patent Signal** - USPTO PatentsView integration via new data.uspto.gov endpoint with patent gap scoring *(completed 2026-03-28)*
- [x] **Phase 6: GitHub Signal** - GitHub organization activity analysis and ML code activity scoring *(completed 2026-03-29)*
- [x] **Phase 7: Earnings Call Signal** - Transcript ingestion with lexicon-based vagueness scoring and FinBERT sentiment analysis *(completed 2026-03-29)*
- [x] **Phase 8: Job Posting Signal** - Job posting ingestion, deduplication, role classification, and hiring mismatch scoring *(completed 2026-03-29)*
- [x] **Phase 9: Composite Scoring and Integration API** - Weighted 6-signal composite score with graceful degradation and Python package API *(completed 2026-03-29)*
- [x] **Phase 10: Data Quality and Pipeline Automation** - Schema validation, staleness monitoring, Prefect orchestration, and structured logging (completed 2026-03-30)

## Phase Details

### Phase 1: Project Skeleton and Database
**Goal**: A working, installable Python package with a fully migrated PostgreSQL database using append-only schema with dual timestamps -- ready for other phases to build on
**Depends on**: Nothing (first phase)
**Requirements**: FNDN-01, FNDN-04, FNDN-05, FNDN-06, INT-01
**Success Criteria** (what must be TRUE):
  1. Running `pip install -e .` installs the package and CLI entry points are available
  2. PostgreSQL database initializes via Alembic migration with companies, daily_scores, signal_details, and pipeline_runs tables -- all using dual timestamps (as_of_date, observed_date) and append-only design
  3. All configuration (signal weights, thresholds, API identities, refresh cadences) loads from YAML/env files with Pydantic validation, not hardcoded values
  4. Running a second Alembic migration on an already-migrated database is a no-op (idempotent migrations)
**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md -- Package scaffold, Typer CLI, Pydantic config, structlog logging, test infrastructure
- [x] 01-02-PLAN.md -- SQLAlchemy ORM models (companies, daily_scores, signal_details, pipeline_runs) with dual timestamps, session factory
- [x] 01-03-PLAN.md -- Alembic migration framework, initial schema migration, integration tests with testcontainers

### Phase 2: Entity Resolution and Universe Builder
**Goal**: The system can identify which mid-cap companies are making AI claims and map each company's identity across SEC (CIK), USPTO (patent assignee), GitHub (org), and job postings (employer name)
**Depends on**: Phase 1
**Requirements**: FNDN-02, FNDN-03
**Success Criteria** (what must be TRUE):
  1. Given a target company, the system resolves its CIK, ticker, patent assignee name, GitHub org URL, and job posting employer name into a single unified record with aliases
  2. The universe builder queries EDGAR full-text search for AI keywords and filters results to mid-cap companies ($2B-$10B market cap), producing a target list of 200-500 companies
  3. Running the universe builder twice on the same day produces the same target list (deterministic)
**Plans:** 5 plans

Plans:
- [x] 02-01-PLAN.md -- Install dependencies, Company model update (is_active), Alembic migration 002, Pydantic type contracts
- [x] 02-02-PLAN.md -- EFTS paginated search client, EDGAR company facts client (EntityPublicFloat, CIK-ticker mapping)
- [x] 02-03-PLAN.md -- Company name normalizer, entity resolver with rapidfuzz fuzzy matching
- [x] 02-04-PLAN.md -- Universe builder orchestrator (EFTS scan -> market cap filter -> entity resolution -> persist)
- [x] 02-05-PLAN.md -- CLI universe commands (scan/list/inspect), integration tests for persistence and lifecycle

### Phase 3: SEC Filing Collection
**Goal**: The system can ingest SEC filings (10-K, 10-Q, 8-K) and extract structured XBRL financial data for every company in the target universe, respecting EDGAR rate limits
**Depends on**: Phase 2
**Requirements**: SEC-01, SEC-03, SEC-05
**Success Criteria** (what must be TRUE):
  1. For any company in the target universe, the system retrieves and stores their most recent 10-K, 10-Q, and 8-K filings with full text content
  2. XBRL financial data (R&D spending, CapEx, revenue) is extracted from company filings and stored with correct dual timestamps
  3. All EDGAR requests include the required User-Agent header and respect the 10 req/sec rate limit -- no 403 errors under normal operation
  4. Running collection for a company that was already collected today skips re-fetching (idempotent daily runs)
**Plans:** 1/4 plans executed

Plans:
- [x] 03-01-PLAN.md -- Pydantic type contracts (FilingData, XBRLFactRecord, XBRL_TAG_GROUPS), ORM models (Filing, XBRLFact), Alembic migration 003, FilingCollectionSettings
- [x] 03-02-PLAN.md -- FilingClient wrapping edgartools for filing retrieval and section extraction (10-K/10-Q/8-K)
- [x] 03-03-PLAN.md -- XBRLExtractor for multi-tag financial data extraction (R&D, CapEx, revenue) with fallback tags and deduplication
- [x] 03-04-PLAN.md -- FilingCollector orchestrator with idempotent persistence, CLI collect commands (company/all/dry-run)

### Phase 4: SEC Scoring and Compute Signal
**Goal**: The system produces SEC filing mismatch scores and compute spending gap scores for target companies -- the first two signals operational end-to-end from raw data to stored scores
**Depends on**: Phase 3
**Requirements**: SEC-02, SEC-04, COMP-01, COMP-02, COMP-03, SCORE-02
**Success Criteria** (what must be TRUE):
  1. For any company with SEC filings, the system counts AI/ML keyword frequency across filing sections (MD&A, Risk Factors, Business Description) over 3-5 year windows and computes a filing mismatch score (0-100)
  2. The compute spending gap score (0-100) correctly flags companies with flat CapEx/cloud spending despite growing AI narrative -- using XBRL data and earnings transcript mentions
  3. Per-signal sub-scores are stored alongside the analysis evidence in the database for auditability
  4. Scores for the same company on the same day are identical when re-run (deterministic scoring)
**Plans:** 4 plans

Plans:
- [x] 04-01-PLAN.md -- Analysis types, two-tier keyword lexicon, CAGR growth utilities, sigmoid normalization
- [x] 04-02-PLAN.md -- SEC filing mismatch scorer (keyword growth vs R&D growth ratio divergence)
- [x] 04-03-PLAN.md -- Compute spending gap scorer (CapEx trend + cloud mention analysis)
- [x] 04-04-PLAN.md -- Scoring orchestrator, DB persistence, CLI score commands, config extension

### Phase 5: Patent Signal
**Goal**: The system produces patent gap scores by comparing a company's AI patent filings against its AI claim intensity
**Depends on**: Phase 2
**Requirements**: PAT-01, PAT-02, PAT-03
**Success Criteria** (what must be TRUE):
  1. The system queries the new PatentSearch API at data.uspto.gov for AI-related patents (CPC codes G06N, G06F18) by company, correctly mapping patent assignee names to the entity resolution table
  2. The patent gap score (0-100) reflects the divergence between a company's AI claim intensity (from filings) and its actual AI patent filing trend
  3. Patent data refreshes weekly without re-fetching patents already stored (incremental collection)
**Plans:** 3 plans

Plans:
- [x] 05-01-PLAN.md -- Patent type contracts (PatentRecord, PatentForScoring), Patent ORM model, Alembic migration 004, PatentGapScoringConfig
- [x] 05-02-PLAN.md -- PatentSearch API client with pagination/rate limiting, PatentCollector with incremental collection and assignee alias expansion
- [x] 05-03-PLAN.md -- Patent gap scorer (pure function), scoring orchestrator extension, CLI patent commands

### Phase 6: GitHub Signal
**Goal**: The system produces GitHub activity scores measuring genuine ML code activity versus absence or abandonment for target companies
**Depends on**: Phase 2
**Requirements**: GH-01, GH-02, GH-03
**Success Criteria** (what must be TRUE):
  1. For any company with a mapped GitHub organization, the system analyzes repo count, language breakdown, commit recency, and ML framework imports (TensorFlow, PyTorch, scikit-learn in requirements/pyproject)
  2. The GitHub activity score (0-100) distinguishes between active ML development, dormant repos, and no GitHub presence
  3. All GitHub API requests stay within the 5,000 req/hr rate limit using a token -- no 429 errors under normal operation
**Plans**: TBD

Plans:
- [x] 06-01: TBD
- [x] 06-02: TBD
- [x] 06-03: TBD
- [x] 06-04: TBD
- [ ] 06-05: TBD

### Phase 7: Earnings Call Signal
**Goal**: The system produces vagueness scores for earnings calls by distinguishing buzzword-heavy AI claims from substantive technical discussion
**Depends on**: Phase 2
**Requirements**: EARN-01, EARN-02, EARN-03, EARN-04, EARN-05
**Success Criteria** (what must be TRUE):
  1. Earnings call transcripts are ingested for target companies using free sources, with quarterly refresh tied to the earnings calendar
  2. The dual-lexicon scorer correctly classifies vague AI claims ("AI-powered", "leveraging AI") separately from substantive claims ("deployed transformer model", "reduced MAPE by 15%") producing a buzzword density ratio
  3. FinBERT sentiment analysis runs on earnings call segments, producing positive/negative/neutral classification that is stored as a supplementary signal (not the primary vagueness detector)
  4. The vagueness score (0-100) combines buzzword density ratio with sentiment-vs-metrics mismatch into a single interpretable number
**Plans:** 4 plans

Plans:
- [x] 07-01-PLAN.md -- Install dependencies (earningscall, transformers, torch), earnings type contracts, ORM model, migration 006, config extensions
- [x] 07-02-PLAN.md -- EarningsClient API wrapper with lazy validation, EarningsCollector orchestrator, CLI earnings commands
- [x] 07-03-PLAN.md -- FinBERT chunked sentiment analyzer, earnings-specific dual-lexicon keyword constants
- [x] 07-04-PLAN.md -- Pure earnings vagueness scorer, ScoringOrchestrator extension, CLI score integration

### Phase 8: Job Posting Signal
**Goal**: The system produces job mismatch scores comparing AI claim intensity to actual AI hiring activity and role quality
**Depends on**: Phase 2
**Requirements**: JOB-01, JOB-02, JOB-03, JOB-04, JOB-05
**Success Criteria** (what must be TRUE):
  1. AI-related job postings are ingested for target companies using JobSpy or similar free scraping sources, with deduplication removing syndicated duplicates via deterministic hash matching (company + title + location)
  2. The role classifier correctly distinguishes AI/ML engineering roles from marketing/strategy roles that merely mention AI in title or description
  3. Job posting lifecycle tracking records first_seen, last_seen, and flags stale postings (90+ days open) as potential ghost jobs
  4. The job mismatch score (0-100) compares AI claim intensity to actual AI hiring activity and role quality -- treating unfilled roles as neutral-to-negative
**Plans:** 3/4 plans executed

Plans:
- [x] 08-01-PLAN.md -- Install python-jobspy, job type contracts (role classifier, dedup hash), JobPosting ORM model, migration 007, JobMismatchScoringConfig
- [x] 08-02-PLAN.md -- JobClient wrapper around python-jobspy, JobCollector with lifecycle tracking, CLI job commands
- [x] 08-03-PLAN.md -- Pure job mismatch scorer (sub-factors: hiring intensity, specificity, ghost ratio, marketing ratio)
- [x] 08-04-PLAN.md -- ScoringOrchestrator extension with _load_job_postings, CLI score integration

### Phase 9: Composite Scoring and Integration API
**Goal**: All six signals combine into a single composite AI Washing Risk Score with configurable weights, graceful degradation, and a clean Python API for downstream modules
**Depends on**: Phase 4, Phase 5, Phase 6, Phase 7, Phase 8
**Requirements**: SCORE-01, SCORE-03, SCORE-04, SCORE-05, INT-02, INT-03
**Success Criteria** (what must be TRUE):
  1. The composite AI Washing Risk Score (0-100) is computed as a weighted average of all 6 sub-scores with configurable weights (default: Jobs 25%, SEC 20%, Earnings 20%, Patents 15%, GitHub 10%, Compute 10%)
  2. When one or more data sources are unavailable, the system produces a partial score with re-normalized weights and attaches a reduced confidence indicator -- it never fails silently
  3. Score interpretation thresholds classify companies into risk bands: 0-30 (genuine), 30-60 (mixed), 60-80 (significant risk), 80-100 (strong short candidate)
  4. All scores are immutable -- each daily run produces new snapshot rows, never updates or deletes existing score records
  5. The Python package API exposes get_score(ticker, date), get_latest_scores(), and get_score_history(ticker, start, end) returning immutable dataclasses with composite, sub-scores, confidence level, data freshness, and pipeline_run_id
**Plans:** 1/3 plans executed

Plans:
- [x] 09-01-PLAN.md -- Pure composite scorer (weighted average, graceful degradation, risk bands), API type contracts, config extension
- [ ] 09-02-PLAN.md -- ScoringOrchestrator DailyScore persistence (idempotent), CLI composite command
- [x] 09-03-PLAN.md -- Public Python API (get_score, get_latest_scores, get_score_history) returning frozen dataclasses

### Phase 10: Data Quality and Pipeline Automation
**Goal**: The system runs autonomously on a daily schedule with comprehensive data validation, staleness monitoring, structured logging, and per-stage error handling -- no human intervention required
**Depends on**: Phase 9
**Requirements**: DQ-01, DQ-02, DQ-03, OPS-01, OPS-02, OPS-03, OPS-04
**Success Criteria** (what must be TRUE):
  1. All ingested data passes Pydantic schema validation before processing -- malformed records are rejected with structured error logs, not silently dropped
  2. Data source availability monitoring tracks last-successful-fetch per source and flags staleness exceeding expected cadence (daily for SEC, weekly for patents, quarterly for earnings)
  3. The daily batch pipeline runs ingestion, analysis, scoring, and output in sequence with Prefect orchestration -- each stage has independent error handling and retry logic with exponential backoff
  4. Every pipeline run is tracked with start_time, end_time, status (succeeded/partially_failed/failed), companies_processed count, and per-source error details
  5. Structured JSON logs via structlog include correlation IDs per pipeline run, enabling tracing any score back to its collection and analysis steps
**Plans:** 4/4 plans complete

Plans:
- [x] 10-01-PLAN.md -- Install prefect, pipeline type contracts (StageResult, PipelineRunResult), DataSourceStatus ORM model, migration 008
- [x] 10-02-PLAN.md -- Pydantic validation wrappers at ingestion boundaries, staleness monitoring logic
- [x] 10-03-PLAN.md -- Correlation ID helpers, PipelineRun lifecycle management, retry decorator audit
- [x] 10-04-PLAN.md -- Prefect daily flow with stage tasks, per-stage error isolation, pipeline CLI commands

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10
Note: Phases 5 and 6 depend only on Phase 2 and can execute in parallel after Phase 4 completes (or after Phase 2 if schedule permits).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Project Skeleton and Database | 3/3 | Complete | 2026-03-27 |
| 2. Entity Resolution and Universe Builder | 5/5 | Complete | 2026-03-28 |
| 3. SEC Filing Collection | 4/4 | Complete | 2026-03-28 |
| 4. SEC Scoring and Compute Signal | 0/4 | Not started | - |
| 5. Patent Signal | 0/3 | Not started | - |
| 6. GitHub Signal | 2/4 | In Progress|  |
| 7. Earnings Call Signal | 0/4 | Not started | - |
| 8. Job Posting Signal | 3/4 | In Progress|  |
| 9. Composite Scoring and Integration API | 1/3 | In Progress|  |
| 10. Data Quality and Pipeline Automation | 4/4 | Complete    | 2026-03-30 |
