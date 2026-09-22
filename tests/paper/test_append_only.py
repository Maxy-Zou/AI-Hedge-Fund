"""Phase 9 -- mechanical append-only enforcement (PT-01, D2, D5).

Three layers exist; this file proves L1 (ORM flush) and L2 (ORM-enabled
Core statements) on SQLite. L3 (PostgreSQL trigger) is proven in
test_migration_roundtrip.py under TEST_DATABASE_URL.

The guard is opt-in via ``AppendOnlyGuard``. ``episodic_memory`` does NOT
opt in -- its retention sweep legitimately deletes -- and the last two
tests pin that (09-PREMORTEM.md #5).
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, event, update
from sqlalchemy.orm import Session

from ai_hedge_fund.db import append_only
from ai_hedge_fund.db.append_only import AppendOnlyGuard, AppendOnlyViolation
from ai_hedge_fund.db.dates import normalise_as_of
from ai_hedge_fund.db.models import EpisodicMemory, PaperFill, PaperTrade

SHA = "b" * 64
AS_OF = normalise_as_of("2026-04-18")


def _seed(db_session: Session) -> tuple[int, PaperTrade, PaperFill]:
    sig = EpisodicMemory(
        ticker="AAPL",
        sector="Technology",
        record_type="analysis",
        signal_direction="long",
        confidence=70,
        policy_sha=SHA,
        as_of_date=AS_OF,
        payload={"schema_version": 1},
    )
    db_session.add(sig)
    db_session.commit()
    trade = PaperTrade(
        signal_id=sig.id,
        ticker="AAPL",
        side="buy",
        order_type="market",
        quantity=10,
        submit_status="submitted",
        broker_order_id="ord-1",
        risk_status_at_submit="APPROVED",
        policy_sha=SHA,
        review_policy_sha=SHA,
        as_of_date=AS_OF,
        payload={"schema_version": 1},
    )
    db_session.add(trade)
    db_session.commit()
    fill = PaperFill(
        trade_id=trade.id,
        broker_fill_id="fill-1",
        filled_qty=10,
        fill_price_cents=18_500_00,
        filled_at=datetime(2026, 4, 18, 14, 30, tzinfo=UTC),
        as_of_date=AS_OF,
        payload={"schema_version": 1},
    )
    db_session.add(fill)
    db_session.commit()
    return sig.id, trade, fill


# --------------------------------------------------------------------------- marker


def test_paper_models_opt_in() -> None:
    assert issubclass(PaperTrade, AppendOnlyGuard) and PaperTrade.__append_only__ is True
    assert issubclass(PaperFill, AppendOnlyGuard) and PaperFill.__append_only__ is True
    assert not getattr(EpisodicMemory, "__append_only__", False)


# --------------------------------------------------------------------------- L1: ORM flush


def test_orm_update_rejected(db_session: Session) -> None:
    _, trade, _ = _seed(db_session)
    trade.quantity = 999
    with pytest.raises(AppendOnlyViolation) as exc:
        db_session.commit()
    db_session.rollback()
    assert exc.value.table == "paper_trades" and exc.value.operation == "UPDATE"
    assert "paper_trades" in str(exc.value) and "UPDATE" in str(exc.value)


def test_orm_update_rejected_on_fills(db_session: Session) -> None:
    _, _, fill = _seed(db_session)
    fill.filled_qty = 1
    with pytest.raises(AppendOnlyViolation):
        db_session.commit()
    db_session.rollback()


def test_orm_delete_rejected(db_session: Session) -> None:
    """D2: DELETE is forbidden too -- a track record is permanent."""
    _, _, fill = _seed(db_session)
    db_session.delete(fill)
    with pytest.raises(AppendOnlyViolation) as exc:
        db_session.commit()
    db_session.rollback()
    assert exc.value.operation == "DELETE"


def test_row_survives_rejected_mutation(db_session: Session) -> None:
    _, trade, _ = _seed(db_session)
    original = trade.quantity
    trade.quantity = 999
    with pytest.raises(AppendOnlyViolation):
        db_session.commit()
    db_session.rollback()
    db_session.expire_all()
    assert db_session.get(PaperTrade, trade.id).quantity == original


# --------------------------------------------------------------------------- L2: Core statements


def test_core_update_statement_rejected(db_session: Session) -> None:
    """09-PREMORTEM #2: ``session.execute(update(...))`` never hits before_flush."""
    _, trade, _ = _seed(db_session)
    with pytest.raises(AppendOnlyViolation) as exc:
        db_session.execute(update(PaperTrade).where(PaperTrade.id == trade.id).values(quantity=1))
    db_session.rollback()
    assert exc.value.table == "paper_trades" and exc.value.operation == "UPDATE"


