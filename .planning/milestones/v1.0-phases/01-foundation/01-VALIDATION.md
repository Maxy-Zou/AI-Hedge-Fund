---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-11
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml (Wave 0 creates) |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | FOUND-01 | — | N/A | integration | `uv run pytest tests/test_graph.py -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | FOUND-01 | — | N/A | integration | `uv run pytest tests/test_checkpoint.py -x` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | FOUND-02 | — | N/A | unit | `uv run pytest tests/test_schemas.py -x` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | FOUND-02 | — | N/A | unit | `uv run pytest tests/test_agent.py -x` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | FOUND-03 | — | N/A | integration | `uv run pytest tests/test_routing.py -x` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | FOUND-04 | — | N/A | integration | `uv run pytest tests/test_observability.py -x` | ❌ W0 | ⬜ pending |
| 01-03-03 | 03 | 2 | FOUND-05 | — | N/A | unit | `uv run pytest tests/test_budget.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures (PostgreSQL test connection, mock LLM responses)
- [ ] `tests/test_graph.py` — stubs for FOUND-01 (LangGraph graph compilation and execution)
- [ ] `tests/test_checkpoint.py` — stubs for FOUND-01 (PostgreSQL checkpointing and resume)
- [ ] `tests/test_schemas.py` — stubs for FOUND-02 (PydanticAI typed schemas)
- [ ] `tests/test_agent.py` — stubs for FOUND-02 (agent validation errors)
- [ ] `tests/test_routing.py` — stubs for FOUND-03 (dual-model routing)
- [ ] `tests/test_observability.py` — stubs for FOUND-04 (Langfuse trace verification)
- [ ] `tests/test_budget.py` — stubs for FOUND-05 (token budget enforcement)
- [ ] `pyproject.toml` — pytest configuration

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Langfuse trace visual inspection | FOUND-04 | Trace visualization requires Langfuse UI | Run pipeline, open Langfuse dashboard, verify trace shows model per step with latency and token counts |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
