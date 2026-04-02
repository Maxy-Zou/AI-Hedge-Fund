# Phase 10: Data Quality and Pipeline Automation - Research

**Researched:** 2026-03-30
**Domain:** Pipeline orchestration, data validation, operational monitoring
**Confidence:** HIGH

## Summary

Phase 10 wraps the complete AI Washing Detector into an autonomous daily pipeline. All 6 signal collectors, all 6 scorers, and the composite scorer exist and work via CLI commands. The work is: (1) add Pydantic schema validation at ingestion boundaries for DQ-01/DQ-03, (2) build a DataSourceStatus tracking table for staleness monitoring (DQ-02), (3) wire everything into Prefect flows/tasks with per-stage error isolation (OPS-03), (4) enhance the existing PipelineRun model with richer status tracking (OPS-04), (5) add correlation IDs to structlog via contextvars (OPS-02), and (6) ensure tenacity retry decorators exist on all API clients (OPS-01 -- already mostly done).

The existing codebase has strong foundations: structlog is configured with `merge_contextvars` already in the processor pipeline, tenacity retry decorators exist on all 7 API clients, PipelineRun ORM model exists with start/end/status/errors fields, and all collectors follow a consistent `collect_for_company`/`collect_all` API pattern. The main new work is Prefect integration and the data quality monitoring layer.

**Primary recommendation:** Use Prefect 3.6.24 with `@flow`/`@task` decorators wrapping existing collector and scorer orchestrator calls. Do NOT rewrite collectors -- wrap them. Keep Prefect as a thin orchestration layer over the existing sync codebase.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- discuss phase was skipped per user setting. All implementation choices are at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion -- discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None -- discuss phase skipped.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DQ-01 | All ingested data passes Pydantic schema validation -- malformed records rejected with structured error logs | Pydantic models already exist for most types (FilingData, XBRLFactRecord, etc). Need validation wrappers at collector boundaries that catch ValidationError and log rejections. |
| DQ-02 | Data source availability monitoring tracks last-successful-fetch per source, flags staleness | New DataSourceStatus ORM model + Alembic migration. Track 6 sources with expected cadence and last_success timestamp. |
| DQ-03 | Input validation enforces types, ranges, and required fields at all system boundaries | Extend existing Pydantic contracts with stricter Field constraints (ranges for scores 0-100, non-empty strings, date ranges). Add validation at API response parsing boundaries. |
| OPS-01 | Retry logic with exponential backoff on all external API calls using tenacity | Already implemented on all 7 clients (EdgarClient, EFTSClient, FilingClient, XBRLExtractor, PatentClient, GitHubClient, EarningsClient, JobClient). Audit and standardize configuration. |
| OPS-02 | Structured JSON logging via structlog with correlation IDs per pipeline run | structlog already configured with merge_contextvars. Add bind_contextvars(run_id=...) at pipeline start, clear at end. |
| OPS-03 | Daily batch pipeline orchestration with per-stage error handling | New Prefect flow with 4 stages as tasks: ingestion, analysis, scoring, output. Each task catches exceptions independently. |
| OPS-04 | Pipeline run status tracking with start/end times, status, companies_processed, errors | PipelineRun model already exists. Enhance with per-source error breakdown and partially_failed status. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python 3.11+ with ruff linting (line-length=100, target-version=py312)
- Immutable data patterns -- return new objects, never mutate
- All monetary values in cents (integers)
- structlog for logging with event-style keys (snake_case)
- tenacity for retry logic
- Lazy imports in CLI for fast startup
- Type hints required on all params and return values
- `from __future__ import annotations` at top of every file
- Google-style docstrings with Args, Returns, Raises sections
- Functions <50 lines, files <800 lines
- Pydantic for data validation at contract boundaries
- SQLAlchemy 2.0 style with `mapped_column()`

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| prefect | 3.6.24 | Pipeline orchestration, scheduling, monitoring | Python-native @flow/@task decorators, built-in retries and caching. Latest stable on PyPI. |
| structlog | 25.5.0 | Structured logging with correlation IDs | Already installed and configured. contextvars support already in processor pipeline. |
| tenacity | 9.1.4+ | Retry with exponential backoff | Already installed and used on all API clients. |
| pydantic | 2.12.5+ | Schema validation at ingestion boundaries | Already installed. Existing type contracts in types.py files. |
| alembic | 1.18.4+ | Database migration for new DataSourceStatus table | Already installed. Existing migration infrastructure. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| freezegun | 1.5.5+ | Time mocking in tests | Testing staleness detection and pipeline run timing |
| pytest-timeout | 2.3+ | Test timeout enforcement | Preventing hung tests in pipeline integration tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Prefect orchestration | Plain cron + Python script | Loses retry, monitoring, partial failure handling. Prefect adds ~50MB but gives observability for free. |
| Prefect serve | Prefect Cloud | Cloud adds cost and external dependency. flow.serve() with cron is sufficient for single-machine daily batch. |
| New validation layer | Pandera (dataframe validation) | Overkill -- we validate individual records, not dataframes. Pydantic already handles this. |

