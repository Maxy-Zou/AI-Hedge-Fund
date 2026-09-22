"""Mechanical append-only enforcement for opt-in tables (Phase 9, PT-01).

Before Phase 9, "append-only" was a docstring convention. This module makes
it a runtime guarantee for any model that inherits :class:`AppendOnlyGuard`:
an UPDATE or DELETE against such a table raises :class:`AppendOnlyViolation`
before any SQL is emitted. Corrections are new rows, never mutations (D2).

Coverage -- three layers, two of them here:

* **L1** ``before_flush``: catches ORM attribute mutation and
  ``session.delete(obj)`` on the unit-of-work path.
* **L2** ``do_orm_execute``: catches ``session.execute(update(Model) ...)``
  and ``delete(Model)`` -- ORM-enabled Core statements, which never pass
  through the flush and would otherwise bypass L1 (09-PREMORTEM.md #2).
* **L3** (not here): a PostgreSQL ``BEFORE UPDATE OR DELETE`` trigger in
  migration 004. It is the only layer that sees raw
  ``session.execute(text("UPDATE ..."))``; the codebase already forbids
  string SQL (T-07-01), and this is why.

The guard is **opt-in** by class marker so tables with legitimate deletes
(``episodic_memory``'s retention sweep) are untouched (09-PREMORTEM.md #5).
Listeners attach to the ``Session`` class, so every session is covered once
this module is imported; ``db/__init__.py`` does that on package import.

After an :class:`AppendOnlyViolation` the session holds a rejected pending
change; callers must ``rollback()``. It signals a programming error, not a
data condition, so it is deliberately not a subclass of ``PaperStoreError``.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, UOWTransaction

Operation = Literal["UPDATE", "DELETE"]


class AppendOnlyViolation(RuntimeError):
    """An UPDATE or DELETE targeted an append-only table."""

    def __init__(self, table: str, operation: Operation) -> None:
        self.table = table
        self.operation = operation
        super().__init__(
            f"append-only table {table}: {operation} not permitted; write a new row instead"
        )


class AppendOnlyGuard:
    """Marker mixin. Models inheriting it are protected by the listeners below."""

    __append_only__: ClassVar[bool] = True


def _is_guarded(cls: type) -> bool:
    return bool(getattr(cls, "__append_only__", False))


def _table_name(cls: type) -> str:
    return str(getattr(cls, "__tablename__", cls.__name__))


@event.listens_for(Session, "before_flush")
def _reject_orm_mutations(session: Session, flush_context: UOWTransaction, instances: Any) -> None:
    """L1: refuse to flush a modified or deleted guarded instance."""
    for obj in session.deleted:
        if _is_guarded(type(obj)):
            raise AppendOnlyViolation(_table_name(type(obj)), "DELETE")
    for obj in session.dirty:
        if _is_guarded(type(obj)) and session.is_modified(obj):
            raise AppendOnlyViolation(_table_name(type(obj)), "UPDATE")


@event.listens_for(Session, "do_orm_execute")
def _reject_core_mutations(state: ORMExecuteState) -> None:
    """L2: refuse ORM-enabled ``update()`` / ``delete()`` statements on guarded tables."""
    if not (state.is_update or state.is_delete):
        return
    mapper = state.bind_mapper
    if mapper is None or not _is_guarded(mapper.class_):
        return
    raise AppendOnlyViolation(_table_name(mapper.class_), "UPDATE" if state.is_update else "DELETE")
