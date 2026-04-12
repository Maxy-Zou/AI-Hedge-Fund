---
status: partial
phase: 02-data-ingestion
source: [02-VERIFICATION.md]
started: 2026-04-12
updated: 2026-04-12
---

## Current Test

[awaiting human testing]

## Tests

### 1. SEC EDGAR Live Temporal Filtering
expected: Call get_filing_sections("AAPL", as_of_date=date(2023, 6, 30)) with real EDGAR_IDENTITY — every filing has filing_date <= 2023-06-30, no future filings
result: [pending]

### 2. yfinance Failure to Tiingo Fallback
expected: Force yfinance empty data for real ticker; PriceClient.download returns Tiingo data with source="tiingo" and warning logged
result: [pending]

### 3. FRED API Temporal Boundary
expected: Call get_macro_context(as_of_date=date(2022, 1, 1)) with real FRED_API_KEY — all values reflect early 2022 data (fed_funds_rate ~0.08%)
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps

### Warning: sentiment_tools.py cache as_of_date bug
sentiment_tools.py line 136 stores `as_of_date=date.today()` instead of the tool's `as_of_date` parameter for cached NewsArticle records. Should be fixed before historical caching is relied upon.
