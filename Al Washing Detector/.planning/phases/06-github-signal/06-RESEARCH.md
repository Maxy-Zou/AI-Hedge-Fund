# Phase 6: GitHub Signal - Research

**Researched:** 2026-03-28
**Domain:** GitHub REST API, repository activity analysis, ML framework detection
**Confidence:** HIGH

## Summary

Phase 6 adds the GitHub activity signal to the AI Washing Detector. This signal measures whether target companies have genuine ML code activity on GitHub versus dormant repos or no GitHub presence at all -- contributing 10% weight to the composite AI washing risk score. The implementation follows well-established patterns from Phases 4 and 5: a typed client layer over httpx with tenacity retries, a collector orchestrator for DB persistence, a pure scoring function, and integration into the existing ScoringOrchestrator.

The GitHub REST API provides all data needed through three endpoint categories: (1) `GET /orgs/{org}/repos` to enumerate an org's public repositories with language and push timestamp metadata, (2) `GET /repos/{owner}/{repo}/languages` for byte-count language breakdowns, and (3) `GET /repos/{owner}/{repo}/contents/{path}` to fetch dependency files (requirements.txt, pyproject.toml, setup.py, setup.cfg) and scan for ML framework imports. The 5,000 req/hr authenticated rate limit is generous for the target universe of ~200 companies. The search/code API should be avoided due to its punitive 10 req/min rate limit.

**Primary recommendation:** Use httpx with tenacity (already in dependencies) to build a GitHubClient following the PatentSearchClient pattern, with token-based authentication, rate limit header tracking, and per-company repo enumeration + language/dependency analysis. No new dependencies required.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- discuss phase was skipped per user setting. All implementation choices at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion -- discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None -- discuss phase skipped. Refer to ROADMAP phase description and success criteria.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GH-01 | System checks GitHub organization repos for target companies, analyzing repo count, language breakdown, commit recency, and ML framework imports | GitHub REST API provides `/orgs/{org}/repos` (repo listing with pushed_at, language), `/repos/{owner}/{repo}/languages` (language bytes), and `/repos/{owner}/{repo}/contents/{path}` (dependency file scanning). Company-to-org mapping already exists via `Company.aliases["github_org"]` from Phase 2 entity resolution. |
| GH-02 | GitHub activity score (0-100) measures genuine ML code activity vs. absence/abandonment | Existing `sigmoid_normalize` and `SignalResult` types from analysis module support 0-100 scoring. Score combines four sub-factors: repo count, ML language ratio, commit recency, and ML framework imports. Pure function scorer following patent_gap_scorer.py pattern. |
| GH-03 | GitHub data respects API rate limits (5,000 req/hr with token) | `GITHUB_TOKEN` already defined in `AppSettings.github_token`. Use `x-ratelimit-remaining` response headers for proactive throttling. tenacity retry on 429/5xx. Budget: ~15-20 API calls per company (1 org repos listing + 1 language call per repo + 1 contents call per repo), so ~200 companies = ~4000 calls, well within 5,000/hr. |
</phase_requirements>

## Standard Stack

### Core (Already Installed)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| httpx | 0.28.1 | HTTP client for GitHub API calls | Already in pyproject.toml |
| tenacity | 9.1.4 | Retry logic with exponential backoff | Already in pyproject.toml |
| structlog | 25.5.0 | Structured logging | Already in pyproject.toml |
| pydantic | 2.12.5+ | Type contracts for GitHub data | Already in pyproject.toml |
| sqlalchemy | 2.0.48+ | ORM for github_repos table | Already in pyproject.toml |
| alembic | 1.18.4+ | Database migration for new table | Already in pyproject.toml |

### Testing (Already Installed)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| pytest | 9.0.2 | Test framework | Already installed |
| pytest-httpx | 0.36.0+ | Mock httpx requests | Already installed |
| freezegun | 1.5.5+ | Mock dates for recency tests | Already installed |

### New Dependencies
None required. All needed libraries are already in the project.

## Architecture Patterns

