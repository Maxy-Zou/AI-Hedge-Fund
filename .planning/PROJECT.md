# AI-Native Hedge Fund — Multi-Agent Research System

## Current State

**Shipped:** v1.0 — Multi-Agent Research System (2026-04-23)
**Active:** v1.1 — Paper Trading + Promotion Gate (started 2026-04-25)

The v1.0 core research pipeline is code-complete and integration-verified: LangGraph + PydanticAI substrate, temporally-correct data ingestion (SEC EDGAR + yfinance + FRED + Finnhub), single-agent research loop, manager-analyst hierarchy with 3 specialists, structured bull/bear adversarial debate, Risk Manager with veto power, episodic + belief memory with offline self-critique, and investor-ready signal output with a LangGraph `interrupt()`-backed human review gate and compliance-grade audit trail. 1,108 tests green. 12 human-UAT items deferred (all require live API keys or subjective judgment; none are code defects).

## Current Milestone: v1.1 Paper Trading + Promotion Gate

**Goal:** Generate a credible track record from v1.0 signals via paper trading on a real clock, gated by a SHA-pinned promotion policy that joins the existing audit chain.

**Source-of-truth plan:** `docs/V1.1_PAPER_TRADING_PLAN.md`

**Target features:**
- Alpaca paper-broker execution layer with deterministic tool-first sizing (LLM never sizes)
- Append-only `paper_trades` / `paper_fills` / `paper_pnl_daily` schema with dual timestamps
- Daily mark-to-market + per-signal attribution (analyst / debate-side / conviction)
- Promotion gate: `promotion_policy_sha` joins `risk_policy_sha` + `review_policy_sha` audit chain
- Track-record CLI (`render_track_record`), JSON + markdown, LP/YC-shareable

**Explicitly OUT (deferred to v1.2+ or parking lot):**
- Literature mining / arXiv-SSRN auto-strategy ingestion (parking lot — replication crisis, dilutes pitch)
- Real-broker / live capital execution (only after promotion gate clears on paper)
- Portfolio optimization on top of ranked signals (v1.2+)
- Web/TUI reviewer UI (v1.2+)

**Carried-forward invariants (from v1.0):**
- Tool-first quantitative path — LLM never computes P&L, attribution, sizing, or promotion decision
- Append-only financial time-series — no row ever updated
- Temporal correctness — `as_of_date <= target` on every recall path
- SHA-pinned policy round-trips — state == column == payload

## What This Is

A multi-agent LLM research system for an AI-native hedge fund targeting US equities and options. Agents generate investment hypotheses, gather evidence from SEC filings and financial data, adversarially critique each other's theses, and produce quantitative signals backed by structured thesis documents. The system is the core IP of a management company targeting YC and eventual LP capital.

## Core Value

Produce institutional-quality investment research at scale — structured theses with quantitative signals that are rigorous enough to trade on and transparent enough to show investors.

## Requirements

### Validated

- ✓ Single research agent reads SEC filings (10-K, 10-Q, 8-K) and produces a structured investment thesis — v1.0 Phase 3
- ✓ Agent uses tool augmentation for all financial calculations (never computes ratios/metrics directly) — v1.0 (tool-first invariant honored across Phases 3-8)
- ✓ Strict temporal controls on all data — every input timestamped, no look-ahead bias — v1.0 (FUTUREX regression proves `as_of_date <= target` end-to-end)
- ✓ Structured thesis output: bull/bear case, evidence citations, confidence score, risk factors — v1.0 Phase 5
- ✓ Quantitative signal output: long/short/neutral + conviction level backed by thesis — v1.0 Phase 8 (`FinalSignalOutput`)
- ✓ Multi-agent specialization: Fundamental, Sentiment, and Technical/Quant analyst agents — v1.0 Phase 4
- ✓ Manager agent synthesizes analyst outputs into unified thesis — v1.0 Phase 4
- ✓ Adversarial bull/bear debate protocol (structured 5-act format, not free-form) — v1.0 Phase 5
- ✓ Dual-model routing: Haiku for extraction, Sonnet for analysis, Opus for complex reasoning — v1.0 Phase 1
- ✓ Human-readable belief memory that persists investment theses across sessions — v1.0 Phase 7 (ruamel.yaml, comment preservation, human-edit guard)
- ✓ LangGraph orchestration with checkpointing and human-in-the-loop capability — v1.0 Phase 1 + 8 (`interrupt()` primitive)
- ✓ PostgreSQL-backed episodic memory for recent analyses and trade outcomes — v1.0 Phase 7 (append-only, 90-day retention)
- ✓ Cost monitoring and per-agent token budget caps — v1.0 Phase 1

