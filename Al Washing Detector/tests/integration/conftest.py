"""Integration test fixtures using testcontainers PostgreSQL.

Provides a real PostgreSQL database for integration tests via Docker.
Runs Alembic migrations once per session, then provides per-test sessions
that rollback after each test.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer


def _ensure_docker_host() -> None:
    """Set DOCKER_HOST if Docker Desktop socket exists but env var is unset.

    Docker Desktop on macOS uses ~/.docker/run/docker.sock instead of
    /var/run/docker.sock. The docker-py library needs DOCKER_HOST set
    to find it.
    """
    if os.environ.get("DOCKER_HOST"):
        return
    desktop_sock = Path.home() / ".docker" / "run" / "docker.sock"
    if desktop_sock.exists():
        os.environ["DOCKER_HOST"] = f"unix://{desktop_sock}"


@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL container for the test session."""
    _ensure_docker_host()
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def db_url(postgres_container):
    """Get the database URL from the running container.

    Converts the testcontainers psycopg2 URL to psycopg3 format
    (postgresql+psycopg://) used by ai_washer.
    """
    url = postgres_container.get_connection_url()
    # testcontainers returns psycopg2 URL; convert to psycopg3
    url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
    return url


@pytest.fixture(scope="session")
def _run_migrations(db_url):
    """Run Alembic migrations against the test database once per session."""
    os.environ["AI_WASHER_DATABASE_URL"] = db_url
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield
    # Downgrade after all tests complete
    command.downgrade(alembic_cfg, "base")


@pytest.fixture
def db_engine(db_url, _run_migrations):
    """Create a SQLAlchemy engine connected to the test database."""
    engine = create_engine(db_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create a database session that rolls back after each test.

    Uses nested transactions (savepoints) so tests can commit
    without affecting other tests.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()
