# Phase 1: Foundation - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

The system can authenticate with Kalshi, define its database schema, and represent market data as typed domain objects. This phase delivers the foundational layer that all subsequent phases depend on: API client, database models, and typed contracts.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and fund-wide conventions (Python 3.11+, SQLAlchemy 2.0, Pydantic, structlog, immutable patterns) to guide decisions.

Key constraints from research:
- Use kalshi-python SDK if available and sufficient; fall back to httpx for missing endpoints
- PostgreSQL + SQLAlchemy for consistency with fund stack (not SQLite)
- Append-only tables for signal/trade data (fund-wide immutability convention)
- Rate limiting must be built into the API client layer from day one
- Politics/policy market filtering at the API client level

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Fund conventions from Al Washing Detector: structlog setup, Pydantic settings with env prefix, SQLAlchemy 2.0 mapped_column style, Alembic migrations
- pyproject.toml pattern with hatchling build backend

### Established Patterns
- `from __future__ import annotations` at top of every file
- Google-style docstrings
- `ruff` for linting/formatting (line-length=100, target-version=py312)
- Module-level `logger = structlog.get_logger(__name__)`
- Frozen dataclasses for immutable result objects
- Pydantic BaseSettings for configuration with env file support

### Integration Points
- New project directory: `Kalshi Insider Tracker/`
- Will need its own pyproject.toml, src/ layout, .env, alembic.ini

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Follow fund conventions from the Al Washing Detector sibling project.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase stayed within scope.

</deferred>
