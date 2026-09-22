---
phase: 10
slug: paper-execution-surface
title: Paper Execution Surface
milestone: v1.1
requirements: [EXEC-01, EXEC-02, EXEC-03, EXEC-04, EXEC-05]
depends_on: [Phase 9]
branch: phase/10-paper-execution-surface
status: awaiting-signoff
companion_docs: [10-SPEC.md, 10-PREMORTEM.md]
written: 2026-09-22
---

# Phase 10 -- Paper Execution Surface: Plan

**Goal** (ROADMAP.md): A signal becomes a submitted paper order, sized deterministically and refused when risk vetoes -- so the track record reflects only orders the pipeline actually sanctioned.

**What Phase 9 left ready:** `insert_paper_trade()` validates lineage and appends immutably; `(signal_id, attempt_no)` is the DB-level idempotency grain; `risk_status_at_submit`, `policy_sha`, `review_policy_sha`, and `payload` are audit columns the store expects the caller to fill. Phase 10 is the caller.

**What this phase needs from the environment:** Alpaca paper credentials in `.env` for the one live-gated smoke test. Every other test is broker-free (a `FakeBroker` behind a `Protocol`) and runs on SQLite. Postgres is optional (migration 005 round-trip has the same SQLite/PG split as Phase 9).

---

## Decisions requiring sign-off

**D1 -- Execution is a standalone step, not a LangGraph node.** `submit_signal --episodic-id N` reads the stored analysis row and its latest review row (the same "latest review wins" query `reconstruct_audit_trail` already uses), decides, submits, records. Rationale: the human-review gate is a LangGraph *interrupt*; bolting broker I/O onto the resumed run couples an irreversible side effect to the LLM run's checkpointer lifecycle. A standalone step is idempotent by construction (its input is an id), matches Phase 11's standalone mark-to-market job, and honours the CLAUDE.md constraint that trade-level decisions are explicitly human-triggered. The graph keeps ending at `review_store`. A future scheduler (PAPER-03) calls the same function.

**D2 -- `BrokerClient` Protocol + `AlpacaPaperBroker` adapter over the official `alpaca-py` SDK + `FakeBroker` for tests.** `alpaca-py` 0.44.0 (Aug 2026) is on Pydantic v2 and is the vendor's maintained client; hand-rolling the REST surface would be net-new code CLAUDE.md tells us to avoid. It is one new dependency, added in its own commit with the lockfile delta. The adapter is mocked at the SDK-client boundary (the `@patch("...TradingClient")` pattern the Finnhub client already uses); every decision/sizing/idempotency test uses `FakeBroker` and never imports the SDK.

**D3 -- Idempotency enforced at the broker too, via `client_order_id = "sig-{signal_id}-a{attempt_no}"`.** Alpaca rejects a duplicate `client_order_id`, so even if our DB write and the HTTP call race on a retry, the broker cannot double-fill. Attempt policy (pure Python): `attempt_no = 1 + max(existing attempts)`; if the latest row for the signal is `submitted`, raise `AlreadySubmitted` (no new row, no HTTP); a new attempt is allowed only when the latest is `rejected`; `max_attempts` from policy (default 3) caps it. A refusal (D4) is terminal: re-running yields `AlreadyDecided`.

**D4 -- Every non-submission is recorded as a row (uniform audit), which needs migration 005 to widen the status CHECK.** Phase 9 admits `submitted | rejected | refused_veto`. Phase 10 adds `refused_review` (reviewer REJECTED) and `refused_policy` (neutral direction, long-only block, no price, sub-minimum size). Same principle as Phase 8's "write a review row on every path": an auditor can distinguish "never attempted" from "attempted and refused, here is why". `payload.refusal_reason` carries the specific cause. Phase 10 therefore owns migration **005**; Phase 11's `paper_pnl_daily` becomes **006** (ROADMAP amended in T8). The `broker_order_id iff submitted` CHECK is unchanged and still holds for every refusal.

**D5 -- Sizing is a pure function of `(signal, execution_policy, as-of price)` with a SHA-pinned policy.** `config/execution_policy.yaml` declares `nav_cents`, `max_position_pct`, conviction scaling bounds, `long_only`, `max_attempts`, `order_type`. `execution_policy_sha` is fingerprinted like the risk and review policies and stamped into the trade `payload`. The price is the latest `daily_prices.adj_close_cents` with `trade_date <= as_of_date` -- from the cache, never a live quote -- so a size is reproducible from the row alone. Shares = `floor(nav * max_position_pct * scale(conviction) / price)`; zero shares refuses (`refused_policy: below_min_size`) rather than submitting nothing.

