## 2026-09-22 — Phase 9 delivered: Paper-Trading Data Layer (PT-01..05), PR #2

First phase executed under the new Development Workflow: Plan -> Spec -> Pre-mortem (signed off) -> TDD -> code review -> PR. Branch `phase/09-paper-data-layer`, 11 commits, every implementation commit preceded by a RED test.

**Shipped:** `PaperTrade` / `PaperFill` models + migration 004 (reversible; PostgreSQL `BEFORE UPDATE OR DELETE` trigger, skipped on SQLite); a three-layer append-only guard (`db/append_only.py` -- ORM flush + ORM-enabled Core statements, opt-in per table, `episodic_memory` untouched); SQLite FK enforcement (`db/sqlite_compat.py`); `db/dates.normalise_as_of` promoted from two duplicate private copies; the `ai_hedge_fund.paper` package (validated inputs, frozen read views, typed errors, append-only writers, temporal recall, CSV seeders). Two fix-as-you-find commits landed first (dead `AppendOnlyMixin` removed; helper promotion).

**Tests:** 79 new functions across `tests/paper/` (6 modules + self-contained fixtures) and `tests/unit/test_db_dates.py`. Suite 1134 -> **1263 passed, 11 skipped** (2 new skips are PostgreSQL-gated; they refuse any database whose name lacks `test`). ruff clean. First alembic migration the suite has ever executed; `compare_metadata` proves migration DDL == ORM with zero structural diffs.

**Decisions executed (all six approved):** `paper_pnl_daily` deferred to Phase 11; DELETE forbidden alongside UPDATE; whole-share quantities; idempotency on `(signal_id, attempt_no)` so a broker rejection is recoverable under append-only; guard opt-in; two fix-as-you-find commits.

**Found during TDD, not predicted by the pre-mortem:** SQLAlchemy's `JSON` type stores Python `None` as the JSON string `'null'`, defeating `NOT NULL` -- paper tables now use `none_as_null=True`; `EpisodicMemory.payload` has the same latent gap (TECH-DEBT). Also: a `pytest | tail` gate pattern was masking pytest's exit status; caught when it let 2 failures through, fixed with `pipefail`, commit amended before push.

**Code review (high effort, before un-draft):** 10 findings, all fixed in `07104d8` with RED tests first. Two would have bitten immediately: the payload secret tripwire rejected `tokens_used` (emitted by every pipeline event), and the PostgreSQL trigger existed only in the migration so a `create_all`-bootstrapped DB had no L3 -- now also attached to the Table objects as idempotent DDL. Also: L2 blind to `update(Model.__table__)`, parity test dropping FK diffs and never comparing CHECKs, negative `limit` unbounded on SQLite, unique detection by message substring, unvalidated seed headers, lingering private alias imports, 75-line `upgrade()`, bare `%` in RAISE. Suite 1263 -> **1283 passed**. The PG trigger remains unexecuted on PostgreSQL here; the `@slow` tests must run against docker-compose before 004 reaches a real DB.

**Docs:** `09-SUMMARY.md` (per-criterion evidence, code review, handoff to Phase 10), ROADMAP (Phase 9 complete, 9.1 amended, Phase 11 owns migration 005), REQUIREMENTS (PT-01..05 Complete), STATE (20%), TECH-DEBT (+4 entries: guard retrofit, episodic JSON null, migration 002 nullability drift, 001-003 untested).

## 2026-09-22 — GSD retired: workflow replaced, all tooling references stripped

User reported the GSD planning/execution tooling is compromised (founder rug-pull, suspected backdoors) and is removing it from their machine. This commit removes every GSD dependency from the repo and replaces the mandated workflow with a plain, tool-free one.

**Security audit (nothing malicious found):**
- Repo `.claude/settings.json` has one `PostToolUse` hook -- `chflags nohidden` on venv `.pth` files. Benign, predates GSD (commit 1180d4f "env hardening"; workaround for a macOS uv bug when the project path had a space -- the path no longer does, so the hook is now dead weight; left for a separate cleanup).
- Global `~/.claude/settings.json`: no hooks. No GSD plugin installed or enabled; the disabled `everything-claude-code` plugin cache contains no GSD code.
- `gsd` in Claude Code shell snapshots is the oh-my-zsh alias `git svn dcommit` -- unrelated.
- `src/`, `tests/`, `alembic/`, `config/`: zero GSD references. Only markdown docs and one JSON config carried them.
- `.planning/config.json` was pure GSD runtime config, including `"mode": "yolo"` (auto-approve) -- deleted.

**CLAUDE.md:** removed the `<!-- GSD:* -->` marker scaffolding (project/stack content kept verbatim), the empty "Project Skills" and "Developer Profile" stubs, and the "GSD Workflow Enforcement" section that required `/gsd-*` commands before edits. Added **Development Workflow**: `main` as sole trunk, one `phase/<NN>-<slug>` branch per phase, six stages per phase (Plan -> Spec -> Pre-mortem -> TDD -> Code review -> Merge via PR), verification gates on every PR. Fix-as-you-find escalation now points at plan+spec+pre-mortem instead of `/gsd-debug`.

**Planning docs:** `ROADMAP.md` (5x `/gsd-execute-phase` -> workflow stages), `PROJECT.md` (`/gsd-transition` / `/gsd-complete-milestone` parentheticals dropped), `STATE.md` (`gsd_state_version` key removed; stale "defining requirements" focus corrected), `MILESTONES.md` (v1.1 recorded as defined; "Next Up" now lists v1.2+ candidates), `docs/V1.1_PAPER_TRADING_PLAN.md` (status line updated; open questions now owned by phase specs). `.planning/` directory kept -- its content is the project's own requirements, roadmap, and research; only the tooling references were GSD's.

**Deliberately not rewritten:** historical v1.0 phase records under `.planning/phases/01-08`, `.planning/milestones/`, `.planning-archive/`, `archive/`, and older PROGRESS.md entries still say things like "ready for `/gsd-verify-work`". They are past-tense records of what happened, contain no executables, and rewriting them would falsify history.

