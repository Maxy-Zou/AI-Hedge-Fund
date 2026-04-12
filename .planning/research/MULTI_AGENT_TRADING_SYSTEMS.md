# Multi-Agent LLM Trading Systems: Domain Research

**Researched:** 2026-04-11
**Overall Confidence:** MEDIUM (strong academic coverage, production data is limited and self-reported)

---

## Paper/System Survey

### Academic Systems (2023-2026)

| Name | Year | Architecture | Key Insight | Limitation | Confidence |
|------|------|-------------|-------------|------------|------------|
| **TradingGPT** | 2023 | Multi-agent with layered memory, distinct agent characters, LLM debate | First to show agent debate improves sentiment classification and trading robustness | Early work; limited eval period; no risk-adjusted metrics reported | MEDIUM |
| **FinMem** | 2023-24 | Single-agent, 3 modules (Profiling, Layered Memory, Decision-making), working memory + layered long-term memory | Layered memory mimicking human cognition (working memory, long-term with decay) significantly outperforms flat memory | Single-agent; heavy cognitive load on one LLM; static investment beliefs; underperformed Buy & Hold on some datasets | HIGH |
| **FinGPT** | 2023-24 | Open-source financial LLM with LoRA fine-tuning, real-time data pipeline | Demonstrated sub-$300 fine-tuning cost via LoRA/QLoRA; data-centric approach solves temporal sensitivity | Not a trading agent per se -- a fine-tuned LLM for sentiment/NLP tasks; not multi-agent | HIGH |
| **FinAgent** | 2024 | Single-agent, multimodal (text+numerical+visual), tool-augmented, dual-level reflection, diversified memory retrieval | 36% average improvement over 12 baselines across 6 datasets; tool augmentation is critical for domain knowledge injection | Single-agent bottleneck; vulnerable to feature leakage via imprecise RAG timestamps; KDD'24 eval on only 5 stocks + 1 crypto | HIGH |
| **FinCon** | 2024 | Multi-agent, manager-analyst hierarchy, conceptual verbal reinforcement, selective knowledge propagation | NeurIPS 2024. Manager-analyst hierarchy reduces unnecessary peer-to-peer communication costs while improving decision quality. Self-critiquing mechanism updates "investment beliefs" episodically | Requires careful tuning of belief update frequency; unclear how beliefs transfer across market regimes | HIGH |
| **StockAgent** | 2024 | Multi-agent simulation (independent agent entities), 4-phase event-driven simulation (Initial, Trading, Post-Trading, Special Events) | Demonstrated how external factors (news events, earnings) systematically impact agent trading behavior and price dynamics | Simulation-focused; more about market microstructure understanding than alpha generation; limited real-world applicability | MEDIUM |
| **TradingAgents** | 2024-25 | 5-layer architecture: UI, orchestration, multi-agent teams, LLM providers, data access. 4 parallel analysts + bull/bear debate + risk management + trader | Best open-source implementation of a trading firm simulation. Structured bull/bear debate produces balanced analysis. Dual-model strategy (deep_think_llm + quick_think_llm) | Eval period only June-Nov 2024 (6 months); no transaction cost modeling in initial version; requires multiple expensive LLM calls per decision | HIGH |
| **HedgeAgents** | 2025 | Fund manager + 3 asset-class specialists (Bitcoin, Dow Jones, Forex), 3 conference types (Budget Allocation, Experience Sharing, Extreme Market) | 70% annualized / 400% over 3 years claimed. Conference-based coordination handles regime changes via Extreme Market Conference | Multi-asset focus (crypto+equities+forex) rather than deep equity research; 400% claim needs heavy scrutiny for look-ahead/survivorship bias; only 4 agents total | LOW |
| **AlphaAgents** | 2025 | 3 agents (Fundamental via RAG on 10-K/10-Q, Sentiment via news/analyst ratings, Valuation via price metrics), structured debate, risk tolerance parameter | BlackRock-affiliated research. Explicit risk tolerance modeling. Multi-agent collaboration outperforms single-agent in both risk-neutral and risk-averse scenarios | Only 4-month backtest window; relies on RAG faithfulness (evaluated via Arize Phoenix); limited stock universe | MEDIUM |
| **SAS (Structured Adversarial Synthesis)** | 2025 | 3-phase: Intelligence Distillation (CIO Briefing), Adversarial Debate (5-act protocol), Final Synthesis | Five-act adversarial debate protocol on earnings calls specifically. GPT-4o judge preferred SAS output over single-agent and unstructured debate | Evaluated by LLM judge, not by trading performance; research-output quality rather than alpha generation | MEDIUM |
| **Trading-R1** | 2025 | Single-agent with RL fine-tuning, 3-stage curriculum (thesis organization, evidence-based reasoning, volatility-aware decisions) | Tauric Research. Combines LLM reasoning with RL reward signals. 3-stage "easy-to-hard" curriculum produces structured, citation-grounded theses | Requires 100k-sample training corpus; fine-tuning approach means model is frozen between updates; 14 equities over 18 months | MEDIUM |
| **FLAG-Trader** | 2025 | LLM as RL policy network with gradient-based optimization, parameter-efficient fine-tuning | Unified architecture where LLM IS the policy -- not just generating signals for a separate system. Trading rewards directly optimize LLM weights | Blurs interpretability; hard to audit "why" decisions are made; fine-tuning required per asset class | MEDIUM |

