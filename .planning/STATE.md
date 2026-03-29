---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: Completed 04-cost-model-and-portfolio-simulator 04-02-PLAN.md
last_updated: "2026-03-29T09:18:43.384Z"
last_activity: 2026-03-29
progress:
  total_phases: 8
  completed_phases: 4
  total_plans: 11
  completed_plans: 11
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-28)

**Core value:** Produce compelling, realistic backtest results the moment any strategy signal is ready — so investor conversations can start immediately.
**Current focus:** Phase 04 — cost-model-and-portfolio-simulator

## Current Position

Phase: 04 (cost-model-and-portfolio-simulator) — EXECUTING
Plan: 2 of 2
Status: Phase complete — ready for verification
Last activity: 2026-03-29

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: none yet
- Trend: -

*Updated after each plan completion*
| Phase 01-universe-and-sector-data P01 | 5 | 2 tasks | 19 files |
| Phase 01-universe-and-sector-data P02 | 5 | 2 tasks | 7 files |
| Phase 01-universe-and-sector-data P03 | 7 | 2 tasks | 5 files |
| Phase 02-price-data-pipeline P01 | 22 | 2 tasks | 6 files |
| Phase 02-price-data-pipeline P02 | 3 | 2 tasks | 4 files |
| Phase 02-price-data-pipeline P03 | 3 | 2 tasks | 2 files |
| Phase 02-price-data-pipeline P04 | 4 | 2 tasks | 3 files |
| Phase 03 P01 | 2 | 2 tasks | 5 files |
| Phase 03 P02 | 5 | 2 tasks | 2 files |
| Phase 04-cost-model-and-portfolio-simulator P01 | 316 | 2 tasks | 5 files |
| Phase 04-cost-model-and-portfolio-simulator P02 | 8 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Vectorized backtesting via vectorbt; quantstats-lumi for risk metrics; Streamlit for dashboard
- Roadmap: Signal Adapter decouples AI Washing Detector from backtester via typed SignalFrame contract
- Roadmap: Phase 3 (Signal Adapter) can run in parallel with Phase 2 — both depend only on Phase 1
- [Phase 01-universe-and-sector-data]: fund-backtest is completely independent from ai_washer — zero cross-package imports
- [Phase 01-universe-and-sector-data]: market_cap_cents stored as BigInteger (cents not dollars) across all fund-backtest models
- [Phase 01-universe-and-sector-data]: TimestampMixin for mutable entities; append-only snapshot tables have no updated_at
- [Phase 01-universe-and-sector-data]: SQLite test fixture creates only universe_tickers table — universe_snapshots uses JSONB which SQLite does not support
- [Phase 01-universe-and-sector-data]: Wikipedia GICS sector takes precedence over yfinance sector in build_universe_entry()
- [Phase 01-universe-and-sector-data]: dry-run defers load_app_settings() until after early return — no DATABASE_URL required for preview
- [Phase 01-universe-and-sector-data]: testcontainers URL uses psycopg2 by default; replaced with psycopg (v3) in db_engine fixture
- [Phase 01-universe-and-sector-data]: Coverage omit: migrations/* and __main__.py excluded from pytest-cov; 92% actual coverage on testable code
- [Phase 02-price-data-pipeline]: PriceBarORM is append-only: no TimestampMixin (no updated_at), created_at added directly
- [Phase 02-price-data-pipeline]: price_to_cents uses round() not int() — prevents floating-point truncation (10.009*100=1000.9 -> 1001)
- [Phase 02-price-data-pipeline]: PriceAnomalyRecord anomaly_type is Literal['return_spike_plus','return_spike_minus'] — closed set prevents drift
- [Phase 02-price-data-pipeline]: Tenacity wait patched via retry.wait=lambda:0 in tests to avoid sleeping while testing real retry behavior through the live decorator
- [Phase 02-price-data-pipeline]: YFRateLimitError() takes no constructor args — instantiate without message string
- [Phase 02-price-data-pipeline]: detect_gaps uses bdate_range(inclusive='neither') to count only missing business days between two dates
- [Phase 02-price-data-pipeline]: tuple_() for anomaly exclusion in get_bars(): NOT ((ticker, bar_date) IN subquery) — per-bar exclusion not per-ticker
- [Phase 02-price-data-pipeline]: PriceBuilder.update() groups tickers by start_date before download_in_chunks() to minimise API calls on daily cadence
- [Phase 02-price-data-pipeline]: RETURNING clause for pg_insert rowcount: use .returning(id) + len(result.all()); psycopg3 returns -1 for ON CONFLICT DO NOTHING without RETURNING
- [Phase 02-price-data-pipeline]: autouse DELETE fixture for integration test isolation: compensates for explicit session.commit() inside repository methods preventing conftest rollback cleanup
- [Phase 03]: SignalFrame/WeightFrame are pd.DataFrame type aliases with docstring contracts; validate_signal_frame() enforces the contract at adapter boundary
- [Phase 03]: All-NaN columns warn (do not raise) in validate_signal_frame(); adapter drops them downstream
- [Phase 03]: SignalAdapterConfig min_coverage=5, gross_exposure_limit=1.0 — mirrors PriceSettings BaseModel pattern
- [Phase 03]: shift(1) is the final step in SignalAdapter.adapt() — Phase 4 Portfolio Simulator must NOT apply an additional shift
- [Phase 03]: Test fixture min_coverage override: 4-ticker fixture requires min_coverage=1 override in tests that isolate shift/weight behavior from coverage logic
- [Phase 04-cost-model-and-portfolio-simulator]: CostConfig defaults: slippage=10bps, commission=5bps, borrow=50bps/yr — flat-rate borrow, tiered is future
- [Phase 04-cost-model-and-portfolio-simulator]: load_cost_config() reads from 'cost' YAML key, consistent with load_signal_adapter_config() pattern
- [Phase 04-cost-model-and-portfolio-simulator]: future_stack=True does not drop NaN in pandas 2.x — must call .dropna() explicitly after stack()
- [Phase 04-cost-model-and-portfolio-simulator]: Entry trades captured by fillna(0.0) before diff() — weight_before=0 for first non-NaN position

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2: FINRA short interest data ingestion pipeline for tiered borrow cost model not yet researched — address in Phase 4 planning
- Phase 2: Dividend liability on shorts — yfinance coverage inconsistent for historical periods; document as known limitation in tearsheet
- Phase 6/7: WeasyPrint (CSS PDF) requires Pango/Cairo on Linux CI — use matplotlib PdfPages for v1 PDF instead

## Session Continuity

Last session: 2026-03-29T09:18:43.381Z
Stopped at: Completed 04-cost-model-and-portfolio-simulator 04-02-PLAN.md
Resume file: None
