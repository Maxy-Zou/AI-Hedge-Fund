# Phase 2: Entity Resolution and Universe Builder - Research

**Researched:** 2026-03-27
**Domain:** SEC EDGAR data access (EFTS full-text search, XBRL company facts), entity resolution via fuzzy string matching, universe construction for mid-cap AI-claiming companies
**Confidence:** HIGH

## Summary

Phase 2 builds two distinct subsystems: (1) a universe builder that discovers mid-cap companies making AI claims by scanning EDGAR full-text search and filtering by market cap, and (2) an entity resolver that maps each discovered company across SEC (CIK), USPTO (patent assignee), GitHub (org), and job postings (employer name) into a unified record stored in the existing Company.aliases JSONB field.

The technical approach is well-supported by existing tooling. edgartools v5.26.1 provides `search_filings()` which wraps the EFTS API at `efts.sec.gov`, but its pagination is limited to 100 results per call. For scanning thousands of filings, we need a custom EFTS client using httpx that handles the `from` parameter for offset-based pagination (max 10,000 results per query). Market cap filtering requires the SEC XBRL company facts API (`data.sec.gov/api/xbrl/companyfacts/`), which provides `EntityPublicFloat` as a proxy since EDGAR does not report market capitalization directly. rapidfuzz v3.14.3 handles fuzzy name matching for entity resolution across data sources.

A critical finding: the Company model from Phase 1 is missing the `is_active` column required by decision D-10 (soft-remove for delistings/mergers). This must be added via an Alembic migration in this phase.

**Primary recommendation:** Build a custom EFTS client for universe scanning (pagination beyond 100), use edgartools for company facts/XBRL data and CIK lookup, use `EntityPublicFloat` from XBRL as the market cap proxy, and use rapidfuzz for cross-source entity name matching.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Curated seed + fuzzy expand approach -- start with manually curated mapping for top 50-100 companies, use fuzzy matching (e.g., fuzzywuzzy/rapidfuzz on company names) to expand. Edge cases validated by humans.
- **D-02:** Use existing Company.aliases JSONB field for mapping storage: `{"cik": "...", "patent_assignee": ["..."], "github_org": "...", "employer_names": ["..."]}`. No separate mapping table needed.
- **D-03:** Companies with partial resolution (e.g., no GitHub org found) are included in the universe with null fields. Downstream composite scoring handles missing signals via graceful degradation.
- **D-04:** Market cap sourced from SEC EDGAR XBRL company facts API (free, via edgartools). May be quarterly-stale -- acceptable for mid-cap filtering.
- **D-05:** EDGAR full-text search (efts.sec.gov) for "artificial intelligence" OR "machine learning" in 10-K filings from last 12 months. Filter results to $2B-$10B market cap.
- **D-06:** Universe builder must be deterministic -- same day = same target list.
- **D-07:** Fully automated EDGAR scan to discover companies. No manual seed list required upfront -- the EDGAR search IS the discovery mechanism. Manual curation can follow.
- **D-08:** All discovered companies added to the Company table immediately. No human review gate before insertion.
- **D-09:** Universe re-scanned monthly. AI washing is slow-moving; new 10-Ks file quarterly. Monthly catches new filers without excessive API usage.
- **D-10:** Delistings, mergers, and market cap changes handled via soft remove -- mark as `is_active=False` with reason. Never delete. Consistent with Phase 1 append-only design.

