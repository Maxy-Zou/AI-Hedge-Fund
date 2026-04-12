---
phase: 9
slug: infrastructure-and-database-setup
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-30
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (both packages) |
| **Config file** | `backtest/pyproject.toml` [tool.pytest.ini_options], `Al Washing Detector/pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `cd backtest && uv run pytest tests/ -x -q` |
| **Full suite command** | `cd backtest && uv run pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~30 seconds (unit only; integration requires Docker) |

---

## Sampling Rate

- **After every task commit:** Run `cd backtest && uv run pytest tests/ -x -q`
- **After every plan wave:** Run full suite in both packages
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | INFRA-01 | manual | `docker compose up -d && docker compose ps` | N/A | ⬜ pending |
| 09-01-02 | 01 | 1 | INFRA-02 | manual | `cat .env.example` | N/A | ⬜ pending |
| 09-01-03 | 01 | 1 | INFRA-03, FIX-01 | unit | `grep version_table backtest/migrations/env.py` | ❌ W0 | ⬜ pending |
| 09-01-04 | 01 | 1 | INFRA-04 | integration | `cd backtest && alembic upgrade head` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers most phase requirements
- Docker Compose validation is inherently manual (container must start)
- Alembic migration validation requires a running PostgreSQL instance

*Most validations for this phase are operational/manual rather than automated tests.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Docker Compose starts PostgreSQL | INFRA-01 | Requires Docker runtime | `docker compose up -d && docker compose ps` — verify "running" status |
| Data survives restart | INFRA-01 | Requires container lifecycle | `docker compose restart && docker compose exec db psql -c "SELECT 1"` |
| Both CLIs connect | INFRA-02 | Requires running database | Run both CLI help commands with .env loaded |
| Migrations apply cleanly | INFRA-04 | Requires running database | `cd backtest && alembic upgrade head && cd ../Al\ Washing\ Detector && alembic upgrade head` |
| Separate version tables | INFRA-03, FIX-01 | Requires running database | `psql -c "SELECT * FROM fund_backtest_alembic_version"` and `psql -c "SELECT * FROM ai_washer_alembic_version"` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
