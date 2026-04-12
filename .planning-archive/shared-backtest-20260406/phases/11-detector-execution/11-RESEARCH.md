# Phase 11: Detector Execution - Research

**Researched:** 2026-03-30
**Domain:** AI Washing Detector CLI, Prefect pipeline orchestration, PostgreSQL scoring tables
**Confidence:** HIGH

## Summary

Phase 11 runs the AI Washing Detector pipeline against real SEC filings to produce `daily_scores` rows in PostgreSQL. The detector has two stages: (1) `universe scan` — populates the `companies` table from SEC EDGAR's full-text search, and (2) the full pipeline — collects all signal data sources and runs scoring. The pipeline is orchestrated by a Prefect `@flow` (`daily_pipeline_flow`) invokable via `ai-washer pipeline run`.

The detector package is fully implemented and functional. The primary execution concerns for this phase are operational: setting the correct env vars, applying the PYTHONPATH workaround (same spaces-in-path issue established in Phase 9), ensuring PyTorch is installed for FinBERT sentiment scoring, and accepting that a full first run will take 4-10 hours due to SEC EDGAR rate limiting (10 req/sec).

All six scoring signals are implemented in `analysis/`. The `ScoringOrchestrator.score_all()` method iterates all active companies, scores each against six signals (SEC filing, compute spending, patent gap, GitHub activity, earnings vagueness, job mismatch), persists `SignalDetail` rows, and writes `DailyScore` composite rows. The `daily_scores` table is monthly RANGE-partitioned with partitions pre-created through 2027-06 in migration 001.

**Primary recommendation:** Run `ai-washer universe scan` first to populate companies, then `ai-washer pipeline run` for the full ingestion + scoring pass. Both commands must be executed with `PYTHONPATH` set explicitly and all required env vars present.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DET-01 | Running `ai-washer universe scan` populates the companies table with real mid-cap entities from SEC EDGAR | `universe scan` command confirmed in CLI; `UniverseBuilder.build()` orchestrates EFTS search → market cap filter → entity resolution → persist |
| DET-02 | Running the AI Washing Detector pipeline produces real `daily_scores` rows in PostgreSQL from SEC filing analysis | `daily_pipeline_flow` Prefect flow confirmed; `ScoringOrchestrator.score_all()` persists `SignalDetail` + `DailyScore` rows; partitioned table pre-created |
| DET-03 | The pipeline completes without manual intervention and logs progress via structlog | All stages use structlog with `stage_started`/`stage_completed` events; each stage is isolated — failure in one does not block others |
</phase_requirements>

## Standard Stack

### Core (already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| edgartools | 5.26.1+ | SEC EDGAR filing access | Handles EFTS search, XBRL extraction, filing parsing |
| prefect | 3.6.24 (verified) | Pipeline orchestration | `@flow` decorator in `daily_flow.py` |
| transformers | 5.3.0 (verified) | FinBERT NLP model | Earnings vagueness scoring; requires PyTorch |
| torch | 2.4+ | FinBERT inference backend | **NOT installed** in current venv — must install for earnings signal |
| tenacity | 9.1.4+ | Retry logic | SEC EDGAR 10 req/sec rate limiting |
| structlog | 25.5.0+ | Structured logging | Pipeline progress and correlation |

### PyTorch Gap

The venv was created on macOS x86_64 (`darwin` + `x86_64`). The `pyproject.toml` conditionally excludes torch:

```
"torch>=2.4,<3.0; sys_platform != 'darwin' or platform_machine == 'arm64'"
```

This condition evaluates to **False** on macOS x86_64 — torch is not installed. The `FinBERTAnalyzer` will fail when `_ensure_loaded()` is called during earnings vagueness scoring. The scorer will raise `ImportError` from `transformers` when it attempts to use torch as the backend.

