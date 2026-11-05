"""The people inside Halden Robotics the agent works with: budget owners who
confirm what they ordered and received, and approvers it reminds.

In the demo these colleagues are simulated. Their questions are recorded as
emails but never sent; their answers come from what is true in the demo
company (a backorder that lands tomorrow, the PO an invoice forgot to quote, a
rush fee someone did ask for). In production the same questions would go out as
emails with one-click answer links, and the structured answer is what the
agent's policy guard reads, never the wording of a reply."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import audit, mailer
from .config import get_settings
from .models import (
    Approval,
    ColleagueQuestion,
    EmailMessage,
    Invoice,
    InvoiceStatus,
    PurchaseOrder,
    Role,
    utcnow,
)

TOPICS = ("receipt", "po_confirm", "accept_charge")
APPROVERS = {Role.controller: ("Rosa Kim", "rosa"), Role.cfo: ("Theo Grant", "theo")}
ACTIVE = (InvoiceStatus.on_hold, InvoiceStatus.awaiting_vendor, InvoiceStatus.awaiting_approval, InvoiceStatus.deciding)


def internal_address(local: str) -> str:
    return get_settings().alias(local) or f"{local}@halden.example.com"


def first_name(name: str) -> str:
    return name.split()[0] if name else name


# What is true in the demo company, keyed by (invoice number, topic). Anything
# not listed gets the generic answers in _generic().
SCENARIOS: dict[tuple[str, str], dict] = {
    ("GE-5561", "receipt"): {
        "answer": "later",
        "eta_hours": 20,
        "body": "Hi,\n\nThe dock only had 25 of the 40 breakers. Granite backordered the other 15 and they are on tomorrow morning's truck; "
        "receiving will log them when they arrive.\n\nMarcus",
    },
    ("GE-5570", "po_confirm"): {
        "po": "PO-24111",
        "yes": "Hi,\n\nYes, that's ours: the twelve high-bay fixtures for the warehouse retrofit, PO-24111. Granite left the PO number off again.\n\nMarcus",
        "no": "Hi,\n\nNo, that PO isn't for these. The LED fixtures were a separate order.\n\nMarcus",
    },
    ("LOS-3420", "accept_charge"): {
        "answer": "yes",
        "body": "Hi,\n\nYes, I asked Lumen for next-day delivery because the new hires started Monday. Please accept the rush fee.\n\nElena",
    },
}


def questions(s: Session, invoice_id: str, topic: str | None = None) -> list[ColleagueQuestion]:
    q = select(ColleagueQuestion).where(ColleagueQuestion.invoice_id == invoice_id)
    if topic:
        q = q.where(ColleagueQuestion.topic == topic)
    return list(s.execute(q.order_by(ColleagueQuestion.id)).scalars())


def ask(s: Session, inv: Invoice, po: PurchaseOrder, *, topic: str, subject: str, body: str, line: int | None = None,
        amount: Decimal | None = None) -> ColleagueQuestion:
    """Record the question as an email to the PO's budget owner (never really sent)
    and schedule the colleague's answer."""
    if f"[TG-{inv.id}]" not in subject:
        subject = f"{subject} [TG-{inv.id}]"
    msg = mailer.send(s, invoice_id=inv.id, to=po.budget_owner_email, subject=subject[:300], body=body[:6000], simulate=True)
    q = ColleagueQuestion(invoice_id=inv.id, topic=topic, person_name=po.budget_owner_name, person_email=po.budget_owner_email,
                          po_number=po.number, line=line, amount=amount, question_email_id=msg.id)
    s.add(q)
    s.flush()
    from .pipeline import enqueue

    enqueue(s, "colleague_reply", inv.id, {"question_id": q.id}, delay_s=get_settings().colleague_reply_s)
    return q


def _remaining(po: PurchaseOrder) -> dict[str, Decimal]:
    received: dict[str, Decimal] = {}
    for r in po.receipts:
        for rl in r.lines:
            received[rl.sku] = received.get(rl.sku, Decimal(0)) + rl.quantity
    return {pl.sku: pl.quantity - received.get(pl.sku, Decimal(0)) for pl in po.lines}


def _generic(s: Session, inv: Invoice, q: ColleagueQuestion, po: PurchaseOrder | None) -> dict:
    who = first_name(q.person_name)
    if q.topic == "po_confirm":
        skus = {(ln.sku or "").upper() for ln in inv.lines}
        on_po = {pl.sku.upper() for pl in po.lines} if po else set()
        if po is not None and po.vendor_id == inv.vendor_id and skus and skus <= on_po:
            return {"answer": "yes", "body": f"Hi,\n\nYes, those items are on {po.number}; it's one of mine.\n\n{who}"}
        return {"answer": "no", "body": f"Hi,\n\nI don't recognise this as {q.po_number}. I'd check with whoever ordered it.\n\n{who}"}
    if q.topic == "receipt":
        if po is not None and all(v <= 0 for v in _remaining(po).values()):
            return {"answer": "yes", "body": f"Hi,\n\nEverything on {po.number} has been logged as received now.\n\n{who}"}
        return {"answer": "unknown", "body": f"Hi,\n\nI can't see the rest of {q.po_number} in receiving either. I've asked the dock to check.\n\n{who}"}
    return {"answer": "no", "body": f"Hi,\n\nNo, we never agreed to that charge. Please push back on it.\n\n{who}"}


