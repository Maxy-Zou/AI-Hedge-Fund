---
phase: 11
slug: mark-to-market
status: draft -- awaiting review
written: 2026-09-25
---

# Phase 11 -- Pre-mortem

Premise: three months on, Phase 11 shipped, the EOD job ran every trading day, Phase 12 promoted a signal on its numbers, and Phase 13 put the track record in front of an LP. Then something traced back here. Severity: **C** corrupts the track record or misstates P&L to an investor; **H** silent wrong behaviour; **M** loud failure.

Each row becomes a test in T1-T9 (file names from 11-SPEC.md section 9). A row with no test is not done.

## Data integrity

| # | Sev | Failure mode | Invariant | Test |
|---|---|---|---|---|
| 1 | C | The job ran at 14:00 ET on a trading day; that day's row was written with no price (skipped) or, after a vendor wrote an intraday bar, with an intraday "close". Append-only froze it forever. | D6 completed-day guard | `test_job.py::test_today_before_close_raises_incomplete`, `::test_today_after_close_buffer_allowed`, `::test_weekend_date_raises` (`now` injected) |
| 2 | C | The mark fell back to the latest price on or before `pnl_date` (the `execution/prices.py` rule), so a holiday or data gap was frozen as a real day with a stale price. | Spec 6.3 exact-date price | `test_job.py::test_missing_exact_date_price_skips_not_stale` (price exists for t-1 only -> `skipped_no_price`, zero rows) |
| 3 | C | A second run of the same date issued UPDATEs through an ORM merge / upsert helper; the PG trigger raised in prod only, and SQLite tests passed. | MTM-04, 11.2 | `test_job.py::test_rerun_issues_no_update` (`before_cursor_execute` counter: 0 statements starting `UPDATE`/`DELETE`); `test_migration_007.py::test_pg_trigger_rejects_update` (`requires_db`) |
| 4 | C | Re-run recomputed a row with a newer vendor price (a second `daily_prices` source arrived) and, finding it different, inserted a second row for the same (signal, date). | 11.4 one row | `test_migration_007.py::test_unique_signal_date`; `test_job.py::test_rerun_after_new_price_source_inserts_nothing` |
| 5 | C | A re-run changed nothing in the table, but JSON key order or float serialisation in `attribution`/`payload` differed between runs, so a checksum audit reported the ledger as modified. | 11.4 byte-identical | `test_job.py::test_prior_rows_byte_identical` (snapshot every column incl. JSON text, re-run, compare); `test_attribution.py::test_no_float_in_attribution` |
| 6 | C | Two concurrent job runs each read "no row yet" and one partially wrote before hitting the unique constraint, leaving half a day's rows. | Spec 6.5 all-or-nothing | `test_job.py::test_unique_violation_rolls_back_whole_batch` (pre-insert one conflicting row mid-batch -> `ConcurrentRun`, count unchanged) |
| 7 | H | `total_pnl_cents` drifted from `realized + unrealized` because one code path rounded the parts and another rounded the sum. | Spec 3 CHECK | `test_migration_007.py::test_total_check_rejects_mismatch`; `test_pnl.py::test_total_is_sum_of_parts` |
| 8 | H | Migration 007's downgrade left the trigger function or an index behind; `upgrade head` after `downgrade -1` failed on PG. | Reversibility | `test_migration_007.py::test_roundtrip_leaves_no_orphans` (SQLite + PG-gated), `::test_parity_with_orm` (`compare_metadata` + CHECK comparison, as 004) |

## Temporal leakage

| # | Sev | Failure mode | Invariant | Test |
|---|---|---|---|---|
| 9 | C | Backfilling a past date after later fills existed counted those fills; the historical series showed positions before they were bought. | Temporal | `test_pnl.py::test_future_fill_raises` (`FutureInputError`); `test_job.py::test_backfill_ignores_later_fills` (fill on t+2, mark t -> no row for that signal) |
| 10 | C | A dividend paid after `pnl_date` was credited on a backfill, inflating realized P&L on earlier days. | Temporal | `test_pnl.py::test_future_dividend_raises`; `test_job.py::test_backfill_ignores_later_dividends` |
| 11 | H | Fill trade date was taken from the UTC date of `transaction_time`; a 20:30 ET after-hours fill landed on the next day. | NY trading date | `test_ingest.py::test_fill_as_of_is_new_york_date` (23:30 UTC -> same NY date; 04:30 UTC -> previous NY date) |
| 12 | H | A price row observed *after* the job's `now` (a later backfill download) was used when re-running an old date with a pinned `now`. | Spec 6.3 `observed_date <= now` | `test_job.py::test_price_observed_after_now_ignored` |

## P&L correctness

