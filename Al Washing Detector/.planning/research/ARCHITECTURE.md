# Architecture Patterns

**Domain:** Autonomous Financial Signal Generation (AI Washing Detection)
**Researched:** 2026-03-27

## Recommended Architecture

This module is a **batch-oriented signal generation pipeline** that ingests data from 5+ external sources, runs NLP and quantitative analysis, produces composite scores, and writes them to a shared PostgreSQL database for consumption by downstream automated trading modules.

The architecture follows a **layered pipeline with isolated collectors** pattern, directly inspired by how quantitative hedge fund factor modeling pipelines are structured (AWS hedge fund workflow, Man Group's signal discovery systems). Each data source gets its own independent collector with its own error handling, retry logic, and cadence. Collectors feed a shared analysis layer, which feeds a scoring layer, which writes immutable snapshots to the database.

```
                    +------------------+
                    |   SCHEDULER      |
                    |  (APScheduler)   |
                    +--------+---------+
                             |
              triggers daily/weekly/quarterly runs
                             |
         +-------------------+--------------------+
         |         |         |         |          |
    +----v--+ +---v---+ +---v---+ +---v---+ +---v---+
    | SEC   | | USPTO | | GitHub| | Jobs  | | Earn  |
    | Coll. | | Coll. | | Coll. | | Coll. | | Coll. |
    +---+---+ +---+---+ +---+---+ +---+---+ +---+---+
        |         |         |         |          |
        |  each writes raw data independently    |
        |         |         |         |          |
        +----+----+----+----+----+----+----+-----+
             |              |              |
        +----v----+   +----v----+   +----v----+
        | Raw     |   | Raw     |   | Raw     |
        | Filing  |   | Patent  |   | Posting |
        | Store   |   | Store   |   | Store   |
        +---------+   +---------+   +---------+
             \              |              /
              \             |             /
         +-----v------------v-----------v------+
         |          ANALYSIS LAYER              |
         |  - NLP Pipeline (filing analysis)    |
         |  - Keyword Frequency Analyzer        |
         |  - Patent Gap Analyzer               |
         |  - Job Mismatch Analyzer             |
         |  - Earnings Vagueness Analyzer       |
         |  - GitHub Activity Analyzer          |
         |  - Compute Spend Analyzer            |
         +-------------------+-----------------+
                             |
                    per-signal scores
                             |
                  +----------v-----------+
                  |    SCORING ENGINE     |
                  |  - Signal weighting   |
                  |  - Composite score    |
                  |  - Confidence calc    |
                  +----------+-----------+
                             |
                   immutable snapshots
                             |
                  +----------v-----------+
                  |    PostgreSQL DB      |
                  |  (shared with fund)   |
                  +----------+-----------+
                             |
              consumed via SQL or Python API
                             |
              +----+---------+--------+----+
              |              |             |
         +----v----+   +----v----+   +----v----+
         | Portfolio|  | Trade   |   | Risk    |
         | Manager |  | Executor|   | Monitor |
         +---------+  +---------+   +---------+
```

### Why This Shape

1. **Isolated collectors** -- Each data source has different rate limits (SEC: 10 req/s, GitHub: 5000/hr, USPTO: unlimited), different cadences (SEC daily, patents weekly, earnings quarterly), and different failure modes. Isolating them means a USPTO outage does not block SEC ingestion.

2. **Separate analysis from collection** -- Raw data is stored before analysis. If the NLP model changes, you re-analyze stored data without re-fetching from rate-limited APIs. This is the Medallion Architecture pattern (Bronze = raw, Silver = analyzed, Gold = scored).

3. **Single scoring engine** -- All signal scores converge here. Weights are configurable. The composite score is computed from whatever signals successfully completed, with confidence adjusted based on signal availability.

4. **Immutable database writes** -- Scores are append-only snapshots. Never overwrite. This is standard practice in quantitative finance: every score is a fact at a point in time.

---

### Component Boundaries

| Component | Responsibility | Communicates With | Failure Mode |
|-----------|---------------|-------------------|--------------|
| **Scheduler** | Triggers collection and scoring runs on configured cadences | All collectors, scoring engine | If scheduler dies, no runs happen. Systemd/supervisord restarts it. |
| **SEC Collector** | Fetches 10-K/10-Q filings, XBRL financial facts from EDGAR | Raw storage (DB), rate limiter | Logs error, marks run as partial. Other collectors unaffected. |
| **USPTO Collector** | Queries PatentsView API for AI-related patents by company | Raw storage (DB) | Same isolation. Patent data updates weekly anyway. |
| **GitHub Collector** | Checks org repos, commit activity, ML-related code | Raw storage (DB) | Same isolation. Stale GitHub data is still usable. |
| **Jobs Collector** | Scrapes/fetches job posting data for target companies | Raw storage (DB) | Highest failure risk (scraping). Gracefully degrades. |
| **Earnings Collector** | Fetches earnings call transcripts when available | Raw storage (DB) | Quarterly cadence. Missing one quarter is tolerable. |
| **Analysis Layer** | Runs NLP, keyword frequency, gap calculations on raw data | Reads raw storage, writes analyzed results | Per-analyzer isolation. One failing analyzer produces a partial score. |
| **Scoring Engine** | Combines signal scores into composite AI Washing Risk Score | Reads analyzed results, writes to scores table | Adjusts confidence when signals are missing. Never blocks on partial data. |
| **Python API** | Exposes scores and raw data to other fund modules as importable functions | Reads from DB | Stateless. Downstream modules call functions or query DB directly. |

---

### Data Flow

**Stage 1: Collection (Raw Data Ingestion)**
```
External API --> Collector --> raw_{source} table in PostgreSQL
                              + raw files on disk (filings, transcripts)
```
Each collector writes to its own raw data table. Raw data is timestamped and never modified after insertion. If a collector fails mid-run, it writes what it has and logs the failure. The next run picks up where it left off.

**Stage 2: Analysis (Signal Extraction)**
```
raw_{source} table --> Analyzer --> signal_scores table
```
Analyzers read raw data and produce per-company, per-signal, per-date scores. Each analyzer is independent. The NLP pipeline for SEC filings runs separately from the patent gap calculator. Results are written as individual signal score records.

**Stage 3: Scoring (Composite Score)**
```
signal_scores table --> Scoring Engine --> composite_scores table
```
The scoring engine reads all available signal scores for a company on a given date, applies configured weights, and produces:
- Composite AI Washing Risk Score (0-100)
- Per-signal breakdown
- Confidence level (based on how many signals were available)
- A snapshot record that is immutable

**Stage 4: Consumption (Downstream Modules)**
```
composite_scores table --> Portfolio Manager (via Python API or SQL)
composite_scores table --> Trade Executor (via Python API or SQL)
composite_scores table --> Risk Monitor (via Python API or SQL)
```
Downstream modules consume scores either by importing the Python package and calling `get_latest_scores()` / `get_score_history()` or by querying PostgreSQL directly.

---

## Database Schema Patterns for Immutable Financial Time Series

Use PostgreSQL with **append-only tables** and **range partitioning by date**. This is the standard pattern for financial time series data per PostgreSQL documentation and AWS hedge fund architecture guidance.

### Core Schema Design Principles

1. **Never UPDATE or DELETE score rows.** Insert new snapshots only. This is non-negotiable for financial data -- every score is a historical fact.
2. **Partition by month** on the `scored_at` date column. Monthly partitions keep query planning fast while matching the expected data volume (~500 companies x 30 days = 15K rows/month).
3. **Store monetary values as integers** (cents). Avoids floating-point rounding issues. All financial amounts use `BIGINT` in cents.
4. **Use composite primary keys** `(company_id, signal_type, scored_at)` to enforce one score per company per signal per scoring run.
5. **Separate raw data from scored data.** Raw tables can be larger and messier. Score tables are clean and fast to query.

### Key Tables

```sql
-- Companies being tracked
CREATE TABLE companies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          VARCHAR(10) NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    cik             VARCHAR(10),           -- SEC CIK number
    market_cap_cents BIGINT,               -- stored as cents
    sector          TEXT,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata        JSONB DEFAULT '{}'
);

-- Raw data from collectors (one table per source, or use type discriminator)
CREATE TABLE raw_collections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID NOT NULL REFERENCES companies(id),
    source          TEXT NOT NULL,          -- 'sec', 'uspto', 'github', 'jobs', 'earnings'
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_date       DATE NOT NULL,          -- what date this data represents
    raw_data        JSONB NOT NULL,         -- the actual collected data
    collection_run_id UUID NOT NULL,        -- groups items from same run
    status          TEXT NOT NULL DEFAULT 'collected'  -- 'collected', 'analyzed', 'error'
) PARTITION BY RANGE (collected_at);

-- Individual signal scores (append-only)
CREATE TABLE signal_scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID NOT NULL REFERENCES companies(id),
    signal_type     TEXT NOT NULL,          -- 'sec_filing', 'patent_gap', 'job_mismatch', etc.
    score           SMALLINT NOT NULL CHECK (score BETWEEN 0 AND 100),
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    scoring_date    DATE NOT NULL,          -- the business date this score represents
    evidence        JSONB NOT NULL,         -- what data drove this score
    model_version   TEXT NOT NULL,          -- tracks which analyzer version produced this
    run_id          UUID NOT NULL
) PARTITION BY RANGE (scored_at);

-- Composite scores (append-only, the primary output)
CREATE TABLE composite_scores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID NOT NULL REFERENCES companies(id),
    score           SMALLINT NOT NULL CHECK (score BETWEEN 0 AND 100),
    confidence      REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    scoring_date    DATE NOT NULL,
    signal_breakdown JSONB NOT NULL,        -- {"sec_filing": 72, "patent_gap": 85, ...}
    signals_available INTEGER NOT NULL,     -- how many of 6 signals were computed
    weights_used    JSONB NOT NULL,         -- the weight config at time of scoring
    run_id          UUID NOT NULL
) PARTITION BY RANGE (scored_at);

-- Pipeline run metadata (for observability)
CREATE TABLE pipeline_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running', -- 'running', 'completed', 'partial', 'failed'
    collectors_status JSONB NOT NULL DEFAULT '{}',   -- {"sec": "success", "github": "failed", ...}
    companies_scored INTEGER DEFAULT 0,
    errors          JSONB DEFAULT '[]'
);

-- Partition creation (monthly)
CREATE TABLE signal_scores_2026_01 PARTITION OF signal_scores
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
-- (repeat for each month, automate via cron or migration)
```

### Query Patterns for Downstream Consumers

```sql
-- Latest composite score per company (what the trading module needs)
SELECT DISTINCT ON (company_id)
    company_id, score, confidence, signal_breakdown, scoring_date
FROM composite_scores
ORDER BY company_id, scored_at DESC;

-- Score history for a specific company (for trend analysis)
SELECT scoring_date, score, confidence, signal_breakdown
FROM composite_scores
WHERE company_id = $1
ORDER BY scoring_date DESC
LIMIT 90;  -- last 90 days

-- High-risk companies above threshold (short candidates)
SELECT DISTINCT ON (cs.company_id)
    c.ticker, c.name, cs.score, cs.confidence, cs.signal_breakdown
FROM composite_scores cs
JOIN companies c ON c.id = cs.company_id
WHERE cs.score >= 60 AND cs.confidence >= 0.6
ORDER BY cs.company_id, cs.scored_at DESC;
```

---

## Python Package Structure

Use the **src layout** with `pyproject.toml` entry points. This is the Python Packaging Authority recommendation for packages that serve as both importable libraries and standalone runners.

```
ai_washing_detector/
|-- pyproject.toml
|-- src/
|   |-- ai_washing_detector/
|       |-- __init__.py              # Public API: get_scores(), get_companies(), etc.
|       |-- __main__.py              # python -m ai_washing_detector entry point
|       |-- cli.py                   # CLI commands (run, score, collect, etc.)
|       |-- config.py                # Settings via environment variables / .env
|       |
|       |-- collectors/
|       |   |-- __init__.py
|       |   |-- base.py              # BaseCollector ABC with retry, rate limiting
|       |   |-- sec_collector.py     # SEC EDGAR collector
|       |   |-- uspto_collector.py   # USPTO PatentsView collector
|       |   |-- github_collector.py  # GitHub API collector
|       |   |-- jobs_collector.py    # Job posting collector
|       |   |-- earnings_collector.py # Earnings transcript collector
|       |
|       |-- analyzers/
|       |   |-- __init__.py
|       |   |-- base.py              # BaseAnalyzer ABC
|       |   |-- sec_analyzer.py      # Filing keyword frequency, R&D gap
|       |   |-- patent_analyzer.py   # Patent gap analysis
|       |   |-- github_analyzer.py   # Repo activity, ML code detection
|       |   |-- jobs_analyzer.py     # Job mismatch scoring
|       |   |-- earnings_analyzer.py # Vagueness scoring, NLP
|       |   |-- compute_analyzer.py  # CapEx/cloud spend gap
|       |
|       |-- scoring/
|       |   |-- __init__.py
|       |   |-- engine.py            # Composite score calculation
|       |   |-- weights.py           # Signal weight configuration
|       |   |-- confidence.py        # Confidence calculation based on available signals
|       |
|       |-- db/
|       |   |-- __init__.py
|       |   |-- models.py            # SQLAlchemy 2.0 ORM models
|       |   |-- session.py           # Session factory, connection management
|       |   |-- migrations/          # Alembic migrations
|       |   |-- queries.py           # Common query functions
|       |
|       |-- scheduling/
|       |   |-- __init__.py
|       |   |-- scheduler.py         # APScheduler configuration
|       |   |-- jobs.py              # Job definitions (daily, weekly, quarterly)
|       |
|       |-- universe/
|       |   |-- __init__.py
|       |   |-- builder.py           # Target universe identification
|       |   |-- filters.py           # Market cap, AI mention filters
|       |
|       |-- nlp/
|       |   |-- __init__.py
|       |   |-- keywords.py          # AI keyword dictionaries and matchers
|       |   |-- vagueness.py         # Vagueness vs. specificity classifier
|       |   |-- sentiment.py         # FinBERT sentiment wrapper
|       |
|       |-- api.py                   # Public Python API for other fund modules
|
|-- tests/
|   |-- unit/
|   |   |-- collectors/
|   |   |-- analyzers/
|   |   |-- scoring/
|   |-- integration/
|   |   |-- test_pipeline.py
|   |   |-- test_db.py
|   |-- conftest.py                  # Shared fixtures
|
|-- alembic.ini
|-- .env.example
```

### Why This Structure

- **src layout** prevents accidental imports of uninstalled code. You always test against the installed package.
- **Collectors, analyzers, scoring as separate subpackages** -- each has a clear boundary and can be tested independently.
- **Base classes (base.py)** in each subpackage define the interface. Adding a new data source means adding one file in `collectors/` and one in `analyzers/`, implementing the base class.
- **api.py at package root** is the public interface for other fund modules. They do `from ai_washing_detector import get_latest_scores`.

### Dual-Purpose Entry Points in pyproject.toml

```toml
[project]
name = "ai-washing-detector"
version = "0.1.0"
requires-python = ">=3.11"

[project.scripts]
ai-washing-detector = "ai_washing_detector.cli:main"

# Also supports: python -m ai_washing_detector
```

This means:
- **As standalone runner:** `ai-washing-detector run --date 2026-03-27` or `python -m ai_washing_detector`
- **As importable library:** `from ai_washing_detector.api import get_latest_scores, get_score_history`

---

## Scheduling Architecture

**Use APScheduler 3.x** (stable release). Not Celery, not Prefect, not APScheduler 4.x.

### Rationale

| Option | Verdict | Why |
|--------|---------|-----|
| APScheduler 3.x | **Use this** | In-process, no broker dependency, cron-style scheduling, PostgreSQL job store for persistence. Perfect for a single-server daily batch system. |
| Celery + Beat | Overkill | Requires Redis or RabbitMQ broker. Designed for distributed task queues. This module runs on one machine. |
| Prefect | Overkill | Full DAG orchestration platform. Adds operational complexity for a system with 5 daily jobs. |
| APScheduler 4.x | Too early | Still in alpha (4.0.0a6 as of 2025). Breaking changes expected. Do not use in production. |
| cron (OS-level) | Fallback | Works but loses visibility into job state, no retry logic, harder to test. Use as a backup trigger for the APScheduler process itself. |

### Schedule Configuration

```python
# Different cadences for different data sources
COLLECTION_SCHEDULE = {
    "sec_collector":      {"trigger": "cron", "hour": 2, "minute": 0},   # Daily at 2 AM
    "github_collector":   {"trigger": "cron", "day_of_week": "mon", "hour": 3},  # Weekly Monday 3 AM
    "uspto_collector":    {"trigger": "cron", "day_of_week": "wed", "hour": 3},  # Weekly Wednesday 3 AM
    "jobs_collector":     {"trigger": "cron", "hour": 4, "minute": 0},   # Daily at 4 AM
    "earnings_collector": {"trigger": "cron", "day": 1, "hour": 5},      # Monthly 1st at 5 AM
    "scoring_run":        {"trigger": "cron", "hour": 6, "minute": 0},   # Daily at 6 AM (after all collectors)
}
```

### Key Design Decisions

1. **Collectors run before scoring.** The scoring run is scheduled after all daily collectors have had time to complete. If a collector is late or failed, the scoring engine uses whatever data is available and adjusts confidence.

2. **APScheduler with PostgreSQL job store.** Jobs survive process restarts. If the scheduler process crashes at 3 AM, when it restarts it knows it missed the 2 AM SEC collection and can run it immediately.

3. **Each job is idempotent.** Running a collector twice for the same date produces the same result (or is a no-op if data already exists). This means missed jobs can be safely re-run.

4. **cron as a watchdog.** A simple OS-level cron job checks that the APScheduler process is running and restarts it if not. Belt and suspenders.

---

## Error Isolation Pattern

This is critical for an autonomous system. One failed data source must not block the others.

### Pattern: Independent Collector with Circuit Breaker

```python
# Pseudocode for the collector execution pattern

class BaseCollector:
    """All collectors inherit this. Provides retry, rate limiting, error isolation."""

    max_retries: int = 3
    retry_delay_seconds: int = 60
    circuit_breaker_threshold: int = 5  # consecutive failures before circuit opens

    def collect(self, companies, date) -> CollectionResult:
        """
        Returns CollectionResult with:
        - status: 'success' | 'partial' | 'failed'
        - data: list of collected records
        - errors: list of error details
        - companies_succeeded: int
        - companies_failed: int
        """
        results = []
        errors = []

        for company in companies:
            try:
                data = self._collect_one(company, date)  # subclass implements
                results.append(data)
            except RateLimitError:
                self._wait_for_rate_limit()
                # retry this company
            except SourceUnavailableError:
                errors.append({"company": company, "error": "source_unavailable"})
                # continue to next company
            except Exception as e:
                errors.append({"company": company, "error": str(e)})
                # continue to next company

        return CollectionResult(
            status=self._determine_status(results, errors),
            data=results,
            errors=errors,
        )
```

### Failure Hierarchy

| Failure Type | Response | Impact |
|-------------|----------|--------|
| Single company fails for one source | Log, skip, continue to next company | One company missing one signal. Confidence adjusted. |
| Entire source API is down | Circuit breaker opens after N failures, skip source for this run | All companies missing one signal. Composite score still computed from remaining signals. |
| Database write fails | Retry with exponential backoff. If persistent, halt this collector's run. | Raw data for this source not persisted. Other collectors unaffected. |
| NLP model fails | Fall back to keyword-only analysis (no FinBERT). Log degradation. | Lower quality analysis but still produces a score. |
| Scoring engine fails | Log, do not write corrupted scores. Alert. | No new scores this run. Previous scores still available to downstream. |

### Confidence Adjustment for Missing Signals

When signals are missing, the composite score is still computed but with reduced confidence:

```
confidence = available_signals / total_signals * base_confidence

Example:
- 6/6 signals available, all high quality: confidence = 1.0
- 4/6 signals available (USPTO and GitHub down): confidence = 0.67
- 2/6 signals available: confidence = 0.33 (score is computed but flagged as low confidence)
```

Downstream trading modules should have a minimum confidence threshold (e.g., 0.5) below which they ignore the score.

---

## Patterns to Follow

### Pattern 1: Immutable Append-Only Records

**What:** Never UPDATE or DELETE score records. Every scoring run creates new rows.

**When:** All financial data storage -- raw collections, signal scores, composite scores.

**Why:** Financial data is a historical record. If weights change or a bug is found, you need to compare old scores against new ones. Overwriting destroys the audit trail.

**Implementation:**
```python
# SQLAlchemy model -- no update methods exposed
class CompositeScore(Base):
    __tablename__ = "composite_scores"

    id = mapped_column(UUID, primary_key=True, default=uuid4)
    company_id = mapped_column(UUID, ForeignKey("companies.id"), nullable=False)
    score = mapped_column(SmallInteger, nullable=False)
    confidence = mapped_column(Float, nullable=False)
    scored_at = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    scoring_date = mapped_column(Date, nullable=False)
    signal_breakdown = mapped_column(JSONB, nullable=False)
    signals_available = mapped_column(Integer, nullable=False)
    weights_used = mapped_column(JSONB, nullable=False)
    run_id = mapped_column(UUID, nullable=False)

    # No update() method. Only insert.
```

### Pattern 2: Collector Base Class with Template Method

**What:** Abstract base class that handles retry logic, rate limiting, and error reporting. Subclasses implement only the data-fetching logic.

**When:** Every data source collector.

**Why:** Ensures consistent error handling across all collectors without duplicating retry/rate-limit code in each one.

### Pattern 3: Registry Pattern for Analyzers

**What:** Analyzers self-register. The scoring engine discovers available analyzers at runtime.

**When:** Adding new signals (e.g., conference/research presence as Signal 7 later).

**Why:** Adding a new signal should require adding one collector file and one analyzer file, not modifying the scoring engine. Open/closed principle.

```python
# Registry
ANALYZER_REGISTRY: dict[str, type[BaseAnalyzer]] = {}

def register_analyzer(signal_type: str):
    def decorator(cls):
        ANALYZER_REGISTRY[signal_type] = cls
        return cls
    return decorator

@register_analyzer("sec_filing")
class SECFilingAnalyzer(BaseAnalyzer):
    ...

@register_analyzer("patent_gap")
class PatentGapAnalyzer(BaseAnalyzer):
    ...

# Scoring engine uses registry
for signal_type, analyzer_cls in ANALYZER_REGISTRY.items():
    analyzer = analyzer_cls()
    score = analyzer.analyze(company, raw_data)
```

### Pattern 4: Run-Based Pipeline Tracking

**What:** Every pipeline execution gets a unique `run_id`. All records produced during that run reference it.

**When:** Every daily scoring run.

**Why:** Enables debugging ("what happened on 2026-03-15?"), rollback analysis ("scores from run X look wrong, compare with run Y"), and completeness checking ("did run X score all companies?").

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Shared Mutable State Between Collectors

**What:** Collectors reading/writing shared in-memory state (e.g., a global company list that one collector mutates).

**Why bad:** Race conditions, hidden dependencies, impossible to test collectors in isolation.

**Instead:** Each collector receives an immutable list of companies and returns its results. No shared mutable state.

### Anti-Pattern 2: Synchronous Sequential Collection

**What:** Running collectors one after another, waiting for each to finish before starting the next.

**Why bad:** Total pipeline time = sum of all collector times. If SEC takes 30 minutes and GitHub takes 20 minutes, total is 50+ minutes.

**Instead:** Run collectors concurrently (asyncio or thread pool). Total time = max of individual collector times. APScheduler supports this natively.

### Anti-Pattern 3: Fat Scoring Engine

**What:** Putting all analysis logic inside the scoring engine alongside the weight calculation.

**Why bad:** Makes the scoring engine untestable, hard to modify individual signals, and violates single responsibility.

**Instead:** Scoring engine only combines pre-computed signal scores. All analysis logic lives in the analyzer layer.

### Anti-Pattern 4: Storing Raw API Responses as Unstructured Text

**What:** Dumping entire API responses as TEXT blobs in the database.

**Why bad:** Cannot query or filter raw data efficiently. Debugging requires parsing text blobs.

**Instead:** Store as JSONB. PostgreSQL can index and query JSONB fields directly. Store the full response for audit, but also extract key fields into typed columns for fast queries.

---

## Interface with Broader Hedge Fund System

### Integration Pattern: Shared PostgreSQL + Python Package API

This module connects to the broader fund through two channels:

**Channel 1: Database (primary)**
```
AI Washing Detector --> PostgreSQL <-- Portfolio Manager
                                   <-- Trade Executor
                                   <-- Risk Monitor
```

The `composite_scores` and `signal_scores` tables are the contract. Downstream modules query these tables directly. Schema changes are versioned via Alembic migrations and coordinated across modules.

**Channel 2: Python Package API (convenience)**
```python
# Other fund modules import this package
from ai_washing_detector.api import (
    get_latest_scores,      # Returns latest composite score per company
    get_score_history,      # Returns score time series for a company
    get_high_risk_companies, # Returns companies above a score threshold
    get_signal_breakdown,   # Returns per-signal detail for a company
    get_universe,           # Returns the current target company universe
)
```

The Python API is a thin wrapper around database queries. It provides type-safe return values (dataclasses or Pydantic models) and handles connection management. Downstream modules do not need to know the database schema -- they call functions.

### Contract Boundaries

| What This Module Owns | What This Module Does NOT Own |
|----------------------|-------------------------------|
| Company universe (which companies to score) | Position sizing (how much to trade) |
| All 6 signal scores + composite | Trade execution (when/how to trade) |
| Score confidence levels | Risk limits (max exposure per position) |
| Historical score snapshots | Portfolio construction |
| Raw data from all sources | Market data (prices, volumes) |
| NLP models and analysis logic | Backtesting framework |

### Downstream Module Contract

Downstream modules can rely on:
1. A new row in `composite_scores` for each scored company each business day (or an explanation in `pipeline_runs` for why it is missing).
2. Scores between 0-100 with confidence between 0.0-1.0.
3. `signal_breakdown` JSONB containing per-signal scores keyed by signal type name.
4. Immutable historical data (old scores never change).
5. The Python API returning consistent types.

---

## Scalability Considerations

| Concern | At 100 companies | At 1,000 companies | At 10,000 companies |
|---------|------------------|---------------------|---------------------|
| API rate limits | Comfortable within limits | SEC: 10 req/s is tight for daily. GitHub: fine with token. | Need request queuing, potentially multiple API keys. |
| DB storage | ~50K rows/year in composite_scores. Trivial. | ~500K rows/year. Partitioning helps. | ~5M rows/year. TimescaleDB extension worth considering. |
| NLP processing | Minutes per run. Single machine fine. | 30-60 minutes per run. Still single machine. | Hours per run. Need parallel workers or GPU for FinBERT. |
| Pipeline runtime | Under 30 minutes total. | 1-2 hours total. | Needs distributed collection. Consider Celery at this scale. |

For v1 targeting mid-cap companies ($2B-$10B), the universe is likely 200-500 companies. The single-server APScheduler architecture handles this comfortably. Scaling concerns are deferred.

---

## Suggested Build Order

Based on component dependencies, the recommended build sequence is:

```
Phase 1: Foundation
  database models + migrations
  config system
  package structure (src layout, pyproject.toml)
      |
      v
Phase 2: Data Collection
  BaseCollector + error handling framework
  SEC Collector (richest data source, most important signal)
  Universe Builder (need companies before you can collect data for them)
      |
      v
Phase 3: First Analysis Pipeline
  SEC Analyzer (keyword frequency + R&D gap)
  Scoring Engine (even with just 1 signal, prove the pipeline end-to-end)
  Python API (basic get_latest_scores)
      |
      v
Phase 4: Remaining Collectors + Analyzers
  USPTO Collector + Patent Analyzer
  GitHub Collector + GitHub Analyzer
  Jobs Collector + Jobs Analyzer
  Earnings Collector + Earnings Analyzer
  Compute Spend Analyzer (derived from SEC data, no new collector)
      |
      v
Phase 5: Scheduling + Automation
  APScheduler integration
  Pipeline run tracking
  Error reporting / alerting
  Idempotency guarantees
      |
      v
Phase 6: NLP Enhancement
  FinBERT integration for earnings analysis
  Vagueness classifier
  Confidence calibration
```

**Why this order:**
1. Database and config come first because everything depends on them.
2. SEC is the richest, most reliable data source. Building one collector end-to-end (collect, analyze, score, store) proves the full pipeline architecture before investing in the other 4 collectors.
3. Remaining collectors are independent of each other and can be built in parallel.
4. Scheduling is added after the pipeline works manually, not before.
5. NLP enhancement is last because keyword-frequency analysis works as a baseline. FinBERT is an accuracy improvement, not a blocker.

---

## Sources

- [AWS: GenAI in Factor Modeling Data Pipelines - Hedge Fund Workflow](https://aws.amazon.com/blogs/industries/genai-in-factor-modeling-data-pipelines-a-hedge-fund-workflow-on-aws/) - Hedge fund pipeline architecture on AWS (MEDIUM confidence)
- [PostgreSQL Documentation: Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) - Official partitioning guidance (HIGH confidence)
- [Python Packaging Guide: src Layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/) - Official Python packaging recommendation (HIGH confidence)
- [Python Packaging Guide: Creating Command-Line Tools](https://packaging.python.org/en/latest/guides/creating-command-line-tools/) - Entry points for dual-purpose packages (HIGH confidence)
- [APScheduler on PyPI](https://pypi.org/project/APScheduler/) - Current stable version and features (HIGH confidence)
- [APScheduler 4.0 Progress Tracking](https://github.com/agronholm/apscheduler/issues/465) - v4 still in alpha (HIGH confidence)
- [Dagster: Data Pipelines with Python](https://dagster.io/guides/data-pipelines-with-python-6-frameworks-quick-tutorial) - Pipeline framework comparison (MEDIUM confidence)
- [EDB: Bluefin for PostgreSQL Immutable Storage](https://www.enterprisedb.com/blog/bluefin-postgresql-revolutionizing-immutable-storage-database-management) - Immutable storage patterns (MEDIUM confidence)
- [QuestDB: Immutable Data Pattern](https://questdb.com/glossary/immutable-data-pattern/) - Append-only design rationale (MEDIUM confidence)
- [Hedgeweek: Man Group deploys agentic AI for quant signal discovery](https://www.hedgeweek.com/man-group-deploys-agentic-ai-for-quant-signal-discovery/) - Industry signal generation architecture (MEDIUM confidence)
- [Open-Finance-Lab/AgenticTrading on GitHub](https://github.com/Open-Finance-Lab/AgenticTrading) - Modular agent-based signal generation (MEDIUM confidence)
