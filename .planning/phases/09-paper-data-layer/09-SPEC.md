---
phase: 09
slug: paper-data-layer
status: implemented
delivered: 2026-09-22
written: 2026-09-22
---

# Phase 9 -- Spec

Concrete interfaces. Everything here is what the tests assert against. Conventions inherited from v1.0 and not restated: `Base` + `DualTimestampMixin` from `db/base.py`; money as `BigInteger` cents; `String(10)` tickers; `uq_<table>_<cols>` / `ix_<table>_<cols>` naming; JSON payload as `JSONB().with_variant(JSON, "sqlite")`; ORM only, never string-built SQL (T-07-01).

---

## 1. Schema (migration `004`)

### 1.1 `paper_trades` -- one row per order *intent* and its synchronous broker response

| column | type | constraints | meaning |
|---|---|---|---|
| `id` | Integer | PK | |
| `signal_id` | Integer | NOT NULL, FK `episodic_memory.id`, indexed | The `FinalSignalOutput.episodic_id` this order executes. PT-03. |
| `attempt_no` | Integer | NOT NULL, default 1, CHECK `>= 1` | Deliberate retry counter (D4). |
| `ticker` | String(10) | NOT NULL, indexed | Denormalized from the signal for join-free recall. Insert validates it equals the episodic row's ticker. |
| `side` | String(4) | NOT NULL, CHECK IN (`buy`, `sell`) | |
| `order_type` | String(6) | NOT NULL, CHECK IN (`market`, `limit`) | |
| `quantity` | Integer | NOT NULL, CHECK `> 0` | Whole shares (D3). |
| `limit_price_cents` | BigInteger | NULL; CHECK `(order_type = 'limit') = (limit_price_cents IS NOT NULL)` | Present iff limit order. |
| `submit_status` | String(12) | NOT NULL, CHECK IN (`submitted`, `rejected`, `refused_veto`) | Outcome of the synchronous submit call. Set once at insert. |
| `broker_order_id` | String(64) | NULL, UNIQUE; CHECK `(submit_status = 'submitted') = (broker_order_id IS NOT NULL)` | Present iff the broker accepted. |
| `risk_status_at_submit` | String(10) | NOT NULL | Snapshot of `risk_assessment.status` at submit time. Audit fact for EXEC-04; Phase 9 does not act on it. |
| `policy_sha` | String(64) | NOT NULL | Risk policy fingerprint carried from the signal. |
| `review_policy_sha` | String(64) | NOT NULL | Review policy fingerprint carried from the signal. |
| `as_of_date` | DateTime(tz) | NOT NULL | Business date of the signal (mixin). |
| `observed_date` | DateTime(tz) | NOT NULL, server_default now() | When the row was written (mixin). |
| `payload` | JSONB / JSON | NOT NULL | Full `FinalSignalOutput` snapshot + broker request/response dicts. |

Constraints: `uq_paper_trades_signal_attempt (signal_id, attempt_no)`, `uq_paper_trades_broker_order_id (broker_order_id)`.
Indexes: `ix_paper_trades_signal_id`, `ix_paper_trades_ticker_asof (ticker, as_of_date)`.

### 1.2 `paper_fills` -- one row per fill event from the broker

| column | type | constraints | meaning |
|---|---|---|---|
| `id` | Integer | PK | |
| `trade_id` | Integer | NOT NULL, FK `paper_trades.id`, indexed | PT-02. |
| `broker_fill_id` | String(64) | NOT NULL, UNIQUE | Dedupes repeated fill events from polling. |
| `filled_qty` | Integer | NOT NULL, CHECK `> 0` | |
| `fill_price_cents` | BigInteger | NOT NULL, CHECK `> 0` | |
| `filled_at` | DateTime(tz) | NOT NULL | Broker's fill timestamp. |
| `as_of_date` | DateTime(tz) | NOT NULL | Trade date of the fill (mixin). |
| `observed_date` | DateTime(tz) | NOT NULL, server_default now() | (mixin) |
| `payload` | JSONB / JSON | NOT NULL | Raw broker fill event. |

Constraints: `uq_paper_fills_broker_fill_id`. Indexes: `ix_paper_fills_trade_id`, `ix_paper_fills_asof (as_of_date)`.

### 1.3 Not created in this phase

`paper_pnl_daily` -- Phase 11, migration 005 (D1).

### 1.4 Migration file

`alembic/versions/004_create_paper_trading_tables.py`, `revision = "004"`, `down_revision = "003"`.

`upgrade()`: `op.create_table("paper_trades", ...)` with inline `sa.ForeignKeyConstraint`, `sa.CheckConstraint`, `sa.UniqueConstraint`; `op.create_table("paper_fills", ...)`; the four `op.create_index` calls; then, only when `op.get_bind().dialect.name == "postgresql"`:

```sql
CREATE FUNCTION paper_append_only_guard() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'append-only table %: % not permitted', TG_TABLE_NAME, TG_OP; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_paper_trades_append_only BEFORE UPDATE OR DELETE ON paper_trades
  FOR EACH ROW EXECUTE FUNCTION paper_append_only_guard();
CREATE TRIGGER trg_paper_fills_append_only  BEFORE UPDATE OR DELETE ON paper_fills
  FOR EACH ROW EXECUTE FUNCTION paper_append_only_guard();
```

`downgrade()`: drop the two triggers and the function (Postgres only), drop indexes, `op.drop_table("paper_fills")`, then `op.drop_table("paper_trades")` -- fills first because of the FK.

---

## 2. Database support modules (`src/ai_hedge_fund/db/`)

### 2.1 `db/__init__.py`

Gains two side-effect imports so listeners are registered whenever anything under `ai_hedge_fund.db` is imported -- which `tests/conftest.py` and every prod entry point already do via `db.models`:

```python
from ai_hedge_fund.db import append_only as _append_only  # noqa: F401  (registers Session listeners)
from ai_hedge_fund.db import sqlite_compat as _sqlite_compat  # noqa: F401  (registers Engine listener)
```

### 2.2 `db/sqlite_compat.py`

```python
@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    """SQLite ignores FOREIGN KEY unless the pragma is on, per connection."""
```
Applies only when `dbapi_connection` is a `sqlite3.Connection`. No-op on psycopg. Guard test: `PRAGMA foreign_keys` returns `1` on the fixture engine.

### 2.3 `db/append_only.py`

```python
class AppendOnlyViolation(RuntimeError):
    """Raised when an UPDATE or DELETE targets an append-only table."""
    def __init__(self, table: str, operation: Literal["UPDATE", "DELETE"]) -> None: ...

class AppendOnlyGuard:
    """Marker mixin. Models that inherit it are protected by the listeners below."""
    __append_only__: ClassVar[bool] = True

@event.listens_for(Session, "before_flush")
def _reject_orm_mutations(session, flush_context, instances) -> None:
    # for obj in session.dirty (that are actually modified) and session.deleted:
    #   if getattr(type(obj), "__append_only__", False): raise AppendOnlyViolation(...)

@event.listens_for(Session, "do_orm_execute")
def _reject_core_mutations(orm_execute_state) -> None:
    # if orm_execute_state.is_update or orm_execute_state.is_delete:
    #   mapper = orm_execute_state.bind_mapper
    #   if mapper is not None and getattr(mapper.class_, "__append_only__", False): raise ...
```

Coverage statement (goes in the module docstring, verbatim intent): L1 catches ORM attribute mutation and `session.delete()`. L2 catches `session.execute(update(Model))` / `delete(Model)`. Neither catches `session.execute(text("UPDATE paper_trades ..."))` -- only the Postgres trigger (L3) does. The codebase already forbids raw SQL (T-07-01); this is why.

`EpisodicMemory` and `PortfolioPosition` do **not** inherit `AppendOnlyGuard` in this phase. Test asserts `purge_expired_episodic`'s Core delete still works with the listeners registered.

### 2.4 `db/dates.py` (fix-as-you-find, D6b)

```python
def normalise_as_of(value: str | date | datetime) -> datetime: ...
```
Byte-for-byte the current `_normalise_as_of` body (naive -> UTC, date -> midnight UTC, str -> `fromisoformat`). `memory/episodic.py` and `risk/portfolio.py` replace their private copies with `from ai_hedge_fund.db.dates import normalise_as_of as _normalise_as_of`.

### 2.5 `db/base.py` (fix-as-you-find, D6a)

Delete `AppendOnlyMixin` and its docstring sentence. Nothing imports it.

### 2.6 `db/models.py` additions

```python
class PaperTrade(Base, DualTimestampMixin, AppendOnlyGuard):
    __tablename__ = "paper_trades"
    __table_args__ = (
        UniqueConstraint("signal_id", "attempt_no", name="uq_paper_trades_signal_attempt"),
        UniqueConstraint("broker_order_id", name="uq_paper_trades_broker_order_id"),
        CheckConstraint("attempt_no >= 1", name="ck_paper_trades_attempt_no"),
        CheckConstraint("quantity > 0", name="ck_paper_trades_quantity"),
        CheckConstraint("side IN ('buy','sell')", name="ck_paper_trades_side"),
        CheckConstraint("order_type IN ('market','limit')", name="ck_paper_trades_order_type"),
        CheckConstraint("submit_status IN ('submitted','rejected','refused_veto')", name="ck_paper_trades_submit_status"),
        CheckConstraint("(order_type = 'limit') = (limit_price_cents IS NOT NULL)", name="ck_paper_trades_limit_price"),
        CheckConstraint("(submit_status = 'submitted') = (broker_order_id IS NOT NULL)", name="ck_paper_trades_broker_id"),
        Index("ix_paper_trades_ticker_asof", "ticker", "as_of_date"),
    )
    # columns per §1.1; signal_id = mapped_column(ForeignKey("episodic_memory.id"), nullable=False, index=True)

class PaperFill(Base, DualTimestampMixin, AppendOnlyGuard):
    __tablename__ = "paper_fills"
    # columns + constraints per §1.2; trade_id = mapped_column(ForeignKey("paper_trades.id"), nullable=False, index=True)
```