| # | Sev | Failure mode | Invariant | Test |
|---|---|---|---|---|
| 13 | C | Marks used cached `adj_close`; each row carried a different download's adjustment factor and dividends vanished from the series (the D4 flaw, A1). | A1 raw close | `test_job.py::test_mark_uses_close_cents_not_adj_close` (seed rows where they differ) |
| 14 | C | A stock split turned 10 shares at $200 into 20 shares at $100; the raw-close mark on 10 shares halved the position overnight and Phase 12 rejected a good signal. | A1 corporate actions | `test_job.py::test_split_after_first_fill_skips_signal` (`skipped_corporate_action`, no row); `test_ingest.py::test_split_activity_stored` |
| 15 | H | Dividends were credited to every signal on the ticker at full amount instead of pro rata, double-counting when two signals held the same stock. | Spec 5 pro rata | `test_job.py::test_dividend_split_pro_rata_across_signals` (sum of credits == `net_amount_cents` exactly) |
| 16 | H | FIFO matched sells by `id` rather than `filled_at`; an out-of-order ingest produced the wrong realized P&L. | Spec 5 FIFO order | `test_pnl.py::test_fifo_uses_filled_at_then_id` |
| 17 | H | A manual short or over-sell on Alpaca produced negative `open_qty`; the CHECK raised mid-batch and no signal was marked that day. | Long-only book | `test_pnl.py::test_oversell_raises`; `test_job.py::test_oversold_signal_skipped_others_marked` |
| 18 | H | Partial fills were ingested from the order's aggregate `filled_avg_price` and lost per-execution prices. | D1 | `test_ingest.py::test_partial_fills_one_row_each` |
| 19 | H | A fractional fill (e.g. from a manual trade) was truncated to whole shares. | Whole shares (Phase 9 D3) | `test_alpaca_activities.py::test_fractional_qty_raises` |
| 20 | H | `DIVWH` withholding (negative) was stored with its sign flipped or skipped; realized income overstated. | Signed cash | `test_alpaca_activities.py::test_withholding_is_negative_cents`; `test_pnl.py::test_withholding_reduces_realized` |

## Attribution

| # | Sev | Failure mode | Invariant | Test |
|---|---|---|---|---|
| 21 | C | The analyst split floored each third; totals across the portfolio were short a few cents, and the LP report did not reconcile. | 11.3 exact sums | `test_rollup.py::test_each_dimension_sums_to_total` (seeded `random.Random(11)` sweep of 500 portfolios incl. 1- and 2-cent totals, negatives); `AttributionInvariantError` raised, not logged |
| 22 | C | v1 analyses (no stances) were silently bucketed as `none_aligned`, making analysts look worse than they were. | D2 honest buckets | `test_attribution.py::test_v1_payload_is_unattributed`; `test_rollup.py::test_unattributed_separate_from_none_aligned` |
| 23 | H | The stance rule was later tweaked and applied at rollup time, rewriting historical attribution. | A2 stance stored at write time | `test_episodic_store_v2.py::test_stances_persisted`; `test_attribution.py::test_uses_stored_stances_not_rederived` |
| 24 | H | An analyst that errored was counted as `neutral` rather than `absent`. | A2 | `test_stances.py::test_errored_analyst_is_absent` |
| 25 | H | Debate winner used `revised_thesis.confidence` (already the post value) as "pre", so every delta was 0 and every signal a draw. | D3 | `test_attribution.py::test_debate_winner_table` (delta >0 / <0 / 0 x buy side); `test_episodic_store_v2.py::test_debate_pre_confidence_from_state` |
| 26 | H | Phase-4-only runs (no debate) crashed the store node on `state["debate_synthesis"]`. | D2 | `test_episodic_store_v2.py::test_no_debate_stores_none` |
| 27 | H | A conviction of exactly 50 or 75 landed in two buckets or none. | Contiguous buckets | `test_mtm_policy.py::test_boundaries_map_to_one_bucket`, `::test_gap_or_overlap_rejected` |
| 28 | H | Editing `sentiment_threshold` did not change `mtm_policy_sha`, so rows under different rules looked identical. | Audit | `test_mtm_policy.py::test_sha_changes_per_field` (parametrized over every field) |

## Vendor drift and security

| # | Sev | Failure mode | Invariant | Test |
|---|---|---|---|---|
| 29 | C | Activity paging stopped after the first 100 records; weeks of fills were never ingested and positions looked flat. | Complete ingest | `test_alpaca_activities.py::test_follows_page_token_until_short_page` |
| 30 | H | alpaca-py was upgraded and its `RESTClient.get` signature or return shape changed; ingest returned 0 activities without error. | Vendor contract | `test_alpaca_activities.py::test_unexpected_shape_raises` (non-list body -> error, never empty); live `test_list_activities_roundtrip` |
| 31 | H | The activities call used a hand-built base URL, bypassing the Phase 10 paper-host guard. | Paper only (Phase 10 D8) | `test_alpaca_activities.py::test_uses_guarded_client` (calls go through the adapter's `TradingClient`, never a new HTTP client) |
| 32 | H | Raw activity JSON with account ids / auth details was stored in `payload` and exported in Phase 13. | Security | `test_ingest.py::test_payload_is_redacted` (reuses `execution/redact.py`) |
| 33 | M | A fill for an order we never placed (manual trade) crashed the ingest. | D1 | `test_ingest.py::test_unknown_order_skipped_and_logged` |

## Scope and LLM boundary

| # | Sev | Failure mode | Invariant | Test |
|---|---|---|---|---|
| 34 | C | A helper in `mtm/` imported an agent module to "explain" a P&L move; an LLM ran in the P&L path. | 11.1 | `test_no_llm.py` (package scan for anthropic / pydantic_ai / langchain imports, as Phase 10) |
| 35 | H | `graph` imported `mtm`, and `mtm` imported `graph`; a circular import broke only the CLI entry point. | Spec 2 layering | `test_no_llm.py::test_mtm_does_not_import_graph`; `tests/scripts/test_mark_to_market.py` runs the CLI entry point |
| 36 | M | `--dry-run` wrote rows. | CLI contract | `test_mark_to_market.py::test_dry_run_writes_nothing`, `test_ingest_fills.py::test_exit_codes` |

## Known and accepted (not tested here -> TECH-DEBT at T9)

- Corporate actions are skipped, not applied (#14 is detection only).
- No correction mechanism for a wrong `paper_pnl_daily` row (D6).
- No exchange calendar: holidays surface as `skipped_no_price`, which is correct but noisy in logs.
- No exit policy, so realized P&L is dividends only (D5), and Phase 12 inherits this.
