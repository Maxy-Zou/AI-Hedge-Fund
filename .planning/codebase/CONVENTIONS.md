# Coding Conventions

**Analysis Date:** 2026-03-28

## Naming Patterns

**Files:**
- Lowercase with underscores: `filing_client.py`, `entity_resolver.py`, `config.py`
- Test files: `test_*.py` (e.g., `test_config.py`, `test_normalizer.py`)
- Module files: `__init__.py`, `__main__.py` (executable entry point)
- Avoid module names that shadow stdlib: `test_models.py` not `test_model.py`

**Functions:**
- Lowercase with underscores: `normalize_company_name()`, `pad_cik()`, `resolve_entity()`
- Private functions prefixed with single underscore: `_make_filing_data()`, `_is_retryable_error()`
- Factory functions: `load_app_settings()`, `load_scoring_config()`, `create_engine_from_settings()`
- Predicate functions: `_is_retryable_error()` returns bool

**Variables:**
- Lowercase with underscores: `company_id`, `filing_date`, `market_cap_cents`
- Constants: `UPPERCASE_WITH_UNDERSCORES` (e.g., `LEGAL_SUFFIXES`, `XBRL_FACTS_URL`, `SEC_RATE_LIMIT_DELAY`)
- Private module constants: `_COLLECTOR_VERSION = "0.3.0"`, `_INTER_COMPANY_DELAY = 1.0`
- Local loop vars: `i`, `cik`, `filing` (same naming convention)

**Types:**
- Classes: `PascalCase` (e.g., `Company`, `FilingCollector`, `UniverseBuilder`, `DualTimestampMixin`)
- Dataclasses: `PascalCase` with `@dataclass(frozen=True)` (e.g., `UniverseBuildResult`, `EFTSHit`)
- Enums/TypeDicts: `PascalCase` (e.g., `ResolutionMethod`)
- Type imports: `from __future__ import annotations` at top, use `str | None` (3.10+ union syntax)

## Code Style

**Formatting:**
- Tool: `ruff` (line-length=100, target-version=py312)
- Run formatter: `ruff format src/ tests/`
- Run linter: `ruff check src/ tests/ --fix`

**Linting:**
- Tool: `ruff` with select rules: `["E", "F", "I", "N", "W", "UP", "B", "SIM"]`
  - E: PEP 8 errors
  - F: PyFlakes (unused imports, undefined names)
  - I: isort (import sorting)
  - N: PEP 8 naming conventions
  - W: Warnings (whitespace, etc)
  - UP: pyupgrade (modernize syntax)
  - B: flake8-bugbear (catch common pitfalls)
  - SIM: flake8-simplify (simplify code)
- Line length: 100 characters max

## Import Organization

**Order:**
1. `from __future__ import annotations` (at very top of file)
2. Standard library imports (stdlib)
3. Third-party imports (pip packages)
4. Local imports (ai_washer modules)

Each group separated by blank line.

**Examples from codebase:**

```python
# Standard library
from __future__ import annotations
import uuid
from datetime import date, datetime, timezone

# Third-party
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

# Local
from ai_washer.config import AppSettings, FilingCollectionSettings
from ai_washer.db.models import Company, Filing, XBRLFact
from ai_washer.ingestion.filing_client import FilingClient
```

**Path Aliases:**
- None configured in `pyproject.toml` — use full relative paths: `from ai_washer.db.models import ...`

**Relative imports in tests:**
- Test files import from installed package: `from ai_washer.config import ...` not `from ..config import ...`

## Error Handling

**Patterns:**
- Catch specific exceptions where possible, but broad `except Exception` allowed for external API calls that may raise diverse errors
- Log warning with `exc_info=True` to capture full stack trace in structlog output
- Return sensible defaults (empty list, None, empty dict) on error — don't propagate
- Retry logic via `@retry` decorator from `tenacity` package for SEC/EPA API calls

**Example from `filing_client.py`:**
```python
try:
    company = edgar.Company(cik)
except Exception:
    log.warning("filing_company_not_found", exc_info=True)
    return []

try:
    filings_collection = company.get_filings(form=form_type)
    latest = filings_collection.latest(effective_count)
except Exception:
    log.warning("filing_fetch_failed", exc_info=True)
    return []
```

**Pydantic validation errors:**
- Let `ValidationError` propagate from `load_*()` factory functions (caller handles)
- In tests: use `pytest.raises(ValidationError, match="pattern")` to verify validation works

## Logging

**Framework:** `structlog` (configured in `src/ai_washer/logging.py`)

**Patterns:**
- Import at module level: `logger = structlog.get_logger(__name__)`
- Bind contextual keys in instance methods: `self._log = logger.bind(collector="filing_collector")`
- Log events (not messages): `log.info("filing_fetch_complete", fetched=len(results))`
- Keys: `snake_case` (e.g., `accession_no`, `company_id`, `form_type`)

**Levels:**
- `log.debug()` — detailed operational info (not used yet in codebase)
- `log.info()` — major milestones (e.g., "filing_fetch_complete", "scan_date")
- `log.warning()` — expected errors that are recovered (e.g., "filing_company_not_found")
- `log.error()` — not used in favor of exceptions (let caller decide logging level)

