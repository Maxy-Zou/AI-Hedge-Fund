# Progress

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
