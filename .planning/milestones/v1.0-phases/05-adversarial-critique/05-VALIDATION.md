---
phase: 5
slug: adversarial-critique
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-21
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (existing in pyproject.toml) |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `uv run pytest tests/unit/ -x --ff` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~30-60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -x --ff`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 5-01-01 | 01 | 1 | DEBATE-01, DEBATE-02, DEBATE-03 | — | Schemas reject empty/short substantive fields | unit | `uv run pytest tests/unit/test_debate_schemas.py` | ❌ W0 | ⬜ pending |
| 5-01-02 | 01 | 1 | DEBATE-01 | — | Bull agent: REASONING tier, zero tools, ≥2 retries, source_analyst citations required | unit | `uv run pytest tests/unit/test_bull_agent.py` | ❌ W0 | ⬜ pending |
| 5-01-03 | 01 | 1 | DEBATE-02 | — | Bear agent: REASONING tier, zero tools, addressed_bull_claims min_length=2 | unit | `uv run pytest tests/unit/test_bear_agent.py` | ❌ W0 | ⬜ pending |
| 5-02-01 | 02 | 2 | DEBATE-03 | — | DebatePipelineState extends MultiAgentPipelineState; act fields have appropriate reducers | unit | `uv run pytest tests/unit/test_debate_state.py` | ❌ W0 | ⬜ pending |
| 5-02-02 | 02 | 2 | DEBATE-03, DEBATE-04 | — | Rebuttal, final, synthesis agents — REASONING tier, zero tools, sequential state reads | unit | `uv run pytest tests/unit/test_rebuttal_agent.py tests/unit/test_final_arguments_agent.py tests/unit/test_debate_synthesis_agent.py` | ❌ W0 | ⬜ pending |
| 5-02-03 | 02 | 2 | DEBATE-04 | — | compute_quality_score deterministic weighted mean of evidence/logic/risk | unit | `uv run pytest tests/unit/test_quality_score.py` | ❌ W0 | ⬜ pending |
| 5-03-01 | 03 | 3 | DEBATE-03 | — | 5 debate nodes follow Phase 4 error-propagation idiom | unit | `uv run pytest tests/unit/test_debate_nodes.py` | ❌ W0 | ⬜ pending |
| 5-03-02 | 03 | 3 | DEBATE-03 | — | build_debate_pipeline: sequential bull→bear→rebuttal→final→synthesis | unit | `uv run pytest tests/unit/test_debate_pipeline_builder.py` | ❌ W0 | ⬜ pending |
| 5-03-03 | 03 | 3 | DEBATE-03, DEBATE-04 | — | Integration: compiled graph runs 5 acts in order with TestModel, missing act raises ValidationError | integration | `uv run pytest tests/integration/test_debate_pipeline.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_debate_schemas.py` — stubs for BullCase, BearCase, RebuttalAct, FinalArgument, DebateSynthesis
- [ ] `tests/unit/test_bull_agent.py` — agent wiring stubs (tier, tools=[], retries, system prompt)
- [ ] `tests/unit/test_bear_agent.py` — agent wiring stubs + addressed_bull_claims constraint
- [ ] `tests/unit/test_debate_state.py` — DebatePipelineState reducer stubs
- [ ] `tests/unit/test_rebuttal_agent.py` — rebuttal agent wiring stubs (clone of test_bull_agent.py with REBUTTAL role)
- [ ] `tests/unit/test_final_arguments_agent.py` — final_arguments agent wiring stubs
- [ ] `tests/unit/test_debate_synthesis_agent.py` — synthesis agent wiring stubs (REASONING tier, output_tokens_limit inherits default)
- [ ] `tests/unit/test_quality_score.py` — compute_quality_score pure-function stubs
- [ ] `tests/unit/test_debate_nodes.py` — node wrapper stubs (happy path + error propagation)
- [ ] `tests/unit/test_debate_pipeline_builder.py` — builder-level wiring assertions
- [ ] `tests/integration/test_debate_pipeline.py` — TestModel-driven compiled-graph stubs
- [ ] `tests/conftest.py` — extend with debate fixtures if needed (reuse Phase 4's TestModel patterns)

*Existing pytest infrastructure covers framework installation.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Post-debate confidence differs from pre-debate in ≥30% of real-LLM runs | DEBATE-04 | Requires real Opus calls; deterministic TestModel can't produce distributional shift | Run debate pipeline 10× on same thesis with real Anthropic API; count runs where `abs(post_confidence - pre_confidence) >= 0.05`; ≥3/10 expected |
| Bear agent actually rebuts bull claims by name (semantic, not just count) | DEBATE-02 | Schema enforces `addressed_bull_claims: list[str] with min_length=2` but not semantic alignment | Sample 5 real-LLM debates; manually verify each listed claim is quoted/paraphrased from BullCase.claims |
| Sycophancy audit — bull or bear capitulating mid-debate | DEBATE-02 | Documented MAD failure mode (arxiv 2509.23055); not catchable via schema | Sample 5 real-LLM debates; check BearCase and final_arguments[bear] for agreement language ("you're right", "I concede", etc.); flag if >1/5 |
| Token cost per debate ≤ $1.00 | Budget guardrail | Real-LLM cost varies with output length; estimate is ~$0.75 | Run 3 real-LLM debates; inspect Langfuse traces; assert total ≤ $1.00/run |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
