# Requirements: AI-Native Hedge Fund

**Defined:** 2026-04-11
**Core Value:** Produce institutional-quality investment research at scale -- structured theses with quantitative signals that are rigorous enough to trade on and transparent enough to show investors.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Foundation

- [ ] **FOUND-01**: LangGraph orchestration graph defined with checkpointing and state persistence to PostgreSQL
- [ ] **FOUND-02**: PydanticAI agent base with typed schemas for hypotheses, evidence, signals, and theses
- [ ] **FOUND-03**: Claude model integration with dual-model routing (Haiku/Sonnet/Opus by task type)
- [ ] **FOUND-04**: Langfuse observability integration for agent traces, cost tracking, and latency monitoring
- [ ] **FOUND-05**: Token budget enforcement per agent and per pipeline run with configurable caps

### Data Ingestion

- [ ] **DATA-01**: SEC EDGAR integration for 10-K, 10-Q, 8-K filings via edgartools with section-level chunking
- [ ] **DATA-02**: XBRL financial data extraction via CompanyFacts API with pre-computed metric summaries
- [ ] **DATA-03**: Equity price data ingestion (yfinance with PostgreSQL caching, Tiingo fallback)
- [ ] **DATA-04**: Insider trade detection from SEC Form 4 filings with cluster buy identification
- [ ] **DATA-05**: News and sentiment aggregation from Finnhub with daily per-ticker summaries
- [ ] **DATA-06**: Macro context from FRED (interest rates, CPI, GDP, yield curve)
- [ ] **DATA-07**: Strict temporal controls -- every data input timestamped, RAG filtered by "available as of" date
- [ ] **DATA-08**: Natural language summaries generated from structured data before LLM consumption

### Single-Agent Research

- [ ] **AGENT-01**: Hypothesis Generator agent can produce a structured investment thesis from SEC filing analysis
- [ ] **AGENT-02**: Agent uses tool augmentation for all financial calculations (ratios, growth rates, valuation metrics)
- [ ] **AGENT-03**: Thesis output includes: bull case, bear case, evidence citations, confidence score (0-100), risk factors
- [ ] **AGENT-04**: Signal output includes: direction (long/short/neutral), conviction level, time horizon, position size suggestion

### Multi-Agent Specialization

- [ ] **MULTI-01**: Fundamental Analyst agent -- RAG over SEC filings, financial statement analysis, valuation
- [ ] **MULTI-02**: Sentiment Analyst agent -- news sentiment, earnings call tone, insider activity signals
- [ ] **MULTI-03**: Technical/Quant Analyst agent -- price patterns, momentum, volatility indicators via computed tools
- [ ] **MULTI-04**: Research Manager agent synthesizes analyst outputs into unified thesis with conflict resolution

### Adversarial Critique

- [x] **DEBATE-01**: Bull Advocate agent presents investment case using analyst evidence
- [x] **DEBATE-02**: Bear Advocate agent presents opposing case with counter-evidence
- [x] **DEBATE-03**: Structured 5-act debate protocol (thesis -> counter-thesis -> rebuttal -> final arguments -> synthesis)  <!-- agents + schemas delivered in 05-01 + 05-02; graph wiring in 05-03 -->
- [x] **DEBATE-04**: Thesis quality scoring based on evidence strength, logical consistency, and risk coverage (compute_quality_score + sub-score schema enforcement landed in 05-02)

### Risk Management

- [ ] **RISK-01**: Risk Manager agent with veto power on high-risk recommendations
- [ ] **RISK-02**: Position sizing constraints enforced as hard limits (not suggestions)
- [ ] **RISK-03**: Portfolio-level risk checks (sector concentration, correlation, max drawdown thresholds)

### Memory and Learning

- [x] **MEM-01
**: Episodic memory in PostgreSQL -- stores recent analyses and trade outcomes with 90-day active retention
- [x] **MEM-02
**: Belief memory as structured human-readable documents (YAML/JSON) -- investment theses, sector models, learned patterns
- [x] **MEM-03
**: Belief memory is editable by humans (transparency for investors, safety mechanism for corrections)
- [x] **MEM-04
**: Cross-session learning -- belief memory updated via self-critique after trade outcomes are known

### Signal and Output

- [x] **SIG-01
**: Quantitative signal output per ticker: direction, conviction, thesis summary, risk score
- [x] **SIG-02
**: Portfolio-level ranked opportunity list with thesis summaries
- [x] **SIG-03
**: Human-in-the-loop review step for signals above a configurable conviction threshold
- [x] **SIG-04
**: Decision audit trail -- every agent step logged with inputs, outputs, and reasoning for compliance

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Paper Trading

- **PAPER-01**: Paper trading integration with Alpaca to generate a live track record from signals
- **PAPER-02**: P&L tracking and performance attribution by agent/strategy
- **PAPER-03**: Automated daily research cycle across a configurable ticker universe

### Dashboard

- **DASH-01**: Streamlit dashboard showing active theses, signals, and portfolio view
- **DASH-02**: Agent execution visualization showing pipeline steps and debate transcripts
- **DASH-03**: Cost monitoring dashboard with per-agent and per-ticker token usage

