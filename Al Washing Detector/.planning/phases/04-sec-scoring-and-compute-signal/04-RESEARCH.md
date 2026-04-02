# Phase 4: SEC Scoring and Compute Signal - Research

**Researched:** 2026-03-28
**Domain:** Financial signal scoring -- keyword frequency analysis, XBRL financial trend computation, score normalization
**Confidence:** HIGH

## Summary

Phase 4 builds the first two scoring engines in the `src/ai_washer/analysis/` package: (1) an SEC filing mismatch scorer that measures the gap between AI keyword growth and R&D spending growth over a 3-year rolling window, and (2) a compute spending gap scorer that detects flat CapEx despite growing AI narrative. Both read from Phase 3's `Filing` and `XBRLFact` tables and write `SignalDetail` rows with JSONB evidence.

The core technical challenge is designing deterministic, pure-function scoring pipelines that operate on local database data (no HTTP calls needed). The keyword analysis requires a curated two-tier lexicon (vague buzzwords vs. substantive terms), section-weighted counting across MD&A/Risk Factors/Business Description, and 3-year YoY growth rate computation. The compute signal shares XBRL infrastructure -- it compares CapEx growth trends against keyword growth trends from the same window.

**Primary recommendation:** Build two independent analyzer classes (SECFilingScorer, ComputeSpendingScorer) with shared utility functions for growth rate computation and score normalization. Use percentile-rank normalization for the 0-100 score output, with a sigmoid-based fallback for early-stage scoring when the universe is small. All scoring logic must be pure functions (no database access, no side effects) that accept typed Pydantic inputs and return typed outputs, with a thin orchestration layer handling database reads/writes.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Section-weighted frequency -- count AI/ML keywords per filing section (MD&A, Risk Factors, Business Description) with configurable weights per section. MD&A claims weighted higher than Risk Factor boilerplate.
- **D-02:** Curated tiered lexicon -- two tiers: vague buzzwords ("AI-powered", "leveraging AI", "machine learning capabilities") vs substantive terms ("neural network", "model training", "inference latency"). Vague terms score higher for washing detection.
- **D-03:** 3-year rolling window for measuring keyword growth trends. Compare current year keyword frequency to 3 years prior.
- **D-04:** Ratio divergence for filing mismatch -- compute AI_keyword_growth_rate / R&D_spend_growth_rate. High ratio = growing AI talk with flat R&D = mismatch.

### Claude's Discretion
- Compute spending gap detection methodology (YoY growth comparison recommended)
- Scoring normalization approach (percentile vs min-max vs z-score)
- Evidence JSONB schema (must be audit-sufficient)
- Specific keyword lists (vague vs substantive terms)
- Section weight values for keyword counting
- Cloud/compute partnership mention keywords for COMP-02

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEC-02 | AI keyword frequency analyzer counts AI/ML mentions across filing sections (MD&A, Risk Factors, Business Description) over 3-5 year windows | Keyword lexicon design, section-weighted counting algorithm, growth rate computation |
| SEC-04 | Filing mismatch score (0-100) computes ratio of AI_mention_growth to R&D_spend_growth, flagging divergence | Ratio divergence formula, normalization to 0-100, deterministic computation |
| COMP-01 | System extracts CapEx and IT spending indicators from XBRL financial data (shares infrastructure with SEC-03) | XBRL_TAG_GROUPS already has `capex` tags; reuse XBRLFact queries |
| COMP-02 | Earnings call transcript analysis checks for cloud/compute partnership mentions (AWS, Azure, GCP, NVIDIA) | Cloud partnership keyword list for filing text (transcripts not available until Phase 7) |
| COMP-03 | Compute spending gap score (0-100) flags flat CapEx/cloud spend despite AI narrative growth | YoY CapEx growth vs keyword growth comparison algorithm |
| SCORE-02 | Per-signal sub-scores stored alongside composite for explainability and audit | SignalDetail model with JSONB evidence schema |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Language:** Python 3.11+
- **Package management:** uv
- **Immutability:** Return new objects, never mutate in place
- **Financial data:** Never overwrite historical records, append new snapshots only
- **Monetary values:** Stored as integers (cents) using BigInteger
- **Validation:** All external data validated at ingestion boundaries via Pydantic
- **Error handling:** Handle errors explicitly at every level
- **File size:** 200-400 lines typical, 800 max
- **Testing:** pytest, TDD workflow, 80%+ coverage target
- **Logging:** structlog for structured JSON output
- **Config:** Scoring weights configurable via `config/scoring.yaml`

## Standard Stack

