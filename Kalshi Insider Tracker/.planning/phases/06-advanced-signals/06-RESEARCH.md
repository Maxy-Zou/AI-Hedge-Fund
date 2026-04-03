# Phase 6: Advanced Signals - Research

**Researched:** 2026-04-03
**Domain:** Signal detection — timing cluster anomaly, win streak feasibility
**Confidence:** HIGH (code analysis); MEDIUM (algorithm design)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

None — all choices are at Claude's discretion.

### Claude's Discretion

All implementation choices. Key constraints:

- Timing cluster detector: detect trades bunched in narrow windows before resolution
- Win streak detector: attempt implementation; if Kalshi API doesn't expose per-account history, formally document infeasibility with evidence
- Both detectors must produce confidence scores in [0, 1] (SIG-05 pattern from Phase 3)
- Both must integrate with existing SignalEngine.run() pipeline
- Both must respect existing cooldown dedup and resolution suppression

### Deferred Ideas (OUT OF SCOPE)

None — this is the final phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SIG-03 | System detects suspicious timing clusters (trades bunched before resolution) | `get_trades(ticker=..., min_ts=..., max_ts=...)` returns aggregate trade timestamps; window-density math on `captured_at` from MarketSnapshot snapshots is a pure-function detector matching existing pattern |
| SIG-04 | System detects accounts/patterns with unusual win streaks (subject to API feasibility) | **INFEASIBLE** — `Trade` model has no user/account field; `get_trades` returns anonymized market-level trades only; `get_fills` is authenticated-user-only; no per-account public endpoint exists in SDK v2.0.0 |
</phase_requirements>

---

## Summary

Phase 6 adds two detectors to the existing SignalEngine pipeline. The critical feasibility question — whether the Kalshi public API exposes per-account trade history — has been definitively answered by direct SDK source inspection.

**Win streak (SIG-04) is infeasible.** The `Trade` model in kalshi-python SDK v2.0.0 contains exactly six fields: `trade_id`, `ticker`, `price`, `count`, `taker_side`, `created_time`. There is no user, account, member, or trader identifier. The `/markets/trades` endpoint returns aggregate market-level trades with no attribution. The only per-user fill data is in `/portfolio/fills`, which returns fills for the authenticated account only — not any other account. No public leaderboard, user history, or per-account endpoint exists in the SDK. This is not a gap in the current research; it is the complete picture of what the API exposes.

**Timing cluster (SIG-03) is fully feasible** using only data already collected: `MarketSnapshot.captured_at` and `MarketSnapshot.volume_24h` from the existing polling loop. The core idea is detecting density spikes in trade-volume timestamps within a rolling lookback window before a market's `close_time`. This follows the exact same stateless-detector pattern as `VolumeSpikeDetector` and `PriceMoveDetector`.

**Primary recommendation:** Implement `TimingClusterDetector` as a pure-function stateless detector; formally document SIG-04 infeasibility in code as a `WinStreakDetector` stub with a clear `INFEASIBLE` docstring and a skipped test explaining the SDK evidence.

---

## SIG-04 Feasibility Finding (CRITICAL)

### SDK Evidence — Win Streak Is Infeasible

**Source:** Direct inspection of installed SDK at `.venv/lib/python3.13/site-packages/kalshi_python/`

**Trade model fields** (`kalshi_python/models/trade.py` — complete field list):
```python
__properties: ClassVar[List[str]] = [
    "trade_id",   # opaque string ID
    "ticker",     # market ticker
    "price",      # int/float cents
    "count",      # quantity
    "taker_side", # 'yes' or 'no'
    "created_time" # datetime
]
```
No `user_id`, `account_id`, `member_id`, `trader_id`, or any account identifier. Confirmed absent.

**Public trades endpoint** (`/markets/trades` via `MarketsApi.get_trades`):
- Parameters: `limit`, `cursor`, `ticker`, `min_ts`, `max_ts`
- Returns: paginated list of `Trade` objects (anonymized, no per-account attribution)
- Verdict: aggregate market activity only