### Production Systems (Known)

| Entity | What's Known | Architecture Details | Status | Confidence |
|--------|-------------|---------------------|--------|------------|
| **Bridgewater AIA Labs** | $2B+ fund trading real capital. 17-person team led by CTO Aaron Linsky. Goal: replicate Ray Dalio's macro process end-to-end by machine | AWS EKS deployment. Amazon Bedrock as LLM abstraction layer (Claude via Anthropic, plus other models). "Millions of 80th-percentile associates working in parallel." Uses multiple LLM providers via Bedrock | Live, managing billions, claiming "unique alpha" | MEDIUM (self-reported, no independent audit) |
| **D.E. Shaw** | LLM Gateway brokers calls to 24+ external models. DocLab tags confidence scores and audit hashes on every retrieval | PII stripping before model calls. Confidence scoring. Audit trail on all retrievals. NOT autonomous trading -- augments human PMs | Production tooling, not autonomous agent trading | MEDIUM |
| **Citadel** | AI Assistant scans transcripts/filings, summarizes brokerage research, flags risks. Daily workflow for equities team | Equity chatbot for research augmentation. Aborted Seattle AI lab -- "top AI scientists could not win trust of discretionary PMs worried about black-box signals and IP leakage" | Production research tool, NOT autonomous trading | MEDIUM |
| **Man Group** | Alpha Assistant can draft but NOT execute trades. Human oversight as governance principle | Research augmentation only. Deliberate human-in-the-loop constraint | Production research tool with explicit no-execution policy | MEDIUM |
| **virattt/ai-hedge-fund** (open source) | 43k+ GitHub stars, 18 specialized agents via LangGraph. React frontend with visual workflow editor | Three-tier: React frontend + FastAPI backend + external data. 12 famous-investor-persona agents + 6 technical agents. Shared AgentState dictionary through LangGraph workflow. 13 LLM provider support | Open-source proof of concept, NOT trading real money | HIGH (code is public) |

**Critical observation:** No production hedge fund is running fully autonomous multi-agent LLM trading. Every real-money deployment maintains human oversight. The firms furthest along (Bridgewater) use LLMs as research augmentation at massive scale, not as autonomous decision-makers.

---

## Architecture Patterns That Work

### 1. Manager-Analyst Hierarchy (RECOMMENDED)

**What:** Central manager agent coordinates specialized analyst agents. Each analyst has a narrow domain (fundamental, sentiment, technical, macro). Manager synthesizes and resolves conflicts.

**Evidence:** FinCon (NeurIPS 2024) demonstrated this reduces communication overhead vs. peer-to-peer while improving decision quality. Mirrors real trading firm structure. AlphaAgents (BlackRock-affiliated) validated the pattern for equity portfolio construction.

