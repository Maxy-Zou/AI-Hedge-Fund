# Phase 7: Earnings Call Signal - Research

**Researched:** 2026-03-29
**Domain:** Earnings call transcript ingestion, dual-lexicon vagueness scoring, FinBERT sentiment analysis
**Confidence:** MEDIUM

## Summary

Phase 7 adds the earnings call vagueness signal (20% weight in composite). This requires three capabilities: (1) ingesting earnings call transcripts for target universe companies, (2) scoring vagueness via a dual-lexicon approach distinguishing buzzword-heavy AI claims from substantive technical discussion, and (3) running FinBERT sentiment analysis on transcript segments to detect sentiment-vs-metrics mismatch. The combined vagueness score (0-100) is stored as a SignalDetail row with full evidence JSONB.

The critical risk identified in STATE.md is confirmed: the `earningscall` Python library's free tier covers only 2 companies (Apple and Microsoft). A paid API key is required for 5,000+ company access. Since the project constraint is "free or free-tier APIs for v1," the recommended approach is to use the `earningscall` library with a free API key (signup required, pricing appears to start at a low tier) as the primary source, with graceful degradation when transcripts are unavailable. An alternative fallback is extracting transcripts from 8-K exhibit filings on SEC EDGAR (some companies furnish transcripts as EX-99.1/EX-99.2 under Reg FD), which is already free via edgartools.

**Primary recommendation:** Use the `earningscall` library (v2.0.1) as the primary transcript source with an API key stored in env config. Implement a fallback path that checks 8-K exhibits for transcript text via edgartools. For FinBERT, use `transformers.pipeline("sentiment-analysis", model="ProsusAI/finbert")` with 512-token chunking and mean aggregation. Reuse the existing dual-lexicon pattern from `keywords.py` with earnings-call-specific word lists.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion -- discuss phase was skipped per user setting. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

### Claude's Discretion
All implementation choices.

### Deferred Ideas (OUT OF SCOPE)
None -- discuss phase skipped.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EARN-01 | System ingests earnings call transcripts for target companies using free sources (EarningsCall Python library) | earningscall v2.0.1 on PyPI, free tier limited to 2 companies, paid key for 5000+. Fallback: 8-K exhibit transcripts via edgartools (already in stack). |
| EARN-02 | Buzzword density scorer distinguishes vague AI claims from substantive claims using dual lexicons | Existing `keywords.py` pattern with VAGUE_BUZZWORDS and SUBSTANTIVE_TERMS provides the template. Extend with earnings-call-specific terms. |
| EARN-03 | FinBERT sentiment analysis runs on earnings call segments producing positive/negative/neutral classification | ProsusAI/finbert on HuggingFace, 512-token max, needs chunking strategy. Requires `transformers>=5.3.0` and `torch>=2.5` (not yet installed). |
| EARN-04 | Vagueness score (0-100) combines buzzword density ratio with sentiment-vs-metrics mismatch | Existing `sigmoid_normalize` and `SignalResult` patterns apply directly. New pure scorer function. |
| EARN-05 | Transcripts refresh quarterly, triggered by earnings calendar | earningscall library provides `get_transcript(year, quarter)` API; incremental collection via DB uniqueness constraint on (company_id, year, quarter). |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| earningscall | 2.0.1 | Earnings call transcript retrieval | Python SDK for EarningsCall API, covers 5000+ companies with API key, MIT license, actively maintained (Mar 2026) |
| transformers | >=5.3.0 | FinBERT model loading and inference | HuggingFace transformers is the standard for pre-trained model inference. Use `pipeline()` for zero-config setup. |
| torch | >=2.5 | FinBERT inference backend | Required by transformers for model weights. CPU-only sufficient for batch of ~200 companies. |
| ProsusAI/finbert | - | Financial sentiment classification | 89% accuracy on financial text. Three-class output (positive/negative/neutral). Pre-trained on financial corpus. |

