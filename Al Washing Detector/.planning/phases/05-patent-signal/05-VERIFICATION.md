---
phase: 05-patent-signal
verified: 2026-03-28T22:50:00Z
status: passed
score: 11/11 must-haves verified
re_verification: false
---

# Phase 5: Patent Signal Verification Report

**Phase Goal:** The system produces patent gap scores by comparing a company's AI patent filings against its AI claim intensity
**Verified:** 2026-03-28T22:50:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Patent data has validated Pydantic schemas for API responses and scoring inputs | VERIFIED | `PatentRecord`, `PatentForScoring` (frozen dataclass), `PatentCollectionResult`, `CPC_AI_PREFIXES`, `PATENT_SIGNAL_VERSION` all exist in `patent_types.py` (97 lines) |
| 2 | Patent DB model exists with append-only design and unique constraint on (company_id, patent_id) | VERIFIED | `class Patent(AppendOnlyMixin, Base)` at models.py:268 with `uq_patents_company_patent_id` unique index |
| 3 | Alembic migration 004 creates the patents table with correct columns and indexes | VERIFIED | `004_add_patent_table.py` with `revision = "004_add_patents"`, `down_revision = "003_add_filings"`, creates table + both indexes |
| 4 | Scoring config includes patent_gap section with configurable window_years and sigmoid parameters | VERIFIED | `PatentGapScoringConfig` in `config.py` (line 116), `patent_gap:` section in `scoring.yaml` (line 28) |
| 5 | Patent client queries PatentSearch API with CPC codes G06N/G06F18 by assignee organization name | VERIFIED | `_build_query` uses `_contains` for assignee and `_begins` for CPC prefixes; `X-Api-Key` header set on every request |
| 6 | Pagination handles large patent portfolios using cursor-based 'after' parameter | VERIFIED | Loop in `search_by_assignee` uses last `patent_id` as cursor; capped at 10 pages (`_MAX_PAGES`) |
| 7 | Rate limiting respects 45 req/min with tenacity exponential backoff | VERIFIED | `@retry(wait=wait_exponential(min=0.1, max=60), stop=stop_after_attempt(5), retry=retry_if_exception(_is_retryable))` on `_fetch_page` |
| 8 | Patent collector uses assignee aliases from entity resolution table for comprehensive matching | VERIFIED | `_get_assignee_names` reads `aliases["patent_assignee"]`, falls back to `company_name`; all aliases searched before deduplification |
| 9 | Patent gap score (0-100) reflects divergence between AI claim intensity growth and patent filing trend | VERIFIED | `compute_patent_gap_score` uses CAGR ratio of claim vs patent growth, sigmoid-normalized to 0-100; live spot check: high claim growth + flat patents → score 76 |
| 10 | Scoring orchestrator integrates patent gap into the existing signal pipeline | VERIFIED | `score_company` calls `_load_patent_counts` (real DB query grouped by year) then `compute_patent_gap_score`, appends to results alongside SEC and compute signals |
| 11 | CLI patent commands allow collecting and scoring patents per company or for all companies | VERIFIED | `patent_app` Typer group registered in `cli.py`; `collect` and `collect-all` commands confirmed via CLI help output |

**Score:** 11/11 truths verified

---

### Required Artifacts

| Artifact | Min Lines | Actual Lines | Key Patterns | Status |
|----------|-----------|-------------|--------------|--------|
| `src/ai_washer/ingestion/patent_types.py` | 60 | 97 | `class PatentRecord`, `frozen=True`, `CPC_AI_PREFIXES`, `PATENT_SIGNAL_VERSION`, `class PatentCollectionResult` | VERIFIED |
| `src/ai_washer/db/models.py` | — | 300+ | `class Patent`, `AppendOnlyMixin`, `uq_patents_company_patent_id` | VERIFIED |
| `src/ai_washer/db/migrations/versions/004_add_patent_table.py` | — | 86 | `revision =`, `down_revision`, creates patents table + indexes, `downgrade` drops table | VERIFIED |
| `src/ai_washer/config.py` | — | — | `class PatentGapScoringConfig`, `patent_gap: PatentGapScoringConfig`, `patentsview_api_key`, `patentsview_base_url` | VERIFIED |
| `config/scoring.yaml` | — | — | `patent_gap:` section with `window_years`, `sigmoid_midpoint`, `sigmoid_steepness` | VERIFIED |
| `tests/unit/test_patent_types.py` | 40 | 165 | 14 test functions | VERIFIED |
| `src/ai_washer/ingestion/patent_client.py` | 100 | 334 | `class PatentSearchClient`, `class PatentClientError`, `_build_query`, `search_by_assignee`, `X-Api-Key`, `_begins`, `wait_exponential` | VERIFIED |
| `src/ai_washer/ingestion/patent_collector.py` | 80 | 354 | `class PatentCollector`, `collect_for_company`, `collect_all`, `_get_last_patent_date`, `_get_assignee_names`, `patent_assignee` | VERIFIED |
| `tests/unit/test_patent_client.py` | 80 | 370 | 16 test functions including `test_search_returns_patents`, `test_empty_api_key_raises` | VERIFIED |
| `tests/unit/test_patent_collector.py` | 60 | 340 | 8 test functions including `test_collect_uses_assignee_aliases`, `test_incremental_uses_last_date` | VERIFIED |
| `src/ai_washer/analysis/patent_gap_scorer.py` | 60 | 87 | `def compute_patent_gap_score`, `signal_type="patent_gap"`, imports `compute_cagr` and `sigmoid_normalize` | VERIFIED |
| `src/ai_washer/analysis/scoring_orchestrator.py` | — | — | `compute_patent_gap_score`, `_load_patent_counts`, `patent_gap` config usage, `Patent` model import | VERIFIED |
| `src/ai_washer/cli.py` | — | — | `patent_app`, `patent_collect_cmd`, `patent_collect_all_cmd`, `PatentCollector` | VERIFIED |
| `tests/unit/test_patent_gap_scorer.py` | 80 | 190 | 11 test functions | VERIFIED |

