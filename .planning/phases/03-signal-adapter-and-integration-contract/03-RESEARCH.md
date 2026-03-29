# Phase 3: Signal Adapter and Integration Contract - Research

**Researched:** 2026-03-29
**Domain:** pandas DataFrame contracts, cross-sectional signal normalization, look-ahead bias prevention
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None — discuss phase was skipped per `workflow.skip_discuss`. All implementation choices are at Claude's discretion.

### Claude's Discretion
All implementation choices: SignalFrame/WeightFrame schema, normalization strategy, min_coverage threshold, shift placement (Signal Adapter vs Portfolio Simulator), module structure, test organization, validation error types.

### Deferred Ideas (OUT OF SCOPE)
None specified.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BT-01 | Engine accepts a signal DataFrame (date x ticker → score) and simulates a long/short portfolio | SignalFrame contract defined here; `validate_signal_frame()` raises descriptive errors on bad input; adapter produces WeightFrame consumed by Phase 4 Portfolio Simulator |
| BT-05 | Engine enforces look-ahead bias prevention (signal shifted by 1 day before execution) | `shift(1)` placed in Signal Adapter so WeightFrame row T carries signals from T-1; verified: spike on T → zero weight on T, nonzero weight on T+1 |
| INT-01 | Well-defined signal contract (DataFrame schema) that any strategy module can conform to | `SignalFrame` type alias + `validate_signal_frame()` function + `SignalAdapterConfig` dataclass constitute the full public contract; documented in `signal/types.py` |
</phase_requirements>

---

## Summary

Phase 3 is a pure-Python, database-free phase. It defines the typed data contract between strategy modules (AI Washing Detector, future strategies) and the backtesting engine, and builds the Signal Adapter that normalizes raw scores into portfolio-ready weights.

The core deliverable is three things: (1) a `SignalFrame` schema — a documented, validated `pd.DataFrame` contract; (2) a `WeightFrame` schema — its output counterpart with values in [-1, +1]; and (3) a `SignalAdapter` class that validates input, ranks scores cross-sectionally, maps them to weights, applies `shift(1)` to enforce the look-ahead bias guarantee, and drops rows with insufficient coverage. All operations are pandas vectorized — no Python loops over dates.

The critical design decision for this phase is **where to place `shift(1)`**. The ARCHITECTURE.md places it in the Portfolio Simulator (Phase 4), but Phase 3 success criterion 3 explicitly requires the Signal Adapter to enforce the zero-weight-on-T guarantee. Resolution: `shift(1)` lives in the Signal Adapter so that the WeightFrame coming out is already temporally safe. The Portfolio Simulator (Phase 4) must NOT apply an additional shift. This is a one-time architectural alignment documented here so Phase 4 planners are not surprised.

**Primary recommendation:** Build `signal/types.py` (contracts), `signal/validator.py` (input validation), `signal/adapter.py` (normalization + shift), and `signal/config.py` (SignalAdapterConfig frozen dataclass). Follow the exact same module pattern as `price/` — one file per concern, Pydantic for contracts, frozen dataclass for configuration.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 3.0.1 (installed) | DataFrame normalization, ranking, shift | Already in stack; `rank(axis=1, pct=True)`, `shift(1)`, `isna().all(axis=1)` are the three key operations |
| numpy | 2.4.3 (installed) | Numerical operations | Required by pandas; used for `np.nan` sentinel and clipping |
| pydantic | 2.12.5 (installed) | SignalAdapterConfig validation | Already in stack; frozen BaseModel for immutable config |
| dataclasses | stdlib | Frozen config container | `@dataclass(frozen=True)` for CostConfig pattern; consistent with ARCHITECTURE.md `CostConfig` precedent |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | 25.5.0 (installed) | Warning logs for dropped tickers, low coverage | Consistent with all other modules — `logger.warning("signal_ticker_dropped", ...)` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `rank(pct=True)` cross-sectional | Custom z-score normalization | Rank is distribution-free (handles outliers); z-score is sensitive to extreme AI Washing scores. Rank is the standard for cross-sectional equity signals. |
| Pydantic BaseModel for config | `@dataclass(frozen=True)` | Either works; existing codebase uses both (`UniverseSettings` is Pydantic BaseModel, `CostConfig` in ARCHITECTURE.md is frozen dataclass). Use Pydantic BaseModel for config consistency with `PriceSettings`/`UniverseSettings`. |

