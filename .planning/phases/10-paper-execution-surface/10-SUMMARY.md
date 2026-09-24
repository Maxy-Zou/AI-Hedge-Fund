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

**Outcome:** Delivered. All five ROADMAP criteria proven; the live paper smoke test passed against real Alpaca paper (order accepted, `client_order_id` round-tripped, cancelled). Every implementation commit was preceded by a RED test.

## Goal achievement

| # | Success criterion | Status | Evidence |
|---|---|---|---|
| 10.1 | Sizing pure Python; zero LLM between signal and size | VERIFIED | `tests/execution/test_sizing.py` (pure table tests), `test_no_llm.py` (scans the shipped package for any LLM surface) |
| 10.2 | Same signal twice -> one order, one row | VERIFIED | `test_submit.py::test_second_submit_raises_already_submitted_without_broker_call`; broker `client_order_id` uniqueness in `test_alpaca_adapter.py::test_duplicate_client_order_id_maps_to_typed_error` |
| 10.3 | VETOED refused before any broker call | VERIFIED | `test_submit.py::test_vetoed_refused_zero_broker_calls` (FakeBroker `calls == 0`), `::test_vetoed_is_terminal` |
| 10.4 | Missing credential fails at construction naming the variable | VERIFIED | `test_alpaca_adapter.py::test_missing_credentials_named[...]`, `::test_live_host_refused` |
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
- **Live smoke tests the adapter directly** (a far-below-market limit buy of 1 SPY, cancelled) rather than the full `submit_signal` path, which would need seeded episodic rows in a live DB.

## Pre-mortem coverage

23 failure modes; all have a SQLite/mocked test except the live-only ones (#1 live host, #18 open-order hygiene) which the credential-gated smoke covers, and #19 (dependency drift) covered by the T1 frozen-resolve gate. Accepted residuals unchanged: broker-side idempotency trust (belt-and-braces with the DB unique), fills deferred to Phase 11, live fill depends on market hours (smoke asserts acceptance, not fill).

## Handoff to Phase 11 (Mark-to-Market)

- Fills are **not** ingested here. `paper_fills` is empty until Phase 11 polls the broker. `submit_signal` records only the synchronous submit response.
- Phase 11 owns **migration 007** for `paper_pnl_daily`.
- Read submitted orders via `query_paper_trades`; join fills once ingested. Refusal rows (`refused_*`, quantity 0) must be excluded from P&L.
- The live smoke leaves no position (limit stays open then cancels); Phase 11's fill tests should seed fills directly rather than depend on live fills.

## Verification

- Full suite: **1385 passed, 8 skipped, 1 deselected** (the deselected `test_checkpoint_resume` is the pre-existing async-checkpointer bug filed in TECH-DEBT; unrelated).
- `ruff format --check` / `ruff check` clean; `uv sync --frozen` resolves.
- Live: `uv run --env-file .env pytest tests/execution/test_alpaca_live.py -m slow` -> 1 passed against Alpaca paper.
