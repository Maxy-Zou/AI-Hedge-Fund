# Architecture

**Analysis Date:** 2026-03-28

## Pattern Overview

**Overall:** Layered data pipeline with three semi-independent workflows coordinated by CLI entry point.

**Key Characteristics:**
- CLI-driven command execution (Typer) with no REST API or continuous services
- Three main operational workflows: Universe Scanning, Filing Collection, and (future) Scoring
- Immutable append-only financial data with dual timestamps (business date vs. collection date)
- Pluggable dependency injection for testing (clients injected into orchestrators)
- Typed data contracts (Pydantic models) at every layer boundary
- Structured logging with contextual binding throughout

## Layers

**CLI/Command Layer:**
- Purpose: Entry point for manual operations and orchestration. Parses arguments, loads settings, and dispatches to workflow orchestrators.
- Location: `src/ai_washer/cli.py`
- Contains: Typer command groups (universe, collect) and individual commands (scan, list, inspect, collect_company, collect_all)
- Depends on: config, universe.builder, ingestion.filing_collector, db.session, db.models
- Used by: External system calls (human or workflow automation)

**Orchestration Layer:**
- Purpose: Coordinates multi-step workflows by composing lower-level clients and persisting results to the database.
- Location: `src/ai_washer/universe/builder.py`, `src/ai_washer/ingestion/filing_collector.py`
- Contains: `UniverseBuilder` (EFTS search → dedup → market cap filter → entity resolution → persist) and `FilingCollector` (filing retrieval → XBRL extraction → database upsert)
- Depends on: Ingestion clients (EFTSClient, EdgarFactsClient, FilingClient, XBRLExtractor), entity resolution, database session factory
- Used by: CLI layer

**Ingestion/Data Fetcher Layer:**
- Purpose: Retrieve raw data from external APIs (SEC EDGAR, EFTS, companyfacts) with retry logic and SEC rate-limit compliance.
- Location: `src/ai_washer/ingestion/`
- Contains:
  - `EFTSClient` - Paginated full-text search of SEC filings for AI keywords
  - `EdgarFactsClient` - Company facts API for EntityPublicFloat and CIK-ticker mapping
  - `FilingClient` - Wrapper around edgartools for retrieving and section-extracting 10-K/10-Q/8-K filings
  - `XBRLExtractor` - Extracts financial facts (R&D, CapEx, Revenue) from XBRL data
- Depends on: httpx (HTTP client), edgartools (SEC filing parsing), tenacity (retry logic), Pydantic (type validation)
- Used by: Orchestration layer (UniverseBuilder, FilingCollector)

**Entity Resolution Layer:**
- Purpose: Map company identities across data sources (SEC name ↔ patent assignee ↔ GitHub org ↔ employer) using fuzzy matching.
- Location: `src/ai_washer/entity/`
- Contains:
  - `EntityResolver` - Fuzzy matching engine (rapidfuzz) with configurable thresholds
  - `normalizer.py` - Company name normalization (strip legal suffixes, case/whitespace collapse)
  - `types.py` - Pydantic contracts for AliasesSchema (Company.aliases JSONB structure)
- Depends on: rapidfuzz (fuzzy string matching)
- Used by: Orchestration layer (UniverseBuilder)

**Data Layer:**
- Purpose: Typed ORM models, database session management, and schema versioning.
- Location: `src/ai_washer/db/`
- Contains:
  - `base.py` - DeclarativeBase, AppendOnlyMixin (UUID PK + created_at + dual timestamps), DualTimestampMixin
  - `models.py` - Six ORM models: Company (mutable entity), DailyScore (append-only, partitioned), SignalDetail (append-only), PipelineRun, Filing (append-only), XBRLFact (append-only)
  - `session.py` - Engine factory, session factory with pool pre-ping
- Depends on: SQLAlchemy 2.0+ (ORM, type annotations), psycopg (PostgreSQL driver), Alembic (migrations)
- Used by: Orchestration layer, CLI layer (for queries)

**Configuration Layer:**
- Purpose: Load and validate app settings from environment, YAML, and Pydantic defaults.
- Location: `src/ai_washer/config.py`
- Contains:
  - `AppSettings` - Database URL, EDGAR identity, log level (env vars with AI_WASHER_ prefix)
  - `UniverseSettings` - Market cap thresholds, AI keywords, fuzzy match threshold, refresh cadence
  - `FilingCollectionSettings` - Form types to collect, section limits, max filings per type
  - `ScoringConfig` - Signal weights (from YAML), risk thresholds
