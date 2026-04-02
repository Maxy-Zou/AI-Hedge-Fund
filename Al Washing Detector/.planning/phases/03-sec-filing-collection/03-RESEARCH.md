# Phase 3: SEC Filing Collection - Research

**Researched:** 2026-03-27
**Domain:** SEC EDGAR filing retrieval (10-K, 10-Q, 8-K), XBRL financial data extraction (R&D, CapEx, revenue), rate-limited batch collection with idempotent daily runs
**Confidence:** HIGH

## Summary

Phase 3 builds the SEC filing collection pipeline -- the first data ingestion layer that feeds the scoring engine. The system must retrieve full-text filings (10-K, 10-Q, 8-K) for every company in the target universe, extract structured XBRL financial data (R&D spending, CapEx, revenue), store both with correct dual timestamps (as_of_date, observed_date), and do so idempotently (re-running for the same company on the same day is a no-op).

The core technical challenge is bridging two different EDGAR data access patterns: (1) edgartools for high-level filing retrieval and section parsing (`Company.get_filings()` -> `filing.obj()` -> TenK/TenQ sections), and (2) the raw XBRL companyfacts API (`data.sec.gov/api/xbrl/companyfacts/`) for structured financial data extraction. The existing `EdgarFactsClient` from Phase 2 already wraps the XBRL companyfacts API with retry logic and rate limiting -- Phase 3 extends it to extract R&D, CapEx, and revenue tags. For filing retrieval, edgartools handles the heavy parsing (HTML to text, section extraction, XBRL standardization) so we do not need to hand-roll parsers.

A critical design decision: filing full text should be stored in the database as JSONB (structured metadata + text excerpts), not as raw HTML files on disk. At ~200-500 companies with ~3 filing types each, the volume is manageable in PostgreSQL. This aligns with the existing pattern of JSONB storage used by Company.aliases and SignalDetail.evidence. A new `Filing` ORM model with AppendOnlyMixin provides the storage layer, and the collection is scoped per-company-per-form-per-date for idempotency.

**Primary recommendation:** Use edgartools `Company(cik).get_filings(form=...)` for filing retrieval and `.obj()` for section parsing, extend EdgarFactsClient for multi-tag XBRL extraction, add a `Filing` model with AppendOnlyMixin, and implement a `FilingCollector` class that checks existing records before fetching (idempotent).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEC-01 | System ingests 10-K, 10-Q, and 8-K filings from SEC EDGAR using edgartools for target universe companies | edgartools `Company.get_filings(form=...)` retrieves filings by type; `filing.obj()` returns TenK/TenQ/EightK objects with section access; `filing.text()` provides full text for storage |
| SEC-03 | XBRL financial data extractor retrieves R&D spending, CapEx, and revenue from company facts | Existing EdgarFactsClient wraps `data.sec.gov/api/xbrl/companyfacts/`; extend to extract us-gaap tags: `ResearchAndDevelopmentExpense`, `PaymentsToAcquirePropertyPlantAndEquipment`, `Revenues`/`RevenueFromContractWithCustomerExcludingAssessedTax` with fallback tag lists per Pitfall 10 |
| SEC-05 | SEC data respects EDGAR rate limits (10 req/sec) with mandatory User-Agent header containing identity | Phase 2 already implements rate limiting in EdgarFactsClient (0.1s delay) and EFTSClient (retry on 429/5xx); edgartools has built-in 30-second caching and configurable rate limiting; User-Agent set via `AppSettings.edgar_identity` |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Language:** Python 3.11+
- **Package management:** uv preferred
- **Immutability:** Return new objects, never mutate in place; financial data must never be overwritten -- append new snapshots only
- **Data handling:** Raw data cached locally, all timestamps UTC, preserve source precision
- **Monetary values:** Stored as integers (cents) in BIGINT columns
- **SEC compliance:** EDGAR requires User-Agent with company/name + email (legal requirement)
- **Rate limits:** SEC 10 req/sec max, be conservative
- **Error handling:** Handle errors explicitly at every level, never silently swallow
- **Input validation:** Validate at system boundaries using schema-based validation (Pydantic)
- **Testing:** pytest, 80%+ coverage target, TDD workflow
- **File organization:** Many small files (200-400 lines typical, 800 max)
- **Coding style:** Immutable data patterns, functions < 50 lines, no deep nesting > 4 levels
- **Dual timestamps:** All financial data uses as_of_date (business date) + observed_date (collection date)