def test_core_delete_statement_rejected(db_session: Session) -> None:
    _, _, fill = _seed(db_session)
    with pytest.raises(AppendOnlyViolation) as exc:
        db_session.execute(delete(PaperFill).where(PaperFill.id == fill.id))
    db_session.rollback()
    assert exc.value.table == "paper_fills" and exc.value.operation == "DELETE"


def test_core_update_on_table_object_rejected(db_session: Session) -> None:
    """Review F5: update(Model.__table__) has no bind_mapper; guard must key on table name too."""
    _, trade, _ = _seed(db_session)
    with pytest.raises(AppendOnlyViolation) as exc:
        db_session.execute(
            update(PaperTrade.__table__)
            .where(PaperTrade.__table__.c.id == trade.id)
            .values(quantity=1)
        )
    db_session.rollback()
    assert exc.value.table == "paper_trades" and exc.value.operation == "UPDATE"


def test_core_delete_on_table_object_rejected(db_session: Session) -> None:
    _, _, fill = _seed(db_session)
    with pytest.raises(AppendOnlyViolation) as exc:
        db_session.execute(delete(PaperFill.__table__).where(PaperFill.__table__.c.id == fill.id))
    db_session.rollback()
    assert exc.value.table == "paper_fills" and exc.value.operation == "DELETE"


def test_legacy_query_update_rejected(db_session: Session) -> None:
    _, trade, _ = _seed(db_session)
    with pytest.raises(AppendOnlyViolation):
        db_session.query(PaperTrade).filter(PaperTrade.id == trade.id).update({"quantity": 1})
    db_session.rollback()


def test_legacy_query_delete_rejected(db_session: Session) -> None:
    _, _, fill = _seed(db_session)
    with pytest.raises(AppendOnlyViolation):
        db_session.query(PaperFill).filter(PaperFill.id == fill.id).delete()
    db_session.rollback()


def test_guarded_table_registry() -> None:
    assert append_only.guarded_tables() == frozenset({"paper_trades", "paper_fills"})


# --------------------------------------------------------------------------- opt-in scope (#5)


def test_episodic_core_delete_unaffected(db_session: Session) -> None:
    """The exact statement shape purge_expired_episodic.py issues must still work."""
    sid, _, _ = _seed(db_session)
    # Detach the paper rows' FK dependency first by using a fresh episodic row.
    extra = EpisodicMemory(
        ticker="MSFT",
        sector="Technology",
        record_type="outcome",
        as_of_date=AS_OF,
        payload={"schema_version": 1},
    )
    db_session.add(extra)
    db_session.commit()
    result = db_session.execute(delete(EpisodicMemory).where(EpisodicMemory.id == extra.id))
    db_session.commit()
    assert result.rowcount == 1


def test_episodic_orm_update_unaffected(db_session: Session) -> None:
    sid, _, _ = _seed(db_session)
    row = db_session.get(EpisodicMemory, sid)
    row.confidence = 71
    db_session.commit()  # must not raise


# --------------------------------------------------------------------------- registration (#4)


def test_listeners_registered_on_session_class() -> None:
    assert event.contains(Session, "before_flush", append_only._reject_orm_mutations)
    assert event.contains(Session, "do_orm_execute", append_only._reject_core_mutations)


def test_guard_registered_via_db_package_import() -> None:
    """A fresh interpreter that imports only db.session (a prod path) must have the guard."""
    code = (
        "import ai_hedge_fund.db.session\n"
        "from sqlalchemy import event\n"
        "from sqlalchemy.orm import Session\n"
        "from ai_hedge_fund.db.append_only import _reject_orm_mutations, _reject_core_mutations\n"
        "assert event.contains(Session, 'before_flush', _reject_orm_mutations)\n"
        "assert event.contains(Session, 'do_orm_execute', _reject_core_mutations)\n"
        "print('registered')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "registered"