**Why it works:** Prevents the "too many cooks" problem. Manager acts as information bottleneck, filtering noise. Selective knowledge propagation means only relevant insights flow to the right nodes. Maps cleanly to org charts that investors understand.

**Implementation pattern:**
```
Manager Agent
  |-- Fundamental Analyst (RAG over filings, 10-K, 10-Q)
  |-- Sentiment Analyst (news, social media, earnings calls)
  |-- Technical Analyst (price data, indicators)
  |-- Macro Analyst (rates, sector rotation, macro indicators)
  |
  v
Risk Manager (veto power, position sizing)
  |
  v
Portfolio Decision
```

### 2. Adversarial Bull/Bear Debate (RECOMMENDED)

**What:** After analysts produce their reports, bull and bear advocate agents argue opposing sides of the thesis. A synthesis agent (or the manager) resolves the debate into a final recommendation.

**Evidence:** TradingAgents demonstrated the pattern with documented improvement in cumulative returns and Sharpe ratio. SAS showed a structured 5-act debate protocol produces higher quality analysis (preferred by GPT-4o judge over single-agent). TradingGPT pioneered the approach showing improved sentiment classification.

**Why it works:** Directly counters confirmation bias -- the single biggest failure mode in investment analysis. Forces explicit consideration of downside risks. Produces self-documenting thesis vs. antithesis that serves as audit trail for investors.

**Critical detail:** The debate must be STRUCTURED (fixed rounds, specific claim/rebuttal format) not free-form. Free-form debate degrades into repetition or one side dominating. SAS's 5-act protocol is the best documented structure.

### 3. Layered Memory with Decay (RECOMMENDED for learning)

**What:** Working memory (current session) + short-term memory (recent trades/analyses) + long-term memory (investment beliefs, learned patterns). Information promotes or demotes between layers based on relevance and recency.

**Evidence:** FinMem demonstrated layered memory outperforms flat memory for trading. FinAgent's dual-level reflection + diversified retrieval produced 36% improvement. FinCon's "conceptual verbal reinforcement" is essentially a belief-update mechanism for long-term memory.

**Why it works:** Financial data is inherently temporal. Recent earnings matter more than year-old earnings. But structural insights ("this company always sandbagging guidance") should persist. Decay prevents stale information from contaminating current decisions.

**Implementation approach:**
```
Working Memory: Current analysis session context (prompt context)
Short-term Memory: Recent N days of analyses, trade outcomes, market events (vector store with recency weighting)
Long-term Memory: Investment beliefs, sector models, learned patterns (structured store, updated episodically via self-critique)
```

### 4. Tool Augmentation (ESSENTIAL, not optional)

**What:** Agents have access to structured tools (financial data APIs, calculators, technical indicator libraries) rather than trying to reason about numbers from raw text.

**Evidence:** FinAgent showed tool augmentation is what separates good performance from mediocre. Raw LLM numerical reasoning is unreliable. Every successful system provides calculator tools, data retrieval tools, and domain-specific analysis tools.

**Why it works:** LLMs are bad at math. Period. Financial analysis requires precise calculations (P/E ratios, DCF models, position sizing). Offloading computation to deterministic tools while using LLMs for qualitative reasoning plays to each component's strengths.

### 5. Dual-Model Strategy (RECOMMENDED for cost control)

**What:** Use a powerful model (Opus, GPT-4+) for complex reasoning (thesis generation, debate, synthesis) and a fast/cheap model (Haiku, GPT-4o-mini) for routine tasks (data extraction, formatting, simple classification).

**Evidence:** TradingAgents implements this as deep_think_llm + quick_think_llm. Practical necessity given that a full multi-agent pipeline can cost $1-5+ per trading decision with a single expensive model.

---

## Architecture Patterns That Don't Work

### 1. Single-Agent Monolith (AVOID)

**What:** One LLM agent tries to do everything -- read filings, analyze sentiment, compute technicals, make decisions.

**Why it fails:** Cognitive overload. FinMem and early FinAgent papers document that placing heavy multi-source processing demands on a single agent degrades performance. Context window gets consumed by data rather than reasoning. No adversarial check on conclusions.

