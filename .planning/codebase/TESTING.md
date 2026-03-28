# Testing Patterns

**Analysis Date:** 2026-03-28

## Test Framework

**Runner:**
- Framework: `pytest` >=9.0
- Config: `pyproject.toml` [tool.pytest.ini_options]
- Test discovery: `tests/` directory with `test_*.py` files

**Assertion Library:**
- `pytest` assertions (built-in): `assert x == y`, `assert x is None`
- Pydantic `ValidationError`: `pytest.raises(ValidationError, match="pattern")`

**Run Commands:**
```bash
# Run all tests
pytest

# Unit tests only (skip integration)
pytest -m "not integration"

# Integration tests only
pytest -m integration

# Watch mode (requires pytest-watch plugin — not in current deps)
pytest --watch

# Coverage report
pytest --cov=src/ai_washer --cov-report=term-missing

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

## Test File Organization

**Location:**
- Co-located pattern: `tests/` parallel to `src/`
- Structure mirrors source: `tests/unit/test_config.py` tests `src/ai_washer/config.py`
- Separation: `tests/unit/` for unit tests, `tests/integration/` for integration tests

**Naming:**
- Test files: `test_*.py` (pytest discovery)
- Test functions: `def test_*():` (pytest discovery)
- Test classes: `class Test*:` (pytest discovery, groups related tests)

**Structure:**
```
tests/
├── conftest.py                 # Shared fixtures (autouse, monkeypatch, tmp_path)
├── unit/
│   ├── __init__.py
│   ├── test_config.py          # Tests for src/ai_washer/config.py
│   ├── test_normalizer.py      # Tests for src/ai_washer/entity/normalizer.py
│   ├── test_universe_builder.py
│   └── ...
├── integration/
│   ├── conftest.py             # DB fixtures (postgres_container, db_session)
│   ├── test_schema.py          # Schema validation tests
│   ├── test_migrations.py      # Alembic migration tests
│   └── test_company_lifecycle.py
└── __init__.py
```

## Test Structure

**Suite Organization:**
```python
# From tests/unit/test_normalizer.py

class TestNormalizeCompanyName:
    """Parametrized tests for standard company name normalization."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ALPHABET INC", "ALPHABET"),
            ("Meta Platforms, Inc.", "META PLATFORMS"),
            # ... more cases
        ],
        ids=[
            "alphabet_inc",
            "meta_platforms_comma_inc_dot",
            # ... more ids
        ],
    )
    def test_normalize(self, raw: str, expected: str) -> None:
        assert normalize_company_name(raw) == expected


class TestEdgeCases:
    """Tests for edge cases in company name normalization."""

    def test_empty_string(self) -> None:
        assert normalize_company_name("") == ""

    def test_whitespace_only(self) -> None:
        assert normalize_company_name("   ") == ""
```

**Patterns:**
- Parametrized tests for many input/output combinations (use `@pytest.mark.parametrize`)
- Group related tests in `TestSomething` classes for organization
- Separate classes for happy path vs edge cases
- Each test is independent (no ordering dependency)

**Fixtures:**
- Module-level fixtures in `conftest.py` (shared across tests)
- Function fixtures (default scope) for test-local data
- `autouse=True` for cross-cutting setup (e.g., `_set_test_env` monkeypatches env vars)

Example from `tests/conftest.py`:
```python
@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch, tmp_path):
    """Set required env vars for tests that load AppSettings."""
    monkeypatch.setenv(
        "AI_WASHER_DATABASE_URL",
        "postgresql+psycopg://localhost:5432/ai_washer_test",
    )
    monkeypatch.setenv("AI_WASHER_EDGAR_IDENTITY", "TestCorp test@example.com")


@pytest.fixture
def scoring_yaml(tmp_path):
    """Create a temporary scoring.yaml for config tests."""
    yaml_content = (
        "weights:\n"
        "  sec_filing: 0.20\n"
        # ... content
    )
    yaml_file = tmp_path / "scoring.yaml"
    yaml_file.write_text(yaml_content)
    return yaml_file
```

## Mocking

**Framework:** `unittest.mock` (stdlib), decorated with `@patch`

**Patterns:**
```python
from unittest.mock import MagicMock, call, patch

class TestFilingCollectorForCompany:
    @patch("ai_washer.ingestion.filing_collector.XBRLExtractor")
    @patch("ai_washer.ingestion.filing_collector.FilingClient")
    @patch("ai_washer.ingestion.filing_collector.get_session_factory")
    @patch("ai_washer.ingestion.filing_collector.create_engine_from_settings")
    def test_collect_for_company(
        self,
        mock_engine_factory,
        mock_session_factory,
        mock_filing_client,
        mock_xbrl_extractor,
    ):
        """Patch all external dependencies, test orchestrator logic."""
        # Setup mocks
        mock_session_factory.return_value = MagicMock()
        mock_filing_client.return_value.get_filings.return_value = [...]

        # Exercise
        collector = FilingCollector(app_settings=settings)
        result = collector.collect_for_company(...)

        # Assert
        assert result.filings_collected > 0
        mock_filing_client.return_value.get_filings.assert_called_once()
```

**Fixture factories (not unittest.mock):**
```python
def _make_filing_data(
    accession_no: str = "0001234567-26-000001",
    form_type: str = "10-K",
) -> FilingData:
    """Build a FilingData fixture with sensible defaults."""
    return FilingData(
        accession_no=accession_no,
        form_type=form_type,
        # ... more fields
    )

def _make_company_mock(
    company_id: uuid.UUID | None = None,
    ticker: str = "TEST",
) -> MagicMock:
    """Build a mock Company object."""
    company = MagicMock()
    company.id = company_id or uuid.uuid4()
    company.ticker = ticker
    return company
```

**What to Mock:**
- External API clients (EFTS, EDGAR, filing client)
- Database session factory (allow injection, patch construction)
- Heavyweight dependencies (XBRLExtractor with torch/model loading)
- Current time (via `freezegun` for date-dependent logic)

**What NOT to Mock:**
- Pydantic models (validate real parsing)
- Configuration loading (test real YAML/env resolution)
- SQLAlchemy engine/session (use testcontainers PostgreSQL for integration tests)
- Pure utility functions (test directly, no mock needed)

## Fixtures and Factories

**Test Data:**
```python
# From tests/unit/test_filing_collector.py

def _make_filing_data(
    accession_no: str = "0001234567-26-000001",
    form_type: str = "10-K",
    filing_date: date = date(2026, 1, 15),
    period_of_report: date | None = date(2025, 12, 31),
) -> FilingData:
    """Build a FilingData fixture."""
    return FilingData(
        accession_no=accession_no,
        form_type=form_type,
        filing_date=filing_date,
        period_of_report=period_of_report,
        sections=FilingSections(
            business="Business description " * 100,
            risk_factors="Risk factors text " * 100,
            mda="Management discussion " * 100,
        ),
        content_hash="abc123hash",
        entity_name="Test Corp",
    )

# Usage in test
def test_collect_for_company_stores_filings(monkeypatch):
    filing = _make_filing_data()  # Get a realistic test filing
    # ... use filing in test
```

**Location:**
- Private factories (`_make_*` functions) defined in test file or `conftest.py`
- Helpers used across multiple tests go in `conftest.py`
- Test-specific factories stay in `test_*.py` file

**Database Fixtures (integration tests):**
```python
# From tests/integration/conftest.py

@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL container for the test session."""
    _ensure_docker_host()
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def db_url(postgres_container):
    """Get the database URL from the running container."""
    url = postgres_container.get_connection_url()
    url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
    return url


