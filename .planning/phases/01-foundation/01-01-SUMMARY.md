---
phase: 01-foundation
plan: 01
subsystem: infra
tags: [python, pydantic, pydantic-settings, sqlalchemy, structlog, langgraph, pydantic-ai, claude]

# Dependency graph
requires: []
provides:
  - Installable ai-hedge-fund Python package with all core dependencies
  - AppSettings configuration loaded from environment with token budget defaults
  - ModelTier enum with Claude Haiku/Sonnet/Opus model IDs and frozen AgentBudget presets
  - PipelineState TypedDict for LangGraph graph state
  - ExtractionOutput, AnalysisOutput, ThesisOutput, SignalOutput validated schemas
  - SQLAlchemy Base with AppendOnlyMixin and DualTimestampMixin
  - DB engine and session factory with connection pooling
  - structlog JSON logging with UTC timestamps
affects: [01-02, 01-03, 02-data-pipeline, 03-agents]

# Tech tracking
tech-stack:
  added: [langgraph, langchain-core, langchain-anthropic, pydantic-ai, anthropic, pydantic, pydantic-settings, langgraph-checkpoint-postgres, psycopg, sqlalchemy, alembic, structlog, httpx, tenacity, langfuse, pytest, pytest-cov, pytest-asyncio, ruff]
  patterns: [pydantic-settings env loading, frozen dataclass for immutable config, TypedDict for LangGraph state, BaseModel with Field constraints for agent outputs, dual-model routing enum]

key-files:
  created:
    - pyproject.toml
    - src/ai_hedge_fund/__init__.py
    - src/ai_hedge_fund/config.py
    - src/ai_hedge_fund/models.py
    - src/ai_hedge_fund/logging.py
    - src/ai_hedge_fund/db/base.py
    - src/ai_hedge_fund/db/session.py
    - src/ai_hedge_fund/schemas/state.py
    - src/ai_hedge_fund/schemas/agents.py
    - src/ai_hedge_fund/schemas/__init__.py
    - tests/conftest.py
    - tests/unit/test_config.py
    - tests/unit/test_schemas.py
    - .env.example
    - .gitignore
  modified: []

key-decisions:
  - "Used pydantic-settings SettingsConfigDict with env_file='.env' and extra='ignore' for clean config loading"
  - "ModelTier enum values use PydanticAI model string format (anthropic:model-name) for direct agent construction"
  - "AgentBudget as frozen dataclass rather than BaseModel for simplicity and guaranteed immutability"
  - "PipelineState uses TypedDict with total=False and Required[] annotations for LangGraph compatibility"
  - "Schema validation uses Pydantic Field constraints (ge/le/min_length/Literal) at the boundary"

patterns-established:
  - "Config pattern: AppSettings(BaseSettings) with get_settings() factory for testability"
  - "Model routing: ModelTier enum -> MODEL_BUDGETS dict -> AgentBudget frozen dataclass"
  - "Schema validation: Pydantic BaseModel with Field constraints for all agent I/O boundaries"
  - "DB mixins: AppendOnlyMixin (created_at + as_of_date) and DualTimestampMixin (as_of_date + observed_date)"
  - "TDD workflow: write failing tests first, implement to pass, verify with ruff"

requirements-completed: [FOUND-02, FOUND-03]

# Metrics
duration: 6min
completed: 2026-04-12
---

# Phase 1 Plan 1: Project Scaffold Summary

**Python package with pydantic-settings config, Claude model routing (Haiku/Sonnet/Opus), typed LangGraph state, validated PydanticAI output schemas, and SQLAlchemy DB foundation**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-12T06:39:09Z
- **Completed:** 2026-04-12T06:44:41Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments
- Installable Python package with 18 production dependencies and 4 dev dependencies via uv
- AppSettings configuration with environment loading, token budget defaults (22K/58K/116K/500K), and all API key fields
- ModelTier enum with current Claude model IDs and immutable AgentBudget presets mapped via MODEL_BUDGETS
- Five typed schemas: PipelineState (LangGraph), ExtractionOutput, AnalysisOutput, ThesisOutput, SignalOutput (PydanticAI)
- SQLAlchemy declarative base with AppendOnlyMixin and DualTimestampMixin for financial data conventions
- 34 unit tests passing covering config defaults, model tiers, budget immutability, schema validation, and serialization

