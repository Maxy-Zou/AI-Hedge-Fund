# Phase 3: Core Signal Detection — Research

**Researched:** 2026-04-02
**Domain:** Statistical anomaly detection on time-series prediction market data
**Confidence:** HIGH (all decisions from locked CONTEXT.md; stack verified from existing codebase)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal,
success criteria, and fund-wide conventions to guide decisions.

Key constraints from CONTEXT.md:
- Volume spike detection: per-market rolling baseline with z-score threshold (configurable)
- Price movement detection: configurable % move relative to market's recent range
- Each signal produces a confidence score between 0.0 and 1.0
- Resolution-day suppression: suppress signals during the final resolution window to avoid false positives
- Signals are computed from MarketSnapshot rows in the database
- Signal results persist to the Signal table (append-only, from Phase 1)
- scipy for statistical computations (z-score, rolling stats)
- Integration with WarmupTracker: signals should only fire after warm-up is complete

### Claude's Discretion
All implementation choices (module layout, internal function signatures, rolling window sizes, z-score
thresholds, confidence formula, integration hook into polling loop).

### Deferred Ideas (OUT OF SCOPE)
- Timing cluster detection (Phase 6)
- Win streak detection (Phase 6)
- Machine learning signal scoring (v2)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SIG-01 | System detects abnormal volume spikes relative to per-market rolling baseline | Rolling window stats on `volume_24h` column from `market_snapshots`; z-score threshold approach |
| SIG-02 | System detects sharp price movements before event resolution | Rolling range of `last_price` over recent N snapshots; % deviation from range midpoint |
| SIG-05 | Each signal produces a confidence score used for threshold-based triggering | Normalized 0.0–1.0 confidence from clamped z-score (volume) or normalized price deviation |
| SIG-06 | System suppresses signals during normal resolution-day activity (false positive filter) | Use `Market.close_time` (already in DB schema) to gate signal emission within configurable blackout window |
</phase_requirements>

---

## Summary

Phase 3 delivers the two core signal detectors (volume spike, price movement), a confidence scoring system,
and a resolution-day false positive suppression filter. All of this is built on top of `MarketSnapshot` rows
already being persisted by the Phase 2 polling daemon.

The signal detection approach is rule-based: per-market rolling statistics computed from the last N snapshots
in PostgreSQL, with z-score thresholds for volume and percentage-move thresholds for price. No ML. Every
signal write goes to the existing `Signal` ORM table (append-only, Phase 1 schema). The `WarmupTracker`
already provides the gating hook — signal detectors call `warmup.is_warmed_up(ticker)` before computing.

The integration path is straightforward: add a `run_signal_detection(ticker, snapshots, warmup, session)` call
inside the existing `poll_tick()` function, after the snapshot persistence block. The signal detector module
lives at `src/kalshi_tracker/signals/` — a new subdirectory, following the project's domain separation pattern.

**Primary recommendation:** Build two independent detector classes (`VolumeSpikeDetector`,
`PriceMoveDetector`) each with a `detect(snapshots) -> Signal | None` interface, composed by a
`SignalEngine` that handles DB reads, warmup gating, resolution-day suppression, and DB writes. Wire
`SignalEngine.run(ticker)` into `poll_tick()` after each successful snapshot persistence.

---

## Standard Stack

### Core (all already in pyproject.toml — VERIFIED from uv.lock)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | >=2.0.48 | Read snapshots, write signals | Already in stack; ORM models defined in Phase 1 |
| psycopg[binary] | >=3.2 | PostgreSQL driver | Already in stack |
| structlog | >=25.5.0 | Structured logging | Already in stack |
| Pydantic | >=2.12.5 | Signal config validation | Already in stack; all config via pydantic-settings |

### New Dependencies Required

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| pandas | >=2.0 | Rolling window statistics on snapshot history | NOT IN pyproject.toml — must add |
| numpy | >=1.26 | Z-score computation, array math | NOT IN pyproject.toml — must add |

**IMPORTANT:** scipy is listed in CONTEXT.md and STACK.md research, but Phase 3 only needs
volume z-scores and price-range deviation — both expressible with numpy/pandas. scipy is only
needed for win-streak binomial tests (Phase 6). Do NOT add scipy in Phase 3.

