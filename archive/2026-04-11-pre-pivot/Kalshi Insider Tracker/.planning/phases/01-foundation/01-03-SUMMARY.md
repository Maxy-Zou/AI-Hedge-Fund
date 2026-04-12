---
phase: 01-foundation
plan: 03
subsystem: kalshi-client
tags: [kalshi-api, rsa-auth, rate-limiting, frozen-dataclass, tdd]
dependency_graph:
  requires:
    - 01-01 (KalshiSettings config, package scaffold, structlog)
  provides:
    - kalshi_tracker.kalshi.types.MarketSnapshot (typed frozen dataclass domain contract)
    - kalshi_tracker.kalshi.client.KalshiClient (SDK facade with RSA auth + rate limiting)
    - kalshi_tracker.kalshi.client.RateLimitError (raised on token bucket exhaustion)
  affects:
    - Phase 2 (polling loop calls KalshiClient.get_politics_markets() on every tick)
    - All downstream phases consume MarketSnapshot as the canonical market data type
tech_stack:
  added:
    - cryptography>=42.0 (RSA key loading, required by kalshi-python for RSA-PSS signing)
  patterns:
    - Frozen dataclass domain contract (MarketSnapshot — immutable, hashable, equality by value)
    - Token bucket rate limiter (thread-safe, raises RateLimitError, not sleep-based)
    - SDK facade pattern (KalshiClient wraps kalshi-python, isolates auth and pagination)
    - from_sdk_market() classmethod for SDK-to-domain-object conversion
key_files:
  created:
    - Kalshi Insider Tracker/src/kalshi_tracker/kalshi/__init__.py
    - Kalshi Insider Tracker/src/kalshi_tracker/kalshi/types.py
    - Kalshi Insider Tracker/src/kalshi_tracker/kalshi/client.py
    - Kalshi Insider Tracker/tests/unit/test_market_snapshot.py
  modified:
    - Kalshi Insider Tracker/tests/unit/test_client.py (stubs replaced with 5 real tests)
    - Kalshi Insider Tracker/pyproject.toml (cryptography dependency added)
    - Kalshi Insider Tracker/uv.lock (lock updated)
decisions:
  - id: D-CLIENT-01
    summary: Token bucket (not sleep/tenacity) for rate limiting — consume() raises RateLimitError immediately rather than blocking the polling loop
  - id: D-CLIENT-02
    summary: from_sdk_market() classmethod normalizes Union[StrictFloat, StrictInt] SDK prices to int via round() — prevents float drift in stored/compared values
  - id: D-CLIENT-03
    summary: Series-by-series fetching strategy — one get_markets() call per series_ticker from allowlist; no category filter exists in Kalshi API (confirmed in RESEARCH.md)
metrics:
  duration_minutes: 4
  tasks_completed: 2
  files_created: 4
  files_modified: 3
  completed_date: "2026-04-02T23:01:48Z"
---

# Phase 01 Plan 03: Kalshi API Client and MarketSnapshot Domain Contract Summary

KalshiClient facade with RSA-PSS auth via kalshi-python SDK, token-bucket rate limiter, series-allowlist filtering, and frozen MarketSnapshot dataclass as the typed domain contract for all downstream consumers.

## What Was Built

### Task 1: MarketSnapshot frozen dataclass (TDD)

Created `src/kalshi_tracker/kalshi/types.py` with the `MarketSnapshot` frozen dataclass.

**Key implementation details:**
- `@dataclass(frozen=True)` — immutable, hashable, value-equality by default
- All price fields are `int` (cents 0-99); `from_sdk_market()` normalizes SDK `Union[StrictFloat, StrictInt]` via `int(round(...))` to prevent floating-point drift
- `from_sdk_market(market, captured_at)` classmethod is the single conversion point from SDK objects to domain objects
- `captured_at` defaults to `datetime.now(UTC)` if not provided — always UTC-aware
- Created `src/kalshi_tracker/kalshi/__init__.py` as the package root

