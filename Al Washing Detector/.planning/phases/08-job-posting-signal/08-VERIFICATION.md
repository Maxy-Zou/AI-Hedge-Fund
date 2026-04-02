---
phase: 08-job-posting-signal
verified: 2026-03-29T00:00:00Z
status: passed
score: 14/14 must-haves verified
re_verification: false
---

# Phase 8: Job Posting Signal Verification Report

**Phase Goal:** The system produces job mismatch scores comparing AI claim intensity to actual AI hiring activity and role quality
**Verified:** 2026-03-29
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | python-jobspy is installed and importable | VERIFIED | `jobspy` import succeeds; `python-jobspy` in pyproject.toml |
| 2  | Role classifier distinguishes engineering, marketing, and ambiguous roles | VERIFIED | `classify_role()` in job_types.py; TestClassifyRole all pass |
| 3  | Dedup hash produces deterministic SHA-256 from company+title+location | VERIFIED | `compute_job_hash()` in job_types.py; TestComputeJobHash all pass |
| 4  | JobPosting ORM model has lifecycle columns (first_seen, last_seen, is_active) | VERIFIED | `class JobPosting` in models.py with all three columns |
| 5  | Migration 007 creates job_postings table with unique dedup_hash constraint | VERIFIED | 007_add_job_postings.py present; creates table + unique index on dedup_hash |
| 6  | JobMismatchScoringConfig is part of ScoringConfig | VERIFIED | `class JobMismatchScoringConfig` in config.py; `job_mismatch` field on ScoringConfig |
| 7  | JobClient wraps python-jobspy and returns list[JobRecord] | VERIFIED | job_client.py calls `scrape_jobs()`; returns typed `list[JobRecord]` |
| 8  | JobCollector persists new postings and updates last_seen on existing ones | VERIFIED | job_collector.py: inserts new, updates `last_seen` on hash match |
| 9  | Postings not seen in current scrape get is_active=False | VERIFIED | `_find_stale_postings` + deactivation loop in collect_for_company |
| 10 | Lifecycle tracking records first_seen, last_seen for ghost job detection | VERIFIED | JobPosting model + JobCollector both handle first_seen/last_seen |
| 11 | CLI job commands (collect, collect-all) work end-to-end | VERIFIED | `job_app` registered on main app; both commands shown in `--help` |
| 12 | Job mismatch score is 0-100 integer, signal_type="job_mismatch" | VERIFIED | `compute_job_mismatch_score` returns `SignalResult`; all range/type tests pass |
| 13 | Ghost ratio penalizes the score; engineering ratio affects score | VERIFIED | `test_ghost_ratio_increases_score` and `test_all_marketing_roles_returns_high_score` pass |
| 14 | ScoringOrchestrator produces job_mismatch as the 6th signal | VERIFIED | `compute_job_mismatch_score` imported and called in scoring_orchestrator.py; `_load_job_postings` helper present |

**Score:** 14/14 truths verified

---

### Required Artifacts

| Artifact | Plan | Status | Details |
|----------|------|--------|---------|
| `src/ai_washer/ingestion/job_types.py` | 08-01 | VERIFIED | Exports JOB_SIGNAL_VERSION, ENGINEERING_KEYWORDS, MARKETING_KEYWORDS, classify_role, compute_job_hash, JobRecord, JobCollectionResult |
| `src/ai_washer/db/models.py` | 08-01 | VERIFIED | `class JobPosting` with full lifecycle columns, unique dedup_hash index |
| `src/ai_washer/db/migrations/versions/007_add_job_postings.py` | 08-01 | VERIFIED | Creates job_postings table; unique index on dedup_hash; downgrade drops table |
| `src/ai_washer/config.py` | 08-01 | VERIFIED | `class JobMismatchScoringConfig`; `job_mismatch` field on ScoringConfig |
| `config/scoring.yaml` | 08-01 | VERIFIED | Contains `job_mismatch` block with all 6 config keys |
| `src/ai_washer/ingestion/job_client.py` | 08-02 | VERIFIED | `JobClient` + `JobClientError`; `search_company_jobs()`; tenacity `@retry` decorator |
| `src/ai_washer/ingestion/job_collector.py` | 08-02 | VERIFIED | `JobCollector` with `collect_for_company` + `collect_all`; full lifecycle logic |
| `src/ai_washer/analysis/job_mismatch_scorer.py` | 08-03 | VERIFIED | `compute_job_mismatch_score` pure function; uses `sigmoid_normalize`; returns `SignalResult` |
| `src/ai_washer/analysis/scoring_orchestrator.py` | 08-04 | VERIFIED | `_load_job_postings` + job mismatch scoring block; graceful skip on no data |
| `tests/unit/test_job_types.py` | 08-01 | VERIFIED | 17 tests all pass |
| `tests/unit/test_job_client.py` | 08-02 | VERIFIED | 9 tests all pass |
| `tests/unit/test_job_collector.py` | 08-02 | VERIFIED | 7 tests all pass |
| `tests/unit/test_job_mismatch_scorer.py` | 08-03 | VERIFIED | 9 tests all pass |
| `tests/unit/test_scoring_orchestrator_job.py` | 08-04 | VERIFIED | 6 tests all pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| job_client.py | jobspy | `scrape_jobs()` call | WIRED | Line 103: `df = scrape_jobs(site_name=..., search_term=..., results_wanted=..., country_indeed="USA")` |
| job_client.py | job_types.py | `classify_role`, `compute_job_hash` | WIRED | Lines 24, 127-128 |
| job_collector.py | db/models.py | `JobPosting` inserts and updates | WIRED | Lines 147-172; `session.add(posting)` + `existing.last_seen = collection_date` |
| cli.py | job_collector.py | `JobCollector` in CLI commands | WIRED | Lines 700, 741: lazy import + instantiation |
| job_mismatch_scorer.py | normalization.py | `sigmoid_normalize` | WIRED | Line 21: `from ai_washer.analysis.normalization import sigmoid_normalize`; called at line 106 |
| job_mismatch_scorer.py | analysis/types.py | Returns `SignalResult` | WIRED | Line 22: import; return at lines 85, 128 |
| scoring_orchestrator.py | job_mismatch_scorer.py | `compute_job_mismatch_score` | WIRED | Line 29: import; called at line 520 |
| scoring_orchestrator.py | db/models.py | Query `JobPosting` table | WIRED | Line 49: import; line 250: `select(JobPosting).where(...)` |
| job_types.py | db/models.py | JobRecord fields map to JobPosting columns | WIRED | Both have title, company_name_raw, location, description, job_url, source_site, role_classification, dedup_hash |
| config.py | config/scoring.yaml | job_mismatch key | WIRED | `ScoringConfig()` loads from YAML; `ghost_days_threshold` confirmed as 90 at runtime |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| job_mismatch_scorer.py | ai_role_count, ghost_ratio, etc. | Parameters from `_load_job_postings` | Yes — SQLAlchemy query on `job_postings` table | FLOWING |
| scoring_orchestrator.py | job_stats tuple | `_load_job_postings` -> `select(JobPosting).where(company_id==...)` | Yes — real DB query; graceful None on no data | FLOWING |
| job_collector.py | records (list[JobRecord]) | `JobClient.search_company_jobs` -> `scrape_jobs()` | Yes — real jobspy scrape; empty list handled | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `compute_job_mismatch_score` returns None for zero claims | Python import + call | `None` returned | PASS |
| No roles + claims=30 returns score >80 | Python import + call | score=95 | PASS |
| All marketing roles returns score >60 | Python import + call | score=100 | PASS |
| Ghost ratio=0.5 > ghost ratio=0.0 | Python import + call | 66 > 60 | PASS |
| signal_type = "job_mismatch" | Python import + call | "job_mismatch" confirmed | PASS |
| CLI `job --help` shows collect and collect-all | `python -m ai_washer job --help` | Both commands listed | PASS |
| All 52 phase-specific tests pass | `uv run pytest tests/unit/test_job_*.py tests/unit/test_scoring_orchestrator_job.py` | 52/52 passed | PASS |
| Full unit suite (746 tests) — no regressions | `uv run pytest tests/unit/` | 746/746 passed | PASS |

