# Roadmap: AI-Native Hedge Fund Multi-Agent Research System

## Overview

Build a multi-agent LLM research system that produces institutional-quality investment theses with quantitative signals. The journey starts with framework scaffolding and observability (Phase 1), layers in financial data ingestion with strict temporal controls (Phase 2), proves out a single research agent end-to-end (Phase 3), then expands to specialized analyst agents with a manager (Phase 4). Adversarial bull/bear debate hardens thesis quality (Phase 5), risk management enforces hard limits (Phase 6), persistent memory enables cross-session learning (Phase 7), and signal output with human review completes the pipeline (Phase 8).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - LangGraph orchestration, PydanticAI agent base, Claude model routing, observability, and token budgets (completed 2026-04-12)
- [x] **Phase 2: Data Ingestion** - SEC filings, XBRL financials, equity prices, insider trades, news, macro data with temporal controls (completed 2026-04-12)
- [ ] **Phase 3: Single-Agent Research** - One agent that reads filings, uses tool-augmented calculations, and produces structured thesis + signal
- [ ] **Phase 4: Multi-Agent Specialization** - Fundamental, Sentiment, and Technical analysts coordinated by a Research Manager
- [ ] **Phase 5: Adversarial Critique** - Bull/Bear advocates argue structured 5-act debate, thesis quality scored
- [ ] **Phase 6: Risk Management** - Risk Manager agent with veto power, position sizing constraints, portfolio-level checks
- [ ] **Phase 7: Memory and Learning** - Episodic memory in PostgreSQL, human-readable belief memory, cross-session learning
- [ ] **Phase 8: Signal and Output** - Quantitative signal output, portfolio ranking, human-in-the-loop review, decision audit trail

## Phase Details

### Phase 1: Foundation
**Goal**: A running LangGraph pipeline with typed agent schemas, multi-model routing, observability traces, and cost guardrails -- so every subsequent phase builds on instrumented, budget-aware infrastructure
**Depends on**: Nothing (first phase)
**Requirements**: FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05
**Success Criteria** (what must be TRUE):
  1. A LangGraph graph compiles and runs with at least two nodes, checkpointing state to PostgreSQL between steps, and resuming from a checkpoint after simulated interruption
  2. A PydanticAI agent accepts a typed input schema and returns a validated output schema -- invalid LLM output is rejected with a descriptive validation error (not silently passed through)
  3. A single pipeline run routes at least two different tasks to different Claude models (e.g., Haiku for extraction, Sonnet for analysis) and the Langfuse trace shows which model handled each step with latency and token counts
  4. When an agent exceeds its configured token budget mid-run, the pipeline halts that agent with a budget-exceeded error rather than continuing to spend
**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md -- Project scaffold, dependencies, config, model routing, DB session, typed schemas
- [x] 01-02-PLAN.md -- PydanticAI agent factory with budget enforcement, extraction and analysis agents
- [x] 01-03-PLAN.md -- LangGraph pipeline, PostgreSQL checkpointing, Langfuse observability, budget-enforced invocation

### Phase 2: Data Ingestion
**Goal**: Agents can query any of the fund's data sources and receive pre-processed, temporally-correct financial data -- so research agents never touch raw APIs and never see future data
**Depends on**: Phase 1
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, DATA-07, DATA-08
**Success Criteria** (what must be TRUE):
  1. Given a ticker and date, the system returns the correct 10-K/10-Q filing sections (Business, Risk Factors, MD&A) that were publicly available as of that date -- filings with a later accepted_date are excluded
  2. Given a ticker, XBRL financial data is returned as a natural-language summary (revenue, margins, cash flow with YoY/QoQ changes) -- not raw JSON -- and all numbers match the SEC source within rounding tolerance
  3. Equity price data for any ticker in the universe is served from PostgreSQL cache (not live yfinance calls), with Tiingo fallback tested, and corporate actions (splits/dividends) are correctly adjusted
  4. Insider trade clusters (3+ insiders buying within 14 days), daily news sentiment summaries, and macro indicators (Fed Funds, CPI, GDP, yield curve) are each retrievable via a single tool call with an as-of date filter
  5. Every data retrieval tool enforces a mandatory as_of_date parameter -- calling without it raises an error, and no tool returns data timestamped after the as_of_date
