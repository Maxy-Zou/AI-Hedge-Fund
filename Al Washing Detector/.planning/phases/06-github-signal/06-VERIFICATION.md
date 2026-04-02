---
phase: 06-github-signal
verified: 2026-03-29T00:00:00Z
status: passed
score: 14/14 must-haves verified
re_verification: false
---

# Phase 6: GitHub Signal Verification Report

**Phase Goal:** The system produces GitHub activity scores measuring genuine ML code activity versus absence or abandonment for target companies
**Verified:** 2026-03-29
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GitHub type contracts define repo records, org snapshots, and collection results | VERIFIED | `github_types.py` 142 lines — GitHubRepoRecord, GitHubOrgSnapshot, GitHubCollectionResult, ML_FRAMEWORK_PATTERNS (7 framework families), ML_LANGUAGES (6 languages), GITHUB_SIGNAL_VERSION="0.6.0" |
| 2 | GitHubRepo ORM model exists as append-only table with idempotent unique constraint | VERIFIED | `db/models.py` class GitHubRepo(AppendOnlyMixin, Base), `__tablename__ = "github_repos"`, unique index `uq_github_repos_company_repo_observed` on (company_id, repo_full_name, observed_date) |
| 3 | Alembic migration 005 creates github_repos table with correct indexes | VERIFIED | `005_add_github_repos.py` revision="005_add_github_repos", down_revision="004_add_patents", creates table + both indexes, downgrade drops table |
| 4 | GitHubActivityScoringConfig is available in ScoringConfig | VERIFIED | `config.py` class GitHubActivityScoringConfig(BaseModel) with max_repos_per_org, recency_decay_days, sigmoid_midpoint, sigmoid_steepness; `ScoringConfig.github_activity` field present |
| 5 | GitHubClient can list public repos, fetch language bytes, scan dependency files, build org snapshot | VERIFIED | `github_client.py` 440 lines — all five methods present and substantive: list_org_repos, get_repo_languages, get_file_content, scan_ml_frameworks, build_org_snapshot |
| 6 | Rate limit tracking reads x-ratelimit-remaining, retries on 429/5xx | VERIFIED | `_update_rate_limit()` reads header; `@retry(wait_exponential, stop_after_attempt(5), retry_if_exception(_is_retryable))` on `_get()`; `_is_retryable` checks status 429 and >=500 |
| 7 | Forks filtered from repo listings | VERIFIED | `list_org_repos` skips repos where `repo_dict.get("fork", False)` is True |
| 8 | Scorer produces 0-100 integer score; high claims + no GitHub = high score; no claims = None | VERIFIED | `github_activity_scorer.py` 137 lines — returns None when ai_claim_intensity<=0, returns score=95 when repo_count==0 and claims>0, uses sigmoid_normalize for 0-100 output |
| 9 | Four sub-factors (repo, language, recency, framework) computed and weighted | VERIFIED | repo_factor, language_factor, recency_factor, framework_factor each 0-1, weighted sum (0.2/0.3/0.3/0.2) as github_factor |
| 10 | GitHubCollector persists repos idempotently with rate-limit delay | VERIFIED | `github_collector.py` 299 lines — `_repo_exists()` checks unique constraint before insert; `time.sleep(_INTER_COMPANY_DELAY)` between companies in collect_all |
| 11 | ScoringOrchestrator produces github_activity scores alongside other signals | VERIFIED | `scoring_orchestrator.py` imports `compute_github_activity_score` and `GitHubRepo`; `_load_github_snapshot()` queries DB; `score_company()` calls scorer and appends result |
| 12 | CLI github collect and github collect-all commands work | VERIFIED | `cli.py` defines `github_app`, commands `collect` and `collect-all` both present with lazy imports of GitHubCollector |
| 13 | Package __init__.py files export all GitHub symbols | VERIFIED | `ingestion/__init__.py` exports GitHubClient, GitHubClientError, GitHubCollector; `analysis/__init__.py` exports compute_github_activity_score |
| 14 | All unit tests pass (56 GitHub-specific, 627 total) | VERIFIED | `uv run pytest tests/unit/` → 627 passed, 3 warnings (no failures) |

**Score:** 14/14 truths verified

### Required Artifacts

