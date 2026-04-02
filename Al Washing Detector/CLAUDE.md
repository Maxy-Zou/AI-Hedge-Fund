# AI Washing Detector

## Project Overview
Quantitative tool to detect "AI washing" in mid-cap public companies ($2B-$10B market cap). Scores companies on the gap between AI claims and actual AI investment, surfacing short candidates for a hedge fund strategy.

## Tech Stack
- **Language:** Python 3.11+
- **SEC Data:** edgartools
- **Patents:** USPTO PatentSearch API (search.patentsview.org/api/v1) — requires API key (free, request at PatentsView support portal)
- **NLP:** FinBERT (HuggingFace transformers) + Claude API for nuanced analysis
- **Database:** PostgreSQL + SQLAlchemy
- **Dashboard:** Streamlit
- **Scheduling:** APScheduler
- **Testing:** pytest

## Architecture
```
src/ai_washer/          # Main package (pip-installable)
  __init__.py           # Package root, __version__
  __main__.py           # python -m ai_washer
  cli.py                # Typer CLI entry points
  config.py             # Pydantic settings (env + YAML)
  logging.py            # structlog configuration
  db/                   # Database layer
    base.py             # DeclarativeBase, mixins
    models.py           # ORM models (Company, DailyScore, etc.)
    session.py          # Engine + session factory
    migrations/         # Alembic migrations
      env.py
      versions/
  ingestion/            # Data fetchers (SEC, patents, jobs, etc.) [future]
  analysis/             # NLP pipelines, scoring engine [future]
config/                 # YAML configuration files
  scoring.yaml          # Signal weights and thresholds
tests/
  unit/
  integration/
```

## Key APIs & Data Sources
- SEC EDGAR API (data.sec.gov) — no API key needed
- USPTO PatentSearch API (search.patentsview.org/api/v1) — requires free API key (legacy api.patentsview.org discontinued May 2025). Request key at https://patentsview-support.atlassian.net/servicedesk/customer/portal/1/group/1/create/18. Graceful degradation when key unavailable.
- TheirStack API (theirstack.com) — job postings, requires API key
- GitHub REST API v3 — requires token for higher rate limits
- EarningsCall / Financial Modeling Prep — earnings transcripts

## Environment Variables
Store all API keys and secrets in `.env` (never commit):
```
EDGAR_IDENTITY=name email    # Required by SEC for identification
PATENTSVIEW_API_KEY=         # USPTO PatentSearch API key (free, request at PatentsView support portal)
THEIRSTACK_API_KEY=
GITHUB_TOKEN=
FMP_API_KEY=
ANTHROPIC_API_KEY=
DATABASE_URL=postgresql://...
```

## Development Rules
- Use virtual environment: `.venv/`
- All data fetchers must implement retry logic with exponential backoff
- SEC EDGAR requires a User-Agent with company/name + email (legal requirement)
- Rate limit all API calls (SEC: 10 req/sec max, be conservative)
- Financial data must be immutable — never overwrite historical records, append new snapshots
- Scoring weights are configurable via `config/scoring.yaml`
- All monetary values stored in cents (integers) to avoid floating point issues

## Signal Weights (Default)
| Signal | Weight |
|--------|--------|
| Job Posting Mismatch | 25% |
| SEC Filing Mismatch | 20% |
| Patent Gap | 15% |
| Earnings Call Vagueness | 20% |
| GitHub Inactivity | 10% |
| Compute Spending Gap | 10% |

<!-- GSD:project-start source:PROJECT.md -->
## Project

**AI Washing Detector**

An autonomous module in a fully automated AI hedge fund that scores mid-cap public companies ($2B-$10B market cap) on the gap between their AI claims and actual AI investment. Produces daily AI Washing Risk Scores across 6 signals, writing structured results to a shared database for downstream portfolio management and trade execution modules to consume. One of the first modules being built for the fund — no human reviews individual trade decisions.

**Core Value:** Accurately quantify the gap between what companies *say* about AI and what they *do* — producing reliable, machine-consumable signals that an automated trading system can act on without human review.

### Constraints