**Installation:**
```bash
uv pip install "prefect>=3.6.23"
```

**Version verification:** Prefect 3.6.24 confirmed on PyPI (2026-03-29). structlog 25.5.0 confirmed installed. tenacity installed (version verified via pip list).

## Architecture Patterns

### Recommended Project Structure
```
src/ai_washer/
  pipeline/               # NEW: Pipeline orchestration (Phase 10)
    __init__.py
    daily_flow.py          # Prefect @flow: daily_pipeline_flow()
    stages.py              # Prefect @task functions wrapping collectors/scorers
    validation.py          # Pydantic validation wrappers for ingestion data
    monitoring.py           # DataSourceStatus tracking logic
    types.py               # Pipeline-specific Pydantic types
  db/
    models.py              # MODIFIED: Add DataSourceStatus model
    migrations/versions/   # NEW: Migration for data_source_status table
  logging.py               # MODIFIED: Add correlation ID helper
```

### Pattern 1: Thin Prefect Wrapper Over Existing Code
**What:** Prefect @task decorators wrap existing collector.collect_all() and orchestrator.score_all() calls without modifying them.
**When to use:** Always -- do NOT rewrite collectors to be Prefect-native.
**Example:**
```python
from prefect import flow, task
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

@task(name="collect-sec-filings", retries=1, retry_delay_seconds=60)
def collect_sec_filings(app_settings: AppSettings) -> StageResult:
    """Wrap existing FilingCollector.collect_all() as a Prefect task."""
    from ai_washer.ingestion.filing_collector import FilingCollector
    collector = FilingCollector(app_settings=app_settings)
    results = collector.collect_all()
    return StageResult(
        stage="sec_filings",
        companies_processed=len(results),
        errors=[e for r in results for e in r.errors],
    )

@flow(name="daily-ai-washing-pipeline", log_prints=True)
def daily_pipeline_flow() -> PipelineRunResult:
    run_id = uuid.uuid4()
    bind_contextvars(run_id=str(run_id), pipeline="daily_batch")
    try:
        # Stage 1: Ingestion (independent per source)
        sec_result = collect_sec_filings(app_settings)
        patent_result = collect_patents(app_settings)
        # ... other collectors

        # Stage 2: Scoring
        scoring_result = score_all_companies(app_settings)

        # Stage 3: Composite
        composite_result = compute_composites(app_settings)

        return PipelineRunResult(...)
    finally:
        clear_contextvars()
```

### Pattern 2: Per-Stage Error Isolation
**What:** Each Prefect task catches its own exceptions and returns a result object. The flow continues even if one stage fails.
**When to use:** All pipeline stages -- a failed patent collection should not prevent scoring.
**Example:**
```python
@task(name="collect-patents")
def collect_patents(app_settings: AppSettings) -> StageResult:
    try:
        collector = PatentCollector(app_settings=app_settings)
        results = collector.collect_all()
        return StageResult(stage="patents", status="succeeded", ...)
    except Exception as exc:
        logger.warning("stage_failed", stage="patents", error=str(exc), exc_info=True)
        return StageResult(stage="patents", status="failed", errors=[str(exc)])
```