### Recommended Module Structure
```
src/ai_washer/
  ingestion/
    github_types.py          # Pydantic types: GitHubRepoRecord, GitHubOrgSnapshot, GitHubCollectionResult
    github_client.py         # GitHubClient: org repos, languages, dependency scanning
    github_collector.py      # GitHubCollector: orchestrates client + DB persistence
  analysis/
    github_activity_scorer.py  # Pure function: compute_github_activity_score()
  db/
    models.py                  # Add GitHubRepo model (append-only)
    migrations/versions/
      005_add_github_repos.py  # Alembic migration
  config.py                    # Add GitHubActivityScoringConfig
  cli.py                       # Add github_app Typer subcommand group
```

### Pattern 1: GitHub API Client (follows PatentSearchClient)

**What:** Typed httpx client with token authentication, rate limit tracking, and tenacity retries.
**When to use:** All GitHub API interactions.

```python
# Source: Established pattern from patent_client.py

class GitHubClientError(Exception):
    """Raised when the GitHub API client encounters an error."""

class GitHubClient:
    """Client for the GitHub REST API v3.

    Enumerates organization repos, fetches language breakdowns,
    and scans dependency files for ML framework imports.
    """

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.github.com",
        client: httpx.Client | None = None,
    ) -> None:
        # Lazy token validation (empty accepted at construction, raises on use)
        self._token = token
        self._base_url = base_url.rstrip("/")
        # Track rate limit from response headers
        self._rate_limit_remaining: int | None = None
        ...

    def list_org_repos(self, org: str) -> list[GitHubRepoRecord]:
        """GET /orgs/{org}/repos with pagination (100 per page)."""

    def get_repo_languages(self, owner: str, repo: str) -> dict[str, int]:
        """GET /repos/{owner}/{repo}/languages -> {lang: bytes}."""

    def get_file_content(self, owner: str, repo: str, path: str) -> str | None:
        """GET /repos/{owner}/{repo}/contents/{path} with raw Accept header.
        Returns None if 404 (file not found)."""

    def scan_ml_frameworks(self, owner: str, repo: str) -> list[str]:
        """Check requirements.txt, pyproject.toml, setup.py, setup.cfg
        for ML framework imports. Returns list of detected frameworks."""
```

### Pattern 2: GitHub Collector (follows PatentCollector)

**What:** Orchestrator that reads Company.aliases["github_org"], calls GitHubClient, persists snapshots to DB.
**When to use:** Data collection from GitHub for each company.

```python
class GitHubCollector:
    """Orchestrates GitHub data collection and DB persistence.

    For each company with a github_org alias:
    1. List all public repos for the org
    2. Get language breakdown for each repo
    3. Scan dependency files for ML frameworks
    4. Persist snapshot to github_repos table
    """

    def collect_for_company(
        self,
        company_id: uuid.UUID,
        github_org: str,
        collection_date: date | None = None,
    ) -> GitHubCollectionResult: ...

    def collect_all(
        self,
        collection_date: date | None = None,
    ) -> list[GitHubCollectionResult]: ...
```

### Pattern 3: Pure Scoring Function (follows patent_gap_scorer)

**What:** Stateless function that takes typed immutable inputs and returns SignalResult.
**When to use:** Scoring logic. The ScoringOrchestrator calls this function.

```python
def compute_github_activity_score(
    repo_count: int,
    ml_language_ratio: float,        # 0.0-1.0: bytes of ML languages / total bytes
    days_since_last_push: int | None,  # None = no repos found
    ml_frameworks_found: list[str],  # e.g., ["tensorflow", "pytorch"]
    ai_claim_intensity: float,       # from shared keyword counts
    scoring_year: int,
    sigmoid_midpoint: float = 1.0,
    sigmoid_steepness: float = 2.0,
) -> SignalResult | None:
    """Compute GitHub activity score.

    Score = sigmoid(gap_ratio) where gap_ratio = claim_factor / github_factor.
    High claims + low GitHub activity = high score (washing).
    Low claims + high GitHub activity = low score (genuine).

    Returns None if no github_org mapped (no data to score).
    """
```

### Pattern 4: DB Model (follows Patent model)

**What:** Append-only table for GitHub repo snapshots.
**When to use:** Persisting collected GitHub data per company per collection run.

