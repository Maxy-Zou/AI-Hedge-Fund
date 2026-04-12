---
status: partial
phase: 03-single-agent-research
source: [03-VERIFICATION.md]
started: 2026-04-12
updated: 2026-04-12
---

## Current Test

[awaiting human testing]

## Tests

### 1. SC-2 — Langfuse trace tool-first verification
expected: Run research agent on real ticker, open Langfuse dashboard, confirm zero bare LLM-generated numbers — every metric preceded by a tool invocation
result: [pending]

### 2. SC-4 — Temporal correctness with different as_of_dates
expected: Run `uv run pytest tests/integration/test_research_pipeline.py -x -v -k "real_llm" --timeout=180` with ANTHROPIC_API_KEY + EDGAR_IDENTITY set. AAPL with as_of_date=2024-01-02 vs 2025-01-02 produce materially different theses
result: [pending]

### 3. Thesis quality subjective review
expected: Review generated thesis — source_tool fields are substantive, confidence scores reasonable, signal direction aligns with thesis
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