- Depends on: pydantic, pydantic-settings (BaseSettings with env file support), pyyaml
- Used by: All layers

**Logging Layer:**
- Purpose: Structured JSON logging for production, human-readable for development.
- Location: `src/ai_washer/logging.py`
- Contains: `configure_logging()` function; switches between ConsoleRenderer (DEBUG) and JSONRenderer (INFO+)
- Depends on: structlog
- Used by: All layers (imported as `structlog.get_logger(__name__)`)

## Data Flow

**Universe Scanning Pipeline (cli.py scan → UniverseBuilder.build):**

1. CLI loads UniverseSettings + AppSettings
2. UniverseBuilder.__init__ creates injected clients (EFTSClient, EdgarFactsClient, EntityResolver)
3. UniverseBuilder.scan() performs keyword searches:
   - For each AI keyword in settings (e.g., "artificial intelligence", "machine learning")
   - EFTSClient paginates through efts.sec.gov results (max 10K per keyword)
   - Collects EFTSHit objects (accession, entity_name, ciks, filing date)
4. deduplicate_by_cik() removes duplicate companies, sorts by CIK for determinism
5. filter_by_market_cap() calls EdgarFactsClient.get_entity_public_float() for each CIK, filters by settings.market_cap_min/max
6. EntityResolver.resolve_entity() creates alias records (CIK + entity name only at this stage)
7. Upsert to Company table (INSERT … ON CONFLICT UPDATE) with is_active=true
8. Soft-deactivate stale companies: mark is_active=false + deactivation_reason for companies no longer in scan results
9. Return UniverseBuildResult with counts

**Filing Collection Pipeline (cli.py collect_company/all → FilingCollector.collect_for_company/all):**

1. CLI resolves company by ticker/CIK, captures Company.id, Company.cik, Company.ticker before session closes
2. FilingCollector.__init__ creates FilingClient + XBRLExtractor
3. For each form type in FilingCollectionSettings (10-K, 10-Q, 8-K):
   - FilingClient.get_latest_filings(form_type, cik, count) retrieves via edgartools
   - edgartools automatically extracts sections (Business, Risk Factors, MD&A)
   - Validate section length ≥ 500 chars (Pitfall 1 mitigation)
   - Compute content_hash (SHA256) for dedup
4. Upsert Filing records to sec_filings table with (company_id, form_type, accession_no) unique constraint
5. For each collected filing, XBRLExtractor.extract_company_xbrl(cik) fetches companyfacts API:
   - Query data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
   - For each concept in XBRL_TAG_GROUPS (rd_expense, capex, revenue)
   - Try fallback tags in order until one has data
   - deduplicate_by_period() keeps latest-filed for each (end_date, fiscal_period)
   - Convert dollars → cents (multiply by 100, round to int)
6. Upsert XBRLFact records with (company_id, concept, end_date, fiscal_period) unique constraint
7. Return CollectionResult with filing_count, xbrl_fact_count, skipped_count, errors

**State Management:**

- **Company**: Mutable entity table. Updates on upsert (market_cap_cents, aliases, is_active, deactivation_reason)
- **Append-only tables**: Filing, XBRLFact, SignalDetail, DailyScore. Never update or delete. New observations append as new rows with dual timestamps (as_of_date for business date, observed_date for collection date)
- **Database transactions**: Each orchestrator method runs within a single session context; failures are atomic
- **Rate limiting**: tenacity @retry decorators with exponential backoff; httpx clients with 30s timeout; manual sleep between companies in collect_all (1.0s)

## Key Abstractions

**EFTSHit:**
- Purpose: Contract for one full-text search result from EFTS API
- Examples: `src/ai_washer/universe/types.py` line 11
- Pattern: Pydantic BaseModel with accession_no, form_type, entity_name, ciks list

**FilingData:**
- Purpose: Contract for parsed filing with sections and metadata
- Examples: `src/ai_washer/ingestion/types.py` line 67
- Pattern: Pydantic BaseModel wrapping FilingSections (optional text extracts)

**XBRLFactRecord:**
- Purpose: Contract for single extracted financial fact
- Examples: `src/ai_washer/ingestion/types.py` line 84
- Pattern: Pydantic with concept (normalized), tag (actual XBRL tag), value_cents (immutable int)

**EntityResolutionResult:**
- Purpose: Contract for resolved company identity across sources
- Examples: `src/ai_washer/entity/types.py` line 52
- Pattern: Pydantic result with AliasesSchema (mapped aliases from all sources + metadata)