### Options Analysis

- **OPT-01**: Options chain analysis via ThetaData integration
- **OPT-02**: Implied volatility surface construction and anomaly detection
- **OPT-03**: Options strategy recommendation (covered calls, protective puts, spreads) based on thesis

### Advanced

- **ADV-01**: Earnings call transcript analysis via FMP Ultimate ($56/mo)
- **ADV-02**: Survivorship-bias-free historical universe reconstruction from EDGAR submissions
- **ADV-03**: Backtest integration -- feed historical signals through vectorized backtester with transaction costs

## Out of Scope

| Feature | Reason |
|---------|--------|
| Fully autonomous trade execution | No production hedge fund runs this; regulatory risk; human oversight is non-negotiable |
| RL fine-tuning of LLMs | Destroys interpretability, research-grade only (FLAG-Trader, Trading-R1) |
| Crypto/forex/multi-asset | Focus on US equities first; multi-asset adds complexity without clear benefit at this stage |
| Visual/chart analysis by LLMs | Computed technical indicators via tools are more reliable |
| Real-time intraday trading | Daily signal cadence matches data availability and fund strategy |
| Custom LLM training | Use frontier models with good prompting; fine-tuning is premature |
| High-frequency trading | Latency requirements incompatible with LLM-based architecture |
| Bloomberg Terminal integration | Cost prohibitive for bootstrap phase; free data stack is sufficient |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01 | Phase 1 | Pending |
| FOUND-02 | Phase 1 | Pending |
| FOUND-03 | Phase 1 | Pending |
| FOUND-04 | Phase 1 | Pending |
| FOUND-05 | Phase 1 | Pending |
| DATA-01 | Phase 2 | Pending |
| DATA-02 | Phase 2 | Pending |
| DATA-03 | Phase 2 | Pending |
| DATA-04 | Phase 2 | Pending |
| DATA-05 | Phase 2 | Pending |
| DATA-06 | Phase 2 | Pending |
| DATA-07 | Phase 2 | Pending |
| DATA-08 | Phase 2 | Pending |
| AGENT-01 | Phase 3 | Pending |
| AGENT-02 | Phase 3 | Pending |
| AGENT-03 | Phase 3 | Pending |
| AGENT-04 | Phase 3 | Pending |
| MULTI-01 | Phase 4 | Pending |
| MULTI-02 | Phase 4 | Pending |
| MULTI-03 | Phase 4 | Pending |
| MULTI-04 | Phase 4 | Pending |
| DEBATE-01 | Phase 5 | Complete |
| DEBATE-02 | Phase 5 | Complete |
| DEBATE-03 | Phase 5 | Partial (schemas + agents in 05-01/02; graph in 05-03) |
| DEBATE-04 | Phase 5 | Complete (compute_quality_score + sub-score schema, 05-02) |
| RISK-01 | Phase 6 | Complete (Phase 6 shipped 2026-04-22) |
| RISK-02 | Phase 6 | Complete (Phase 6 shipped 2026-04-22) |
| RISK-03 | Phase 6 | Complete (Phase 6 shipped 2026-04-22) |
| MEM-01 | Phase 7 | Complete (07-01 substrate + 07-03 graph wiring + 07-05 e2e; shipped 2026-04-22) |
| MEM-02 | Phase 7 | Complete (07-02 Belief schema + 07-03 memory_recall_node reads beliefs_consulted + 07-05 e2e; shipped 2026-04-22) |
| MEM-03 | Phase 7 | Complete (07-02 write_belief chokepoint + 07-03 read path + 07-04 ingest_outcome cross-req + 07-05 e2e MEM-03 x MEM-04; shipped 2026-04-22) |
| MEM-04 | Phase 7 | Complete (07-04 compute_new_confidence + RationaleOnly + ingest_outcome; 07-05 e2e write loop 72->82; shipped 2026-04-22) |
| SIG-01 | Phase 8 | Complete (08-01 FinalSignalOutput + assemble_final_signal + 08-03 output_node + 08-04 run_analysis CLI + 08-05 e2e SIG-01 no-null proof; shipped 2026-04-23) |
| SIG-02 | Phase 8 | Complete (08-02 query_portfolio_view + audit_reconstruct CLI + 08-05 e2e freshness proof; shipped 2026-04-23) |
| SIG-03 | Phase 8 | Complete (08-01 ReviewPolicy + ReviewDecision + 08-03 human_review_node interrupt + 08-04 CLI stdin reviewer + 08-05 e2e APPROVED/REJECTED resume proof + VETOED-never-reaches-review; shipped 2026-04-23) |
| SIG-04 | Phase 8 | Complete (08-02 reconstruct_audit_trail + 08-03 review_store_node append-only + 08-05 e2e 3-way review_policy_sha equality + audit reconstruction proof; shipped 2026-04-23) |

**Coverage:**
- v1 requirements: 36 total
- Mapped to phases: 36
- Unmapped: 0

---
*Requirements defined: 2026-04-11*
*Last updated: 2026-04-11 after roadmap creation (traceability verified, 36/36 mapped)*
