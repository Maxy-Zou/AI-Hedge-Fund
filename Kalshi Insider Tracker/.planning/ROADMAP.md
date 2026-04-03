# Roadmap: Kalshi Insider Tracker

## Overview

Six phases deliver a complete automated copy-trading daemon. Phase 1 establishes the database schema and Kalshi API client — the foundation everything else reads from and writes to. Phase 2 adds the polling loop that collects live market snapshots. Phase 3 implements the first two anomaly detectors (volume spike, price movement) which are directly computable from the collected data. Phase 4 wires detection to execution with a mandatory Risk Guard before any order touches the market, starting in paper trading mode. Phase 5 ships the Streamlit monitoring dashboard. Phase 6 adds the two harder signals (timing clusters, win streak) once the core system is validated in production.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - DB schema, Kalshi API client, typed domain objects
- [ ] **Phase 2: Data Pipeline** - Polling loop ingests and persists market snapshots
- [x] **Phase 3: Core Signal Detection** - Volume spike and price movement anomaly detectors (completed 2026-04-03)
- [x] **Phase 4: Trade Execution** - Risk Guard + paper trading mode + live execution (completed 2026-04-03)
- [x] **Phase 5: Monitoring Dashboard** - Streamlit UI showing markets, signals, positions, P&L (completed 2026-04-03)
- [x] **Phase 6: Advanced Signals** - Timing cluster detector and win streak detector (completed 2026-04-03)

## Phase Details

### Phase 1: Foundation
**Goal**: The system can authenticate with Kalshi, define its schema, and represent market data as typed objects
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-03, DATA-05, LOG-03
**Success Criteria** (what must be TRUE):
  1. System authenticates with Kalshi API using RSA key-pair and receives a valid response
  2. Database schema is fully migrated (all tables exist with correct columns and constraints)
  3. System can fetch politics/policy market listings and deserialize them into typed domain objects
  4. Append-only constraint is enforced at the ORM level — no update or delete operations compile against signal/trade tables
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffold: pyproject.toml, config, logging, CLI skeleton, test stubs
- [x] 01-02-PLAN.md — DB layer: AppendOnlyMixin, ORM models (Market, MarketSnapshot, Signal, Trade), Alembic migration
- [x] 01-03-PLAN.md — Kalshi API client: RSA auth, rate limiter, politics filtering, MarketSnapshot domain type

### Phase 2: Data Pipeline
**Goal**: The system continuously collects live market snapshots and accumulates baseline data before any signals can fire
**Depends on**: Phase 1
**Requirements**: DATA-02, DATA-04, DATA-06
**Success Criteria** (what must be TRUE):
  1. Daemon polls all politics/policy markets every 5-10 seconds without missing intervals under normal conditions
  2. Each poll persists a market snapshot (price, volume, order book) to the database
  3. System enforces a warm-up period — no signals fire until baseline data has been collected for every active market
  4. Rate limiter stays within Kalshi API limits — no 429 responses during a 10-minute run
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md — Setup: add apscheduler dependency, extend AppSettings config fields, create daemon package, write RED test scaffolding
- [x] 02-02-PLAN.md — Implementation: WarmupTracker, polling job + _to_orm translator, PollingDaemon scheduler, wire CLI start command

### Phase 3: Core Signal Detection
**Goal**: The system detects volume spikes and sharp price movements and scores them with confidence values
**Depends on**: Phase 2
**Requirements**: SIG-01, SIG-02, SIG-05, SIG-06
**Success Criteria** (what must be TRUE):
  1. System computes per-market rolling volume baselines and flags snapshots that exceed the z-score threshold
  2. System detects sharp price movements (configurable % move in N seconds) relative to the market's recent range
  3. Every detected signal produces a numeric confidence score between 0 and 1
  4. System suppresses signals that fire on resolution day during the final resolution window (false positive filter active)
**Plans**: 3 plans

Plans:
- [x] 03-01-PLAN.md — Setup: install numpy + factory-boy, add SignalSettings to config.py, write 12 RED tests (6 detector + 6 engine)
- [x] 03-02-PLAN.md — Detectors: signals/ package, DetectionResult type, VolumeSpikeDetector, PriceMoveDetector (GREEN for detector tests)
- [x] 03-03-PLAN.md — Engine + wiring: SignalEngine orchestrator, resolution suppression, cooldown dedup, wire into make_poll_tick() (GREEN for all 12 tests)

