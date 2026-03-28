# External Integrations

**Analysis Date:** 2026-03-28

## APIs & External Services

**SEC EDGAR:**
- SEC EDGAR full-text search (EFTS)
  - Service: https://efts.sec.gov/LATEST/search-index
  - What it's used for: Full-text search of SEC filings for AI-claiming companies
  - SDK/Client: edgartools (internal HTTP via httpx)
  - Rate limit: 10 req/sec (enforced in `src/ai_washer/ingestion/edgar_client.py` with 0.1s delays)
  - Auth: User-Agent header with SEC-compliant identity string (env var `AI_WASHER_EDGAR_IDENTITY`)
  - Implementation: `src/ai_washer/ingestion/efts_client.py` (EFTSClient class)

**SEC EDGAR Company Facts (XBRL):**
- SEC XBRL company facts API
  - Service: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
  - What it's used for: Fetching EntityPublicFloat and other XBRL facts for market cap filtering
  - SDK/Client: edgartools + httpx
  - Rate limit: 10 req/sec (enforced in `src/ai_washer/ingestion/edgar_client.py`)
  - Auth: User-Agent header with SEC-compliant identity string
  - Implementation: `src/ai_washer/ingestion/edgar_client.py` (EdgarFactsClient class)

**SEC Company Tickers JSON:**
- SEC company tickers mapping
  - Service: https://www.sec.gov/files/company_tickers.json
  - What it's used for: CIK-to-ticker and company name mapping for universe building
  - SDK/Client: httpx
  - Rate limit: Standard HTTP limits
  - Auth: User-Agent header
  - Implementation: `src/ai_washer/ingestion/edgar_client.py` (get_cik_ticker_mapping)

**SEC Filing Retrieval (10-K, 10-Q, 8-K):**
- SEC EDGAR filing text extraction
  - Service: data.sec.gov (via edgartools)
  - What it's used for: Fetching full filing text and extracting sections (Business, Risk Factors, MD&A)
  - SDK/Client: edgartools
  - Rate limit: 10 req/sec (implemented internally by edgartools)
  - Auth: User-Agent header set via `edgar.set_identity()` in FilingClient.__init__
  - Implementation: `src/ai_washer/ingestion/filing_client.py` (FilingClient class)
  - Configuration: `src/ai_washer/config.py` (FilingCollectionSettings)
    - Form types: 10-K, 10-Q, 8-K (configurable)
    - Section max chars: 50,000 (configurable)
    - Max filings per type: max_8k_filings=10, max_annual_filings=5, max_quarterly_filings=8

## Data Storage

**Databases:**
- PostgreSQL 16+
  - Connection: `AI_WASHER_DATABASE_URL` env var
  - Client: SQLAlchemy 2.0.48+ with psycopg3 (async/sync driver)
  - Engine configuration: `src/ai_washer/db/session.py` (create_engine_from_settings)
  - ORM Models: `src/ai_washer/db/models.py`
    - **companies** - Entity table for tracked public companies (UUID primary key, mutable)
    - **daily_scores** - Append-only daily composite AI washing scores (monthly RANGE partitioning on scored_at)
    - **signal_details** - Append-only individual signal scores with evidence
    - **pipeline_runs** - Operational tracking for batch runs
    - **sec_filings** - Append-only SEC filing text and metadata (Phase 3+)
    - **xbrl_facts** - Append-only XBRL financial data points (Phase 3+)
  - Migrations: Alembic 1.18.4+ (`src/ai_washer/db/migrations/`)
    - Transactional migrations on PostgreSQL
  - All monetary values stored as BIGINT (cents, not dollars) to avoid floating-point issues

**File Storage:**
- Local filesystem only (v1)
- caching: Raw data cached locally to avoid redundant API calls
- No cloud storage configured (S3, GCS, etc.)

**Caching:**
- In-memory via edgartools internal caching
- httpx connection pooling for SEC EDGAR requests
- No external cache system (Redis, Memcached) configured

## Authentication & Identity

**Auth Provider:**
- Custom SEC compliance headers (no OAuth/JWT)

