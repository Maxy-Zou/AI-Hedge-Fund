"""SQLAlchemy declarative base and timestamp mixins.

Provides the foundation for all database models in the system.
AppendOnlyMixin enforces the fund convention that financial time-series
data is never overwritten. DualTimestampMixin captures both the business
date (as_of_date) and the collection date (observed_date) to prevent
look-ahead bias.
"""

from __future__ import annotations

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


class AppendOnlyMixin:
    """Mixin for append-only tables (financial time-series convention).

    Records are only inserted, never updated or deleted. The created_at
    field is set by the database server on insert.
    """

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    as_of_date: Mapped[str | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class DualTimestampMixin:
    """Mixin for tables requiring business date and collection date separation.

    as_of_date: The business date the data represents (e.g., filing date).
    observed_date: When we actually collected/observed the data.

    This separation prevents look-ahead bias -- queries filter by as_of_date
    to ensure only data available at that time is used.
    """

    as_of_date: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    observed_date: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