```python
class GitHubRepo(AppendOnlyMixin, Base):
    """Append-only GitHub repository snapshot.

    One row per repo per collection run. Stores repo metadata,
    language breakdown, and ML framework detection results.
    Unique constraint on (company_id, repo_full_name, observed_date)
    for idempotent collection.
    """
    __tablename__ = "github_repos"

    company_id: Mapped[uuid.UUID]  # FK to companies
    repo_full_name: Mapped[str]    # "org/repo-name"
    repo_name: Mapped[str]         # "repo-name"
    primary_language: Mapped[str | None]
    language_bytes: Mapped[dict]   # JSONB: {"Python": 50000, "JavaScript": 20000}
    pushed_at: Mapped[datetime | None]
    is_fork: Mapped[bool]
    is_archived: Mapped[bool]
    stargazers_count: Mapped[int]
    ml_frameworks: Mapped[list]    # JSONB: ["tensorflow", "pytorch"]
    collection_metadata: Mapped[dict]  # JSONB
```

### Anti-Patterns to Avoid

- **Using the Search/Code API for ML framework detection:** The code search API has a punitive 10 req/min rate limit. Instead, use the contents API to fetch specific dependency files (requirements.txt, pyproject.toml) at known paths. This is 1-4 API calls per repo vs. an expensive search query.
- **Cloning repositories:** Never clone or download repo archives. The contents API provides targeted file access.
- **Analyzing private repos:** Only public repos are relevant for this signal. Companies that hide their AI work in private repos still get flagged as "no GitHub presence."
- **Treating forks as original work:** Filter out forked repos (`is_fork=True`) from the activity calculation. Forks inflate repo count without representing genuine work.
- **Treating archived repos as active:** Archived repos should count toward "historical presence" but not "active development."

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP rate limiting | Custom token bucket | tenacity + x-ratelimit-remaining headers | GitHub provides remaining-count in headers; tenacity retries on 429 |
| Base64 file decoding | Custom decoder | Accept: application/vnd.github.raw+json | Raw content header avoids base64 entirely |
| Repo pagination | Custom page counter | Link header parsing or per_page=100 + page iteration | GitHub standard pagination with known total |
| ML framework detection | NLP/regex on all code | Scan 4 known dependency files | requirements.txt, pyproject.toml, setup.py, setup.cfg cover 95%+ of Python projects |
| Score normalization | Custom 0-100 mapping | Existing sigmoid_normalize() | Already used by SEC, compute, and patent scorers |

**Key insight:** The GitHub signal is data-poor compared to SEC filings -- it produces a small number of discrete signals (repo count, language ratio, recency, framework list) rather than dense text. The scoring function should be simple and direct rather than attempting complex NLP.

## Common Pitfalls

### Pitfall 1: GitHub API 202 Responses on Statistics Endpoints
**What goes wrong:** The `/repos/{owner}/{repo}/stats/*` endpoints return HTTP 202 (Accepted) the first time they are called, meaning the data is being computed and is not yet available.
**Why it happens:** GitHub computes statistics on-demand and caches them. First request triggers computation.
**How to avoid:** Do NOT use the statistics endpoints. The data needed (repo count, language, push date, dependencies) is all available from the repos listing endpoint and contents API, which return 200 immediately.
**Warning signs:** Getting 202 responses when you expected data.

### Pitfall 2: Companies Without GitHub Org Mapping
**What goes wrong:** Not all companies in the target universe will have a `github_org` in their aliases. If the scorer crashes on None, it breaks the pipeline.
**Why it happens:** Entity resolution (Phase 2) uses exact first-word matching for GitHub orgs, which is conservative. Many mid-cap companies do not have obvious GitHub presences.
**How to avoid:** The scorer must return None (insufficient data) when no github_org exists, matching the existing pattern where patent scorer returns None when no API key is set. The ScoringOrchestrator already handles None returns with "signal_skipped" logging.
**Warning signs:** Crashes during score_all() for companies without github_org.