## Standard Stack

### Core (Phase 3-specific -- all already installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| edgartools | 5.26.1 | Filing retrieval, section parsing, TenK/TenQ/EightK objects | Already installed. `Company.get_filings(form=...)` retrieves filings; `.obj()` returns typed objects with section access (`.business`, `.risk_factors`, `.management_discussion`); `.text()` for full text; built-in 30s caching and rate limiting. |
| httpx | 0.28.1 | Direct XBRL companyfacts API calls | Already installed and used by EdgarFactsClient. Sync client with retry via tenacity. |
| tenacity | 9.1.2 | Retry logic with exponential backoff for EDGAR API calls | Already installed and used in Phase 2 clients. Same retry pattern extends to new API calls. |
| SQLAlchemy | 2.0.48+ | ORM models for Filing and XBRLFact tables | Already installed. AppendOnlyMixin from db/base.py provides dual timestamps + UUID PK. |
| Alembic | 1.18.4+ | Database migration for new tables | Already installed. Next migration is 003. |
| Pydantic | 2.12.5 | Type contracts for filing data and XBRL facts | Already installed. Schema validation at ingestion boundary. |

### Supporting (already installed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | 25.5.0+ | Structured logging for collection progress | Log per-company fetch status, XBRL tag extraction, idempotency skips |
| beautifulsoup4 + lxml | latest | HTML parsing for filing sections not handled by edgartools | Fallback for filing content extraction if edgartools section parser fails on specific filings |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| edgartools for filing retrieval | Direct EDGAR filing API + httpx | Enormous parsing burden. edgartools handles 20+ filing types, section extraction, XBRL standardization. No benefit to reimplementing. |
| XBRL companyfacts API for financial data | edgartools `Company.get_facts().to_pandas()` | edgartools wraps this same API but returns DataFrames. For our use case (extracting specific tags for storage), direct JSON parsing is simpler and avoids pandas dependency in the ingestion layer. |
| Storing filing text in DB | Storing filing HTML as files on disk | At 200-500 companies x 3 form types, DB storage is manageable. JSONB enables querying. File storage adds filesystem management complexity for minimal benefit at this scale. |

**No new dependencies required.** All packages needed for Phase 3 are already in pyproject.toml from Phases 1-2.

## Architecture Patterns

### Recommended Project Structure (Phase 3 additions)
```
src/ai_washer/
  ingestion/
    __init__.py            # Updated: export new classes
    efts_client.py         # Existing (unchanged)
    edgar_client.py        # Existing: EXTENDED with multi-tag XBRL extraction
    filing_client.py       # NEW: edgartools wrapper for filing retrieval (~250 lines)
    types.py               # NEW: Pydantic schemas for filing data, XBRL facts (~200 lines)
  db/
    models.py              # EXTENDED: add Filing and XBRLFact models
    migrations/versions/
      003_add_filing_tables.py  # NEW: migration for sec_filings, xbrl_facts tables
  config.py                # EXTENDED: add FilingCollectionSettings
  cli.py                   # EXTENDED: add filing collection CLI commands
```

### Pattern 1: Filing Retrieval via edgartools
**What:** Use edgartools to retrieve filings by form type for a company, extract section text from the typed filing object, and store structured metadata + text excerpts.
**When to use:** Every filing collection operation for 10-K, 10-Q, 8-K filings.
**Why:** edgartools handles all the complexity of EDGAR filing access: filing index pagination, HTML/SGML parsing, section identification, and XBRL extraction. Reimplementing any of this would be months of work.
**Example:**
```python
# Source: edgartools documentation + vincent.codes.finance tutorial
import edgar

edgar.set_identity("YourCo email@example.com")

company = edgar.Company("AAPL")

# Get most recent 10-K filings
tenk_filings = company.get_filings(form="10-K")
latest_tenk = tenk_filings.latest(1)

# Convert to typed object for section access
filing = latest_tenk[0]
tenk = filing.obj()  # Returns TenK object

# Access specific sections
business = tenk["Item 1"]        # Business Description
risk_factors = tenk["Item 1A"]   # Risk Factors
mda = tenk["Item 7"]             # Management Discussion & Analysis

# Get filing metadata
accession_no = filing.accession_number
filing_date = filing.filing_date
period_of_report = filing.period_of_report

# Get full text (for keyword analysis in Phase 4)
full_text = filing.text()
```

