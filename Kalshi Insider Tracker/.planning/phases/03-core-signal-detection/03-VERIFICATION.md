---
phase: 03-core-signal-detection
verified: 2026-04-03T11:53:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
gaps: []
human_verification: []
---

# Phase 03: Core Signal Detection Verification Report

**Phase Goal:** The system detects volume spikes and sharp price movements and scores them with confidence values
**Verified:** 2026-04-03T11:53:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                       | Status     | Evidence                                                                                    |
|----|--------------------------------------------------------------------------------------------|------------|---------------------------------------------------------------------------------------------|
| 1  | System computes per-market rolling volume baselines and flags snapshots exceeding z-score   | VERIFIED   | `VolumeSpikeDetector.detect()` in `detectors.py` computes z-score on `volume_24h[-window:]` |
| 2  | System detects sharp price movements relative to market's recent range                     | VERIFIED   | `PriceMoveDetector.detect()` in `detectors.py` computes `move_pct = abs(curr-prev)/range`  |
| 3  | Every detected signal produces a numeric confidence score between 0 and 1                  | VERIFIED   | Both detectors clamp confidence via `min(max(..., 0.0), 1.0)`; test `test_confidence_clamped` confirms 1.0 |
| 4  | System suppresses signals on resolution day during the final resolution window              | VERIFIED   | `_is_suppressed()` in `engine.py` returns True when within `blackout_minutes` of `close_time`; Gate 2 in `run()` |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact                                          | Expected                                              | Status     | Details                                                             |
|---------------------------------------------------|-------------------------------------------------------|------------|---------------------------------------------------------------------|
| `src/kalshi_tracker/signals/__init__.py`          | Package init for signals module                       | VERIFIED   | Exists; empty package marker                                        |
| `src/kalshi_tracker/signals/types.py`             | `DetectionResult` frozen dataclass                    | VERIFIED   | `@dataclass(frozen=True)` with `signal_type`, `confidence`, `details` |
| `src/kalshi_tracker/signals/detectors.py`         | `VolumeSpikeDetector` and `PriceMoveDetector`         | VERIFIED   | Both classes present; 200 lines, substantive implementations         |
| `src/kalshi_tracker/signals/engine.py`            | `SignalEngine` with 4-gate orchestration              | VERIFIED   | 223 lines; warmup gate, suppression gate, cooldown gate, min-confidence gate |
| `src/kalshi_tracker/daemon/poller.py`             | `make_poll_tick()` extended with `signal_engine` param | VERIFIED   | `signal_engine: SignalEngine | None = None` added; `_get_close_times()` present |
| `src/kalshi_tracker/config.py`                    | `SignalSettings` with 7 threshold fields              | VERIFIED   | All 7 fields present with correct defaults and `KALSHI_SIGNAL_` prefix |
| `tests/unit/signals/test_detectors.py`            | 6 tests for VolumeSpikeDetector and PriceMoveDetector | VERIFIED   | 6 test functions; all 6 GREEN                                       |
| `tests/unit/signals/test_engine.py`               | 6 tests for SignalEngine gates                        | VERIFIED   | 6 test functions; all 6 GREEN                                       |

---

### Key Link Verification

| From                                       | To                                          | Via                                                    | Status  | Details                                                              |
|--------------------------------------------|---------------------------------------------|--------------------------------------------------------|---------|----------------------------------------------------------------------|
| `signals/detectors.py`                     | `signals/types.py`                          | `from kalshi_tracker.signals.types import DetectionResult` | WIRED  | Line 25 of detectors.py                                             |
| `signals/engine.py`                        | `signals/detectors.py`                      | `from kalshi_tracker.signals.detectors import PriceMoveDetector, VolumeSpikeDetector` | WIRED | Line 26 of engine.py |
| `signals/engine.py`                        | `db/models.py`                              | `Signal` row construction and `session.add()`          | WIRED   | Lines 146-153 of engine.py; `session.add(signal_row)` confirmed     |
| `signals/engine.py`                        | `daemon/warmup.py`                          | `self._warmup.is_warmed_up(ticker)`                    | WIRED   | Line 106 of engine.py; Gate 1                                       |
| `daemon/poller.py`                         | `signals/engine.py`                         | `signal_engine.run(ticker, close_time=...)`            | WIRED   | Lines 138-150 of poller.py; TYPE_CHECKING guard for import          |
| `tests/unit/signals/test_detectors.py`     | `signals/detectors.py`                      | `from kalshi_tracker.signals.detectors import ...`     | WIRED   | Line 16 of test_detectors.py                                        |
| `tests/unit/signals/test_engine.py`        | `signals/engine.py`                         | `from kalshi_tracker.signals.engine import SignalEngine` | WIRED | Line 23 of test_engine.py                                           |

---

### Data-Flow Trace (Level 4)

