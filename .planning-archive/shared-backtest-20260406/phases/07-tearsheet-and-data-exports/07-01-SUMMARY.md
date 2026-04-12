---
phase: 07-tearsheet-and-data-exports
plan: "01"
subsystem: backtest/reports
tags: [tdd, matplotlib, pdf, csv, json, exports, tearsheet]
dependency_graph:
  requires:
    - fund_backtest.simulator.types (CostConfig, PortfolioResult)
    - fund_backtest.metrics.types (MetricsBundle)
    - fund_backtest.dashboard.demo_data (test fixtures)
  provides:
    - fund_backtest.reports.TearsheetBuilder
    - fund_backtest.reports.ExportBuilder
  affects:
    - downstream consumers of PDF tearsheets
    - downstream consumers of CSV/JSON exports
tech_stack:
  added: []
  patterns:
    - matplotlib PdfPages for PDF generation (Agg backend, no display required)
    - _prepend_cost_header() module-level helper for prepending CSV comment lines
    - gridspec.GridSpec for multi-panel figure layout
key_files:
  created:
    - backtest/src/fund_backtest/reports/__init__.py
    - backtest/src/fund_backtest/reports/tearsheet.py
    - backtest/src/fund_backtest/reports/exporter.py
    - backtest/tests/unit/test_tearsheet.py
    - backtest/tests/unit/test_exporter.py
  modified: []
decisions:
  - Matplotlib Agg backend guarded with get_backend() != "Agg" check before use() call to avoid double-switching when already set
  - Monthly heatmap uses 'ME' resample alias (pandas 3.x compatible, per Phase 06 decision)
  - _prepend_cost_header() is a module-level private function (not a method) — no state needed
  - Rolling Series fields excluded from JSON by explicit key enumeration (not model_dump) for safety
metrics:
  duration: "3 minutes"
  completed: "2026-03-29T18:36:14Z"
  tasks_completed: 2
  files_created: 5
  files_modified: 0
  tests_added: 13
  tests_passing: 13
---

# Phase 7 Plan 1: Tearsheet and Data Exports Summary

**One-liner:** matplotlib PDF tearsheet (equity/drawdown/heatmap/metrics) and CSV+JSON exports with cost assumptions embedded in every output file.

## What Was Built

Implemented the `reports/` package with two classes:

**TearsheetBuilder** (`reports/tearsheet.py`):
- `build(result, bundle, cost_config, output_path) -> Path`
- Generates a US Letter (11x8.5") PDF with 4 panels via GridSpec:
  - Row 0 (full width): Equity curve from cumulative net returns
  - Row 1 (full width): Drawdown fill (red, alpha 0.3)
  - Row 2 left: Monthly returns heatmap (imshow, RdYlGn colormap, ME resampling)
  - Row 2 right: Metrics table with 10 risk/return metrics + 3 cost assumption rows
- Uses `matplotlib.backends.backend_pdf.PdfPages` for valid PDF output
- Sets PDF metadata title to "AI Hedge Fund — Backtest Tearsheet"

**ExportBuilder** (`reports/exporter.py`):
- `export_csv(result, cost_config, output_dir) -> list[Path]`
  - Writes `daily_returns.csv`, `positions.csv`, `trade_log.csv`
  - All files: ISO 8601 dates (YYYY-MM-DD via `date_format="%Y-%m-%d"`)
  - All files: First line is `# cost_assumptions: slippage=Xbps, commission=Xbps, borrow=Xbps/yr`
- `export_json(bundle, cost_config, output_dir) -> Path`
  - Writes `metrics.json` with 10 scalar metrics + `cost_assumptions` dict
  - Explicitly excludes `rolling_sharpe` and `rolling_drawdown` (non-JSON-serializable)

## Tests (13 passing)

**test_tearsheet.py** (3 tests):
- `test_build_creates_pdf_file`: file exists and size > 0
- `test_pdf_is_valid_pdf`: magic bytes `b"%PDF"`
- `test_build_returns_path`: return value equals input path

**test_exporter.py** (10 tests):
- `test_export_csv_creates_three_files`: all 3 CSV files present
- `test_csv_dates_are_iso8601`: second data line starts with "20", no "00:00:00"
- `test_csv_has_cost_comment`: first line of each CSV starts with "# cost_assumptions:"
- `test_csv_cost_values_match_config`: comment contains exact bps values
- `test_export_csv_returns_three_paths`: list of 3 Path objects
- `test_export_json_creates_metrics_file`: metrics.json exists
- `test_json_has_cost_assumptions_key`: JSON has cost_assumptions with 3 keys
- `test_json_excludes_rolling_series`: no rolling_sharpe or rolling_drawdown in JSON
- `test_json_scalar_values_match_bundle`: all 10 scalar metrics match bundle
- `test_export_json_returns_path`: returns Path to metrics.json

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all output methods produce real file content.

## Self-Check: PASSED
