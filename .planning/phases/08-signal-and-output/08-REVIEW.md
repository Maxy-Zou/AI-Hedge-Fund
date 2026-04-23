---
phase: 08-signal-and-output
reviewed: 2026-04-22T00:00:00Z
depth: standard
files_reviewed: 37
files_reviewed_list:
  - config/review_policy.yaml
  - pyproject.toml
  - scripts/verify_langfuse_spans.py
  - src/ai_hedge_fund/graph/nodes.py
  - src/ai_hedge_fund/graph/pipeline.py
  - src/ai_hedge_fund/graph/review_deps.py
  - src/ai_hedge_fund/memory/recall.py
  - src/ai_hedge_fund/output/__init__.py
  - src/ai_hedge_fund/output/formatter.py
  - src/ai_hedge_fund/output/portfolio_view.py
  - src/ai_hedge_fund/output/signal.py
  - src/ai_hedge_fund/review/__init__.py
  - src/ai_hedge_fund/review/decision.py
  - src/ai_hedge_fund/review/policy.py
  - src/ai_hedge_fund/schemas/signal_output.py
  - src/ai_hedge_fund/schemas/state.py
  - src/ai_hedge_fund/scripts/audit_reconstruct.py
  - src/ai_hedge_fund/scripts/portfolio_view.py
  - src/ai_hedge_fund/scripts/run_analysis.py
  - tests/graph/conftest.py
  - tests/graph/test_output_node.py
  - tests/graph/test_pipeline_review.py
  - tests/graph/test_review_node.py
  - tests/integration/conftest.py
  - tests/integration/test_phase8_audit_reconstruction.py
  - tests/integration/test_phase8_e2e.py
  - tests/integration/test_phase8_review_policy_sha_linkage.py
  - tests/output/test_audit_reconstruct.py
  - tests/output/test_final_signal.py
  - tests/output/test_formatter.py
  - tests/output/test_langfuse_span_coverage.py
  - tests/output/test_portfolio_view.py
  - tests/review/test_review_decision.py
  - tests/review/test_review_policy.py
  - tests/scripts/test_portfolio_view_cli.py
  - tests/scripts/test_run_analysis.py
findings:
  critical: 0
  warning: 3
  info: 6
  total: 9
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-04-22T00:00:00Z
**Depth:** standard
**Files Reviewed:** 37
**Status:** issues_found

## Summary

Phase 8 (Signal and Output) delivers the capstone: human review gate via LangGraph `interrupt()`, the `FinalSignalOutput` investor-facing contract, portfolio view, and compliance-grade audit trail reconstruction. The implementation is strongly aligned with the plan artifacts:

- **Security posture is solid.** `yaml.safe_load` is used exclusively for the review policy (T-08-01). `ReviewPolicy` / `ReviewDecision` / `FinalSignalOutput` are all `frozen=True, extra="forbid"`. No hardcoded secrets; ANTHROPIC_API_KEY is env-driven. SQLAlchemy queries are parameterised (no string concatenation).
- **SIG invariants are enforced as specified.**
  - SIG-01: `FinalSignalOutput` has no Optional required fields; every missing-field test raises `ValidationError`.
  - SIG-02: `portfolio_view.py` has no memoization; `test_no_lru_cache_decorator` greps the source as a regression guard.
  - SIG-03: `human_review_node` literally calls `interrupt(review_request)`; `test_interrupt_primitive_is_invoked_in_source` greps the source.
  - SIG-04: `reconstruct_audit_trail` assembles the analysis + review rows with both `policy_sha` fields; raises `ValueError` on wrong id.
- **Append-only invariant preserved.** `review_store_node` always constructs a NEW `record_type='review'` `EpisodicMemory` row; no UPDATE on analysis rows (verified by integration-level snapshot test).
- **VETOED bypass prevented.** The Phase-6 router ends the graph before Phase-8 review can fire; `output_node` short-circuits on missing signal; `human_review_node` short-circuits on error. `test_vetoed_never_reaches_review` confirms no review row is written on veto.
- **Backcompat preserved.** `build_debate_pipeline()` with no kwargs compiles to the exact Phase-5 topology; Phase-6/7 combinations remain byte-for-byte unchanged (3 backcompat tests + topology diff tests in `test_pipeline_review.py`).
- **Tool-first compliance.** No LLM call in `output/signal.py`, `output/portfolio_view.py`, `review/policy.py`, `review/decision.py`, or `scripts/audit_reconstruct.py`. `derive_risk_score` is pure Python.

Findings below are all non-blocking correctness / hardening nits. No critical issues were found.

## Warnings

### WR-01: `_format_output` VETOED branch renders full 64-char SHA when `--json` is used

