# Phase 9: Infrastructure and Database Setup - Research

**Researched:** 2026-03-30
**Domain:** Docker Compose, PostgreSQL 16, Alembic multi-package migrations, shared .env convention
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion — pure infrastructure phase.

Key constraints from research (locked):
- Docker Compose v2 with `postgres:16-alpine` (85MB image)
- Named volume required (not anonymous) to prevent data loss on `docker system prune`
- Both packages' `env.py` must declare distinct `version_table` names
- Single `.env` convention must configure `DATABASE_URL`, `AI_WASHER_DATABASE_URL`, and `FUND_BACKTEST_DATABASE_URL`
- Docker Compose file belongs at repo root (shared by both packages)

### Claude's Discretion
All implementation choices are at Claude's discretion — use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None — infrastructure phase.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | PostgreSQL 16 runs locally via Docker Compose with a named volume for data persistence | Docker Compose v2 confirmed available (v2.40.3); `postgres:16-alpine` image; named volume `ai_hedge_fund_pgdata` |
| INFRA-02 | A shared `.env` convention configures both packages (`ai_washer` and `fund_backtest`) to connect to the same database | Both `AppSettings` use `env_file=".env"` with distinct prefixes (`AI_WASHER_`, `FUND_BACKTEST_`); `.env` at repo root solves this when CLI is invoked from repo root |
| INFRA-03 | Alembic `version_table` is unique per package so both migration chains run without collision | Neither `env.py` sets `version_table` — both default to `public.alembic_version`; fix: add `version_table="fund_backtest_alembic_version"` / `"ai_washer_alembic_version"` to `context.configure()` calls |
| INFRA-04 | Both Alembic migration chains run successfully against the Docker PostgreSQL instance | Fund-backtest has 2 migrations (001, 002); ai_washer has 8 migrations (001–008); both use `psycopg[binary]` driver; connection string format must match |
| FIX-01 | Alembic `env.py` in both packages sets a distinct `version_table` to prevent migration collisions | Same fix as INFRA-03 — add `version_table` to `context.configure()` in both `run_migrations_offline()` and `run_migrations_online()` |
</phase_requirements>

---

## Summary

This phase wires together two independently developed Python packages (`fund_backtest` and `ai_washer`) to share a single PostgreSQL 16 database instance running in Docker. The three concrete deliverables are: (1) a `docker-compose.yml` at the repo root, (2) a shared `.env` + `.env.example` at the repo root, and (3) a `version_table` fix in both Alembic `env.py` files.

The **collision bug** is the hard prerequisite: both `env.py` files currently call `context.configure()` without specifying `version_table`, so Alembic defaults to `public.alembic_version` for both packages. If both migration chains run against the same database, the second one will fail with "already at head" or silently overwrite each other's migration state. The fix is a one-line addition to each `context.configure()` call.

The **env convention** is slightly tricky because Pydantic BaseSettings resolves `.env` relative to the current working directory, not the package root. Both CLIs (`fund-backtest` and `ai-washer`) need to be invoked from the repo root, where the shared `.env` lives, or the path must be made explicit. The existing `env_file=".env"` in both configs makes a root-level `.env` the natural choice.

**Primary recommendation:** Docker Compose at repo root, single `.env` at repo root with all three URL variables, `version_table` added to both `context.configure()` calls.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Docker Compose v2 | 2.40.3 (confirmed) | PostgreSQL container orchestration | v2 syntax (`docker compose` not `docker-compose`); bundled with Docker Desktop |
| postgres | 16-alpine | PostgreSQL image | Alpine variant is 85MB vs 350MB for full; PostgreSQL 16 required per project constraints |
| psycopg[binary] | 3.2+ (in both pyproject.toml) | PostgreSQL driver for Alembic and SQLAlchemy | Already installed in both packages; `[binary]` avoids build deps |
| Alembic | 1.18.4+ (in both pyproject.toml) | Database migrations | Already installed; `version_table` param in `context.configure()` is the fix |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic-settings | 2.13.1+ | Loads `.env` into AppSettings | Already used in both packages; `env_file=".env"` resolves from CWD |

**No new installations required.** This phase creates files and edits existing code only.

