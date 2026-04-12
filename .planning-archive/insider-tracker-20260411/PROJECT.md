# Insider Tracker Backtesting Pipeline

## What This Is

An end-to-end pipeline that replays historical Kalshi prediction market data through the Insider Tracker's signal detectors, populates a PostgreSQL database with historical signals, and runs the kalshi-backtest engine's InsiderTrackerAdapter strategy against them to produce P&L metrics. Connects two existing, functional codebases — the Insider Tracker (signal detection) and kalshi-backtest (backtesting engine) — with the missing infrastructure and replay logic needed to get backtest results.

## Core Value

Get real P&L numbers from running the insider trading detection algorithm against historical Kalshi data — so you can validate whether the signal is profitable before risking capital.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] PostgreSQL installed and running locally
- [ ] Insider Tracker database created with schema (alembic migration)
- [ ] Historical Kalshi market data available for replay (from kalshi-backtest's DuckDB or fresh API pull)
- [ ] Historical replay module that feeds Kalshi historical data through Insider Tracker signal detectors (volume spike, price move, timing cluster)
- [ ] Replay module populates the Insider Tracker's PostgreSQL `signals` table with time-accurate historical signals
- [ ] kalshi-backtest's InsiderTrackerAdapter reads signals from PostgreSQL during backtest
- [ ] Backtest runs end-to-end producing P&L metrics (win rate, total return, Sharpe)
- [ ] Clear CLI workflow: one or two commands to replay → backtest → see results

### Out of Scope

- Live trading — this is about validating the signal historically
- New signal detectors — use the existing 3 detectors as-is
- Dashboard/visualization beyond basic P&L numbers — just need the metrics
- Modifying the Insider Tracker's real-time polling system
- Modifying the kalshi-backtest engine internals

## Context

**Existing codebases:**
- `Kalshi Insider Tracker/` — Fully functional real-time signal detection system. 3 detectors (volume spike, price move, timing cluster). PostgreSQL-backed. APScheduler polling. Paper/live modes. Has alembic migration for schema. No historical backfill capability.
- `kalshi-backtest/` — Fully functional backtesting engine. DuckDB storage. Historical Kalshi API ingestion working. Has `InsiderTrackerAdapter` strategy that reads from Insider Tracker's PostgreSQL. Has recent output from prior runs. Strategy Protocol interface.

**The gap:** The Insider Tracker only generates signals from real-time market polling. The backtester's `InsiderTrackerAdapter` expects signals in PostgreSQL. A replay module is needed to bridge historical data → signal detection → PostgreSQL.

**Data:** kalshi-backtest already has historical Kalshi data in DuckDB (markets + candles tables, Dec 2025+). The Kalshi API can pull more if needed.

**Credentials:** Kalshi API key and PEM file are already configured.

## Constraints

- **PostgreSQL**: Must be installed from scratch on macOS
- **Data source**: Kalshi API only — use existing kalshi-backtest ingestion or direct API calls
- **Signal detectors**: Use the Insider Tracker's existing detectors unchanged — don't rewrite them
- **Stack**: Python 3.11+, uv — consistent with both existing projects
- **Immutability**: Append-only signal and snapshot data (fund-wide convention)
- **Independence**: Replay module should bridge the two projects without creating tight coupling

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Replay historical data through existing detectors (not embed detectors in backtest) | Keeps signal logic in one place (Insider Tracker), tests the actual detection code path | — Pending |
| PostgreSQL for signal storage (not DuckDB) | InsiderTrackerAdapter already reads from PostgreSQL; matches Insider Tracker's schema | — Pending |
| Use kalshi-backtest's existing DuckDB data as replay source | Data already ingested and validated; avoids duplicate API calls | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-06 after initialization*
