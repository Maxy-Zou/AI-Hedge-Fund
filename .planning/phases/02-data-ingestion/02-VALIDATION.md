---
phase: 2
slug: data-ingestion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-12
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run python -m pytest tests/ -x -q -k "not requires_api_key and not requires_db"` |
| **Full suite command** | `uv run python -m pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick command
- **After every plan wave:** Run full suite
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Status |
|---------|------|------|-------------|-----------|--------|
| 02-01-01 | 01 | 1 | DATA-01 | integration | ⬜ pending |
| 02-01-02 | 01 | 1 | DATA-02 | integration | ⬜ pending |
| 02-02-01 | 02 | 1 | DATA-03 | integration | ⬜ pending |
| 02-02-02 | 02 | 1 | DATA-04 | integration | ⬜ pending |
| 02-03-01 | 03 | 2 | DATA-05, DATA-06 | integration | ⬜ pending |
| 02-03-02 | 03 | 2 | DATA-07 | unit | ⬜ pending |
| 02-04-01 | 04 | 3 | DATA-08 | unit | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/unit/test_temporal.py` — stubs for DATA-07 temporal enforcement
- [ ] `tests/integration/test_edgar.py` — stubs for DATA-01, DATA-02
- [ ] `tests/integration/test_prices.py` — stubs for DATA-03
- [ ] `tests/integration/test_market_data.py` — stubs for DATA-04, DATA-05, DATA-06

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SEC EDGAR rate limit compliance | DATA-01 | Requires live SEC API calls with timing | Run filing retrieval for 5 tickers, verify no 429 responses |
| yfinance fallback to Tiingo | DATA-03 | Requires simulating yfinance failure | Mock yfinance failure, verify Tiingo serves data |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