### Claude's Discretion
- Exact fuzzy matching threshold and algorithm (rapidfuzz vs fuzzywuzzy vs custom)
- EDGAR full-text search pagination strategy
- How to handle subsidiaries (map to parent company or track separately)
- CLI commands for manual universe management (add/remove/inspect companies)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FNDN-02 | Company entity resolution maps companies across data sources (CIK, patent assignee, GitHub org, job posting employer) into a unified master table with aliases | edgartools Company lookup + CIK mapping, rapidfuzz for fuzzy name matching, Company.aliases JSONB storage pattern |
| FNDN-03 | Target universe builder identifies mid-cap companies ($2B-$10B market cap) making AI claims via EDGAR full-text search, filtered by sector | EFTS API for AI keyword search in 10-K filings, XBRL company facts API for EntityPublicFloat as market cap proxy, company_tickers.json for ticker-CIK mapping |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Language:** Python 3.11+
- **Package management:** uv preferred
- **Immutability:** Return new objects, never mutate in place
- **Data handling:** Raw data cached locally, all timestamps UTC, preserve source precision
- **Financial data:** Never overwrite historical records, append new snapshots only
- **API compliance:** SEC EDGAR requires User-Agent with company/name + email
- **Rate limits:** SEC 10 req/sec max, be conservative
- **Monetary values:** Stored as integers (cents) in BIGINT columns
- **Error handling:** Handle errors explicitly at every level, never silently swallow
- **Input validation:** Validate at system boundaries using schema-based validation
- **Testing:** pytest, 80%+ coverage target, TDD workflow
- **File organization:** Many small files (200-400 lines typical, 800 max)
- **Coding style:** Immutable data patterns, functions <50 lines, no deep nesting >4 levels

## Standard Stack

### Core (Phase 2-specific additions)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| edgartools | >=5.26.1 | Company lookup, CIK resolution, XBRL company facts | Already in project stack. Provides `find_company()`, `get_company_facts()`, `Company.shares_outstanding`, `Company.public_float`. Has built-in EFTS search via `search_filings()` but limited to 100 results. |
| httpx | 0.28.1 | Custom EFTS client for paginated full-text search | Already installed. Needed because edgartools EFTS search caps at 100 results and lacks offset pagination. Direct EFTS API calls with `from` parameter required for full universe scan. |
| rapidfuzz | >=3.14.3 | Fuzzy string matching for entity resolution | C++ core, 10x faster than fuzzywuzzy, MIT license. Standard for production entity matching. `fuzz.token_sort_ratio` handles word-order variations in company names. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | >=9.1.4 | Retry logic for EDGAR and EFTS API calls | Already in project stack. Wrap all external HTTP calls with exponential backoff + jitter. |
| structlog | >=25.5.0 | Structured logging for universe scan progress | Already configured. Log company discovery counts, resolution status, API errors. |
| pydantic | >=2.12.5 | Validation models for EFTS responses and entity data | Already in project. Define schemas for EFTS results, company facts, alias structures. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| rapidfuzz | fuzzywuzzy | fuzzywuzzy is slower (pure Python), GPL-licensed (not MIT). rapidfuzz is a drop-in replacement with C++ speed. No reason to use fuzzywuzzy. |
| rapidfuzz | polyfuzz | polyfuzz adds sklearn/sentence-transformers dependencies. Overkill for company name matching. rapidfuzz is lighter and faster for exact string similarity. |
| Custom EFTS client | edgartools search_filings() | edgartools search_filings() caps at 100 results with no pagination. Universe scan needs thousands of results. Must use raw EFTS API. |
| EntityPublicFloat (XBRL) | yfinance market_cap | yfinance scrapes Yahoo Finance (fragile, rate-limited, ToS gray area). EntityPublicFloat is free, official SEC data, same source as all other company data. Quarterly staleness is acceptable per D-04. |

**Installation:**
```bash
# From project root with uv
uv add edgartools httpx rapidfuzz tenacity
```

**Version verification:**
- edgartools: 5.26.1 (verified via `pip3 index versions edgartools`)
- httpx: 0.28.1 (verified, already installed in project)
- rapidfuzz: 3.14.3 (verified via `pip3 index versions rapidfuzz`)

## Architecture Patterns

