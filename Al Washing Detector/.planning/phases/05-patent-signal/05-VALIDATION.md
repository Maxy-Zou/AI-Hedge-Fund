---
phase: 05
slug: patent-signal
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-28
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/unit/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-T1 | 01 | 1 | PAT-01 | unit | `uv run pytest tests/unit/test_patent_types.py -x -q` | TBD | pending |
| 05-01-T2 | 01 | 1 | PAT-01, PAT-03 | import | `.venv/bin/python -c "from ai_washer.db.models import Patent; from ai_washer.config import ScoringConfig, PatentGapScoringConfig; print('OK')"` | TBD | pending |
| 05-02-T1 | 02 | 2 | PAT-01 | unit | `uv run pytest tests/unit/test_patent_client.py -x -q` | TBD | pending |
| 05-02-T2 | 02 | 2 | PAT-01, PAT-03 | unit | `uv run pytest tests/unit/test_patent_collector.py -x -q` | TBD | pending |
| 05-03-T1 | 03 | 3 | PAT-01, PAT-02 | unit | `uv run pytest tests/unit/test_patent_gap_scorer.py -x -q` | TBD | pending |
| 05-03-T2 | 03 | 3 | PAT-01, PAT-02, PAT-03 | unit | `uv run pytest tests/unit/test_scoring_orchestrator.py -x -q` | TBD | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

*No Wave 0 directory creation needed. All plans write test files to the existing flat `tests/unit/` directory structure.*

*Existing infrastructure covers framework, database fixtures, and test directories.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PatentSearch API returns real data | PAT-01 | Requires API key and network | Run `uv run python -m ai_washer patent collect <TICKER>` with valid API key |

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