### Active (v1.1 — in flight)

- [ ] Paper-broker execution layer (Alpaca paper) with deterministic sizing — v1.1
- [ ] Append-only paper-trading schema (`paper_trades`, `paper_fills`, `paper_pnl_daily`) — v1.1
- [ ] Daily mark-to-market + per-signal attribution — v1.1
- [ ] Promotion gate with `promotion_policy_sha` in audit chain — v1.1
- [ ] Track-record CLI / report (LP/YC-shareable JSON + markdown) — v1.1

### Active (deferred to v1.2+)

- [ ] Rich reviewer UI replacing CLI blocking stdin (web or TUI)
- [ ] Portfolio optimization on top of ranked signals (SIG-02 produces the rank; optimization is next)
- [ ] Automated compliance report generation (Langfuse trace → PDF)
- [ ] Live-run UAT closure for Phases 1/2/3/5/7/8 (12 human-UAT items deferred at v1.0 close; tracked in STATE.md)
- [ ] VALIDATION.md frontmatter retrofit for Phases 1/2/5/6 (Nyquist convention introduced starting Phase 7)

### Out of Scope

- Fully autonomous trade execution without human oversight — no production system does this, regulatory risk too high
- RL fine-tuning of LLMs (FLAG-Trader, Trading-R1 approach) — destroys interpretability, research-grade only
- Crypto/forex/multi-asset — focus on US equities + options first
- Visual/chart analysis — computed technical indicators via tools are more reliable than LLM chart reading
- Real-time intraday trading — daily signal cadence matches data availability and fund strategy
- Custom LLM training or fine-tuning — use frontier models (Claude) with good prompting, not custom models
- High-frequency trading — latency requirements don't match LLM-based architecture
- Literature mining / arXiv-SSRN auto-strategy ingestion — replication crisis (Hou/Xue/Zhang 2020: ~64% of 452 anomalies fail to replicate); LLM auto-extraction would surface mostly decayed anomalies. Dilutes the "research-on-filings" pitch. If revisited, lives as a side project (Slack digest for human review), never wired into agents.

## Context

**Research basis:** Comprehensive domain research completed 2026-04-11 covering multi-agent trading systems (13 academic papers, 5 production systems), agent frameworks (9 compared), financial data sources (20+ evaluated), and competitive landscape.

**Key research findings:**
- Manager-Analyst hierarchy + adversarial debate is the architecture with strongest evidence (FinCon NeurIPS 2024, TradingAgents, AlphaAgents/BlackRock)
- FINSABER (KDD 2026) found LLM strategies don't beat buy-and-hold on rigorous evaluation — position as "research at scale" not "AI that beats the market"
- LangGraph is dominant in production financial agent systems (S&P Global/Kensho, 43k-star open source implementations)
- Token cost is #1 operational risk — naive multi-agent pipeline costs $2-5/analysis vs $0.30-0.80 optimized
- The YC RFS slot for AI-native hedge funds is mostly unfilled (Standard Signal is only direct competitor)

**Prior work:** Two strategy implementations (AI Washing Detector, Kalshi Insider Tracker) and two backtest engines were developed and archived in `archive/2026-04-11-pre-pivot/`. Patterns worth referencing: entity resolution code, append-only database schemas, Protocol-based strategy interface, SEC EDGAR integration via edgartools.

