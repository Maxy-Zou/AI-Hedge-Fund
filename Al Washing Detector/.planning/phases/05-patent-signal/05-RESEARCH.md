# Phase 5: Patent Signal - Research

**Researched:** 2026-03-28
**Domain:** USPTO Patent Data Ingestion, CPC Classification, Patent Gap Scoring
**Confidence:** MEDIUM (API access uncertainty is the primary risk)

## Summary

Phase 5 implements the patent gap signal: querying USPTO patent data for AI-related patents (CPC codes G06N and G06F18) by company, matching patent assignees to the entity resolution table, and producing a 0-100 patent gap score comparing patent filing trend to AI claim intensity from SEC filings.

The primary technical challenge is API access. The PatentSearch API at `search.patentsview.org/api/v1/` requires an API key, and new key grants have been temporarily suspended as PatentsView migrates to the USPTO Open Data Portal (data.uspto.gov). The migration began March 20, 2026 and some services are temporarily paused. The implementation MUST account for this uncertainty by designing a clean client abstraction that can switch between the PatentSearch API (primary) and bulk data download (fallback) without affecting scoring logic.

The scoring architecture follows the established pattern from Phase 4: a pure-function scorer (no DB access) consuming typed immutable inputs, an orchestrator extension that bridges DB reads/writes, and a new DB model for patent data. The entity resolution challenge of mapping patent assignee names to companies is partially solved -- Company.aliases already contains a `patent_assignee` list field populated by the entity resolver using fuzzy matching.

**Primary recommendation:** Build a PatentSearch API client using raw httpx (no Python wrapper library is reliable enough), with structured fallback to bulk data download, and integrate into the existing scoring orchestrator pattern.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- discuss phase was skipped per user setting (skip_discuss: true). All implementation choices are at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None -- discuss phase skipped.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PAT-01 | System queries USPTO PatentsView API (data.uspto.gov -- new endpoint) for AI-related patents by company using CPC codes G06N and G06F18 | PatentSearch API documentation mapped; CPC code hierarchy documented; assignee field names identified; httpx client pattern from existing codebase applies |
| PAT-02 | Patent gap score (0-100) measures AI patent filing trend against AI claim intensity from filings | Existing growth.py (CAGR), normalization.py (sigmoid), and keyword counting from Phase 4 provide the claim intensity side; patent count trend is new |
| PAT-03 | Patent data refreshes weekly (patents move slowly) | Incremental collection via last-collected-date tracking; append-only Patent model with unique constraint for idempotency |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Language:** Python 3.11+ (project uses 3.12)
- **HTTP client:** httpx (already a dependency, sync+async)
- **Testing:** pytest with 80%+ coverage; TDD workflow
- **Immutability:** Never mutate existing data; return new objects
- **Financial data:** Append-only; never overwrite historical records
- **Input validation:** Pydantic schemas at system boundaries
- **Error handling:** Explicit at every level; never silently swallow
- **Retry logic:** tenacity with exponential backoff on all external API calls
- **Logging:** structlog for structured JSON logging
- **File organization:** Many small files, 200-400 lines typical, 800 max
- **Database:** PostgreSQL + SQLAlchemy 2.0; Alembic migrations
- **Scoring config:** Externalized in config/scoring.yaml
- **Git commits:** Conventional commits format; no co-author attribution

## Standard Stack

### Core (already installed -- no new dependencies required)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | 0.28.1 | HTTP client for PatentSearch API | Already in pyproject.toml; sync client for API calls, consistent with existing ingestion pattern |
| tenacity | 9.1.4 | Retry with exponential backoff | Already in pyproject.toml; handles API rate limits (45 req/min) and transient failures |
| pydantic | 2.12.5 | Request/response validation | Already in pyproject.toml; validates patent data at ingestion boundary |
| structlog | 25.5.0 | Structured logging | Already in pyproject.toml; JSON logs with correlation context |
| rapidfuzz | 3.14.3 | Fuzzy name matching for assignee resolution | Already in pyproject.toml; entity resolver already uses this |
| sqlalchemy | 2.0.48 | ORM for Patent model | Already in pyproject.toml; append-only pattern established |

