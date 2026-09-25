---
phase: 11
slug: mark-to-market
title: Mark-to-Market and Attribution
doc: spec
companion_docs: [11-PLAN.md, 11-PREMORTEM.md]
written: 2026-09-25
status: signed-off (A1, A2 approved 2026-09-25)
---

# Phase 11 -- Spec

Concrete interfaces for every task in `11-PLAN.md`. Money is integer cents everywhere; the only
non-integer arithmetic is `Decimal`, rounded once, half-even. Every timestamp is tz-aware UTC;
"trading day" means the `America/New_York` calendar date.

---

## Amendments to the plan found while specifying (sign-off needed)

**A1 -- D4 is replaced: mark at raw `close_cents`, dividends as broker cash events.**
The plan's formula (`fill_price * adj_close[t] / adj_close[fill_date]`) does not work with this
database. `store_prices` (`data/tools/price_tools.py`) inserts with `ON CONFLICT DO NOTHING`, so each
`daily_prices` row keeps the adjustment factor *of the day it was downloaded*. The adj_close for the
fill date and for `t` come from different downloads, and the dividend between them is never in the
ratio. Recomputing from a fresh download would mean a live, non-reproducible input.

Replacement: this is an *accounting* P&L for a broker account, so it uses the broker's own numbers.
- Unrealized = `open_qty * close_cents[t] - open_cost_cents` (raw close, FIFO lots at fill price).
- Dividends are **realized income**, taken from Alpaca `DIV*` account activities (the cash the
  account actually got), stored append-only in `paper_cash_events`.
- `SPLIT`, `SPIN`, `MA`, `NC` activities are stored too, but this phase doesn't apply them: a signal
  whose ticker has one after its first fill is skipped with `skipped_corporate_action` (logged,
  no row). Applying them is TECH-DEBT.