**pandas/numpy version note:** The system Python has numpy 1.26.4 but the venv has neither pandas
nor numpy installed. Add both to `[project.dependencies]` in `pyproject.toml`.

### Testing Dependencies (some missing from venv — must add)

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| freezegun | >=1.5.5 | Mock `datetime.now(UTC)` in signal detection | INSTALLED (7.1.0 in venv) |
| factory-boy | >=3.3 | Generate MarketSnapshot ORM rows for tests | NOT IN pyproject.toml — must add |
| pytest-cov | >=7.0 | Coverage reporting | INSTALLED (7.1.0 in venv) |

**Installation (new deps only):**
```bash
uv add pandas>=2.0 numpy>=1.26
uv add --dev factory-boy>=3.3
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/kalshi_tracker/
├── signals/                    # NEW — Phase 3
│   ├── __init__.py
│   ├── detectors.py            # VolumeSpikeDetector, PriceMoveDetector
│   ├── engine.py               # SignalEngine: orchestrates detection + DB I/O
│   └── types.py                # DetectionResult frozen dataclass
├── daemon/
│   ├── poller.py               # MODIFIED — call SignalEngine.run() after snapshot persist
│   └── warmup.py               # UNCHANGED
├── config.py                   # MODIFIED — add SignalSettings fields
└── db/
    └── models.py               # UNCHANGED — Signal table already defined
```

### Pattern 1: Detector Interface

Each detector is a pure stateless class — no DB access, no side effects. It receives a list of
`MarketSnapshot` domain objects (or ORM rows converted to a simple structure) and returns a
`DetectionResult | None`.

```python
# src/kalshi_tracker/signals/types.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class DetectionResult:
    """Output contract from a single detector. Immutable."""
    signal_type: str        # 'volume_spike' | 'price_move'
    confidence: float       # 0.0 – 1.0 (clamped)
    details: dict           # arbitrary JSON payload for Signal.details column
```

```python
# src/kalshi_tracker/signals/detectors.py
class VolumeSpikeDetector:
    def __init__(self, z_threshold: float = 2.5, window: int = 60) -> None: ...
    def detect(self, snapshots: list[SnapshotRow]) -> DetectionResult | None: ...

class PriceMoveDetector:
    def __init__(self, move_pct_threshold: float = 0.15, window: int = 60) -> None: ...
    def detect(self, snapshots: list[SnapshotRow]) -> DetectionResult | None: ...
```

### Pattern 2: SignalEngine Orchestrator

`SignalEngine` is the only class that touches the database. It:
1. Queries the last N snapshots for a given ticker
2. Checks `WarmupTracker.is_warmed_up(ticker)` — skip if not warmed up
3. Checks resolution-day suppression — skip if within blackout window
4. Runs each detector
5. Persists any `DetectionResult` to the `Signal` table

```python
# src/kalshi_tracker/signals/engine.py
class SignalEngine:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        warmup: WarmupTracker,
        settings: SignalSettings,
        detectors: list[BaseDetector] | None = None,
    ) -> None: ...

    def run(self, ticker: str, close_time: datetime | None = None) -> list[Signal]: ...
```

### Pattern 3: Integration into poll_tick()

The existing `make_poll_tick()` factory in `poller.py` accepts injected dependencies. Phase 3
adds `signal_engine` as an additional injectable parameter. After the snapshot persist block:

```python
# poller.py — make_poll_tick() extended
def make_poll_tick(
    client: KalshiClient,
    session_factory: sessionmaker[Session],
    warmup: WarmupTracker,
    signal_engine: SignalEngine | None = None,   # NEW — optional for backwards compat
) -> Callable[[], None]:
    def poll_tick() -> None:
        # ... existing snapshot fetch + persist ...
        if signal_engine is not None:
            for snap in snapshots:
                signal_engine.run(snap.ticker, close_time=???)   # see note below
    return poll_tick
```

**Note on close_time:** The `Market` table has `close_time` but `MarketSnapshot` (domain type) does
not carry it. Two options:
1. Query `Market.close_time` once per tick (extra DB query per unique ticker) — simple
2. Pass close_time through the domain snapshot (requires adding field to `MarketSnapshot`) — more coupled