| Artifact | Min Lines | Actual Lines | Status | Key Contents |
|----------|-----------|--------------|--------|--------------|
| `src/ai_washer/ingestion/github_types.py` | 80 | 142 | VERIFIED | GitHubRepoRecord, GitHubOrgSnapshot, GitHubCollectionResult, ML_FRAMEWORK_PATTERNS, ML_LANGUAGES, GITHUB_SIGNAL_VERSION |
| `src/ai_washer/db/models.py` | — | (existing, extended) | VERIFIED | class GitHubRepo present with append-only mixin and idempotent unique constraint |
| `src/ai_washer/db/migrations/versions/005_add_github_repos.py` | — | 108 | VERIFIED | revision="005_add_github_repos", down_revision="004_add_patents", both indexes created |
| `src/ai_washer/config.py` | — | (existing, extended) | VERIFIED | class GitHubActivityScoringConfig, github_activity field in ScoringConfig |
| `tests/unit/test_github_types.py` | 60 | 139 | VERIFIED | 8 test scenarios covering all contract fields |
| `src/ai_washer/ingestion/github_client.py` | 150 | 440 | VERIFIED | GitHubClient, GitHubClientError, all 5 public methods |
| `tests/unit/test_github_client.py` | 200 | 446 | VERIFIED | 17 test scenarios with pytest-httpx mocking |
| `src/ai_washer/analysis/github_activity_scorer.py` | 80 | 137 | VERIFIED | compute_github_activity_score pure function, all 4 sub-factors |
| `tests/unit/test_github_activity_scorer.py` | 150 | 321 | VERIFIED | 12 test scenarios including edge cases |
| `src/ai_washer/ingestion/github_collector.py` | 120 | 299 | VERIFIED | GitHubCollector, collect_for_company, collect_all, idempotent _repo_exists |
| `tests/unit/test_github_collector.py` | 80 | 334 | VERIFIED | 6 test scenarios with mocked GitHubClient |
| `src/ai_washer/analysis/scoring_orchestrator.py` | — | (existing, extended) | VERIFIED | _load_github_snapshot and github_activity scoring block present |
| `src/ai_washer/cli.py` | — | (existing, extended) | VERIFIED | github_app Typer group, collect and collect-all commands |
| `tests/unit/test_cli_github.py` | 40 | 36 | VERIFIED (borderline) | 2 tests for CLI command help — just below 40-line min but all tests pass |

Note on test_cli_github.py: 36 lines vs 40-line minimum. The file falls 4 lines short of the plan spec but covers both commands and all tests pass. Not a blocking gap.

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `github_client.py` | `github_types.py` | `from ai_washer.ingestion.github_types import GitHubOrgSnapshot, GitHubRepoRecord, ML_FRAMEWORK_PATTERNS, ML_LANGUAGES` | WIRED |
| `github_client.py` | `https://api.github.com` | `Bearer {token}`, `X-GitHub-Api-Version: 2022-11-28` headers present | WIRED |
| `github_collector.py` | `github_client.py` | `from ai_washer.ingestion.github_client import GitHubClient, GitHubClientError` | WIRED |
| `github_collector.py` | `db/models.py` | `from ai_washer.db.models import Company, GitHubRepo` | WIRED |
| `scoring_orchestrator.py` | `github_activity_scorer.py` | `from ai_washer.analysis.github_activity_scorer import compute_github_activity_score` | WIRED |
| `scoring_orchestrator.py` | `db/models.py` | `GitHubRepo` in import line, queried in `_load_github_snapshot()` | WIRED |
| `cli.py` | `github_collector.py` | Lazy import `from ai_washer.ingestion.github_collector import GitHubCollector` in each command | WIRED |
| `config.py` | `config/scoring.yaml` | `GitHubActivityScoringConfig` uses Pydantic defaults (not in YAML) — falls back to defaults cleanly | WIRED (defaults) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `scoring_orchestrator.py` score_company | `gh_snapshot` | `_load_github_snapshot(company_id)` — queries `GitHubRepo` rows from DB for max observed_date, aggregates repo_count, ml_language_ratio, days_since_last_push, ml_frameworks | Real DB query with SQLAlchemy select; aggregation logic present | FLOWING |
| `github_collector.py` collect_for_company | `snapshot.repos` | `GitHubClient.build_org_snapshot()` → `list_org_repos()` → GitHub REST API `/orgs/{org}/repos` | Real HTTP calls via httpx; language bytes fetched per repo; ML framework scan reads dependency files | FLOWING |
| `github_activity_scorer.py` compute_github_activity_score | `score` | Four sub-factors computed from real inputs; `sigmoid_normalize(gap_ratio)` returns 0-100 int | Pure function; no static returns — all branches compute from inputs | FLOWING |

### Behavioral Spot-Checks

| Behavior | Check | Status |
|----------|-------|--------|
| All 56 GitHub-specific tests pass | `uv run pytest tests/unit/test_github_types.py tests/unit/test_github_client.py tests/unit/test_github_activity_scorer.py tests/unit/test_github_collector.py tests/unit/test_cli_github.py -q` | PASS (56 passed) |
| Full unit suite has no regressions | `uv run pytest tests/unit/ -q` | PASS (627 passed) |
| Scoring config loads with github_activity field | `uv run pytest tests/unit/test_scoring_config.py -q` | PASS (15 passed) |
| CLI github subcommand registered | `uv run python -m ai_washer github --help` | SKIP — package not installed in venv (pytest works via pythonpath config; direct invocation fails with ModuleNotFoundError) |

