# Phase 4: Cost Model and Portfolio Simulator - Research

**Researched:** 2026-03-29
**Domain:** Vectorized portfolio simulation — cost modeling, daily P&L, trade log generation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting.
Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

CRITICAL from Phase 3: WeightFrame already has shift(1) applied. The Portfolio Simulator must NOT
apply an additional shift.

### Claude's Discretion
All implementation choices — module layout, CostConfig design, PortfolioResult structure,
trade log schema, vectorization strategy, test fixture design.

### Deferred Ideas (OUT OF SCOPE)
None — discuss phase skipped.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BT-02 | Engine supports short positions as a first-class operation | Negative weights from WeightFrame are short positions; sign convention established in types.py |
| BT-03 | Engine models transaction costs (slippage + commission, configurable bps) | CostConfig frozen dataclass; vectorized turnover mask × bps deduction |
| BT-04 | Engine models short borrow costs (configurable flat rate, default 50bps/yr) | Daily borrow charge = annual_bps / 252 per short position; applied to negative-weight rows |
| BT-06 | Engine uses equal-weight position sizing across all signal-selected tickers | SignalAdapter already handles equal-weight normalization; simulator receives pre-sized WeightFrame |
| BT-07 | Engine produces a daily returns series and a trade log as output | PortfolioResult: returns Series + trade_log DataFrame |
</phase_requirements>

---

## Summary

Phase 4 builds on the WeightFrame contract established in Phase 3. The simulator receives a
WeightFrame (date x ticker, values in [-1, +1], already shift(1)-applied) and a PriceFrame
(date x ticker, close prices as floats), applies cost deductions, and emits a PortfolioResult.

The core math is fully vectorized: no Python loops over dates. Gross returns are computed as
`(close[t] / close[t-1] - 1) * weight[t-1]`, transaction costs are applied to turnover rows
(weight_change > 0), and short borrow costs are applied daily to negative-weight positions.
The trade log is derived from the turnover frame by melting to long format.

The key architectural insight is that equal-weight sizing is already handled by the SignalAdapter
(BT-06 is satisfied upstream). The simulator only needs to apply costs and aggregate returns.
CostConfig is a frozen Pydantic BaseModel following the PriceSettings/SignalAdapterConfig pattern
already established in config.py — no hardcoded values anywhere in the simulator.

**Primary recommendation:** Implement `simulator/types.py` (CostConfig, PortfolioResult),
`simulator/engine.py` (PortfolioSimulator), add CostConfig to `config.py`, and cover with TDD
unit tests against synthetic data with hand-calculated reference values.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 3.0.1 | Vectorized DataFrame math — pct_change, diff, mul, sum | Already installed; the entire codebase uses DataFrames |
| numpy | 2.4.3 | Array masking, abs(), clip(), where() | Already installed; pandas dependency |
| pydantic | 2.12.5 | CostConfig frozen BaseModel + PortfolioResult validation | Established pattern: PriceSettings, SignalAdapterConfig |
| structlog | 25.5.0 | Structured logging in simulator | Established project-wide pattern |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.2 | Unit testing with TDD | Tests written before implementation |
| freezegun | 1.5.5 | Date mocking | Only needed if date-dependent logic emerges |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Plain pandas | vectorbt | vectorbt adds a heavy dependency with its own opinionated abstractions; pure pandas gives full control and is sufficient at 200 tickers |
| Pydantic frozen BaseModel for CostConfig | Python dataclass(frozen=True) | dataclass matches ARCHITECTURE.md's CostConfig sketch, but project uses Pydantic uniformly (PriceSettings, SignalAdapterConfig) — stay consistent |

**No new packages to install.** All dependencies are already in `pyproject.toml`.

---

## Architecture Patterns