---

### Key Link Verification

| From | To | Via | Status | Evidence |
|------|----|-----|--------|----------|
| `patent_types.py` | `db/models.py` | PatentRecord fields map to Patent model columns | WIRED | Both have `patent_id`, `patent_title`, `patent_date`, `assignee_organization`, `cpc_codes` |
| `config.py` | `config/scoring.yaml` | `PatentGapScoringConfig` loaded from YAML `patent_gap` section | WIRED | `patent_gap:` present in yaml; `ScoringConfig` has `patent_gap: PatentGapScoringConfig` field |
| `patent_client.py` | PatentSearch API | `httpx GET` with `X-Api-Key` header | WIRED | `headers={"X-Api-Key": api_key}` on client construction and per-request; URL `{base_url}/patent/` |
| `patent_collector.py` | `db/models.py` | `Patent` model for DB persistence | WIRED | `from ai_washer.db.models import Company, Patent` at line 26 |
| `patent_collector.py` | `patent_client.py` | `PatentSearchClient` for API calls | WIRED | `from ai_washer.ingestion.patent_client import PatentClientError, PatentSearchClient` at line 28 |
| `patent_gap_scorer.py` | `analysis/growth.py` | `compute_cagr` for trend calculation | WIRED | `from ai_washer.analysis.growth import compute_cagr` at line 12; called at lines 62-63 |
| `patent_gap_scorer.py` | `analysis/normalization.py` | `sigmoid_normalize` for 0-100 mapping | WIRED | `from ai_washer.analysis.normalization import sigmoid_normalize` at line 13; called at line 74 |
| `scoring_orchestrator.py` | `patent_gap_scorer.py` | calls `compute_patent_gap_score` with loaded data | WIRED | `from ai_washer.analysis.patent_gap_scorer import compute_patent_gap_score` at line 24; called at line 216 |
| `scoring_orchestrator.py` | `db/models.py` | queries `Patent` model for patent counts by year | WIRED | `Patent` imported line 31; `_load_patent_counts` uses `extract("year", Patent.patent_date)` grouped by year |
| `cli.py` | `patent_collector.py` | `PatentCollector` for CLI collect commands | WIRED | `from ai_washer.ingestion.patent_collector import PatentCollector` at lines 433 and 469 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `scoring_orchestrator.py` | `patent_counts` | `_load_patent_counts` queries `Patent` table with `func.count()` grouped by `patent_date.year` | Yes — real DB aggregation query | FLOWING |
| `scoring_orchestrator.py` | `ai_keyword_counts` | `compute_keyword_counts_by_year(filings)` — shared from SEC filing scorer, no recomputation | Yes — derived from real filing data already loaded | FLOWING |
| `patent_collector.py` | `all_patents` | `patent_client.search_by_assignee(name)` — real HTTP call to PatentSearch API | Yes — live API response validated via `PatentRecord` | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| CLI patent subcommand exposes `collect` and `collect-all` | `CliRunner().invoke(app, ['patent', '--help'])` | Output shows both commands | PASS |
| Scorer returns high score for high claim growth + flat patents | `compute_patent_gap_score({2021:2,...}, {2021:10.0,...,2024:40.0}, 2024)` | `score=76, signal_type="patent_gap"` | PASS |
| Scorer returns None for insufficient overlapping data | `compute_patent_gap_score({2024:5}, {2024:10.0}, 2024)` | `None` | PASS |
| All analysis package imports resolve | `from ai_washer.analysis import compute_patent_gap_score, ScoringOrchestrator` | `All imports OK` | PASS |
| 49 phase 5 unit tests pass | `pytest tests/unit/test_patent_*.py` | `49 passed` | PASS |
| Full unit suite (571 tests) passes with no regressions | `pytest tests/unit/` | `571 passed` | PASS |

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| PAT-01 | 05-01, 05-02, 05-03 | System queries USPTO PatentsView API for AI-related patents by company using CPC codes G06N and G06F18 | SATISFIED | `PatentSearchClient._build_query` uses `_begins` filter for `G06N` and `G06F18`; `X-Api-Key` header; endpoint `{base_url}/patent/` |
| PAT-02 | 05-03 | Patent gap score (0-100) measures AI patent filing trend against AI claim intensity from filings | SATISFIED | `compute_patent_gap_score` produces CAGR-based ratio of claim intensity vs patent filing trend, sigmoid-normalized to 0-100; integrated into `ScoringOrchestrator.score_company` |
| PAT-03 | 05-01, 05-02, 05-03 | Patent data refreshes weekly (patents move slowly) | SATISFIED | Incremental collection via `_get_last_patent_date` (MAX query per company); unique constraint `uq_patents_company_patent_id` provides idempotency; `collect_all` with inter-company delay supports scheduled weekly runs |