### Core (already installed, no new dependencies needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | >=2.12.5 | Type contracts for scoring inputs/outputs | Already used throughout project for data validation |
| sqlalchemy | >=2.0.48 | Database reads (Filing, XBRLFact) and writes (SignalDetail) | Already installed, sync engine pattern established |
| structlog | >=25.5.0 | Structured logging in scoring pipelines | Already configured project-wide |

### Supporting (already installed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyyaml | >=6.0 | Reading scoring config weights | Already used for config/scoring.yaml |
| typer | >=0.24.1 | CLI `score` subcommand group | Extending existing cli.py |
| rich | >=14.0 | Terminal output for score results | Already available for CLI formatting |

### No New Dependencies Required

This phase operates entirely on local database data. No HTTP calls, no NLP models, no new libraries. All computation is arithmetic (keyword counting, growth rates, ratios, normalization) using Python stdlib + existing stack. This is intentional -- the analysis layer should be the lightest, most testable part of the system.

## Architecture Patterns

### Recommended Project Structure

```
src/ai_washer/
  analysis/                    # NEW package (Phase 4)
    __init__.py                # Public API exports
    types.py                   # Pydantic types for scoring contracts
    keywords.py                # Keyword lexicon and counting logic
    sec_filing_scorer.py       # SEC filing mismatch score engine
    compute_spending_scorer.py # Compute spending gap score engine
    normalization.py           # Score normalization utilities
    growth.py                  # Growth rate computation utilities
```

### Pattern 1: Pure Function Scoring Core + Thin DB Orchestration

**What:** All scoring logic lives in pure functions that accept typed inputs and return typed outputs. A separate orchestration layer handles database reads/writes.

**When to use:** Always for scoring engines. This is the established pattern from Phase 3 (see `xbrl_extractor.py` -- pure `extract_facts_for_concept()` + class `XBRLExtractor` for HTTP).

**Why:** Pure functions are trivially testable (no mocks needed), deterministic by construction, and composable. The DB layer is tested separately with integration tests.

**Example:**
```python
# Pure function (no DB, no side effects)
def compute_keyword_frequencies(
    sections: dict[str, str | None],
    lexicon: KeywordLexicon,
    section_weights: dict[str, float],
) -> KeywordFrequencyResult:
    """Count keyword occurrences across filing sections with weights."""
    ...
    return KeywordFrequencyResult(
        total_weighted_count=total,
        by_section=section_counts,
        by_tier=tier_counts,
    )

# Orchestration layer (DB reads/writes)
class SECFilingScorer:
    def score_company(self, company_id, scoring_date, run_id) -> SignalResult:
        filings = self._load_filings(company_id)  # DB read
        xbrl_facts = self._load_xbrl_facts(company_id)  # DB read
        result = compute_filing_mismatch(filings, xbrl_facts, self._config)  # Pure
        self._persist_signal(result, company_id, scoring_date, run_id)  # DB write
```

### Pattern 2: Pydantic Type Contracts Per Subpackage

**What:** `analysis/types.py` defines all input/output schemas for the scoring layer, following the established `ingestion/types.py` pattern.

**When to use:** Every data boundary in the analysis layer.

**Example types needed:**
- `KeywordLexicon` -- the two-tier keyword dictionary
- `KeywordFrequencyResult` -- per-section, per-tier counts
- `FilingMismatchInput` -- sections text + XBRL facts for one company
- `GrowthRateResult` -- keyword growth + spending growth over window
- `SignalResult` -- score (0-100) + evidence JSONB

### Pattern 3: Configurable Scoring Parameters via ScoringConfig Extension

**What:** Extend `config/scoring.yaml` with section weights, keyword lists, normalization parameters. Read via existing `ScoringConfig` Pydantic model.

**When to use:** All tunable scoring parameters.

**Example additions to scoring.yaml:**
```yaml
sec_filing:
  section_weights:
    mda: 0.50
    risk_factors: 0.20
    business: 0.30
  window_years: 3

compute_spending:
  capex_weight: 0.70
  cloud_mention_weight: 0.30
```

### Anti-Patterns to Avoid