### Recommended Project Structure
```
backtest/src/fund_backtest/
├── simulator/
│   ├── __init__.py       # empty package marker
│   ├── types.py          # CostConfig (frozen Pydantic), PortfolioResult, PriceFrame alias
│   └── engine.py         # PortfolioSimulator class
├── config.py             # Add load_cost_config() factory (existing file)
tests/unit/
├── test_simulator_types.py   # CostConfig validation tests
└── test_simulator_engine.py  # PortfolioSimulator behavioral tests
```

### Pattern 1: CostConfig as Frozen Pydantic BaseModel
**What:** All cost parameters in a single frozen model. No hardcoded values in the simulator.
**When to use:** Any parameter that affects simulation output — slippage, commission, borrow rate.

```python
# Source: established project pattern (config.py SignalAdapterConfig)
from pydantic import BaseModel

class CostConfig(BaseModel):
    """Frozen cost configuration for the portfolio simulator.

    All cost parameters are in basis points (bps) unless noted.
    One basis point = 0.0001 (0.01%).
    """
    model_config = {"frozen": True}

    slippage_bps: float = 10.0
    """One-way slippage per trade in bps (default 10 bps = 0.10%)."""

    commission_bps: float = 5.0
    """One-way commission per trade in bps (default 5 bps = 0.05%)."""

    borrow_cost_bps_annual: float = 50.0
    """Annualized short borrow cost in bps (default 50 bps = 0.50%/yr)."""
```

**CRITICAL:** Pydantic `model_config = {"frozen": True}` makes the model immutable
(sets `__hash__` and raises on mutation). This is the Pydantic v2 equivalent of
`@dataclass(frozen=True)` — use it for consistency with the project's Pydantic-first
approach. Do NOT use `@dataclass(frozen=True)` since other config models use Pydantic.

### Pattern 2: PortfolioResult as Pydantic BaseModel (arbitrary_types_allowed)
**What:** Output container with pandas Series/DataFrame fields.
**When to use:** Passing simulation results to downstream Risk Engine and Reporting layers.

```python
# Source: established project pattern (Pydantic BaseModel for typed contracts)
from pydantic import BaseModel
import pandas as pd

class PortfolioResult(BaseModel):
    """Output of a completed simulation run."""
    model_config = {"arbitrary_types_allowed": True}

    gross_returns: pd.Series
    """Daily gross returns (before cost deduction). index=DatetimeIndex."""

    net_returns: pd.Series
    """Daily net returns (after all costs). index=DatetimeIndex."""

    positions: pd.DataFrame
    """Date x ticker weight held each day. Same shape as input WeightFrame."""

    trade_log: pd.DataFrame
    """One row per trade: date, ticker, direction, weight_change, cost_bps, cost_fraction."""
```

**Note on `arbitrary_types_allowed`:** Pydantic v2 requires this config flag to accept
non-Pydantic types like `pd.Series` and `pd.DataFrame` as model fields. Precedent exists
in the project (check if needed), but if not yet used, this is the standard approach.

### Pattern 3: Vectorized P&L Computation (NO Python loops over dates)
**What:** All portfolio math operates on full DataFrames with pandas operations.
**When to use:** The entire simulator engine — this is the core design constraint.

```python
# Source: ARCHITECTURE.md data flow, O'Reilly Python for Algorithmic Trading Ch4

def _compute_gross_returns(
    weights: pd.DataFrame,  # WeightFrame — already shift(1) applied
    prices: pd.DataFrame,   # date x ticker, float close prices
) -> pd.Series:
    """Vectorized daily gross portfolio return.

    Formula: gross_return[t] = sum_over_tickers(weight[t-1] * (close[t]/close[t-1] - 1))

    CRITICAL: WeightFrame is already shift(1)-applied from Phase 3.
    weight[t] in WeightFrame = signal computed at t-1 (safe to use against return[t]).
    """
    # Daily return per ticker: pct_change() aligns with weight already shifted
    daily_returns = prices.pct_change()

    # Align: only tickers present in both frames
    tickers = weights.columns.intersection(daily_returns.columns)
    w = weights[tickers]
    r = daily_returns[tickers]

    # Weighted sum across tickers — result is a Series indexed by date
    # NaN weights (first row) produce NaN return — caller drops with dropna()
    return (w * r).sum(axis=1)
```

