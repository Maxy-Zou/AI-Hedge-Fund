---
phase: 04-trade-execution
plan: "01"
subsystem: execution
tags: [tdd, red-tests, risk-guard, trade-executor, type-contracts]
dependency_graph:
  requires: []
  provides:
    - execution layer RED test suite (9 tests)
    - ApprovalResult and ExecutionResult frozen dataclasses
  affects:
    - 04-02-PLAN.md (GREEN implementation of RiskGuard + TradeExecutor)
tech_stack:
  added: []
  patterns:
    - TDD RED-first: all tests written before any production implementation
    - frozen dataclass type contracts for interface definition
    - mock_session_factory pattern from signals/conftest.py replicated
key_files:
  created:
    - tests/unit/execution/__init__.py
    - tests/unit/execution/conftest.py
    - tests/unit/execution/test_risk_guard.py
    - tests/unit/execution/test_executor.py
    - src/kalshi_tracker/execution/__init__.py
    - src/kalshi_tracker/execution/types.py
  modified: []
decisions:
  - "signal_factory uses current_price (not price_cents) to match Signal.details JSONB schema with direction and contracts fields"
  - "trade_factory builds MagicMock with all Trade ORM fields for flexible test composition"
  - "ApprovalResult.trade_cost_cents defaults to 0 to support blocked results without extra construction"
metrics:
  duration_seconds: 139
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_created: 6
  files_modified: 0
requirements:
  - EXEC-01
  - EXEC-02
  - EXEC-03
  - EXEC-04
  - EXEC-05
  - EXEC-06
  - LOG-02
---

# Phase 04 Plan 01: Execution Layer RED Tests + Type Contracts Summary

**One-liner:** 9 RED tests covering all execution requirements (EXEC-01 through EXEC-06, LOG-02) with ApprovalResult/ExecutionResult frozen dataclass contracts for Plan 02 implementers.

## What Was Built

Created the TDD RED test suite for the execution layer and the type contract definitions. No production implementation code — only tests and interface definitions.

### Task 1: RiskGuard RED Tests + conftest

- `tests/unit/execution/__init__.py` — package marker
- `tests/unit/execution/conftest.py` — shared fixtures following established mock_session_factory pattern:
  - `mock_session_factory`: returns `(factory, session)` with full query chain mocking
  - `signal_factory`: callable creating Signal MagicMocks with `ticker`, `confidence`, `details` (direction, current_price, contracts)
  - `trade_factory`: callable creating Trade MagicMocks with all ORM fields
- `tests/unit/execution/test_risk_guard.py` — 5 RED tests:
  - `test_per_trade_cap_blocks` (EXEC-03): 51 cents * 100 contracts = 5_100 > 5_000
  - `test_total_exposure_cap_blocks` (EXEC-04): existing 49_500 + new 600 = 50_100 > 50_000
  - `test_duplicate_signal_blocks` (EXEC-05): filled Trade within 300s dedup window
  - `test_in_flight_blocks` (EXEC-06): pending Trade within 60s in-flight window
  - `test_approve_passes_clean`: no trades, cost within cap → approved=True

### Task 2: TradeExecutor RED Tests + types.py

- `src/kalshi_tracker/execution/__init__.py` — package marker
- `src/kalshi_tracker/execution/types.py` — interface contracts:
  - `ApprovalResult(frozen=True)`: approved, reason, trade_cost_cents
  - `ExecutionResult(frozen=True)`: trade, mode
- `tests/unit/execution/test_executor.py` — 4 RED tests:
  - `test_paper_trade_writes_row` (EXEC-01): portfolio_api=None → Trade(mode='paper', status='filled') added
  - `test_live_trade_calls_api` (EXEC-02): portfolio_api=mock → create_order() called once
  - `test_blocked_trade_logged` (LOG-02): RiskGuard blocks → Trade(status='rejected') persisted
  - `test_below_threshold_returns_none`: confidence=0.3 < threshold=0.6 → None, no DB write

## Verification

```
$ uv run pytest tests/unit/execution/
ERROR tests/unit/execution/test_risk_guard.py  — ModuleNotFoundError: kalshi_tracker.execution.risk_guard
ERROR tests/unit/execution/test_executor.py    — ModuleNotFoundError: kalshi_tracker.execution.executor
```

Both test files fail with ModuleNotFoundError — RED state confirmed. types.py imports successfully:
```
$ python -c "from kalshi_tracker.execution.types import ApprovalResult, ExecutionResult"
# (no error)
```

## Commits

| Hash | Message |
|------|---------|
| c1d2dbf | test(04-01): add 9 RED tests for execution layer |

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- [x] `tests/unit/execution/__init__.py` exists
- [x] `tests/unit/execution/conftest.py` exists
- [x] `tests/unit/execution/test_risk_guard.py` exists with 5 test functions
- [x] `tests/unit/execution/test_executor.py` exists with 4 test functions
- [x] `src/kalshi_tracker/execution/__init__.py` exists
- [x] `src/kalshi_tracker/execution/types.py` exists with ApprovalResult and ExecutionResult
- [x] All 9 tests fail with ModuleNotFoundError (RED state)
- [x] `from kalshi_tracker.execution.types import ApprovalResult, ExecutionResult` succeeds
- [x] Commit c1d2dbf exists
