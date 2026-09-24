---
phase: 10
slug: paper-execution-surface
status: signed-off
written: 2026-09-22
---

# Phase 10 -- Spec

Inherits every Phase 9 convention. New package: `src/ai_hedge_fund/execution/`. Nothing in it may import `pydantic_ai` or anything under `ai_hedge_fund.agents` (enforced by test).

---

## 1. Configuration

### 1.1 `AppSettings` additions (`config.py`)

```python
alpaca_paper_api_key: str = ""
alpaca_paper_secret: str = ""
alpaca_paper_host: str = "https://paper-api.alpaca.markets"
```
Env names (`env_prefix=""`): `ALPACA_PAPER_API_KEY`, `ALPACA_PAPER_SECRET`, `ALPACA_PAPER_HOST`. `.env.example` documents all three.

### 1.2 `config/execution_policy.yaml` and `execution/policy.py`

```yaml
nav_cents: 10000000          # $100,000 paper NAV (D6)
max_position_pct: 0.05       # cap per position as a fraction of NAV
min_conviction: 55           # below this the scale is 0 -> refused (below_min_size)
full_conviction: 90          # at/above this the scale is 1.0
long_only: true              # D7
max_attempts: 3              # D3
order_type: market           # market | limit
limit_offset_bps: 25         # only used when order_type == limit
```

```python
class ExecutionPolicy(BaseModel):            # extra="forbid", frozen=True
    nav_cents: int = Field(gt=0, strict=True)
    max_position_pct: float = Field(gt=0, le=1)
    min_conviction: int = Field(ge=0, le=100)
    full_conviction: int = Field(ge=0, le=100)   # validator: > min_conviction
    long_only: bool = True
    max_attempts: int = Field(ge=1, le=10, strict=True)
    order_type: Literal["market", "limit"] = "market"
    limit_offset_bps: int = Field(ge=0, le=1000, strict=True)

DEFAULT_EXECUTION_POLICY_PATH = Path("config/execution_policy.yaml")
def load_execution_policy(path=DEFAULT_EXECUTION_POLICY_PATH) -> ExecutionPolicy   # yaml.safe_load only
def compute_execution_policy_sha(policy: ExecutionPolicy) -> str                    # -> policy_sha.fingerprint
```

### 1.3 `ai_hedge_fund/policy_sha.py` (D9)

```python
def fingerprint(model: BaseModel) -> str:
    """SHA-256 over canonical JSON (sort_keys=True, separators=(",", ":")) of model.model_dump(mode="json")."""
```
`risk.policy.compute_policy_sha` and `review.policy.compute_review_policy_sha` become one-line delegates. Byte-identical output is the contract; their existing tests prove it.

---

## 2. Migration 005 -- widen `submit_status` (D4)

`alembic/versions/005_widen_paper_trade_submit_status.py`, `revision="005"`, `down_revision="004"`.

```python
NEW = "submit_status IN ('submitted', 'rejected', 'refused_veto', 'refused_review', 'refused_policy')"
OLD = "submit_status IN ('submitted', 'rejected', 'refused_veto')"
def upgrade():   op.drop_constraint("ck_paper_trades_submit_status", "paper_trades", type_="check"); op.create_check_constraint("ck_paper_trades_submit_status", "paper_trades", NEW)
def downgrade(): (reverse; must fail loudly if refused_review/refused_policy rows exist -- op.execute a guard SELECT first)
```
SQLite cannot `ALTER ... DROP CONSTRAINT`; use `with op.batch_alter_table("paper_trades") as b:` so the round-trip test still runs on SQLite (alembic recreates the table). `records.SubmitStatus` widens to the five values; `db/models.py` CHECK text updated identically (parity + CHECK tests enforce).

`paper_trades.payload` for a refusal: `{"schema_version": 1, "refusal_reason": <str>, "decision": {...}, "execution_policy_sha": ..., "final_signal": {...}}`.

---

## 3. `execution` package

### 3.1 `execution/errors.py`