**Installation:** No new packages needed. All dependencies already in `pyproject.toml`.

---

## Architecture Patterns

### Recommended Project Structure
```
backtest/src/fund_backtest/
├── signal/              # New module — Phase 3 deliverable
│   ├── __init__.py      # Empty
│   ├── types.py         # SignalFrame alias, WeightFrame alias, validation types
│   ├── validator.py     # validate_signal_frame() — raises SignalValidationError
│   └── adapter.py       # SignalAdapter class — normalize + shift
├── config.py            # Add SignalAdapterConfig Pydantic model here
backtest/tests/
├── unit/
│   ├── test_signal_types.py      # SignalFrame/WeightFrame contract tests
│   └── test_signal_adapter.py    # Normalization, shift, look-ahead bias guard
```

No new migration needed — Phase 3 has no database tables.

### Pattern 1: SignalFrame and WeightFrame as Documented Type Aliases

These are `pd.DataFrame` instances with enforced shape/dtype conventions. Python cannot enforce these at the type-checker level, so runtime validation is the contract.

```python
# Source: fund_backtest/signal/types.py
from __future__ import annotations
import pandas as pd

# Type aliases — not runtime types, but document the contract
SignalFrame = pd.DataFrame
"""
A date-indexed, ticker-columned DataFrame of raw strategy scores.

Schema:
    index:   pd.DatetimeIndex, UTC, daily business-day frequency
    columns: list[str] — ticker symbols (e.g. "AAPL", "NVDA")
    values:  float — raw scores, arbitrary scale (e.g. 0–100 for AI Washing)
    NaN:     allowed — means "no signal for this ticker on this date"

Invariants enforced by validate_signal_frame():
    - index is DatetimeIndex (not integer or string)
    - columns are non-empty strings
    - values are float-compatible (not object dtype with strings)
    - No fully-empty column (all-NaN column = dropped ticker, log warning)
"""

WeightFrame = pd.DataFrame
"""
Output of SignalAdapter.adapt(). Portfolio-ready weights.

Schema:
    index:   pd.DatetimeIndex — same calendar as input SignalFrame, after shift(1)
             (first row will be all-NaN due to shift; rows before min_coverage met are dropped)
    columns: list[str] — universe-filtered tickers
    values:  float in [-1.0, +1.0]
             negative = short, positive = long, zero = flat
             NaN = no position (insufficient coverage date was dropped)

Invariants:
    - All non-NaN values are in [-1.0, +1.0]
    - abs(weights).sum(axis=1) <= gross_exposure_limit per row
"""
```

### Pattern 2: SignalAdapterConfig as Pydantic BaseModel

Follow `PriceSettings` pattern exactly — Pydantic BaseModel (not frozen dataclass) for config, `load_signal_adapter_config()` factory in `config.py`.

```python
# Source: fund_backtest/config.py (add alongside PriceSettings)
class SignalAdapterConfig(BaseModel):
    """Signal adapter configuration — controls normalization and coverage rules."""

    min_coverage: int = 5
    """Minimum number of tickers with non-NaN scores on a date before generating weights.
    Dates with fewer non-NaN tickers are dropped (no weights emitted for that date)."""

    gross_exposure_limit: float = 1.0
    """Maximum sum of abs(weights) per row. Weights are scaled down if exceeded."""
```

### Pattern 3: validate_signal_frame() as Standalone Function

Follow `detect_return_anomalies()` / `compute_coverage()` pattern — standalone module-level function, not a method. Returns nothing on success, raises `SignalValidationError` on failure.

