# Phase 2: Data Pipeline - Research

**Researched:** 2026-04-03
**Domain:** APScheduler polling daemon, MarketSnapshot persistence, warm-up state management
**Confidence:** HIGH (all core patterns verified against live sources and existing Phase 1 code)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- APScheduler with IntervalTrigger(seconds=10) for the polling loop — NOT Prefect or cron
- Each poll: call KalshiClient.get_politics_markets() → persist MarketSnapshot rows to DB
- Warm-up period: collect N snapshots per market before allowing signals (configurable threshold)
- Rate limiter already built into KalshiClient (Phase 1) — poller must respect it
- Single-process synchronous daemon — no async, no message queues for v1
- Append-only MarketSnapshot persistence (Phase 1 ORM models already enforce this)

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and fund-wide conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None — infrastructure phase stayed within scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-02 | System polls Kalshi API every 5-10 seconds for market data | APScheduler BackgroundScheduler + IntervalTrigger(seconds=10) with coalesce=True, max_instances=1 |
| DATA-04 | System persists market snapshots (price, volume, order book) to database on each poll | Phase 1 MarketSnapshot ORM model + AppendOnlyMixin already complete; polling job writes one row per market per tick |
| DATA-06 | System collects baseline data during warm-up period before any signals fire | In-memory warmup_counts dict tracks per-market snapshot count; configurable threshold in AppSettings |
</phase_requirements>

---

## Summary

Phase 2 builds the polling daemon on top of the Phase 1 foundation. The core work is three tasks: (1) wire APScheduler's BackgroundScheduler to call `KalshiClient.get_politics_markets()` every 10 seconds, (2) persist each returned `MarketSnapshot` (domain dataclass) to the `market_snapshots` DB table via the Phase 1 ORM, and (3) maintain per-market snapshot counters to enforce the warm-up period before Phase 3 signals can fire.

The Phase 1 code is fully compatible with all three tasks. `KalshiClient.get_politics_markets()` already returns `list[kalshi_tracker.kalshi.types.MarketSnapshot]` (frozen dataclass). The ORM model `db.models.MarketSnapshot` (which is a different object — the SQLAlchemy row) already has the `AppendOnlyMixin`. The polling job's responsibility is to translate one to the other and commit. The warm-up state lives entirely in memory; it does not need a DB table because it is reset on process restart (which is the correct behavior — a fresh process should re-collect baseline data).

The daemon process is started via a new `start` command in the existing Typer CLI (`cli.py`). The scheduler runs as a BackgroundScheduler so the main thread can handle SIGTERM/SIGINT for graceful shutdown.

**Primary recommendation:** BackgroundScheduler + IntervalTrigger(seconds=10) + in-process warm-up counter dict. No new DB tables needed. Add `apscheduler>=3.11.0` and `freezegun` (dev) to pyproject.toml.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| apscheduler | 3.11.2 (latest) | Interval polling daemon | Locked decision. Provides drift correction, error isolation, and clean shutdown. Current version verified against PyPI. |
| sqlalchemy | >=2.0.48 (already installed) | ORM persistence | Already in pyproject.toml; Phase 1 ORM models ready. |
| psycopg[binary] | >=3.2 (already installed) | PostgreSQL sync driver | Already in pyproject.toml. |

### Supporting (test)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| freezegun | >=1.5.5 | Time mocking | Testing warm-up countdown; asserting captured_at timestamps are correct |
| pytest-asyncio | >=1.0 | Async test support | Not needed for sync daemon — but add if async paths emerge |

**Installation (only new package needed):**
```bash
uv add apscheduler>=3.11.0
uv add --dev freezegun>=1.5.5
```

**Version verification:** APScheduler 3.11.2 confirmed current as of 2026-04-03 via PyPI.

---

## Architecture Patterns

### Recommended Project Structure

