# Domain Pitfalls

**Domain:** Automated prediction market anomaly detection and copy-trading (Kalshi politics/policy markets)
**Researched:** 2026-04-02
**Confidence:** MEDIUM — training data through August 2025; web tools unavailable for verification. All Kalshi-specific API rate limits and regulatory details should be verified against current Kalshi documentation before implementation.

---

## Critical Pitfalls

Mistakes that cause rewrites, account suspension, or significant financial loss.

---

### Pitfall C-01: Treating Signal Confidence as a Binary Gate

**What goes wrong:** The system checks `if signal_confidence >= threshold: execute_trade()`. In practice the threshold is tuned on the small sample of early trades, then the market regime changes (new political event type, election cycle ends) and the calibration is wrong. The system either floods into bad trades or misses obvious signals.

**Why it happens:** Developers set a numeric threshold during initial development, observe it "works," and never revisit it. The baseline for "normal volume" in a dead market and a hot election week are completely different numbers.

**Consequences:** Correlated losses across multiple trades in the same bad regime. The $500 exposure cap gets consumed by a single bad period.

**Prevention:**
- Signal confidence should be a score with multiple components, not a single number
- Maintain a rolling baseline window (e.g., 7-day median volume per market) rather than a static historical mean
- Separate thresholds per signal type (volume spike vs. timing cluster vs. win streak) — their base rates differ
- Log the component scores alongside every trade decision for post-hoc audit

**Warning signs:**
- All signals fire simultaneously during major political events (baseline is stale)
- Zero signals for weeks even when markets are active (threshold drifted too high)
- Every trade in a 48-hour window resolves the same direction (regime correlation)

**Phase to address:** Signal detection design phase (before any auto-execution is wired)

---

### Pitfall C-02: Race Condition Between Signal Detection and Order Execution