**Test results (RED → GREEN):**
- 5 tests in `tests/unit/test_market_snapshot.py` all GREEN

### Task 2: KalshiClient facade with RSA auth, rate limiter, and politics filtering (TDD)

Created `src/kalshi_tracker/kalshi/client.py` with `KalshiClient` and `_TokenBucket`.

**Key implementation details:**
- `KalshiClient.__init__` constructs `ApiClient(Configuration(host=...))` then calls `set_kalshi_auth(key_id=..., private_key_path=...)` (DATA-01)
- `_TokenBucket` is thread-safe (uses `threading.Lock`); tokens refilled proportionally to elapsed time (not fixed windows)
- `get_politics_markets()` iterates over `settings.politics_series` allowlist, one `get_markets(series_ticker=..., status="open")` call per series (DATA-03)
- Pagination handled via `response.cursor` loop inside `_fetch_series_markets()`
- `RateLimitError` raised (not swallowed) — callers decide how to handle exhaustion
- Added `cryptography` dependency (missing transitive dep of `kalshi-python` for RSA-PSS)

**Test results (stubs → 5 GREEN):**
- `test_client_init_with_rsa_key` — DATA-01: SDK ApiClient constructed
- `test_rsa_headers_present` — DATA-01: `set_kalshi_auth()` called with correct key_id and path
- `test_markets_filtered_to_politics_series` — DATA-03: one call per allowlist series
- `test_get_politics_markets_returns_snapshots` — DATA-03: returns `list[MarketSnapshot]` with int prices
- `test_rate_limit_enforced` — DATA-05: `_TokenBucket` raises `RateLimitError` when empty

## Verification Results

```
pytest tests/unit/test_client.py  →  5 passed
pytest tests/unit/test_market_snapshot.py  →  5 passed
pytest tests/unit/  →  16 passed, 4 skipped
ruff check src/kalshi_tracker/kalshi/ tests/unit/  →  All checks passed
from kalshi_tracker.kalshi.client import KalshiClient, RateLimitError  →  OK
from kalshi_tracker.kalshi.types import MarketSnapshot  →  OK
```

## Commits

| Hash | Message |
|------|---------|
| `9dcea15` | feat(01-foundation-03): add MarketSnapshot frozen dataclass and typed domain contract |
| `116b2d3` | feat(01-foundation-03): add KalshiClient with RSA auth, rate limiter, politics filtering |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Dependency] cryptography package not in pyproject.toml**
- **Found during:** Task 2 — `from kalshi_python import ApiClient` failed with `ModuleNotFoundError: No module named 'cryptography'`
- **Issue:** `kalshi-python` SDK requires `cryptography` for RSA-PSS signing (`from cryptography.hazmat.primitives import serialization, hashes`). The package is a transitive requirement but was not declared in `pyproject.toml`.
- **Fix:** `uv add cryptography` — added explicitly to `[project.dependencies]`
- **Files modified:** `pyproject.toml`, `uv.lock`
- **Commit:** `116b2d3`

**2. [Rule 1 - Ruff fixes] ruff lint violations in generated files**
- **Found during:** Post-implementation linting
- **Issues:** UP017 (`timezone.utc` → `UTC` alias), F401 (unused `time` import in tests), F841 (unused variables in tests)
- **Fix:** `ruff check --fix` auto-applied UP017/F401; F841 fixed manually (removed `client = ` and `snapshots = ` assignments where result was not needed by test assertions)
- **Files modified:** `client.py`, `types.py`, `test_client.py`, `test_market_snapshot.py`

## Known Stubs

None — all plan deliverables are fully wired.

The 4 skipped tests in `tests/unit/test_models.py` are intentional Plan 02 stubs (ORM models not yet created). These are owned by Plan 02, not Plan 03.

## Self-Check: PASSED
