# Phase 9: Infrastructure and Database Setup - Context

**Gathered:** 2026-03-30
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

A running PostgreSQL 16 instance is reachable by both packages via a shared .env convention, and both Alembic migration chains apply cleanly without version table collision.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key constraints from research:
- Docker Compose v2 with postgres:16-alpine (85MB image)
- Named volume required (not anonymous) to prevent data loss on `docker system prune`
- Both packages' `env.py` must declare distinct `version_table` names
- Single `.env` convention must configure `DATABASE_URL`, `AI_WASHER_DATABASE_URL`, and `FUND_BACKTEST_DATABASE_URL`
- Docker Compose file belongs at repo root (shared by both packages)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backtest/src/fund_backtest/config.py` — Pydantic settings with `FUND_BACKTEST_` env prefix
- `Al Washing Detector/src/ai_washer/config.py` — Pydantic settings with `AI_WASHER_` env prefix
- Both packages have Alembic `env.py` and `alembic.ini` already configured

### Established Patterns
- Both packages use `psycopg[binary]` PostgreSQL driver
- Settings loaded via Pydantic BaseSettings with env file support
- Alembic migrations use SQLAlchemy 2.0 style

### Integration Points
- Shared PostgreSQL database: `ai_hedge_fund`
- `AiWashingLoader` in fund_backtest reads from ai_washer's `daily_scores` table via raw SQL
- Both `env.py` files currently write to `public.alembic_version` (collision)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>

---

*Phase: 09-infrastructure-and-database-setup*
*Context gathered: 2026-03-30 via autonomous mode (infrastructure skip)*