**Resolution options (in order of preference):**
1. Install torch manually: `uv pip install torch>=2.4` in the detector venv — keeps all 6 signals active
2. Accept degraded scoring: earnings vagueness signal will be skipped with `signal_skipped` log if FinBERT fails gracefully, but the current code does NOT have a graceful fallback — it will raise during `ScoringOrchestrator.score_company()` unless the exception propagates to the stage wrapper in `stages.py`, which catches `Exception` and marks stage as failed

**Confirmed:** `stages.py` `score_all_stage()` wraps `orch.score_all()` in `try/except Exception` — if FinBERT fails for one company, the entire scoring stage returns `status="failed"`. The exception must be caught at the per-company level to allow partial scoring.

### Installation

```bash
# From Al Washing Detector/ directory
cd "Al Washing Detector"

# Install PyTorch (required for FinBERT earnings scoring)
PYTHONPATH="$(pwd)/src" .venv/bin/pip install torch>=2.4

# Verify everything is available
PYTHONPATH="$(pwd)/src" \
  AI_WASHER_DATABASE_URL="postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund" \
  AI_WASHER_EDGAR_IDENTITY="YourCompany yourname@example.com" \
  .venv/bin/python -m ai_washer check-config
```

**Version verification:** `prefect 3.6.24`, `transformers 5.3.0` confirmed installed. torch absent — requires install.

## Architecture Patterns

### Command Execution Pattern (PYTHONPATH Workaround)

All `ai-washer` commands must be executed with `PYTHONPATH` set explicitly. The `.pth` file mechanism is skipped by Python 3.12 when the venv path contains spaces ("AI Hedgefund").

```bash
# Canonical pattern — confirmed working in Phase 9
cd "/path/to/Al Washing Detector"
PYTHONPATH="$(pwd)/src" \
  AI_WASHER_DATABASE_URL="postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund" \
  AI_WASHER_EDGAR_IDENTITY="CompanyName user@email.com" \
  .venv/bin/python -m ai_washer <command>

# Alternatively, use the installed script with PYTHONPATH
PYTHONPATH="$(pwd)/src" \
  AI_WASHER_DATABASE_URL="..." \
  AI_WASHER_EDGAR_IDENTITY="..." \
  .venv/bin/ai-washer <command>
```

NOTE: `export $(grep -v '^#' ../.env | xargs)` fails when `.env` values contain spaces (e.g., `AI_WASHER_EDGAR_IDENTITY=Company name@example.com`). Set env vars directly inline or use `source .env` equivalent that handles spaces.

### Pipeline Execution Flow

```
ai-washer universe scan
  → UniverseBuilder.build()
    → EFTSClient.search_filings() [keywords: "artificial intelligence", "machine learning"]
    → filter_market_cap() [$1.5B–$9B widened range per Pitfall 2 in config]
    → entity resolution (rapidfuzz fuzzy matching)
    → persist companies to companies table
    → UniverseBuildResult (company_count, new_count, updated_count, deactivated_count)

ai-washer pipeline run
  → daily_pipeline_flow() [Prefect @flow]
    → mark_stale_runs() — clean up crashed prior runs
    → start_pipeline_run() — create PipelineRun record, bind run_id to structlog contextvars
    → collect_sec_filings_stage() → FilingCollector.collect_all() [10-K, 10-Q, 8-K]
    → collect_patents_stage() → PatentCollector.collect_all() [USPTO PatentsView API]
    → collect_github_stage() → GitHubCollector.collect_all() [GitHub REST API v3]
    → collect_earnings_stage() → EarningsCollector.collect_all() [earningscall API]
    → collect_jobs_stage() → JobCollector.collect_all() [python-jobspy scraper]
    → score_all_stage() → ScoringOrchestrator.score_all()
        → per company: score_company() [6 signals]
        → persist_signals() [SignalDetail rows, idempotent]
        → compute_and_persist_composite() [DailyScore row]
    → compute_composites_stage() [currently calls score_all() again — duplicate]
    → end_pipeline_run() — always runs (finally block), updates PipelineRun status
```

### Stage Isolation Pattern

