# Phase 1: Project Skeleton and Database - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver an installable Python package (`ai_washer`) with a fully migrated PostgreSQL database using append-only schema with dual timestamps, configuration management, and CLI entry points. This is the foundation every other phase builds on — no signal logic, no ingestion, no scoring. Just the skeleton and data layer.

</domain>

<decisions>
## Implementation Decisions

### Package Structure
- **D-01:** Package name is `ai_washer` — import path: `from ai_washer import ...`
- **D-02:** Pip-installable package using src layout (`src/ai_washer/`). Other fund modules install via `pip install` from local path or private PyPI.
- **D-03:** CLI built with Typer — entry points defined in pyproject.toml for `ai-washer` CLI command.
- **D-04:** Use `pyproject.toml` as the single project metadata file (PEP 621). No setup.py or setup.cfg.

### Database Design
- **D-05:** JSONB columns for flexible filing content storage (structured sections like MD&A, Risk Factors). Normalized columns for extracted metrics (R&D, CapEx, keyword counts).
- **D-06:** Monthly range partitioning on `daily_scores` table by `scored_at` date.
- **D-07:** UUID primary keys across all tables — globally unique, safe for future distributed scenarios.
- **D-08:** Dual timestamps on all financial data: `as_of_date` (when the data was true) and `observed_date` (when we collected it). Append-only — never UPDATE or DELETE score rows.
- **D-09:** All monetary values stored as BIGINT (cents) to avoid floating-point issues.

### Config Approach
- **D-10:** Signal weights and scoring thresholds in `config/scoring.yaml` — human-readable, easy to tweak without code changes.
- **D-11:** Secrets via `.env` file + pydantic-settings — standard 12-factor approach. Environment variables in production.
- **D-12:** Pydantic models for all configuration validation — fail fast on startup if config is invalid.

### Claude's Discretion
- Dev tooling choices (uv vs pip, ruff config, pre-commit hooks, test fixtures) — user deferred these to Claude. Research recommends uv + ruff as the 2026 standard.
- Exact SQLAlchemy model structure, index strategy, and migration file organization.
- Async vs sync database driver choice for Phase 1 (both psycopg3 and asyncpg are in the stack).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — Core value, constraints, integration pattern (shared DB + Python API)
- `.planning/REQUIREMENTS.md` — FNDN-01 through FNDN-06, INT-01 acceptance criteria
- `ai_washing_detector_research.md` §6 — Technical architecture suggestions (data pipeline, recommended stack, key libraries)

### Research
- `.planning/research/STACK.md` — Verified library versions, rationale for each choice
- `.planning/research/ARCHITECTURE.md` — Component boundaries, database schema patterns, project structure
- `.planning/research/PITFALLS.md` — Data model pitfalls (dual timestamps, append-only, partition management)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing source code.

### Established Patterns
- None — this phase establishes the patterns for all subsequent phases.

### Integration Points
- PostgreSQL shared database is the primary integration point for downstream fund modules.
- Python package API (Phase 9) will build on the models and repositories established here.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. Research recommends the Astral toolchain (uv + ruff) and edgartools as primary SEC library.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-project-skeleton-and-database*
*Context gathered: 2026-03-27*
