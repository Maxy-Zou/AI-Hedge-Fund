---
phase: 7
slug: memory-and-learning
status: all_fixed
fix_scope: critical_warning
findings_in_scope: 3
fixed: 3
skipped: 0
iteration: 1
created: 2026-04-22
---

# Phase 7 — Code Review Fix Report

> Auto-fix report for the 3 warnings identified in `07-REVIEW.md`. All warnings resolved in a single iteration. 6 Info findings are out of scope per `fix_scope: critical_warning`.

---

## Scope

| Severity | In REVIEW.md | In scope | Fixed | Skipped |
|----------|--------------|----------|-------|---------|
| Critical | 0 | 0 | — | — |
| Warning  | 3 | 3 | 3 | 0 |
| Info     | 6 | 0 (out of scope) | — | — |
| **Total** | **9** | **3** | **3** | **0** |

Iteration: 1 of 1 (no re-review loop — all warnings resolved in first pass).

---

## Fixes Applied

### WR-01 — Regex guard on sector belief path (defense-in-depth)

**File:** `src/ai_hedge_fund/graph/nodes.py` (memory_recall_node sector branch)
**Finding:** `sector` string flowed into `beliefs_path / "sectors" / f"{sector}.yaml"` without the same `[A-Z0-9.\-]{1,10}` guard used for the ticker subtree. If a caller bypassed `CandidateMetadata` validation and injected a raw dict with a malicious sector string, path traversal was possible.
**Fix:** Added an explicit regex validation before the sector path join — a malformed sector now raises `ValueError` (consistent with `belief_path_for_ticker`) rather than silently traversing. Aligns with the project's tool-first / validate-at-boundaries invariant (CLAUDE.md).
**Commit:** `64d07b2 fix(07): WR-01 add regex guard on sector belief path`
**Regression check:** All memory + graph tests green.

### WR-02 — Log orphan outcome row before FileNotFoundError

**File:** `src/ai_hedge_fund/scripts/ingest_outcome.py`
**Finding:** When `ingest_outcome` committed the outcome EpisodicMemory row before discovering the belief YAML was missing, the `FileNotFoundError` propagated with no `logger.warning`. Operators had no signal that an orphan row existed and needed follow-up (manual belief creation or row cleanup).
**Fix:** Added a structured `logger.warning("orphan_outcome_row_created", ticker=..., episodic_id=..., belief_path=...)` call between the DB commit and the belief-file read. Orphan rows are still created by design (DB INSERT is valuable partial progress), but now operator-visible.
**Commit:** `bea30b0 fix(07): WR-02 log orphan outcome row before FileNotFoundError`
**Regression check:** `test_ingest_outcome_missing_belief_file` still passes (outcome row + FileNotFoundError both asserted); new log emission is observable via structlog capture.

### WR-03 — Pin `observed_date` nullable=False in mixin + migration

**Files:** `src/ai_hedge_fund/db/base.py` (DualTimestampMixin), `alembic/versions/003_create_episodic_memory.py`
**Finding:** `observed_date` column was implicitly `nullable=True`. A future row insert with `observed_date=None` would succeed at both the ORM and DDL layers, silently defeating the temporal audit trail that underpins the look-ahead-bias defense.
**Fix:** Added `nullable=False` to both the mapped column in `DualTimestampMixin` and the DDL in the Alembic 003 migration. `server_default=func.now()` still populates the value at the DB boundary; the non-null now makes a caller-supplied `None` a type error rather than a silent NULL row.
**Commit:** `ce69156 fix(07): WR-03 pin observed_date nullable=False in mixin + migration`
**Regression check:** 234 tests across tests/memory + tests/graph + tests/integration/test_phase7_* all green. Full Phase 7 subsuite unchanged.

---

## Commit Trail

| # | Hash | Finding | Message |
|---|------|---------|---------|
| 1 | `64d07b2` | WR-01 | fix(07): WR-01 add regex guard on sector belief path |
| 2 | `bea30b0` | WR-02 | fix(07): WR-02 log orphan outcome row before FileNotFoundError |
| 3 | `ce69156` | WR-03 | fix(07): WR-03 pin observed_date nullable=False in mixin + migration |

---

## Out-of-scope (Info findings, deferred to backlog)

The 6 Info findings from 07-REVIEW.md were NOT fixed in this pass (fix_scope=critical_warning). They are minor hardening items to be deferred to a future chore phase or handled opportunistically:

- IN-01: Extract magic numbers (retention 90 days, per-event delta cap 10, recall limit 10) to named constants.
- IN-02: Add a Postgres CHECK constraint on `record_type` (enum-like values: 'analysis' | 'outcome').
- IN-03: Share the ticker regex between belief and episodic schemas (currently duplicated).
- IN-04: Normalise stray Unicode em dash (—) to ASCII where it appears in user-facing strings.
- IN-05: Docstring typos noted by the reviewer — cosmetic.
- IN-06: Consider adding a module-level `__all__` to `memory/beliefs.py` and `memory/critique.py`.

---

## Next Steps

- `/gsd-verify-work` — phase verification (goal-backward check)
- REVIEW-FIX status: `all_fixed` — no further fixes needed for critical + warning severity
- Info findings remain on the backlog for future cleanup

---

*Fix iteration 1 of 1. All in-scope findings resolved. Regression surface clean.*