**Recommendation:** Option 1. Add a `get_market_close_times(tickers, session) -> dict[str, datetime]`
helper in `engine.py`. One SELECT per poll tick (not per ticker) using `WHERE ticker IN (...)`.

### Pattern 4: Resolution-Day Suppression (SIG-06)

`Market.close_time` is already stored in the DB. Suppression logic:

```python
def _is_suppressed(close_time: datetime | None, now: datetime, blackout_minutes: int) -> bool:
    """Return True if now is within blackout_minutes before close_time."""
    if close_time is None:
        return False
    delta = close_time - now
    return timedelta(0) <= delta <= timedelta(minutes=blackout_minutes)
```

Default `blackout_minutes = 30` (configurable). This prevents copying stale trades in the final
resolution window where price is already converging to 0 or 100.

### Pattern 5: Z-Score Volume Signal (SIG-01)

```python
import numpy as np

def _compute_volume_zscore(volumes: list[int]) -> float:
    """Z-score of the latest volume vs. rolling window."""
    arr = np.array(volumes, dtype=float)
    if arr.std() == 0:
        return 0.0
    return float((arr[-1] - arr[:-1].mean()) / arr[:-1].std())
```

**Confidence formula:** `confidence = min(max((z_score - threshold) / threshold, 0.0), 1.0)`
- z=2.5 at threshold=2.5 → confidence=0.0 (just tripped)
- z=5.0 at threshold=2.5 → confidence=1.0 (double the threshold)

This produces a smooth 0–1 confidence signal proportional to how anomalous the spike is.

**What to use as volume field:** Use `volume_24h` (not lifetime `volume`). Lifetime volume is
monotonically increasing and cannot be used for rolling z-scores. `volume_24h` resets daily and
reflects current activity level. Confirmed from `MarketSnapshot.volume_24h` column in models.py.

### Pattern 6: Price Move Signal (SIG-02)

```python
def _compute_price_move_pct(prices: list[int]) -> float:
    """Fractional move of latest price relative to recent range."""
    if len(prices) < 2:
        return 0.0
    recent = prices[:-1]
    price_range = max(recent) - min(recent)
    if price_range == 0:
        return 0.0
    move = abs(prices[-1] - prices[-2])
    return move / price_range
```

**Confidence formula:** `confidence = min(move_pct / threshold, 1.0)`

**What to use as price field:** Use `last_price` (integer cents, 0–99). The mid-price
`(yes_bid + yes_ask) // 2` is an alternative but requires both sides to be non-zero, which is
not guaranteed. `last_price` is always populated.

### Pattern 7: Settings Extension (config.py)

Add a `SignalSettings` class (new class, not extending `AppSettings` — keeps concerns separated):

```python
class SignalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="KALSHI_SIGNAL_",
        extra="ignore",
    )
    volume_z_threshold: float = 2.5       # z-score threshold for volume spikes
    volume_window: int = 60               # number of snapshots in rolling window
    price_move_threshold: float = 0.15    # 15% of recent range
    price_window: int = 60                # number of snapshots for price range
    resolution_blackout_minutes: int = 30 # suppress signals this many minutes before close
    min_confidence: float = 0.0           # minimum confidence to persist signal (0 = persist all)
```

### Anti-Patterns to Avoid

- **Computing rolling stats in Python loops:** Use `numpy` array slicing, not a Python `for` loop
  over snapshot rows. Numpy is orders of magnitude faster and avoids off-by-one errors.
- **Using lifetime `volume` field for z-scores:** It is monotonically increasing — std will grow
  unbounded and z-scores will become meaningless. Always use `volume_24h`.
- **One DB query per detector per ticker:** Fetch snapshots once per ticker per tick, pass the list
  to all detectors. Avoid N+1 query patterns.
- **Suppressing ALL signals on close_time IS NULL:** Markets without a scheduled close time should
  not be suppressed. `is_suppressed()` must return `False` when `close_time is None`.
- **Confidence > 1.0 or < 0.0:** Always clamp. Floating-point edge cases (std ≈ 0) can produce
  NaN or infinity. Guard all divisions; clamp output to [0.0, 1.0].