- **Mixing DB access with scoring logic:** Scoring functions must NOT accept Session objects or query the database. All data is passed in as typed arguments. This ensures determinism and testability.
- **Mutable accumulators:** Do not build scores by mutating a running state object. Use pure reduction: `functools.reduce` or list comprehensions that produce new values.
- **Hardcoded thresholds:** All scoring parameters (section weights, window size, normalization bounds) must come from config, not magic numbers in code.
- **Float comparison for determinism:** Use `round()` or `Decimal` for any intermediate calculations that affect the final integer score. Floating point accumulation across hundreds of keyword matches can produce different results depending on order.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Keyword matching in text | Regex per-keyword loop | Pre-compiled `re.compile` with word boundary `\b` and `re.IGNORECASE` | Compiling once is 10x faster for repeated searches; word boundaries prevent partial matches ("AI" inside "FAIR") |
| Growth rate computation | Custom formula per signal | Shared `compute_cagr()` utility in `growth.py` | CAGR (Compound Annual Growth Rate) is the standard measure; one implementation prevents divergence between SEC and Compute signals |
| Score normalization 0-100 | Ad-hoc clamp per scorer | Shared `normalize_score()` in `normalization.py` | Consistent normalization across all signals ensures comparability |
| XBRL fact time-series queries | Raw SQL per scorer | Shared query helper that returns sorted list of `(fiscal_year, value_cents)` tuples | Both SEC and Compute scorers need the same R&D/CapEx time series |

**Key insight:** The SEC filing scorer and compute spending scorer share significant infrastructure (XBRL fact queries, growth rate computation, normalization). Extracting shared utilities into `growth.py` and `normalization.py` prevents code duplication and ensures both signals use identical calculation methods.

## Keyword Lexicon Design

### Research Findings

Academic research (arxiv:2508.19313) analyzing 30,000+ SEC filings used these AI-related keywords with 98.78% precision: Artificial Intelligence, Deepfake, Natural Language Processing, Machine Learning, Deep Learning, Computer Vision, Generative, Image Recognition, Speech Recognition, Voice Assistant, Chatbot, Recommendation System, A.I, NLP, Recommender System, Artificial General Intelligence, AGI.

SEC enforcement cases (2024 Delphia and Global Predictions fines) specifically targeted unsupported claims using terms like "AI-powered" and "machine learning" without substantiation. The SEC now requires companies to define "AI," "generative AI," "deep learning," and "large language models" within their specific business context.

Bloomberg Tax analysis found a 700% increase in AI-related terms in S&P 500 10-K filings from 2019 to 2024, with average terms per filing rising from 1 to 19.

### Recommended Two-Tier Lexicon

**Tier 1: Vague Buzzwords (score HIGHER for washing detection)**

These terms are promotional and rarely accompanied by technical substance:
```python
VAGUE_BUZZWORDS = [
    "ai-powered", "ai-driven", "ai-enabled", "ai-first",
    "leveraging ai", "leveraging artificial intelligence",
    "leveraging machine learning",
    "powered by ai", "powered by artificial intelligence",
    "cutting-edge ai", "revolutionary ai", "state-of-the-art ai",
    "world-class ai", "industry-leading ai",
    "ai capabilities", "ai solutions", "ai platform",
    "machine learning capabilities", "ai-enhanced",
    "ai transformation", "ai strategy", "ai initiative",
    "intelligent automation", "cognitive computing",
    "predictive analytics", "smart technology",
    "next-generation ai",
]
```

**Tier 2: Substantive Terms (score LOWER -- indicate genuine AI work)**

These terms suggest actual technical implementation:
```python
SUBSTANTIVE_TERMS = [
    "neural network", "deep learning", "transformer model",
    "model training", "model inference", "inference latency",
    "training data", "training pipeline", "fine-tuning",
    "gpu cluster", "compute infrastructure",
    "natural language processing", "computer vision",
    "reinforcement learning", "generative adversarial",
    "large language model", "embedding", "vector database",
    "mlops", "model deployment", "feature engineering",
    "hyperparameter", "gradient descent", "backpropagation",
    "convolutional neural", "recurrent neural",
    "attention mechanism", "tokenization",
]
```

**Confidence:** MEDIUM -- derived from SEC enforcement language, academic keyword lists, and AI industry terminology. The specific tier assignments are judgment calls that should be validated against labeled examples after v1 scoring runs.

### Cloud/Compute Partnership Keywords (for COMP-02)

For detecting cloud/compute partnership mentions in filing text:
```python
CLOUD_COMPUTE_KEYWORDS = [
    "amazon web services", "aws", "azure", "google cloud",
    "gcp", "nvidia", "gpu", "tpu",
    "cloud computing", "cloud infrastructure",
    "data center", "compute capacity",
    "hyperscaler", "cloud partnership",
    "cloud migration", "saas", "iaas", "paas",
    "oracle cloud", "ibm cloud", "alibaba cloud",
]
```

## Scoring Normalization Approach

### Recommendation: Sigmoid-Based Normalization (Claude's Discretion)