@pytest.fixture
def db_session(db_engine):
    """Create a database session that rolls back after each test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()
```

## Coverage

**Requirements:**
- Target: 80%+ (per global testing rules)
- Not enforced in CI yet (baseline is 0%)

**View Coverage:**
```bash
pytest --cov=src/ai_washer --cov-report=term-missing
# Shows line-by-line uncovered lines:
#   src/ai_washer/config.py:45: missing
```

**Coverage config in pyproject.toml:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
markers = [
    "integration: integration tests requiring PostgreSQL (deselect with '-m not integration')",
]
```

## Test Types

**Unit Tests** (`tests/unit/`):
- Scope: Single function or class in isolation
- Mock all external dependencies
- Fast: <1 second per test, <10 seconds total
- Example: `test_normalize_company_name()` tests the normalization logic in `entity/normalizer.py` with many parametrized inputs
- Coverage: Each code path, edge cases (empty string, whitespace, guard conditions)

**Integration Tests** (`tests/integration/`):
- Scope: Multiple components working together (e.g., schema creation, data persistence)
- Use real PostgreSQL database (via testcontainers)
- Marker: `@pytest.mark.integration` (run with `pytest -m integration` or skip with `-m "not integration"`)
- Setup: Alembic migrations run once per session (`_run_migrations` fixture)
- Teardown: Each test rolls back via transaction savepoint (no manual cleanup needed)
- Example: `test_insert_company_and_query()` verifies Company model can persist and retrieve data

**E2E Tests:**
- Not yet present in codebase
- Would test full pipeline: CLI invocation → universe scan → filing collection → score persistence
- Likely via CLI integration tests (invoking `ai-washer` commands)

## Common Patterns

**Async Testing:**
- Codebase is sync-first (SQLAlchemy session, httpx.Client, not async/await)
- No async tests currently (pytest-asyncio not in deps)
- Future: If async methods added, use `pytest-asyncio` with `@pytest.mark.asyncio`

**Error Testing:**
```python
def test_app_settings_requires_database_url(monkeypatch):
    monkeypatch.delenv("AI_WASHER_DATABASE_URL", raising=False)
    monkeypatch.delenv("AI_WASHER_EDGAR_IDENTITY", raising=False)
    from ai_washer.config import AppSettings

    with pytest.raises(ValidationError):
        AppSettings()


def test_signal_weights_rejects_bad_sum():
    from ai_washer.config import SignalWeights

    with pytest.raises(ValidationError, match="sum"):
        SignalWeights(
            sec_filing=0.50,
            patent_gap=0.50,
            earnings_call=0.50,
            job_posting=0.25,
            github_activity=0.10,
            compute_spending=0.10,
        )
```

**Time-dependent Testing (freezegun):**
```python
from freezegun import freeze_time

def test_collection_metadata_timestamp():
    with freeze_time("2026-03-28"):
        result = collector.collect_for_company(...)
        assert result.collection_metadata["collected_at"] == "2026-03-28T00:00:00Z"
```

**Monkeypatch for Config:**
```python
def test_app_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("AI_WASHER_DATABASE_URL", "postgresql+psycopg://db:5432/test")
    monkeypatch.setenv("AI_WASHER_EDGAR_IDENTITY", "TestCo test@test.com")
    from ai_washer.config import AppSettings

    settings = AppSettings()
    assert settings.database_url == "postgresql+psycopg://db:5432/test"
    assert settings.edgar_identity == "TestCo test@test.com"
```

## Test Markers and Organization

**Marker: integration**
```python
pytestmark = pytest.mark.integration  # Applied to all tests in module

def test_schema_correctness(db_engine):
    """This test requires PostgreSQL (marked integration)."""
    ...
```

**Run subsets:**
```bash
# Unit tests only
pytest -m "not integration"

# Integration tests only
pytest -m integration

# All tests
pytest
```

---

*Testing analysis: 2026-03-28*
