---
name: phase-exec
description: Execute a split phase wave by wave - serial tasks in the main session, parallel tasks as TDD subagents in isolated git worktrees - merging and running the full gate after each wave. Use when the user runs /phase-exec after /phase-split has written the LEDGER. Next step - /phase-review.
argument-hint: "[phase number] [--from-wave N]"
disable-model-invocation: true
---

# phase-exec

Implement the plan with tests first, as fast as the wave schedule allows, without losing track
of state. The ledger `<NN>-LEDGER.md` is the source of truth -- conversation memory does not
survive compaction, and re-running a finished task is the most expensive failure mode.

## Preconditions (check, don't assume)

- On branch `phase/<NN>-<slug>`, working tree clean.
- `<NN>-PLAN.md` has `status: signed-off`; `<NN>-LEDGER.md` exists with waves.
- Postgres is up (`docker compose up -d`) with the `ai_hedge_fund_test` database. Postgres
  tests skip unless `TEST_DATABASE_URL` is set, so the gate below sets it explicitly.
- Read the ledger. Start at the first wave with a task not `done`. Never redo a `done` task.

## Per wave

1. **Serial wave** (one task): implement it in the main session and **commit it** before the
   next wave -- worktrees start from the phase branch's committed `HEAD`, so uncommitted
   scaffold work is invisible to parallel agents.
2. **Parallel wave:** in **one message**, launch one `Agent` per task with
   `isolation: "worktree"` and `run_in_background: false`. Each prompt must be self-contained:
   - the task's YAML entry, the PLAN's **Interfaces** section, and the pre-mortem entries whose
     node ids live in files this task owns;
   - "Write the failing tests first and run them to see them fail; then implement until they
     pass; then refactor. Run `uv run pytest <your test files> -q` and ruff on your files.";
   - "Edit only files you own: <list>. If you need to change any other file, stop and report
     what and why instead of editing it.";
   - "Do not set `TEST_DATABASE_URL`: Postgres tests share one database and run in the wave
     gate after merging, not in parallel worktrees.";
   - "Commit with a conventional message (`test:` then `feat:`) on your worktree branch and
     report the branch name, commits, and anything that deviated from the Interfaces section."
3. **Merge in plan order** into the phase branch (`git merge --no-ff <branch>`). On any
   conflict, stop: a conflict means the ownership in the PLAN was wrong. Resolve it by hand, fix
   the task block so the scheduler would have caught it, and note it in the ledger.
4. **Gate** (every wave, after merging):
   ```bash
   TEST_DATABASE_URL=postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund_test uv run pytest -q -rs
   uv run ruff format --check . && uv run ruff check .
   uv run python -m ai_hedge_fund.devtools.premortem_check .planning/phases/<NN>-<slug>/<NN>-PLAN.md --done <every finished task id>
   ```
   All three must pass. In the `-rs` output no skip reason may mention `TEST_DATABASE_URL` --
   a skipped Postgres test is a gate failure, not a pass. `--done` limits the pre-mortem check
   to tests in files owned by finished tasks, so it is green mid-phase only if nothing done is
   missing.
5. **Update the ledger** (status, commits, notes) and commit it. If any task changed an
   interface, update the PLAN's Interfaces section in the same commit -- the plan stays live.

## After the last wave

`premortem_check` without `--done` must report **0 missing**. A test that is genuinely
impossible now (e.g. needs live credentials) gets `deferred: "TECH-DEBT: <reason>"` in the
manifest and a matching `.planning/TECH-DEBT.md` entry -- never a silent drop.

## When to stop and ask the user

Only for: an action that is irreversible or outward-facing (live credentials, real orders,
pushing), a change that contradicts a signed-off Decision, or the same gate failing after two
fix attempts. Everything else, decide, record the ruling in the ledger's Notes, and continue.

Finish by telling the user the next step is `/phase-review`.
