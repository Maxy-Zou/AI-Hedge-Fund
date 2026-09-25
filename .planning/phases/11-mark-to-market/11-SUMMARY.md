---
phase: 11
slug: mark-to-market
status: shipped -- PR #7 open, awaiting merge
delivered: 2026-09-25
branch: phase/11-mark-to-market
requirements: [MTM-01, MTM-02, MTM-03, MTM-04]
migrations: [007]
---

# Phase 11 -- Mark-to-Market and Attribution: Summary

**Goal:** a daily job that turns fills into an append-only P&L series decomposed by analyst, debate side, and conviction. **Outcome:** delivered. Spec amendments A1 (raw close + broker dividends; cached `adj_close` keeps its download-day factor) and A2 (derived analyst stance) are in `11-SPEC.md`; the review amended s4 (activity batch) and s5 (dividend credit).

## Success criteria

| # | Criterion | Proof | Result |
|---|---|---|---|
| 11.1 | P&L from fills + day's close + broker dividends; pure Python, no LLM | `tests/mtm/test_pnl.py`, `tests/mtm/test_job.py::test_mark_uses_close_cents_not_adj_close`, `tests/mtm/test_no_llm.py::test_mtm_source_has_no_llm_surface`, `::test_mtm_does_not_import_graph` | pass |
| 11.2 | Re-run adds 0 rows, 0 UPDATEs | `tests/mtm/test_job.py::test_rerun_issues_no_update`, `tests/mtm/test_store.py::test_rerun_skips_existing_and_issues_no_update`, `tests/mtm/test_migration_007.py::test_pg_trigger_rejects_update` (Postgres) | pass |
| 11.3 | Analyst / debate / conviction sum to total | `tests/mtm/test_rollup.py::test_each_dimension_sums_to_total` (exact, 500 random books), `::test_invariant_violation_raises_not_logs` | pass |
| 11.4 | One row per (signal, date); prior rows byte-identical | `tests/mtm/test_migration_007.py::test_unique_signal_date`, `tests/mtm/test_job.py::test_prior_rows_byte_identical` | pass |

Pre-mortem: `uv run python -m ai_hedge_fund.devtools.premortem_check .planning/phases/11-mark-to-market/11-PREMORTEM.md` -> 58 test ids, 0 missing, 0 deferred.

## Verification (final gates, merged with main)

```
uv sync --frozen --extra dev                        -> Checked 170 packages
TEST_DATABASE_URL=... uv run pytest -q -rs          -> 1904 passed, 9 skipped in 27.85s
                                                       (skips: live Alpaca / Anthropic / EDGAR keys only)
uv run ruff format --check . && uv run ruff check . -> clean
```

Tests: 1515 at branch start -> 1812 on the branch (1751 before review) -> 1904 after merging main (+ its devtools suite). Also run manually: the 77 DB-touching `mtm` tests against Postgres via a fixture override (pass), and `tests/execution/test_alpaca_live.py::test_list_activities_roundtrip` against Alpaca paper with credentials (pass; the account had no fills or dividends yet, so the first real fill should be checked against the parser).

## Review (six parallel lenses + one targeted re-review)

- **Spec compliance:** 1 H confirmed (late fill double-credited a dividend -> fixed with H5), 1 L deferred.
- **Database fidelity:** schema and suite hold on Postgres incl. non-UTC sessions; 1 M (loader vs core fill date) + 3 L fixed, 1 M deferred (Postgres fixture).
- **Vendor contracts:** H1 (documented activity shapes rejected by SDK-model validation) and H2 (one bad row aborted ingest) fixed; canceled cash + non-JSON body fixed; ex-date deferred.
- **Entry points & tests:** 1 H (dup of H2); scrubbing test strengthened; stance rule tied to real schemas (no defect, kept as a guard); 5 L deferred.
- **Fail-closed & security:** 1 H (dup of H3); naive timestamps, non-positive/overflow values, oversold dividend reallocation, NaN stances, reserved bucket name, page-token cycles fixed.
- **Temporal & data integrity:** H3 (intraday bar frozen as close), H4 (split-adjusted close for a pre-split date), H5 (dividend over/double credit) fixed; ingest watermark deferred.
- **Re-review of fixes:** all closed; 1 M (credits could exceed payment) + 3 L found in the fixes and fixed (`tests/mtm/test_job.py::test_credits_capped_when_signals_hold_more_than_paid`, `::test_dividend_and_withholding_never_overcredit`). No open CRITICAL/HIGH.

## Found and fixed outside the phase scope

`submit_signal --json` printed a log line ahead of the JSON in production (`tests/scripts/test_submit_signal.py::test_json_stdout_is_pure_json_even_when_the_broker_logs`); migration 004 docstring; new worktrees need `chflags -R nohidden .venv` (Python 3.13 skips hidden `.pth` files).

## Deferred (`.planning/TECH-DEBT.md`)

Corporate actions detected but not applied; no correction path for a written row; no broker/ledger reconciliation; dividends use pay-date holdings (no ex-date); no exchange calendar; Postgres test fixture; no ingest watermark; rollup conviction key set and latest-row labels; row SHA vs stance SHA; minor test gaps.

## Operating notes and handoff to Phase 12

- After the close: `python -m ai_hedge_fund.scripts.ingest_fills --since <date>`, then `python -m ai_hedge_fund.scripts.mark_to_market` (last completed trading day by default). Order matters: rows are append-only.
- Rows are cumulative per signal; daily returns are differences of consecutive rows; a skipped day has no row (missing, not zero).
- Realized P&L is dividends only until an exit policy exists (D5).
- Read through `ai_hedge_fund.mtm.rollup.attribution_rollup` / `ai_hedge_fund.mtm.store.query_pnl_rows`.
