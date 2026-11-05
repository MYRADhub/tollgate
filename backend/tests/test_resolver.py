"""The exception agent: it investigates, asks the budget owner, waits, and acts
on the structured answer, with every fact-changing step guarded in code."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tollgate import agent, briefing, clock, colleagues, pipeline
from tollgate.api import app
from tollgate.api_actions import decide_approval
from tollgate.config import get_settings
from tollgate.db import session_scope
from tollgate.models import AuditEvent, ColleagueQuestion, EmailMessage, Invoice, Job, PurchaseOrder
from tollgate.seed import demo_inbox
from tollgate.worker import drain


def load(*names):
    ids = {}
    with session_scope() as s:
        for d in demo_inbox():
            if not names or d.file_name in names:
                ids[d.spec.number] = pipeline.ingest(s, d.pdf(), d.file_name).id
    drain()
    return ids


def advance(hours):
    with session_scope() as s:
        clock.advance(s, hours, get_settings().max_clock_offset_days)
    drain()


def inv(iid):
    with session_scope() as s:
        i = s.get(Invoice, iid)
        s.expunge(i)
        return i


def questions(iid, topic=None):
    with session_scope() as s:
        return [(q.topic, q.po_number, q.answer, q.person_name) for q in colleagues.questions(s, iid, topic)]


def kinds(iid):
    with session_scope() as s:
        return [e.kind for e in s.execute(select(AuditEvent).where(AuditEvent.invoice_id == iid).order_by(AuditEvent.id)).scalars()]


@pytest.fixture(autouse=True)
def _clock():
    clock.forget()
    yield
    clock.forget()


def test_missing_po_is_found_confirmed_and_attached(db):
    ids = load("granite-GE-5570.pdf")
    i = inv(ids["GE-5570"])
    assert i.status.value == "on_hold" and i.agent_state["waiting_for"] == "colleague"
    assert questions(i.id) == [("po_confirm", "PO-24111", "pending", "Marcus Ode")]
    assert "tool" in kinds(i.id)  # it looked up the vendor's open POs before asking
    with session_scope() as s:
        asked = s.execute(select(EmailMessage).where(EmailMessage.invoice_id == i.id, EmailMessage.direction == "out")).scalars().one()
        assert asked.status == "simulated" and "PO-24111" in asked.body

    advance(0.05)  # Marcus answers
    i = inv(ids["GE-5570"])
    assert i.status.value == "scheduled"
    assert i.po_number == "PO-24111"
    assert i.agent_state["po_attached"] == {"po": "PO-24111", "confirmed_by": "Marcus Ode"}
    assert "Marcus Ode confirmed PO-24111" in i.summary


def test_attach_po_is_guarded(db):
    ids = load("granite-GE-5570.pdf")
    with session_scope() as s:
        i = s.get(Invoice, ids["GE-5570"])
        with pytest.raises(agent.Denied, match="has not confirmed"):
            agent._execute(s, i, {"type": "attach_po", "po_number": "PO-24111"})
        with pytest.raises(agent.Denied, match="not an open PO of this invoice's vendor"):
            agent._execute(s, i, {"type": "attach_po", "po_number": "PO-24106"})  # Lumen's PO
        # a "yes" from someone who does not own the PO does not count
        s.add(ColleagueQuestion(invoice_id=i.id, topic="po_confirm", person_name="Dana Whitfield", person_email="dana@halden.example.com",
                                po_number="PO-24111", answer="yes"))
        s.flush()
        with pytest.raises(agent.Denied, match="has not confirmed"):
            agent._execute(s, i, {"type": "attach_po", "po_number": "PO-24111"})
        with pytest.raises(agent.Denied, match="no open RECEIPT|no open QTY_NOT_RECEIVED"):
            agent._execute(s, i, {"type": "ask_colleague", "topic": "receipt", "po_number": "PO-24111"})


def test_owner_who_does_not_recognise_the_po_leads_to_escalation(db, monkeypatch):
    monkeypatch.setitem(colleagues.SCENARIOS, ("GE-5570", "po_confirm"), {"po": "PO-99999", "yes": "", "no": "Hi,\n\nNot mine.\n\nMarcus"})
    ids = load("granite-GE-5570.pdf")
    advance(0.05)
    i = inv(ids["GE-5570"])
    assert i.status.value == "on_hold" and i.agent_state["waiting_for"] == "person"
    assert "raise a PO" in i.agent_state["recommendation"]
    assert i.po_number is None


def test_small_unordered_charge_becomes_a_change_order(db):
    ids = load("lumen-LOS-3420.pdf")
    assert questions(ids["LOS-3420"]) == [("accept_charge", "PO-24112", "pending", "Elena Sorensen")]
    advance(0.05)
    i = inv(ids["LOS-3420"])
    assert i.status.value == "scheduled"
    with session_scope() as s:
        po = s.execute(select(PurchaseOrder).where(PurchaseOrder.number == "PO-24112")).scalar_one()
        assert "DLV-RUSH" in {pl.sku for pl in po.lines}
        assert any("accepted charge" in r.received_by for r in po.receipts)


def test_declined_charge_goes_back_to_the_vendor(db, monkeypatch):
    monkeypatch.setitem(colleagues.SCENARIOS, ("LOS-3420", "accept_charge"), {"answer": "no", "body": "Hi,\n\nNo, we never asked for that.\n\nElena"})
    ids = load("lumen-LOS-3420.pdf")
    advance(0.05)
    i = inv(ids["LOS-3420"])
    assert i.status.value == "awaiting_vendor"
    with session_scope() as s:
        out = [e.recipient for e in s.execute(select(EmailMessage).where(EmailMessage.invoice_id == i.id, EmailMessage.direction == "out")).scalars()]
        assert any("lumen" in r for r in out)


def test_charge_above_the_change_order_limit_is_never_accepted(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "change_order_limit_usd", 50.0)
    ids = load("lumen-LOS-3420.pdf")
    i = inv(ids["LOS-3420"])
    assert questions(i.id) == []  # not asked: $65 is over the limit, so it goes to the vendor
    assert i.status.value == "awaiting_vendor"
    with session_scope() as s:
        x = s.get(Invoice, i.id)
        s.add(ColleagueQuestion(invoice_id=x.id, topic="accept_charge", person_name="Elena Sorensen",
                                person_email=s.execute(select(PurchaseOrder).where(PurchaseOrder.number == "PO-24112")).scalar_one().budget_owner_email,
                                po_number="PO-24112", line=2, answer="yes"))
        s.flush()
        with pytest.raises(agent.Denied, match="change-order limit"):
            agent._execute(s, x, {"type": "accept_charge", "line": 2})


def test_backorder_waits_for_receiving_then_pays(db):
    ids = load("granite-GE-5561.pdf")
    advance(0.05)
    i = inv(ids["GE-5561"])
    assert i.status.value == "on_hold" and i.agent_state["waiting_for"] == "receipt"
    assert questions(i.id)[0][2] == "later"
    advance(24)
    i = inv(ids["GE-5561"])
    assert i.status.value == "scheduled"
    assert "goods_received" in kinds(i.id)
    with session_scope() as s:
        assert not briefing.build(s)["working"]


def test_receipt_nobody_can_confirm_is_escalated_after_two_tries(db, monkeypatch):
    monkeypatch.delitem(colleagues.SCENARIOS, ("GE-5561", "receipt"))
    ids = load("granite-GE-5561.pdf")
    advance(0.05)
    advance(0.05)
    i = inv(ids["GE-5561"])
    assert [q[2] for q in questions(i.id)] == ["unknown", "unknown"]
    assert i.status.value == "on_hold" and i.agent_state["waiting_for"] == "person"
    assert "credit note" in i.agent_state["recommendation"]


def test_quarantined_invoice_is_not_worked(db):
    ids = load("brightline-BIS-2090.pdf")
    assert questions(ids["BIS-2090"]) == []
    assert "tool" not in kinds(ids["BIS-2090"])


def test_approver_is_reminded_twice_at_most(db):
    ids = load("ostara-OC-7720.pdf")
    assert inv(ids["OC-7720"]).status.value == "awaiting_approval"
    for _ in range(3):
        advance(21)
    assert kinds(ids["OC-7720"]).count("approval_reminder") == 2
    with session_scope() as s:
        mails = list(s.execute(select(EmailMessage).where(EmailMessage.invoice_id == ids["OC-7720"], EmailMessage.subject.like("Reminder:%"))).scalars())
        assert len(mails) == 2 and all(m.status == "simulated" for m in mails)


def test_briefing_after_a_day(db):
    load()
    advance(0.05)
    advance(24)
    with session_scope() as s:
        b = briefing.build(s)
    by_agent = {r["number"] for r in b["resolved"] if r["by_agent"]}
    assert {"GE-5570", "LOS-3420", "GE-5561", "KFL-88812-R", "ASA-0091"} <= by_agent
    assert {n["kind"] for n in b["needs_you"]} == {"approval", "bank_change", "quarantine"}
    assert {w["number"] for w in b["working"]} == {"BIS-2077"}
    assert b["human_touches"] == 0
    assert b["exceptions"]["resolved_by_agent"] == len(by_agent)
    assert b["time_saved"]["hours"] > 0
    assert b["work"]["questions"] >= 3 and b["work"]["lookups"] >= 3
    q = next(n for n in b["needs_you"] if n["kind"] == "quarantine")
    assert q["recommendation"].startswith("Reject")

    # a person approving OC-7720 is a touch, and it is no longer waiting on anyone
    a = next(n for n in b["needs_you"] if n["kind"] == "approval")
    with session_scope() as s:
        decide_approval(s, a["approval_id"], user="Rosa Kim", role="controller", decision="approved")
    drain()
    with session_scope() as s:
        b = briefing.build(s)
    assert b["human_touches"] == 1
    assert "approval" not in {n["kind"] for n in b["needs_you"]}


def test_fast_forward_endpoint(db):
    c = TestClient(app)
    r = c.post("/api/demo/clock", json={"hours": 24})
    assert r.status_code == 200 and r.json()["offset_hours"] == 24
    assert c.post("/api/demo/clock", json={"hours": 0}).status_code == 400
    for _ in range(5):
        c.post("/api/demo/clock", json={"hours": 72})
    r = c.post("/api/demo/clock", json={"hours": 72})
    assert r.status_code == 400 and "days ahead" in r.json()["detail"]
    assert c.get("/api/config").json()["clock"]["offset_hours"] == 14 * 24
    c.post("/api/demo/reset")
    assert c.get("/api/config").json()["clock"]["offset_hours"] == 0


def test_fast_forward_runs_what_was_due(db):
    ids = load("granite-GE-5570.pdf")
    with session_scope() as s:
        assert s.execute(select(Job).where(Job.kind == "colleague_reply", Job.status == "queued")).scalar_one()
    c = TestClient(app)
    c.post("/api/demo/clock", json={"hours": 1})
    drain()
    assert inv(ids["GE-5570"]).status.value == "scheduled"


def test_model_investigation_loop(db, monkeypatch):
    ids = load("granite-GE-5570.pdf")
    replies = iter([
        {"tool": "open_pos", "args": {}, "why": "find the PO"},
        {"tool": "drop_tables", "args": {}, "why": "not a tool"},
        {"tool": "po", "args": {"po_number": "PO-24106"}, "why": "another vendor's PO"},
        {"done": True, "notes": "PO-24111 covers the only line; ask Marcus."},
    ])
    import tollgate.llm as llm

    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: next(replies))
    from tollgate import resolver

    with session_scope() as s:
        i = s.get(Invoice, ids["GE-5570"])
        notes = resolver.investigate(s, i, {"NO_PO"}, use_model=True)
        evs = [e.summary for e in s.execute(select(AuditEvent).where(AuditEvent.invoice_id == i.id, AuditEvent.kind == "tool").order_by(AuditEvent.id.desc()).limit(4)).scalars()]
    assert any("PO-24111 (Marcus Ode, covers 1/1 lines)" in e for e in evs)
    assert '"invoice_lines_covered": 1' in notes
    assert "no tool 'drop_tables'" in notes
    assert "no PO PO-24106 for this vendor" in notes  # tools stay inside the invoice's vendor
    assert any(e.startswith("Investigation:") for e in evs)


def test_colleague_questions_are_capped(db):
    ids = load("granite-GE-5570.pdf")
    with session_scope() as s:
        i = s.get(Invoice, ids["GE-5570"])
        res = agent._execute(s, i, {"type": "ask_colleague", "topic": "po_confirm", "po_number": "PO-24111", "subject": "x", "body": "y"})
        assert "still waiting" in res  # the same question is not asked twice
        for q in colleagues.questions(s, i.id):
            q.answer = "unknown"
        for n in range(2):
            s.add(ColleagueQuestion(invoice_id=i.id, topic="po_confirm", person_name="x", person_email="x", po_number=f"PO-0{n}", answer="no"))
        s.flush()
        with pytest.raises(agent.Denied, match="already asked 3 times"):
            agent._execute(s, i, {"type": "ask_colleague", "topic": "po_confirm", "po_number": "PO-24111", "subject": "x", "body": "y"})


def test_billing_errors_are_sent_to_the_vendor_not_a_colleague(db):
    ids = load("brightline-BIS-2077.pdf")
    with session_scope() as s:
        i = s.get(Invoice, ids["BIS-2077"])
        with pytest.raises(agent.Denied, match="PRICE_VARIANCE is the vendor's to fix: email_vendor"):
            agent._execute(s, i, {"type": "ask_colleague", "topic": "accept_charge", "po_number": "PO-24107", "line": 1})
