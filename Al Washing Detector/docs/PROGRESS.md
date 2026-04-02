# Progress

## Project Setup — 2026-03-27
- Initialized git repository
- Created CLAUDE.md with project architecture and development rules
- Created .gitignore for Python/financial data project
- Set up Claude Code permissions for Python development workflow
- Created docs/PROGRESS.md for progress tracking

## GSD Project Initialization — 2026-03-27
- Initialized GSD workflow with `/gsd:new-project`
- Created .planning/PROJECT.md, config.json, REQUIREMENTS.md, ROADMAP.md, STATE.md
- Ran 4 parallel domain researchers (stack, features, architecture, pitfalls)
- Key findings: PatentsView API migrated to data.uspto.gov, FinBERT measures sentiment not vagueness
- 10 phases, 45 requirements mapped across all 6 signals + foundation + scoring + ops + integration

## Phase 1: Planning — 2026-03-27
- Ran /gsd:discuss-phase 1 — captured 12 implementation decisions (package name, DB design, config)
- Ran /gsd:plan-phase 1 — spawned researcher, planner, and plan checker
- 3 plans created in 3 waves, all 5 requirements covered (FNDN-01, FNDN-04, FNDN-05, FNDN-06, INT-01)
- Plan checker found 4 blockers (monthly partitions, verify commands, VALIDATION.md mapping, CLAUDE.md)
- All blockers fixed in revision, verification passed on iteration 2
- Files: .planning/phases/01-project-skeleton-and-database/01-{01,02,03}-PLAN.md

## Phase 1, Plan 01: Package Scaffold -- 2026-03-27
- Scaffolded ai_washer Python package with src layout, Typer CLI, Pydantic config, structlog logging
- Created test infrastructure (conftest.py, test_package.py, test_config.py) -- TDD red/green cycle
- AppSettings loads from env with AI_WASHER_ prefix, ScoringConfig from config/scoring.yaml
- SignalWeights validates sum to 1.0, ScoringConfig validates threshold ranges 0-100
- Updated CLAUDE.md Architecture section to reflect actual src/ai_washer/ layout
- All 10 unit tests passing
- Files created: pyproject.toml, src/ai_washer/{__init__,__main__,cli,config,logging}.py, config/scoring.yaml, tests/{conftest,unit/test_package,unit/test_config}.py
- Test count: 10 unit tests

## Phase 1, Plan 02: SQLAlchemy ORM Models -- 2026-03-27
- Created database base classes: DeclarativeBase, DualTimestampMixin, AppendOnlyMixin
- Four ORM models: Company, DailyScore, SignalDetail, PipelineRun
- DailyScore: composite PK (id, scored_at), RANGE partition by scored_at (D-06)
- UUID PKs on all tables (D-07), dual timestamps on financial tables (D-08)
- BIGINT for market_cap_cents (D-09), JSONB for flexible content (D-05)
- Session factory wired to AppSettings database_url
- No update/delete methods on append-only models (DailyScore, SignalDetail)
- Full TDD red/green cycle for all models
- Files created: src/ai_washer/db/{base,models,session,__init__}.py, tests/unit/test_models.py
- Test count: 68 total (10 pre-existing + 58 new model tests)

## Phase 1, Plan 03: Alembic Migrations -- 2026-03-27
- Set up Alembic migrations framework with env.py reading DATABASE_URL from AI_WASHER_DATABASE_URL
- Initial migration creates all four tables with correct types and constraints
- daily_scores table uses RANGE partitioning on scored_at with 18 monthly partitions (D-06)
- 12 partitions for 2026 + 6 buffer partitions for 2027
- Migration is fully reversible and idempotent
- Integration tests use testcontainers PostgreSQL (real database, not mocks)
- Docker Desktop auto-detection for macOS in conftest.py
- Added pytest-timeout and integration marker to pyproject.toml
- Files created: alembic.ini, src/ai_washer/db/migrations/{__init__,env,script.py.mako}.py, src/ai_washer/db/migrations/versions/{__init__,001_initial_schema}.py, tests/integration/{conftest,test_migrations,test_schema}.py
- Test count: 79 total (68 pre-existing + 11 new integration tests)

