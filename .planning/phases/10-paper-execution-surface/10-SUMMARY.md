---
phase: 10
slug: paper-execution-surface
status: complete
delivered: 2026-09-24
branch: phase/10-paper-execution-surface
pr: 4
requirements: [EXEC-01, EXEC-02, EXEC-03, EXEC-04, EXEC-05]
migrations: [005, 006]
---

# Phase 10 -- Paper Execution Surface: Summary

**Goal:** A signal becomes a submitted paper order, sized deterministically and refused when risk vetoes -- so the track record reflects only orders the pipeline actually sanctioned.

**Outcome:** Delivered. All five ROADMAP criteria proven; the live paper tests pass against real Alpaca paper. Every implementation commit was preceded by a RED test. **A second, independent code review (round 2) found a critical defect the first review missed** -- most refusal statuses could not be stored on PostgreSQL -- plus a bypassable paper-host guard and several correctness gaps; all were fixed before merge (see *Code review*). This summary's original pre-mortem coverage claim was also wrong and is corrected below.

## Goal achievement

| # | Success criterion | Status | Evidence |
|---|---|---|---|
| 10.1 | Sizing pure Python; zero LLM between signal and size | VERIFIED | `tests/execution/test_sizing.py` (pure table tests), `test_no_llm.py` (scans the shipped package for any LLM surface) |
| 10.2 | Same signal twice -> one order, one row | VERIFIED | `test_submit.py::test_second_submit_raises_already_submitted_without_broker_call`, `::test_lost_response_is_adopted_on_rerun` (timeout after acceptance -> still one order, one row); duplicate classification proven live in `test_alpaca_live.py::test_duplicate_is_classified_and_lookup_finds_the_order` |
| 10.3 | VETOED refused before any broker call | VERIFIED | `test_submit.py::test_vetoed_refused_zero_broker_calls` (FakeBroker `calls == 0`), `::test_vetoed_is_terminal` |
| 10.4 | Missing credential fails at construction naming the variable | VERIFIED | `test_alpaca_adapter.py::test_missing_credentials_named[...]`, `::test_non_paper_host_refused[...]` (9 live/look-alike hosts) |
| 10.5 | Submitted order's broker id persisted | VERIFIED | `test_submit.py::test_submitted_persists_broker_order_id`; live `test_alpaca_live.py::test_paper_roundtrip` (passed against Alpaca paper 2026-09-24) |

## What shipped

| Area | Files |
|---|---|
| Shared | `src/ai_hedge_fund/policy_sha.py` (`fingerprint`, promoted from risk/review) |
| Config | `execution/policy.py`, `config/execution_policy.yaml`, `config.py` (`alpaca_paper_*`), `.env.example` |
| Schema | migration 005 (widen submit_status), migration 006 (quantity >= 0 for refusals + submitted-positive paired CHECK) |
| Execution | `execution/` -- `errors.py`, `prices.py`, `sizing.py`, `decide.py`, `broker.py`, `alpaca.py`, `redact.py`, `submit.py` |
| CLI | `scripts/submit_signal.py` |
| Tests | `tests/execution/` (policy, settings, prices, sizing, decide, redact, fake_broker, alpaca_adapter, submit, no_llm, alpaca_live), `tests/scripts/test_submit_signal.py`, `tests/unit/test_policy_sha.py` |

## Decisions as executed

D1 standalone `submit_signal` step (not a graph node) -- done. D2 BrokerClient Protocol + alpaca-py adapter + FakeBroker -- done. D3 idempotency at DB `(signal_id, attempt_no)` and broker `client_order_id` -- done. D4 refusals recorded as rows -- done (needed migration 005 for the statuses **and** 006 for quantity 0, the latter unforeseen). D5 SHA-pinned sizing from cached as-of price -- done. D6 NAV configurable, $100k default -- done. D7 long-only -- done (`short` -> `refused_policy: long_only`). D8 paper-host + credential guards -- done, and exercised live. D9 shared `fingerprint()` -- done.

## Deviations from 10-PLAN

- **Migration 006 added mid-phase (T6).** The spec's D4 anticipated widening the status CHECK (005) but not that Phase 9's `quantity > 0` CHECK forbids a refusal row (a refusal has no positive quantity). 006 relaxes it to `>= 0` with a paired CHECK keeping submitted orders positive. Consequence: **Phase 11's `paper_pnl_daily` is now migration 007** (ROADMAP updated).
- **`NO_REVIEW_POLICY_SHA` sentinel.** A VETOED signal never reaches review, so it has no `review_policy_sha`, yet the Phase 9 column is required 64-char. Refused-before-review rows store all-zeros, documented, rather than weakening the column to nullable.
- **Round-2 review changes (all post-T9):** migration 005 amended in place to widen `submit_status` to VARCHAR(20) (005 never reached `main`; dev DB re-migrated, paper tables were empty). New errors `BrokerAuthError`, `ClientOrderIdConflict`, `InvalidSignal`; new refusal reason `invalid_signal`; `BrokerClient` gains `get_order_by_client_order_id`; `client_order_id` is now `sig-<id>-a<n>-<tag>`; `requests` declared as a direct dependency (own commit).
- **Live smoke tests the adapter directly** (a far-below-market limit buy of 1 SPY, cancelled) rather than the full `submit_signal` path, which would need seeded episodic rows in a live DB.