---

## Architecture Patterns

### Recommended Project Structure
```
AI Hedgefund/                     # repo root
├── docker-compose.yml            # NEW — shared PostgreSQL container
├── .env                          # NEW — shared secrets (not committed)
├── .env.example                  # NEW — documents all required vars
├── .gitignore                    # EXISTS — already ignores .env
├── backtest/
│   ├── .env.example              # NEW — backtest-specific vars (subset)
│   ├── src/fund_backtest/db/migrations/env.py   # EDIT — add version_table
│   └── ...
└── Al Washing Detector/
    ├── .env.example              # EXISTS — needs DATABASE_URL update + FUND_BACKTEST_ vars added? No: only ai_washer vars
    └── src/ai_washer/db/migrations/env.py       # EDIT — add version_table
```

### Pattern 1: Docker Compose Named Volume
**What:** PostgreSQL 16 service with a named volume and healthcheck
**When to use:** Any local dev setup where data must survive `docker system prune`
**Example:**
```yaml
# Source: Docker Compose v2 official docs
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ai_hedge_fund
      POSTGRES_USER: hedge
      POSTGRES_PASSWORD: hedge
    ports:
      - "5432:5432"
    volumes:
      - ai_hedge_fund_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hedge -d ai_hedge_fund"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  ai_hedge_fund_pgdata:
    driver: local
```

**Named volume vs anonymous:** Anonymous volumes (`- /var/lib/postgresql/data`) are pruned by `docker system prune`. Named volumes (`ai_hedge_fund_pgdata:`) survive unless you explicitly `docker volume rm`. Always use named volumes for databases.

### Pattern 2: Alembic version_table Isolation
**What:** `version_table` parameter in `context.configure()` gives each package its own migration tracking table
**When to use:** Any monorepo where multiple Alembic packages share one database
**Example:**
```python
# Source: Alembic docs — context.configure() API
# fund_backtest env.py — run_migrations_online()
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    version_table="fund_backtest_alembic_version",  # ADD THIS
)

# fund_backtest env.py — run_migrations_offline()
context.configure(
    url=url,
    target_metadata=target_metadata,
    literal_binds=True,
    version_table="fund_backtest_alembic_version",  # ADD THIS
)
```
```python
# ai_washer env.py — run_migrations_online()
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    version_table="ai_washer_alembic_version",  # ADD THIS
)

# ai_washer env.py — run_migrations_offline()
context.configure(
    url=get_url(),
    target_metadata=target_metadata,
    literal_binds=True,
    dialect_opts={"paramstyle": "named"},
    version_table="ai_washer_alembic_version",  # ADD THIS
)
```

### Pattern 3: Shared .env with Prefixed Variables
**What:** Single `.env` at repo root contains all package-specific vars under their prefixes
**When to use:** Monorepo with multiple Python packages using Pydantic BaseSettings
```bash
# .env at repo root
# PostgreSQL connection (shared)
DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund

# fund-backtest package (FUND_BACKTEST_ prefix)
FUND_BACKTEST_DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund

# ai-washer package (AI_WASHER_ prefix)
AI_WASHER_DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund
AI_WASHER_EDGAR_IDENTITY=YourCompany yourname@example.com
AI_WASHER_GITHUB_TOKEN=
AI_WASHER_LOG_LEVEL=INFO
```

**CWD binding:** Pydantic BaseSettings resolves `env_file=".env"` from the process CWD. Both CLIs must be invoked from the repo root to pick up the root `.env`. Document this in the `.env.example` header.

### Anti-Patterns to Avoid
- **Anonymous Docker volume:** `- /var/lib/postgresql/data` — destroyed by `docker system prune`; always use a named volume
- **Hardcoded credentials in docker-compose.yml without env substitution:** Accept the dev-only credentials in the compose file (no secrets rotation needed for local dev); document that production would use secrets management
- **Running `alembic upgrade head` from the wrong directory:** `alembic.ini` uses relative `script_location`; must run from the package directory (`backtest/` or `Al Washing Detector/`)
- **Using `DATABASE_URL` alone:** `fund_backtest/config.py` reads `FUND_BACKTEST_DATABASE_URL` (with prefix); passing only `DATABASE_URL` will cause `ValidationError` on `AppSettings()` construction

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PostgreSQL healthcheck | Custom ping script | `pg_isready` in Docker `healthcheck` | Built into postgres:16-alpine; handles TCP + auth check |
| Migration version isolation | Custom version table schema | Alembic `version_table` param | One-liner in `context.configure()`; Alembic manages the table lifecycle |
| .env parsing | Custom env reader | `pydantic-settings` already in both packages | Already handles prefix, type coercion, and `.env` file loading |