### Supporting (no new packages needed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| alembic | 1.18.4 | Schema migration for new patent table | Migration 004 for patents table |
| pytest-httpx | 0.36.0 | Mock httpx calls in tests | Already in dev deps; mock PatentSearch API responses |
| freezegun | 1.5.5 | Time mocking for weekly refresh logic | Already in dev deps; test collection cadence |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw httpx | pyUSPTO library | pyUSPTO (v0.2.1) wraps USPTO ODP but does NOT wrap PatentSearch API. Different APIs. pyUSPTO.PatentDataClient is for patent file wrapper search, not PatentsView. |
| Raw httpx | patent_client library | patent_client wraps USPTO ODP only (applications filed after 2001). Does not wrap the PatentSearch API which covers granted patents since 1976. |
| PatentSearch API | PatentsView bulk download | Bulk data (TSV files) is a viable fallback but requires downloading multi-GB files. Good as Plan B if API key cannot be obtained. |
| PatentSearch API | Legacy PatentsView API (api.patentsview.org) | Discontinued May 2025. The DEV.to article claiming "no API key required" references this dead endpoint. |

**Installation:** No new packages needed. All dependencies already in pyproject.toml.

## Architecture Patterns

### Recommended Project Structure
```
src/ai_washer/
  ingestion/
    patent_client.py        # PatentSearch API client (httpx)
    patent_types.py         # Pydantic schemas for patent data
  analysis/
    patent_gap_scorer.py    # Pure scoring function (no DB)
    types.py                # Extended with PatentForScoring dataclass
    scoring_orchestrator.py # Extended to include patent signal
  config.py                 # Extended with PatentGapScoringConfig
  db/
    models.py               # Extended with Patent model
    migrations/versions/
      004_add_patent_table.py
tests/
  unit/
    test_patent_client.py
    test_patent_types.py
    test_patent_gap_scorer.py
  integration/
    test_patent_signal_persistence.py (extend existing)
```

### Pattern 1: Pure Scorer + Orchestrator Bridge
**What:** Scoring logic is a pure function; the orchestrator is the ONLY module with DB access.
**When to use:** Every signal scorer follows this pattern (established in Phase 4).
**Example:**
```python
# Pure function -- no DB, no side effects
def compute_patent_gap_score(
    patent_counts_by_year: dict[int, int],
    ai_claim_intensity_by_year: dict[int, float],
    scoring_year: int,
    window_years: int = 3,
    sigmoid_midpoint: float = 1.0,
    sigmoid_steepness: float = 2.0,
) -> SignalResult | None:
    """Compare patent filing trend to AI claim intensity trend."""
    ...
```

### Pattern 2: Typed Immutable Input
**What:** Frozen dataclass for scorer inputs, matching Phase 4's FilingForScoring pattern.
**When to use:** Data flowing from DB to scorer.
**Example:**
```python
@dataclass(frozen=True)
class PatentForScoring:
    """Immutable patent record for scoring."""
    patent_id: str
    grant_date: date
    cpc_codes: tuple[str, ...]  # Tuple, not list, for immutability
    assignee_organization: str
```

### Pattern 3: Idempotent Collection with Unique Constraint
**What:** DB unique constraint on (company_id, patent_id) prevents duplicate storage; collector checks before insert.
**When to use:** All data collection (established in Phase 3 with accession_no for filings).
**Example:**
```python
# In Patent model
__table_args__ = (
    Index(
        "uq_patents_company_patent_id",
        "company_id",
        "patent_id",
        unique=True,
    ),
)
```