**Why not percentile rank:** Percentile rank requires a sufficiently large comparison population. With an initial universe of 200-500 companies, and potentially fewer than 100 having sufficient filing history for 3-year windows, percentile ranking produces coarse scores (each company jumps by 1-2 points). Worse, the score for a given company changes when other companies enter/leave the universe -- violating the determinism requirement.

**Why not min-max:** Extremely sensitive to outliers. A single company with an anomalous keyword count stretches the entire scale. The same company can score 80 one day and 40 the next if a new outlier enters.

**Why not raw z-score:** Z-scores are unbounded and can be negative. Mapping to 0-100 requires clamping which loses information at the tails.

**Recommended approach: Sigmoid mapping of the ratio divergence.**

The filing mismatch ratio (keyword_growth / rd_growth) naturally centers around 1.0 (equal growth). Values > 1 indicate more talk than spend; values < 1 indicate more spend than talk. A sigmoid function maps this ratio to 0-100 with configurable steepness:

```python
import math

def sigmoid_normalize(
    ratio: float,
    midpoint: float = 1.0,
    steepness: float = 2.0,
    max_score: int = 100,
) -> int:
    """Map a ratio to 0-100 using a sigmoid curve.

    ratio=1.0 (equal growth) maps to ~50
    ratio>1.0 (more talk than spend) maps to 50-100
    ratio<1.0 (more spend than talk) maps to 0-50

    Parameters
    ----------
    ratio:
        The raw divergence ratio (keyword_growth / spending_growth).
    midpoint:
        The ratio value that maps to score 50.
    steepness:
        Controls how quickly scores approach 0 or 100.
    max_score:
        Upper bound for the score.
    """
    x = steepness * (ratio - midpoint)
    sigmoid = 1.0 / (1.0 + math.exp(-x))
    return min(max_score, max(0, round(sigmoid * max_score)))
```

**Properties:**
- Deterministic: same ratio always produces same score
- Bounded: output is always 0-100
- Stable: adding/removing companies does not change existing scores
- Interpretable: score 50 = neutral, >50 = mismatch, <50 = genuine investment
- Configurable: `midpoint` and `steepness` in scoring.yaml

**Confidence:** HIGH -- sigmoid normalization is standard in quantitative finance for bounded scoring of ratio signals. The approach satisfies all four success criteria.

## Growth Rate Computation

### 3-Year Rolling Window CAGR

Per decision D-03, compare current year to 3 years prior using Compound Annual Growth Rate:

```python
def compute_cagr(
    start_value: float,
    end_value: float,
    years: int,
) -> float | None:
    """Compute annualized growth rate over a period.

    Returns None if start_value is zero or negative (cannot compute growth).
    """
    if start_value <= 0 or years <= 0:
        return None
    if end_value <= 0:
        return -1.0  # Total decline
    return (end_value / start_value) ** (1.0 / years) - 1.0
```

### Handling Missing Data

XBRL data may have gaps (companies that do not report R&D as a separate line item). When R&D spending is unavailable:

1. Check for the `rd_expense` concept in XBRLFact first
2. Fall back to checking `capex` as a proxy for technology investment
3. If neither is available, the SEC filing mismatch score cannot be computed -- set score to None and document the reason in evidence JSONB
4. The scoring orchestrator should handle missing scores gracefully by not writing a SignalDetail row (rather than writing a zero score)

### Keyword Growth Rate

Count total weighted keywords per filing year, then compute CAGR over the 3-year window:

```
keyword_growth = CAGR(year_N_keyword_count, year_N+3_keyword_count, 3)
rd_growth = CAGR(year_N_rd_spend, year_N+3_rd_spend, 3)
mismatch_ratio = (1 + keyword_growth) / (1 + rd_growth)
```

Adding 1.0 to both growth rates prevents division by zero and handles negative growth gracefully.

## Evidence JSONB Schema (Claude's Discretion)

### Recommended Schema for SEC Filing Mismatch

```json
{
    "signal_version": "0.4.0",
    "window_start_year": 2021,
    "window_end_year": 2024,
    "keyword_counts": {
        "by_year": {
            "2021": {"vague": 12, "substantive": 8, "total_weighted": 34.0},
            "2022": {"vague": 18, "substantive": 7, "total_weighted": 47.5},
            "2023": {"vague": 25, "substantive": 6, "total_weighted": 62.0},
            "2024": {"vague": 35, "substantive": 5, "total_weighted": 85.5}
        },
        "by_section": {
            "mda": {"vague": 45, "substantive": 12},
            "risk_factors": {"vague": 30, "substantive": 8},
            "business": {"vague": 15, "substantive": 6}
        },
        "section_weights_used": {"mda": 0.50, "risk_factors": 0.20, "business": 0.30}
    },
    "financial_data": {
        "rd_spend_cents": {
            "2021": 150000000000,
            "2024": 160000000000
        },
        "rd_growth_cagr": 0.022
    },
    "scoring": {
        "keyword_growth_cagr": 0.359,
        "mismatch_ratio": 1.330,
        "raw_sigmoid_output": 0.72,
        "normalization_params": {"midpoint": 1.0, "steepness": 2.0}
    },
    "data_quality": {
        "filings_analyzed": 4,
        "years_with_data": [2021, 2022, 2023, 2024],
        "missing_sections": [],
        "xbrl_concept_used": "ResearchAndDevelopmentExpense"
    }
}
```

