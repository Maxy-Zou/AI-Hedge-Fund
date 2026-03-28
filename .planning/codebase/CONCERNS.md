# Codebase Concerns

**Analysis Date:** 2026-03-28

## Error Handling & Data Loss

**Broad exception catching in filing client:**
- Issue: `except Exception` blocks in `src/ai_washer/ingestion/filing_client.py` (lines 104-106, 111-113, 127, 208, 297, 310) swallow errors without distinguishing between API failures, parsing errors, and data integrity issues.
- Files: `src/ai_washer/ingestion/filing_client.py` (lines 104-113, 127-133, 208-214, 297-298, 310-316)
- Impact: Silent failures on malformed filing data could lead to missed sections being logged as warnings but still returning empty content. Hard to debug which specific edgartools operation failed.
- Fix approach: Refactor to catch specific exceptions (ValueError for parsing, AttributeError for missing fields, HTTPError for network). Log exception type explicitly with structlog's `exc_info=True`. Return a Result type instead of implicit None to distinguish "no data" from "failure".

**Graceful degradation without explicit circuit breaking:**
- Issue: When FilingClient fails to extract a section (e.g., Item 1 parsing fails), it silently falls back to full_text_excerpt. No mechanism to track repeated failures per form type or company, leading to unbounded degradation in data quality.
- Files: `src/ai_washer/ingestion/filing_client.py` (lines 238-239, 272-273)
- Impact: If edgartools is broken for 10-K parsing across all companies, the system will silently degrade to full text for all companies without alerting operators.
- Fix approach: Add per-company/form-type failure counters to database. Threshold alerting in FilingCollector when degradation exceeds 20% of a batch. Log structured failures as "filing_extraction_degraded" events with company CIK for monitoring.

**Filing collector catches and suppresses exceptions without categorizing:**
- Issue: `src/ai_washer/ingestion/filing_collector.py` (lines 130-137, 153-156) catch all exceptions per form type and per XBRL extraction, but don't distinguish between rate limit errors (should retry), data corruption (should alert), and missing data (expected).
- Files: `src/ai_washer/ingestion/filing_collector.py` (lines 130-137, 153-156)
- Impact: A rate limit error from SEC API (429) is treated the same as a missing company (404) or parsing error. Retryable errors are lost, making error logs useless for triaging.
- Fix approach: Catch specific httpx exceptions (HTTPStatusError with status code 429 for retry-able, 404 for skip, 5xx for transient). Re-raise rate limit errors instead of appending to errors list. Use structured error types (RateLimitError, NotFoundError, ParseError) with distinct handling paths.

## Data Integrity & Precision

**Floating-point to cents conversion precision loss:**
- Issue: `src/ai_washer/ingestion/xbrl_extractor.py` (line 139) and `src/ai_washer/ingestion/edgar_client.py` (line 151) convert dollars to cents via `int(value_dollars * 100)`. This silently truncates sub-cent values (e.g., $1.234 becomes 123 cents instead of 124). XBRL values often have decimal precision beyond cents.
- Files: `src/ai_washer/ingestion/xbrl_extractor.py:139`, `src/ai_washer/ingestion/edgar_client.py:151`
- Impact: Financial data loses precision without audit trail. If SEC data includes $0.005, it silently becomes $0.00. No way to detect this happened.
- Fix approach: Use `from decimal import Decimal` to preserve full precision, round to cents explicitly: `int(Decimal(str(value_dollars)).quantize(Decimal('0.01')) * 100)`. Document rounding strategy in docstring. Add a `value_cents_precise` field to track precision loss if needed.

**Market cap division for display without guards:**
- Issue: `src/ai_washer/cli.py` (lines 103, 147) divide market_cap_cents by 100_000_000 for display. If market_cap_cents is None, this crashes. The CLI has no guard.
- Files: `src/ai_washer/cli.py:103, :147`
- Impact: `ai-washer universe list` crashes when displaying a company with null market_cap_cents. This can happen for fresh companies added before XBRL data fetch.
- Fix approach: Check for None before division: `"${company.market_cap_cents // 100_000_000}M" if company.market_cap_cents else "N/A"`. Add type guard in List command.

