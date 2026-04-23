---
phase: 02-data-ingestion
plan: 04
subsystem: sentiment-macro-tools
tags: [finnhub, fred, sentiment, macro, temporal-enforcement, tools]
dependency_graph:
  requires: [02-01]
  provides: [finnhub-client, fred-client, sentiment-tools, macro-tools]
  affects: [agent-pipelines, research-agents]
tech_stack:
  added: []
  patterns: [FinnhubClient-wrapper, FredClient-wrapper, enforce_as_of_date-on-tools, check-before-insert-caching, None-sentiment-handling]
key_files:
  created:
    - src/ai_hedge_fund/data/clients/__init__.py
    - src/ai_hedge_fund/data/clients/finnhub_client.py
    - src/ai_hedge_fund/data/clients/fred_client.py
    - src/ai_hedge_fund/data/tools/sentiment_tools.py
    - src/ai_hedge_fund/data/tools/macro_tools.py
    - tests/unit/test_sentiment_tools.py
    - tests/unit/test_macro_tools.py
  modified:
    - src/ai_hedge_fund/data/tools/__init__.py
decisions:
  - Used check-before-insert pattern for DB caching instead of raw SQL ON CONFLICT (SQLite test compatibility)
  - None sentiment scores replaced with 0.0 before passing to format_news_summary (existing formatter does not handle None)
  - CPI YoY uses 12-month DateOffset comparison from pandas; GDP growth uses QoQ annualized formula ((1+r)^4-1)
metrics:
  duration: 7m
  completed: "2026-04-12T08:02:00Z"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 36
  files_created: 7
  files_modified: 1
---

# Phase 02 Plan 04: Sentiment and Macro Tools Summary

Finnhub news sentiment aggregation and FRED macro indicator retrieval with temporal controls, natural language summaries, and DB caching via FinnhubClient and FredClient wrappers.

## Completed Tasks

| # | Name | Commit | Tests |
|---|------|--------|-------|
| 1 | Finnhub news client and daily sentiment tools | c532b25 | 17 |
| 2 | FRED macro data client and macro context tools | 93805ef | 19 |

## Key Artifacts

### FinnhubClient (`src/ai_hedge_fund/data/clients/finnhub_client.py`)
- `FinnhubClient(api_key)` -- wraps finnhub-python SDK with API key validation
- `get_company_news(ticker, from_date, to_date)` -- retrieves news articles mapped to standardized dicts; tenacity retry with exponential backoff; returns empty list on error
- `get_news_sentiment(ticker)` -- retrieves aggregate sentiment scores (buzz_score, company_score, sector_average)
- Response mapping: unix timestamp to UTC datetime, headline/source/url extraction

### FredClient (`src/ai_hedge_fund/data/clients/fred_client.py`)
- `FRED_SERIES` -- config dict mapping 7 series: FEDFUNDS, CPIAUCSL, GDP, GDPC1, T10Y2Y, DGS10, DGS2
- `FredClient(api_key)` -- wraps fredapi.Fred with API key validation
- `get_series(series_id, observation_start, observation_end)` -- retrieves pandas Series with tenacity retry
- `get_latest_values(as_of_date)` -- returns dict of latest non-NaN value per series, filtered by as_of_date
- `compute_cpi_yoy(as_of_date)` -- YoY percentage change from 12-month-ago CPI observation
- `compute_gdp_growth(as_of_date)` -- QoQ annualized real GDP growth from prior quarter

### Sentiment Tool (`src/ai_hedge_fund/data/tools/sentiment_tools.py`)
- `@enforce_as_of_date get_news_sentiment(ticker, as_of_date, lookback_days=7, db_session, settings)` -- single-call tool for agents
- Temporal filtering: excludes articles with published_date > end-of-day as_of_date
- Average sentiment: computed from non-None scores only
- NL summary via `format_news_summary`; returns "No recent news" for empty results
- DB caching: articles stored to NewsArticle model via check-before-insert

### Macro Tool (`src/ai_hedge_fund/data/tools/macro_tools.py`)
- `@enforce_as_of_date get_macro_context(as_of_date, db_session, settings)` -- single-call tool (no ticker -- market-wide)
- Fetches all 7 FRED series, computes CPI YoY and GDP growth
- NL summary via `format_macro_summary`; handles None values by defaulting to 0.0
- DB caching: observations stored to MacroIndicator model via check-before-insert

### Re-exports (`src/ai_hedge_fund/data/tools/__init__.py`)
- Exports: `get_news_sentiment`, `get_macro_context`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] format_news_summary does not handle None sentiment scores**
- **Found during:** Task 1 TDD GREEN
- **Issue:** The existing `format_news_summary` in `summary.py` calls `sum(a["sentiment_score"] for a in articles)` which fails with TypeError when sentiment_score is None (Finnhub does not always provide sentiment)
- **Fix:** In sentiment_tools.py, replace None sentiment_score with 0.0 in a copy of the articles list before passing to the formatter; original articles retain None for transparency
- **Files modified:** `src/ai_hedge_fund/data/tools/sentiment_tools.py`
- **Commit:** c532b25

## Verification Results

- 36 unit tests passing (17 sentiment + 19 macro)
- ruff check clean on all 4 source files
- All tools use `@enforce_as_of_date` decorator
- API keys loaded from config, never hardcoded
- All acceptance criteria from plan verified

## Known Stubs

None -- all data paths are fully wired to real API clients (mocked in tests).

## Threat Flags

None -- all new surface matches the plan's threat model (T-02-14 through T-02-18).

## Self-Check: PASSED

- All 8 created/modified files verified on disk
- Both task commits (c532b25, 93805ef) verified in git log
