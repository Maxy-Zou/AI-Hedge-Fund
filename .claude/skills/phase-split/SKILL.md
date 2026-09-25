---
name: phase-split
description: Split a signed-off phase PLAN.md into parallel execution waves by file ownership, restructure tasks so more of them can run concurrently, and write the wave schedule to the phase LEDGER. Use after /phase-plan is signed off. Next step - /phase-exec.
argument-hint: "[phase number]"
---

# phase-split

Turn the plan's `phase-tasks` block into waves that run concurrently without merge conflicts.
Parallelism is decided by a script, not by judgment: two tasks can share a wave only if they own
disjoint files, neither reads what the other writes, and neither touches a shared hotspot.

## Steps

1. Locate `.planning/phases/<NN>-<slug>/<NN>-PLAN.md`. Refuse if `status` is not `signed-off`
   -- tell the user to finish `/phase-plan` first.

2. Run the scheduler:
   ```bash
   uv run python -m ai_hedge_fund.devtools.waves .planning/phases/<NN>-<slug>/<NN>-PLAN.md
   ```
   Exit 1 means the task block is invalid (unknown key, cycle, missing `owns`); fix the PLAN.
   Hotspots (always run alone) are listed in `HOTSPOT_PATTERNS` in
   `src/ai_hedge_fund/devtools/waves.py`: lockfile, migrations, `config.py`, `db/models.py`,
   graph state/wiring, `conftest.py`, `__init__.py`, planning docs.

3. **Widen the waves.** Read each `note:` line; each one is a serialization you might remove:
   - `both own <file>` between leaf tasks -- move that shared edit into the T0 scaffold
     (e.g. declare both error classes in `errors.py` up front), leaving each leaf task to own
     only its new module and test file.
   - `reads <file>` -- if the reader needs only the *interface*, have T0 create a stub with the
     final signature so the reader depends on T0, not on the full implementation.
   - A leaf task marked serial only because it touches `__init__.py` -- move the export to T0.
   Edit the PLAN's task block (a plan change, so commit it) and rerun until the notes left are
   true dependencies. Do not split a task below "one module + its tests"; a task too small to
   test alone is not worth a worktree.

4. **Sanity-check width.** Default cap is 4 concurrent tasks (`--max-parallel`). More than that
   rarely pays: the review and merge after each wave are serial, and this repo's phases have had
   at most ~4 independent leaf tasks.

5. **Write the ledger** `.planning/phases/<NN>-<slug>/<NN>-LEDGER.md`:
   ```markdown
   # Phase <NN> -- Ledger
   Source of truth for progress; read this first after any context compaction.

   ## Waves
   <paste the scheduler output>

   ## Progress
   | Task | Wave | Status | Commit(s) | Notes |
   |---|---|---|---|---|
   | T0 | 1 | pending | | |

   ## Review
   (filled by /phase-review)
   ```
   Commit PLAN edits and the ledger together.

6. Show the user the waves in one short table and say the next step is `/phase-exec`.
