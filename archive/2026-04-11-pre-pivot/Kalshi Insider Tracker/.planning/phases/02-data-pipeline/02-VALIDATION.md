---
phase: 2
slug: data-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-03
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0+ |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/daemon/ -m "not integration" -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds (unit), ~30 seconds (with integration) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/daemon/ -m "not integration" -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | DATA-02 | unit | `uv run pytest tests/daemon/test_poller.py -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | DATA-04 | unit | `uv run pytest tests/daemon/test_poller.py::test_to_orm_mapping -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | DATA-06 | unit | `uv run pytest tests/daemon/test_warmup.py -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | DATA-02 | unit | `uv run pytest tests/daemon/test_poller.py::test_poll_tick_calls_client -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | DATA-04 | unit | `uv run pytest tests/daemon/test_poller.py::test_poll_tick_persists_snapshots -x` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 2 | DATA-06 | unit | `uv run pytest tests/daemon/test_warmup.py::test_warmed_up_at_threshold -x` | ❌ W0 | ⬜ pending |
| 02-02-04 | 02 | 2 | DATA-04 | integration | `uv run pytest tests/daemon/test_poller.py -m integration -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/daemon/__init__.py` — package init
- [ ] `tests/daemon/test_poller.py` — covers DATA-02, DATA-04
- [ ] `tests/daemon/test_warmup.py` — covers DATA-06
- [ ] `tests/conftest.py` — shared fixtures (session_factory mock, KalshiClient mock)
- [ ] `uv add apscheduler>=3.11.0` — runtime dependency
- [ ] `uv add --dev freezegun>=1.5.5` — time mocking for tests

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Daemon polls Kalshi for 10 min without 429 | DATA-02 | Requires live API key + 10 min run | Run `kalshi-tracker poll start` with valid `.env`, monitor logs for 10 minutes |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
