# Progress

## 2026-04-22 — Phase 6 Plan 02: Portfolio Data Layer

- **PortfolioPosition** (`src/ai_hedge_fund/db/models.py`): append-only SQLAlchemy model on `Base + DualTimestampMixin` with `UniqueConstraint(ticker, as_of_date)`; mirrors the DailyPrice pattern for financial-time-series persistence
- **Alembic 002** (`alembic/versions/002_create_portfolio_positions.py`): creates `portfolio_positions` table with index on ticker and the unique constraint; `down_revision = "001"`
- **PortfolioSnapshot + loader** (`src/ai_hedge_fund/risk/portfolio.py`): frozen Pydantic models (`PortfolioSnapshot`, `PortfolioSnapshotPosition`); `load_portfolio(db_session, as_of_date)` filters by `as_of_date <= target` (Pitfall 2 temporal correctness) and collapses to latest row per ticker; `seed_portfolio_from_csv` writes one row per CSV record with a shared as_of_date
- **CSV fixture** (`tests/risk/fixtures/portfolio_sample.csv`): 5 positions across 4 sectors (Technology x2, Healthcare, Financials, Consumer Staples) for concentration-test variation
- **Tests added:** 12 (4 model + 8 loader); test count now 30 in `tests/risk/` alongside 06-01's schema tests

## 2026-04-22 — Phase 5 Complete: Adversarial Critique

- **Debate schemas** (`src/ai_hedge_fund/schemas/debate.py`): 8 Pydantic models (BullClaim, BullCase, BearClaim, BearCase, RebuttalPoint, RebuttalAct, FinalArguments, DebateSynthesis) with `min_length`/`ge/le`/`Literal` constraints enforcing the 5-act protocol; `BearCase` model_validator enforces addressed_bull_claims ↔ BearClaim.addresses_bull_claim cross-link
- **5 adversarial agents** (`src/ai_hedge_fund/agents/{bull,bear,rebuttal,final_arguments,debate_synthesis}.py`): all REASONING tier (Opus), zero tools, retries=2; rebuttal + final_arguments use `output_override=8_000` cost guardrail; synthesis uses default REASONING cap
- **Pure-function quality score** (`src/ai_hedge_fund/agents/debate_synthesis.py::compute_quality_score`): weighted mean over evidence/logic/risk (0.4/0.3/0.3 module constants); CLAUDE.md tool-first enforcement
- **5 async debate nodes + pipeline** (`src/ai_hedge_fund/graph/{nodes.py,pipeline.py}`): `build_debate_pipeline` sequential chain (manager→bull→bear→rebuttal→final→synthesis→signal); no manager→signal diamond (Pitfall 4 avoided); `debate_synthesis_node` overwrites LLM quality_score + pre_debate_confidence via `model_copy(update=...)`
- **DebatePipelineState** TypedDict (single-writer debate fields, NO operator.add reducer, contract-tested)
- **Phase 4 pipeline unchanged** (byte-for-byte guarantee, `TestPhase4PipelineStillWorks` enforces)
- **Test count: +107 new tests** (472 → 578 unit tests passing, 0 regressions). 4 new integration tests for the 10-agent end-to-end debate flow.
- **Code review**: 0 critical, 3 warnings auto-fixed (BearCase cross-link validator, NonEmptyStr element constraint, explicit thesis precondition in debate_synthesis_node), 5 info items deferred as tech debt
- **Human UAT deferred**: 5 items requiring real Anthropic API + Langfuse (30%-of-runs confidence delta, semantic rebuttal alignment, sycophancy audit, per-debate token cost, Langfuse trace audit) persisted to `05-HUMAN-UAT.md`
- Files: `05-CONTEXT.md`, `05-RESEARCH.md`, `05-PATTERNS.md`, `05-VALIDATION.md`, `05-01/02/03-PLAN.md`, `05-01/02/03-SUMMARY.md`, `05-REVIEW.md`, `05-REVIEW-FIX.md`, `05-VERIFICATION.md`, `05-HUMAN-UAT.md`
- Milestone v1.0 progress: 5/8 phases complete