CLAUDE.md's "always use adjusted close for return calculations" still governs *return series*
(Phase 12's Sharpe is computed from these cumulative P&L rows, which already include dividends, so
it doesn't need adjusted prices). Recorded as a deliberate exception in `11-SUMMARY.md`.

**A2 -- Analyst "direction" is derived; the analyst schemas have none.**
`FundamentalAnalysis` / `TechnicalAnalysis` carry `bull_factors` / `bear_factors`;
`SentimentAnalysis` carries `composite_score` in `[-1, 1]`. None has a direction field. Stance
rule (pure, in `mtm/attribution.py`, thresholds in `mtm_policy.yaml`):
- fundamental, technical: `bull` if `len(bull_factors) > len(bear_factors)`, `bear` if `<`,
  else `neutral`.
- sentiment: `bull` if `composite_score >= +sentiment_threshold` (default 0.2), `bear` if
  `<= -sentiment_threshold`, else `neutral`.
- An analyst with `error` set, or missing from the payload, is `absent`.
An analyst is credited when its stance equals the executed side (`buy` -> `bull`). The stance is
computed at *store* time (T2) and persisted, so a later rule change can't rewrite history; the
rule's version is part of `mtm_policy_sha`.

---

## 1. `config/mtm_policy.yaml` + `mtm/policy.py` (T1)

```yaml
conviction_buckets:          # contiguous, non-overlapping, cover 0..100
  - {name: low,    min: 0,  max: 49}
  - {name: medium, min: 50, max: 74}
  - {name: high,   min: 75, max: 100}
sentiment_threshold: 0.2     # A2
stance_rule_version: 1       # bump when the A2 rule changes
market_close_buffer_minutes: 30   # D6: today is "complete" at 16:00 ET + buffer
```

```python
class ConvictionBucket(BaseModel):  # frozen, extra=forbid
    name: str = Field(min_length=1, max_length=16)
    min: int = Field(ge=0, le=100, strict=True)
    max: int = Field(ge=0, le=100, strict=True)

class MtmPolicy(BaseModel):  # frozen, extra=forbid
    conviction_buckets: tuple[ConvictionBucket, ...] = Field(min_length=1)
    sentiment_threshold: float = Field(gt=0, lt=1)
    stance_rule_version: int = Field(ge=1, strict=True)
    market_close_buffer_minutes: int = Field(ge=0, le=240, strict=True)
    # validator: sorted by min, first.min == 0, last.max == 100, each min == prev.max + 1,
    # names unique; otherwise ValueError naming the offending bucket.

    def bucket_for(self, conviction: int) -> str: ...

DEFAULT_MTM_POLICY_PATH = Path("config/mtm_policy.yaml")
def load_mtm_policy(path: Path | str = DEFAULT_MTM_POLICY_PATH) -> MtmPolicy: ...  # safe_load
def compute_mtm_policy_sha(policy: MtmPolicy) -> str: ...  # policy_sha.fingerprint
```

## 2. Attribution inputs at store time (T2, D2 + A2)

`episodic_store_node` (`graph/nodes.py`) writes `payload.schema_version = 2` and adds:

```python
"analyst_stances": {          # A2, computed by mtm.attribution.derive_stances(state["analyst_reports"], policy)
    "fundamental": "bull" | "bear" | "neutral" | "absent",
    "sentiment":   ...,
    "technical":   ...,
},
"debate": {                   # None when the run had no debate (Phase-4 pipeline)
    "pre_debate_confidence": int,
    "post_debate_confidence": int,
    "quality_score": int,
} | None,
"mtm_policy_sha": str,        # the stance rule that produced analyst_stances
```

The node loads `MtmPolicy` through its existing deps; `derive_stances` is pure and lives in `mtm/`
so the graph imports `mtm`, never the reverse. Fields already in the payload are unchanged. Readers
must accept v1 and v2 (`recall.py` returns `payload` verbatim; no change there).

## 3. Migration 007 (T3)

`alembic/versions/007_create_paper_pnl_daily.py`, `down_revision = "006"`. Creates two tables, both
with `AppendOnlyGuard` on the ORM and the migration-004 PG trigger (DDL copied, not imported, as in 004).

```text
paper_cash_events
  id                 Integer PK
  broker_activity_id String(64)  NOT NULL  UNIQUE uq_paper_cash_events_activity
  activity_type      String(8)   NOT NULL  CHECK IN ('DIV','DIVCGL','DIVCGS','DIVNRA','DIVROC',
                                                     'DIVTXEX','DIVWH','SPLIT','SPIN','MA','NC')
  ticker             String(10)  NOT NULL
  event_date         Date        NOT NULL                 -- broker's activity date
  net_amount_cents   BigInteger  NOT NULL                 -- signed; 0 for non-cash actions
  payload            JSON(B)     NOT NULL                 -- redacted raw activity
  as_of_date, observed_date      (DualTimestampMixin)
  INDEX ix_paper_cash_events_ticker_date (ticker, event_date)

paper_pnl_daily
  id                    Integer PK
  signal_id             Integer FK episodic_memory.id NOT NULL
  pnl_date              Date        NOT NULL
  ticker                String(10)  NOT NULL
  open_qty              Integer     NOT NULL  CHECK >= 0
  open_cost_cents       BigInteger  NOT NULL  CHECK >= 0
  mark_close_cents      BigInteger  NOT NULL  CHECK > 0
  price_source          String(20)  NOT NULL
  realized_pnl_cents    BigInteger  NOT NULL   -- cumulative since first fill: FIFO sells + dividends
  unrealized_pnl_cents  BigInteger  NOT NULL
  total_pnl_cents       BigInteger  NOT NULL
      CHECK ck_paper_pnl_daily_total: total_pnl_cents = realized_pnl_cents + unrealized_pnl_cents
  attribution           JSON(B)     NOT NULL   -- section 5
  mtm_policy_sha        String(64)  NOT NULL
  payload               JSON(B)     NOT NULL   -- inputs: fill ids, cash-event ids, price row id
  as_of_date, observed_date         (as_of_date = pnl_date 00:00 UTC via normalise_as_of)
  UNIQUE uq_paper_pnl_daily_signal_date (signal_id, pnl_date)
  INDEX  ix_paper_pnl_daily_date (pnl_date)
```

Values are **cumulative**, not daily deltas: a daily delta depends on the previous row existing, and
a row written before a gap was filled could never be fixed. Deltas are derived in the rollup.
`downgrade()` drops both triggers (PG) and both tables. `004`'s docstring correction is T0.

Records (`mtm/records.py`): `NewPnlRow`, `PnlRowRecord`, `NewCashEvent`, `CashEventRecord`, which
follow the `paper/records.py` pattern (frozen, `extra=forbid`, strict ints, secret-key check on `payload`).
Store (`mtm/store.py`): `insert_pnl_rows(session, rows) -> InsertResult(inserted: int, skipped_existing: int)`,
`insert_cash_event(session, new) -> CashEventRecord | None` (None on duplicate activity id).

## 4. Broker activities (T4, D1 + A1)

```python
# execution/broker.py
@dataclass(frozen=True)
class BrokerActivity:
    activity_id: str
    activity_type: str                  # FILL | DIV* | SPLIT | SPIN | MA | NC
    symbol: str
    occurred_at: datetime               # tz-aware UTC (FILL: transaction_time; others: date 00:00 NY -> UTC)
    broker_order_id: str | None         # FILL only
    side: Literal["buy", "sell"] | None # FILL only
    qty: int | None                     # FILL only; whole shares, else ValueError
    price_cents: int | None             # FILL only
    net_amount_cents: int | None        # non-FILL; Decimal(str(x)) * 100, half-even
    raw: dict[str, Any]                 # redacted

class BrokerClient(Protocol):
    ...  # existing three methods unchanged
    def list_activities(self, types: Sequence[str], since: date) -> list[BrokerActivity]: ...
```

`AlpacaPaperBroker.list_activities` calls `self._client.get("/account/activities", {"activity_types":
",".join(types), "after": since.isoformat(), "direction": "asc", "page_size": 100})`, following
`page_token` until a short page. alpaca-py 0.44.0 has the `TradeActivity` / `NonTradeActivity` models
but **no `TradingClient` method** for this endpoint, so it uses the SDK's `RESTClient.get` (same auth,
same paper-host guard, no new dependency). A fractional `qty` raises `FractionalQuantity` (whole-share
invariant, Phase 9 D3). Errors are classified by the existing `_classify_api_error`. `FakeBroker` gains
a `activities` list and returns the `since`/`types` slice.

