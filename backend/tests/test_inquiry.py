from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tollgate import inquiry, llm
from tollgate import config as cfgmod
from tollgate.api import app
from tollgate.db import session_scope
from tollgate.models import AuditEvent, EmailMessage, Vendor
from tollgate.worker import drain


def ask(c, key=None, **override):
    p = next(x for x in c.get("/api/demo/inquiry-presets").json() if x["key"] == (key or "status"))
    msg = {**{k: p[k] for k in ("sender", "subject", "body")}, **override}
    assert c.post("/api/demo/inquiry", json=msg).status_code == 200
    drain()
    return c.get("/api/inquiries").json()["items"][0]


@pytest.fixture
def c(db):
    client = TestClient(app)
    client.post("/api/demo/inbox", json=None)
    drain()
    return client


def test_registered_vendor_gets_status_from_the_ledger(c):
    q = ask(c, "status")
    assert q["match"] == "address" and q["intent"] == "payment_status" and q["outcome"] == "answered"
    assert "BIS-2077" in q["reply"]["body"] and "waiting for you" in q["reply"]["body"]


def test_short_payment_is_explained_with_the_contract_deduction(c):
    q = ask(c, "deduction")
    assert q["intent"] == "deduction_question"
    body = q["reply"]["body"]
    assert "USD 975.00" in body and "Service credit" in body and "December 1, 2026" in body


def test_another_vendors_invoice_is_treated_as_not_found(c):
    q = ask(c, "fishing")
    body = q["reply"]["body"]
    assert "could not find invoice VCS-10488" in body
    assert "5,184" not in body and "Vantage" not in body and "9044" not in body
    assert "asked_about_other_invoices" in q["flags"]


def test_bank_change_by_email_is_refused_and_nothing_changes(c):
    with session_scope() as s:
        before = s.execute(select(Vendor.bank_account).where(Vendor.name == "Vantage Cloud Services")).scalar_one()
    q = ask(c, "bank")
    assert q["intent"] == "bank_change" and "bank_change_request" in q["flags"]
    assert "never change bank" in q["reply"]["body"] and "VCS-10488" not in q["reply"]["body"]
    with session_scope() as s:
        assert s.execute(select(Vendor.bank_account).where(Vendor.name == "Vantage Cloud Services")).scalar_one() == before
        ev = s.execute(select(AuditEvent).where(AuditEvent.kind == "inquiry").order_by(AuditEvent.id.desc())).scalars().first()
        assert ev.actor == "policy"


def test_lookalike_domain_gets_nothing(c):
    q = ask(c, "spoof")
    assert q["match"] == "lookalike" and "impersonation" in q["flags"] and q["facts"] is None
    body = q["reply"]["body"]
    assert "could not match" in body and "BIS-" not in body and "$" not in body


def test_instructions_in_the_email_are_flagged_and_change_nothing(c):
    q = ask(c, "injection")
    assert "ai_instructions" in q["flags"]
    assert all(n.startswith("KFL-") for n in inquiry.INVOICE_TOKEN.findall(q["reply"]["body"]))


def test_unknown_and_freemail_senders_are_not_matched_by_domain(db):
    with session_scope() as s:
        assert inquiry.identify(s, "someone@gmail.com").match == "unknown"
        v = s.execute(select(Vendor).where(Vendor.name == "Polaris Network Services")).scalar_one()
        dom = v.email.split("@")[1]
        assert inquiry.identify(s, f"controller@{dom}").match == "domain"
        assert inquiry.identify(s, v.email.upper()).vendor.id == v.id
        assert inquiry.identify(s, v.email, "mx.google.com; dmarc=fail (p=NONE)").match == "auth_failed"


def test_automatic_messages_are_not_answered(c):
    with session_scope() as s:
        from tollgate import mailer

        raw = (b"From: billing@polaris.example.com\r\nTo: ap@halden.example.com\r\nSubject: Out of office\r\n"
               b"Auto-Submitted: auto-replied\r\nMessage-ID: <ooo@x>\r\n\r\nI am away until Monday.\r\n")
        mailer.handle_inbound(s, raw)
    drain()
    q = c.get("/api/inquiries").json()["items"][0]
    assert q["outcome"].startswith("not answered") and q["reply"] is None


