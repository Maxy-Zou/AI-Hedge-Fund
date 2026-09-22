"""Database layer -- PostgreSQL persistence with append-only patterns.

Side-effect imports below register SQLAlchemy event listeners on the
``Engine`` / ``Session`` classes. They live here, at the package root, so
that importing *anything* under ``ai_hedge_fund.db`` (which every entry
point and ``tests/conftest.py`` already do via ``db.models``) guarantees
the listeners are active in tests and production alike
(09-PREMORTEM.md #4).
"""

from ai_hedge_fund.db import sqlite_compat as _sqlite_compat  # noqa: F401