### Supporting (already in stack)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| edgartools | >=5.26.1 | 8-K exhibit transcript fallback | When earningscall has no transcript, check 8-K filings for EX-99 exhibits containing transcript text |
| httpx | >=0.28.1 | HTTP client (earningscall uses it internally or we use for fallback) | Already in dependencies |
| tenacity | >=9.1.4 | Retry logic for API calls | Wrap earningscall calls with retry |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| earningscall | Finnhub API | Finnhub has earnings transcripts but unclear if free tier includes them. earningscall has a dedicated Python SDK. |
| earningscall | API Ninjas | Premium-only for transcripts ($39+/month). Not free. |
| earningscall | 8-K EDGAR only | Free but coverage is incomplete -- not all companies file transcripts as 8-K exhibits. Would miss many mid-caps. |
| FinBERT local | Claude API | Per-call cost and latency. FinBERT is free, runs locally, 89% accurate. Claude reserved for v2 per tech stack decisions. |

**Installation:**
```bash
uv add earningscall>=2.0.1
uv add transformers>=5.3.0 torch>=2.5
```

**Note on torch:** torch is a large dependency (~2GB). Install CPU-only variant where possible:
```bash
uv add torch --index-url https://download.pytorch.org/whl/cpu
```

## Architecture Patterns

### Recommended Project Structure
```
src/ai_washer/
  ingestion/
    earnings_client.py       # EarningsCall API wrapper (transcript fetching)
    earnings_collector.py    # Orchestrator: collect transcripts for companies
    earnings_types.py        # Pydantic types: TranscriptRecord, EarningsCollectionResult
  analysis/
    earnings_vagueness_scorer.py  # Pure scorer: dual-lexicon + FinBERT + score
    finbert_analyzer.py           # FinBERT wrapper: chunking, inference, aggregation
    keywords.py                   # EXTEND: add EARNINGS_VAGUE_TERMS, EARNINGS_SUBSTANTIVE_TERMS
  db/
    models.py                # ADD: EarningsTranscript model
    migrations/versions/
      006_add_earnings_transcripts.py  # New migration
```

### Pattern 1: EarningsCall Client Wrapper
**What:** Thin wrapper around `earningscall` library that normalizes output to Pydantic types, handles API key validation (lazy like GitHubClient/PatentSearchClient), and adds retry logic.
**When to use:** All transcript retrieval operations.
**Example:**
```python
# Source: earningscall PyPI + project convention
from earningscall import get_company
import structlog

logger = structlog.get_logger(__name__)

class EarningsClient:
    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key
        # Lazy validation: accept empty at construction, raise on first call

    def get_transcript(
        self, ticker: str, year: int, quarter: int
    ) -> TranscriptRecord | None:
        if not self._api_key:
            raise EarningsClientError("API key required")
        # earningscall sets API key via module-level var
        import earningscall
        earningscall.api_key = self._api_key
        company = get_company(ticker)
        transcript = company.get_transcript(year=year, quarter=quarter, level=2)
        if transcript is None:
            return None
        return TranscriptRecord(
            ticker=ticker,
            year=year,
            quarter=quarter,
            text=transcript.text,
            speakers=transcript.speakers,  # Level 2 data
        )
```

### Pattern 2: FinBERT Chunked Inference
**What:** Split transcript text into 510-token chunks (512 minus CLS/SEP), run FinBERT on each chunk, aggregate probabilities via mean.
**When to use:** All sentiment analysis on earnings call text.
**Example:**
```python
# Source: HuggingFace transformers pipeline + FinBERT model card
from transformers import pipeline, AutoTokenizer

class FinBERTAnalyzer:
    def __init__(self) -> None:
        self._pipe = pipeline(
            "sentiment-analysis",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            batch_size=8,
            truncation=True,
            max_length=512,
        )
        self._tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")

    def analyze_text(self, text: str) -> SentimentResult:
        chunks = self._chunk_text(text, max_tokens=510)
        if not chunks:
            return SentimentResult(positive=0.0, negative=0.0, neutral=1.0)
        results = self._pipe(chunks)
        # Aggregate: mean of label probabilities across chunks
        ...
```

