"""SQLAlchemy declarative base and timestamp mixins.

Provides the foundation for all database models in the system.
DualTimestampMixin captures both the business date (as_of_date) and the
collection date (observed_date) to prevent look-ahead bias.
"""

from __future__ import annotations

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


class DualTimestampMixin:
    """Mixin for tables requiring business date and collection date separation.

    as_of_date: The business date the data represents (e.g., filing date).
    observed_date: When we actually collected/observed the data.

    This separation prevents look-ahead bias -- queries filter by as_of_date
    to ensure only data available at that time is used.

    Both columns are ``nullable=False``: a row without an ``observed_date``
    would silently defeat the temporal audit trail that underpins the
    look-ahead-bias defense (see CLAUDE.md "Data Handling"). ``server_default``
    guarantees the column is populated at the DB boundary; the ORM-level
    non-null makes a caller-supplied ``None`` a type error instead of a
    silent NULL insert.
    """

    as_of_date: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    observed_date: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
