---
status: partial
phase: 05-adversarial-critique
source: [05-VERIFICATION.md, 05-VALIDATION.md]
started: 2026-04-22T01:30:00Z
updated: 2026-04-22T01:30:00Z
---

## Current Test

[awaiting human testing — all 5 items require real Anthropic API + Langfuse]

## Tests

### 1. DEBATE-04 SC-4: 30%-of-runs confidence delta
expected: Running build_debate_pipeline with real Anthropic API on >=10 tickers shows `post_debate_confidence != pre_debate_confidence` (delta >=5) in >=3 of 10 runs
result: [pending]
how: Set ANTHROPIC_API_KEY, run compiled build_debate_pipeline on 10 different tickers with the same seed thesis, record `state["thesis"]["confidence"] - pre_debate_confidence` per run, assert ratio >= 0.3.

### 2. DEBATE-02 semantic alignment: bear actually rebuts named bull claims
expected: Sample 5 real-LLM debates; for each `BearCase.addressed_bull_claims` entry, verify it is a verbatim/near-verbatim paraphrase of a `BullCase.claims[i].claim` produced by the Bull Advocate in that run
result: [pending]
how: Inspect Langfuse traces for 5 runs; manually compare BearCase.addressed_bull_claims strings against the preceding BullCase.claims list. Schema enforces count + non-empty + cross-link (per WR-01/WR-02 fixes); only semantic paraphrase correctness remains.

### 3. Sycophancy audit: bull/bear capitulation mid-debate
expected: Sample 5 real-LLM debates; flag any BearCase or final_arguments[bear] that contains agreement language ("you're right", "I concede", "good point"); fail if >1/5 show capitulation
result: [pending]
how: Grep/visual-review the Langfuse trace outputs. Documented MAD failure mode (arxiv 2509.23055). If >1/5 found, strengthen BEAR_SYSTEM_PROMPT adversarial priming.

### 4. Token cost per debate <= $1.00
expected: Run 3 real-LLM debates end-to-end; inspect Langfuse traces; assert total cost per run <= $1.00
result: [pending]
how: Set LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST, run 3 debates, read trace cost totals. Research estimate was ~$0.75/debate; real measurement needed.

### 5. Langfuse trace audit: structured debate events visible
expected: Langfuse shows 10 distinct agent spans (3 analysts + manager + bull + bear + rebuttal + final_arguments + debate_synthesis + signal) per pipeline run with structlog events (`bull_complete`, `bear_complete`, etc.) attached
result: [pending]
how: Run one real-LLM debate, open Langfuse UI, verify span hierarchy matches the sequential debate chain and structlog fields (input/output/total tokens, pre_conf/post_conf/quality for synthesis) are visible.

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps

(none yet — fill in after real-LLM runs)