### Recommended Schema for Compute Spending Gap

```json
{
    "signal_version": "0.4.0",
    "window_start_year": 2021,
    "window_end_year": 2024,
    "capex_data": {
        "by_year_cents": {
            "2021": 500000000000,
            "2024": 520000000000
        },
        "capex_growth_cagr": 0.013,
        "xbrl_concept_used": "PaymentsToAcquirePropertyPlantAndEquipment"
    },
    "cloud_mentions": {
        "by_year": {
            "2021": 3,
            "2024": 4
        },
        "keywords_found": ["aws", "cloud infrastructure"]
    },
    "keyword_growth_cagr": 0.359,
    "scoring": {
        "capex_vs_keyword_ratio": 0.036,
        "cloud_mention_factor": 0.1,
        "combined_gap_score": 78,
        "normalization_params": {"midpoint": 1.0, "steepness": 2.0}
    },
    "data_quality": {
        "capex_years_available": [2021, 2022, 2023, 2024],
        "filings_with_cloud_mentions": 3
    }
}
```

**Key design principle:** Evidence must contain enough data to reconstruct the score from scratch. This enables auditing, debugging, and explaining why a company received a particular score.

## Determinism Requirements

Success criterion 4 requires identical scores when re-run for the same company on the same day. Requirements for determinism:

1. **Sort all inputs before processing:** Filing lists sorted by `filing_date` ascending, XBRL facts sorted by `end_date` ascending. The orchestrator must sort before passing to pure functions.
2. **No randomness:** No random sampling, no stochastic operations.
3. **Pin the scoring date:** The scoring date determines the 3-year window. Pass it explicitly, never use `datetime.now()` inside scoring logic.
4. **Float rounding:** Use `round(value, 10)` for intermediate float operations to prevent platform-dependent floating point drift. Final score uses `round()` to int.
5. **Keyword matching order:** Iterate keywords in lexicon definition order (list, not set). Use sorted section names.

## Common Pitfalls

### Pitfall 1: Section Text May Be None or Suspiciously Short

**What goes wrong:** Phase 3 stores filing sections as JSONB where individual sections can be None (section parsing failed) or contain a `full_text_excerpt` fallback. Naively iterating over sections without null checks crashes the keyword counter. Short sections (< 500 chars) are likely table-of-contents stubs per Phase 3 decision.

**Why it happens:** `FilingSections` has optional fields. The scoring layer must handle all permutations.

**How to avoid:** Check `sections.get("mda")` for None before counting. If a section is None, skip it and reduce the section weight denominator. Document in evidence which sections were available.

**Warning signs:** Companies with unusually low keyword counts may have missing sections rather than low AI mention rates.

### Pitfall 2: Division by Zero in Growth Rate Ratios

**What goes wrong:** R&D spending can be zero (company does not report it separately) or the 3-year-ago value can be zero (company was pre-revenue). Computing keyword_growth / rd_growth produces a ZeroDivisionError or infinity.

**Why it happens:** Not all XBRL concepts are available for all companies. The `rd_expense` tag group has 3 fallback tags, but some companies genuinely report zero.

**How to avoid:** Return `None` from CAGR when start_value is zero. The mismatch ratio computation must handle None growth rates: if R&D growth is unavailable, the score cannot be computed (document in evidence, do not write a zero score). If R&D growth is 0% (flat spending), still allow ratio computation using `(1 + keyword_growth) / (1 + 0)` = `1 + keyword_growth`.

**Warning signs:** Scores of exactly 0 or exactly 100 in production data -- likely edge case mishandling.

### Pitfall 3: Keyword Matching Inside Words

**What goes wrong:** Searching for "AI" matches "FAIR", "MAINTAIN", "BRAIN", "CERTAIN". This dramatically inflates vague buzzword counts for every filing.

**Why it happens:** Substring matching without word boundaries.