## 2026-03-27 — Project Setup

- Initialized git repo
- Created top-level `CLAUDE.md` with project conventions
- Created `.gitignore` (Python, data files, env, IDE)
- Created `docs/PROGRESS.md`
- Existing: `Al Washing Detector/` subfolder with research doc

## 2026-03-28 to 2026-04-06 — Strategy Development (archived)

- Built AI Washing Detector: SEC EDGAR ingestion, entity resolution, FinBERT NLP scoring, 11-table PostgreSQL schema, Prefect pipeline, 66 tests
- Built Kalshi Insider Tracker: real-time Kalshi polling, anomaly detection (volume/price/timing), APScheduler daemon, Streamlit dashboard, 12 tests
- Built fund-backtest: vectorized equity backtester, yfinance OHLCV ingestion, SignalAdapter pattern, Streamlit dashboard, quantstats metrics
- Built kalshi-backtest: Protocol-based strategy interface, DuckDB storage, Kalshi API historical data ingestion, binary contract simulation engine
- Completed Insider Tracker backtesting pipeline (replay historical data through signal detectors)

## 2026-04-11 — Strategic Pivot

- Archived all existing strategies and backtest engines to `archive/2026-04-11-pre-pivot/`
  - `Al Washing Detector/` (392 source files, 66 tests, 10 GSD phases)
  - `Kalshi Insider Tracker/` (28 source files, 12 tests, 6 GSD phases)
  - `backtest/` (fund-backtest equity engine)
  - `kalshi-backtest/` (prediction market engine with Protocol-based strategy interface)
  - Dashboard PNGs, `run_pipeline.sh`
- Archived planning artifacts to `.planning-archive/insider-tracker-20260411/`
- Rewrote `CLAUDE.md` for new direction
- Stripped strategy-specific env vars from `.env.example`
- New direction: AI-native multi-agent hedge fund — LLM agents for hypothesis generation, evidence gathering, adversarial critique, and backtesting

## 2026-04-11 — GSD Project Initialization

- Completed domain research (4 parallel agents):
  - Multi-agent trading systems: 13 academic papers, 5 production systems surveyed
  - Agent frameworks: 9 frameworks compared (LangGraph + PydanticAI recommended)
  - Financial data sources: 20+ APIs evaluated, free stack + $110/mo paid upgrade mapped
  - Competitive landscape: YC RFS analysis, fund structure, regulatory considerations
- Research files: `.planning/research/` (MULTI_AGENT_TRADING_SYSTEMS.md, AGENT_FRAMEWORKS.md, DATA_SOURCES.md, COMPETITIVE_LANDSCAPE.md, STACK.md, FEATURES.md, ARCHITECTURE.md)
- Created `.planning/PROJECT.md` — full project context with key decisions from research
- Created `.planning/REQUIREMENTS.md` — 36 v1 requirements across 8 categories
- Created `.planning/ROADMAP.md` — 8-phase roadmap with testable success criteria
- Created `.planning/STATE.md` — project state tracking
- Updated `CLAUDE.md` with architecture (Manager-Analyst + Adversarial Debate), stack (LangGraph + PydanticAI + Claude), data sources, conventions, and agent development rules
- Updated `.env.example` with all required environment variables

## 2026-04-11 — Networking Research

- Compiled comprehensive outreach list across 9 categories (~60+ people)
- Categories: AI finance founders, quant practitioners, LLM researchers, skeptics, compliance, data vendors, AI infra builders, allocators, YC alumni
- Added 10 conferences/events, 10 online communities, 7 podcasts, 3 outreach templates
- Prioritized first 5 outreach targets and sequenced by stage (now → pre-YC → post-YC → fundraising)
- File: `docs/NETWORKING_RESEARCH.md`