## Phase 2, Plan 01: Dependencies, Schema, and Type Contracts -- 2026-03-27
- Installed Phase 2 deps: edgartools, httpx, rapidfuzz, tenacity (runtime) + freezegun, pytest-httpx (dev)
- Extended Company model with is_active (Boolean, default True) and deactivation_reason (String, nullable) for soft-delete per D-10
- Created Alembic migration 002_add_active (add_column for both new fields, reversible)
- Defined Pydantic type contracts: AliasesSchema (D-02 JSONB structure), ResolutionMetadata, EntityResolutionResult
- Defined EFTS types: EFTSHit, EFTSResponse (with is_truncated property), MarketCapRange (min < max validation)
- Added UniverseSettings to config.py with widened $1.5B-$9B market cap thresholds per Pitfall 2
- Created entity/, ingestion/, universe/ subpackage directories
- Full TDD red/green cycle for all types and model changes
- Files created: src/ai_washer/{entity,ingestion,universe}/{__init__,types}.py, migrations/versions/002_add_company_active_fields.py, tests/unit/{test_entity_types,test_universe_types}.py
- Files modified: pyproject.toml, uv.lock, src/ai_washer/db/models.py, src/ai_washer/config.py, tests/unit/test_models.py
- Test count: 112 total (68 pre-existing + 5 new model tests + 39 new type tests)

## Phase 2, Plan 03: Entity Resolution Engine -- 2026-03-27
- Built company name normalizer: strips legal suffixes (Inc, Corp, LLC, Ltd, etc.), normalizes case/whitespace/punctuation
- LEGAL_SUFFIXES ordered longest-first for correct matching (INCORPORATED before INC)
- Built EntityResolver class with configurable fuzzy match threshold using rapidfuzz token_sort_ratio
- Fuzzy matching for patent_assignee and employer_names; exact matching for github_org slugs
- Partial resolution accepted: null fields for missing data sources per D-03
- Resolution metadata records method (automated_fuzzy), confidence score, needs_review flag
- resolve_batch for processing multiple entities with structlog progress logging
- Module-level resolve_entity convenience function
- Updated entity/__init__.py to export full public API
- Full TDD red/green cycle for both normalizer and resolver
- Files created: src/ai_washer/entity/{normalizer,resolver}.py, tests/unit/{test_normalizer,test_entity_resolver}.py
- Files modified: src/ai_washer/entity/__init__.py
- Test count: 173 total (112 pre-existing + 37 normalizer tests + 24 resolver tests)

## Phase 2, Plan 02: EFTS and EDGAR HTTP Clients -- 2026-03-27
- Built EFTSClient: paginated full-text search of SEC EFTS API (efts.sec.gov/LATEST/search-index)
- Automatic offset-based pagination up to 10K cap, truncation detection via total_relation='gte'
- Built EdgarFactsClient: XBRL company facts API for EntityPublicFloat (market cap proxy)
- Dollar-to-cents conversion, most-recent-entry selection by end date, 404 graceful handling
- CIK normalization utilities: pad_cik (10-digit zero-padded) and strip_cik (leading zeros removed)
- get_cik_ticker_mapping from SEC company_tickers.json for CIK-to-ticker resolution
- Batch EntityPublicFloat fetching with SEC rate limit compliance (10 req/sec)
- Both clients: SEC-compliant User-Agent, tenacity retry (exponential backoff), structlog logging
- Both clients: context manager support for httpx.Client lifecycle
- Full TDD red/green cycle for both clients (pytest-httpx mocked HTTP)
- Files created: src/ai_washer/ingestion/{efts_client,edgar_client}.py, tests/unit/{test_efts_client,test_edgar_client}.py
- Files modified: src/ai_washer/ingestion/__init__.py
- Test count: 206 total (173 pre-existing + 13 EFTS tests + 20 EDGAR tests)