### Recommended Project Structure (Phase 2 additions)
```
src/ai_washer/
  ingestion/
    __init__.py
    efts_client.py       # Custom EFTS API client with pagination (~200 lines)
    edgar_client.py      # edgartools wrapper for company facts/XBRL (~200 lines)
  entity/
    __init__.py
    resolver.py          # Entity resolution: CIK -> aliases mapping (~250 lines)
    fuzzy_matcher.py     # rapidfuzz name matching utilities (~150 lines)
  universe/
    __init__.py
    builder.py           # Universe construction orchestrator (~300 lines)
    filters.py           # Market cap filter, AI keyword filter (~150 lines)
  db/
    models.py            # Updated Company model (is_active, deactivation_reason)
    migrations/versions/
      002_add_company_active_fields.py  # New migration
  config.py              # Updated: add universe config settings
  cli.py                 # Updated: add universe subcommand group
```

### Pattern 1: EFTS Paginated Search Client
**What:** A custom HTTP client that wraps the `efts.sec.gov/LATEST/search-index` API with offset-based pagination, handling the 10,000-result cap per query.
**When to use:** Every universe scan that needs to discover all 10-K filings mentioning AI keywords.
**Why:** edgartools `search_filings()` returns max 100 results. The raw EFTS API supports `from` parameter for pagination (up to 10,000 total). Universe scan may match 2,000-5,000 filings.
**Example:**
```python
# Source: EFTS API documentation + hermes project pattern
import httpx
from typing import Iterator

EFTS_BASE = "https://efts.sec.gov/LATEST/search-index"
PAGE_SIZE = 100  # EFTS max per request

def search_efts(
    query: str,
    forms: str = "10-K",
    start_date: str | None = None,
    end_date: str | None = None,
) -> Iterator[dict]:
    """Yield all EFTS results with automatic pagination."""
    params = {
        "q": query,
        "forms": forms,
        "from": 0,
        "size": PAGE_SIZE,
    }
    if start_date and end_date:
        params["dateRange"] = "custom"
        params["startdt"] = start_date
        params["enddt"] = end_date

    headers = {"User-Agent": edgar_identity}  # SEC compliance

    while params["from"] < 10_000:  # EFTS cap
        resp = client.get(EFTS_BASE, params=params, headers=headers)
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break
        for hit in hits:
            yield hit["_source"]
        params["from"] += PAGE_SIZE
```

### Pattern 2: Entity Resolution with Fuzzy Matching
**What:** Map a company's legal name (from SEC) to variant names used by USPTO, GitHub, and job boards using rapidfuzz token_sort_ratio.
**When to use:** After discovering companies via EFTS, resolve their identities across data sources.
**Why:** Company names vary across sources: "ALPHABET INC" (SEC) vs "Google LLC" (USPTO) vs "google" (GitHub). Exact matching fails. Fuzzy matching with a threshold handles variations.
**Example:**
```python
# Source: rapidfuzz documentation
from rapidfuzz import fuzz, process

MATCH_THRESHOLD = 85  # Score 0-100, 85+ is a strong match

def find_best_match(
    query: str,
    candidates: list[str],
    threshold: int = MATCH_THRESHOLD,
) -> tuple[str, int] | None:
    """Find the best fuzzy match for a company name."""
    result = process.extractOne(
        query,
        candidates,
        scorer=fuzz.token_sort_ratio,
        score_cutoff=threshold,
    )
    return (result[0], result[1]) if result else None
```

### Pattern 3: Deterministic Universe Build
**What:** Ensure the universe builder produces the same output when run twice on the same day.
**When to use:** Every universe scan (per D-06).
**Why:** Downstream systems need predictable company lists. Non-determinism in universe construction propagates through all scoring.
**Implementation approach:**
1. Pin the date range to calendar day boundaries (midnight UTC to midnight UTC)
2. Sort all discovered CIKs before processing
3. Use deterministic tie-breaking for market cap edge cases (alphabetical by ticker)
4. Cache the EFTS response set per date to avoid EFTS API returning different pagination ordering across calls
5. Store the scan date and result hash as metadata

