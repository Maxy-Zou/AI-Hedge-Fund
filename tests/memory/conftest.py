"""Shared fixtures for the Phase 7 memory test suite.

Inherits db_session and sqlite_engine from the root tests/conftest.py.
Fixtures here are consumed by plans 07-01 through 07-05:

- memory_db_session: alias for the project-wide db_session (kept for clarity
  so memory tests self-document their intent).
- beliefs_tmp_dir: per-test temp directory populated with a tickers/ and
  sectors/ subtree; write tests copy fixture files into this dir so the
  originals stay immutable.
- sample_belief_yaml_path / sample_belief_human_edited_path /
  sample_belief_field_locked_path: read-only golden fixtures.
- sample_episodic_csv_path: seed CSV consumed by the episodic recall tests.
- sample_outcomes_yaml_path: outcome events consumed by the critique tests.
"""

from __future__ import annotations

import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def memory_db_session(db_session: Session) -> Session:
    """Alias for the project-wide db_session fixture (readability)."""
    return db_session


@pytest.fixture()
def sample_belief_yaml_path() -> Path:
    return FIXTURES_DIR / "belief_aapl.yaml"


@pytest.fixture()
def sample_belief_human_edited_path() -> Path:
    return FIXTURES_DIR / "belief_aapl_human_edited.yaml"


@pytest.fixture()
def sample_belief_field_locked_path() -> Path:
    return FIXTURES_DIR / "belief_aapl_field_locked.yaml"


@pytest.fixture()
def sample_episodic_csv_path() -> Path:
    return FIXTURES_DIR / "seeded_episodic.csv"


@pytest.fixture()
def sample_outcomes_yaml_path() -> Path:
    return FIXTURES_DIR / "outcomes_sample.yaml"


@pytest.fixture()
def beliefs_tmp_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Materialise a writable beliefs/ tree seeded from fixtures.

    Layout::

        <tmp>/tickers/AAPL.yaml              (copy of belief_aapl.yaml)
        <tmp>/tickers/AAPL_human.yaml        (copy of belief_aapl_human_edited.yaml)
        <tmp>/tickers/AAPL_locked.yaml       (copy of belief_aapl_field_locked.yaml)
        <tmp>/sectors/                       (empty; Plan 07-02 may seed)
    """
    tickers_dir = tmp_path / "tickers"
    tickers_dir.mkdir()
    (tmp_path / "sectors").mkdir()
    shutil.copy2(FIXTURES_DIR / "belief_aapl.yaml", tickers_dir / "AAPL.yaml")
    shutil.copy2(
        FIXTURES_DIR / "belief_aapl_human_edited.yaml",
        tickers_dir / "AAPL_human.yaml",
    )
    shutil.copy2(
        FIXTURES_DIR / "belief_aapl_field_locked.yaml",
        tickers_dir / "AAPL_locked.yaml",
    )
    yield tmp_path