**Plans:** 4 plans

Plans:
- [x] 02-01-PLAN.md -- Data foundation: temporal enforcement, DB models, NL summary formatters, Alembic migrations
- [x] 02-02-PLAN.md -- SEC EDGAR filing retrieval and XBRL financial data extraction
- [x] 02-03-PLAN.md -- Equity price caching (yfinance + Tiingo) and insider trade cluster detection
- [x] 02-04-PLAN.md -- Finnhub news sentiment and FRED macro indicators

### Phase 3: Single-Agent Research
**Goal**: A single research agent can analyze a company from SEC filings and produce an investment thesis with quantitative signal -- proving the core research loop works end-to-end before adding multi-agent complexity
**Depends on**: Phase 2
**Requirements**: AGENT-01, AGENT-02, AGENT-03, AGENT-04
**Success Criteria** (what must be TRUE):
  1. Given a ticker, the agent produces a structured thesis containing: bull case (minimum 3 supporting points with filing citations), bear case (minimum 3 points with citations), confidence score (0-100), and at least 2 named risk factors
  2. Every financial metric in the thesis (P/E ratio, revenue growth, margins, etc.) was computed by a deterministic tool call -- the Langfuse trace shows zero instances of the LLM generating a number without a preceding tool invocation
  3. The signal output includes direction (long/short/neutral), conviction level (low/medium/high), time horizon, and suggested position size -- all fields validated against the Pydantic schema with no missing values
  4. Running the agent on the same ticker with an as_of_date of 2024-01-01 vs 2025-01-01 produces materially different theses reflecting different filing data -- demonstrating temporal correctness rather than memorized knowledge
**Plans:** 3 plans

Plans:
- [x] 03-01-PLAN.md -- Tighten ThesisOutput schema and build research agent with 6 data tool wrappers
- [x] 03-02-PLAN.md -- Signal agent, ResearchPipelineState, and LangGraph research -> signal pipeline
- [x] 03-03-PLAN.md -- Integration tests, package exports, and human-verified real-ticker demo

### Phase 4: Multi-Agent Specialization
**Goal**: Three specialized analyst agents each contribute domain-specific analysis, and a Research Manager synthesizes their outputs into a unified thesis with explicit conflict resolution
**Depends on**: Phase 3
**Requirements**: MULTI-01, MULTI-02, MULTI-03, MULTI-04
**Success Criteria** (what must be TRUE):
  1. The Fundamental Analyst produces a valuation-focused analysis using SEC filing RAG and XBRL financial data -- its output cites specific filing sections and includes computed valuation metrics
  2. The Sentiment Analyst produces a sentiment-focused analysis incorporating news sentiment scores, insider trading activity, and (where available) earnings call tone -- its output includes a composite sentiment score with component breakdown
  3. The Technical/Quant Analyst produces a momentum/volatility analysis using only computed technical indicators (RSI, moving averages, volatility measures) via tool calls -- no price pattern descriptions generated by the LLM without tool backing
  4. The Research Manager receives all three analyst reports and produces a unified thesis that explicitly identifies where analysts agree, where they conflict, and how conflicts were resolved -- the unified thesis is not simply a concatenation
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD
- [ ] 04-03: TBD

### Phase 5: Adversarial Critique
**Goal**: Every thesis is stress-tested through a structured bull/bear debate before becoming a signal -- so the system's output reflects adversarial scrutiny, not confirmation bias
**Depends on**: Phase 4
**Requirements**: DEBATE-01, DEBATE-02, DEBATE-03, DEBATE-04
**Success Criteria** (what must be TRUE):
  1. The Bull Advocate constructs a positive investment case using evidence from analyst reports -- its arguments reference specific data points (not vague assertions) and each claim cites its source analyst
  2. The Bear Advocate constructs a negative investment case with counter-evidence -- it directly addresses and rebuts at least 2 specific bull claims rather than presenting an independent negative thesis
  3. The debate follows the 5-act protocol (thesis, counter-thesis, rebuttal, final arguments, synthesis) with each act producing a structured output -- skipping an act or producing an empty act causes a validation error
  4. The final synthesis includes a thesis quality score based on evidence strength, logical consistency, and risk coverage -- and the post-debate confidence score differs from the pre-debate score in at least 30% of runs (demonstrating the debate actually changes the assessment)
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD
- [ ] 05-03: TBD

