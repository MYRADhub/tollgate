"""Invoice lifecycle: ingest -> read -> check. Decisions live in agent.py."""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, checks, contracts
from .config import get_settings
from .extraction import extract, extract_from_text
from .injection import screen
from .models import (
    Contract,
    Severity,
    ContractTerm,
    ServiceMetric,
    Finding,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    Job,
    PurchaseOrder,
    Vendor,
    utcnow,
)
from .pdfdoc import read_pdf
from .storage import get_store

log = logging.getLogger(__name__)

INACTIVE = (InvoiceStatus.rejected, InvoiceStatus.superseded, InvoiceStatus.failed)


def enqueue(s: Session, kind: str, invoice_id: str | None = None, payload: dict | None = None, delay_s: float = 0) -> Job:
    job = Job(kind=kind, invoice_id=invoice_id, payload=payload or {}, run_after=utcnow() + timedelta(seconds=delay_s))
    s.add(job)
    s.flush()
    return job


def ingest(
    s: Session,
    data: bytes,
    file_name: str,
    *,
    source: str = "upload",
    source_ref: str | None = None,
    supersedes_id: str | None = None,
    actor: str = "system",
) -> Invoice:
    sha = hashlib.sha256(data).hexdigest()
    key = f"invoices/{sha[:2]}/{sha}.pdf"
    get_store().put(key, data)
    inv = Invoice(
        source=source, source_ref=source_ref, file_key=key, file_name=file_name[:300], file_sha256=sha, supersedes_id=supersedes_id
    )
    s.add(inv)
    s.flush()
    audit.record(
        s,
        actor=actor,
        kind="received",
        invoice_id=inv.id,
        summary=f"Received {file_name} via {source}" + (f" (replaces {supersedes_id})" if supersedes_id else ""),
        detail={"sha256": sha, "bytes": len(data), "source_ref": source_ref},
    )
    enqueue(s, "process", inv.id)
    return inv


def _set_status(s: Session, inv: Invoice, status: InvoiceStatus) -> None:
    inv.status = status
    s.flush()


def read_document(s: Session, inv: Invoice) -> None:
    _set_status(s, inv, InvoiceStatus.extracting)
    data = get_store().get(inv.file_key)
    pdf = read_pdf(data)
    try:
        ex = extract(pdf)
    except Exception as e:
        log.exception("vision extraction failed; using text layer")
        audit.record(s, actor="agent", kind="extraction_fallback", invoice_id=inv.id, summary=f"Vision model unavailable ({type(e).__name__}); read the text layer instead")
        ex = extract_from_text(pdf)
    signals = screen(pdf.text, pdf.hidden_spans, ex.instructions_noticed)

    inv.vendor_name_raw = ex.vendor_name
    inv.number = ex.number
    inv.po_number = (ex.po_number or "").strip().upper() or None
    inv.invoice_date = ex.invoice_date
    inv.due_date = ex.due_date
    inv.currency = ex.currency
    inv.subtotal = ex.subtotal
    inv.tax = ex.tax
    inv.total = ex.total
    inv.remit_bank_name = ex.bank_name
    inv.remit_account = ex.account
    inv.remit_routing = ex.routing
    inv.raw_text = pdf.text[:20000]
    inv.lines = [
        InvoiceLine(
            position=i + 1,
            sku=ln["sku"],
            description=ln["description"],
            quantity=ln["quantity"],
            unit_price=ln["unit_price"],
            amount=ln["amount"],
        )
        for i, ln in enumerate(ex.lines)
    ]
    inv.extraction = {
        "method": ex.method,
        "vendor_tax_id": ex.vendor_tax_id,
        "vendor_email_on_document": ex.vendor_email,
        "notes": ex.notes,
        "ungrounded": ex.ungrounded,
        "injection_signals": signals,
        "hidden_spans": pdf.hidden_spans,
        "evidence": (ex.raw or {}).get("evidence", {}),
        "pages": pdf.page_count,
    }
    s.flush()
    audit.record(
        s,
        actor="agent",
        kind="extracted",
        invoice_id=inv.id,
        summary=f"Read invoice {ex.number or '?'} from {ex.vendor_name or 'unknown vendor'}: "
        f"{len(ex.lines)} line(s), total {ex.currency or ''} {ex.total if ex.total is not None else '?'} ({ex.method})",
        detail={"ungrounded": ex.ungrounded, "injection_signals": len(signals)},
    )
    if signals:
        audit.record(
            s,
            actor="agent",
            kind="injection_detected",
            invoice_id=inv.id,
            summary=f"Found {len(signals)} instruction(s) aimed at an AI inside the document; ignored and quarantined",
            detail={"signals": signals},
        )