```
src/kalshi_tracker/
├── daemon/
│   ├── __init__.py
│   ├── poller.py          # PollingDaemon: scheduler setup, job function, shutdown
│   └── warmup.py          # WarmupTracker: per-market snapshot counter + is_warmed_up()
├── kalshi/
│   ├── client.py          # KalshiClient (Phase 1 — unchanged)
│   └── types.py           # MarketSnapshot domain dataclass (Phase 1 — unchanged)
├── db/
│   ├── models.py          # ORM models including MarketSnapshot (Phase 1 — unchanged)
│   └── session.py         # get_session_factory() (Phase 1 — unchanged)
├── config.py              # AppSettings + KalshiSettings — add poll_interval_seconds, warmup_snapshots
└── cli.py                 # Add `start` command that creates PollingDaemon and runs it
```

### Pattern 1: BackgroundScheduler for Signal-Interruptible Main Thread

Use `BackgroundScheduler` (not `BlockingScheduler`) so the main thread can block on `signal.pause()` and respond to SIGTERM/SIGINT for clean shutdown. BlockingScheduler blocks the main thread entirely, making graceful shutdown require a separate thread — unnecessary complexity.

**Example:**
```python
# Source: APScheduler 3.x docs, verified via PyPI + kubeblogs.com guide
import signal
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = BackgroundScheduler()
scheduler.add_job(
    poll_tick,
    IntervalTrigger(seconds=10),
    id="poll_markets",
    max_instances=1,    # prevent overlap if a tick runs long
    coalesce=True,      # if ticks queued up, run only once
    misfire_grace_time=5,  # allow up to 5s late start before skipping
)
scheduler.start()

# Main thread: block until SIGTERM/SIGINT
try:
    signal.pause()
except (KeyboardInterrupt, SystemExit):
    scheduler.shutdown(wait=True)
```

### Pattern 2: Translating Domain Dataclass to ORM Row

Phase 1 produces two different `MarketSnapshot` types:
- `kalshi_tracker.kalshi.types.MarketSnapshot` — frozen dataclass (domain contract)
- `kalshi_tracker.db.models.MarketSnapshot` — SQLAlchemy ORM model (DB row)

The polling job translates one to the other. This translation belongs in the polling job (or a thin mapper), never inside the client or the ORM model.

```python
# In poller.py — the translation function
from kalshi_tracker.kalshi.types import MarketSnapshot as DomainSnapshot
from kalshi_tracker.db.models import MarketSnapshot as OrmSnapshot

def _to_orm(domain: DomainSnapshot) -> OrmSnapshot:
    """Translate domain snapshot to ORM row (no business logic here)."""
    return OrmSnapshot(
        ticker=domain.ticker,
        series_ticker=domain.series_ticker,
        yes_bid=domain.yes_bid,
        yes_ask=domain.yes_ask,
        no_bid=domain.no_bid,
        no_ask=domain.no_ask,
        last_price=domain.last_price,
        volume=domain.volume,
        volume_24h=domain.volume_24h,
        status=domain.status,
        captured_at=domain.captured_at,
        raw_snapshot={},  # v1: leave empty; populate in Phase 3 if needed
    )
```

### Pattern 3: In-Memory Warm-Up Counter

The warm-up state is an in-process dict — not a DB table. Rationale: warm-up state is transient; a restarted daemon should re-collect baseline data from scratch. A `WarmupTracker` class encapsulates this state cleanly and provides the `is_warmed_up(ticker)` predicate that Phase 3 will call.

```python
# In daemon/warmup.py
class WarmupTracker:
    """Tracks per-market snapshot count. Warm-up complete when threshold met."""

    def __init__(self, threshold: int) -> None:
        self._threshold = threshold
        self._counts: dict[str, int] = {}

    def record(self, ticker: str) -> None:
        """Increment snapshot count for ticker."""
        self._counts[ticker] = self._counts.get(ticker, 0) + 1

    def is_warmed_up(self, ticker: str) -> bool:
        """Return True if ticker has collected >= threshold snapshots."""
        return self._counts.get(ticker, 0) >= self._threshold

    def status(self) -> dict[str, int]:
        """Return copy of current counts (read-only snapshot)."""
        return dict(self._counts)
```

### Pattern 4: Config Extension for Polling Parameters

Add two new fields to `AppSettings` (not `KalshiSettings`) — they are infrastructure concerns, not API credentials:

```python
# In config.py — extend AppSettings
poll_interval_seconds: int = 10       # DATA-02: 5-10s interval
warmup_snapshots: int = 60            # DATA-06: ~10 min of data at 10s interval
```

These are in `AppSettings` with `KALSHI_TRACKER_` prefix (e.g., `KALSHI_TRACKER_POLL_INTERVAL_SECONDS=10`).

### Anti-Patterns to Avoid

- **Calling `KalshiClient` directly from the scheduler job without try/except:** APScheduler will catch and log unhandled exceptions but won't stop the scheduler. However, if `RateLimitError` is raised inside the job, it must be caught and logged — not re-raised — so the scheduler continues ticking. A bare `except Exception` in the job function is acceptable here per CLAUDE.md conventions.
- **Creating a new DB session per tick without using context manager:** Always use `with session_factory() as session:` to guarantee rollback on exception and connection return to pool.
- **Importing `kalshi_tracker.db.models.MarketSnapshot` as `MarketSnapshot` at the top level of `poller.py`:** It will shadow the domain dataclass import if both are imported as `MarketSnapshot`. Use explicit aliases: `from kalshi_tracker.db.models import MarketSnapshot as OrmSnapshot`.
- **Storing warm-up state in DB:** Over-engineering. Warm-up is intentionally process-local so a restart forces fresh baseline collection. A DB table would require migration and cleanup logic for zero benefit.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Interval polling with drift correction | `while True: time.sleep(10)` | APScheduler BackgroundScheduler | sleep() loops accumulate drift; no clean shutdown; no error isolation per tick |
| Per-job error isolation | Try/except wrapper class | APScheduler built-in | Unhandled exceptions in jobs are caught, logged, and don't kill the scheduler |
| Graceful shutdown on SIGTERM | Custom signal handler | `scheduler.shutdown(wait=True)` | APScheduler waits for running jobs to complete before stopping |

**Key insight:** The polling infrastructure itself is a solved problem with APScheduler. The only custom logic needed is the job function body (call client → translate → persist → update warmup state).

---

## Common Pitfalls

### Pitfall 1: Name Collision Between Domain and ORM MarketSnapshot

**What goes wrong:** Both `kalshi_tracker.kalshi.types` and `kalshi_tracker.db.models` define a class named `MarketSnapshot`. If both are imported without aliases, one silently shadows the other, causing `AttributeError` at runtime (e.g., ORM `MarketSnapshot` has no `from_sdk_market()` method).

**Why it happens:** Standard naming — both represent the same concept at different layers.

**How to avoid:** Always import with explicit aliases in files that need both: `from kalshi_tracker.kalshi.types import MarketSnapshot as DomainSnapshot` and `from kalshi_tracker.db.models import MarketSnapshot as OrmSnapshot`.

**Warning signs:** `AttributeError: type object 'MarketSnapshot' has no attribute 'from_sdk_market'`

### Pitfall 2: APScheduler max_instances=1 + Long Poll Duration = Missed Ticks

**What goes wrong:** If `get_politics_markets()` takes >10s (network latency, many series in allowlist), the next tick fires while the previous is still running. With `max_instances=1` (required to prevent overlapping DB writes), the second tick is treated as a misfire. If `misfire_grace_time` is too short, the tick is skipped entirely.

**Why it happens:** politics_series allowlist has multiple series; each series makes N paginated API calls; 5+ series can easily take 3-5s per poll.

**How to avoid:** Set `misfire_grace_time=30` (generous, since we want reliability over strict interval adherence). The scheduler will run the job late rather than skipping it. Log a warning if tick duration exceeds `poll_interval_seconds * 0.8` so tuning is visible.

**Warning signs:** Log line from APScheduler: `"Execution of job 'poll_markets' skipped: maximum number of running instances reached"`

### Pitfall 3: Session Not Committed Before Process Exit

**What goes wrong:** On SIGTERM, `scheduler.shutdown(wait=True)` waits for the running tick to finish. But if the tick's DB session is using `autocommit=False` (default) and the commit happens after `session.close()`, rows are silently rolled back.