**Evidence:** FinCon paper explicitly identifies "static or minimal investment belief systems" and "weak filtering of market noise" as single-agent limitations. AlphaAgents shows multi-agent consistently outperforms single-agent in both risk-neutral and risk-averse scenarios.

### 2. Unstructured Peer-to-Peer Agent Communication (AVOID)

**What:** All agents talk to all agents in a free-form chat.

**Why it fails:** Communication overhead grows quadratically. Agents repeat information. Conversations drift. No clear decision authority. MAST taxonomy identifies "inter-agent misalignment" as one of 3 major failure categories, with specific modes including task derailment and inconsistent state.

**Evidence:** FinCon specifically reduced unnecessary peer-to-peer communication by adopting a hierarchy instead. MAST-Data (1600+ annotated traces) shows inter-agent misalignment is pervasive across all 7 frameworks studied.

### 3. LLM-as-Calculator (AVOID)

**What:** Asking the LLM to perform financial calculations (DCF, ratio analysis, statistical measures) directly in its reasoning.

**Why it fails:** LLMs hallucinate numbers. They will confidently produce incorrect P/E ratios, wrong compound growth rates, and fabricated statistics. In financial contexts this is catastrophic -- a hallucinated number feeds into a real trade.

**Evidence:** The financial hallucination research documents specific cases: LLMs stating a 10-to-1 stock split when the document says 6-to-1. Industry reports estimate $250M+ annually in hallucination-related losses.

### 4. Autonomous Execution Without Human Oversight (AVOID at this stage)

**What:** Agent makes decision, agent executes trade, no human review.

**Why it fails:** Every production hedge fund maintains human oversight. Citadel's aborted Seattle lab showed that even with top AI talent, discretionary PMs rejected black-box signals. Man Group's explicit policy: "can draft but not execute." The trust problem is not technical -- it is organizational and regulatory.

**Evidence:** Zero confirmed cases of a hedge fund running fully autonomous LLM-based trading in production without human veto capability.

### 5. Training-Data-Period Backtesting (CRITICAL PITFALL)

**What:** Evaluating an LLM's trading ability on events that occurred before its training data cutoff.

**Why it fails:** The LLM may have MEMORIZED the outcome rather than reasoning from evidence. This is the most insidious form of look-ahead bias, and it is unique to LLM-based systems.

**Evidence:** FINSABER benchmark (KDD 2026) showed that "previously reported LLM advantages deteriorate significantly under broader cross-section and longer-term evaluation." LLM strategies are "overly conservative in bull markets, underperforming passive benchmarks, and overly aggressive in bear markets, incurring heavy losses." On truly out-of-sample data, LLMs consistently fail to beat buy-and-hold.

---

## Memory and Learning Approaches

### Approaches Documented in Literature

| System | Memory Type | Storage | Update Mechanism | Learning? |
|--------|------------|---------|-----------------|-----------|
| **FinMem** | Layered (working + long-term with tiers) | In-memory during session | Summarization, observation, reflection operations on working memory; promotion/demotion between long-term tiers | Adjustable "cognitive span" -- how far back to look. Not true cross-session learning |
| **FinCon** | Conceptual beliefs + analyst reports | Structured store | Episodic self-critique updates "investment beliefs" via verbal reinforcement. Selective propagation to relevant nodes | YES -- beliefs update based on outcomes. Closest to real learning in the literature |
| **FinAgent** | Dual-level reflection + diversified retrieval | Vector store | First level: immediate reflection on current data. Second level: retrieval of similar past scenarios | Retrieval-based -- "learning" by finding analogous past situations, not by updating weights |
| **TradingAgents** | Agent memory per session | Session state | Each agent maintains context within a session via LangGraph state dictionary | NO -- no cross-session learning in current implementation |
| **HedgeAgents** | Experience sharing conferences | Unspecified | "Agents formulate investment experience comparable to human experts" via Experience Sharing Conference | Claimed but poorly documented |
| **A-MEM (general)** | Zettelkasten-style interconnected notes | Structured store with links | Dynamic indexing; new memories generate comprehensive notes with contextual descriptions, keywords, tags | YES -- creates knowledge graphs. Not finance-specific but applicable |

