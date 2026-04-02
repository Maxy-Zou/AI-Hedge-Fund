"""SQLAlchemy declarative base and append-only mixins for Kalshi market data.

Per fund convention (CLAUDE.md): signal and trade data is append-only.
AppendOnlyMixin provides UUID PK + created_at. No update() or delete() methods.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all Kalshi Tracker ORM models."""


class AppendOnlyMixin:
    """UUID primary key + created_at. Append-only by design — no update/delete.

    Apply to: MarketSnapshot, Signal, Trade.
    Do NOT apply to: Market (entity table — mutable metadata).
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # No update() or delete() methods. Append-only is enforced by convention
    # (fund-wide immutability rule, LOG-03). Adding update/delete here violates contract.
