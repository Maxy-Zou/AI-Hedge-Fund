---
name: phase-plan
description: Plan a ROADMAP phase or any multi-file feature before coding - research in parallel, probe vendor APIs, and write one PLAN.md holding decisions, interfaces, a machine-readable task list, and the pre-mortem as a test manifest. Use when starting a new phase, when the user asks to plan/spec/design a feature, or when a change touches schema, the pipeline graph, or an external API. Skip for changes describable in one sentence (go straight to TDD + /code-review). Next step - /phase-split.
argument-hint: "[phase number or feature description]"
---

# phase-plan

Produce **one** document, `.planning/phases/<NN>-<slug>/<NN>-PLAN.md`, that a human signs off
and every later skill reads. It replaces the old PLAN + SPEC + PREMORTEM trio: in Phase 10 the
SPEC froze at sign-off while the code moved on, and five pre-mortem tests were named but never
written. Keep it short -- decisions and contracts, not implementation prose.

## Size gate

If the change fits in one sentence ("add a --limit flag to portfolio_view"), stop and say so:
TDD it directly and run `/code-review`. This skill is for work with interfaces other code will
depend on.

## Steps

1. **Load context.** Read the phase entry in `.planning/ROADMAP.md`, the requirement ids it
   cites in `.planning/REQUIREMENTS.md`, the previous phase's `SUMMARY.md`, and open items in
   `.planning/TECH-DEBT.md` that this phase touches.

2. **Research in parallel (read-only).** Launch the independent questions at once as `Explore`
   agents in a single message: modules this phase touches and their existing patterns to reuse;
   tests and fixtures that already cover neighbouring code; library docs via context7 for any
   dependency the phase leans on. Reads never conflict, so fan out freely.

3. **Probe every external contract before designing against it.** For each vendor API the phase
   calls (broker, data source, LLM feature), get real response and error shapes -- from a probe
   against the sandbox/paper endpoint (see `scripts/probe_data_apis.py`) or the vendor's current
   docs -- and save them as test fixtures. Never write an error-code mapping from memory: Phase 10
   guessed Alpaca's duplicate-order code wrong and only a live probe caught it.

4. **Write the PLAN** from [template.md](template.md). Rules the task list must satisfy:
   - Every task lists the exact files it `owns` (source *and* its tests), what it `reads`, and
     what it `depends` on. `/phase-split` schedules from this block, so be exact.
   - Put shared edits in a **T0 scaffold task**: new error classes, config fields, test fakes,
     ORM columns, migration file (reserve its number), `__init__` exports, dependency adds.
     Leaf tasks then only create new modules and can run in parallel.
   - At least one test drives the **real entry point** (CLI `_main`, graph build), not only the
     inner function -- Phase 10's CLI wrapper broke while inner-function tests stayed green.
   - Anything touching schema, column widths, CHECKs, or triggers gets a test that runs on
     **Postgres**; SQLite ignores VARCHAR length and let a crash through in Phase 10.

5. **Pre-mortem as a manifest.** Assume the phase shipped and failed three months later. List
   failure modes (data integrity, temporal leakage, cost, security, vendor drift, fail-open
   parsing) in the `phase-premortem` block, each with the invariant it breaks and the **full
   pytest node id** of the test that would catch it. These tests do not exist yet; they are the
   RED list for `/phase-exec`, and `premortem_check` will fail the gate until every one exists.

6. **Validate the blocks:**
   ```bash
   uv run python -m ai_hedge_fund.devtools.waves .planning/phases/<NN>-<slug>/<NN>-PLAN.md
   ```
   It must exit 0. (Do not expect `premortem_check` to pass yet.)

7. **Sign-off.** Commit the PLAN on `phase/<NN>-<slug>` (cut from `main`), then show the user
   only the **Decisions** list, with your recommendation per decision and which ones genuinely
   need them. Keep it reviewable in two minutes. On approval set `status: signed-off` and
   `signed_off: <date>` in the frontmatter and commit it (`docs(<NN>): sign off plan`).

8. Tell the user the next step is `/phase-split`.

## The plan stays live

When execution or review changes an interface, update the **Interfaces** section in the same
commit as the code. Do not park design changes in a "Deviations" list.