**UniverseBuildResult / CollectionResult:**
- Purpose: Immutable operation results with counts and error lists
- Examples: `src/ai_washer/universe/builder.py` line 36, `src/ai_washer/ingestion/types.py` line 103
- Pattern: Dataclass/Pydantic with frozen=True (or BaseModel) for immutability

**AppendOnlyMixin / DualTimestampMixin:**
- Purpose: Enforce immutability and audit trail on financial data
- Examples: `src/ai_washer/db/base.py`
- Pattern: SQLAlchemy mixin classes auto-generating UUID pk, created_at, as_of_date, observed_date

## Entry Points

**Module Entry (python -m ai_washer):**
- Location: `src/ai_washer/__main__.py`
- Triggers: Loads cli.app from `src/ai_washer/cli.py` and executes it
- Responsibilities: Delegates to Typer CLI router

**Script Entry (ai-washer CLI command):**
- Location: Installed via pyproject.toml `[project.scripts]` as `ai-washer = "ai_washer.cli:app"`
- Triggers: Command-line invocation with subcommands
- Responsibilities: Parses arguments, routes to Typer command handlers

**Command Handlers (universe scan, collect company, etc.):**
- Location: `src/ai_washer/cli.py` lines 39–277
- Triggers: CLI subcommand selection (e.g., `ai-washer universe scan`, `ai-washer collect company AAPL`)
- Responsibilities:
  - Load settings (AppSettings, UniverseSettings, FilingCollectionSettings)
  - Create orchestrators (UniverseBuilder, FilingCollector) with injected dependencies
  - Capture mutable state before session closes (for company lookups)
  - Call orchestrator methods
  - Format and echo results to stdout

## Error Handling

**Strategy:** Fail fast with detailed contextual logging; let tenacity retries handle transient API errors; collect errors into result objects for batch operations.

**Patterns:**

1. **API-level retries:**
   - `EFTSClient`, `EdgarFactsClient`, `FilingClient`, `XBRLExtractor` all use `@tenacity.retry` decorators
   - Configuration: `stop_after_attempt(3)`, `wait_exponential(multiplier=1, min=1, max=10)`
   - Predicate: `_is_retryable_error()` allows 429 (rate limit) and 5xx errors
   - Logging: `before_sleep_log()` logs retry attempts at WARN level

2. **Validation errors:**
   - Pydantic validates all contract types at ingestion boundaries (EFTSHit, FilingData, XBRLFactRecord)
   - Invalid shapes raise `ValidationError` which propagates to CLI as exit code 1
   - Example: `src/ai_washer/config.py` line 37 validates signal weights sum to 1.0

3. **Batch operation resilience:**
   - FilingCollector.collect_all() accumulates errors in CollectionResult.errors list
   - Does not stop on first failure; continues through all companies
   - CLI echoes final error count and individual error messages

4. **User-facing errors:**
   - CLI catches company not found and shows friendly message with err=True flag
   - Example: `src/ai_washer/cli.py` line 139

5. **Database integrity:**
   - Unique constraints on (company_id, form_type, accession_no) and (company_id, concept, end_date, fiscal_period) ensure idempotent re-collection
   - Upsert logic in orchestrators handles duplicate collection gracefully

## Cross-Cutting Concerns

**Logging:**
- Mechanism: structlog with `structlog.get_logger(__name__)` in all modules
- Binding: Context added via `.bind(field=value)` in orchestrators (company_id, cik, ticker, signal_type, etc.)
- Output: JSON in production, pretty console in DEBUG mode

**Validation:**
- Mechanism: Pydantic BaseModel at contract boundaries (config, types, models)
- Approach: Fail fast on invalid input (raising ValidationError)
- Scope: Config loading, API response parsing, CLI argument coercion

**Authentication/Authorization:**
- Mechanism: EDGAR identity (User-Agent string) required in environment; stored in AppSettings
- Scope: All SEC API calls (EFTS, companyfacts, edgartools)
- Implementation: Passed to EFTSClient, EdgarFactsClient, FilingClient at construction time

**Retry & Rate Limiting:**
- Mechanism: tenacity decorators on API client methods; manual sleep in batch loops
- Configuration: 3 attempts max, exponential backoff (1–10s), 0.1s delay after each API call
- Rationale: SEC EDGAR enforces 10 req/sec limit; GitHub enforces 5k req/hr

**Immutability:**
- Mechanism: Append-only ORM models (AppendOnlyMixin), frozen dataclasses/Pydantic, no in-place mutations
- Scope: Financial time-series data (DailyScore, SignalDetail, Filing, XBRLFact), operation results
- Exception: Company table is mutable for aliases, market_cap_cents, is_active (entity metadata, not signal data)
