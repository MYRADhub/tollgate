from datetime import date
from decimal import Decimal as D

from sqlalchemy import select

from tollgate.db import session_scope
from tollgate.models import Payment, PaymentRun
from tollgate.paymentrun import Candidate, plan

TODAY = date(2026, 11, 4)


def c(i, amount, due, pct=None, deadline=None):
    return Candidate(i, f"inv{i}", f"N{i}", "V", D(amount), due, D(pct) if pct else None, deadline)


def test_due_invoices_first_then_best_discounts_within_floor():
    cands = [
        c(1, "10000", date(2026, 11, 8)),  # due inside the horizon
        c(2, "8000", date(2026, 11, 16), "2", date(2026, 11, 11)),  # 2/10 net 15: ~146%/yr
        c(3, "9000", date(2026, 12, 3), "1", date(2026, 11, 13)),  # 1/10 net 30: ~18%/yr
        c(4, "5000", date(2026, 12, 20)),  # no discount, not due
    ]
    p = plan(cands, TODAY, D("40000"), D("15000"), 7)
    pay = {i["payment_id"]: i for i in p["items"] if i["decision"] == "pay"}
    assert set(pay) == {1, 2}  # 25,000 available: 10,000 due + 7,840 discounted; the 1% one would breach the floor
    assert pay[2]["discount"] == "160.00"
    assert p["discounts"] == "160.00"
    assert D(p["cash_after"]) >= D("15000")
    deferred = {i["payment_id"]: i["reason"] for i in p["items"] if i["decision"] == "defer"}
    assert "floor" in deferred[3] or "committed" in deferred[3]
    assert "no early-payment discount" in deferred[4]


def test_expired_discount_is_not_taken():
    p = plan([c(1, "1000", date(2026, 11, 30), "2", date(2026, 11, 1))], TODAY, D("40000"), D("15000"), 7)
    assert p["items"][0]["decision"] == "defer"


def test_run_is_planned_after_scheduling_and_approval_releases_with_discount(db):
    from tests.test_e2e import load_inbox
    from tollgate.paymentrun import approve, bank_file

    load_inbox()
    with session_scope() as s:
        run = s.execute(select(PaymentRun).where(PaymentRun.status == "proposed")).scalar_one()
        paid = [i for i in run.plan["items"] if i["decision"] == "pay"]
        assert paid and run.discounts > 0
        rid = run.id
    with session_scope() as s:
        approve(s, rid, "Rosa Kim", "controller")
    with session_scope() as s:
        released = list(s.execute(select(Payment).where(Payment.run_id == rid)).scalars())
        assert all(p.status == "released" for p in released)
        assert any(p.discount > 0 for p in released)
        assert "TG-RUN-" in bank_file(s, rid)
