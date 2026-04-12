# Feature Landscape

**Domain:** Multi-agent LLM financial research and trading system
**Researched:** 2026-04-11

## Table Stakes

Features users (fund investors, internal team) expect. Missing = system feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Investment hypothesis generation | Core value prop -- agents produce trade ideas from data | High | Claude + SEC filing tools + market data |
| Evidence gathering from multiple sources | Investors expect data-driven theses, not hallucinated opinions | High | SEC filings, earnings, news, price data |
| Adversarial thesis critique | Differentiates from simple LLM wrapper; reduces confirmation bias | High | Debate protocol between thesis/antithesis agents |
| Quantitative signal output | Fund needs actionable signals, not prose | Medium | Typed schema: ticker, direction, confidence, timeframe |
| Risk assessment per signal | Cannot trade without risk-adjusted sizing | Medium | Position limits, correlation, drawdown thresholds |
| Audit trail of agent reasoning | Regulatory and investor due diligence requirement | Medium | Full trace of agent steps, tool calls, intermediate reasoning |
| Backtest integration | Investors demand historical validation before capital allocation | Medium | Feed signals into existing backtest framework |
| Cost monitoring and budget caps | Multi-agent LLM = expensive; must be operationally sustainable | Medium | Per-agent and per-pipeline token budgets |

## Differentiators

Features that set system apart from other AI-powered funds and simple LLM wrappers.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Multi-model routing | Use Haiku for extraction, Sonnet for analysis, Opus for deep reasoning -- optimizes cost/quality | Medium | 60-87% cost reduction via task-appropriate model selection |
| Human-in-the-loop review | Analyst can inspect/modify agent reasoning before signal execution | Medium | LangGraph interrupt() with state inspection |
| Prompt caching for document analysis | Analyze same 10-K multiple times (different angles) at 90% reduced cost | Low | Anthropic API cache_control parameter |
| Cross-strategy agent reuse | Same evidence-gathering agents serve multiple strategies | Medium | Modular agent design, strategy-agnostic tool layer |
| Time-travel debugging | Rewind agent state to any checkpoint for investigation | Low | LangGraph checkpoint feature -- free with framework |
| Real-time signal streaming | Stream partial results as agents complete (don't wait for full pipeline) | Medium | LangGraph streaming + async node execution |
| Agent persona calibration | Tune agent aggressiveness, risk tolerance, analytical style per strategy | Medium | Parameterized agent instructions, A/B testable |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Autonomous trading execution | Legal/regulatory risk; fund must have human approval for trades | Human-in-the-loop approval gate before any order |
| Real-time market data agents | Daily signal cadence doesn't need real-time; adds massive complexity | Daily batch processing with cached market data |
| Custom LLM fine-tuning | Expensive, maintenance-heavy, and Claude/GPT improve faster than you can fine-tune | Use prompt engineering, few-shot examples, and structured output |
| Web scraping agents | Legal risk, fragile, unreliable data quality | Use official APIs (SEC EDGAR, yfinance, news APIs with licenses) |
| Natural language trading interface | Chatbot UX is wrong for a quantitative fund; adds ambiguity | CLI and programmatic API for signal consumption |
| Agent memory across analysis sessions | Accumulated stale context causes hallucination drift; each analysis should be fresh | Stateless per-analysis runs; persistent data in PostgreSQL only |
| Fancy UI dashboard for agents | Engineering time wasted on UI instead of signal quality | CLI output + Langfuse traces for agent monitoring |

## Feature Dependencies

```
Hypothesis Generation --> Evidence Gathering (hypotheses need evidence)
Evidence Gathering --> Adversarial Critique (critique needs evidence to evaluate)
Adversarial Critique --> Signal Generation (signals emerge from survived theses)
Signal Generation --> Risk Assessment (raw signals need risk-adjusted sizing)
Risk Assessment --> Backtest Integration (risk-adjusted signals feed backtester)

Cost Monitoring --> All agents (must be built into framework from start)
Audit Trail --> All agents (must be built into framework from start)

Human-in-the-Loop --> Signal Generation (review gate before signal output)
Model Routing --> All agents (cost optimization applies everywhere)
```

## MVP Recommendation

Prioritize:
1. **Hypothesis generation from SEC filings** -- proves the core agent loop works
2. **Evidence gathering (market data + filings)** -- makes hypotheses data-grounded
3. **Quantitative signal output** -- produces the actionable output the fund needs
4. **Cost monitoring** -- must be present from day one; multi-agent systems are expensive
5. **Audit trail** -- must be present from day one; investor and compliance requirement

Defer:
- **Adversarial critique**: Add after single-agent pipeline proves value (Phase 3)
- **Multi-model routing**: Optimize after baseline costs are measured (Phase 3)
- **Human-in-the-loop**: Add when signals approach production use (Phase 5)
- **Cross-strategy reuse**: Design for it from start, but don't build until second strategy exists
- **Backtest integration**: Phase 4, after signal schema is stable

## Sources

- [TradingAgents agent roles and workflow](https://github.com/TauricResearch/TradingAgents)
- [virattt/ai-hedge-fund 3-stage architecture](https://github.com/virattt/ai-hedge-fund)
- [Multi-agent cost optimization benchmarks](https://arxiv.org/html/2603.22651)
- [LangGraph human-in-the-loop documentation](https://docs.langchain.com/oss/python/langgraph/persistence)
