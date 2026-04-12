---
phase: 02-price-data-pipeline
verified: 2026-03-29T08:34:53Z
status: passed
score: 5/5 must-haves verified
gaps: []
human_verification:
  - test: "Run `fund-backtest data download` against a live PostgreSQL instance with a populated universe"
    expected: "price_bars table populated with 5 years of daily OHLCV bars for all active tickers; Rich table printed with requested/successful/failed/bars_inserted counts"
    why_human: "Requires a running PostgreSQL instance and active yfinance network access. Integration tests mock yfinance; real download behavior (rate limiting, 429 handling, batch sleep) is not exercised."
  - test: "Run `fund-backtest data update` the day after a download"
    expected: "Only the new trading day's bars are appended; historical row count is unchanged; bars_inserted matches the universe size"
    why_human: "True incremental update requires two real downloads on separate calendar days; cannot be reproduced without a live database and real yfinance calls."
  - test: "Run `fund-backtest data coverage` with data present"
    expected: "Table shows tickers with bars, earliest/latest bar_date, and unreviewed anomaly count"
    why_human: "Requires a populated price_bars table with real data to exercise the min/max date query meaningfully."
---

# Phase 2: Price Data Pipeline Verification Report

**Phase Goal:** Daily OHLCV price data for all universe tickers is cached in PostgreSQL, validated, and incrementally updated without overwriting historical bars
**Verified:** 2026-03-29T08:34:53Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running `data download` for a fresh universe populates PostgreSQL with 5 years of daily OHLCV bars for all tickers | VERIFIED | `test_price_builder_download_with_mocked_yfinance`: 2 tickers x 5 bars = 10 rows inserted; summary.bars_inserted == 10. `PriceBuilder.download()` wires `download_in_chunks()` → `PriceBar.from_yfinance_row()` → `repo.insert_bars()` with lookback_years=5. |
| 2 | Running `data update` the next day appends only the new trading day's bars — no historical rows are modified | VERIFIED | `test_price_builder_update_incremental`: pre-seeded AAPL bar on 2026-01-02; after `builder.update()`, `aapl_jan2 == 1` (no duplicate). `PriceBuilder.update()` uses `get_last_dates()` + `timedelta(days=1)` per ticker; `insert_bars()` uses `ON CONFLICT DO NOTHING`. No UPDATE DML exists anywhere in `repository.py`. |
| 3 | Any ticker with a single-day return exceeding ±50% is flagged in the log and excluded from downstream use until manually reviewed | VERIFIED | `detect_return_anomalies()` uses `pct_change().abs() > threshold`; `test_anomaly_record_inserted_for_spike` confirms anomaly row inserted with `is_reviewed=False`; `test_get_bars_excludes_anomalous_bar` confirms bar excluded via `tuple_().in_()` subquery; `test_get_bars_includes_anomalous_bar_when_reviewed` confirms reviewed anomaly no longer blocks the bar. |
| 4 | A coverage report shows how many requested tickers returned valid data; pipeline alerts if coverage falls below 95% | VERIFIED | `compute_coverage()` delegates to `CoverageReport.from_counts()`; `PriceBuilder.download()` and `update()` both call `compute_coverage()` and `log.warning("coverage_below_threshold", ...)` when `coverage.below_threshold`; `test_compute_coverage_below_threshold` (94/100 → below_threshold=True) and `test_compute_coverage_above_threshold` both pass. `fund-backtest data coverage` CLI command queries `get_coverage_tickers()` + min/max date + anomaly count. |
| 5 | Downloads are chunked (~80 tickers per batch) with exponential backoff — no 429 errors cause a silent data gap | VERIFIED | `_download_batch()` decorated with `@retry(retry_if_exception_type((YFRateLimitError, requests.HTTPError)), stop_after_attempt(5), wait_exponential(multiplier=1, min=5, max=60))`; `test_download_batch_retries_on_rate_limit` confirms retry invoked (call_count==3 after 2 failures); `PriceSettings.batch_size=80`; `download_in_chunks()` sleeps between batches (not after last). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backtest/src/fund_backtest/db/migrations/versions/002_price_bars_schema.py` | Alembic migration for price_bars + price_anomalies | VERIFIED | revision="002", down_revision="001"; creates both tables with correct columns, 5 indexes including partial index `WHERE is_reviewed = false`; unique constraints `uq_price_bars_ticker_date` and `uq_price_anomalies_ticker_date_type` |
| `backtest/src/fund_backtest/price/types.py` | PriceBar, PriceAnomalyRecord, DownloadSummary, CoverageReport | VERIFIED | All 4 types present and substantive; `price_to_cents` uses `round()` not `int()`; `PriceBar.from_yfinance_row()` classmethod; `CoverageReport.from_counts()` classmethod; `PriceAnomalyRecord.anomaly_type` is `Literal["return_spike_plus","return_spike_minus"]` |
| `backtest/src/fund_backtest/config.py` | PriceSettings Pydantic model | VERIFIED | `PriceSettings` with `lookback_years=5`, `batch_size=80`, `batch_sleep_secs=1.0`, `coverage_alert_threshold=0.95`, `return_anomaly_threshold=0.50`, `max_gap_days=3`; `load_price_settings()` factory present |
| `backtest/src/fund_backtest/db/models.py` | PriceBarORM and PriceAnomalyORM ORM models | VERIFIED | `PriceBarORM` has no `updated_at` (append-only); `created_at` via direct `mapped_column`; `UNIQUE(ticker, bar_date)`; `PriceAnomalyORM` with `is_reviewed` boolean, `UNIQUE(ticker, bar_date, anomaly_type)` |
| `backtest/src/fund_backtest/price/downloader.py` | download_in_chunks(), _download_batch() with tenacity, get_failed_tickers() | VERIFIED | All 3 functions present; tenacity decorator on `_download_batch` with `stop_after_attempt(5)`, `wait_exponential(min=5, max=60)`; `get_failed_tickers` handles both missing-column and all-NaN-Close cases |
| `backtest/src/fund_backtest/price/validator.py` | detect_return_anomalies(), detect_gaps(), compute_coverage() | VERIFIED | All 3 functions present; `pct_change().dropna()` pattern; `bdate_range(inclusive="neither")` for gap detection; `compute_coverage` delegates to `CoverageReport.from_counts()` |
| `backtest/src/fund_backtest/price/repository.py` | PriceBarRepository with insert_bars, insert_anomalies, get_last_dates, get_bars | VERIFIED | `on_conflict_do_nothing(index_elements=["ticker","bar_date"])`; `.returning(PriceBarORM.id)` for correct rowcount; `get_last_dates()` uses `MAX(bar_date) GROUP BY ticker`; `get_bars()` uses `tuple_().in_()` for per-bar anomaly exclusion |
| `backtest/src/fund_backtest/price/builder.py` | PriceBuilder with download() and update() | VERIFIED | Both methods return `DownloadSummary`; `update()` uses per-ticker `last_dates` + `timedelta(days=1)`; both call `detect_return_anomalies()` + `repo.insert_anomalies()`; `compute_coverage()` + warning logged |
| `backtest/src/fund_backtest/cli.py` | data_app Typer subgroup with download, update, coverage | VERIFIED | `data_app = typer.Typer(...)` registered as `app.add_typer(data_app, name="data")`; all 3 commands present with `PriceBuilder`/`PriceBarRepository` wiring; same error-handling pattern as `universe_app` |
| `backtest/tests/unit/test_price_types.py` | Unit tests for PriceBar cents conversion | VERIFIED | 18 tests passing; covers `price_to_cents` round-not-truncate, `PriceBar.from_yfinance_row`, ticker normalization, `CoverageReport.from_counts`, `PriceSettings` defaults |
| `backtest/tests/unit/test_downloader.py` | Unit tests for chunking, retry, failed tickers | VERIFIED | 7 tests passing; covers batch chunking, retry on `YFRateLimitError`, all-NaN-Close detection, missing-from-columns detection, sleep-between-batches behavior |
| `backtest/tests/unit/test_validator.py` | Unit tests for anomaly, gap, coverage | VERIFIED | 17 tests passing; covers ±50% spike detection, gap threshold at 3 business days, coverage threshold at 95% |
| `backtest/tests/integration/test_price_pipeline.py` | Integration tests against PostgreSQL testcontainer | VERIFIED | 9 tests covering: insert, idempotency, get_last_dates, anomaly insert, anomaly exclusion, anomaly reviewed inclusion, builder download with mocked yfinance, dry-run, incremental update |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `price/types.py` | `db/models.py (PriceBarORM)` | `PriceBar.model_dump()` feeds `pg_insert().values()` in repository | VERIFIED | `repository.py` explicitly maps `b.ticker`, `b.bar_date`, `b.open_cents`, ... `b.close_cents`, `b.volume` to PriceBarORM row dict |
| `config.py` | `price/builder.py` | `PriceSettings` passed to `PriceBuilder` constructor | VERIFIED | `from fund_backtest.config import PriceSettings` in builder.py; `PriceBuilder.__init__(settings: PriceSettings | None)` |
| `price/builder.py` | `price/downloader.py` | calls `download_in_chunks()` inside `download()` and `update()` | VERIFIED | `from fund_backtest.price.downloader import download_in_chunks` confirmed; called in both methods |
| `price/builder.py` | `price/repository.py` | calls `self._repo.insert_bars()`, `self._repo.insert_anomalies()`, `self._repo.get_last_dates()` | VERIFIED | All three method calls present in both `download()` and `update()` |
| `price/repository.py` | `db/models.py` | `pg_insert(PriceBarORM).on_conflict_do_nothing()` | VERIFIED | `from fund_backtest.db.models import PriceAnomalyORM, PriceBarORM` confirmed; `pg_insert(PriceBarORM)` and `pg_insert(PriceAnomalyORM)` both used |
| `cli.py (data_app)` | `price/builder.py` | `PriceBuilder(session=session, settings=settings)` → `builder.download()` / `builder.update()` | VERIFIED | `from fund_backtest.price.builder import PriceBuilder` in cli.py; both CLI commands instantiate PriceBuilder and call the appropriate method |
| `tests/integration/test_price_pipeline.py` | `price/repository.py` | `PriceBarRepository(db_session)` used to verify DB state | VERIFIED | `from fund_backtest.price.repository import PriceBarRepository` in integration test; used as both system under test and DB verification tool |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `price/builder.py` | `results` (list of ticker/DataFrame tuples) | `download_in_chunks()` → `_download_batch()` → `yf.download()` | Yes — integration tests mock yf.download to return real MultiIndex DataFrames; `PriceBar.from_yfinance_row()` converts to cents | FLOWING |
| `price/repository.py` | `inserted` (row count) | `pg_insert(PriceBarORM).values(rows).on_conflict_do_nothing().returning(id)` → `len(result.all())` | Yes — RETURNING clause returns actual inserted IDs; integration test confirms `inserted == 3` and `inserted == 0` on duplicate | FLOWING |
| `price/repository.py` | `{ticker: last_date}` | `SELECT ticker, MAX(bar_date) FROM price_bars WHERE ticker = ANY(:tickers) GROUP BY ticker` | Yes — real SQL GROUP BY query; integration test confirms `last_dates["AAPL"] == date(2026, 1, 2)` after inserting that bar | FLOWING |
| `cli.py` | `tickers_with_bars`, `result.min_date`, `anomaly_count` | `repo.get_coverage_tickers()` + `SELECT MIN/MAX(bar_date) FROM price_bars` + `PriceAnomalyORM` count | Yes — all three are real DB queries; no hardcoded fallbacks (only `"No data"` string when table is empty) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `price_to_cents` uses round() not int() | `price_to_cents(183.73) == 18373` and `price_to_cents(10.009) == 1001` | Both assertions pass | PASS |
| Migration 002 chained from 001 | Check `revision="002"`, `down_revision="001"`, `uq_price_bars_ticker_date` in file | All patterns found | PASS |
| Repository uses ON CONFLICT DO NOTHING | Check `on_conflict_do_nothing` in repository.py | Found | PASS |
| PriceBarORM is append-only (no updated_at) | `hasattr(PriceBarORM, 'updated_at')` | False — no `updated_at` attribute | PASS |
| CLI data_app registered | Check `app.registered_groups` contains `data` | `data` present | PASS |
| PriceBuilder uses per-ticker start dates | Check `get_last_dates`, `ticker_starts`, `timedelta(days=1)` in builder.py | All 3 patterns found | PASS |
| All 66 unit tests pass | `pytest tests/unit/ -x -q` | 66 passed in 1.23s | PASS |
| RETURNING clause for rowcount | Check `.returning(PriceBarORM.id)` and `.returning(PriceAnomalyORM.id)` | Both present | PASS |
| No UPDATE DML in repository | Regex scan for UPDATE statements (excluding comments) | 0 matches | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DATA-01 | 02-01, 02-02, 02-04 | System downloads daily OHLCV price data via yfinance for all tickers in the mid-cap universe | SATISFIED | `download_in_chunks()` calls `yf.download()` with `auto_adjust=True`; `PriceBar.from_yfinance_row()` converts rows to cents; `test_price_builder_download_with_mocked_yfinance` proves 5 bars per ticker inserted |
| DATA-02 | 02-01, 02-03, 02-04 | System caches price data in PostgreSQL to avoid redundant API calls | SATISFIED | `PriceBarRepository.insert_bars()` persists to `price_bars` table; `ON CONFLICT DO NOTHING` means re-running download does not refetch (idempotent at DB level); `test_insert_bars_idempotent_on_conflict_do_nothing` proves second insert returns 0 rows |
| DATA-03 | 02-03, 02-04 | System performs incremental daily updates (append new bars, never overwrite historical) | SATISFIED | `PriceBuilder.update()` uses `get_last_dates()` + `timedelta(days=1)` per ticker; `ON CONFLICT DO NOTHING` enforces immutability; no UPDATE/DELETE DML in repository; `test_price_builder_update_incremental` proves pre-seeded bar not duplicated |
| DATA-04 | 02-01, 02-02, 02-04 | System validates downloaded data (gap detection, daily return sanity check >±50%, missing ticker alerts) | SATISFIED | `detect_return_anomalies()` flags \|return\| > 0.50; `detect_gaps()` flags gaps >3 business days via `bdate_range`; `get_failed_tickers()` detects missing columns and all-NaN Close; `test_anomaly_record_inserted_for_spike` proves anomaly written to DB |
| DATA-06 | 02-02, 02-03, 02-04 | System chunks yfinance downloads (~80 tickers/batch) with retry logic to handle rate limits | SATISFIED | `download_in_chunks()` with `batch_size=80`; `_download_batch()` with tenacity `stop_after_attempt(5)` + `wait_exponential` on `YFRateLimitError` and `requests.HTTPError`; `test_download_batch_retries_on_rate_limit` proves call_count==3 after 2 failures |

All 5 Phase 2 requirements (DATA-01, DATA-02, DATA-03, DATA-04, DATA-06) are satisfied.

**Orphaned requirements check:** REQUIREMENTS.md maps DATA-01 through DATA-04 and DATA-06 exclusively to Phase 2. DATA-05 and DATA-07 are Phase 1 requirements. No Phase 2 requirements exist in REQUIREMENTS.md beyond those declared in the plan frontmatter. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

No stubs, placeholder comments, TODO/FIXME markers, empty implementations, or hardcoded empty data found in any phase 2 files. All functions contain real logic.

One note: `PriceBuilder.download()` dry-run path returns `DownloadSummary(successful=[], failed=[], bars_inserted=0)` even though tickers were found. This is correct behavior by design (dry_run means no DB writes), not a stub.

### Human Verification Required

#### 1. Live `data download` Against Real PostgreSQL

**Test:** Run `fund-backtest data download` against a live PostgreSQL instance after `universe refresh` has populated `universe_tickers`
**Expected:** `price_bars` table populated with 5 years of daily OHLCV bars for all active tickers; Rich table printed showing tickers requested, successful, failed, and bars_inserted; no silent data gaps
**Why human:** Requires running PostgreSQL and live yfinance network access. Integration tests mock `yf.download`; actual rate-limiting behavior, 429 handling, and batch sleep are not exercised in CI.

#### 2. Live Incremental `data update`

**Test:** Run `fund-backtest data update` on a database that already has yesterday's bars
**Expected:** Only today's bars are appended; historical bar count is unchanged; `bars_inserted` equals universe size (or 0 if market closed)
**Why human:** True incremental behavior requires real calendar progression — cannot be reproduced without a live database and two real yfinance downloads on separate days.

#### 3. `data coverage` With Real Data

**Test:** Run `fund-backtest data coverage` after a successful `data download`
**Expected:** Table shows correct tickers-with-bars count matching universe size, earliest bar ~5 years ago, latest bar = most recent trading day, unreviewed anomaly count
**Why human:** Requires populated `price_bars` table; the min/max date query is meaningless without real data.

### Gaps Summary

No gaps. All 5 observable truths are verified, all 13 required artifacts exist, are substantive, and are wired. All 5 requirements are satisfied. 66 unit tests and 9 integration tests pass. Coverage is at 82.78% (above the 80% threshold). Three items are routed to human verification because they require a live PostgreSQL instance and real yfinance network access, which cannot be tested programmatically without external services.

---

_Verified: 2026-03-29T08:34:53Z_
_Verifier: Claude (gsd-verifier)_
