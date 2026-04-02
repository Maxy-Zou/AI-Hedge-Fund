---
phase: 3
slug: sec-filing-collection
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0.2 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/unit/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -x --timeout=120` |
| **Estimated runtime** | ~15 seconds (unit), ~30 seconds (full with integration) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x --timeout=120`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | SEC-01 | unit | `python -m pytest tests/unit/test_filing_models.py -x` | No -- Wave 0 | pending |
| 03-01-02 | 01 | 1 | SEC-01 | unit | `python -m pytest tests/unit/test_filing_client.py -x` | No -- Wave 0 | pending |
| 03-02-01 | 02 | 2 | SEC-03 | unit | `python -m pytest tests/unit/test_xbrl_extractor.py -x` | No -- Wave 0 | pending |
| 03-02-02 | 02 | 2 | SEC-05 | unit | `python -m pytest tests/unit/test_filing_client.py::test_rate_limiting -x` | No -- Wave 0 | pending |
| 03-03-01 | 03 | 3 | SEC-01 | unit | `python -m pytest tests/unit/test_filing_collector.py -x` | No -- Wave 0 | pending |
| 03-03-02 | 03 | 3 | SEC-01,SEC-03 | integration | `python -m pytest tests/integration/test_filing_collection.py -x --timeout=120` | No -- Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_filing_client.py` -- covers SEC-01-a/b/c, SEC-05-a/b/c
- [ ] `tests/unit/test_filing_models.py` -- covers SEC-01-d, SEC-03-d
- [ ] `tests/unit/test_xbrl_extractor.py` -- covers SEC-03-a/b/c/e
- [ ] `tests/unit/test_filing_collector.py` -- covers IDEMPOTENT-a
- [ ] `tests/integration/test_filing_collection.py` -- covers SEC-01-e, SEC-03-f, IDEMPOTENT-b
- [ ] Existing test infrastructure (conftest.py, integration/conftest.py) provides shared fixtures

*(No new framework install needed -- all test dependencies already installed)*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live EDGAR rate compliance | SEC-05 | Needs real API calls to verify no 403s | Run `python -m ai_washer collect --company AAPL --dry-run` against live EDGAR |
| edgartools section parser mid-cap coverage | SEC-01 | HTML quality varies by filer | Spot-check 5 mid-cap 10-K filings for section extraction quality |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