**How to avoid:** Use `\bAI\b` regex with word boundary assertions. For multi-word phrases like "AI-powered", match the full phrase. Pre-compile all regex patterns once at module load time for performance.

**Warning signs:** Every company scoring > 80 on the SEC signal -- likely false positives from substring matches.

### Pitfall 4: XBRL Value Unit Mismatch

**What goes wrong:** XBRLFact stores `value_cents` (integer, converted from dollars by `int(val * 100)`). When computing growth rates, forgetting that values are in cents produces nonsensical CAGRs.

**Why it happens:** The conversion happens in `xbrl_extractor.py`, and downstream code may assume dollar values.

**How to avoid:** Always use `value_cents` consistently. The growth rate is a ratio, so the unit cancels out -- but if mixing dollars and cents in the same calculation, the ratio is wrong by 100x. Document the unit in type annotations: `value_cents: int`.

**Warning signs:** Growth rates that are orders of magnitude too large or too small.

### Pitfall 5: Fiscal Year vs Calendar Year Mismatch

**What goes wrong:** The 3-year rolling window uses fiscal years from XBRL (which may end in June, September, or any month) while keyword counts from filings use filing dates (which cluster in Q1 for annual reports). Comparing fiscal year 2024 R&D to calendar year 2024 keyword counts may compare different time periods.

**Why it happens:** Companies have different fiscal year ends. Apple's FY2024 ends September 2024; Microsoft's FY2024 ends June 2024.

**How to avoid:** Use `fiscal_year` from XBRLFact for all time-series alignment. For keyword counting, group filings by `period_of_report` year (not `filing_date` year). This aligns both series to the same business calendar.

**Warning signs:** Companies with non-December fiscal year ends showing anomalous score jumps -- likely a time alignment bug.

### Pitfall 6: COMP-02 Cannot Use Earnings Transcripts Yet

**What goes wrong:** COMP-02 specifies "earnings call transcript analysis checks for cloud/compute partnership mentions." But earnings transcripts are not collected until Phase 7. Implementing COMP-02 to depend on transcript data would make Phase 4 dependent on Phase 7.

**Why it happens:** The requirement was written considering the full system, not the phase dependency order.

**How to avoid:** For Phase 4, implement COMP-02 using SEC filing text (10-K sections already collected) instead of earnings transcripts. Search for cloud partnership keywords in MD&A, Business Description, and 8-K text. Document this as a Phase 7 enhancement opportunity -- when transcripts become available, the compute signal can incorporate them as an additional input.

**Warning signs:** If COMP-02 tests reference transcript data that does not exist yet.

## Code Examples

### Keyword Counting with Word Boundaries

```python
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class KeywordMatch:
    keyword: str
    tier: str  # "vague" or "substantive"
    section: str
    count: int


def count_keywords_in_text(
    text: str,
    patterns: list[tuple[re.Pattern, str, str]],
) -> list[KeywordMatch]:
    """Count keyword occurrences in text using pre-compiled patterns.

    Parameters
    ----------
    text:
        The filing section text to search.
    patterns:
        List of (compiled_regex, keyword_string, tier) tuples.

    Returns
    -------
    list[KeywordMatch]
        One entry per keyword that had at least one match.
    """
    results = []
    text_lower = text.lower()
    for pattern, keyword, tier in patterns:
        matches = pattern.findall(text_lower)
        if matches:
            results.append(KeywordMatch(
                keyword=keyword,
                tier=tier,
                section="",  # Set by caller
                count=len(matches),
            ))
    return results


def compile_lexicon(
    vague: list[str],
    substantive: list[str],
) -> list[tuple[re.Pattern, str, str]]:
    """Pre-compile keyword patterns with word boundaries."""
    patterns = []
    for keyword in vague:
        pattern = re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)
        patterns.append((pattern, keyword, "vague"))
    for keyword in substantive:
        pattern = re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)
        patterns.append((pattern, keyword, "substantive"))
    return patterns
```

### Growth Rate and Mismatch Ratio