```python
class ExecutionError(Exception): ...
class MissingBrokerCredentials(ExecutionError): ...   # message names the env var
class LiveEndpointRefused(ExecutionError): ...        # host lacks "paper-api"
class NoPriceAvailable(ExecutionError): ...
class SignalNotReviewed(ExecutionError): ...          # analysis row has no review row
class AlreadySubmitted(ExecutionError): ...           # latest attempt is 'submitted'
class AlreadyDecided(ExecutionError): ...             # latest attempt is refused_*
class AttemptsExhausted(ExecutionError): ...
class BrokerRejected(ExecutionError): ...             # broker returned an error; recorded as 'rejected'
class DuplicateClientOrderId(BrokerRejected): ...     # broker saw client_order_id before
```

### 3.2 `execution/prices.py`

```python
def latest_adj_close_cents(db_session, ticker: str, as_of_date) -> int:
    """MAX trade_date <= normalise_as_of(as_of_date) from daily_prices; NoPriceAvailable if none. Never a live quote."""
```

### 3.3 `execution/sizing.py` (pure)

```python
@dataclass(frozen=True)
class SizeResult:
    shares: int                  # whole shares, >= 0
    notional_cents: int
    scale: float                 # 0..1 from conviction
    price_cents: int

def conviction_scale(conviction: int, policy: ExecutionPolicy) -> float:
    """0 below min_conviction; linear to 1.0 at full_conviction; clamp."""

def size_order(conviction: int, price_cents: int, policy: ExecutionPolicy) -> SizeResult:
    """shares = floor(nav_cents * max_position_pct * scale / price_cents). Integer arithmetic only."""
```

### 3.4 `execution/decide.py` (pure)

```python
class Refusal(BaseModel):   # frozen
    status: Literal["refused_veto", "refused_review", "refused_policy"]
    reason: Literal["risk_vetoed", "review_rejected", "neutral_direction", "long_only", "no_price", "below_min_size"]

class OrderPlan(BaseModel):  # frozen
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: int
    limit_price_cents: int | None
    size: SizeResult

Decision = Refusal | OrderPlan

def decide(final_signal: FinalSignalOutput, risk_status: str, review_status: str,
           price_cents: int | None, policy: ExecutionPolicy) -> Decision:
    # order of checks is the audit order: veto -> review -> direction -> long_only -> price -> size
```

### 3.5 `execution/broker.py`

```python
@dataclass(frozen=True)
class BrokerOrderRequest:
    client_order_id: str; symbol: str; side: Literal["buy","sell"]; qty: int
    order_type: Literal["market","limit"]; limit_price_cents: int | None; time_in_force: Literal["day"] = "day"

@dataclass(frozen=True)
class BrokerOrderResult:
    broker_order_id: str; status: str; submitted_at: datetime; raw: dict[str, Any]   # raw is already redacted

class BrokerClient(Protocol):
    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderResult: ...     # raises BrokerRejected / DuplicateClientOrderId
    def cancel_order(self, broker_order_id: str) -> None: ...                     # used by the live smoke test only
```

### 3.6 `execution/alpaca.py` (D2, D8)

```python
class AlpacaPaperBroker:
    def __init__(self, api_key: str, secret: str, host: str) -> None:
        # MissingBrokerCredentials("ALPACA_PAPER_API_KEY") etc. for any empty value
        # LiveEndpointRefused unless "paper-api" in host
        self._client = TradingClient(api_key, secret, paper=True, url_override=host)
    @classmethod
    def from_settings(cls, settings: AppSettings) -> "AlpacaPaperBroker": ...
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True,
           retry=retry_if_exception_type(TransientBrokerError))   # never retry a rejection or a duplicate
    def submit_order(self, req) -> BrokerOrderResult:
        # MarketOrderRequest / LimitOrderRequest(symbol, qty, side, time_in_force=DAY, client_order_id=req.client_order_id)
        # APIError code for duplicate client_order_id -> DuplicateClientOrderId; other 4xx -> BrokerRejected; 5xx/timeouts -> TransientBrokerError
        # result.raw = redact(order.model_dump(mode="json"))
```
Logging: structlog events carry `client_order_id`, `symbol`, `qty`, `broker_order_id` -- never the key, secret, or host credentials.

