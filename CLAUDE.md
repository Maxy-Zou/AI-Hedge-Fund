# AI Hedge Fund

Multi-strategy quantitative trading project. Each strategy lives in its own subfolder with its own CLAUDE.md for strategy-specific context.

## Project Structure

```
AI Hedgefund/
├── CLAUDE.md                # This file — project-wide conventions
├── shared/                  # Common utilities across strategies (when needed)
├── Al Washing Detector/     # Strategy: AI Washing short signal
└── <future strategies>/     # Each subfolder is a self-contained strategy
```

## Stack

- **Language:** Python 3.11+
- **Package management:** TBD per strategy (uv preferred when possible)

## Conventions

- Each strategy subfolder should have its own CLAUDE.md with thesis, data sources, and run instructions
- All API keys and secrets go in `.env` files (never committed)
- Use immutable data patterns — return new objects, don't mutate in place
- Validate all external data (API responses, scraped content, file inputs) at ingestion boundaries

## Data Handling

- Raw data cached locally to avoid redundant API calls
- All timestamps in UTC
- Financial data should preserve source precision (don't round prematurely)

## Running Strategies

Each strategy should define its own entry point and dependencies. Check the strategy's CLAUDE.md for specifics.

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Shared Backtesting Infrastructure**

Strategy-agnostic backtesting framework and historical market data pipeline for the AI Hedge Fund. Collects daily OHLCV price data for mid-cap equities ($2B-$10B market cap), runs vectorized backtests against any signal the fund produces, and generates investor-ready output (interactive dashboard, PDF tearsheets, raw data exports). The first consumer is the AI Washing Detector's short signal, but the framework is designed for any future strategy.

**Core Value:** Produce compelling, realistic backtest results the moment any strategy signal is ready — so investor conversations can start immediately.

### Constraints

- **Data source**: yfinance only for v1 — free, no API key, daily OHLCV
- **Frequency**: Daily bars only — matches the fund's signal cadence
- **History**: 5 years minimum (back to ~2021) to cover COVID recovery and multiple regimes
- **Stack**: Python 3.11+, uv, PostgreSQL — consistent with existing fund infrastructure
- **Immutability**: Historical price data must never be overwritten — append new snapshots only (fund-wide convention)
- **Independence**: Must work as a standalone module — no hard dependency on the AI Washing Detector's internals
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.12 - Backend logic, data ingestion, analysis, and CLI
- SQL - PostgreSQL data definition and queries (via SQLAlchemy ORM)
## Runtime
- Python 3.12 (specified in `.python-version`)
- Minimum: Python 3.11
- Maximum: Python 3.13 (constrained by `requires-python = ">=3.11,<3.14"` in `pyproject.toml`)
- uv (recommended, not currently locked in repo)
- Lock file: `uv.lock` present (276 KB)
## Frameworks
- Typer 0.24.1+ - CLI framework for command-line interface (`src/ai_washer/cli.py`)
- SQLAlchemy 2.0.48+ - ORM and database toolkit
- Alembic 1.18.4+ - Database migrations
- Pydantic 2.12.5+ - Data validation and type-safe settings
- structlog 25.5.0+ - Structured logging with processor pipelines
- pytest 9.0+ - Test framework
- Test configuration: `pyproject.toml` [tool.pytest.ini_options]
- ruff 0.15+ - Fast Python linter and formatter (replaces black, flake8, isort, pyupgrade)
## Key Dependencies
- httpx 0.28.1+ - Async/sync HTTP client for SEC EDGAR, USPTO, GitHub APIs
- tenacity 9.1.4+ - Retry logic with exponential backoff
- edgartools 5.26.1+ - SEC EDGAR filing parsing and XBRL data extraction
- psycopg[binary] 3.2+ - PostgreSQL async/sync driver
- rapidfuzz 3.14.3+ - Fuzzy string matching for entity resolution
- rich 14.0+ - Terminal formatting for pretty tables, progress bars, colored output
- pyyaml 6.0+ - YAML parsing for scoring configuration
## Configuration
- Environment variables with `AI_WASHER_` prefix (loaded from `.env` or environment)
- `.env.example` documents required configuration
- `AI_WASHER_DATABASE_URL` - PostgreSQL connection string
- `AI_WASHER_EDGAR_IDENTITY` - SEC-compliant User-Agent string
- `AI_WASHER_GITHUB_TOKEN` (optional) - GitHub API token for higher rate limits
- `AI_WASHER_LOG_LEVEL` (optional, default: INFO) - Logging level
- Build backend: hatchling
- Build configuration in `pyproject.toml` [build-system]
- Package location: `src/ai_washer` (pip-installable)
- Entry point: `ai-washer = "ai_washer.cli:app"`
- `config/scoring.yaml` - Signal weights and risk thresholds (YAML format)
- `config/scoring.example.yaml` - Example configuration template
- `alembic.ini` - Alembic migration settings
## Platform Requirements
- Python 3.11+ (3.12 recommended)
- PostgreSQL 12+ (tested with binary psycopg driver)
- Virtual environment: `.venv/` directory
- Python 3.12 runtime
- PostgreSQL 16+ (for JSONB and partitioning support)
- Deployment target: Autonomous batch scheduler (daily processing)
- PostgreSQL via testcontainers[postgres] for integration tests
- Python 3.12 with pytest runner
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Lowercase with underscores: `filing_client.py`, `entity_resolver.py`, `config.py`
- Test files: `test_*.py` (e.g., `test_config.py`, `test_normalizer.py`)
- Module files: `__init__.py`, `__main__.py` (executable entry point)
- Avoid module names that shadow stdlib: `test_models.py` not `test_model.py`
- Lowercase with underscores: `normalize_company_name()`, `pad_cik()`, `resolve_entity()`
- Private functions prefixed with single underscore: `_make_filing_data()`, `_is_retryable_error()`
- Factory functions: `load_app_settings()`, `load_scoring_config()`, `create_engine_from_settings()`
- Predicate functions: `_is_retryable_error()` returns bool
- Lowercase with underscores: `company_id`, `filing_date`, `market_cap_cents`
- Constants: `UPPERCASE_WITH_UNDERSCORES` (e.g., `LEGAL_SUFFIXES`, `XBRL_FACTS_URL`, `SEC_RATE_LIMIT_DELAY`)
- Private module constants: `_COLLECTOR_VERSION = "0.3.0"`, `_INTER_COMPANY_DELAY = 1.0`
- Local loop vars: `i`, `cik`, `filing` (same naming convention)
- Classes: `PascalCase` (e.g., `Company`, `FilingCollector`, `UniverseBuilder`, `DualTimestampMixin`)
- Dataclasses: `PascalCase` with `@dataclass(frozen=True)` (e.g., `UniverseBuildResult`, `EFTSHit`)
- Enums/TypeDicts: `PascalCase` (e.g., `ResolutionMethod`)
- Type imports: `from __future__ import annotations` at top, use `str | None` (3.10+ union syntax)
## Code Style
- Tool: `ruff` (line-length=100, target-version=py312)
- Run formatter: `ruff format src/ tests/`
- Run linter: `ruff check src/ tests/ --fix`
- Tool: `ruff` with select rules: `["E", "F", "I", "N", "W", "UP", "B", "SIM"]`
- Line length: 100 characters max
## Import Organization
- None configured in `pyproject.toml` — use full relative paths: `from ai_washer.db.models import ...`
- Test files import from installed package: `from ai_washer.config import ...` not `from ..config import ...`
## Error Handling
- Catch specific exceptions where possible, but broad `except Exception` allowed for external API calls that may raise diverse errors
- Log warning with `exc_info=True` to capture full stack trace in structlog output
- Return sensible defaults (empty list, None, empty dict) on error — don't propagate
- Retry logic via `@retry` decorator from `tenacity` package for SEC/EPA API calls
- Let `ValidationError` propagate from `load_*()` factory functions (caller handles)
- In tests: use `pytest.raises(ValidationError, match="pattern")` to verify validation works
## Logging
- Import at module level: `logger = structlog.get_logger(__name__)`
- Bind contextual keys in instance methods: `self._log = logger.bind(collector="filing_collector")`
- Log events (not messages): `log.info("filing_fetch_complete", fetched=len(results))`
- Keys: `snake_case` (e.g., `accession_no`, `company_id`, `form_type`)
- `log.debug()` — detailed operational info (not used yet in codebase)
- `log.info()` — major milestones (e.g., "filing_fetch_complete", "scan_date")
- `log.warning()` — expected errors that are recovered (e.g., "filing_company_not_found")
- `log.error()` — not used in favor of exceptions (let caller decide logging level)
## Comments
- Explain *why*, not *what* (code shows what, comments explain intent)
- Lock-in decisions: D-03 (partial entity resolution), D-07 (UUID primary keys), D-08 (dual timestamps)
- Tricky algorithmic steps (e.g., longest-suffix-first ordering in `normalize_company_name()`)
- Gotchas: "Guard: if stripping would empty the name, keep original"
- Future risks: "Note: Uses DualTimestampMixin (not AppendOnlyMixin) because the PK structure is custom"
- Triple-quoted docstrings on every public function/class and module
- Format: Google-style with Args, Returns, Raises sections
- Example from `filing_collector.py`:
- Present on every .py file (first thing after `from __future__`), explaining purpose and usage
- Example from `edgar_client.py`:
## Function Design
- Target: <50 lines per function
- Private helper methods may be slightly longer (coordinate complex steps)
- Break into smaller functions rather than nested logic
- Use explicit keyword args, not *args/**kwargs (except in decorators)
- Type hints required on all params and return values
- Use `| None` for optional types (3.10+ syntax via `from __future__ import annotations`)
- Be consistent: don't return None sometimes and empty list other times for same function
- Precedent: API calls return empty list on error (e.g., `FilingClient.get_filings()` → `[]`)
- Factory functions return the object or raise ValidationError (e.g., `load_app_settings()`)
## Module Design
- Define `__all__` when a module has many internals (e.g., test fixture factories)
- Example from tests: functions prefixed with `_` are private, not in `__all__`
- Public classes/functions: no prefix
- `src/ai_washer/db/__init__.py` exports `Base` for import convenience
- `src/ai_washer/ingestion/__init__.py` exists but may stay empty (imports are explicit)
- Keep barrel imports shallow (one or two levels max)
- Use `@dataclass(frozen=True)` for immutable result objects: `UniverseBuildResult`, `EFTSHit`
- Example:
- Use for configuration and validated input/output: `AppSettings`, `SignalWeights`, `FilingData`
- Always validate: add `@model_validator` for cross-field checks
- Example from `config.py`:
- Use `mapped_column()` with type hints (SQLAlchemy 2.0 style)
- No mutation: models are append-only or immutable by design
- Example from `models.py`:
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- CLI-driven command execution (Typer) with no REST API or continuous services
- Three main operational workflows: Universe Scanning, Filing Collection, and (future) Scoring
- Immutable append-only financial data with dual timestamps (business date vs. collection date)
- Pluggable dependency injection for testing (clients injected into orchestrators)
- Typed data contracts (Pydantic models) at every layer boundary
- Structured logging with contextual binding throughout
## Layers
- Purpose: Entry point for manual operations and orchestration. Parses arguments, loads settings, and dispatches to workflow orchestrators.
- Location: `src/ai_washer/cli.py`
- Contains: Typer command groups (universe, collect) and individual commands (scan, list, inspect, collect_company, collect_all)
- Depends on: config, universe.builder, ingestion.filing_collector, db.session, db.models
- Used by: External system calls (human or workflow automation)
- Purpose: Coordinates multi-step workflows by composing lower-level clients and persisting results to the database.
- Location: `src/ai_washer/universe/builder.py`, `src/ai_washer/ingestion/filing_collector.py`
- Contains: `UniverseBuilder` (EFTS search → dedup → market cap filter → entity resolution → persist) and `FilingCollector` (filing retrieval → XBRL extraction → database upsert)
- Depends on: Ingestion clients (EFTSClient, EdgarFactsClient, FilingClient, XBRLExtractor), entity resolution, database session factory
- Used by: CLI layer
- Purpose: Retrieve raw data from external APIs (SEC EDGAR, EFTS, companyfacts) with retry logic and SEC rate-limit compliance.
- Location: `src/ai_washer/ingestion/`
- Contains:
- Depends on: httpx (HTTP client), edgartools (SEC filing parsing), tenacity (retry logic), Pydantic (type validation)
- Used by: Orchestration layer (UniverseBuilder, FilingCollector)
- Purpose: Map company identities across data sources (SEC name ↔ patent assignee ↔ GitHub org ↔ employer) using fuzzy matching.
- Location: `src/ai_washer/entity/`
- Contains:
- Depends on: rapidfuzz (fuzzy string matching)
- Used by: Orchestration layer (UniverseBuilder)
- Purpose: Typed ORM models, database session management, and schema versioning.
- Location: `src/ai_washer/db/`
- Contains:
- Depends on: SQLAlchemy 2.0+ (ORM, type annotations), psycopg (PostgreSQL driver), Alembic (migrations)
- Used by: Orchestration layer, CLI layer (for queries)
- Purpose: Load and validate app settings from environment, YAML, and Pydantic defaults.
- Location: `src/ai_washer/config.py`
- Contains:
- Depends on: pydantic, pydantic-settings (BaseSettings with env file support), pyyaml
- Used by: All layers
- Purpose: Structured JSON logging for production, human-readable for development.
- Location: `src/ai_washer/logging.py`
- Contains: `configure_logging()` function; switches between ConsoleRenderer (DEBUG) and JSONRenderer (INFO+)
- Depends on: structlog
- Used by: All layers (imported as `structlog.get_logger(__name__)`)
## Data Flow
- **Company**: Mutable entity table. Updates on upsert (market_cap_cents, aliases, is_active, deactivation_reason)
- **Append-only tables**: Filing, XBRLFact, SignalDetail, DailyScore. Never update or delete. New observations append as new rows with dual timestamps (as_of_date for business date, observed_date for collection date)
- **Database transactions**: Each orchestrator method runs within a single session context; failures are atomic
- **Rate limiting**: tenacity @retry decorators with exponential backoff; httpx clients with 30s timeout; manual sleep between companies in collect_all (1.0s)
## Key Abstractions
- Purpose: Contract for one full-text search result from EFTS API
- Examples: `src/ai_washer/universe/types.py` line 11
- Pattern: Pydantic BaseModel with accession_no, form_type, entity_name, ciks list
- Purpose: Contract for parsed filing with sections and metadata
- Examples: `src/ai_washer/ingestion/types.py` line 67
- Pattern: Pydantic BaseModel wrapping FilingSections (optional text extracts)
- Purpose: Contract for single extracted financial fact
- Examples: `src/ai_washer/ingestion/types.py` line 84
- Pattern: Pydantic with concept (normalized), tag (actual XBRL tag), value_cents (immutable int)
- Purpose: Contract for resolved company identity across sources
- Examples: `src/ai_washer/entity/types.py` line 52
- Pattern: Pydantic result with AliasesSchema (mapped aliases from all sources + metadata)
- Purpose: Immutable operation results with counts and error lists
- Examples: `src/ai_washer/universe/builder.py` line 36, `src/ai_washer/ingestion/types.py` line 103
- Pattern: Dataclass/Pydantic with frozen=True (or BaseModel) for immutability
- Purpose: Enforce immutability and audit trail on financial data
- Examples: `src/ai_washer/db/base.py`
- Pattern: SQLAlchemy mixin classes auto-generating UUID pk, created_at, as_of_date, observed_date
## Entry Points
- Location: `src/ai_washer/__main__.py`
- Triggers: Loads cli.app from `src/ai_washer/cli.py` and executes it
- Responsibilities: Delegates to Typer CLI router
- Location: Installed via pyproject.toml `[project.scripts]` as `ai-washer = "ai_washer.cli:app"`
- Triggers: Command-line invocation with subcommands
- Responsibilities: Parses arguments, routes to Typer command handlers
- Location: `src/ai_washer/cli.py` lines 39–277
- Triggers: CLI subcommand selection (e.g., `ai-washer universe scan`, `ai-washer collect company AAPL`)
- Responsibilities:
## Error Handling
## Cross-Cutting Concerns
- Mechanism: structlog with `structlog.get_logger(__name__)` in all modules
- Binding: Context added via `.bind(field=value)` in orchestrators (company_id, cik, ticker, signal_type, etc.)
- Output: JSON in production, pretty console in DEBUG mode
- Mechanism: Pydantic BaseModel at contract boundaries (config, types, models)
- Approach: Fail fast on invalid input (raising ValidationError)
- Scope: Config loading, API response parsing, CLI argument coercion
- Mechanism: EDGAR identity (User-Agent string) required in environment; stored in AppSettings
- Scope: All SEC API calls (EFTS, companyfacts, edgartools)
- Implementation: Passed to EFTSClient, EdgarFactsClient, FilingClient at construction time
- Mechanism: tenacity decorators on API client methods; manual sleep in batch loops
- Configuration: 3 attempts max, exponential backoff (1–10s), 0.1s delay after each API call
- Rationale: SEC EDGAR enforces 10 req/sec limit; GitHub enforces 5k req/hr
- Mechanism: Append-only ORM models (AppendOnlyMixin), frozen dataclasses/Pydantic, no in-place mutations
- Scope: Financial time-series data (DailyScore, SignalDetail, Filing, XBRLFact), operation results
- Exception: Company table is mutable for aliases, market_cap_cents, is_active (entity metadata, not signal data)
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