- **Data sources**: Free or free-tier APIs for v1 — SEC EDGAR (10 req/sec limit), USPTO PatentSearch API (free API key required, graceful degradation when unavailable), GitHub (5,000 req/hr with token)
- **Immutability**: Financial data must never be overwritten — append new snapshots only. All monetary values stored as integers (cents).
- **SEC compliance**: EDGAR requires User-Agent with company name + email (legal requirement)
- **Autonomy**: Module must operate without human intervention — robust error handling, retry logic, graceful degradation when a data source is unavailable
- **Refresh cadence**: Daily batch processing
- **Language**: Python 3.11+ (best ecosystem for NLP + financial data)
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Package Management & Tooling
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| uv | >=0.11.2 | Package manager, virtual env, Python version management | 10-100x faster than pip, single binary replaces pip+poetry+pyenv+virtualenv. Written in Rust by the Astral team. Standard for new Python projects in 2026. |
| ruff | >=0.15.7 | Linting + formatting | Replaces flake8, black, isort, pyupgrade in one tool. 10-100x faster (Rust). Single config in pyproject.toml. |
| Python | >=3.11, <3.14 | Runtime | Best ecosystem for NLP + financial data. 3.11+ for performance gains and exception groups. Upper bound for library compatibility. |
### Core Framework & Runtime
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Typer | >=0.24.1 | CLI interface for manual runs and debugging | Type-hint-based CLI with zero boilerplate. Built on Click so escape hatch exists. No web framework needed -- this module has no UI. |
| Pydantic | >=2.12.5 | Data validation, settings, schema enforcement | Rust-core validation (fastest in Python). Type-safe models for financial data. pydantic-settings for env config. Universal in the Python ecosystem. |
### Data Ingestion
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| edgartools | >=5.23.2 | SEC EDGAR filing access and parsing | Free, no API keys, no rate limits. Parses 20+ filing types into typed Python objects with DataFrames. XBRL standardization from 32K+ real filings. Actively maintained (weekly releases). MCP server for Claude integration. The clear winner over sec-api (paid) and direct EDGAR scraping (painful). |
| httpx | >=0.28.1 | HTTP client for USPTO, GitHub, and job APIs | Sync and async in one library. HTTP/2 support. Connection pooling. Drop-in replacement for requests with async capability. Use for all non-edgartools API calls. |
| python-jobspy | latest | LinkedIn + Indeed + Glassdoor job scraping | Aggregates 8+ job boards in one call. Returns structured data with title, company, description, salary, date. Free, no API key. LinkedIn rate-limits around page 10, but Indeed has no limit. Best free option for v1. |
| beautifulsoup4 + lxml | latest | HTML parsing for filings and web content | bs4 with lxml parser is the standard for HTML/XML parsing. edgartools uses lxml internally. Keep for any supplementary parsing (earnings transcripts, etc). |
### NLP & Analysis
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| transformers | >=5.3.0 | FinBERT model loading and inference | HuggingFace transformers v5 is the model-definition framework. Use `pipeline("sentiment-analysis", model="ProsusAI/finbert")` for zero-config sentiment. Batch inference via `batch_size` parameter. |
| torch | >=2.5 | FinBERT inference backend | Required by transformers for model inference. CPU-only is fine for daily batch on ~200 companies. No GPU needed at this scale. |
| ProsusAI/finbert | - | Financial sentiment classification | 89% accuracy on financial text vs 76% for generic BERT. Pre-trained on financial corpus. Three-class output (positive/negative/neutral). Use for earnings call vagueness and SEC filing sentiment. |
| pandas | >=3.0.1 | Data manipulation and analysis | pandas 3.0 (Jan 2026) with PyArrow backend by default. Used for tabular analysis of scores, time series, and signal computation. |
| numpy | >=2.0 | Numerical computation | Required by pandas and transformers. Use for score normalization and statistical operations. |
### Database
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | >=16 | Primary data store | ACID compliance for financial data. JSONB for semi-structured filing content. Partitioning for time-series score history. Mature, battle-tested, free. |
| SQLAlchemy | >=2.0.48 | ORM and database toolkit | 2.0-style with type annotations. Both sync and async support. Repository pattern friendly. `mapped_column()` for declarative models. |
| asyncpg | latest | Async PostgreSQL driver | Fastest async PG driver for Python. Required by SQLAlchemy async engine (`postgresql+asyncpg`). |
| psycopg | >=3.2 | Sync PostgreSQL driver | psycopg3 (not psycopg2) for sync operations. Pure Python with optional C speedups. Used by Alembic migrations. |
| Alembic | >=1.18.4 | Database migrations | De facto standard for SQLAlchemy migrations. Autogenerate from model changes. Transactional migrations on PostgreSQL. |
### Workflow Orchestration
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Prefect | >=3.6.23 | Pipeline orchestration, scheduling, monitoring | Python-native with decorator API (`@flow`, `@task`). Built-in retries, caching, event-driven automations. Open-source events/automation system (previously Cloud-only). Transactional interface for idempotent pipelines. No DAG files or YAML -- pure Python. Replaces APScheduler (too simple) and Celery (too complex for batch). |
### Resilience & HTTP
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| tenacity | >=9.1.4 | Retry logic with exponential backoff | Decorator-based retries for API calls. Configurable wait strategies (exponential, random jitter). Handles SEC EDGAR 10 req/sec limit and GitHub 5K req/hr limit gracefully. Sync and async support. |
### Logging & Observability
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| structlog | >=25.5.0 | Structured logging | JSON output for production, human-readable for dev. Processor pipeline for adding context (company_cik, signal_type, score). Essential for autonomous system -- structured logs are how you debug without a UI. |
### Testing
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pytest | >=9.0.2 | Test framework | Industry standard. Fixtures, parametrize, plugins. Best ecosystem. |
| pytest-cov | >=7.1.0 | Coverage reporting | Target 80%+ coverage per project requirements. |
| pytest-asyncio | >=1.0 | Async test support | Required for testing async database operations and HTTP calls. |
| pytest-httpx | latest | HTTP mocking for httpx | Mock external API calls (SEC, USPTO, GitHub, jobs) in tests. Prevents flaky tests from real API calls. |
| factory-boy | latest | Test data factories | Generate realistic test fixtures for Company, Filing, Patent, Score models. Better than hand-crafted fixtures for financial data. |
| freezegun | latest | Time mocking | Mock dates for testing "daily batch" logic, score history, and time-dependent scoring. |
### CLI & Developer Experience
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| rich | latest | Terminal output formatting | Pretty tables, progress bars, and colored output for CLI. Used by edgartools internally. |
| typer | >=0.24.1 | CLI framework | (see Core Framework section above) |
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| SEC Data | edgartools | sec-api | sec-api requires paid API key. edgartools is free, faster iteration, better Python objects, more actively maintained. sec-api's only advantage is real-time WebSocket stream, which we do not need for daily batch. |
| SEC Data | edgartools | Direct EDGAR API + requests | Enormous parsing burden. edgartools handles 20+ filing types, XBRL standardization, caching. Reimplementing this is months of work for no benefit. |
| NLP | FinBERT (local) | Claude API | Claude API adds per-call cost and latency. FinBERT runs locally, is free, and 89% accurate on financial sentiment. Claude API is overkill for keyword frequency and vagueness detection. Reserve Claude for future "qualitative analysis" upgrade, not v1. |
| NLP | FinBERT (local) | Custom fine-tuned model | Premature optimization. FinBERT works out-of-the-box. Fine-tuning requires labeled training data we do not have yet. Add fine-tuning in a later phase after collecting labeled examples from v1 scores. |
| Orchestration | Prefect | APScheduler | APScheduler is single-process, no retry/caching/monitoring. Fine for cron but not for a multi-step pipeline with 6 signal sources that can fail independently. |
| Orchestration | Prefect | Celery | Celery requires Redis/RabbitMQ broker, worker processes, complex config. Designed for distributed task queues, not batch data pipelines. Massive overhead for a daily batch job. |
| Orchestration | Prefect | Airflow | Airflow requires separate scheduler/webserver/database. DAG files, YAML config, heavier infra. Prefect is simpler for a small team (2-5 people) with pure Python API. |
| Database | PostgreSQL | SQLite | Cannot handle concurrent writes from multiple signal pipelines. No JSONB. No partitioning. Not suitable for shared DB consumed by downstream trading modules. |
| Database | PostgreSQL | MongoDB | Financial data is inherently relational (company -> filings -> scores). ACID compliance required for immutable snapshots. PostgreSQL JSONB gives document flexibility where needed. |
| HTTP Client | httpx | requests | requests has no async support and never will. httpx provides both sync and async with HTTP/2. Future-proof choice. |
| HTTP Client | httpx | aiohttp | aiohttp is async-only (no sync fallback). httpx works in both modes. Simpler API. |
| Job Scraping | python-jobspy | linkedin-jobs-scraper | linkedin-jobs-scraper is LinkedIn-only and uses headless browser (heavy). JobSpy aggregates 8 job boards, returns structured data, lighter weight. |
| Job Scraping | python-jobspy | TheirStack API | TheirStack is paid. v1 uses free sources only. JobSpy is free and open source. |
| Package Manager | uv | poetry | uv is 10-100x faster, handles Python version management, simpler lockfile. Poetry still better for library publishing, but this is an application, not a library. |
| Package Manager | uv | pip + venv | uv is a drop-in replacement with 10-100x speed. No reason to use raw pip in 2026. |
| Linter/Formatter | ruff | black + flake8 + isort | ruff replaces all three in one tool, 10-100x faster. Single config file. |
| Testing | pytest | unittest | pytest has better fixtures, parametrize, plugins, and community. unittest is verbose and outdated. |
| Logging | structlog | stdlib logging | structlog provides structured JSON output, processor pipelines, and bound loggers. stdlib logging is unstructured and harder to parse in production. |
## Architecture Decisions
### Why Not async-first?
- **Sync SQLAlchemy** for database operations (simpler, Alembic-compatible)
- **httpx sync client** for most API calls
- **httpx async client** only for parallel API calls within a signal (e.g., fetching 200 companies' GitHub data concurrently)
### Why FinBERT over Claude API for v1?
### Why PostgreSQL integers for money?
## Installation
# Install uv (if not already installed)
# Create project
# Set Python version
# Core dependencies
# NLP dependencies (separate because torch is large)
# Dev dependencies
## Version Pinning Strategy
## Confidence Assessment
| Component | Confidence | Basis |
|-----------|------------|-------|
| edgartools | HIGH | PyPI verified (5.23.2), active GitHub, official docs, clear market leader for free SEC access |
| FinBERT via transformers | HIGH | HuggingFace model hub verified, transformers 5.3.0 on PyPI, published accuracy benchmarks |
| PostgreSQL + SQLAlchemy | HIGH | Industry standard, SQLAlchemy 2.0.48 verified on PyPI, Alembic 1.18.4 verified |
| Prefect | HIGH | v3.6.23 verified on PyPI, open-source events system, Python-native API, strong community |
| httpx | MEDIUM | 0.28.1 stable but 1.0 still in dev preview. Stable enough for production use, widely adopted. |
| python-jobspy | MEDIUM | Active on PyPI/GitHub, but LinkedIn rate-limiting is a known issue. May need proxy rotation or fallback to Indeed-only for reliability. |
| uv + ruff | HIGH | Both from Astral, massive adoption in 2025-2026, verified latest versions on PyPI |
| structlog | HIGH | Mature library (25.5.0), standard for structured logging in Python |
## Sources
- [edgartools PyPI](https://pypi.org/project/edgartools/) - v5.23.2 (Mar 2026)
- [edgartools GitHub](https://github.com/dgunning/edgartools) - MIT license, active development
- [edgartools docs](https://edgartools.readthedocs.io/) - Complete guide to SEC filings in Python
- [ProsusAI/finbert on HuggingFace](https://huggingface.co/ProsusAI/finbert) - Financial sentiment model
- [transformers PyPI](https://pypi.org/project/transformers/) - v5.3.0 (Mar 2026)
- [SQLAlchemy PyPI](https://pypi.org/project/SQLAlchemy/) - v2.0.48 (Mar 2026)
- [Alembic PyPI](https://pypi.org/project/alembic/) - v1.18.4 (Feb 2026)
- [Prefect PyPI](https://pypi.org/project/prefect/) - v3.6.23 (Mar 2026)
- [Prefect 3.0 What's New](https://docs.prefect.io/v3/get-started/whats-new-prefect-3) - Events, transactions, performance
- [httpx PyPI](https://pypi.org/project/httpx/) - v0.28.1 stable
- [python-jobspy GitHub](https://github.com/speedyapply/JobSpy) - Multi-board job scraper
- [Pydantic docs](https://docs.pydantic.dev/latest/) - v2.12.5
- [structlog docs](https://www.structlog.org/) - v25.5.0
- [tenacity PyPI](https://pypi.org/project/tenacity/) - v9.1.4 (Feb 2026)
- [pytest PyPI](https://pypi.org/project/pytest/) - v9.0.2
- [ruff PyPI](https://pypi.org/project/ruff/) - v0.15.7 (Mar 2026)
- [uv PyPI](https://pypi.org/project/uv/) - v0.11.2 (Mar 2026)
- [pandas PyPI](https://pypi.org/project/pandas/) - v3.0.1 (Feb 2026)
- [USPTO PatentSearch API](https://search.patentsview.org/api/v1) - New API replacing legacy api.patentsview.org (discontinued May 2025)
- [typer docs](https://typer.tiangolo.com/) - v0.24.1 (Feb 2026)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->


<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