Each ingestion stage in `stages.py` is wrapped in `try/except Exception`. A failure in one stage (e.g., patent API down) returns `StageResult(status="failed")` and does NOT prevent subsequent stages from running. This is the design for an autonomous system.

```python
# Source: Al Washing Detector/src/ai_washer/pipeline/stages.py
def collect_patents_stage(settings: AppSettings) -> StageResult:
    try:
        collector = PatentCollector(app_settings=settings)
        results = collector.collect_all()
        ...
    except Exception as exc:
        logger.warning("stage_failed", stage="patents", error=str(exc), exc_info=True)
        return StageResult(stage="patents", status="failed", errors=[str(exc)])
```

### DailyScore Table

- **Schema:** `daily_scores` — RANGE partitioned on `scored_at` (DateTime with timezone)
- **Partitions:** Pre-created monthly through 2027-06 in migration 001
- **Idempotency:** `ScoringOrchestrator.persist_composite()` checks for existing row via `func.date(DailyScore.scored_at) == scoring_date` before inserting — safe to re-run
- **Composite score:** integer `SmallInteger` (0-100 range), `signal_breakdown` JSONB, `confidence` float, `weights_used` JSONB
- **Key field:** `run_id` UUID — links each score to its pipeline run for tracing

### Anti-Patterns to Avoid

- **Running without PYTHONPATH:** `uv run ai-washer` silently fails with ModuleNotFoundError on this project path
- **Using `export $(grep .env | xargs)`:** Fails when env var values contain spaces — use inline env vars
- **Running pipeline before universe scan:** `ScoringOrchestrator.score_all()` selects `WHERE Company.is_active = True AND Company.cik IS NOT NULL` — if companies table is empty, 0 scores are produced with no error
- **Expecting instant completion:** First run processes N companies × 5 data sources at 10 req/sec SEC limit — budget 4-10 hours

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pipeline orchestration | Custom scheduler | `ai-washer pipeline run` / `daily_pipeline_flow()` | Prefect flow already implemented with stage isolation and correlation IDs |
| Score computation | Direct SQL inserts | `ScoringOrchestrator.score_all()` | Handles all 6 signals, idempotency checks, composite computation |
| Progress logging | Custom print statements | structlog contextvars already bound with `run_id` | Every log line in the pipeline already carries the run correlation ID |
| Universe scan | Manual EDGAR API calls | `ai-washer universe scan` | UniverseBuilder handles EFTS pagination, market cap widening, entity resolution |
| .env loading | Manual `source .env` | Inline env vars in command string | Avoids the space-in-value `xargs` failure |

## Common Pitfalls

### Pitfall 1: torch Not Installed on macOS x86_64

**What goes wrong:** `ai-washer pipeline run` reaches earnings vagueness scoring and raises `ImportError` or `RuntimeError` when FinBERT tries to load PyTorch. The `score_all_stage()` exception handler catches this and marks the entire scoring stage as `failed`. No `daily_scores` rows are written.

**Why it happens:** `pyproject.toml` conditionally excludes torch on `darwin` + non-arm64. The system is macOS x86_64, so torch was never installed.

**How to avoid:** Run `uv pip install "torch>=2.4"` in the detector venv before executing the pipeline.

**Warning signs:** "PyTorch was not found" printed to stderr at import time (transformers logs this at module load); `stage_failed stage=scoring` in structlog output.

### Pitfall 2: EDGAR_IDENTITY Must Be Real

**What goes wrong:** SEC EDGAR rejects requests with invalid User-Agent and returns 403. The `EFTSClient` and `FilingClient` include the identity in every request header.

**Why it happens:** SEC legal requirement — they must be able to contact the data requester.

**How to avoid:** Use a real company name and real email in `AI_WASHER_EDGAR_IDENTITY`. Format: `CompanyName email@domain.com`.

**Warning signs:** `HTTPStatusError: 403` from httpx in SEC collector logs.

### Pitfall 3: Universe Scan Hits EFTS Rate Limits