def build_context(s: Session, inv: Invoice) -> checks.CheckContext:
    vendors = [
        checks.VendorData(v.id, v.name, v.tax_id, v.bank_account, v.bank_routing, v.status, v.payment_terms_days)
        for v in s.execute(select(Vendor)).scalars()
    ]
    pos: dict[str, checks.POData] = {}
    for po in s.execute(select(PurchaseOrder)).scalars():
        received: dict[str, Decimal] = defaultdict(Decimal)
        for r in po.receipts:
            for rl in r.lines:
                received[rl.sku] += rl.quantity
        pos[po.number.upper()] = checks.POData(
            po.number,
            po.vendor_id,
            po.currency,
            po.status,
            [checks.POLineData(pl.sku, pl.description, pl.quantity, pl.unit_price) for pl in po.lines],
            dict(received),
        )
    prior = []
    q = select(Invoice).where(Invoice.id != inv.id, Invoice.status.not_in(INACTIVE + (InvoiceStatus.received, InvoiceStatus.extracting)))
    for p in s.execute(q).scalars():
        if p.id == inv.supersedes_id:
            continue
        if p.source == "lab" and inv.source != "lab":
            continue  # attack-lab experiments never affect real invoices
        billed: dict[str, Decimal] = defaultdict(Decimal)
        for ln in p.lines:
            if ln.sku:
                billed[ln.sku.upper()] += ln.quantity
        prior.append(checks.PriorInvoice(p.id, p.number, p.vendor_id, p.total, p.invoice_date, p.file_sha256, p.po_number, dict(billed)))
    return checks.CheckContext(vendors=vendors, pos=pos, prior=prior, price_tolerance_pct=get_settings().price_tolerance_pct,
                               auto_pay_limit=get_settings().auto_pay_limit)


def to_check_input(inv: Invoice) -> checks.InvoiceData:
    ex = inv.extraction or {}
    return checks.InvoiceData(
        id=inv.id,
        number=inv.number,
        vendor_name=inv.vendor_name_raw,
        vendor_tax_id=ex.get("vendor_tax_id"),
        po_number=inv.po_number,
        invoice_date=inv.invoice_date,
        due_date=inv.due_date,
        currency=inv.currency,
        subtotal=inv.subtotal,
        tax=inv.tax,
        total=inv.total,
        remit_account=inv.remit_account,
        remit_routing=inv.remit_routing,
        file_sha256=inv.file_sha256,
        lines=[checks.LineData(ln.description, ln.quantity, ln.unit_price, ln.amount, (ln.sku or None)) for ln in inv.lines],
        injection_signals=ex.get("injection_signals") or [],
        ungrounded_fields=ex.get("ungrounded") or [],
    )


def vendor_terms(s: Session, vendor_id: str | None) -> list[contracts.TermData]:
    if not vendor_id:
        return []
    rows = s.execute(
        select(ContractTerm, Contract.title).join(Contract, Contract.id == ContractTerm.contract_id)
        .where(Contract.vendor_id == vendor_id, ContractTerm.status == "approved").order_by(ContractTerm.id)
    ).all()
    return [contracts.TermData(t.id, t.kind, t.params, t.quote, title) for t, title in rows]


def contract_recoveries(s: Session, inv: Invoice, findings: list[checks.FindingData]) -> list[checks.FindingData]:
    terms = vendor_terms(s, inv.vendor_id)
    if not terms or not inv.lines:
        return []
    metrics = {
        (m.period, m.metric): m.value
        for m in s.execute(select(ServiceMetric).where(ServiceMetric.vendor_id == inv.vendor_id)).scalars()
    }
    tax_rate = (inv.tax / inv.subtotal).quantize(Decimal("0.0001")) if inv.tax and inv.subtotal else Decimal(0)
    lines = [contracts.LineIn(ln.position, ln.sku, ln.description, ln.quantity, ln.unit_price, ln.amount) for ln in inv.lines]
    # A line already blocked for exceeding its PO price is going back to the vendor; don't also claim it.
    disputed = {f.evidence.get("line") for f in findings if f.code == "PRICE_VARIANCE"}
    out = []
    for r in contracts.apply_terms(lines, inv.invoice_date, terms, metrics, tax_rate):
        if r.evidence.get("line") in disputed:
            continue
        out.append(checks.FindingData(r.code, r.severity, r.title, r.detail, r.evidence, r.amount))
    return out


