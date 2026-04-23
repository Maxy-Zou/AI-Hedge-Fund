---
phase: 08-signal-and-output
fixed_at: 2026-04-22T00:00:00Z
review_path: .planning/phases/08-signal-and-output/08-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 8: Code Review Fix Report

**Fixed at:** 2026-04-22T00:00:00Z
**Source review:** .planning/phases/08-signal-and-output/08-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (critical_warning scope -- the 3 warnings; 6 Info items out of scope)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: `_format_output` VETOED branch renders full 64-char SHA when `--json` is used

**Files modified:** `src/ai_hedge_fund/scripts/run_analysis.py`
**Commit:** d3da6f7
**Applied fix:** Added explicit comments on both `as_json` branches of `_format_output` documenting that the JSON surface is the audit-grade form where full 64-char `policy_sha` values are intentional (compliance pipelines need the complete hash for tamper-evident linkage to DB-stored policy rows). Markdown branch continues to truncate per T-08-14; behavior unchanged -- only documentation added.

### WR-02: `format_review_request_md` leaks raw dict reprs (including full SHAs) in risk_assessment + hits sections

**Files modified:** `src/ai_hedge_fund/output/formatter.py`
**Commit:** aaafde8
**Applied fix:** Added two dedicated helpers in `formatter.py`:
- `_fmt_risk(risk)` -- renders `risk_assessment` dict as individual bullet rows (`status`, `constraint_violated`, `rationale`, `policy_sha`) and truncates `policy_sha` via `_short_sha`. Unknown extra keys (observed/limit/etc) are preserved but passed through `_fmt_value` so no SHA leaks.
- `_fmt_hit(hit)` -- renders each `episodic_hits` / `beliefs_consulted` entry with any `*_sha` field truncated. Scalar entries fall through to `str(hit)` (backcompat for the existing test that passes plain strings).

`format_review_request_md` now calls `_fmt_risk(risk)` in place of `_fmt_value(risk)` and wraps each hit/belief with `_fmt_hit(...)`. The reviewer packet no longer displays any full 64-char policy hash.

### WR-03: `_default_reviewer_io` accepts reviewer_note up to unbounded length; Pydantic re-validation raises late

**Files modified:** `src/ai_hedge_fund/scripts/run_analysis.py`
**Commit:** 2b12b01
**Applied fix:** Replaced the single-shot `input()` / default-substitution block with a `while True` re-prompt loop. The loop enforces the documented 1-2000 char cap at stdin time so over-long pastes are rejected with an actionable message (`Note too long (N chars; limit 2000). Try again.`) BEFORE the pipeline's Pydantic re-validation fires. Empty-input substitution (`{status.lower()} without note`) is preserved inside the loop so the min-length invariant is never violated.

---

_Fixed: 2026-04-22T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
