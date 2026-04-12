# Feature Landscape

**Domain:** Prediction market anomaly detection and automated copy-trading (Kalshi politics/policy)
**Researched:** 2026-04-02
**Confidence:** MEDIUM — web search unavailable; findings drawn from domain knowledge of market microstructure, algorithmic trading, and surveillance system design. Flags noted where empirical validation is needed.

---

## Table Stakes

Features that must exist or the system is useless. Missing any one makes the product incoherent.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Kalshi market poller | Cannot detect anything without live data | Low | REST polling every 5-10s; must handle pagination and rate-limit backoff gracefully |
| Market universe filter | Need to scope to politics/policy category only | Low | Filter by `category` field from Kalshi API; maintain whitelist of active market series |
| Volume spike detector | Primary signal — unusual volume is the first indicator of informed trading | Medium | Requires rolling baseline per market (7-14 day trailing average); z-score or percentile threshold |
| Price movement detector | Sharp YES/NO price shifts before resolution indicate informed flow | Medium | Track mid-price change per polling interval; flag moves beyond 2-3 standard deviations |
| Win-streak tracker | Repeated wins on low-liquidity markets = non-random performance | High | Requires per-account trade history; Kalshi public API exposes aggregate trades, not individual accounts — this is the hardest signal to compute |
| Timing-cluster detector | Trades bunching in narrow windows before resolution = suspicious coordination | Medium | Track trade timestamps in a rolling window (e.g., 30-60 min before scheduled resolution) |
| Signal confidence scorer | Combine individual signals into a single go/no-go decision for trade execution | Medium | Weighted composite of triggered signals; threshold must be tunable without code changes |
| Copy-trade executor | The entire point of the system — buy the same direction as the detected signal | Medium | Must respect Kalshi order placement API; handle partial fills and rejected orders |
| Per-trade hard limit ($50) | Protects capital while signals are unvalidated | Low | Enforced at system level, not just config — must be a hard ceiling in the order-placement code |
| Total exposure hard limit ($500) | Caps total open-position risk | Low | Sum of open YES + NO positions; block new trades when limit reached regardless of signal score |
| Trade log persistence | Every signal, every order, every outcome must be recorded | Low | Append-only storage; needed for P&L, tuning, and audit trail |
| Running P&L tracker | Know if the system is making money | Low | Per-trade realized P&L on resolution; unrealized mark-to-market on open positions |
| Live dashboard | Primary human interface — see what the system is doing | Medium | Shows: monitored markets, recent signals, current positions, cumulative P&L |
| Graceful API error handling | Kalshi API will return 429s, 503s, timeouts | Low | Exponential backoff with jitter; never let a transient error cascade into a missed signal or duplicate order |

---

## Differentiators

Features that add real competitive edge. Not expected at baseline, but meaningfully increase signal quality or operational confidence.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Per-market adaptive baseline | Static global thresholds miss market-specific liquidity regimes | Medium | Each market has its own volume/price baseline updated continuously; prevents false signals on chronically thin markets |
| Signal decay timer | Insider signals expire — don't copy a trade if too much time has passed since detection | Low | Set configurable TTL (e.g., 15 minutes) after which a signal is discarded even if still above threshold |
| Duplicate signal suppression | Same market signaling repeatedly should not multiply position size | Low | Track open position per market; block additional buy signals if already positioned |
| Order book depth inspection | A volume spike on an illiquid order book is more significant than on a deep one | Medium | Pull order book snapshot alongside trade feed; adjust signal score by relative depth |
| Pre-resolution lockout | Copying trades within minutes of scheduled resolution is low-EV | Low | Configurable blackout window (e.g., final 5 minutes) — signal may be priced-in already |
| Signal attribution log | Record which sub-signals triggered each copy-trade | Low | Invaluable for later tuning — did volume-spike signals outperform timing-cluster signals? |
| Position aging alerts | Flag positions that have been open longer than expected without resolution | Low | Alerts in dashboard when a position is still open X days past expected resolution date |
| Market metadata enrichment | Tag each market with scheduled resolution date and known news catalysts | Medium | Improves timing-cluster detector accuracy — cluster before known deadline vs. random date means more |
| Configurable signal weights | Tune the composite score without deploys | Low | YAML or JSON config file; each signal's weight and threshold independently adjustable |
| Paper trading mode | Simulate execution without real money to validate signal quality | Low | Log "would have placed" orders; compare to actual outcomes — critical for initial validation phase |

---

## Anti-Features

