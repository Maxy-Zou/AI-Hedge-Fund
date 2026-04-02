---
phase: 07
slug: earnings-call-signal
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-29
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/unit/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~60 seconds (FinBERT model load adds ~10s first run) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

*To be populated after planning — task IDs and test files depend on plan structure.*

---

## Wave 0 Requirements

- [ ] Install transformers, torch (CPU), earningscall via `uv add`
- [ ] Verify FinBERT model loads: `uv run python -c "from transformers import pipeline; p = pipeline('sentiment-analysis', model='ProsusAI/finbert'); print('OK')"`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| EarningsCall API returns real transcript | EARN-01 | Requires API key | Run with `EARNINGSCALL_API_KEY` env var set |
| FinBERT produces expected sentiment | EARN-03 | Model download required | Run after `uv run python -c "from transformers import pipeline"` succeeds |

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
