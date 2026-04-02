# AI Washing Detector

## What This Is

An autonomous module in a fully automated AI hedge fund that scores mid-cap public companies ($2B-$10B market cap) on the gap between their AI claims and actual AI investment. Produces daily AI Washing Risk Scores across 6 signals, writing structured results to a shared database for downstream portfolio management and trade execution modules to consume. One of the first modules being built for the fund — no human reviews individual trade decisions.

## Core Value

Accurately quantify the gap between what companies *say* about AI and what they *do* — producing reliable, machine-consumable signals that an automated trading system can act on without human review.

## Requirements

### Validated

- [x] Shared PostgreSQL database for downstream module consumption — *Validated in Phase 1: Project Skeleton and Database*
- [x] Clean Python package API for integration with other fund modules — *Validated in Phase 1: Project Skeleton and Database*
- [x] Historical score tracking (immutable snapshots, never overwrite) — *Validated in Phase 1: append-only schema with dual timestamps*

### Active

- [ ] Daily batch scoring of mid-cap companies across 6 signals
- [ ] SEC filing analysis (AI keyword frequency vs. R&D spending growth)
- [ ] Job posting mismatch detection (AI claims vs. actual AI hiring)
- [ ] Patent gap analysis (AI claims vs. AI patent filings)
- [ ] Earnings call vagueness scoring (buzzwords vs. substance)
- [ ] GitHub/open-source activity analysis
- [ ] Compute spending gap detection
- [ ] Composite AI Washing Risk Score (0-100) with configurable signal weights
- [ ] Target universe builder (identify mid-cap companies making AI claims)
- [x] ~~Shared PostgreSQL database for downstream module consumption~~ → Validated
- [x] ~~Clean Python package API for integration with other fund modules~~ → Validated
- [x] ~~Historical score tracking (immutable snapshots, never overwrite)~~ → Validated
- [ ] Automated daily data refresh pipeline

### Out of Scope

- Paid API integrations (TheirStack, Revelio Labs, FMP) — v1 uses free sources only, paid added later
- Trade execution — handled by a separate downstream module
- Portfolio management / position sizing — separate module
- Real-time streaming / event-driven architecture — daily batch is sufficient for AI washing signals
- Web dashboard / UI — the consumer is other automated modules, not humans
- Mobile app
- REST API gateway — premature until multiple services need it

## Context

- **Broader system:** This is one of the first modules in a fully autonomous AI hedge fund being built from scratch. Other modules (portfolio management, execution, risk) will be built separately.
- **Integration pattern:** Shared PostgreSQL database + Python package API. Other modules import this as a library or query the DB directly.
- **Data sources (v1, all free):**
  - SEC EDGAR API (data.sec.gov) — filings, XBRL financial data
  - USPTO PatentsView API (api.patentsview.org) — patent search
  - GitHub REST API v3 — organization repos and activity
  - Open-source LinkedIn job scraping (linkedin-jobs-api or similar)
  - edgartools Python library for SEC filing parsing
- **Regulatory backdrop:** SEC CETU has made AI washing enforcement an "immediate priority." Enforcement actions are catalysts for short positions.
- **Small team** (2-5 people) building the fund — output needs to be understandable without explanation for debugging and monitoring.
- **Research document:** `ai_washing_detector_research.md` in project root contains detailed signal definitions, data sources, scoring framework, and technical architecture suggestions.

## Constraints

- **Data sources**: Free APIs only for v1 — SEC EDGAR (10 req/sec limit), USPTO PatentsView (no key needed), GitHub (5,000 req/hr with token)
- **Immutability**: Financial data must never be overwritten — append new snapshots only. All monetary values stored as integers (cents).
- **SEC compliance**: EDGAR requires User-Agent with company name + email (legal requirement)
- **Autonomy**: Module must operate without human intervention — robust error handling, retry logic, graceful degradation when a data source is unavailable
- **Refresh cadence**: Daily batch processing
- **Language**: Python 3.11+ (best ecosystem for NLP + financial data)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Free data sources only for v1 | Reduce dependencies and cost while proving the thesis | -- Pending |
| Shared DB + Python API as integration pattern | Simplest integration for a system being built from scratch — no premature service mesh | -- Pending |
| Daily batch over real-time | AI washing is a slow-moving signal — daily is sufficient, saves complexity | -- Pending |
| All 6 signals in v1 | Composite score needs multiple signals to reduce false positives — no single signal is reliable alone | -- Pending |
| No UI in v1 | Consumer is automated systems, not humans — dashboard is a later add-on for debugging | -- Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-27 after Phase 1 completion — foundation package and database established*
