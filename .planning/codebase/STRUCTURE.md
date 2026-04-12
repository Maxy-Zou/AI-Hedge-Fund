# Codebase Structure

**Analysis Date:** 2026-03-28

## Directory Layout

```
AI Hedgefund/
└── Al Washing Detector/                  # Single strategy module
    ├── CLAUDE.md                         # Strategy-specific context
    ├── ai_washing_detector_research.md   # Research notes
    ├── pyproject.toml                    # Project metadata, dependencies, build config
    ├── alembic.ini                       # Alembic migration runner config
    ├── uv.lock                           # Lockfile (uv package manager)
    │
    ├── config/                           # YAML configuration files
    │   ├── scoring.example.yaml          # Template for signal weights and thresholds
    │   └── scoring.yaml                  # Active scoring config (env-var loadable)
    │
    ├── docs/                             # Project documentation
    │   └── PROGRESS.md                   # Ongoing progress log
    │
    ├── src/ai_washer/                    # Main package (pip-installable)
    │   ├── __init__.py                   # Package version (__version__ = "0.1.0")
    │   ├── __main__.py                   # Entry point for `python -m ai_washer`
    │   ├── cli.py                        # Typer CLI commands (universe, collect subcommands)
    │   ├── config.py                     # Pydantic settings (AppSettings, UniverseSettings, etc.)
    │   ├── logging.py                    # structlog configuration
    │   │
    │   ├── db/                           # Database layer (ORM, migrations, session)
    │   │   ├── __init__.py               # db module exports
    │   │   ├── base.py                   # DeclarativeBase, AppendOnlyMixin, DualTimestampMixin
    │   │   ├── models.py                 # ORM models (Company, DailyScore, SignalDetail, PipelineRun, Filing, XBRLFact)
    │   │   ├── session.py                # Engine/session factory functions
    │   │   └── migrations/               # Alembic migration scripts
    │   │       ├── env.py                # Migration environment config
    │   │       └── versions/             # Migration version files
    │   │           ├── 001_initial_schema.py
    │   │           ├── 002_add_company_active_fields.py
    │   │           ├── 003_add_filing_tables.py
    │   │           └── __init__.py
    │   │
    │   ├── ingestion/                    # Data fetchers (SEC APIs, parsing)
    │   │   ├── __init__.py               # ingestion module exports
    │   │   ├── types.py                  # Pydantic contracts (FilingData, XBRLFactRecord, CollectionResult)
    │   │   ├── edgar_client.py           # EdgarFactsClient (companyfacts API, market cap lookup)
    │   │   ├── efts_client.py            # EFTSClient (SEC full-text search with pagination)
    │   │   ├── filing_client.py          # FilingClient (wrapper around edgartools for section extraction)
    │   │   ├── filing_collector.py       # FilingCollector orchestrator (filing retrieval + XBRL extraction + persist)
    │   │   └── xbrl_extractor.py         # XBRLExtractor (financial fact extraction from companyfacts API)
    │   │
    │   ├── entity/                       # Entity resolution (cross-source company matching)
    │   │   ├── __init__.py               # entity module exports
    │   │   ├── types.py                  # Pydantic contracts (AliasesSchema, EntityResolutionResult)
    │   │   ├── normalizer.py             # Company name normalization (suffix stripping, case collapse)
    │   │   └── resolver.py               # EntityResolver (fuzzy matching with rapidfuzz)
    │   │
    │   └── universe/                     # Universe building (company scanning, filtering)
    │       ├── __init__.py               # universe module exports
    │       ├── types.py                  # Pydantic contracts (EFTSHit, EFTSResponse, MarketCapRange)
    │       ├── filters.py                # filter_by_market_cap(), deduplicate_by_cik()
    │       └── builder.py                # UniverseBuilder orchestrator (scan → dedup → filter → resolve → persist)
    │
    ├── tests/                            # Test suite (unit + integration)
    │   ├── __init__.py
    │   ├── conftest.py                   # Shared fixtures (_set_test_env, scoring_yaml)
    │   │
    │   ├── unit/                         # Unit tests (no database)
    │   │   ├── __init__.py
    │   │   ├── test_config.py            # Config loading, validation
    │   │   ├── test_models.py            # ORM model behavior
    │   │   ├── test_entity_normalizer.py # Name normalization
    │   │   ├── test_entity_resolver.py   # Fuzzy matching
    │   │   ├── test_entity_types.py      # Alias schema validation
    │   │   ├── test_universe_types.py    # EFTS hit parsing
    │   │   ├── test_universe_filters.py  # Market cap filtering, dedup
    │   │   ├── test_universe_builder.py  # UniverseBuilder workflow (mocked clients)
    │   │   ├── test_efts_client.py       # EFTSClient pagination, retry logic (mocked HTTP)
    │   │   ├── test_edgar_client.py      # EdgarFactsClient API calls (mocked HTTP)
    │   │   ├── test_filing_types.py      # Filing section validation
    │   │   ├── test_filing_client.py     # FilingClient section extraction (mocked edgartools)
    │   │   ├── test_filing_collector.py  # FilingCollector workflow (mocked clients)
    │   │   ├── test_xbrl_extractor.py    # XBRL fact extraction, dedup (mocked HTTP)
    │   │   ├── test_cli_universe.py      # CLI universe commands (mocked builders)
    │   │   ├── test_cli_filings.py       # CLI collect commands (mocked collectors)
    │   │   └── test_package.py           # Import checks, version
    │   │
    │   └── integration/                  # Integration tests (real PostgreSQL via testcontainers)
    │       ├── __init__.py
    │       ├── conftest.py               # Database fixtures (postgres_container, session_factory)
    │       ├── test_schema.py            # ORM models, migration application
    │       ├── test_migrations.py        # Alembic migration forward/backward
    │       ├── test_company_lifecycle.py # Company CRUD, aliases, deactivation
    │       └── test_universe_builder.py  # UniverseBuilder end-to-end (real DB, mocked APIs)
    │
    └── .venv/                            # Virtual environment (excluded from version control)
```