| Artifact                          | Data Variable  | Source                                       | Produces Real Data      | Status    |
|-----------------------------------|----------------|----------------------------------------------|-------------------------|-----------|
| `signals/engine.py` — `run()`     | `snapshots`    | `_fetch_snapshots()` → DB query `OrmSnapshot` | Yes — `ORDER BY captured_at DESC LIMIT N` | FLOWING |
| `signals/engine.py` — `run()`     | `result`       | `detector.detect(snapshots)`                 | Yes — real computation from snapshots | FLOWING |
| `signals/engine.py` — `run()`     | `signal_row`   | `Signal(ticker=..., confidence=result.confidence, ...)` | Yes — populated from DetectionResult | FLOWING |
| `signals/detectors.py`            | `confidence`   | `min(max((z_score - threshold) / threshold, 0.0), 1.0)` | Yes — computed from `volume_24h` numpy array | FLOWING |

---

### Behavioral Spot-Checks

| Behavior                                               | Command                                                                                             | Result                         | Status  |
|--------------------------------------------------------|-----------------------------------------------------------------------------------------------------|--------------------------------|---------|
| 12 signal unit tests all pass GREEN                    | `pytest tests/unit/signals/ -v`                                                                     | 12 passed in 0.58s             | PASS    |
| Full unit suite passes with no regressions             | `pytest tests/unit/ -q`                                                                             | 45 passed in 0.75s             | PASS    |
| `_is_suppressed(None, now, 30)` returns False          | Python assertion in subprocess                                                                      | Assertion passed               | PASS    |
| `_is_suppressed(20min, now, 30min)` returns True       | Python assertion in subprocess                                                                      | Assertion passed               | PASS    |
| `_is_suppressed(60min, now, 30min)` returns False      | Python assertion in subprocess                                                                      | Assertion passed               | PASS    |
| Extreme z-score clamps confidence to exactly 1.0      | Python assertion: `result.confidence == 1.0` on 100x spike                                         | Assertion passed               | PASS    |
| `DetectionResult` is immutable (frozen dataclass)      | `r.confidence = 2.0` raises exception                                                               | FrozenInstanceError raised     | PASS    |

---

### Requirements Coverage

| Requirement | Source Plan    | Description                                              | Status    | Evidence                                                                  |
|-------------|----------------|----------------------------------------------------------|-----------|---------------------------------------------------------------------------|
| SIG-01      | 03-01, 03-02, 03-03 | Volume spike detection using z-score on rolling baseline | SATISFIED | `VolumeSpikeDetector` with z-score formula; 4 tests GREEN                |
| SIG-02      | 03-01, 03-02, 03-03 | Sharp price movement detection relative to recent range  | SATISFIED | `PriceMoveDetector` with move_pct formula; 2 tests GREEN                 |
| SIG-05      | 03-01, 03-02, 03-03 | Confidence scoring in [0.0, 1.0] per detected signal     | SATISFIED | Confidence clamped in both detectors; `DetectionResult.confidence` flows to `Signal.confidence` in DB |
| SIG-06      | 03-01, 03-03        | Signal suppression during resolution blackout window     | SATISFIED | `_is_suppressed()` + Gate 2 in `SignalEngine.run()`; `test_resolution_suppression` GREEN |

---

### Anti-Patterns Found

| File                    | Line | Pattern | Severity | Impact |
|-------------------------|------|---------|----------|--------|
| None found              | —    | —       | —        | —      |

No TODOs, FIXMEs, placeholder returns, hardcoded empty data, or stub implementations found in any of the four phase artifact files. The `raw_snapshot={}` in `poller.py` line 82 is an intentional v1 decision documented in comments (not a stub).

---

### Human Verification Required

None. All observable truths for this phase can be verified programmatically. The signal detection logic is pure computation with unit test coverage; the wiring is verified via grep and test execution.

---

### Gaps Summary

No gaps. All four success criteria are satisfied:

1. **Rolling volume baselines and z-score flagging** — `VolumeSpikeDetector` uses `numpy` z-score on `volume_24h[-window:]`. Window guard (`< window + 1`) and zero-std guard prevent crashes on thin markets.

2. **Sharp price movement detection** — `PriceMoveDetector` uses `move_pct = abs(current - prev) / price_range`. Zero-range guard prevents division by zero.

3. **Numeric confidence in [0.0, 1.0]** — Both detectors clamp confidence via `min(max(..., 0.0), 1.0)`. The flat-baseline spike case correctly returns confidence=1.0 (not NaN or infinity). `DetectionResult` is a frozen dataclass ensuring immutability.

4. **Suppression on resolution day** — `_is_suppressed(close_time, now, blackout_minutes)` is a pure function returning True when `0 <= (close_time - now) <= blackout_minutes`. `SignalEngine.run()` applies it as Gate 2. Returns False when `close_time=None`.

The full signal detection pipeline is end-to-end wired: `make_poll_tick()` in `poller.py` calls `signal_engine.run(ticker, close_time=...)` after each snapshot persist, using a single SELECT IN batch query (`_get_close_times()`) to avoid N+1 lookups per ticker.

---

_Verified: 2026-04-03T11:53:00Z_
_Verifier: Claude (gsd-verifier)_
