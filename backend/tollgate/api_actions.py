"""Human actions. Each one is checked here, recorded in the audit chain, and
hands control back to the agent through the job queue."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit
from .models import (
    Approval,
    BankChange,
    GoodsReceipt,
    Invoice,
    InvoiceStatus,
    PurchaseOrder,
    ReceiptLine,
    Role,
    utcnow,
)
from .pipeline import enqueue

RANK = {Role.clerk: 0, Role.controller: 1, Role.cfo: 2}


class ActionError(ValueError):
    pass


def decide_approval(
    s: Session, approval_id: int, *, user: str, role: str, decision: str, comment: str | None = None, callback_note: str | None = None
) -> Approval:
    a = s.get(Approval, approval_id)
    if a is None:
        raise ActionError("approval not found")
    if a.decision is not None:
        raise ActionError("already decided")
    if decision not in ("approved", "rejected"):
        raise ActionError("decision must be approved or rejected")
    try:
        r = Role(role)
    except ValueError as e:
        raise ActionError("unknown role") from e
    user = (user or "").strip()
    if not user:
        raise ActionError("user required")
    if RANK[r] < RANK[a.required_role]:
        raise ActionError(f"needs {a.required_role.value} or above")

    if a.kind == "bank_change":
        siblings = list(s.execute(select(Approval).where(Approval.bank_change_id == a.bank_change_id, Approval.id != a.id)).scalars())
        bc = s.get(BankChange, a.bank_change_id)
        if decision == "approved":
            if any(x.decided_by and x.decided_by.lower() == user.lower() for x in siblings):
                raise ActionError("a bank change needs two different approvers")
            if not bc.callback_note and not (callback_note or "").strip():
                raise ActionError("record the callback to the phone number on file before approving")
            if callback_note:
                bc.callback_note = callback_note.strip()

    a.decision, a.decided_by, a.decided_role, a.comment, a.decided_at = decision, user, r, comment, utcnow()
    s.flush()
    audit.record(
        s,
        actor=f"{user} ({r.value})",
        kind=f"approval:{decision}",
        invoice_id=a.invoice_id,
        summary=f"{user} {decision} the {a.kind.replace('_', ' ')}" + (f": {comment}" if comment else "") + (f" | callback: {callback_note}" if callback_note else ""),
    )

    if a.kind == "payment":
        if decision == "approved":
            enqueue(s, "decide", a.invoice_id, {"trigger": f"{r.value} approved payment"})
        else:
            inv = s.get(Invoice, a.invoice_id)
            inv.status = InvoiceStatus.rejected
            audit.record(s, actor=f"{user} ({r.value})", kind="rejected", invoice_id=inv.id, summary=f"Invoice rejected by {user}")
    elif a.kind == "bank_change":
        bc = s.get(BankChange, a.bank_change_id)
        siblings = list(s.execute(select(Approval).where(Approval.bank_change_id == bc.id)).scalars())
        if decision == "rejected":
            bc.status = "rejected"
            for x in siblings:
                if x.decision is None:
                    x.decision, x.decided_by, x.decided_role, x.decided_at, x.comment = "rejected", user, r, utcnow(), "closed with the change"
            audit.record(s, actor=f"{user} ({r.value})", kind="bank_change_rejected", invoice_id=bc.invoice_id,
                         summary=f"Bank change for {bc.vendor.name} rejected; account on file unchanged")
            if bc.invoice_id:
                enqueue(s, "decide", bc.invoice_id, {"trigger": "bank change rejected after callback",
                                                     "extra": "A person rejected the requested bank change. Treat the remit-to details as fraudulent; keep the invoice on hold for a person and do not email the address on the document."})
        elif all(x.decision == "approved" for x in siblings):
            v = bc.vendor
            old = v.bank_account
            v.bank_account, v.bank_routing, v.bank_name, v.bank_verified_at = bc.new_account, bc.new_routing, bc.new_bank_name, utcnow()
            bc.status = "approved"
            audit.record(s, actor="system", kind="bank_change_applied", invoice_id=bc.invoice_id,
                         summary=f"{v.name} remit-to account changed from ...{(old or '')[-4:]} to ...{bc.new_account[-4:]} after callback and two approvals")
            if bc.invoice_id:
                enqueue(s, "recheck", bc.invoice_id, {"reason": "bank change verified"})
    return a


def record_receipt(s: Session, invoice_id: str, *, user: str) -> GoodsReceipt:
    """Receiving logs the rest of what this invoice bills for."""
    inv = s.get(Invoice, invoice_id)
    if inv is None or not inv.po_number:
        raise ActionError("invoice has no PO")
    po = s.execute(select(PurchaseOrder).where(PurchaseOrder.number == inv.po_number)).scalar_one_or_none()
    if po is None:
        raise ActionError("PO not found")
    received: dict[str, Decimal] = defaultdict(Decimal)
    for r in po.receipts:
        for rl in r.lines:
            received[rl.sku] += rl.quantity
    ordered = {pl.sku: pl.quantity for pl in po.lines}
    lines = []
    for sku, qty in ordered.items():
        missing = qty - received.get(sku, Decimal(0))
        if missing > 0:
            lines.append(ReceiptLine(sku=sku, quantity=missing))
    if not lines:
        raise ActionError("everything on this PO is already received")
    gr = GoodsReceipt(po_id=po.id, received_on=utcnow().date(), received_by=user, lines=lines)
    s.add(gr)
    s.flush()
    audit.record(s, actor=user, kind="goods_received", invoice_id=inv.id,
                 summary=f"{user} logged receipt on {po.number}: " + ", ".join(f"{ln.quantity.normalize():f} x {ln.sku}" for ln in lines))
    enqueue(s, "recheck", inv.id, {"reason": "goods receipt recorded"})
    return gr


def learn_fingerprint(s: Session, invoice_id: str, *, user: str) -> None:
    """A person confirmed the document is genuine: the vendor's model learns its layout."""
    from . import fingerprint
    from .models import VendorFingerprint

    inv = s.get(Invoice, invoice_id)
    if inv is None or inv.source == "lab" or not inv.vendor_id:
        return  # attack-lab experiments never teach the real models
    fp = s.get(VendorFingerprint, inv.vendor_id)
    doc = (inv.extraction or {}).get("fingerprint_features")
    if fp is None or not doc:
        return
    fp.model = fingerprint.learn(fp.model, doc, by=user, invoice=inv.number or inv.id, at=utcnow().isoformat())
    modes = fp.model.get("modes", [])
    fp.metrics = {**fp.metrics, "confirmed": len(fp.model["confirmed"]), "learned_layouts": [{"label": m["label"], "confirmed": m["confirmed"]} for m in modes]}
    audit.record(s, actor="agent", kind="fingerprint_learned", invoice_id=inv.id,
                 summary=f"{inv.vendor.name}'s fingerprint model learned a second layout ({doc.get('producer')}) from {inv.number}, confirmed genuine by {user}. "
                         "Its next invoices in this layout will pass; anything else is still checked against the usual one.")


