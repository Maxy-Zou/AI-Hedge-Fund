# Phase 9: Composite Scoring and Integration API - Research

**Researched:** 2026-03-29
**Domain:** Composite score aggregation, graceful degradation, Python public API design
**Confidence:** HIGH

## Summary

Phase 9 combines the six individual signal scores (already produced by `ScoringOrchestrator.score_company()`) into a single composite AI Washing Risk Score (0-100), adds risk classification bands, implements graceful degradation when signals are unavailable, writes immutable `DailyScore` rows, and exposes a clean Python API at `ai_washer.api` for downstream portfolio management modules.

The existing infrastructure is remarkably well-prepared. `ScoringOrchestrator` already calls all 6 pure scorers and returns `list[SignalResult]`. `SignalWeights` in `config.py` already validates that weights sum to 1.0. `DailyScore` ORM model already has `composite_score`, `signal_breakdown`, `confidence`, `weights_used`, and `run_id` columns. The `scoring.yaml` config already has `high_risk_threshold` (60) and `low_risk_threshold` (30). This phase is primarily composition and API surface -- no new data sources, no new external dependencies, no new database tables.

**Primary recommendation:** Build a pure `compute_composite_score()` function in a new `composite_scorer.py`, extend `ScoringOrchestrator` to call it and persist `DailyScore` rows, add risk classification, then create the `ai_washer.api` module with `get_score()`, `get_latest_scores()`, and `get_score_history()` returning frozen dataclasses.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCORE-01 | Composite AI Washing Risk Score (0-100) as weighted average of 6 sub-scores with configurable weights | `SignalWeights` already defined in config.py with sum-to-1.0 validator. `DailyScore` model ready with composite_score column. Pure function computes weighted average from `list[SignalResult]` + `SignalWeights`. |
| SCORE-03 | Score interpretation thresholds: 0-30 genuine, 30-60 mixed, 60-80 significant risk, 80-100 strong short candidate | `scoring.yaml` already has `high_risk_threshold: 60` and `low_risk_threshold: 30`. Need to add a 4-band classification (current config only has 2 thresholds). Add `significant_risk_threshold: 80` or use 4-band enum. |
| SCORE-04 | Graceful degradation with re-normalized weights when data sources unavailable, plus reduced confidence indicator | Pure function filters available signals, re-normalizes their weights to sum to 1.0, computes confidence as `sum(available_weights) / 1.0`. |
| SCORE-05 | All scores immutable -- each daily run produces new snapshot rows | `DailyScore` uses `DualTimestampMixin` (append-only). Idempotency check on `(company_id, scored_at date)` before insert. |
| INT-02 | Python API: `get_score(ticker, date)`, `get_latest_scores()`, `get_score_history(ticker, start, end)` returning immutable dataclasses | New `src/ai_washer/api.py` module with frozen dataclasses and session-scoped query functions. |
| INT-03 | Structured output: composite, sub-scores, confidence, data freshness per signal, pipeline_run_id | `DailyScore.signal_breakdown` JSONB stores sub-scores. Confidence from SCORE-04. run_id already on DailyScore. Data freshness added to signal_breakdown evidence. |
</phase_requirements>

## Standard Stack

No new dependencies needed. This phase uses only existing libraries already in the project.

### Core (Already Installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | >=2.0.48 | ORM queries for DailyScore reads/writes | Already used throughout |
| Pydantic | >=2.12.5 | Data validation for API response types | Already used for all type contracts |
| structlog | >=25.5.0 | Structured logging for composite scoring events | Already used throughout |

### No New Dependencies
This phase is purely compositional -- no new packages to install.

## Architecture Patterns

### Recommended New Files
```
src/ai_washer/
  analysis/
    composite_scorer.py    # Pure function: compute_composite_score()
  api.py                   # Public API: get_score(), get_latest_scores(), get_score_history()
  api_types.py             # Frozen dataclasses for API return types
tests/unit/
  test_composite_scorer.py # Unit tests for pure composite scoring
  test_api_types.py        # Unit tests for API type contracts
  test_api.py              # Unit tests for API functions (mock session)
```

