"""SQLite compatibility shims.

PostgreSQL enforces FOREIGN KEY constraints unconditionally. SQLite does
not: enforcement is off unless ``PRAGMA foreign_keys = ON`` is issued on
every connection. Without this shim an FK test on the in-memory fixture
passes vacuously and PT-03 is unproven (09-PREMORTEM.md #1).

The listener is registered on the ``Engine`` *class*, so it applies to
every engine created after this module is imported -- including the
``sqlite:///:memory:`` engine in ``tests/conftest.py``. ``db/__init__.py``
imports this module for its side effect; importing anything under
``ai_hedge_fund.db`` is therefore sufficient.

No-op for every non-SQLite DBAPI connection.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from sqlalchemy import Engine, event


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
    """Turn on FK enforcement for SQLite DBAPI connections."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