### Pattern 3: Validation Wrapper at Ingestion Boundary
**What:** Validate raw API responses through Pydantic before passing to collectors.
**When to use:** At the boundary between external API data and internal processing.
**Example:**
```python
from pydantic import ValidationError

def validate_and_collect(raw_records: list[dict], model: type[BaseModel]) -> tuple[list, list]:
    """Validate raw records, returning (valid, rejected) tuple."""
    valid = []
    rejected = []
    for record in raw_records:
        try:
            validated = model.model_validate(record)
            valid.append(validated)
        except ValidationError as exc:
            logger.warning(
                "record_rejected",
                model=model.__name__,
                errors=exc.error_count(),
                details=str(exc),
            )
            rejected.append({"record": record, "error": str(exc)})
    return valid, rejected
```

### Pattern 4: Staleness Monitoring
**What:** DataSourceStatus table tracks last successful fetch per source with expected cadence.
**When to use:** After each successful collection stage completes.
**Example:**
```python
class DataSourceStatus(Base):
    __tablename__ = "data_source_status"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_message: Mapped[str | None] = mapped_column(String(500))
    expected_cadence_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    is_stale: Mapped[bool] = mapped_column(Boolean, server_default=sa.text("false"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

### Anti-Patterns to Avoid
- **Rewriting collectors as Prefect tasks:** Collectors work. Wrap them, don't rewrite them.
- **Using Prefect Cloud for v1:** Unnecessary complexity. flow.serve() with cron is sufficient for local daily batch.
- **Putting validation logic in the flow:** Validation belongs in a reusable module, not in Prefect task bodies.
- **Blocking entire pipeline on one stage failure:** Each stage must be independent with its own error handling.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pipeline scheduling | Custom cron + subprocess | Prefect flow.serve(cron="...") | Built-in retry, monitoring, state tracking |
| Retry logic | Custom retry loops | tenacity @retry decorator | Already used throughout codebase, battle-tested |
| Correlation IDs | Custom thread-local storage | structlog.contextvars | Already configured in logging.py processor pipeline |
| Data validation | Custom if/else chains | Pydantic model_validate() | Already used for all type contracts, auto-generates error messages |
| Pipeline state machine | Custom status tracking | Prefect flow states + PipelineRun model | Prefect handles running/failed/completed states |

**Key insight:** Almost all infrastructure for this phase already exists. The work is wiring it together, not building new abstractions.

## Common Pitfalls

### Pitfall 1: Prefect Import Weight
**What goes wrong:** Importing prefect adds significant startup time (~2-3 seconds) due to its dependency tree.
**Why it happens:** Prefect loads its entire runtime including httpx, pydantic, and many internal modules on import.
**How to avoid:** Keep Prefect imports lazy -- only import in the pipeline module, not in cli.py or any module imported at CLI startup. Add a new CLI command group (`pipeline`) with lazy imports.
**Warning signs:** CLI commands like `ai-washer version` becoming slow.

### Pitfall 2: Prefect Server Requirement
**What goes wrong:** Some Prefect features (dashboards, scheduled deployments) require a running Prefect server.
**Why it happens:** Prefect 3 defaults to ephemeral server for simple usage, but flow.serve() needs a persistent process.
**How to avoid:** For v1, use `flow.serve(cron="0 6 * * *")` which runs an embedded server. Document that the process must stay running. For production, consider systemd/launchd service.
**Warning signs:** Scheduled runs showing as "Late" in Prefect logs.

### Pitfall 3: Validation Breaking Existing Data Flow
**What goes wrong:** Adding strict Pydantic validation to existing collectors causes previously-working data to be rejected.
**Why it happens:** External APIs return edge cases (null fields, unexpected types) that were silently handled before.
**How to avoid:** Add validation in "warn" mode first (log but don't reject), then tighten after collecting baseline. Use `model_validate` with `strict=False` initially.
**Warning signs:** Sudden drop in collected records after adding validation.

### Pitfall 4: FinBERT Loading in Pipeline
**What goes wrong:** FinBERT model loading adds 30-60 seconds to pipeline startup, and if it happens inside a Prefect task that retries, it reloads each time.
**Why it happens:** The ScoringOrchestrator lazy-loads FinBERT on first use.
**How to avoid:** Load FinBERT once in the flow, pass the analyzer instance to the scoring task. Or ensure the scoring task only retries on transient errors, not model loading failures.
**Warning signs:** Scoring task taking 60+ seconds on retry.

### Pitfall 5: Correlation ID Leaking Between Runs
**What goes wrong:** contextvars from a previous pipeline run leak into the next run if clear_contextvars() is not called.
**Why it happens:** structlog.contextvars persists across function calls in the same thread.
**How to avoid:** Always call `clear_contextvars()` in a `finally` block at the start and end of each flow run.
**Warning signs:** Logs from run N+1 showing run_id from run N.

### Pitfall 6: PipelineRun ended_at Not Set on Crash
**What goes wrong:** If the pipeline crashes, ended_at stays NULL and status stays "running" forever.
**Why it happens:** No cleanup handler for unexpected termination.
**How to avoid:** Use try/finally to always set ended_at. Also add a startup check that marks any "running" PipelineRun older than 4 hours as "crashed".
**Warning signs:** Multiple PipelineRun rows with status="running".

## Code Examples

### Correlation ID Integration with structlog
```python
# Source: structlog docs + existing logging.py pattern
import uuid
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