### 3.7 `execution/redact.py`

```python
SECRET_KEY = re.compile(r"(^|_)(secret|api_key|token|password|authorization)(_|$)", re.I)
def redact(obj: Any) -> Any:
    """Recursively replace values of secret-like keys with '***' at every depth; strings are scanned for the configured key/secret values and replaced too."""
```

### 3.8 `execution/submit.py` (D1, D3, D4)

```python
@dataclass(frozen=True)
class SubmitDeps:
    db_session: Session
    broker: BrokerClient
    policy: ExecutionPolicy
    policy_sha: str

def load_signal_context(db_session, episodic_id: int) -> SignalContext:
    """analysis row (record_type='analysis' or ValueError) + latest review row (or SignalNotReviewed);
    returns FinalSignalOutput.model_validate(review.payload['final_signal']), review_status, risk_status
    (from analysis.payload['risk_assessment']['status']), ticker, as_of_date."""

def next_attempt(db_session, signal_id: int, policy) -> int:
    """Latest paper_trades row for signal_id (recall, as_of far future): none -> 1;
    submitted -> AlreadySubmitted; refused_* -> AlreadyDecided; rejected -> attempt+1, AttemptsExhausted if > max_attempts."""

def submit_signal(deps: SubmitDeps, episodic_id: int, *, dry_run: bool = False) -> PaperTradeRecord | Decision:
    """1 load context  2 next_attempt  3 price (None if NoPriceAvailable)  4 decide
       5a Refusal -> insert_paper_trade(submit_status=refusal.status, broker_order_id=None, payload{refusal_reason,...})
       5b OrderPlan -> client_order_id=f"sig-{signal_id}-a{attempt}"; broker.submit_order
           ok -> insert 'submitted' with broker_order_id + redacted raw
           BrokerRejected -> insert 'rejected' with payload.broker_error (redacted); re-raise after recording
           DuplicateClientOrderId -> treat as already submitted: look up existing row; if none, insert 'submitted'
             with broker_order_id from the duplicate response when available, else raise
       dry_run -> return the Decision after step 4, write nothing, call nothing."""
```
Zero LLM calls anywhere in this module (10.1).

### 3.9 `scripts/submit_signal.py`

```
submit_signal --episodic-id N [--policy PATH] [--database-url URL] [--dry-run] [--json]
exit 0: submitted (prints broker_order_id) | exit 2: refused (prints status + reason) | exit 1: error
```
DI kwargs `broker_factory=`, `session_factory=` on `_main(argv, *, ...)` for tests (the `run_analysis` pattern).

---

## 4. Tests

```
tests/execution/
  __init__.py  conftest.py  fakes.py (FakeBroker: records requests, rejects duplicate client_order_id, scriptable failures)
  test_execution_policy.py  test_prices.py  test_sizing.py  test_decide.py  test_submit.py
  test_redact.py  test_alpaca_adapter.py (SDK mocked)  test_no_llm.py  test_alpaca_live.py (@slow, credential-gated)
tests/scripts/test_submit_signal.py
tests/unit/test_policy_sha.py
tests/paper/ -- parametrizations updated for the widened status set; migration round-trip covers 005
```
Live test guard: skip unless `ALPACA_PAPER_API_KEY` and `ALPACA_PAPER_SECRET` are set; assert `"paper-api" in host`; ticker `SPY`, qty 1, `client_order_id` includes a UUID suffix so reruns never collide; cancels the order if still open at the end.

---

## 5. Sequence summary

```
episodic_id -> load_signal_context -> next_attempt -> latest_adj_close -> decide
   Refusal  -> paper_trades row (refused_*), exit 2
   OrderPlan -> client_order_id -> broker.submit_order -> paper_trades row (submitted | rejected)
```
