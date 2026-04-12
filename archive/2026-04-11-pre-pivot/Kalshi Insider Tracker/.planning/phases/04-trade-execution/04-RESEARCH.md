# Phase 4: Trade Execution - Research

**Researched:** 2026-04-03
**Domain:** Automated order execution, risk management, signal deduplication (Kalshi prediction markets)
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Risk Guard limits ($50/trade, $500 total) MUST be code-level constants, NOT config values — this is a critical safety constraint from research
- Paper trading mode is the default — live mode requires explicit opt-in
- Signal deduplication: prevent same signal from triggering duplicate orders across consecutive polls
- In-flight order tracking: prevent re-submission while a prior order is pending
- All trade data (placed, blocked, simulated) persists to the Trade table (append-only)
- Signal log (LOG-01): every signal detection event logged to DB
- Trade log (LOG-02): every trade placed/blocked/simulated logged to DB
- Use kalshi-python SDK for order placement (KalshiClient already built in Phase 1)

### Claude's Discretion
All implementation choices are at Claude's discretion — infrastructure phase. The above constraints are the only locked decisions.

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXEC-01 | System operates in paper trading mode (simulated trades, no real capital) | PaperTradeExecutor logs Trade rows with mode='paper' and status='filled'; no Kalshi API call |
| EXEC-02 | System auto-executes real copy trades via Kalshi API when signals exceed threshold | LiveTradeExecutor calls PortfolioApi.create_order(); confidence threshold gate in TradeExecutor.execute() |
| EXEC-03 | System enforces $50 per-trade limit as a code-level constant (not config) | MAX_PER_TRADE_CENTS = 5_000 in risk_guard.py; asserted before every order |
| EXEC-04 | System enforces $500 total exposure limit as a code-level constant (not config) | MAX_TOTAL_EXPOSURE_CENTS = 50_000 in risk_guard.py; derived from DB query, not in-memory counter |
| EXEC-05 | System deduplicates signals to prevent duplicate orders from consecutive polls | RiskGuard checks Trade table for open/pending trade on same ticker before approving |
| EXEC-06 | System tracks in-flight orders to prevent race conditions between detection and execution | Trade row written with status='pending' before API call; RiskGuard rejects if pending row exists for ticker |
| LOG-01 | System logs every detected signal (market, type, confidence, timestamp) to database | Already handled by SignalEngine.run() in Phase 3 — Signal rows are appended on every detection |
| LOG-02 | System logs every trade placed (market, direction, size, price, outcome) to database | Trade row persisted for every execution outcome: placed, blocked, simulated |
</phase_requirements>

---

## Summary

Phase 4 builds the execution layer that sits between the SignalEngine (Phase 3) and the Kalshi API. The architecture is a three-component chain: **RiskGuard** → **TradeExecutor** (Paper or Live) → **Persistence**. The poller already calls `signal_engine.run()` per tick and collects `Signal` ORM rows; Phase 4 consumes those rows.

The kalshi-python SDK v2.1.4 (already installed in `.venv`) provides `PortfolioApi` with `create_order()`, `get_orders()`, `get_positions()`, and `get_balance()`. The `CreateOrderRequest` model has a `client_order_id` field — this is the correct idempotency mechanism for preventing duplicate live orders. Order status values are `resting | canceled | executed | pending`.

The `Trade` ORM model (Phase 1) already has all necessary columns: `ticker`, `signal_id`, `side`, `contracts`, `price_cents`, `mode` ('paper'|'live'), `status` ('pending'|'filled'|'rejected'), `placed_at`, and `kalshi_order_id`. No schema migration is needed.

**Primary recommendation:** Build a `TradeExecutor` class with paper/live mode switch, gates all orders through a `RiskGuard` that reads live exposure from DB (not an in-memory counter), and uses `client_order_id` = signal UUID for idempotent live order submission.

---

## Standard Stack

### Core (all already in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| kalshi-python | 2.1.4 (installed) | Order placement via PortfolioApi | Official SDK, handles RSA signing; `create_order()` is verified in installed SDK |
| SQLAlchemy | >=2.0.48 | DB reads for exposure calculation and Trade writes | Already project standard; append-only Trade table is Phase 1 |
| structlog | >=25.5.0 | Structured logging per order event | Project-wide standard; every order must log with ticker, mode, reason |
| tenacity | >=9.1.4 | Retry on network errors for live order placement | Project standard; retry 3x on exceptions; do NOT retry on Kalshi 4xx |

