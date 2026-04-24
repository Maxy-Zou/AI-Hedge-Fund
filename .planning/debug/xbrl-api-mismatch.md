---
slug: xbrl-api-mismatch
status: resolved
trigger: run_analysis pipeline aborts inside xbrl_client.get_facts — edgartools 5.28.5 API does not match assumptions made by src/ai_hedge_fund/data/clients/xbrl_client.py and (partially) edgar_client.py
created: 2026-04-24
updated: 2026-04-24
---

# Debug Session: xbrl-api-mismatch

## Symptoms

<!-- DATA_START -->
- **expected**: `uv run python -m ai_hedge_fund.scripts.run_analysis --ticker AAPL --as-of 2026-04-18 --sector Technology` completes end-to-end and prints a final signal markdown.
- **actual**: Fails during the fundamental-agent data fetch. Top-level error in the log is `RetryError[<Future at 0x... state=finished raised AttributeError>]` surfaced from `xbrl_client.get_facts`. The underlying `AttributeError` (unwrapped via direct probe) is `'EntityFacts' object has no attribute 'to_pandas'`.
- **errors**:
    - `'EntityFacts' object has no attribute 'to_pandas'` — `xbrl_client.py:133` calls `company_facts.to_pandas()`; current edgartools exposes `to_dataframe()` instead.
    - Also latent: downstream column access in `_resolve_concept_facts` (xbrl_client.py:237–249) expects `fact, namespace, val, units, fp, fy, filed, form`. The actual `to_dataframe()` columns are `concept, label, value, numeric_value, unit, period_type, period_start, period_end, fiscal_year, fiscal_period` (no `filed`, no `form`, no `namespace`). Temporal filtering currently depends on `filed` (filed_date).
    - Earlier (now patched) break: `'EntityFiling' object has no attribute 'form_type'` in `edgar_client.py` — patched to `.form` in two places and rerun reached this xbrl failure.
- **timeline**: First real end-to-end pipeline run. Project just finished Phase 8 / milestone v1.0. edgartools is pinned `>=5.28.5` in `pyproject.toml`; installed version is `5.28.5`. Implies the edgartools-facing data layer was built/tested against a different API version (likely older) and integration was never exercised against the installed version.
- **repro**:
    ```
    cd /Users/maxzou/Documents/projects/AI\ Hedgefund
    export ANTHROPIC_API_KEY=... EDGAR_IDENTITY="Max Zou maxzou@andrew.cmu.edu" \
           DATABASE_URL=... FINNHUB_API_KEY=... FRED_API_KEY=...
    echo y | uv run python -m ai_hedge_fund.scripts.run_analysis \
        --ticker AAPL --as-of 2026-04-18 --sector Technology
    # see /tmp/ai_hedge_runs/aapl_run5.log
    ```
- **direct API probe** (confirms the mismatch without pipeline noise):
    ```python
    import edgar; edgar.set_identity("Max Zou maxzou@andrew.cmu.edu")
    facts = edgar.Company("AAPL").get_facts()
    # facts.to_pandas()          -> AttributeError
    df = facts.to_dataframe()    # works; 24579 rows
    list(df.columns)             # ['concept','label','value','numeric_value','unit',
                                 #  'period_type','period_start','period_end',
                                 #  'fiscal_year','fiscal_period']
    ```

Relevant files:
- `src/ai_hedge_fund/data/clients/xbrl_client.py` — primary offender (get_facts, get_financial_metrics, _resolve_concept_facts)
- `src/ai_hedge_fund/data/clients/edgar_client.py:81,162` — already patched `.form_type` → `.form`; mention for context
- `src/ai_hedge_fund/data/tools/filing_tools.py` — consumer, expects `form_type` key in dicts (still supplied by edgar_client — keep)
- `pyproject.toml:23` — `edgartools>=5.28.5`
<!-- DATA_END -->

## Current Focus

```yaml
status: resolved
hypothesis: confirmed — xbrl_client.py was written against a pre-5.x edgartools API. Migrated to to_dataframe(pit_mode=True), which exposes filing_date and form_type natively.
next_action: none; resolved.
test: full pipeline end-to-end (AAPL / 2026-04-18 / Technology) exits cleanly with a markdown signal; full unit suite (578 tests) passes.
expecting: fix landed.
```