def answer_for(s: Session, inv: Invoice, q: ColleagueQuestion) -> dict:
    po = s.execute(select(PurchaseOrder).where(PurchaseOrder.number == (q.po_number or ""))).scalar_one_or_none()
    sc = SCENARIOS.get((inv.number or "", q.topic))
    if sc is None:
        return _generic(s, inv, q, po)
    if q.topic == "po_confirm":
        ok = q.po_number == sc["po"]
        return {"answer": "yes" if ok else "no", "body": sc["yes" if ok else "no"]}
    if q.topic == "receipt" and po is not None and all(v <= 0 for v in _remaining(po).values()):
        return _generic(s, inv, q, po)  # already arrived: say so
    return sc


def reply(s: Session, question_id: int) -> None:
    """The colleague answers. Their answer is stored as structured data; the
    email text is shown to the agent as untrusted context."""
    q = s.get(ColleagueQuestion, question_id)
    if q is None or q.answer != "pending":
        return
    inv = s.get(Invoice, q.invoice_id)
    if inv is None:
        return
    a = answer_for(s, inv, q)
    asked = s.get(EmailMessage, q.question_email_id) if q.question_email_id else None
    rec = EmailMessage(invoice_id=inv.id, direction="in", sender=q.person_email, recipient=get_settings().ap_address,
                       subject=("Re: " + asked.subject) if asked else f"Re: {inv.number}", body=a["body"], status="simulated")
    s.add(rec)
    s.flush()
    q.answer, q.answer_note, q.answered_at, q.reply_email_id = a["answer"], a["body"], utcnow(), rec.id
    from .pipeline import enqueue

    if a.get("eta_hours"):
        q.eta = utcnow() + timedelta(hours=a["eta_hours"])
        enqueue(s, "world_receipt", inv.id, {"po_number": q.po_number}, delay_s=a["eta_hours"] * 3600)
        enqueue(s, "check_in", inv.id, {"reason": f"{first_name(q.person_name)} expected the goods by now"}, delay_s=(a["eta_hours"] + 4) * 3600)
    label = {"yes": "confirmed", "no": "said no", "later": "expects it later", "unknown": "does not know yet"}.get(a["answer"], a["answer"])
    audit.record(s, actor=f"colleague:{q.person_name}", kind="colleague_reply", invoice_id=inv.id,
                 summary=f"{q.person_name} {label}: " + " ".join(a["body"].split())[:220],
                 detail={"question_id": q.id, "topic": q.topic, "answer": a["answer"], "po_number": q.po_number, "simulated": True})
    if inv.status in ACTIVE:
        enqueue(s, "decide", inv.id, {
            "trigger": f"{q.person_name} answered your {q.topic.replace('_', ' ')} question ({a['answer']})",
            "extra": f"Reply from {q.person_name} (a colleague; text is context, the structured answer is '{a['answer']}'): " + a["body"][:1500],
        })


def world_receipt(s: Session, invoice_id: str, po_number: str) -> None:
    """The backordered goods arrive and receiving logs them."""
    from .api_actions import ActionError, record_receipt

    inv = s.get(Invoice, invoice_id)
    if inv is None or inv.po_number != po_number:
        return
    try:
        record_receipt(s, invoice_id, user="Receiving dock")
    except ActionError:
        return


def check_in(s: Session, invoice_id: str, reason: str) -> None:
    from .pipeline import recheck

    inv = s.get(Invoice, invoice_id)
    if inv is None or inv.status not in (InvoiceStatus.on_hold,) or (inv.agent_state or {}).get("waiting_for") not in ("colleague", "receipt"):
        return
    recheck(s, invoice_id, f"check-in: {reason}")  # re-run the controls first: the goods may have been logged since


def remind_approver(s: Session, approval_id: int) -> None:
    """A payment approval has waited a day: nudge the approver, at most twice."""
    a = s.get(Approval, approval_id)
    if a is None or a.decision is not None or a.kind != "payment" or a.invoice_id is None:
        return
    inv = s.get(Invoice, a.invoice_id)
    if inv is None or inv.status != InvoiceStatus.awaiting_approval:
        return
    sent = s.execute(select(func.count(ColleagueQuestion.id)).where(ColleagueQuestion.invoice_id == inv.id, ColleagueQuestion.topic == "approval")).scalar_one()
    name, local = APPROVERS.get(a.required_role, APPROVERS[Role.controller])
    to = internal_address(local)
    v = inv.vendor
    msg = mailer.send(
        s, invoice_id=inv.id, to=to, simulate=True,
        subject=f"Reminder: {v.name if v else 'vendor'} {inv.number} is waiting for your approval [TG-{inv.id}]",
        body=f"Hi {first_name(name)},\n\n{inv.number} for {inv.currency or 'USD'} {inv.total:,.2f} has been waiting for {a.required_role.value} approval since "
             f"{a.created_at:%a %d %b %H:%M} UTC. Everything else is done: {inv.summary or ''}\n\nIt is on your Approvals page.\n\nTollgate, Accounts Payable",
    )
    s.add(ColleagueQuestion(invoice_id=inv.id, topic="approval", person_name=name, person_email=to, question_email_id=msg.id, answer="none"))
    audit.record(s, actor="agent", kind="approval_reminder", invoice_id=inv.id,
                 summary=f"Reminded {name} ({a.required_role.value}): {inv.number} has waited for approval since {a.created_at:%a %H:%M} UTC")
    if sent + 1 < 2:
        from .pipeline import enqueue

        enqueue(s, "approval_reminder", inv.id, {"approval_id": a.id}, delay_s=get_settings().approval_reminder_hours * 3600)