---

## Common Pitfalls

### Pitfall 1: Alembic Runs from Wrong Directory
**What goes wrong:** `alembic upgrade head` fails with "Can't locate revision identifier" or doesn't find migrations
**Why it happens:** `alembic.ini` has `script_location = src/fund_backtest/db/migrations` — this is relative to the directory where `alembic` is invoked
**How to avoid:** Always run `alembic` commands from the package directory:
  - `cd backtest && alembic upgrade head`
  - `cd "Al Washing Detector" && alembic upgrade head`
**Warning signs:** "No such file or directory" for migrations path

### Pitfall 2: Wrong psycopg URL Scheme
**What goes wrong:** `sqlalchemy.exc.NoSuchModuleError` or connection refused
**Why it happens:** psycopg3 requires `postgresql+psycopg://` not `postgresql://` or `postgresql+psycopg2://`
**How to avoid:** Use `postgresql+psycopg://` in all connection strings; the `[binary]` extra installs the C extension but the dialect name is still `psycopg`
**Warning signs:** `ModuleNotFoundError: No module named 'psycopg2'`

### Pitfall 3: fund_backtest env.py silently ignores missing DATABASE_URL
**What goes wrong:** Alembic runs but targets an empty/wrong database
**Why it happens:** `backtest/env.py` uses `os.environ.get("DATABASE_URL") or os.environ.get("FUND_BACKTEST_DATABASE_URL")` — if neither is set, it falls through to the `alembic.ini` value (`%(DATABASE_URL)s`), which is an unparsed interpolation string, causing an error or silent failure
**How to avoid:** Ensure `FUND_BACKTEST_DATABASE_URL` is set before running backtest migrations; verify with `echo $FUND_BACKTEST_DATABASE_URL`

### Pitfall 4: ai_washer env.py raises RuntimeError on missing URL
**What goes wrong:** `ai-washer` Alembic command raises `RuntimeError: AI_WASHER_DATABASE_URL environment variable is required`
**Why it happens:** `ai_washer/env.py:get_url()` raises explicitly if `AI_WASHER_DATABASE_URL` is not set — correct behavior but means you MUST have the var set before running migrations
**How to avoid:** Load the `.env` file or export the variable before running `alembic upgrade head` in `Al Washing Detector/`

### Pitfall 5: Docker container not ready when running migrations
**What goes wrong:** `alembic upgrade head` fails with "connection refused"
**Why it happens:** `docker compose up -d` returns immediately; PostgreSQL takes 2-5 seconds to initialize
**How to avoid:** Wait for healthcheck to pass: `docker compose up -d && docker compose wait postgres` or use a poll loop. Document in README.

### Pitfall 6: ai_washer .env.example has wrong database name
**What goes wrong:** Existing `.env.example` in `Al Washing Detector/` uses `ai_washer` as DB name; the shared DB is named `ai_hedge_fund`
**Why it happens:** The existing `.env.example` was written before the shared DB convention was established
**How to avoid:** Update `Al Washing Detector/.env.example` to use `ai_hedge_fund` as the database name; create `backtest/.env.example` with `ai_hedge_fund`

---

## Code Examples

### Complete docker-compose.yml (verified pattern)
```yaml
# Source: Docker Compose v2 official docs + postgres image docs
services:
  postgres:
    image: postgres:16-alpine
    container_name: ai_hedge_fund_postgres
    environment:
      POSTGRES_DB: ai_hedge_fund
      POSTGRES_USER: hedge
      POSTGRES_PASSWORD: hedge
    ports:
      - "5432:5432"
    volumes:
      - ai_hedge_fund_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hedge -d ai_hedge_fund"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

volumes:
  ai_hedge_fund_pgdata:
    driver: local
```