**Also noticed, not addressed:** `.planning/phases/01-08` and `.planning/milestones/v1.0-phases/01-08` are byte-identical duplicates (the v1.0 archive step copied without removing the originals). Same class of issue as the CLAUDE.md duplication fixed 2026-09-21.

No code changed. Suite untouched at 1134 passed, 9 skipped.

## 2026-09-21 — v1.1 roadmap: Phases 9-13 defined, 23/23 requirements mapped

`.planning/STATE.md` claimed "REQUIREMENTS.md + ROADMAP.md pending". Only half true: `REQUIREMENTS.md` already held all 23 v1.1 requirements (EXEC/PT/MTM/PROMO/TRACK) from the 2026-04-25 bootstrap, but its traceability table read `TBD -- pending roadmap` for every row, and `ROADMAP.md` still said "No next milestone defined yet." So the requirements were real and the roadmap genuinely was not.

**Written by hand, bypassing GSD.** The project's CLAUDE.md requires `/gsd-*` commands before file edits, but no GSD tooling is installed in this environment (`~/.claude/commands/` is empty, no GSD plugin, no gsd skill). User explicitly authorized the bypass. Format matched against `milestones/v1.0-ROADMAP.md` so the artifacts stay consistent with what the tooling produces: phase list, then Phase Details with Goal / Depends on / Requirements / numbered observable Success Criteria.

**Phases (one per requirement category, linear dependency chain):**
- **Phase 9 — Paper-Trading Data Layer** (PT-01..05): append-only tables, dual timestamps, `signal_id` FK to `episodic_memory.id`, FUTUREX temporal regression.
- **Phase 10 — Paper Execution Surface** (EXEC-01..05): Alpaca paper client, deterministic sizing, idempotent submit, VETOED circuit breaker, fail-fast credential load.
- **Phase 11 — Mark-to-Market and Attribution** (MTM-01..04): daily EOD P&L, idempotent by skip-or-insert, attribution by analyst / debate-side / conviction.
- **Phase 12 — Promotion Gate** (PROMO-01..05): SHA-pinned `promotion_policy.yaml`, pure-Python verdict, three-way audit-chain equality.
- **Phase 13 — Track-Record Reporting** (TRACK-01..04): `render_track_record` CLI, LP-shareable markdown, machine-verifiable JSON.

**One deliberate deviation from the source plan.** `docs/V1.1_PAPER_TRADING_PLAN.md` drafted execution as Phase A and storage as Phase B. The roadmap inverts it. EXEC-03 (idempotent submit keyed on `signal_id`) has no way to deduplicate without a persisted `paper_trades` row, and EXEC-01 records order intent at submission time -- execution depends on the table it writes to, not the reverse. Storage-first also means no execution code ever exists that could write an unauditable row. Rationale recorded in REQUIREMENTS.md so the inversion is not mistaken for drift later.

**Files changed:**
- `.planning/ROADMAP.md` — v1.1 milestone entry, 5-phase list, full Phase Details, 5 rows added to the Progress table.
- `.planning/REQUIREMENTS.md` — traceability table expanded from 5 category-level `TBD` rows to 23 per-requirement rows with phase assignments; coverage block and phase-ordering note added.
- `.planning/STATE.md` — reconciled: `status: defining_requirements` -> `ready_to_execute`, `total_phases: 0` -> `5`, stale `stopped_at` / `last_activity` corrected.

**Caveat on `status: ready_to_execute`:** the observable GSD status vocabulary in this repo is `{executing, verifying, complete, draft, human_needed, partial, tech_debt, defining_requirements}` — none of which describes "roadmap done, execution not started." That token is invented; if the GSD tooling expects a specific value once reinstalled, it needs correcting.

No code changed. Test suite untouched at 1134 passed, 9 skipped.
## 2026-09-21 — Style: ruff format sweep + clear the lint backlog

Cleared the formatting debt deliberately deferred during the dependency-pinning
work, where a large mechanical reformat would have buried a 27-line API fix.

`ruff format --check .` reported 64 files, but that number was two unrelated
things stacked together:

- **28 `.py` files** — the genuine debt. This is exactly the count ruff 0.15.x
  reported on the same tree, so 0.16's formatter changes introduced *zero* new
  Python diffs. The drift predates the `>=0.16.8,<0.17` pin.
- **36 `.md` files**, all under `.planning-archive/` — entirely new in 0.16,
  which formats Python code blocks *inside Markdown*. These were cosmetic edits
  to illustrative snippets in a dated archive snapshot.

`extend-exclude` already covered `archive` and `.planning`, but the pattern
`.planning` does not match the directory `.planning-archive`, so the archive
fell through the gap. Added it — the sweep now scopes to real code only, and
`ruff format --check .` stays quiet on future runs instead of reporting 36
permanently-dirty files.

**The 4 non-auto-fixable lint errors, fixed by hand rather than `# noqa`'d:**

- **`test_agents.py` E402 ×3** — three imports sat mid-file under a
  `# ---- Concrete agent tests ----` comment. They can't move to the top of the
  file: `agents/extraction.py:28` and `agents/analysis.py:27` call
  `create_agent()` at module import time, which PydanticAI validates against
  `ANTHROPIC_API_KEY`. Moved them into the import block that already follows the
  `os.environ.setdefault` on line 20, so the env var is still set first. ruff
  exempts imports that follow `os.environ` mutations, which is why that block
  was never flagged while the mid-file one was.
- **`test_macro_tools.py` E501** — 104-char single-line docstring, wrapped to
  multi-line with the wording unchanged.

The other 17 were auto-fixed: `I001` import sorting and `UP017`
(`timezone.utc` → `datetime.UTC`, an alias swap on `requires-python >=3.11`,
not a semantic change).

Kept as three commits so the mechanical diff stays reviewable: the exclude
config, the pure `ruff format` sweep, then the lint fixes.