### Phase 4: Trade Execution
**Goal**: Detected signals result in copy trades, with a hard Risk Guard enforcing position limits before any order reaches the market
**Depends on**: Phase 3
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-04, EXEC-05, EXEC-06, LOG-01, LOG-02
**Success Criteria** (what must be TRUE):
  1. System starts in paper trading mode — signals are logged as simulated trades without placing real orders
  2. Risk Guard rejects any order that would exceed $50 per trade or $500 total exposure, logged as a blocked trade
  3. When switched to live mode, system places real orders via Kalshi API for signals above the confidence threshold
  4. Duplicate signals from consecutive polls for the same market condition do not produce duplicate orders
  5. In-flight orders are tracked so a second detection event does not re-submit while the first order is pending
**Plans**: 3 plans
**UI hint**: no

Plans:
- [x] 04-01-PLAN.md — RED tests: 9 failing tests for RiskGuard + TradeExecutor, type contracts in types.py
- [x] 04-02-PLAN.md — Implementation: RiskGuard (hard limits as constants), TradeExecutor (paper/live dispatch) — all 9 tests GREEN
- [x] 04-03-PLAN.md — Wiring: ExecutionSettings to config.py, TradeExecutor into make_poll_tick, --live flag to CLI

### Phase 5: Monitoring Dashboard
**Goal**: Users can observe all monitored markets, live signals, open positions, and running P&L from a single screen
**Depends on**: Phase 1 (schema), Phase 4 (for meaningful data)
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04
**Success Criteria** (what must be TRUE):
  1. Dashboard displays all currently monitored politics/policy markets with their latest price and volume
  2. Dashboard shows a live feed of detected signals with type, confidence score, and timestamp, updating every ~10 seconds
  3. Dashboard shows all open positions with their current status
  4. Dashboard shows running P&L (realized + unrealized) across all trades
**Plans**: 2 plans
**UI hint**: yes

Plans:
- [x] 05-01-PLAN.md — Add streamlit+pandas deps, implement read-only query layer (4 functions)
- [x] 05-02-PLAN.md — Build 4-panel Streamlit app, wire CLI dashboard command, verify in browser

### Phase 6: Advanced Signals
**Goal**: The system detects suspicious timing clusters and win streak patterns, expanding anomaly coverage beyond Phase 3
**Depends on**: Phase 4 (live system running, signals validated in production)
**Requirements**: SIG-03, SIG-04
**Success Criteria** (what must be TRUE):
  1. System detects trades bunched in narrow windows before resolution and scores them as timing cluster signals
  2. Win streak detector is either fully functional (per-account history exposed by Kalshi API) or formally documented as infeasible with API evidence
  3. Both new signal types integrate with the existing confidence scoring and deduplication pipeline
**Plans**: 2 plans

Plans:
- [x] 06-01-PLAN.md — RED tests: 7 failing tests for TimingClusterDetector (5), WinStreakDetector stub (1), engine registration (2)
- [x] 06-02-PLAN.md — Implementation: TimingClusterDetector + WinStreakDetector stub, SignalSettings fields, engine wiring + fetch limit fix

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/3 | Planned | - |
| 2. Data Pipeline | 1/2 | In Progress|  |
| 3. Core Signal Detection | 3/3 | Complete   | 2026-04-03 |
| 4. Trade Execution | 3/3 | Complete   | 2026-04-03 |
| 5. Monitoring Dashboard | 2/2 | Complete   | 2026-04-03 |
| 6. Advanced Signals | 2/2 | Complete   | 2026-04-03 |

### Phase 06.1: Integration Wiring — Wire SignalEngine into CLI, populate markets table, fix cooldown time window, add dashboard logging (INSERTED)

**Goal:** [Urgent work - to be planned]
**Requirements**: TBD
**Depends on:** Phase 6
**Plans:** 0/0 plans complete

Plans:
- [x] TBD (run /gsd:plan-phase 06.1 to break down) (completed 2026-04-03)
