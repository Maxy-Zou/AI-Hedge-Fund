# Phase 8: Job Posting Signal - Research

**Researched:** 2026-03-29
**Domain:** Job scraping, role classification, mismatch scoring
**Confidence:** MEDIUM

## Summary

Phase 8 adds the highest-weighted signal (25%) in the composite score: the gap between AI claims and actual AI hiring activity. The core workflow is scrape job postings via python-jobspy, classify roles as genuine AI/ML vs. marketing, deduplicate across job boards, track posting lifecycles for ghost job detection, and compute a mismatch score against SEC filing claim intensity.

The primary technical risk is python-jobspy's reliability. LinkedIn aggressively rate-limits (around page 10), Indeed is the most stable scraper, and all endpoints cap at ~1,000 results per search. For mid-cap companies (~200 in the universe), Indeed + Google should provide sufficient coverage without proxies. Ghost job detection (27-30% of postings are phantom) requires lifecycle tracking via first_seen/last_seen timestamps with a 90-day staleness threshold.

**Primary recommendation:** Use python-jobspy 1.1.82 with Indeed + Google as primary sources (LinkedIn optional with proxy). Build deterministic dedup hash (company + title + location). Implement a simple keyword-based role classifier with two tiers (engineering vs. marketing). Follow the established collector/client/types/scorer pattern from Phases 5-7.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- discuss phase was skipped per user setting. All implementation choices at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion -- discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None -- discuss phase skipped.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| JOB-01 | Ingest AI-related job postings using free scraping sources (JobSpy) | python-jobspy 1.1.82 via `scrape_jobs()`, Indeed + Google primary sites, search_term targeting AI/ML roles |
| JOB-02 | Role classifier distinguishes AI/ML engineering from marketing/strategy roles | Two-tier keyword classifier: engineering keywords (pytorch, tensorflow, ml pipeline, data scientist) vs. marketing keywords (AI strategy, AI-powered, digital transformation) |
| JOB-03 | Deduplication via deterministic hash (company + title + location) | SHA-256 of normalized (lowered, stripped) company + title + location; unique DB constraint prevents double-insert |
| JOB-04 | Lifecycle tracking with first_seen, last_seen, is_active for ghost job detection | JobPosting model with first_seen, last_seen, is_active columns; weekly refresh updates last_seen; >90 days marks as potential ghost |
| JOB-05 | Job mismatch score (0-100) comparing AI claims to hiring activity | Pure function scorer following sigmoid_normalize pattern; sub-factors: role_count, seniority_ratio, specificity, ghost_ratio |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Immutability**: Financial data never overwritten -- append new snapshots. Job postings are a special case: lifecycle tracking requires UPDATE to last_seen/is_active (similar to Company entity table, not append-only)
- **Error handling**: Catch specific exceptions, return sensible defaults (empty list) on error
- **Retry logic**: tenacity decorators for external API calls
- **Rate limiting**: Manual sleep between companies in collect_all (1.0s established pattern)
- **Scoring config**: All parameters externalized in config/scoring.yaml via Pydantic config classes
- **Pure scorers**: analysis/ scorers have NO DB access; ScoringOrchestrator is the only bridge
- **Type contracts**: Pydantic types.py in each subpackage defines module interfaces
- **Signal version**: Must be "0.8.0" matching Phase 8 numbering convention
- **Idempotent collection**: Unique DB constraints prevent double-counting
- **Lazy imports**: Heavy modules imported inside CLI command functions
- **structlog**: `logger = structlog.get_logger(__name__)` at module level, bind context in collectors

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-jobspy | 1.1.82 | Job posting scraping from Indeed, Google, LinkedIn | Only viable free multi-board scraper. Returns pandas DataFrame. CLAUDE.md recommends it. |
| pandas | >=3.0.1 | DataFrame processing from jobspy output | Already in project deps. jobspy returns DataFrames natively. |
| hashlib (stdlib) | - | SHA-256 deterministic dedup hash | Stdlib, no deps. Same pattern as filing content_hash (Phase 3). |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | >=9.1.4 | Retry on transient scraping failures | Already in project. Wrap jobspy calls. |
| rapidfuzz | >=3.14.3 | Fuzzy company name matching for dedup | Already in project. Match scraped company names to Company.name/aliases. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| python-jobspy | Direct Indeed/LinkedIn scraping | Much more work, same rate limits, no community maintenance |
| python-jobspy | TheirStack API | Paid service -- violates v1 free-only constraint |
| Keyword classifier | FinBERT/LLM classifier | Overkill for v1. Keyword-based is interpretable, fast, no model loading. Can upgrade in v2. |

**Installation:**
```bash
uv add python-jobspy
```

## Architecture Patterns