**What goes wrong:** EFTS search with keyword "artificial intelligence" returns hundreds of pages. Successive requests without delay can trigger 429 responses.

**Why it happens:** SEC EDGAR enforces 10 req/sec. The universe builder uses tenacity retry logic but needs sensible inter-request delays.

**How to avoid:** Run universe scan during off-peak hours. The tenacity decorator handles transient failures, but check the builder's `_inter_company_delay` constant.

**Warning signs:** `stage_failed stage=sec_filings` or repeated `tenacity.RetryError` in logs.

### Pitfall 4: compute_composites_stage Calls score_all() Again

**What goes wrong:** `stages.py` `compute_composites_stage()` calls `ScoringOrchestrator.score_all()` again — this is the same operation as `score_all_stage()`. On second call, `persist_signals()` and `persist_composite()` idempotency checks mean no duplicates, but it doubles the runtime unnecessarily.

**Why it happens:** The stage was added as an explicit tracking step, but `score_all()` already includes composite computation internally. The idempotency checks save correctness but not time.

**How to avoid:** Awareness only — the pipeline still produces correct results. If performance is a concern, the planner can note this as a known inefficiency.

**Warning signs:** Pipeline log shows `scoring_complete` twice with the same companies.

### Pitfall 5: empty_database Gives No Errors But Zero Scores

**What goes wrong:** Running `pipeline run` when `companies` table is empty produces `scoring_complete companies_scored=0 signals_persisted=0` with no error. The pipeline "succeeds" but writes nothing to `daily_scores`.

**Why it happens:** `score_all()` filters `WHERE is_active=True AND cik IS NOT NULL` — returns empty list, scores nobody, writes nothing.

**How to avoid:** Run `universe scan` before `pipeline run`. Verify companies exist via `ai-washer universe list`.

**Warning signs:** Pipeline completes with `companies_processed=0` in the summary output.

### Pitfall 6: PatentsView API Key Optional but Patent Signal Degrades

**What goes wrong:** Without `AI_WASHER_PATENTSVIEW_API_KEY`, the patent collector makes unauthenticated requests to the PatentsView API. The legacy `api.patentsview.org` was discontinued May 2025; the new `search.patentsview.org/api/v1` requires an API key.

**Why it happens:** The CLAUDE.md notes graceful degradation when key is unavailable, but the new API endpoint enforces authentication.

**How to avoid:** Request a free PatentsView API key from the support portal. Set `AI_WASHER_PATENTSVIEW_API_KEY` in env. Without it, `patent_gap` signal will be skipped for all companies.

**Warning signs:** `stage_failed stage=patents` or all companies showing `signal_skipped signal_type=patent_gap`.

## Code Examples

### Universe Scan (DET-01)

```bash
# Source: Al Washing Detector/src/ai_washer/cli.py:scan()
cd "/path/to/Al Washing Detector"
PYTHONPATH="$(pwd)/src" \
  AI_WASHER_DATABASE_URL="postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund" \
  AI_WASHER_EDGAR_IDENTITY="YourCompany yourname@example.com" \
  .venv/bin/python -m ai_washer universe scan

# Output:
# Starting universe scan...
# Scan date: 2026-03-30
# Companies in universe: N
#   New: X
#   Updated: Y
#   Deactivated: Z
#   Skipped (no market cap): W
```

### Verify Companies Before Pipeline

```bash
PYTHONPATH="$(pwd)/src" \
  AI_WASHER_DATABASE_URL="..." \
  AI_WASHER_EDGAR_IDENTITY="..." \
  .venv/bin/python -m ai_washer universe list --limit 10
```

### Full Pipeline Run (DET-02, DET-03)

```bash
# Source: Al Washing Detector/src/ai_washer/cli.py:pipeline_run_cmd()
PYTHONPATH="$(pwd)/src" \
  AI_WASHER_DATABASE_URL="postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund" \
  AI_WASHER_EDGAR_IDENTITY="YourCompany yourname@example.com" \
  AI_WASHER_GITHUB_TOKEN="ghp_..." \
  .venv/bin/python -m ai_washer pipeline run

# Output:
# Pipeline status: succeeded
# Companies processed: N
# Total errors: X
# Stages: 7
#   [OK] sec_filings (N companies)
#   [OK] patents (N companies)
#   ...
```