Features to explicitly NOT build in v1. Each has a specific reason.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| WebSocket real-time feed | Added complexity, WebSocket reconnect logic is fragile, politics markets don't require sub-second latency | REST polling every 5-10 seconds is sufficient and simpler |
| Per-account win-streak tracking via scraping | Kalshi does not expose per-account trade history in the public API; scraping violates ToS and is fragile | Approximate win-streak signals via aggregate market-level patterns (consecutive sharp moves from same direction) |
| Multi-leg / spread positions | Complexity explodes; position tracking for spreads requires a separate accounting layer | Single directional copy-trades (YES or NO) only |
| Automatic threshold auto-tuning | Feedback loops that adjust thresholds based on P&L create overfitting and instability | Manual threshold review after each production week; tune deliberately |
| Push notifications (Slack/SMS/email) | Dashboard is sufficient for v1; notification infrastructure is scope creep | Build dashboard first; add notifications only when user validates need in production |
| Manual override / semi-auto mode | The user explicitly chose full-auto; a half-baked semi-auto mode adds UI complexity for no value | Hard limits ($50/$500) are the human-override mechanism |
| Non-politics market monitoring | Economics, weather, and sports markets have different insider dynamics; mixed signals corrupt the model | Explicitly scope to `category=politics` in the market filter; add other categories only after v1 validation |
| Historical backfill of signals | Backtesting is handled by the shared backtest framework in the parent project | Export trade log in a format compatible with the shared backtester; don't duplicate backtesting logic here |
| Portfolio optimization / Kelly sizing | Conservative fixed limits are intentional — this is an unvalidated experimental strategy | Fixed $50/trade until P&L data justifies dynamic sizing |
| User authentication / multi-user support | This is a single-operator system | No login layer needed; run locally or on a private server |
| REST API / webhook exposure | No downstream consumers of this system's signals in v1 | Internal modules only; expose via dashboard, not HTTP endpoints |

---

## Feature Dependencies

```
Kalshi market poller
  └── Market universe filter
        ├── Volume spike detector          ← requires rolling baseline
        ├── Price movement detector        ← requires rolling baseline
        ├── Timing-cluster detector        ← requires trade timestamp stream
        └── Win-streak tracker             ← requires aggregate trade history (limited by API)

Volume spike detector ─┐
Price movement detector─┤
Win-streak tracker     ─┼──► Signal confidence scorer
Timing-cluster detector─┘         │
                                   ▼
                           Copy-trade executor
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼               ▼
              Trade log    Per-trade limit   Total exposure limit
                    │
                    ▼
              P&L tracker
                    │
                    ▼
              Live dashboard
```

Additional dependency constraints:

- **Signal decay timer** depends on signal confidence scorer (must know when a signal was first raised)
- **Duplicate signal suppression** depends on trade log (must know current open positions)
- **Pre-resolution lockout** depends on market metadata (must know scheduled resolution timestamp)
- **Paper trading mode** depends on copy-trade executor (wraps executor with a "dry run" flag)
- **Signal attribution log** is a natural extension of the trade log (same write path, richer payload)

---

## MVP Recommendation

Prioritize these features in order for a working v1:

1. **Kalshi market poller + market universe filter** — the data foundation; nothing works without it
2. **Volume spike detector + price movement detector** — the two most computable signals from public API data; don't need per-account history
3. **Signal confidence scorer** — even a simple weighted sum is enough to start; use configurable YAML weights
4. **Per-trade hard limit + total exposure hard limit** — enforce these before any live execution is wired
5. **Copy-trade executor** — connect signal to action; test in paper trading mode first
6. **Trade log + P&L tracker** — needed immediately to know if the system is working
7. **Live dashboard** — minimal version; market list + active signals + position table + P&L total
8. **Timing-cluster detector** — add once the first two signals are stable; more complex to tune
9. **Win-streak tracker** — last, because it requires the most creative API workaround; add once baseline signals are validated

**Defer indefinitely:**
- Win-streak via per-account data — blocked by API; invest effort only if Kalshi adds a public leaderboard API
- Order book depth inspection — useful but not critical for initial signal validation
- Market metadata enrichment — adds signal accuracy but requires manual curation of resolution dates

---

## Risk Notes on Individual Features

| Feature | Risk | Mitigation |
|---------|------|------------|
| Volume spike detector | False positives on thin markets with small absolute volumes | Use relative threshold (z-score) not absolute; require minimum baseline volume before signal fires |
| Win-streak tracker | Cannot compute from public API without per-account data | Use as a secondary confirmation signal only; do not gate copy-trades on it |
| Copy-trade executor | Duplicate orders if polling loop fires twice during execution | Use idempotency key or order deduplication within a signal TTL window |
| Total exposure limit | Race condition if two signals fire simultaneously in async code | Enforce limit check as an atomic operation; check-then-place must be serialized |
| Dashboard | Stale data if poller falls behind | Show "last updated" timestamp prominently; alert visually if data is >30s stale |

---

## Sources

- Kalshi project context: `.planning/PROJECT.md`
- Domain knowledge: market microstructure, surveillance system design, algorithmic trading patterns (training knowledge, confidence MEDIUM)
- Note: WebSearch and WebFetch were unavailable during this research session. Kalshi API specifics (exact endpoint names, rate limits, available fields for trade history) should be verified against official Kalshi API documentation before implementation begins.