### Recommended Approach for Our System

**Three-tier memory architecture:**

1. **Session Memory (Working):** Current analysis context. Lives in LLM context window + structured scratchpad. Discarded after session. Cost: free (just prompt tokens).

2. **Episodic Memory (Short-term):** Recent analyses, trade outcomes, market events. Stored in PostgreSQL (we already have it) with vector embeddings for similarity search. Retention: 90 days active, then archived. Retrieval: by ticker, sector, thesis theme, date range.

3. **Belief Memory (Long-term):** Investment theses, sector models, learned patterns about specific companies. Structured documents (not embeddings) updated via explicit self-critique cycles after trade outcomes are known. This is where the system actually "learns." Format: structured YAML/JSON with thesis, evidence, confidence, last-updated, outcome-if-known.

**Key design decision:** Belief Memory should be human-readable and human-editable. This is both a feature (transparency for investors) and a safety mechanism (humans can correct systematic errors). Do NOT make beliefs opaque embeddings.

---

## Production Reality Check

### What Actually Works in Production (as of 2026)

1. **LLM-augmented research at scale:** Bridgewater's "millions of associates" approach. Use LLMs to read, summarize, and extract structured data from massive document sets (filings, transcripts, news). This is proven, deployed, managing billions.

2. **Sentiment signal extraction:** FinGPT and similar fine-tuned models extract sentiment from news/social media with useful accuracy. This is the most commoditized and validated use case.

3. **Document analysis and summarization:** Citadel, D.E. Shaw, Man Group all use LLMs to process research reports, filings, transcripts. Not controversial, clearly works.

