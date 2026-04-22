---
phase: 6
slug: risk-management
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-22
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (per pyproject.toml) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/risk -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/risk -q`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 6-01-01 | 01 | 1 | RISK-01 | — | Deterministic veto (not LLM-produced) | unit | `uv run pytest tests/risk/test_policy_schema.py` | ❌ W0 | ⬜ pending |
| 6-02-01 | 02 | 1 | RISK-01 | — | Append-only portfolio state | unit | `uv run pytest tests/risk/test_portfolio_loader.py` | ❌ W0 | ⬜ pending |
| 6-03-01 | 03 | 2 | RISK-02 | — | Position-size rejection returns named limit | unit | `uv run pytest tests/risk/test_position_size.py` | ❌ W0 | ⬜ pending |
| 6-03-02 | 03 | 2 | RISK-03 | — | Sector concentration named-constraint violation | unit | `uv run pytest tests/risk/test_sector_check.py` | ❌ W0 | ⬜ pending |
| 6-03-03 | 03 | 2 | RISK-03 | — | Correlation check deterministic (golden fixture) | unit | `uv run pytest tests/risk/test_correlation.py` | ❌ W0 | ⬜ pending |
| 6-03-04 | 03 | 2 | RISK-03 | — | Drawdown historical-sim golden value | unit | `uv run pytest tests/risk/test_drawdown.py` | ❌ W0 | ⬜ pending |
| 6-04-01 | 04 | 3 | RISK-01 | — | Risk-manager agent produces rationale only (no status computed by LLM) | unit | `uv run pytest tests/risk/test_risk_manager_agent.py` | ❌ W0 | ⬜ pending |
| 6-05-01 | 05 | 3 | RISK-01 | — | `risk_manager_node` hard-overrides status via model_copy | unit | `uv run pytest tests/graph/test_risk_node.py` | ❌ W0 | ⬜ pending |
| 6-06-01 | 06 | 4 | RISK-01 | — | build_debate_pipeline routes veto to __end__, approved to signal | integration | `uv run pytest tests/graph/test_pipeline_with_risk.py` | ❌ W0 | ⬜ pending |
| 6-07-01 | 07 | 5 | RISK-01,02,03 | — | All 4 constraint fixtures produce structured "blocked by risk" output | integration | `uv run pytest tests/integration/test_phase6_e2e.py` | ❌ W0 | ⬜ pending |
| 6-07-02 | 07 | 5 | RISK-01 | — | policy_sha persisted on RiskAssessment for audit | integration | `uv run pytest tests/integration/test_policy_sha_audit.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/risk/__init__.py` — test package marker
- [ ] `tests/risk/conftest.py` — shared fixtures: sample portfolio CSV, sample policy YAML, golden price series, DebatePipelineState factory
- [ ] `tests/graph/conftest.py` extension — risk-aware pipeline factory (if not present)
- [ ] Golden-value fixtures committed under `tests/risk/fixtures/`:
  - `portfolio_sample.csv` (5-position paper portfolio across 3 sectors)
  - `risk_policy_sample.yaml` (known thresholds matching test expectations)
  - `returns_golden.parquet` (deterministic price history for correlation/drawdown goldens)
- [ ] Pre-Phase-5 regression: `tests/graph/test_pipeline_no_risk_backcompat.py` (ensures pipeline built without risk node behaves unchanged)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Policy YAML edits take effect on next pipeline run | RISK-01 | Config reload is runtime, not automated | 1. Edit `config/risk_policy.yaml` (tighten max_position_pct). 2. Re-run pipeline on the same fixture. 3. Verify `RiskAssessment.policy_sha` changed and veto triggers at the new limit. |
| End-to-end "blocked by risk" rendering in signal output | RISK-01 | Human review — confirms the UX message is clear | Run full pipeline on a known-violating thesis; read final output; confirm the constraint name, observed value, and limit are all present and human-readable. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
