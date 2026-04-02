# Kalshi Insider Tracker

## What This Is

An automated system that monitors Kalshi politics/policy prediction markets for abnormal trading activity suggestive of insider knowledge, then copies those trades in real-time. It detects volume spikes, sharp price moves, win streaks, and suspicious timing clusters — then auto-executes the same directional bet with conservative position limits.

## Core Value

Detect and copy insider-like trades on Kalshi politics/policy markets before the event resolves — turning information asymmetry detection into profit.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] System polls Kalshi API every 5-10 seconds for politics/policy market activity
- [ ] Detect abnormal volume spikes relative to market baseline
- [ ] Detect sharp price movements before event resolution
- [ ] Detect accounts/patterns with unusual win streaks on low-liquidity markets
- [ ] Detect suspicious timing clusters (trades bunched in narrow windows before resolution)
- [ ] Auto-execute copy trades when signal confidence exceeds threshold
- [ ] Enforce per-trade limit (~$50) and total exposure limit (~$500)
- [ ] Live dashboard showing monitored markets, active signals, and current positions
- [ ] Full trade log (every signal detected, every trade placed, outcomes)
- [ ] Running P&L tracking across all trades

### Out of Scope

- Non-politics markets (economics, weather, sports) — focusing on politics/policy where insider info is most actionable for v1
- Push notifications (Slack, SMS, email) — dashboard is primary interface for v1
- Manual/semi-auto execution modes — fully automated from day one
- Backtesting framework — the shared backtest module in the parent project handles this
- Multi-account support — single Kalshi account for v1

## Context

- Kalshi is a CFTC-regulated prediction market where users trade on real-world event outcomes
- Politics/policy markets (elections, regulatory decisions, government actions) are the target — these are where insider knowledge is most likely to appear and most valuable
- Kalshi provides a public REST API and the user has an API key
- The system must distinguish genuine insider signals from normal market noise (whale trades, hedging, market making)
- This is a research-driven strategy — the signal detection heuristics will need tuning over time
- Conservative risk limits reflect that this is experimental and signals need validation in production

## Constraints

- **Data source**: Kalshi public API only — no scraping, no third-party data providers for v1
- **Polling**: 5-10 second intervals — not WebSocket (simpler, sufficient for politics markets which don't move sub-second)
- **Stack**: Python 3.11+ — consistent with the rest of the AI Hedge Fund
- **Risk**: Hard limits on position sizing ($50/trade, $500 total) enforced at the system level, not just config
- **Independence**: Self-contained strategy module — no hard dependencies on AI Washing Detector or other strategies
- **Rate limits**: Must respect Kalshi API rate limits

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Politics/policy markets only | Insider knowledge most actionable and detectable in this category | -- Pending |
| Polling over WebSocket | Simpler implementation, politics markets don't require sub-second latency | -- Pending |
| Full auto-execution | User wants no human-in-the-loop; conservative limits mitigate risk | -- Pending |
| All four signal types from day one | Volume, price, win streaks, timing — comprehensive detection vs. shipping one at a time | -- Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-02 after initialization*
