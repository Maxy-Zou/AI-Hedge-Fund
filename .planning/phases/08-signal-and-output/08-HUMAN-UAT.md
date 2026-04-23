---
status: partial
phase: 08-signal-and-output
source: [08-VERIFICATION.md, 08-VALIDATION.md]
started: 2026-04-23
updated: 2026-04-23
---

## Current Test

[awaiting human testing — both items require live ANTHROPIC_API_KEY + running pipeline + Langfuse]

## Tests

### 1. SIG-03 Reviewer packet usability — human reads Markdown review request and forms an informed decision
**expected:** A reviewer can open the stdout Markdown + the `/tmp/review-<thread_id>.json` full-detail JSON from `scripts/run_analysis.py`, read them, understand the thesis/debate/risk context, and decide APPROVED or REJECTED with a meaningful reviewer_note. Markdown structure is clear (thesis summary, direction, conviction, risk fields, debate highlights all present and labeled).
**result:** [pending]
**how:**
1. Set `ANTHROPIC_API_KEY` and `LANGFUSE_*` env vars.
2. Pick a ticker with expected high conviction (e.g., a well-known large-cap with strong fundamentals).
3. Run `uv run python -m ai_hedge_fund.scripts.run_analysis --ticker <TICKER> --as-of 2026-04-22`.
4. Wait for the review gate to fire (pipeline will print the Markdown review packet and pause on stdin).
5. Inspect the Markdown structure: does it clearly show the thesis summary, direction, conviction, all five SIG-01 fields, risk_assessment, a useful debate excerpt? Is anything missing?
6. Open `/tmp/review-<thread_id>.json` in an editor and verify the full context is there for drill-down.
7. Decide (APPROVED / REJECTED) + enter a reviewer_note. Verify the pipeline completes cleanly after your decision.
8. Mark result `passed` if the packet was sufficient to decide in <2 minutes. If the packet was confusing or missing context, mark `failed` and log a gap.

**Estimated time:** 10-15 minutes (including a real LLM run; cost ~$0.50-$1.00).

### 2. SIG-04 Audit reconstruction — compliance reviewer traces a real signal backward in <5 minutes
**expected:** Given a signal's `episodic_id` from a live run, `scripts/audit_reconstruct.py` produces output containing the analysis row, the review row (if any), both `policy_sha` values (risk + review), the Langfuse thread_id hint, and a timestamp. A human compliance reviewer can follow the chain from final signal back to every agent that contributed within 5 minutes.
**result:** [pending]
**how:**
1. Complete UAT item 1 first (produces a live episodic_id).
2. Note the `episodic_id` printed at the end of `run_analysis` (or query `episodic_memory` directly: `SELECT id FROM episodic_memory ORDER BY id DESC LIMIT 1`).
3. Run `uv run python -m ai_hedge_fund.scripts.audit_reconstruct --episodic-id <id>`.
4. Verify output contains:
   - the analysis row (ticker, as_of_date, signal fields, payload)
   - the review row (if review gate fired; with `record_type='review'` and `review_policy_sha`)
   - `policy_sha` AND `review_policy_sha` populated
   - a Langfuse thread_id hint (for correlation with the Langfuse UI)
5. Open the Langfuse UI, navigate to the thread_id, verify the per-agent spans (input/output/model/tokens/timestamp) are all present and sensible.
6. Time yourself: how long from "here is an episodic_id" to "I understand every step that produced this signal"? If under 5 minutes, mark `passed`. If longer, identify the bottleneck and mark `failed`.

**Estimated time:** 5-10 minutes (on top of UAT item 1).

---

## Acceptance

Phase 8 is code-complete and verified automatically (4/4 ROADMAP criteria pass). These 2 UAT items live here until validated. Partial validation acceptable.

**Update instructions:** When a test is run, replace `result: [pending]` with `result: passed | failed | skipped` and append a short note. If both tests pass, update frontmatter `status: partial` → `status: resolved`.