**Competitive position:** YC has explicitly requested AI-native hedge funds. Standard Signal (YC P26, solo founder) is the only direct competitor. Kimpton AI and Trata are tools-for-funds, not funds. Incumbents (Citadel, Point72) are structurally slow due to compliance inertia.

## Constraints

- **Stack**: Python 3.11+, uv, PostgreSQL, LangGraph + PydanticAI — proven combination for financial multi-agent systems
- **LLM provider**: Claude models primary (Haiku/Sonnet/Opus routing) — 200k context handles full 10-K filings
- **Data budget**: Start at $0/mo (SEC EDGAR + yfinance + Finnhub + FMP free + FRED), upgrade to ~$110/mo (Polygon + FMP Ultimate + ThetaData) when budget allows
- **Immutability**: All financial time-series data is append-only (fund-wide convention from prior work)
- **Honest positioning**: Never claim autonomous alpha generation — SEC fined Delphia and Global Predictions for AI washing (March 2024)
- **Human oversight**: All trade-level decisions require human review — no production hedge fund runs fully autonomous LLM trading

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| LangGraph for orchestration | Dominant in production financial agent systems (Kensho/S&P, Captide), graph-based state machines map to analyst-debate-synthesis pipeline, checkpointing + human-in-the-loop built in | ✓ Good (v1.0) |
| PydanticAI for agent logic | Type-safe I/O catches financial data errors at dev time, matches existing Pydantic patterns, dependency injection for testability | ✓ Good (v1.0) |
| Manager-Analyst + Adversarial Debate architecture | Strongest evidence base across 3 independent papers (FinCon, TradingAgents, AlphaAgents), reduces communication overhead vs peer-to-peer | ✓ Good (v1.0) |
| Structured 5-act debate protocol (not free-form) | SAS paper shows structured debate outperforms free-form; free-form degrades into repetition | ✓ Good (v1.0) |
| Dual-model routing from day one | TradingAgents validated deep_think_llm + quick_think_llm pattern; without it, costs spiral to $5K/day at 500 tickers | ✓ Good (v1.0) |
| Tool-first for all quantitative work | LLMs hallucinate financial numbers; FinAgent showed 36% improvement from tool augmentation | ✓ Good (v1.0) |
| Human-readable belief memory | Both transparency feature (investors can inspect) and safety mechanism (humans can correct systematic errors) | ✓ Good (v1.0) |
| Start with free data stack, upgrade incrementally | $0/mo is sufficient for v1; $110/mo (Polygon + FMP + ThetaData) is the "can talk to investors" threshold | ✓ Good (v1.0) |
| Target YC with management company structure | YC takes 7% of management company (C-Corp), not the fund (LP). Use Repool (YC S21) for fund infrastructure | ✓ Good (v1.0) |
| Paper trading before live capital (v1.1 scope) | YC/LP credibility gap requires a track record; FINSABER shows backtests of LLM strategies are unreliable, only forward paper trading on real-clock live data is credible. Cheapest path to a defensible record. | Pending (v1.1) |
| Promotion gate via `promotion_policy_sha` (v1.1) | Reuses Phase 6/8 SHA-pinned policy pattern; gates signal → live capital eligibility on Sharpe / DD / hit-rate / sample-size thresholds. Compliance-grade audit chain extended end-to-end. | Pending (v1.1) |
| Defer literature mining / paper ingestion (v1.1 parking lot) | Hou/Xue/Zhang 2020 replicated 452 anomalies, ~64% failed. Auto-extracting strategies from arXiv would pollute signal with decayed anomalies. Also dilutes the "research-on-filings" pitch. If revisited, ships as a side-project Slack digest, never as pipeline input. | Pending (v1.1) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase merges to `main`:**
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone:**
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-25 — v1.1 (Paper Trading + Promotion Gate) milestone started*
