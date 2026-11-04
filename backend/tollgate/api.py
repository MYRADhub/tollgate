"""HTTP API for the Tollgate web app."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from . import api_actions, audit, pipeline
from .agent import required_role
from .config import get_settings
from .db import SessionLocal, get_session, init_db, session_scope
from .models import (
    Approval,
    AuditEvent,
    Contract,
    ContractTerm,
    CriticReview,
    ServiceMetric,
    BankChange,
    EmailMessage,
    Finding,
    Invoice,
    InvoiceStatus,
    Job,
    Payment,
    PaymentRun,
    PurchaseOrder,
    Severity,
    Vendor,
    utcnow,
)
from .storage import get_store

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with session_scope() as s:
        if s.execute(select(func.count(Vendor.id))).scalar_one() == 0:
            from .seed import reset_and_seed

            reset_and_seed(s)
    yield


app = FastAPI(title="Tollgate", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

_uploads: deque[float] = deque()


def _rate_limit() -> None:
    now = time.time()
    while _uploads and now - _uploads[0] > 3600:
        _uploads.popleft()
    if len(_uploads) >= settings.max_uploads_per_hour:
        raise HTTPException(429, "Upload limit reached for this demo; try again later.")
    _uploads.append(now)


def j(x):
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, datetime):
        if x.tzinfo is None:  # SQLite drops the zone; every timestamp here is UTC
            x = x.replace(tzinfo=timezone.utc)
        return x.isoformat()
    if isinstance(x, date):
        return x.isoformat()
    if hasattr(x, "value"):
        return x.value
    return x


def ser(obj, fields: list[str]) -> dict:
    return {f: j(getattr(obj, f)) for f in fields}


INV_FIELDS = [
    "id", "status", "source", "file_name", "number", "po_number", "vendor_name_raw", "vendor_id", "invoice_date", "due_date",
    "currency", "subtotal", "tax", "total", "summary", "created_at", "updated_at", "supersedes_id",
]


def invoice_row(inv: Invoice) -> dict:
    d = ser(inv, INV_FIELDS)
    d["vendor_name"] = inv.vendor.name if inv.vendor else inv.vendor_name_raw
    open_block = [f for f in inv.findings if f.severity == Severity.block and not f.resolved]
    d["blocking"] = len(open_block)
    d["flags"] = sorted({f.code for f in open_block})
    d["at_risk"] = float(max((f.amount_at_risk or 0 for f in open_block), default=0))
    d["waiting_for"] = (inv.agent_state or {}).get("waiting_for")
    rec = [f for f in inv.findings if f.severity == Severity.recover and not f.resolved]
    d["recover"] = sorted({f.code for f in rec})
    d["recover_amount"] = float(sum((f.amount_at_risk or 0) for f in rec))
    return d


# --------------------------------------------------------------------------- reads


@app.get("/api/health")
def health():
    return {"ok": True, "inference": bool(settings.inference_api_key), "mail": settings.mail_enabled, "storage": "s3" if settings.s3_endpoint else "local"}


@app.get("/api/config")
def config():
    from .llm import spent_usd

    return {
        "inference_spent_usd": round(spent_usd(), 4),
        "inference_budget_usd": settings.inference_budget_usd,
        "auto_pay_limit": settings.auto_pay_limit,
        "controller_limit": settings.controller_limit,
        "price_tolerance_pct": settings.price_tolerance_pct,
        "models": {"vision": settings.model_vision, "reasoning": settings.model_reasoning, "critic": settings.model_critic, "safety": settings.model_safety},
        "inference": bool(settings.inference_api_key),
        "mail": settings.mail_enabled,
        "mailbox": settings.gmail_address or None,
        "storage": "Vultr Object Storage" if settings.s3_endpoint else "local disk",
        "database": "PostgreSQL" if settings.database_url.startswith("postgres") else "SQLite",
        "controls": pipeline.checks_run(),
        "demo_mode": settings.demo_mode,
    }


@app.get("/api/stats")
def stats(s: Session = Depends(get_session)):
    invs = list(s.execute(select(Invoice).where(Invoice.source.not_in(["history", "lab"]))).scalars())
    by_status: dict[str, int] = {}
    for i in invs:
        by_status[i.status.value] = by_status.get(i.status.value, 0) + 1
    decided = [i for i in invs if i.status.value not in ("received", "extracting", "checking", "deciding", "superseded")]
    touchless = [
        i for i in invs if i.status in (InvoiceStatus.scheduled, InvoiceStatus.paid) and not any(f.severity == Severity.block for f in i.findings)
        and not s.execute(select(Approval.id).where(Approval.invoice_id == i.id)).first()
    ]
    prevented = Decimal(0)
    caught = []
    for i in invs:
        blocks = [f for f in i.findings if f.severity == Severity.block]
        if not blocks or i.status in (InvoiceStatus.superseded,):
            continue
        if i.status in (InvoiceStatus.scheduled, InvoiceStatus.paid):
            continue
        amt = max((f.amount_at_risk or Decimal(0) for f in blocks), default=Decimal(0))
        prevented += amt
        caught.append({"id": i.id, "number": i.number, "codes": sorted({f.code for f in blocks}), "amount": float(amt)})
    corrected = Decimal(0)
    for i in invs:
        if i.supersedes_id and i.status in (InvoiceStatus.scheduled, InvoiceStatus.paid):
            old = s.get(Invoice, i.supersedes_id)
            if old and old.total and i.total:
                corrected += max(old.total - i.total, Decimal(0))
    real = select(Invoice.id).where(Invoice.source != "lab")
    recovered = s.execute(select(func.coalesce(func.sum(Payment.deductions), 0)).where(Payment.invoice_id.in_(real))).scalar_one() or 0
    # What a person sees: one item per payment approval, one per bank change (whatever its slots)
    pending = list(s.execute(select(Approval.kind, Approval.bank_change_id, Approval.id).where(Approval.decision.is_(None), Approval.invoice_id.in_(real))).all())
    pending_approvals = len({(k, bc) if k == "bank_change" else (k, i) for k, bc, i in pending})
    scheduled_total = s.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status.in_(["scheduled", "released"]), Payment.run_id.is_not(None) | (Payment.status == "scheduled"))).scalar_one()
    discounts = s.execute(select(func.coalesce(func.sum(Payment.discount), 0)).where(Payment.invoice_id.in_(real))).scalar_one() or 0
    return {
        "invoices": len(invs),
        "by_status": by_status,
        "decided": len(decided),
        "touchless": len(touchless),
        "touchless_rate": (len(touchless) / len(decided)) if decided else 0,
        "prevented": float(prevented + corrected),
        "recovered": float(recovered),
        "discounts": float(discounts),
        "caught": caught,
        "pending_approvals": pending_approvals,
        "scheduled_total": float(scheduled_total or 0),
        "queue": s.execute(select(func.count(Job.id)).where(Job.status.in_(["queued", "running"]), Job.run_after <= utcnow())).scalar_one(),
        "scheduled_followups": s.execute(select(func.count(Job.id)).where(Job.status == "queued", Job.run_after > utcnow())).scalar_one(),
    }


@app.get("/api/invoices")
def list_invoices(status: str | None = None, s: Session = Depends(get_session)):
    q = select(Invoice).where(Invoice.source.not_in(["history", "lab"])).order_by(Invoice.created_at.desc())
    if status:
        q = q.where(Invoice.status.in_([InvoiceStatus(x) for x in status.split(",")]))
    return [invoice_row(i) for i in s.execute(q).scalars()]


@app.get("/api/invoices/{invoice_id}")
def get_invoice(invoice_id: str, s: Session = Depends(get_session)):
    inv = s.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(404)
    po = s.execute(select(PurchaseOrder).where(PurchaseOrder.number == (inv.po_number or ""))).scalar_one_or_none()
    d = invoice_row(inv)
    d.update(ser(inv, ["remit_bank_name", "remit_account", "remit_routing"]))
    d["extraction"] = inv.extraction or {}
    d["pages"] = int((inv.extraction or {}).get("pages") or 1)
    d["line_matches"] = (inv.agent_state or {}).get("line_matches", [])
    d["agent_state"] = {k: v for k, v in (inv.agent_state or {}).items() if k != "line_matches"}
    d["lines"] = [ser(ln, ["position", "sku", "description", "quantity", "unit_price", "amount"]) for ln in inv.lines]
    d["findings"] = [ser(f, ["id", "code", "severity", "title", "detail", "evidence", "amount_at_risk", "resolved", "resolution", "resolved_by"]) for f in inv.findings]
    d["vendor"] = (
        ser(inv.vendor, ["id", "name", "email", "tax_id", "bank_name", "bank_account", "bank_routing", "bank_verified_at", "payment_terms_days", "status"])
        if inv.vendor else None
    )
    if po:
        received: dict[str, float] = {}
        for r in po.receipts:
            for rl in r.lines:
                received[rl.sku] = received.get(rl.sku, 0) + float(rl.quantity)
        d["po"] = {
            **ser(po, ["number", "department", "budget_owner_name", "budget_owner_email", "currency", "status", "issued_on"]),
            "lines": [{**ser(pl, ["sku", "description", "quantity", "unit_price"]), "received": received.get(pl.sku, 0)} for pl in po.lines],
        }
    else:
        d["po"] = None
    d["approvals"] = [
        ser(a, ["id", "kind", "required_role", "reason", "decision", "decided_by", "decided_role", "comment", "created_at", "decided_at", "bank_change_id"])
        for a in s.execute(select(Approval).where(Approval.invoice_id == inv.id).order_by(Approval.id)).scalars()
    ]
    d["emails"] = [
        ser(e, ["id", "direction", "sender", "recipient", "subject", "body", "attachments", "status", "created_at"])
        for e in s.execute(select(EmailMessage).where(EmailMessage.invoice_id == inv.id).order_by(EmailMessage.id)).scalars()
    ]
    pay = s.execute(select(Payment).where(Payment.invoice_id == inv.id)).scalar_one_or_none()
    d["payment"] = ser(pay, ["gross", "deductions", "discount", "amount", "currency", "pay_to_account", "pay_to_routing", "scheduled_for",
                             "due_date", "discount_deadline", "discount_pct", "status", "run_id"]) if pay else None
    bc = s.execute(select(BankChange).where(BankChange.invoice_id == inv.id)).scalar_one_or_none()
    d["bank_change"] = ser(bc, ["id", "old_account", "new_account", "new_routing", "new_bank_name", "status", "callback_note"]) if bc else None
    chain_ids = [inv.id]
    if inv.supersedes_id:
        chain_ids.append(inv.supersedes_id)
    d["timeline"] = [
        ser(e, ["id", "actor", "kind", "summary", "detail", "created_at", "hash", "invoice_id"])
        for e in s.execute(select(AuditEvent).where(AuditEvent.invoice_id.in_(chain_ids)).order_by(AuditEvent.id)).scalars()
    ]
    d["superseded_by"] = s.execute(select(Invoice.id).where(Invoice.supersedes_id == inv.id)).scalar_one_or_none()
    d["critic"] = [
        ser(r, ["id", "verdict", "summary", "points", "independent_amount", "model", "proposal", "created_at"])
        for r in s.execute(select(CriticReview).where(CriticReview.invoice_id == inv.id).order_by(CriticReview.id)).scalars()
    ]
    d["controls_count"] = len(pipeline.checks_run())
    d["min_role"] = (inv.agent_state or {}).get("min_role")
    from .agent import needed_role

    nr = needed_role(inv)
    d["approval_needed"] = nr.value if nr else None
    return d


@app.get("/api/invoices/{invoice_id}/file")
def invoice_file(invoice_id: str, s: Session = Depends(get_session)):
    inv = s.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(404)
    return Response(get_store().get(inv.file_key), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{inv.file_name}"'})


@app.get("/api/invoices/{invoice_id}/pages/{page}.png")
def invoice_page(invoice_id: str, page: int, s: Session = Depends(get_session)):
    import io

    import pypdfium2 as pdfium

    inv = s.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(404)
    doc = pdfium.PdfDocument(get_store().get(inv.file_key))
    try:
        if not 0 <= page < min(len(doc), 4):
            raise HTTPException(404)
        img = doc[page].render(scale=2.0).to_pil()
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
    finally:
        doc.close()
    return Response(out.getvalue(), media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/approvals")
def list_approvals(pending: bool = True, s: Session = Depends(get_session)):
    q = select(Approval).where(Approval.invoice_id.in_(select(Invoice.id).where(Invoice.source != "lab"))).order_by(Approval.id.desc())
    if pending:
        q = q.where(Approval.decision.is_(None))
    out = []
    for a in s.execute(q).scalars():
        d = ser(a, ["id", "kind", "required_role", "reason", "decision", "decided_by", "decided_role", "created_at", "invoice_id", "bank_change_id"])
        inv = s.get(Invoice, a.invoice_id) if a.invoice_id else None
        if inv:
            d["invoice"] = invoice_row(inv)
        if a.bank_change_id:
            bc = s.get(BankChange, a.bank_change_id)
            d["bank_change"] = {**ser(bc, ["old_account", "new_account", "new_bank_name", "status", "callback_note"]), "vendor": bc.vendor.name}
            d["other_approvers"] = [
                x.decided_by for x in s.execute(select(Approval).where(Approval.bank_change_id == bc.id, Approval.id != a.id)).scalars() if x.decided_by
            ]
        out.append(d)
    return out


@app.get("/api/vendors")
def vendors(s: Session = Depends(get_session)):
    out = []
    for v in s.execute(select(Vendor).order_by(Vendor.name)).scalars():
        d = ser(v, ["id", "name", "email", "tax_id", "bank_name", "bank_account", "bank_routing", "bank_verified_at", "payment_terms_days", "status"])
        d["invoices"] = s.execute(select(func.count(Invoice.id)).where(Invoice.vendor_id == v.id)).scalar_one()
        d["exceptions"] = s.execute(
            select(func.count(func.distinct(Finding.invoice_id))).join(Invoice, Invoice.id == Finding.invoice_id).where(Invoice.vendor_id == v.id, Finding.severity == Severity.block)
        ).scalar_one()
        out.append(d)
    return out


@app.get("/api/purchase-orders")
def purchase_orders(s: Session = Depends(get_session)):
    out = []
    for po in s.execute(select(PurchaseOrder).order_by(PurchaseOrder.number)).scalars():
        received: dict[str, float] = {}
        for r in po.receipts:
            for rl in r.lines:
                received[rl.sku] = received.get(rl.sku, 0) + float(rl.quantity)
        out.append({
            **ser(po, ["number", "department", "budget_owner_name", "status", "issued_on", "currency"]),
            "vendor": po.vendor.name,
            "total": float(sum(pl.quantity * pl.unit_price for pl in po.lines)),
            "lines": [{**ser(pl, ["sku", "description", "quantity", "unit_price"]), "received": received.get(pl.sku, 0)} for pl in po.lines],
        })
    return out


@app.get("/api/payments")
def payments(s: Session = Depends(get_session)):
    out = []
    for p in s.execute(select(Payment).order_by(Payment.scheduled_for)).scalars():
        inv = s.get(Invoice, p.invoice_id)
        out.append({**ser(p, ["id", "gross", "deductions", "discount", "amount", "currency", "pay_to_account", "scheduled_for", "due_date",
                              "discount_deadline", "discount_pct", "status", "invoice_id", "run_id"]),
                    "vendor": inv.vendor.name if inv.vendor else None, "number": inv.number})
    return out


def _lab_ids():
    return select(Invoice.id).where(Invoice.source == "lab")


@app.get("/api/audit")
def audit_log(invoice_id: str | None = None, limit: int = Query(200, le=1000), scope: str = "all", s: Session = Depends(get_session)):
    q = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if invoice_id:
        q = q.where(AuditEvent.invoice_id == invoice_id)
    if scope == "main":
        q = q.where((AuditEvent.invoice_id.is_(None)) | AuditEvent.invoice_id.not_in(_lab_ids()))
    out = []
    rows = list(s.execute(q).scalars())
    labels = _invoice_labels(s, {e.invoice_id for e in rows if e.invoice_id})
    for e in rows:
        d = ser(e, ["id", "actor", "kind", "summary", "invoice_id", "created_at", "hash", "prev_hash"])
        d.update(labels.get(e.invoice_id, {}))
        out.append(d)
    return out


def _invoice_labels(s: Session, ids: set) -> dict:
    if not ids:
        return {}
    out = {}
    for inv in s.execute(select(Invoice).where(Invoice.id.in_(ids))).scalars():
        out[inv.id] = {"number": inv.number, "vendor": inv.vendor.name if inv.vendor else inv.vendor_name_raw, "lab": inv.source == "lab"}
    return out


@app.get("/api/audit/verify")
def audit_verify(s: Session = Depends(get_session)):
    ok, broken = audit.verify_chain(s)
    n = s.execute(select(func.count(AuditEvent.id))).scalar_one()
    head = s.execute(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1)).scalar_one_or_none()
    return {"ok": ok, "broken_at": broken, "events": n, "head": head}


@app.get("/api/events")
async def events(since: int | None = None):
    """Live feed of audit events. Polls the table so it sees the worker's writes."""

    async def gen():
        last = since
        if last is None:
            with SessionLocal() as s:
                last = s.execute(select(func.coalesce(func.max(AuditEvent.id), 0))).scalar_one()
        while True:
            with SessionLocal() as s:
                rows = list(s.execute(select(AuditEvent).where(AuditEvent.id > last).order_by(AuditEvent.id).limit(100)).scalars())
                labels = _invoice_labels(s, {e.invoice_id for e in rows if e.invoice_id})
                payloads = [{**ser(e, ["id", "actor", "kind", "summary", "invoice_id", "created_at"]), **labels.get(e.invoice_id, {})} for e in rows]
            for e, d in zip(rows, payloads):
                last = e.id
                yield {"event": "audit", "id": str(e.id), "data": json.dumps(d)}
            await asyncio.sleep(1.0)

    return EventSourceResponse(gen(), ping=15)