## Directory Purposes

**`src/ai_washer/`:**
- Purpose: Main package root; installable via `pip install -e .` or `uv pip install -e .`
- Contains: All source code organized by layer (db, ingestion, entity, universe)
- Key files: `__init__.py` (version), `__main__.py` (module entry), `cli.py` (command entry)

**`src/ai_washer/db/`:**
- Purpose: Data persistence layer; ORM models and database connection management
- Contains: SQLAlchemy models, session/engine factories, Alembic migrations
- Key files: `models.py` (6 ORM tables), `base.py` (mixins), `session.py` (factories)

**`src/ai_washer/ingestion/`:**
- Purpose: External data fetching from SEC APIs, edgartools integration
- Contains: HTTP clients with retry logic, Pydantic contracts for API responses, section extraction, XBRL parsing
- Key files: `filing_collector.py` (orchestrator), `types.py` (contracts), `*_client.py` (API wrappers)

**`src/ai_washer/entity/`:**
- Purpose: Cross-source identity resolution (SEC name ↔ patent assignee ↔ GitHub org)
- Contains: Fuzzy matching engine, name normalization, alias schema
- Key files: `resolver.py` (EntityResolver), `normalizer.py` (name cleaning), `types.py` (AliasesSchema)

**`src/ai_washer/universe/`:**
- Purpose: Company universe scanning and filtering
- Contains: EFTS search client integration, market cap filtering, deduplication
- Key files: `builder.py` (UniverseBuilder orchestrator), `filters.py` (utilities), `types.py` (contracts)

**`config/`:**
- Purpose: Runtime configuration files (not code)
- Contains: YAML templates and active scoring config
- Key files: `scoring.yaml` (signal weights, risk thresholds)

**`tests/unit/`:**
- Purpose: Fast, isolated unit tests (no database)
- Contains: Tests for individual components with mocked dependencies
- Key files: Named `test_<module>.py` matching source structure
- Pattern: Uses `pytest-httpx` for mocking HTTP, `factory-boy` for test data

**`tests/integration/`:**
- Purpose: End-to-end tests requiring real database
- Contains: Database fixtures, migration tests, workflow integration tests
- Key files: `conftest.py` (testcontainers PostgreSQL setup), `test_<workflow>.py` files
- Pattern: Uses `testcontainers[postgres]` for ephemeral database

**`docs/`:**
- Purpose: Project documentation and progress tracking
- Contains: PROGRESS.md (running log of changes)

## Key File Locations

**Entry Points:**
- `src/ai_washer/__main__.py`: Executes when running `python -m ai_washer`
- `src/ai_washer/cli.py`: Typer app definition and all commands (scan, list, inspect, collect, etc.)
- Script entry via pyproject.toml: `ai-washer = "ai_washer.cli:app"`

**Configuration:**
- `src/ai_washer/config.py`: AppSettings (env vars), UniverseSettings, FilingCollectionSettings, ScoringConfig
- `config/scoring.yaml`: YAML-backed signal weights and risk thresholds

**Core Logic:**
- `src/ai_washer/universe/builder.py`: UniverseBuilder orchestrator (main scanning pipeline)
- `src/ai_washer/ingestion/filing_collector.py`: FilingCollector orchestrator (main collection pipeline)
- `src/ai_washer/entity/resolver.py`: EntityResolver (fuzzy matching engine)

**Database:**
- `src/ai_washer/db/models.py`: ORM model definitions (Company, DailyScore, Filing, XBRLFact, etc.)
- `src/ai_washer/db/base.py`: Mixins (AppendOnlyMixin, DualTimestampMixin) for model consistency
- `src/ai_washer/db/migrations/versions/`: Alembic migration scripts (001, 002, 003)

**Testing:**
- `tests/conftest.py`: Shared fixtures (env vars, temp files)
- `tests/integration/conftest.py`: Database fixtures (testcontainers PostgreSQL)

## Naming Conventions

**Files:**
- Source modules: `snake_case.py` (e.g., `entity_resolver.py`, `filing_collector.py`)
- Test files: `test_<module>.py` (e.g., `test_entity_resolver.py`, `test_filing_collector.py`)
- ORM migrations: Numbered `NNN_description.py` (e.g., `001_initial_schema.py`, `003_add_filing_tables.py`)

