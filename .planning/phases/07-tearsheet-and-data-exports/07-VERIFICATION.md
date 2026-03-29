---
phase: 07-tearsheet-and-data-exports
verified: 2026-03-29T19:15:00Z
status: passed
score: 10/10 must-haves verified
re_verification: false
gaps: []
human_verification: []
---

# Phase 7: Tearsheet and Data Exports Verification Report

**Phase Goal:** A single-page PDF tearsheet and machine-readable CSV/JSON exports are generated from any backtest run, with all cost assumptions explicitly labelled
**Verified:** 2026-03-29T19:15:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | TearsheetBuilder.build() writes a PDF file that exists on disk | VERIFIED | test_build_creates_pdf_file PASSED; file exists with size > 0 and b"%PDF" magic bytes |
| 2 | The PDF includes cost assumptions (slippage, commission, borrow) visible in the metrics table | VERIFIED | tearsheet.py lines 176-179: "--- Cost Assumptions ---", Slippage, Commission, Borrow Rate rows in table |
| 3 | ExportBuilder.export_csv() writes daily_returns.csv, positions.csv, and trade_log.csv with ISO 8601 dates | VERIFIED | test_export_csv_creates_three_files and test_csv_dates_are_iso8601 PASSED; date_format="%Y-%m-%d" used |
| 4 | ExportBuilder.export_json() writes metrics.json with a cost_assumptions key | VERIFIED | test_json_has_cost_assumptions_key PASSED; exporter.py lines 129-133 confirm key present |
| 5 | All CSV files include a # cost_assumptions: comment as the first line | VERIFIED | test_csv_has_cost_comment PASSED; _prepend_cost_header() function confirmed in exporter.py |
| 6 | All export methods accept PortfolioResult, MetricsBundle, and CostConfig from existing types | VERIFIED | Both classes import from fund_backtest.simulator.types and fund_backtest.metrics.types |
| 7 | Running `fund-backtest backtest export --tearsheet` writes a PDF to the output directory | VERIFIED | test_export_tearsheet_creates_pdf PASSED via CliRunner; exit_code 0, tearsheet.pdf exists |
| 8 | Running `fund-backtest backtest export --csv` writes daily_returns.csv, positions.csv, trade_log.csv | VERIFIED | test_export_csv_creates_three_files (CLI) PASSED; all 3 files created |
| 9 | Running `fund-backtest backtest export --json` writes metrics.json | VERIFIED | test_export_json_creates_metrics_file (CLI) PASSED; metrics.json created |
| 10 | Running `fund-backtest backtest export --all` runs all three exports in one command | VERIFIED | test_export_all_creates_all_outputs PASSED; all 5 output files created |