The ORM definitions and migration 004 must produce identical DDL for these two tables; `test_migration_matches_models` enforces it.

---

## 3. Paper package (`src/ai_hedge_fund/paper/`)

Mirrors `memory/`: frozen read models + seeder in one module, query in another, so the temporal-filter contract can be imported without I/O.

### 3.1 `paper/errors.py`

```python
class PaperStoreError(Exception): ...
class SignalNotFound(PaperStoreError): ...         # no episodic row with that id
class SignalWrongRecordType(PaperStoreError): ...  # row exists but record_type != 'analysis'
class SignalTickerMismatch(PaperStoreError): ...   # new.ticker != episodic row's ticker
class AmbiguousSignal(PaperStoreError): ...        # seeder: >1 episodic rows match (ticker, as_of_date)
class DuplicateSubmission(PaperStoreError): ...    # uq_paper_trades_signal_attempt hit
class TradeNotFound(PaperStoreError): ...
class DuplicateFill(PaperStoreError): ...          # uq_paper_fills_broker_fill_id hit
```

### 3.2 `paper/records.py`

All four models: `model_config = ConfigDict(extra="forbid", frozen=True)`.

```python
class NewPaperTrade(BaseModel):
    signal_id: int = Field(ge=1)
    attempt_no: int = Field(default=1, ge=1)
    ticker: str = Field(min_length=1, max_length=10)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: int = Field(gt=0)                       # strict int: floats rejected
    limit_price_cents: int | None = Field(default=None, gt=0)
    submit_status: Literal["submitted", "rejected", "refused_veto"]
    broker_order_id: str | None = Field(default=None, max_length=64)
    risk_status_at_submit: str = Field(min_length=1, max_length=10)
    policy_sha: str = Field(min_length=64, max_length=64)
    review_policy_sha: str = Field(min_length=64, max_length=64)
    as_of_date: str | date | datetime
    payload: dict[str, Any]

    # model_validator(mode="after"):
    #   limit_price_cents present iff order_type == "limit"
    #   broker_order_id present iff submit_status == "submitted"
    #   no top-level payload key matches /(secret|api_key|token|password)/i  -> ValueError

class NewPaperFill(BaseModel):
    trade_id: int = Field(ge=1)
    broker_fill_id: str = Field(min_length=1, max_length=64)
    filled_qty: int = Field(gt=0)
    fill_price_cents: int = Field(gt=0)
    filled_at: datetime
    as_of_date: str | date | datetime
    payload: dict[str, Any]

class PaperTradeRecord(BaseModel):   # read view; every column of §1.1, dates as ISO-8601 str
class PaperFillRecord(BaseModel):    # read view; every column of §1.2
```

Pydantic's `int` in strict-enough mode: `quantity: int` must reject `10.5`; test asserts `ValidationError`. Use `Field(strict=True)` on the cents/qty fields if lax coercion lets a float through.

### 3.3 `paper/store.py`

```python
def insert_paper_trade(db_session: Session, new: NewPaperTrade) -> PaperTradeRecord:
    """Validate lineage, append one row, commit, return the frozen record.

    1. SELECT episodic_memory WHERE id = new.signal_id  -> SignalNotFound
    2. row.record_type != 'analysis'                     -> SignalWrongRecordType
    3. row.ticker != new.ticker                          -> SignalTickerMismatch
    4. session.add(PaperTrade(...)); session.commit()
       IntegrityError on uq_paper_trades_signal_attempt -> session.rollback(); raise DuplicateSubmission
       IntegrityError on uq_paper_trades_broker_order_id -> session.rollback(); raise DuplicateSubmission
       any other IntegrityError -> session.rollback(); re-raise
    5. return _to_trade_record(row)
    """

def insert_paper_fill(db_session: Session, new: NewPaperFill) -> PaperFillRecord:
    """SELECT paper_trades WHERE id = new.trade_id -> TradeNotFound; add; commit;
    IntegrityError on uq_paper_fills_broker_fill_id -> rollback; DuplicateFill."""
```