```python
# Source: fund_backtest/signal/validator.py
class SignalValidationError(ValueError):
    """Raised when a SignalFrame fails contract validation.

    Always includes a descriptive message naming the exact violation.
    """

def validate_signal_frame(signal: pd.DataFrame) -> None:
    """Validate a DataFrame against the SignalFrame contract.

    Raises SignalValidationError with a descriptive message on first violation.
    Does not modify the input.

    Checks:
        1. index is DatetimeIndex
        2. columns are non-empty strings
        3. at least one column exists
        4. no all-NaN columns exist (warns and drops, does not raise)
        5. values are float-compatible dtype
    """
```

### Pattern 4: SignalAdapter Class

```python
# Source: fund_backtest/signal/adapter.py
class SignalAdapter:
    """Normalizes raw strategy scores into portfolio-ready WeightFrame.

    Pipeline:
        1. validate_signal_frame() — raises on bad input
        2. Drop all-NaN columns with warning log
        3. Cross-sectional rank within each date: rank(axis=1, pct=True) -> [0, 1]
        4. Map percentile ranks to weights: weights = 2 * ranks - 1 -> [-1, +1]
        5. Zero out rows with fewer than config.min_coverage non-NaN tickers
        6. Clip to gross_exposure_limit (scale down proportionally if sum > limit)
        7. Apply shift(1): WeightFrame row T carries signal from T-1
           (enforces look-ahead bias guarantee — signal spike on T = zero weight on T)

    The shift(1) means:
        - WeightFrame.iloc[0] is always NaN (no prior signal on first day)
        - Phase 4 Portfolio Simulator must NOT apply an additional shift
    """

    def __init__(self, config: SignalAdapterConfig | None = None) -> None:
        self._config = config or SignalAdapterConfig()
        self._log = logger.bind(component="signal_adapter")

    def adapt(self, signal: SignalFrame) -> WeightFrame:
        """Convert a raw SignalFrame into a portfolio-ready WeightFrame.

        Args:
            signal: Raw score DataFrame. Validated internally.

        Returns:
            WeightFrame with values in [-1, +1], temporally shifted by 1 day.

        Raises:
            SignalValidationError: If signal fails contract validation.
        """
```

### Critical: shift(1) Design Decision

The ARCHITECTURE.md data flow shows `shift(1)` in the Portfolio Simulator (Phase 4). Phase 3 success criterion 3 explicitly requires the Signal Adapter to emit zero weight on T from a spike on T. These are reconciled as follows:

**Adopted design:** `shift(1)` lives in Signal Adapter. The WeightFrame output is already temporally safe.
**Phase 4 implication:** Portfolio Simulator uses `weight[t-1]` implicitly because the WeightFrame was already shifted — no additional shift in Phase 4. This is equivalent mathematically.
**Why here:** The look-ahead bias guarantee is a property of the WeightFrame contract. Any code that receives a WeightFrame should be able to trust it. Putting the shift in the adapter makes this guarantee explicit at the contract boundary.

### Anti-Patterns to Avoid

- **All-NaN-column raises instead of drops:** An all-NaN column means the strategy has no signal for that ticker ever. Raising an error would break batch runs when one ticker has data gaps. Log a warning and drop silently — same pattern as `get_failed_tickers()` in the downloader.
- **Applying shift(1) twice:** Phase 4 must not shift weights again. Document in `WeightFrame` docstring and Phase 4 planning constraints.
- **Loop over dates for cross-sectional rank:** `df.rank(axis=1, pct=True)` is fully vectorized. Never `for date in df.index: df.loc[date] = ...`.
- **Modifying the input SignalFrame:** All operations must return new DataFrames. Input is read-only (immutability convention).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-sectional percentile ranking | Custom sort + divide | `df.rank(axis=1, pct=True)` | Handles NaN correctly (NaN stays NaN in rank output), vectorized across all rows at once |
| Date alignment / shift | Manual index manipulation | `df.shift(1)` | One-liner, preserves index, correctly inserts NaN row at start |
| NaN-row detection | `for r in df.iterrows()` | `df.isna().all(axis=1)` | Vectorized, returns boolean mask usable with `.loc[]` |
| Gross exposure scaling | Custom loop | `df.div(row_abs_sum, axis=0).where(abs_sum > limit, df)` | One conditional division |

