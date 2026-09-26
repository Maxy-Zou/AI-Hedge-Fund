"""Throwaway PostgreSQL databases for migration tests.

Migration tests upgrade and downgrade, so running them on the shared
``TEST_DATABASE_URL`` database leaves it at whatever head the current branch
has -- which breaks other branches' Postgres tests. Each caller instead gets a
fresh ``<shared name>_<uuid>`` database on the same server, dropped on exit.

A whole database (not a schema) because the migrations create a trigger
function and the tests count it in ``pg_proc``, which is database-wide.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine, create_engine, make_url, text

REPO_ROOT = Path(__file__).resolve().parents[1]


def _admin_engine(url: str) -> Engine:
    return create_engine(url, isolation_level="AUTOCOMMIT")


@contextmanager
def scratch_database(shared_url: str) -> Iterator[str]:
    """Yield the URL of a new, empty database; drop it (forcibly) afterwards."""
    base = make_url(shared_url)
    if not base.database or "test" not in base.database:
        raise ValueError(f"refusing to create a scratch database from non-test {base.database!r}")
    name = f"{base.database}_{uuid.uuid4().hex[:12]}"
    admin = _admin_engine(shared_url)
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        try:
            yield base.set(database=name).render_as_string(hide_password=False)
        finally:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        admin.dispose()


@contextmanager
def scratch_alembic(shared_url: str) -> Iterator[tuple[Config, str]]:
    """Alembic config pointed at a scratch database; DATABASE_URL restored on exit.

    alembic/env.py reads DATABASE_URL first, so it is set for the duration.
    """
    previous = os.environ.get("DATABASE_URL")
    try:
        with scratch_database(shared_url) as url:
            os.environ["DATABASE_URL"] = url
            yield Config(str(REPO_ROOT / "alembic.ini")), url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