### Pattern 3: Collector Pattern (consistent with Phase 5/6)
**What:** EarningsCollector follows the same init/collect_for_company/collect_all pattern as PatentCollector and GitHubCollector.
**When to use:** All collection orchestration.

### Pattern 4: Pure Scorer Function (consistent with Phase 4/5/6)
**What:** `compute_earnings_vagueness_score()` is a pure function -- typed inputs, typed outputs, no DB access, no side effects. Evidence dict follows JSONB schema.
**When to use:** All scoring.

### Anti-Patterns to Avoid
- **Loading FinBERT per company:** Model loading takes 5-10 seconds. Load ONCE at scorer construction, reuse for all companies.
- **Running FinBERT on entire transcript:** 512-token limit means truncation loses data. MUST chunk and aggregate.
- **Storing raw transcript text in DB:** Transcripts are large (10-50KB). Store text in JSONB with sections (prepared_remarks, qa) but consider max_chars limit like Filing model.
- **Calling earningscall API without rate handling:** The library has built-in retry but wrap with tenacity for consistency with project patterns.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Transcript fetching | Custom scraper for earnings sites | `earningscall` library | Handles 5000+ companies, speaker segmentation, quarterly access |
| Financial sentiment | Custom sentiment model | ProsusAI/finbert via transformers | 89% accuracy pre-trained on financial corpus, zero fine-tuning needed |
| Token chunking | Custom text splitter | `AutoTokenizer.encode` + sliding window | Tokenizer handles subword splitting correctly, custom splitters break mid-word |
| Keyword matching | Custom string search | Existing `compile_lexicon` + `count_keywords_in_text` from keywords.py | Already handles word boundaries, case insensitivity, compiled regex |
| Score normalization | Custom 0-100 mapping | Existing `sigmoid_normalize` from normalization.py | Already handles overflow, midpoint, steepness parameters |

## Common Pitfalls

### Pitfall 1: EarningsCall Free Tier Covers Only 2 Companies
**What goes wrong:** Without an API key, only Apple and Microsoft transcripts are available. The target universe is ~200 mid-cap companies.
**Why it happens:** earningscall library defaults to free tier.
**How to avoid:** Require `AI_WASHER_EARNINGSCALL_API_KEY` in AppSettings. Implement graceful degradation (log warning, skip company, produce no score) when key is missing or company not covered.
**Warning signs:** Empty transcripts returned for most companies.

### Pitfall 2: FinBERT 512-Token Truncation
**What goes wrong:** Earnings call transcripts are 5,000-20,000 words. Passing full text to FinBERT silently truncates to first 512 tokens, losing 95%+ of content.
**Why it happens:** BERT architecture has a fixed 512-token context window.
**How to avoid:** Chunk text into 510-token segments (reserving 2 for CLS/SEP), run inference on each chunk, aggregate probabilities via mean.
**Warning signs:** All transcripts produce nearly identical sentiment scores (because only intro text is analyzed).

### Pitfall 3: Quarterly Calendar Alignment
**What goes wrong:** Companies report on different fiscal calendars. Q1 for one company might be Jan-Mar, for another Apr-Jun.
**Why it happens:** Fiscal year end dates vary by company.
**How to avoid:** Use the earningscall library's year/quarter parameters which align to the company's fiscal calendar. Store the year and quarter as provided by the API, not calendar quarters.
**Warning signs:** Missing transcripts for companies with non-standard fiscal years.

### Pitfall 4: Duplicate Transcript Storage
**What goes wrong:** Re-running collection stores the same transcript twice.
**Why it happens:** No idempotency check.
**How to avoid:** Unique constraint on (company_id, year, quarter) in the earnings_transcripts table. Check-before-insert pattern (same as Filing, Patent, GitHubRepo).
**Warning signs:** Duplicate rows in database, inflated collection counts.

### Pitfall 5: FinBERT Model Download on First Run
**What goes wrong:** First inference call downloads ~400MB model from HuggingFace, causing timeout or failure in production.
**Why it happens:** transformers auto-downloads models on first use.
**How to avoid:** Document model download as a setup step. Consider a CLI command `ai-washer earnings setup` that pre-downloads the model. The model is cached in `~/.cache/huggingface/`.
**Warning signs:** Long first-run time, network errors in airgapped environments.