### Root .env.example
```bash
# =============================================================================
# AI Hedge Fund — Shared Database Configuration
# Run CLIs from repo root to load this file automatically.
# Copy to .env and fill in values.
# =============================================================================

# PostgreSQL connection (Docker Compose default — change for remote DB)
DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund

# fund-backtest package
FUND_BACKTEST_DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund

# ai-washer package
AI_WASHER_DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund
AI_WASHER_EDGAR_IDENTITY=YourCompany yourname@example.com
AI_WASHER_GITHUB_TOKEN=
AI_WASHER_LOG_LEVEL=INFO
```

### Migration verification commands
```bash
# Start database
docker compose up -d
docker compose ps  # wait until postgres is healthy

# Run fund-backtest migrations
cd backtest
alembic upgrade head
alembic current  # should print "002 (head)"
cd ..

# Run ai-washer migrations
cd "Al Washing Detector"
alembic upgrade head
alembic current  # should print "008_... (head)"
cd ..

# Verify both version tables exist in the shared database
docker exec ai_hedge_fund_postgres psql -U hedge -d ai_hedge_fund \
  -c "SELECT table_name FROM information_schema.tables WHERE table_name LIKE '%alembic%';"
# Expected output:
#          table_name
# --------------------------------
#  fund_backtest_alembic_version
#  ai_washer_alembic_version
```

---

## Runtime State Inventory

> Included: this is a migration/infrastructure phase with database state.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | No existing PostgreSQL data (Docker container not yet running; `pg_isready` returns "not found") | None — fresh database |
| Live service config | No existing `docker-compose.yml` at repo root | Create new file |
| OS-registered state | No existing Alembic version tables (no database exists yet) | None — fresh migration run |
| Secrets/env vars | `AI_WASHER_DATABASE_URL` currently points to `ai_washer` DB name in `.env.example`; needs updating to `ai_hedge_fund` | Update `.env.example` in `Al Washing Detector/` |
| Build artifacts | No stale artifacts — no rename involved | None |

**Nothing found in category:** No existing database state. This is a greenfield infrastructure setup.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Container runtime | ✓ | 29.0.1 | — |
| Docker Compose v2 | PostgreSQL orchestration | ✓ | 2.40.3 | — |
| Python 3.12 | backtest package | ✓ | per .python-version | — |
| psycopg[binary] | Alembic driver | ✓ | in both pyproject.toml | — |
| alembic | Migrations | ✓ | 1.18.4+ in both pyproject.toml | — |
| Local PostgreSQL | — | ✗ | — | Use Docker Compose (preferred) |

**Missing dependencies with no fallback:** None — Docker is available and is the intended solution.

**Missing dependencies with fallback:** Local PostgreSQL not present, but Docker Compose handles this.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 (backtest), pytest 9.0+ (ai_washer) |
| Config file | `backtest/pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `cd backtest && python -m pytest tests/unit/ -x -q` |
| Full suite command | `cd backtest && python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | Docker Compose starts postgres:16-alpine with named volume | smoke | `docker compose ps \| grep healthy` | ❌ Wave 0 (shell verification, not pytest) |
| INFRA-02 | Shared .env loaded by both AppSettings | unit | `cd backtest && python -m pytest tests/unit/test_config.py -x -k env` | ✅ (config tests exist) |
| INFRA-03 | version_table distinct per package | smoke | `docker exec ai_hedge_fund_postgres psql -U hedge -d ai_hedge_fund -c "SELECT table_name FROM information_schema.tables WHERE table_name LIKE '%alembic%';"` | ❌ Wave 0 (shell verification) |
| INFRA-04 | Both migration chains apply cleanly | smoke | `cd backtest && alembic upgrade head && alembic current` | ❌ Wave 0 (shell verification) |
| FIX-01 | Same as INFRA-03 | smoke | Same as INFRA-03 | ❌ Wave 0 (shell verification) |

**Note:** INFRA-01, INFRA-03, INFRA-04, FIX-01 are infrastructure smoke tests — they verify Docker/database state, not Python logic. They run as shell commands, not pytest. The "automated command" column captures the verification step.