All 3 requirement IDs (PAT-01, PAT-02, PAT-03) declared across plan frontmatter are accounted for and satisfied.

No orphaned requirements found — REQUIREMENTS.md shows all three mapped to Phase 5 with status "Complete".

---

### Anti-Patterns Found

None. Scan across all 8 key implementation files found zero instances of:
- TODO/FIXME/HACK/placeholder comments
- Stub return patterns (`return null`, `return []`, `return {}`)
- Empty handlers
- Hardcoded empty props passed to rendering code

---

### Human Verification Required

#### 1. PatentsView API Live Query

**Test:** Set `PATENTSVIEW_API_KEY` in `.env` and run `ai-washer patent collect <ticker>` for a large company (e.g., MSFT).
**Expected:** Non-zero `patent_count`, collection completes without error, patents visible in DB with AI-related CPC codes.
**Why human:** Live API call requires valid key and network access; PatentsView API key approval may be pending.

#### 2. Pagination at Scale

**Test:** Run collection for a company known to have 100+ AI patents in USPTO. Verify all pages are fetched.
**Expected:** `pages_fetched > 1` in structured logs, patent count matches what PatentsView reports for that assignee.
**Why human:** Requires live API + known reference company; can't mock cursor boundary behavior at true scale.

#### 3. Weekly Refresh Idempotency

**Test:** Run `patent collect-all` twice in succession against a populated DB.
**Expected:** Second run shows `skipped_count` equal to first run's `patent_count`; `patent_count` on second run is 0 (or near-zero if new grants appear).
**Why human:** Requires populated DB with real patent data and controlled timing.

---

### Summary

Phase 5 goal is fully achieved. The patent gap signal pipeline is complete end-to-end:

1. **Types (Plan 01):** `PatentRecord` validates USPTO API responses at the ingestion boundary; `PatentForScoring` is a frozen dataclass for immutable scoring inputs; `Patent` ORM model follows the append-only pattern with a unique constraint; migration 004 creates the schema; `PatentGapScoringConfig` extends `ScoringConfig` with configurable sigmoid parameters.

2. **Ingestion (Plan 02):** `PatentSearchClient` queries the PatentSearch API with correct `_begins` CPC filters and `_contains` assignee filter, handles cursor-based pagination (10-page safety cap), retries 429/5xx via tenacity, and raises clear errors on missing API key or auth failure. `PatentCollector` searches all `patent_assignee` aliases, uses incremental collection via `MAX(patent_date)`, deduplicates cross-assignee by `patent_id`, and persists with collection metadata.

3. **Scoring and CLI (Plan 03):** `compute_patent_gap_score` is a pure function computing CAGR-based divergence between AI claim intensity (from SEC filings, shared with compute scorer) and patent filing trend, normalized via sigmoid to 0-100. `ScoringOrchestrator.score_company` now produces three signals: `sec_filing`, `compute_spending`, and `patent_gap`. CLI `patent collect` and `patent collect-all` commands with `--dry-run` support are registered.

All 571 unit tests pass with no regressions. No anti-patterns detected.

---

_Verified: 2026-03-28T22:50:00Z_
_Verifier: Claude (gsd-verifier)_
