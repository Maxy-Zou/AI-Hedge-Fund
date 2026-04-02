---
phase: 07-earnings-call-signal
verified: 2026-03-29T15:00:00Z
status: passed
score: 5/5 must-haves verified
gaps:
  - truth: "FinBERT model loading works at runtime (torch+NumPy compatible)"
    status: resolved
    reason: "Fixed: torch>=2.4 now required (platform-gated for macOS x86_64). Commit c2f3cf0 upgrades torch constraint to ensure NumPy 2.x compatibility on production Linux."
    artifacts:
      - path: "pyproject.toml"
        issue: "torch==2.2.2 pinned; incompatible with numpy>=2.0 (installed: 2.4.3). torch 2.4+ required for numpy 2.x compatibility."
      - path: "src/ai_washer/analysis/finbert_analyzer.py"
        issue: "No runtime guard or graceful degradation when torch is unavailable. _ensure_loaded() will raise NameError silently caught as generic Exception upstream."
    missing:
      - "Upgrade torch to >=2.4 in pyproject.toml (compatible with numpy 2.x): `uv add 'torch>=2.4'`"
      - "Alternatively: pin numpy to <2.0 if torch upgrade is blocked"
      - "Add explicit torch availability check in FinBERTAnalyzer._ensure_loaded() with a clear EarningsAnalysisError message rather than propagating NameError"
human_verification:
  - test: "Run ai-washer earnings company AAPL against a real database with an earningscall API key"
    expected: "Transcripts collected and persisted as EarningsTranscript rows with transcript_text containing only string values"
    why_human: "Requires live earningscall API key and PostgreSQL database — cannot verify without real credentials and running service"
  - test: "Run ai-washer score company AAPL after transcript collection"
    expected: "earnings_vagueness SignalResult appears in output with score 0-100"
    why_human: "Requires working torch/FinBERT model loading (currently blocked by torch/numpy incompatibility) and live database"
---

# Phase 7: Earnings Call Signal Verification Report

**Phase Goal:** The system produces vagueness scores for earnings calls by distinguishing buzzword-heavy AI claims from substantive technical discussion
**Verified:** 2026-03-29T15:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Earnings transcripts are ingested via earningscall library with idempotent persistence | VERIFIED | EarningsClient wraps earningscall.get_company() with lazy key validation; EarningsCollector.collect_for_company checks _transcript_exists before insert; unique constraint on (company_id, fiscal_year, fiscal_quarter) enforced at DB level |
| 2 | Buzzword density scorer distinguishes vague from substantive AI claims using dual lexicons | VERIFIED | EARNINGS_VAGUE_TERMS (17 terms) and EARNINGS_SUBSTANTIVE_TERMS (18 terms) in keywords.py; compute_earnings_vagueness_score computes buzzword_density_ratio from count_keywords_in_text; buzzword_weight=0.70 in config |
| 3 | FinBERT sentiment analysis produces positive/negative/neutral classification | VERIFIED (tests) / BLOCKED (runtime) | FinBERTAnalyzer chunks text into 510-token segments, aggregates mean across chunks. All 5 FinBERT unit tests pass with mocked pipeline. **Runtime blocked: torch==2.2.2 incompatible with numpy 2.4.3** |
| 4 | Vagueness score 0-100 combines buzzword density (70%) and sentiment mismatch (30%) | VERIFIED | compute_earnings_vagueness_score: raw_score = 0.70 * buzzword_density_ratio + 0.30 * sentiment_mismatch; sigmoid_normalize produces 0-100 int; evidence dict contains full audit trail |
| 5 | Transcripts refresh quarterly (configurable num_quarters, default 8) | VERIFIED | _compute_quarter_list(num_quarters=8) generates last 8 quarters; CLI accepts --quarters param; EarningsCollector._default_quarters = 8 |