**File:** `src/ai_hedge_fund/scripts/run_analysis.py:265-280`
**Issue:** The markdown branch truncates the risk policy SHA to 12 chars (`sha = (risk.get("policy_sha") or "")[:12]`) — matching the T-08-14 hardening applied in `output/formatter.py`. The JSON branch one line earlier dumps the full `risk_assessment` dict, which includes the full 64-char `policy_sha` verbatim. This is a soft inconsistency with the T-08-14 truncation intent already applied on the non-JSON paths. For v1 (attended local terminal) this is acceptable, but it diverges from the formatter contract without an explicit comment explaining why the JSON path doesn't truncate. If the JSON form is piped to a file shared with a compliance reviewer, the policy_sha is visible in full — that is likely the desired audit-trail behaviour, but it should be an explicit decision.

**Fix:** Either (a) add a short comment noting the JSON path is the audit-grade surface and full SHAs are intentional there, or (b) truncate for consistency:
```python
if as_json:
    # Full SHAs intentional — JSON surface is for audit pipelines, not human display.
    return json.dumps(payload, indent=2, default=str)
```

### WR-02: `format_review_request_md` leaks raw dict reprs (including full SHAs) in risk_assessment + hits sections

**File:** `src/ai_hedge_fund/output/formatter.py:104, 141-149`
**Issue:** `_fmt_value(risk)` on line 141 calls `str(value)` on the raw `risk_assessment` dict, which renders the Python repr (e.g. `{'status': 'APPROVED', 'policy_sha': 'aaaaaa...aaaaaa' (64 chars), ...}`) including the **full 64-char policy_sha**. Same issue for `episodic_hits` and `beliefs_consulted` rendered via `"- {h}"` with `h` being a dict. This partially defeats the T-08-14 truncation already applied to `format_signal_md`'s Audit section, because the reviewer sees the signal's SHA truncated but then the risk assessment's SHA in full two sections below.

The reviewer-facing packet is shown on an attended local terminal (T-08-31 documented exception), so this is not a v1 blocker — but it is an inconsistency worth fixing before the first external compliance demo.

**Fix:** Render `risk_assessment` with a dedicated mini-formatter that truncates SHAs:
```python
def _fmt_risk(risk: dict | None) -> str:
    if not risk:
        return "-"
    lines = [
        f"- status: {risk.get('status', '-')}",
        f"- constraint_violated: {risk.get('constraint_violated', '-')}",
        f"- rationale: {risk.get('rationale', '-')}",
        f"- policy_sha: {_short_sha(risk.get('policy_sha'))}",
    ]
    return "\n".join(lines)
```
Then replace `_fmt_value(risk)` with `_fmt_risk(risk)`. Apply the same pattern to episodic_hits / beliefs_consulted if they carry SHAs.

### WR-03: `_default_reviewer_io` accepts reviewer_note up to unbounded length; Pydantic re-validation raises late

**File:** `src/ai_hedge_fund/scripts/run_analysis.py:109-111`
**Issue:** `note = input("Reviewer note (1-2000 chars): ").strip()` does not enforce the documented 2000-char limit. The reviewer could paste 3000 characters; the error only surfaces in `human_review_node` via `ReviewDecision.model_validate`, which raises `ValidationError`. Because `_main` catches `Exception` and returns 1 (line 355), the reviewer sees `ERROR: <long Pydantic trace>` after they've already typed / pasted the note — losing their input. The prompt advertises `(1-2000 chars)` but doesn't enforce it at the source.

The empty-note branch is handled: empty input is substituted with `f"{status.lower()} without note"`. Only the max-length path is unguarded.

**Fix:** Validate note length at prompt time and re-prompt on failure:
```python
while True:
    note = input("Reviewer note (1-2000 chars): ").strip()
    if not note:
        note = f"{status.lower()} without note"
    if len(note) <= 2000:
        break
    print(f"Note too long ({len(note)} chars; limit 2000). Try again.")
```

## Info

### IN-01: `derive_risk_score` clamps ratio but doesn't special-case negative `observed`

**File:** `src/ai_hedge_fund/output/signal.py:51-56`
**Issue:** The `float(risk_assessment.get("observed") or 0.0)` + `max(0.0, min(1.0, observed/limit))` pipeline correctly clamps any negative `observed` to 0 (covered by `test_derive_risk_score_bounded` parametrised case `(-5, 10)`). However, a negative `observed` realistically indicates a buggy / anomalous risk check result, not a real risk score; silently mapping it to 0 (no risk) masks the upstream bug. Info only — the current behaviour matches the Plan 08-01 specification and all tests pass.

**Fix:** If desired, add a structlog warning when observed < 0 to surface upstream bugs:
```python
if observed < 0:
    logger.warning("derive_risk_score_negative_observed", observed=observed, limit=limit)
```