## Phase 2, Plan 04: Universe Builder Orchestrator -- 2026-03-27
- Built market cap filter: filter_by_market_cap with inclusive boundary check and None handling
- Built CIK deduplication: deduplicate_by_cik normalizes format and sorts ascending for determinism (D-06)
- Built UniverseBuilder orchestrator: full pipeline scan -> dedup -> market cap filter -> entity resolution -> persist
- Dependency injection for all clients (EFTSClient, EdgarFactsClient, EntityResolver) enabling isolated unit tests
- scan() searches each keyword separately with quoted phrases and 12-month lookback window per D-05
- filter_market_cap() batch-fetches EntityPublicFloat and filters by widened $1.5B-$9B range per Pitfall 2
- resolve_entities() maps each company through EntityResolver for cross-source alias population (D-02)
- persist() upserts by CIK and soft-removes missing companies (is_active=False) per D-10
- build() orchestrates full deterministic pipeline per D-06 (sorted by CIK, date-pinned queries)
- build_universe() convenience function for simple invocation
- Updated universe/__init__.py with UniverseBuildResult export
- SQLite JSONB compatibility in tests via type adapter
- Full TDD red/green cycle for both filter and builder modules
- Files created: src/ai_washer/universe/{filters,builder}.py, tests/unit/{test_universe_filters,test_universe_builder}.py
- Files modified: src/ai_washer/universe/__init__.py, docs/PROGRESS.md
- Test count: 233 total (206 pre-existing + 13 filter tests + 14 builder tests)

## Phase 2, Plan 05: CLI Universe Commands and Integration Tests -- 2026-03-28
- Added CLI universe subcommand group: scan (--dry-run), list (--active/--all, --limit), inspect (ticker/CIK)
- scan: triggers full universe build or dry-run (EFTS search + market cap filter only)
- list: queries Company table with optional active-only filter and pagination
- inspect: shows detailed company info including JSONB aliases and deactivation status
- 9 unit tests for CLI commands with CliRunner and monkeypatch mocks
- Integration tests: Company JSONB aliases round-trip via AliasesSchema, batch persistence
- Integration tests: soft-remove lifecycle (deactivate, reactivate, active-only query, soft-delete preservation per D-10)
- Checkpoint: verified 260 tests passing, all Phase 2 modules importable
- Files created: tests/unit/test_cli_universe.py, tests/integration/test_universe_builder.py, tests/integration/test_company_lifecycle.py
- Files modified: src/ai_washer/cli.py
- Test count: 260 total (233 pre-existing + 9 CLI unit tests + 7 integration tests + 11 others)

## Phase 3, Plan 01: SEC Filing Data Contracts and Storage Layer -- 2026-03-28
- Defined Pydantic type contracts: FilingData, FilingSections, XBRLFactRecord, XBRLTagGroup, CollectionResult
- Created XBRL_TAG_GROUPS constant mapping 3 financial concepts to ordered XBRL tag fallback lists
- Added Filing ORM model (sec_filings) with AppendOnlyMixin, unique constraint on (company_id, form_type, accession_no)
- Added XBRLFact ORM model (xbrl_facts) with BigInteger value_cents, unique constraint on (company_id, concept, end_date, fiscal_period)
- Created Alembic migration 003 chaining from 002, creates both tables with all indexes
- Added FilingCollectionSettings to config.py with configurable form types, section_max_chars, and max filing counts
- Files created: src/ai_washer/ingestion/types.py, src/ai_washer/db/migrations/versions/003_add_filing_tables.py, tests/unit/test_filing_types.py, tests/unit/test_filing_models.py
- Files modified: src/ai_washer/db/models.py, src/ai_washer/config.py
- Test count: 321 total (260 pre-existing + 41 type tests + 38 model tests - 18 absorbed into count)