def start_pipeline_run() -> uuid.UUID:
    """Initialize a new pipeline run with correlation ID."""
    run_id = uuid.uuid4()
    clear_contextvars()
    bind_contextvars(
        run_id=str(run_id),
        pipeline="daily_batch",
    )
    return run_id
```

### Prefect Flow with Independent Error Handling
```python
from prefect import flow, task
from prefect.states import Completed, Failed

@dataclass(frozen=True)
class StageResult:
    stage: str
    status: str  # "succeeded" | "failed" | "skipped"
    companies_processed: int = 0
    errors: list[str] = field(default_factory=list)

@flow(name="daily-ai-washing-pipeline")
def daily_pipeline_flow() -> None:
    run_id = start_pipeline_run()
    pipeline_run = create_pipeline_run(run_id)

    stages: list[StageResult] = []

    # Ingestion stage -- each source independent
    stages.append(collect_sec_filings_task(settings))
    stages.append(collect_patents_task(settings))
    stages.append(collect_github_task(settings))
    stages.append(collect_earnings_task(settings))
    stages.append(collect_jobs_task(settings))

    # Scoring stage
    stages.append(score_all_task(settings, run_id))

    # Composite stage
    stages.append(composite_task(settings, run_id))

    # Update staleness monitoring
    update_source_status(stages)

    # Finalize pipeline run
    finalize_pipeline_run(pipeline_run, stages)
```

### DataSourceStatus Staleness Check
```python
def check_staleness(session: Session) -> list[dict]:
    """Check all data sources for staleness."""
    from datetime import datetime, timezone

    stmt = select(DataSourceStatus)
    sources = session.execute(stmt).scalars().all()
    stale = []
    now = datetime.now(timezone.utc)

    for source in sources:
        if source.last_success_at is None:
            stale.append({"source": source.source_name, "reason": "never_succeeded"})
        else:
            hours_since = (now - source.last_success_at).total_seconds() / 3600
            if hours_since > source.expected_cadence_hours:
                stale.append({
                    "source": source.source_name,
                    "reason": "exceeded_cadence",
                    "hours_since": hours_since,
                    "expected_hours": source.expected_cadence_hours,
                })
    return stale
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| APScheduler for batch jobs | Prefect 3 with @flow/@task | Prefect 3.0 GA (2024) | Built-in retries, monitoring, partial failure handling |
| Manual correlation IDs | structlog.contextvars | structlog 21.x+ | Thread-safe, zero-boilerplate correlation |
| Custom validation | Pydantic v2 model_validate | Pydantic 2.0 (2023) | Rust-core validation, 5-50x faster than v1 |