### Pattern 4: Client Abstraction for API Uncertainty
**What:** PatentClient class encapsulates all API interaction behind a clean interface, making it possible to swap implementations (API vs bulk download) without changing scoring logic.
**When to use:** When the external data source has availability uncertainty.
**Example:**
```python
class PatentSearchClient:
    """Client for the PatentsView PatentSearch API."""

    BASE_URL = "https://search.patentsview.org/api/v1"

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=30.0)

    def search_patents_by_assignee_and_cpc(
        self,
        assignee_name: str,
        cpc_prefixes: tuple[str, ...] = ("G06N", "G06F18"),
        after_date: date | None = None,
    ) -> list[PatentRecord]:
        """Search for AI-related patents by assignee."""
        ...
```

### Anti-Patterns to Avoid
- **Coupling scorer to API client:** The scorer must NEVER import or call the API client. It receives typed data only.
- **Mutating patent records:** Patents are append-only. Never update existing patent rows.
- **Using legacy PatentsView API:** api.patentsview.org was discontinued May 2025.
- **Hardcoding CPC codes:** Put CPC codes in config, not in scorer logic.
- **Skipping assignee normalization:** Patent assignee names vary wildly (e.g., "NOKIA" has 89 variations in USPTO data). Always normalize before matching.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Company name fuzzy matching | Custom string comparison | rapidfuzz (already imported) + existing EntityResolver | Handles legal suffix variations, case, punctuation automatically |
| CAGR computation | Custom growth formula | growth.py:compute_cagr (Phase 4) | Already tested, handles edge cases (zero start, negative values) |
| Sigmoid normalization | Custom score mapping | normalization.py:sigmoid_normalize (Phase 4) | Consistent with all other signal scores |
| HTTP retry logic | Custom retry loops | tenacity decorators | Handles 429 rate limits, exponential backoff, jitter |
| API response pagination | Manual page tracking | Cursor-based pagination helper | PatentSearch API uses cursor-based "after" parameter |

**Key insight:** Phase 5 reuses nearly all building blocks from Phases 2-4. The only genuinely new code is: (1) the PatentSearch API client, (2) the Patent DB model, and (3) the patent gap scoring formula. Everything else (entity matching, growth computation, sigmoid normalization, orchestrator pattern, CLI integration) is adaptation of existing code.

## Common Pitfalls

### Pitfall 1: PatentSearch API Key Unavailability
**What goes wrong:** New API key grants are temporarily suspended (as of March 2026) due to data.uspto.gov migration. You cannot get an API key to call the PatentSearch API.
**Why it happens:** PatentsView migrated to USPTO Open Data Portal on March 20, 2026. Services are temporarily paused.
**How to avoid:** Design the patent client with a clean abstraction layer. Implement the PatentSearch API client as the primary path but have an env var `PATENTSVIEW_API_KEY` that, when absent, triggers a clear error message pointing the user to the key request page. Add a `PATENT_DATA_SOURCE` config option (`api` vs `bulk`) for future fallback.
**Warning signs:** HTTP 401/403 responses from the API; API key request page returns "temporarily suspended."

### Pitfall 2: Patent Assignee Name Mismatch
**What goes wrong:** Patent assignees are registered under legal entity names that differ from SEC filing names (e.g., "ALPHABET INC" in SEC vs "GOOGLE LLC" as patent assignee).
**Why it happens:** Companies file patents through subsidiaries, have name changes, or use different legal entities. The USPTO confirmed "NOKIA" appears as 89 different assignee name variations.
**How to avoid:** Use the existing `Company.aliases.patent_assignee` field populated by the EntityResolver. When searching patents, try ALL patent_assignee aliases for a company, not just the SEC name. The EntityResolver already uses rapidfuzz fuzzy matching for this field.
**Warning signs:** Zero patents returned for a company known to have AI patents.

### Pitfall 3: CPC Code Hierarchy Confusion
**What goes wrong:** Searching for exact CPC code "G06N" misses patents classified under subcodes like "G06N3/08" (neural network learning methods).
**Why it happens:** CPC codes are hierarchical. G06N is a class, G06N3 is a subclass, G06N3/08 is a group. The API's `_begins` operator must be used to match all subcodes.
**How to avoid:** Use `_begins` operator in PatentSearch API queries: `{"_begins":{"cpc_group_id":"G06N"}}`. This matches G06N, G06N1/00, G06N3/08, etc. Similarly for G06F18.
**Warning signs:** Very low patent counts for companies with known AI patent portfolios.