**Example from `filing_collector.py`:**
```python
logger = structlog.get_logger(__name__)
self._log = logger.bind(collector="filing_collector")

self._log.info("filing_fetch_complete", fetched=len(results))
self._log.warning("filing_extraction_failed", accession_no=accession, exc_info=True)
```

## Comments

**When to Comment:**
- Explain *why*, not *what* (code shows what, comments explain intent)
- Lock-in decisions: D-03 (partial entity resolution), D-07 (UUID primary keys), D-08 (dual timestamps)
- Tricky algorithmic steps (e.g., longest-suffix-first ordering in `normalize_company_name()`)
- Gotchas: "Guard: if stripping would empty the name, keep original"
- Future risks: "Note: Uses DualTimestampMixin (not AppendOnlyMixin) because the PK structure is custom"

**JSDoc/Docstrings:**
- Triple-quoted docstrings on every public function/class and module
- Format: Google-style with Args, Returns, Raises sections
- Example from `filing_collector.py`:
```python
def collect_for_company(
    self,
    company_id: uuid.UUID,
    cik: str,
    ticker: str,
    collection_date: date | None = None,
) -> CollectionResult:
    """Collect filings and XBRL facts for a single company.

    Retrieves filings for each configured form type, extracts XBRL
    financial data, and persists both to the database. Skips any
    records that already exist (idempotent).

    Parameters
    ----------
    company_id:
        UUID of the Company row in the database.
    cik:
        SEC CIK number for the company.
    ticker:
        Company ticker symbol (for logging).
    collection_date:
        Date to record as observed_date. Defaults to today (UTC).

    Returns
    -------
    CollectionResult
        Counts of filings collected, XBRL facts extracted, skipped,
        and any errors encountered.
    """
```

**Module docstrings:**
- Present on every .py file (first thing after `from __future__`), explaining purpose and usage
- Example from `edgar_client.py`:
```python
"""EDGAR company facts client for EntityPublicFloat and CIK-ticker mapping.

Wraps the data.sec.gov XBRL company facts API and SEC company_tickers.json
with SEC-compliant User-Agent headers, tenacity retry on transient errors,
and CIK normalization utilities.

Usage::

    with EdgarFactsClient(edgar_identity="YourCo you@example.com") as client:
        float_cents = client.get_entity_public_float("320193")
        mapping = client.get_cik_ticker_mapping()
"""
```

## Function Design

**Size:**
- Target: <50 lines per function
- Private helper methods may be slightly longer (coordinate complex steps)
- Break into smaller functions rather than nested logic

**Parameters:**
- Use explicit keyword args, not *args/**kwargs (except in decorators)
- Type hints required on all params and return values
- Use `| None` for optional types (3.10+ syntax via `from __future__ import annotations`)

**Return Values:**
- Be consistent: don't return None sometimes and empty list other times for same function
- Precedent: API calls return empty list on error (e.g., `FilingClient.get_filings()` → `[]`)
- Factory functions return the object or raise ValidationError (e.g., `load_app_settings()`)

**Example of well-designed function:**
```python
def normalize_company_name(name: str) -> str:
    """Normalize company name for entity resolution.

    Steps: strip, upper-case, remove commas/periods, collapse spaces,
    strip legal suffix, guard against empty result.

    Args:
        name: Raw company name (e.g., "Meta Platforms, Inc.")

    Returns:
        Normalized name (e.g., "META PLATFORMS")
    """
```

## Module Design

**Exports:**
- Define `__all__` when a module has many internals (e.g., test fixture factories)
- Example from tests: functions prefixed with `_` are private, not in `__all__`
- Public classes/functions: no prefix

**Barrel Files:**
- `src/ai_washer/db/__init__.py` exports `Base` for import convenience
- `src/ai_washer/ingestion/__init__.py` exists but may stay empty (imports are explicit)
- Keep barrel imports shallow (one or two levels max)

**Dataclasses and Frozen Immutability:**
- Use `@dataclass(frozen=True)` for immutable result objects: `UniverseBuildResult`, `EFTSHit`
- Example:
```python
@dataclass(frozen=True)
class UniverseBuildResult:
    """Immutable result of a universe build operation."""
    scan_date: date
    company_count: int
    new_count: int
    updated_count: int
    deactivated_count: int
    skipped_no_market_cap: int
```

**Pydantic BaseModel:**
- Use for configuration and validated input/output: `AppSettings`, `SignalWeights`, `FilingData`
- Always validate: add `@model_validator` for cross-field checks
- Example from `config.py`:
```python
class SignalWeights(BaseModel):
    """Signal weights for composite scoring. All weights must sum to 1.0."""
    sec_filing: float = 0.20
    # ...

    @model_validator(mode="after")
    def _check_weights_sum(self) -> SignalWeights:
        total = sum([self.sec_filing, self.patent_gap, ...])
        if abs(total - 1.0) > 0.001:
            msg = f"Signal weights must sum to 1.0 (got {total:.4f})"
            raise ValueError(msg)
        return self
```

**SQLAlchemy ORM models:**
- Use `mapped_column()` with type hints (SQLAlchemy 2.0 style)
- No mutation: models are append-only or immutable by design
- Example from `models.py`:
```python
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    ticker: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False
    )
```

---

*Convention analysis: 2026-03-28*
