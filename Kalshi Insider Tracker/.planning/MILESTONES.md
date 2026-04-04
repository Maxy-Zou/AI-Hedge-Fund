# Milestones

## v1.0 Kalshi Insider Tracker MVP (Shipped: 2026-04-04)

**Phases completed:** 7 phases, 15 plans, 21 tasks

**Key accomplishments:**

- One-liner:
- 1. [Rule 2 - Missing Dependency] cryptography package not in pyproject.toml
- APScheduler dependency added, AppSettings extended with polling config fields (poll_interval_seconds, warmup_snapshots), daemon package skeleton created, and 10 RED TDD tests written for WarmupTracker and polling job contracts
- APScheduler-based polling daemon implemented: WarmupTracker, make_poll_tick factory, _to_orm translator, PollingDaemon scheduler wrapper, and CLI start command fully wired — all 10 RED tests from Plan 01 turned GREEN
- One-liner:
- One-liner:
- One-liner:
- One-liner:
- One-liner:
- One-liner:
- One-liner:
- 4-panel Streamlit dashboard (Markets/Signals/Positions/P&L tabs) with 10s auto-refresh and `kalshi-tracker dashboard` CLI command wired via subprocess
- One-liner:
- Burst volume concentration detector (SIG-03) using consecutive-delta concentration ratio, plus WinStreakDetector infeasibility stub (SIG-04) — all 7 Phase 6 RED tests turned GREEN

---
