# Phase 2: Entity Resolution and Universe Builder - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Identify which mid-cap companies are making AI claims (universe builder) and map each company's identity across SEC (CIK), USPTO (patent assignee), GitHub (org), and job postings (employer name) into a unified record (entity resolution). No signal collection, no scoring — just finding and mapping companies.

</domain>

<decisions>
## Implementation Decisions

### Entity Mapping Strategy
- **D-01:** Curated seed + fuzzy expand approach — start with manually curated mapping for top 50-100 companies, use fuzzy matching (e.g., fuzzywuzzy/rapidfuzz on company names) to expand. Edge cases validated by humans.
- **D-02:** Use existing Company.aliases JSONB field for mapping storage: `{"cik": "...", "patent_assignee": ["..."], "github_org": "...", "employer_names": ["..."]}`. No separate mapping table needed.
- **D-03:** Companies with partial resolution (e.g., no GitHub org found) are included in the universe with null fields. Downstream composite scoring handles missing signals via graceful degradation.

### Universe Construction
- **D-04:** Market cap sourced from SEC EDGAR XBRL company facts API (free, via edgartools). May be quarterly-stale — acceptable for mid-cap filtering.
- **D-05:** EDGAR full-text search (efts.sec.gov) for "artificial intelligence" OR "machine learning" in 10-K filings from last 12 months. Filter results to $2B-$10B market cap.
- **D-06:** Universe builder must be deterministic — same day = same target list.

### Data Seeding
- **D-07:** Fully automated EDGAR scan to discover companies. No manual seed list required upfront — the EDGAR search IS the discovery mechanism. Manual curation can follow.
- **D-08:** All discovered companies added to the Company table immediately. No human review gate before insertion.

### Refresh Cadence
- **D-09:** Universe re-scanned monthly. AI washing is slow-moving; new 10-Ks file quarterly. Monthly catches new filers without excessive API usage.
- **D-10:** Delistings, mergers, and market cap changes handled via soft remove — mark as `is_active=False` with reason. Never delete. Consistent with Phase 1 append-only design.

### Claude's Discretion
- Exact fuzzy matching threshold and algorithm (rapidfuzz vs fuzzywuzzy vs custom)
- EDGAR full-text search pagination strategy
- How to handle subsidiaries (map to parent company or track separately)
- CLI commands for manual universe management (add/remove/inspect companies)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — Core value, constraints, integration pattern
- `.planning/REQUIREMENTS.md` — FNDN-02 (entity resolution), FNDN-03 (universe builder) acceptance criteria
- `ai_washing_detector_research.md` §2 Signal 1 (job posting data sources), §4 (target universe approach)

### Research
- `.planning/research/STACK.md` — edgartools for SEC EDGAR, httpx for APIs
- `.planning/research/ARCHITECTURE.md` — Component boundaries, entity resolution as critical path
- `.planning/research/PITFALLS.md` — Entity resolution complexity, ghost job posting implications

### Phase 1 Artifacts
- `.planning/phases/01-project-skeleton-and-database/01-CONTEXT.md` — Package structure (src/ai_washer/), DB design decisions
- `src/ai_washer/db/models.py` — Existing Company model with aliases JSONB field
- `src/ai_washer/db/base.py` — Base class, DualTimestampMixin, AppendOnlyMixin
- `src/ai_washer/config.py` — AppSettings pattern for environment config

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Company` model in `src/ai_washer/db/models.py` — already has `cik`, `ticker`, `name`, `sector`, `market_cap_cents` (BIGINT), `is_active` (Boolean), `aliases` (JSONB), `as_of_date`, `observed_date`
- `AppSettings` in `src/ai_washer/config.py` — pattern for EDGAR identity config (User-Agent header)
- `create_engine_from_settings()` and `get_session_factory()` in `src/ai_washer/db/session.py`
- Typer CLI in `src/ai_washer/cli.py` — can add `universe` subcommand group

### Established Patterns
- Pydantic for all data validation
- structlog for structured JSON logging
- UUID primary keys on all models
- Append-only / dual timestamps on financial data

### Integration Points
- New modules go in `src/ai_washer/` (entity_resolver.py, universe_builder.py, or similar)
- EDGAR identity (company name + email) needed in AppSettings for SEC API compliance
- CLI commands for running universe scans manually

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. Research identified entity resolution as the critical path blocker for all multi-signal scoring.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-entity-resolution-and-universe-builder*
*Context gathered: 2026-03-27*