### Anti-Patterns to Avoid
- **Calling EFTS per-company:** EFTS is a full-text search engine. Search by keyword ("artificial intelligence"), not by company. One query returns all matching filings across all filers. Iterating per-company is wasteful and hits rate limits.
- **Using market_cap from external sources:** Decision D-04 locks this to EDGAR XBRL. Do not introduce yfinance or other price APIs.
- **Storing entity resolution in a separate mapping table:** Decision D-02 locks this to Company.aliases JSONB. Do not create a new table.
- **Blocking on missing entity data:** Decision D-03 explicitly allows partial resolution. Do not reject companies missing GitHub or patent data.
- **Mutating Company records in-place for market cap updates:** Use UPDATE (Company is an entity table, not append-only per Phase 1 decision), but always set updated_at via onupdate trigger.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fuzzy string matching | Custom Levenshtein distance, edit-distance scoring | rapidfuzz `fuzz.token_sort_ratio` + `process.extractOne` | Handles word reordering ("Inc Alphabet" vs "Alphabet Inc"), C++ performance, well-tested edge cases |
| CIK-to-ticker mapping | Manual scraping of SEC company pages | `data.sec.gov/files/company_tickers.json` (free, no auth) + edgartools `get_ticker_to_cik_lookup()` | SEC maintains this file with ~10K entries. Updated regularly. Contains cik_str, ticker, title. |
| XBRL fact extraction | Raw XBRL XML parsing | edgartools `Company(ticker).get_facts()` or direct `data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json` | XBRL parsing is enormously complex. edgartools normalizes taxonomy variations. The raw API returns pre-processed JSON. |
| HTTP retry logic | Custom retry loops with sleep | tenacity `@retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(5))` | Handles jitter, exponential backoff, configurable stop conditions. Already in project dependencies. |
| SEC identity management | Hardcoded User-Agent strings | edgartools `set_identity()` + AppSettings.edgar_identity | edgartools handles identity for its own calls. For raw httpx calls, pull from AppSettings. |

## Common Pitfalls

### Pitfall 1: EFTS Pagination Cap at 10,000 Results
**What goes wrong:** The EFTS API hard-caps at 10,000 results per query. If "artificial intelligence" OR "machine learning" matches more than 10,000 10-K filings in 12 months, the universe scan is incomplete.
**Why it happens:** EFTS is built on Elasticsearch which defaults to a 10K deep-pagination limit.
**How to avoid:** Split the query into multiple narrower searches: (1) search "artificial intelligence" separately from "machine learning", (2) split by date ranges (e.g., Q1 + Q2 + Q3 + Q4), (3) union and deduplicate results by CIK. Each sub-query stays under 10K. Also note: the `total.relation` field in the response is "gte" when over 10K, which is a signal to split.
**Warning signs:** `total.relation == "gte"` in the EFTS response, or `total.value == 10000` exactly.

### Pitfall 2: EntityPublicFloat Is Not Market Cap
**What goes wrong:** EDGAR XBRL reports `EntityPublicFloat` (from DEI taxonomy), not market capitalization. Public float is total shares outstanding minus restricted/insider shares, multiplied by price. It is typically 60-90% of market cap for most companies.
**Why it happens:** SEC requires public float disclosure (for determining filer status), but market cap is not a required XBRL tag. No free SEC API provides market cap directly.
**How to avoid:** Use EntityPublicFloat as a proxy with adjusted thresholds. If targeting $2B-$10B market cap, search for EntityPublicFloat of roughly $1.5B-$9B to account for the float-to-cap ratio. Alternatively, use `EntityCommonStockSharesOutstanding` and multiply by a price from a free source. For v1, the float proxy with widened thresholds is simpler and stays within the free-API constraint.
**Warning signs:** Companies near the $2B or $10B boundary being incorrectly included/excluded. Validate a sample of 20 companies against known market caps.

### Pitfall 3: edgartools search_filings() Is Not Sufficient for Full Scan
**What goes wrong:** Developers use edgartools' `search_filings()` for the universe scan and get only 100 results, concluding the universe is small. In reality, "artificial intelligence" matches thousands of 10-K filings.
**Why it happens:** edgartools' EFTS wrapper sets `limit` to 20 by default (max 100) and has no pagination beyond that single page.
**How to avoid:** Use edgartools `search_filings()` only for targeted per-company searches (e.g., "did company X mention AI?"). For the full universe scan, use a custom httpx-based EFTS client with the `from` parameter for offset pagination.
**Warning signs:** Universe size of <100 companies when expecting 200-500.

