"""Database engine and session factory.

Provides functions to create SQLAlchemy engine and session factory
from a database URL. The engine uses connection pooling with pre-ping
to handle stale connections gracefully.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def get_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine with connection pooling.

    Args:
        database_url: PostgreSQL connection string
            (e.g., 'postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund').

    Returns:
        Configured SQLAlchemy Engine instance.
    """
    return create_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
    )


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine.

    Sessions created by this factory do not expire objects on commit,
    allowing continued access to loaded attributes after commit.

    Args:
        engine: SQLAlchemy Engine to bind sessions to.

    Returns:
        Configured sessionmaker instance.
    """
    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
