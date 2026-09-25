---
phase: 12
slug: promotion-gate
title: Promotion Gate
milestone: v1.1
requirements: [PROMO-01, PROMO-02, PROMO-03, PROMO-04, PROMO-05]
branch: phase/12-promotion-gate
status: draft            # draft -> signed-off. AWAITING HUMAN SIGN-OFF on D1-D12.
signed_off:
written: 2026-09-26
---

# Phase 12 -- Promotion Gate

**Goal** (ROADMAP.md): A SHA-pinned policy that decides whether a signal has earned live capital,
joined to the existing audit chain so any verdict is reconstructible after the fact.

**Starting point:** Phase 11 (merged, PR #7) left `paper_pnl_daily`: one append-only row per
(signal, NY trading day) with **cumulative** integer-cent `realized/unrealized/total_pnl_cents`,
`open_qty`, `open_cost_cents`, `mtm_policy_sha`, and `payload.fill_ids`. A skipped day has no row
(missing, not zero). Realized P&L is dividends only until an exit policy exists (11-PLAN D5), so
every metric below runs on mostly-unrealized P&L. `policy_sha.fingerprint()` is the one canonical
SHA helper; risk/review/execution/mtm policies each wrap it as `compute_*_policy_sha`.
`AppendOnlyGuard` + the PG trigger function `paper_append_only_guard()` (migration 004) are the
append-only pattern. The standalone-CLI shape is `scripts/mark_to_market._main`.

**Environment:** no new vendor. Postgres (`TEST_DATABASE_URL`) for migration/trigger/width tests.
Optional live Anthropic call for the rationale, stubbed with `TestModel` in the suite.
**Blocked on PR #8** (`fix/migration-chain-hardening`, migration 008) -- see D2.

## Gaps found while planning (drive D1-D5)

- **`record_type` lives only on `episodic_memory`, which is not append-only.** It is a bare
  `VARCHAR(20)` with no CHECK; the table has no `AppendOnlyGuard` on purpose, because
  `scripts/purge_expired_episodic.py` deletes rows older than 90 days. A `'promotion'` row there
  would be mutable and purged -- PROMO-05 cannot hold.
- **There is no top-level `*_policy_sha` in graph state, and `review_policy_sha` has no column.**
  Risk SHA: `state["risk_assessment"]["policy_sha"]`, column `episodic_memory.policy_sha`.
  Review SHA: payload only. The Phase 7/8 "three-way" tests compare state, payload and a
  recomputation; no existing test compares state + a dedicated column + `FinalSignalOutput`.
  PROMO-04 therefore needs a real column, which means a migration.
- **The gate cannot run inside the research graph.** A verdict needs weeks of marks that do not
  exist when `build_debate_pipeline` runs. "Graph state" must be a separate, small graph (D4).
- **No return denominator is stored.** `open_cost_cents` falls to 0 on a close; NAV is a policy
  constant. Metrics need a per-signal capital base (D6).
- **The retention purge breaks on any traded signal older than 90 days.** It issues a bare
  `DELETE ... WHERE as_of_date < cutoff` on `episodic_memory`; `paper_trades.signal_id` and
  `paper_pnl_daily.signal_id` are FKs (enforced on SQLite too, `db/sqlite_compat.py`), so the
  whole sweep fails with an IntegrityError. The gate's own window is ~90 days (D8), so the
  signals it judges are exactly the ones the purge trips on (D12).
- **No Sharpe/hit-rate code exists in `src/`.** The only drawdown code is
  `risk/drawdown.py::project_max_drawdown_pct`, which is tied to `RiskPolicy` and a pandas returns
  frame. The archived backtest used `quantstats` (not a dependency). New pure functions are
  needed (D6/D7).

## Decisions -- ALL AWAITING HUMAN SIGN-OFF

One line of choice + one line of rationale each. **Needs sign-off** = a product call or a v1.0
touch; the rest are defaults you can wave through.

- **D1 -- Decisions go in a new append-only table `promotion_decisions` with a `record_type`
  column fixed to `'promotion'` by CHECK and a dedicated `promotion_policy_sha VARCHAR(64) NOT
  NULL`.** `episodic_memory` is unguarded and purged at 90 days, so PROMO-05 can only hold on a
  guarded table. Rejected: an `episodic_memory` row (mutable, purged, and needs a SHA column
  anyway); guarding `episodic_memory` (v1.2 TECH-DEBT, conflicts with the purge).
  **Needs sign-off.**

- **D2 -- Migration number is 009 (`down_revision = "008"`), a hard dependency on PR #8.**
  PR #8 (open) takes 008 and adds `tests/db/test_migration_chain.py` (linear chain, unfiltered
  ORM/schema parity, including nullability). `/phase-exec` must not start until PR #8 is merged
  and this branch is rebased on main. T0 bumps `HEAD` in `tests/paper/test_migration_roundtrip.py`
  to `"009"`, and the ORM model must match the migration exactly. Fallback if PR #8 stalls:
  renumber to 008 (one revision id, one `down_revision`, one constant). Whichever merges second
  renumbers. **Needs sign-off.**