**D6 -- NAV baseline: configurable in the policy, default `$100,000`.** This answers the open question from `docs/V1.1_PAPER_TRADING_PLAN.md` with "both": one file, one default, and the SHA changes when someone edits it. Reading equity from the broker account is deferred to v1.2 -- it would make sizing depend on a live value and break reproducibility. **Your call if you'd rather start from broker equity now.**

**D7 -- Long-only for this phase (`long_only: true`).** `direction == "short"` is recorded as `refused_policy: long_only`. This is the conservative option the source plan suggested; shorts add locate/margin semantics that deserve their own pre-mortem. Flipping the flag later changes the policy SHA, so the switch is auditable. **Your call if you want shorts from day one.**

**D8 -- Two hard safety guards, fail-closed:** (a) `AlpacaPaperBroker` refuses to construct unless the host contains `paper-api` -- a live-trading URL in `ALPACA_PAPER_HOST` is a startup error, not a live order; (b) missing credentials raise `MissingBrokerCredentials` naming the variable at construction time, before any order (EXEC-05). Secrets are never logged, and `redact()` strips secret-like keys at *every* nesting level of the broker request/response before it becomes `payload` (Phase 9's tripwire only checks the top level; the pre-mortem there flagged nesting as Phase 10's job).

**D9 -- Fix-as-you-find: one generic `fingerprint()` helper.** `compute_policy_sha` (risk) and `compute_review_policy_sha` (review) are byte-identical copies. Phase 10 would need a third. Promote the canonical-JSON SHA-256 to `ai_hedge_fund/policy_sha.py` and re-point both existing callers; their existing SHA tests are the proof it is byte-for-byte unchanged. Own commit, like D6 in Phase 9.

**Scope note:** fill ingestion (polling the broker for fills into `paper_fills`) is **Phase 11** -- MTM-01 says "pulls fills". Phase 10 records the synchronous submit response only. A paper market order often fills instantly; that fill still enters `paper_fills` in Phase 11.

---

## Success criteria -> proof

| # | ROADMAP criterion | Proven by |
|---|---|---|
| 10.1 | Sizing is pure Python; zero LLM calls between signal and size | `tests/execution/test_sizing.py` (pure-function table tests), `tests/execution/test_no_llm.py` (the `execution` package imports nothing from `pydantic_ai` / `agents`; no `agent.run` in the package) |
| 10.2 | Same `signal_id` twice -> exactly one broker order, one row | `tests/execution/test_submit.py::test_second_submit_raises_already_submitted_without_broker_call`, `::test_network_retry_same_attempt_dedupes` (FakeBroker call count == 1; DB count == 1); `tests/execution/test_alpaca_adapter.py::test_duplicate_client_order_id_maps_to_typed_error` |
| 10.3 | VETOED refused before any broker call (zero HTTP) | `test_submit.py::test_vetoed_refused_zero_broker_calls` (FakeBroker asserts `calls == []`), `::test_vetoed_records_refused_veto_row` |
| 10.4 | Missing credential fails at construction naming the variable | `tests/execution/test_alpaca_adapter.py::test_missing_credentials_named[ALPACA_PAPER_API_KEY / _SECRET / _HOST]`, `::test_live_host_refused` |
| 10.5 | Submitted order's broker id persisted | `test_submit.py::test_submitted_persists_broker_order_id`; live-gated `tests/execution/test_alpaca_live.py::test_paper_roundtrip` (skips without credentials) |

---

## Tasks (ordered; RED -> GREEN -> refactor; one or more atomic commits each)

**T0 -- Fix-as-you-find (D9).** RED: `tests/unit/test_policy_sha.py` pins `fingerprint()` against the known SHA of `config/risk_policy.yaml`. GREEN: `policy_sha.py`; `risk/policy.py` and `review/policy.py` delegate. Existing SHA tests unchanged and green.

**T1 -- Dependency.** `uv add alpaca-py` (bounded `>=0.44,<1`), lockfile committed alone. `uv sync --frozen` gate.