### Supporting (already in pyproject.toml)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uuid | stdlib | Generate `client_order_id` for idempotent submission | Every live order gets a deterministic UUID derived from signal.id |
| freezegun | >=1.5.5 | Time mocking in tests | For testing time-windowed dedup logic |
| pytest | >=9.0.2 | Test framework | Unit tests for RiskGuard and TradeExecutor; mock PortfolioApi |

### No New Dependencies Needed

Phase 4 requires zero new packages. All needed libraries are in pyproject.toml.

---

## Architecture Patterns

### Recommended Module Structure

```
src/kalshi_tracker/
├── execution/
│   ├── __init__.py
│   ├── risk_guard.py       # RiskGuard class — hard limits, dedup, in-flight checks
│   ├── executor.py         # TradeExecutor — paper/live dispatch
│   └── types.py            # ExecutionResult, ApprovalResult frozen dataclasses
tests/unit/execution/
│   ├── __init__.py
│   ├── test_risk_guard.py
│   └── test_executor.py
```

The poller already wires `signal_engine` via `make_poll_tick`. Phase 4 adds `trade_executor` as the third injectable dependency in `make_poll_tick`.

### Pattern 1: RiskGuard as a Hard Gate

**What:** Stateless function/class that reads from DB on every call; never caches exposure in memory.
**When to use:** Before every order — paper AND live.

```python
# Source: ARCHITECTURE.md Pattern 2 + verified SDK Order model

# risk_guard.py — hard limits as module constants (EXEC-03, EXEC-04)
MAX_PER_TRADE_CENTS: int = 5_000       # $50 — NOT from config
MAX_TOTAL_EXPOSURE_CENTS: int = 50_000  # $500 — NOT from config

@dataclass(frozen=True)
class ApprovalResult:
    approved: bool
    reason: str  # 'approved' | 'per_trade_cap' | 'total_exposure_cap' | 'in_flight' | 'duplicate'
    trade_cost_cents: int = 0

class RiskGuard:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def approve(self, signal: Signal) -> ApprovalResult:
        """Gate signal through risk checks. Reads live DB state — no in-memory counters."""
        # 1. Compute trade cost from signal price (yes_ask cents * contracts)
        trade_cost_cents = self._compute_cost(signal)

        # 2. Per-trade cap (EXEC-03)
        if trade_cost_cents > MAX_PER_TRADE_CENTS:
            return ApprovalResult(approved=False, reason="per_trade_cap")

        # 3. In-flight / duplicate check (EXEC-05, EXEC-06)
        with self._session_factory() as session:
            # Check for pending or recent filled trade on same ticker
            if self._has_in_flight(signal.ticker, session):
                return ApprovalResult(approved=False, reason="in_flight")

            # 4. Total exposure cap (EXEC-04) — query DB for current open exposure
            current_exposure = self._total_open_exposure(session)
            if current_exposure + trade_cost_cents > MAX_TOTAL_EXPOSURE_CENTS:
                return ApprovalResult(approved=False, reason="total_exposure_cap")

        return ApprovalResult(approved=True, reason="approved", trade_cost_cents=trade_cost_cents)
```

### Pattern 2: TradeExecutor with Paper/Live Dispatch

**What:** Single `TradeExecutor` class that dispatches to paper or live path based on mode setting.
**When to use:** Consume signals from SignalEngine after Risk Guard approval.

```python
# executor.py
class TradeExecutor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        risk_guard: RiskGuard,
        portfolio_api: PortfolioApi | None,  # None = paper mode (safe default)
        confidence_threshold: float = 0.6,
    ) -> None: ...

    def execute(self, signal: Signal) -> Trade | None:
        """Execute one signal: gate through RiskGuard, then paper or live path."""
        if signal.confidence < self.confidence_threshold:
            return None  # below threshold — not blocked, just not actionable

        approval = self._risk_guard.approve(signal)
        if not approval.approved:
            return self._persist_blocked(signal, approval.reason)  # LOG-02

        if self._portfolio_api is None:
            return self._execute_paper(signal, approval)  # EXEC-01
        else:
            return self._execute_live(signal, approval)   # EXEC-02
```