**Per-user fills endpoint** (`/portfolio/fills` via `PortfolioApi.get_fills`):
- Returns fills for the **authenticated user only**
- No `user_id` parameter — cannot query another account's fills
- Verdict: self-only, not useful for detecting other traders' win streaks

**No other relevant endpoints in SDK:**
- `api_keys_api.py`, `communications_api.py`, `events_api.py`, `exchange_api.py`
- `milestones_api.py`, `multivariate_collections_api.py`, `series_api.py`
- `structured_targets_api.py`

None of these contain leaderboard, user history, or per-account trade data.

**Confidence:** HIGH — based on complete enumeration of all SDK API modules and every model field.

### Correct Implementation for SIG-04

Implement a `WinStreakDetector` stub that:
1. Documents infeasibility with SDK evidence in its docstring
2. Has `detect() -> None` always (signals nothing — correct behavior)
3. Is NOT registered in `SignalEngine._detectors` (so it never fires)
4. Has a test that asserts `detect()` returns `None` and documents why

This satisfies the success criterion: "formally documented as infeasible with API evidence."

---

## Timing Cluster Detector Design (SIG-03)

### What "Timing Cluster" Means Here

A timing cluster is a surge in trade activity (measured via volume increments) concentrated in a narrow time window before market resolution. Unlike the volume spike detector (which compares rolling z-scores on `volume_24h`), the timing cluster detector asks: "is volume accumulating **unusually fast** in the pre-close window?"

Key distinction from `VolumeSpikeDetector`:
- VolumeSpike: Is right now's volume unusually high vs. its own rolling baseline?
- TimingCluster: Is volume **growth rate** concentrated in a suspicious narrow window before close?

### Available Data

From `MarketSnapshot` (already in DB):
- `captured_at` — timestamp of each poll snapshot (every 5-10 seconds)
- `volume_24h` — rolling 24h volume at time of capture
- `ticker` — market identifier

From `Market` ORM model:
- `close_time` — resolution timestamp (already used by `_is_suppressed`)

**There is no raw trades stream available.** Volume increments must be inferred by differencing consecutive `volume_24h` values.

### Algorithm Design

```
volume_delta(t) = volume_24h[t] - volume_24h[t-1]    (if > 0; clamp to 0)

recent_window  = snapshots in last `cluster_minutes` minutes
lookback_window = snapshots in last `lookback_minutes` minutes (includes recent)

recent_volume  = sum of volume_delta in recent_window
total_volume   = sum of volume_delta in lookback_window

If total_volume == 0: return None (no activity at all)

concentration = recent_volume / total_volume

# Optional proximity weighting: bonus if close_time is near
# (This is additive, not a gate — SIG-03 does not suppress near resolution, 
# unlike the engine's resolution blackout which fires on Gate 2)

confidence = clamp((concentration - cluster_threshold) / (1 - cluster_threshold), 0.0, 1.0)
```

**Parameters:**
- `cluster_minutes: int = 30` — recent window length (trade burst window)
- `lookback_minutes: int = 120` — baseline comparison window
- `cluster_threshold: float = 0.6` — fraction of volume that must be in recent window to fire
- `min_snapshots: int = 12` — guard: require at least 12 snapshots in lookback window (2 minutes at 10s polling)
- `min_total_volume: int = 10` — guard: require at least 10 volume units to avoid noise on dead markets

**Confidence formula:** Linear scale from `cluster_threshold` (0.0) to 1.0 (100% concentration).

### Interaction with Resolution Suppression

The engine's Gate 2 (`_is_suppressed`) already suppresses ALL signals within `resolution_blackout_minutes` (default 30 min) of close. The timing cluster detector does NOT need its own resolution suppression — it will never fire in the final 30 minutes anyway. The detector can legitimately fire at 31-120 minutes before close.

**No changes needed to SignalEngine gating logic.**

### Integration with SignalEngine

The detector integrates identically to existing detectors:

1. Add to `detectors.py` alongside `VolumeSpikeDetector` and `PriceMoveDetector`
2. Add new `SignalSettings` fields for the three configurable parameters
3. Add to `SignalEngine.__init__`'s default detector list (alongside existing two)
4. `_fetch_snapshots` already fetches enough data — just need to ensure `lookback_minutes * (60/poll_interval)` is within the fetch limit

**Fetch limit concern:** Current `_fetch_snapshots` fetches `max(volume_window, price_window) + 1` = 61 snapshots. At 10s polling, 61 snapshots = ~10 minutes. The timing cluster needs `lookback_minutes=120` = ~720 snapshots at 10s. The fetch limit must be extended to accommodate the timing cluster window.

**Fix:** Update `_fetch_snapshots` to also include the timing cluster lookback in its `max()` calculation. This is a one-line change in `engine.py`.

### Snapshots Passed to Detector

The engine passes snapshots already sorted oldest-first (from `_fetch_snapshots`'s reversal). The timing cluster detector receives the same list and needs only `captured_at` and `volume_24h`.

### Config Fields to Add to SignalSettings

```python
# In kalshi_tracker/config.py SignalSettings class:
cluster_minutes: int = 30           # KALSHI_SIGNAL_CLUSTER_MINUTES
cluster_lookback_minutes: int = 120  # KALSHI_SIGNAL_CLUSTER_LOOKBACK_MINUTES
cluster_threshold: float = 0.6      # KALSHI_SIGNAL_CLUSTER_THRESHOLD
cluster_min_volume: int = 10        # KALSHI_SIGNAL_CLUSTER_MIN_VOLUME
```

---

## Standard Stack

No new dependencies required. All needed libraries are already installed:

| Library | Purpose | Already in pyproject.toml |
|---------|---------|--------------------------|
| numpy | Array math for volume delta computation | Yes |
| structlog | Debug logging on detection | Yes |
| pytest | Test framework | Yes |
| freezegun | Time-mocking for timestamp-sensitive tests | Yes |

**No new packages to install.**

---

## Architecture Patterns

### Detector Pattern (from existing code)

All detectors follow this contract:
```python
class XxxDetector:
    """Docstring describing algorithm."""

    def __init__(self, param1: float = default, ...) -> None:
        """Store config, bind to logger."""
        self.param1 = param1

    def detect(self, snapshots: list) -> DetectionResult | None:
        """
        Args:
            snapshots: List of objects with attributes. Oldest first.
        Returns:
            DetectionResult if anomaly detected, None otherwise.
        """
        # Guards first (return None early)
        # Algorithm
        # Return DetectionResult(signal_type=..., confidence=..., details={...})
```

Key invariants from existing detectors:
- **Stateless**: no DB I/O, no mutation, no side effects
- **Duck-typed input**: works with ORM rows and MagicMock (tests use MagicMock)
- **confidence in [0, 1]**: always clamped with `min(max(..., 0.0), 1.0)`
- **details dict**: must contain the raw statistics used to compute confidence
- **Guards return None**: insufficient data, zero denominators, below threshold

### WinStreakDetector Stub Pattern

```python
class WinStreakDetector:
    """Win streak signal — INFEASIBLE with Kalshi public API.

    The Kalshi /markets/trades endpoint returns anonymized Trade objects with
    no user/account identifier (fields: trade_id, ticker, price, count,
    taker_side, created_time). The /portfolio/fills endpoint returns fills for
    the authenticated user only. No public per-account trade history exists
    in kalshi-python SDK v2.0.0.

    This class is a formal infeasibility stub satisfying SIG-04's success
    criterion: "formally documented as infeasible with API evidence."
    It is NOT registered in SignalEngine and will never fire.
    """

    def detect(self, snapshots: list) -> DetectionResult | None:
        """Always returns None — infeasible without per-account trade history."""
        return None
```

### File Structure

```
src/kalshi_tracker/signals/
├── detectors.py      # Add TimingClusterDetector + WinStreakDetector here
├── engine.py         # One-line fix to _fetch_snapshots limit
└── types.py          # No changes needed

src/kalshi_tracker/config.py   # Add 4 new SignalSettings fields

tests/unit/signals/
├── conftest.py        # snapshot_factory already has captured_at; may add cluster helper
├── test_detectors.py  # Add timing cluster tests; add win streak infeasibility test
└── test_engine.py     # Add timing cluster registration test
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Volume differencing | Custom derivative library | `arr[1:] - arr[:-1]` with numpy |
| Confidence clamping | Custom saturating math | `min(max(val, 0.0), 1.0)` — matches existing pattern exactly |
| Timestamp windowing | Custom time-range filter | `[s for s in snapshots if s.captured_at >= cutoff]` — simple list comprehension |

---

## Common Pitfalls

### Pitfall 1: Timing Cluster Fires on Resolution-Day Noise (Pitfall M-07)

**What goes wrong:** Everyone piles into a market in the final hour before resolution. This looks like a timing cluster but is normal behavior.

**Why it happens:** The timing cluster inherently detects concentration before close — which is also what resolution-day activity looks like.

**How to avoid:** The engine's existing `resolution_blackout_minutes=30` gate (Gate 2) already suppresses signals within 30 minutes of close. Ensure the timing cluster's `lookback_minutes` doesn't extend so far back that the "recent window" is always within the 30-min blackout (it won't — 30-min burst window fires at 31+ min before close). **No additional handling needed** — Gate 2 covers this.

**Warning signs:** Timing cluster signals only ever appear in the Signal table at 29-35 minutes before close. If so, `cluster_minutes` should be reduced.

### Pitfall 2: Volume Delta Spikes on Market Open / Data Gaps

**What goes wrong:** When the poller restarts, the first snapshot after a data gap shows a huge `volume_24h` delta (24 hours of real volume accumulated during downtime). This produces a spurious timing cluster signal.

**Why it happens:** `volume_24h` is a rolling 24h total. A 2-hour gap followed by a snapshot doesn't mean 2 hours of trades happened in 30 seconds.

**How to avoid:** Add a guard: if `delta > volume_24h * 0.5` for any single step (i.e., more than 50% of 24h volume in one poll interval), treat that delta as suspicious and clamp it to 0 or skip the window. Alternatively, require minimum `min_snapshots` spread across the full `lookback_minutes` range to ensure no large gaps.

**Warning signs:** Timing cluster fires immediately after system restart or poller recovery.

### Pitfall 3: fetch_snapshots Limit Too Small for Timing Cluster

**What goes wrong:** `SignalEngine._fetch_snapshots` fetches `max(volume_window, price_window) + 1 = 61` rows. At 10s polling, that's only 10 minutes. The timing cluster needs 120 minutes of data = ~720 rows. The detector receives too few snapshots and always returns None.

**Why it happens:** The fetch limit was designed for the existing two detectors. Adding a third with a longer lookback requires updating the limit.

**How to avoid:** Change `_fetch_snapshots` to:
```python
# engine.py — _fetch_snapshots
lookback_snapshots = (self._settings.cluster_lookback_minutes * 60) // 10 + 1
limit = max(
    self._settings.volume_window,
    self._settings.price_window,
    lookback_snapshots,
) + 1
```
This is backward-compatible — existing detectors receive more snapshots than needed (they slice `[-(window+1):]` themselves).

### Pitfall 4: Negative Volume Deltas From API

**What goes wrong:** `volume_24h` occasionally decreases between polls (API normalizes or resets). `volume_delta = volume_24h[t] - volume_24h[t-1]` becomes negative.

**Why it happens:** The 24h rolling window rolls off old volume as time passes. A large trade from 24h ago dropping off the window can cause apparent decreases.

**How to avoid:** Clamp all deltas: `delta = max(volume_24h[t] - volume_24h[t-1], 0)`. A decrease cannot represent a trade happening now, so 0 is the correct floor.

---

## Code Examples

### TimingClusterDetector Skeleton

```python
# Source: derived from existing VolumeSpikeDetector pattern in detectors.py
class TimingClusterDetector:
    """Detect suspicious concentration of trading activity before resolution.

    Computes volume growth rate in a recent `cluster_minutes` window vs.
    a longer `lookback_minutes` baseline. High concentration (>= cluster_threshold)
    suggests unusual pre-resolution activity.

    Formula:
        deltas = [max(v[t] - v[t-1], 0) for t in range(1, len)]
        recent_volume = sum of deltas where captured_at >= now - cluster_minutes
        total_volume = sum of all deltas in lookback window
        concentration = recent_volume / total_volume  (if total_volume > 0)
        confidence = clamp((concentration - threshold) / (1 - threshold), 0, 1)

    Guards:
        - Returns None if fewer than min_snapshots in lookback window
        - Returns None if total_volume < min_total_volume (dead market)
        - Returns None if concentration <= cluster_threshold
    """

    def __init__(
        self,
        cluster_minutes: int = 30,
        lookback_minutes: int = 120,
        cluster_threshold: float = 0.6,
        min_total_volume: int = 10,
    ) -> None:
        self.cluster_minutes = cluster_minutes
        self.lookback_minutes = lookback_minutes
        self.cluster_threshold = cluster_threshold
        self.min_total_volume = min_total_volume

    def detect(self, snapshots: list) -> DetectionResult | None:
        # Implementation follows guards-then-algorithm pattern
        ...
```

### SignalEngine \_fetch_snapshots Fix

```python
# engine.py — _fetch_snapshots (one-line change)
def _fetch_snapshots(self, ticker: str, session: Session) -> list:
    lookback_snapshots = (self._settings.cluster_lookback_minutes * 60) // 10 + 1
    limit = max(
        self._settings.volume_window,
        self._settings.price_window,
        lookback_snapshots,
    ) + 1
    rows = (
        session.query(OrmSnapshot)
        .filter(OrmSnapshot.ticker == ticker)
        .order_by(OrmSnapshot.captured_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))
```

### Test Pattern for Timing Cluster

```python
# Uses snapshot_factory from conftest.py — captured_at already set sequentially
# (10s spacing by default)
def make_cluster_snapshots(
    lookback_count: int = 720,     # 120 min at 10s = 720 snaps
    burst_count: int = 180,        # 30 min burst (recent window)
    baseline_vol: int = 10,        # trickle volume in baseline
    burst_vol: int = 100,          # surge volume in burst
) -> list:
    volumes = [baseline_vol] * (lookback_count - burst_count) + [burst_vol] * burst_count
    prices = [50] * lookback_count
    return snapshot_factory("CLUSTER-TEST-1", volumes, prices)
```

### WinStreak Infeasibility Test

```python
def test_win_streak_infeasible_stub() -> None:
    """WinStreakDetector.detect() always returns None.

    SIG-04 is infeasible: Kalshi /markets/trades returns anonymized Trade objects
    with no account identifier (SDK v2.0.0 Trade fields: trade_id, ticker, price,
    count, taker_side, created_time). /portfolio/fills is self-only.
    See: .venv/lib/python3.13/site-packages/kalshi_python/models/trade.py
    """
    from kalshi_tracker.signals.detectors import WinStreakDetector
    detector = WinStreakDetector()
    assert detector.detect([]) is None
```

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0+ |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/signals/ -x -q` |
| Full suite command | `uv run pytest --cov=kalshi_tracker --cov-report=term-missing` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SIG-03 | TimingClusterDetector fires when burst volume exceeds threshold | unit | `uv run pytest tests/unit/signals/test_detectors.py -k cluster -x` | ❌ Wave 0 |
| SIG-03 | TimingClusterDetector returns None on insufficient snapshots | unit | same | ❌ Wave 0 |
| SIG-03 | TimingClusterDetector returns None on dead market (zero volume) | unit | same | ❌ Wave 0 |
| SIG-03 | TimingClusterDetector registered and runs in SignalEngine | unit | `uv run pytest tests/unit/signals/test_engine.py -k cluster -x` | ❌ Wave 0 |
| SIG-03 | _fetch_snapshots fetches enough rows for lookback window | unit | same | ❌ Wave 0 |
| SIG-04 | WinStreakDetector.detect() always returns None (infeasibility stub) | unit | `uv run pytest tests/unit/signals/test_detectors.py -k win_streak -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/unit/signals/ -x -q`
- **Per wave merge:** `uv run pytest --cov=kalshi_tracker --cov-report=term-missing`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

Tests are added as part of TDD — write tests first (RED), implement to pass (GREEN). Existing `test_detectors.py` will be extended (not replaced). Existing `conftest.py` `snapshot_factory` is sufficient — may add a `cluster_snapshot_factory` helper for cleaner test setup.

---

## Environment Availability

Step 2.6: SKIPPED — this phase is purely code changes. No external services, databases, or CLIs beyond what's already configured in the project.

---

## Open Questions

1. **Polling interval assumption in fetch limit**
   - What we know: snapshots are 5-10 seconds apart; `_fetch_snapshots` uses a fixed row count
   - What's unclear: if polling interval is 5s, 720 rows = 60 min, not 120 min
   - Recommendation: Use time-based filtering instead of row count to make lookback_minutes exact. `captured_at >= now - timedelta(minutes=lookback_minutes)` avoids the polling-interval assumption entirely. This is a cleaner approach for TimingClusterDetector.detect() — filter by timestamp inside the detector rather than relying on the row count from the engine.

2. **Should WinStreakDetector be registered at all?**
   - What we know: It always returns None; registering it adds a no-op to every tick
   - What's unclear: Whether the planner prefers it registered (for completeness/documentation) or excluded
   - Recommendation: Do NOT register it in SignalEngine defaults. The infeasibility stub should live in `detectors.py` for documentation purposes but be absent from the active detector list.

---

## Sources

### Primary (HIGH confidence)

- Direct SDK source inspection: `.venv/lib/python3.13/site-packages/kalshi_python/models/trade.py` — confirmed Trade model has no account identifier
- Direct SDK source inspection: `.venv/lib/python3.13/site-packages/kalshi_python/api/markets_api.py` — confirmed `get_trades` parameters (no user filter)
- Direct SDK source inspection: `.venv/lib/python3.13/site-packages/kalshi_python/api/portfolio_api.py` — confirmed `get_fills` is self-only, no user_id parameter
- `src/kalshi_tracker/signals/detectors.py` — existing detector pattern (stateless, duck-typed, confidence formula)
- `src/kalshi_tracker/signals/engine.py` — SignalEngine gating, `_fetch_snapshots`, `_is_on_cooldown`
- `src/kalshi_tracker/signals/types.py` — DetectionResult contract
- `src/kalshi_tracker/config.py` — SignalSettings fields, existing thresholds
- `tests/unit/signals/conftest.py` — snapshot_factory, mock_session, WarmupTracker fixtures

### Secondary (MEDIUM confidence)

- `PITFALLS.md` Pitfall M-07 — resolution-day timing cluster false positive (training-data-sourced, applies directly)
- `FEATURES.md` — anti-feature: "Per-account win-streak tracking via scraping" explicitly excluded
- `STATE.md` accumulated decisions — confirm SIG-04 was flagged as API-uncertain from roadmap phase

---

## Metadata

**Confidence breakdown:**
- SIG-04 infeasibility: HIGH — complete SDK enumeration, definitive
- SIG-03 algorithm design: MEDIUM — derived from existing patterns, logic is sound, but cluster_threshold default (0.6) may need tuning in production
- Fetch limit fix: HIGH — derived directly from existing engine code
- Architecture patterns: HIGH — exact copy of established patterns in this codebase

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable SDK, 30-day window)
