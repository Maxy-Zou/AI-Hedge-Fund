---
phase: 1
slug: data-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-04
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | DATA-01 | integration | `uv run pytest tests/test_ingest.py -k historical` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DATA-02 | integration | `uv run pytest tests/test_ingest.py -k tier_split` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DATA-03 | unit | `uv run pytest tests/test_schema.py -k lookahead` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DATA-04 | integration | `uv run pytest tests/test_ingest.py -k incremental` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DATA-05 | unit | `uv run pytest tests/test_validation.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DATA-06 | unit | `uv run pytest tests/test_schema.py -k utc` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | CLI-01 | integration | `uv run pytest tests/test_cli.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures (DuckDB in-memory test database)
- [ ] `tests/test_schema.py` — stubs for DATA-03, DATA-06
- [ ] `tests/test_ingest.py` — stubs for DATA-01, DATA-02, DATA-04
- [ ] `tests/test_validation.py` — stubs for DATA-05
- [ ] `tests/test_cli.py` — stubs for CLI-01
