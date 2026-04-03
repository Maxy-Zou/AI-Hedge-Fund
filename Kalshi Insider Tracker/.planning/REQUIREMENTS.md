# Requirements: Kalshi Insider Tracker

**Defined:** 2026-04-02
**Core Value:** Detect and copy insider-like trades on Kalshi politics/policy markets before the event resolves

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Data Infrastructure

- [x] **DATA-01**: System authenticates with Kalshi API using API key/RSA key pair
- [x] **DATA-02**: System polls Kalshi API every 5-10 seconds for market data
- [x] **DATA-03**: System filters to politics/policy markets only, ignoring other categories
- [x] **DATA-04**: System persists market snapshots (price, volume, order book) to database on each poll
- [x] **DATA-05**: System enforces Kalshi API rate limits (conservative default, tunable from observations)
- [x] **DATA-06**: System collects baseline data during warm-up period before any signals fire

### Signal Detection

- [x] **SIG-01**: System detects abnormal volume spikes relative to per-market rolling baseline
- [x] **SIG-02**: System detects sharp price movements before event resolution
- [ ] **SIG-03**: System detects suspicious timing clusters (trades bunched before resolution)
- [ ] **SIG-04**: System detects accounts/patterns with unusual win streaks (subject to API feasibility)
- [x] **SIG-05**: Each signal produces a confidence score used for threshold-based triggering
- [x] **SIG-06**: System suppresses signals during normal resolution-day activity (false positive filter)

### Trade Execution

- [x] **EXEC-01**: System operates in paper trading mode (simulated trades, no real capital)
- [x] **EXEC-02**: System auto-executes real copy trades via Kalshi API when signals exceed threshold
- [x] **EXEC-03**: System enforces $50 per-trade limit as a code-level constant (not config)
- [x] **EXEC-04**: System enforces $500 total exposure limit as a code-level constant (not config)
- [x] **EXEC-05**: System deduplicates signals to prevent duplicate orders from consecutive polls
- [x] **EXEC-06**: System tracks in-flight orders to prevent race conditions between detection and execution

### Monitoring Dashboard

- [ ] **DASH-01**: Dashboard shows live view of all monitored politics/policy markets
- [ ] **DASH-02**: Dashboard shows real-time feed of detected signals with confidence scores
- [ ] **DASH-03**: Dashboard shows current open positions and their status
- [ ] **DASH-04**: Dashboard shows running P&L across all trades (realized + unrealized)

### Persistence & Logging

- [ ] **LOG-01**: System logs every detected signal (market, type, confidence, timestamp) to database
- [x] **LOG-02**: System logs every trade placed (market, direction, size, price, outcome) to database
- [x] **LOG-03**: All signal and trade data is append-only (never updated or deleted)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Expansion

- **EXP-01**: Monitor additional market categories (economics, weather, sports)
- **EXP-02**: Push notifications (Slack, SMS, email) when signals fire
- **EXP-03**: Multi-account support for diversified execution
- **EXP-04**: Adaptive threshold tuning based on historical signal performance

### Advanced Signals

- **ADV-01**: Machine learning model for signal scoring (replace/augment z-score thresholds)
- **ADV-02**: Cross-market correlation detection (coordinated activity across related markets)

## Out of Scope

| Feature | Reason |
|---------|--------|
| WebSocket streaming | Polling every 5-10s is sufficient for politics markets; WebSocket adds complexity for no gain |
| Per-account web scraping | Likely violates Kalshi ToS; fragile; prefer public API data only |
| Automatic threshold tuning | Overfitting risk on unvalidated signals; manual tuning in v1 |
| Backtesting | Shared backtest module in parent project handles this |
| Non-politics markets | Focusing where insider info is most actionable for v1 |
| Mobile app | Dashboard-first approach; mobile is premature |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 2 | Complete |
| DATA-03 | Phase 1 | Complete |
| DATA-04 | Phase 2 | Complete |
| DATA-05 | Phase 1 | Complete |
| DATA-06 | Phase 2 | Complete |
| SIG-01 | Phase 3 | Complete |
| SIG-02 | Phase 3 | Complete |
| SIG-03 | Phase 6 | Pending |
| SIG-04 | Phase 6 | Pending |
| SIG-05 | Phase 3 | Complete |
| SIG-06 | Phase 3 | Complete |
| EXEC-01 | Phase 4 | Complete |
| EXEC-02 | Phase 4 | Complete |
| EXEC-03 | Phase 4 | Complete |
| EXEC-04 | Phase 4 | Complete |
| EXEC-05 | Phase 4 | Complete |
| EXEC-06 | Phase 4 | Complete |
| DASH-01 | Phase 5 | Pending |
| DASH-02 | Phase 5 | Pending |
| DASH-03 | Phase 5 | Pending |
| DASH-04 | Phase 5 | Pending |
| LOG-01 | Phase 4 | Pending |
| LOG-02 | Phase 4 | Complete |
| LOG-03 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0

---
*Requirements defined: 2026-04-02*
*Last updated: 2026-04-02 — traceability filled after roadmap creation*