### Pattern 3: Write Pending Row Before API Call (EXEC-06)

**What:** Persist a `Trade` row with `status='pending'` BEFORE calling the Kalshi API. Update to 'filled' or 'rejected' after response. This makes in-flight tracking durable across crashes.

```python
def _execute_live(self, signal: Signal, approval: ApprovalResult) -> Trade:
    # Step 1: Write pending row to DB — in-flight guard (EXEC-06)
    pending_trade = Trade(
        ticker=signal.ticker,
        signal_id=signal.id,
        side=signal.direction,
        contracts=self._compute_contracts(approval.trade_cost_cents, price),
        price_cents=price,
        mode="live",
        status="pending",
        placed_at=datetime.now(UTC),
        kalshi_order_id=None,
    )
    with self._session_factory() as session:
        session.add(pending_trade)
        session.commit()

    # Step 2: Call Kalshi API (idempotent via client_order_id = str(signal.id))
    try:
        request = CreateOrderRequest(
            ticker=signal.ticker,
            client_order_id=str(signal.id),  # M-05 idempotency
            side=signal.direction,           # 'yes' | 'no'
            action="buy",
            count=pending_trade.contracts,
            type="limit",
            yes_price=price if signal.direction == "yes" else None,
            no_price=price if signal.direction == "no" else None,
        )
        response = self._portfolio_api.create_order(create_order_request=request)
        kalshi_order_id = response.order.order_id if response.order else None
        final_status = "filled"
    except Exception:
        kalshi_order_id = None
        final_status = "rejected"

    # Step 3: Append new row (append-only — no update) with final status
    filled_trade = Trade(
        ticker=pending_trade.ticker,
        signal_id=pending_trade.signal_id,
        side=pending_trade.side,
        contracts=pending_trade.contracts,
        price_cents=pending_trade.price_cents,
        mode="live",
        status=final_status,
        placed_at=pending_trade.placed_at,
        kalshi_order_id=kalshi_order_id,
    )
    with self._session_factory() as session:
        session.add(filled_trade)
        session.commit()
    return filled_trade
```

**Critical note:** The Trade table uses `AppendOnlyMixin` — rows are never updated. To record the outcome, write a SECOND row with the final status. The `_has_in_flight` check in RiskGuard looks for `status='pending'` rows in a narrow time window.

### Pattern 4: Poller Wiring — Add TradeExecutor as Third Injectable

The existing `make_poll_tick` factory accepts `signal_engine: SignalEngine | None`. Extend it with `trade_executor: TradeExecutor | None` following the same pattern:

```python
def make_poll_tick(
    client: KalshiClient,
    session_factory: sessionmaker[Session],
    warmup: WarmupTracker,
    signal_engine: SignalEngine | None = None,
    trade_executor: TradeExecutor | None = None,   # Phase 4 addition
) -> Callable[[], None]:
    def poll_tick() -> None:
        ...
        if signal_engine is not None:
            for snap in snapshots:
                signals = signal_engine.run(snap.ticker, ...)
                if trade_executor is not None:
                    for signal in signals:
                        trade_executor.execute(signal)
    return poll_tick
```

### Pattern 5: Exposure Calculation from DB (not in-memory)

Query the Trade table for all open positions to compute total exposure:

```python
def _total_open_exposure(self, session: Session) -> int:
    """Sum cost of all trades that are 'pending' or 'filled' with live mode.

    Reads from DB every time — no caching. This is the single source of truth.
    """
    rows = (
        session.query(Trade)
        .filter(
            Trade.mode == "live",
            Trade.status.in_(["pending", "filled"]),
        )
        .all()
    )
    return sum(t.contracts * t.price_cents for t in rows)
```

### Anti-Patterns to Avoid