### Pitfall 6: Sentiment-Metrics Mismatch Calculation
**What goes wrong:** Combining buzzword density with sentiment incorrectly by treating them as independent signals.
**Why it happens:** The score formula is not well-defined.
**How to avoid:** Define clearly: vagueness_score = f(buzzword_ratio, sentiment_mismatch). Buzzword ratio = vague_count / (vague_count + substantive_count). Sentiment mismatch = positive_sentiment when metrics are flat/declining (requires cross-referencing XBRL data from Phase 3). Start simple: weighted combination of buzzword_density_ratio (primary, 70%) and sentiment_inflation_flag (secondary, 30%).
**Warning signs:** Score does not discriminate between genuinely positive AI stories and vague AI hype.

## Code Examples

### EarningsTranscript ORM Model
```python
# Follows existing AppendOnlyMixin pattern from models.py
class EarningsTranscript(AppendOnlyMixin, Base):
    __tablename__ = "earnings_transcripts"
    __table_args__ = (
        Index(
            "uq_earnings_transcripts_company_year_quarter",
            "company_id", "fiscal_year", "fiscal_quarter",
            unique=True,
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    transcript_date: Mapped[date] = mapped_column(Date, nullable=False)
    transcript_text: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )  # {"prepared_remarks": "...", "qa": "...", "full_text": "..."}
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="earningscall"
    )
    collection_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
```

### Dual-Lexicon for Earnings Calls
```python
# Extends existing keywords.py pattern
EARNINGS_VAGUE_TERMS: tuple[str, ...] = (
    "ai-powered",
    "ai-driven",
    "leveraging ai",
    "ai transformation",
    "ai strategy",
    "ai initiatives",
    "ai capabilities",
    "ai solutions",
    "intelligent automation",
    "digital transformation",
    "ai journey",
    "ai roadmap",
    "ai-first",
    "ai opportunity",
    "ai momentum",
    "exciting ai",
    "tremendous ai",
)

EARNINGS_SUBSTANTIVE_TERMS: tuple[str, ...] = (
    "deployed transformer model",
    "trained on",
    "inference latency",
    "gpu cluster",
    "model accuracy",
    "f1 score",
    "training pipeline",
    "feature engineering",
    "a/b testing",
    "model serving",
    "ml infrastructure",
    "data pipeline",
    "model retraining",
    "production model",
    "mlops",
    "fine-tuned",
    "embedding model",
    "vector search",
)
```

### FinBERT Chunked Inference
```python
# Source: HuggingFace transformers + ProsusAI/finbert model card
def chunk_text_for_bert(text: str, tokenizer, max_tokens: int = 510) -> list[str]:
    """Split text into chunks that fit within BERT's 512-token limit."""
    tokens = tokenizer.encode(text, add_special_tokens=False)
    chunks = []
    for i in range(0, len(tokens), max_tokens):
        chunk_tokens = tokens[i : i + max_tokens]
        chunk_text = tokenizer.decode(chunk_tokens, skip_special_tokens=True)
        chunks.append(chunk_text)
    return chunks
```