### Recommended Project Structure
```
src/ai_washer/
  ingestion/
    job_client.py          # Thin wrapper around jobspy.scrape_jobs()
    job_collector.py       # Orchestrator: scrape -> classify -> dedup -> persist
    job_types.py           # Pydantic contracts + constants + role classifier
  analysis/
    job_mismatch_scorer.py # Pure function scorer (no DB access)
  db/
    models.py              # Add JobPosting model
    migrations/versions/
      007_add_job_postings.py  # Alembic migration
```

### Pattern 1: Collector Pattern (established in Phases 5-7)
**What:** Client wraps external API, Collector orchestrates DB persistence
**When to use:** Every data ingestion signal
**Example:**
```python
# job_client.py -- thin wrapper
class JobClient:
    def search_company_jobs(self, company_name: str, ...) -> list[JobRecord]:
        """Scrape job postings for a company via python-jobspy."""
        df = scrape_jobs(
            site_name=["indeed", "google"],
            search_term=f'"{company_name}" AI OR "machine learning"',
            results_wanted=50,
            country_indeed="USA",
        )
        return [JobRecord.from_dataframe_row(row) for _, row in df.iterrows()]
```

### Pattern 2: Deterministic Dedup Hash
**What:** SHA-256 of normalized (company + title + location) for cross-board dedup
**When to use:** Before persisting any job posting
**Example:**
```python
import hashlib

def compute_job_hash(company: str, title: str, location: str) -> str:
    """Deterministic hash for cross-board deduplication."""
    normalized = f"{company.lower().strip()}|{title.lower().strip()}|{location.lower().strip()}"
    return hashlib.sha256(normalized.encode()).hexdigest()
```

### Pattern 3: Lifecycle Tracking (UPDATE, not append-only)
**What:** JobPosting model with first_seen, last_seen, is_active. Weekly refresh updates last_seen for active postings. Postings not seen in current scrape get is_active=False.
**When to use:** Ghost job detection requires mutable state
**Note:** This is the same pattern as the Company entity table -- mutable metadata, not financial time-series data. The append-only rule applies to scoring/signal data, not entity metadata.

### Pattern 4: Two-Tier Role Classifier
**What:** Keyword-based classification into engineering/marketing roles
**When to use:** Distinguish genuine AI hiring from marketing fluff
**Example:**
```python
ENGINEERING_KEYWORDS = [
    "machine learning engineer", "ml engineer", "data scientist",
    "deep learning", "nlp engineer", "computer vision",
    "pytorch", "tensorflow", "mlops", "ml infrastructure",
    "research scientist", "applied scientist",
]
MARKETING_KEYWORDS = [
    "ai strategy", "ai-powered", "digital transformation",
    "ai evangelist", "innovation lead", "thought leader",
    "ai product marketing", "ai partnership",
]

def classify_role(title: str, description: str) -> str:
    """Classify job as 'engineering', 'marketing', or 'ambiguous'."""
    text = f"{title} {description}".lower()
    eng_hits = sum(1 for kw in ENGINEERING_KEYWORDS if kw in text)
    mkt_hits = sum(1 for kw in MARKETING_KEYWORDS if kw in text)
    if eng_hits > mkt_hits:
        return "engineering"
    elif mkt_hits > eng_hits:
        return "marketing"
    return "ambiguous"
```

### Anti-Patterns to Avoid
- **Treating job postings as append-only**: Lifecycle tracking requires updates to last_seen and is_active. This is entity data, not signal data.
- **Scraping all job boards simultaneously**: LinkedIn rate-limits aggressively. Use Indeed + Google first, LinkedIn only if proxies are available.
- **Relying on company name exact match from scraper**: Company names in job postings vary ("Apple Inc" vs "Apple" vs "Apple, Inc."). Use rapidfuzz for matching to Company.name.
- **Building a complex NLP classifier for v1**: Keywords are interpretable, fast, and sufficient. ML classifier is v2.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Job board scraping | Custom Indeed/LinkedIn scrapers | python-jobspy | Handles pagination, rate limits, HTML parsing. Maintenance burden is on the library. |
| Company name fuzzy matching | Levenshtein from scratch | rapidfuzz (already in project) | C++ extension, handles edge cases (suffixes, abbreviations). Already used in entity resolution. |
| Score normalization | Custom sigmoid function | sigmoid_normalize (analysis/normalization.py) | Already implemented and tested with overflow protection. |
| DataFrame to typed records | Manual dict parsing | Pydantic BaseModel.model_validate() | Validates at boundary, catches malformed data. |

## Common Pitfalls

