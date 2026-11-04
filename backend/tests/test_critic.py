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
