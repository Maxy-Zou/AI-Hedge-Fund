---
phase: 1
slug: project-skeleton-and-database
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-27
---

# Phase 1 -- Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/unit -x -q` |
| **Full suite command** | `uv run pytest tests/ -v --tb=short --timeout=120` |
| **Estimated runtime** | ~30 seconds (unit), ~90 seconds (full with integration) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v --tb=short --timeout=120`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds (unit), 90 seconds (integration)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-T1 | 01 | 1 | FNDN-04 | scaffold | `test -f tests/conftest.py && test -f tests/unit/test_package.py && test -f tests/unit/test_config.py` | N/A (creates files) | pending |
| 01-01-T2 | 01 | 1 | FNDN-04, FNDN-05 | unit | `uv run pytest tests/unit/test_package.py tests/unit/test_config.py -x -v` | tests/unit/test_package.py, tests/unit/test_config.py | pending |
| 01-02-T1 | 02 | 2 | FNDN-01 | unit | `uv run pytest tests/unit/test_models.py -x -v -k "base or mixin"` | tests/unit/test_models.py | pending |
| 01-02-T2 | 02 | 2 | FNDN-01, INT-01 | unit | `uv run pytest tests/unit/test_models.py -x -v` | tests/unit/test_models.py | pending |
| 01-03-T1 | 03 | 3 | FNDN-06 | import | `uv run python -c "import importlib.util; spec = importlib.util.find_spec('ai_washer.db.migrations.env'); assert spec is not None; print('OK')"` | src/ai_washer/db/migrations/env.py | pending |
| 01-03-T2 | 03 | 3 | FNDN-06, INT-01 | integration | `uv run pytest tests/integration/ -x -v -m integration --timeout=120` | tests/integration/test_migrations.py, tests/integration/test_schema.py | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` -- shared fixtures (test env vars, scoring.yaml)
- [ ] `tests/unit/__init__.py` -- unit test package
- [ ] `tests/integration/__init__.py` -- integration test package
- [ ] `pytest` + `testcontainers[postgres]` -- installed as dev dependencies

Created by Plan 01-01 Task 1.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CLI entry points accessible | FNDN-04 | Requires shell invocation | Run `uv run ai-washer --help` and verify output |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s (unit) / < 120s (integration)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending execution
