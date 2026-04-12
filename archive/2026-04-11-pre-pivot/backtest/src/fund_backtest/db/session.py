"""SQLAlchemy engine and session factory for fund-backtest."""
from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from fund_backtest.config import AppSettings, load_app_settings


def create_engine_from_settings(settings: AppSettings | None = None) -> Engine:
    """Create SQLAlchemy engine from application settings.

    Args:
        settings: Optional AppSettings instance. If None, loads from environment.

    Returns:
        Configured SQLAlchemy Engine with connection pooling and pre-ping.
    """
    if settings is None:
        settings = load_app_settings()
    return create_engine(
        settings.database_url,
        echo=settings.log_level == "DEBUG",
        pool_pre_ping=True,
    )


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Create sessionmaker factory bound to given engine.

    Args:
        engine: Optional Engine instance. If None, creates one from settings.

    Returns:
        Configured sessionmaker that produces Session instances.
    """
    if engine is None:
        engine = create_engine_from_settings()
    return sessionmaker(bind=engine, expire_on_commit=False)