### Score a Single Company (Validation)

```bash
# Source: Al Washing Detector/src/ai_washer/cli.py:score_company_cmd()
PYTHONPATH="$(pwd)/src" \
  AI_WASHER_DATABASE_URL="..." \
  AI_WASHER_EDGAR_IDENTITY="..." \
  .venv/bin/python -m ai_washer score company MSFT --dry-run
```

### Verify daily_scores After Pipeline

```bash
psql postgresql://hedge:hedge@localhost:5432/ai_hedge_fund \
  -c "SELECT c.ticker, ds.composite_score, ds.confidence, ds.scored_at
      FROM daily_scores ds JOIN companies c ON ds.company_id = c.id
      ORDER BY ds.composite_score DESC LIMIT 20;"
```

### Check Pipeline Status

```bash
PYTHONPATH="$(pwd)/src" \
  AI_WASHER_DATABASE_URL="..." \
  AI_WASHER_EDGAR_IDENTITY="..." \
  .venv/bin/python -m ai_washer pipeline status
```

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | PostgreSQL container | Yes | 29.0.1 | — |
| PostgreSQL | Data store | Yes (container healthy) | 16 | — |
| ai_washer package | All commands | Yes (with PYTHONPATH) | from src/ | — |
| prefect | Pipeline orchestration | Yes | 3.6.24 | — |
| edgartools | Universe scan, filing collection | Yes | 5.26.1 | — |
| transformers | FinBERT earnings scoring | Yes | 5.3.0 | skip earnings signal |
| torch | FinBERT backend | **No** | absent | install via uv pip |
| AI_WASHER_EDGAR_IDENTITY | SEC EDGAR compliance | Needs real value | — | no fallback — SEC requires it |
| AI_WASHER_PATENTSVIEW_API_KEY | Patent signal | No (optional) | — | patent signal degraded/skipped |
| AI_WASHER_GITHUB_TOKEN | GitHub signal (rate limits) | Needs value | — | unauthenticated = 60 req/hr (vs 5K) |
| AI_WASHER_EARNINGSCALL_API_KEY | Earnings transcripts | Needs value | — | EarningsCall API may reject |

**Missing dependencies with no fallback:**
- torch — scoring stage will fail if not installed before pipeline run
- AI_WASHER_EDGAR_IDENTITY must contain a real email (SEC legal requirement)

**Missing dependencies with fallback:**
- AI_WASHER_PATENTSVIEW_API_KEY — patent signal skipped gracefully; other 5 signals still score
- AI_WASHER_GITHUB_TOKEN — GitHub works unauthenticated at 60 req/hr; will hit rate limits for large universe

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0+ |
| Config file | `Al Washing Detector/pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `cd "Al Washing Detector" && PYTHONPATH=src .venv/bin/pytest tests/unit/ -x -q` |
| Full suite command | `cd "Al Washing Detector" && PYTHONPATH=src .venv/bin/pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DET-01 | `universe scan` populates companies table | manual/smoke | `ai-washer universe list` after scan | N/A (operational) |
| DET-02 | `pipeline run` produces `daily_scores` rows | manual/smoke | `SELECT COUNT(*) FROM daily_scores` | N/A (operational) |
| DET-03 | Pipeline completes without manual intervention | manual/smoke | `ai-washer pipeline status` | N/A (operational) |

All three DET requirements are operational (run a command, verify DB state). They are not unit-testable in isolation — they require a live PostgreSQL instance with real SEC EDGAR network access. Verification is by post-condition SQL queries.

### Sampling Rate

- **Per task commit:** N/A — this phase is operational execution, not code changes
- **Per wave merge:** N/A
- **Phase gate:** Verify via SQL post-conditions before `/gsd:verify-work`