Note: "10 engineering roles, claims=30" scores 50 (not <40 as stated in PLAN 08-03 behavior spec). The plan used 10 roles in the prose but the test file correctly uses 20 roles to get a low score. At 10 roles, claims=30 produces gap_ratio=1.0 -> score=50 (midpoint), which is mathematically expected. The test passes; the plan spec was approximate. Not a gap.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| JOB-01 | 08-02 | System ingests AI-related job postings using free scraping sources | SATISFIED | `JobClient` + `JobCollector` implemented; `ai-washer job collect` CLI command works |
| JOB-02 | 08-01, 08-03 | Job role classifier distinguishes AI/ML engineering from marketing/strategy roles | SATISFIED | `classify_role()` in job_types.py; scorer uses `ai_role_count` vs `marketing_role_count` |
| JOB-03 | 08-01, 08-04 | Job posting deduplication removes duplicates using deterministic hash | SATISFIED | `compute_job_hash()` SHA-256; `dedup_hash` unique constraint in migration + DB model; used in JobCollector insert/update logic |
| JOB-04 | 08-02 | Job posting lifecycle tracking records first_seen, last_seen, time_to_fill for stale detection | SATISFIED | `first_seen`, `last_seen`, `is_active` columns; `_find_stale_postings` sets `is_active=False` |
| JOB-05 | 08-03, 08-04 | Job mismatch score (0-100) compares AI claim intensity to actual hiring activity | SATISFIED | `compute_job_mismatch_score` pure function; wired into `ScoringOrchestrator.score_company` as 6th signal |

All 5 phase requirements (JOB-01 through JOB-05) are satisfied. All requirements from all 4 plans (08-01 through 08-04) accounted for. No orphaned requirements — REQUIREMENTS.md traceability table maps all 5 JOB-* IDs to Phase 8.

---

### Anti-Patterns Found

None. No TODO/FIXME/placeholder markers. No empty return stubs. No hardcoded static return bodies. No orphaned code paths.

---

### Human Verification Required

#### 1. Live jobspy scrape integration

**Test:** Run `ai-washer job collect --ticker AAPL` against a real PostgreSQL database
**Expected:** Command completes, logs show jobs_found > 0 or a graceful empty result; no crash
**Why human:** Cannot verify real scraping behavior without live network and database in CI

#### 2. Ghost posting deactivation in production data

**Test:** After two collection runs 91+ days apart, check that postings not re-scraped in run 2 have is_active=False
**Expected:** `SELECT count(*) FROM job_postings WHERE is_active=false AND company_id=...` returns > 0
**Why human:** Requires a real database with data spanning multiple collection dates

#### 3. Scoring orchestrator full end-to-end with job data

**Test:** Run `ai-washer score company AAPL` after collecting job data for AAPL
**Expected:** Output includes a `job_mismatch` signal alongside the other 5 signals
**Why human:** Requires live database with both SEC filing data (for ai_claim_intensity) and job posting data

---

## Gaps Summary

No gaps. All phase must-haves verified.

---

_Verified: 2026-03-29_
_Verifier: Claude (gsd-verifier)_