### Pitfall 4: Company Name Variations Across SEC Filing Entities
**What goes wrong:** SEC legal entity names are wildly different from common names. "ALPHABET INC" is Google's parent. "META PLATFORMS INC" used to be "FACEBOOK INC". "AMAZON COM INC" (note the space) is Amazon. Direct string matching on SEC names fails for fuzzy matching against USPTO or GitHub names.
**Why it happens:** SEC uses the exact legal entity name from incorporation documents. Each data source uses its own naming convention.
**How to avoid:** Build a normalization pipeline: (1) strip legal suffixes (Inc, Corp, LLC, Ltd, LP, Co), (2) normalize whitespace and punctuation, (3) handle common abbreviations (Intl -> International), (4) then apply rapidfuzz on the cleaned names. For the ~200-500 target universe, manual validation of fuzzy matches is feasible and recommended.
**Warning signs:** Many "unresolved" entities that should have matches. High false-positive rate in fuzzy matching.

### Pitfall 5: CIK Padding and Format Inconsistencies
**What goes wrong:** CIK numbers appear in different formats: "320193" (no padding) in company_tickers.json, "0000320193" (10-digit zero-padded) in XBRL API URLs, and "320193" (unpadded) in EFTS results. Code that stores one format and queries with another gets zero results.
**Why it happens:** SEC APIs are inconsistent in their CIK formatting.
**How to avoid:** Always store CIK as a string. Define a normalization function: `cik.lstrip("0").zfill(10)` for padded URLs, `cik.lstrip("0")` for comparison. Apply normalization at every API boundary.
**Warning signs:** XBRL API calls returning 404 for known companies.

### Pitfall 6: Determinism Broken by EFTS Relevance Scoring
**What goes wrong:** EFTS returns results sorted by Elasticsearch relevance score. The same query on different calls can return results in slightly different order, and when pagination is involved, this can cause different companies to appear on different pages.
**Why it happens:** Elasticsearch relevance scoring is not perfectly deterministic across index shards.
**How to avoid:** Do not rely on EFTS ordering for determinism. Collect ALL results (paginate fully), then deduplicate by CIK, then sort deterministically (e.g., by CIK ascending) before applying market cap filter. The determinism comes from post-processing, not from the API call order.
**Warning signs:** Universe builder producing different company counts on consecutive runs.

## Code Examples

### EFTS API Response Structure (Verified)
```python
# Source: apifyforge/edgar-filing-search + hermes project
# The EFTS API response has this structure:
{
    "hits": {
        "total": {
            "value": 3847,           # Total matches (or 10000 if capped)
            "relation": "eq"         # "eq" = exact count, "gte" = 10000+ matches
        },
        "hits": [
            {
                "_source": {
                    "accession_no": "0001234567-26-000123",
                    "form_type": "10-K",
                    "file_date": "2026-02-15",
                    "entity_name": "ACME CORP",
                    "file_num": "001-12345",
                    "ciks": ["0001234567"],
                    "period_of_report": "2025-12-31",
                    "display_names": ["ACME Corp (CIK 0001234567)"],
                }
            },
            # ... more hits
        ]
    }
}

# Query parameters sent to efts.sec.gov/LATEST/search-index:
# q="artificial intelligence" OR "machine learning"
# forms=10-K
# dateRange=custom
# startdt=2025-03-27
# enddt=2026-03-27
# from=0 (increment by 100 for pagination)
# size=100 (max per page, though some sources say 50)
```