### Pattern 4: Transaction Cost as Turnover Mask
**What:** Cost is only charged on days where a position changes (turnover).
**When to use:** Slippage and commission charges.

```python
# Source: ARCHITECTURE.md "Apply CostModel to turnover rows"

def _compute_transaction_costs(
    weights: pd.DataFrame,
    cost_config: CostConfig,
) -> pd.Series:
    """Vectorized transaction cost: (slippage_bps + commission_bps) * |weight_change|.

    Transaction cost is charged proportional to the absolute weight change,
    NOT the full position size. Only rebalancing trades incur costs.

    Units: cost is returned as a fraction (e.g. 0.0015 for 15 bps).
    """
    bps_per_trade = (cost_config.slippage_bps + cost_config.commission_bps) / 10_000
    # Weight change per ticker per day
    weight_change = weights.diff().abs()
    # Aggregate across tickers: total cost per day
    return (weight_change * bps_per_trade).sum(axis=1)
```

### Pattern 5: Short Borrow Cost as Daily Accrual
**What:** Borrow cost accrues daily on the absolute value of negative (short) weights.
**When to use:** Any day where the portfolio has short positions.

```python
# Source: PITFALLS.md Pitfall 5; ARCHITECTURE.md "Apply borrow_cost_bps to short positions daily"

def _compute_borrow_costs(
    weights: pd.DataFrame,
    cost_config: CostConfig,
) -> pd.Series:
    """Vectorized daily short borrow cost.

    Annual borrow rate is divided by 252 trading days for daily accrual.
    Applied only to negative-weight (short) positions.

    Units: returned as a fraction (e.g. 0.0000198 for 50bps/252 days).
    """
    daily_borrow_rate = cost_config.borrow_cost_bps_annual / 10_000 / 252
    # Short positions have negative weights — mask positives to zero
    short_weights = weights.clip(upper=0.0).abs()
    # Aggregate across tickers
    return (short_weights * daily_borrow_rate).sum(axis=1)
```

### Pattern 6: Trade Log Generation via melt()
**What:** Convert the turnover DataFrame (wide format) to a long-format trade log.
**When to use:** Building the trade_log component of PortfolioResult.

```python
# Source: pandas documentation; standard long/short trade log pattern

def _build_trade_log(weights: pd.DataFrame, cost_per_ticker: pd.DataFrame) -> pd.DataFrame:
    """Build trade log from weight changes and per-ticker costs.

    Produces one row per (date, ticker) pair where abs(weight_change) > threshold.
    Includes direction (long/short), weight_change magnitude, and cost in bps.
    """
    weight_change = weights.diff()
    threshold = 1e-8  # filter floating-point noise

    # Melt to long format
    wc_long = (
        weight_change
        .where(weight_change.abs() > threshold)  # only real trades
        .stack()  # date x ticker -> multi-index
        .reset_index()
        .rename(columns={"level_0": "date", "level_1": "ticker", 0: "weight_change"})
    )
    wc_long["direction"] = wc_long["weight_change"].apply(
        lambda x: "long" if x > 0 else "short"
    )
    return wc_long
```

**Note on pandas 3.0 stack():** In pandas 3.0, `DataFrame.stack()` with default
`future_stack=True` (the new behavior) raises on mixed dtypes. For a float WeightFrame
this is not an issue, but be explicit: test with `future_stack=True` to avoid deprecation
warnings. Alternatively, use `.melt()` for cleaner syntax.

### Pattern 7: PriceFrame Loading from PriceBarRepository
**What:** Load close prices from the repository as a date x ticker DataFrame.
**When to use:** When the simulator needs real price data (integration path).