### Pattern 1: Pure Composite Scorer Function
**What:** A stateless function that takes `list[SignalResult]` + `SignalWeights` and returns a composite result with score, confidence, and breakdown.
**When to use:** Always -- keeps scoring logic testable without database.
**Example:**
```python
# src/ai_washer/analysis/composite_scorer.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CompositeResult:
    score: int                    # 0-100
    confidence: float             # 0.0-1.0
    risk_band: str                # "genuine" | "mixed" | "significant_risk" | "strong_short"
    signal_breakdown: dict        # {signal_type: score}
    weights_used: dict            # {signal_type: re-normalized weight}
    signals_available: list[str]
    signals_missing: list[str]

def compute_composite_score(
    signal_results: list[SignalResult],
    weights: SignalWeights,
    risk_thresholds: RiskThresholds,
) -> CompositeResult:
    """Pure function: weighted average with graceful degradation."""
    ...
```

### Pattern 2: Risk Band Classification
**What:** Map composite score to 4 risk bands using configurable thresholds.
**When to use:** After computing composite score.
**Key detail:** The existing config has `high_risk_threshold` (60) and `low_risk_threshold` (30). Need to add one more threshold at 80 for the 4-band classification per success criteria. Add `strong_short_threshold: 80` to `ScoringConfig`.

```python
RISK_BANDS = {
    (0, 30): "genuine",
    (30, 60): "mixed",
    (60, 80): "significant_risk",
    (80, 101): "strong_short",
}
```

### Pattern 3: Graceful Degradation via Weight Re-normalization
**What:** When fewer than 6 signals are available, re-normalize the available weights to sum to 1.0 and compute confidence as the proportion of total weight that was available.
**When to use:** Every composite score computation (handles both full and partial cases).
**Example:**
```python
# Available signals and their original weights
available = {r.signal_type: r.score for r in signal_results}
all_weights = weights.model_dump()  # {signal_type: weight}

# Map signal_type names to weight keys
SIGNAL_TO_WEIGHT = {
    "sec_filing": "sec_filing",
    "patent_gap": "patent_gap",
    "earnings_vagueness": "earnings_call",
    "job_mismatch": "job_posting",
    "github_activity": "github_activity",
    "compute_spending": "compute_spending",
}

available_weight_sum = sum(
    all_weights[SIGNAL_TO_WEIGHT[st]] for st in available
)
confidence = available_weight_sum  # Already 0.0-1.0 since weights sum to 1.0

# Re-normalize
renormalized = {
    st: all_weights[SIGNAL_TO_WEIGHT[st]] / available_weight_sum
    for st in available
}
composite = round(sum(available[st] * renormalized[st] for st in available))
```

### Pattern 4: Frozen Dataclass API Types
**What:** Return frozen dataclasses from the public API, not ORM models or dicts.
**When to use:** All `ai_washer.api` functions.
**Why:** Downstream modules get immutable, typed objects. No SQLAlchemy dependency leaks.
```python
@dataclass(frozen=True)
class CompanyScore:
    ticker: str
    company_name: str
    scored_at: datetime
    composite_score: int
    risk_band: str
    confidence: float
    signal_breakdown: dict[str, int]
    weights_used: dict[str, float]
    signals_available: list[str]
    signals_missing: list[str]
    run_id: uuid.UUID
```

### Pattern 5: Session-Accepting API Functions
**What:** API functions accept an optional `Session` parameter. If None, create one internally. This lets the API work standalone or within an existing transaction.
**When to use:** All public API functions in `ai_washer.api`.
```python
def get_score(
    ticker: str,
    score_date: date | None = None,
    *,
    session: Session | None = None,
) -> CompanyScore | None:
    """Get composite score for a company on a specific date."""
    ...
```

### Anti-Patterns to Avoid
- **Mutating SignalResult or DailyScore:** All financial data is immutable. Never update existing rows.
- **Leaking ORM objects from API:** Always convert to frozen dataclasses before returning.
- **Hard-coding weight mappings:** Use `SignalWeights` fields, not magic strings. The signal_type names in `SignalResult` differ from `SignalWeights` field names (e.g., "earnings_vagueness" vs "earnings_call") -- maintain an explicit mapping dict.
- **Skipping composite when fewer than N signals:** The spec says graceful degradation, not minimum threshold. Even 1 signal should produce a composite (with very low confidence).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Weight validation | Custom sum check | `SignalWeights` Pydantic model_validator | Already exists, validates sum to 1.0 |
| UUID generation | Manual uuid calls | `uuid.uuid4()` default on model | Consistent with all other models |
| Idempotency | Manual dedup logic | SQL EXISTS check pattern | Same pattern used in `persist_signals` |
| Datetime handling | String parsing | `datetime.fromisoformat()` + timezone-aware | Consistent with existing code |