**Why it happens:** SQLAlchemy sessions require explicit `.commit()`. If the tick function exits via exception after `.add_all()` but before `.commit()`, the rows are rolled back.

**How to avoid:** Always use `session.commit()` explicitly inside the `with session_factory() as session:` block, immediately after `session.add_all(orm_rows)`. Don't rely on context manager exit to commit — only exceptions trigger rollback, not normal exit (in SQLAlchemy 2.0 session context managers).

**Warning signs:** Database row count does not increase after ticks that logged "snapshots persisted" — check if commit precedes or follows session exit.

### Pitfall 4: Warm-Up Counter Not Thread-Safe

**What goes wrong:** APScheduler runs the polling job in a thread pool by default. If two ticks overlap (which `max_instances=1` prevents, but belt-and-suspenders), concurrent dict mutation can corrupt counts.

**Why it happens:** Python dict operations are not atomic in a multi-threaded context.

**How to avoid:** With `max_instances=1` this is effectively impossible, but add a `threading.Lock` to `WarmupTracker._counts` mutations if paranoia requires it. Document that single-instance scheduling is the real guard.

**Warning signs:** Warm-up counters stuck at unexpected values under load.

---

## Code Examples

Verified patterns from Phase 1 code and APScheduler 3.x:

### Complete Polling Job Function

```python
# Source: derived from Phase 1 KalshiClient + APScheduler 3.x patterns
import structlog
from kalshi_tracker.kalshi.client import KalshiClient, RateLimitError
from kalshi_tracker.kalshi.types import MarketSnapshot as DomainSnapshot
from kalshi_tracker.db.models import MarketSnapshot as OrmSnapshot
from kalshi_tracker.daemon.warmup import WarmupTracker
from sqlalchemy.orm import sessionmaker, Session

logger = structlog.get_logger(__name__)

def make_poll_tick(
    client: KalshiClient,
    session_factory: sessionmaker[Session],
    warmup: WarmupTracker,
) -> callable:
    """Factory returning the polling job function with injected dependencies."""

    def poll_tick() -> None:
        """Single poll tick: fetch markets → persist snapshots → update warmup."""
        try:
            snapshots: list[DomainSnapshot] = client.get_politics_markets()
        except RateLimitError:
            logger.warning("poll_tick_rate_limited")
            return
        except Exception:
            logger.warning("poll_tick_api_error", exc_info=True)
            return

        orm_rows = [_to_orm(s) for s in snapshots]

        try:
            with session_factory() as session:
                session.add_all(orm_rows)
                session.commit()
        except Exception:
            logger.warning("poll_tick_db_error", exc_info=True)
            return

        for snap in snapshots:
            warmup.record(snap.ticker)

        logger.info(
            "poll_tick_complete",
            snapshot_count=len(snapshots),
        )

    return poll_tick
```

### PollingDaemon Start / Stop

```python
# Source: APScheduler 3.x BackgroundScheduler pattern (verified via kubeblogs.com guide)
import signal
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

class PollingDaemon:
    def __init__(self, poll_tick_fn, poll_interval_seconds: int = 10) -> None:
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(
            poll_tick_fn,
            IntervalTrigger(seconds=poll_interval_seconds),
            id="poll_markets",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
        )

    def start(self) -> None:
        self._scheduler.start()
        logger.info("polling_daemon_started")
        try:
            signal.pause()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            self._scheduler.shutdown(wait=True)
            logger.info("polling_daemon_stopped")
```

### CLI `start` Command Extension

