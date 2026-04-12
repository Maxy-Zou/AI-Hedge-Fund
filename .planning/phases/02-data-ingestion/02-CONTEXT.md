# Phase 2: Data Ingestion - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Agents can query any of the fund's data sources and receive pre-processed, temporally-correct financial data -- so research agents never touch raw APIs and never see future data. This phase builds the complete data layer: SEC filings (10-K, 10-Q, 8-K) via edgartools, XBRL financial extraction via CompanyFacts API, equity price caching (yfinance → PostgreSQL), insider trade detection from Form 4, news/sentiment from Finnhub, and macro data from FRED. Every tool enforces a mandatory as_of_date parameter to prevent look-ahead bias.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints from PROJECT.md and CLAUDE.md:
- Every data input must have a timestamp; RAG retrieval filtered by "available as of analysis date"
- Always use filing date (not period end date) for SEC data — prevents look-ahead bias
- Always use adjusted close prices for return calculations
- Pre-process structured data into natural language summaries before LLM consumption
- Raw data cached locally (PostgreSQL) to avoid redundant API calls
- Append-only for financial time-series data (never overwrite historical observations)
- Dual timestamps where relevant: business date (as_of_date) vs. collection date (observed_date)
- Free data stack for v1: SEC EDGAR, yfinance, Finnhub (60 req/min), FMP (250 calls/day), FRED

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Architecture
- `CLAUDE.md` — Data handling rules, temporal controls, data source priority table
- `.planning/PROJECT.md` — Constraints on data budget, free tier limits
- `.planning/REQUIREMENTS.md` — DATA-01 through DATA-08 acceptance criteria
- `.planning/ROADMAP.md` — Phase 2 success criteria (5 verifiable conditions)

### Phase 1 Foundation (Dependencies)
- `src/ai_hedge_fund/config.py` — AppSettings, database_url, API key management
- `src/ai_hedge_fund/db/base.py` — DeclarativeBase, AppendOnlyMixin, DualTimestampMixin
- `src/ai_hedge_fund/db/session.py` — Engine and session factory
- `src/ai_hedge_fund/schemas/` — Existing Pydantic schema patterns

### Prior Work (Reference Patterns)
- `archive/2026-04-11-pre-pivot/Al Washing Detector/src/ai_washer/ingestion/` — EDGAR client, XBRL extractor, filing collector patterns
- `archive/2026-04-11-pre-pivot/Al Washing Detector/src/ai_washer/db/models.py` — SQLAlchemy model patterns

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- AppendOnlyMixin and DualTimestampMixin in db/base.py — use for all financial time-series tables
- SQLAlchemy session factory in db/session.py — reuse for data ingestion queries
- AppSettings in config.py — extend with data source API keys
- Prior EDGAR integration code in archive (edgartools, XBRL extraction)

### Established Patterns
- Pydantic BaseModel for all data schemas with validation
- Immutable data patterns (frozen dataclasses, new object returns)
- structlog for logging
- Type hints on all functions

### Integration Points
- Data tools will be called by PydanticAI agents (from Phase 1)
- All tools need as_of_date parameter (mandatory, per CLAUDE.md)
- Results stored in PostgreSQL (via docker-compose.yml)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase, no discussion occurred.

</deferred>

---

*Phase: 02-data-ingestion*
*Context gathered: 2026-04-12 via autonomous mode (infrastructure skip)*