## Common Pitfalls

### Pitfall 1: Signal Type Name Mismatch
**What goes wrong:** `SignalResult.signal_type` values ("sec_filing", "patent_gap", "earnings_vagueness", "job_mismatch", "github_activity", "compute_spending") do NOT match `SignalWeights` field names ("sec_filing", "patent_gap", "earnings_call", "job_posting", "github_activity", "compute_spending"). Note: "earnings_vagueness" != "earnings_call" and "job_mismatch" != "job_posting".
**Why it happens:** Signal types are domain names, weight keys are signal category names. They diverged organically.
**How to avoid:** Define an explicit `SIGNAL_TYPE_TO_WEIGHT_KEY` constant dict. Use it everywhere. Test it covers all 6 signals.
**Warning signs:** KeyError when looking up weights for a signal type.

### Pitfall 2: DailyScore Partition Key in PK
**What goes wrong:** DailyScore uses `RANGE (scored_at)` partitioning, requiring `scored_at` in the primary key. Inserting without considering the partition structure may fail.
**Why it happens:** PostgreSQL requires partition key in PK for partitioned tables.
**How to avoid:** Always populate `scored_at` as timezone-aware datetime. Check that a partition exists for the target month (existing migration created initial partitions).
**Warning signs:** "no partition found for row" error on INSERT.

### Pitfall 3: Confidence = 0 When No Signals Available
**What goes wrong:** If `score_company()` returns empty results (no signals at all), dividing by zero when computing confidence.
**Why it happens:** All 6 data sources may be unavailable for a newly added company.
**How to avoid:** Return None (no composite score) when zero signals are available. A composite of nothing is meaningless.
**Warning signs:** ZeroDivisionError in weight re-normalization.

### Pitfall 4: Idempotency for DailyScore Rows
**What goes wrong:** Running `score_all()` twice on the same day creates duplicate DailyScore rows.
**Why it happens:** DailyScore has no unique constraint on (company_id, scored_at::date).
**How to avoid:** Add EXISTS check before INSERT, same pattern as `persist_signals`. Check on (company_id, scored_at date).
**Warning signs:** Duplicate composite scores for same company on same day.

### Pitfall 5: scored_at is DateTime, not Date
**What goes wrong:** Comparing scored_at (DateTime with timezone) to a plain date for idempotency check.
**Why it happens:** `DailyScore.scored_at` is `DateTime(timezone=True)`, not `Date`.
**How to avoid:** Use `func.date(DailyScore.scored_at) == scoring_date` or cast to date in the query. Or use a date-range filter: `scored_at >= start_of_day AND scored_at < start_of_next_day`.
**Warning signs:** Idempotency check fails to find existing row, creates duplicate.

## Code Examples

### Composite Score Computation
```python
from ai_washer.analysis.types import SignalResult
from ai_washer.config import SignalWeights

SIGNAL_TYPE_TO_WEIGHT_KEY: dict[str, str] = {
    "sec_filing": "sec_filing",
    "patent_gap": "patent_gap",
    "earnings_vagueness": "earnings_call",
    "job_mismatch": "job_posting",
    "github_activity": "github_activity",
    "compute_spending": "compute_spending",
}

ALL_SIGNAL_TYPES = list(SIGNAL_TYPE_TO_WEIGHT_KEY.keys())

def compute_composite_score(
    signal_results: list[SignalResult],
    weights: SignalWeights,
) -> CompositeResult | None:
    if not signal_results:
        return None

    weight_dict = weights.model_dump()
    available = {r.signal_type: r.score for r in signal_results}

    available_weight_sum = sum(
        weight_dict[SIGNAL_TYPE_TO_WEIGHT_KEY[st]] for st in available
    )

    confidence = round(available_weight_sum, 4)

    renormalized = {
        st: weight_dict[SIGNAL_TYPE_TO_WEIGHT_KEY[st]] / available_weight_sum
        for st in available
    }

    raw_score = sum(available[st] * renormalized[st] for st in available)
    composite = max(0, min(100, round(raw_score)))

    missing = [st for st in ALL_SIGNAL_TYPES if st not in available]

    return CompositeResult(
        score=composite,
        confidence=confidence,
        signal_breakdown=available,
        weights_used=renormalized,
        signals_available=sorted(available.keys()),
        signals_missing=sorted(missing),
        risk_band=classify_risk_band(composite),
    )
```

