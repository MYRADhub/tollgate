from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tollgate import pipeline, statements
from tollgate.api import app
from tollgate.db import session_scope
from tollgate.models import EmailMessage, Invoice, Payment, Statement, VendorCredit
from tollgate.seed import VENDORS, spec_for, vendor_email
from tollgate.invoicegen import render
from tollgate.statements import StatementSpec, StLine
from tollgate.worker import drain

CTRL = {"user": "Rosa Kim", "role": "controller"}


@pytest.fixture
def c(db):
    client = TestClient(app)
    client.post("/api/demo/inbox", json=None)
    drain()
    return client


def load_demo(c):
    c.post("/api/demo/statements", json=None)
    drain()
    d = c.get("/api/statements").json()
    return {st["vendor"].split()[0]: st for st in d["statements"]}, d["credits"]


def items(st):
    return {x["reference"]: x for x in st["result"]["items"]}


def inv_by_number(c, n):
    r = next(r for r in c.get("/api/invoices").json() if r["number"] == n)
    return c.get(f"/api/invoices/{r['id']}").json()


def test_every_difference_is_explained_to_the_cent(c):
    sts, _ = load_demo(c)
    for st in sts.values():
        assert st["status"] == "reconciled" and st["result"]["unexplained"] == "0.00"
        assert Decimal(st["result"]["explained"]) == Decimal(st["result"]["vendor_balance"]) - Decimal(st["result"]["our_balance"])


def test_kestrel_unapplied_payment_duplicate_and_credit(c):
    sts, credits = load_demo(c)
    k = items(sts["Kestrel"])
    assert k["KFL-88812"]["kind"] == "unapplied_payment" and k["KFL-88812"]["paid_on"] == "2026-11-01"
    assert k["KFL-88812-R"]["kind"] == "disputed"
    assert k["CM-4471"]["kind"] == "credit" and k["CM-4471"]["credit_status"] == "open"
    with session_scope() as s:
        mail = s.execute(select(EmailMessage).where(EmailMessage.subject.like("Statement reconciliation, Kestrel%"))).scalar_one()
        assert "KFL-88812: 1,920.00 paid on 2026-11-01" in mail.body and mail.recipient == vendor_email("kestrel")


def test_brightline_missing_invoice_is_requested_and_never_paid(c):
    sts, _ = load_demo(c)
    b = items(sts["Brightline"])
    assert b["BIS-1987"]["kind"] == "missing"
    assert not any(r["number"] == "BIS-1987" for r in c.get("/api/invoices").json())
    with session_scope() as s:
        mail = s.execute(select(EmailMessage).where(EmailMessage.subject.like("Statement reconciliation, Brightline%"))).scalar_one()
        assert "BIS-1987" in mail.body and "confirm whether you issued" in mail.body and "BIS-2090" in mail.body


def test_an_invoice_the_vendor_does_not_list_is_held(c):
    sts, _ = load_demo(c)
    assert items(sts["Brightline"])["BIS-2090"]["kind"] == "not_on_statement"
    d = inv_by_number(c, "BIS-2090")
    assert d["status"] == "on_hold" and "NOT_ON_VENDOR_STATEMENT" in [f["code"] for f in d["findings"]]


def test_a_scheduled_payment_is_pulled_when_the_statement_omits_it(c):
    v = next(x for x in VENDORS if x.slug == "brightline")
    spec = StatementSpec(v.name, v.address, vendor_email("brightline"), date(2026, 11, 3),
                         [StLine(date(2026, 11, 1), "invoice", "BIS-2077", "Bearings", Decimal("1206.58"))])
    assert inv_by_number(c, "BIS-2041")["status"] == "scheduled"
    with session_scope() as s:
        statements.ingest(s, statements.render(spec), "brightline-statement.pdf")
    drain()
    d = inv_by_number(c, "BIS-2041")
    assert d["status"] in ("on_hold", "awaiting_vendor") and d["payment"] is None
    assert "NOT_ON_VENDOR_STATEMENT" in [f["code"] for f in d["findings"]]


def test_claiming_a_credit_needs_a_controller(c):
    _, credits = load_demo(c)
    r = c.post(f"/api/credits/{credits[0]['id']}/decide", json={"user": "Sam Patel", "role": "clerk", "approve": True})
    assert r.status_code == 400


def test_approved_credit_comes_off_a_scheduled_payment_with_remittance(c):
    _, credits = load_demo(c)
    cm = next(x for x in credits if x["reference"] == "CM-2207")
    before = inv_by_number(c, "BIS-2041")["payment"]["amount"]
    r = c.post(f"/api/credits/{cm['id']}/decide", json={**CTRL, "approve": True}).json()
    assert r["status"] == "applied" and r["applied_invoice_number"] == "BIS-2041"
    d = inv_by_number(c, "BIS-2041")
    assert d["payment"]["deductions"] == 156.2 and abs(d["payment"]["amount"] - (before - 156.2)) < 0.001
    assert any("Remittance advice" in e["subject"] and "CM-2207" in e["body"] for e in d["emails"])
    assert c.post(f"/api/credits/{cm['id']}/decide", json={**CTRL, "approve": True}).status_code == 400