# --------------------------------------------------------------------------- writes


class Actor(BaseModel):
    user: str
    role: str


class ApprovalDecision(Actor):
    decision: str
    comment: str | None = None
    callback_note: str | None = None


class Resolve(Actor):
    justification: str


class Reject(Actor):
    reason: str


def _wrap(fn):
    try:
        with session_scope() as s:
            return fn(s)
    except api_actions.ActionError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/invoices")
async def upload(file: UploadFile = File(...), x_demo_user: str | None = Header(None)):
    _rate_limit()
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "File too large")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Only PDF invoices are accepted")
    with session_scope() as s:
        inv = pipeline.ingest(s, data, file.filename or "invoice.pdf", source="upload", actor=x_demo_user or "upload")
        return {"id": inv.id}


@app.post("/api/approvals/{approval_id}/decide")
def decide(approval_id: int, body: ApprovalDecision):
    return _wrap(lambda s: {"ok": bool(api_actions.decide_approval(
        s, approval_id, user=body.user, role=body.role, decision=body.decision, comment=body.comment, callback_note=body.callback_note))})


@app.post("/api/findings/{finding_id}/resolve")
def resolve(finding_id: int, body: Resolve):
    return _wrap(lambda s: api_actions.resolve_finding(s, finding_id, user=body.user, role=body.role, justification=body.justification) or {"ok": True})