### Pattern 2: XBRL Multi-Tag Financial Data Extraction
**What:** Extend the existing EdgarFactsClient to extract multiple us-gaap financial concepts (R&D, CapEx, revenue) from the companyfacts API, with fallback tag lists for each concept.
**When to use:** For every company in the target universe, extract key financial metrics from XBRL data.
**Why:** Companies use different XBRL tags for the same economic concept (Pitfall 10). A fallback list of tags per concept handles this variability without manual per-company configuration.
**Example:**
```python
# Source: SEC EDGAR companyfacts API documentation
# Response structure for data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json:
#
# {
#   "cik": 320193,
#   "entityName": "Apple Inc.",
#   "facts": {
#     "dei": { ... },
#     "us-gaap": {
#       "ResearchAndDevelopmentExpense": {
#         "label": "Research and Development Expense",
#         "units": {
#           "USD": [
#             {
#               "end": "2025-09-27",
#               "val": 31370000000,   # in dollars (not cents)
#               "accn": "0000320193-25-000106",
#               "fy": 2025,
#               "fp": "FY",
#               "form": "10-K",
#               "filed": "2025-11-01",
#               "frame": "CY2025"
#             },
#             ...
#           ]
#         }
#       },
#       ...
#     }
#   }
# }

# Tag fallback lists per financial concept:
XBRL_TAG_GROUPS = {
    "rd_expense": [
        "ResearchAndDevelopmentExpense",
        "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "CapitalExpenditureDiscontinuedOperations",
    ],
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
}
```

### Pattern 3: Idempotent Daily Collection
**What:** Before fetching any filing or XBRL data, check if a record already exists for this company + form type + date combination. Skip if found.
**When to use:** Every collection run. Success Criterion 4 requires this.
**Why:** Daily batch runs must be re-runnable without side effects. A company processed at 2 AM should not be re-fetched if the run restarts at 4 AM.
**Example:**
```python
# Idempotency check pattern
def _already_collected(
    session: Session,
    company_id: uuid.UUID,
    form_type: str,
    collection_date: date,
) -> bool:
    """Check if a filing was already collected for this company/form/date."""
    stmt = select(Filing).where(
        Filing.company_id == company_id,
        Filing.form_type == form_type,
        Filing.observed_date == collection_date,
    )
    return session.execute(stmt).scalar_one_or_none() is not None
```

### Pattern 4: Two-Layer Storage (Filings + XBRL Facts)
**What:** Store filing metadata and text excerpts in a `sec_filings` table, and store extracted XBRL financial facts in a separate `xbrl_facts` table. Both use AppendOnlyMixin (dual timestamps, UUID PK, immutable).
**When to use:** All SEC data storage. Filings hold text content; XBRL facts hold numerical financial data.
**Why:** Separation of concerns: filing text feeds Phase 4's keyword analysis (SEC-02), while XBRL facts feed Phase 4's R&D gap scoring (SEC-04, COMP-01). Different query patterns, different update cadences.

### Anti-Patterns to Avoid
- **Fetching all filings for all companies in a single pass:** edgartools creates HTTP connections per Company object. Iterate per-company with rate limiting, not in a giant batch.
- **Storing raw HTML in the database:** Filing HTML can be 1-10 MB. Store structured text excerpts (sections) and metadata, not raw HTML. edgartools' `.text()` and section accessors extract what we need.
- **Relying solely on edgartools for XBRL fact extraction:** edgartools' `get_facts().to_pandas()` works but introduces pandas into the ingestion layer. For storing specific tags, use the raw companyfacts JSON (already wrapped by EdgarFactsClient) and extract the tags we need directly.
- **Using filing `period_of_report` as `as_of_date`:** Use `filing.filing_date` (the date the filing became publicly available) as `observed_date`, and `period_of_report` as `as_of_date`. This prevents look-ahead bias per Pitfall 2.
- **Making the XBRL extraction depend on filing retrieval:** XBRL companyfacts API returns all historical facts in one call, independent of individual filings. Fetch XBRL facts separately, not by parsing each filing's inline XBRL.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SEC filing HTML parsing | Custom HTML parser for 10-K sections | edgartools `filing.obj()` -> TenK/TenQ section accessors | edgartools handles 20+ filing types, SGML, and HTML variants. Section extraction is brittle -- edgartools has been battle-tested on 32K+ filings. |
| XBRL taxonomy normalization | Custom XBRL XML parser | `data.sec.gov/api/xbrl/companyfacts/` JSON API (already wrapped by EdgarFactsClient) | The SEC pre-normalizes XBRL into JSON. Parsing raw XBRL XML is enormously complex. The JSON API gives us what we need. |
| Rate limiting for EDGAR | Custom rate limiter with time.sleep() | tenacity `@retry` with `wait_exponential` + edgartools built-in rate limiting | Both are already implemented in Phase 2 code. Reuse, don't rewrite. |
| Filing accession number parsing | Custom regex for accession number format | edgartools `filing.accession_number` property | Accession numbers have a specific format (CIK-YY-NNNNNN) that edgartools normalizes. |
| Company-to-CIK resolution for filing lookup | Manual CIK lookup from company_tickers.json | Company model already stores CIK in aliases JSONB (Phase 2) | The universe builder already resolved CIK for every company. Use the stored CIK. |