- **Signal fires during warmup:** `WarmupTracker.is_warmed_up()` already exists. Phase 3 MUST
  check it. The rolling window requires at least `window` snapshots to produce meaningful stats.
  If `count < window`, skip detection silently (no signal, no log spam).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rolling mean/std | Manual accumulator loop | `numpy` array operations | Accumulator has precision drift, numpy is tested at scale |
| Z-score math | Custom formula | `numpy` array ops `(x - mean) / std` | Same formula — but numpy handles edge cases (NaN, zero std) more robustly when paired with guards |
| Array bounds/slicing | Manual index arithmetic | `arr[-window:]` slice syntax | Python slice semantics are safe on short arrays (no IndexError) |
| DB session lifecycle | Manual `try/finally` | `with session_factory() as session:` | Context manager already handles rollback on exception — proven in Phase 2 |
| Confidence clamping | Custom clamp function | `min(max(val, 0.0), 1.0)` | One-liner, no import needed, avoid reinventing |

**Key insight:** The statistical operations are trivial enough that pandas DataFrames would be
overkill for per-market detection. Use numpy array slices directly for performance and simplicity.
Pandas adds value only if you're doing cross-market analysis (not in this phase).

---

## Common Pitfalls

### Pitfall 1: volume_24h Resets at Kalshi Midnight Boundary
**What goes wrong:** `volume_24h` drops sharply to 0 at the Kalshi daily reset. A naive z-score
detector will fire a false positive "spike" when `volume_24h` suddenly jumps from 0 back to normal
trading volume.
**Why it happens:** The rolling window straddles the midnight boundary with near-zero values, making
the new day's normal volume look like an anomaly.
**How to avoid:** Add a guard: if `current_volume_24h < mean * 0.1` (i.e., the latest value is
suspiciously low), treat the window as invalid and skip detection. Or: filter snapshots to same
calendar day as the latest snapshot before computing stats.
**Warning signs:** Signals firing at Kalshi midnight UTC with `direction=down` or suspiciously low
z-scores on the previous tick.

### Pitfall 2: Zero Standard Deviation on Thin Markets
**What goes wrong:** Markets with no trading activity produce a `volume_24h` sequence of all zeros.
`std = 0`, so `z_score = (0 - 0) / 0 = NaN`.
**Why it happens:** Kalshi politics markets can go hours or days with no trades.
**How to avoid:** Guard `if std == 0: return 0.0` before the division. Never return NaN — always
return a float in [0.0, 1.0].
**Warning signs:** `NaN` or `inf` confidence values in `Signal.confidence` column.

### Pitfall 3: Rolling Window Shorter Than Required
**What goes wrong:** If a market only has 10 snapshots but the window is 60, z-score is computed
on insufficient data and the signal is statistically invalid.
**Why it happens:** WarmupTracker uses snapshot count to gate signals, but the warmup threshold
(`warmup_snapshots = 60`) may not match the rolling window (`volume_window = 60`). If they differ,
a market may be "warmed up" but the rolling window query returns fewer rows than expected.
**How to avoid:** Require `len(snapshots) >= window` before running detection. The minimum snapshots
queried from DB should equal `max(volume_window, price_window)`. Also: ensure `warmup_snapshots`
setting >= the rolling window size.
**Warning signs:** Signals from markets with only a few hours of history.

### Pitfall 4: Resolution-Day Suppression Timezone Mismatch
**What goes wrong:** `Market.close_time` is stored as UTC. If `datetime.now()` is called without
`UTC` timezone, the comparison `close_time - now` will raise `TypeError: can't subtract offset-naive
and offset-aware datetimes`.
**Why it happens:** Python datetime arithmetic requires both sides to be timezone-aware.
**How to avoid:** Always use `datetime.now(UTC)` (with UTC import from `datetime`). This is already
established project convention — `MarketSnapshot.captured_at` uses `datetime.now(UTC)`.
**Warning signs:** `TypeError` in suppression check during testing.