### edgartools Company Facts for Market Cap Proxy
```python
# Source: edgartools README + XBRL API documentation
import edgar

edgar.set_identity("YourCo your@email.com")

# Method 1: Via edgartools
company = edgar.Company("AAPL")
public_float = company.public_float  # EntityPublicFloat in USD

# Method 2: Via raw XBRL API (for batch processing)
import httpx

def get_entity_public_float(cik: str) -> int | None:
    """Get EntityPublicFloat in cents from XBRL company facts."""
    padded_cik = cik.lstrip("0").zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{padded_cik}.json"
    headers = {"User-Agent": "YourCo your@email.com"}
    resp = httpx.get(url, headers=headers)
    if resp.status_code != 200:
        return None

    facts = resp.json()
    dei = facts.get("facts", {}).get("dei", {})
    float_data = dei.get("EntityPublicFloat", {})
    units = float_data.get("units", {}).get("USD", [])
    if not units:
        return None

    # Get most recent value
    latest = max(units, key=lambda x: x.get("end", ""))
    return int(latest["val"] * 100)  # Convert to cents
```

### rapidfuzz Entity Matching
```python
# Source: rapidfuzz documentation
from rapidfuzz import fuzz, process, utils

def normalize_company_name(name: str) -> str:
    """Strip legal suffixes and normalize for matching."""
    suffixes = [
        " INC", " CORP", " LLC", " LTD", " LP", " CO",
        " INC.", " CORP.", " LTD.", " CO.",
        " INCORPORATED", " CORPORATION", " LIMITED",
    ]
    upper = name.upper().strip()
    for suffix in suffixes:
        if upper.endswith(suffix):
            upper = upper[: -len(suffix)].strip()
    return upper

def resolve_entity(
    sec_name: str,
    candidates: dict[str, list[str]],  # source -> [names]
    threshold: int = 85,
) -> dict[str, str | None]:
    """Resolve SEC entity name against candidate names from each source."""
    normalized_sec = normalize_company_name(sec_name)
    aliases = {}

    for source, names in candidates.items():
        normalized_candidates = {
            normalize_company_name(n): n for n in names
        }
        match = process.extractOne(
            normalized_sec,
            list(normalized_candidates.keys()),
            scorer=fuzz.token_sort_ratio,
            score_cutoff=threshold,
        )
        if match:
            aliases[source] = normalized_candidates[match[0]]
        else:
            aliases[source] = None  # Partial resolution per D-03

    return aliases
```