## Phase 3, Plan 03: XBRL Financial Fact Extraction -- 2026-03-28
- Built XBRLExtractor class: fetches XBRL companyfacts JSON from EDGAR API with tenacity retry and rate limiting
- Pure function extract_facts_for_concept: tries tags in XBRL_TAG_GROUPS order, uses first match with USD entries
- Pure function deduplicate_by_period: keeps latest filed date per (end, fp) pair to handle amended filings
- Pure function extract_all_facts: extracts rd_expense, capex, revenue concepts into dict of XBRLFactRecord lists
- Dollar-to-cents conversion via int(val * 100) for financial data integrity
- Form filter exact match: "10-K" excludes "10-K/A" and "10-Q"
- Context manager support, SEC-compliant User-Agent, 404 graceful handling
- Updated ingestion/__init__.py to export XBRLExtractor, extract_facts_for_concept, extract_all_facts, deduplicate_by_period
- Full TDD red/green cycle with 23 new tests (pytest-httpx for class, fixture JSON for pure functions)
- Files created: src/ai_washer/ingestion/xbrl_extractor.py, tests/unit/test_xbrl_extractor.py
- Files modified: src/ai_washer/ingestion/__init__.py
- Test count: 344 total (321 pre-existing + 23 new XBRL extractor tests)

## Phase 3, Plan 02: SEC Filing Client (edgartools wrapper) -- 2026-03-28
- Built FilingClient class wrapping edgartools for 10-K, 10-Q, 8-K filing retrieval
- Section extraction via bracket notation on TenK/TenQ objects (Item 1, Item 1A, Item 7)
- Content hash computed as SHA-256 of concatenated non-None section text
- Section length validation: short sections (< 500 chars) trigger warning and full_text_excerpt fallback (Pitfall 1)
- Section text truncated at configurable section_max_chars limit (default 50K, Pitfall 6)
- edgar.set_identity called in __init__ before any API calls (Pitfall 5)
- Graceful error handling: CIK not found and API failures return empty list, no crashes
- Default filing counts from FilingCollectionSettings (5 annual, 8 quarterly, 10 current)
- Context manager protocol for consistency with EdgarFactsClient/EFTSClient
- Updated ingestion/__init__.py with FilingClient, FilingData, FilingSections, XBRLFactRecord, XBRL_TAG_GROUPS, CollectionResult exports
- Full TDD red/green cycle with 15 new tests (mocked edgartools via unittest.mock.patch)
- Files created: src/ai_washer/ingestion/filing_client.py, tests/unit/test_filing_client.py
- Files modified: src/ai_washer/ingestion/__init__.py
- Test count: 359 total (344 pre-existing + 15 new filing client tests)

## Phase 3, Plan 04: Filing Collection Orchestrator and CLI -- 2026-03-28
- Built FilingCollector orchestrator class coordinating FilingClient + XBRLExtractor + DB persistence
- Idempotent collection: skips filings by (company_id, form_type, accession_no) and XBRL facts by (company_id, concept, end_date, fiscal_period)
- Dual timestamps on all persisted records: as_of_date (business date), observed_date (collection date)
- Per-form-type error handling with graceful degradation (errors captured, not raised)
- collect_all iterates active companies with inter-company rate limiting delay
- Collection metadata includes collector_version and collected_at timestamp
- CLI 'collect company <ticker>' for single-company collection with --dry-run
- CLI 'collect all' for full universe collection with --dry-run
- FilingCollector exported from ingestion package __init__.py
- Full TDD red/green cycle with 17 new tests (10 collector + 7 CLI)
- Files created: src/ai_washer/ingestion/filing_collector.py, tests/unit/test_filing_collector.py, tests/unit/test_cli_filings.py
- Files modified: src/ai_washer/cli.py, src/ai_washer/ingestion/__init__.py
- Test count: 376 total (359 pre-existing + 10 collector tests + 7 CLI tests)