**Key insight:** Every operation in the Signal Adapter is a standard pandas operation. There is no custom algorithm to write here — only composition of existing pandas primitives.

---

## Common Pitfalls

### Pitfall 1: NaN Propagation in rank()
**What goes wrong:** `df.rank(axis=1, pct=True)` with NaN values. When a row has some NaN and some non-NaN, rank correctly handles non-NaN values and leaves NaN as NaN. But if a row is ALL NaN, rank returns all NaN — which is correct behavior, but must be detected as a "no signal" row and dropped/zeroed before emitting weights.
**Why it happens:** The min_coverage check must happen AFTER ranking, not before, because ranking itself is correct with partial NaN.
**How to avoid:** After ranking, compute `non_nan_count = ranks.notna().sum(axis=1)`. Zero out rows where `non_nan_count < min_coverage`.
**Warning signs:** WeightFrame rows that are all-NaN instead of all-zero for low-coverage dates.

### Pitfall 2: shift(1) Drops First Row's Meaning
**What goes wrong:** After `shift(1)`, the first date in the WeightFrame is all-NaN. If downstream code treats NaN as zero weight, this is fine. If it treats NaN as "no data" and raises, it breaks.
**Why it happens:** `shift(1)` inserts NaN at index position 0 — there is no prior signal.
**How to avoid:** Document in WeightFrame that the first row is always NaN by design. Portfolio Simulator must handle NaN rows gracefully (treat as zero weight).
**Warning signs:** Phase 4 integration test fails on the first row of a WeightFrame.

### Pitfall 3: Float Precision in [-1, +1] Bounds Check
**What goes wrong:** `rank(pct=True)` produces values like `0.9999999999999998` due to floating-point division. After `2 * rank - 1`, this becomes `0.9999999999999996`, which is not exactly 1.0. A strict `value <= 1.0` check passes, but a test asserting `max_value == 1.0` fails.
**Why it happens:** Standard floating-point arithmetic. The rank denominator `(n - 1)` for `n` items introduces rounding.
**How to avoid:** Use `abs(weights).max() <= 1.0 + 1e-9` in assertions, not `== 1.0`. Or clip with `weights.clip(-1.0, 1.0)` after mapping.
**Warning signs:** Test failures like `AssertionError: 0.9999999999999996 != 1.0`.

### Pitfall 4: available_date vs filing_date Terminology
**What goes wrong:** The ROADMAP success criterion 1 mentions `available_date` index "strictly after the `filing_date`". This is the AI Washing Detector's concern (Phase 8), not the Signal Adapter's. The Signal Adapter only sees the `available_date`-indexed SignalFrame — it does not know about filing dates.
**Why it happens:** The success criterion conflates the Detector's output contract with the Adapter's input contract.
**How to avoid:** The Signal Adapter validates that the index is a DatetimeIndex. The responsibility for ensuring `available_date > filing_date` belongs to whoever produces the SignalFrame (the AI Washing Detector, in Phase 8). Document this boundary in `SignalFrame` docstring.
**Warning signs:** Trying to add `filing_date` as a column in the SignalFrame schema — it doesn't belong there.

---

## Code Examples

Verified patterns from pandas 3.0.1 (tested in project venv):

### Cross-Sectional Rank Normalization
```python
# Source: verified in project venv (pandas 3.0.1, numpy 2.4.3)
import pandas as pd

# input: df with arbitrary float scores, NaN allowed
ranks = df.rank(axis=1, pct=True)      # -> values in (0, 1], NaN stays NaN
weights = 2 * ranks - 1                # -> values in (-1, +1]

# clip to handle floating-point edge cases
weights = weights.clip(-1.0, 1.0)
```