- **In-memory exposure counter:** Using a module-level variable to track exposure. Crashes and restarts silently reset it to zero. Always derive from DB.
- **Updating Trade rows:** The Trade model uses AppendOnlyMixin. Write a new row for each status transition, never UPDATE an existing row.
- **Direct signal_engine → executor call (bypassing poller):** Bypasses the RiskGuard if called out of sequence. TradeExecutor should only be called from within poll_tick where signal.id is committed to DB.
- **Market orders for live execution:** Always use `type="limit"` with `yes_price` or `no_price`. Market orders cause slippage on thin politics markets.
- **Retrying on Kalshi 4xx:** Insufficient balance (402/400), market closed (400), invalid order (400) are logic errors. Only retry on 5xx or network exceptions.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Order placement + RSA signing | Custom httpx order client | `PortfolioApi.create_order()` from kalshi-python | SDK already handles RSA-PSS signing, pagination, typed request/response models |
| Idempotency key generation | Custom hash function | `str(signal.id)` as `client_order_id` | Signal.id is UUID (from AppendOnlyMixin); already unique per detection event |
| In-flight detection | Time-based cooldown timer | DB query for `status='pending'` Trade rows | Survives crashes; works across restarts; single source of truth |
| Exposure tracking | In-memory running total | DB query summing pending+filled Trade rows | Survives restarts; never drifts from true position state |

---

## SDK API Reference (Verified from Installed kalshi-python 2.1.4)

### CreateOrderRequest fields (all verified)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `ticker` | str | yes | Market ticker |
| `client_order_id` | str or None | no | Idempotency key — use `str(signal.id)` |
| `side` | 'yes' or 'no' | yes | Direction |
| `action` | 'buy' or 'sell' | yes | Always 'buy' for copy trades |
| `count` | int >= 1 | yes | Number of contracts |
| `type` | 'limit' or 'market' | yes | Always 'limit' (avoid slippage) |
| `yes_price` | int 1-99 | conditional | Required when side='yes'; cents |
| `no_price` | int 1-99 | conditional | Required when side='no'; cents |

### Order status values (verified from Order model enum)

`resting` | `canceled` | `executed` | `pending`

Map to Trade.status: `pending` → pending, `executed` → filled, `canceled`/other → rejected.

### PortfolioApi methods available

| Method | Purpose |
|--------|---------|
| `create_order()` | Place order; returns `CreateOrderResponse` with `.order.order_id` |
| `get_orders()` | List open/resting orders |
| `get_positions()` | Get current positions (returns `GetPositionsResponse` with `.positions` list) |
| `get_balance()` | Account balance in cents (`GetBalanceResponse.balance`) |

---

## LOG-01 Status: Already Complete

`LOG-01` (log every detected signal to DB) is **already implemented** by `SignalEngine.run()` in Phase 3. The Signal ORM row is persisted before `execute()` is called. Phase 4 only needs to implement LOG-02 (trade logging).

---

## Common Pitfalls

### Pitfall 1: AppendOnlyMixin Prevents Trade Row Updates
**What goes wrong:** Developer calls `session.query(Trade).filter(...).first()` then modifies `trade.status = "filled"`. SQLAlchemy allows the attribute assignment but the `AppendOnlyMixin` convention requires writing a new row instead.
**Why it happens:** The mixin doesn't enforce this at the database level — it's a project convention.
**How to avoid:** Never modify a fetched Trade row. For each status transition, insert a new Trade row with the new status. Document in docstring.
**Warning signs:** Flaky tests where a Trade row's status unexpectedly changes.

### Pitfall 2: RiskGuard Exposure Calculation Includes Paper Trades
**What goes wrong:** `_total_open_exposure` sums ALL trades including `mode='paper'`. Paper trades don't represent real capital at risk, so this over-counts exposure and unnecessarily blocks live trades.
**How to avoid:** Filter `Trade.mode == "live"` in the exposure query.

### Pitfall 3: Pending Trade from Previous Crash Blocks All Execution
**What goes wrong:** System crashes mid-order, leaving a `status='pending'` Trade row. On restart, `_has_in_flight` sees it and blocks all new orders for that ticker indefinitely.
**How to avoid:** Add a time-window to the in-flight check — only treat trades as in-flight if `placed_at > (now - 60 seconds)`. Stale pending rows beyond 60s are treated as timed out.

### Pitfall 4: Confidence Threshold Not Applied Before RiskGuard
**What goes wrong:** Low-confidence signals (below the EXEC-02 threshold) reach RiskGuard and get logged as "blocked" rather than simply "below threshold." This pollutes the blocked-trade log.
**How to avoid:** Apply confidence threshold check BEFORE calling `risk_guard.approve()`. Return `None` (not a blocked Trade row) for sub-threshold signals.

