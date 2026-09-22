---
phase: 10
slug: paper-execution-surface
status: awaiting-signoff
written: 2026-09-22
---

# Phase 10 -- Pre-mortem

Premise: three months on, Phase 10 shipped, paper trading ran daily through Phases 11-13, and something traces back here. Severity: **C** corrupts the track record or sends an order that should not exist; **H** silent wrong behaviour; **M** loud failure.

| # | Sev | Failure mode | Invariant | Test |
|---|---|---|---|---|
| 1 | C | `ALPACA_PAPER_HOST` was set to the live endpoint in a copied `.env`; orders went to a real account. | Paper only (D8) | `test_alpaca_adapter.py::test_live_host_refused` (construction raises `LiveEndpointRefused` for any host without `paper-api`); live smoke asserts host too |
| 2 | C | A network timeout after the broker accepted the order triggered a retry; two orders filled. | EXEC-03 | `test_submit.py::test_network_retry_same_attempt_dedupes` (FakeBroker rejects the duplicate `client_order_id`; one row); adapter never retries on `BrokerRejected`/`DuplicateClientOrderId` (`test_alpaca_adapter.py::test_no_retry_on_rejection`) |
| 3 | C | Sizing used a live quote; the same signal re-sized differently on re-run and the audit row could not reproduce the quantity. | Determinism (D5) | `test_prices.py::test_uses_cached_adj_close_only` (no HTTP client in `prices.py`), `test_sizing.py::test_size_is_pure` (same inputs -> same output, no I/O) |
| 4 | C | Price lookup ignored `as_of_date` and used the latest close; a backfilled signal was sized with future prices. | Temporal | `test_prices.py::test_future_price_rows_excluded` (FUTUREX-style seed at 2099) |
| 5 | C | The VETOED check read `risk_status` from the CLI argument instead of the stored analysis row; an operator could submit a vetoed signal. | EXEC-04 | `test_submit.py::test_vetoed_refused_zero_broker_calls` loads status from the DB row; no CLI flag exists to override |
| 6 | C | Reviewer REJECTED was treated as "not required" because both are non-APPROVED strings. | SIG-03 | `test_decide.py::test_review_rejected_refuses`, `::test_not_required_allows`, `::test_approved_allows` |
| 7 | H | Broker request/response stored in `payload` included the `Authorization` header or the key in a nested `config` dict; Phase 13's export leaked it. | Security (D8) | `test_redact.py::test_nested_secret_keys_stripped`, `::test_secret_values_stripped_from_strings`; `test_submit.py::test_payload_has_no_secret_values` |
| 8 | H | A broker rejection raised before the row was written; the attempt vanished and the next run resubmitted as attempt 1. | Uniform audit (D4) | `test_submit.py::test_broker_rejection_recorded_then_reraised` |
| 9 | H | Zero shares (small NAV / high price / low conviction) was submitted; the broker rejected it; the ledger filled with noise. | D5 | `test_sizing.py::test_zero_shares_refuses`, `test_decide.py::test_below_min_size_refusal` |
| 10 | H | `max_position_pct * nav` computed in floats produced 9.999999 shares -> 9, or 10.000001 -> 10, differing by platform. | Money precision | `test_sizing.py::test_integer_arithmetic_only` (asserts on exact boundary cases) |
| 11 | H | Attempt counter derived from a recall with the default `limit`/`as_of` missed older rows; attempt 1 was re-used and hit the unique constraint on every retry. | D3 | `test_submit.py::test_next_attempt_sees_all_prior_rows` (as_of far future, limit high) |
| 12 | H | Refusals consumed attempts; after `max_attempts` refusals a later legitimate resubmit was blocked. | D3/D4 | `test_submit.py::test_refusal_is_terminal_already_decided` (refusal -> `AlreadyDecided`, never `AttemptsExhausted`) |
| 13 | H | The `submit_status` CHECK still admitted only three values on prod because migration 005 was never applied; first refusal raised `IntegrityError`. | 10.x | `test_migration_roundtrip.py` covers 005 on SQLite via `batch_alter_table` and PG-gated; `test_models.py` parametrized on all five statuses |
| 14 | H | Migration 005's downgrade dropped rows carrying the new statuses silently. | Reversibility | `test_migration_roundtrip.py::test_005_downgrade_refuses_when_new_statuses_present` |
| 15 | H | `long_only` was flipped in YAML and nothing changed the SHA because the field had a default and was omitted from `model_dump`. | Audit | `test_execution_policy.py::test_sha_changes_when_long_only_flips` |
| 16 | H | A `short` signal was submitted as a `sell` of a position we do not hold. | D7 | `test_decide.py::test_short_refused_when_long_only`, `::test_short_becomes_sell_when_shorts_enabled` (policy `long_only=false`) |
| 17 | M | Missing `ALPACA_PAPER_SECRET` surfaced as a 401 from the broker mid-run rather than at startup. | EXEC-05 | `test_alpaca_adapter.py::test_missing_credentials_named[...]` |
| 18 | M | The live smoke test left an open order on the paper account every CI run. | Hygiene | `test_alpaca_live.py::test_paper_roundtrip` cancels if still open; UUID suffix on `client_order_id` |
| 19 | M | `alpaca-py` pulled an incompatible Pydantic; nothing noticed until import. | Deps | T1 gate: `uv sync --frozen` + full suite after adding the dependency (its constraint is `pydantic>=2.0.3,<3`, verified on PyPI 2026-09-22) |
| 20 | M | An LLM call crept into sizing ("ask the model for a size hint"). | Tool-first (CLAUDE.md) | `test_no_llm.py` (package imports scanned; `agent.run` absent) |
| 21 | M | `--dry-run` wrote a refusal row. | CLI contract | `test_submit_signal.py::test_dry_run_writes_nothing` (row count unchanged, FakeBroker uncalled) |
| 22 | H | `load_signal_context` picked an *older* review row (e.g. a REJECTED followed by a later APPROVED re-review) because ordering was by `as_of_date`, not `id`. | Latest review wins | `test_submit.py::test_latest_review_row_wins` (two review rows, same as_of, later id APPROVED) |
| 23 | H | `FinalSignalOutput` in the review payload was stored under a slightly different key by Phase 8 than Phase 10 reads. | Contract | `test_submit.py::test_loads_final_signal_from_real_review_store_shape` (fixture built by calling Phase 8's `review_store_node` payload builder, not a hand-written dict) |

## Accepted residuals

- The broker's own idempotency depends on Alpaca honouring `client_order_id` uniqueness; the DB unique constraint is the second line. Both are tested; neither is bypassed by design.
- Fills are not ingested in this phase (Phase 11). Between submit and Phase 11, `paper_fills` is empty by design.
- The live smoke test spends nothing (paper) but does depend on market hours for a fill; it asserts acceptance and `client_order_id` round-trip, not fill.