## Task Commits

Each task was committed atomically:

1. **Task 1: Project scaffold, dependencies, config, models, logging, DB session**
   - `beac179` (test: failing tests for config, models, logging -- TDD RED)
   - `769c3e5` (feat: scaffold project with config, models, logging, DB session -- TDD GREEN)
2. **Task 2: LangGraph state schemas and PydanticAI output schemas**
   - `5caeab4` (test: failing tests for schemas -- TDD RED)
   - `31711e2` (feat: add LangGraph state and PydanticAI output schemas -- TDD GREEN)

## Files Created/Modified
- `pyproject.toml` -- Package definition with all 18 production + 4 dev dependencies
- `src/ai_hedge_fund/__init__.py` -- Package root with version
- `src/ai_hedge_fund/config.py` -- AppSettings with env loading and token budget defaults
- `src/ai_hedge_fund/models.py` -- ModelTier enum, AgentBudget frozen dataclass, MODEL_BUDGETS mapping
- `src/ai_hedge_fund/logging.py` -- structlog JSON configuration with UTC timestamps
- `src/ai_hedge_fund/db/__init__.py` -- Database layer module
- `src/ai_hedge_fund/db/base.py` -- DeclarativeBase, AppendOnlyMixin, DualTimestampMixin
- `src/ai_hedge_fund/db/session.py` -- Engine and session factory with connection pooling
- `src/ai_hedge_fund/schemas/__init__.py` -- Re-exports all schema classes
- `src/ai_hedge_fund/schemas/state.py` -- PipelineState TypedDict for LangGraph
- `src/ai_hedge_fund/schemas/agents.py` -- ExtractionOutput, AnalysisOutput, ThesisOutput, SignalOutput
- `tests/conftest.py` -- Shared test fixtures
- `tests/unit/test_config.py` -- 14 tests for config, models, logging
- `tests/unit/test_schemas.py` -- 20 tests for schema validation
- `.env.example` -- All environment variables with comments
- `.gitignore` -- Python, secrets, IDE, OS exclusions

## Decisions Made
- Used `pydantic-settings` SettingsConfigDict with `env_file=".env"` and `extra="ignore"` for clean configuration loading that ignores unknown env vars
- ModelTier enum values use PydanticAI model string format (`anthropic:claude-haiku-4-5`) so they can be passed directly to PydanticAI Agent constructors
- AgentBudget implemented as frozen dataclass (not BaseModel) for simplicity and guaranteed immutability via `@dataclass(frozen=True)`
- PipelineState uses TypedDict with `total=False` and `Required[]` annotations for LangGraph StateGraph compatibility
- ThesisOutput.confidence uses int 0-100 range (not float 0-1) for clearer human readability in thesis documents
- SignalOutput uses Literal types for direction/conviction to enforce categorical constraints at the Pydantic validation boundary

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None -- no external service configuration required. Docker Compose PostgreSQL is needed for runtime but not for tests.

## Next Phase Readiness
- Package installs and imports cleanly -- all subsequent plans can import from `ai_hedge_fund`
- Config, models, and schemas provide the typed foundation for Plan 02 (LangGraph pipeline) and Plan 03 (Langfuse observability)
- DB session factory ready for PostgreSQL checkpointing in Plan 02

## Self-Check: PASSED

- All 16 created files verified present on disk
- All 4 task commits verified in git log (beac179, 769c3e5, 5caeab4, 31711e2)
- 34/34 unit tests passing
- ruff check src/ clean

---
*Phase: 01-foundation*
*Completed: 2026-04-12*