### Phase 6: Risk Management
**Goal**: A Risk Manager agent enforces hard portfolio constraints that cannot be overridden by research agents -- so no signal reaches the human reviewer without passing quantitative risk checks
**Depends on**: Phase 5
**Requirements**: RISK-01, RISK-02, RISK-03
**Success Criteria** (what must be TRUE):
  1. The Risk Manager can veto a high-conviction recommendation and the veto is final -- the pipeline produces a "blocked by risk" output with the specific constraint violated, not a modified recommendation
  2. Position sizing constraints are enforced as hard limits: a signal suggesting >X% allocation to a single position is rejected (not silently capped), and the rejection reason references the specific limit
  3. Portfolio-level checks run against the current portfolio state: sector concentration exceeding threshold, correlation above threshold with existing positions, or projected max drawdown breaching limits each trigger a named constraint violation
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

### Phase 7: Memory and Learning
**Goal**: The system remembers past analyses and learns from outcomes -- so research quality improves over time instead of starting from zero every session
**Depends on**: Phase 6
**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04
**Success Criteria** (what must be TRUE):
  1. Episodic memory stores completed analyses and (when available) trade outcomes in PostgreSQL with 90-day active retention -- querying by ticker, sector, or date range returns relevant prior analyses that the agent references in new research
  2. Belief memory is stored as structured YAML/JSON documents containing investment theses, sector models, and learned patterns -- a human can open the file, read the beliefs in plain language, and understand why the system holds each belief
  3. A human can edit a belief memory entry (change confidence, add a note, mark a belief as incorrect) and the next analysis for that ticker/sector reflects the human edit -- the system does not silently overwrite human corrections
  4. After a trade outcome is known (profit or loss), the system's self-critique process updates relevant beliefs with the outcome and adjusts confidence -- the updated belief document shows the outcome, the critique reasoning, and the new confidence level
**Plans**: TBD

Plans:
- [ ] 07-01: TBD
- [ ] 07-02: TBD
- [ ] 07-03: TBD

### Phase 8: Signal and Output
**Goal**: The pipeline produces investor-ready output with full audit trail and human review gate -- so every signal that reaches a trading decision has been researched, debated, risk-checked, and approved by a human
**Depends on**: Phase 7
**Requirements**: SIG-01, SIG-02, SIG-03, SIG-04
**Success Criteria** (what must be TRUE):
  1. Each ticker's signal output includes: direction (long/short/neutral), conviction (0-100), one-paragraph thesis summary, risk score, and the full thesis document is linked -- all fields populated, no nulls
  2. A portfolio-level view ranks all analyzed tickers by conviction, shows thesis summaries, and groups by sector -- the ranking updates when new analyses complete
  3. Signals with conviction above a configurable threshold trigger a human review step: the pipeline pauses, presents the thesis and debate transcript to the reviewer, and does not finalize until the human approves or rejects
  4. Every agent step in the pipeline is logged with inputs, outputs, reasoning, model used, tokens consumed, and timestamp -- given any final signal, a compliance reviewer can trace backward through every step that produced it
**Plans**: TBD

Plans:
- [ ] 08-01: TBD
- [ ] 08-02: TBD
- [ ] 08-03: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8

| Phase | Plans Complete | Status | Completed |
|-------|---------------|--------|-----------|
| 1. Foundation | 3/3 | Complete | 2026-04-12 |
| 2. Data Ingestion | 0/4 | Planned | - |
| 3. Single-Agent Research | 0/3 | Not started | - |
| 4. Multi-Agent Specialization | 0/3 | Not started | - |
| 5. Adversarial Critique | 0/3 | Not started | - |
| 6. Risk Management | 0/2 | Not started | - |
| 7. Memory and Learning | 0/3 | Not started | - |
| 8. Signal and Output | 0/3 | Not started | - |
