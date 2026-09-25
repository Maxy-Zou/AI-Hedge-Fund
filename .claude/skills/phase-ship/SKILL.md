---
name: phase-ship
description: Close out a reviewed phase - run the final verification gates, write the SUMMARY mapping each success criterion to its proof, update ROADMAP/REQUIREMENTS/TECH-DEBT/PROGRESS, push the branch, and open the pull request. Use when the user runs /phase-ship after /phase-review.
argument-hint: "[phase number]"
disable-model-invocation: true
---

# phase-ship

Everything that happens once, at the end, so the other stages stay about code. Never merge the
PR yourself -- the user merges.

## Steps

1. **Final gates** -- all must pass; paste the tail of each into the SUMMARY:
   ```bash
   uv sync --frozen --extra dev
   TEST_DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund_test uv run pytest -q -rs
   uv run ruff format --check . && uv run ruff check .
   uv run python -m ai_hedge_fund.devtools.premortem_check .planning/phases/<NN>-<slug>/<NN>-PLAN.md
   ```
   No skip reason may mention `TEST_DATABASE_URL`. The ledger's Review section must show no
   open CRITICAL/HIGH. If anything fails, stop and report; do not ship around it.

2. **Write `<NN>-SUMMARY.md`** (keep it under ~80 lines):
   - Success criteria table: each ROADMAP criterion -> the test node id or command that proves
     it -> pass.
   - Test counts before -> after, and suite wall time.
   - Review outcome: one line per lens from the ledger.
   - Deferred items with their TECH-DEBT entries.
   - Refer to work by **file path and test node id**, not commit hashes -- merges rewrite
     hashes, and 10-SUMMARY ended up citing a commit that doesn't exist on `main`. Add the PR
     number in a follow-up commit once step 4 opens it.
   The PLAN's Interfaces section should already match the code; if it doesn't, fix the PLAN now
   rather than writing a Deviations list.

3. **Update tracking docs** in one `docs(<NN>): ...` commit: ROADMAP (phase complete,
   criteria checked), REQUIREMENTS (status per requirement id), TECH-DEBT (new deferred items;
   close any this phase resolved), and a concise `docs/PROGRESS.md` entry at the top.

4. **Open the PR:** push with `-u`, then `gh pr create` against `main`. Body: goal, links to
   PLAN / LEDGER / SUMMARY, the success-criteria table, review summary, deferred items, and a
   test plan checklist. End the body with the attribution line from the current session's
   instructions.

5. Give the user the PR link and anything that needs them (e.g. a live-credential smoke test
   they must run themselves). Delete the phase branch only after they merge.