@app.post("/api/invoices/{invoice_id}/receipt")
def receipt(invoice_id: str, body: Actor):
    return _wrap(lambda s: {"ok": bool(api_actions.record_receipt(s, invoice_id, user=body.user))})


@app.post("/api/invoices/{invoice_id}/reject")
def reject(invoice_id: str, body: Reject):
    return _wrap(lambda s: {"ok": bool(api_actions.reject_invoice(s, invoice_id, user=f"{body.user} ({body.role})", reason=body.reason))})


# --------------------------------------------------------------------------- contracts


def contract_row(s: Session, c: Contract) -> dict:
    metrics = [
        ser(m, ["period", "metric", "value", "source"])
        for m in s.execute(select(ServiceMetric).where(ServiceMetric.vendor_id == c.vendor_id).order_by(ServiceMetric.period)).scalars()
    ]
    return {
        **ser(c, ["id", "vendor_id", "title", "effective_date", "text", "created_at"]),
        "vendor": c.vendor.name,
        "terms": [ser(t, ["id", "kind", "params", "quote", "summary", "status", "source", "reviewed_by", "created_at"]) for t in c.terms],
        "metrics": metrics,
    }


@app.get("/api/contracts")
def list_contracts(s: Session = Depends(get_session)):
    rows = s.execute(select(Contract).join(Vendor, Vendor.id == Contract.vendor_id).order_by(Vendor.name)).scalars()
    return [contract_row(s, c) for c in rows]