```python
def compute_filing_mismatch_ratio(
    keyword_counts_by_year: dict[int, float],
    rd_spend_by_year: dict[int, int],
    window_years: int = 3,
    scoring_year: int | None = None,
) -> tuple[float | None, dict]:
    """Compute the filing mismatch ratio for a company.

    Returns
    -------
    tuple[float | None, dict]
        The mismatch ratio (or None if insufficient data), plus
        evidence dict with intermediate values.
    """
    if scoring_year is None:
        scoring_year = max(keyword_counts_by_year.keys())

    start_year = scoring_year - window_years
    evidence = {
        "window_start_year": start_year,
        "window_end_year": scoring_year,
    }

    # Keyword growth
    start_kw = keyword_counts_by_year.get(start_year)
    end_kw = keyword_counts_by_year.get(scoring_year)
    if start_kw is None or end_kw is None:
        evidence["error"] = "insufficient_keyword_data"
        return None, evidence

    kw_growth = compute_cagr(max(start_kw, 0.1), end_kw, window_years)

    # R&D growth
    start_rd = rd_spend_by_year.get(start_year)
    end_rd = rd_spend_by_year.get(scoring_year)
    if start_rd is None or end_rd is None:
        evidence["error"] = "insufficient_rd_data"
        return None, evidence

    rd_growth = compute_cagr(max(start_rd, 1), end_rd, window_years)

    # Ratio with +1 offset to handle negative growth
    kw_factor = 1.0 + (kw_growth if kw_growth is not None else 0.0)
    rd_factor = 1.0 + (rd_growth if rd_growth is not None else 0.0)

    if rd_factor <= 0:
        rd_factor = 0.01  # Prevent division by zero for extreme decline

    ratio = kw_factor / rd_factor

    evidence["keyword_growth_cagr"] = kw_growth
    evidence["rd_growth_cagr"] = rd_growth
    evidence["mismatch_ratio"] = round(ratio, 6)

    return ratio, evidence
```

### SignalDetail Persistence

```python
from datetime import date
from uuid import UUID

from ai_washer.db.models import SignalDetail


def create_signal_detail(
    company_id: UUID,
    signal_type: str,
    score: int,
    evidence: dict,
    scoring_date: date,
    run_id: UUID,
) -> SignalDetail:
    """Create an immutable SignalDetail row.

    Note: as_of_date is the scoring_date (business date the score represents).
    observed_date defaults to today via server_default.
    """
    return SignalDetail(
        company_id=company_id,
        signal_type=signal_type,
        score=score,
        evidence=evidence,
        run_id=run_id,
        as_of_date=scoring_date,
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw keyword counting in full filing text | Section-weighted, tier-aware counting with word boundaries | 2024-2025 (SEC enforcement drove specificity) | 700% increase in AI mentions makes naive counting useless -- context is essential |
| Manual AI washing identification | Rule-based keyword divergence analysis | 2024 (first SEC AI washing penalties) | Quantitative scoring now possible with established keyword taxonomies |
| Simple ratios for financial comparison | CAGR-based growth comparison with sigmoid normalization | Standard practice | Handles multi-year trends and varying fiscal calendars correctly |

**Deprecated/outdated:**
- FinBERT for AI washing detection: FinBERT measures sentiment (positive/negative/neutral), not vagueness vs. specificity. Not relevant for Phase 4 keyword-based approach. Reserved for Phase 7 earnings call analysis.

## Open Questions

1. **Section weight calibration**
   - What we know: MD&A should be weighted highest (D-01), Risk Factors lowest. Recommended: MD&A 0.50, Business 0.30, Risk Factors 0.20.
   - What's unclear: Optimal weights are unknown until we see real scoring results across the universe.
   - Recommendation: Use the recommended defaults, make configurable in scoring.yaml, plan to recalibrate after Phase 9 when all signals are available.

2. **Sigmoid steepness parameter**
   - What we know: Steepness controls how quickly scores approach 0 or 100 from the midpoint.
   - What's unclear: The optimal steepness depends on the actual distribution of mismatch ratios across the target universe, which we do not have yet.
   - Recommendation: Start with steepness=2.0 (moderate sensitivity). Log the raw ratio distribution after first full scoring run to calibrate.

3. **COMP-02 fidelity without transcripts**
   - What we know: Cloud/compute partnership mentions in SEC filings are a partial proxy for COMP-02.
   - What's unclear: How much discriminative power is lost by using filing text instead of earnings transcripts.
   - Recommendation: Implement with filing text for Phase 4, document as enhancement opportunity for Phase 7 integration.

4. **Handling companies with fewer than 3 years of filing data**
   - What we know: Newly public or recently entered universe companies may not have 3 years of history.
   - What's unclear: Should they receive a score with reduced confidence, or no score at all?
   - Recommendation: No score if fewer than 2 years of data. If exactly 2 years available, compute 2-year growth rate and document in evidence. Never extrapolate.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0.2 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/unit/ -x -q` |
