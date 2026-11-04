from email.message import EmailMessage as Mime

from sqlalchemy import select

from tollgate.config import Settings
from tollgate.db import session_scope
from tollgate.mailer import handle_inbound
from tollgate.models import EmailMessage, Invoice, Job


def test_aliases_use_tag_and_strip_existing_plus():
    s = Settings(gmail_address="jane.doe+old@gmail.com", mail_tag="tollgate")
    assert s.ap_address == "jane.doe+tollgate@gmail.com"
    assert s.alias("brightline") == "jane.doe+tollgate-brightline@gmail.com"
    assert Settings(gmail_address="").ap_address == "ap@halden.example.com"


def _msg(subject, *, out=False, pdf=False):
    m = Mime()
    m["From"] = "someone@example.com"
    m["To"] = "ap@halden.example.com"
    m["Subject"] = subject
    m["Message-ID"] = f"<{abs(hash(subject + str(out) + str(pdf)))}@t>"
    if out:
        m["X-Tollgate-Out"] = "1"
    m.set_content("hello")
    if pdf:
        m.add_attachment(b"%PDF-1.4 x", maintype="application", subtype="pdf", filename="a.pdf")
    return m.as_bytes()


def test_own_outbound_is_ignored(db):
    with session_scope() as s:
        assert handle_inbound(s, _msg("Invoice X [TG-aaaaaaaaaaaa]", out=True)) is None
        assert s.execute(select(EmailMessage)).first() is None


def test_unrelated_mail_without_pdf_is_ignored(db):
    with session_scope() as s:
        assert handle_inbound(s, _msg("lunch?")) is None


def test_reply_is_threaded_to_invoice(db):
    from tollgate import pipeline
    from tollgate.seed import demo_inbox

    with session_scope() as s:
        inv = pipeline.ingest(s, demo_inbox()[0].pdf(), "x.pdf")
        r = handle_inbound(s, _msg(f"Re: Invoice [TG-{inv.id}]"))
        assert r == f"reply for {inv.id}"
        assert s.execute(select(Job).where(Job.kind == "vendor_reply", Job.invoice_id == inv.id)).scalar_one()


def test_new_invoice_by_email(db):
    with session_scope() as s:
        r = handle_inbound(s, _msg("Invoice attached", pdf=True))
        assert r and "new invoice" in r
        assert s.execute(select(Invoice).where(Invoice.source == "email")).scalar_one()


def test_budget_guard_blocks_calls(db, monkeypatch):
    import pytest

    from tollgate import llm
    from tollgate.config import get_settings

    llm._record("glm-5.3", type("U", (), {"prompt_tokens": 1000, "completion_tokens": 1000})())
    assert abs(llm.spent_usd() - 0.006) < 1e-9
    llm.flush_spend()
    assert abs(llm.spent_usd() - 0.006) < 1e-9
    monkeypatch.setattr(get_settings(), "inference_budget_usd", 0.005)
    with pytest.raises(llm.BudgetExceeded):
        llm.chat("glm-5.3", [{"role": "user", "content": "hi"}])


def test_demo_reset_keeps_the_inference_spend(db):
    from tollgate import llm
    from tollgate.seed import reset_and_seed

    llm._record("glm-5.3", type("U", (), {"prompt_tokens": 1000, "completion_tokens": 0})())
    llm.flush_spend()
    with session_scope() as s:
        reset_and_seed(s)
    assert llm.spent_usd() >= 0.003