### Pitfall 4: Field Name Changes After API Migration
**What goes wrong:** Code uses old field names from the legacy API that don't exist in the PatentSearch API.
**Why it happens:** The PatentSearch API renamed fields: `patent_number` -> `patent_id`, endpoints changed from plural to singular (`patents` -> `patent`), `cpc_subsections` -> `cpc_group`.
**How to avoid:** Use ONLY PatentSearch API field names confirmed from the rOpenSci March 2026 breaking release analysis: `patent_id`, `patent_date`, `patent_title`, `assignee_organization`, `cpc_group_id`, `cpc_class_id`.
**Warning signs:** HTTP 400 "unknown field" errors from the API.

### Pitfall 5: Rate Limit Exhaustion
**What goes wrong:** Exceeding 45 requests/minute causes HTTP 429 responses and temporary lockout.
**Why it happens:** Each company may require multiple API calls (multiple assignee name variations, pagination for large patent portfolios).
**How to avoid:** Use tenacity with `wait_exponential` and honor the `Retry-After` response header. Budget approximately 30 req/min to stay under the limit with margin. Process companies sequentially, not in parallel.
**Warning signs:** 429 responses; `Retry-After` header in response.

### Pitfall 6: Scoring Window Misalignment
**What goes wrong:** Patent filing trend uses grant_date years, but AI claim intensity uses period_of_report years. If the windows don't overlap, the gap score is meaningless.
**Why it happens:** Patent grants lag filings by 2-4 years. A patent filed in 2022 may be granted in 2025. Using grant_date directly would misalign with the SEC filing claim window.
**How to avoid:** Use `patent_date` (grant date) for counting purposes, but ensure the scoring window (default 3 years) looks at the same calendar years for both patent counts and keyword intensity. The scoring function should take both series aligned by calendar year.
**Warning signs:** Scores that don't correlate with known AI investment levels.

### Pitfall 7: Incremental Collection Logic
**What goes wrong:** Weekly refresh re-fetches ALL patents for ALL companies, wasting API quota and time.
**Why it happens:** No tracking of last successful collection date per company.
**How to avoid:** Store `last_patent_collected_date` per company (or derive from MAX(patent_date) in the patents table). On weekly refresh, only query patents with `patent_date` after this date. The unique constraint on (company_id, patent_id) provides idempotency as a safety net.
**Warning signs:** Collection takes hours instead of minutes; duplicate patent rows (caught by unique constraint).

## Code Examples

### PatentSearch API Query Structure
```python
# Source: search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/
# Confirmed from rOpenSci breaking release (March 2026)

import json
import httpx

BASE_URL = "https://search.patentsview.org/api/v1"

def search_ai_patents_by_assignee(
    client: httpx.Client,
    api_key: str,
    assignee_name: str,
    after_date: str | None = None,
) -> dict:
    """Search for AI patents by assignee organization name."""
    # Build query: assignee name AND (G06N OR G06F18)
    cpc_filter = {
        "_or": [
            {"_begins": {"cpc_group_id": "G06N"}},
            {"_begins": {"cpc_group_id": "G06F18"}},
        ]
    }
    query = {
        "_and": [
            {"_contains": {"assignees.assignee_organization": assignee_name}},
            cpc_filter,
        ]
    }

    if after_date:
        query["_and"].append({"_gte": {"patent_date": after_date}})

    params = {
        "q": json.dumps(query),
        "f": json.dumps([
            "patent_id",
            "patent_title",
            "patent_date",
            "assignees.assignee_organization",
            "cpc_current.cpc_group_id",
            "cpc_current.cpc_class_id",
        ]),
        "o": json.dumps({"size": 100}),
    }

    response = client.get(
        f"{BASE_URL}/patent/",
        params=params,
        headers={"X-Api-Key": api_key},
    )
    response.raise_for_status()
    return response.json()
```