**XBRL deduplication doesn't handle amended vs. original filed dates:**
- Issue: `src/ai_washer/ingestion/xbrl_extractor.py:deduplicate_by_period()` (lines 51-77) keeps the most recent filing for each (end, fp) pair. But "filed" is the XBRL filing date, not the amendment date. If a 10-K/A is filed later with the same "filed" timestamp (same filing date), the original 10-K is lost.
- Files: `src/ai_washer/ingestion/xbrl_extractor.py:51-77`
- Impact: Amended financial statements are ignored. If a company restates revenue, the original (incorrect) value persists in the database.
- Fix approach: Check `form` field for "/A" suffix and explicitly prefer amendments. Update docstring to clarify semantics of "filed" vs. "accn" (accession number contains date info). Add test for 10-K vs. 10-K/A scenario.

## Test Coverage Gaps

**No integration tests for FilingCollector with real database:**
- Issue: `src/ai_washer/ingestion/filing_collector.py` has 10 unit tests that mock FilingClient and XBRLExtractor. No integration test confirms end-to-end idempotency: collecting the same filings twice should produce 0 new inserts on the second run.
- Files: `src/ai_washer/ingestion/filing_collector.py`, `tests/unit/test_filing_collector.py` (10 tests, all mocked)
- Impact: Idempotent collection claim is untested. Duplicate detection via (company_id, form_type, accession_no) could have edge cases.
- Fix approach: Add `tests/integration/test_filing_collector.py` with real PostgreSQL (testcontainers). Create 2-3 companies, collect filings, verify counts, then collect again and verify counts unchanged. Test edge case: CIK format variations (leading zeros).

**FilingClient section extraction not tested with actual edgartools objects:**
- Issue: `src/ai_washer/ingestion/filing_client.py` has 15 unit tests using `unittest.mock.patch` on edgartools. No test confirms that the bracket notation (`filing_obj[key]`) works with real TenK/TenQ objects.
- Files: `src/ai_washer/ingestion/filing_client.py`, `tests/unit/test_filing_client.py` (15 tests, all mocked)
- Impact: If edgartools changes bracket notation (unlikely but possible in a major version), tests won't catch it until runtime in production.
- Fix approach: Add fixture with real edgartools TenK/TenQ objects (created from sample XBRL). Test section extraction with real objects at least once. Keep mocked tests for error cases.

**No test coverage for config YAML loading:**
- Issue: `src/ai_washer/config.py` defines ScoringConfig with YAML loading via Pydantic. Tests pass None for `_yaml_file` to use in-memory defaults. No integration test loads the actual `config/scoring.yaml` file.
- Files: `src/ai_washer/config.py:85-137`, `tests/unit/test_config.py`
- Impact: If `config/scoring.yaml` is malformed (bad YAML, missing weights field), the app crashes at startup with unclear error. No pre-flight validation.
- Fix approach: Add integration test that loads `config/scoring.yaml` and validates schema. Add startup validation in CLI: `check_config` should test YAML load explicitly.

**No test for EntityResolver with empty candidates:**
- Issue: `src/ai_washer/entity/resolver.py:resolve_entity()` handles empty candidate lists gracefully, but no test confirms behavior when `candidates={}` (all sources missing).
- Files: `src/ai_washer/entity/resolver.py`, `tests/unit/test_entity_resolver.py`
- Impact: Edge case not covered: company with zero aliases resolved. Confidence calculation divides by zero if match_scores is empty.
- Fix approach: Add test case for `resolve_entity(..., candidates={})` and verify `confidence=0.0`. Verify `needs_review=False` for no matches (different from low-confidence matches).

## Performance & Scalability

