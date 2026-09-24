"""PostgreSQL checkpointer setup and management for LangGraph.

Provides context managers for creating PostgresSaver instances that
handle connection lifecycle and automatic table creation.

The sync version uses PostgresSaver.from_conn_string (contextmanager).
The async version uses AsyncPostgresSaver.from_conn_string (asynccontextmanager).

Threat model T-03-04: PostgreSQL connection uses local docker-compose
with default credentials -- acceptable for development. Production
requires proper auth credentials from environment.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from ai_hedge_fund.config import get_settings


@contextmanager
def create_checkpointer(database_url: str | None = None) -> Iterator[PostgresSaver]:
    """Create a sync PostgresSaver checkpointer with automatic table setup.

    Only for graphs driven by sync ``invoke``. Every pipeline here runs via
    ``ainvoke``, which calls ``aget_tuple`` -- unimplemented on the sync saver
    (``NotImplementedError``) -- so use :func:`create_async_checkpointer` there.

    Use as a context manager to ensure proper connection cleanup.
    Converts SQLAlchemy-style URLs to psycopg format automatically.

    Args:
        database_url: PostgreSQL connection string. If None, uses settings.

    Yields:
        Configured PostgresSaver with checkpoint tables created.
    """
    url = database_url or get_settings().database_url
    # PostgresSaver needs psycopg connection string format (not SQLAlchemy)
    pg_url = url.replace("postgresql+psycopg://", "postgresql://")

    with PostgresSaver.from_conn_string(pg_url) as checkpointer:
        checkpointer.setup()
        yield checkpointer


@asynccontextmanager
async def create_async_checkpointer(
    database_url: str | None = None,
) -> AsyncIterator[AsyncPostgresSaver]:
    """Create an async PostgresSaver checkpointer with automatic table setup.

    Use as an async context manager to ensure proper connection cleanup.
    Converts SQLAlchemy-style URLs to psycopg format automatically.

    Args:
        database_url: PostgreSQL connection string. If None, uses settings.

    Yields:
        Configured AsyncPostgresSaver with checkpoint tables created.
    """
    url = database_url or get_settings().database_url
    pg_url = url.replace("postgresql+psycopg://", "postgresql://")

    async with AsyncPostgresSaver.from_conn_string(pg_url) as checkpointer:
        await checkpointer.setup()
        yield checkpointer