**Deprecated/outdated:**
- Prefect 2.x: Significantly different API. All examples should use 3.x patterns.
- APScheduler: Too simple for multi-stage pipeline with independent error handling.

## Open Questions

1. **Prefect Server vs Ephemeral Mode**
   - What we know: flow.serve() with cron requires a long-running process. Prefect can run in ephemeral mode (no separate server) for direct invocation.
   - What's unclear: Whether flow.serve() is stable for months-long daemon use without Prefect Cloud.
   - Recommendation: Start with direct invocation via CLI command (`ai-washer pipeline run`) + system cron. Add flow.serve() as optional "daemon mode" later.

2. **Validation Strictness Level**
   - What we know: Existing collectors handle edge cases with try/except and return empty results.
   - What's unclear: How many existing records would fail strict Pydantic validation.
   - Recommendation: Start with logging-only validation (warn, don't reject). Tighten after baseline.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.12 | -- |
| PostgreSQL | Database | Yes | 16+ (via connection) | -- |
| prefect | OPS-03 | No | -- | Must install: `uv pip install "prefect>=3.6.23"` |
| structlog | OPS-02 | Yes | 25.5.0 | -- |
| tenacity | OPS-01 | Yes | 9.x | -- |
| pydantic | DQ-01, DQ-03 | Yes | 2.12.5+ | -- |
| alembic | DQ-02 | Yes | 1.18.4 | -- |

**Missing dependencies with no fallback:**
- prefect: Must be installed. Add to pyproject.toml dependencies.

**Missing dependencies with fallback:**
- None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0+ |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/unit/ -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DQ-01 | Pydantic validation rejects malformed records with structured logs | unit | `python -m pytest tests/unit/test_pipeline_validation.py -x` | No -- Wave 0 |
| DQ-02 | Staleness monitoring flags stale sources | unit | `python -m pytest tests/unit/test_source_monitoring.py -x` | No -- Wave 0 |
| DQ-03 | Input validation enforces types, ranges, required fields | unit | `python -m pytest tests/unit/test_pipeline_validation.py -x` | No -- Wave 0 |
| OPS-01 | Retry decorators exist on all API clients | unit | `python -m pytest tests/unit/test_retry_audit.py -x` | No -- Wave 0 |
| OPS-02 | Correlation IDs appear in structured logs | unit | `python -m pytest tests/unit/test_pipeline_logging.py -x` | No -- Wave 0 |
| OPS-03 | Pipeline flow runs stages independently, partial failure handled | unit | `python -m pytest tests/unit/test_daily_flow.py -x` | No -- Wave 0 |
| OPS-04 | PipelineRun tracks start/end/status/errors per run | unit | `python -m pytest tests/unit/test_pipeline_tracking.py -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -x -q --timeout=30`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_pipeline_validation.py` -- covers DQ-01, DQ-03
- [ ] `tests/unit/test_source_monitoring.py` -- covers DQ-02
- [ ] `tests/unit/test_retry_audit.py` -- covers OPS-01
- [ ] `tests/unit/test_pipeline_logging.py` -- covers OPS-02
- [ ] `tests/unit/test_daily_flow.py` -- covers OPS-03
- [ ] `tests/unit/test_pipeline_tracking.py` -- covers OPS-04
- [ ] Prefect install: `uv pip install "prefect>=3.6.23"` -- required before flow tests

## Existing Code Inventory

### What Already Exists (do NOT rebuild)
| Component | Location | Status |
|-----------|----------|--------|
| PipelineRun ORM model | `src/ai_washer/db/models.py:126` | Exists with id, started_at, ended_at, status, companies_processed, errors |
| structlog with contextvars | `src/ai_washer/logging.py` | merge_contextvars already in processor pipeline |
| tenacity on EdgarClient | `src/ai_washer/ingestion/edgar_client.py` | 3 attempts, exponential backoff |
| tenacity on EFTSClient | `src/ai_washer/ingestion/efts_client.py` | 3 attempts, exponential backoff |
| tenacity on PatentClient | `src/ai_washer/ingestion/patent_client.py` | 3 attempts, exponential backoff |
| tenacity on GitHubClient | `src/ai_washer/ingestion/github_client.py` | 3 attempts, exponential backoff |
| tenacity on EarningsClient | `src/ai_washer/ingestion/earnings_client.py` | 3 attempts, exponential backoff |
| tenacity on JobClient | `src/ai_washer/ingestion/job_client.py` | 3 attempts, exponential backoff |
| tenacity on XBRLExtractor | `src/ai_washer/ingestion/xbrl_extractor.py` | 3 attempts, exponential backoff |
| Pydantic type contracts | `src/ai_washer/ingestion/types.py`, `*/types.py` | FilingData, XBRLFactRecord, CollectionResult, etc. |
| ScoringOrchestrator.score_all() | `src/ai_washer/analysis/scoring_orchestrator.py` | Scores all companies, persists signals + composites |
| All 5 collectors | `src/ai_washer/ingestion/*_collector.py` | collect_for_company() + collect_all() pattern |
| CLI commands | `src/ai_washer/cli.py` | All collect/score commands working |

### What Needs Building
| Component | Purpose | Requirement |
|-----------|---------|-------------|
| `src/ai_washer/pipeline/` module | Prefect flow + tasks | OPS-03 |
| DataSourceStatus ORM model | Staleness tracking | DQ-02 |
| Alembic migration | data_source_status table | DQ-02 |
| Validation wrappers | Pydantic validation at ingestion boundary | DQ-01, DQ-03 |
| Correlation ID helpers | bind/clear contextvars in pipeline | OPS-02 |
| Enhanced PipelineRun tracking | per-source errors, stage breakdown | OPS-04 |
| Pipeline CLI commands | `ai-washer pipeline run`, `ai-washer pipeline status` | OPS-03 |

### Expected Source Cadences (for DQ-02)
| Source | Expected Cadence | Rationale |
|--------|-----------------|-----------|
| sec_filings | 24 hours | Daily batch |
| patents | 168 hours (7 days) | Weekly refresh per PAT-03 |
| github | 24 hours | Daily batch |
| earnings | 2160 hours (90 days) | Quarterly refresh per EARN-05 |
| job_postings | 24 hours | Daily batch |
| xbrl_facts | 24 hours | Collected alongside filings |

## Sources

### Primary (HIGH confidence)
- Codebase inspection -- all source files read directly
- [Prefect PyPI](https://pypi.org/project/prefect/) - v3.6.24 confirmed (Mar 2026)
- [structlog contextvars docs](https://www.structlog.org/en/stable/contextvars.html) - merge_contextvars pattern
- [Prefect Flows docs](https://docs.prefect.io/v3/concepts/flows) - @flow/@task decorator patterns

### Secondary (MEDIUM confidence)
- [Prefect retries guide](https://docs.prefect.io/v3/how-to-guides/workflows/retries) - retry_delay_seconds, exponential_backoff
- [Prefect local processes](https://docs-3.prefect.io/v3/deploy/run-flows-in-local-processes) - flow.serve() pattern

### Tertiary (LOW confidence)
- [Prefect flow.serve cron bug](https://github.com/PrefectHQ/prefect/issues/17208) - 422 error with cron in 3.2.2+, may be resolved in 3.6.x. Needs validation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries verified on PyPI, most already installed
- Architecture: HIGH - Wrapping existing code, minimal new abstractions
- Pitfalls: HIGH - Based on direct codebase inspection and known Prefect patterns
- Data quality: HIGH - Pydantic already used throughout, pattern is clear

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (Prefect releases weekly, but API is stable in 3.x)