**Environment note:** partway through, `uv run pytest` started failing with
`ModuleNotFoundError: No module named 'ai_hedge_fund'`. The venv had
`virtualenv`-package artifacts (`_virtualenv.pth`/`_virtualenv.py`) inside a
uv-created environment, which shadowed uv's editable-install `.pth`. Identical
`.pth` content worked under a later-sorting filename, confirming a load-order
conflict. `rm -rf .venv && uv sync --extra dev` restored it. Note that a bare
`uv sync` prunes `[project.optional-dependencies] dev` — it drops
`pytest-asyncio`, which `asyncio_mode = "auto"` needs; `pytest` itself survives
only transitively via `pytest-httpx`. Use `--extra dev`.

**Verified:** 1134 passed, 9 skipped — unchanged before the sweep, after the
sweep, and after the lint fixes. `ruff check .` and `ruff format --check .`
both clean.

**Files changed:** 28 reformatted (`src/`, `tests/`, `alembic/env.py`);
`pyproject.toml` (exclude); lint fixes in `tests/unit/test_agents.py`,
`tests/unit/test_macro_tools.py`, `tests/unit/test_sentiment_tools.py`,
`tests/memory/test_episodic_model.py`

## 2026-09-21 — Docs: dedupe CLAUDE.md (408 → 291 lines)

A bad merge had left 12 section headings appearing exactly twice, so the main
context document carried two drifted copies of Architecture, Conventions, GSD
Workflow Enforcement, and Developer Profile.

The two halves turned out to be different regimes: lines 1–195 were the
hand-edited sections, and lines 196–408 were GSD-managed blocks delimited by
`<!-- GSD:*-start/end -->` markers. Diffing each pair showed the hand-edited
copies were strict supersets:

- **Conventions** — the GSD copy was missing `### Dependency Policy` and
  `### Fix-as-you-find` entirely.
- **Architecture** — the GSD copy had ASCII-degraded text (`<-` for `←`,
  "Three tiers" for "Three-tier architecture") and dropped the SAS-paper note
  under the debate protocol.
- **Data Sources** — the GSD copy's `### Data Sources (Priority Order)` table
  dropped the Notes column and the specific rate limits (`Free (60 req/min)`,
  `Free (250 calls/day)`).

Kept the richer copy of each, then removed the redundant `GSD:conventions` and
`GSD:architecture` blocks with their markers. For GSD Workflow Enforcement and
Developer Profile the copies were identical apart from command spelling
(`/gsd:quick` vs `/gsd-quick`); kept the GSD-generated dash form, since the
tooling that writes those blocks is the authority on its own command names.

Verified: no repeated headings, all 5 remaining GSD marker pairs balanced, no
line of original content dropped except the superseded duplicates, no new text
introduced.

**Files changed:** `CLAUDE.md` (408 → 291 lines)

## 2026-09-21 — Fix: pydantic-ai 2.x API drift broke 84 tests on fresh clone

Third instance of the vendor-drift class flagged in the 2026-04-24 entry — this time in a *direct* dependency, not a data vendor. A clean clone + `uv sync --extra dev` resolved `pydantic-ai==2.46.0` (pyproject pins only `>=1.0.0`), and 84 of 1134 tests failed immediately.

**Two breaking renames across the 1.x → 2.x major bump:**
- `AgentRunResult.usage()` became a property, not a method → `TypeError: 'RunUsage' object is not callable` (72 failures, all downstream of one module).
- `Agent._max_result_retries` → `Agent._max_output_retries` (12 failures, test-side assertions only).

**Files changed:**
- `src/ai_hedge_fund/graph/nodes.py` — 15 call sites, `result.usage()` → `result.usage`.
- `tests/unit/test_{bull,bear,research,manager,fundamental,sentiment,technical,signal,rebuttal,final_arguments,debate_synthesis}_agent.py` — 12 assertions renamed to `_max_output_retries`.

27 lines total, no behavior change: `usage` returns the same `RunUsage`, so every downstream `.input_tokens` / `.output_tokens` read is unaffected. Token-budget enforcement and Langfuse span attributes verified intact by the existing suites.

**Verification:**
- Full suite: **1134 passed, 9 skipped** (was 84 failed / 1050 passed). Runtime 26s.
- `ruff check` clean on all 12 touched files.
- Pre-existing and NOT introduced here: 19 `ruff check` errors + 64 files failing `ruff format --check` at pristine HEAD, caused by ruff resolving to 0.16.8 against a `>=0.15.0` pin. Left untouched — a formatting sweep would bury this fix in a 64-file diff.

**Root cause closed in the same session (not just the symptom).** `uv.lock` was in `.gitignore` and every dependency in `pyproject.toml` was an open-ended `>=` floor, so a fresh clone resolved to whatever was newest on PyPI that day -- every clone was a fresh drift roll. This is the same failure mode as the 2026-04-24 edgartools entry, and the "weekly live-API smoke test" proposed there would not have caught it: this break is at import/unit-test level with no network involved.

Three changes close the class:
- **`uv.lock` is now committed** (removed from `.gitignore`). 167 packages pinned; `uv sync --frozen --extra dev` verified reproducible.
- **Every direct dependency carries an upper bound** (`>=floor,<next-major`). Two floors were raised because they were actively wrong, not merely loose: `pydantic-ai>=1.0.0` -> `>=2.0.0` (1.x would now fail against the migrated call sites; annotated inline in pyproject.toml) and `anthropic>=0.94.0` -> `>=1.0.0` (that dep had silently crossed 0.x -> 1.x too, so far without breaking). All other floors left as-is -- they encode "minimum known-good", and the lock pins the actual resolve.
- **ruff unified and capped** at `>=0.16.8,<0.17`. It previously appeared twice with conflicting floors (`>=0.15.0` in optional-dependencies, `>=0.15.10` in dependency-groups), so formatter output was not deterministic across environments.
- **`### Dependency Policy` added to CLAUDE.md** so the convention outlives this session: frozen installs, deliberate per-package upgrades, lockfile deltas in their own commit.

Suite re-verified green (1134 passed, 9 skipped) after re-resolving from scratch against the new bounds.

**Pre-existing, deliberately not swept here:** `ruff format --check` reports 64 unformatted files under 0.16.8 -- but also 28 under 0.15.x, the version this code was written against. So this is genuine formatting debt, not pure version drift, and a 64-file reformat would have buried a 27-line fix. Worth its own commit.

