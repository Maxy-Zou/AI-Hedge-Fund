"""Mechanical append-only enforcement for opt-in tables (Phase 9, PT-01).

Before Phase 9, "append-only" was a docstring convention. This module makes
it a runtime guarantee for any model that inherits :class:`AppendOnlyGuard`:
an UPDATE or DELETE against such a table raises :class:`AppendOnlyViolation`
before any SQL is emitted. Corrections are new rows, never mutations (D2).

Coverage -- three layers:

* **L1** ``before_flush``: ORM attribute mutation and ``session.delete(obj)``
  on the unit-of-work path.
* **L2** ``do_orm_execute``: ``session.execute(update(...) / delete(...))``
  whether built from the mapped class *or* its ``Table`` object, plus the
  legacy ``Query.update()`` / ``Query.delete()`` path. These never pass
  through the flush and would otherwise bypass L1 (09-PREMORTEM.md #2).
* **L3** PostgreSQL ``BEFORE UPDATE OR DELETE`` trigger -- the only layer that
  sees raw ``session.execute(text("UPDATE ..."))``. Attached to the ``Table``
  objects via :func:`attach_postgres_guard` so ``Base.metadata.create_all``
  produces it, and created again (idempotently) by migration 004 so
  ``alembic upgrade`` produces it. The codebase already forbids string SQL
  (T-07-01); L3 is the backstop.

The guard is **opt-in** by class marker so tables with legitimate deletes
(``episodic_memory``'s retention sweep) are untouched (09-PREMORTEM.md #5).
Listeners attach to the ``Session`` class; ``db/__init__.py`` imports this
module so every session in the process is covered.

After an :class:`AppendOnlyViolation` the session holds a rejected pending
change; callers must ``rollback()``. It signals a programming error, not a
data condition, so it is deliberately not a subclass of ``PaperStoreError``.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from sqlalchemy import DDL, Table, event
from sqlalchemy.orm import ORMExecuteState, Session, UOWTransaction

Operation = Literal["UPDATE", "DELETE"]

_GUARDED: set[str] = set()

# PostgreSQL DDL. Written with RAISE ... USING MESSAGE so the text contains no
# '%' -- SQLAlchemy's DDL() applies Python %-formatting and psycopg applies
# pyformat, and a bare '%' would be mangled by one or the other. Every
# statement is idempotent so create_all and migration 004 can both run it.
PG_GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION paper_append_only_guard() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = 'append-only table ' || TG_TABLE_NAME || ': ' || TG_OP
                  || ' not permitted; write a new row instead',
        ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql
"""


def pg_trigger_statements(table_name: str) -> tuple[str, str]:
    """(DROP TRIGGER IF EXISTS ..., CREATE TRIGGER ...) for one guarded table."""
    trg = f"trg_{table_name}_append_only"
    return (
        f"DROP TRIGGER IF EXISTS {trg} ON {table_name}",
        f"CREATE TRIGGER {trg} BEFORE UPDATE OR DELETE ON {table_name} "
        "FOR EACH ROW EXECUTE FUNCTION paper_append_only_guard()",
    )


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

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        name = getattr(cls, "__tablename__", None)
        if name:
            _GUARDED.add(str(name))


def guarded_tables() -> frozenset[str]:
    """Table names currently protected by the guard."""
    return frozenset(_GUARDED)


def attach_postgres_guard(table: Table) -> None:
    """Register the L3 trigger DDL to fire after ``create_all`` on PostgreSQL only."""
    drop_trg, create_trg = pg_trigger_statements(table.name)
    for stmt in (PG_GUARD_FUNCTION, drop_trg, create_trg):
        event.listen(table, "after_create", DDL(stmt).execute_if(dialect="postgresql"))


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
    """L2: refuse ``update()`` / ``delete()`` statements aimed at a guarded table.

    Keyed on the statement's target table name, not only on ``bind_mapper``,
    so ``update(Model.__table__)`` is caught as well as ``update(Model)``.
    """
    if not (state.is_update or state.is_delete):
        return
    operation: Operation = "UPDATE" if state.is_update else "DELETE"
    mapper = state.bind_mapper
    if mapper is not None and _is_guarded(mapper.class_):
        raise AppendOnlyViolation(_table_name(mapper.class_), operation)
    target = getattr(state.statement, "table", None)
    name = getattr(target, "name", None)
    if name in _GUARDED:
        raise AppendOnlyViolation(str(name), operation)