4. **Structured thesis generation:** LLMs can produce well-structured investment theses given the right data and prompts. The quality is "80th percentile associate" level (Bridgewater's claim) -- useful but not exceptional.

### What Is Genuinely Uncertain

1. **Alpha generation from LLM signals alone:** The FINSABER study (KDD 2026, the most rigorous long-term evaluation to date) found that LLM-based strategies "do not overcome the Efficient Market Hypothesis in realistic conditions" and that "prior gains stemmed from survivorship and look-ahead biases rather than genuine market inefficiency." This is the single most important finding in this research.

2. **Multi-agent coordination overhead vs. benefit:** MAST taxonomy shows that despite enthusiasm, "performance gains on popular benchmarks are often minimal compared to single agent frameworks or even simple baselines such as best-of-N sampling." The coordination overhead may not pay for itself.

3. **Cross-regime generalization:** LLM strategies are "overly conservative in bull markets and overly aggressive in bear markets." No system has demonstrated consistent performance across multiple market regimes in rigorous out-of-sample testing.

### What Is Hype

1. **"400% returns over 3 years" claims (HedgeAgents and similar):** Almost certainly contaminated by look-ahead bias, survivorship bias, or both. No transaction costs, no slippage, cherry-picked evaluation periods.

2. **"Outperforms 12 baselines" (common in papers):** Baselines are often weak (simple moving average crossover, basic buy-and-hold). Outperforming a bad baseline is not the same as generating alpha.

3. **"LLM agents can replace human traders":** Zero evidence from production. Every firm maintaining human oversight. The industry trend is augmentation, not replacement.

4. **"RL fine-tuned LLMs will solve trading":** FLAG-Trader and Trading-R1 show promise but require massive training corpora, are fragile to regime change, and destroy the interpretability that is the main advantage of LLM-based systems.

### The Honest Assessment

**LLMs are genuinely useful for:** Processing unstructured financial data (filings, transcripts, news) into structured signals at a scale and speed humans cannot match. Generating well-reasoned investment theses. Adversarial critique of those theses.

**LLMs are NOT proven to:** Generate consistent alpha from their signals alone. Replace quantitative factor models. Perform reliable financial calculations without tool augmentation. Maintain performance across market regimes.

**The viable path for a new fund:** Use multi-agent LLMs for research and thesis generation (this works). Combine LLM-generated qualitative signals with traditional quantitative signals (hedges against LLM failure modes). Maintain human oversight on execution (regulatory and practical necessity). Be honest with investors: the LLM is a research tool that scales human-quality analysis, not an oracle.

---

## Key Takeaways for Our System

### Architecture Recommendation

Adopt a **Manager-Analyst Hierarchy with Adversarial Debate**, the pattern with the strongest evidence base:

```
                    [Research Manager]
                    /       |        \
         [Fundamental]  [Sentiment]  [Technical/Quant]
                    \       |        /
                  [Bull Advocate Agent]
                          vs.
                  [Bear Advocate Agent]
                          |
                   [Thesis Synthesis]
                          |
                   [Risk Manager] (veto power)
                          |
                   [Human Review] <-- NON-NEGOTIABLE
                          |
                   [Signal Output]
```

### Critical Design Decisions

1. **Tool-first, LLM-second for quantitative work.** LLMs should NEVER compute financial ratios, run backtests, or calculate position sizes directly. They orchestrate tools that do this deterministically.

2. **Strict temporal controls on all data.** Every piece of data entering the system must have a timestamp. RAG retrieval must filter by "available as of analysis date." This prevents the most common form of look-ahead bias in LLM systems.

3. **Structured debate protocol, not free-form.** Adopt a fixed-round format (SAS's 5-act protocol is a good starting point): (1) Initial thesis, (2) Counter-thesis, (3) Rebuttal, (4) Final arguments, (5) Synthesis.

4. **Dual-model strategy from day one.** Expensive model (Claude Opus) for thesis generation and debate. Cheap model (Claude Haiku) for data extraction, formatting, classification. Otherwise costs spiral.

5. **Belief Memory must be human-readable.** Investment beliefs that the system learns over time should be stored as structured documents that a human PM can read, edit, and override. Not opaque embeddings.

6. **Do NOT claim autonomous alpha generation to investors.** Position as: "LLM-powered research at scale that augments human decision-making and produces institutional-quality thesis documentation." This is honest, defensible, and actually what works in production.

### Phased Implementation Strategy

**Phase 1 -- Foundation (single-agent research pipeline):**
- One research agent that can read filings, extract data, generate a structured thesis
- Tool augmentation for financial calculations
- PostgreSQL-backed episodic memory
- This alone is useful and testable

**Phase 2 -- Multi-agent specialization:**
- Split into Fundamental + Sentiment + Technical analysts
- Manager agent for synthesis
- Shared state via structured message passing (not free-form chat)

**Phase 3 -- Adversarial critique:**
- Add Bull/Bear advocate agents
- Structured debate protocol
- Thesis quality scoring

**Phase 4 -- Memory and learning:**
- Belief Memory with episodic self-critique
- Cross-session learning from trade outcomes
- Pattern recognition across historical analyses

**Phase 5 -- Signal integration and backtesting:**
- Combine LLM-generated qualitative signals with quantitative factors
- Rigorous out-of-sample backtesting (FINSABER methodology)
- Transaction cost and slippage modeling

### Framework Choice

**LangGraph** for the multi-agent orchestration layer. Rationale:
- Most production-ready of available frameworks (steepest learning curve but most control)
- Graph-based state machines map naturally to the analyst-debate-synthesis pipeline
- Durable execution and human-in-the-loop support built in
- The virattt/ai-hedge-fund (43k+ stars) proves the pattern works with LangGraph specifically
- Alternatives considered: CrewAI (too opinionated, less control), AutoGen (conversational focus doesn't match our structured pipeline)

### Data Sources to Prioritize

For US equities analysis, prioritize these (all free or low-cost):
- **SEC EDGAR** (free): 10-K, 10-Q, 8-K filings -- the gold standard for fundamental analysis
- **yfinance** (free): Price data, basic fundamentals -- already in our stack
- **Earnings call transcripts**: SEC EDGAR (free, as 8-K exhibits) or EarningsAPI / Finnhub (low cost)
- **Financial news**: Finnhub, or NewsAPI for broader coverage
- **SEC EDGAR XBRL**: Structured financial statement data -- already built in our existing AI Washing pipeline

### What to Defer or Skip

- **RL fine-tuning of LLMs** (FLAG-Trader, Trading-R1): Requires massive data, destroys interpretability, and is research-grade not production-grade. Revisit in 12+ months.
- **Crypto/forex multi-asset** (HedgeAgents pattern): Focus on US equities first. Multi-asset adds complexity without clear benefit at our stage.
- **Visual/chart analysis** (FinAgent's multimodal approach): Marginal benefit vs. complexity. Technical analysis via computed indicators (tool augmentation) is more reliable than LLM chart reading.
- **Fully autonomous execution**: No human-in-the-loop removal for at least the first year. Regulatory, trust, and practical reasons.

---

## Sources

### Academic Papers
- [FinMem: Layered Memory LLM Trading Agent](https://arxiv.org/abs/2311.13743) - ICLR 2024, IEEE
- [TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138) - Tauric Research, 2024-25
- [FinCon: Synthesized LLM Multi-Agent System](https://arxiv.org/abs/2407.06567) - NeurIPS 2024
- [FinAgent: Multimodal Foundation Agent for Financial Trading](https://arxiv.org/abs/2402.18485) - KDD 2024
- [HedgeAgents: Balanced-aware Multi-agent Financial Trading](https://arxiv.org/abs/2502.13165) - ACM Web Conference 2025
- [AlphaAgents: LLM Multi-Agents for Equity Portfolio Construction](https://arxiv.org/abs/2508.11152) - BlackRock, 2025
- [Structured Adversarial Synthesis](https://aclanthology.org/2025.finnlp-2.21/) - EMNLP FinNLP Workshop 2025
- [Trading-R1: Financial Trading with LLM Reasoning via RL](https://arxiv.org/abs/2509.11420) - Tauric Research, 2025
- [FLAG-Trader: Fusion LLM-Agent with Gradient-based RL](https://aclanthology.org/2025.findings-acl.716/) - ACL 2025
- [TradingGPT: Multi-Agent System with Layered Memory](https://arxiv.org/abs/2309.03736) - 2023
- [StockAgent: LLM Stock Trading in Simulated Environments](https://arxiv.org/abs/2407.18957) - 2024
- [FinGPT: Open-Source Financial Large Language Models](https://arxiv.org/abs/2306.06031) - 2023-24
- [Can LLM-based Financial Investing Strategies Outperform the Market in Long Run?](https://arxiv.org/abs/2505.07078) - KDD 2026 (FINSABER)
- [Why Do Multi-Agent LLM Systems Fail? (MAST)](https://arxiv.org/abs/2503.13657) - UC Berkeley, 2025
- [Toward Reliable Evaluation of LLM-Based Financial Multi-Agent Systems](https://arxiv.org/html/2603.27539v1) - 2026
- [Orchestration Framework: From Algorithmic to Agentic Trading](https://arxiv.org/html/2512.02227v1) - 2025
- [Deficiency of LLMs in Finance: Hallucination](https://arxiv.org/abs/2311.15548) - 2023
- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) - 2025

### Production Systems
- [Bridgewater AIA Labs](https://www.bridgewater.com/aia-labs)
- [Bridgewater $2B ML Fund](https://fortune.com/2024/07/01/bridgewater-2-billion-fund-machine-learning-decision-making-openai-anthropic-perplexity/)
- [Citadel AI Assistant](https://www.ai-street.co/p/citadel-reveals-ai-assistant)
- [AI Use by Hedge Funds (Resonanz Capital analysis)](https://resonanzcapital.com/insights/ai-use-by-hedge-funds-made-tangible-from-lego-bots-to-alpha-assistants)

### Open-Source Implementations
- [virattt/ai-hedge-fund (43k+ stars)](https://github.com/virattt/ai-hedge-fund)
- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
- [AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT)

### Evaluation and Failure Analysis
- [MAST Taxonomy (UC Berkeley)](https://sky.cs.berkeley.edu/project/mast/)
- [MAST Dataset (GitHub)](https://github.com/multi-agent-systems-failure-taxonomy/MAST)
- [FINSABER Benchmark (GitHub)](https://github.com/waylonli/FINSABER)
- [Multi-Agent Architecture Patterns (TrueFoundry)](https://www.truefoundry.com/blog/multi-agent-architecture)