def reject_invoice(s: Session, invoice_id: str, *, user: str, reason: str) -> Invoice:
    inv = s.get(Invoice, invoice_id)
    if inv is None:
        raise ActionError("invoice not found")
    if inv.status in (InvoiceStatus.paid, InvoiceStatus.scheduled):
        raise ActionError(f"invoice is already {inv.status.value}")
    inv.status = InvoiceStatus.rejected
    audit.record(s, actor=user, kind="rejected", invoice_id=inv.id, summary=f"{user} rejected the invoice: {reason}")
    return inv


def resolve_finding(s: Session, finding_id: int, *, user: str, role: str, justification: str) -> None:
    from .agent import human_resolve
    from .models import Finding

    if not justification.strip():
        raise ActionError("justification required")
    f = s.get(Finding, finding_id)
    if f is None:
        raise ActionError("finding not found")
    if f.code in ("BANK_MISMATCH",):
        raise ActionError("bank mismatches are cleared only through the bank change process")
    if f.code in ("PROMPT_INJECTION", "DOC_FINGERPRINT") and Role(role) == Role.clerk:
        raise ActionError("a controller must clear a quarantined document" if f.code == "PROMPT_INJECTION"
                          else "a controller must confirm a document the vendor's fingerprint model rejected")
    human_resolve(s, finding_id, f"{user} ({role})", justification)
    if f.code == "DOC_FINGERPRINT":
        learn_fingerprint(s, f.invoice_id, user=user)
    enqueue(s, "decide", f.invoice_id, {"trigger": f"{user} cleared {f.code}"})
