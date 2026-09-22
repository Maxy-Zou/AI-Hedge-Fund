"""Phase 9 -- paper_trades / paper_fills schema tests (PT-01..04).

Runs on the in-memory SQLite fixture from tests/conftest.py. The very first
test is the guard that makes every later foreign-key assertion meaningful:
SQLite silently ignores FOREIGN KEY unless ``PRAGMA foreign_keys`` is on
(09-PREMORTEM.md #1).
"""

from __future__ import annotations

from sqlalchemy import Engine, text


def test_sqlite_fk_pragma_enabled(sqlite_engine: Engine) -> None:
    """09-PREMORTEM #1 guard: FK enforcement must be ON for the fixture engine.

    If this fails, every ``IntegrityError`` assertion on a foreign key in this
    suite is vacuous and PT-03 is unproven.
    """
    with sqlite_engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