### Look-Ahead Bias Guard (shift)
```python
# Source: verified in project venv
# Signal spike on T=2 (index position 2):
# df.iloc[2] = {'AAPL': 99.0, 'NVDA': 1.0}  <- extreme scores on T
# After shift(1), weights.iloc[2] = weights based on T-1 signals (not T)
# weights.iloc[3] = weights based on T signals (the spike is now T+1)

weights_shifted = weights.shift(1)   # row 0 becomes NaN
# Test assertion: weights_shifted.iloc[spike_day].abs().sum() == prior-day-sum, not spike-sum
```

### NaN-Row Zeroing (min_coverage)
```python
# Source: verified in project venv
non_nan_count = weights.notna().sum(axis=1)
low_coverage_mask = non_nan_count < config.min_coverage
# Zero out low-coverage rows (do not raise; log warning)
weights = weights.copy()
weights.loc[low_coverage_mask] = 0.0
```

### Gross Exposure Scaling
```python
# Source: pandas docs pattern
abs_sum = weights.abs().sum(axis=1)
needs_scaling = abs_sum > config.gross_exposure_limit
# Scale rows that exceed the limit (leave others unchanged)
scale_factor = config.gross_exposure_limit / abs_sum.where(needs_scaling, 1.0)
weights = weights.mul(scale_factor, axis=0)
```

### Validation Pattern (from validator.py)
```python
# Source: consistent with existing codebase error patterns
class SignalValidationError(ValueError):
    """Raised when a SignalFrame fails contract validation."""

def validate_signal_frame(signal: pd.DataFrame) -> None:
    if not isinstance(signal.index, pd.DatetimeIndex):
        raise SignalValidationError(
            f"SignalFrame.index must be DatetimeIndex, got {type(signal.index).__name__}"
        )
    if signal.columns.empty:
        raise SignalValidationError("SignalFrame must have at least one ticker column")
    if not all(isinstance(c, str) and c for c in signal.columns):
        raise SignalValidationError("All SignalFrame column names must be non-empty strings")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pandas 1.x `.rank(pct=True, na_option='keep')` | pandas 3.0.x `.rank(pct=True)` NaN handling is the same — NaN stays NaN by default | pandas 3.0 (Jan 2026) | No API change; NaN handling confirmed stable |
| Custom signal normalization per strategy | Cross-sectional rank as universal normalizer | Standard practice since ~2015 | Rank is scale-invariant; works for AI Washing 0-100, z-scores, anything |

**Deprecated/outdated:**
- `pyfolio`: Quantopian-origin, minimally maintained. Irrelevant to Phase 3 (that's Phase 5+), but noted for planning.

---

## Open Questions

1. **Gross exposure limit: scale or clip?**
   - What we know: ARCHITECTURE.md defines `gross_exposure_limit: float = 1.0` in CostConfig. The Signal Adapter receives this via `SignalAdapterConfig`.
   - What's unclear: Should rows exceeding the limit be proportionally scaled (preserves relative weights) or clipped per-ticker (changes relative weights)?
   - Recommendation: Proportional scaling. `weights = weights.mul(limit / abs_sum, axis=0).where(abs_sum > limit, weights)`. This preserves cross-sectional signal rankings.

2. **Should Signal Adapter filter to universe tickers?**
   - What we know: ARCHITECTURE.md says "Clip/reject out-of-universe tickers" is step 2 of the Signal Adapter.
   - What's unclear: Does Phase 3 need to query `universe_tickers` from the DB, or is filtering deferred to Phase 8 integration?
   - Recommendation: Accept an optional `universe_tickers: list[str] | None` parameter. If provided, drop columns not in the universe. If None (default), pass all columns through. This keeps Phase 3 database-free while supporting Phase 8.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pandas | signal normalization | Yes | 3.0.1 | — |
| numpy | pandas operations | Yes | 2.4.3 | — |
| pydantic | config model | Yes | 2.12.5 | — |
| structlog | warning logs | Yes | 25.5.0 | — |
| pytest | unit tests | Yes (venv) | 9.0.2 | — |
| PostgreSQL | none | N/A | — | Not needed for Phase 3 |

**Missing dependencies with no fallback:** None.

**Environment note:** All dependencies already in `pyproject.toml`. No new packages needed. Use `.venv/bin/python -m pytest tests/unit/` to run (66 existing + new tests).

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `backtest/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/python -m pytest tests/unit/ -x -q` |
| Full suite command | `.venv/bin/python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BT-01 | SignalFrame accepted, WeightFrame returned | unit | `.venv/bin/python -m pytest tests/unit/test_signal_adapter.py -x` | Wave 0 |
| BT-05 | Spike on T → zero weight on T, nonzero on T+1 | unit | `.venv/bin/python -m pytest tests/unit/test_signal_adapter.py::test_look_ahead_bias_guard -x` | Wave 0 |
| INT-01 | Invalid inputs raise SignalValidationError | unit | `.venv/bin/python -m pytest tests/unit/test_signal_types.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/unit/ -x -q`
- **Per wave merge:** `.venv/bin/python -m pytest tests/unit/ -q`
- **Phase gate:** Full unit suite green (no integration tests needed — no DB)