### Pitfall 1: LinkedIn Rate Limiting
**What goes wrong:** LinkedIn blocks after ~page 10 (50-100 results) with one IP. Returns empty results silently.
**Why it happens:** LinkedIn aggressively detects scraping patterns.
**How to avoid:** Use Indeed + Google as primary sources. LinkedIn only with proxy rotation if available. Don't depend on LinkedIn for coverage.
**Warning signs:** Decreasing result counts, empty DataFrames, HTTP 429 responses.

### Pitfall 2: Company Name Mismatch
**What goes wrong:** JobSpy returns company names that don't match Company.name or aliases. "Apple Inc." vs "Apple" vs "APPLE INC" causes missed matches.
**Why it happens:** Job boards normalize company names differently.
**How to avoid:** Use rapidfuzz with threshold 85 (established in Phase 2 entity resolution). Also check Company.aliases for additional match surfaces.
**Warning signs:** High "unmatched company" counts in collection logs.

### Pitfall 3: Syndicated Duplicate Postings
**What goes wrong:** Same job posted on Indeed AND Google shows up as two separate postings, inflating counts.
**Why it happens:** Companies cross-post to multiple boards. JobSpy scrapes each independently.
**How to avoid:** Deterministic hash dedup (company + title + location) before persistence. The hash catches exact duplicates; near-duplicates (slight title variations) need fuzzy matching on title with threshold ~90.
**Warning signs:** Duplicate hash counts in collection logs. Same company having 2x expected postings.

### Pitfall 4: Ghost Job False Positives
**What goes wrong:** Legitimate long-term hires (senior roles, specialized positions) get flagged as ghost jobs.
**Why it happens:** 90-day threshold catches some real roles that are genuinely hard to fill.
**How to avoid:** Ghost job flag is a factor in scoring, not a binary filter. Weight it as one sub-factor (e.g., 20% of mismatch score), not a disqualifier. Log ghost_ratio in evidence for audit.
**Warning signs:** >50% ghost rate for a company (suspiciously high).

### Pitfall 5: Empty Scrape Results
**What goes wrong:** JobSpy returns empty DataFrame for valid companies. Could be rate limit, could be company doesn't post publicly.
**Why it happens:** Some mid-cap companies use internal recruiting or niche boards not covered by JobSpy.
**How to avoid:** Return None/empty result gracefully. Scoring handles missing job signal via SCORE-04 (graceful degradation with re-normalized weights). Log as "no_job_data" for audit.
**Warning signs:** Consistently empty results across multiple collection runs.

### Pitfall 6: Search Term Overfitting
**What goes wrong:** Searching for "AI machine learning" finds too many false positives (e.g., "AI-powered sales tool" marketing roles) or misses results.
**Why it happens:** Job boards search descriptions in addition to titles.
**How to avoid:** Search broadly, classify precisely. Use a general search term like `"{company_name}" AI OR "machine learning"` and rely on the role classifier to filter.
**Warning signs:** High marketing_role ratio (>70%) in results.

## Code Examples

### JobPosting ORM Model
```python
class JobPosting(Base):
    """Job posting with lifecycle tracking.

    NOT append-only -- requires updates to last_seen, is_active.
    Similar to Company entity table pattern.
    Unique constraint on dedup_hash for cross-board deduplication.
    """
    __tablename__ = "job_postings"
    __table_args__ = (
        Index("ix_job_postings_company_date", "company_id", "first_seen"),
        Index("uq_job_postings_dedup_hash", "dedup_hash", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company_name_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    job_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_site: Mapped[str] = mapped_column(String(50), nullable=False)
    role_classification: Mapped[str] = mapped_column(String(20), nullable=False)
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen: Mapped[date] = mapped_column(Date, nullable=False)
    last_seen: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("true"))
    collection_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

### Job Mismatch Scorer Sub-Factors
```python
def compute_job_mismatch_score(
    ai_role_count: int,
    marketing_role_count: int,
    total_role_count: int,
    ghost_ratio: float,
    ai_claim_intensity: float,
    scoring_year: int,
    sigmoid_midpoint: float = 1.0,
    sigmoid_steepness: float = 2.0,
) -> SignalResult | None:
    """Compute job mismatch gap score.

    Sub-factors:
    - hiring_intensity: ai_role_count / normalized cap (0-1)
    - specificity: ai_roles / total_roles ratio (higher = more genuine)
    - ghost_penalty: ghost_ratio reduces job_factor
    - marketing_ratio: marketing roles / total (higher = more washing)

    High score = lots of AI claims, few genuine AI hires.
    """
```

### ScoringConfig Addition
```python
class JobMismatchScoringConfig(BaseModel):
    """Configuration for job posting mismatch scoring."""
    ghost_days_threshold: int = Field(default=90, ge=30, le=365)
    ghost_penalty_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    sigmoid_midpoint: float = Field(default=1.0)
    sigmoid_steepness: float = Field(default=2.0)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| TheirStack paid API | python-jobspy free scraping | 2024 | Free alternative with good multi-board coverage |
