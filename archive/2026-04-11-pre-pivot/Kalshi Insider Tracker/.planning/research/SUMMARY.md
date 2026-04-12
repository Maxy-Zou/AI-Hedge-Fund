# Research Summary: Kalshi Insider Tracker

**Domain:** Real-time prediction market anomaly detection + automated copy-trading
**Researched:** 2026-04-02
**Overall confidence:** MEDIUM — Fund stack verified from sibling projects (HIGH). Kalshi-specific API surface from training data (MEDIUM). Rate limits and ToS verified only at implementation time (LOW).

---

## Executive Summary

The Kalshi Insider Tracker is a single-process Python daemon that polls Kalshi's politics/policy markets every 5-10 seconds, applies four anomaly detectors (volume spike, price movement, win streak, timing cluster), and auto-executes copy trades when signals cross a confidence threshold. It is self-contained within the AI Hedge Fund project structure and shares almost the entire technology stack with the sibling Al Washing Detector module.

The technology choices are de-risked by the existing fund stack. PostgreSQL, SQLAlchemy, Pydantic, structlog, tenacity, Typer, Streamlit, and plotly are all already in production in sibling projects with verified versions. The only net-new additions are `kalshi-python` (official SDK), `APScheduler` (interval polling), and `scipy` (statistical tests). This means the implementation risk concentrates almost entirely on the Kalshi API integration specifics — authentication, rate limits, and available endpoints — not on framework selection.

The system's architecture follows a strict five-layer hierarchy (Ingest → Signal Engine → Risk Guard → Trade Executor → Persistence) with a read-only Streamlit dashboard as the observability layer. A critical design constraint is that the Risk Guard must enforce the $50/trade and $500/total-exposure limits as compiled-in constants, not configurable values — this is non-negotiable before any live execution is enabled. Failure to enforce this at the code level (rather than config level) is the most common cause of runaway positions in automated trading systems.

The four signal types have significantly different implementation complexity. Volume spike and price movement detectors are straightforward rolling-statistic computations that can be implemented early. The timing cluster detector requires a trade-event buffer and resolution-date awareness to avoid false positives on normal resolution-day activity. The win streak detector is the hardest — it requires per-account trade history which the Kalshi public API may not expose, making this signal architecturally uncertain until the API surface is verified.

---

## Key Findings

**Stack:** Python 3.11+, kalshi-python SDK, APScheduler (polling), pandas/scipy (signal math), PostgreSQL + SQLAlchemy (persistence), Streamlit + plotly (dashboard) — consistent with the existing fund stack

**Architecture:** Single-process daemon; five-layer strict dependency hierarchy; append-only PostgreSQL; Risk Guard as a hard gate; Streamlit dashboard reads from DB independently

**Critical pitfall:** Race condition between signal detection and order execution — the same market condition can trigger duplicate orders on consecutive polls without explicit signal deduplication and in-flight order tracking

---

## Implications for Roadmap

Based on research, suggested phase structure:

1. **Foundation: DB schema + Kalshi API client** — All other work depends on this. Verify auth mechanism, rate limits, and available endpoints here. Build the typed domain objects (MarketSnapshot, TradeEvent) as frozen dataclasses before any signal logic.
   - Addresses: Market polling, trade log persistence
   - Avoids: Building signal logic on an unverified API surface

2. **Data collection: Polling loop** — APScheduler with IntervalTrigger; ingest layer that normalizes Kalshi responses into typed domain objects. No signal processing yet — just collect and persist.
   - Addresses: 5-10 second polling requirement
   - Avoids: Signal noise before baselines are established (warm-up period)

3. **Signal detection: Volume spike + price movement** — The two most computable signals from public API data. Per-market rolling baselines. Z-score thresholds loaded from YAML config.
   - Addresses: Primary anomaly signals
   - Avoids: Win streak complexity (save for later)