**Also spotted, not addressed:** `CLAUDE.md` has 12 duplicated section headings (`## Conventions`, `## Architecture`, `### Code Style`, `### Layers`, and 8 more each appear twice) -- roughly half the 408-line file is duplicated content, likely a bad merge. And GitHub's default branch is `main`, a 2-commit stub; all 539 commits of real work live on `shared/backtest-framework`, so a fresh clone lands on an effectively empty repo.

Second drift surfaced from the first end-to-end AAPL run: APPROVED risk assessments shipped with `risk_score: 0/100`. Root cause: `derive_risk_score` (output/signal.py) read `observed`/`limit` off `RiskAssessment`, but those fields are only populated when a check fires a `Violation` -- i.e. only on VETOED. APPROVED runs collapsed `or 0.0` / `or 1.0` fallbacks to ratio=0.

**Fix shape (per 08-RESEARCH.md A9):** every deterministic check now returns a `CheckResult(ratio, violation | None)` NamedTuple so utilization aggregation runs even when no violation fires. The risk_manager_node aggregates `utilization = min(1.0, max(per_check_ratios))` and writes it to a new required `RiskAssessment.utilization: float` field. `derive_risk_score` reads that field directly; legacy observed/limit fallback preserved for stored audit payloads.

Invariants preserved:
- "First violation wins" short-circuit kept by walking the ordered `[exclusions, position_size, sector, correlation, drawdown]` list and taking the first non-`None` violation.
- Tool-first: LLM still authors only the rationale; `status` and `utilization` are Python-derived (T-06-02, T-08-12).
- Frozen result types: `Violation` stays a frozen Pydantic model; new `CheckResult` is a NamedTuple (immutable).
- Policy SHA audit (T-06-04) and veto bypass protection (T-06-02) untouched.

**Files changed:**
- `src/ai_hedge_fund/schemas/risk.py` — added `CheckResult` NamedTuple + required `utilization: float = Field(ge=0.0, le=1.0)` on `RiskAssessment`.
- `src/ai_hedge_fund/risk/checks.py` — `check_position_size`, `check_sector_concentration`, `check_exclusions` return `CheckResult`; shared `_safe_ratio` helper.
- `src/ai_hedge_fund/risk/correlation.py` — `check_correlation` returns `CheckResult`.
- `src/ai_hedge_fund/risk/drawdown.py` — `check_drawdown` returns `CheckResult`; `insufficient_price_history` fail-closed branch saturates `ratio=1.0` so utilization reflects the data-quality breach.
- `src/ai_hedge_fund/graph/nodes.py` — `risk_manager_node` runs all 5 checks unconditionally, aggregates utilization, logs it.
- `src/ai_hedge_fund/output/signal.py` — `derive_risk_score` reads `utilization` directly with legacy observed/limit fallback for back-compat.

**Test changes:**
- `tests/risk/test_position_size.py`, `test_sector_check.py`, `test_correlation.py`, `test_drawdown.py` — updated for new return shape; added per-check ratio assertions including pass-through utilization for APPROVED branches.
- `tests/risk/test_risk_assessment_schema.py` — added 5 tests covering `utilization` required-field semantics, [0,1] bounds, and `CheckResult` immutability + tuple unpacking.
- `tests/output/test_final_signal.py` — added utilization-driven derivation tests, legacy fallback tests, and out-of-range clamp tests (defensive against stale payloads).
- `tests/graph/test_risk_node.py` — added 3-test utilization aggregation regression suite (APPROVED non-zero, VETOED clamps to 1.0, max-aggregation across checks).

**Verification:**
- 76 risk tests + 94 output tests + 105 graph tests = 275 tests, all green post-fix.
- Phase-6/7/8 integration suite (78 tests touching risk_assessment) all green; 3 unrelated `pytest.mark.asyncio` plugin failures pre-existed and are not caused by this fix.
- `ruff format` reformatted 2 files (cosmetic); `ruff check` clean on every file touched.
- End-to-end re-run pending (requires live `ANTHROPIC_API_KEY` + EDGAR + DB) -- session file `.planning/debug/risk-score-zero-on-approved.md` marked `status: resolved`, with the AAPL re-run flagged as the human-UAT verification step.

# Progress

## 2026-04-24 — First end-to-end pipeline run (AAPL) + edgartools 5.28.5 migration

First real `run_analysis` invocation against live APIs surfaced two classes of drift that milestone-v1.0's unit tests had masked:

- **edgartools API drift.** Code was written against a pre-5.x edgartools surface; installed `edgartools==5.28.5` renamed `EntityFiling.form_type` → `.form` and replaced `CompanyFacts.to_pandas()` (flat `namespace/fact/val/units/fp/fy/filed/form` schema) with `EntityFacts.to_dataframe(pit_mode=True)` (`concept/value/unit/period_type/period_end/fiscal_year/fiscal_period/filing_date/form_type`). Migration strategy: use native `pit_mode=True` path — it preserves `filing_date` + `form_type` columns and is documented as "lookahead-bias-free for backtesting", matching our temporal-controls invariant natively. No `FactQuery.as_of()` rewrite needed.
- **Risk returns DataFrame never populated.** `run_analysis.py` hard-coded `RiskDeps(returns=pd.DataFrame())`, so even with `daily_prices` seeded the drawdown check always reported `observed=0.0 < limit=60` and VETOed. Patched to query `daily_prices` for `{candidate_ticker ∪ portfolio_tickers}` where `trade_date <= as_of_date`, pivot on ticker, compute `np.log(prices / prices.shift(1))`.

**Files changed (code fixes):**
- `src/ai_hedge_fund/data/clients/edgar_client.py:81,162` — `.form_type` → `.form`
- `src/ai_hedge_fund/data/clients/xbrl_client.py` — full rewrite of `get_facts` + `_resolve_concept_facts` against `to_dataframe(pit_mode=True)`; dedupe restatements per `(concept, period_end)` by latest `filing_date`; prefer 10-K / 10-K/A; public contract (`{ticker, fiscal_period, fiscal_year, metrics: {concept: {current, prior}}}`) preserved.
- `src/ai_hedge_fund/scripts/run_analysis.py` — build real log-returns DataFrame from `daily_prices` before constructing `RiskDeps`.
- `tests/unit/test_financial_tools.py` — fixture `_make_company_facts` produces `.to_dataframe(pit_mode=True)` in the new schema.
- `tests/unit/test_filing_tools.py` — `MockFiling.form_type` → `.form` to match real `EntityFiling`.

