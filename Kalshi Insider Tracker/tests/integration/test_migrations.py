"""Integration tests for Alembic migrations — LOG-03 (schema verification).

All tests are skipped until Plan 02 implements the database models and migrations.
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.skip(reason="DB models not yet implemented — Plan 02"),
    pytest.mark.integration,
]


def test_all_tables_created() -> None:
    """LOG-03: Alembic migration creates all expected tables with correct columns."""
    pytest.fail("Not yet implemented")
