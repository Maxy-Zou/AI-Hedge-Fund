---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-02
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0+ |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] — Wave 0 installs |
| **Quick run command** | `pytest tests/unit/ -x -q` |
| **Full suite command** | `pytest tests/ -x -q --cov=src/kalshi_tracker` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/unit/ -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q --cov=src/kalshi_tracker`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | DATA-01 | unit | `pytest tests/unit/test_client.py::test_client_init_with_rsa_key -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | DATA-01 | unit (mock) | `pytest tests/unit/test_client.py::test_rsa_headers_present -x` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | DATA-03 | unit (mock) | `pytest tests/unit/test_client.py::test_markets_filtered_to_politics_series -x` | ❌ W0 | ⬜ pending |
| 01-01-04 | 01 | 1 | DATA-05 | unit | `pytest tests/unit/test_client.py::test_rate_limit_enforced -x` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | LOG-03 | unit | `pytest tests/unit/test_models.py::test_signal_is_append_only -x` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | LOG-03 | integration | `pytest tests/integration/test_migrations.py::test_all_tables_created -x -m integration` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/__init__.py` — package root
- [ ] `tests/unit/__init__.py` — unit test package
- [ ] `tests/unit/test_client.py` — stubs for DATA-01, DATA-03, DATA-05
- [ ] `tests/unit/test_models.py` — stubs for LOG-03
- [ ] `tests/unit/test_config.py` — stubs for config validation
- [ ] `tests/integration/__init__.py` — integration test package
- [ ] `tests/integration/test_migrations.py` — stubs for migration verification
- [ ] `tests/conftest.py` — shared fixtures

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Auth smoke test against demo API returns 200 | DATA-01 | Requires real API keys | Run `python -c "from kalshi_tracker.client import KalshiClient; c = KalshiClient(); print(c.get_markets())"` with valid credentials |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
