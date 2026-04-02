---
phase: 2
slug: entity-resolution-and-universe-builder
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0.2 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/unit/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -x --timeout=120` |
| **Estimated runtime** | ~15 seconds |

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
| 02-01-01 | 01 | 1 | FNDN-02 | unit | `python -m pytest tests/unit/test_entity_resolver.py::test_resolve_cik_ticker -x` | No -- Wave 0 | pending |
| 02-01-02 | 01 | 1 | FNDN-02 | unit | `python -m pytest tests/unit/test_fuzzy_matcher.py::test_patent_assignee_match -x` | No -- Wave 0 | pending |
| 02-01-03 | 01 | 1 | FNDN-02 | unit | `python -m pytest tests/unit/test_entity_resolver.py::test_aliases_jsonb_structure -x` | No -- Wave 0 | pending |
| 02-01-04 | 01 | 1 | FNDN-02 | unit | `python -m pytest tests/unit/test_entity_resolver.py::test_partial_resolution -x` | No -- Wave 0 | pending |
| 02-02-01 | 02 | 1 | FNDN-03 | unit | `python -m pytest tests/unit/test_efts_client.py::test_pagination -x` | No -- Wave 0 | pending |
| 02-02-02 | 02 | 1 | FNDN-03 | unit | `python -m pytest tests/unit/test_universe_filters.py::test_market_cap_filter -x` | No -- Wave 0 | pending |
| 02-02-03 | 02 | 2 | FNDN-03 | unit | `python -m pytest tests/unit/test_universe_builder.py::test_deterministic -x` | No -- Wave 0 | pending |
| 02-03-01 | 03 | 2 | FNDN-03 | integration | `python -m pytest tests/integration/test_universe_builder.py::test_companies_persisted -x` | No -- Wave 0 | pending |
| 02-03-02 | 03 | 2 | FNDN-03 | integration | `python -m pytest tests/integration/test_company_lifecycle.py::test_soft_remove -x` | No -- Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_efts_client.py` -- stubs for FNDN-03-a (EFTS pagination)
- [ ] `tests/unit/test_entity_resolver.py` -- stubs for FNDN-02-a, FNDN-02-c, FNDN-02-d
- [ ] `tests/unit/test_fuzzy_matcher.py` -- stubs for FNDN-02-b (rapidfuzz matching)
- [ ] `tests/unit/test_universe_filters.py` -- stubs for FNDN-03-b (market cap filter)
- [ ] `tests/unit/test_universe_builder.py` -- stubs for FNDN-03-c (determinism)
- [ ] `tests/integration/test_universe_builder.py` -- stubs for FNDN-03-d (persistence)
- [ ] `tests/integration/test_company_lifecycle.py` -- stubs for FNDN-03-e (soft remove)
- [ ] `pytest-httpx` already in dev dependencies -- used for mocking httpx calls to EFTS and XBRL APIs
- [ ] Framework install: `uv add --dev freezegun` (time mocking for determinism tests)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| EFTS `size` param max (50 vs 100) | FNDN-03 | Conflicting docs, needs live API call | Run EFTS query with size=100, check if response has 100 or 50 hits |
| EntityPublicFloat coverage | FNDN-03 | Needs empirical check against live XBRL data | Fetch 50 sample mid-cap CIKs, check EntityPublicFloat presence rate |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
