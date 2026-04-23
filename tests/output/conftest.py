"""Shared fixtures for Phase-8 output tests.

Reuses the Phase-7 memory_db_session via re-export from tests.memory.conftest --
portfolio_view + final_signal tests need an empty EpisodicMemory table they can
seed. Keep this module thin: production-fixture seeding happens inside each
test's arrange block (tests need different row shapes).
"""

from __future__ import annotations

from pathlib import Path

# Re-export Phase-7 memory fixtures so tests/output/ sees them without direct import
from tests.memory.conftest import memory_db_session as portfolio_db_session  # noqa: F401

FIXTURES_DIR = Path(__file__).parent / "fixtures"