**Unbounded pagination in EFTS without timeout:**
- Issue: `src/ai_washer/ingestion/efts_client.py:paginate()` (lines 85-147) loops while `offset < EFTS_MAX_OFFSET` without per-page timeout or circuit breaker. If SEC API is slow, this can hang for minutes.
- Files: `src/ai_washer/ingestion/efts_client.py:85-147`
- Impact: A single slow page can block the entire `universe scan` command for 5-10 minutes without logging progress per page.
- Fix approach: Add per-page timeout to httpx.Client (already 30.0s in request, good), add progress logging per page (every 10 pages), add circuit breaker: if 3 consecutive pages fail, abort with structured error instead of retrying all.

**Market cap batch fetching has no chunking:**
- Issue: `src/ai_washer/ingestion/edgar_client.py:get_entity_public_float_batch()` (lines 180-195) fetches all companies in a single loop without batching. If filtering yields 500 companies, this makes 500 sequential HTTP requests (with rate limiting delay).
- Files: `src/ai_washer/ingestion/edgar_client.py:180-195`
- Impact: Filtering 500 companies takes 500 * 0.1s = 50 seconds even with perfect network. No way to parallelize or cache.
- Fix approach: Implement batch fetching via httpx async client. Fetch 5-10 companies per batch (limited by SEC rate limit 10 req/sec), concurrently. Cache results in memory during scan phase (single scan execution). Add caching decorator for future runs.

**Entity resolver batch processing logs every 50 items:**
- Issue: `src/ai_washer/entity/resolver.py:resolve_batch()` (lines 181-186) logs progress every 50 entities. For 5,000 entities, this is 100 log lines (low), but for future scaling to 50K, this becomes noisy.
- Files: `src/ai_washer/entity/resolver.py:181-186`
- Impact: Low severity, but future-proofs to pre-emptively log at 200+ interval or use exponential intervals.
- Fix approach: Change to `if (i + 1) % 200 == 0 or (i + 1) == total:`. Document expected batch size assumptions.

## Database & Migration Issues

**Monthly partitioning hardcoded for 2026-2027:**
- Issue: `src/ai_washer/db/migrations/versions/001_initial_schema.py` (line 88-104 of models.py defines partitioning schema, actual partition creation in 001 migration) creates 18 monthly partitions: 12 for 2026 + 6 for 2027. After June 2027, queries on new data fail silently or go to the DEFAULT partition.
- Files: `src/ai_washer/db/models.py:88-92`, `src/ai_washer/db/migrations/versions/001_initial_schema.py`
- Impact: Scores inserted after 2027-06 silently fail to partition or fill DEFAULT. Query performance degrades. Future data loss risk.
- Fix approach: Implement partition management strategy: add Alembic hook to create partitions on-demand for new months, or implement annual rollover script. Document partition strategy in CLAUDE.md. Add monitoring alert if DEFAULT partition grows > 0 rows.

**No migration for future scoring schema changes:**
- Issue: `DailyScore` model stores signal breakdown and weights as JSONB (D-05). Changing signal weights in `config/scoring.yaml` doesn't update historical scores. No versioning of schema per historical run.
- Files: `src/ai_washer/db/models.py:75-114`
- Impact: Historical scores with old weights become incomparable to new scores. No way to answer "what would the score have been with new weights?" questions.
- Fix approach: Add `weights_schema_version` field to DailyScore. Store `WEIGHTS_VERSION` constant in config. Add migration guide in CLAUDE.md for weight changes: bump version, recompute, or keep dual historical columns.

## Fragile Areas

**CLI commands assume database is initialized:**
- Issue: Commands like `ai-washer universe list` and `ai-washer collect` call `create_engine_from_settings()` without checking if database exists or migrations are applied. Missing tables cause obscure SQLAlchemy errors.
- Files: `src/ai_washer/cli.py` (lines 84-95 for list, lines 114-117 for collect)
- Impact: User runs `ai-washer universe list` on fresh install, gets `ProgrammingError: relation "companies" does not exist` instead of helpful message.
- Fix approach: Add `check_db_schema()` function that runs `SELECT 1 FROM information_schema.tables WHERE table_name='companies'` and raises helpful error with instructions to run migrations if missing. Call from each CLI command that needs DB access.