def statement_findings(s: Session, inv: Invoice, findings: list[checks.FindingData]) -> list[checks.FindingData]:
    """From the vendor's latest reconciled statement: an invoice they do not list
    (blocking), and credit memos a controller approved claiming (recoveries)."""
    from . import statements
    from .models import Statement

    if not inv.vendor_id or inv.source == "lab":
        return []
    out = []
    trusted = [x for x in s.execute(select(Statement).where(Statement.vendor_id == inv.vendor_id, Statement.status == "reconciled").order_by(Statement.id.desc())).scalars()
               if not (x.result or {}).get("report_only")]
    st = trusted[0] if trusted else None
    if st is not None and any(x["kind"] == "not_on_statement" and x.get("invoice_id") == inv.id for x in (st.result or {}).get("items", [])):
        out.append(checks.FindingData("NOT_ON_VENDOR_STATEMENT", Severity.block, "The vendor's own statement does not list this invoice",
                                      f"{inv.vendor.name if inv.vendor else 'The vendor'}'s statement dated {st.statement_date} lists their open invoices and this is not one of them. "
                                      "A real invoice appears on the vendor's statement; ask them to confirm they issued it.",
                                      {"statement_id": st.id}, inv.total))
    taken = sum((f.amount_at_risk or Decimal(0) for f in findings if f.severity == Severity.recover), Decimal(0))
    out.extend(statements.credit_recoveries(s, inv, taken))
    return out


def run_controls(s: Session, inv: Invoice) -> checks.CheckResult:
    _set_status(s, inv, InvoiceStatus.checking)
    result = checks.run_checks(to_check_input(inv), build_context(s, inv))
    inv.vendor_id = result.vendor.id if result.vendor else None
    result.findings.extend(contract_recoveries(s, inv, result.findings))
    result.findings.extend(statement_findings(s, inv, result.findings))

    # Keep human resolutions of findings that recur; drop findings no longer true.
    previous = {(f.code, f.title): f for f in inv.findings}
    kept: list[Finding] = []
    for fd in result.findings:
        old = previous.get((fd.code, fd.title))
        f = Finding(
            invoice_id=inv.id,
            code=fd.code,
            severity=fd.severity,
            title=fd.title,
            detail=fd.detail,
            evidence=_jsonable(fd.evidence),
            amount_at_risk=fd.amount_at_risk,
        )
        if old is not None and old.resolved:
            f.resolved, f.resolution, f.resolved_by = True, old.resolution, old.resolved_by
        kept.append(f)
    cleared = [f for k, f in previous.items() if k not in {(x.code, x.title) for x in result.findings} and not f.resolved]
    inv.findings = kept
    inv.agent_state = {**(inv.agent_state or {}), "line_matches": _jsonable(result.line_matches)}
    s.flush()
    blocking = [f for f in kept if f.severity.value == "block" and not f.resolved]
    recover = [f for f in kept if f.severity.value == "recover"]
    other = len(kept) - len(blocking) - len(recover)
    audit.record(
        s,
        actor="controls",
        kind="checked",
        invoice_id=inv.id,
        summary=(
            f"Ran {len(checks_run())} controls and {len(vendor_terms(s, inv.vendor_id))} contract terms: {len(blocking)} blocking"
            + (f", {len(recover)} recovery worth {sum((f.amount_at_risk or 0) for f in recover):,.2f}" if recover else "")
            + (f", {other} other" if other else "")
            + (f"; {len(cleared)} earlier finding(s) now clear" if cleared else "")
        ),
        detail={"findings": [f"{f.severity.value}:{f.code}" for f in kept], "cleared": [f.code for f in cleared]},
    )
    return result


def checks_run() -> list[str]:
    return [
        "hidden instructions", "extraction grounding", "vendor master", "lookalike vendor", "tax ID", "vendor status", "bank account on file",
        "duplicate file", "duplicate number", "resubmission", "split billing", "line math", "subtotal", "total and tax",
        "PO exists", "PO vendor", "PO open", "currency", "item on PO", "price vs PO", "qty vs ordered",
        "qty vs received", "payment terms",
    ]


def _jsonable(x):
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_jsonable(v) for v in x]
    if isinstance(x, Decimal):
        return str(x)
    if hasattr(x, "isoformat"):
        return x.isoformat()
    return x


def process(s: Session, invoice_id: str) -> None:
    from . import agent

    inv = s.get(Invoice, invoice_id)
    if inv is None or inv.status in INACTIVE:
        return
    if inv.number is None and not inv.lines:
        read_document(s, inv)
    run_controls(s, inv)
    agent.decide(s, inv, trigger="new invoice" if inv.agent_state.get("decisions", 0) == 0 else "re-check")


def recheck(s: Session, invoice_id: str, reason: str) -> None:
    from . import agent

    inv = s.get(Invoice, invoice_id)
    if inv is None or inv.status in INACTIVE + (InvoiceStatus.scheduled, InvoiceStatus.paid):
        return
    run_controls(s, inv)
    agent.decide(s, inv, trigger=reason)