class NewContract(Actor):
    vendor_id: str
    title: str
    text: str


def _add_extracted(s: Session, c: Contract, actor: str) -> dict:
    from .contracts import extract_terms

    if not settings.inference_api_key:
        raise HTTPException(503, "Contract reading needs Vultr Serverless Inference")
    found, rejected = extract_terms(c.text)
    existing = {(t.kind, json.dumps(t.params, sort_keys=True)) for t in c.terms if t.status != "rejected"}
    added = 0
    for t in found:
        key = (t["kind"], json.dumps(t["params"], sort_keys=True))
        if key in existing:
            continue
        c.terms.append(ContractTerm(kind=t["kind"], params=t["params"], quote=t["quote"], summary=t["summary"], status="proposed", source=settings.model_reasoning))
        added += 1
    s.flush()
    audit.record(s, actor="agent", kind="contract_read", summary=f"Read {c.vendor.name} {c.title}: {len(found)} term(s) found, {added} new for review"
                 + (f", {len(rejected)} discarded ({'; '.join(rejected)[:300]})" if rejected else ""), detail={"by": actor})
    from .llm import flush_spend

    flush_spend()
    return {"found": len(found), "added": added, "rejected": rejected}


@app.post("/api/contracts")
def add_contract(body: NewContract):
    _rate_limit()
    if len(body.text) < 200:
        raise HTTPException(400, "Paste the contract text (at least a few paragraphs)")
    with session_scope() as s:
        v = s.get(Vendor, body.vendor_id)
        if v is None:
            raise HTTPException(404, "vendor not found")
        c = Contract(vendor_id=v.id, title=body.title[:200] or "Agreement", text=body.text[:60000])
        s.add(c)
        s.flush()
        audit.record(s, actor=f"{body.user} ({body.role})", kind="contract_added", summary=f"{body.user} added {v.name}: {c.title}")
        result = _add_extracted(s, c, body.user)
        return {"id": c.id, **result}