- **D3 -- The gate unit is one signal (`episodic_memory.id` of an `analysis` row with at least one
  `paper_pnl_daily` row).** This follows the ROADMAP wording. Caveat: with long-only buy-and-hold
  and no exit rule, a per-signal verdict asks "has this one position risen steadily for N days".
  A strategy-level (cohort) gate is probably what an LP means by "earned live capital", but it
  belongs with Phase 13's aggregate report. **Needs sign-off.** Recommendation: per signal now;
  cohort-level is v1.2.

- **D4 -- "Graph state" is a small dedicated LangGraph `StateGraph` (`promotion/graph.py`), not a
  node in the research pipeline.** Nodes: `load_track_record -> compute_metrics -> decide ->
  [explain] -> persist`. The verdict is set in `decide`. `explain` (the only LLM node) may return
  only `{"rationale", "rationale_status"}`, and a wrapper rejects any other key. That makes
  PROMO-03 structural, not a convention. The three-way check compares
  `state["promotion_policy_sha"]`, `promotion_decisions.promotion_policy_sha` and
  `PromotionDecisionOutput.promotion_policy_sha`. Alternative: a frozen dataclass "job state"
  like `mtm/job.py` (simpler, but it meets the letter of criterion 4 less directly, and a
  second-graph precedent is new ground either way). **Needs sign-off.** Recommendation: StateGraph,
  no checkpointer.

- **D5 -- The output payload is a new `PromotionDecisionOutput` (frozen, `extra="forbid"`), not a
  field on `FinalSignalOutput`.** A signal's `FinalSignalOutput` is emitted weeks before any
  promotion verdict exists. The output is what `--json` prints and is also stored whole as
  `promotion_decisions.payload["output"]`. Default; override at sign-off.

- **D6 -- Return basis: a per-signal sleeve funded with its gross invested capital.**
  `invested_t` = sum of buy-fill cost (`filled_qty * fill_price_cents`) filled on or before
  `pnl_date` (it never decreases). Equity `E_t = invested_t + total_pnl_cents_t`. The return per
  observation is `r_t = (total_t - total_{t-1}) / (invested_t + total_{t-1})`, with `total_0 = 0`
  for the first row, so capital added mid-track is never counted as return. A missing day is
  **not** zero-filled: the next row's delta is one multi-day observation (zero-filling would
  fabricate data). Drawdown is peak-to-trough on `E_t` as a fraction, from 0 to 1. All inputs are
  integer cents; ratios are Python floats via `statistics`. **Needs sign-off.** Alternative:
  NAV-denominated returns ($100k). This gives nearly the same Sharpe but understates drawdown about 20x
  for a 5% position.