### Company.aliases JSONB Schema
```python
# Source: D-02 decision
# The aliases field stores entity resolution mappings:
{
    "cik": "0001234567",               # 10-digit padded
    "patent_assignee": [                # List: companies have multiple assignee names
        "ACME CORP",
        "ACME TECHNOLOGIES LLC"
    ],
    "github_org": "acme-corp",          # GitHub organization slug, or null
    "employer_names": [                 # List: job postings use variant names
        "Acme Corp",
        "Acme Corporation",
        "ACME"
    ],
    "resolution_metadata": {
        "resolved_at": "2026-03-27",
        "method": "automated_fuzzy",    # or "manual_seed", "manual_override"
        "confidence": 0.92,             # Fuzzy match confidence
        "needs_review": false
    }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| fuzzywuzzy for string matching | rapidfuzz (drop-in, 10x faster) | 2024+ | No reason to use fuzzywuzzy in new projects |
| SEC market cap from Yahoo Finance | EntityPublicFloat from XBRL company facts API | Ongoing | Free, official, no scraping risk |
| Manual company universe lists | EFTS full-text search discovery | EFTS available since ~2020 | Automated universe construction at scale |
| edgartools pre-5.0 (limited EFTS) | edgartools 5.26.1 with search_filings() | 2025-2026 | Built-in EFTS wrapper, but still limited to 100 results |

**Deprecated/outdated:**
- **fuzzywuzzy:** GPL-licensed, pure Python. rapidfuzz is the replacement.
- **sec-api (paid):** Not needed; all functionality available through free SEC APIs + edgartools.
- **Legacy PatentsView API (api.patentsview.org):** Discontinued May 2025. Migrated to data.uspto.gov.

## Open Questions

1. **EFTS `size` parameter cap: 50 or 100?**
   - What we know: edgartools caps at 100. The apifyforge project uses 50. SEC docs do not clearly specify the max.
   - What's unclear: Whether 100 actually works or silently truncates to 50.
   - Recommendation: Start with `size=50` in the custom client. Test with 100. Use whichever works reliably.

2. **EntityPublicFloat coverage for mid-cap companies**
   - What we know: EntityPublicFloat is a required DEI tag for most SEC filers. edgartools provides `company.public_float`.
   - What's unclear: What percentage of 10-K filers actually have this tag populated in the XBRL companyfacts API? Some smaller companies may be missing it.
   - Recommendation: Fetch a sample of 50 mid-cap CIKs and check EntityPublicFloat availability. Fall back to `EntityCommonStockSharesOutstanding` if needed (requires a price source for market cap calculation).

3. **Subsidiary handling for entity resolution**
   - What we know: Large companies file patents under subsidiary names (Google LLC under Alphabet Inc). This is Claude's discretion per CONTEXT.md.
   - What's unclear: How deep the subsidiary tree goes for typical mid-cap companies.
   - Recommendation: Map subsidiaries to the parent company. Use CIK linkage where available (SEC tracks parent-subsidiary relationships in some filings). For v1, a manual mapping of known subsidiaries for the top 50 companies is pragmatic at this scale.

4. **Interaction between D-01 (curated seed + fuzzy expand) and D-07 (fully automated EDGAR scan)**
   - What we know: D-07 says the EDGAR scan is the discovery mechanism (no manual seed required). D-01 says curated mapping for top 50-100 companies.
   - What's unclear: Whether D-01's "curated seed" means a manually curated list of ENTITY MAPPINGS (aliases) for the top 50-100 companies discovered by EFTS, or a manually curated list of companies to seed the universe.
   - Recommendation: Interpret as: (1) EFTS discovers all companies (per D-07), (2) entity resolution uses fuzzy matching for all, (3) the top 50-100 by relevance get manually curated alias mappings for higher accuracy. This reconciles both decisions.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.12 | -- |
| PostgreSQL | Company table | Yes (via Docker/testcontainers) | 16 | -- |
| httpx | EFTS client, XBRL API | Yes | 0.28.1 | -- |
| edgartools | Company lookup, XBRL facts | No (not installed) | -- | Must install: `uv add edgartools` |
| rapidfuzz | Fuzzy name matching | No (not installed) | -- | Must install: `uv add rapidfuzz` |
| tenacity | Retry logic | No (not installed) | -- | Must install: `uv add tenacity` |
| Docker | Integration tests | Yes | -- | Required for testcontainers |

**Missing dependencies with no fallback:**
- edgartools, rapidfuzz, tenacity must be installed before implementation begins

**Missing dependencies with fallback:**
- None -- all missing deps have straightforward `uv add` installation

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/unit/ -x -q` |
| Full suite command | `python -m pytest tests/ -x --timeout=120` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FNDN-02-a | Entity resolver maps CIK + ticker for a known company | unit | `python -m pytest tests/unit/test_entity_resolver.py::test_resolve_cik_ticker -x` | No -- Wave 0 |
| FNDN-02-b | Fuzzy matcher finds patent assignee name from SEC name | unit | `python -m pytest tests/unit/test_fuzzy_matcher.py::test_patent_assignee_match -x` | No -- Wave 0 |
| FNDN-02-c | Aliases JSONB populated with resolution results | unit | `python -m pytest tests/unit/test_entity_resolver.py::test_aliases_jsonb_structure -x` | No -- Wave 0 |
| FNDN-02-d | Partial resolution (null fields) accepted per D-03 | unit | `python -m pytest tests/unit/test_entity_resolver.py::test_partial_resolution -x` | No -- Wave 0 |
| FNDN-03-a | EFTS client paginates beyond 100 results | unit | `python -m pytest tests/unit/test_efts_client.py::test_pagination -x` | No -- Wave 0 |
| FNDN-03-b | Market cap filter accepts companies in $2B-$10B range | unit | `python -m pytest tests/unit/test_universe_filters.py::test_market_cap_filter -x` | No -- Wave 0 |
| FNDN-03-c | Universe builder is deterministic (same day = same list) | unit | `python -m pytest tests/unit/test_universe_builder.py::test_deterministic -x` | No -- Wave 0 |
| FNDN-03-d | Discovered companies written to Company table | integration | `python -m pytest tests/integration/test_universe_builder.py::test_companies_persisted -x` | No -- Wave 0 |
| FNDN-03-e | is_active=False soft remove works per D-10 | integration | `python -m pytest tests/integration/test_company_lifecycle.py::test_soft_remove -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -x --timeout=120`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_efts_client.py` -- covers FNDN-03-a (EFTS pagination)
- [ ] `tests/unit/test_entity_resolver.py` -- covers FNDN-02-a, FNDN-02-c, FNDN-02-d
- [ ] `tests/unit/test_fuzzy_matcher.py` -- covers FNDN-02-b (rapidfuzz matching)
- [ ] `tests/unit/test_universe_filters.py` -- covers FNDN-03-b (market cap)
- [ ] `tests/unit/test_universe_builder.py` -- covers FNDN-03-c (determinism)
- [ ] `tests/integration/test_universe_builder.py` -- covers FNDN-03-d (persistence)
- [ ] `tests/integration/test_company_lifecycle.py` -- covers FNDN-03-e (soft remove)
- [ ] `pytest-httpx` already in dev dependencies -- used for mocking httpx calls to EFTS and XBRL APIs
- [ ] Framework install: `uv add --dev freezegun` (time mocking for determinism tests)

## Sources

### Primary (HIGH confidence)
- [SEC EDGAR EFTS API](https://efts.sec.gov/LATEST/search-index) - Full text search endpoint, verified via apifyforge implementation and hermes project
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) - Official XBRL companyfacts API documentation
- [SEC company_tickers.json](https://www.sec.gov/files/company_tickers.json) - CIK-ticker-name mapping file
- [edgartools GitHub](https://github.com/dgunning/edgartools) - Source code verified: search_filings() in edgar/search/efts.py, EFTSSearch/EFTSResult classes, find_company(), get_company_facts()
- [rapidfuzz GitHub](https://github.com/rapidfuzz/RapidFuzz) - v3.14.3, C++ core, MIT license
- [rapidfuzz docs](https://rapidfuzz.github.io/RapidFuzz/) - fuzz.token_sort_ratio, process.extractOne API

### Secondary (MEDIUM confidence)
- [apifyforge/edgar-filing-search](https://github.com/apifyforge/edgar-filing-search) - EFTS response structure (14 fields), pagination with `from` param, 50-result pages
- [hermes financial project](https://github.com/schnetzlerjoe/hermes) - edgartools + custom EFTS pattern: "edgartools has no EFTS" for full search, uses custom `sec_efts_get` helper
- [SEC EFTS FAQ](https://www.sec.gov/edgar/search/efts-faq.html) - Boolean operators, wildcards, NEAR() proximity search

### Tertiary (LOW confidence)
- EFTS `size` parameter max (50 vs 100) -- conflicting sources, needs live testing
- EntityPublicFloat coverage percentage across mid-cap filers -- needs empirical validation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - edgartools, httpx, rapidfuzz all verified on PyPI with current versions. EFTS API endpoint verified via multiple independent projects.
- Architecture: HIGH - Pattern follows established edgartools + custom EFTS approach used by hermes project. Entity resolution via fuzzy matching is a well-understood problem.
- Pitfalls: HIGH - EFTS pagination cap (10K) verified via Elasticsearch defaults. EntityPublicFloat vs market cap distinction verified via SEC XBRL documentation. Company name variation across SEC/USPTO/GitHub is documented in PITFALLS.md Pitfall 7.
- Market cap proxy: MEDIUM - EntityPublicFloat as market cap proxy is pragmatic but imprecise. Coverage across mid-cap filers needs validation.

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (30 days -- EDGAR APIs are stable, edgartools releases weekly but API is stable)
