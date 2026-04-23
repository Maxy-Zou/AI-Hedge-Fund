# Progress

## 2026-04-23 — Phase 8 Plan 08-02: query_portfolio_view (SIG-02) + reconstruct_audit_trail CLI (SIG-04)

- **query_portfolio_view** (`src/ai_hedge_fund/output/portfolio_view.py`): pure read-path query over append-only `episodic_memory`. Returns `{sector: [entry, ...]}` ranked by `conviction DESC, as_of_date DESC`; latest-per-ticker; `record_type='analysis'` only; `as_of_date <= target` temporal cutoff; `limit_per_sector=50` DoS cap. No memoization -- the append-only table IS the cache (Pitfall C / T-08-15).
- **reconstruct_audit_trail + audit_reconstruct CLI** (`src/ai_hedge_fund/scripts/audit_reconstruct.py`): synchronous reconstruction of analysis row + linked review row + Langfuse `thread_id` hint; `policy_sha` + `review_policy_sha` preserved for compliance linkage. CLI: `uv run python -m ai_hedge_fund.scripts.audit_reconstruct --episodic-id N` prints JSON. Raises `ValueError` on missing id OR wrong `record_type` (T-08-19 repudiation mitigation).
- **output/__init__.py** extended: `query_portfolio_view` re-exported alongside the 4 existing Plan 08-01 re-exports (APPEND, not rewrite).
- **Tests added:** +21 (11 portfolio_view + 10 audit_reconstruct). Wave-1 output suite 84/84 green; cross-phase (output + memory + review) 268/268 green; full suite 1026 passed (+21 from 08-01 baseline), 2 pre-existing unrelated failures.
- Files: `08-02-PLAN.md`, `08-02-SUMMARY.md`, `portfolio_view.py`, `audit_reconstruct.py`, `test_portfolio_view.py`, `test_audit_reconstruct.py`, `output/__init__.py`, `STATE.md`, `ROADMAP.md`, `REQUIREMENTS.md`.
- Requirements closed: **SIG-02** (portfolio view) and **SIG-04** (compliance-grade audit read side).
- Milestone progress: 3/6 Phase-8 plans complete; ~91% overall.

## 2026-04-22 — Phase 7 Post-Completion: Review, Fixes, Verification

- **Code review (standard depth):** 34 source files reviewed. 0 critical, 3 warnings (WR-01 sector regex guard gap, WR-02 orphan outcome row logging, WR-03 observed_date nullable=False hardening), 6 info items deferred.
- **All 3 warnings fixed in one iteration** (commits `64d07b2`, `bea30b0`, `ce69156`). REVIEW-FIX status: `all_fixed`.
- **Verification (goal-backward):** 4/4 ROADMAP success criteria pass automated verification (status: `human_needed`). 2 UAT items persisted to `07-HUMAN-UAT.md` (MEM-02 subjective readability; MEM-03 live pipeline + Langfuse trace). User deferred UAT; phase accepted as code-complete.
- **Regression after fixes:** 234 memory/graph/integration tests green with WR-03 applied; 921 full suite green (2 pre-existing unrelated failures documented).
- **Artifacts:** `07-REVIEW.md`, `07-REVIEW-FIX.md`, `07-VERIFICATION.md`, `07-HUMAN-UAT.md`.
- **Milestone status:** 7/8 phases complete — Phase 8 (Signal and Output) remains.

## 2026-04-22 — Phase 7 Complete: Memory and Learning

Plan 07-05 ships the integration test suite and closes the phase:

- **14 new integration tests** across `tests/integration/test_phase7_e2e.py` (8 e2e scenarios) and `tests/integration/test_phase7_policy_sha_linkage.py` (6 policy_sha audit linkage tests).
- **All 12 agents stubbed via TestModel** in every scenario (fundamental, sentiment, technical, manager, bull, bear, rebuttal, final_arguments, debate_synthesis, risk_manager, signal, self_critique). Zero real LLM calls.
- **MEM-01..04 + MEM-03 x MEM-04 interaction + Pitfall-2 temporal correctness + Phase-5 backcompat** all proven end-to-end via composed `build_debate_pipeline(with_memory=True, with_risk=True)` runs on seeded fixtures.
- **Phase 6 -> Phase 7 policy_sha audit chain** proven by 6 dedicated tests: deterministic (same policy), change-sensitive (different policy), idempotent (revert), well-formed (64-hex APPROVED + VETOED), three-way equal (state / column / payload all agree).
- **VETOED persistence ratified** (research Open Question 1): a vetoed run produces a stored EpisodicMemory row with `payload['risk_assessment']['status'] == 'VETOED'` AND `signal_direction is None` AND a well-formed policy_sha.
- **tests/integration/conftest.py** added: re-exports 7 memory fixtures from `tests/memory/conftest.py` so integration tests consume them via pytest's sibling-conftest discovery (avoids F811 ruff false-positive from direct module imports). Mirrors the pattern already in `tests/graph/conftest.py`.
- **199 Phase-7 tests green** across `tests/memory` (162) + `tests/graph/test_memory_nodes.py` + `tests/graph/test_pipeline_with_memory.py` (23) + `tests/integration/test_phase7_*.py` (14).
- **Full suite:** 920 passed, 9 skipped, 2 pre-existing baseline failures (`test_research_pipeline.py` async tests missing `pytest-asyncio`, documented in `deferred-items.md`).
- **Cross-phase regression clean:** Phase 5 (17 integration) + Phase 6 (122 graph/risk + 17 integration) + earlier Phase 7 (185 memory + graph) all still green byte-for-byte.
- **07-VALIDATION.md:** `nyquist_compliant: true`, `wave_0_complete: true`, Per-Task Verification Map populated with 15 rows (all green), Validation Sign-Off approved.
- **REQUIREMENTS.md:** MEM-01, MEM-02, MEM-03, MEM-04 all marked Complete with phase-7 attribution.
- **Milestone v1.0 progress: 7/8 phases complete** (ready for Phase 8 — Signal and Output).

Files: `07-05-PLAN.md`, `07-05-SUMMARY.md`, `test_phase7_e2e.py`, `test_phase7_policy_sha_linkage.py`, `tests/integration/conftest.py`, `07-VALIDATION.md` (sign-off), `deferred-items.md` (ruff I001 deferral), `STATE.md`, `ROADMAP.md`, `REQUIREMENTS.md`.

## 2026-04-22 — Phase 7 Plan 04: Offline Self-Critique Loop (MEM-04)

- **compute_new_confidence** (`src/ai_hedge_fund/memory/critique.py`): pure deterministic math. Returns int in `[0, 100]`; agreement (long+pos, short+neg) raises confidence, disagreement and neutral+big-move lower it; per-event |delta| capped at 10 (Pitfall 5 drift guard); `ValueError` on unknown signal_direction.
- **format_critique_context** (`src/ai_hedge_fund/memory/critique.py`): deterministic 5-section prompt (BELIEF / OUTCOME / OLD_CONFIDENCE / NEW_CONFIDENCE (DETERMINISTIC) / LINKED_ANALYSIS) for audit-reproducible LLM input.
- **self_critique_agent** (`src/ai_hedge_fund/agents/self_critique.py`): PydanticAI `Agent[None, RationaleOnly]` on REASONING tier with `retries=2`; system prompt uses EXPLAIN exclusively; forbidden verbs (decide/judge/determine/rule/verdict + plurals) absent via word-boundary regex (T-07-31 analog of T-06-02b). `RationaleOnly` has EXACTLY ONE field (T-07-30).
- **ingest_outcome CLI** (`src/ai_hedge_fund/scripts/ingest_outcome.py`): 6-step offline loop — regex-guard → append outcome row → load belief → compute new confidence → LLM rationale → write_belief (MEM-03 chokepoint).
- **MEM-03 × MEM-04 cross-requirement proven:** human-edited belief survives outcome ingest (confidence unchanged, critique_history updated, skipped audit visible to operator).
- **Tests added:** +111 (93 critique math + 13 self-critique agent + 5 ingest_outcome). Full cross-phase regression (phases 5/6/7): 291 passing.

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