- **D7 -- Metric definitions (product call).**
  - *Sharpe:* `mean(r) / stdev(r, ddof=1) * sqrt(annualization_days)`, risk-free = 0.
    It is `None` (undefined) when n < 2 or the stdev is 0. Options:
    (a) sqrt(252), rf = 0 **[recommended]**, the archived backtest's convention;
    (b) sqrt(252) with rf from FRED DGS3MO as of each date (more correct, but adds a data
        dependency and a temporal filter);
    (c) unannualised per-observation Sharpe.
    `annualization_days` is a policy field, so it is SHA-pinned.
  - *Hit rate:* share of observations with `total_t - total_{t-1} > 0`; a flat delta counts as a
    miss. Options: (a) per-observation within the signal **[recommended, matches D3]**;
    (b) share of profitable signals (cohort-level, belongs to D3's cohort gate / Phase 13).
  - *Sample size:* the number of return observations (= marked rows).
    *Paper-days:* calendar days from the first fill's NY trading date to `as_of`
    (`(as_of - first_fill_date).days`). This needs no exchange calendar, which the project lacks.
  **Needs sign-off.**

- **D8 -- Default thresholds in `config/promotion_policy.yaml` (product call).** Every field is
  required; there are no code defaults (PROMO-01).

  | field | A: conservative **[recommended]** | B: fast feedback |
  |---|---|---|
  | `min_paper_days` | 90 | 30 |
  | `min_sample_size` | 60 | 20 |
  | `min_sharpe` | 1.0 | 0.5 |
  | `max_drawdown` | 0.15 | 0.20 |
  | `min_hit_rate` | 0.50 | 0.45 |
  | `annualization_days` | 252 | 252 |
  | `metric_rule_version` | 1 | 1 |

  Honest-positioning note: the standard error of an annualised Sharpe from 60 daily observations
  is about sqrt(252/60) = 2.0. A Sharpe >= 1.0 gate is a floor, not evidence of skill; the Phase
  13 report must say so. The values are literature-style defaults, not fitted. The v1.1 open
  question 2 (derive them from an in-sample backtest) stays open. **Needs sign-off.**

- **D9 -- Verdict rules (pure Python, all bounds inclusive).**
  1. No observations -> `paper-only` (`no_track_record`).
  2. `max_drawdown > policy.max_drawdown` -> `rejected` (`drawdown_above_max`), **at any sample
     size**: a realised drawdown is evidence no matter how short the window.
  3. `paper_days < min` or `sample_size < min` -> `paper-only` (`below_min_paper_days` /
     `below_min_sample`).
  4. Sharpe undefined -> `paper-only` (`sharpe_undefined`); undefined never passes.
  5. `sharpe < min` or `hit_rate < min` -> `rejected` (reason codes list every failing metric).
  6. Otherwise -> `eligible-for-live` (`all_thresholds_met`).

  `rejected` is not terminal: a later run appends a new row, and the highest `id` per signal is
  the current verdict (the same rule as reviews, `execution/submit.py:122`). `eligible-for-live`
  is advisory. No live order path exists in v1.1, and any live allocation needs human review
  (CLAUDE.md). **Needs sign-off** on rule 2 (the option is to judge drawdown only after the
  minimums).

- **D10 -- The LLM rationale is opt-in (`--with-rationale`), on the Haiku (EXTRACTION) tier, with
  about an 800-token output cap.** The prompt holds the deterministic metrics, the verdict and the
  reason codes. The model returns only `PromotionRationale.rationale`. On any LLM failure
  (`UsageLimitExceeded`, API error) the decision is still recorded with `rationale=None` and
  `rationale_status="failed"`, so the model can never block or alter a verdict. Off by default so
  a daily cron costs $0. The reason codes are the audit source of truth; the prose is commentary.
  Default; override at sign-off.

- **D11 -- Point-in-time inputs; every run appends.** A decision for `as_of` reads `paper_pnl_daily`
  rows with `pnl_date <= as_of AND observed_date <= observed_cutoff` (the run's start time), and
  fills the same way. `as_of` defaults to today's NY trading date; a future `as_of` exits 3. The
  row payload stores the pnl row ids, fill ids, `observed_cutoff`, the full policy dump, the
  metrics, and the signal's upstream SHAs (`policy_sha`, `review_policy_sha`,
  `execution_policy_sha`, the distinct `mtm_policy_sha`s), so the decision replays exactly. Each run
  appends a row even when nothing changed (every run is an audit event; `--dry-run` writes
  nothing). Default; override at sign-off.

- **D12 -- Fix the retention purge in this phase (fix-as-you-find, its own commit).**
  `purge_expired_episodic` skips `episodic_memory` rows referenced by `paper_trades`,
  `paper_pnl_daily` or `promotion_decisions`, instead of failing the whole sweep on an FK error.
  The change is under 30 LOC, and without it no 90-day promotion history can coexist with
  retention. Alternative: defer to TECH-DEBT and never run the purge. **Needs sign-off** (it
  touches a v1.0 script).

## Interfaces

All new code lives in `src/ai_hedge_fund/promotion/`. The only LLM-importing module is
`promotion/graph.py`, via `agents/promotion_rationale.py`. `metrics`, `gate`, `policy`, `inputs`
and `store` must not import `ai_hedge_fund.agents`, `pydantic_ai` or `ai_hedge_fund.graph`.

```python
# promotion/records.py (T0) -- contracts; all BaseModel frozen, extra="forbid"
Verdict = Literal["paper-only", "eligible-for-live", "rejected"]
ReasonCode = Literal["no_track_record", "below_min_paper_days", "below_min_sample",
                     "sharpe_undefined", "sharpe_below_min", "drawdown_above_max",
                     "hit_rate_below_min", "all_thresholds_met"]
RationaleStatus = Literal["not_requested", "ok", "failed"]

class PromotionPolicy(BaseModel):          # every field required, no defaults (PROMO-01)
    min_paper_days: int                    # strict, ge=1
    min_sample_size: int                   # strict, ge=2
    min_sharpe: float
    max_drawdown: float                    # gt=0, le=1 (fraction)
    min_hit_rate: float                    # ge=0, le=1
    annualization_days: int                # strict, ge=1
    metric_rule_version: int               # strict, ge=1; bump when D6/D7 formulas change

class Observation(BaseModel):
    pnl_row_id: int; pnl_date: date; total_pnl_cents: int; invested_cents: int   # strict ints

class TrackRecord(BaseModel):
    signal_id: int; ticker: str; as_of: date; observed_cutoff: datetime   # tz-aware UTC
    first_fill_date: date | None
    observations: tuple[Observation, ...]  # pnl_date ascending, unique
    fill_ids: tuple[int, ...]
    upstream_shas: dict[str, str | list[str]]

class PromotionMetrics(BaseModel):
    paper_days: int; sample_size: int
    sharpe: float | None; max_drawdown: float | None
    hit_count: int; hit_rate: float | None; total_pnl_cents: int

class GateResult(BaseModel):
    verdict: Verdict; reasons: tuple[ReasonCode, ...]   # non-empty, ordered as in D9

class PromotionDecisionOutput(BaseModel):   # the "output payload" of criterion 4
    decision_id: int | None                 # None on --dry-run
    signal_id: int; ticker: str; as_of: date; decided_at: datetime
    verdict: Verdict; reasons: tuple[ReasonCode, ...]; metrics: PromotionMetrics
    promotion_policy_sha: str               # min_length=64, max_length=64
    rationale: str | None; rationale_status: RationaleStatus

class NewPromotionDecision(BaseModel): ...  # insert DTO: output + track-record replay inputs
class PromotionDecisionRecord(BaseModel): ...  # read DTO incl. id, observed_date

# promotion/errors.py (T0)
class PromotionError(Exception): ...
class UnknownSignal(PromotionError): ...    # id missing or not record_type='analysis'
class FutureAsOf(PromotionError): ...       # as_of > trading_date(now) -> CLI exit 3
class ExplainContractViolation(PromotionError): ...  # explain node returned a non-rationale key

# promotion/state.py (T0)
class PromotionState(TypedDict, total=False):
    signal_id: int; as_of: date; observed_cutoff: datetime
    policy: PromotionPolicy; promotion_policy_sha: str
    track_record: TrackRecord; metrics: PromotionMetrics; gate_result: GateResult
    rationale: str | None; rationale_status: RationaleStatus
    decision_id: int | None; output: dict   # PromotionDecisionOutput.model_dump(mode="json")

# promotion/policy.py (T1)
DEFAULT_PROMOTION_POLICY_PATH = Path("config/promotion_policy.yaml")
def load_promotion_policy(path: Path | str = DEFAULT_PROMOTION_POLICY_PATH) -> PromotionPolicy: ...
def compute_promotion_policy_sha(policy: PromotionPolicy) -> str: ...  # returns policy_sha.fingerprint(policy)

# promotion/metrics.py (T2) -- pure
def observation_returns(obs: Sequence[Observation]) -> tuple[float, ...]: ...
def sharpe(returns: Sequence[float], *, annualization_days: int) -> float | None: ...
def max_drawdown(obs: Sequence[Observation]) -> float | None: ...
def compute_metrics(track: TrackRecord, policy: PromotionPolicy) -> PromotionMetrics: ...

# promotion/inputs.py (T3)
def load_track_record(db_session: Session, signal_id: int, *, as_of: date,
                      observed_cutoff: datetime) -> TrackRecord: ...    # raises UnknownSignal
def gate_candidates(db_session: Session, *, as_of: date, observed_cutoff: datetime) -> list[int]: ...

# promotion/gate.py (T4) -- pure, the only place a verdict is made
def decide(metrics: PromotionMetrics, policy: PromotionPolicy) -> GateResult: ...

# promotion/store.py (T5) -- insert only; never UPDATE/DELETE
def insert_decision(db_session: Session, new: NewPromotionDecision) -> PromotionDecisionRecord: ...
def query_decisions(db_session: Session, *, signal_id: int) -> list[PromotionDecisionRecord]: ...  # id asc
def latest_decision(db_session: Session, signal_id: int) -> PromotionDecisionRecord | None: ...  # max id

# agents/promotion_rationale.py (T6)
class PromotionRationale(BaseModel): rationale: str   # 1..1500 chars, extra="forbid"
promotion_rationale_agent: Agent[None, PromotionRationale]   # ModelTier.EXTRACTION
def get_promotion_rationale_limits() -> UsageLimits: ...     # output_override=800
def build_rationale_prompt(metrics: PromotionMetrics, result: GateResult,
                           policy: PromotionPolicy) -> str: ...

# promotion/graph.py (T7)
def build_promotion_graph(*, session_factory: Callable[[], Session], with_rationale: bool,
                          persist: bool = True) -> CompiledStateGraph: ...
async def run_gate(signal_id: int, *, as_of: date, observed_cutoff: datetime,
                   policy: PromotionPolicy, session_factory: Callable[[], Session],
                   with_rationale: bool = False, persist: bool = True) -> PromotionState: ...
```

**DDL (migration `009_create_promotion_decisions.py`, T0):**

```sql
CREATE TABLE promotion_decisions (
  id                   INTEGER PRIMARY KEY,
  signal_id            INTEGER NOT NULL REFERENCES episodic_memory(id),
  record_type          VARCHAR(20) NOT NULL,          -- CHECK record_type = 'promotion'
  decision_as_of       DATE NOT NULL,                 -- the as_of the track record was cut at
  verdict              VARCHAR(20) NOT NULL,          -- CHECK IN ('paper-only','eligible-for-live','rejected')
  promotion_policy_sha VARCHAR(64) NOT NULL,          -- CHECK length = 64
  metrics              JSONB NOT NULL,                -- PromotionMetrics (JSON on SQLite, none_as_null)
  reasons              JSONB NOT NULL,
  rationale            TEXT NULL,
  payload              JSONB NOT NULL,                -- {"output", "inputs", "policy", "upstream_shas", "schema_version": 1}
  as_of_date           TIMESTAMPTZ NOT NULL,          -- normalise_as_of(decision_as_of)
  observed_date        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_promotion_decisions_signal ON promotion_decisions (signal_id, id);
-- PG: trigger trg_promotion_decisions_append_only -> paper_append_only_guard() (owned by 004;
-- downgrade drops only this trigger). ORM: PromotionDecision(Base, DualTimestampMixin, AppendOnlyGuard).
```

**CLI `python -m ai_hedge_fund.scripts.promotion_gate` (T8):**

```python
def _main(argv: list[str] | None = None, *, session_factory: Callable[[], Session] | None = None,
          now_factory: Callable[[], datetime] | None = None) -> int: ...
# --signal-id INT (repeatable) | --all      (mutually exclusive, one required)
# --as-of YYYY-MM-DD (default trading_date(now)); --policy PATH; --database-url
# --dry-run (compute, write nothing); --json (list[PromotionDecisionOutput], stdout pure JSON);
# --with-rationale (D10)
# exit 0: every requested signal decided (any verdict); 1: PromotionError / UnknownSignal;
#      2: argparse; 3: FutureAsOf.   route_logs_to_stderr() like mark_to_market.
```

**`scripts/audit_reconstruct.reconstruct_audit_trail` (T10):** the result gains
`promotion_rows: list[dict]` (id ascending: verdict, `promotion_policy_sha`, `decision_as_of`,
reasons, `observed_date`) and `latest_promotion: dict | None`. Existing keys are unchanged.

## External contracts

| Vendor call | Probed shape / fixture | Source |
|---|---|---|
| Anthropic via pydantic-ai `Agent.run` (rationale only) | none new: same `output_type` model + `UsageLimits` pattern as `agents/risk_manager.py` (`RationaleOnly`); stubbed with `TestModel(custom_output_args=...)` | existing pattern, `tests/graph/test_risk_node.py`; no live probe needed (no new error mapping, since any exception maps to `rationale_status="failed"`) |

No broker or data vendor is called. The gate reads only persisted Phase 10/11 rows.

## Success criteria -> proof

| # | ROADMAP criterion | Proven by |
|---|---|---|
| 1 | policy YAML declares 5 thresholds; loader rejects any missing | `tests/promotion/test_policy.py::test_missing_threshold_rejected` (parametrized over every field), `::test_unknown_key_rejected`, `::test_repo_policy_file_loads` |
| 2 | `promotion_policy_sha` from the shared helper, not a third copy | `tests/promotion/test_policy.py::test_sha_delegates_to_shared_fingerprint`, `tests/unit/test_policy_sha_single_source.py::test_only_policy_sha_module_hashes_policies` |
| 3 | pure-Python verdict in {paper-only, eligible-for-live, rejected}; LLM prose only | `tests/promotion/test_gate.py::test_verdict_table` , `tests/promotion/test_graph.py::test_rationale_cannot_change_verdict`, `::test_explain_node_extra_key_raises`, `tests/promotion/test_no_llm.py::test_verdict_path_has_no_llm_surface` |
| 4 | state == column == payload | `tests/integration/test_phase12_promotion_sha_linkage.py::test_three_way_sha_equality` (drives `scripts.promotion_gate._main` and the graph; also == recomputed SHA) |
| 5 | each decision appends a `record_type='promotion'` row; prior row untouched | `tests/promotion/test_store.py::test_redecide_leaves_prior_row_byte_identical`, `tests/promotion/test_migration_009.py::test_pg_trigger_rejects_update_and_delete`, `::test_record_type_check_rejects_other_values` |

## Tasks

T0 is the scaffold: migration 009, ORM model, package `__init__`s, error classes, the record/state
contracts, the test seeding helpers, and the migration test. It owns hotspots, so it runs alone.

```yaml phase-tasks
- id: T0
  title: scaffold -- migration 009, PromotionDecision ORM, promotion package contracts, test seeds
  owns:
    - alembic/versions/009_create_promotion_decisions.py
    - src/ai_hedge_fund/db/models.py
    - src/ai_hedge_fund/promotion/__init__.py
    - src/ai_hedge_fund/promotion/errors.py
    - src/ai_hedge_fund/promotion/records.py
    - src/ai_hedge_fund/promotion/state.py
    - tests/promotion/__init__.py
    - tests/promotion/seed.py
    - tests/promotion/test_migration_009.py
    - tests/promotion/test_records.py
    - tests/paper/test_migration_roundtrip.py
  reads:
    - alembic/versions/007_create_paper_pnl_daily.py
    - alembic/versions/008_enforce_not_null_observed_date.py
    - src/ai_hedge_fund/db/append_only.py
    - src/ai_hedge_fund/mtm/store.py
    - tests/db/test_migration_chain.py
- id: T1
  title: promotion policy loader, YAML, SHA via shared fingerprint, single-source guard
  owns:
    - src/ai_hedge_fund/promotion/policy.py
    - config/promotion_policy.yaml
    - tests/promotion/test_policy.py
    - tests/unit/test_policy_sha_single_source.py
  reads: [src/ai_hedge_fund/policy_sha.py, src/ai_hedge_fund/promotion/records.py]
  depends: [T0]
- id: T2
  title: pure metrics -- observation returns, Sharpe, max drawdown, hit rate, paper-days
  owns: [src/ai_hedge_fund/promotion/metrics.py, tests/promotion/test_metrics.py]
  reads: [src/ai_hedge_fund/promotion/records.py]
  depends: [T0]
- id: T3
  title: point-in-time track-record loader and gate candidates
  owns: [src/ai_hedge_fund/promotion/inputs.py, tests/promotion/test_inputs.py]
  reads: [src/ai_hedge_fund/promotion/records.py, src/ai_hedge_fund/db/models.py, tests/promotion/seed.py]
  depends: [T0]
- id: T4
  title: pure verdict function and the no-LLM import guard
  owns:
    - src/ai_hedge_fund/promotion/gate.py
    - tests/promotion/test_gate.py
    - tests/promotion/test_no_llm.py
  reads: [src/ai_hedge_fund/promotion/records.py]
  depends: [T0]
- id: T5
  title: append-only decision store and latest-wins query
  owns: [src/ai_hedge_fund/promotion/store.py, tests/promotion/test_store.py]
  reads: [src/ai_hedge_fund/promotion/records.py, src/ai_hedge_fund/db/models.py, tests/promotion/seed.py]
  depends: [T0]
- id: T6
  title: rationale-only Haiku agent
  owns: [src/ai_hedge_fund/agents/promotion_rationale.py, tests/unit/test_promotion_rationale_agent.py]
  reads: [src/ai_hedge_fund/agents/risk_manager.py, src/ai_hedge_fund/agents/base.py, src/ai_hedge_fund/promotion/records.py]
  depends: [T0]
- id: T7
  title: promotion StateGraph -- load, metrics, decide, explain, persist
  owns: [src/ai_hedge_fund/promotion/graph.py, tests/promotion/test_graph.py]
  reads:
    - src/ai_hedge_fund/promotion/state.py
    - src/ai_hedge_fund/promotion/policy.py
    - src/ai_hedge_fund/promotion/metrics.py
    - src/ai_hedge_fund/promotion/inputs.py
    - src/ai_hedge_fund/promotion/gate.py
    - src/ai_hedge_fund/promotion/store.py
    - src/ai_hedge_fund/agents/promotion_rationale.py
  depends: [T1, T2, T3, T4, T5, T6]
- id: T8
  title: promotion_gate CLI entry point plus end-to-end three-way SHA / replay / re-decide tests
  owns:
    - src/ai_hedge_fund/scripts/promotion_gate.py
    - tests/scripts/test_promotion_gate.py
    - tests/integration/test_phase12_promotion_sha_linkage.py
  reads: [src/ai_hedge_fund/promotion/graph.py, src/ai_hedge_fund/scripts/mark_to_market.py]
  depends: [T7]
- id: T10
  title: audit_reconstruct includes promotion decisions
  owns: [src/ai_hedge_fund/scripts/audit_reconstruct.py, tests/output/test_audit_reconstruct.py]
  reads: [src/ai_hedge_fund/promotion/store.py]
  depends: [T5]
- id: T11
  title: retention purge skips referenced signal rows (D12, own commit)
  owns: [src/ai_hedge_fund/scripts/purge_expired_episodic.py, tests/memory/test_episodic_retention.py]
  reads: [src/ai_hedge_fund/db/models.py, tests/promotion/seed.py]
  depends: [T0]
```

Per-task notes:

- **T0** -- Rebase on main after PR #8 merges (D2) before writing anything. RED first:
  `test_migration_009.py` checks ORM/migration parity (CHECKs and widths), the `record_type` and
  verdict CHECKs, and the PG width of `'eligible-for-live'`, the trigger and the downgrade (the
  downgrade keeps `paper_append_only_guard()`). Bump `HEAD = "009"`. `tests/promotion/seed.py`
  (a plain module, not a conftest) builds analysis row -> submitted trade -> fills -> pnl rows
  through the real `insert_paper_fill` / `mtm.store.insert_pnl_rows`, with explicit
  `observed_date`. It is a test fixture only, never production data. The `db/models.py`
  docstring lists `'promotion'` for the new table only; `episodic_memory.record_type` is untouched.
- **T1** -- `test_missing_threshold_rejected` is parametrized over all 7 fields. Also covered:
  YAML with an unknown key, `min_sharpe` as a string, `max_drawdown: 1.5`, and an empty file.
  `test_sha_delegates_to_shared_fingerprint` monkeypatches `policy_sha.fingerprint` and asserts
  it is the call. The single-source guard scans `src/` for `hashlib.sha256`, allowlisting
  `policy_sha.py` and `execution/submit.py` (order-id tag).
- **T2** -- Hand-computed series: a flat series (Sharpe `None`), one observation, a gap day as
  one observation (not zero-filled), capital added mid-track, a monotonic rise (drawdown 0), and a
  known peak-trough-recovery series. No floats from money: all inputs are `int` cents.
- **T3** -- FUTUREX: a `pnl_date=2099-01-01` row and a row with `observed_date` after the cutoff
  are both excluded. Fills filled after `as_of` are excluded from `invested`. A non-`analysis` id
  raises `UnknownSignal`.
- **T4** -- A table test over D9 rules 1-6, inclusive bounds at exact threshold values, and
  multiple failing reasons listed together. The no-LLM guard (AST imports, like
  `tests/mtm/test_no_llm.py`) covers `metrics, gate, policy, inputs, store, records`.
- **T7** -- The explain node receives adversarial `TestModel` output (prose claiming "eligible").
  The verdict, metrics and SHA in state stay equal to their values before explain. The graph
  loads the policy once per run. A persist failure raises and writes nothing partial.
- **T8** -- Drive `_main` in-process and one subprocess `--help` (real entry point). `--json`
  stdout is pure JSON even when logging. A signal with no rows gets `paper-only`, not an error.
  `--with-rationale` off means zero model requests.
- **T8 (end-to-end file)** -- `state["promotion_policy_sha"] == row.promotion_policy_sha ==
  output.promotion_policy_sha == compute_promotion_policy_sha(load_promotion_policy())`. Replay:
  rebuild the track record from the payload's stored ids and cutoff, and `decide` returns the
  stored verdict. Re-decide: the first row is byte-identical after a second run.

## Pre-mortem

Premise: three months on, this phase shipped and something traces back here.
Severity: **C** corrupts data or sends an order that shouldn't exist; **H** silent wrong
behaviour; **M** loud failure.

```yaml phase-premortem
- id: PM1
  severity: C
  failure: the LLM rationale (or a prompt-injected ticker/news string) flips a verdict to eligible-for-live
  invariant: PROMO-03 -- verdict is set only by gate.decide; the explain node may write rationale keys only
  test:
    - tests/promotion/test_graph.py::test_rationale_cannot_change_verdict
    - tests/promotion/test_graph.py::test_explain_node_extra_key_raises
- id: PM2
  severity: C
  failure: re-running the gate UPDATEs the previous decision row instead of appending
  invariant: PROMO-05 -- promotion_decisions is append-only at ORM and database level
  test:
    - tests/promotion/test_store.py::test_redecide_leaves_prior_row_byte_identical
    - tests/promotion/test_store.py::test_orm_update_and_delete_rejected
    - tests/promotion/test_migration_009.py::test_pg_trigger_rejects_update_and_delete
- id: PM3
  severity: H
  failure: someone adds a third hand-rolled canonical-JSON SHA and it drifts (e.g. sort_keys dropped)
  invariant: PROMO-02 -- every policy SHA comes from policy_sha.fingerprint
  test:
    - tests/promotion/test_policy.py::test_sha_delegates_to_shared_fingerprint
    - tests/unit/test_policy_sha_single_source.py::test_only_policy_sha_module_hashes_policies
- id: PM4
  severity: H
  failure: the SHA in the row differs from the one in the JSON output or graph state (policy reloaded mid-run, or file edited during a batch)
  invariant: PROMO-04 -- state == column == payload == recomputed, byte-for-byte
  test:
    - tests/integration/test_phase12_promotion_sha_linkage.py::test_three_way_sha_equality
    - tests/promotion/test_graph.py::test_policy_loaded_once_per_run
- id: PM5
  severity: C
  failure: a policy YAML missing min_sharpe loads with a silent default and the gate promotes on fewer checks
  invariant: PROMO-01 -- every threshold required, unknown keys rejected
  test:
    - tests/promotion/test_policy.py::test_missing_threshold_rejected
    - tests/promotion/test_policy.py::test_unknown_key_rejected
    - tests/promotion/test_policy.py::test_repo_policy_file_loads
- id: PM6
  severity: H
  failure: a future-dated (FUTUREX 2099) row or a mark written after the run started leaks into the track record
  invariant: temporal correctness -- pnl_date <= as_of and observed_date <= observed_cutoff
  test:
    - tests/promotion/test_inputs.py::test_futurex_row_excluded
    - tests/promotion/test_inputs.py::test_rows_observed_after_cutoff_excluded
    - tests/promotion/test_inputs.py::test_fills_after_as_of_not_invested
- id: PM7
  severity: H
  failure: zero-variance or single-observation track record yields Sharpe inf/NaN and passes the gate
  invariant: undefined metrics never produce eligible-for-live
  test:
    - tests/promotion/test_metrics.py::test_sharpe_undefined_for_zero_variance_or_one_observation
    - tests/promotion/test_gate.py::test_undefined_sharpe_is_paper_only
- id: PM8
  severity: H
  failure: a skipped mark day is zero-filled, inflating sample size and deflating volatility
  invariant: missing is not zero -- a gap is one multi-day observation (D6)
  test: tests/promotion/test_metrics.py::test_gap_day_is_one_observation_not_zero_fill
- id: PM9
  severity: H
  failure: capital added by a second fill is counted as a positive return
  invariant: D6 -- returns are P&L deltas over sleeve equity; invested capital is not return
  test: tests/promotion/test_metrics.py::test_added_capital_not_counted_as_return
- id: PM10
  severity: H
  failure: drawdown computed on P&L cents (not equity) or with the wrong sign reports 0 for a losing position
  invariant: D6 -- drawdown is peak-to-trough on invested + total P&L, as a fraction 0..1
  test: tests/promotion/test_metrics.py::test_max_drawdown_known_series
- id: PM11
  severity: H
  failure: a thin track record is labelled rejected (or eligible) instead of paper-only
  invariant: D9 -- below minimum paper-days/sample is paper-only unless the drawdown limit is breached
  test:
    - tests/promotion/test_gate.py::test_verdict_table
    - tests/promotion/test_gate.py::test_insufficient_sample_is_paper_only
    - tests/promotion/test_gate.py::test_drawdown_breach_rejects_before_minimums
- id: PM12
  severity: H
  failure: a metric exactly at the threshold flips verdict depending on float rounding or < vs <=
  invariant: D9 -- bounds are inclusive and tested at the exact value
  test: tests/promotion/test_gate.py::test_thresholds_are_inclusive
- id: PM13
  severity: H
  failure: the verdict path imports pydantic_ai/agents, so an LLM can creep into the numbers
  invariant: tool-first -- metrics/gate/policy/inputs/store/records have no LLM surface
  test: tests/promotion/test_no_llm.py::test_verdict_path_has_no_llm_surface
- id: PM14
  severity: M
  failure: an Anthropic outage or token-cap hit aborts the run and no decision is recorded
  invariant: D10 -- LLM failure degrades to rationale=None, rationale_status=failed; verdict still persisted
  test: tests/promotion/test_graph.py::test_rationale_failure_still_records_verdict
- id: PM15
  severity: M
  failure: a daily cron silently pays for an LLM call per signal
  invariant: D10 -- rationale is opt-in; default run makes zero model requests
  test: tests/scripts/test_promotion_gate.py::test_rationale_off_by_default_makes_no_llm_call
- id: PM16
  severity: M
  failure: the CLI wrapper breaks (import error, log line on stdout) while inner-function tests stay green
  invariant: the real entry point is exercised and --json stdout is pure JSON
  test:
    - tests/scripts/test_promotion_gate.py::test_module_entry_point_runs
    - tests/scripts/test_promotion_gate.py::test_json_stdout_is_pure_json
    - tests/scripts/test_promotion_gate.py::test_future_as_of_exits_three
- id: PM17
  severity: M
  failure: one signal with no marks aborts a --all batch
  invariant: D9 rule 1 -- no track record is a paper-only verdict, not an error
  test: tests/scripts/test_promotion_gate.py::test_signal_without_rows_is_paper_only_not_error
- id: PM18
  severity: M
  failure: the eligible-for-live verdict (17 chars) or a malformed SHA overflows or escapes a column on Postgres though SQLite accepted it
  invariant: column widths and CHECKs hold on Postgres (Phase 10 VARCHAR precedent)
  test:
    - tests/promotion/test_migration_009.py::test_pg_verdict_width_and_checks
    - tests/promotion/test_migration_009.py::test_record_type_check_rejects_other_values
- id: PM19
  severity: M
  failure: migration 009 drifts from the ORM, or its downgrade drops the shared guard function and unguards paper tables
  invariant: linear chain, exact ORM parity, shared trigger function survives downgrade
  test:
    - tests/promotion/test_migration_009.py::test_orm_matches_migration
    - tests/promotion/test_migration_009.py::test_pg_downgrade_009_keeps_shared_guard_function
    - tests/db/test_migration_chain.py::test_sqlite_head_matches_orm_exactly
    - tests/db/test_migration_chain.py::test_chain_is_linear_from_001_to_head
- id: PM20
  severity: H
  failure: a stored decision cannot be reproduced later (inputs not recorded), so the audit chain is repudiable
  invariant: D11 -- payload holds row ids, fill ids, cutoff and policy; replay returns the stored verdict
  test:
    - tests/integration/test_phase12_promotion_sha_linkage.py::test_stored_decision_replays_to_same_verdict
    - tests/output/test_audit_reconstruct.py::test_includes_promotion_decisions_latest_last
- id: PM21
  severity: H
  failure: the current verdict is read by as_of or observed_date instead of id, so an older re-run shadows the newest decision
  invariant: latest decision per signal is the highest id (same rule as reviews)
  test: tests/promotion/test_store.py::test_latest_decision_is_highest_id
- id: PM22
  severity: M
  failure: the retention purge hits an FK on a traded 90-day-old signal and the whole sweep fails (or, if FKs were off, orphans the promotion history)
  invariant: D12 -- rows referenced by paper or promotion tables are never purged; unreferenced expired rows still are
  test:
    - tests/memory/test_episodic_retention.py::test_purge_keeps_rows_referenced_by_paper_and_promotion_tables
    - tests/memory/test_episodic_retention.py::test_purge_still_deletes_unreferenced_expired_rows
```

## Out of scope

- Cohort / strategy-level promotion and cross-signal hit rate (D3; Phase 13 report or v1.2).
- Any live-capital order path; `eligible-for-live` is advisory (REQUIREMENTS: live execution deferred).
- An exit policy (realised P&L); metrics run on mostly-unrealised P&L until one exists (11-PLAN D5).
- A risk-free rate from FRED (D7 option b), and an exchange calendar (TECH-DEBT, Phase 11).
- Deriving thresholds from an in-sample backtest (v1.1 open question 2; D8 ships literature defaults).
- Scheduling the gate (PAPER-03 scheduler).
- Guarding `episodic_memory` itself (TECH-DEBT v1.2).