## Evidence

- timestamp: 2026-04-24T11:28 | `aapl_run4.log` shows `'EntityFiling' object has no attribute 'form_type'` — patched in `edgar_client.py:81,162` → `.form`.
- timestamp: 2026-04-24T11:35 | `aapl_run5.log` with edgar fix applied shows `RetryError[... AttributeError]` after three `xbrl_client.get_facts` retry entries.
- timestamp: 2026-04-24T11:40 | Direct probe confirmed `EntityFacts.to_pandas` absent; `to_dataframe()` returns schema `concept,label,value,numeric_value,unit,period_type,period_start,period_end,fiscal_year,fiscal_period`.
- timestamp: 2026-04-24T11:41 | `FactQuery` object exposes `as_of`, `by_concept`, `by_fiscal_year`, `by_fiscal_period`, `date_range`, `latest`, etc. → clean native path for temporal filtering without `filed_date`.
- timestamp: 2026-04-24T14:05 | Read `.venv/.../edgar/entity/entity_facts.py:246–343`. Found `to_dataframe(pit_mode=True)` — documented as "Point-in-Time mode for backtesting... enables lookahead-bias-free analysis". In PIT mode the DataFrame gains `filing_date` + `form_type` columns (exactly matching the old code's dependencies), preserves all restatements (no period dedup), and sorts by `(concept, period_end, filing_date)`. This is a cleaner native fit than `FactQuery.as_of()` — no need to rewrite around query-builder API.
- timestamp: 2026-04-24T14:10 | Live probe of AAPL: `to_dataframe(pit_mode=True)` returns 24,579 rows with `concept` values like `us-gaap:Revenues`, `dei:EntityCommonStockSharesOutstanding`. `filing_date` / `period_end` are native `datetime.date`. `numeric_value` is the cleaned numeric float (same as `value` for numeric facts). No `namespace` column — taxonomy is folded into the `concept` prefix.
- timestamp: 2026-04-24T14:18 | Rewrote `xbrl_client.py`: call `to_dataframe(pit_mode=True)`, match concepts on `concept == f"us-gaap:{tag}"`, filter `filing_date <= as_of_date`, dedupe restatements per `(concept, period_end)` by keeping max `filing_date`, prefer 10-K/10-K/A facts, pick current+prior by `period_end` descending. Derives "latest fiscal year" from `period_end.year` rather than the pit_mode `fiscal_year` column (which can reflect filing's FY, not fact's FY). Public contract preserved: `{ticker, fiscal_period, fiscal_year, metrics: {concept: {current, prior}}}`.
- timestamp: 2026-04-24T14:20 | Rewrote test fixtures in `tests/unit/test_financial_tools.py`: `_make_fact_row` keeps pre-migration call signature; `_make_company_facts` now produces a mock with `.to_dataframe(pit_mode=True)` returning a DataFrame in the new schema. Dates parsed to `datetime.date` at DataFrame construction. Period_end defaulted from fiscal_year for FY facts (Dec 31) with quarter approximations for Q1/Q2/Q3.
- timestamp: 2026-04-24T14:22 | `uv run pytest tests/unit/test_financial_tools.py` — 10/10 pass.
- timestamp: 2026-04-24T14:24 | End-to-end verification — `aapl_verify.log` shows full pipeline completing: sentiment, technical, fundamental, manager, bull, bear, rebuttal, final_arguments, debate_synthesis all produce real token counts. Risk manager returns `VETOED` for legitimate reason (`insufficient_price_history` — 0 days observed vs 60 day min), not a data-layer crash. Final output is a markdown "BLOCKED BY RISK" signal. `grep -cE "Traceback|AttributeError|RetryError|KeyError" aapl_verify.log` → 0.
- timestamp: 2026-04-24T14:28 | Full unit suite: 8 failures surfaced in `tests/unit/test_filing_tools.py` — `MockFiling` exposed `.form_type` but the post-patch `edgar_client.py` reads `.form` (the real edgartools attribute name). Verified against `.venv/.../edgar/entity/filings.py:32–171` — `EntityFiling.form` is canonical, no `.form_type`. Fixed `MockFiling.__init__` to store the kwarg on `.form`. Test kwarg name (`form_type=`) kept for readability.
- timestamp: 2026-04-24T14:34 | Full suite green: 578 unit tests pass, 1032 tests pass across `tests/unit + tests/graph + tests/memory + tests/output + tests/review + tests/risk + tests/scripts`. Ruff format + check clean on all changed files.

## Eliminated

- Pin downgrade — not needed. `to_dataframe(pit_mode=True)` on 5.28.5 is a cleaner native fit than the old API; temporal controls are explicitly supported.
- `FactQuery.as_of()` migration — deferred. `pit_mode=True` gives us the same information with simpler semantics (one DataFrame, filter in place). `FactQuery` could be a future refactor but adds no value for this fix.

## Resolution

- root_cause: `src/ai_hedge_fund/data/clients/xbrl_client.py` and `tests/unit/test_filing_tools.py` were written against a pre-5.x edgartools API surface. Production code called `CompanyFacts.to_pandas()` (replaced by `EntityFacts.to_dataframe()` in 5.x) and indexed a flat `namespace/fact/val/units/fp/fy/filed/form` schema that no longer exists. Separately, `EntityFiling.form_type` was renamed to `.form`. edgartools >= 5.28 exposes `to_dataframe(pit_mode=True)` with `filing_date` and `form_type` as first-class columns, explicitly for lookahead-bias-free analysis — a cleaner fit than the old API we were emulating.
- fix:
  1. Rewrote `XbrlClient.get_facts` / `get_financial_metrics` / `_resolve_concept_facts` in `src/ai_hedge_fund/data/clients/xbrl_client.py` to call `to_dataframe(pit_mode=True)`, match concepts on taxonomy-prefixed `concept` strings (`us-gaap:<Tag>`), filter `filing_date <= as_of_date` for temporal controls, dedupe restatements per `(concept, period_end)` by keeping the latest filing, prefer 10-K / 10-K/A for FY data, and derive "latest fiscal year" from `period_end.year` (pit_mode's `fiscal_year` column reflects the filing's FY rather than the fact's FY).
  2. Public contract preserved end-to-end: `{ticker, fiscal_period, fiscal_year, metrics: {concept: {current, prior}}}`, with monetary concepts converted to integer cents exactly as before. Consumer `financial_tools.get_financial_summary` and `format_financial_summary` are untouched.
  3. Updated mock fixtures in `tests/unit/test_financial_tools.py` (`_make_company_facts` now returns a mock with `.to_dataframe(pit_mode=True)` producing the new-schema DataFrame) and `tests/unit/test_filing_tools.py` (`MockFiling` now stores the form on `.form` to match real `EntityFiling`). Test-level call signatures unchanged.
  4. Orchestrator's earlier `edgar_client.py` `.form_type → .form` patch is kept — verified correct against installed edgartools source.
- verification:
  - End-to-end: `run_analysis --ticker AAPL --as-of 2026-04-18 --sector Technology` runs cleanly. All 9 pipeline stages (sentiment through debate_synthesis) emit real token counts. Risk manager returns a legitimate `VETOED` with markdown signal (`insufficient_price_history`: 0 days observed vs 60-day minimum — unrelated to the data layer; empty DB). Log `/tmp/ai_hedge_runs/aapl_verify.log` has zero tracebacks, AttributeErrors, RetryErrors, or KeyErrors.
  - Unit: `uv run pytest tests/unit` → 578 passed.
  - Broader: `uv run pytest tests/` excluding integration → 1032 passed.
  - Lint: `ruff check` clean on all three changed files.
- files_changed:
  - `src/ai_hedge_fund/data/clients/xbrl_client.py` — rewritten to target edgartools >= 5.28 `EntityFacts.to_dataframe(pit_mode=True)` API with preserved temporal-controls invariant and preserved public contract.
  - `tests/unit/test_financial_tools.py` — fixture helpers updated to the new DataFrame schema; test assertions unchanged.
  - `tests/unit/test_filing_tools.py` — `MockFiling.form_type` renamed to `.form` (matches real `EntityFiling` API post-`edgar_client.py` patch); test kwargs unchanged.