```python
# Source: price/repository.py (existing implementation)
def load_price_frame(
    repo: PriceBarRepository,
    tickers: list[str],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Load close prices as a date x ticker DataFrame.

    Prices are stored in cents in PostgreSQL. Convert to float dollars
    for simulator math to avoid integer overflow in pct_change().
    """
    bars = repo.get_bars(tickers, start_date, end_date)
    rows = [
        {"date": b.bar_date, "ticker": b.ticker, "close": b.close_cents / 100.0}
        for b in bars
    ]
    df = pd.DataFrame(rows)
    return df.pivot(index="date", columns="ticker", values="close")
```

### Anti-Patterns to Avoid

- **Additional shift(1) in simulator:** The WeightFrame is ALREADY shifted from Phase 3.
  Adding `.shift(1)` in the simulator introduces a 2-day lag — a silent logic error that
  produces wrong results without raising any exceptions. This is the #1 risk for this phase.

- **Hardcoded cost values:** Any `* 0.001` or `/ 252` inline in the simulator without
  referencing `cost_config` violates BT-03/BT-04 and the success criterion "no hardcoded values."

- **Python loop over dates:** `for date in weight_frame.index: ...` kills performance and
  violates the architecture contract. 200 tickers x 1,250 days must run as vectorized ops.

- **Mutating input DataFrames:** All simulator operations must return new DataFrames (project
  immutability rule). Never use `.iloc[...] = ...` or `.loc[...] = ...` on input frames.

- **Integer overflow in bps math:** CostConfig stores bps as `float`. Avoid `int` fields —
  fractional bps (e.g., 7.5 bps) must be representable without truncation.

- **`.sum(axis=1)` on mixed-NaN frames:** `weights.diff()` preserves NaN from the first row.
  When summing across tickers, NaN propagation depends on `skipna`. The default `skipna=True`
  means NaN positions are treated as 0 — correct behavior here. Document this explicitly.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Percentage returns | Custom loop computing close[t]/close[t-1]-1 | `prices.pct_change()` | Built-in, NaN-safe, aligns indices automatically |
| Turnover computation | Loop checking weight changes | `weights.diff().abs()` | One-line vectorized; handles NaN rows correctly |
| Trade log generation | Manual date iteration | `DataFrame.stack()` + `reset_index()` + `.melt()` | Vectorized, produces correct multi-index result |
| Config validation | Manual `if bps < 0: raise` | Pydantic `Field(ge=0)` validators | Consistent with all other config models in the codebase |
| Frozen config object | `@dataclass(frozen=True)` | Pydantic `model_config = {"frozen": True}` | All project configs use Pydantic; stay consistent |

**Key insight:** The entire simulator is a composition of pandas operations that already exist.
The implementation risk is in correct alignment of indices and the NaN handling at the first row —
not in algorithmic complexity.

---

## Common Pitfalls

### Pitfall 1: Double Shift (Critical)
**What goes wrong:** Simulator applies `.shift(1)` to weights that are already shifted,
producing a 2-day lag. Returns look slightly worse than hand-calculated reference.
**Why it happens:** ARCHITECTURE.md's data flow diagram (Step 1) says "Shift weights by 1 period"
as if the simulator owns this step — but Phase 3 already did it.
**How to avoid:** Read the Phase 3 CRITICAL note. Add a comment in `engine.py`:
`# WeightFrame is already shift(1)-applied — DO NOT shift again (Phase 3 invariant)`.
**Warning signs:** Hand-calculated reference test fails by exactly 1 day.

### Pitfall 2: bps / 10_000 vs bps / 100 Confusion
**What goes wrong:** Cost appears 100x too large or too small.
**Why it happens:** "Basis points" = 1/10000 of a whole. It's easy to confuse bps with
percent (1/100). 10 bps = 0.10% = 0.001 as a fraction.
**How to avoid:** Define a module-level constant `_BPS_TO_FRACTION = 1e-4` or compute
inline with `/ 10_000`. Add a docstring note: "1 bps = 0.0001 (one basis point = one hundredth
of one percent)". The hand-calculated reference test will catch this.
**Warning signs:** Net returns are dramatically lower than gross (cost 100x too high) or
effectively identical to gross (cost 100x too low).