### Pitfall 5: N+1 Queries per Ticker
**What goes wrong:** `SignalEngine.run()` is called once per ticker per poll tick (potentially 10-50
markets). If each call opens a separate DB connection and runs multiple queries, connection pool
exhaustion occurs under sustained polling.
**Why it happens:** Naive implementation queries DB separately for each detector for each ticker.
**How to avoid:** Single query per ticker: `SELECT * FROM market_snapshots WHERE ticker = :ticker
ORDER BY captured_at DESC LIMIT :window`. Pass the result list to all detectors. Consider batching:
fetch all tickers' recent snapshots in one query with `WHERE ticker IN (...)`.
**Warning signs:** DB connection count climbing under `pg_stat_activity`, slow poll ticks (>1000ms).

### Pitfall 6: Signal Flooding on Consecutive Poll Ticks
**What goes wrong:** A genuine volume spike lasts 3-5 poll ticks (30-50 seconds). The detector fires
on every tick, producing 3-5 duplicate `Signal` rows for the same event.
**Why it happens:** Signal detectors are stateless — they don't know a signal for this ticker was
just written 10 seconds ago.
**How to avoid (Phase 3 scope):** Add a simple recency check in `SignalEngine`: query for the most
recent `Signal` for this `(ticker, signal_type)`. If one exists within the last `cooldown_seconds`
(default: 300 seconds = 5 minutes), skip writing a new one. This is a lighter version of the
deduplication that Phase 4 will enforce for trade execution.
**Warning signs:** Signal table has many rows with identical `ticker + signal_type` within the same
30-second window.

---

## Code Examples

Verified patterns from existing codebase:

### DB Session Pattern (from poller.py)
```python
# Source: src/kalshi_tracker/daemon/poller.py
with session_factory() as session:
    session.add_all(orm_rows)
    session.commit()  # explicit commit required — context manager exit does NOT commit
```

### WarmupTracker Usage (already established)
```python
# Source: src/kalshi_tracker/daemon/warmup.py
warmup.is_warmed_up(ticker)  # returns bool
warmup.record(ticker)         # increments count
```

### AppendOnlyMixin Pattern (Signal table)
```python
# Source: src/kalshi_tracker/db/models.py
Signal(
    ticker="PRES-24-DJT",
    signal_type="volume_spike",
    confidence=0.75,
    details={"z_score": 3.2, "volume_24h": 1450, "mean": 320.5, "std": 85.1},
    detected_at=datetime.now(UTC),
)
# No id needed — uuid.uuid4() default applied by AppendOnlyMixin
```

### Numpy Z-Score Pattern
```python
import numpy as np

arr = np.array([320, 315, 330, 310, 1450], dtype=float)  # last is current
baseline = arr[:-1]
current = arr[-1]
std = baseline.std()
if std == 0.0:
    z = 0.0
else:
    z = (current - baseline.mean()) / std
confidence = float(min(max((z - threshold) / threshold, 0.0), 1.0))
```