| LinkedIn-only scraping | Multi-board (Indeed primary) | 2025 | Indeed has no rate limiting, more reliable |
| Manual ghost detection | Lifecycle tracking (first_seen/last_seen) | Emerging pattern | Systematic approach to 27-30% ghost job problem |

## Open Questions

1. **Indeed search coverage for mid-cap companies**
   - What we know: Indeed has no rate limiting and the best scraper in JobSpy
   - What's unclear: Whether all ~200 mid-cap companies in the universe have Indeed-visible job postings
   - Recommendation: Collect with Indeed + Google, log companies with zero results for manual review

2. **Company name matching accuracy**
   - What we know: rapidfuzz at threshold 85 works for entity resolution
   - What's unclear: Job board company names may need different threshold or preprocessing
   - Recommendation: Start at 85, monitor unmatched rate, adjust. Store company_name_raw for debugging.

3. **Ghost job 90-day threshold appropriateness**
   - What we know: STATE.md notes ghost job rate is 27-30%. 90 days is conventional.
   - What's unclear: Whether 90 days is optimal for mid-cap AI roles specifically
   - Recommendation: Make threshold configurable in scoring.yaml (ghost_days_threshold). Start at 90, calibrate after first data collection.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| python-jobspy | JOB-01 (job scraping) | Not installed | 1.1.82 on PyPI | Install via `uv add python-jobspy` |
| PostgreSQL | DB storage | Assumed available | 16+ | -- |
| rapidfuzz | Company name matching | Installed | >=3.14.3 | -- |
| pandas | DataFrame processing | Installed | >=3.0.1 | -- |

**Missing dependencies with no fallback:**
- python-jobspy: Must be installed. No alternative free multi-board scraper exists.

**Missing dependencies with fallback:**
- None

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0.2 |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/unit/test_job_*.py -x` |
| Full suite command | `python -m pytest tests/ -x --timeout=60` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| JOB-01 | Job postings ingested via JobSpy | unit | `python -m pytest tests/unit/test_job_client.py -x` | Wave 0 |
| JOB-02 | Role classifier distinguishes engineering from marketing | unit | `python -m pytest tests/unit/test_job_types.py -x` | Wave 0 |
| JOB-03 | Dedup via deterministic hash | unit | `python -m pytest tests/unit/test_job_types.py::test_dedup_hash -x` | Wave 0 |
| JOB-04 | Lifecycle tracking first_seen/last_seen/is_active | unit + integration | `python -m pytest tests/unit/test_job_collector.py -x` | Wave 0 |
| JOB-05 | Mismatch score 0-100 comparing claims to hiring | unit | `python -m pytest tests/unit/test_job_mismatch_scorer.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/test_job_*.py -x`
- **Per wave merge:** `python -m pytest tests/ -x --timeout=60`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_job_types.py` -- covers JOB-02 (role classifier), JOB-03 (dedup hash)
- [ ] `tests/unit/test_job_client.py` -- covers JOB-01 (scraping wrapper)
- [ ] `tests/unit/test_job_collector.py` -- covers JOB-04 (lifecycle tracking)
- [ ] `tests/unit/test_job_mismatch_scorer.py` -- covers JOB-05 (mismatch score)
- [ ] `python-jobspy` package: `uv add python-jobspy` -- not yet installed

## Sources

### Primary (HIGH confidence)
- [python-jobspy PyPI](https://pypi.org/project/python-jobspy/) - v1.1.82 verified
- [JobSpy GitHub README](https://github.com/speedyapply/JobSpy) - API docs, parameters, limitations
- Existing codebase: Phase 5-7 collector/client/types/scorer patterns verified by reading source

### Secondary (MEDIUM confidence)
- [JobSpy rate limiting notes](https://github.com/speedyapply/JobSpy) - LinkedIn caps at page 10, Indeed has no limit
- Ghost job 27-30% rate from STATE.md (sourced from project research phase)

### Tertiary (LOW confidence)
- Ghost job detection via embedding similarity (community suggestion, not implemented in JobSpy)
- 90-day threshold conventionality (needs calibration against actual data)

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - python-jobspy is the only viable free option; reliability depends on job board anti-scraping measures
- Architecture: HIGH - follows established collector/client/types/scorer pattern from Phases 5-7 exactly
- Pitfalls: MEDIUM - ghost job detection strategy is theoretically sound but STATE.md explicitly flags it as untested
- Role classifier: MEDIUM - keyword-based is standard for v1 but accuracy unvalidated on real job data

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (python-jobspy updates frequently, job board anti-scraping measures change)