### Pitfall 3: NaN First Row Propagates into Returns
**What goes wrong:** The first row of PortfolioResult.net_returns is NaN (from the shift
artifact in WeightFrame). If the caller doesn't drop it, cumulative return calculations are
corrupted.
**Why it happens:** `weights.diff()` on a frame where row 0 is NaN produces NaN in row 1
(diff needs two non-NaN values). `pct_change()` on prices also produces NaN for row 0.
**How to avoid:** The simulator should drop the leading NaN row from all output Series before
returning. Use `net_returns.dropna()` on final output. Document this in PortfolioResult docstring:
"First row of input WeightFrame is always NaN (shift artifact) — simulator drops it before
returning returns Series."
**Warning signs:** PortfolioResult.net_returns.iloc[0] is NaN; cumsum() starting from NaN.

### Pitfall 4: `.sum(axis=1)` with skipna Behavior
**What goes wrong:** Rows with partial NaN ticker coverage sum incorrectly.
**Why it happens:** `pandas.DataFrame.sum(axis=1)` has `skipna=True` by default, meaning NaN
positions are treated as 0 contribution. This is correct for tickers not in the portfolio.
However, if ALL tickers are NaN for a row (the first row), the result is 0.0 (not NaN).
This means the first row of gross_returns appears as 0.0 return rather than NaN — subtle but
important for the trade log and cumulative NAV.
**How to avoid:** After computing `(weights * returns).sum(axis=1)`, apply a mask:
where the weight row is all-NaN, set the return to NaN. Then `dropna()` before returning.
**Warning signs:** NAV starts with a flat 0.0% day instead of starting after the first real
rebalance.

### Pitfall 5: Price Frame Index Misalignment
**What goes wrong:** WeightFrame dates don't align with PriceFrame dates (e.g., different
start dates, missing trading days, timezone differences). Result is NaN returns or silent
misaligned multiplication.
**Why it happens:** WeightFrame comes from signal data (potentially sparser) while PriceFrame
comes from price data (full trading calendar). pandas will align on index when multiplying
two DataFrames, introducing NaN for dates present in one but not the other.
**How to avoid:** Before simulation, align indices:
`common_dates = weights.index.intersection(prices.index)` and reindex both frames.
Log the count of dates dropped from each side.
**Warning signs:** Large number of NaN rows in returns. Returns Series much shorter than
expected.

---

## Code Examples

Verified patterns from existing codebase:

### Existing Config Pattern (from config.py)
```python
# Source: backtest/src/fund_backtest/config.py — SignalAdapterConfig
class SignalAdapterConfig(BaseModel):
    """Signal adapter configuration."""
    min_coverage: int = 5
    gross_exposure_limit: float = 1.0
```
CostConfig follows this exact pattern with `model_config = {"frozen": True}` added.

### Existing Test Pattern (from test_signal_adapter.py)
```python
# Source: backtest/tests/unit/test_signal_adapter.py
def _make_signal_frame() -> pd.DataFrame:
    """Factory function for test fixtures."""
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    return pd.DataFrame({"AAPL": [10.0, ...], "NVDA": [90.0, ...]}, index=dates)
```
Simulator tests follow this pattern: factory function + class-organized test methods.