## Phase 4, Plan 01: Analysis Foundation -- 2026-03-28
- Created analysis package with shared type contracts and utility functions
- FilingForScoring frozen dataclass: canonical shared input for both SEC and compute scorers
- 5 Pydantic models: KeywordLexicon, SectionKeywordCounts, KeywordFrequencyResult, GrowthRateResult, SignalResult
- Two-tier keyword lexicon: 27 vague buzzwords, 28 substantive terms, 21 cloud/compute keywords (immutable tuples)
- compile_lexicon: word-boundary regex prevents false positives (AI not matching FAIR/MAINTAIN)
- compute_section_weighted_frequency: handles None/short sections with weight renormalization
- compute_cagr: handles zero/negative start, zero years, total decline, flat growth
- build_yearly_series: prefers FY, sums Q1-Q4 if all present, falls back to max quarterly
- sigmoid_normalize: deterministic 0-100 int scores, overflow-safe (clamp at +/-500)
- Added pythonpath=["src"] to pytest config for worktree compatibility
- Files created: src/ai_washer/analysis/{__init__,types,keywords,growth,normalization}.py, tests/unit/{test_analysis_types,test_keywords,test_growth,test_normalization}.py
- Files modified: pyproject.toml
- Test count: 443 total (376 pre-existing + 67 new analysis tests)

## Phase 4, Plan 03: Compute Spending Gap Scorer -- 2026-03-28
- Built compute spending gap scorer: pure-function engine detecting flat CapEx despite growing AI narrative
- count_cloud_mentions_by_year: detects cloud/compute keywords in mda, risk_factors, business sections
- compute_capex_keyword_gap: CapEx vs AI keyword growth divergence with 70% CapEx + 30% cloud mention weighting
- compute_compute_spending_score: full scoring pipeline producing SignalResult(signal_type="compute_spending", score=0-100)
- Imports FilingForScoring from shared types.py (no local type definitions)
- Uses CLOUD_COMPUTE_KEYWORDS from keywords.py for cloud mention detection
- Evidence includes filing_text data_source per Pitfall 6 (transcripts in Phase 7)
- Signal version 0.4.0, sigmoid normalization, full audit trail in evidence JSONB
- Updated analysis/__init__.py with 3 new exports
- Full TDD red/green cycle with 25 new tests
- Files created: src/ai_washer/analysis/compute_spending_scorer.py, tests/unit/test_compute_spending_scorer.py
- Files modified: src/ai_washer/analysis/__init__.py
- Test count: 468 total (443 pre-existing + 25 new compute scorer tests)

## Phase 4, Plan 04: Scoring Orchestrator and CLI -- 2026-03-28
- Built ScoringOrchestrator: thin DB layer bridging pure scorers to database reads/writes
- Only analysis module with DB access; reads Filing+XBRLFact, writes SignalDetail with evidence JSONB
- Idempotent persistence: exists-check on (company_id, signal_type, as_of_date) before insert
- Keyword counts shared between SEC and compute scorers for consistency
- CLI score subcommands: score company TICKER and score all with --dry-run and --date options
- Extended scoring.yaml with sec_filing and compute_spending parameter sections
- Added SecFilingScoringConfig and ComputeSpendingScoringConfig Pydantic models with validation bounds
- Integration test proves SignalDetail rows persisted and queryable in PostgreSQL (SCORE-02)
- ScoringOrchestrator exported from analysis package
- Full TDD red/green cycle
- Files created: src/ai_washer/analysis/scoring_orchestrator.py, tests/unit/{test_scoring_config,test_scoring_orchestrator,test_cli_scoring}.py, tests/integration/test_signal_persistence.py
- Files modified: config/scoring.yaml, src/ai_washer/config.py, src/ai_washer/cli.py, src/ai_washer/analysis/__init__.py, pyproject.toml
- Test count: 520 total (468 pre-existing + 16 config tests + 8 orchestrator tests + 6 CLI tests + 2 integration tests + 20 absorbed)
