---
name: phase-review
description: Review a finished phase branch with independent fresh-context reviewers running in parallel, one per risk area (spec compliance, database fidelity, vendor contracts, entry points, fail-closed/security, temporal and data integrity), then fix confirmed findings test-first with a single targeted re-review. Use after /phase-exec completes, or when the user asks to review a phase or feature branch before its PR. Next step - /phase-ship.
argument-hint: "[phase number or branch]"
---

# phase-review

One review, run in parallel, instead of sequential rounds. In Phase 10 the author's self-review
missed a critical Postgres crash that an independent reviewer later found, and each fix batch
needed another full round. Reviewers here never see the implementation conversation -- only the
diff, the PLAN, and their brief.

## Steps

1. **Gather inputs:** `git diff main...HEAD --stat`, the full diff, `<NN>-PLAN.md`, and the
   Agent Development Rules in `CLAUDE.md`. Confirm `/phase-exec`'s final gate passed; if not,
   stop -- review is not a substitute for a green suite.

2. **Launch every lens in one message** as read-only `general-purpose` agents, in the
   background, so no lens reads another's output. Each gets: the diff range, the PLAN path, its
   brief below, and the output contract. Skip a lens only if the diff has nothing in its area
   (say which you skipped and why).

   | Lens | Brief |
   |---|---|
   | Spec compliance | Every Decision, Interface, and success criterion is implemented as written; every criterion's proving test exists and asserts the criterion (not something weaker). |
   | Database fidelity | Migrations reversible and matching the ORM; column widths, CHECKs, triggers, and append-only rules hold **on Postgres** (SQLite hides width and trigger bugs); any schema-touching path has a Postgres-run test. |
   | Vendor contracts | Every assumption about an external API (error codes, status values, retry/idempotency semantics, rate limits) is backed by a probed fixture or dated doc, not memory; retries cannot double-submit. |
   | Entry points and tests | Each feature is exercised through its real entry point (CLI `_main`, graph build, DI factories); find tests that cannot fail, tests of mocks rather than behaviour, and pre-mortem tests that don't actually check their invariant. |
   | Fail-closed and security | Parsers and guards reject unexpected input (unknown enum values, casing, substring URL checks); secrets never reach logs, payloads, or error messages; no live endpoints reachable from paper paths. |
   | Temporal and data integrity | As-of filtering on every read, filing date not period end, UTC timestamps, append-only writes, no float money, deterministic tie-breaks, tool-first (no LLM computing numbers). |

   **Output contract** for every lens: a list of findings, each with severity
   (CRITICAL/HIGH/MEDIUM/LOW), `file:line`, a concrete failure scenario (input -> wrong result),
   and the RED test that would prove it. Correctness and requirement gaps only -- no style, no
   speculative refactors. "No findings" is a valid answer.

3. **Triage** in the main session: dedupe across lenses, then confirm each CRITICAL/HIGH by
   writing its RED test and watching it fail. A finding whose test passes is rejected -- record
   it as such. MEDIUM/LOW go to `.planning/TECH-DEBT.md` with a one-line ruling, unless trivial
   to fix now.

4. **Fix** each confirmed finding test-first, one commit per finding or tight group
   (`fix(<area>): ...`). Update the PLAN's Interfaces section in the same commit if a contract
   changed.

5. **One targeted re-review:** a single fresh agent gets only the fix diff
   (`git diff <pre-fix-sha>..HEAD`) plus the confirmed findings, and checks each fix closes its
   finding without breaking a neighbour. If it finds a new CRITICAL, fix it and re-review that
   fix once more; after that, stop and bring the user in rather than looping.

6. **Record** in the ledger's Review section: per lens, findings raised / confirmed / rejected /
   deferred, and the commits that fixed them. Rerun the full gate from `/phase-exec`.

7. Tell the user the outcome in a few lines and that the next step is `/phase-ship`.