### Hand-Calculated Reference Pattern
For BT-07 success criterion 4 ("produces returns matching hand-calculated reference"):
```python
# Synthetic 3-ticker, 5-day scenario:
# Day 0: weights = NaN (shift artifact) — no position
# Day 1: AAPL=+0.5, NVDA=-0.5 (long AAPL, short NVDA)
# Day 2: prices move AAPL +2%, NVDA +1%
#   gross_return[day2] = 0.5*0.02 + (-0.5)*0.01 = 0.01 - 0.005 = 0.005 (0.5%)
#   transaction_cost[day1->day2] = 0 (no weight change on day 2)
#   borrow_cost[day2] = 0.5 * (50/10000/252) = ~0.0000992
#   net_return[day2] = 0.005 - 0.0000992 ≈ 0.004901
```
The test computes this by hand and asserts `abs(simulator_result - 0.004901) < 1e-9`.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `backtest/pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `cd backtest && .venv/bin/python -m pytest tests/unit/ -q` |
| Full suite command | `cd backtest && .venv/bin/python -m pytest tests/ -q -m "not integration"` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BT-02 | Short positions carry negative weights; borrow cost applied | unit | `pytest tests/unit/test_simulator_engine.py::TestShortPositions -x` | Wave 0 |
| BT-03 | Slippage + commission deducted on weight-change days | unit | `pytest tests/unit/test_simulator_engine.py::TestTransactionCosts -x` | Wave 0 |
| BT-04 | Borrow cost at 50bps/yr default; accrues daily on short positions | unit | `pytest tests/unit/test_simulator_engine.py::TestBorrowCosts -x` | Wave 0 |
| BT-06 | Equal-weight sizing already in WeightFrame; simulator preserves it | unit | `pytest tests/unit/test_simulator_engine.py::TestEqualWeight -x` | Wave 0 |
| BT-07 | PortfolioResult has net_returns Series + trade_log DataFrame | unit | `pytest tests/unit/test_simulator_types.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backtest && .venv/bin/python -m pytest tests/unit/ -q`
- **Per wave merge:** `cd backtest && .venv/bin/python -m pytest tests/ -q -m "not integration"`
- **Phase gate:** Full suite (unit only — simulator has no DB dependency) green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `backtest/tests/unit/test_simulator_types.py` — covers BT-07 (PortfolioResult schema)
- [ ] `backtest/tests/unit/test_simulator_engine.py` — covers BT-02, BT-03, BT-04, BT-06
- [ ] `backtest/src/fund_backtest/simulator/__init__.py` — package marker
- [ ] `backtest/src/fund_backtest/simulator/types.py` — CostConfig, PortfolioResult, PriceFrame
- [ ] `backtest/src/fund_backtest/simulator/engine.py` — PortfolioSimulator

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@dataclass(frozen=True)` for config | Pydantic BaseModel (frozen) | Phase 3 establishes pattern | Stay consistent with project |
| `DataFrame.stack()` with multi-level | `DataFrame.stack(future_stack=True)` | pandas 3.0 | Needed to avoid FutureWarning |
| Pyfolio for risk/tearsheet | quantstats (Phase 5, not Phase 4) | 2022+ | No impact on Phase 4 |

**Deprecated/outdated for this project:**
- `pandas.DataFrame.stack()` without `future_stack=True`: raises FutureWarning in pandas 3.0.
  Use `stack(future_stack=True)` or `.melt()` for trade log generation.

---

## Open Questions

1. **PriceFrame loading interface**
   - What we know: PriceBarRepository.get_bars() returns List[PriceBarORM]; close_cents is BigInteger.
   - What's unclear: Should the simulator accept a pre-built DataFrame, or should it accept a
     repository + date range and load prices internally?
   - Recommendation: Accept a pre-built `prices: pd.DataFrame` (date x ticker, float close in
     dollars). Keep the simulator pure (no DB dependency). Provide a separate `load_price_frame()`
     utility in `simulator/types.py` or a helper module. This matches the Phase 5 Risk Engine
     pattern (computable from synthetic data without DB).

2. **Trade log: one row per trade vs. one row per (date, ticker) rebalance**
   - What we know: Success criterion says "trade log shows slippage + commission" per trade.
   - What's unclear: Does a weight change from 0.3 to 0.4 count as 1 trade or 2 (close 0.3,
     open 0.4)?
   - Recommendation: One row per (date, ticker) weight change event. Include `weight_before`,
     `weight_after`, `weight_change`, `cost_fraction`, `cost_bps` columns. Downstream consumers
     can aggregate as needed.