## Pre-mortem coverage

23 failure modes. **Correction:** this section originally said every mode had a test. Review round 2 found five named tests that did not exist (#2 x2, #10, #11, #23) and several that could not fail (a payload-secret test against a broker that never returns secrets; a float-drift test whose inputs could not drift; adapter tests that never counted retries). All are now real: #2 by `test_transport_error_is_retried_then_transient` (asserts 3 calls, same client_order_id) and `test_other_api_error_maps_to_broker_rejected` (asserts 1 call); #10 by `test_size_matches_exact_rational_reference` (40 policy bands vs a rational reference); #11 by `test_next_attempt_sees_all_prior_rows` (characterization -- passed first run); #23 by `test_loads_real_review_store_shape`; #7 by `test_error_message_scrubbed_of_credentials`. Live-only modes (#1, #18) are covered by the credential-gated live tests; #19 by the frozen-resolve gate. Accepted residuals: fills deferred to Phase 11; live fill depends on market hours (tests assert acceptance, not fill); concurrency and price-source precedence (TECH-DEBT).

## Code review

- **Round 1 (self-review, T9):** 6 findings; 4 fixed (lazy broker so dry-run/refusals need no credentials, 006 downgrade guard, hyphenated secret keys, exit code 3 for already-handled), 2 deferred.
- **Round 2 (independent reviewer, pre-merge):** 10 findings, all addressed, each RED-first:
  - **R1 (critical)** `submit_status` VARCHAR(12) could not hold `refused_review`/`refused_policy` (14 chars): 5 of 6 refusal paths crashed on PostgreSQL with an uncaught DataError and wrote no audit row. SQLite ignores VARCHAR length, so the suite was green. Reproduced on the dev DB. New SQLite-level guards (status-fits-column, ORM/migration width parity) and a PG test inserting every status.
  - **R2** paper-host guard was a substring check (`https://paper-api@api.alpaca.markets` reached the live API). Now parsed and allow-listed.
  - **R5** error classification rebuilt from shapes **probed on the real paper API**: the code the adapter keyed duplicates on (40010001) is actually "client_order_id too long"; the real duplicate is 42210000, shared with "asset not found", so it is matched by message. 401/403 are auth errors, not rejections (no attempt burned).
  - **R3** timeouts/connection errors now retry with the same client_order_id; a re-run after a lost response adopts the broker's order after a symbol/side/qty match (closes round-1 F3). **R7** client_order_id namespaced per database so adoption cannot pick up a foreign order.
  - **R4** sizing in exact rational arithmetic (float math dropped a share at exact boundaries). **R6** fail closed on unrecognised statuses/directions ("LONG" used to become a *sell*) and validate the stored signal against `FinalSignalOutput`. **R9** broker messages credential-scrubbed. **R10** deterministic same-day multi-source price. **R8** test gaps above.

## Handoff to Phase 11 (Mark-to-Market)

- Fills are **not** ingested here. `paper_fills` is empty until Phase 11 polls the broker. `submit_signal` records only the synchronous submit response.
- Phase 11 owns **migration 007** for `paper_pnl_daily`.
- Read submitted orders via `query_paper_trades`; join fills once ingested. Refusal rows (`refused_*`, quantity 0) must be excluded from P&L.
- Fill polling can look orders up by `client_order_id` via `BrokerClient.get_order_by_client_order_id` (proven live). Stored `side`/`status` are wire values (`buy`, `pending_new`).
- The live smoke leaves no position (limit stays open then cancels); Phase 11's fill tests should seed fills directly rather than depend on live fills.

## Verification

- Full suite (after round 2): **1500 passed, 11 skipped, 1 deselected** (the deselected `test_checkpoint_resume` is the pre-existing async-checkpointer bug, fixed separately in PR #5).
- PostgreSQL-gated: `TEST_DATABASE_URL=... pytest tests/paper -m slow` -> 3 passed (incl. every submit_status inserting on real PG), stable across repeated runs.
- `ruff format --check` / `ruff check` clean; `uv sync --frozen` resolves.
- Live: `uv run --env-file .env pytest tests/execution/test_alpaca_live.py -m slow` -> 2 passed against Alpaca paper (round trip; duplicate classification + lookup).