### Sampling Rate
- **Per task commit:** `docker compose ps` (confirm postgres healthy)
- **Per wave merge:** `alembic current` in both packages
- **Phase gate:** Both `alembic current` show `(head)` and `information_schema.tables` shows two distinct alembic version tables

### Wave 0 Gaps
- No new pytest tests required — this phase is pure infrastructure/config. Existing unit tests for `config.py` in both packages will serve as regression guards if `.env` loading is changed.
- [ ] `backtest/.env.example` — does not exist, must be created as part of INFRA-02
- [ ] `docker-compose.yml` at repo root — does not exist, must be created as part of INFRA-01

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `docker-compose` (v1 CLI) | `docker compose` (v2, bundled) | Docker Desktop 3.0+ | Different binary name; v2 syntax required |
| `postgresql://` scheme for psycopg3 | `postgresql+psycopg://` | SQLAlchemy 2.0 | Must use dialect-qualified URL |

**Deprecated/outdated:**
- `docker-compose` (standalone binary): replaced by `docker compose` plugin; v1 reached EOL. The installed version is v2 (`docker compose version` confirmed).

---

## Open Questions

1. **Where do developers invoke the CLIs from?**
   - What we know: `env_file=".env"` resolves from CWD; repo root has `.gitignore` that ignores `.env`
   - What's unclear: If a developer runs `cd backtest && fund-backtest universe refresh`, the `.env` file they load is `backtest/.env`, not the root `.env`
   - Recommendation: Document in `.env.example` that CLIs should be invoked from repo root, OR consider absolute path env_file. The simplest approach is also creating package-level `.env.example` files that reference the root one, plus a note in the root README.

2. **Should the `backtest/` package also get its own `.env.example`?**
   - What we know: `backtest/` has no `.env.example` currently (confirmed by filesystem check)
   - What's unclear: Whether developers will navigate to `backtest/` to run migrations
   - Recommendation: Yes — create `backtest/.env.example` with `FUND_BACKTEST_DATABASE_URL` pointing to the shared DB. Mirrors the existing pattern in `Al Washing Detector/`.

---

## Project Constraints (from CLAUDE.md)

Extracted from `./CLAUDE.md` and global rules:

- **Immutability:** Historical price data must never be overwritten — append only. Not directly relevant to this infrastructure phase, but the Docker volume must be named (not anonymous) to preserve persistence.
- **Python 3.12:** Use Python 3.12 runtime. Alembic and psycopg are already installed in both venvs.
- **uv preferred:** No new packages are installed in this phase, so uv usage is not required.
- **No hardcoded secrets:** Docker Compose file will use hardcoded dev credentials (acceptable for local dev only); `.env` is in `.gitignore`.
- **GSD Workflow:** Changes go through `/gsd:execute-phase`; no direct repo edits outside GSD workflow.
- **Immutable data patterns:** Not applicable to config/Docker files.
- **Testing at 80% coverage:** This phase adds no new Python logic — no coverage delta expected.

---

## Sources

### Primary (HIGH confidence)
- Codebase inspection — both `env.py` files read directly; confirmed `version_table` not set in either
- Codebase inspection — `config.py` in both packages read directly; confirmed `env_file=".env"` with CWD resolution
- Codebase inspection — `alembic.ini` in both packages read directly; confirmed `script_location` is package-relative
- Environment probe — `docker --version` (29.0.1), `docker compose version` (2.40.3-desktop.1) confirmed
- Environment probe — `pg_isready` not found; no local PostgreSQL installed; Docker is the only DB option

### Secondary (MEDIUM confidence)
- Docker Compose v2 named volume behavior — standard Docker docs pattern; well-established
- Alembic `version_table` parameter — documented in Alembic `context.configure()` API; used by the multi-tenant pattern

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries confirmed in pyproject.toml; Docker confirmed available
- Architecture: HIGH — all files inspected; no alternatives to evaluate
- Pitfalls: HIGH — identified from direct code inspection (not from training data assumptions)

**Research date:** 2026-03-30
**Valid until:** 2026-06-30 (stable infrastructure; Docker/Alembic APIs change slowly)