**EntityResolver confidence calculation fails silently on single match:**
- Issue: `src/ai_washer/entity/resolver.py:resolve_entity()` (lines 127-131) calculates `overall_confidence = mean(match_scores) / 100.0 if match_scores else 0.0`. With a single match (e.g., one patent assignee), this is `[85.0] / 100.0 = 0.85`. But dividing by 100 assumes scores are 0-100, which is true for rapidfuzz but fragile.
- Files: `src/ai_washer/entity/resolver.py:127-131`
- Impact: If rapidfuzz score range ever changes or a new scorer is added, confidence calculation breaks silently.
- Fix approach: Add constant `FUZZY_SCORE_MAX = 100` at module level. Add assertion that all match_scores are in [0, 100]. Document confidence semantics in module docstring (normalized to 0-1).

**UniverseBuilder.scan() returns unordered results:**
- Issue: `src/ai_washer/universe/builder.py:scan()` aggregates EFTS search results across 2 keywords ("artificial intelligence", "machine learning") without deterministic ordering. Results depend on EFTS API ordering, which can vary day to day.
- Files: `src/ai_washer/universe/builder.py` (scan method, deduplicate_by_cik used but no sorting at end)
- Impact: Dry-run output is non-deterministic. Hard to compare dry-run results across dates. Not idempotent.
- Fix approach: Sort results by CIK at the end of scan(): `return sorted(results, key=lambda x: x.ciks[0] if x.ciks else "")`. Document that scan() is not time-stable but is CIK-stable.

**FilingSections has partial fields, no validation:**
- Issue: `src/ai_washer/ingestion/types.py` defines FilingSections with all optional fields (business, risk_factors, mda, financial_statements, full_text_excerpt all nullable). No validation that at least one field is populated.
- Files: `src/ai_washer/ingestion/types.py` (FilingSections model)
- Impact: A filing can be persisted with all None sections. Not invalid per schema, but useless for analysis.
- Fix approach: Add Pydantic `@model_validator` to FilingSections: at least one of [business, risk_factors, mda, full_text_excerpt] must be non-None.

## Validation & Input Safety

**CIK formatting assumptions not validated at boundaries:**
- Issue: `src/ai_washer/ingestion/edgar_client.py:pad_cik()` assumes CIK is numeric string, no validation. If a non-numeric CIK is passed (e.g., from typo in CLI), it crashes silently or pads incorrectly.
- Files: `src/ai_washer/ingestion/edgar_client.py:pad_cik()` and strip_cik functions (no validation)
- Impact: User runs `ai-washer collect company ABC` (invalid CIK format), gets confusing error instead of "Invalid CIK format".
- Fix approach: Add validation in pad_cik: `if not cik.isdigit(): raise ValueError(f"CIK must be numeric, got {cik!r}")`. Add same validation in Company model CIK field (String type, should be constrained to digits only). Validate in CLI before passing to collectors.

**No rate limit backoff awareness in EFTS/EDGAR clients:**
- Issue: `src/ai_washer/ingestion/efts_client.py` and `edgar_client.py` implement tenacity retry with exponential backoff, but don't expose Retry-After headers from SEC. If SEC sends `Retry-After: 120`, the client still retries with exponential backoff starting at 1 second.
- Files: `src/ai_washer/ingestion/efts_client.py:193-200`, `src/ai_washer/ingestion/edgar_client.py:216-223`
- Impact: During SEC maintenance or rate limit events, clients don't respect Retry-After, causing cascading failures across multiple companies in collect_all.
- Fix approach: Extract `Retry-After` header in retry handlers. Use `max(exponential_backoff, retry_after)` for wait time. Log Retry-After violations as warnings.

## Dependency Risks

**edgartools version pinned loosely:**
- Issue: `pyproject.toml` specifies `edgartools>=5.26.1` (no upper bound). edgartools is actively maintained (weekly releases). Major version could break bracket notation API.
- Files: `pyproject.toml` dependency list
- Impact: Future edgartools 6.0 could change API (e.g., change from `tenk["Item 1"]` to `tenk.item_1`), breaking FilingClient.
- Fix approach: Add upper bound: `edgartools>=5.26.1,<6`. Add note in CLAUDE.md monitoring changelog. Quarterly dependency audit for breaking changes.