**Key insight:** Phase 2 built the discovery infrastructure (EFTS search, CIK resolution, market cap filtering). Phase 3 uses the discovered universe to collect data. The CIK stored in Company.aliases is the key that links everything.

## Common Pitfalls

### Pitfall 1: edgartools Section Parser Misidentifying Sections
**What goes wrong:** edgartools' TenK section accessor (e.g., `tenk["Item 7"]` for MD&A) sometimes grabs the table of contents entry instead of the actual section content. This is a known issue mentioned in PITFALLS.md (Pitfall 5).
**Why it happens:** 10-K HTML structure varies wildly between companies and filing years. Some use `<a>` anchors, others use headers, some embed sections in tables.
**How to avoid:** Validate that extracted section text length is reasonable (MD&A should be thousands of characters, not dozens). If a section is suspiciously short (< 500 chars), log a warning and store the full filing text as a fallback. Do not fail the entire collection for a section parsing issue.
**Warning signs:** Section text that looks like "Item 7. Management's Discussion and Analysis of Financial Condition" with no actual discussion content.

### Pitfall 2: XBRL Tag Inconsistency Across Companies (from Pitfall 10)
**What goes wrong:** Companies use different XBRL tags for the same financial concept. "ResearchAndDevelopmentExpense" is the standard tag, but companies may use `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost` or even custom extensions.
**Why it happens:** XBRL taxonomy allows custom extensions. Companies choose tags based on their specific accounting treatment.
**How to avoid:** Define ordered fallback lists per concept (see XBRL_TAG_GROUPS above). Try the most common tag first, fall back to alternatives. Store which tag was actually found (`matched_tag` field) so anomalies can be investigated. Flag companies where R&D is $0 or null -- almost always a tag mismatch, not zero R&D.
**Warning signs:** R&D expense returning None for a technology company that clearly has R&D spending.

### Pitfall 3: XBRL Duplicate Entries for Same Fiscal Period
**What goes wrong:** The companyfacts API returns all accepted filings' data. When a company amends a filing (10-K/A), both the original and amended values appear. Restated figures also create duplicates.
**Why it happens:** EDGAR keeps all accepted filing data, never removing superseded values.
**How to avoid:** When extracting facts for a concept, filter by `form` type (prefer "10-K" over "10-K/A"), then take the entry with the latest `filed` date for each `end` date period. This gives the most recently filed value for each fiscal period. Also filter by `fp` (fiscal period) to distinguish annual ("FY") from quarterly ("Q1", "Q2", "Q3", "Q4") data.
**Warning signs:** Multiple entries with the same `end` date but different `val` values.

### Pitfall 4: Look-Ahead Bias in Timestamp Assignment (from Pitfall 2)
**What goes wrong:** Using `period_of_report` (the fiscal period end date) as the date the data was "known" creates look-ahead bias. A 10-K for fiscal year ending Dec 31, 2025 is typically filed in Feb-Mar 2026. Using Dec 31 as the signal date means the backtest "sees" data 60-90 days before it was publicly available.
**Why it happens:** Developers conflate "when the data represents" with "when the data was available."
**How to avoid:** Store BOTH dates using the dual timestamp pattern: `as_of_date` = `period_of_report` (what period this data covers) and `observed_date` = `filing_date` (when SEC published it). Downstream scoring and backtesting must use `observed_date` to determine data availability.
**Warning signs:** Filing `observed_date` before its `as_of_date` -- this is expected and correct for annual/quarterly filings.