### Pitfall 3: Rate Limit Exhaustion Across Companies
**What goes wrong:** With ~200 companies, each needing ~15-20 API calls, the collection could approach the 5,000/hr limit if repos per org are large.
**Why it happens:** Some orgs (e.g., Google, Microsoft) have thousands of public repos. Fetching languages for all of them would blow the budget.
**How to avoid:** (1) Cap repos analyzed per org at 100 (sorted by pushed_at desc, most recent first). (2) Track x-ratelimit-remaining header and pause/slow when below a threshold (e.g., 500 remaining). (3) Only fetch languages for repos that have been pushed to in the last 2 years.
**Warning signs:** x-ratelimit-remaining dropping below 500 during collection.

### Pitfall 4: ML Framework Detection False Positives
**What goes wrong:** A requirements.txt containing "tensorflow" might be a tutorial fork, not production ML code.
**Why it happens:** Companies fork popular ML repos or have demo/tutorial repos.
**How to avoid:** (1) Exclude forked repos. (2) Weight framework detection by repo size/activity -- a 10-star repo with 1 commit should count less than a 100-star repo with active commits. (3) Record framework detections per-repo in evidence for auditability.
**Warning signs:** High ML framework counts from companies with no real ML activity.

### Pitfall 5: Confusing Organization Visibility with Absence
**What goes wrong:** Some companies use GitHub for open-source projects but keep proprietary ML code private. Scoring them as "no GitHub presence" is misleading.
**Why it happens:** The API only sees public repos.
**How to avoid:** The score measures *public* GitHub ML activity, which is a valid signal for AI washing detection. Companies genuinely investing in AI often have open-source contributions, research repos, or framework integrations visible publicly. Document this limitation in evidence. The 10% composite weight appropriately limits its influence.
**Warning signs:** Known AI-active companies scoring very high on this signal.

### Pitfall 6: Dependency File Path Variations
**What goes wrong:** Not finding ML frameworks because the dependency file is in a subdirectory (e.g., `ml/requirements.txt`) or uses a non-standard name.
**Why it happens:** Monorepos and multi-project repos nest dependency files.
**How to avoid:** Check root-level dependency files only: `requirements.txt`, `pyproject.toml`, `setup.py`, `setup.cfg`. Root-level is a reasonable 80/20 heuristic. Scanning every subdirectory would multiply API calls.
**Warning signs:** Low ML framework detection rates despite known ML repos.

## Code Examples

### GitHub API Authentication and Rate Limit Tracking

```python
# Source: GitHub REST API docs (docs.github.com/en/rest)

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False

class GitHubClient:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self._token = token
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.Client(
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            self._owns_client = True
        self._rate_limit_remaining: int | None = None

    def _update_rate_limit(self, response: httpx.Response) -> None:
        remaining = response.headers.get("x-ratelimit-remaining")
        if remaining is not None:
            self._rate_limit_remaining = int(remaining)

    @retry(
        wait=wait_exponential(min=0.1, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        response = self._client.get(f"{self._base_url}{path}", params=params)
        self._update_rate_limit(response)
        response.raise_for_status()
        return response
```

### Listing Organization Repos (Paginated)

```python
# Source: docs.github.com/en/rest/repos/repos

def list_org_repos(self, org: str, max_repos: int = 100) -> list[GitHubRepoRecord]:
    """Fetch public repos for an org, sorted by most recently pushed."""
    all_repos: list[GitHubRepoRecord] = []
    page = 1
    per_page = min(100, max_repos)

    while len(all_repos) < max_repos:
        response = self._get(
            f"/orgs/{org}/repos",
            params={
                "type": "public",
                "sort": "pushed",
                "direction": "desc",
                "per_page": per_page,
                "page": page,
            },
        )
        repos_data = response.json()
        if not repos_data:
            break

        for repo_dict in repos_data:
            if repo_dict.get("fork", False):
                continue  # Skip forks
            record = self._parse_repo(repo_dict)
            if record is not None:
                all_repos.append(record)

        if len(repos_data) < per_page:
            break
        page += 1

    return all_repos[:max_repos]
```

### ML Framework Detection from Dependency Files

