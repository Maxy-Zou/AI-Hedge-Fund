---
status: partial
phase: 07-memory-and-learning
source: [07-VERIFICATION.md, 07-VALIDATION.md]
started: 2026-04-22
updated: 2026-04-22
---

## Current Test

[awaiting human testing — 1 readability check + 1 live-pipeline run]

## Tests

### 1. MEM-02 subjective readability — belief YAML is plain English
**expected:** A human can open a belief YAML and understand every field without consulting code or documentation. No opaque base64, SHA hashes (except `policy_sha` which is labeled), or encoded blobs appear in the body. Field names are self-descriptive (`thesis`, `confidence`, `sector`, `human_edited`, `field_locks`, `critique_history`).
**result:** [pending]
**how:**
1. Open `tests/memory/fixtures/belief_aapl.yaml` in a text editor.
2. Read top-to-bottom. Verify every field is either a plain-English string or a labeled scalar.
3. Do the same for `tests/memory/fixtures/belief_aapl_human_edited.yaml` and `tests/memory/fixtures/belief_aapl_field_locked.yaml`.
4. If all three are readable without extra context, mark `result: passed`. If any field requires code-reading to interpret, note which field and why.

**Estimated time:** 2 minutes.

### 2. MEM-03 live end-to-end — human edit reflected in next analysis via real pipeline + Langfuse trace
**expected:** A human edit to a belief YAML is visible in the analyst prompts of the next memory-enabled pipeline run for that ticker. The output thesis's confidence reflects the human override (not the machine-learned value the pipeline would have otherwise used).
**result:** [pending]
**how:**
1. Set `ANTHROPIC_API_KEY` and `LANGFUSE_*` env vars.
2. Copy `tests/memory/fixtures/belief_aapl_human_edited.yaml` to a beliefs directory where `confidence: 20` and `human_edited: true` are set; add a distinctive `human_note: "UAT test marker XYZ-2026"` line.
3. Run `build_debate_pipeline(with_memory=True, memory_deps=...)` end-to-end against AAPL with the beliefs directory pointing at the test location. Use a live Anthropic model (not TestModel).
4. Open the Langfuse trace. Verify:
   - The `memory_recall_node` produced `beliefs_consulted` containing the AAPL entry with `human_edited: true`, `confidence: 20`, `human_note: "UAT test marker XYZ-2026"`.
   - The analyst (fundamental/sentiment/technical) prompts include the belief text verbatim (or clearly reference the human-edited confidence).
   - The output `state["thesis"]["confidence"]` reflects the human override — either equals 20 or is clamped near it (not a free-running LLM estimate above 50).
5. If all three hold, mark `result: passed`. If the belief didn't reach the prompt, mark `result: failed` and open a gap.

**Estimated time:** 15-30 minutes (requires live API + Langfuse account; cost ~$0.50 per run).

### 3. MEM-04 live end-to-end — outcome-driven self-critique round-trip
**expected:** Optional companion to test 2. After a live analysis completes, run `ingest_outcome` with a simulated profit/loss; verify the belief YAML shows a new `revisions:` entry containing the outcome, the LLM-authored rationale, the deterministic new confidence, and `updated_at`.
**result:** [pending — OPTIONAL; the TestModel-stubbed e2e test covers the shape deterministically]
**how:**
1. After test 2 completes, run `uv run python -m ai_hedge_fund.scripts.ingest_outcome --ticker AAPL --outcome-pct 0.05 --as-of <today> --beliefs-dir <path>` with live Anthropic API.
2. Re-open the AAPL belief YAML. Verify a new `revisions:` entry appended with:
   - `outcome: 0.05` (or similar)
   - `source: self_critique`
   - A non-empty `rationale` string (LLM-authored, natural language)
   - `new_confidence` that matches `compute_new_confidence(prior, 0.05, signal_direction)` deterministically
   - A fresh `updated_at` timestamp
3. If all four fields are present and correctly populated, mark `result: passed`.

**Estimated time:** 5 minutes on top of test 2.

---

## Acceptance

Phase 7 is code-complete and verified automatically. These UAT items live here until validated. Partial validation acceptable — test 1 alone establishes MEM-02 subjective bar; test 2 alone establishes MEM-03 live loop.

**Update instructions:** When a test is run, replace `result: [pending]` with `result: passed | failed | skipped` and append a short note. If all tests pass, update frontmatter `status: partial` → `status: resolved` and `updated: <ISO>` timestamp.
