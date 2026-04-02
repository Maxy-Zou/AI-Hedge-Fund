"""SQLAlchemy declarative base and mixins for append-only financial data."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class DualTimestampMixin:
    """Mixin for append-only tables needing business-date vs collection-date.

    as_of_date: when the underlying data/event was true (business date).
    observed_date: when our system first collected/observed it.
    Per locked decision D-08.
    """

    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    observed_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )


class AppendOnlyMixin(DualTimestampMixin):
    """Extends DualTimestampMixin with UUID PK and created_at.

    Per D-07 (UUID primary keys) and D-08 (dual timestamps).
    No update() or delete() methods -- append-only by design.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