### Patent DB Model (following existing patterns)
```python
# Follows Phase 3 Filing model pattern exactly
class Patent(AppendOnlyMixin, Base):
    """Append-only patent record from USPTO PatentsView."""

    __tablename__ = "patents"
    __table_args__ = (
        Index("ix_patents_company_date", "company_id", "patent_date"),
        Index("uq_patents_company_patent_id", "company_id", "patent_id", unique=True),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    patent_id: Mapped[str] = mapped_column(String(20), nullable=False)
    patent_title: Mapped[str] = mapped_column(String(500), nullable=False)
    patent_date: Mapped[date] = mapped_column(Date, nullable=False)
    assignee_organization: Mapped[str] = mapped_column(String(500), nullable=False)
    cpc_codes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="[]")
    collection_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
```

### Patent Gap Scoring Formula
```python
# Reuses existing building blocks from Phases 2-4
from ai_washer.analysis.growth import compute_cagr
from ai_washer.analysis.normalization import sigmoid_normalize

def compute_patent_gap_score(
    patent_counts_by_year: dict[int, int],
    ai_claim_intensity_by_year: dict[int, float],
    scoring_year: int,
    window_years: int = 3,
    sigmoid_midpoint: float = 1.0,
    sigmoid_steepness: float = 2.0,
) -> SignalResult | None:
    """Compute patent gap: AI claim intensity trend vs patent filing trend.

    High score = lots of AI talk, few patents (washing signal).
    Low score = patent activity matches or exceeds claims.
    """
    end_year = scoring_year
    start_year = end_year - window_years

    # Get claim intensity growth
    start_claims = ai_claim_intensity_by_year.get(start_year)
    end_claims = ai_claim_intensity_by_year.get(end_year)
    if start_claims is None or end_claims is None:
        return None

    # Get patent count growth
    start_patents = patent_counts_by_year.get(start_year, 0)
    end_patents = patent_counts_by_year.get(end_year, 0)

    claim_growth = compute_cagr(max(start_claims, 0.1), end_claims, window_years)
    patent_growth = compute_cagr(max(start_patents, 1), end_patents, window_years)

    # Ratio: high claim growth / low patent growth = high score (washing)
    claim_factor = 1.0 + (claim_growth if claim_growth is not None else 0.0)
    patent_factor = 1.0 + (patent_growth if patent_growth is not None else 0.0)

    if patent_factor <= 0:
        patent_factor = 0.01

    ratio = claim_factor / patent_factor
    score = sigmoid_normalize(ratio, midpoint=sigmoid_midpoint, steepness=sigmoid_steepness)

    evidence = {
        "signal_version": "0.5.0",
        "claim_growth_cagr": claim_growth,
        "patent_growth_cagr": patent_growth,
        "gap_ratio": ratio,
        "patent_counts": patent_counts_by_year,
        "window": {"start": start_year, "end": end_year},
    }

    return SignalResult(signal_type="patent_gap", score=score, evidence=evidence)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Legacy PatentsView API (api.patentsview.org) | PatentSearch API (search.patentsview.org/api/v1) | May 2025 (legacy discontinued) | Must use new API with API key; field names changed; ElasticSearch-based query language |
| PatentsView standalone site | USPTO Open Data Portal (data.uspto.gov) | March 20, 2026 (migration) | PatentsView now hosted on data.uspto.gov; API key grants temporarily suspended |
| Plural endpoint names (patents/) | Singular endpoint names (patent/) | 2024 (PatentSearch API release) | URL path changed; 27 endpoints (up from 7) |
| patent_number field | patent_id field | 2024 | Field renamed in new API |
| cpc_subsections endpoint | cpc_group endpoint | 2024 | Endpoint renamed |
| Page-based pagination (page, per_page) | Cursor-based pagination (size, after) | 2024 | No more 100K row cap; use "after" cursor for pagination |

**Deprecated/outdated:**
- Legacy PatentsView API at api.patentsview.org: Discontinued May 2025. Do not use.
- pypatent library: Wraps legacy API (web scraping). Dead.
- PatentsView API Wrapper (mikeym88/PatentsView-API-Wrapper): Wraps legacy API. Dead.
- patent_client library: Wraps USPTO ODP (applications only, post-2001). Does NOT cover PatentsView patent search.

## CPC Code Reference

### G06N -- Computing Arrangements Based on Specific Computational Models
| Subcode | Description | Relevance |
|---------|-------------|-----------|
| G06N 1/00 | Biological models | Medium (evolutionary algorithms) |
| G06N 3/00 | Neural networks | HIGH (core deep learning) |
| G06N 3/04 | Architecture | HIGH (transformer patents etc.) |
| G06N 3/08 | Learning methods | HIGH (training algorithms) |
| G06N 5/00 | Knowledge representation | Medium (expert systems) |
| G06N 7/00 | Other computational models | Medium (probabilistic models) |
| G06N 20/00 | Machine learning | HIGH (ML techniques) |

### G06F18 -- Pattern Recognition
| Subcode | Description | Relevance |
|---------|-------------|-----------|
| G06F 18/20 | Feature extraction | HIGH |
| G06F 18/21 | Classification | HIGH |
| G06F 18/22 | Matching | Medium |
| G06F 18/24 | Clustering | HIGH |

**Query strategy:** Use `_begins` operator with prefixes "G06N" and "G06F18" to capture all subcodes in both classes.

## Open Questions

1. **PatentSearch API Key Availability**
   - What we know: New key grants are "temporarily suspended" as of March 2026; the key request page (Jira service desk) may or may not be processing requests
   - What's unclear: When key grants will resume; whether existing keys still work post-migration
   - Recommendation: Request a key now via https://patentsview-support.atlassian.net/servicedesk/customer/portal/1/group/1/create/18. Design the client to fail gracefully with a clear error if no key is available. The scoring orchestrator should skip the patent signal (returning None) if the client cannot connect, consistent with existing graceful degradation pattern.

2. **Post-Migration API URL Stability**
   - What we know: search.patentsview.org hosted the API pre-migration; data.uspto.gov is the new home
   - What's unclear: Whether search.patentsview.org still resolves, or if the URL changed to a data.uspto.gov path
   - Recommendation: Make BASE_URL configurable via env var (PATENTSVIEW_BASE_URL) with default "https://search.patentsview.org/api/v1". This allows zero-code-change URL updates.

3. **Bulk Data Fallback Complexity**
   - What we know: PatentsView bulk downloads (TSV files) contain assignee and CPC data; files are multi-GB
   - What's unclear: Whether bulk data is still available post-migration at data.uspto.gov
   - Recommendation: Defer bulk data fallback to a future iteration. For v1, implement API-only with clear error handling if API is unavailable. The signal will simply be missing from the composite score (SCORE-04 graceful degradation handles this).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| httpx | Patent API client | Yes | 0.28.1 | -- |
| tenacity | Retry logic | Yes | 9.1.4 | -- |
| rapidfuzz | Assignee name matching | Yes | 3.14.3 | -- |
| pydantic | Data validation | Yes | 2.12.5 | -- |
| structlog | Logging | Yes | 25.5.0 | -- |
| pytest | Testing | Yes | 9.0.2 | -- |
| pytest-httpx | HTTP mocking | Yes | 0.36.0 | -- |
| freezegun | Time mocking | Yes | 1.5.5 | -- |
| PatentSearch API key | PAT-01 | UNKNOWN | -- | Skip signal; graceful degradation |
| PostgreSQL | Patent storage | Yes | (via testcontainers) | -- |

**Missing dependencies with no fallback:**
- PatentSearch API key: Required for API access. Grants temporarily suspended. Code MUST handle absence gracefully.

**Missing dependencies with fallback:**
- None. All Python packages are already installed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `.venv/bin/python -m pytest tests/unit/ -x -q` |
| Full suite command | `.venv/bin/python -m pytest tests/ -x --timeout=120` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PAT-01 | Patent client queries PatentSearch API with CPC codes G06N/G06F18 by assignee | unit | `.venv/bin/python -m pytest tests/unit/test_patent_client.py -x` | Wave 0 |
| PAT-01 | Patent assignee names map to entity resolution table | unit | `.venv/bin/python -m pytest tests/unit/test_patent_types.py -x` | Wave 0 |
| PAT-02 | Patent gap score 0-100 reflects divergence between claims and patents | unit | `.venv/bin/python -m pytest tests/unit/test_patent_gap_scorer.py -x` | Wave 0 |
| PAT-02 | Scoring orchestrator loads patents and calls pure scorer | unit | `.venv/bin/python -m pytest tests/unit/test_scoring_orchestrator.py -x` | Existing (extend) |
| PAT-03 | Incremental collection skips already-stored patents | unit | `.venv/bin/python -m pytest tests/unit/test_patent_client.py::test_incremental -x` | Wave 0 |
| PAT-03 | Patent model unique constraint enforces idempotency | integration | `.venv/bin/python -m pytest tests/integration/test_signal_persistence.py -x -m integration` | Existing (extend) |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/unit/ -x -q --timeout=30`
- **Per wave merge:** `.venv/bin/python -m pytest tests/ -x --timeout=120`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_patent_client.py` -- covers PAT-01 API client, query construction, pagination, error handling
- [ ] `tests/unit/test_patent_types.py` -- covers patent Pydantic schemas and frozen dataclass
- [ ] `tests/unit/test_patent_gap_scorer.py` -- covers PAT-02 scoring formula, edge cases, evidence dict

## Sources

### Primary (HIGH confidence)
- [PatentSearch API Reference](https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/) - Base URL, auth, rate limits, query syntax
- [PatentSearch API Endpoint Dictionary](https://search.patentsview.org/docs/docs/Search%20API/EndpointDictionary/) - Field names for assignee, CPC, patent
- [rOpenSci Breaking Release](https://ropensci.org/blog/2026/03/10/patentsview-breaking-release/) - Confirmed field name changes, new endpoint structure, query patterns
- [USPTO CPC G06N Definition](https://www.uspto.gov/web/patents/classification/cpc/html/cpc-G06N.html) - AI/ML CPC code hierarchy

### Secondary (MEDIUM confidence)
- [USPTO Migration Announcement](https://www.uspto.gov/subscription-center/2026/patentsview-migrating-uspto-open-data-portal-march-20) - Migration date and scope
- [PatentsView API FAQs](https://patentsview.org/apis/api-faqs) - API key policy, rate limits
- [PatentsView Key Request Portal](https://patentsview-support.atlassian.net/servicedesk/customer/portal/1/group/1/create/18) - Where to request API key

### Tertiary (LOW confidence)
- [DEV.to USPTO article](https://dev.to/0012303/uspto-has-a-free-patent-api-search-8m-patents-no-key-required-3c9i) - References LEGACY API only (not current). Do not rely on.
- [pyUSPTO PyPI](https://pypi.org/project/pyUSPTO/) - Wraps ODP, NOT PatentsView. Not suitable for this use case.
- [Terrorizer Algorithm (assignee disambiguation)](https://arxiv.org/html/2403.12083v1) - Academic approach to assignee name harmonization; informational only

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All packages already in pyproject.toml; no new dependencies
- Architecture: HIGH - Follows exact patterns from Phases 3-4 (client, scorer, orchestrator)
- API access: LOW - Key grants temporarily suspended; post-migration URL stability unknown
- Scoring formula: MEDIUM - Reuses proven CAGR/sigmoid building blocks; novel ratio design untested
- Pitfalls: HIGH - Well-documented API migration issues; assignee matching is a known hard problem with existing solution in codebase

**Research date:** 2026-03-28
**Valid until:** 2026-04-15 (API migration situation is rapidly evolving)