### Vagueness Score Formula
```python
def compute_earnings_vagueness_score(
    transcript_text: dict[str, str | None],
    sentiment_result: SentimentResult,
    ai_claim_intensity: float,
    buzzword_weight: float = 0.70,
    sentiment_weight: float = 0.30,
    sigmoid_midpoint: float = 1.0,
    sigmoid_steepness: float = 2.0,
) -> SignalResult | None:
    """Pure function: compute vagueness score from transcript analysis.

    buzzword_density_ratio = vague_count / max(vague_count + substantive_count, 1)
    sentiment_mismatch = positive_sentiment * (1 - substantive_ratio)
    raw_ratio = buzzword_weight * buzzword_density_ratio + sentiment_weight * sentiment_mismatch
    score = sigmoid_normalize(raw_ratio, midpoint, steepness)
    """
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| BERT base for financial text | FinBERT (ProsusAI) | 2019, still standard | 89% vs 76% accuracy on financial sentiment |
| transformers v4.x | transformers v5.x | Jan 2026 | New pipeline API, better batch support |
| earningscall v1.x | earningscall v2.0.1 | Mar 2026 | New SDK version, updated API |

## Open Questions

1. **EarningsCall API Key Cost**
   - What we know: Free tier = 2 companies only. Paid key unlocks 5000+. PyPI shows v2.0.1 (Mar 2026), MIT license.
   - What's unclear: Exact pricing for paid tier. Signup page is JS-rendered and could not be scraped.
   - Recommendation: Sign up for API key and test with target universe. If cost is prohibitive, fall back to 8-K exhibit extraction only (lower coverage but free). Add `AI_WASHER_EARNINGSCALL_API_KEY` to AppSettings as optional (empty string default, like github_token).

2. **8-K Transcript Coverage for Mid-Caps**
   - What we know: Some companies file earnings call transcripts as 8-K EX-99.1/EX-99.2 exhibits on EDGAR. This is free and already accessible via edgartools.
   - What's unclear: What percentage of mid-cap target universe companies actually file transcripts as 8-K exhibits. Coverage may be 20-40% for mid-caps.
   - Recommendation: Implement as secondary fallback. The 8-K filings are already collected in Phase 3. Can parse existing 8-K data for transcript-like exhibits.

3. **torch CPU-only Installation Size**
   - What we know: Full torch is ~2GB. CPU-only is ~200MB.
   - What's unclear: Whether uv handles `--index-url` for CPU-only torch cleanly.
   - Recommendation: Install CPU-only torch. Daily batch on ~200 companies does not need GPU. Document installation in dev setup.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | Yes | 3.12.11 | -- |
| PostgreSQL | Database | Yes | (via testcontainers) | -- |
| transformers | EARN-03 (FinBERT) | No | -- | Must install: `uv add transformers>=5.3.0` |
| torch | EARN-03 (FinBERT) | No | -- | Must install: `uv add torch>=2.5` (CPU-only) |
| earningscall | EARN-01 (transcripts) | No | -- | Must install: `uv add earningscall>=2.0.1` |
| ProsusAI/finbert model | EARN-03 | No | -- | Auto-downloads on first use (~400MB). Add setup step. |
| earningscall API key | EARN-01 | Unknown | -- | Requires signup. Graceful degradation when unavailable. |

**Missing dependencies with no fallback:**
- transformers + torch: Required for EARN-03. Must be installed. Wave 0 task.
- earningscall: Required for EARN-01. Must be installed. Wave 0 task.

**Missing dependencies with fallback:**
- earningscall API key: If unavailable, fall back to 8-K exhibit parsing (lower coverage). Signal still produces scores for companies with 8-K transcripts.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0 |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/unit/ -x --timeout=30` |
| Full suite command | `python -m pytest tests/ --timeout=120` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EARN-01 | Transcript ingestion from earningscall API | unit (mock API) | `python -m pytest tests/unit/test_earnings_client.py -x` | No -- Wave 0 |
| EARN-01 | 8-K fallback transcript extraction | unit | `python -m pytest tests/unit/test_earnings_client.py::test_8k_fallback -x` | No -- Wave 0 |
| EARN-02 | Dual-lexicon buzzword density scoring | unit | `python -m pytest tests/unit/test_earnings_vagueness_scorer.py -x` | No -- Wave 0 |
| EARN-03 | FinBERT chunked sentiment analysis | unit (mock model) | `python -m pytest tests/unit/test_finbert_analyzer.py -x` | No -- Wave 0 |
| EARN-04 | Combined vagueness score 0-100 | unit | `python -m pytest tests/unit/test_earnings_vagueness_scorer.py::test_combined_score -x` | No -- Wave 0 |
| EARN-05 | Quarterly incremental collection | unit | `python -m pytest tests/unit/test_earnings_collector.py -x` | No -- Wave 0 |
| EARN-05 | DB idempotency (unique constraint) | integration | `python -m pytest tests/integration/test_earnings_persistence.py -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -x --timeout=30`
- **Per wave merge:** `python -m pytest tests/ --timeout=120 -m "not integration"`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_earnings_client.py` -- covers EARN-01
- [ ] `tests/unit/test_earnings_collector.py` -- covers EARN-05
- [ ] `tests/unit/test_finbert_analyzer.py` -- covers EARN-03
- [ ] `tests/unit/test_earnings_vagueness_scorer.py` -- covers EARN-02, EARN-04
- [ ] `tests/integration/test_earnings_persistence.py` -- covers EARN-05 DB layer
- [ ] Package install: `uv add earningscall>=2.0.1 transformers>=5.3.0 torch>=2.5`
- [ ] FinBERT model tests should mock the pipeline (no actual model download in CI)

## Project Constraints (from CLAUDE.md)

- **Immutability:** Financial data must never be overwritten -- append new snapshots only. Earnings transcripts are append-only.
- **Immutable data patterns:** Return new objects, don't mutate in place. Frozen dataclasses for scoring inputs.
- **SEC compliance:** EDGAR requires User-Agent with company name + email (already handled for 8-K fallback).
- **Free APIs for v1:** EarningsCall API key may have a cost -- needs signup validation. 8-K fallback is guaranteed free.
- **Error handling:** Comprehensive error handling at every level. Graceful degradation when transcript source unavailable.
- **File organization:** Many small files > few large files. 200-400 lines typical, 800 max.
- **Function design:** < 50 lines per function. Type hints on all params and return values.
- **Ruff:** line-length=100, target-version=py312. Run `ruff format` and `ruff check --fix`.
- **Testing:** TDD approach. 80%+ coverage. Unit tests mock external APIs.
- **Logging:** structlog with contextual binding. `log.info("event_name", key=value)` pattern.
- **Config:** Pydantic settings with AI_WASHER_ prefix. New config for earnings in ScoringConfig.
- **DB conventions:** AppendOnlyMixin for financial data. UUID PKs. JSONB for flexible evidence.
- **Lazy imports in CLI:** Heavy modules imported inside command functions.
- **Signal version:** Use `0.7.0` for earnings call scorer (matching phase numbering).
- **Scorer pattern:** ScoringOrchestrator is the ONLY analysis module with DB access. Scorers are pure functions.

## Sources

### Primary (HIGH confidence)
- [earningscall PyPI](https://pypi.org/project/earningscall/) - v2.0.1, Mar 2026, MIT license
- [earningscall GitHub](https://github.com/EarningsCall/earningscall-python) - API usage, free tier limits (2 companies), level 1-4 data
- [ProsusAI/finbert HuggingFace](https://huggingface.co/ProsusAI/finbert) - Model card, three-class sentiment output
- [ProsusAI/finBERT GitHub](https://github.com/ProsusAI/finBERT) - Implementation examples, 512-token limit

### Secondary (MEDIUM confidence)
- [SEC EDGAR 8-K transcript filings](https://www.sec.gov/search-filings) - Verified: some companies file transcripts as EX-99 exhibits in 8-K forms
- [Finnhub Earnings Transcripts API](https://finnhub.io/docs/api/earnings-call-transcripts-api) - Alternative source, speaker-segmented, unclear free tier
- [BERT long text handling](https://medium.com/@priyatoshanand/handle-long-text-corpus-for-bert-model-3c85248214aa) - 510-token chunking with mean aggregation strategy

### Tertiary (LOW confidence)
- EarningsCall API pricing: Could not scrape pricing page (JS-rendered). Free tier confirmed at 2 companies. Paid tier pricing unknown.

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - earningscall library confirmed on PyPI but pricing unclear; FinBERT well-established
- Architecture: HIGH - follows established project patterns exactly (collector/client/scorer split)
- Pitfalls: HIGH - 512-token truncation and free-tier limitation are well-documented issues

**Research date:** 2026-03-29
**Valid until:** 2026-04-15 (earningscall library may update pricing)
