"""Database engine and session factory for Kalshi Insider Tracker."""

from __future__ import annotations

import structlog
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from kalshi_tracker.config import AppSettings

logger = structlog.get_logger(__name__)


def create_engine_from_settings(settings: AppSettings) -> Engine:
    """Create SQLAlchemy engine from AppSettings.

    Args:
        settings: Loaded AppSettings with database_url.

    Returns:
        Configured synchronous SQLAlchemy engine.
    """
    logger.info("db_engine_creating", url_prefix=settings.database_url[:30])
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine.

    Args:
        engine: SQLAlchemy engine.

    Returns:
        sessionmaker that produces Session instances.

    Usage:
        factory = get_session_factory(engine)
        with factory() as session:
            session.add(snapshot)
            session.commit()
    """
    return sessionmaker(engine, expire_on_commit=False)