```python
# Source: Common Python packaging conventions

# Dependency files to check (root-level only)
_DEPENDENCY_FILES = ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg")

# ML frameworks to detect (package names as they appear in pip/pyproject)
ML_FRAMEWORK_PATTERNS: dict[str, list[str]] = {
    "tensorflow": ["tensorflow", "tensorflow-gpu", "tf-nightly", "keras"],
    "pytorch": ["torch", "torchvision", "torchaudio", "pytorch-lightning"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "jax": ["jax", "jaxlib", "flax"],
    "huggingface": ["transformers", "datasets", "tokenizers"],
    "xgboost": ["xgboost"],
    "lightgbm": ["lightgbm"],
}

def scan_ml_frameworks(self, owner: str, repo: str) -> list[str]:
    """Check dependency files for ML framework imports."""
    detected: set[str] = set()
    for dep_file in _DEPENDENCY_FILES:
        content = self.get_file_content(owner, repo, dep_file)
        if content is None:
            continue
        content_lower = content.lower()
        for framework, patterns in ML_FRAMEWORK_PATTERNS.items():
            for pattern in patterns:
                if pattern in content_lower:
                    detected.add(framework)
                    break
    return sorted(detected)
```

### Scoring Function Structure

```python
# Source: Follows patent_gap_scorer.py pattern

_SIGNAL_VERSION = "0.6.0"

def compute_github_activity_score(
    repo_count: int,
    ml_language_ratio: float,
    days_since_last_push: int | None,
    ml_frameworks_found: list[str],
    ai_claim_intensity: float,
    scoring_year: int,
    sigmoid_midpoint: float = 1.0,
    sigmoid_steepness: float = 2.0,
) -> SignalResult | None:
    """Score GitHub activity relative to AI claims.

    github_factor components:
    - repo_factor: normalized repo count (0-1)
    - language_factor: ML language ratio (0-1)
    - recency_factor: decay based on days since last push (0-1)
    - framework_factor: normalized count of ML frameworks detected (0-1)

    gap_ratio = claim_factor / github_factor
    score = sigmoid(gap_ratio)
    """
    if repo_count == 0 and days_since_last_push is None:
        # No GitHub presence at all
        if ai_claim_intensity > 0:
            # Making AI claims with zero GitHub presence = max score
            return SignalResult(
                signal_type="github_activity",
                score=95,  # Near-max, not 100 (allow some uncertainty)
                evidence={...},
            )
        return None  # No claims, no GitHub = nothing to score
    ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| GitHub API v3 unversioned | API version header `X-GitHub-Api-Version: 2022-11-28` | 2022 | Must include version header for stable responses |
| Code search via `/search/code` | Contents API for specific files | Always true | Code search has 10 req/min limit; contents API uses primary rate limit |
| unauthenticated access (60 req/hr) | Token auth (5,000 req/hr) | Always true | Token already in AppSettings.github_token |

**Deprecated/outdated:**
- GitHub Search API v3 sort/order params for code search: "closing down" per current docs. Use contents API instead.
- GraphQL API: More efficient for complex queries but adds dependency (graphql-core) and complexity. REST API sufficient for this use case.

## Open Questions

1. **Optimal repo cap per organization**
   - What we know: Some orgs have 1000+ public repos. Fetching languages for all is expensive.
   - What's unclear: What's the right cap? 100 sorted by pushed_at seems reasonable.
   - Recommendation: Start with 100 repos max per org, sorted by most recently pushed. This captures active repos and stays within rate limits. Add config parameter for tuning.

2. **GitHub org mapping coverage**
   - What we know: Phase 2 entity resolution maps github_org via exact first-word match, which is conservative.
   - What's unclear: What percentage of target universe companies will have github_org mapped?
   - Recommendation: The scorer should gracefully return None for unmapped companies. This is consistent with how the patent scorer handles missing API keys. Future improvement could add manual org mapping overrides.

3. **ML language classification**
   - What we know: Python is the dominant ML language, but R, Julia, C++, and Rust are also used.
   - What's unclear: What's the right ML language list?
   - Recommendation: Use Python, R, Julia, C++, Rust, and Jupyter Notebook as ML-adjacent languages. Weight Python + Jupyter highest. Store as configurable constant, not in YAML config (these are domain facts, not user-tunable thresholds).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| httpx | GitHub API calls | Yes | 0.28.1 | -- |
| tenacity | Retry logic | Yes | 9.1.4 | -- |
| structlog | Logging | Yes | 25.5.0 | -- |
| pydantic | Type contracts | Yes | 2.12.5+ | -- |
| pytest-httpx | HTTP mocking | Yes | 0.36.0+ | -- |
| freezegun | Date mocking | Yes | 1.5.5+ | -- |
| PostgreSQL | Data persistence | Yes (per project setup) | 16+ | -- |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

All required packages are already installed in the project's virtual environment.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/python -m pytest tests/unit/ -x -q` |
| Full suite command | `.venv/bin/python -m pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GH-01 | GitHub client fetches org repos, languages, dependency files; collector persists snapshots | unit | `.venv/bin/python -m pytest tests/unit/test_github_client.py tests/unit/test_github_collector.py -x` | No -- Wave 0 |
| GH-02 | Scorer produces 0-100 score distinguishing active ML, dormant, no presence | unit | `.venv/bin/python -m pytest tests/unit/test_github_activity_scorer.py -x` | No -- Wave 0 |
| GH-03 | Rate limit respect: retry on 429, track remaining header | unit | `.venv/bin/python -m pytest tests/unit/test_github_client.py::TestRateLimiting -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/unit/ -x -q`
- **Per wave merge:** `.venv/bin/python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_github_types.py` -- covers GH-01 (type contracts)
- [ ] `tests/unit/test_github_client.py` -- covers GH-01, GH-03 (API client)
- [ ] `tests/unit/test_github_collector.py` -- covers GH-01 (collector orchestrator)
- [ ] `tests/unit/test_github_activity_scorer.py` -- covers GH-02 (pure scoring function)
- [ ] `tests/unit/test_cli_github.py` -- covers CLI integration

## Project Constraints (from CLAUDE.md)

**From project CLAUDE.md and parent CLAUDE.md:**
- Python 3.11+ (running 3.12.11)
- All API keys/secrets in `.env` (GITHUB_TOKEN already defined in AppSettings)
- Immutable data patterns -- return new objects, never mutate
- Validate all external data at ingestion boundaries (Pydantic models for API responses)
- Financial data must be immutable -- append new snapshots, never overwrite
- All data fetchers must implement retry logic with exponential backoff
- Rate limit all API calls (GitHub: 5,000 req/hr with token)
- File organization: many small files, 200-400 lines typical, 800 max
- Functions under 50 lines
- Error handling at every level
- Signal version 0.6.0 (matching phase numbering convention)

**From global rules:**
- TDD approach: write tests first
- 80%+ test coverage target
- Conventional commits format
- No hardcoded secrets

## Sources

### Primary (HIGH confidence)
- [GitHub REST API - Rate Limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) -- 5,000 req/hr authenticated, 10 req/min for search
- [GitHub REST API - Repos](https://docs.github.com/en/rest/repos/repos) -- /orgs/{org}/repos endpoint, response schema
- [GitHub REST API - Repository Contents](https://docs.github.com/en/rest/repos/contents) -- /repos/{owner}/{repo}/contents/{path} for file access
- [GitHub REST API - Repository Statistics](https://docs.github.com/en/rest/metrics/statistics) -- Stats endpoints return 202 initially (avoid using)
- Existing codebase: PatentSearchClient, PatentCollector, patent_gap_scorer patterns (HIGH confidence -- direct source code inspection)

### Secondary (MEDIUM confidence)
- GitHub API Version header `X-GitHub-Api-Version: 2022-11-28` -- referenced in current docs
- ML framework package names -- verified against PyPI (tensorflow, torch, scikit-learn, etc.)

### Tertiary (LOW confidence)
- None. All findings verified against official documentation or existing codebase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All dependencies already installed, no new packages needed
- Architecture: HIGH -- Follows established patterns from Phases 4-5, direct code inspection
- Pitfalls: HIGH -- GitHub API behavior well-documented, rate limits clearly specified
- Scoring logic: MEDIUM -- The specific sub-factor weights (repo count, language ratio, recency, frameworks) are reasonable but may need tuning after initial data collection

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (GitHub API is stable; rate limits and endpoints rarely change)
