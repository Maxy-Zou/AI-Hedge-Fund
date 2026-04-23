"""Shared fixtures for Phase-8 Plan 08-04 CLI tests.

Re-exports the Phase-7 memory fixtures (memory_db_session + its alias
portfolio_db_session) so tests/scripts/ can exercise the run_analysis
and portfolio_view CLIs against a real in-memory SQLite session without
duplicating fixture setup.
"""

from __future__ import annotations

# Re-export the Phase-7 fixture so tests/scripts/ sees it without direct import.
from tests.memory.conftest import memory_db_session as portfolio_db_session  # noqa: F401