### Wave 0 Gaps

None — existing test infrastructure covers all unit tests for this package. Phase 11 is pure operational execution with no new code.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `uv run ai-washer` | `PYTHONPATH=src .venv/bin/python -m ai_washer` | Phase 9 (established) | Required due to spaces-in-path .pth skipping bug |
| api.patentsview.org | search.patentsview.org/api/v1 | May 2025 | Old API discontinued; new API requires API key |

**Deprecated/outdated:**
- `uv run alembic`: Not reliable in this repo (Phase 9 decision) — use `.venv/bin/alembic` with PYTHONPATH
- `api.patentsview.org`: Discontinued May 2025; use `search.patentsview.org/api/v1` with free API key

## Open Questions

1. **PyTorch installation on macOS x86_64**
   - What we know: torch is excluded by the pyproject.toml condition for darwin+x86_64
   - What's unclear: Will `uv pip install torch` install a CPU-only x86 torch that works? Or does it require a separate index?
   - Recommendation: Try `uv pip install torch` in the detector venv first; if it fails, use `pip install torch --index-url https://download.pytorch.org/whl/cpu`

2. **EarningsCall API key requirement**
   - What we know: `earningscall>=2.0.1` is installed; `AI_WASHER_EARNINGSCALL_API_KEY` is an optional setting
   - What's unclear: Whether the earningscall library works without an API key for basic transcript access
   - Recommendation: Test `earnings collect company MSFT --dry-run` to see if unauthenticated access works

3. **Universe scan duration and result count**
   - What we know: EFTS searches for "artificial intelligence" and "machine learning" across mid-cap SEC filers
   - What's unclear: How many companies will actually match and clear the $1.5B-$9B market cap filter (estimated 100-300)
   - Recommendation: Run `universe scan --dry-run` first to see hit count before committing to DB

4. **compute_composites_stage double-scoring**
   - What we know: Both `score_all_stage()` and `compute_composites_stage()` call `ScoringOrchestrator.score_all()` — idempotency prevents duplicate rows but doubles runtime
   - What's unclear: Whether this is intentional or a bug in the pipeline design
   - Recommendation: Plan should note this and either accept it (idempotency protects correctness) or file as a follow-up fix

## Sources

### Primary (HIGH confidence)

- Direct code inspection — `Al Washing Detector/src/ai_washer/cli.py` — all command definitions verified
- Direct code inspection — `Al Washing Detector/src/ai_washer/pipeline/daily_flow.py` — Prefect flow implementation
- Direct code inspection — `Al Washing Detector/src/ai_washer/pipeline/stages.py` — stage isolation pattern
- Direct code inspection — `Al Washing Detector/src/ai_washer/analysis/scoring_orchestrator.py` — score_all() and persist logic
- Direct code inspection — `Al Washing Detector/src/ai_washer/db/models.py` — DailyScore schema
- Direct code inspection — `Al Washing Detector/src/ai_washer/config.py` — AppSettings env var names
- Live CLI test — `ai-washer check-config` confirmed working with PYTHONPATH workaround
- Live DB query — `companies=0, daily_scores=0, sec_filings=0` (current state)
- Live `docker ps` — `ai_hedge_fund_postgres` container healthy
- Phase 9 SUMMARY — PYTHONPATH workaround pattern established and documented

### Secondary (MEDIUM confidence)

- `Al Washing Detector/CLAUDE.md` — PatentsView API key status and endpoint change documented
- `pyproject.toml` torch conditional dependency — macOS x86_64 exclusion confirmed by reading the marker expression

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — directly inspected installed packages and CLI
- Architecture: HIGH — read full pipeline flow implementation
- Pitfalls: HIGH — PyTorch gap confirmed by `pip show torch` returning not found; other pitfalls confirmed by code inspection
- Environment: HIGH — docker ps confirmed healthy; env var names confirmed from config.py and .env.example

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable — no external API changes expected in 30 days)