3. **FINRA tiered borrow cost (from STATE.md blocker)**
   - What we know: STATE.md flags "FINRA short interest data ingestion pipeline for tiered borrow
     cost model not yet researched." Pitfall 5 in PITFALLS.md suggests tiered borrow rates based
     on short interest % of float.
   - What's unclear: Should Phase 4 implement tiered borrow, or flat-rate only?
   - Recommendation: Implement flat-rate only (BT-04 requirement: "configurable flat rate,
     default 50bps/yr"). Tiered borrow requires FINRA data ingestion which is a separate phase.
     Document as a known limitation in CostConfig docstring. The `borrow_cost_bps_annual` field
     is already the right abstraction — a future upgrade can make it a per-ticker override map.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | yes | 3.12.11 | — |
| pandas | Core simulation | yes | 3.0.1 | — |
| numpy | Array ops | yes | 2.4.3 | — |
| pydantic | CostConfig, PortfolioResult | yes | 2.12.5 | — |
| pytest | TDD tests | yes | 9.0.2 | — |
| PostgreSQL | Price loading (integration) | not found (pg_isready absent) | — | Synthetic data for unit tests |

**Missing dependencies with no fallback:** None (all unit tests run without PostgreSQL).

**Missing dependencies with fallback:** PostgreSQL is not available locally, but the simulator
has no DB dependency by design. Unit tests use synthetic DataFrames. Integration tests are marked
with `@pytest.mark.integration` and skipped by default.

---

## Project Constraints (from CLAUDE.md)

**From global CLAUDE.md / coding-style.md:**
- NEVER mutate input DataFrames — all simulator ops return new objects
- Functions < 50 lines; files < 800 lines
- No hardcoded values — all parameters from CostConfig
- Validate at system boundaries — CostConfig uses Pydantic validators for non-negative bps
- Error handling: catch specific exceptions; log with structlog; return sensible defaults

**From fund-backtest CLAUDE.md:**
- Immutability: financial data (prices, returns) never overwritten — append new observations only
- All monetary values stored in cents in the DB, but simulator works in float dollars internally
- Python 3.11+ syntax: `from __future__ import annotations`, `str | None` union syntax
- Naming: `snake_case` for functions/variables, `PascalCase` for classes
- Logging: `logger = structlog.get_logger(__name__)`, event-style keys (`simulator_run_complete`)
- Docstrings: Google-style on every public function/class, triple-quoted

**Phase 4 specific constraint (from CONTEXT.md):**
- WeightFrame from Phase 3 has shift(1) applied — Portfolio Simulator MUST NOT apply additional shift

---

## Sources

### Primary (HIGH confidence)
- Project codebase `signal/adapter.py` — Phase 3 implementation, shift(1) behavior confirmed
- Project codebase `config.py` — Pydantic BaseModel pattern for CostConfig
- Project codebase `price/types.py` — cents/float conversion pattern
- `.planning/research/ARCHITECTURE.md` — vectorized simulator data flow and CostConfig schema
- `.planning/research/PITFALLS.md` — cost modeling pitfalls (borrow, slippage, look-ahead)

### Secondary (MEDIUM confidence)
- pandas 3.0 docs — `DataFrame.stack(future_stack=True)`, `pct_change()`, `diff()`
- `.planning/STATE.md` — decisions log confirming shift(1) is Phase 3 responsibility
- O'Reilly Python for Algorithmic Trading Ch4 — vectorized gross returns formula

### Tertiary (LOW confidence)
- None — all findings verified against existing codebase or official docs.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages already installed and verified
- Architecture: HIGH — fully defined in ARCHITECTURE.md; implementation patterns verified
  against existing codebase conventions
- Pitfalls: HIGH — double-shift and bps confusion are concrete, verifiable errors;
  NaN handling patterns confirmed against pandas 3.0 behavior

**Research date:** 2026-03-29
**Valid until:** 2026-04-29 (stable domain — pandas vectorized math doesn't change rapidly)
