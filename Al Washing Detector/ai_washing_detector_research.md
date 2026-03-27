# AI Washing Detector — Research & Data Sources for Claude Code

## 1. Thesis Summary

**Core idea:** Many mid-cap public companies are claiming AI adoption to boost investor confidence, but the reality behind those claims is often thin. This tool aims to quantify the gap between what companies *say* about AI and what they *do* — then flag companies where that gap is widest as short candidates.

**Why mid-caps?** Less analyst scrutiny = larger information asymmetry. More likely to overstate AI claims without being called out.

**Key term:** "AI Washing" — overstating or misrepresenting AI capabilities to attract investors. Analogous to greenwashing. The SEC has already brought enforcement actions against this practice (see Section 7).

---

## 2. Signal Categories to Track

### Signal 1: Job Postings vs. AI Claims (Primary Signal)

**What to look for:**
- Company announces "major AI initiative" but has zero open ML/AI roles
- Company posts AI roles but they stay open for 6+ months (can't attract talent = probably not serious)
- AI job postings are only in marketing/comms ("AI Strategy Lead") rather than engineering ("ML Engineer," "MLOps," "Data Scientist," "AI Infrastructure")
- Ratio of AI roles to total engineering roles is tiny despite big AI claims
- Job descriptions use vague AI buzzwords vs. specific technical requirements (PyTorch, TensorFlow, transformer architectures, CUDA, etc.)

**Data sources:**
- **TheirStack (theirstack.com)** — Job Postings API aggregating LinkedIn, Indeed, Glassdoor, etc. Returns structured data with company info, job descriptions, posting dates. REST API with JSON responses. Has company financial data attached (revenue, employee count, stock exchange). Tracks job postings historically. **Best for: bulk tracking of job postings by company.**
- **Revelio Labs (reveliolabs.com)** — Premium workforce intelligence. 4.1B job postings from 6.6M companies. COSMOS dataset covers postings from 440K employer websites + major job boards. Also tracks employee headcount, inflows/outflows, skills. Investors are a primary customer segment. Has an Employee-Linked Patents dataset (launched June 2025). **Best for: institutional-grade workforce data, but expensive.**
- **Mantiks LinkedIn Jobs API (mantiks.io)** — Credit-based LinkedIn job scraping. Track postings by company, role, location over time. Webhooks for new postings. Good for competitive intelligence.
- **Lix API (lix-it.com)** — LinkedIn Job Posting Enrichment endpoint. Returns full job listing details including description, metadata, posting dates.
- **GitHub: linkedin-jobs-api** — Open source Node.js package for scraping public LinkedIn job listings. Free but rate-limited.
- **People Data Labs** — B2B data provider with employment records and job postings API.

**Fulfillment tracking approach:**
1. Snapshot a company's AI-related job postings weekly
2. Track how long they stay open (> 90 days = red flag)
3. Track if they're eventually filled (check LinkedIn for new hires with matching titles)
4. Compare posting volume against earnings call AI claims

### Signal 2: SEC Filing Analysis (10-K, 10-Q, 8-K)

**What to look for:**
- Frequency of "AI," "artificial intelligence," "machine learning," "deep learning" mentions over time in 10-K filings
- Whether AI mention growth correlates with R&D spending growth (if mentions 5x but R&D flat = red flag)
- Vagueness of AI claims in risk factors vs. substantive technical descriptions
- Compare "AI" mentions in Management Discussion & Analysis vs. actual CapEx/R&D line items

**Data sources:**
- **SEC EDGAR API (data.sec.gov)** — Free, no API key needed. RESTful JSON APIs for submissions, XBRL company facts, filing full text. Updated in real-time. Key endpoints:
  - `data.sec.gov/submissions/CIK##########.json` — filing history by company
  - `data.sec.gov/api/xbrl/companyfacts/CIK##########.json` — all financial facts
  - Full-text search via EDGAR Full-Text Search (efts.sec.gov)
- **edgartools (Python)** — `pip install edgartools`. Parses filings into Python objects. MIT license, free, no API keys. Has MCP server for Claude integration. Covers 20+ filing types with typed DataFrames. **Recommended as primary SEC tool.**
- **sec-api (Python)** — `pip install sec-api`. 18M+ filings, full-text search, section extractor for 10-K/10-Q (can pull just MD&A section, risk factors, etc.). Requires API key (free tier available). Stream API for real-time new filings.
- **Apify SEC EDGAR scrapers** — Multiple actors available for scraping EDGAR. Pay-per-event pricing. MCP-ready.

**Analysis approach:**
1. Pull 10-K filings for target companies over past 3-5 years
2. Count AI/ML keyword frequency by section (MD&A, Risk Factors, Business Description)
3. Extract R&D expense from XBRL data
4. Compute ratio: AI_mention_growth / R&D_spend_growth
5. Flag companies where mentions grew significantly but R&D didn't

### Signal 3: Patent Filings

**What to look for:**
- Companies claiming AI innovation but filing zero AI-related patents
- Patent filing trend (declining while AI claims increase = red flag)
- Quality of patents — are they genuinely ML/AI or just traditional software rebranded?

**Data sources:**
- **USPTO PatentsView API (api.patentsview.org)** — Free, no API key, no registration. 8M+ patents searchable. Query by assignee (company), CPC classification codes, abstract text. Returns patent number, title, date, assignee, abstract. AI-relevant CPC codes: G06N (machine learning), G06F18 (pattern recognition).
  ```
  POST https://api.patentsview.org/patents/query
  Body: {
    "q": {"_and": [
      {"_text_any": {"patent_abstract": "machine learning artificial intelligence"}},
      {"assignee_organization": "COMPANY_NAME"}
    ]},
    "f": ["patent_number","patent_title","patent_date","assignee_organization"],
    "s": [{"patent_date": "desc"}]
  }
  ```
- **USPTO Open Data Portal (data.uspto.gov)** — Bulk data downloads and search APIs for patent file wrappers.
- **Google Patents (via Apify)** — Scraper covering 100+ patent offices worldwide (USPTO, EPO, WIPO, CNIPA, JPO).
- **Lens.org** — Free platform integrating patent data with scholarly literature. Has APIs for programmatic access. Good for cross-referencing patents with academic publications.

### Signal 4: Earnings Call Transcript Analysis

**What to look for:**
- Executives using AI buzzwords without specifics ("AI-powered," "leveraging AI") vs. concrete details ("we deployed a transformer model for demand forecasting that reduced error by 15%")
- Increase in AI mentions on calls without analyst follow-up questions about specifics
- Sentiment mismatch: overly optimistic AI framing vs. flat/declining technical KPIs
- CEO vs. CTO language gap (CEO hypes AI, CTO on the same call is vague or absent)

**Data sources:**
- **EarningsCall API** — Python library for fetching earnings call transcripts. Can get transcripts for S&P 500 and beyond. GitHub: EarningsCall/earnings-call-analysis.
- **Financial Modeling Prep (FMP)** — Real-time earnings call transcripts API. Covers most public companies.
- **API Ninjas Earnings Transcript API** — Returns transcript split by speaker, with built-in sentiment scoring (-1 to +1). Simple REST API with API key.
- **Apify: Earnings Call Transcript & Sentiment Scraper** — Processes video/audio into structured JSON with speaker diarization and sentiment.

**NLP approach (for Claude Code to implement):**
- Use FinBERT (pre-trained on financial text) for sentiment analysis
- Build a custom classifier trained on earnings calls to detect "sugar-coated" vs. substantive AI claims
- Key insight from research: executives systematically sugarcoat bad news on calls, so general-purpose sentiment models underperform. A model trained specifically on earnings call "corporatese" would be more accurate.

### Signal 5: GitHub / Open Source Activity

**What to look for:**
- Does the company have a GitHub organization with ML/AI repos?
- Are they contributing to open-source ML projects?
- Are repos active or abandoned?
- Do repos contain real ML code or just marketing READMEs?

**Data sources:**
- **GitHub REST API v3** — 5,000 requests/hour authenticated. Search repos by org, query commit history, check contributor activity.
  - `GET /orgs/{org}/repos` — list company repos
  - `GET /repos/{owner}/{repo}/stats/contributors` — contributor activity
  - Search API: `GET /search/repositories?q=org:{company}+topic:machine-learning`
- **GitHub GraphQL API v4** — More flexible queries. `contributionsCollection` object for detailed metrics.

### Signal 6: Cloud/Compute Spending Indicators

**What to look for:**
- Companies claiming AI adoption but not increasing cloud/compute spending
- No disclosed relationships with GPU providers (NVIDIA, AMD) or cloud AI services (AWS SageMaker, Azure ML, GCP Vertex AI)
- IT spending flat while AI claims ramp

**Data sources:**
- XBRL financial data from SEC filings (CapEx, R&D, IT spending line items)
- Earnings call transcripts (mentions of cloud partnerships, GPU procurement)
- 8-K filings (material contracts with cloud/compute providers)

### Signal 7: Conference & Research Presence

**What to look for:**
- Company employees publishing at NeurIPS, ICML, AAAI, ACL, CVPR
- Company sponsoring AI conferences vs. just attending
- Technical blog posts with real depth vs. marketing fluff

**Data sources:**
- **Semantic Scholar API** — Free. Search academic papers by author affiliation.
- **arXiv API** — Search preprints by author/affiliation.
- **Conference proceedings** — Most major ML conferences publish proceedings online.

---

## 3. Scoring Framework (Suggested)

Each company gets scored on a 0-100 "AI Washing Risk Score":

| Signal | Weight | Scoring Logic |
|--------|--------|---------------|
| Job Posting Mismatch | 25% | High AI claims + few/no AI hires + long time-to-fill |
| SEC Filing Mismatch | 20% | AI mention growth >> R&D growth |
| Patent Gap | 15% | Zero or declining AI patents despite AI claims |
| Earnings Call Vagueness | 20% | High buzzword density + low specificity + analyst skepticism |
| GitHub Inactivity | 10% | No org repos, no ML code, no open-source contributions |
| Compute Spending Gap | 10% | Flat CapEx/cloud spend despite AI narrative |

**Score interpretation:**
- 0-30: Likely genuine AI adoption
- 30-60: Mixed signals, worth monitoring
- 60-80: Significant AI washing risk
- 80-100: Strong short candidate

---

## 4. Target Universe: Identifying Mid-Cap Companies Making AI Claims

**Approach to build the watchlist:**
1. Use SEC EDGAR full-text search to find all mid-cap (market cap $2B-$10B) companies with high "AI/ML" mention frequency in recent 10-K filings
2. Filter for companies where AI mentions increased >100% year-over-year
3. Cross-reference against sector (non-tech companies claiming AI are higher risk)
4. Monitor earnings call transcripts for new AI announcements
5. Track 8-K filings for press releases mentioning AI initiatives

**Useful screener:** EDGAR full-text search for filings containing "artificial intelligence" or "machine learning" filed in the last 12 months, filtered by filer size (mid-cap).

---

## 5. Regulatory Backdrop & Catalysts

### SEC Enforcement Precedent

The SEC has already established "AI washing" as an enforcement priority:

- **March 2024: Delphia (USA) Inc.** — Settled for $225,000. Claimed to use AI/ML to analyze client data for investment decisions. Never actually did. Charged with negligent fraud under Advisers Act.
- **March 2024: Global Predictions Inc.** — Settled for $175,000. Falsely claimed to be the "first regulated AI financial advisor" with "expert AI driven forecasts." Had no substantiation.
- **February 2024: Rockwell Capital Management** — Fraud case for claiming AI-driven crypto trading. Raised $1.2M on false AI claims.
- **June 2024: Joonko (CEO Ilit Raz)** — Charged with defrauding investors of $21M using falsified AI recruitment capabilities.
- **April 2025: Nate Inc. (CEO Albert Saniger)** — FBI charges for attempting to defraud investors of $40M. Claimed app was "fully automated based on AI" — actual automation was minimal.

### SEC CETU (Cybersecurity and Emerging Technologies Unit)
The SEC's newly constituted CETU has stated that "rooting out" AI washing fraud is an "immediate priority." This creates a regulatory catalyst — SEC enforcement actions can trigger stock price drops.

### FTC Activity
- **September 2024: "Operation AI Comply"** — FTC crackdown on misleading AI claims.
- Apple, Google, Microsoft, Samsung have been revising AI marketing claims under BBB probe.

### Key Catalyst for Shorts
When the SEC or FTC takes action against a company for AI washing, it typically triggers:
1. Immediate stock price drop (news reaction)
2. Analyst downgrades
3. Investor lawsuits (see: Tucker v. Apple, June 2025)
4. Sustained valuation reset as "AI premium" is removed

---

## 6. Technical Architecture Suggestions for Claude Code

### Data Pipeline
```
[Data Ingestion] → [Storage] → [Analysis Engine] → [Scoring] → [Dashboard]

Ingestion:
  - Cron jobs pulling job postings (daily)
  - SEC filing monitor (real-time via Stream API or daily batch)
  - Patent API queries (weekly)
  - Earnings transcript pulls (quarterly, triggered by earnings calendar)
  - GitHub org activity checks (weekly)

Storage:
  - PostgreSQL for structured data (company profiles, scores, time series)
  - S3/local storage for raw filings and transcripts
  - Redis for caching API responses

Analysis:
  - NLP pipeline for filing/transcript analysis (FinBERT or Claude API)
  - Keyword frequency analysis
  - Time series comparison (claims vs. actions)
  - Anomaly detection for score changes

Output:
  - Company scorecards with breakdown by signal
  - Watchlist with alerts for score changes
  - Historical trend charts
```

### Recommended Tech Stack
- **Language:** Python (best ecosystem for NLP + financial data)
- **SEC Data:** edgartools library (`pip install edgartools`)
- **Patents:** Direct PatentsView API calls (no library needed, free REST API)
- **Job Data:** TheirStack API or build scraper using linkedin-jobs-api
- **NLP:** FinBERT via HuggingFace transformers, or Claude API for more nuanced analysis
- **Database:** PostgreSQL + SQLAlchemy
- **Dashboard:** Streamlit or Dash for rapid prototyping
- **Scheduling:** APScheduler or Celery for data pipeline automation

### Key Python Libraries
```
edgartools          # SEC EDGAR filing parsing
transformers        # FinBERT and other NLP models
requests            # API calls
beautifulsoup4      # HTML parsing for filings
pandas              # Data manipulation
sqlalchemy          # Database ORM
streamlit           # Dashboard
plotly              # Charting
schedule            # Job scheduling
```

---

## 7. Risk Considerations for the Strategy

**Timing risk:** AI washing can persist for quarters before the market cares. Short positions bleed if the stock keeps rising on hype. Consider using options (puts) for defined risk.

**Catalyst dependency:** Without a catalyst (SEC action, earnings miss, competitor exposure), the gap may not close. Build a catalyst monitoring system.

**Borrow costs:** Mid-cap shorts can have high borrow costs. Factor this into position sizing.

**Short squeeze risk:** Mid-caps with high short interest are squeeze candidates. Monitor short interest data.

**Data quality:** Job posting data can be noisy (ghost postings, reposted roles). Need to build deduplication and validation logic.

**False positives:** Some companies may legitimately be early in AI adoption and hiring hasn't caught up yet. Use multiple signals to reduce false positive rate.

---

## 8. Related Academic & Industry Research

- **CFA Institute (June 2025):** "AI Washing: Signs, Symptoms, and Suggested Solutions" — practical questionnaire for detecting AI washing through due diligence
- **California Management Review (Dec 2024):** "AI Washing: The Cultural Traps That Lead to Exaggeration" — explores how knowledge gaps at the C-suite level enable AI washing
- **Sage Journals (2025):** "Responsible AI in Marketing: AI Booing and AI Washing Cycle of AI Mistrust" — framework for understanding the cyclical relationship between AI hype and backlash
- **Debevoise (March 2026):** "Agent Washing" — emerging variant where companies overstate AI agent capabilities. Newer evolution of AI washing worth monitoring.
- **Built In (2025-2026):** Research showing that many companies are "AI washing" layoffs — attributing financially motivated cuts to AI automation that doesn't actually exist yet. Forrester's AI Job Impact Forecast confirms this trend.

---

## 9. Quick-Start Checklist for Claude Code

1. [ ] Set up Python project with virtual environment
2. [ ] Install edgartools, set EDGAR identity
3. [ ] Build SEC filing keyword analyzer (count AI mentions per 10-K section)
4. [ ] Build R&D spending extractor from XBRL data
5. [ ] Set up PatentsView API integration
6. [ ] Build job posting tracker (start with TheirStack or LinkedIn scraping)
7. [ ] Build earnings call transcript fetcher
8. [ ] Implement NLP pipeline for vagueness detection
9. [ ] Create scoring engine combining all signals
10. [ ] Build Streamlit dashboard for monitoring
11. [ ] Set up cron jobs for automated data refresh
12. [ ] Create alert system for score changes > threshold