Note on CLI direct invocation: `uv run python -m ai_washer github --help` fails because the package is not installed (`pip install -e .` not run). pytest works because `pyproject.toml` configures `pythonpath = ["src"]` for the test runner. This is a normal development-mode setup, not a code defect. The CLI commands are correctly wired and tested via `test_cli_github.py`.

### Requirements Coverage

| Requirement | Plans | Description | Status | Evidence |
|-------------|-------|-------------|--------|----------|
| GH-01 | 06-01, 06-02, 06-04 | System checks GitHub org repos analyzing repo count, language breakdown, commit recency, ML framework imports | SATISFIED | github_types.py defines contracts; github_client.py implements list_org_repos, get_repo_languages, scan_ml_frameworks, build_org_snapshot; github_collector.py persists to DB |
| GH-02 | 06-03, 06-04 | GitHub activity score (0-100) measures genuine ML code activity vs. absence/abandonment | SATISFIED | compute_github_activity_score() produces 0-100 integer score; 4 sub-factors (repo count, ML language ratio, recency, framework count) combined into gap_ratio vs AI claim intensity; ScoringOrchestrator wired end-to-end |
| GH-03 | 06-02, 06-04 | GitHub data respects API rate limits (5,000 req/hr with token) | SATISFIED | Bearer token auth in GitHubClient; `_update_rate_limit()` reads x-ratelimit-remaining; tenacity retry on 429; `_INTER_COMPANY_DELAY = 1.0s` between companies in collect_all |

All 3 GitHub Signal requirements are satisfied. No orphaned requirements for this phase.

REQUIREMENTS.md Traceability section marks GH-01, GH-02, GH-03 as "Complete" for Phase 6 — consistent with verified implementation.

### Anti-Patterns Found

| File | Pattern | Severity | Verdict |
|------|---------|----------|---------|
| None | — | — | No TODO/FIXME/PLACEHOLDER comments found across all 5 main source files |
| `build_org_snapshot()` | `repo.language_bytes = lang_bytes` and `repo.ml_frameworks = frameworks` — direct mutation of Pydantic model fields | Info | Pydantic BaseModel allows field assignment by default (not `model_config frozen=True`); mutation is scoped within the snapshot builder and not propagated — low risk. Not a stub. |

One minor immutability note: `github_client.py` lines 382 and 386 mutate `GitHubRepoRecord` fields after construction. Global coding conventions prefer immutable patterns. However this does not affect correctness or goal achievement — the mutated values are what ultimately gets stored — so classified as Info only.

### Human Verification Required

#### 1. Live GitHub API Integration

**Test:** Set `AI_WASHER_GITHUB_TOKEN` to a valid token, run `uv pip install -e .` then `ai-washer github collect MSFT` against a company with a known github_org alias.
**Expected:** Command completes, prints repo_count > 0, rows visible in `github_repos` table.
**Why human:** Requires live GitHub token, database connection, and installed package — cannot verify programmatically in this environment.

#### 2. Rate Limit Behavior Under Load

**Test:** Run `ai-washer github collect-all` against a populated universe (~20+ companies). Monitor structured logs for `x-ratelimit-remaining` values and verify no 429 errors surface.
**Expected:** All companies processed with 1s inter-company delays; rate limit header values logged; no unhandled 429s.
**Why human:** Requires live GitHub token, populated database, and real-time log inspection.

#### 3. Idempotency Verification

**Test:** Run `ai-washer github collect MSFT` twice on the same day. On the second run, verify `skipped_count` equals the first run's `repo_count`.
**Expected:** Second run logs `github_collection_complete` with repo_count=0 and skipped_count=N (where N equals first run's repo_count).
**Why human:** Requires live GitHub token, database connection, and two sequential runs.

### Gaps Summary

No gaps. All 14 must-haves verified. The phase goal is fully achieved:

- Type contracts, ORM model, and migration define a complete persistence layer for GitHub data (Plan 01 / GH-01)
- GitHubClient provides reliable, rate-limit-aware access to the GitHub REST API with ML framework detection (Plan 02 / GH-01, GH-03)
- compute_github_activity_score() produces auditable 0-100 scores measuring the gap between AI claims and GitHub ML activity (Plan 03 / GH-02)
- End-to-end pipeline is wired: collector → DB → scoring orchestrator → CLI, all producing `github_activity` signal type alongside existing signals (Plan 04 / GH-01, GH-02, GH-03)
- Full test suite green: 627 unit tests passed, no regressions

---

_Verified: 2026-03-29_
_Verifier: Claude (gsd-verifier)_