**What goes wrong:** The poll cycle detects a signal at T=0. The trade execution logic places an order. A second poll at T=5s detects the same signal again (it hasn't cleared) and places a second order. Position doubles unintentionally.

**Why it happens:** Polling systems require explicit deduplication logic. Without a signal state machine (DETECTED → ORDER_PENDING → FILLED → EXPIRED), the same raw market condition triggers repeated orders.

**Consequences:** Exposure limit violated. Multiple orders on the same market at different price levels. The $50/trade limit becomes $50 per poll cycle for the same trade.

**Prevention:**
- Implement a signal state machine: each unique (market_id, signal_type, timestamp_window) combination has one lifecycle
- Track in-flight orders separately from the filled position. Never fire a new order for a market that has an open order
- Idempotency key on every order submission using the signal's fingerprint hash
- The execution layer must query current open orders before placing a new one

**Warning signs:**
- Database has duplicate signals for the same market within the same 30-second window
- Actual position size exceeds configured per-market limit
- Kalshi returns a duplicate order error (if they check this server-side)

**Phase to address:** Order execution layer, before auto-execution is enabled

---

### Pitfall C-03: Ignoring Kalshi Order Book Thinness — Market Impact on Entry

**What goes wrong:** The system detects a price spike and submits a market order (or aggressive limit) for $50. On a thin politics market with $500 total liquidity, a $50 order moves the price 5-10 cents. The system is copying the insider's entry price but actually entering at the post-spike price and worsening it further.

**Why it happens:** Anomaly detection systems are designed to detect unusual activity — but placing a copy trade IS unusual activity in a thin market. The system becomes the anomaly it is trying to exploit.

**Consequences:** Consistent negative slippage on every copy trade. The signal is real but the execution destroys the edge. The win rate looks good in theory but P&L is flat or negative.

**Prevention:**
- Always use limit orders, never market orders
- Cap order size relative to best-ask depth, not just absolute dollar amount
- Log the spread at time of signal detection vs. time of fill. Alert when spread exceeds 3 cents
- For very thin markets (< $200 open interest), skip or halve position sizing
- Consider a "minimum liquidity" filter: only trade markets with enough depth to absorb the order without moving price more than 1-2 cents

**Warning signs:**
- Average fill price is consistently 2+ cents worse than the signal detection price
- Markets where signals fire have very low total volume/open interest
- Multiple unfilled limit orders sitting at stale prices

**Phase to address:** Order execution design, before live trading; revisit during P&L review phase

---

### Pitfall C-04: Win Streak Detection Counting Platform Bots/Market Makers as Insiders

**What goes wrong:** The win streak heuristic tracks accounts that bet correctly many times in a row. On thin politics markets, market makers and bots that are constantly quoting both sides will have natural win streaks on one side simply due to mean-reversion mechanics. The system generates constant false-positive signals on these accounts.

**Why it happens:** Win streak detection without accounting for position size, time-to-resolution, and whether the account was quoting both sides simultaneously is nearly always misleading. A $1 correct bet 10 times in a row looks the same as a $50 correct bet 10 times.

**Consequences:** High false positive rate on win streak signal type. If the system auto-executes, it copies market-maker hedging behavior and loses money systematically. Detection quality degrades trust in all signals.

**Prevention:**
- Weight win streaks by position size, not just count (a $1 win is noise)
- Require that the "win" was directional and early — not within the last 1-2 hours before resolution (market maker convergence)
- Filter accounts with high two-sided trading activity (long and short on same market) — these are market makers
- Minimum position size threshold to count a "streak entry" (e.g., $10 minimum)
- Confidence decay: a streak that ends on a resolution >90% priced is less impressive than one at 50%

**Warning signs:**
- Win streak signals fire on accounts you know are active on both sides
- Win streak accounts have small average position sizes (< $5)
- Signals cluster around markets nearing resolution (>85% price)

**Phase to address:** Win streak signal implementation

---

### Pitfall C-05: Regulatory / Account Risk from Automated Trading Patterns

**What goes wrong:** Kalshi, as a CFTC-regulated exchange, has terms of service that may prohibit or restrict certain automated trading behaviors, including systematic copy-trading, front-running detected order flow, or patterns that constitute market manipulation. The account gets suspended or funds frozen.

**Why it happens:** Prediction market operators face regulatory scrutiny and may flag accounts that show unusual automated patterns — consistent high-frequency polling, always entering after another specific account moves, or patterns that correlate with political insider activity (which is itself an edge case under CFTC commodity law).

**Consequences:** Account suspension with funds in limbo. Regulatory inquiry. Potential legal exposure if the copied trades were themselves insider trading (copying an insider may not shield you legally).

**Prevention:**
- Read and re-read Kalshi's Terms of Service, specifically automated trading and copy-trading clauses
- Verify with Kalshi support (email) whether the planned system complies before building
- Never reference specific tracked accounts in system logs in a way that implies you are front-running them
- Rate-limit API polling to the stated allowed rate — do not exceed it even if technically possible
- Keep position sizes conservative (the $50/$500 caps already help here)
- The system should be framed as "anomaly-driven signal detection" not "copy-trading"
- Consult a CFTC-knowledgeable attorney before deploying with real capital — LOW confidence on legal exposure specifics

**Warning signs:**
- Kalshi support contacts you proactively
- API keys stop working or return 403s without explanation
- Kalshi adds ToS language about automated trading in a platform update

**Phase to address:** Pre-build research phase; revisit before enabling live execution

---

### Pitfall C-06: Hard Position Limits Enforced Only in Config, Not Code

**What goes wrong:** The $50/trade and $500/total limits are stored as config values. During development or testing, a developer changes them temporarily. The test environment executes against the real Kalshi account. Limits are no longer enforced at the execution level — only at the config-read level.

**Why it happens:** Risk limits treated as "preferences" rather than hard constraints baked into the execution layer. This is the most common risk management failure in automated trading systems.

**Consequences:** Single oversized position or runaway loop could exhaust the account or exceed the $500 total exposure. With auto-execution, there is no human to stop it.

**Prevention:**
- Implement position limits as invariants enforced in code, not config reads
- The order submission function must query current positions from the database before every order — not rely on an in-memory counter
- `assert total_exposure + new_order_size <= MAX_TOTAL_EXPOSURE` as a hard check before every API call
- MAX_TOTAL_EXPOSURE and MAX_TRADE_SIZE are module-level constants in the execution module, not loaded from config
- Separate "soft limit" (configurable) from "hard ceiling" (immutable constant), and both must pass

**Warning signs:**
- Risk limit constants are in a `.env` file or `config.yaml`
- The execution function accepts an order without checking current positions
- Test code uses different limit values

**Phase to address:** Order execution layer design — enforce before any live trading

---

## Moderate Pitfalls

---

### Pitfall M-01: Polling Interval vs. Signal Staleness Mismatch

**What goes wrong:** 5-10 second polling is too slow for certain signal types. A timing cluster (10 trades in 60 seconds) looks very different when you poll every 10 seconds vs. every 2 seconds — you may see only the tail of the cluster and misclassify the pattern. Conversely, volume spike detection at 5-second intervals can double-count the same spike across two polls.

**Prevention:**
- Design signal detection to operate on a rolling time window, not point-in-time snapshot
- Volume spike: compare 5-minute rolling volume to 1-hour baseline, not current poll vs. last poll
- Timing cluster: maintain an event buffer of last N trades with timestamps, not just current poll's trades
- Document the minimum meaningful polling interval for each signal type separately

**Phase to address:** Signal detection design

---

### Pitfall M-02: Overfitting Signal Thresholds to Initial Observation Period

**What goes wrong:** The system is tuned during a major election cycle (peak activity, clear signals) and then deployed during a quiet period. All thresholds are too sensitive. Alternatively: tuned during a quiet period, deployed during elections — all thresholds are too conservative and miss obvious signals.

**Prevention:**
- Parameterize all thresholds clearly and document what market conditions they were tuned under
- Use relative thresholds (X standard deviations above rolling mean) not absolute numbers
- Plan for a "threshold review" milestone after 30 and 90 days of live operation
- Build in configurable sensitivity presets: conservative/normal/aggressive, with clear documentation on when each applies

**Phase to address:** Signal tuning phase; revisit in ongoing operations

---

### Pitfall M-03: Conflating "Market Open Interest" with "Liquidity"

**What goes wrong:** A market shows $10,000 in open interest (total bets placed historically) but the current order book depth at current price is $50. The system treats the market as liquid based on open interest and submits a full $50 order, which dominates the book.

**Prevention:**
- Use real-time order book depth at current price level (best bid/ask size), not open interest or total volume
- Define "liquid enough to trade" as: ask depth >= 2x order size at current price level
- Kalshi API provides order book snapshots — always query this before sizing an order

**Phase to address:** Order execution design

---

### Pitfall M-04: Signal Generation Without Baseline Initialization

**What goes wrong:** The system starts fresh with no historical baseline. On the first poll, every market looks anomalous because there is no baseline to compare against. The system fires signals and trades immediately on startup.

**Prevention:**
- Require a "warm-up period" before enabling auto-execution: collect N polls of baseline data first
- Use a `WARMING_UP` system state that disables execution for the first 30-60 minutes after startup
- Persist baselines to the database so restarts do not require full re-warm

**Phase to address:** System startup and initialization design

---

### Pitfall M-05: API Error Handling — Treating Transient Failures as Trade Confirmations

**What goes wrong:** The order submission gets a network timeout. The system assumes the order failed, retries, and places a duplicate order. But the original order was accepted and is now pending. Result: double position.

**Prevention:**
- On order submission, always request an order ID from Kalshi before treating it as placed
- On timeout, query open orders before retrying — never assume timeout = failure
- Implement idempotency: generate a client_order_id before submission, check if it exists before resubmitting
- Kalshi API may support a `client_order_id` parameter — use it if available (verify in docs)

**Phase to address:** Order execution layer

---

### Pitfall M-06: Database as Single Source of Truth for Position State Drifts from Kalshi

**What goes wrong:** The local database says position X is open. Kalshi actually settled the market and the position resolved hours ago (system was down during resolution). The local exposure counter is wrong. Next signal fires, system thinks exposure is near limit when it's actually $0.

**Prevention:**
- On every startup and periodically (every 60 seconds), reconcile local position state against Kalshi's account positions endpoint
- Never trust only the local database for exposure calculations — always verify against Kalshi API
- Build a reconciliation loop: `db_positions XOR kalshi_positions` alerts on mismatches

**Phase to address:** Position tracking design

---

### Pitfall M-07: Timing Cluster Signal Fires on Scheduled Resolution Events

**What goes wrong:** Every Kalshi politics market has a scheduled resolution time (e.g., "Will X happen by January 20th?"). As the resolution time approaches, many bettors rush to close or open positions in the final hours. This creates a "timing cluster" that looks exactly like insider behavior but is just normal resolution-day activity.

**Prevention:**
- Add a `time_to_resolution` filter: suppress timing cluster signals when resolution is < 2 hours away
- Track resolution timestamps for every monitored market; this should be a first-class field in the schema
- Volume spike signals should also decay sensitivity as resolution approaches (everyone piles in at end)

**Phase to address:** Signal detection design

---

## Minor Pitfalls

---

### Pitfall Mi-01: Dashboard State Out of Sync with Execution State

**What goes wrong:** The dashboard shows "no active positions" but the execution engine has open orders. The database write for the position succeeded, but the dashboard query is stale or caching. A developer sees "no positions" and manually places a trade, doubling exposure.

**Prevention:**
- Dashboard must always read from live database state, no in-memory caching for position data
- Use a clearly visible "last refreshed" timestamp on the dashboard
- Position display should include both filled positions AND pending orders

**Phase to address:** Dashboard implementation

---

### Pitfall Mi-02: Logging Signal Data Without the Reasoning

**What goes wrong:** A signal fires, a trade executes, the trade loses. The log says "signal fired: volume_spike, market X." Post-mortem is impossible because the log doesn't capture the actual numbers: what was the spike magnitude, what was the baseline, what were the contributing factors.

**Prevention:**
- Log every signal with its full component scores, not just the final confidence value
- Log the market state snapshot (price, volume, order book depth) at the time of signal detection
- This data is invaluable for tuning thresholds and evaluating the detection model post-hoc

**Phase to address:** Logging design, should be done from day one

---

### Pitfall Mi-03: Kalshi API Version Changes Breaking Production

**What goes wrong:** Kalshi updates their API (they have done breaking changes before). The system silently breaks — orders fail, polls return unexpected schemas. No alert fires because the system doesn't validate API responses against an expected schema.

**Prevention:**
- Validate every Kalshi API response with Pydantic models before processing
- Fail loudly (alert and halt auto-execution) on schema validation errors — do not silently skip
- Pin to a specific API version in all requests if Kalshi supports versioned endpoints
- Subscribe to Kalshi developer announcements/changelog

**Phase to address:** API client implementation

---

### Pitfall Mi-04: Running Multiple Instances of the System Simultaneously

**What goes wrong:** Developer has two terminal sessions running. Both are polling and detecting signals. Both submit orders for the same signal. Exposure doubles.

**Prevention:**
- Implement a process lock (file lock or database flag) that prevents two instances from running simultaneously
- Alert loudly on startup if another instance is detected
- Keep this simple: a `running.lock` file with PID is sufficient

**Phase to address:** System infrastructure

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| API client setup | Rate limit violations causing 429 bans | Implement retry with exponential backoff from day one; track requests per minute |
| Signal detection | Fires on resolution-day noise (Pitfall M-07) | Always check time-to-resolution before emitting signal |
| Win streak detection | False positives on market makers (Pitfall C-04) | Weight by position size and filter two-sided accounts |
| Order execution | Duplicate orders from retry logic (Pitfall M-05) | Use client_order_id + pre-submission open-order check |
| Risk limits | Config-only enforcement (Pitfall C-06) | Hard constants in code, not config |
| Position tracking | State drift from Kalshi (Pitfall M-06) | Reconciliation loop every 60 seconds |
| Live auto-execution | Regulatory exposure (Pitfall C-05) | Verify ToS compliance before enabling |
| Dashboard | Stale position display (Pitfall Mi-01) | Always read from live DB, show last-refreshed timestamp |
| First deployment | No baseline data causes immediate signal flood (Pitfall M-04) | Mandatory warm-up period before execution enabled |
| Production operations | API schema changes break silently (Pitfall Mi-03) | Pydantic validation on every response, fail loudly |

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Race conditions / execution logic | HIGH | General automated trading system engineering; applies directly |
| Market impact / order book thinness | HIGH | Well-documented in thin-market trading literature |
| False positive patterns (market makers, resolution-day) | HIGH | Predictable from market structure; domain knowledge |
| Kalshi-specific API rate limits | LOW | Cannot verify without current Kalshi docs; must check before building |
| Kalshi ToS on automated/copy-trading | LOW | Cannot verify current ToS text; MUST verify before deploying capital |
| CFTC legal exposure for copy-trading | LOW | Requires legal counsel; training data insufficient for definitive claim |
| Win streak detection mechanics | MEDIUM | General statistics; Kalshi-specific account visibility may differ from assumption |

---

## Open Questions Requiring Verification

1. **Does Kalshi expose per-account trading history publicly?** The win streak signal assumes you can see which accounts placed trades and their history. Kalshi may anonymize this in their public API — if so, win streak detection is not feasible as designed.

2. **What are the current Kalshi API rate limits?** Polling at 5-10 seconds across N markets = N/5 to N/10 requests per second. This needs to be validated against the actual limits before the polling architecture is finalized.

3. **Does Kalshi support `client_order_id` for idempotent order submission?** This is the cleanest solution for Pitfall M-05 but requires API support.

4. **Are there Kalshi ToS restrictions on automated trading, copy-trading, or polling frequency?** This is a critical legal/compliance question that should be answered before any capital is deployed.

5. **Does Kalshi provide WebSocket order book feeds?** Even if polling is chosen for simplicity, knowing WebSocket is available means it can be used selectively for order book depth queries without switching the whole architecture.

---

## Sources

- Kalshi PROJECT.md (project requirements and constraints)
- Training data: Automated trading system design patterns (HIGH confidence, general domain)
- Training data: Thin-market execution mechanics (HIGH confidence, general domain)
- Training data: Kalshi CFTC regulatory status as of August 2025 (MEDIUM confidence; verify current status)
- Training data: Prediction market mechanics and market maker behavior (HIGH confidence)
- Kalshi API documentation: NOT verified (web fetch unavailable) — all Kalshi-specific claims marked LOW confidence
