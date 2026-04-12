# Networking Research — AI-Native Hedge Fund

Compiled 2026-04-11. Verify current roles and contact details before outreach.

---

## Table of Contents

1. [AI x Finance Founders](#1-ai-x-finance-founders)
2. [Quant Fund Practitioners](#2-quant-fund-practitioners)
3. [LLM-for-Finance Researchers](#3-llm-for-finance-researchers)
4. [Skeptics and Critics](#4-skeptics-and-critics)
5. [SEC / Compliance Experts](#5-sec--compliance-experts)
6. [Data Vendors and Infrastructure](#6-data-vendors-and-infrastructure)
7. [AI Agent Infrastructure Builders](#7-ai-agent-infrastructure-builders)
8. [Allocators and Fund-of-Funds](#8-allocators-and-fund-of-funds)
9. [YC Alumni in Fintech/Quant](#9-yc-alumni-in-fintechquant)
10. [Conferences and Events](#10-conferences-and-events)
11. [Online Communities](#11-online-communities)
12. [Podcasts](#12-podcasts)
13. [Cold Outreach Templates](#13-cold-outreach-templates)
14. [Priority Actions](#14-priority-actions)

---

## 1. AI x Finance Founders

| Name | Role / Company | Why Relevant | What to Learn | Reach |
|------|---------------|--------------|---------------|-------|
| **Richard Craib** | Founder & CEO, Numerai | Pioneer of "hedge fund as platform" — crowdsources ML models from data scientists, stakes with NMR token. Closest analog to multi-agent signal aggregation. | Signal aggregation from multiple models, tournament-based model evaluation, auditable AI investment process. | X: @richardcraib. Podcasts: Lex Fridman, Bankless, Flirting with Models. Very responsive on X. |
| **Ben Fishman** | Co-founder, Composer (acquired by Titan 2023) | Built AI layer on systematic trading strategies. Demonstrates product-ification of quant strategies. | Go-to-market for AI trading tools, simplifying quant pipelines, what worked vs. didn't in retail quant. | LinkedIn. Fintech podcast appearances. |
| **Yoshi Yokokawa** | Co-founder & CEO, Alpaca (YC W16) | API-first brokerage-as-a-service. Infrastructure many AI trading startups build on. $100M+ raised. | Brokerage infrastructure, regulatory requirements for algo trading, API design for financial systems. | X: @yaboratory. LinkedIn. Developer conferences. |
| **Daniel Nadler** | Founder, Kensho (acquired by S&P Global for ~$550M) | Built NLP systems for financial event analysis, earnings calls, macro data. Directly overlaps with SEC filing analysis pipeline. | NLP for financial documents at scale, what acquirers value, positioning AI analytics vs. AI trading. | LinkedIn. Harvard/MIT talks. Academic publications. |
| **Alex Lu** | Founder & CEO, Kavout | AI-powered stock analysis using "Kai Score" (ML-generated ratings from multiple data sources). Operating since ~2015. | Signal generation and packaging, presenting AI signals with disclaimers, longevity challenges. | LinkedIn. Fintech podcasts. |
| **Caesar Sengupta** | Founder & CEO, Arta Finance | Former Google VP (led Google Pay). Raised $90M+ for AI-first "digital family office." | Framing AI-in-finance for investors, fundraising strategy, regulatory navigation for wealth management. | X: @caesars. LinkedIn. TechCrunch/Bloomberg interviews. |
| **Yin Luo** | Vice Chairman & Head of Quant Research, Wolfe Research | One of the most respected quant researchers on Wall Street. Vocal about LLM applications in finance, published on GPT/Claude for financial analysis. | What institutional quant researchers think about LLM investing, where they see alpha vs. noise, rigorous backtesting. | LinkedIn. Conferences: Battle of the Quants, QuantMinds. |

---

## 2. Quant Fund Practitioners

| Name | Role / Affiliation | Why Relevant | What to Learn | Reach |
|------|-------------------|--------------|---------------|-------|
| **Marcos Lopez de Prado** | Professor at Cornell, former Head of ML at AQR | Author of *Advances in Financial Machine Learning*. Invented meta-labeling, triple-barrier method, combinatorial purged CV. The definitive authority on ML in quant finance. | Proper cross-validation for financial time series, feature importance, bet sizing, why most ML backtests are wrong. | SSRN papers. Frequent conference keynotes. LinkedIn. Podcasts: Top Traders Unplugged, Flirting with Models. |
| **Robert Carver** | Former Head of Fixed Income, Man AHL. Independent trader & author. | Unusually transparent about what actually works in systematic trading. Books: *Systematic Trading*, *Advanced Futures Trading Strategies*. | Position sizing, portfolio construction, when adding complexity (e.g., LLM agents) helps vs. hurts. | Blog: systematicmoney.com. X: @investingidiocy. Very responsive on X. |
| **Ernest Chan** | Managing Member, QTS Capital Management. Former IBM researcher. | Runs a real quant fund and writes openly about strategy development. Books: *Quantitative Trading*, *Machine Trading*. | Evaluating real alpha vs. data-mined noise, practical pipeline design, when ML adds value vs. simpler models. | X: @chanep. Blog: epchan.blogspot.com. Podcasts: Top Traders Unplugged. |
| **Rishi Narang** | Founding Principal, T2AM (fund of funds for quant/systematic). Author of *Inside the Black Box*. | Has evaluated hundreds of quant funds as an allocator. Knows what separates survivors from failures. | How allocators evaluate quant strategies, due diligence process, red flags LPs watch for. | X: @rishiknarang. Podcasts: Flirting with Models, Top Traders Unplugged. LinkedIn. |
| **Emanuel Derman** | Professor at Columbia, former Head of Quant Strategies at Goldman Sachs | One of the original quant practitioners. Deep thinker on philosophy of financial models. Author of *My Life as a Quant*. | Limits of quantitative models, distinction between models in physics vs. finance — critical for anyone building an "AI hedge fund." | Books. Columbia lectures (some on YouTube). LinkedIn. |
| **Andrew Ang** | Head of Quantitative Investing, BlackRock (~$100B+ in systematic strategies) | Runs one of the largest systematic investment operations. BlackRock's AlphaAgents paper reports through his org. | Factor investing at scale, gap between academic research and production, how institutions deploy quant strategies. | LinkedIn. BlackRock research pubs. Conference keynotes (CFA Institute, JOIM). |
| **Matthew Dixon** | Professor at IIT, former quant at Deutsche Bank & Lehman Brothers | Author of *Machine Learning in Finance*. Bridges academia and practice. | Practical ML techniques that work in finance vs. hype, feature engineering, model validation, specific failure modes. | Papers on arXiv/SSRN. X: @maboroshi_mf. Conference talks. |
| **Gary Kazantsev** | Head of ML Engineering, Bloomberg CTO Office | Leads Bloomberg's ML research for financial applications. Bloomberg released BloombergGPT. | State of the art in financial NLP, what Bloomberg sees as valuable vs. noise in AI-for-finance. | Speaks at KDD, NeurIPS Financial AI workshops. LinkedIn. |

---

## 3. LLM-for-Finance Researchers

| Name | Role / Affiliation | Why Relevant | What to Learn | Reach |
|------|-------------------|--------------|---------------|-------|
| **Xiao-Yang Liu** | Professor at RPI. Creator of FinRL and FinGPT. | Built the most widely-used open-source frameworks for RL and LLM in finance. FinGPT is the open-source counterpart to BloombergGPT. | Open-source LLM fine-tuning for financial tasks, what works when adapting general LLMs to finance, benchmarks. | GitHub: AI4Finance-Foundation. X: @XiaoYangLiu10. arXiv papers. |
| **Shijie Wu / BloombergGPT team** | Researchers at Bloomberg | Built BloombergGPT (50B params trained on financial corpus). Established benchmarks for LLM financial understanding. | How domain-specific pretraining affects financial task performance, what financial NLP tasks LLMs are good at. | Paper: arXiv 2303.17564. LinkedIn. Bloomberg AI blog. |
| **Yue Zhang / FinCon team** | Westlake/Zhejiang University | FinCon (NeurIPS 2024) validated the manager-analyst hierarchy + adversarial debate pattern your architecture uses. Direct architectural validation. | Multi-agent coordination patterns, how structured debate improves decision quality, which agent topologies work. | NeurIPS proceedings. arXiv paper. |
| **Alejandro Lopez-Lira** | Professor, University of Florida | Published "Can ChatGPT Forecast Stock Price Movements?" — one of the most cited early papers on LLM stock prediction. | Whether LLM sentiment actually has alpha, methodology for testing LLM predictions, signal decay. | SSRN papers. X: @alexlopezlira. Conference talks. |
| **Qianqian Xie / FINSABER team** | Likely Yale / FinNLP community | FINSABER (KDD 2026) shows LLM strategies don't beat buy-and-hold on rigorous evaluation. The most important skeptical result for your project. | Exactly how and why LLM trading strategies fail under rigorous backtesting, evaluation pitfalls to avoid. | KDD 2026 proceedings. arXiv paper. |
| **Zhiyu Li / FinMem team** | Academic researchers | FinMem implements layered memory (session, episodic, belief) for trading agents — directly relevant to your three-tier memory architecture. | Memory architecture design for financial LLM agents, episodic memory with retention/decay. | arXiv paper. |
| **Markus Leippold** | Professor, University of Zurich. Director, Swiss Finance Institute. | Prolific researcher on NLP/LLM applications in finance including climate finance NLP and sentiment analysis. | Rigorous methodology for evaluating LLM signals, what textual features actually predict returns. | SSRN/arXiv papers. University of Zurich page. |

---

## 4. Skeptics and Critics

These conversations will sharpen your thesis and help avoid known failure modes.

| Name | Why Relevant | Key Work to Read First | Reach |
|------|-------------|----------------------|-------|
| **Marcos Lopez de Prado** | "The 7 Reasons Most Machine Learning Funds Fail" — every failure mode applies to LLM agents. | SSRN paper + Chapter 11 of *Advances in Financial Machine Learning*. | See above. |
| **Campbell Harvey** | Duke professor, former AFA president. Showed most published "factors" are false discoveries via multiple testing framework. | "...and the Cross-Section of Expected Returns" (SSRN). | X: @camaborsa. Podcasts: Rational Reminder. Duke faculty page. |
| **Andrew Lo** | MIT professor. Adaptive Markets Hypothesis — market efficiency varies over time, strategies that work decay as markets adapt. | *Adaptive Markets* (book). | SSRN papers. MIT faculty page. Podcasts: Odd Lots. LinkedIn. |
| **Nassim Nicholas Taleb** | Most prominent critic of quantitative overconfidence in finance. Fat tails, model fragility, why backtest-winners blow up. | *The Black Swan*, *Fooled by Randomness*. | X: @nntaleb (extremely active). YouTube lectures. Combative but rigorous. |
| **Gary Marcus** | Most vocal critic of LLM reliability. Hallucination, brittleness, lack of reasoning — all apply to LLM financial agents. | Substack: "The Road to AI We Can Trust." | X: @GaryMarcus. Books. Podcast circuit. |
| **Rob Harvey** | Co-founder of Man Numeric (~$40B AUM). Speaks about difficulty of translating ML research into actual trading alpha. | Conference talks. | Conference talks (SQA, JOIM). LinkedIn. |

---

## 5. SEC / Compliance Experts

| Name | Role / Company | Why Relevant | What to Learn | Reach |
|------|---------------|--------------|---------------|-------|
| **Amy Lynch** | President, FrontLine Compliance | Boutique firm serving emerging hedge fund managers. More accessible and cost-effective than BigLaw for early-stage. | Practical compliance program setup pre-launch, mock SEC exam prep, what infrastructure to build before taking capital. | frontlinecompliance.com. LinkedIn. Frequent speaker at hedge fund startup events. |
| **Val Dahiya** | Partner, Seward & Kissel (Investment Management Group) | Arguably the most specialized hedge fund law firm. Formed hundreds of funds. | Fund formation timeline and costs, optimal legal structure for AI-driven fund, seed deal structures. | sewardkissel.com. LinkedIn. They actively court emerging managers. |
| **Gurbir Grewal** | Former Director, SEC Division of Enforcement (2021-2024) | Oversaw Delphia ($225K) and Global Predictions ($175K) AI washing enforcement actions in March 2024. Now in private practice. | What specifically triggered those cases, where the line is for AI claims, how to position honestly. | LinkedIn. Conference circuit (Securities Enforcement Forum, PLI). |
| **Barry Barbash** | Partner, Willkie Farr & Gallagher; former Director, SEC Division of Investment Management | Led the SEC division overseeing investment advisers. Deep institutional knowledge. | How SEC evaluates AI/algorithmic fund disclosures, what "adequate disclosure" means, common first-time registrant pitfalls. | LinkedIn. Willkie Farr website. Industry conferences (ICI, SIFMA). |
| **Scott Bauguess** | Former SEC Chief Economist; now at Georgetown/consulting | Led SEC's data analytics division. Understands how SEC evaluates quant strategies from the inside. | How SEC staff evaluate quant fund disclosures, what documentation they expect, risk model disclosure requirements. | LinkedIn. Georgetown faculty page. Academic conferences. |
| **Hester Peirce** | SEC Commissioner ("Crypto Mom") | Innovation-friendly regulator. Public statements signal where regulatory winds are blowing. | AI regulation trajectory, potential safe harbors for AI-driven funds. | Speeches on sec.gov. Not for direct advisory, but her public positions are a regulatory weather vane. |

---

## 6. Data Vendors and Infrastructure

| Name | Role / Company | Why Relevant | What to Learn | Reach |
|------|---------------|--------------|---------------|-------|
| **Abraham Thomas** | Co-Founder, Quandl (acquired by Nasdaq, now Nasdaq Data Link) | Built one of the foundational alt data platforms for quant finance. Now angel investing. | Alt data evaluation frameworks, signal vs. noise in data, pricing for emerging managers. | LinkedIn. X. Writes about data and quant finance. Potentially interested in AI fund approaches. |
| **Lamar Wilson** | CEO & Co-Founder, Polygon.io | Your first planned paid data upgrade ($29/mo). Real-time and historical equity APIs for developers. | API reliability at scale, what data quant funds consume most, startup/academic pricing. | LinkedIn. Polygon community Slack/Discord. Developer-friendly founders. |
| **Jonathan Morgan** | Creator, edgartools (open source) | Your Priority 1 data source for SEC filings. Python library wrapping SEC EDGAR. | XBRL parsing edge cases, CompanyFacts API reliability, bulk filing retrieval best practices. | GitHub: dgunning/edgartools. Engage by contributing or filing detailed issues. |
| **Mike Dickey** | CEO, Finnhub | Your Priority 5 data source (60 req/min free tier). News, sentiment, real-time quotes. | Free tier limitations, bulk data for backtesting, sentiment methodology, what other quant funds use Finnhub for. | finnhub.io. LinkedIn. Small company — founders responsive to serious users. |
| **Darius Dale** | Founder, 42 Macro | Former Bridgewater analyst. Built macro data platform. | Which free data sources are sufficient for early-stage quant research, where paid data actually adds alpha. | 42macro.com. LinkedIn. X: @42macro. Active on fintwit. |
| **Jens Nordvig** | Founder, Exante Data | AI-driven macro data analytics for institutional investors. Similar hybrid AI+data approach. | Productizing AI-driven financial analysis, institutional expectations, data pipeline architecture. | LinkedIn. exantedata.com. Bloomberg/CNBC appearances. |

---

## 7. AI Agent Infrastructure Builders

| Name | Role / Company | Why Relevant | What to Learn | Reach |
|------|---------------|--------------|---------------|-------|
| **Harrison Chase** | Co-Founder & CEO, LangChain | LangGraph (your orchestration layer) is his product. Primary architect of the framework your pipeline runs on. | LangGraph best practices for multi-agent, checkpointing strategies, human-in-the-loop patterns, roadmap. | X: @hwchase17. LangChain Discord. blog.langchain.dev. Very active publicly. |
| **Nuno Campos** | Lead Engineer, LangGraph | Primary technical lead for LangGraph. Builds the graph execution engine. | Low-level architecture decisions, performance optimization, debugging state machines, parallel agent execution. | GitHub: nuno-campos. LangChain Discord (#langgraph). Very responsive on GitHub. |
| **Samuel Colvin** | Creator, Pydantic / PydanticAI | Your agent logic layer. Created both Pydantic (validation) and PydanticAI (agent framework). | PydanticAI agent patterns for finance, dependency injection, structured output validation, LangGraph integration. | GitHub: samuelcolvin. X: @samuel_colvin. pydantic.dev. Very active in OSS. |
| **Max Deichmann** | Co-Founder & CEO, Langfuse | Your observability layer. Open-source, self-hosted traces, cost tracking, latency monitoring. | Production observability for multi-agent, cost tracking per agent run, self-hosted deployment. | LinkedIn. langfuse.com. GitHub. Langfuse Discord. |
| **Alex Albert** | Head of Developer Relations, Anthropic | Your entire LLM layer runs on Claude. Primary interface between Anthropic and developers. | Model selection for financial tasks, token optimization, prompt engineering for structured analysis, startup credits. | LinkedIn. X: @alexalbert__. Anthropic Discord. |
| **Amanda Askell** | Prompt Engineering Lead, Anthropic | Leads prompt engineering research. Your agents need carefully crafted prompts for analysis, debate, and synthesis. | Advanced prompting for financial domain, structured output techniques, adversarial patterns for bull/bear debate, reducing hallucination. | LinkedIn. X. Published research. |

---

## 8. Allocators and Fund-of-Funds

| Name | Role / Company | Why Relevant | What to Learn | Reach |
|------|---------------|--------------|---------------|-------|
| **Donald Steinbrugge** | Founder & CEO, Agecroft Partners | One of the most prominent hedge fund marketing/capital introduction consultants. Annual surveys on allocator preferences. | What allocators look for in first-time managers, minimum track record, how to position AI-native vs. traditional quant. | agecroft.com. LinkedIn. Publishes free research. Speaks at nearly every hedge fund conference. |
| **Rishi Narang** | Founding Principal, T2AM | Fund-of-funds focused on quant/systematic managers. Also listed in Practitioners (dual role). | How allocators evaluate quant strategies, due diligence process, common rejection reasons. | X: @rishiknarang. LinkedIn. |
| **Brad Alford** | Founder, Alpha Capital Management | Fund-of-funds that explicitly invests in emerging managers. One of the few who looks at pre-$100M AUM. | What makes an emerging manager investable, minimum operational infrastructure, first-time allocation process. | LinkedIn. alphacapitalmanagement.com. Emerging manager conferences. |
| **Michael Oliver Weinberg** | Former CIO, Protege Partners & APG. Now at Columbia Business School. | Ran one of the most famous emerging manager programs (Protege Partners — the Buffett bet firm). | Institutional perspective on what makes emerging quant managers investable, common first-time mistakes. | LinkedIn. Columbia Business School. Events: GAIM, Context Summits. |
| **Cameron Joyce** | Head of Research, Preqin (now part of BlackRock) | Tracks alternative asset allocations globally. Publishes research on allocator preferences. | Current state of hedge fund fundraising, which allocator types are open to emerging managers. | LinkedIn. Preqin research publications. Alt investment conferences. |
| **Alina Trigub** | Founder, SAMO Financial | Capital introduction and fund consulting for emerging managers. Accessible entry point. | Practical fundraising roadmap, investor deck construction, fee norms for emerging AI funds. | samofinancial.com. LinkedIn. Hosts webinars for emerging managers. |

---

## 9. YC Alumni in Fintech/Quant

**Note:** YC has historically been less active in pure quant trading — most YC fintech is payments, lending, insurance, or infrastructure. This is a positioning opportunity: you could be *the* YC company in AI-native quant.

| Name | Company | YC Batch | Status | Relevance |
|------|---------|----------|--------|-----------|
| **Yoshi Yokokawa** | Alpaca (brokerage-as-a-service) | W16 | Active, $100M+ raised | API-first brokerage infrastructure |
| **Karan Moorjani** | Kalshi (prediction market exchange) | S19 | Active, CFTC-regulated | Young founder navigating financial regulation. How YC thinks about regulated fintech. X: @karanmoorjani |
| **Raghu Yarlagadda** | FalconX (institutional crypto trading) | S18 | Active, valued at $8B at peak | Institutional trading infrastructure, algorithmic execution |
| **Brandon Arvanaghi** | Meow (corporate treasury/yield) | W22 | Active | How to frame simple financial products for YC |
| **Sam Hodges** | Funding Circle (YC S12) → Vouch Insurance (YC S19) | S12, S19 | Active (Vouch). Funding Circle IPO'd on LSE. | Repeat YC fintech founder. ML for credit scoring — AI-in-finance positioning. |

**YC partners with fintech focus to study:**
- **Dalton Caldwell** — Managing Director, does fintech office hours
- **Brad Flora** — YC partner, fintech focus

---

## 10. Conferences and Events

| Event | When | Where | Cost | Why Go |
|-------|------|-------|------|--------|
| **Battle of the Quants** | Spring + Fall editions | NYC | $1,500-$2,500 | Premier quant finance event. Direct access to PMs, researchers, allocators. |
| **NeurIPS** | December 2026 | Rotates (recent: Vancouver) | $500-$1,000 + travel | FinCon was published here. Finance workshops are where your people are. Focus on workshop days. |
| **ICML** | July 2026 | Rotates | $500-$1,000 + travel | ML for Finance workshop. Co-author a paper if possible. |
| **Finovate Fall** | September 2026 | NYC | $1,500-$2,000 | Fintech demo event. Apply for a demo spot — 7 min on stage > 100 cold emails. |
| **Y Combinator Startup School** | Ongoing cohorts | Online | Free | Access YC network pre-application. Find other fintech founders. |
| **TradeTech / Trading Show** | Spring (London), Fall (US) | London / US | $1,000-$2,500 | Institutional trading tech. Look for "emerging managers" or "startup showcase" tracks. |
| **Hedge Fund Association / Emerging Manager Forums** | Various | NYC, Chicago | $200-$500 | Service providers (legal, prime brokerage) + allocators who seed early funds. |
| **QuantCon / Quant Finance Conference** | Spring/Summer | NYC or virtual | $200-$800 | Algo/systematic strategy community. Submit a talk proposal on LLM agents. |
| **AI & Big Data in Finance** | May/June | London (hybrid) | $500-$1,200 | Explicitly AI + financial services. Hands-on workshops have smaller groups. |
| **Local meetups** | Monthly | NYC, SF, London, Chicago | Free-$20 | Lowest barrier. Attend 3+ times. Give a lightning talk. Check Meetup.com, Lu.ma. |

---

## 11. Online Communities

| Community | Platform | Activity | Why Join |
|-----------|----------|----------|----------|
| **r/algotrading** | Reddit (500K+ members) | Very active | Technical feedback on backtesting, data pipelines, tools. Search before posting. |
| **r/quant** | Reddit (100K+) | Active | More professional. Factor models, risk management. Occasional posts from top firms. |
| **LangChain / LangGraph Discord** | Discord | Very active | Your technical home base. Share what you're building — LangChain team features use cases. |
| **QuantConnect Community** | Forum + Discord | Active | Backtesting framework community. Data handling, look-ahead bias, strategy validation. |
| **Hacker News** | news.ycombinator.com | Extremely active | YC partners read HN. A "Show HN" about your multi-agent system could supplement your YC app. |
| **Wilmott Forums** | Web forum | Moderate (high quality) | Quant professionals and academics. Serious practitioners. Good for finding advisors. |
| **EliteTrader Forums** | Web forum | Active (since late 1990s) | "Automated Trading" and "Professional Trading" subforums have real practitioners. Good reality check. |
| **Twitter/X FinTwit** | X | Very active | Follow: @chanep, @investingidiocy, @rishiknarang, @alexlopezlira, @camaborsa, @nntaleb, @GaryMarcus. Build in public. |
| **Langfuse Discord** | Discord | Active | Your observability layer community. Direct access to founders. |
| **Emerging Manager Groups** | LinkedIn groups, private Slacks | Moderate (curated) | Other first-time fund managers. Ask fund lawyers for introductions to private channels. |

---

## 12. Podcasts

| Podcast | Host | Why Listen |
|---------|------|-----------|
| **Flirting with Models** | Corey Hoffstein (Newfound Research) | Deep technical quant conversations. Corey is active on X and responsive. Engage before reaching out. |
| **Top Traders Unplugged** | Niels Kaastrup-Larsen | Long-running systematic/quant focus. "Systematic Investor" series. Guests are often approachable. |
| **Chat With Traders** | Aaron Fifield | Frequently features quant and systematic traders. Active community. |
| **Invest Like the Best** | Patrick O'Shaughnessy | From a quant background. Guests discuss tech-driven investing. Listener base includes allocators. His firm's venture arm (Positive Sum) invests in fintech. |
| **Odd Lots** | Joe Weisenthal, Tracy Alloway (Bloomberg) | Market structure, macro, tech-meets-markets. Hosts are well-connected and responsive on X. |
| **Machine Learning Street Talk** | Tim Scarfe, Keith Duggar | ML-focused with increasing finance coverage. Has covered LLM agents and multi-agent systems. |
| **Lex Fridman Podcast** (select episodes) | Lex Fridman | Jim Simons, Ray Dalio episodes. AI researcher episodes often apply to multi-agent systems. |

---

## 13. Cold Outreach Templates

### Template A — To a Quant PM or Researcher

> **Subject:** Your [specific paper/talk/tweet] on [topic] -- question from a fund builder
>
> Hi [Name],
>
> I came across your [specific work]. Your point about [specific insight] resonated because I'm running into exactly that challenge.
>
> I'm building an AI-native research platform for a quantitative fund -- a multi-agent LLM pipeline where specialized agents (fundamental, sentiment, technical) generate investment theses, then adversarially debate them in a structured protocol before any signal reaches production. We're in the paper trading phase now.
>
> I'd value 15 minutes of your time to get your perspective on [one specific question]. I'm not looking for proprietary insights -- just calibration from someone who's been in production.
>
> Happy to work around your schedule. And if this isn't the right time, no worries at all.
>
> Best,
> [Your name]

### Template B — To a Fintech/AI Founder or YC Alum

> **Subject:** Fellow builder in AI + finance -- quick question
>
> Hey [Name],
>
> I've been following [company] since [specific milestone]. The way you approached [specific aspect] is something I think about a lot.
>
> Quick context: I'm a technical founder building an AI-native quant fund. The core is a multi-agent LLM system where Claude-powered agents research securities, debate each other adversarially, and produce structured investment theses. We're pre-revenue, paper trading, and planning to apply to YC.
>
> I'd love to pick your brain for 15-20 minutes on [choose one specific question].
>
> I know your time is valuable. Happy to share what I've learned about [something you can offer] in return.
>
> [Your name]

### Template C — To an Academic Researcher

> **Subject:** Your work on [specific paper] -- potential collaboration
>
> Dear [Professor/Dr. Name],
>
> I read your [specific paper]. The finding that [specific result] directly informed how we designed our system.
>
> I'm building a production multi-agent LLM pipeline for investment research. The architecture uses a structured adversarial debate protocol (inspired partly by your work) where bull and bear agents challenge each other's theses before synthesis. We're using LangGraph for orchestration and PydanticAI for typed agent definitions.
>
> I'm writing because:
> 1. I'd value your feedback on whether our debate protocol design is sound (happy to share our architecture doc)
> 2. I'm curious whether you've seen other practitioners implementing similar approaches
> 3. If there's mutual interest, I'd welcome the chance to discuss a more ongoing advisory relationship
>
> I'm respectful of your time -- even a 15-minute call or an email exchange would be genuinely helpful. And if you have students working in this area, I'd be happy to share our codebase and learnings.
>
> Best regards,
> [Your name]

---

## 14. Priority Actions

### Immediate Reads (free, highest ROI)

1. Lopez de Prado — "The 7 Reasons Most Machine Learning Funds Fail" (SSRN)
2. FINSABER paper — why LLM strategies fail under rigorous evaluation
3. FinCon paper — architectural validation for your multi-agent design
4. Campbell Harvey — "...and the Cross-Section of Expected Returns" (multiple testing framework)

### Immediate Follows (X/Twitter)

@richardcraib, @chanep, @investingidiocy, @rishiknarang, @alexlopezlira, @camaborsa, @nntaleb, @GaryMarcus, @hwchase17, @samuel_colvin

### Books (in order)

1. *Advances in Financial Machine Learning* — Lopez de Prado
2. *Systematic Trading* — Robert Carver
3. *Inside the Black Box* — Rishi Narang
4. *Models.Behaving.Badly* — Emanuel Derman

### First 5 Outreach Targets (most relevant to your stage)

1. **Richard Craib** (Numerai) — multi-model signal aggregation parallels multi-agent approach
2. **Robert Carver** — accessible, responsive, will give you the honest "does this complexity help?" answer
3. **Amy Lynch** (FrontLine Compliance) — practical compliance roadmap before YC application
4. **Harrison Chase** (LangChain) — your orchestration layer, potential startup credits, architecture advice
5. **Karan Moorjani** (Kalshi, YC S19) — young founder, regulated finance, YC path

### Sequencing by Stage

1. **Now:** AI infrastructure builders (Harrison Chase, Samuel Colvin, Langfuse team) — they help you build. Engage via OSS contributions and Discord. Zero cost.
2. **Pre-YC:** Compliance (Amy Lynch or Seward & Kissel) — one consultation gives you a regulatory roadmap for your application.
3. **Pre-YC:** Quant practitioners + skeptics (Carver, Lopez de Prado) — sharpen your thesis before you have to defend it.
4. **Post-YC:** Data vendors (Polygon, Finnhub) — negotiate startup pricing as you move from paper to live.
5. **Fundraising:** Allocators (Steinbrugge, Alford, Weinberg) — these matter when you have a track record.