| Full suite command | `python -m pytest tests/ -x --timeout=60` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEC-02 | Keyword frequency counts across sections over 3-year window | unit | `python -m pytest tests/unit/test_keywords.py -x` | Wave 0 |
| SEC-04 | Filing mismatch score 0-100 from ratio divergence | unit | `python -m pytest tests/unit/test_sec_filing_scorer.py -x` | Wave 0 |
| COMP-01 | CapEx extraction from XBRL data (reuse XBRLFact queries) | unit | `python -m pytest tests/unit/test_compute_spending_scorer.py -x` | Wave 0 |
| COMP-02 | Cloud/compute partnership mention detection in filing text | unit | `python -m pytest tests/unit/test_keywords.py::TestCloudKeywords -x` | Wave 0 |
| COMP-03 | Compute spending gap score 0-100 | unit | `python -m pytest tests/unit/test_compute_spending_scorer.py -x` | Wave 0 |
| SCORE-02 | SignalDetail rows with evidence JSONB persisted | integration | `python -m pytest tests/integration/test_signal_persistence.py -x` | Wave 0 |
| Determinism | Same company + same day = identical scores | unit | `python -m pytest tests/unit/test_determinism.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -x --timeout=60`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_keywords.py` -- covers SEC-02, COMP-02 keyword counting
- [ ] `tests/unit/test_sec_filing_scorer.py` -- covers SEC-04 mismatch scoring
- [ ] `tests/unit/test_compute_spending_scorer.py` -- covers COMP-01, COMP-03
- [ ] `tests/unit/test_normalization.py` -- covers sigmoid normalization
- [ ] `tests/unit/test_growth.py` -- covers CAGR computation
- [ ] `tests/unit/test_determinism.py` -- covers determinism requirement
- [ ] `tests/unit/test_analysis_types.py` -- covers Pydantic type contracts
- [ ] `tests/integration/test_signal_persistence.py` -- covers SCORE-02 DB writes

## Sources

### Primary (HIGH confidence)
- Existing codebase: `src/ai_washer/db/models.py` -- SignalDetail, Filing, XBRLFact model schemas
- Existing codebase: `src/ai_washer/ingestion/types.py` -- FilingSections, XBRL_TAG_GROUPS, XBRLFactRecord
- Existing codebase: `src/ai_washer/ingestion/xbrl_extractor.py` -- Pure function + class pattern for extraction
- Existing codebase: `src/ai_washer/config.py` -- ScoringConfig, SignalWeights, FilingCollectionSettings patterns
- Existing codebase: `config/scoring.yaml` -- Current signal weight configuration
- [SEC Charges Investment Advisers for AI Washing](https://www.sec.gov/newsroom/press-releases/2024-36) -- First SEC AI washing penalties establishing enforcement precedent
- [SEC Comment Letter Trend: AI-Related Disclosures](https://corpgov.law.harvard.edu/2025/01/16/sec-comment-letter-trend-ai-related-disclosures/) -- SEC evaluation criteria for AI claims

### Secondary (MEDIUM confidence)
- [arxiv:2508.19313 -- AI Risk Disclosures in SEC 10-K Forms](https://arxiv.org/html/2508.19313v1) -- 30,000+ filing analysis with 98.78% precision keyword list: AI, ML, Deep Learning, NLP, Computer Vision, etc.
- [Bloomberg Tax: SEC's 700% Increase in AI Disclosures](https://news.bloombergtax.com/daily-tax-report-international/secs-700-increase-in-ai-disclosures-sets-stage-for-litigation) -- Quantitative trend data on AI mention growth
- [SEC AI Washing Enforcement Overview](https://corpgov.law.harvard.edu/2024/07/19/ai-washing-enforcement-continues-highlighting-risks-to-companies-and-investors/) -- Harvard Law School analysis of enforcement patterns
- [SEC Investor Advisory Committee AI Disclosure Recommendations](https://www.dandodiary.com/2025/12/articles/securities-laws/sec-investor-advisory-committee-recommends-ai-related-disclosure-guidelines/) -- December 2025 SEC guidance

### Tertiary (LOW confidence)
- Score normalization methods: general data science literature on sigmoid, z-score, min-max normalization -- applied to financial context via domain knowledge
- Keyword tier classification (vague vs substantive): author judgment based on SEC enforcement language and industry terminology -- needs validation against labeled data

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing libraries sufficient
- Architecture: HIGH -- follows established codebase patterns (pure functions + class, types.py contracts)
- Scoring methodology: MEDIUM -- sigmoid normalization and lexicon tiers are well-reasoned but unvalidated against real data
- Keyword lexicon: MEDIUM -- derived from academic research and SEC enforcement, but tier assignments need calibration
- Pitfalls: HIGH -- directly derived from codebase analysis and documented Phase 3 decisions

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable domain -- scoring methodology and SEC disclosure patterns evolve slowly)
