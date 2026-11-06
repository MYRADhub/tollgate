from decimal import Decimal

from sqlalchemy import select

from tollgate.db import session_scope
from tollgate.models import Approval, CriticReview, Invoice, Payment
from tollgate.worker import drain
from tests.test_e2e import load_inbox


def test_offline_critic_reviews_deductions_and_payment_proceeds(db):
    ids = load_inbox()
    with session_scope() as s:
        rv = s.execute(select(CriticReview).where(CriticReview.invoice_id == ids["polaris-PNS-55120.pdf"])).scalar_one()
        assert rv.verdict == "agree" and rv.independent_amount == Decimal("5525.00")
        assert s.get(Invoice, ids["polaris-PNS-55120.pdf"]).status.value == "scheduled"


def test_clean_small_invoice_skips_critic(db):
    ids = load_inbox()
    with session_scope() as s:
        assert s.execute(select(CriticReview).where(CriticReview.invoice_id == ids["lumen-LOS-3391.pdf"])).first() is None


def test_disagreement_escalates_to_cfo(db, monkeypatch):
    from tollgate import critic
    from tollgate.models import CriticReview as CR

    def fake_review(s, inv):
        rv = CR(invoice_id=inv.id, proposal=critic.proposal_for(inv), verdict="disagree", summary="SLA tier is wrong",
                points=["99.31 is below 99.5"], independent_amount=Decimal("5200.00"), model="test")
        s.add(rv)
        s.flush()
        return rv

    monkeypatch.setattr(critic, "offline_review", fake_review)
    ids = load_inbox()
    inv_id = ids["polaris-PNS-55120.pdf"]
    with session_scope() as s:
        inv = s.get(Invoice, inv_id)
        assert inv.status.value == "awaiting_approval"
        assert s.execute(select(Payment).where(Payment.invoice_id == inv_id)).first() is None
        appr = s.execute(select(Approval).where(Approval.invoice_id == inv_id)).scalar_one()
        assert appr.required_role.value == "cfo" and "Critic disagree" in appr.reason

    import pytest

    from tollgate.api_actions import ActionError, decide_approval

    with session_scope() as s:
        with pytest.raises(ActionError):
            decide_approval(s, appr.id, user="Rosa Kim", role="controller", decision="approved")
    with session_scope() as s:
        decide_approval(s, appr.id, user="Theo Grant", role="cfo", decision="approved")
    drain()
    with session_scope() as s:
        assert s.get(Invoice, inv_id).status.value == "scheduled"


def _oc(s, ids):
    inv = s.get(Invoice, ids["ostara-OC-7720.pdf"])
    f = next(f for f in inv.findings if f.code == "VOLUME_PRICE")
    return inv, f


def test_offline_critic_recomputes_the_volume_price_from_the_contract(db):
    ids = load_inbox()
    with session_scope() as s:
        rv = s.execute(select(CriticReview).where(CriticReview.invoice_id == ids["ostara-OC-7720.pdf"])).scalar_one()
        assert rv.verdict == "agree" and rv.independent_amount == Decimal("31944.00")


def test_offline_critic_disagrees_with_an_over_claimed_deduction(db):
    from tollgate import critic

    ids = load_inbox()
    with session_scope() as s:
        inv, f = _oc(s, ids)
        f.amount_at_risk = Decimal("2160.00")
        rv = critic.offline_review(s, inv)
        assert rv.verdict == "disagree" and rv.independent_amount == Decimal("31944.00")
        assert any("2,160.00 deducted; the contract term gives 1,416.00" in p for p in rv.points)


def test_offline_critic_disagrees_when_a_recovery_is_missing(db):
    from tollgate import critic

    ids = load_inbox()
    with session_scope() as s:
        inv, f = _oc(s, ids)
        s.delete(f)
        s.flush()
        s.refresh(inv)
        rv = critic.offline_review(s, inv)
        assert rv.verdict == "disagree" and rv.independent_amount == Decimal("31944.00")
        assert any("owed under" in p and "not deducted" in p for p in rv.points)


def test_offline_critic_accepts_a_recovery_a_person_waived(db):
    from tollgate import critic

    ids = load_inbox()
    with session_scope() as s:
        inv, f = _oc(s, ids)
        f.resolved, f.resolved_by = True, "Rosa Kim"
        rv = critic.offline_review(s, inv)
        assert rv.verdict == "agree" and rv.independent_amount == Decimal("33360.00")


def test_offline_critic_rejects_deductions_nothing_supports(db):
    from tollgate import critic
    from tollgate.models import Finding, Severity

    ids = load_inbox()
    with session_scope() as s:
        inv, _ = _oc(s, ids)
        s.add(Finding(invoice_id=inv.id, code="SLA_CREDIT", severity=Severity.recover, title="Invented credit", detail="", evidence={}, amount_at_risk=Decimal("500.00")))
        s.add(Finding(invoice_id=inv.id, code="VENDOR_CREDIT", severity=Severity.recover, title="Phantom memo", detail="", evidence={"credit_id": 999999}, amount_at_risk=Decimal("50.00")))
        s.flush()
        s.refresh(inv)
        rv = critic.offline_review(s, inv)
        assert rv.verdict == "disagree" and rv.independent_amount == Decimal("31944.00")
        assert any("Invented credit" in p and "no approved contract term" in p for p in rv.points)
        assert any("Phantom memo" in p and "no approved credit memo" in p for p in rv.points)


def test_offline_critic_agrees_with_the_price_cap_after_delivery(db):
    from tollgate import critic

    ids = load_inbox()
    with session_scope() as s:
        inv = s.get(Invoice, ids["granite-GE-5561.pdf"])
        rv = critic.offline_review(s, inv)
        assert rv.verdict == "agree" and rv.independent_amount == inv.total - Decimal("43.20")