```python
# Source: Phase 1 cli.py pattern (Typer)
@app.command()
def start(log_level: str = "INFO") -> None:
    """Start the Kalshi insider tracking polling daemon."""
    configure_logging(log_level)
    app_settings = load_app_settings()
    kalshi_settings = load_kalshi_settings()
    engine = create_engine_from_settings(app_settings)
    session_factory = get_session_factory(engine)
    client = KalshiClient(kalshi_settings)
    warmup = WarmupTracker(threshold=app_settings.warmup_snapshots)
    poll_tick = make_poll_tick(client, session_factory, warmup)
    daemon = PollingDaemon(poll_tick, app_settings.poll_interval_seconds)
    daemon.start()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `while True: time.sleep(N)` polling loops | APScheduler BackgroundScheduler + IntervalTrigger | APScheduler 3.x (2015+) | Drift correction, error isolation, clean shutdown |
| APScheduler 4.x async-first API | APScheduler 3.x synchronous API | 4.x released but 3.x still maintained | 3.x is the right choice for sync single-process daemons; 4.x rewrote the API for asyncio-first |

**Important version note:** APScheduler 4.x is a complete API rewrite (async-first, different import paths). The project uses 3.x (`>=3.11.0`). Do NOT use 4.x patterns — they are incompatible. The `readthedocs.io/en/master` URL points to 4.x docs; use `readthedocs.io/en/3.x` or `readthedocs.io/en/stable` for 3.x docs.

**Deprecated/outdated:**
- APScheduler 4.x `AsyncScheduler`: Different import path (`from apscheduler import AsyncScheduler`). Not used here — keep to 3.x `BackgroundScheduler`.

---

## Open Questions

1. **`raw_snapshot` JSONB field in ORM MarketSnapshot**
   - What we know: The ORM `MarketSnapshot` has `raw_snapshot: Mapped[dict]` with `server_default="{}"`. The domain dataclass has no raw dict field.
   - What's unclear: Should Phase 2 populate `raw_snapshot` with the full SDK market dict for debugging/auditing? Or leave empty as currently planned?
   - Recommendation: Leave `raw_snapshot={}` in Phase 2. The field was designed for future use. Populating it requires serializing the SDK object to dict — extra complexity with no consumer yet.

2. **Market upsert vs insert-only**
   - What we know: The `Market` (entity) table is mutable and must be upserted when markets appear. The `MarketSnapshot` (time-series) table is append-only.
   - What's unclear: Should the polling job also upsert the `Market` entity table on each tick, or only insert `MarketSnapshot` rows?
   - Recommendation: Yes — the poller should upsert `Market` rows (update `status`, `last_updated`) on each tick. New markets appear in the Kalshi API over time and must be registered. Use SQLAlchemy's `merge()` or a PostgreSQL `ON CONFLICT DO UPDATE` for the `markets` table.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | ✓ | 3.12.11 | — |
| uv | Package management | ✓ | 0.11.2 | pip |
| PostgreSQL | Database | ✗ | — | Docker (`docker run postgres:16`) |
| apscheduler | Polling daemon | ✗ (not yet installed) | 3.11.2 on PyPI | — |
| pytest (via uv) | Testing | ✓ | 9.0.2 | — |
| freezegun (not yet installed) | Time mocking in tests | ✗ | 1.5.5 on PyPI | — |

**Missing dependencies with no fallback:**
- PostgreSQL: Required for integration tests and running the daemon end-to-end. Use `docker run -e POSTGRES_PASSWORD=test -p 5432:5432 postgres:16` for local development. `testcontainers[postgres]` handles this in integration tests (not in pyproject.toml yet — needs adding).

**Missing dependencies with fallback:**
- `apscheduler`: Add via `uv add apscheduler>=3.11.0` in Wave 0 (setup plan).
- `freezegun`: Add via `uv add --dev freezegun>=1.5.5` in Wave 0.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/ -m "not integration" -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-02 | Scheduler fires poll job every 10 seconds | unit | `uv run pytest tests/daemon/test_poller.py -x` | ❌ Wave 0 |
| DATA-02 | poll_tick calls KalshiClient.get_politics_markets() | unit | `uv run pytest tests/daemon/test_poller.py::test_poll_tick_calls_client -x` | ❌ Wave 0 |
| DATA-02 | poll_tick handles RateLimitError without crashing | unit | `uv run pytest tests/daemon/test_poller.py::test_poll_tick_rate_limit -x` | ❌ Wave 0 |
| DATA-04 | poll_tick persists one OrmSnapshot per domain snapshot | unit | `uv run pytest tests/daemon/test_poller.py::test_poll_tick_persists_snapshots -x` | ❌ Wave 0 |
| DATA-04 | ORM row fields match domain dataclass values | unit | `uv run pytest tests/daemon/test_poller.py::test_to_orm_mapping -x` | ❌ Wave 0 |
| DATA-06 | WarmupTracker.is_warmed_up() returns False below threshold | unit | `uv run pytest tests/daemon/test_warmup.py::test_not_warmed_up -x` | ❌ Wave 0 |
| DATA-06 | WarmupTracker.is_warmed_up() returns True at threshold | unit | `uv run pytest tests/daemon/test_warmup.py::test_warmed_up_at_threshold -x` | ❌ Wave 0 |
| DATA-04 | Snapshots accumulate in DB over multiple ticks (integration) | integration | `uv run pytest tests/daemon/test_poller.py -m integration -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/daemon/ -m "not integration" -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/daemon/__init__.py` — package init
- [ ] `tests/daemon/test_poller.py` — covers DATA-02, DATA-04
- [ ] `tests/daemon/test_warmup.py` — covers DATA-06
- [ ] `tests/conftest.py` — shared fixtures (session_factory mock, KalshiClient mock)
- [ ] Framework additions: `uv add --dev freezegun>=1.5.5`
- [ ] Framework additions: `uv add --dev testcontainers[postgres]>=4.14` (for integration tests)
- [ ] Framework additions: `uv add apscheduler>=3.11.0` (runtime)

---

## Project Constraints (from CLAUDE.md)

Directives the planner must verify compliance with:

| Directive | Source | Applies To Phase 2 |
|-----------|--------|-------------------|
| Single-process synchronous daemon | CONTEXT.md | Use BackgroundScheduler (sync), not asyncio scheduler |
| Append-only MarketSnapshot persistence | CLAUDE.md fund-wide + Phase 1 ORM | Only INSERT into market_snapshots — no UPDATE |
| Immutable data patterns | CLAUDE.md global | `_to_orm()` returns new OrmSnapshot; `WarmupTracker` returns new dict from `status()` |
| Error handling: never silently swallow | CLAUDE.md global | poll_tick must log warnings on RateLimitError and API exceptions, not pass silently |
| Validate at system boundaries | CLAUDE.md global | Config new fields (poll_interval_seconds, warmup_snapshots) validated by Pydantic with >0 validators |
| Functions < 50 lines | CLAUDE.md global | `poll_tick` body, `_to_orm`, `WarmupTracker` methods must stay under 50 lines each |
| Files < 800 lines | CLAUDE.md global | `poller.py` and `warmup.py` are thin — easily under limit |
| structlog for all logging | CLAUDE.md project | `logger = structlog.get_logger(__name__)` in `poller.py` and `warmup.py` |
| Demo API default | Phase 1 KalshiSettings | `api_base_url` defaults to demo — polling daemon runs against demo by default |
| ruff linting (100 char lines, py312 target) | CLAUDE.md project | All new files must pass `ruff check src/ tests/ --fix` |

---

## Sources

### Primary (HIGH confidence)
- Phase 1 source code (`client.py`, `models.py`, `session.py`, `config.py`, `cli.py`) — exact APIs, existing patterns, naming conventions
- APScheduler 3.11.2 on PyPI (pypi.org/project/APScheduler) — version confirmed current, feature set verified
- APScheduler kubeblogs.com guide — BackgroundScheduler + IntervalTrigger code patterns, SIGINT handling

### Secondary (MEDIUM confidence)
- WebSearch APScheduler 3.x docs — misfire_grace_time, coalesce, max_instances parameters confirmed via multiple sources

### Tertiary (LOW confidence)
- None — all material claims verified via primary or secondary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — APScheduler 3.11.2 verified on PyPI; all other packages already in pyproject.toml
- Architecture: HIGH — derived directly from Phase 1 code inspection and locked CONTEXT.md decisions
- Pitfalls: HIGH — name collision is a direct observation from the Phase 1 code; session commit pitfall is standard SQLAlchemy behavior; APScheduler version split is verified

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (APScheduler 3.x is stable; Kalshi API surface not directly used in this phase)