def test_approved_credit_is_taken_from_the_next_invoice(c):
    _, credits = load_demo(c)
    cm = next(x for x in credits if x["reference"] == "CM-4471")
    assert c.post(f"/api/credits/{cm['id']}/decide", json={**CTRL, "approve": True}).json()["status"] == "approved"
    assert c.get("/api/stats").json()["credits_approved"] == 320.0
    nxt = spec_for("kestrel", "KFL-88901", date(2026, 11, 3), "PO-24103", [("FRT-LTL", "LTL freight, Denver to SLC, per load", 2, "640.00")], tax_rate=Decimal("0"))
    with session_scope() as s:
        pipeline.ingest(s, render(nxt), "kestrel-KFL-88901.pdf", source="email")
    drain()
    d = inv_by_number(c, "KFL-88901")
    assert d["status"] == "scheduled" and d["payment"]["deductions"] == 320.0 and d["payment"]["amount"] == 960.0
    with session_scope() as s:
        cr = s.get(VendorCredit, cm["id"])
        assert cr.status == "applied" and cr.applied_invoice_number == "KFL-88901"
    assert c.get("/api/stats").json()["credits_approved"] == 0


def test_declined_credit_is_not_taken(c):
    _, credits = load_demo(c)
    cm = next(x for x in credits if x["reference"] == "CM-2207")
    assert c.post(f"/api/credits/{cm['id']}/decide", json={**CTRL, "approve": False}).json()["status"] == "declined"
    assert inv_by_number(c, "BIS-2041")["payment"]["deductions"] == 0


def test_payments_the_vendor_recorded_match_and_net_to_zero(c):
    v = next(x for x in VENDORS if x.slug == "kestrel")
    spec = StatementSpec(v.name, v.address, vendor_email("kestrel"), date(2026, 11, 3), [
        StLine(date(2026, 10, 2), "invoice", "KFL-88812", "Freight", Decimal("1920.00")),
        StLine(date(2026, 11, 1), "payment", "PMT-1101", "Payment, thank you", Decimal("-1920.00")),
    ])
    with session_scope() as s:
        st = statements.ingest(s, statements.render(spec), "kestrel-statement.pdf")
        sid = st.id
    drain()
    with session_scope() as s:
        res = s.get(Statement, sid).result
    assert [x["kind"] for x in res["items"]] == ["matched"] and res["unexplained"] == "0.00"
    assert res["vendor_balance"] == "0.00" and res.get("emailed") is None


def test_unknown_vendor_statement_is_not_reconciled(db):
    spec = StatementSpec("Apex Strategic Advisory LLC", "1 Main St", "a@apex.example.com", date(2026, 11, 3),
                         [StLine(date(2026, 10, 1), "invoice", "ASA-0042", "Advisory", Decimal("7500.00"))])
    with session_scope() as s:
        sid = statements.ingest(s, statements.render(spec), "apex-statement.pdf").id
    drain()
    with session_scope() as s:
        st = s.get(Statement, sid)
        assert st.status == "unmatched_vendor" and st.result is None
        assert not s.execute(select(EmailMessage)).first()


def test_emailed_statement_is_routed_to_reconciliation(db):
    from email.message import EmailMessage as Mime

    from tollgate import mailer

    m = Mime()
    m["From"], m["To"], m["Subject"], m["Message-ID"] = vendor_email("kestrel"), "ap@halden.example.com", "Your November statement", "<st@x>"
    m.set_content("Statement attached.")
    m.add_attachment(statements.demo_statements()[0][3], maintype="application", subtype="pdf", filename="november.pdf")
    with session_scope() as s:
        mailer.handle_inbound(s, m.as_bytes())
        assert s.execute(select(Statement)).scalar_one() and not s.execute(select(Invoice).where(Invoice.source == "email")).first()


def test_normalise_flips_signs_checks_grounding_and_totals():
    d = statements.normalise({"vendor_name": "X", "lines": [
        {"type": "invoice", "reference": "a-1", "amount": "100.00"},
        {"type": "credit", "reference": "cm-1", "amount": 20},
        {"type": "invoice", "reference": "a-2", "amount": "55.55"},
    ], "balance": "80.00"}, "a-1 100.00 cm-1 -20.00 total 80.00")
    assert [x["amount"] for x in d["lines"]] == ["100.00", "-20.00", "55.55"]
    assert [x["grounded"] for x in d["lines"]] == [True, True, False]
    assert d["lines"][0]["reference"] == "A-1" and d["adds_up"] is False


def test_lab_invoices_are_ignored_by_reconciliation(c):
    c.post("/api/lab/attack", json={"template": "duplicate_altered"})
    drain()
    sts, _ = load_demo(c)
    refs = {x["reference"] for st in sts.values() for x in st["result"]["items"]}
    with session_scope() as s:
        lab = {n for n in s.execute(select(Invoice.number).where(Invoice.source == "lab")).scalars() if n}
    assert not (refs & lab)