### Freezegun Pattern for Time-Sensitive Tests
```python
# Source: freezegun docs — already used in project tests
from freezegun import freeze_time
from datetime import datetime, UTC

@freeze_time("2026-01-15 10:00:00+00:00")
def test_resolution_blackout_suppresses_signal():
    close_time = datetime(2026, 1, 15, 10, 20, tzinfo=UTC)  # 20 min from now
    assert _is_suppressed(close_time, datetime.now(UTC), blackout_minutes=30) is True
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| scipy.stats.zscore | numpy manual (mean/std) | — | scipy not needed for Phase 3; numpy is sufficient and already planned |
| pandas rolling() | numpy array slicing | — | For per-market single-ticker detection, numpy slices are simpler and faster than pandas rolling windows |
| Global volume threshold | Per-market rolling z-score | v1 design | Per-market baseline prevents thin markets from never firing and liquid markets from always firing |

---

## Open Questions

1. **Should SignalEngine batch-fetch all tickers' snapshots in a single query per poll tick?**
   - What we know: Each poll tick covers 10-50 markets; separate queries per ticker are simple but scale linearly
   - What's unclear: Whether connection pool pressure becomes an issue in practice
   - Recommendation: Implement single-ticker query first (simpler, easier to test). If poll tick duration exceeds 500ms, switch to batch query. Add structured log of `elapsed_ms` to detect this early.

2. **Should `volume_24h` or a derived delta be used for z-score?**
   - What we know: `volume_24h` resets daily; using the raw value means the rolling window at day boundary is noisy
   - What's unclear: Whether the daily reset causes false positives in practice (depends on when markets are most active)
   - Recommendation: Use `volume_24h` directly in v1 with the midnight boundary guard documented above. Collect production data in Phase 2 before over-engineering.

3. **Should Signal cooldown be enforced in Phase 3 or deferred to Phase 4?**
   - What we know: Phase 4 requires EXEC-05 (signal deduplication for trade execution). Phase 3's signal flooding is a separate concern (data quality vs. execution deduplication).
   - What's unclear: Whether signal flooding creates any problems before Phase 4 is built
   - Recommendation: Implement cooldown in Phase 3 as a lightweight `max_age_seconds` query on the Signal table. It is a data quality concern independent of trade execution.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | Signal persistence | Assumed (Phase 2 used it) | Unknown — not checked in this session | — |
| Python 3.12 | Runtime | ✓ | 3.12.11 | — |
| numpy | Z-score computation | ✗ — not in venv | — | Must install: `uv add numpy>=1.26` |
| pandas | Rolling stats (optional) | ✗ — not in venv | — | Numpy array slicing is sufficient; pandas not required for Phase 3 |
| freezegun | Time-sensitive test fixtures | ✓ | 7.1.0 | — |
| factory-boy | Test data factories | ✗ — not in venv | — | Must install: `uv add --dev factory-boy>=3.3` |
| pytest-cov | Coverage reporting | ✓ | 7.1.0 | — |

**Missing dependencies with no fallback:**
- `numpy` — required for z-score computation (Wave 0: `uv add numpy>=1.26`)
- `factory-boy` — required for test fixtures generating MarketSnapshot rows (Wave 0: `uv add --dev factory-boy>=3.3`)

**Missing dependencies with fallback:**
- `pandas` — NOT required for Phase 3 (numpy array slicing is sufficient). Add only if cross-market analysis is needed in a future phase.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2+ |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `.venv/bin/python -m pytest tests/unit/signals/ -x -q` |
| Full suite command | `.venv/bin/python -m pytest tests/unit/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SIG-01 | Volume z-score > threshold produces DetectionResult | unit | `pytest tests/unit/signals/test_detectors.py::test_volume_spike_fires_above_threshold -x` | ❌ Wave 0 |
| SIG-01 | Volume below threshold returns None | unit | `pytest tests/unit/signals/test_detectors.py::test_volume_no_signal_below_threshold -x` | ❌ Wave 0 |
| SIG-01 | Zero std deviation returns 0.0 confidence (no crash) | unit | `pytest tests/unit/signals/test_detectors.py::test_volume_zero_std_guard -x` | ❌ Wave 0 |
| SIG-01 | Warmup gate blocks signal before warmup complete | unit | `pytest tests/unit/signals/test_engine.py::test_engine_skips_unwarmed_market -x` | ❌ Wave 0 |
| SIG-02 | Price move > threshold produces DetectionResult | unit | `pytest tests/unit/signals/test_detectors.py::test_price_move_fires_above_threshold -x` | ❌ Wave 0 |
| SIG-02 | Zero price range returns 0.0 confidence (no crash) | unit | `pytest tests/unit/signals/test_detectors.py::test_price_move_zero_range_guard -x` | ❌ Wave 0 |
| SIG-05 | Confidence clamped to [0.0, 1.0] | unit | `pytest tests/unit/signals/test_detectors.py::test_confidence_clamped -x` | ❌ Wave 0 |
| SIG-05 | Signal row persisted with confidence in [0.0, 1.0] | unit | `pytest tests/unit/signals/test_engine.py::test_engine_persists_signal -x` | ❌ Wave 0 |
| SIG-06 | Signal suppressed when now is within blackout of close_time | unit | `pytest tests/unit/signals/test_engine.py::test_resolution_suppression -x` | ❌ Wave 0 |
| SIG-06 | Signal NOT suppressed when close_time is None | unit | `pytest tests/unit/signals/test_engine.py::test_no_suppression_without_close_time -x` | ❌ Wave 0 |
| SIG-06 | Signal NOT suppressed when close_time > blackout window | unit | `pytest tests/unit/signals/test_engine.py::test_no_suppression_outside_blackout -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/unit/signals/ -x -q`
- **Per wave merge:** `.venv/bin/python -m pytest tests/unit/ -q`
- **Phase gate:** Full unit suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/signals/__init__.py` — new test package
- [ ] `tests/unit/signals/test_detectors.py` — unit tests for VolumeSpikeDetector and PriceMoveDetector
- [ ] `tests/unit/signals/test_engine.py` — unit tests for SignalEngine (warmup gate, suppression, persistence)
- [ ] `tests/unit/signals/conftest.py` — shared fixtures (snapshot factory, mock session)
- [ ] Framework: `uv add numpy>=1.26` — required before any detector code compiles
- [ ] Framework: `uv add --dev factory-boy>=3.3` — required for test data factories

---

## Project Constraints (from CLAUDE.md)

| Directive | Source | Impact on Phase 3 |
|-----------|--------|-------------------|
| Immutable data — return new objects, never mutate | CLAUDE.md coding-style | `DetectionResult` must be `@dataclass(frozen=True)` |
| 200–400 lines typical, 800 max per file | CLAUDE.md coding-style | `detectors.py` and `engine.py` must be separate files |
| Handle errors explicitly at every level | CLAUDE.md coding-style | All detector methods must handle ZeroDivisionError, NaN; never propagate |
| Validate all external data at system boundaries | CLAUDE.md coding-style | Snapshot lists from DB are "external" — validate len before computing |
| TDD: write tests first (RED) then implement (GREEN) | CLAUDE.md testing | Wave 0 writes RED tests; implementation in Wave 1 |
| 80%+ test coverage | CLAUDE.md testing | All detector branches (zero-std, short window, warmup gate) must be tested |
| structlog with contextual binding | KALSHI CLAUDE.md | `self._log = logger.bind(ticker=ticker, signal_type="volume_spike")` pattern |
| Pydantic settings for config | KALSHI CLAUDE.md | New `SignalSettings(BaseSettings)` class in `config.py` |
| Append-only signal writes | KALSHI CLAUDE.md (LOG-03) | Never UPDATE Signal rows — only INSERT |
| AppendOnlyMixin pattern | KALSHI CLAUDE.md | `Signal` table already uses this — honor in write path |
| Functions < 50 lines | CLAUDE.md coding-style | Each detector method must be compact |
| No hardcoded values | CLAUDE.md coding-style | All thresholds via `SignalSettings` — no magic numbers |

---

## Sources

### Primary (HIGH confidence)
- Direct code read: `src/kalshi_tracker/db/models.py` — Signal schema confirmed (ticker, signal_type, confidence float, details JSONB, detected_at)
- Direct code read: `src/kalshi_tracker/daemon/warmup.py` — WarmupTracker.is_warmed_up() interface confirmed
- Direct code read: `src/kalshi_tracker/daemon/poller.py` — make_poll_tick() factory pattern confirmed; integration point identified
- Direct code read: `src/kalshi_tracker/config.py` — AppSettings pattern confirmed; SignalSettings should follow same BaseSettings approach
- Direct code read: `src/kalshi_tracker/kalshi/types.py` — `volume_24h` and `last_price` fields confirmed in MarketSnapshot
- Bash: `uv.lock` inspection — confirmed pandas, numpy, scipy NOT installed; freezegun, pytest-cov installed

### Secondary (MEDIUM confidence)
- `.planning/phases/03-core-signal-detection/03-CONTEXT.md` — algorithm choices (z-score, % move, scipy flag)
- `.planning/research/STACK.md` — library recommendations, confidence levels
- `.planning/research/FEATURES.md` — signal dependency graph, risk notes

### Tertiary (LOW confidence)
- volume_24h midnight reset behavior — inferred from Kalshi API design knowledge; not verified from live API docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all core deps verified from pyproject.toml and uv.lock; new deps (numpy, factory-boy) flagged with install commands
- Algorithm patterns: HIGH — z-score and percentage-move are standard; code examples use only numpy (no ambiguity)
- Integration points: HIGH — poller.py and WarmupTracker code read directly; integration pattern is clear
- Pitfalls: MEDIUM — volume_24h midnight reset is inferred, not observed in production; all others are well-known numerical/threading patterns

**Research date:** 2026-04-02
**Valid until:** Stable — no external dependencies likely to change before Phase 3 implementation