Contract: after any raised `PaperStoreError` the session is rolled back and immediately usable. Test proves it by performing a successful insert right after a `DuplicateSubmission`.

The FK is the mechanical existence check (with SQLite pragma on, and always on Postgres). Steps 1-3 exist to produce *typed* errors and to enforce the ticker/record_type invariants the FK cannot express.

### 3.4 `paper/recall.py`

```python
def query_paper_trades(
    db_session: Session, *, as_of_date: str | date | datetime,
    ticker: str | None = None, signal_id: int | None = None, limit: int = 50,
) -> list[PaperTradeRecord]:
    """Always filters PaperTrade.as_of_date <= normalise_as_of(as_of_date).
    Requires ticker or signal_id (ValueError otherwise -- Pitfall-8 DoS guard, same as memory.recall).
    Orders as_of_date DESC, id DESC. Bounded by limit."""

def query_paper_fills(
    db_session: Session, *, as_of_date: str | date | datetime,
    trade_id: int | None = None, limit: int = 200,
) -> list[PaperFillRecord]:
    """Same temporal filter. trade_id optional (fills are bounded by trade cardinality)."""
```

Boundary semantics: a row whose `as_of_date` equals the target **is** returned (`<=`, not `<`). Tested explicitly.

### 3.5 `paper/seed.py` (test fixtures only; not a CLI)

```python
def seed_paper_trades_from_csv(db_session: Session, csv_path: str | Path) -> int:
    """Header: signal_ticker,signal_as_of_date,attempt_no,ticker,side,order_type,quantity,
    limit_price_cents,submit_status,broker_order_id,risk_status_at_submit,policy_sha,
    review_policy_sha,as_of_date
    Resolves signal_id by exact (ticker, as_of_date, record_type='analysis') match:
    0 rows -> SignalNotFound; >1 rows -> AmbiguousSignal. Goes through insert_paper_trade
    so every seeded row passes the same validation as a real one."""

def seed_paper_fills_from_csv(db_session: Session, csv_path: str | Path) -> int:
    """Header: broker_order_id,broker_fill_id,filled_qty,fill_price_cents,filled_at,as_of_date
    Resolves trade_id by broker_order_id -> TradeNotFound."""
```

### 3.6 `paper/__init__.py`

Re-exports the four record types, two insert functions, two query functions, two seeders, and the error hierarchy.

---

## 4. Tests (`tests/paper/`)

```
tests/paper/
  __init__.py
  conftest.py                      seeded_signals (seeds tests/memory/fixtures/seeded_episodic.csv -> {ticker: id}),
                                   paper_trades_csv_path, paper_fills_csv_path
  fixtures/seeded_paper_trades.csv   >= 6 rows incl. FUTUREX @ 2099-01-01 (signal = existing FUTUREX episodic row),
                                     one 'rejected' row (no broker id), one 'refused_veto' row, one limit order,
                                     two attempts for one signal
  fixtures/seeded_paper_fills.csv    >= 4 rows incl. one FUTUREX fill @ 2099-01-01, partial fills for one trade
  test_models.py                   columns, NOT NULL, CHECKs, uniques, FK (+ pragma guard), timestamps
  test_append_only.py              L1 x2, L2 x2, exception message, listener registered, episodic delete unaffected
  test_migration_roundtrip.py      SQLite file-DB round-trip; compare_metadata; Postgres-gated @slow variants
  test_store.py                    every path in §3.3 incl. session-usable-after-error
  test_recall.py                   temporal filter, FUTUREX (PT-05), boundary, ordering, limit, DoS guard, naive/aware
  test_seed.py                     resolution, SignalNotFound, AmbiguousSignal, TradeNotFound, counts
```

Postgres-gated tests read `TEST_DATABASE_URL` from the environment; `pytest.skip` when unset. They are the only tests in the phase that need Docker.

---

## 5. Dialect notes

- `server_default=func.now()` renders as `CURRENT_TIMESTAMP` on SQLite and `now()` on Postgres. Both populate `observed_date`.
- SQLite stores `DateTime(timezone=True)` as naive text. `normalise_as_of` forces UTC on every comparison input so `<=` is stable on both dialects. Read models emit ISO-8601 strings, not datetimes, for the same reason (matches `EpisodicHit`).
- SQLite enforces CHECK constraints and UNIQUE constraints natively; FKs only with the pragma (§2.2).
- `compare_metadata` on SQLite reports spurious diffs for some type reflections; the test filters to the two paper tables and to diff kinds `add_table / remove_table / add_column / remove_column / add_index / remove_index / add_constraint / remove_constraint`. Type-modification diffs on SQLite are recorded, not asserted.
