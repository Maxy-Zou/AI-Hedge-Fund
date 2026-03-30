# Shared Backtesting Infrastructure

## What This Is

Strategy-agnostic backtesting framework and historical market data pipeline for the AI Hedge Fund. Collects daily OHLCV price data for mid-cap equities ($2B-$10B market cap), runs vectorized backtests against any signal the fund produces, and generates investor-ready output (interactive dashboard, PDF tearsheets, raw data exports). The first consumer is the AI Washing Detector's short signal, but the framework is designed for any future strategy.

## Core Value

Produce compelling, realistic backtest results the moment any strategy signal is ready — so investor conversations can start immediately.

## Requirements

### Validated

- ✓ Universe management — maintain and refresh the list of target tickers matching market cap criteria — Phase 1
- ✓ GICS sector classification per ticker stored in PostgreSQL — Phase 1
- ✓ Historical daily OHLCV price data for mid-cap universe via yfinance — Phase 2
- ✓ Data caching and incremental updates — append-only PostgreSQL cache — Phase 2
- ✓ Data validation — ±50% return anomalies, gap detection, coverage alerting — Phase 2
- ✓ Chunked downloads with retry — 80-ticker batches, tenacity exponential backoff — Phase 2
- ✓ Signal contract — typed SignalFrame/WeightFrame with validation — Phase 3
- ✓ Look-ahead bias prevention — shift(1) in Signal Adapter, not simulator — Phase 3
- ✓ Vectorized portfolio simulator with short support — Phase 4
- ✓ Transaction cost modeling — slippage, commission, borrow costs in frozen CostConfig — Phase 4
- ✓ Equal-weight position sizing (via upstream SignalAdapter) — Phase 4
- ✓ Daily returns Series + trade log DataFrame output — Phase 4
- ✓ Risk metrics — Sharpe, Sortino, Calmar, drawdown, CAGR, hit rate, turnover — Phase 5
- ✓ Benchmark comparison with alpha/beta — Phase 5
- ✓ Rolling Sharpe + rolling drawdown at configurable windows — Phase 5
- ✓ Streamlit dashboard — equity curve, drawdown, monthly heatmap, sector exposure — Phase 6
- ✓ PDF tearsheet — single-page factsheet with metrics and charts — Phase 7
- ✓ CSV/JSON exports with cost assumption labels — Phase 7
- ✓ AI Washing Detector integration — live score loading via shared PostgreSQL — Phase 8
- ✓ End-to-end pipeline — signal → adapt → simulate → metrics → export — Phase 8

### Active
- [ ] Vectorized backtesting engine — takes a signal DataFrame (date x ticker → score) and simulates a long/short portfolio
- [ ] Realistic transaction cost modeling — slippage, commission, borrow costs for shorts
- [ ] Risk metrics computation — Sharpe, Sortino, max drawdown, Calmar, hit rate, win/loss ratio, turnover
- [ ] Benchmark comparison — compare strategy returns against S&P 500, Russell 2000, and equal-weight mid-cap
- [ ] Position sizing — configurable rules (equal weight, score-proportional, risk parity)
- [ ] Interactive Streamlit dashboard — equity curves, drawdown charts, rolling metrics, sector breakdown
- [ ] PDF tearsheet generation — single-page fund factsheet with key metrics and charts
- [ ] Raw data export — CSV/JSON of daily returns, positions, and trade log
- [ ] Integration interface — well-defined contract for how strategy modules (like AI Washing Detector) pass signals in

### Out of Scope

- Event-driven / tick-level backtesting — overkill for daily signal strategies, adds complexity without value for v1
- Live trading execution — this is backtesting only, not a trading system
- Intraday data — daily granularity is sufficient for the fund's signal cadence
- Paid data providers — yfinance is sufficient for v1; can upgrade later if coverage gaps emerge
- Jupyter notebook output — dashboard and tearsheet cover investor needs; notebooks add maintenance burden

## Context

- The AI Washing Detector (in `Al Washing Detector/`) is the first strategy being built in a separate terminal. It produces daily AI Washing Risk Scores per company. Once it's operational, its scores become the first signal fed into this backtester.
- The hedge fund targets mid-cap companies ($2B-$10B market cap) — roughly 200-500 tickers at any given time.
- Investors expect standard quant fund metrics: Sharpe ratio, max drawdown, and an equity curve at minimum. A polished tearsheet significantly improves credibility.
- yfinance provides free daily OHLCV with no API key. Known limitations: occasional gaps, no corporate actions adjustment guarantees, rate limiting on bulk requests.
- The backtester must handle short-selling signals (the AI Washing Detector is a short strategy).
- The shared database is PostgreSQL (same instance as the Detector uses).
- Python 3.11+ with uv as package manager, consistent with the Detector's stack.

## Constraints

- **Data source**: yfinance only for v1 — free, no API key, daily OHLCV
- **Frequency**: Daily bars only — matches the fund's signal cadence
- **History**: 5 years minimum (back to ~2021) to cover COVID recovery and multiple regimes
- **Stack**: Python 3.11+, uv, PostgreSQL — consistent with existing fund infrastructure
- **Immutability**: Historical price data must never be overwritten — append new snapshots only (fund-wide convention)
- **Independence**: Must work as a standalone module — no hard dependency on the AI Washing Detector's internals

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Vectorized over event-driven | Daily signals don't need tick simulation; vectorized is 10-100x faster and simpler | -- Pending |
| yfinance for price data | Free, no API key, sufficient for daily OHLCV on mid-caps | -- Pending |
| Streamlit for dashboard | Already in the Detector's stack, fast to build, good for investor demos | -- Pending |
| Strategy-agnostic interface | Future strategies plug in without modifying the backtester | -- Pending |
| Separate branch workflow | Other terminal actively building Detector on main; avoid git conflicts | -- Pending |

## Current Milestone: v1.1 Live End-to-End Pipeline

**Goal:** Run the full pipeline with real data so the dashboard shows actual backtest results from real AI Washing Detector scores.

**Target features:**
- PostgreSQL setup via Docker Compose for local development
- Download real OHLCV price data for the mid-cap universe
- Run the AI Washing Detector against real SEC filings to produce scores
- Execute a real backtest (signal → simulate → metrics)
- Dashboard and tearsheet displaying actual results

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
*Last updated: 2026-03-29 — Milestone v1.1 started*
