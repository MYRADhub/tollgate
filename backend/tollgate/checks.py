"""Deterministic invoice controls.

Nothing in this module calls a model. The LLM reads documents and proposes
actions; these checks decide what is true about an invoice, so a persuasive
document (or a prompt injection) cannot talk its way past them.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from rapidfuzz import fuzz

from .models import Severity

CENT = Decimal("0.01")


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class LineData:
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    sku: str | None = None


@dataclass
class InvoiceData:
    id: str
    number: str | None
    vendor_name: str | None
    vendor_tax_id: str | None
    po_number: str | None
    invoice_date: date | None
    due_date: date | None
    currency: str | None
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal | None
    remit_account: str | None
    remit_routing: str | None
    file_sha256: str
    lines: list[LineData] = field(default_factory=list)
    injection_signals: list[dict] = field(default_factory=list)
    ungrounded_fields: list[str] = field(default_factory=list)


@dataclass
class VendorData:
    id: str
    name: str
    tax_id: str | None
    bank_account: str | None
    bank_routing: str | None
    status: str = "active"
    payment_terms_days: int = 30


@dataclass
class POLineData:
    sku: str
    description: str
    quantity: Decimal
    unit_price: Decimal


@dataclass
class POData:
    number: str
    vendor_id: str
    currency: str
    status: str
    lines: list[POLineData]
    received: dict[str, Decimal]  # sku -> quantity received to date


@dataclass
class PriorInvoice:
    id: str
    number: str | None
    vendor_id: str | None
    total: Decimal | None
    invoice_date: date | None
    file_sha256: str
    po_number: str | None
    billed: dict[str, Decimal] = field(default_factory=dict)  # sku -> qty billed


@dataclass
class FindingData:
    code: str
    severity: Severity
    title: str
    detail: str
    evidence: dict = field(default_factory=dict)
    amount_at_risk: Decimal | None = None


@dataclass
class CheckContext:
    vendors: list[VendorData]
    pos: dict[str, POData]
    prior: list[PriorInvoice]
    price_tolerance_pct: float = 2.0


@dataclass
class CheckResult:
    vendor: VendorData | None
    po: POData | None
    findings: list[FindingData]
    line_matches: list[dict]

    @property
    def blocking(self) -> list[FindingData]:
        return [f for f in self.findings if f.severity == Severity.block]


def normalize_number(n: str | None) -> str:
    if not n:
        return ""
    s = re.sub(r"[^A-Za-z0-9]", "", n).upper()
    s = re.sub(r"^(INVOICE|INV|NO|NR)", "", s)
    return s.lstrip("0")


def normalize_account(a: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", a or "").upper()


def normalize_tax_id(t: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", t or "").upper()


def match_vendor(inv: InvoiceData, vendors: list[VendorData]) -> tuple[VendorData | None, int]:
    tid = normalize_tax_id(inv.vendor_tax_id)
    if tid:
        for v in vendors:
            if normalize_tax_id(v.tax_id) == tid:
                return v, 100
    best, best_score = None, 0
    for v in vendors:
        score = int(fuzz.token_set_ratio((inv.vendor_name or "").lower(), v.name.lower()))
        if score > best_score:
            best, best_score = v, score
    return (best, best_score) if best_score >= 88 else (None, best_score)


def _match_line(line: LineData, po: POData) -> POLineData | None:
    if line.sku:
        for pl in po.lines:
            if pl.sku.upper() == line.sku.upper():
                return pl
    best, score = None, 0
    for pl in po.lines:
        s = fuzz.token_set_ratio(line.description.lower(), pl.description.lower())
        if s > score:
            best, score = pl, s
    return best if score >= 80 else None


def run_checks(inv: InvoiceData, ctx: CheckContext) -> CheckResult:
    findings: list[FindingData] = []
    total = inv.total or Decimal(0)

    # --- document integrity -------------------------------------------------
    for sig in inv.injection_signals:
        findings.append(
            FindingData(
                "PROMPT_INJECTION",
                Severity.block,
                "Document contains instructions aimed at an AI",
                "The invoice carries text that tries to instruct an automated reader "
                f"({sig.get('kind', 'instruction')}). It was ignored for extraction and the invoice is held.",
                {"excerpt": sig.get("excerpt", "")[:400], "source": sig.get("source")},
                total,
            )
        )
    if inv.ungrounded_fields:
        findings.append(
            FindingData(
                "LOW_CONFIDENCE",
                Severity.warn,
                "Some extracted fields could not be found in the document text",
                "These fields were read from the image but not confirmed against the text layer: "
                + ", ".join(inv.ungrounded_fields),
                {"fields": inv.ungrounded_fields},
            )
        )

    # --- vendor ---------------------------------------------------------------
    vendor, vscore = match_vendor(inv, ctx.vendors)
    if vendor is None:
        findings.append(
            FindingData(
                "UNKNOWN_VENDOR",
                Severity.block,
                "Vendor is not in the vendor master",
                f"'{inv.vendor_name}' does not match any approved vendor (best match score {vscore}).",
                {"vendor_name": inv.vendor_name, "tax_id": inv.vendor_tax_id},
                total,
            )
        )
    else:
        if vendor.status != "active":
            findings.append(
                FindingData(
                    "VENDOR_INACTIVE",
                    Severity.block,
                    f"Vendor is {vendor.status}",
                    f"{vendor.name} is marked {vendor.status} in the vendor master.",
                    {"vendor_id": vendor.id},
                    total,
                )
            )
        if inv.remit_account and normalize_account(inv.remit_account) != normalize_account(vendor.bank_account):
            findings.append(
                FindingData(
                    "BANK_MISMATCH",
                    Severity.block,
                    "Remit-to bank account differs from the verified account on file",
                    f"Invoice asks for payment to account ending {normalize_account(inv.remit_account)[-4:]}; "
                    f"the verified account for {vendor.name} ends {normalize_account(vendor.bank_account)[-4:]}. "
                    "This is the pattern of business email compromise fraud. Payment goes only to the verified "
                    "account until two people approve a change after a callback.",
                    {
                        "invoice_account": inv.remit_account,
                        "invoice_routing": inv.remit_routing,
                        "master_account": vendor.bank_account,
                        "master_routing": vendor.bank_routing,
                    },
                    total,
                )
            )

    # --- duplicates -----------------------------------------------------------
    num = normalize_number(inv.number)
    for p in ctx.prior:
        if p.id == inv.id:
            continue
        if p.file_sha256 == inv.file_sha256:
            findings.append(
                FindingData(
                    "DUPLICATE_FILE",
                    Severity.block,
                    "The exact same file was already received",
                    f"Byte-identical to invoice record {p.id}.",
                    {"prior_invoice_id": p.id},
                    total,
                )
            )
            continue
        same_vendor = vendor is not None and p.vendor_id == vendor.id
        if not same_vendor:
            continue
        pnum = normalize_number(p.number)
        if num and pnum and num == pnum:
            findings.append(
                FindingData(
                    "DUPLICATE_NUMBER",
                    Severity.block,
                    "Invoice number already billed by this vendor",
                    f"Invoice {inv.number} matches previously received {p.number} (record {p.id}).",
                    {"prior_invoice_id": p.id, "prior_number": p.number},
                    total,
                )
            )
            continue
        close_date = (
            inv.invoice_date is not None
            and p.invoice_date is not None
            and abs((inv.invoice_date - p.invoice_date).days) <= 45
        )
        similar_number = bool(num and pnum and fuzz.ratio(num, pnum) >= 80)
        if p.total is not None and inv.total is not None and money(p.total) == money(inv.total) and (close_date or similar_number):
            findings.append(
                FindingData(
                    "DUPLICATE_SUSPECT",
                    Severity.block,
                    "Looks like a resubmission of an earlier invoice",
                    f"Same vendor and same total ({money(inv.total)}) as {p.number} (record {p.id})"
                    + (", with a near-identical invoice number" if similar_number else ", dated within 45 days")
                    + ".",
                    {"prior_invoice_id": p.id, "prior_number": p.number},
                    total,
                )
            )

    # --- arithmetic -----------------------------------------------------------
    line_sum = Decimal(0)
    for i, ln in enumerate(inv.lines):
        line_sum += ln.amount
        expected = money(ln.quantity * ln.unit_price)
        if abs(expected - money(ln.amount)) > CENT:
            findings.append(
                FindingData(
                    "LINE_MATH",
                    Severity.block,
                    f"Line {i + 1} does not add up",
                    f"{ln.quantity} x {money(ln.unit_price)} = {expected}, but the line says {money(ln.amount)}.",
                    {"line": i + 1, "expected": expected, "stated": ln.amount},
                    max(money(ln.amount) - expected, Decimal(0)) or None,
                )
            )
    if inv.subtotal is not None and inv.lines and abs(money(line_sum) - money(inv.subtotal)) > CENT:
        findings.append(
            FindingData(
                "SUBTOTAL_MATH",
                Severity.block,
                "Lines do not sum to the subtotal",
                f"Lines sum to {money(line_sum)}; subtotal says {money(inv.subtotal)}.",
                {"line_sum": line_sum, "subtotal": inv.subtotal},
                max(money(inv.subtotal) - money(line_sum), Decimal(0)) or None,
            )
        )
    if inv.subtotal is not None and inv.total is not None:
        expected_total = money(inv.subtotal + (inv.tax or Decimal(0)))
        if abs(expected_total - money(inv.total)) > CENT:
            findings.append(
                FindingData(
                    "TOTAL_MATH",
                    Severity.block,
                    "Subtotal plus tax does not equal the total",
                    f"{money(inv.subtotal)} + {money(inv.tax or 0)} = {expected_total}; total says {money(inv.total)}.",
                    {"expected": expected_total, "stated": inv.total},
                    max(money(inv.total) - expected_total, Decimal(0)) or None,
                )
            )

    # --- PO and receipt matching (3-way) --------------------------------------
    po: POData | None = None
    line_matches: list[dict] = []
    if not inv.po_number:
        findings.append(
            FindingData(
                "NO_PO",
                Severity.block,
                "No purchase order referenced",
                "Company policy requires a PO for every vendor invoice. The budget owner must confirm the spend.",
                {},
                total,
            )
        )
    else:
        po = ctx.pos.get(inv.po_number.strip().upper())
        if po is None:
            findings.append(
                FindingData(
                    "PO_NOT_FOUND",
                    Severity.block,
                    f"PO {inv.po_number} does not exist",
                    "The referenced purchase order is not in the system.",
                    {"po_number": inv.po_number},
                    total,
                )
            )
        elif vendor is not None and po.vendor_id != vendor.id:
            findings.append(
                FindingData(
                    "PO_VENDOR_MISMATCH",
                    Severity.block,
                    "PO belongs to a different vendor",
                    f"PO {po.number} was issued to another vendor.",
                    {"po_number": po.number},
                    total,
                )
            )
            po = None
        elif po.status != "open":
            findings.append(
                FindingData(
                    "PO_CLOSED",
                    Severity.block,
                    f"PO {po.number} is {po.status}",
                    "Invoices cannot be paid against a closed purchase order.",
                    {"po_number": po.number},
                    total,
                )
            )

    if po is not None:
        if inv.currency and po.currency and inv.currency.upper() != po.currency.upper():
            findings.append(
                FindingData(
                    "CURRENCY_MISMATCH",
                    Severity.block,
                    "Invoice currency differs from the PO",
                    f"Invoice is in {inv.currency}, PO is in {po.currency}.",
                    {},
                    total,
                )
            )
        previously_billed: dict[str, Decimal] = defaultdict(Decimal)
        for p in ctx.prior:
            if p.id != inv.id and p.po_number and p.po_number.strip().upper() == po.number.upper():
                for sku, q in p.billed.items():
                    previously_billed[sku] += q
        tol = Decimal(str(ctx.price_tolerance_pct)) / 100
        for i, ln in enumerate(inv.lines):
            pl = _match_line(ln, po)
            if pl is None:
                line_matches.append({"line": i + 1, "po_sku": None})
                findings.append(
                    FindingData(
                        "UNORDERED_ITEM",
                        Severity.block,
                        f"Line {i + 1} is not on the PO",
                        f"'{ln.description}' was never ordered on {po.number}.",
                        {"line": i + 1},
                        money(ln.amount),
                    )
                )
                continue
            received = po.received.get(pl.sku, Decimal(0))
            billed_before = previously_billed.get(pl.sku, Decimal(0))
            line_matches.append(
                {
                    "line": i + 1,
                    "po_sku": pl.sku,
                    "po_qty": pl.quantity,
                    "po_price": pl.unit_price,
                    "received": received,
                    "billed_before": billed_before,
                }
            )
            if ln.unit_price > pl.unit_price * (1 + tol):
                over = money((ln.unit_price - pl.unit_price) * ln.quantity)
                findings.append(
                    FindingData(
                        "PRICE_VARIANCE",
                        Severity.block,
                        f"Line {i + 1} billed above the PO price",
                        f"{pl.sku}: billed {money(ln.unit_price)} per unit, PO price is {money(pl.unit_price)} "
                        f"({((ln.unit_price / pl.unit_price - 1) * 100).quantize(Decimal('0.1'))}% over, "
                        f"tolerance {ctx.price_tolerance_pct}%). Overcharge {over}.",
                        {"line": i + 1, "sku": pl.sku, "billed": ln.unit_price, "po_price": pl.unit_price},
                        over,
                    )
                )
            if billed_before + ln.quantity > pl.quantity:
                excess = billed_before + ln.quantity - pl.quantity
                findings.append(
                    FindingData(
                        "QTY_OVER_ORDERED",
                        Severity.block,
                        f"Line {i + 1} bills more than was ordered",
                        f"{pl.sku}: ordered {pl.quantity}, already billed {billed_before}, this invoice {ln.quantity}.",
                        {"line": i + 1, "sku": pl.sku, "excess": excess},
                        money(excess * ln.unit_price),
                    )
                )
            elif billed_before + ln.quantity > received:
                excess = billed_before + ln.quantity - received
                findings.append(
                    FindingData(
                        "QTY_NOT_RECEIVED",
                        Severity.block,
                        f"Line {i + 1} bills for goods not yet received",
                        f"{pl.sku}: received {received}, already billed {billed_before}, this invoice {ln.quantity}. "
                        f"{excess} unit(s) have no goods receipt.",
                        {"line": i + 1, "sku": pl.sku, "excess": excess, "received": received},
                        money(excess * ln.unit_price),
                    )
                )

    # --- terms ----------------------------------------------------------------
    if vendor and inv.invoice_date and inv.due_date:
        agreed = inv.invoice_date + timedelta(days=vendor.payment_terms_days)
        if inv.due_date < agreed:
            findings.append(
                FindingData(
                    "TERMS_SHORTENED",
                    Severity.info,
                    "Due date is earlier than agreed payment terms",
                    f"Terms are net {vendor.payment_terms_days} (due {agreed}); invoice asks for {inv.due_date}. "
                    "Payment will be scheduled on the agreed date.",
                    {"agreed_due": agreed, "stated_due": inv.due_date},
                )
            )

    return CheckResult(vendor=vendor, po=po, findings=findings, line_matches=line_matches)
