"""Render realistic vendor invoice PDFs for the demo dataset."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


@dataclass
class InvLine:
    sku: str
    description: str
    quantity: Decimal
    unit_price: Decimal

    @property
    def amount(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))


@dataclass
class InvoiceSpec:
    vendor_name: str
    vendor_address: str
    vendor_tax_id: str | None
    vendor_email: str
    number: str
    invoice_date: date
    due_date: date
    po_number: str | None
    bill_to: str
    lines: list[InvLine]
    tax_rate: Decimal = Decimal("0.08")
    currency: str = "USD"
    bank_name: str = ""
    account: str = ""
    routing: str = ""
    accent: tuple[float, float, float] = (0.12, 0.33, 0.55)
    note: str | None = None
    hidden_text: str | None = None
    override_total: Decimal | None = None
    extra: dict = field(default_factory=dict)

    @property
    def subtotal(self) -> Decimal:
        return sum((ln.amount for ln in self.lines), Decimal(0))

    @property
    def tax(self) -> Decimal:
        return (self.subtotal * self.tax_rate).quantize(Decimal("0.01"))

    @property
    def total(self) -> Decimal:
        return self.override_total if self.override_total is not None else self.subtotal + self.tax


def _fmt(x: Decimal) -> str:
    return f"{x:,.2f}"


def render(spec: InvoiceSpec) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.setTitle(f"Invoice {spec.number}")
    c.setAuthor(spec.vendor_name)
    w, h = LETTER
    accent = colors.Color(*spec.accent)

    c.setFillColor(accent)
    c.rect(0, h - 90, w, 90, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(40, h - 50, spec.vendor_name)
    c.setFont("Helvetica", 9)
    for i, ln in enumerate(spec.vendor_address.split("\n")):
        c.drawString(40, h - 66 - i * 11, ln)
    c.setFont("Helvetica-Bold", 26)
    c.drawRightString(w - 40, h - 55, "INVOICE")

    c.setFillColor(colors.black)
    y = h - 125
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "BILL TO")
    c.setFont("Helvetica", 9)
    for i, ln in enumerate(spec.bill_to.split("\n")):
        c.drawString(40, y - 13 - i * 11, ln)

    meta = [
        ("Invoice No.", spec.number),
        ("Invoice Date", spec.invoice_date.strftime("%B %d, %Y")),
        ("Due Date", spec.due_date.strftime("%B %d, %Y")),
        ("PO Number", spec.po_number or "-"),
        ("Tax ID", spec.vendor_tax_id or "-"),
        ("Currency", spec.currency),
    ]
    for i, (k, v) in enumerate(meta):
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(w - 150, y - i * 13, k)
        c.setFont("Helvetica", 9)
        c.drawString(w - 140, y - i * 13, v)

    y = h - 225
    c.setFillColor(colors.Color(0.94, 0.95, 0.97))
    c.rect(40, y - 6, w - 80, 20, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    cols = [45, 120, 380, 450, w - 45]
    c.drawString(cols[0], y, "Item")
    c.drawString(cols[1], y, "Description")
    c.drawRightString(cols[2] + 30, y, "Qty")
    c.drawRightString(cols[3] + 40, y, "Unit Price")
    c.drawRightString(cols[4], y, "Amount")
    c.setFont("Helvetica", 9)
    for ln in spec.lines:
        y -= 20
        c.drawString(cols[0], y, ln.sku)
        c.drawString(cols[1], y, ln.description[:48])
        c.drawRightString(cols[2] + 30, y, f"{ln.quantity.normalize():f}")
        c.drawRightString(cols[3] + 40, y, _fmt(ln.unit_price))
        c.drawRightString(cols[4], y, _fmt(ln.amount))
        c.setStrokeColor(colors.Color(0.88, 0.88, 0.9))
        c.line(40, y - 6, w - 40, y - 6)

    y -= 30
    rows = [("Subtotal", spec.subtotal), (f"Sales tax ({(spec.tax_rate * 100).normalize():f}%)", spec.tax)]
    for k, v in rows:
        c.setFont("Helvetica", 9)
        c.drawRightString(cols[3] + 40, y, k)
        c.drawRightString(cols[4], y, _fmt(v))
        y -= 15
    c.setFillColor(accent)
    c.rect(cols[3] - 60, y - 8, w - 40 - (cols[3] - 60), 22, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(cols[3] + 40, y, f"Total Due ({spec.currency})")
    c.drawRightString(cols[4], y, _fmt(spec.total))
    c.setFillColor(colors.black)

    y -= 50
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "REMIT PAYMENT TO")
    c.setFont("Helvetica", 9)
    remit = [f"Bank: {spec.bank_name}", f"Account No.: {spec.account}", f"Routing (ABA): {spec.routing}", f"Questions: {spec.vendor_email}"]
    for i, ln in enumerate(remit):
        c.drawString(40, y - 13 - i * 12, ln)

    if spec.note:
        ny = y - 80
        c.setFillColor(colors.Color(1, 0.97, 0.88))
        c.rect(40, ny - 30, w - 80, 40, stroke=0, fill=1)
        c.setFillColor(colors.Color(0.45, 0.3, 0))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(50, ny - 2, "PLEASE NOTE")
        c.setFont("Helvetica", 9)
        c.drawString(50, ny - 16, spec.note[:110])
        c.setFillColor(colors.black)

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.grey)
    c.drawCentredString(w / 2, 40, f"Thank you for your business. Payment terms per agreement. {spec.vendor_name}")

    if spec.hidden_text:
        # White, tiny text: invisible on screen and in print, present in the text layer.
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 1.5)
        hy = 70
        words = spec.hidden_text.split()
        for i in range(0, len(words), 30):
            c.drawString(40, hy, " ".join(words[i : i + 30]))
            hy -= 2

    c.showPage()
    c.save()
    return buf.getvalue()
