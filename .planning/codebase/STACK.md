# Technology Stack

**Analysis Date:** 2026-03-28

## Languages

**Primary:**
- Python 3.12 - Backend logic, data ingestion, analysis, and CLI

**Secondary:**
- SQL - PostgreSQL data definition and queries (via SQLAlchemy ORM)

## Runtime

**Environment:**
- Python 3.12 (specified in `.python-version`)
- Minimum: Python 3.11
- Maximum: Python 3.13 (constrained by `requires-python = ">=3.11,<3.14"` in `pyproject.toml`)

**Package Manager:**
- uv (recommended, not currently locked in repo)
- Lock file: `uv.lock` present (276 KB)

## Frameworks

**Core Application:**
- Typer 0.24.1+ - CLI framework for command-line interface (`src/ai_washer/cli.py`)
  - Subcommands: `universe` (universe scanning), `collect` (SEC filing collection), `check-config`

**Data Access:**
- SQLAlchemy 2.0.48+ - ORM and database toolkit
  - Configuration: `src/ai_washer/db/session.py` creates engine from `database_url` setting
  - Models: `src/ai_washer/db/models.py` (Company, DailyScore, SignalDetails, PipelineRuns, SecFilings, XBRLFacts)
- Alembic 1.18.4+ - Database migrations
  - Migrations directory: `src/ai_washer/db/migrations/versions/`

**Configuration:**
- Pydantic 2.12.5+ - Data validation and type-safe settings
  - YAML support via pydantic-settings[yaml] 2.13.1+
  - Settings classes in `src/ai_washer/config.py`: AppSettings, SignalWeights, UniverseSettings, FilingCollectionSettings, ScoringConfig

**Logging:**
- structlog 25.5.0+ - Structured logging with processor pipelines
  - Configuration: `src/ai_washer/logging.py`
  - JSON output for production, human-readable for development

**Testing:**
- pytest 9.0+ - Test framework
  - pytest-cov 7.0+ - Coverage reporting (target: 80%+)
  - pytest-timeout 2.3+ - Test timeout management
  - pytest-httpx 0.36.0+ - HTTP mocking for httpx client
  - factory-boy 3.3+ - Test data factories
  - testcontainers[postgres] 4.14+ - PostgreSQL containers for integration tests
  - freezegun 1.5.5+ - Time mocking for temporal tests
- Test configuration: `pyproject.toml` [tool.pytest.ini_options]
  - Marker for integration tests: `@pytest.mark.integration`
  - Test paths: `tests/`
  - File pattern: `test_*.py`

**Linting & Formatting:**
- ruff 0.15+ - Fast Python linter and formatter (replaces black, flake8, isort, pyupgrade)
  - Line length: 100
  - Target version: py312
  - Rules: E, F, I, N, W, UP, B, SIM
  - Configuration: `pyproject.toml` [tool.ruff]

## Key Dependencies

**HTTP & API Communication:**
- httpx 0.28.1+ - Async/sync HTTP client for SEC EDGAR, USPTO, GitHub APIs
  - Used in: `src/ai_washer/ingestion/edgar_client.py`, `src/ai_washer/ingestion/efts_client.py`
  - Supports both sync and async workflows
- tenacity 9.1.4+ - Retry logic with exponential backoff
  - Configured in: `src/ai_washer/ingestion/edgar_client.py`, `src/ai_washer/ingestion/efts_client.py`
  - SEC EDGAR rate limit: 10 req/sec (enforced with 0.1s delays in `edgar_client.py`)

**SEC Data Access:**
- edgartools 5.26.1+ - SEC EDGAR filing parsing and XBRL data extraction
  - Free, no API key required
  - Core ingestion module: `src/ai_washer/ingestion/filing_client.py`
  - XBRL extraction: `src/ai_washer/ingestion/xbrl_extractor.py`
  - Parses 10-K, 10-Q, 8-K forms with configurable section limits

**Database:**
- psycopg[binary] 3.2+ - PostgreSQL async/sync driver
  - Binary compilation included for performance
  - Driver URL scheme: `postgresql+psycopg://`

**Text Matching:**
- rapidfuzz 3.14.3+ - Fuzzy string matching for entity resolution
  - Used in: `src/ai_washer/entity/normalizer.py`, `src/ai_washer/entity/resolver.py`
  - Fuzzy match threshold: 85 (configurable in UniverseSettings)

**CLI & Output:**
- rich 14.0+ - Terminal formatting for pretty tables, progress bars, colored output
  - Used in CLI commands for user-friendly output

**YAML Configuration:**
- pyyaml 6.0+ - YAML parsing for scoring configuration
  - Config file: `config/scoring.yaml`
  - Weights configured for 6 signals: sec_filing, patent_gap, earnings_call, job_posting, github_activity, compute_spending
  - Risk thresholds: high_risk_threshold (60), low_risk_threshold (30)

## Configuration

**Environment:**
- Environment variables with `AI_WASHER_` prefix (loaded from `.env` or environment)
- `.env.example` documents required configuration

**Required Environment Variables:**
- `AI_WASHER_DATABASE_URL` - PostgreSQL connection string
  - Format: `postgresql+psycopg://user:password@host:port/database`
- `AI_WASHER_EDGAR_IDENTITY` - SEC-compliant User-Agent string
  - Format: `YourCompany your.email@example.com` (required by SEC EDGAR)
- `AI_WASHER_GITHUB_TOKEN` (optional) - GitHub API token for higher rate limits
- `AI_WASHER_LOG_LEVEL` (optional, default: INFO) - Logging level

**Build:**
- Build backend: hatchling
- Build configuration in `pyproject.toml` [build-system]
- Package location: `src/ai_washer` (pip-installable)
- Entry point: `ai-washer = "ai_washer.cli:app"`

**Configuration Files:**
- `config/scoring.yaml` - Signal weights and risk thresholds (YAML format)
- `config/scoring.example.yaml` - Example configuration template
- `alembic.ini` - Alembic migration settings

## Platform Requirements

**Development:**
- Python 3.11+ (3.12 recommended)
- PostgreSQL 12+ (tested with binary psycopg driver)
- Virtual environment: `.venv/` directory

**Production:**
- Python 3.12 runtime
- PostgreSQL 16+ (for JSONB and partitioning support)
- Deployment target: Autonomous batch scheduler (daily processing)

**Testing Environment:**
- PostgreSQL via testcontainers[postgres] for integration tests
- Python 3.12 with pytest runner

---

*Stack analysis: 2026-03-28*
