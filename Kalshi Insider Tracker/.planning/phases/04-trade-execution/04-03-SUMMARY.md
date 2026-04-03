---
phase: "04"
plan: "03"
subsystem: trade-execution
tags: [cli, config, poller, wiring, paper-mode, live-mode]
dependency_graph:
  requires:
    - "04-02"  # TradeExecutor and RiskGuard implemented
  provides:
    - "ExecutionSettings in config"
    - "trade_executor parameter in make_poll_tick"
    - "tracker start --live CLI flag"
  affects:
    - "daemon/poller.py"
    - "cli.py"
    - "config.py"
    - "kalshi/client.py"
tech_stack:
  added: []
  patterns:
    - "TYPE_CHECKING guard for TradeExecutor in poller.py (prevents circular imports)"
    - "portfolio_api property on KalshiClient (exposes authenticated SDK instance)"
    - "ExecutionSettings with KALSHI_EXEC_ prefix following AppSettings/KalshiSettings pattern"
key_files:
  created: []
  modified:
    - "src/kalshi_tracker/config.py"
    - "src/kalshi_tracker/daemon/poller.py"
    - "src/kalshi_tracker/cli.py"
    - "src/kalshi_tracker/kalshi/client.py"
decisions:
  - "KalshiClient.portfolio_api property exposes PortfolioApi sharing the same RSA-authenticated ApiClient — avoids duplicating auth setup in CLI"
  - "trade_executor defaults to None in make_poll_tick — preserves backwards compatibility with callers that don't pass an executor"
  - "signal_engine.run() return value captured as signals list — enables executor loop without restructuring existing poller logic"
  - "ExecutionSettings.confidence_threshold validated in [0,1] at load time — prevents misconfigured threshold from silently accepting all signals"
metrics:
  duration_minutes: 5
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_modified: 4
---

# Phase 04 Plan 03: Wiring TradeExecutor into Poller and CLI Summary

**One-liner:** End-to-end signal→execution path wired via paper/live CLI flag with ExecutionSettings and injected TradeExecutor in make_poll_tick.

## What Was Built

### Task 1: ExecutionSettings + make_poll_tick extension

- Added `ExecutionSettings` class to `config.py` with `KALSHI_EXEC_` env prefix and `confidence_threshold` field (default 0.6, validated [0,1])
- Added `load_execution_settings()` factory function following existing pattern
- Extended `make_poll_tick` with 5th parameter `trade_executor: "TradeExecutor | None" = None`
- `signal_engine.run()` return value is now captured as `signals` list
- When `trade_executor` is not None, each signal is fed to `trade_executor.execute(signal)` inside a per-signal try/except — execution errors are logged but never propagate to stop the tick

### Task 2: CLI --live flag + KalshiClient.portfolio_api

- Added `--live` boolean flag to `tracker start` Typer command (default False = paper mode)
- `KalshiClient` gains a `portfolio_api` property that exposes the `PortfolioApi` instance sharing the same RSA-authenticated `ApiClient` — no duplicate auth setup
- CLI constructs `RiskGuard` and `TradeExecutor` with `portfolio_api=None` (paper) or `client.portfolio_api` (live)
- `TradeExecutor` is always constructed (even in paper mode) so the full execution path is exercised
- Passes `trade_executor` to `make_poll_tick` as 5th argument

## Deviations from Plan

### Auto-added functionality

**1. [Rule 2 - Missing] KalshiClient.portfolio_api property**
- **Found during:** Task 2 — plan mentioned reading KalshiClient to find PortfolioApi accessor
- **Issue:** KalshiClient had no public way to expose its PortfolioApi to CLI callers
- **Fix:** Added `portfolio_api` property returning `self._portfolio_api` (already constructed internally alongside MarketsApi)
- **Files modified:** `src/kalshi_tracker/kalshi/client.py`
- **Commit:** a1f4ff8

No other deviations — plan executed as designed.

## Test Results

- Before: 54 passed, 4 deselected (integration)
- After: 54 passed, 4 deselected (integration)
- Regressions: 0

## Self-Check: PASSED

Files verified:
- [x] `src/kalshi_tracker/config.py` — ExecutionSettings and load_execution_settings present
- [x] `src/kalshi_tracker/daemon/poller.py` — trade_executor param + execute loop present
- [x] `src/kalshi_tracker/cli.py` — --live flag + TradeExecutor construction present
- [x] `src/kalshi_tracker/kalshi/client.py` — portfolio_api property present
- [x] Commit 787bac5: Task 1
- [x] Commit a1f4ff8: Task 2
