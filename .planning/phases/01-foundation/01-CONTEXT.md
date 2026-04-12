# Phase 1: Foundation - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

A running LangGraph pipeline with typed agent schemas, multi-model routing, observability traces, and cost guardrails -- so every subsequent phase builds on instrumented, budget-aware infrastructure.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints from PROJECT.md and CLAUDE.md:
- Python 3.11+, uv for package management
- LangGraph >= 0.3 for orchestration with PostgreSQL checkpointing
- PydanticAI >= 1.0 for typed agent definitions
- langchain-anthropic >= 0.3 for Claude model integration
- Langfuse >= 2.0 for observability (open-source, self-hosted)
- Dual-model routing: Haiku for extraction, Sonnet for analysis, Opus for complex reasoning
- Token budget enforcement per agent and per pipeline run
- Immutable data patterns, type hints required, functions under 50 lines, files under 800 lines
- ruff for formatting and linting

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Architecture
- `CLAUDE.md` — Project conventions, architecture, data handling rules, agent development rules
- `.planning/PROJECT.md` — Core value, constraints, key decisions
- `.planning/REQUIREMENTS.md` — Phase 1 requirements: FOUND-01 through FOUND-05
- `.planning/ROADMAP.md` — Phase 1 success criteria (4 verifiable conditions)

### Prior Work (Reference Patterns)
- `archive/2026-04-11-pre-pivot/Al Washing Detector/src/ai_washer/config.py` — Configuration pattern from prior project
- `archive/2026-04-11-pre-pivot/Al Washing Detector/src/ai_washer/db/` — SQLAlchemy + migration patterns

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- No existing source code — greenfield project
- Prior work in archive/ has SQLAlchemy database patterns, config management, and EDGAR integration code

### Established Patterns
- Prior project used src/package_name/ layout with domain submodules (db/, ingestion/, analysis/, pipeline/)
- SQLAlchemy with Alembic-style migrations for database schema management
- Pydantic-based configuration

### Integration Points
- docker-compose.yml exists for PostgreSQL
- .env pattern for secrets (per CLAUDE.md conventions)

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

*Phase: 01-foundation*
*Context gathered: 2026-04-11 via autonomous mode (infrastructure skip)*