### IN-02: `portfolio_view.query_portfolio_view` relies on Python dict iteration order for "latest per ticker"

**File:** `src/ai_hedge_fund/output/portfolio_view.py:89-96`
**Issue:** The "latest row per ticker" logic uses `.order_by(EpisodicMemory.ticker, EpisodicMemory.as_of_date.desc())` and then `if row.ticker not in latest_by_ticker:` takes the first seen per ticker. Correctness depends on the SQL `order_by` being honored by the driver (true for PostgreSQL + SQLite). The loop assumes within each ticker group the DESC order is stable. SQLAlchemy will honour this, but the logic is implicit — readers have to trace from the ORDER BY to the dict insertion to see why `not in` gives the latest row.

**Fix:** A row-number / window-function query would be more obvious but adds complexity; the current approach is fine. Consider adding a docstring comment on line 93 explaining the ordering contract:
```python
# Pick latest row per ticker. ORDER BY ticker, as_of_date DESC means the
# first row seen per ticker IS the latest; `if row.ticker not in ...`
# skips subsequent older rows for that ticker.
```

### IN-03: `_normalise_as_of` imported from private-looking module path

**File:** `src/ai_hedge_fund/graph/nodes.py:102`, `src/ai_hedge_fund/memory/recall.py:23`, `src/ai_hedge_fund/output/portfolio_view.py:44`
**Issue:** Three modules import `_normalise_as_of` from `ai_hedge_fund.memory.episodic`. The underscore prefix signals it is module-private, but it is used as a cross-package helper. This is inconsistent with Python convention.

**Fix:** Rename to `normalise_as_of` (public) in `memory/episodic.py` and update the three import sites, or move it to a shared helper module (`ai_hedge_fund/common/time.py`). Low priority — no functional impact.

### IN-04: `route_before_review` missing threshold fails closed to `human_review` but blocks below-threshold run without checkpointer

**File:** `src/ai_hedge_fund/graph/nodes.py:1386-1391`
**Issue:** When `_review_threshold` is missing from state, the router returns `"human_review"` (fail-closed — the stricter branch). However, if the caller forgot to seed `_review_threshold` AND did not supply a checkpointer, `with_review=True`'s build-time guard catches the checkpointer case, but an in-process test that manually seeds a dict without `_review_threshold` will still hit `interrupt()` and silently pause. This is defensible (fail-closed is the documented intent) but a more actionable behavior would be to log a warning when the fail-closed branch fires.

**Fix:** Optional — add a structlog warning on the fail-closed path so the missing key is visible:
```python
if threshold is None or conviction is None:
    logger.warning(
        "route_before_review_fail_closed",
        has_threshold=threshold is not None,
        has_conviction=conviction is not None,
    )
    return "human_review"
```

### IN-05: `assemble_final_signal` reads `state["signal"]` / `state["thesis"]` with `[]` access; no explicit pre-check

**File:** `src/ai_hedge_fund/output/signal.py:82-83`
**Issue:** `signal = state["signal"]; thesis = state["thesis"]` will raise `KeyError` with a generic "signal" message if a caller forgets the precondition. The `output_node` caller pre-checks `state.get("signal") is None` before calling, so the key always exists in production. For test authors writing unit tests against `assemble_final_signal` directly, a missing `signal` will raise `KeyError` rather than a validation-style error.

**Fix:** Not worth changing — the module docstring explicitly documents "Raises ValidationError if state is missing any field required by FinalSignalOutput" and the caller contract is explicit. Optionally, add explicit error handling for a friendlier test experience:
```python
if "signal" not in state or "thesis" not in state:
    raise ValueError("assemble_final_signal requires state['signal'] and state['thesis']")
```

### IN-06: `review_store_node` computes `status` via `(decision or {}).get("status") or "NOT_REQUIRED"`

**File:** `src/ai_hedge_fund/graph/nodes.py:1334`
**Issue:** This idiom collapses three distinct cases into `"NOT_REQUIRED"`:
  1. `decision is None` (below-threshold path — correct).
  2. `decision.get("status") is None` (malformed decision — should never happen because `ReviewDecision.model_validate` rejects it, but the row-writer doesn't know).
  3. `decision.get("status") == ""` (same as above).

All three produce an indistinguishable audit row. The defensive collapse is reasonable, but it could mask a future bug where a reviewer decision was stored without a status. No current test or production path triggers case 2 or 3.

**Fix:** Optional — make case 2/3 explicit:
```python
if decision is None:
    status = "NOT_REQUIRED"
else:
    status = decision.get("status")
    if not status:
        logger.error("review_store_missing_status", decision=decision)
        status = "NOT_REQUIRED"  # keep row write; flag the anomaly
```

---

_Reviewed: 2026-04-22T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