**Verification:**
- End-to-end run: `AAPL / 2026-04-18 / Technology` completes in ~3.7 min, ~111k tokens (~$1.50–2 API cost). Output: `direction=NEUTRAL, conviction=55, review_status=NOT_REQUIRED, risk_status=APPROVED`. Debate pre/post confidence: 62 → 55 (bear moved the needle); synthesis quality: 79.
- Full test suite: 1032/1032 passing across `tests/{unit,graph,memory,output,review,risk,scripts}`. Ruff clean.
- Persisted: `episodic_memory.id=3` (analysis) + `id=4` (review NOT_REQUIRED audit row) with `risk_policy_sha` and `review_policy_sha` stamped.
- Debug session record: `.planning/debug/xbrl-api-mismatch.md` (resolved).

**Ops steps taken (not code):**
- Added free-tier `FINNHUB_API_KEY` + `FRED_API_KEY` to `.env` (sentiment + macro agents hard-required them).
- Seeded `daily_prices` with 85 days of AAPL OHLCV via `PriceClient.download()` (2025-12-15 → 2026-04-18).
- Stamped alembic to `head` (DB had tables from a prior `metadata.create_all()` but no `alembic_version` row); ran `Base.metadata.create_all(checkfirst=True)` to backfill `portfolio_positions`, `episodic_memory`, `daily_prices`, `insider_trades`, `macro_indicators`, `news_articles`.

**Gap worth flagging:** milestone-v1.0 shipped with 100% unit-test coverage but zero integration runs against live edgartools/yfinance/Finnhub/FRED. The `08-HUMAN-UAT.md` verification step apparently never exercised the real data layer. Consider adding a smoke-test target that runs one pipeline per week against live APIs to catch vendor-API drift early.

## 2026-04-23 — Phase 8 Plan 08-05 + MILESTONE v1.0 COMPLETE (8/8 phases)

- **Phase-gate integration suite (18 tests) shipped:**
  - `tests/integration/test_phase8_e2e.py` — 8 composed-pipeline scenarios covering SIG-01..04 (above-threshold interrupt, below-threshold NOT_REQUIRED, APPROVED/REJECTED resume via `Command(resume=ReviewDecision(...))`, T-08-05 append-only invariant under REJECTED, T-08-06 VETOED-never-reaches-review, uniform-audit NOT_REQUIRED row, portfolio_view freshness, Phase-5 backcompat topology).
  - `tests/integration/test_phase8_review_policy_sha_linkage.py` — 6 three-way SHA scenarios (determinism, drift sensitivity, idempotent revert, 64-char hex on APPROVED + REJECTED, three-way equality state/row/recomputed).
  - `tests/integration/test_phase8_audit_reconstruction.py` — 4 audit-trail scenarios (APPROVED + NOT_REQUIRED + both risk/review policy_shas + wrong-id ValueError).
  - All 12 agents (11 debate/risk + self_critique) stubbed via TestModel; zero real LLM calls.
- **Rule 1 auto-fix:** `src/ai_hedge_fund/memory/recall.py::query_episodic` now filters `record_type IN ('analysis','outcome')`. Review rows are audit metadata, not analyst evidence — surfacing them to `memory_recall_node` violated `EpisodicHit.record_type` pattern `^(analysis|outcome)$` and blocked multi-run integration tests sharing a session.
- **Validation sign-off:** `.planning/phases/08-signal-and-output/08-VALIDATION.md` stamped with `nyquist_compliant: true`, `wave_0_complete: true`, `status: complete`. Per-Task Verification Map populated with 15 rows across Plans 08-00..08-05, all marked green.
- **Test counts:** Phase-8 integration 18/18 green; full suite 1108 passed, 9 skipped, 2 documented pre-existing baseline failures (pytest-asyncio absence on research_pipeline.py — unchanged).
- **Requirements closed:** SIG-01 (no-null signal), SIG-02 (portfolio view freshness), SIG-03 (HITL review gate), SIG-04 (compliance audit trail) — all delivered end-to-end.
- **MILESTONE v1.0 COMPLETE: 8/8 phases, 34/34 plans shipped.** Phase 1 (Foundation) -> Phase 2 (Data) -> Phase 3 (Research Agent) -> Phase 4 (Multi-Agent) -> Phase 5 (Debate) -> Phase 6 (Risk) -> Phase 7 (Memory) -> Phase 8 (Signal + Output) all green.
- Files: `test_phase8_e2e.py`, `test_phase8_review_policy_sha_linkage.py`, `test_phase8_audit_reconstruction.py`, `08-05-SUMMARY.md`, `08-VALIDATION.md`, `STATE.md`, `ROADMAP.md`, `REQUIREMENTS.md`, `recall.py` (Rule 1 fix).

## 2026-04-23 — Phase 8 Plan 08-03: Graph wiring (HITL interrupt + output assembly + review_store)

- **ReviewDeps** (`src/ai_hedge_fund/graph/review_deps.py`): frozen dataclass mirroring `MemoryDeps`/`RiskDeps`. Carries `db_session` + XOR `policy`/`policy_path`; XOR enforced in `__post_init__`; `TYPE_CHECKING` SQLAlchemy import to keep runtime surface minimal.
- **4 new graph primitives** (`src/ai_hedge_fund/graph/nodes.py`):
  - `output_node` (SIG-01): pure-Python `FinalSignalOutput` assembly from authoritative state; stamps `review_policy_sha`; short-circuits on upstream error / missing signal / missing episodic_id.
  - `human_review_node` (SIG-03): builds review_request dict + calls `langgraph.types.interrupt(review_request)` -- the genuine LangGraph HITL primitive (T-08-03 mitigation, greppable in source); `Command(resume=...)` -> `ReviewDecision.model_validate` (T-08-04 schema enforcement).
  - `review_store_node` (SIG-04): appends new `record_type='review'` `EpisodicMemory` row with `linked_analysis_id` (T-08-05 append-only); fires on BOTH reviewed and NOT_REQUIRED paths (audit row uniformity).
  - `route_before_review`: fail-closed conditional router; `conviction >= threshold` routes to `human_review`; below or missing routes to either `review_store` (below threshold) or `human_review` (fail-closed missing state).