### Pitfall 5: Paper Mode Uses yes_ask Price, Live Mode Uses a Different Price
**What goes wrong:** Paper mode records the price at detection time. Live mode fills at the actual order book price. For reporting consistency, both should record the same reference price (yes_ask at time of signal detection), with the understanding that live fills may differ.
**How to avoid:** Compute `price_cents` once from `signal.details` (recorded by SignalEngine) and use the same value for both paper and live Trade rows.

---

## Code Examples

### Blocking a Trade (LOG-02 — rejected path)

```python
# Source: verified Trade model from models.py
def _persist_blocked(self, signal: Signal, reason: str) -> Trade:
    """Write a Trade row with status='rejected' for Risk Guard blocks (LOG-02)."""
    trade = Trade(
        ticker=signal.ticker,
        signal_id=signal.id,
        side=signal.details.get("direction", "yes"),
        contracts=0,
        price_cents=signal.details.get("current_price", 0),
        mode="live" if self._portfolio_api else "paper",
        status="rejected",
        placed_at=datetime.now(UTC),
        kalshi_order_id=None,
    )
    with self._session_factory() as session:
        session.add(trade)
        session.commit()
    return trade
```

### Testing RiskGuard with Mock Session

Following the established mock_session pattern from `tests/unit/signals/conftest.py`:

```python
# tests/unit/execution/conftest.py
@pytest.fixture
def mock_session_factory():
    """Return a mock session factory for RiskGuard tests."""
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    session.query.return_value.filter.return_value.all.return_value = []
    factory = MagicMock(return_value=session)
    factory.return_value.__enter__ = MagicMock(return_value=session)
    factory.return_value.__exit__ = MagicMock(return_value=False)
    return factory, session
```

### Wiring to poller (make_poll_tick extension)

```python
# Extended make_poll_tick signature — Phase 4 adds trade_executor param
def make_poll_tick(
    client: KalshiClient,
    session_factory: sessionmaker[Session],
    warmup: WarmupTracker,
    signal_engine: SignalEngine | None = None,
    trade_executor: "TradeExecutor | None" = None,  # TYPE_CHECKING guard same as signal_engine
) -> Callable[[], None]:
```

---

## Environment Availability

All required tools and dependencies are already installed. No new packages needed.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| kalshi-python | EXEC-02 order placement | Yes | 2.1.4 | Paper mode (EXEC-01) |
| SQLAlchemy | Risk Guard DB reads | Yes | 2.0.48+ | — |
| PostgreSQL | Trade persistence | Existing project DB | — | — |
| PortfolioApi | EXEC-02 live orders | Yes (in installed SDK) | 2.1.4 | — |

**Step 2.6: No blocking missing dependencies.** Paper mode (EXEC-01) is the default and requires only DB access. Live mode (EXEC-02) requires a real Kalshi API key which is already handled by KalshiSettings.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2+ |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/execution/ -x` |
| Full suite command | `uv run pytest tests/ -m "not integration"` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXEC-01 | Paper trade writes Trade row with mode='paper', status='filled', no API call | unit | `pytest tests/unit/execution/test_executor.py::test_paper_trade_writes_row -x` | Wave 0 |
| EXEC-02 | Live trade calls PortfolioApi.create_order() with correct params | unit | `pytest tests/unit/execution/test_executor.py::test_live_trade_calls_api -x` | Wave 0 |
| EXEC-03 | RiskGuard rejects signal costing > $50 | unit | `pytest tests/unit/execution/test_risk_guard.py::test_per_trade_cap_blocks -x` | Wave 0 |
| EXEC-04 | RiskGuard rejects when total exposure would exceed $500 | unit | `pytest tests/unit/execution/test_risk_guard.py::test_total_exposure_cap_blocks -x` | Wave 0 |
| EXEC-05 | RiskGuard rejects duplicate signal for same ticker with recent filled trade | unit | `pytest tests/unit/execution/test_risk_guard.py::test_duplicate_signal_blocks -x` | Wave 0 |
| EXEC-06 | RiskGuard rejects signal when pending Trade row exists for ticker | unit | `pytest tests/unit/execution/test_risk_guard.py::test_in_flight_blocks -x` | Wave 0 |
| LOG-01 | Signal row persisted in DB for every detection (already tested in Phase 3) | unit | `pytest tests/unit/signals/test_engine.py -x` | Exists |
| LOG-02 | Trade row persisted for every execution outcome (paper/live/blocked) | unit | `pytest tests/unit/execution/test_executor.py::test_blocked_trade_logged -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/execution/ -x`
- **Per wave merge:** `uv run pytest tests/ -m "not integration"`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/execution/__init__.py` — package marker
- [ ] `tests/unit/execution/conftest.py` — mock_session_factory, signal_factory, trade_factory fixtures
- [ ] `tests/unit/execution/test_risk_guard.py` — covers EXEC-03, EXEC-04, EXEC-05, EXEC-06
- [ ] `tests/unit/execution/test_executor.py` — covers EXEC-01, EXEC-02, LOG-02
- [ ] `src/kalshi_tracker/execution/__init__.py` — package marker
- [ ] `src/kalshi_tracker/execution/types.py` — ApprovalResult, ExecutionResult
- [ ] `src/kalshi_tracker/execution/risk_guard.py` — RiskGuard class
- [ ] `src/kalshi_tracker/execution/executor.py` — TradeExecutor class