**T2 -- Execution policy (D5, D6, D7).** RED: `test_execution_policy.py` -- YAML loads, `extra=forbid`, bounds, SHA deterministic + change-sensitive, `long_only` default true, `nav_cents` default 10_000_000. GREEN: `execution/policy.py`, `config/execution_policy.yaml`.

**T3 -- Migration 005 (D4).** RED: parity + CHECK tests updated for the new status set; `test_models.py` parametrization gains `refused_review` / `refused_policy` (accepted) and still rejects `filled`. GREEN: `alembic/versions/005_widen_paper_trade_submit_status.py` (drop + re-add the named CHECK; reversible), `records.SubmitStatus` widened, `NewPaperTrade` invariant unchanged.

**T4 -- As-of price + sizing (D5).** RED: `test_prices.py` (latest `adj_close_cents` with `trade_date <= as_of`, none -> `NoPriceAvailable`, temporal leak seed), `test_sizing.py` (table tests: conviction scaling, flooring, zero -> refusal, policy caps, no float money). GREEN: `execution/prices.py`, `execution/sizing.py`.

**T5 -- Broker abstraction (D2, D3, D8).** RED: `test_fake_broker.py` (records calls, honours `client_order_id` uniqueness), `test_alpaca_adapter.py` (SDK mocked: request mapping, `client_order_id` passed, APIError -> `BrokerRejected`, duplicate -> `DuplicateClientOrderId`, credentials named, live host refused, nothing secret in logs), `test_redact.py` (nested secret keys stripped). GREEN: `execution/broker.py` (Protocol, result types, errors), `execution/alpaca.py`, `execution/redact.py`, `tests/execution/fakes.py`.

**T6 -- Decision + submit orchestration (D1, D3, D4).** RED: `test_decide.py` (pure: veto -> refused_veto; REJECTED -> refused_review; neutral / short-under-long-only / no price / zero shares -> refused_policy with reason; APPROVED+NOT_REQUIRED or APPROVED+APPROVED with long -> order), `test_submit.py` (attempt bookkeeping, AlreadySubmitted / AlreadyDecided, retry after rejected -> attempt 2, broker rejection recorded as `rejected` with redacted payload, submitted persists broker id, payload carries `execution_policy_sha` + `client_order_id`, zero LLM). GREEN: `execution/decide.py`, `execution/submit.py`.

**T7 -- CLI.** RED: `tests/scripts/test_submit_signal.py` with injected `broker_factory` / `session_factory` (the `run_analysis` DI pattern): `--dry-run` prints the decision and writes nothing; success/refusal exit codes; `--episodic-id` must be an analysis row. GREEN: `scripts/submit_signal.py`.

**T8 -- Live-gated smoke + docs.** `tests/execution/test_alpaca_live.py` (`@slow`; skips unless `ALPACA_PAPER_API_KEY` set; asserts host is paper; submits 1 share of a liquid ticker, asserts `client_order_id` round-trips, cancels if still open). `.env.example` gains the three vars. ROADMAP: Phase 10 complete, Phase 11 owns migration 006. REQUIREMENTS EXEC-01..05 -> Complete. STATE. `10-SUMMARY.md`. PROGRESS. TECH-DEBT if anything is deferred.

**T9 -- Code review, then PR.** Same protocol as Phase 9: high-effort review against spec + pre-mortem + CLAUDE.md before un-drafting; findings fixed with RED tests first.

---

## Explicitly out of scope

- Fill ingestion / polling into `paper_fills` (Phase 11). Any P&L (Phase 11).
- A LangGraph execution node or changes to `build_debate_pipeline` (D1).
- Reading NAV from broker equity (v1.2). Fractional shares (v1.2). Shorts (policy flag, off).
- Live trading credentials or endpoints -- structurally refused (D8).
- Scheduling / automated daily submission (PAPER-03, deferred).

## Verification gates (every code commit)

- `uv run pytest -q` green; `uv run ruff format --check . && uv run ruff check .` clean; `uv sync --frozen --extra dev` resolves.
- The `execution` package contains no LLM import (10.1) -- enforced by a test, not a review note.

## Open questions -> resolved by recommendation above

NAV baseline (D6) and shorts (D7) are decided here with defaults; override either at sign-off. Promotion thresholds and the live data feed remain Phase 12 / Phase 11 questions.
