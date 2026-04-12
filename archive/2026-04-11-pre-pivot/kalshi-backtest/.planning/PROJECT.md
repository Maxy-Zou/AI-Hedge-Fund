# Kalshi Backtesting Engine

## What This Is

A strategy-agnostic backtesting engine for Kalshi prediction markets. Pulls historical contract data from the Kalshi API, replays trading signals against actual price movements, and produces P&L metrics, trade logs, visual dashboards, and strategy comparisons. Designed with a plugin interface so any future Kalshi strategy — not just insider tracking — can be backtested by implementing a simple Strategy protocol.

## Core Value

Accurately simulate any Kalshi trading strategy against historical data so you can validate signal quality and optimize parameters before risking real capital.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Historical Kalshi contract data ingestion from Kalshi API (all event categories)
- [ ] Data storage with append-only semantics for historical contract snapshots
- [ ] Strategy plugin interface — define a Strategy protocol, implement `generate_signals()`, plug it in
- [ ] Signal replay engine — replay historical signals against actual contract price movements
- [ ] Strategy parameter optimization — test different entry/exit rules, sizing, thresholds
- [ ] P&L metrics — total return, Sharpe, max drawdown, win rate, avg trade P&L
- [ ] Trade log — every entry/exit with timestamps, prices, contract details
- [ ] Visual dashboard — equity curve, trade markers, strategy performance charts
- [ ] Strategy comparison — run multiple strategies side-by-side and compare results
- [ ] Insider Tracker adapter — first strategy plugin consuming signals from the Kalshi Insider Tracker

### Out of Scope

- Equities/stock backtesting — already handled by `backtest/` module
- Live trading execution — this is simulation only
- Market-making strategies — signal-based strategies only for v1
- Real-time streaming — batch historical analysis, not live feeds
- Mobile or web deployment — CLI and local dashboard only

## Context

- The AI Hedge Fund already has a stock backtesting framework at `backtest/` (equities, daily OHLCV, PostgreSQL). This is a separate engine because Kalshi's binary event contracts have fundamentally different data models (yes/no pricing, event resolution, expiration dates) vs. stock OHLCV bars.
- The Kalshi Insider Tracker (`Kalshi Insider Tracker/`) is the first signal source — it detects unusual activity in Kalshi markets. Its signals will be the first consumer of this backtesting engine.
- Kalshi API provides historical contract and event data. All event categories (weather, politics, economics, crypto, sports) are in scope.
- Past ~1 year of historical data is the initial target lookback window.
- Future strategies will be signal-based (volume spikes, price momentum, cross-market signals, etc.) and should plug in via the same Strategy protocol.

## Constraints

- **Data source**: Kalshi API only — no third-party data providers for v1
- **Stack**: Python 3.11+, uv — consistent with existing fund infrastructure
- **Immutability**: Historical contract data must never be overwritten — append new snapshots only (fund-wide convention)
- **Independence**: Must work as a standalone module — no hard dependency on Insider Tracker internals (communicate via the Strategy plugin interface)
- **History**: ~1 year lookback (configurable per backtest run)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Separate module from stock backtest | Kalshi binary events are fundamentally different from equity OHLCV — shared abstractions would be forced | — Pending |
| Plugin Strategy interface | User wants to add future strategies easily — protocol/ABC pattern is cleanest | — Pending |
| Kalshi API as sole data source | Free, authoritative, sufficient for v1 | — Pending |
| Signal-based strategies only | Keeps scope manageable; market-making is a different problem domain | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-04 after initialization*