*(Framework and test infra already set up — no pytest installation needed)*

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Market orders for copy trades | Limit orders always | Avoids slippage on thin politics markets (PITFALL C-03) |
| Config-based risk limits | Module-level constants | Prevents accidental override (PITFALL C-06, EXEC-03/04) |
| In-memory exposure tracking | DB-derived exposure | Survives crashes; single source of truth (PITFALL M-06) |

---

## Open Questions

1. **How many contracts for a given trade cost?**
   - What we know: The Trade model stores `contracts` (int) and `price_cents` (int). Cost = contracts * price_cents. The Kalshi `count` field is the number of contracts.
   - What's unclear: What price to use for sizing — the signal's `yes_ask` at detection time? If yes_ask is 0 (rare), what fallback?
   - Recommendation: Use `yes_ask` from Signal.details (populated by detectors). If 0, skip execution and log a warning. Floor contracts at 1.

2. **Should paper trades also check real exposure from the live Kalshi API?**
   - What we know: Paper mode never calls the Kalshi API.
   - What's unclear: Should paper mode still count toward the $500 exposure cap (to simulate risk), or only count live trades?
   - Recommendation: Count only `mode='live'` trades toward exposure cap. Paper trades are simulations; mixing them with the hard cap makes the live limit unpredictable.

3. **Does the Signal.details dict reliably contain `direction` and `current_price`?**
   - What we know: SignalEngine persists `result.details` (from DetectionResult.details) which is detector-specific.
   - What's unclear: Whether both VolumeSpikeDetector and PriceMoveDetector populate `direction` and a price field consistently.
   - Recommendation: Inspect detector `details` output in Wave 0 tests; add a `get_price_from_signal()` helper that handles missing keys gracefully.

---

## Sources

### Primary (HIGH confidence)
- Installed kalshi-python 2.1.4 SDK source code at `.venv/lib/python3.13/site-packages/kalshi_python/` — verified `CreateOrderRequest`, `Order`, `PortfolioApi`, `GetBalanceResponse`, `GetPositionsResponse` models and method signatures
- `src/kalshi_tracker/db/models.py` — verified Trade model schema (Phase 1 output)
- `src/kalshi_tracker/signals/engine.py` — verified Signal persistence and integration point
- `src/kalshi_tracker/daemon/poller.py` — verified make_poll_tick factory pattern for extension

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md` — Risk Guard pattern, anti-patterns, data flow design
- `.planning/research/PITFALLS.md` — C-02 (race condition), C-06 (hard limits), M-05 (idempotency), M-06 (state drift)
- `tests/unit/signals/conftest.py` — mock_session pattern to follow for execution tests

### Tertiary (LOW confidence)
- None — all critical claims verified from installed code

---

## Metadata

**Confidence breakdown:**
- SDK API surface: HIGH — verified from installed .venv source code
- Architecture patterns: HIGH — derived from existing project patterns (engine.py, poller.py)
- Risk Guard design: HIGH — verified against ARCHITECTURE.md and PITFALLS.md which are HIGH confidence sources
- Trade model schema: HIGH — read directly from models.py

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable — no external moving parts)