**Score:** 10/10 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backtest/src/fund_backtest/reports/__init__.py` | Public exports: TearsheetBuilder, ExportBuilder | VERIFIED | Exports both classes; `__all__ = ["TearsheetBuilder", "ExportBuilder"]` |
| `backtest/src/fund_backtest/reports/tearsheet.py` | TearsheetBuilder class with .build() method | VERIFIED | 184-line substantive implementation; 4-panel matplotlib GridSpec layout |
| `backtest/src/fund_backtest/reports/exporter.py` | ExportBuilder class with .export_csv() and .export_json() methods | VERIFIED | 139-line implementation; both methods produce real file output |
| `backtest/tests/unit/test_tearsheet.py` | Unit tests for TearsheetBuilder | VERIFIED | 3 tests: test_build_creates_pdf_file, test_pdf_is_valid_pdf, test_build_returns_path |
| `backtest/tests/unit/test_exporter.py` | Unit tests for ExportBuilder | VERIFIED | 10 tests covering CSV files, cost comments, JSON schema, rolling series exclusion |
| `backtest/src/fund_backtest/cli.py` | backtest_app + export command wired into main app | VERIFIED | backtest_app registered; @backtest_app.command(name="export") with 5 flags |
| `backtest/tests/unit/test_cli.py` | CLI integration tests for export commands | VERIFIED | 5 export tests appended: --tearsheet, --csv, --json, --all, no-flags |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `reports/tearsheet.py` | `fund_backtest.simulator.types.PortfolioResult` | direct import | VERIFIED | Line 34: `from fund_backtest.simulator.types import CostConfig, PortfolioResult` |
| `reports/tearsheet.py` | `fund_backtest.metrics.types.MetricsBundle` | direct import | VERIFIED | Line 33: `from fund_backtest.metrics.types import MetricsBundle` |
| `reports/exporter.py` | `cost_config.slippage_bps, commission_bps, borrow_cost_bps_annual` | _prepend_cost_header uses CostConfig fields | VERIFIED | Lines 43-45 reference all three fields dynamically (not hardcoded) |
| `cli.py` | `fund_backtest.reports.TearsheetBuilder` | import in export command handler | VERIFIED | Line 28: `from fund_backtest.reports import ExportBuilder, TearsheetBuilder` |
| `cli.py` | `fund_backtest.dashboard.demo_data.make_demo_result` | demo data in export commands | VERIFIED | Line 22: `from fund_backtest.dashboard.demo_data import make_demo_bundle, make_demo_result`; lines 274-275 call both |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `cli.py` export command | `result`, `bundle`, `cost_config` | `make_demo_result()`, `make_demo_bundle(result)`, `load_cost_config()` | Yes — demo data produces populated PortfolioResult with real pandas Series/DataFrames; cost_config loaded from config | FLOWING (demo mode by design; Phase 8 replaces with live data) |
| `tearsheet.py` | `net_returns`, `bundle`, `cost_config` | Passed in as arguments from caller | Yes — all 4 panels render from real PortfolioResult/MetricsBundle fields; cost table reads from CostConfig fields | FLOWING |
| `exporter.py` | `result.net_returns`, `result.positions`, `result.trade_log`, `bundle.*` | Passed in as arguments | Yes — pandas .to_csv() writes real data; json.dumps serializes real scalar fields | FLOWING |

Note: Demo mode is the documented design for Phase 7. The SUMMARY explicitly states "Phase 8 will replace `make_demo_result()` with live backtest runs." This is intentional, not a stub.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 13 unit tests for TearsheetBuilder + ExportBuilder pass | `.venv/bin/python -m pytest tests/unit/test_tearsheet.py tests/unit/test_exporter.py -v` | 13 passed in 7.95s | PASS |
| 5 CLI export tests pass | `.venv/bin/python -m pytest tests/unit/test_cli.py -k export -v` | 5 passed in 4.81s | PASS |
| Full unit suite passes | `.venv/bin/python -m pytest tests/unit/ -v` | 158 passed in 19.66s | PASS |
| Test coverage >= 80% | `.venv/bin/python -m pytest tests/unit/ --cov=fund_backtest` | TOTAL 80% (1200 stmts, 234 missed) | PASS |
| reports module import | `python -c "from fund_backtest.reports import TearsheetBuilder, ExportBuilder"` | SKIP — module not installed as editable outside venv; tests confirm import works via pytest | SKIP (pytest confirms) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| RPT-04 | 07-01-PLAN.md, 07-02-PLAN.md | PDF tearsheet generates a single-page fund factsheet with key metrics and charts | SATISFIED | TearsheetBuilder.build() produces valid PDF with equity curve, drawdown, monthly heatmap, and metrics/cost table; 3 unit tests + 1 CLI test confirm |
| RPT-05 | 07-01-PLAN.md, 07-02-PLAN.md | System exports daily returns, positions, and trade log as CSV and JSON | SATISFIED | ExportBuilder.export_csv() writes 3 CSVs with ISO 8601 dates; export_json() writes metrics.json; 10 unit tests + 2 CLI tests confirm |
| RPT-06 | 07-01-PLAN.md, 07-02-PLAN.md | All outputs label cost assumptions (slippage, borrow rate, commission) explicitly | SATISFIED | CSV first line = "# cost_assumptions: slippage=Xbps, commission=Xbps, borrow=Xbps/yr"; JSON contains "cost_assumptions" dict; PDF metrics table includes "--- Cost Assumptions ---" section with all 3 values |

No orphaned requirements — REQUIREMENTS.md maps RPT-04, RPT-05, RPT-06 to Phase 7 only.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | — | — | — |

No TODOs, FIXMEs, placeholder returns, or hardcoded empty values found in phase 7 files. The demo-mode data sourcing in the CLI export command (`make_demo_result()`) is an intentional design decision documented in both the PLAN and SUMMARY — Phase 8 will wire live data.

### Human Verification Required

None. All automated checks passed with sufficient confidence. The CLI operates in demo mode by design (documented in PLAN and SUMMARY as an explicit Phase 7 constraint). No visual or real-time behavior requires manual inspection beyond what the test suite already covers.

### Gaps Summary

No gaps. All 10 observable truths are verified, all 7 required artifacts exist and are substantive and wired, all 3 key links are confirmed, all 3 requirements (RPT-04, RPT-05, RPT-06) are satisfied, test coverage is exactly 80%, and 158 unit tests pass.

---

_Verified: 2026-03-29T19:15:00Z_
_Verifier: Claude (gsd-verifier)_