4. **Execution: Risk Guard + Trade Executor** — Wire detection to execution. Risk Guard must exist before any order is placed. Start with paper trading mode.
   - Addresses: Auto-execution, hard position limits
   - Avoids: Live capital risk before signals are validated

5. **Dashboard: Streamlit monitoring UI** — Markets, signals, positions, P&L. Auto-refresh every 10s.
   - Addresses: Live monitoring interface

6. **Signal expansion: Timing cluster + win streak** — Add remaining signals once volume/price signals are validated in production.
   - Addresses: Suspicious timing detection; win streak (subject to API feasibility)
   - Avoids: Win streak if Kalshi API doesn't expose per-account history

**Phase ordering rationale:**
- DB schema and API client must come first — everything else reads from or writes to both
- Polling loop before signal logic — signals need baseline data that only accumulates from polling
- Risk Guard before Trade Executor — the executor must never exist in a deployable state without the guard
- Dashboard can be developed in parallel with phases 3-4 since it only requires the DB schema from phase 1
- Win streak deferred — uncertain API feasibility; don't block other signals on it

**Research flags for phases:**
- Phase 1 (API client): HIGH priority to verify — authentication mechanism, exact endpoint paths, rate limits, whether client_order_id is supported for idempotent orders
- Phase 1 (API client): Verify per-account trade history availability — determines win streak feasibility
- Pre-execution: Verify Kalshi ToS on automated trading before enabling live execution
- Phase 4 (execution): Start in paper trading mode; review logs before switching to live

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH (fund conventions) / MEDIUM (Kalshi SDK) | Fund stack verified from sibling pyproject.toml files. kalshi-python version unverified — check PyPI before adding. |
| Features | HIGH | Derived directly from PROJECT.md requirements; no speculation |
| Architecture | HIGH (patterns) / MEDIUM (API surface) | Polling daemon architecture is standard. Kalshi-specific endpoint paths are MEDIUM confidence from training data — verify at implementation. |
| Pitfalls | HIGH (general trading patterns) / LOW (Kalshi-specific) | Race conditions, market impact, position limit enforcement are well-documented algorithmic trading patterns. Kalshi ToS and rate limits require direct verification. |

---

## Gaps to Address

1. **Kalshi API rate limits** — Not publicly documented with a hard number. Implement conservative rate limiting from day one (stay under 60 req/min) and tune from observations. This is the most immediate operational unknown.

2. **Per-account trade history availability** — The win streak signal assumes you can identify individual account activity. The Kalshi public API may anonymize or aggregate trade history. Verify before designing win streak architecture — this could make the signal infeasible as described.

3. **kalshi-python SDK version and completeness** — The official SDK may not cover all needed endpoints (particularly order book depth and per-market trade history). Verify which endpoints are in the SDK vs. require raw httpx calls.

4. **Kalshi client_order_id support** — Idempotent order submission requires this. If not supported, need an alternative deduplication approach (pre-submission open-order query).

5. **Kalshi ToS on automated trading** — Must be verified before deploying real capital. The system as designed could be classified as systematic front-running or copy-trading depending on how Kalshi interprets their ToS. This is a hard prerequisite for live execution, not just a nice-to-have.

6. **kalshi-python SDK auth mechanism** — As of training data (August 2025), Kalshi v2 API uses RSA key-pair signing. The official SDK should handle this, but the exact setup flow (key format, required environment variables) needs to be verified against current documentation before the first API call is attempted.

---

## Sources

- `.planning/PROJECT.md` — authoritative project requirements
- `Al Washing Detector/pyproject.toml` — verified fund stack versions
- `backtest/pyproject.toml` — verified Streamlit, plotly, pandas versions
- Training data (August 2025 cutoff) — Kalshi API structure, APScheduler, algorithmic trading patterns
- Note: WebSearch and WebFetch were unavailable during this research session. All Kalshi-specific claims should be verified against https://trading.kalshi.com/trade-api/v2/docs before implementation begins.
