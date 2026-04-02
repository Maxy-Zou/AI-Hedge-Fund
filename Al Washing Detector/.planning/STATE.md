---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: Completed 10-04-PLAN.md
last_updated: "2026-03-30T02:35:26.716Z"
last_activity: 2026-03-30
progress:
  total_phases: 10
  completed_phases: 10
  total_plans: 38
  completed_plans: 38
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-27)

**Core value:** Accurately quantify the gap between what companies say about AI and what they do -- producing reliable, machine-consumable signals that an automated trading system can act on without human review.
**Current focus:** Phase 10 — data-quality-and-pipeline-automation

## Current Position

Phase: 10
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-03-30

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 5min | 2 tasks | 18 files |
| Phase 01 P02 | 7min | 2 tasks | 6 files |
| Phase 01 P03 | 28min | 2 tasks | 11 files |
| Phase 02 P01 | 13min | 2 tasks | 13 files |
| Phase 02 P03 | 3min | 2 tasks | 5 files |
| Phase 02 P02 | 5min | 2 tasks | 6 files |
| Phase 02 P04 | 5min | 2 tasks | 6 files |
| Phase 02 P05 | 5min | 3 tasks | 4 files |
| Phase 03 P01 | 17min | 2 tasks | 6 files |
| Phase 03 P03 | 8min | 1 tasks | 4 files |
| Phase 03 P02 | 19min | 2 tasks | 4 files |
| Phase 03 P04 | 5min | 2 tasks | 5 files |
| Phase 04 P01 | 6min | 2 tasks | 10 files |
| Phase 04 P03 | 4min | 1 tasks | 4 files |
| Phase 04 P04 | 9min | 2 tasks | 10 files |
| Phase 05 P02 | 11min | 2 tasks | 5 files |
| Phase 05 P03 | 4min | 2 tasks | 6 files |
| Phase 06-github-signal P01 | 2min | 1 tasks | 5 files |
| Phase 06-github-signal P03 | 2min | 1 tasks | 2 files |
| Phase 06-github-signal P02 | 3min | 1 tasks | 2 files |
| Phase 06-github-signal P04 | 5min | 2 tasks | 8 files |
| Phase 07-earnings-call-signal P01 | 6min | 2 tasks | 10 files |
| Phase 07-earnings-call-signal P03 | 3min | 2 tasks | 5 files |
| Phase 07-earnings-call-signal PP02 | 5min | 2 tasks | 5 files |
| Phase 07-earnings-call-signal P04 | 11min | 2 tasks | 5 files |
| Phase 08-job-posting-signal P03 | 4min | 1 tasks | 2 files |
| Phase 08-job-posting-signal P02 | 5min | 2 tasks | 5 files |
| Phase 08-job-posting-signal P04 | 6min | 1 tasks | 4 files |
| Phase 09 P01 | 3min | 1 tasks | 8 files |
| Phase 09 P03 | 4min | 1 tasks | 3 files |
| Phase 10 P01 | 5min | 2 tasks | 6 files |
| Phase 10 P03 | 4min | 2 tasks | 3 files |
| Phase 10 P02 | 11min | 2 tasks | 4 files |
| Phase 10 P04 | 7min | 2 tasks | 6 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: Entity resolution and universe builder split into own phase (Phase 2) -- research identified these as critical path blockers that deserve focused attention
- [Roadmap]: SEC signal split across two phases (collection in 3, scoring in 4) -- proves full pipeline end-to-end with most reliable data source before expanding
- [Roadmap]: Job postings deferred to Phase 8 (after all other signals) -- noisiest signal, highest ghost job risk, should only be added after pipeline is proven
- [Roadmap]: Compute signal grouped with SEC scoring (Phase 4) -- shares XBRL infrastructure with SEC-03, natural co-delivery
- [Roadmap]: Pipeline automation last (Phase 10) -- only automate what works manually
- [Phase 01]: Used pydantic-settings YamlConfigSettingsSource for scoring config with _yaml_file override for testing
- [Phase 01]: Installed uv 0.11.2 globally as project toolchain (was not pre-installed on system)
- [Phase 01]: DailyScore uses DualTimestampMixin (not AppendOnlyMixin) due to custom composite PK required by partitioning
- [Phase 01]: Company is entity table (not append-only) -- allows updates to aliases, market_cap, sector
- [Phase 01]: Manual Alembic migration (not autogenerate) for daily_scores partitioned table -- autogenerate does not handle PARTITION BY
- [Phase 01]: Integration test pattern: session-scoped testcontainers PostgreSQL with per-test rollback via savepoints
- [Phase 01]: stdlib venv (python3 -m venv) required instead of uv-managed venv due to .pth file processing bug
- [Phase 02]: UniverseSettings uses $1.5B-$9B range (wider than $2B-$10B target) for EntityPublicFloat proxy approximation per Pitfall 2
- [Phase 02]: Soft-delete pattern: is_active Boolean with server_default true + deactivation_reason String(255) per D-10
- [Phase 02]: Pydantic type contracts pattern: types.py in each subpackage defines module interfaces before implementation
- [Phase 02]: GitHub org uses exact match (lowered first word) instead of fuzzy -- short slugs produce too many false positives
- [Phase 02]: Confidence-based review flagging: >=95 auto-approved, threshold-to-95 flagged needs_review=True
- [Phase 02]: tenacity retry min wait 0.1s for testability; CIK stored stripped, padded at API boundary; EntityPublicFloat int(val*100) for cents
- [Phase 02]: CIK-based persistence (not ticker-based) -- CIK is the authoritative SEC identifier, tickers can change
- [Phase 02]: Each AI keyword searched separately in EFTS (not combined) to avoid 10K result cap per Pitfall 1
- [Phase 02]: SQLite JSONB-to-JSON type adapter pattern for unit test isolation without PostgreSQL dependency
- [Phase 02]: Lazy imports in CLI: heavy modules imported inside command functions to keep CLI startup fast
- [Phase 03]: Literal type constraint on FilingData.form_type for compile-time safety
- [Phase 03]: XBRL_TAG_GROUPS as module constant (not config) since tags are SEC standards, not user-configurable
- [Phase 03]: BigInteger for XBRLFact.value_cents to handle large monetary values in cents
- [Phase 03]: Idempotency via unique DB constraints: Filing by accession_no, XBRLFact by concept+period
- [Phase 03]: Pure function + class pattern for XBRL extraction: stateless logic in module-level functions, HTTP in class
- [Phase 03]: edgartools bracket notation for TenK/TenQ section access (Item 1, Item 1A, Item 7)
- [Phase 03]: SHA-256 content hash of concatenated section text for filing deduplication
- [Phase 03]: 500-char minimum for section validation with full_text_excerpt fallback (Pitfall 1)
- [Phase 03]: Inter-company rate limit delay of 1.0s in collect_all for SEC compliance
- [Phase 03]: Collector version string (0.3.0) in collection_metadata for audit traceability
- [Phase 04]: pythonpath=[src] added to pytest config to fix .pth file processing issue in stdlib venv worktree
- [Phase 04]: Frozen dataclass for scoring inputs (FilingForScoring): immutable, shared across SEC and compute scorers
- [Phase 04]: Two-tier keyword classification: vague buzzwords vs substantive terms with word-boundary regex
- [Phase 04]: Sigmoid normalization with clamp at +/-500 for overflow safety
- [Phase 04]: 70/30 CapEx/cloud-mention weighting for compute spending gap metric per D-05
- [Phase 04]: Cloud mention detection uses filing text sections (not transcripts) per Pitfall 6; transcripts deferred to Phase 7
- [Phase 04]: Signal version 0.4.0 for compute spending scorer matching phase numbering
- [Phase 04]: ScoringOrchestrator is the ONLY analysis module with DB access -- scorers remain pure functions
- [Phase 04]: Keyword counts shared between SEC and compute scorers via compute_keyword_counts_by_year for consistency
- [Phase 04]: Idempotent persistence via exists-check on (company_id, signal_type, as_of_date) before insert
- [Phase 05]: Lazy API key validation: PatentSearchClient accepts empty key at construction, raises on search (enables orchestrator skip)
- [Phase 05]: Cursor-based pagination via last patent_id, capped at 10 pages for safety
- [Phase 05]: Cross-assignee deduplication in-memory by patent_id before DB persistence
- [Phase 05]: Signal version 0.5.0 for patent gap scorer matching phase numbering
- [Phase 05]: Shared ai_keyword_counts reused across SEC, compute, and patent scorers (no recomputation)
- [Phase 05]: Patent factor clamped to 0.01 minimum to prevent division by zero in gap ratio
- [Phase 06-github-signal]: ML_FRAMEWORK_PATTERNS and ML_LANGUAGES as domain constants, GITHUB_SIGNAL_VERSION=0.6.0, idempotent daily collection via unique constraint
- [Phase 06-github-signal]: Lazy token validation for GitHubClient: accept empty at construction, raise on first API call (consistent with PatentSearchClient)
- [Phase 06-github-signal]: Fork filtering at client level in list_org_repos; raw content Accept header for direct file text retrieval
- [Phase 06-github-signal]: GitHubCollector follows PatentCollector pattern: same __init__, collect_for_company, collect_all API shape
- [Phase 06-github-signal]: GitHub max_date query for most-recent snapshot: aggregates only latest observed_date repos for scoring
- [Phase 06-github-signal]: AI claim intensity for GitHub scoring sourced from shared kw_by_year dict (scoring_year key)
- [Phase 07-earnings-call-signal]: torch pinned to 2.2.2 for macOS x86_64 compat; production will use >=2.5
- [Phase 07-earnings-call-signal]: EarningsVaguenessScoringConfig: buzzword_weight=0.70, sentiment_weight=0.30 with sum-to-1.0 validator
- [Phase 07-earnings-call-signal]: EarningsTranscript unique on (company_id, fiscal_year, fiscal_quarter) for idempotent collection
- [Phase 07-earnings-call-signal]: FinBERT top-label redistribution: remaining probability split equally across other two labels for aggregation
- [Phase 07-earnings-call-signal]: Lazy model loading: pipeline and tokenizer created on first analyze_text call, reused thereafter
- [Phase 07-earnings-call-signal]: transcript_text JSONB stores only string values; speakers dict in collection_metadata
- [Phase 07-earnings-call-signal]: EarningsClient tenacity retry on ConnectionError (3 attempts, 0.1-10s exponential backoff)
- [Phase 07-earnings-call-signal]: Default 8 quarters (2 years) of transcript history per company
- [Phase 07-earnings-call-signal]: ai_claim_intensity=None defaults to 0.5 (SEC data unavailable = assume claims present, score transcript alone)
- [Phase 07-earnings-call-signal]: Lazy FinBERTAnalyzer in orchestrator: model only loaded when earnings transcripts exist
- [Phase 08-job-posting-signal]: Test adjusted to 20 AI roles for low-score case: 10 roles at hiring_intensity=0.5 produces gap_ratio=1.0 (midpoint=50), not <40
- [Phase 08-job-posting-signal]: Default sites indeed+google (no LinkedIn due to rate-limit risk)
- [Phase 08-job-posting-signal]: Lifecycle tracking: stale postings deactivated by comparing last_seen < collection_date
- [Phase 08-job-posting-signal]: Ghost ratio uses configurable ghost_days_threshold (default 90); ai_claim_intensity defaults to 0.0 for job scoring
- [Phase 09]: SIGNAL_TYPE_TO_WEIGHT_KEY handles earnings_vagueness->earnings_call and job_mismatch->job_posting name mismatches
- [Phase 09]: CompanyScore uses frozen dataclass (not Pydantic) for immutable public API types
- [Phase 09]: signal_freshness populated lazily from SignalDetail.as_of_date aggregation per company
- [Phase 09]: Own-session pattern: auto-create session if not provided, close in finally block
- [Phase 10]: DataSourceStatus inherits from Base (not mixin) -- operational table like PipelineRun
- [Phase 10]: Pre-seeded 6 data sources with calibrated cadences (24h daily, 168h patents, 2160h earnings)
- [Phase 10]: Per-source error format: list of {stage, errors} dicts in JSONB for structured pipeline error tracking
- [Phase 10]: Correlation ID pattern: bind_contextvars at pipeline start, clear_contextvars at end to prevent leaking
- [Phase 10]: now_utc parameter over freezegun: freezegun hangs with SQLAlchemy func.now()/onupdate; explicit param is simpler
- [Phase 10]: Single-table SQLite fixture: create only DataSourceStatus table to avoid JSONB compilation errors
- [Phase 10]: Plain functions (not @task) for stages -- collectors already have tenacity retries
- [Phase 10]: Prefect @flow only on daily_pipeline_flow -- minimal Prefect surface area

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 5]: New PatentsView API at data.uspto.gov has no confirmed Python client library -- may need raw httpx calls. Needs investigation during Phase 5 planning.
- [Phase 7]: Free earnings call transcript source for mid-cap companies unconfirmed -- EarningsCall library may not cover target universe. Needs validation during Phase 7 planning.
- [Phase 8]: Ghost job posting rate (27-30%) can poison the highest-weighted signal. Lifecycle tracking strategy is theoretically sound but untested.

## Session Continuity

Last session: 2026-03-30T02:18:56.771Z
Stopped at: Completed 10-04-PLAN.md
Resume file: None
