# Phase 2: Entity Resolution and Universe Builder - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 02-entity-resolution-and-universe-builder
**Areas discussed:** Entity mapping strategy, Universe construction, Data seeding approach, Refresh cadence

---

## Entity Mapping Strategy

### Q1: How to map companies across data sources?

| Option | Description | Selected |
|--------|-------------|----------|
| Curated seed + fuzzy expand (Recommended) | Start with manually curated mapping for top 50-100, use fuzzy matching to expand | ✓ |
| Fully automated fuzzy | Automated fuzzy matching on company names — faster but higher false-positive rate | |
| Manual-only mapping table | Hand-curated CSV/YAML — most accurate but doesn't scale | |

**User's choice:** Curated seed + fuzzy expand (Recommended)

### Q2: How to store alias/mapping data?

| Option | Description | Selected |
|--------|-------------|----------|
| JSONB aliases field (Recommended) | Use existing Company.aliases JSONB | ✓ |
| Separate mapping table | New table: company_identities(company_id, source, identifier) | |
| You decide | Claude picks based on query patterns | |

**User's choice:** JSONB aliases field (Recommended)

---

## Universe Construction

### Q3: Market cap data source?

| Option | Description | Selected |
|--------|-------------|----------|
| SEC EDGAR XBRL (Recommended) | Extract from company facts API — free, already using edgartools | ✓ |
| Free financial API | Yahoo Finance, Alpha Vantage — more current but adds dependency | |
| You decide | Claude picks most reliable free source | |

**User's choice:** SEC EDGAR XBRL (Recommended)

### Q4: EDGAR full-text search strategy?

| Option | Description | Selected |
|--------|-------------|----------|
| Keyword search on recent 10-Ks (Recommended) | Search efts.sec.gov for AI/ML keywords in 10-K filings from last 12 months | ✓ |
| Multi-filing search | Search 10-K, 10-Q, and 8-K — broader but more noise | |
| Keyword + frequency threshold | Only include companies with 10+ AI/ML mentions | |

**User's choice:** Keyword search on recent 10-Ks (Recommended)

---

## Data Seeding Approach

### Q5: How to bootstrap initial company list?

| Option | Description | Selected |
|--------|-------------|----------|
| Automated EDGAR scan (Recommended) | Run EDGAR search, auto-populate Company table. Manual curation after. | ✓ |
| Curated seed list first | Hand-picked 50 known AI-claiming mid-caps, then expand | |
| Hybrid | EDGAR scan to discover, human review to confirm/reject | |

**User's choice:** Automated EDGAR scan (Recommended)

### Q6: Handling companies with partial source resolution?

| Option | Description | Selected |
|--------|-------------|----------|
| Include with gaps (Recommended) | Add to universe, mark missing sources as null. Graceful degradation handles it. | ✓ |
| Require minimum sources | Only include companies resolvable on 3+ of 5 sources | |
| You decide | Claude picks based on downstream signal requirements | |

**User's choice:** Include with gaps (Recommended)

---

## Refresh Cadence

### Q7: How often to re-scan for new companies?

| Option | Description | Selected |
|--------|-------------|----------|
| Monthly (Recommended) | Re-run EDGAR search monthly — AI washing is slow-moving | ✓ |
| Quarterly | Aligned with earnings/filing cadence | |
| Weekly | More responsive but higher API cost | |

**User's choice:** Monthly (Recommended)

### Q8: Handling delistings, mergers, market cap changes?

| Option | Description | Selected |
|--------|-------------|----------|
| Soft remove (Recommended) | Mark inactive with reason, keep historical data. Never delete. | ✓ |
| Auto-purge | Remove from active universe, archive data | |
| You decide | Claude picks based on append-only constraint | |

**User's choice:** Soft remove (Recommended)

---

## Claude's Discretion

- Fuzzy matching algorithm and threshold
- EDGAR search pagination strategy
- Subsidiary handling
- CLI commands for manual universe management

## Deferred Ideas

None — discussion stayed within phase scope.