### Pitfall 5: edgartools Identity Not Set Before API Calls
**What goes wrong:** edgartools requires `edgar.set_identity()` to be called before any API access. Without it, calls may fail with 403 or return empty results. The identity is a module-level global, not per-client.
**Why it happens:** edgartools uses a module-level identity that must be initialized before use. It is separate from the httpx User-Agent header used by EdgarFactsClient.
**How to avoid:** Call `edgar.set_identity(app_settings.edgar_identity)` at the entry point of any code path that uses edgartools directly. The filing client should do this in its `__init__` or as a context manager setup.
**Warning signs:** 403 errors or empty filing lists when using edgartools.

### Pitfall 6: Large Filing Content Overwhelming Database
**What goes wrong:** A typical 10-K filing's full text can be 200K-500K characters. Storing full text for 200-500 companies x 3 form types x multiple years could bloat the database.
**Why it happens:** The temptation to store "everything" for future analysis.
**How to avoid:** Store structured excerpts, not full text. For Phase 3 storage: (1) filing metadata (accession_no, form_type, dates, CIK), (2) section excerpts (MD&A, Risk Factors, Business -- limited to first 50K chars each), (3) a `content_hash` for deduplication. Full text is available on-demand from EDGAR via the accession number if needed later.
**Warning signs:** Database size growing faster than expected; slow queries on filing text columns.

## Code Examples

### edgartools Filing Retrieval for a Company
```python
# Source: edgartools documentation, vincent.codes.finance tutorial
import edgar
from edgar import Company

# Must set identity before any edgartools API calls
edgar.set_identity("YourCo email@example.com")

# Look up company by CIK (stored in Company.aliases from Phase 2)
company = Company(cik_or_ticker)

# Get recent 10-K filings (returns a Filings collection)
tenk_filings = company.get_filings(form="10-K")
latest_tenk = tenk_filings.latest(1)  # Most recent 1

# Access filing metadata
filing = latest_tenk[0]
accession_no = filing.accession_number   # "0000320193-25-000106"
filing_date = filing.filing_date         # date object
period = filing.period_of_report         # date object (fiscal period end)
form_type = filing.form                  # "10-K"

# Convert to typed object for section access
tenk = filing.obj()  # Returns TenK object

# Access sections via bracket notation
business_text = tenk["Item 1"]           # Business Description
risk_text = tenk["Item 1A"]              # Risk Factors
mda_text = tenk["Item 7"]               # MD&A

# Or use convenience properties (when available)
# tenk.business, tenk.risk_factors, tenk.management_discussion

# Full text for storage
full_text = filing.text()
```

### XBRL Financial Fact Extraction with Fallback Tags
```python
# Source: SEC EDGAR companyfacts API documentation
# Extension of existing EdgarFactsClient pattern

def extract_xbrl_facts(
    facts_json: dict,
    tag_group: list[str],
    form_filter: str | None = "10-K",
) -> list[dict]:
    """Extract XBRL facts for the first matching tag in a tag group.

    Args:
        facts_json: Raw companyfacts JSON response.
        tag_group: Ordered list of us-gaap tags to try.
        form_filter: Optional form type filter (e.g., "10-K").

    Returns:
        List of fact dicts with keys: end, val, filed, form, fy, fp, accn, tag.
    """
    us_gaap = facts_json.get("facts", {}).get("us-gaap", {})

    for tag in tag_group:
        tag_data = us_gaap.get(tag, {})
        usd_entries = tag_data.get("units", {}).get("USD", [])

        if not usd_entries:
            continue

        # Filter by form type if specified
        if form_filter:
            entries = [e for e in usd_entries if e.get("form") == form_filter]
        else:
            entries = usd_entries

        if not entries:
            continue

        # Deduplicate: for each (end, fp) pair, keep latest filed date
        deduped = _deduplicate_by_period(entries)

        # Attach which tag was matched
        return [
            {**entry, "matched_tag": tag}
            for entry in deduped
        ]

    return []  # No matching tag found


def _deduplicate_by_period(entries: list[dict]) -> list[dict]:
    """For duplicate (end, fp) combinations, keep the latest filed date."""
    best: dict[tuple[str, str], dict] = {}
    for entry in entries:
        key = (entry.get("end", ""), entry.get("fp", ""))
        existing = best.get(key)
        if existing is None or entry.get("filed", "") > existing.get("filed", ""):
            best[key] = entry
    return list(best.values())
```