@app.post("/api/contracts/{contract_id}/extract")
def reextract(contract_id: int, body: Actor):
    _rate_limit()
    with session_scope() as s:
        c = s.get(Contract, contract_id)
        if c is None:
            raise HTTPException(404)
        return _add_extracted(s, c, body.user)


class TermDecision(Actor):
    decision: str


@app.post("/api/terms/{term_id}/decide")
def decide_term(term_id: int, body: TermDecision):
    if body.role not in ("controller", "cfo"):
        raise HTTPException(400, "Contract terms are approved by the controller or CFO")
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be approved or rejected")
    with session_scope() as s:
        t = s.get(ContractTerm, term_id)
        if t is None:
            raise HTTPException(404)
        t.status, t.reviewed_by = body.decision, f"{body.user} ({body.role})"
        c = t.contract
        audit.record(s, actor=f"{body.user} ({body.role})", kind=f"term_{body.decision}",
                     summary=f"{body.user} {body.decision} a {c.vendor.name} contract term: {t.summary}")
        if body.decision == "approved":
            for inv in s.execute(select(Invoice).where(Invoice.vendor_id == c.vendor_id, Invoice.status.in_(
                    [InvoiceStatus.on_hold, InvoiceStatus.awaiting_approval, InvoiceStatus.awaiting_vendor]))).scalars():
                pipeline.enqueue(s, "recheck", inv.id, {"reason": "contract term approved"})
        return {"ok": True}