- **DebatePipelineState extension** (`src/ai_hedge_fund/schemas/state.py`): 4 new single-writer keys (`final_signal`, `review_decision`, `review_stored_id`, `_review_threshold`) -- NO `operator.add` reducer.
- **build_debate_pipeline extension** (`src/ai_hedge_fund/graph/pipeline.py`): 3 new kwargs (`with_output`, `with_review`, `review_deps`) + 4 ValueError guards (T-08-21 + T-08-23 + 2 structural). Pipeline-builder normalises `review_deps` once at build time (loads YAML if `policy_path`); per-call I/O eliminated. Surgical edge edits: existing `episodic_store -> END` becomes conditional on `not with_output`; new tail block adds `episodic_store -> output -> [route_before_review|review_store] -> END`.
- **Tests added:** +45 (7 in `test_review_node.py` + 24 in `test_output_node.py` + 14 in `test_pipeline_review.py`). Graph subsuite 101/101 green; Phase 5/6/7 cross-phase regression 31/31 green; full suite 1071 passing (2 pre-existing pytest-asyncio failures documented in 07-04 deferred-items).
- **VETOED-no-review invariant verified:** VETO routes to episodic_store (Phase-6 conditional); output_node short-circuits on missing signal; human_review_node short-circuits on the resulting error; no `__interrupt__` fires.
- Files: `08-03-PLAN.md`, `08-03-SUMMARY.md`, `review_deps.py`, `nodes.py`, `pipeline.py`, `state.py`, `test_review_node.py`, `test_output_node.py`, `test_pipeline_review.py`, `tests/graph/conftest.py`, `STATE.md`, `ROADMAP.md`, `REQUIREMENTS.md`.
- Requirements progressed (CLI in 08-04, e2e in 08-05): **SIG-01** (output_node graph wiring), **SIG-03** (human_review_node interrupt + route_before_review), **SIG-04** (review_store_node append-only persistence).
- Milestone progress: 4/6 Phase-8 plans complete; ~94% overall.

## 2026-04-23 — Phase 8 Plan 08-02: query_portfolio_view (SIG-02) + reconstruct_audit_trail CLI (SIG-04)

- **query_portfolio_view** (`src/ai_hedge_fund/output/portfolio_view.py`): pure read-path query over append-only `episodic_memory`. Returns `{sector: [entry, ...]}` ranked by `conviction DESC, as_of_date DESC`; latest-per-ticker; `record_type='analysis'` only; `as_of_date <= target` temporal cutoff; `limit_per_sector=50` DoS cap. No memoization -- the append-only table IS the cache (Pitfall C / T-08-15).
- **reconstruct_audit_trail + audit_reconstruct CLI** (`src/ai_hedge_fund/scripts/audit_reconstruct.py`): synchronous reconstruction of analysis row + linked review row + Langfuse `thread_id` hint; `policy_sha` + `review_policy_sha` preserved for compliance linkage. CLI: `uv run python -m ai_hedge_fund.scripts.audit_reconstruct --episodic-id N` prints JSON. Raises `ValueError` on missing id OR wrong `record_type` (T-08-19 repudiation mitigation).
- **output/__init__.py** extended: `query_portfolio_view` re-exported alongside the 4 existing Plan 08-01 re-exports (APPEND, not rewrite).
- **Tests added:** +21 (11 portfolio_view + 10 audit_reconstruct). Wave-1 output suite 84/84 green; cross-phase (output + memory + review) 268/268 green; full suite 1026 passed (+21 from 08-01 baseline), 2 pre-existing unrelated failures.
- Files: `08-02-PLAN.md`, `08-02-SUMMARY.md`, `portfolio_view.py`, `audit_reconstruct.py`, `test_portfolio_view.py`, `test_audit_reconstruct.py`, `output/__init__.py`, `STATE.md`, `ROADMAP.md`, `REQUIREMENTS.md`.
- Requirements closed: **SIG-02** (portfolio view) and **SIG-04** (compliance-grade audit read side).
- Milestone progress: 3/6 Phase-8 plans complete; ~91% overall.

## 2026-04-22 — Phase 7 Post-Completion: Review, Fixes, Verification

- **Code review (standard depth):** 34 source files reviewed. 0 critical, 3 warnings (WR-01 sector regex guard gap, WR-02 orphan outcome row logging, WR-03 observed_date nullable=False hardening), 6 info items deferred.
- **All 3 warnings fixed in one iteration** (commits `64d07b2`, `bea30b0`, `ce69156`). REVIEW-FIX status: `all_fixed`.
- **Verification (goal-backward):** 4/4 ROADMAP success criteria pass automated verification (status: `human_needed`). 2 UAT items persisted to `07-HUMAN-UAT.md` (MEM-02 subjective readability; MEM-03 live pipeline + Langfuse trace). User deferred UAT; phase accepted as code-complete.
- **Regression after fixes:** 234 memory/graph/integration tests green with WR-03 applied; 921 full suite green (2 pre-existing unrelated failures documented).
- **Artifacts:** `07-REVIEW.md`, `07-REVIEW-FIX.md`, `07-VERIFICATION.md`, `07-HUMAN-UAT.md`.
- **Milestone status:** 7/8 phases complete — Phase 8 (Signal and Output) remains.

## 2026-04-22 — Phase 7 Complete: Memory and Learning

Plan 07-05 ships the integration test suite and closes the phase:

- **14 new integration tests** across `tests/integration/test_phase7_e2e.py` (8 e2e scenarios) and `tests/integration/test_phase7_policy_sha_linkage.py` (6 policy_sha audit linkage tests).
- **All 12 agents stubbed via TestModel** in every scenario (fundamental, sentiment, technical, manager, bull, bear, rebuttal, final_arguments, debate_synthesis, risk_manager, signal, self_critique). Zero real LLM calls.
- **MEM-01..04 + MEM-03 x MEM-04 interaction + Pitfall-2 temporal correctness + Phase-5 backcompat** all proven end-to-end via composed `build_debate_pipeline(with_memory=True, with_risk=True)` runs on seeded fixtures.
- **Phase 6 -> Phase 7 policy_sha audit chain** proven by 6 dedicated tests: deterministic (same policy), change-sensitive (different policy), idempotent (revert), well-formed (64-hex APPROVED + VETOED), three-way equal (state / column / payload all agree).
- **VETOED persistence ratified** (research Open Question 1): a vetoed run produces a stored EpisodicMemory row with `payload['risk_assessment']['status'] == 'VETOED'` AND `signal_direction is None` AND a well-formed policy_sha.
- **tests/integration/conftest.py** added: re-exports 7 memory fixtures from `tests/memory/conftest.py` so integration tests consume them via pytest's sibling-conftest discovery (avoids F811 ruff false-positive from direct module imports). Mirrors the pattern already in `tests/graph/conftest.py`.
- **199 Phase-7 tests green** across `tests/memory` (162) + `tests/graph/test_memory_nodes.py` + `tests/graph/test_pipeline_with_memory.py` (23) + `tests/integration/test_phase7_*.py` (14).
- **Full suite:** 920 passed, 9 skipped, 2 pre-existing baseline failures (`test_research_pipeline.py` async tests missing `pytest-asyncio`, documented in `deferred-items.md`).
- **Cross-phase regression clean:** Phase 5 (17 integration) + Phase 6 (122 graph/risk + 17 integration) + earlier Phase 7 (185 memory + graph) all still green byte-for-byte.
- **07-VALIDATION.md:** `nyquist_compliant: true`, `wave_0_complete: true`, Per-Task Verification Map populated with 15 rows (all green), Validation Sign-Off approved.
- **REQUIREMENTS.md:** MEM-01, MEM-02, MEM-03, MEM-04 all marked Complete with phase-7 attribution.
- **Milestone v1.0 progress: 7/8 phases complete** (ready for Phase 8 — Signal and Output).

Files: `07-05-PLAN.md`, `07-05-SUMMARY.md`, `test_phase7_e2e.py`, `test_phase7_policy_sha_linkage.py`, `tests/integration/conftest.py`, `07-VALIDATION.md` (sign-off), `deferred-items.md` (ruff I001 deferral), `STATE.md`, `ROADMAP.md`, `REQUIREMENTS.md`.

## 2026-04-22 — Phase 7 Plan 04: Offline Self-Critique Loop (MEM-04)

- **compute_new_confidence** (`src/ai_hedge_fund/memory/critique.py`): pure deterministic math. Returns int in `[0, 100]`; agreement (long+pos, short+neg) raises confidence, disagreement and neutral+big-move lower it; per-event |delta| capped at 10 (Pitfall 5 drift guard); `ValueError` on unknown signal_direction.
- **format_critique_context** (`src/ai_hedge_fund/memory/critique.py`): deterministic 5-section prompt (BELIEF / OUTCOME / OLD_CONFIDENCE / NEW_CONFIDENCE (DETERMINISTIC) / LINKED_ANALYSIS) for audit-reproducible LLM input.
- **self_critique_agent** (`src/ai_hedge_fund/agents/self_critique.py`): PydanticAI `Agent[None, RationaleOnly]` on REASONING tier with `retries=2`; system prompt uses EXPLAIN exclusively; forbidden verbs (decide/judge/determine/rule/verdict + plurals) absent via word-boundary regex (T-07-31 analog of T-06-02b). `RationaleOnly` has EXACTLY ONE field (T-07-30).
- **ingest_outcome CLI** (`src/ai_hedge_fund/scripts/ingest_outcome.py`): 6-step offline loop — regex-guard → append outcome row → load belief → compute new confidence → LLM rationale → write_belief (MEM-03 chokepoint).
- **MEM-03 × MEM-04 cross-requirement proven:** human-edited belief survives outcome ingest (confidence unchanged, critique_history updated, skipped audit visible to operator).
- **Tests added:** +111 (93 critique math + 13 self-critique agent + 5 ingest_outcome). Full cross-phase regression (phases 5/6/7): 291 passing.

## 2026-04-22 — Phase 6 Plan 02: Portfolio Data Layer

- **PortfolioPosition** (`src/ai_hedge_fund/db/models.py`): append-only SQLAlchemy model on `Base + DualTimestampMixin` with `UniqueConstraint(ticker, as_of_date)`; mirrors the DailyPrice pattern for financial-time-series persistence
- **Alembic 002** (`alembic/versions/002_create_portfolio_positions.py`): creates `portfolio_positions` table with index on ticker and the unique constraint; `down_revision = "001"`
- **PortfolioSnapshot + loader** (`src/ai_hedge_fund/risk/portfolio.py`): frozen Pydantic models (`PortfolioSnapshot`, `PortfolioSnapshotPosition`); `load_portfolio(db_session, as_of_date)` filters by `as_of_date <= target` (Pitfall 2 temporal correctness) and collapses to latest row per ticker; `seed_portfolio_from_csv` writes one row per CSV record with a shared as_of_date
- **CSV fixture** (`tests/risk/fixtures/portfolio_sample.csv`): 5 positions across 4 sectors (Technology x2, Healthcare, Financials, Consumer Staples) for concentration-test variation
- **Tests added:** 12 (4 model + 8 loader); test count now 30 in `tests/risk/` alongside 06-01's schema tests

## 2026-04-22 — Phase 5 Complete: Adversarial Critique