### Wave 0 Gaps
- [ ] `backtest/tests/unit/test_signal_types.py` — covers INT-01 (validation errors)
- [ ] `backtest/tests/unit/test_signal_adapter.py` — covers BT-01, BT-05 (normalization + look-ahead bias)

*(No framework install needed — pytest already installed in venv)*

---

## Project Constraints (from CLAUDE.md)

Directives from the project CLAUDE.md that the planner must enforce:

| Directive | Impact on Phase 3 |
|-----------|-------------------|
| Immutable patterns — return new objects, never mutate | All adapter operations must return new DataFrames; input `signal` is never modified in-place |
| All monetary values stored in cents (integers) | Not applicable — signal scores are floats, not monetary values |
| Validate all external data at ingestion boundaries | `validate_signal_frame()` is the ingestion boundary for strategy module signals |
| fund-backtest is completely independent from ai_washer | Signal module must have zero imports from `ai_washer` package |
| Lowercase with underscores for module/function names | `signal/adapter.py`, `validate_signal_frame()`, `signal_adapter_config` |
| Functions < 50 lines | `adapt()` method will need helper methods for each pipeline step |
| Triple-quoted docstrings on every public function/class | Required on `SignalAdapter`, `adapt()`, `validate_signal_frame()`, `SignalAdapterConfig` |
| `from __future__ import annotations` at top | Required on all new `.py` files |
| ruff (line-length=100, target-version=py312) | All new files pass `ruff check` and `ruff format` |
| 80% test coverage minimum | Two new test files required before implementation (TDD) |
| No hardcoded values — use constants or config | `min_coverage`, `gross_exposure_limit` always from `SignalAdapterConfig` |

---

## Sources

### Primary (HIGH confidence)
- pandas 3.0.1 source (installed in project venv) — `rank(axis=1, pct=True)`, `shift(1)`, `isna().all(axis=1)`, `clip()` all verified with live execution
- Project ARCHITECTURE.md — SignalFrame/WeightFrame schema, normalization pipeline, CostConfig pattern
- Project REQUIREMENTS.md — BT-01, BT-05, INT-01 requirement text
- ROADMAP.md Phase 3 success criteria — exact test assertions for look-ahead bias guard
- Existing codebase (`price/types.py`, `universe/types.py`, `config.py`) — structural patterns to replicate

### Secondary (MEDIUM confidence)
- pandas docs `DataFrame.rank()` — `pct=True`, `na_option` default behavior confirmed stable across pandas 3.x

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages installed and verified in project venv
- Architecture: HIGH — verified pandas operations with live code execution; patterns confirmed from existing codebase
- Pitfalls: HIGH — NaN propagation and float precision verified with live tests; shift(1) design decision documented with rationale

**Research date:** 2026-03-29
**Valid until:** 2026-04-29 (pandas 3.x API is stable; no fast-moving dependencies in this phase)
