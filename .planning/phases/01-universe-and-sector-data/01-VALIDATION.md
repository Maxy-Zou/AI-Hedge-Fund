---
phase: 1
slug: universe-and-sector-data
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9.0.2 |
| **Config file** | `backtest/pyproject.toml` (Wave 0 creates) |
| **Quick run command** | `cd backtest && uv run pytest tests/unit -x -q` |
| **Full suite command** | `cd backtest && uv run pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backtest && uv run pytest tests/unit -x -q`
- **After every plan wave:** Run `cd backtest && uv run pytest tests/ -v --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 0 | - | setup | `cd backtest && uv run pytest --co -q` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | DATA-05 | unit | `cd backtest && uv run pytest tests/unit/test_universe.py -v` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | DATA-07 | unit | `cd backtest && uv run pytest tests/unit/test_sector.py -v` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | DATA-05 | integration | `cd backtest && uv run pytest tests/integration/ -v` | ❌ W0 | ⬜ pending |
| 01-04-01 | 04 | 2 | DATA-05, DATA-07 | cli | `cd backtest && uv run pytest tests/unit/test_cli.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backtest/pyproject.toml` — package definition with pytest, pytest-cov dependencies
- [ ] `backtest/tests/conftest.py` — shared fixtures (mock yfinance responses, test DB)
- [ ] `backtest/tests/unit/` — unit test directory structure
- [ ] `backtest/tests/integration/` — integration test directory structure

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| yfinance rate limit compliance | DATA-05 | Requires real API calls | Run `universe refresh` with 5+ tickers, verify no 429 errors in logs |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