### Filing ORM Model (AppendOnlyMixin pattern)
```python
# Source: existing db/models.py patterns from Phase 1-2

class Filing(AppendOnlyMixin, Base):
    """Append-only SEC filing record with text excerpts.

    Stores filing metadata and section text for downstream analysis.
    One row per company per form type per filing date.
    """
    __tablename__ = "sec_filings"
    __table_args__ = (
        Index(
            "ix_sec_filings_company_form_observed",
            "company_id", "form_type", "observed_date",
        ),
        # Unique constraint for idempotency
        Index(
            "uq_sec_filings_company_form_accession",
            "company_id", "form_type", "accession_no",
            unique=True,
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    form_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "10-K", "10-Q", "8-K"
    accession_no: Mapped[str] = mapped_column(String(25), nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_of_report: Mapped[date | None] = mapped_column(Date, nullable=True)
    sections: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # sections schema: {"business": "...", "risk_factors": "...", "mda": "...", ...}
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collection_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
```

### Idempotent Collection Check
```python
# Source: project pattern from Phase 2 (UniverseBuilder.persist)

def collect_filings_for_company(
    company: Company,
    collection_date: date,
    session: Session,
    filing_client: FilingClient,
) -> CollectionResult:
    """Collect all filing types for one company, skipping already-collected."""
    results = []

    for form_type in ["10-K", "10-Q", "8-K"]:
        # Idempotency: check if already collected today
        existing = session.execute(
            select(Filing).where(
                Filing.company_id == company.id,
                Filing.form_type == form_type,
                Filing.observed_date == collection_date,
            )
        ).scalar_one_or_none()

        if existing is not None:
            logger.info(
                "filing_already_collected",
                company=company.ticker,
                form_type=form_type,
                date=str(collection_date),
            )
            continue

        # Fetch and store
        filing_data = filing_client.get_latest_filing(
            cik=company.cik,
            form_type=form_type,
        )
        if filing_data is not None:
            filing_record = Filing(
                company_id=company.id,
                form_type=form_type,
                accession_no=filing_data.accession_no,
                filing_date=filing_data.filing_date,
                period_of_report=filing_data.period_of_report,
                sections=filing_data.sections,
                content_hash=filing_data.content_hash,
                as_of_date=filing_data.period_of_report or filing_data.filing_date,
                observed_date=collection_date,
            )
            session.add(filing_record)
            results.append(filing_record)

    return CollectionResult(filings=results)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw EDGAR HTTP scraping + regex for sections | edgartools typed objects (TenK, TenQ) with section accessors | edgartools 5.x (2025-2026) | Section extraction is reliable and maintained by library authors |
| Parsing raw XBRL XML from filings | SEC companyfacts JSON API (pre-normalized) | Available since 2020, stabilized 2024+ | No need to parse XBRL XML; JSON API returns structured facts |
| Single XBRL tag per concept | Fallback tag lists per financial concept | Ongoing best practice | Handles taxonomy variation across companies |
| Storing full filing HTML | Structured excerpts in JSONB + on-demand full text via accession number | Current best practice | Manageable DB size while preserving queryability |

**Deprecated/outdated:**
- **Raw XBRL XML parsing:** Use the companyfacts JSON API instead.
- **sec-api (paid):** All functionality available free via edgartools + direct EDGAR APIs.
- **Storing period_of_report as the "available" date:** Always use filing_date for when data became public.

## Open Questions

1. **edgartools Section Accessor Reliability for Mid-Cap Companies**
   - What we know: edgartools TenK section parsing works well for large-cap companies with standard filing formats. Tested against Apple, Microsoft, etc.
   - What's unclear: How well does it handle mid-cap companies with non-standard HTML formatting? Some smaller filers use unusual filing structures.
   - Recommendation: Implement a fallback strategy: if `tenk["Item 7"]` returns < 500 chars, log a warning and try `filing.text()` as full-text fallback. Track failure rates per company to identify persistent parsing issues.

2. **XBRL Fact Coverage for Revenue Tag Across Companies**
   - What we know: `Revenues` was the traditional tag, but ASC 606 (adopted 2018-2020) introduced `RevenueFromContractWithCustomerExcludingAssessedTax` as the preferred tag.
   - What's unclear: What percentage of our mid-cap universe uses which tag? Some may still use the older tag.
   - Recommendation: The fallback tag list handles this (try new tag first, fall back to old). Log which tag matched per company to build a mapping over time.

3. **8-K Filing Volume and Relevance**
   - What we know: 8-K is a "current report" filed for material events. Companies may file 20-50+ 8-Ks per year. Most are irrelevant to AI washing (e.g., director resignations, dividend declarations).
   - What's unclear: Whether to collect ALL 8-Ks or filter to specific event types (Item 2.02 for earnings, Item 7.01/8.01 for press releases mentioning AI).
   - Recommendation: For Phase 3 (collection only), collect the most recent 5-10 8-Ks per company. Phase 4 (scoring) will determine which are relevant. Storage cost is low since 8-Ks are much shorter than 10-Ks.

4. **edgartools Company Lookup by CIK vs Ticker**
   - What we know: `Company("AAPL")` works for ticker lookup. `Company(cik=320193)` should work for CIK lookup. Our universe stores CIK in Company.aliases.
   - What's unclear: Whether edgartools CIK lookup is as reliable as ticker lookup for all companies.
   - Recommendation: Use CIK for lookup (authoritative per Phase 2 decision). Fall back to ticker if CIK lookup fails. Log discrepancies.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| edgartools | Filing retrieval, section parsing | Yes | 5.26.1 | -- |
| httpx | XBRL companyfacts API | Yes | 0.28.1 | -- |
| tenacity | Retry logic | Yes | 9.1.2 | -- |
| SQLAlchemy | ORM models | Yes | 2.0.48+ | -- |
| Alembic | Database migration | Yes | 1.18.4+ | -- |
| PostgreSQL (via Docker) | Data storage, integration tests | Yes (Docker 29.0.1) | 16 | -- |
| pytest | Test framework | Yes | 9.0.2 | -- |
| pytest-httpx | Mock HTTP calls | Yes | 0.36.0+ | -- |
| freezegun | Time mocking | Yes | 1.5.5+ | -- |

**Missing dependencies with no fallback:** None -- all required packages are already installed.

**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/unit/ -x -q` |
| Full suite command | `python -m pytest tests/ -x --timeout=120` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEC-01-a | FilingClient retrieves 10-K filing for a known company | unit | `python -m pytest tests/unit/test_filing_client.py::test_get_tenk_filing -x` | No -- Wave 0 |
| SEC-01-b | FilingClient retrieves 10-Q filing and extracts sections | unit | `python -m pytest tests/unit/test_filing_client.py::test_get_tenq_sections -x` | No -- Wave 0 |
| SEC-01-c | FilingClient retrieves 8-K filing | unit | `python -m pytest tests/unit/test_filing_client.py::test_get_eightk_filing -x` | No -- Wave 0 |
| SEC-01-d | Filing model stores filing with correct dual timestamps | unit | `python -m pytest tests/unit/test_filing_models.py::test_filing_dual_timestamps -x` | No -- Wave 0 |
| SEC-01-e | Filing collection stores filings for a company in DB | integration | `python -m pytest tests/integration/test_filing_collection.py::test_filing_persisted -x` | No -- Wave 0 |
| SEC-03-a | XBRL extractor retrieves R&D expense with tag fallback | unit | `python -m pytest tests/unit/test_xbrl_extractor.py::test_rd_expense_extraction -x` | No -- Wave 0 |
| SEC-03-b | XBRL extractor retrieves CapEx with tag fallback | unit | `python -m pytest tests/unit/test_xbrl_extractor.py::test_capex_extraction -x` | No -- Wave 0 |
| SEC-03-c | XBRL extractor retrieves revenue with tag fallback | unit | `python -m pytest tests/unit/test_xbrl_extractor.py::test_revenue_extraction -x` | No -- Wave 0 |
| SEC-03-d | XBRL facts stored with correct dual timestamps | unit | `python -m pytest tests/unit/test_filing_models.py::test_xbrl_fact_dual_timestamps -x` | No -- Wave 0 |
| SEC-03-e | XBRL deduplication handles amended filings | unit | `python -m pytest tests/unit/test_xbrl_extractor.py::test_deduplication_amended -x` | No -- Wave 0 |
| SEC-03-f | XBRL facts persisted to database | integration | `python -m pytest tests/integration/test_filing_collection.py::test_xbrl_facts_persisted -x` | No -- Wave 0 |
| SEC-05-a | All HTTP requests include User-Agent header | unit | `python -m pytest tests/unit/test_filing_client.py::test_user_agent_header -x` | No -- Wave 0 |
| SEC-05-b | Rate limiting prevents 403 errors (mock 10+ rapid requests) | unit | `python -m pytest tests/unit/test_filing_client.py::test_rate_limiting -x` | No -- Wave 0 |
| SEC-05-c | Retry logic handles 429 and 5xx errors | unit | `python -m pytest tests/unit/test_filing_client.py::test_retry_on_transient_error -x` | No -- Wave 0 (reuse Phase 2 pattern) |
| IDEMPOTENT-a | Re-running collection for same company+date skips re-fetch | unit | `python -m pytest tests/unit/test_filing_collector.py::test_idempotent_skip -x` | No -- Wave 0 |
| IDEMPOTENT-b | Idempotency verified via integration test | integration | `python -m pytest tests/integration/test_filing_collection.py::test_idempotent_rerun -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -x --timeout=120`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_filing_client.py` -- covers SEC-01-a/b/c, SEC-05-a/b/c
- [ ] `tests/unit/test_filing_models.py` -- covers SEC-01-d, SEC-03-d
- [ ] `tests/unit/test_xbrl_extractor.py` -- covers SEC-03-a/b/c/e
- [ ] `tests/unit/test_filing_collector.py` -- covers IDEMPOTENT-a
- [ ] `tests/integration/test_filing_collection.py` -- covers SEC-01-e, SEC-03-f, IDEMPOTENT-b
- [ ] `src/ai_washer/ingestion/types.py` -- Pydantic schemas for filing data, XBRL facts (typed contracts before implementation)
- [ ] Existing `tests/conftest.py` and `tests/integration/conftest.py` provide all shared fixtures needed

*(No new framework install needed -- all test dependencies are already installed)*

## Sources

### Primary (HIGH confidence)
- [edgartools GitHub](https://github.com/dgunning/edgartools) - v5.26.1, MIT license, Filing.obj() returns TenK/TenQ/EightK typed objects with section accessors
- [edgartools PyPI](https://pypi.org/project/edgartools/) - v5.26.1 verified installed in project
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) - Official companyfacts API documentation
- [SEC EDGAR Accessing Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) - Rate limit policy (10 req/sec), User-Agent requirements
- [SEC EDGAR Developer Resources](https://www.sec.gov/about/developer-resources) - companyconcept and companyfacts endpoint specifications
- [The Full Stack Accountant - Intro to EDGAR API](https://www.thefullstackaccountant.com/blog/intro-to-edgar) - companyfacts JSON structure verified: facts -> us-gaap -> tag -> units -> USD -> [{end, val, accn, fy, fp, form, filed, frame}]
- [EDGAR XBRL Guide March 2026](https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide.pdf) - XBRL taxonomy specifications, tag naming conventions
- Existing codebase: `EdgarFactsClient` (src/ai_washer/ingestion/edgar_client.py) -- already wraps XBRL companyfacts API with retry and rate limiting

### Secondary (MEDIUM confidence)
- [Vincent Codes Finance - edgartools tutorial](https://vincent.codes.finance/posts/edgartools/) - Practical examples of Company.get_filings(), filing.obj(), section access, XBRL data
- [XBRL US Revenue Guidance](https://xbrl.us/data-rule/guid-revenue/) - Revenue tag naming conventions (RevenueFromContractWithCustomerExcludingAssessedTax vs Revenues)
- [SEC XBRL Custom Tags Trend](https://www.sec.gov/data-research/gaap-xbrl-custom-tags) - Custom tag usage trends across filers

### Tertiary (LOW confidence)
- edgartools section parser reliability for mid-cap companies -- needs empirical validation during implementation
- 8-K filtering strategy (which Item types are relevant) -- needs Phase 4 scoring requirements to determine

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All dependencies already installed and used in Phase 2. edgartools API verified via PyPI, GitHub, and tutorials. XBRL companyfacts API structure verified via official SEC docs and The Full Stack Accountant tutorial.
- Architecture: HIGH - Filing retrieval pattern follows edgartools documented API. XBRL extraction extends existing EdgarFactsClient. ORM models follow established Phase 1-2 patterns (AppendOnlyMixin, JSONB storage).
- Pitfalls: HIGH - XBRL tag inconsistency documented by SEC XBRL Guide and PITFALLS.md (Pitfall 10). Look-ahead bias documented in PITFALLS.md (Pitfall 2). edgartools section parser issues documented in PITFALLS.md (Pitfall 5).
- Idempotency: HIGH - Pattern matches Phase 2's UniverseBuilder.persist (check-before-write with database query). Standard approach for daily batch systems.

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (30 days -- EDGAR APIs are stable, edgartools releases weekly but API surface is stable)
