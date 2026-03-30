---
phase: 11-detector-execution
plan: 01
subsystem: Al Washing Detector
tags: [pytorch, efts-api, universe-scan, pre-flight, environment-setup]
dependency_graph:
  requires: []
  provides: [companies-table-populated, torch-installed, finbert-ready, efts-api-fix]
  affects: [11-02-pipeline-run]
tech_stack:
  added:
    - torch==2.2.2 (CPU-only wheel via download.pytorch.org/whl/cpu)
    - transformers downgraded 5.3.0 -> 4.57.6 (required for torch 2.2.2 compat on macOS x86_64)
  patterns:
    - EFTSHit.from_search_index() factory method for new EFTS search-index API format
    - EFTS field mapping: adsh->accession_no, form->form_type, period_ending->period_of_report
key_files:
  modified:
    - Al Washing Detector/src/ai_washer/ingestion/efts_client.py
    - Al Washing Detector/src/ai_washer/universe/types.py
decisions:
  - torch 2.2.2 installed via CPU wheel index; torch>=2.4 has no macOS x86_64 wheels (pyproject.toml conditional exclusion is correct)
  - transformers 4.57.6 used instead of 5.3.0 — transformers 5.x requires torch>=2.4; 4.57.6 is the last version compatible with torch 2.2.2
  - EFTS search-index API field rename discovered at runtime — adsh/form/period_ending replace accession_no/form_type/period_of_report; entity_name derived from display_names[0] prefix
metrics:
  duration: 41min
  completed_date: "2026-03-30"
  tasks_completed: 2
  files_modified: 2
---

# Phase 11 Plan 01: Pre-Flight Checks and Environment Setup Summary

**One-liner:** Installed PyTorch CPU wheel, fixed EFTS API field rename breaking universe scan, ran scan to populate 815 companies in database.

## What Was Built

Pre-flight environment verification for the AI Washing Detector pipeline, including dependency installation, EFTS API compatibility fix, and universe scan execution.

### Task 1: EDGAR Identity Verification (Auto-Approved)

The `AI_WASHER_EDGAR_IDENTITY` was already configured in `.env` with the value `AIHedgeFundResearch research@aihedgefund.dev` — a real identity satisfying SEC compliance requirements. This checkpoint was auto-approved per execution context instructions.

### Task 2: Install PyTorch and Run Pre-Flight Checks

**Step 1 — Docker:** Container `ai_hedge_fund_postgres` was already healthy (Up 2 hours).

**Step 2 — PyTorch installation:**
- Initial attempt: `uv pip install torch>=2.4` failed — torch>=2.4 has no macOS x86_64 wheels (only Linux/Windows aarch64/x86_64)
- The `pyproject.toml` conditional `sys_platform != 'darwin' or platform_machine == 'arm64'` correctly excluded torch on macOS x86_64
- Installed torch 2.2.2 via `uv pip install torch --index-url https://download.pytorch.org/whl/cpu`
- transformers 5.3.0 rejected torch 2.2.2 with "Disabling PyTorch because PyTorch >= 2.4 is required"
- Downgraded transformers to 4.57.6 (last version supporting torch 2.2.2) to restore FinBERT functionality

**Step 3 — EDGAR identity:** Confirmed `AIHedgeFundResearch research@aihedgefund.dev` is present and not a placeholder.

**Step 4 — Companies table:** Initially empty (Phase 10 universe scan data was not persisted yet). Universe scan executed in this plan.

**Step 5 — check-config:** All required vars reported valid after torch/transformers fix.

**Step 6 — Universe scan:** Command ran successfully with EFTS API fix (see Deviations). Scan took ~30 minutes, populated 815 companies.

**Step 7 — Universe list:** Real companies returned with CIK and market cap values (Alcoa, American Airlines, Microsoft, etc.).

## Verification Results

| Check | Status | Details |
|-------|--------|---------|
| torch import | PASS | torch 2.2.2 — CPU-only, sufficient for FinBERT on macOS x86_64 |
| FinBERT import | PASS | FinBERTAnalyzer instantiates without error after transformers downgrade |
| EDGAR identity | PASS | AIHedgeFundResearch research@aihedgefund.dev (real identity) |
| check-config | PASS | All required vars OK, no missing required vars |
| companies table | PASS | 815 active companies (requirement: >= 50) |
| universe list | PASS | Real companies with CIK values, market caps, tickers |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] EFTS search-index API field names changed**

- **Found during:** Task 2, Step 4 (universe scan execution)
- **Issue:** The EFTS API at `efts.sec.gov/LATEST/search-index` changed its `_source` field names. Previously returned `accession_no`, `form_type`, `entity_name`. Now returns `adsh`, `form`, and omits `entity_name` (derivable from `display_names[0]`). Also `period_of_report` is now `period_ending`.
- **Fix:** Added `EFTSHit.from_search_index()` factory classmethod in `universe/types.py` with explicit field mapping. Updated `EFTSClient._parse_efts_response()` to call `from_search_index()` instead of `EFTSHit(**hit["_source"])`.
- **Files modified:** `Al Washing Detector/src/ai_washer/ingestion/efts_client.py`, `Al Washing Detector/src/ai_washer/universe/types.py`
- **Commit:** e666c50

**2. [Rule 2 - Missing Critical Functionality] torch>=2.4 unavailable on macOS x86_64; transformers 5.x incompatible with torch 2.2.2**

- **Found during:** Task 2, Step 2 (PyTorch installation)
- **Issue:** `pyproject.toml` conditionally excluded torch on darwin+x86_64. torch>=2.4 has no macOS x86_64 CPU wheels. transformers 5.3.0 hard-requires torch>=2.4 and disables PyTorch when torch 2.2.2 is present, preventing FinBERT model loading.
- **Fix:** Installed torch 2.2.2 via CPU wheel index. Downgraded transformers from 5.3.0 to 4.57.6 (compatible with torch 2.2.2). FinBERT can now be instantiated and used for earnings vagueness scoring.
- **Impact:** The earnings vagueness signal will function at inference time. Pipeline plan (11-02) can proceed without a scoring stage failure.
- **Note:** This is a runtime environment fix — no source code changes to scoring logic.

## Known Stubs

None — this plan is operational (environment setup + data population), no UI or data stubs.

## Universe Scan Results

```
Scan date: 2026-03-30
Companies in universe: 832 (815 new + 17 updated)
Market cap range: $1.5B - $9B (widened per UniverseBuilder config)
Skipped (no market cap data): 2,964
Skipped (out of range): 2,922
EFTS results: 7,708 "artificial intelligence" + 4,020 "machine learning" = 11,728 raw
Unique CIKs after dedup: 3,796
Passed market cap filter: 832
Persisted to DB: 815 new, 17 updated
```

## Self-Check: PASSED

- e666c50: fix(11-01): update EFTSHit to handle changed EFTS search-index API format — confirmed via `git log --oneline -1`
- companies table: 815 active rows — confirmed via `SELECT COUNT(*) FROM companies WHERE is_active = true`
- torch 2.2.2: imports without error — confirmed via `python -c "import torch; print(torch.__version__)"`
- check-config: Configuration valid — confirmed via CLI output
