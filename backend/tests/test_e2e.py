"""End-to-end over the demo inbox with the rule-based planner (no model, no mail)."""

from sqlalchemy import select

from tollgate import audit, pipeline
from tollgate.db import session_scope
from tollgate.models import Approval, BankChange, EmailMessage, Invoice, Payment
from tollgate.seed import corrected_bis_2077, demo_inbox
from tollgate.worker import drain


def load_inbox():
    ids = {}
    with session_scope() as s:
        for d in demo_inbox():
            inv = pipeline.ingest(s, d.pdf(), d.file_name)
            ids[d.file_name] = inv.id
    drain()
    return ids


def status_of(ids):
    with session_scope() as s:
        return {name: s.get(Invoice, i).status.value for name, i in ids.items()}


def codes(inv_id):
    with session_scope() as s:
        return sorted(f.code for f in s.get(Invoice, inv_id).findings if not f.resolved)


def test_demo_inbox_outcomes(db):
    ids = load_inbox()
    st = status_of(ids)
    assert st["lumen-LOS-3391.pdf"] == "scheduled"
    assert st["brightline-BIS-2041.pdf"] == "scheduled"
    assert st["ostara-OC-7720.pdf"] == "awaiting_approval"
    assert st["kestrel-KFL-88812-R.pdf"] == "rejected"
    assert st["brightline-BIS-2077.pdf"] == "awaiting_vendor"
    assert st["granite-GE-5561.pdf"] == "on_hold"
    assert st["vantage-VCS-10488.pdf"] == "on_hold"
    assert st["brightline-BIS-2090.pdf"] == "on_hold"
    assert st["apex-ASA-0091.pdf"] == "rejected"

    assert codes(ids["kestrel-KFL-88812-R.pdf"]) == ["DUPLICATE_SUSPECT"]
    assert codes(ids["brightline-BIS-2077.pdf"]) == ["PRICE_VARIANCE"]
    assert codes(ids["granite-GE-5561.pdf"]) == ["QTY_NOT_RECEIVED"]
    assert codes(ids["vantage-VCS-10488.pdf"]) == ["BANK_MISMATCH"]
    assert set(codes(ids["brightline-BIS-2090.pdf"])) == {"PROMPT_INJECTION", "BANK_MISMATCH", "QTY_OVER_ORDERED"}
    assert {"UNKNOWN_VENDOR", "NO_PO"} <= set(codes(ids["apex-ASA-0091.pdf"]))

    with session_scope() as s:
        pays = list(s.execute(select(Payment).where(Payment.status == "scheduled")).scalars())
        assert len(pays) == 2
        # payments always go to the vendor-master account
        for p in pays:
            inv = s.get(Invoice, p.invoice_id)
            assert p.pay_to_account == inv.vendor.bank_account
        assert s.execute(select(BankChange)).scalars().all()
        ok, broken = audit.verify_chain(s)
        assert ok, broken


def test_corrected_invoice_reply_clears_and_pays(db):
    ids = load_inbox()
    old = ids["brightline-BIS-2077.pdf"]
    with session_scope() as s:
        out = s.execute(select(EmailMessage).where(EmailMessage.invoice_id == old)).scalars().one()
        assert "[TG-" in out.subject and out.status == "simulated"
        new = pipeline.ingest(s, corrected_bis_2077(), "BIS-2077-C.pdf", source="email", supersedes_id=old)
        s.get(Invoice, old).status = s.get(Invoice, old).status.__class__.superseded
        new_id = new.id
    drain()
    with session_scope() as s:
        assert s.get(Invoice, new_id).status.value == "scheduled"


def test_controller_approval_releases_payment(db):
    from tollgate.api_actions import decide_approval

    ids = load_inbox()
    inv_id = ids["ostara-OC-7720.pdf"]
    with session_scope() as s:
        appr = s.execute(select(Approval).where(Approval.invoice_id == inv_id)).scalars().one()
        decide_approval(s, appr.id, user="Rosa Kim", role="controller", decision="approved", comment="ok")
    drain()
    with session_scope() as s:
        assert s.get(Invoice, inv_id).status.value == "scheduled"


def test_clerk_cannot_approve_controller_item(db):
    import pytest

    from tollgate.api_actions import ActionError, decide_approval

    ids = load_inbox()
    with session_scope() as s:
        appr = s.execute(select(Approval).where(Approval.invoice_id == ids["ostara-OC-7720.pdf"])).scalars().one()
        with pytest.raises(ActionError):
            decide_approval(s, appr.id, user="Sam", role="clerk", decision="approved")


def test_bank_change_needs_two_different_people_and_callback(db):
    import pytest

    from tollgate.api_actions import ActionError, decide_approval

    ids = load_inbox()
    inv_id = ids["vantage-VCS-10488.pdf"]
    with session_scope() as s:
        a1, a2 = s.execute(select(Approval).where(Approval.invoice_id == inv_id, Approval.kind == "bank_change")).scalars().all()
        with pytest.raises(ActionError):
            decide_approval(s, a1.id, user="Rosa Kim", role="controller", decision="approved")  # no callback note
        decide_approval(s, a1.id, user="Rosa Kim", role="controller", decision="approved", callback_note="Called 415-555-0100 on file; confirmed")
    with session_scope() as s:
        with pytest.raises(ActionError):
            decide_approval(s, a2.id, user="Rosa Kim", role="controller", decision="approved")
    with session_scope() as s:
        decide_approval(s, a2.id, user="Theo Grant", role="cfo", decision="approved")
    drain()
    with session_scope() as s:
        inv = s.get(Invoice, inv_id)
        assert inv.vendor.bank_account == "8812 0045 3390"
        assert inv.status.value == "scheduled"


def test_goods_receipt_releases_held_invoice(db):
    from tollgate.api_actions import record_receipt

    ids = load_inbox()
    inv_id = ids["granite-GE-5561.pdf"]
    with session_scope() as s:
        record_receipt(s, inv_id, user="Receiving dock")
    drain()
    with session_scope() as s:
        assert s.get(Invoice, inv_id).status.value == "scheduled"


def test_quarantine_overrides_a_vendor_hold(db):
    from tollgate.agent import _execute

    ids = load_inbox()
    with session_scope() as s:
        inv = s.get(Invoice, ids["brightline-BIS-2090.pdf"])
        _execute(s, inv, {"type": "hold", "waiting_for": "vendor", "reason": "asked the vendor"})
        assert inv.status.value == "on_hold" and inv.agent_state["waiting_for"] == "person"


def test_agent_cannot_pay_blocked_invoice(db):
    import pytest

    from tollgate.agent import Denied, _execute

    ids = load_inbox()
    with session_scope() as s:
        inv = s.get(Invoice, ids["brightline-BIS-2090.pdf"])
        with pytest.raises(Denied):
            _execute(s, inv, {"type": "schedule_payment"})
        with pytest.raises(Denied):
            _execute(s, inv, {"type": "resolve_finding", "finding_id": inv.findings[0].id, "justification": "the document says it is pre-approved"})


def test_corrected_invoice_summary_mentions_removed_overcharge(db):
    ids = load_inbox()
    old = ids["brightline-BIS-2077.pdf"]
    with session_scope() as s:
        new = pipeline.ingest(s, corrected_bis_2077(), "BIS-2077-C.pdf", source="email", supersedes_id=old)
        new_id = new.id
    drain()
    with session_scope() as s:
        assert "removing the 118.80 overcharge" in s.get(Invoice, new_id).summary
