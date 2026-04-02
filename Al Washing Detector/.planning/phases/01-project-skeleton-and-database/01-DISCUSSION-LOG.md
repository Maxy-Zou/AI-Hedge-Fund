# Phase 1: Project Skeleton and Database - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-27
**Phase:** 01-project-skeleton-and-database
**Areas discussed:** Package structure, Database design, Config approach

---

## Package Structure

### Q1: How should other fund modules consume this package?

| Option | Description | Selected |
|--------|-------------|----------|
| Pip-installable (Recommended) | pip install from local path or private PyPI — clean import boundaries, versioned releases | ✓ |
| Monorepo import | All fund modules in one repo, import via relative paths — simpler but tighter coupling | |
| You decide | Claude picks the best approach for an early-stage fund | |

**User's choice:** Pip-installable (Recommended)
**Notes:** None

### Q2: CLI framework for manual runs and debugging?

| Option | Description | Selected |
|--------|-------------|----------|
| Typer (Recommended) | Type-hint-based CLI, auto-generated help, minimal boilerplate — research recommends this | ✓ |
| Click | More verbose but battle-tested, Typer is built on it | |
| Argparse | Standard library, no dependencies, but more manual work | |

**User's choice:** Typer (Recommended)
**Notes:** None

### Q3: What should the package be named?

| Option | Description | Selected |
|--------|-------------|----------|
| ai_washer | Short, memorable — `from ai_washer import get_score` | ✓ |
| ai_washing_detector | Descriptive, matches the project name exactly | |
| washdetect | Compact, unique namespace — `from washdetect import get_score` | |

**User's choice:** ai_washer
**Notes:** None

---

## Database Design

### Q4: How should filing content be stored?

| Option | Description | Selected |
|--------|-------------|----------|
| JSONB columns (Recommended) | Store structured sections as JSONB — flexible, queryable, avoids 20-column tables | ✓ |
| Normalized tables | Separate table per filing section — more rigid but standard relational design | |
| Hybrid | JSONB for raw content, normalized columns for extracted metrics | |

**User's choice:** JSONB columns (Recommended)
**Notes:** None

### Q5: Partition strategy for append-only score tables?

| Option | Description | Selected |
|--------|-------------|----------|
| Monthly range (Recommended) | Partition daily_scores by month — good balance for daily batch writes | ✓ |
| Quarterly range | Fewer partitions, aligned with earnings cadence | |
| No partitioning yet | Start simple, add partitioning when data volume requires it | |

**User's choice:** Monthly range (Recommended)
**Notes:** None

### Q6: UUID or auto-increment integers for primary keys?

| Option | Description | Selected |
|--------|-------------|----------|
| UUIDs (Recommended) | Globally unique, safe for distributed systems, no sequence contention | ✓ |
| Auto-increment integers | Simpler, smaller indexes, but IDs are guessable | |
| You decide | Claude picks based on the integration pattern | |

**User's choice:** UUIDs (Recommended)
**Notes:** None

---

## Config Approach

### Q7: Where should signal weights and scoring thresholds live?

| Option | Description | Selected |
|--------|-------------|----------|
| YAML file (Recommended) | config/scoring.yaml — human-readable, easy to tweak | ✓ |
| TOML (pyproject.toml) | Keep everything in pyproject.toml | |
| Database table | Store config in PostgreSQL — queryable, versioned | |

**User's choice:** YAML file (Recommended)
**Notes:** None

### Q8: How should secrets be managed?

| Option | Description | Selected |
|--------|-------------|----------|
| .env + pydantic-settings (Recommended) | .env file locally, environment variables in production | ✓ |
| AWS Secrets Manager | Cloud-native secret management — adds AWS dependency | |
| You decide | Claude picks simplest secure approach | |

**User's choice:** .env + pydantic-settings (Recommended)
**Notes:** None

---

## Claude's Discretion

- Dev tooling (uv vs pip, ruff config, pre-commit hooks, test fixtures, CI)
- SQLAlchemy model structure, index strategy, migration file organization
- Async vs sync database driver choice for Phase 1

## Deferred Ideas

None — discussion stayed within phase scope.