**Implementation:**
- SEC EDGAR requires User-Agent header in format: "CompanyName email@example.com"
- Stored in env var: `AI_WASHER_EDGAR_IDENTITY`
- Set via `edgar.set_identity()` in edgartools before any API calls
- Example: `edgar_identity="YourCompany yourname@example.com"`
- Implementation: `src/ai_washer/config.py` (AppSettings.edgar_identity)

**GitHub (Optional, Rate Limiting Only):**
- Service: GitHub REST API v3
- Purpose: Rate limit increases (5,000 req/hr with token vs 60 req/hr without)
- Token: `AI_WASHER_GITHUB_TOKEN` env var (optional)
- Future use: Job posting verification, software engineering team sizing (not yet implemented)

## Monitoring & Observability

**Error Tracking:**
- None configured (future: Sentry could be added)
- Errors logged structurally via structlog

**Logs:**
- Structured JSON logging via structlog 25.5.0+
- Log level: `AI_WASHER_LOG_LEVEL` env var (default: INFO)
- Configuration: `src/ai_washer/logging.py`
- Output: stdout with JSON formatting in production
- Includes context: company_cik, signal_type, score, API call details, retry attempts

**Retry Tracking:**
- Built-in via tenacity with before_sleep_log callbacks
- Logs all retries with backoff strategy (exponential: 0.1s to 30s max)
- Implements `_is_retryable_error` predicate for HTTP 429 and 5xx errors

## CI/CD & Deployment

**Hosting:**
- Not configured in current codebase
- Intended: Autonomous batch scheduler running daily
- No Docker, Kubernetes, or cloud provider config found

**CI Pipeline:**
- Not configured in current codebase
- Tests run locally via pytest

**Build:**
- Built with hatchling backend
- Entry point: `ai-washer = "ai_washer.cli:app"` (CLI app)
- No deployment pipeline configured yet

## Environment Configuration

**Required env vars:**
- `AI_WASHER_DATABASE_URL` - PostgreSQL connection URL
- `AI_WASHER_EDGAR_IDENTITY` - SEC User-Agent string

**Optional env vars:**
- `AI_WASHER_GITHUB_TOKEN` - GitHub API token for higher rate limits
- `AI_WASHER_LOG_LEVEL` - Logging level (default: INFO)

**Secrets location:**
- `.env` file (Git-ignored, never committed)
- Example template: `.env.example` documents all required and optional variables

**Configuration files (not secrets):**
- `config/scoring.yaml` - Signal weights and risk thresholds (committed)
  - Weights: sec_filing (20%), patent_gap (15%), earnings_call (20%), job_posting (25%), github_activity (10%), compute_spending (10%)
  - Thresholds: high_risk (60), low_risk (30)

## Webhooks & Callbacks

**Incoming:**
- None (batch-only system, no event triggers)

**Outgoing:**
- None configured in v1
- Future: Results written to shared database for downstream portfolio management and trade execution modules

## Data Source Rate Limits & Compliance

**SEC EDGAR:**
- Limit: 10 requests/sec (enforced in code with 0.1s delays)
- User-Agent required per SEC legal requirement
- Retry strategy: Exponential backoff (0.1s to 30s) on 429, 5xx errors

**GitHub API:**
- Limit with token: 5,000 requests/hour
- Limit without token: 60 requests/hour
- Token: Optional in `AI_WASHER_GITHUB_TOKEN`

**USPTO PatentsView API:**
- Not yet implemented in current codebase
- Planned for Phase 4+
- No API key required, free REST API

**Job Posting Data:**
- Not yet implemented in current codebase
- Planned integration: python-jobspy (free, multi-board scraper)
- Alternative: TheirStack API (paid, requires key)

## Third-Party Service Alternatives Evaluated

**SEC Data:**
- Chosen: edgartools (free, no key, actively maintained)
- Alternative rejected: sec-api (paid tier required)
- Alternative rejected: Direct EDGAR scraping (high maintenance burden)

**NLP Sentiment Analysis:**
- Planned: FinBERT via transformers (free, runs locally, 89% accuracy)
- Alternative rejected: Claude API (adds per-call cost and latency for v1)

**HTTP Client:**
- Chosen: httpx (async and sync support, HTTP/2, connection pooling)
- Alternative rejected: requests (no async support)
- Alternative rejected: aiohttp (async-only, no sync fallback)

---

*Integration audit: 2026-03-28*