`mtm/ingest.py`:
```python
@dataclass(frozen=True)
class IngestResult:
    fills_inserted: int; fills_skipped_duplicate: int; fills_skipped_unknown_order: int
    cash_inserted: int; cash_skipped_duplicate: int

def ingest_activities(session: Session, broker: BrokerClient, since: date) -> IngestResult: ...
```
FILL -> look up `paper_trades` by `broker_order_id` where `submit_status = 'submitted'`; not found ->
`fills_skipped_unknown_order` + `logger.warning("fill_unknown_order", ...)`; found ->
`insert_paper_fill` (duplicate id -> `skipped_duplicate`, caught via the store's unique-violation helper).
Fill `as_of_date` = NY trading date of `occurred_at`. Non-FILL -> `insert_cash_event` for any ticker
(filtering to our tickers happens in the job).

CLI `scripts/ingest_fills.py`: `--since YYYY-MM-DD` (required), `--database-url`, `--json`,
`broker_factory` / `session_factory` injection as in `submit_signal.py`. Exit 0 on success, 2 on
broker error, 1 on anything else.

## 5. P&L and attribution cores (T5, T6) -- pure, no I/O

```python
# mtm/pnl.py
@dataclass(frozen=True)
class Lot: fill_id: int; qty: int; price_cents: int; filled_at: datetime

@dataclass(frozen=True)
class PositionMark:
    open_qty: int; open_cost_cents: int
    realized_pnl_cents: int; unrealized_pnl_cents: int; total_pnl_cents: int
    fill_ids: tuple[int, ...]; cash_event_ids: tuple[int, ...]

def mark_position(fills: Sequence[FillIn], dividends: Sequence[CashIn],
                  close_cents: int, pnl_date: date) -> PositionMark: ...
```
- Inputs are filtered by the caller to `trading_date(filled_at) <= pnl_date` and
  `event_date <= pnl_date`; `mark_position` **re-asserts** this and raises `FutureInputError` (the
  temporal guard is enforced at two layers).
- FIFO in `(filled_at, fill_id)` order. A sell beyond open quantity raises `OversoldError`
  (long-only book; a short would mean corrupt data).
- Dividends are credited to a signal pro rata to its open quantity on the event date, across all
  signals holding that ticker (the broker pays the account, not the signal). Integer split with
  the remainder to the lowest `signal_id`; this lives in `mtm/job.py`, which has the cross-signal view.
- All values are ints; no float appears anywhere (tests assert types).

```python
# mtm/attribution.py
def derive_stances(analyst_reports: Sequence[dict], policy: MtmPolicy) -> dict[str, Stance]: ...  # A2
def debate_winner(debate: dict | None, side: Side) -> Literal["bull", "bear", "draw", "unattributed"]: ...
def attribution_for(analysis_payload: dict, confidence: int | None, side: Side,
                    policy: MtmPolicy) -> Attribution: ...

class Attribution(BaseModel):  # frozen; stored verbatim in paper_pnl_daily.attribution
    schema: Literal["v2", "unattributed"]
    credited_analysts: tuple[Literal["fundamental", "sentiment", "technical"], ...]  # () -> none_aligned
    debate_winner: Literal["bull", "bear", "draw", "unattributed"]
    conviction_bucket: str        # from episodic_memory.confidence; "unknown" if NULL
```
The debate rule is plan D3 (`delta` sign relative to the executed side). v1 payloads give
`schema="unattributed"`, `credited_analysts=()`, `debate_winner="unattributed"`, and a conviction
bucket is still derived because `confidence` exists in v1. `credited_analysts=()` on v1 rows rolls up to
`unattributed`, not `none_aligned`. The rollup tells them apart by `schema`.

## 6. EOD job (T7, D6)

```python
# mtm/job.py
@dataclass(frozen=True)
class JobResult:
    pnl_date: date; inserted: int; skipped_existing: int
    skipped_no_price: tuple[int, ...]; skipped_corporate_action: tuple[int, ...]

def run_mark_to_market(session: Session, pnl_date: date, policy: MtmPolicy,
                       *, now: datetime, dry_run: bool = False) -> JobResult: ...
```
1. **Completed-day guard:** `pnl_date` must be a weekday and `< trading_date(now)`, or equal to it
   with `now >= 16:00 ET + buffer`. Otherwise `IncompleteTradingDay` and no writes. (Holidays show up as
   `skipped_no_price`; no exchange calendar dependency.)
2. Signals in scope: distinct `paper_trades.signal_id` with `submit_status='submitted'` and at least one
   fill with trading date `<= pnl_date`.
3. Price: `close_cents` from `daily_prices` with `trade_date == pnl_date` **exactly** (a stale price must
   not be frozen as that day's mark), same tie rule as `execution/prices.py`, and `observed_date <= now`.
   Missing -> `skipped_no_price`.
4. Corporate action (`SPLIT|SPIN|MA|NC`) for the ticker with `event_date` in `(first_fill_date, pnl_date]`
   -> `skipped_corporate_action`.
5. Build every row in memory, then `insert_pnl_rows`: existing `(signal_id, pnl_date)` pairs are read
   first and skipped; the rest are inserted in one transaction. **No UPDATE is ever issued.** A race with a
   concurrent run hits the unique constraint, rolls back, and raises `ConcurrentRun`. It never partially writes.
6. `now` is injected (tests pin it); the CLI passes `datetime.now(UTC)`.

CLI `scripts/mark_to_market.py`: `--date YYYY-MM-DD` (default: last completed trading day),
`--policy`, `--database-url`, `--dry-run` (compute and print, write nothing), `--json`. Exit codes: 0 ok
(including all-skipped), 3 `IncompleteTradingDay`, 1 other.

## 7. Rollup (T8, D7)

```python
# mtm/rollup.py
Dimension = Literal["analyst", "debate_winner", "conviction_bucket"]

class AttributionReport(BaseModel):  # frozen
    start: date; end: date
    total_pnl_cents: int                       # sum over signals of latest-row-in-range total
    by_analyst: dict[str, int]                 # fundamental|sentiment|technical|none_aligned|unattributed
    by_debate_winner: dict[str, int]           # bull|bear|draw|unattributed
    by_conviction_bucket: dict[str, int]       # policy bucket names + "unknown"
    signals: int; mtm_policy_shas: tuple[str, ...]

def attribution_rollup(session: Session, start: date, end: date) -> AttributionReport: ...
```
P&L in range per signal = `total` of its last row with `pnl_date <= end` minus `total` of its last row
with `pnl_date < start` (0 if none). Analyst split is equal, integer, with the remainder assigned in the order
fundamental -> sentiment -> technical. **Invariant (asserted inside the function and by tests):** each of
the three dicts sums exactly to `total_pnl_cents`. A mismatch raises `AttributionInvariantError`; it is
never logged and returned.

## 8. Errors (`mtm/errors.py`)

`MtmError` base; `IncompleteTradingDay`, `FutureInputError`, `OversoldError`, `ConcurrentRun`,
`AttributionInvariantError`. `FractionalQuantity` goes in `execution/errors.py` next to the other broker errors.

## 9. Tests -> files (inputs to 11-PREMORTEM.md)

| Area | File |
|---|---|
| Policy | `tests/mtm/test_mtm_policy.py` |
| Stances + store v2 | `tests/mtm/test_stances.py`, `tests/graph/test_episodic_store_v2.py` |
| Migration 007 | `tests/mtm/test_migration_007.py` (round-trip, parity, CHECKs, unique, PG trigger `requires_db`) |
| Activities | `tests/execution/test_alpaca_activities.py` (SDK `get` mocked, paging, fractional), `tests/mtm/test_ingest.py` |
| P&L core | `tests/mtm/test_pnl.py` |
| Attribution | `tests/mtm/test_attribution.py` |
| Job | `tests/mtm/test_job.py` (incl. UPDATE counter via `before_cursor_execute`, byte-identical re-run) |
| Rollup | `tests/mtm/test_rollup.py` |
| No LLM | `tests/mtm/test_no_llm.py` |
| CLIs | `tests/scripts/test_ingest_fills.py`, `tests/scripts/test_mark_to_market.py` |
| Live | `tests/execution/test_alpaca_live.py::test_list_activities_roundtrip` (`@slow`, creds-gated) |

`hypothesis` is not a dev dependency; the sum invariants use parametrized table tests plus a seeded
`random.Random(11)` sweep, not a new dependency.