**Directories:**
- Packages: `snake_case` (e.g., `ai_washer`, `ingestion`, `entity`)
- Functional domains: Plural or descriptive (e.g., `universe`, `db`, `tests`)

**Classes:**
- PascalCase for all classes (e.g., `UniverseBuilder`, `FilingClient`, `EntityResolver`, `Company`)
- ORM models: PascalCase (e.g., `Company`, `Filing`, `XBRLFact`)
- Mixins: PascalCase ending with "Mixin" (e.g., `AppendOnlyMixin`)
- Exceptions: Inherit from Exception, PascalCase (none currently used)

**Functions:**
- Module-level: `snake_case` (e.g., `normalize_company_name()`, `filter_by_market_cap()`, `deduplicate_by_cik()`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `EFTS_BASE_URL`, `MIN_SECTION_CHARS`, `XBRL_TAG_GROUPS`)

**Variables:**
- Local: `snake_case` (e.g., `company_id`, `filing_count`, `matched_score`)
- Private/protected: `_leading_underscore` (e.g., `_session_factory`, `_edgar_client`)

## Where to Add New Code

**New Feature (e.g., scoring module, GitHub activity signal):**
- Primary code: Create new `src/ai_washer/<domain>/` module (e.g., `src/ai_washer/scoring/` with `engine.py`, `types.py`)
- Client integration: Add client in appropriate module (e.g., `src/ai_washer/ingestion/github_client.py` for GitHub signal)
- CLI commands: Add subcommands to existing app in `src/ai_washer/cli.py` (e.g., `@score_app.command()`)
- Tests: Create `tests/unit/test_<module>.py` and `tests/integration/test_<module>.py` files

**New Component/Module (e.g., new API client):**
- Implementation: Add to appropriate layer directory
  - Data fetcher: `src/ai_washer/ingestion/<source>_client.py`
  - Entity resolution: `src/ai_washer/entity/<resolver_type>.py`
  - Analysis/scoring: `src/ai_washer/analysis/<signal_name>.py` (future)
- Exports: Update `src/ai_washer/<module>/__init__.py` to export public classes
- Tests: Create `tests/unit/test_<source>_client.py` with mocked HTTP via `pytest-httpx`

**Utilities/Shared Helpers:**
- Location: Add to existing module that "owns" the concern (e.g., name normalization → `src/ai_washer/entity/normalizer.py`)
- No separate utilities module; keep coupling low by organizing around domains
- Tests: Add cases to existing `tests/unit/test_<module>.py` file

**Database Changes (schema additions, new tables):**
- ORM model: Add class to `src/ai_washer/db/models.py` (inherit from Base, use mapped_column + type annotations)
- Mixins: Use AppendOnlyMixin for financial data (append-only), plain Base for operational data
- Migration: Create new file in `src/ai_washer/db/migrations/versions/` with `alembic revision --autogenerate -m "description"`
- Update docs: Note any changes to data layer design decisions in `docs/PROGRESS.md`

## Special Directories

**`src/ai_washer/db/migrations/versions/`:**
- Purpose: Alembic migration scripts for schema versioning
- Generated: Partially (run `alembic revision --autogenerate` to scaffold)
- Committed: Yes — these are schema history
- Editing: Never edit manually; create new revisions instead

**`config/`:**
- Purpose: Runtime YAML configuration (not code)
- Generated: No
- Committed: `scoring.example.yaml` yes; `scoring.yaml` depends on deploy environment
- Editing: Direct YAML edits; can be updated by deployment automation

**`.venv/`:**
- Purpose: Virtual environment directory
- Generated: Yes (created by `uv venv`)
- Committed: No (in .gitignore)
- Editing: Never manually; regenerate if needed

**`tests/unit/` vs `tests/integration/`:**
- Unit: Single component in isolation (mocked dependencies). Fast, run on every commit.
- Integration: Multiple components + real PostgreSQL database. Slower, run before merge.
- Execution: `pytest -m "not integration"` for unit only; `pytest` for all; `pytest -m integration` for integration only

## Import Patterns

**Standard imports (src code):**
```python
from ai_washer.config import AppSettings, load_app_settings
from ai_washer.db.models import Company, Filing
from ai_washer.db.session import create_engine_from_settings, get_session_factory
from ai_washer.universe.builder import UniverseBuilder
from ai_washer.ingestion.filing_collector import FilingCollector
```

**Test imports:**
```python
import pytest
from sqlalchemy import select
from unittest.mock import patch, MagicMock
import factory
from ai_washer.config import load_app_settings
from ai_washer.db.models import Company
```

**External library conventions:**
- SQLAlchemy: `from sqlalchemy import ...` for functions/types; `import sqlalchemy as sa` for schema defs
- Pydantic: `from pydantic import BaseModel, Field, model_validator`
- Structlog: `logger = structlog.get_logger(__name__)` at module top
- Typer: `app = typer.Typer()` at module top; `@app.command()` for handlers