def test_replies_per_sender_are_capped(c, monkeypatch):
    monkeypatch.setattr(inquiry, "MAX_REPLIES_PER_SENDER_PER_DAY", 2)
    outcomes = [ask(c, "status")["outcome"] for _ in range(3)]
    assert outcomes == ["answered", "answered", "not answered: reply limit for this sender reached"]


FACTS = {"vendor": "Polaris", "invoices": [{"invoice": "PNS-55120", "amount": "6,500.00", "currency": "USD", "status": "scheduled",
                                            "pay_date": "December 1, 2026", "pay_amount": "5,525.00", "deductions": [{"reason": "SLA credit", "amount": "975.00"}]}],
         "not_on_your_account": []}


@pytest.mark.parametrize("draft,problem", [
    ("We will pay USD 5,525.00 on December 1, 2026 for PNS-55120.", None),
    ("We will pay $5,525 on Dec 1 after deducting $975.", None),
    ("We will pay $5,600.00 on December 1, 2026.", "amount"),
    ("Payment goes out on Dec 3.", "date"),
    ("Payment goes out on 12/3.", "date"),
    ("PNS-55120 and VCS-10488 are both scheduled.", "reference"),
    ("We pay you at account 6120 3391 0457.", "digits"),
    ("We cannot share Vantage's remittance details.", "another supplier"),
])
def test_draft_verifier(draft, problem):
    probs = inquiry.verify_draft(draft, FACTS, {"PNS-55120", "VCS-10488"}, ["Vantage Cloud Services", "Lumen Office Supply"])
    if problem is None:
        assert probs == []
    else:
        assert probs and problem in probs[0]


def _fake_chat(text):
    return lambda *a, **k: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def test_model_draft_is_used_only_when_grounded(c, monkeypatch):
    monkeypatch.setattr(cfgmod.get_settings(), "inference_api_key", "set")
    monkeypatch.setattr(inquiry, "classify", lambda subj, body: inquiry.classify_offline(subj, body))
    monkeypatch.setattr(llm, "chat", _fake_chat("Hi, PNS-55120 will be paid USD 5,525.00 on December 1, 2026, after a USD 975.00 service credit. Halden Robotics Accounts Payable"))
    q = ask(c, "deduction")
    assert q["reply_source"] == "model" and q["draft_problems"] == []
    monkeypatch.setattr(llm, "chat", _fake_chat("Hi, PNS-55120 will be paid in full, USD 6,500.00, on December 2, 2026."))
    q = ask(c, "deduction")
    assert q["reply_source"] == "template" and any("date" in p for p in q["draft_problems"])
    assert "USD 975.00" in q["reply"]["body"]


def test_bank_request_needs_the_policy_in_the_draft(c, monkeypatch):
    monkeypatch.setattr(cfgmod.get_settings(), "inference_api_key", "set")
    monkeypatch.setattr(inquiry, "classify", lambda subj, body: inquiry.classify_offline(subj, body))
    monkeypatch.setattr(llm, "chat", _fake_chat("Thanks, we have updated your account."))
    q = ask(c, "bank")
    assert q["reply_source"] == "template" and "never change bank" in q["reply"]["body"]


def test_a_model_cannot_route_a_bank_request_around_the_policy(monkeypatch):
    monkeypatch.setattr(cfgmod.get_settings(), "inference_api_key", "set")
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"intent": "payment_status", "invoice_numbers": []})
    assert inquiry.classify("Remittance", "Please update our bank account to 1234 5678 9012").intent == "bank_change"


def test_demo_inquiry_validates_input(db):
    c = TestClient(app)
    assert c.post("/api/demo/inquiry", json={"sender": "nobody", "subject": "x", "body": "y"}).status_code == 400