**httpx still in 0.x (pre-1.0):**
- Issue: `pyproject.toml` specifies `httpx>=0.28.1`. httpx is planned for 1.0 release in 2026-Q2, which could change API.
- Files: `pyproject.toml`
- Impact: Upgrade to httpx 1.0 could require code changes (timeout parameters, error handling).
- Fix approach: Monitor httpx releases. Lock to `httpx>=0.28.1,<1.0` until 1.0 is released and tested. Plan migration once 1.0 is available (likely Q2-Q3 2026).

**Pydantic version assumes 2.x stability:**
- Issue: `pyproject.toml` specifies `pydantic>=2.12.5` (broad range). Pydantic 3.0 is planned for late 2026 with breaking changes (removing v1 compatibility layer).
- Files: `pyproject.toml`, entire config.py
- Impact: Pydantic 3.0 could require code changes, e.g., field validators syntax.
- Fix approach: Pin to `pydantic>=2.12.5,<3`. Monitor Pydantic 3.0 beta releases. Plan upgrade in 2026-Q4 once stable.

## Security Considerations

**EDGAR identity in plaintext environment variables:**
- Issue: `src/ai_washer/config.py` loads `edgar_identity` from `AI_WASHER_EDGAR_IDENTITY` env var (User-Agent string like "CompanyName email@example.com"). This exposes company email in environment.
- Files: `src/ai_washer/config.py:22`
- Impact: Email harvesting risk if environment is exposed (e.g., via logs, error messages, process inspection).
- Fix approach: Document in CLAUDE.md that EDGAR_IDENTITY should use generic company name or handle, not email. Store email in secrets manager if available. Add warning log if identity contains "@".

**Database connection string in logs on DEBUG:**
- Issue: `src/ai_washer/db/session.py:24` enables `echo=True` when log_level=="DEBUG", which logs all SQL queries including credentials in the connection string if embedded (though unlikely with postgresql://).
- Files: `src/ai_washer/db/session.py:22-26`
- Impact: If DATABASE_URL contains inline password (bad practice but possible), it's logged on DEBUG.
- Fix approach: Sanitize connection string before echoing: remove password. Use psycopg URL parsing to strip credentials before logging. Document in CLAUDE.md that DATABASE_URL should use env vars or secrets, not inline passwords.

**No input validation on ticker symbols:**
- Issue: CLI command `ai-washer collect company <ticker>` doesn't validate ticker format. A malicious actor could pass SQL injection payloads if the ticker field is ever used in raw SQL (unlikely with SQLAlchemy ORM, but possible in future hardcoded queries).
- Files: `src/ai_washer/cli.py` (collect company command)
- Impact: Low risk with current ORM, but violates defense-in-depth principle.
- Fix approach: Add regex validation on ticker: `^[A-Z]{1,5}$` in Company model or CLI. Reject invalid tickers early with clear error.

## Technical Debt Summary

| Issue | Severity | Fix Effort | Impact |
|-------|----------|-----------|--------|
| Broad exception catching in filing client | HIGH | Medium | Silent data loss, hard to debug |
| Floating-point to cents conversion | MEDIUM | Low | Precision loss without audit trail |
| Partition strategy hardcoded to 2026-2027 | HIGH | Medium | Data loss risk post-June 2027 |
| No database initialization check in CLI | MEDIUM | Low | Poor user experience on fresh install |
| EFTS pagination no circuit breaker | MEDIUM | Medium | Potential hangs under load |
| Market cap batch fetching not parallelized | LOW | High | Performance left on table |
| EDGAR identity email exposure | MEDIUM | Low | Email harvesting risk |
| CIK validation missing at boundaries | MEDIUM | Low | Poor error messages |

---

*Concerns audit: 2026-03-28*