### DailyScore Persistence
```python
def persist_composite(
    self,
    company_id: uuid.UUID,
    result: CompositeResult,
) -> bool:
    """Write DailyScore row, idempotent on (company_id, scored_at date)."""
    scored_at = datetime(
        self._scoring_date.year,
        self._scoring_date.month,
        self._scoring_date.day,
        tzinfo=timezone.utc,
    )

    # Idempotency: check existing
    exists_stmt = select(DailyScore).where(
        DailyScore.company_id == company_id,
        func.date(DailyScore.scored_at) == self._scoring_date,
    )
    if self._session.execute(exists_stmt).scalar_one_or_none() is not None:
        return False

    row = DailyScore(
        company_id=company_id,
        scored_at=scored_at,
        composite_score=result.score,
        signal_breakdown=result.signal_breakdown,
        confidence=result.confidence,
        weights_used=result.weights_used,
        run_id=self._run_id,
        as_of_date=self._scoring_date,
    )
    self._session.add(row)
    self._session.flush()
    return True
```

### Public API Function
```python
def get_score(
    ticker: str,
    score_date: date | None = None,
    *,
    session: Session | None = None,
) -> CompanyScore | None:
    """Retrieve composite score for a company on a date.

    Args:
        ticker: Company ticker symbol (case-insensitive).
        score_date: Date to retrieve score for. Defaults to most recent.
        session: Optional SQLAlchemy session. Creates one if not provided.

    Returns:
        CompanyScore frozen dataclass, or None if no score exists.
    """
    ...
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9.0 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/unit/ -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCORE-01 | Weighted average of 6 sub-scores produces 0-100 score | unit | `python -m pytest tests/unit/test_composite_scorer.py -x` | No -- Wave 0 |
| SCORE-03 | Risk band classification: 4 thresholds | unit | `python -m pytest tests/unit/test_composite_scorer.py::test_risk_bands -x` | No -- Wave 0 |
| SCORE-04 | Partial scores with re-normalized weights and confidence | unit | `python -m pytest tests/unit/test_composite_scorer.py::test_graceful_degradation -x` | No -- Wave 0 |
| SCORE-05 | Immutable DailyScore rows, idempotent persistence | unit | `python -m pytest tests/unit/test_composite_persistence.py -x` | No -- Wave 0 |
| INT-02 | get_score, get_latest_scores, get_score_history return dataclasses | unit | `python -m pytest tests/unit/test_api.py -x` | No -- Wave 0 |
| INT-03 | Structured output with composite, sub-scores, confidence, run_id | unit | `python -m pytest tests/unit/test_api_types.py -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_composite_scorer.py` -- covers SCORE-01, SCORE-03, SCORE-04
- [ ] `tests/unit/test_composite_persistence.py` -- covers SCORE-05
- [ ] `tests/unit/test_api.py` -- covers INT-02
- [ ] `tests/unit/test_api_types.py` -- covers INT-03

## Open Questions

1. **DailyScore Partition Coverage**
   - What we know: Migration 001 created initial partitions for daily_scores. The partitioned table uses `RANGE (scored_at)`.
   - What's unclear: How many months of partitions were pre-created. If scoring runs in a month without a partition, INSERT will fail.
   - Recommendation: Check existing migration for partition range. If needed, add partition creation logic or a migration that extends partitions through 2027.

2. **Signal Type to Weight Key Mapping**
   - What we know: Two names differ ("earnings_vagueness" vs "earnings_call", "job_mismatch" vs "job_posting").
   - What's unclear: Whether to rename for consistency or maintain the mapping.
   - Recommendation: Maintain mapping dict. Renaming signal types would break existing SignalDetail rows in the database. The mapping is a one-time constant.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `src/ai_washer/analysis/scoring_orchestrator.py` -- current orchestrator with all 6 signals
- Codebase analysis: `src/ai_washer/config.py` -- SignalWeights with sum validator, ScoringConfig with thresholds
- Codebase analysis: `src/ai_washer/db/models.py` -- DailyScore model with all required columns
- Codebase analysis: `config/scoring.yaml` -- existing weight and threshold configuration

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all existing
- Architecture: HIGH - clear extension of existing patterns (pure scorer + orchestrator + persistence)
- Pitfalls: HIGH - identified from direct codebase analysis (name mismatches, partition keys, idempotency)

**Research date:** 2026-03-29
**Valid until:** 2026-04-28 (stable -- internal composition, no external API changes)
