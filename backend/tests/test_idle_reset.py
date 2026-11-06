from sqlalchemy import func, select

from tollgate import audit
from tollgate.db import session_scope
from tollgate.models import AuditEvent, Invoice
from tollgate.worker import IdleReset
from tests.test_e2e import load_inbox


def _invoices():
    with session_scope() as s:
        return s.execute(select(func.count(Invoice.id))).scalar()


def test_a_fresh_demo_is_never_reset(db):
    idle = IdleReset(3600)
    assert not idle.check(0)
    assert not idle.check(10_000)
    with session_scope() as s:
        assert s.execute(select(AuditEvent.kind).order_by(AuditEvent.id.desc()).limit(1)).scalar() == "seed"


def test_a_used_demo_resets_after_the_idle_time(db):
    load_inbox()
    before = _invoices()
    assert before > 1
    idle = IdleReset(3600)
    assert not idle.check(0)
    assert not idle.check(3599)
    assert idle.check(3600)
    assert _invoices() < before
    with session_scope() as s:
        assert s.execute(select(AuditEvent.kind).order_by(AuditEvent.id.desc()).limit(1)).scalar() == "seed"
    assert not idle.check(3601) and not idle.check(9000)  # fresh again: left alone


def test_activity_restarts_the_idle_timer(db):
    load_inbox()
    idle = IdleReset(3600)
    idle.check(0)
    with session_scope() as s:
        audit.record(s, actor="Rosa Kim", kind="approval", summary="still here")
    assert not idle.check(3000)
    assert not idle.check(6000)  # 3000s since the activity was seen
    assert idle.check(6600)


def test_zero_disables_the_idle_reset(db):
    load_inbox()
    idle = IdleReset(0)
    assert not idle.check(0) and not idle.check(10**9)