- **Debate schemas** (`src/ai_hedge_fund/schemas/debate.py`): 8 Pydantic models (BullClaim, BullCase, BearClaim, BearCase, RebuttalPoint, RebuttalAct, FinalArguments, DebateSynthesis) with `min_length`/`ge/le`/`Literal` constraints enforcing the 5-act protocol; `BearCase` model_validator enforces addressed_bull_claims ↔ BearClaim.addresses_bull_claim cross-link
- **5 adversarial agents** (`src/ai_hedge_fund/agents/{bull,bear,rebuttal,final_arguments,debate_synthesis}.py`): all REASONING tier (Opus), zero tools, retries=2; rebuttal + final_arguments use `output_override=8_000` cost guardrail; synthesis uses default REASONING cap
- **Pure-function quality score** (`src/ai_hedge_fund/agents/debate_synthesis.py::compute_quality_score`): weighted mean over evidence/logic/risk (0.4/0.3/0.3 module constants); CLAUDE.md tool-first enforcement
- **5 async debate nodes + pipeline** (`src/ai_hedge_fund/graph/{nodes.py,pipeline.py}`): `build_debate_pipeline` sequential chain (manager→bull→bear→rebuttal→final→synthesis→signal); no manager→signal diamond (Pitfall 4 avoided); `debate_synthesis_node` overwrites LLM quality_score + pre_debate_confidence via `model_copy(update=...)`
- **DebatePipelineState** TypedDict (single-writer debate fields, NO operator.add reducer, contract-tested)
- **Phase 4 pipeline unchanged** (byte-for-byte guarantee, `TestPhase4PipelineStillWorks` enforces)
- **Test count: +107 new tests** (472 → 578 unit tests passing, 0 regressions). 4 new integration tests for the 10-agent end-to-end debate flow.
- **Code review**: 0 critical, 3 warnings auto-fixed (BearCase cross-link validator, NonEmptyStr element constraint, explicit thesis precondition in debate_synthesis_node), 5 info items deferred as tech debt
- **Human UAT deferred**: 5 items requiring real Anthropic API + Langfuse (30%-of-runs confidence delta, semantic rebuttal alignment, sycophancy audit, per-debate token cost, Langfuse trace audit) persisted to `05-HUMAN-UAT.md`
- Files: `05-CONTEXT.md`, `05-RESEARCH.md`, `05-PATTERNS.md`, `05-VALIDATION.md`, `05-01/02/03-PLAN.md`, `05-01/02/03-SUMMARY.md`, `05-REVIEW.md`, `05-REVIEW-FIX.md`, `05-VERIFICATION.md`, `05-HUMAN-UAT.md`
- Milestone v1.0 progress: 5/8 phases complete

## 2026-03-27 — Project Setup

- Initialized git repo
- Created top-level `CLAUDE.md` with project conventions
- Created `.gitignore` (Python, data files, env, IDE)
- Created `docs/PROGRESS.md`
- Existing: `Al Washing Detector/` subfolder with research doc

## 2026-03-28 to 2026-04-06 — Strategy Development (archived)

- Built AI Washing Detector: SEC EDGAR ingestion, entity resolution, FinBERT NLP scoring, 11-table PostgreSQL schema, Prefect pipeline, 66 tests
- Built Kalshi Insider Tracker: real-time Kalshi polling, anomaly detection (volume/price/timing), APScheduler daemon, Streamlit dashboard, 12 tests
- Built fund-backtest: vectorized equity backtester, yfinance OHLCV ingestion, SignalAdapter pattern, Streamlit dashboard, quantstats metrics
- Built kalshi-backtest: Protocol-based strategy interface, DuckDB storage, Kalshi API historical data ingestion, binary contract simulation engine
- Completed Insider Tracker backtesting pipeline (replay historical data through signal detectors)

## 2026-04-11 — Strategic Pivot

- Archived all existing strategies and backtest engines to `archive/2026-04-11-pre-pivot/`
  - `Al Washing Detector/` (392 source files, 66 tests, 10 GSD phases)
  - `Kalshi Insider Tracker/` (28 source files, 12 tests, 6 GSD phases)
  - `backtest/` (fund-backtest equity engine)
  - `kalshi-backtest/` (prediction market engine with Protocol-based strategy interface)
  - Dashboard PNGs, `run_pipeline.sh`
- Archived planning artifacts to `.planning-archive/insider-tracker-20260411/`
- Rewrote `CLAUDE.md` for new direction
- Stripped strategy-specific env vars from `.env.example`
- New direction: AI-native multi-agent hedge fund — LLM agents for hypothesis generation, evidence gathering, adversarial critique, and backtesting

## 2026-04-11 — GSD Project Initialization

- Completed domain research (4 parallel agents):
  - Multi-agent trading systems: 13 academic papers, 5 production systems surveyed
  - Agent frameworks: 9 frameworks compared (LangGraph + PydanticAI recommended)
  - Financial data sources: 20+ APIs evaluated, free stack + $110/mo paid upgrade mapped
  - Competitive landscape: YC RFS analysis, fund structure, regulatory considerations
- Research files: `.planning/research/` (MULTI_AGENT_TRADING_SYSTEMS.md, AGENT_FRAMEWORKS.md, DATA_SOURCES.md, COMPETITIVE_LANDSCAPE.md, STACK.md, FEATURES.md, ARCHITECTURE.md)
- Created `.planning/PROJECT.md` — full project context with key decisions from research
- Created `.planning/REQUIREMENTS.md` — 36 v1 requirements across 8 categories
- Created `.planning/ROADMAP.md` — 8-phase roadmap with testable success criteria
- Created `.planning/STATE.md` — project state tracking
- Updated `CLAUDE.md` with architecture (Manager-Analyst + Adversarial Debate), stack (LangGraph + PydanticAI + Claude), data sources, conventions, and agent development rules
- Updated `.env.example` with all required environment variables

## 2026-04-11 — Networking Research

- Compiled comprehensive outreach list across 9 categories (~60+ people)
- Categories: AI finance founders, quant practitioners, LLM researchers, skeptics, compliance, data vendors, AI infra builders, allocators, YC alumni
- Added 10 conferences/events, 10 online communities, 7 podcasts, 3 outreach templates
- Prioritized first 5 outreach targets and sequenced by stage (now → pre-YC → post-YC → fundraising)
- File: `docs/NETWORKING_RESEARCH.md`
