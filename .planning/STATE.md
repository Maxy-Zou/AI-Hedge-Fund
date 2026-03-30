---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Live End-to-End Pipeline
status: roadmap_created
stopped_at: null
last_updated: "2026-03-29T00:00:00.000Z"
last_activity: 2026-03-29
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-29)

**Core value:** Produce compelling, realistic backtest results the moment any strategy signal is ready — so investor conversations can start immediately.
**Current focus:** Phase 9 — Infrastructure and Database Setup

## Current Position

Phase: 9 — Infrastructure and Database Setup
Plan: —
Status: Not started
Last activity: 2026-03-29 — Roadmap created for v1.1

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

**v1.0 Velocity Reference:**
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
| Phase 05-risk-metrics-engine P01 | 5min | 2 tasks | 7 files |
| Phase 05-risk-metrics-engine P02 | 4min | 2 tasks | 3 files |
| Phase 06-streamlit-dashboard P01 | 210min | 2 tasks | 6 files |
| Phase 06-streamlit-dashboard P02 | 15min | 2 tasks | 1 files |
| Phase 06-streamlit-dashboard P03 | 1min | 2 tasks | 1 files |
| Phase 07-tearsheet-and-data-exports P01 | 3min | 2 tasks | 5 files |
| Phase 07 P02 | 13min | 2 tasks | 3 files |
| Phase 08-ai-washing-detector-integration P01 | 1min | 2 tasks | 3 files |
| Phase 08-ai-washing-detector-integration P02 | 5min | 2 tasks | 3 files |

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
- [Phase 05-risk-metrics-engine]: arbitrary_types_allowed=True in MetricsBundle model_config for pd.Series fields (mirrors PortfolioResult pattern)
- [Phase 05-risk-metrics-engine]: max_drawdown stored as negative float; periods=252 constant enforced via _TRADING_DAYS_PER_YEAR to avoid 20% Sharpe inflation from qs default 365
- [Phase 05-risk-metrics-engine]: alpha=0.0 and beta=0.0 default when benchmark=None
- [Phase 05-risk-metrics-engine]: qs.stats.greeks() guarded against near-zero benchmark variance (< 1e-12): returns alpha=0.0, beta=0.0 to avoid numerical instability from division-by-near-zero
- [Phase 05-risk-metrics-engine]: win_loss_ratio guarded with math.isfinite(): returns 0.0 when no losing days exist (avoids non-finite float in frozen MetricsBundle)
- [Phase 06-streamlit-dashboard]: streamlit>=1.50.0 declares pandas<3 conflicting with project pandas>=3.0.1; resolved via tool.uv.override-dependencies and POSIX-only environments restriction
- [Phase 06-streamlit-dashboard]: plotly added as core dep; streamlit installed via uv pip with pandas override — cannot be in lockfile without conflict
- [Phase 06-streamlit-dashboard]: ME resample alias used (not M) — required for pandas 3.x month-end compatibility
- [Phase 06-streamlit-dashboard]: _annotate_drawdown_episodes handles open-ended trailing episodes (no closing transition at end of series)
- [Phase 06-streamlit-dashboard]: width="stretch" used for all st.plotly_chart calls (Streamlit 1.45+ API; use_container_width deprecated and absent)
- [Phase 06-streamlit-dashboard]: Benchmark fetch (SPY/IWM) gracefully degrades to empty dict — equity chart renders strategy-only on yfinance failure
- [Phase 07-tearsheet-and-data-exports]: Matplotlib Agg backend guarded with get_backend() != 'Agg' check before use() call to avoid double-switching when already set
- [Phase 07-tearsheet-and-data-exports]: Rolling Series fields excluded from JSON by explicit key enumeration (not model_dump) for type safety
- [Phase 07-tearsheet-and-data-exports]: export command placed directly on backtest_app (not nested sub-typer) — Typer sub-typer requires extra command level incompatible with test invocation pattern
- [Phase 07-tearsheet-and-data-exports]: dashboard/app.py added to coverage omit — Streamlit UI cannot be unit-tested; 5 data-command error-path tests added to reach 80% coverage
- [Phase 08-ai-washing-detector-integration]: DB-as-integration-boundary: AiWashingLoader uses sqlalchemy.text() raw SQL — no cross-package imports from ai_washer; database is the only coupling point
- [Phase 08-ai-washing-detector-integration]: pivot_table(aggfunc='last') deduplication in AiWashingLoader — most recently inserted row wins when multiple scores share (ticker, date)
- [Phase 08-ai-washing-detector-integration]: Signal guard before load_app_settings(): unknown signal exits 1 without requiring DATABASE_URL env var
- [Phase 08-ai-washing-detector-integration]: Module-level imports for AiWashingLoader/PortfolioSimulator/MetricsEngine in cli.py: required for unittest.mock.patch to target fund_backtest.cli.* namespace
- [v1.1 Roadmap]: FIX-01 and INFRA-03 are the same fix (Alembic version_table) — both mapped to Phase 9 so the fix is authoritatively done once before any migration run
- [v1.1 Roadmap]: Phase 12 (Bug Fixes) can execute concurrently with Phase 11 (Detector run) since Detector is 4-10h and fixes touch only backtest code, not Detector internals
- [v1.1 Roadmap]: Docker Compose placed at repo root — shared volume between both packages; named volume prevents data loss on docker system prune

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 9: Alembic version table collision must be fixed before running either migration chain — INFRA-03/FIX-01 are the hard prerequisite
- Phase 10: yfinance 429 errors likely on first bulk download of 200-500 tickers — verify batch_sleep_secs=3.0 is configured before starting
- Phase 10: AI_WASHER_EDGAR_IDENTITY must be a valid email in User-Agent format for SEC EDGAR compliance
- Phase 11: First Detector run against real SEC filings takes 4-10 hours due to rate limits — plan to run overnight or in background
- Phase 11/12 parallel: Phase 12 bug fixes are safe to develop while Phase 11 executes, but merge/test against real scores only after Phase 11 completes
- Phase 13: SignalAdapter.min_coverage=5 requires at least 5 ticker overlap between ai_washer companies and fund_backtest universe — verify in Phase 10 before proceeding

## Session Continuity

Last session: 2026-03-29
Stopped at: Roadmap created for v1.1 — ready to plan Phase 9
Resume file: None