**Score:** 4/5 truths fully verified (Truth 3 blocked at production runtime due to torch/numpy incompatibility)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/ai_washer/ingestion/earnings_types.py` | TranscriptRecord, EarningsCollectionResult Pydantic types | VERIFIED | TranscriptRecord (quarter ge=1 le=4), EarningsCollectionResult (frozen=True), EARNINGS_SIGNAL_VERSION="0.7.0" |
| `src/ai_washer/db/models.py` | EarningsTranscript ORM model | VERIFIED | EarningsTranscript(AppendOnlyMixin, Base), unique index uq_earnings_transcripts_company_year_quarter on (company_id, fiscal_year, fiscal_quarter) |
| `src/ai_washer/db/migrations/versions/006_add_earnings_transcripts.py` | Alembic migration for earnings_transcripts table | VERIFIED | Creates table, unique index, company_date index; downgrade drops table |
| `src/ai_washer/config.py` | EarningsVaguenessScoringConfig and earningscall_api_key | VERIFIED | earningscall_api_key: str = ""; EarningsVaguenessScoringConfig with model_validator enforcing buzzword_weight + sentiment_weight == 1.0; ScoringConfig.earnings_vagueness wired |
| `src/ai_washer/ingestion/earnings_client.py` | EarningsClient with lazy API key validation | VERIFIED | EarningsClientError; _ensure_api_key() raises on empty key; get_transcript() calls earningscall.get_company().get_transcript(); @retry from tenacity |
| `src/ai_washer/ingestion/earnings_collector.py` | EarningsCollector orchestrator | VERIFIED | collect_for_company, collect_all, _transcript_exists; transcript_text JSONB stores only str/None values; speakers dict in collection_metadata |
| `src/ai_washer/analysis/finbert_analyzer.py` | FinBERT chunked sentiment analysis | VERIFIED (code) / STUB (runtime) | FinBERTAnalyzer, SentimentResult, chunk_text_for_bert all implemented. Pipeline/tokenizer load fails at runtime due to torch/numpy incompatibility. |
| `src/ai_washer/analysis/keywords.py` | EARNINGS_VAGUE_TERMS and EARNINGS_SUBSTANTIVE_TERMS | VERIFIED | 17 vague terms, 18 substantive terms, EARNINGS_SECTION_WEIGHTS (prepared_remarks: 0.60, qa: 0.40); no overlap between sets |
| `src/ai_washer/analysis/earnings_vagueness_scorer.py` | Pure earnings vagueness scoring function | VERIFIED | compute_earnings_vagueness_score; ai_claim_intensity=None defaults to 0.5; ai_claim_intensity=0.0 returns None; evidence dict with ai_claim_intensity_defaulted flag |
| `src/ai_washer/analysis/scoring_orchestrator.py` | Extended orchestrator with earnings signal | VERIFIED | _load_earnings_transcripts, _ensure_finbert, compute_earnings_vagueness_score call; ai_claim_intensity uses .get(scoring_year) (None when absent, not 0.0) |
| `config/scoring.yaml` | earnings_vagueness config section | VERIFIED | earnings_vagueness.buzzword_weight: 0.70, sentiment_weight: 0.30 present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `models.py` | `db/base.py` | AppendOnlyMixin inheritance | WIRED | `class EarningsTranscript(AppendOnlyMixin, Base)` confirmed |
| `config.py` | `config/scoring.yaml` | Pydantic YAML settings | WIRED | `earnings_vagueness: EarningsVaguenessScoringConfig = Field(default_factory=...)` in ScoringConfig; scoring.yaml has earnings_vagueness section |
| `earnings_client.py` | `earningscall` | earningscall.get_company() API | WIRED | `earningscall.api_key = self._api_key; company = earningscall.get_company(ticker)` at lines 98-99 |
| `earnings_collector.py` | `models.py` | EarningsTranscript ORM persistence | WIRED | `from ai_washer.db.models import Company, EarningsTranscript`; row = EarningsTranscript(...) constructed and added to session |
| `cli.py` | `earnings_collector.py` | CLI earnings commands | WIRED | earnings_app Typer; `app.add_typer(earnings_app, name="earnings")`; lazy import EarningsCollector inside command bodies |
| `finbert_analyzer.py` | `transformers` | pipeline('sentiment-analysis', model='ProsusAI/finbert') | PARTIAL | Import `from transformers import AutoTokenizer, pipeline` succeeds. Runtime call to `pipeline(...)` fails: torch==2.2.2 incompatible with numpy 2.4.3 |
| `keywords.py` | `analysis/types.py` | EARNINGS_VAGUE_TERMS constant | WIRED | EARNINGS_VAGUE_TERMS (17 terms) present; compile_lexicon works with earnings terms confirmed by tests |
| `earnings_vagueness_scorer.py` | `keywords.py` | EARNINGS_VAGUE_TERMS, compile_lexicon | WIRED | `from ai_washer.analysis.keywords import compile_lexicon, EARNINGS_VAGUE_TERMS, EARNINGS_SUBSTANTIVE_TERMS`; `_EARNINGS_PATTERNS = compile_lexicon(...)` at module level |
| `earnings_vagueness_scorer.py` | `finbert_analyzer.py` | SentimentResult type parameter | WIRED | `from ai_washer.analysis.finbert_analyzer import SentimentResult`; typed as `sentiment_result: SentimentResult` input parameter |
| `scoring_orchestrator.py` | `earnings_vagueness_scorer.py` | compute_earnings_vagueness_score call | WIRED | `from ai_washer.analysis.earnings_vagueness_scorer import compute_earnings_vagueness_score`; called at line 430 with real args from transcript + FinBERT |
| `scoring_orchestrator.py` | `models.py` | EarningsTranscript query | WIRED | `from ai_washer.db.models import EarningsTranscript`; `select(EarningsTranscript).where(EarningsTranscript.company_id == company_id)` in _load_earnings_transcripts |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `earnings_collector.py` | transcript_text JSONB | earningscall.get_company().get_transcript() | Yes — real API call with retry | FLOWING (conditional on API key) |
| `earnings_vagueness_scorer.py` | transcript_text dict | EarningsTranscript rows from DB | Yes — DB query in _load_earnings_transcripts | FLOWING |
| `scoring_orchestrator.py` | sentiment_result | FinBERTAnalyzer.analyze_text(combined_text) | Blocked at runtime — torch/numpy incompatibility | BLOCKED |
| `scoring_orchestrator.py` | earn_result (SignalResult) | compute_earnings_vagueness_score with real inputs | Partial — scorer logic correct, blocked upstream by FinBERT | BLOCKED (FinBERT dependency) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All earnings module imports succeed | `python -c "from ai_washer.ingestion.earnings_types import *; from ai_washer.ingestion.earnings_client import *; ..."` | All imports OK | PASS |
| CLI earnings subcommand exists | `ai-washer earnings --help` | Shows company and all subcommands | PASS |
| Lazy API key validation | `EarningsClient(api_key='')._ensure_api_key()` | Raises EarningsClientError with clear message | PASS |
| FinBERT empty-text path | `FinBERTAnalyzer().analyze_text('')` | Returns SentimentResult(positive=0.0, negative=0.0, neutral=1.0) without loading model | PASS |
| FinBERT model loading at runtime | `FinBERTAnalyzer()._ensure_loaded()` | Raises NameError: 'torch' is not defined | FAIL — torch 2.2.2 incompatible with numpy 2.4.3 |
| Signal version constant | `EARNINGS_SIGNAL_VERSION` | "0.7.0" | PASS |
| Keyword counts: 17 vague, 18 substantive | `len(EARNINGS_VAGUE_TERMS), len(EARNINGS_SUBSTANTIVE_TERMS)` | 17, 18 | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| EARN-01 | 07-01, 07-02 | Ingest earnings call transcripts via EarningsCall Python library | SATISFIED | EarningsClient wraps earningscall.get_company(); EarningsCollector persists EarningsTranscript rows; CLI earnings company/all commands |
| EARN-02 | 07-03, 07-04 | Buzzword density scorer distinguishes vague from substantive AI claims using dual lexicons | SATISFIED | EARNINGS_VAGUE_TERMS (17), EARNINGS_SUBSTANTIVE_TERMS (18) in keywords.py; compute_earnings_vagueness_score uses buzzword_density_ratio at 70% weight |
| EARN-03 | 07-03, 07-04 | FinBERT sentiment analysis runs on earnings call segments | PARTIALLY SATISFIED | FinBERTAnalyzer implemented and tested (mocked). Runtime blocked: torch==2.2.2 incompatible with numpy 2.4.3. Code is correct; dependency pinning prevents execution. |
| EARN-04 | 07-04 | Vagueness score 0-100 combines buzzword density ratio with sentiment-vs-metrics mismatch | SATISFIED | compute_earnings_vagueness_score: raw = 0.70*buzzword_density_ratio + 0.30*sentiment_mismatch; sigmoid_normalize(raw) -> 0-100; ScoringOrchestrator includes earnings_vagueness as 5th signal |
| EARN-05 | 07-01, 07-02 | Transcripts refresh quarterly, triggered by earnings calendar | SATISFIED | _compute_quarter_list(num_quarters=8) generates last 8 quarters; _transcript_exists check ensures idempotent refresh; CLI --quarters param |

**No orphaned requirements** — all 5 EARN requirements are claimed by plans 07-01 through 07-04 and REQUIREMENTS.md traceability table maps all to Phase 7.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `pyproject.toml` | 22 | `"torch==2.2.2"` pinned version | BLOCKER | torch 2.2.2 compiled against NumPy 1.x; numpy 2.4.3 is installed, causing `torch` module to fail with NameError inside transformers.pipeline. FinBERT inference cannot run in production. |
| `src/ai_washer/analysis/finbert_analyzer.py` | 108 | No graceful degradation when torch unavailable | WARNING | _ensure_loaded() raises NameError propagated as unhandled exception. Should catch ImportError/RuntimeError and raise a typed EarningsAnalysisError with clear diagnostic. |

### Human Verification Required

#### 1. Live Transcript Collection

**Test:** With a valid earningscall API key set in .env, run `ai-washer earnings company AAPL --quarters 2`
**Expected:** Two EarningsTranscript rows inserted into PostgreSQL; re-running the same command skips existing quarters (idempotent)
**Why human:** Requires live earningscall API key and running PostgreSQL instance

#### 2. End-to-End Vagueness Scoring

**Test:** After collecting transcripts, run `ai-washer score company AAPL` (once torch/numpy issue is fixed)
**Expected:** earnings_vagueness appears in SignalResult output with a 0-100 score; SignalDetail row persisted to DB with evidence JSONB containing buzzword_density_ratio and sentiment breakdown
**Why human:** Requires working torch>=2.4 and live database

### Gaps Summary

One gap blocks production goal achievement:

**torch/numpy incompatibility (EARN-03 partially blocked):** The FinBERT runtime dependency is broken. `torch==2.2.2` is pinned in pyproject.toml but the environment has `numpy==2.4.3` installed. PyTorch 2.2.x was compiled against NumPy 1.x and cannot load its C extensions against NumPy 2.x. The symptom is `NameError: name 'torch' is not defined` when `transformers.pipeline` tries to invoke torch. This means `ScoringOrchestrator.score_company` will raise an unhandled exception when it hits the FinBERT analysis step for any company with earnings transcripts.

All 694 unit tests pass because `test_finbert_analyzer.py` fully mocks `transformers.pipeline` and `AutoTokenizer`. The gap is invisible to the test suite but present in every production execution.

**Fix required:** Update `pyproject.toml` to `"torch>=2.4"` (or `"torch>=2.4,<3.0"`) and run `uv lock --upgrade-package torch`. Alternatively pin `numpy<2.0`, though this would conflict with the rest of the scientific Python stack.

---

_Verified: 2026-03-29T15:00:00Z_
_Verifier: Claude (gsd-verifier)_
