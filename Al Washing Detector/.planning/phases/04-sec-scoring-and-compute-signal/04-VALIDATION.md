---
phase: 04
slug: sec-scoring-and-compute-signal
status: draft
nyquist_compliant: false
wave_0_complete: true
created: 2026-03-28
---

# Phase 04 — Validation Strategy

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
| 04-01-01 | 01 | 1 | SEC-02 | unit | `uv run pytest tests/unit/test_analysis_types.py tests/unit/test_keywords.py -x -q` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | SEC-02 | unit | `uv run pytest tests/unit/test_growth.py tests/unit/test_normalization.py -x -q` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | SEC-04 | unit | `uv run pytest tests/unit/test_sec_filing_scorer.py -x -q` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 1 | COMP-01 | unit | `uv run pytest tests/unit/test_compute_spending_scorer.py -x -q` | ❌ W0 | ⬜ pending |
| 04-04-01 | 04 | 3 | SCORE-02 | unit | `uv run pytest tests/unit/test_scoring_config.py tests/unit/test_config.py -x -q` | ❌ W0 | ⬜ pending |
| 04-04-02 | 04 | 3 | SCORE-02 | unit+integration | `uv run pytest tests/unit/test_scoring_orchestrator.py tests/unit/test_cli_scoring.py -x -q && uv run pytest tests/integration/test_signal_persistence.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*No Wave 0 directory creation needed. All plans write test files to the existing flat `tests/unit/` directory structure. Integration tests go in the existing `tests/integration/` directory.*

*Existing infrastructure covers framework, database fixtures, and test directories.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