# --------------------------------------------------------------------------- payment runs


@app.get("/api/payment-runs")
def payment_runs(s: Session = Depends(get_session)):
    from .paymentrun import cash_position

    runs = [ser(r, ["id", "run_date", "status", "cash_before", "cash_floor", "total", "discounts", "plan", "proposed_by", "approved_by", "created_at", "approved_at"])
            for r in s.execute(select(PaymentRun).order_by(PaymentRun.id.desc()).limit(20)).scalars()]
    return {"cash": float(cash_position(s)), "floor": settings.cash_floor_usd, "horizon_days": settings.run_horizon_days, "runs": runs}


@app.post("/api/payment-runs/plan")
def plan_run(body: Actor):
    from .paymentrun import propose

    with session_scope() as s:
        run = propose(s, actor=f"{body.user} ({body.role})")
        return {"id": run.id if run else None}


@app.post("/api/payment-runs/{run_id}/approve")
def approve_run(run_id: int, body: Actor):
    from .paymentrun import approve

    return _wrap(lambda s: {"ok": bool(approve(s, run_id, body.user, body.role))})


@app.get("/api/payment-runs/{run_id}/bank-file")
def run_file(run_id: int, s: Session = Depends(get_session)):
    from .paymentrun import bank_file

    r = s.get(PaymentRun, run_id)
    if r is None or r.status != "approved":
        raise HTTPException(404)
    return Response(bank_file(s, run_id), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="tollgate-run-{run_id}.csv"'})


# --------------------------------------------------------------------------- attack lab


@app.get("/api/lab/templates")
def lab_templates():
    from .lab import DEFAULT_BANK_NOTE, DEFAULT_HIDDEN, DEFAULT_VISIBLE, TEMPLATES

    defaults = {"hidden_instruction": DEFAULT_HIDDEN, "visible_instruction": DEFAULT_VISIBLE, "bank_change": DEFAULT_BANK_NOTE}
    return [{**t.__dict__, "default_text": defaults.get(t.key)} for t in TEMPLATES]


class LabAttack(BaseModel):
    template: str
    text: str | None = None


@app.post("/api/lab/attack")
def lab_attack(body: LabAttack):
    from .lab import BY_KEY, build

    if body.template not in BY_KEY:
        raise HTTPException(400, "unknown template")
    _rate_limit()
    with session_scope() as s:
        seq = s.execute(select(func.count(Invoice.id)).where(Invoice.source == "lab")).scalar_one() + 1
        ids = []
        group = f"{body.template}-{seq}"
        for name, pdf, _desc in build(body.template, body.text, seq):
            inv = pipeline.ingest(s, pdf, name, source="lab", source_ref=group, actor="attack lab")
            ids.append(inv.id)
        return {"ids": ids, "group": group}


@app.post("/api/lab/upload")
async def lab_upload(file: UploadFile = File(...)):
    _rate_limit()
    data = await file.read()
    if len(data) > 15 * 1024 * 1024 or not data.startswith(b"%PDF"):
        raise HTTPException(400, "Upload a PDF under 15 MB")
    with session_scope() as s:
        seq = s.execute(select(func.count(Invoice.id)).where(Invoice.source == "lab")).scalar_one() + 1
        inv = pipeline.ingest(s, data, file.filename or "upload.pdf", source="lab", source_ref=f"upload-{seq}", actor="attack lab")
        return {"ids": [inv.id], "group": f"upload-{seq}"}


@app.get("/api/lab/attempts")
def lab_attempts(s: Session = Depends(get_session)):
    from .lab import BY_KEY, outcome

    groups: dict[str, dict] = {}
    for inv in s.execute(select(Invoice).where(Invoice.source == "lab").order_by(Invoice.created_at.desc())).scalars():
        g = inv.source_ref or inv.id
        key = g.rsplit("-", 1)[0]
        row = invoice_row(inv)
        row["outcome"] = outcome(inv.status.value, row["blocking"])
        row["checks"] = [f.code for f in inv.findings if f.severity.value == "block"]
        grp = groups.setdefault(g, {"group": g, "template": key, "name": BY_KEY[key].name if key in BY_KEY else "Your upload",
                                    "technique": BY_KEY[key].technique if key in BY_KEY else "Custom", "invoices": [], "created_at": row["created_at"]})
        grp["invoices"].append(row)
    out = []
    for g in groups.values():
        outs = [i["outcome"] for i in g["invoices"]]
        g["outcome"] = "pending" if "pending" in outs else ("caught" if "caught" in outs else "missed")
        out.append(g)
    return out


@app.get("/api/lab/evals")
def lab_evals():
    import pathlib

    p = pathlib.Path(__file__).resolve().parent / "eval_results.json"
    if not p.exists():
        return {"available": False}
    return {"available": True, **json.loads(p.read_text())}


# --------------------------------------------------------------------------- demo


@app.get("/api/demo/inbox")
def demo_list():
    from .seed import demo_inbox

    return [{"index": i, "file_name": d.file_name, "title": d.title, "expectation": d.expectation} for i, d in enumerate(demo_inbox())]


@app.post("/api/demo/inbox")
def demo_load(indexes: list[int] | None = None):
    from .seed import demo_inbox

    _rate_limit()
    items = demo_inbox()
    chosen = [items[i] for i in (indexes or range(len(items))) if 0 <= i < len(items)]
    ids = []
    with session_scope() as s:
        for k, d in enumerate(chosen):
            inv = pipeline.ingest(s, d.pdf(), d.file_name, source="email", source_ref=f"{d.spec.vendor_email}: Invoice {d.spec.number}")
            ids.append(inv.id)
    return {"ids": ids}


@app.get("/api/demo/inbox/{index}/file")
def demo_file(index: int):
    from .seed import demo_inbox

    items = demo_inbox()
    if not 0 <= index < len(items):
        raise HTTPException(404)
    return Response(items[index].pdf(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{items[index].file_name}"'})


@app.post("/api/demo/reset")
def demo_reset():
    if not settings.demo_mode:
        raise HTTPException(403)
    from .seed import reset_and_seed

    with session_scope() as s:
        reset_and_seed(s)
    return {"ok": True}


@app.post("/api/demo/vendor-reply/{invoice_id}")
def demo_vendor_reply(invoice_id: str):
    """Play the vendor: reply to the agent's email with a corrected invoice.
    With Gmail connected, a real reply to the agent's email does the same."""
    from email.message import EmailMessage as Mime
    from email.utils import make_msgid

    from . import mailer
    from .seed import corrected_bis_2077

    with session_scope() as s:
        inv = s.get(Invoice, invoice_id)
        if inv is None:
            raise HTTPException(404)
        out = s.execute(select(EmailMessage).where(EmailMessage.invoice_id == inv.id, EmailMessage.direction == "out").order_by(EmailMessage.id.desc())).scalars().first()
        if out is None:
            raise HTTPException(400, "The agent has not emailed this vendor")
        m = Mime()
        m["From"] = out.recipient
        m["To"] = out.sender
        m["Subject"] = "Re: " + out.subject
        m["Message-ID"] = make_msgid(domain="vendor.example.com")
        if inv.number == "BIS-2077":
            m.set_content("Hi,\n\nApologies, our system applied the new price list early. Corrected invoice attached at the PO price.\n\nBest,\nBrightline AR")
            m.add_attachment(corrected_bis_2077(), maintype="application", subtype="pdf", filename="BIS-2077-C.pdf")
        else:
            m.set_content("Hi,\n\nThanks for flagging. We have reviewed it and will follow up shortly.\n\nBest regards")
        result = mailer.handle_inbound(s, m.as_bytes())
        return {"ok": True, "result": result}
