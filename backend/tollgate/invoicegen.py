"""Render realistic vendor invoice PDFs for the demo dataset."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
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
    style: str | None = None  # key into STYLES: the billing system that produced the PDF

    @property
    def subtotal(self) -> Decimal:
        return sum((ln.amount for ln in self.lines), Decimal(0))

    @property
    def tax(self) -> Decimal:
        return (self.subtotal * self.tax_rate).quantize(Decimal("0.01"))

    @property
    def total(self) -> Decimal:
        return self.override_total if self.override_total is not None else self.subtotal + self.tax


@dataclass(frozen=True)
class HouseStyle:
    """How one vendor's billing system lays out its invoices. Every real vendor
    sends PDFs from the same system, so these are as consistent as a signature."""

    font: str = "Helvetica"
    bold: str = "Helvetica-Bold"
    pagesize: tuple = LETTER
    band: float = 90  # header band height; 0 draws a rule instead
    name_size: float = 20
    title_size: float = 26
    meta_x: float = 150  # right-edge offset of the meta labels
    bill_y: float = 125
    table_top: float = 225
    row_h: float = 20
    footer_y: float = 40
    footer: str = "Thank you for your business. Payment terms per agreement."
    mark: str = "none"  # none | square | circle
    creator: str = "(unspecified)"
    producer: str = "ReportLab PDF Library - www.reportlab.com"


STYLES: dict[str, HouseStyle] = {
    "brightline": HouseStyle(font="Times-Roman", bold="Times-Bold", band=110, name_size=22, title_size=28, meta_x=160, bill_y=140,
                             table_top=245, row_h=18, footer_y=36, mark="square", footer="Brightline Industrial Supply. Net terms per master agreement.",
                             creator="Sage Intacct", producer="Sage Intacct Reporting Services"),
    "ostara": HouseStyle(pagesize=A4, band=0, name_size=18, title_size=22, meta_x=170, bill_y=120, table_top=250, row_h=22, footer_y=46,
                         footer="Ostara Components GmbH. Amtsgericht Stuttgart HRB 724411.", creator="SAP S/4HANA", producer="SAP NetWeaver PDF Converter"),
    "kestrel": HouseStyle(font="Courier", bold="Courier-Bold", band=70, name_size=17, title_size=24, meta_x=140, bill_y=110, table_top=215, row_h=19,
                          footer="Kestrel Freight & Logistics. All loads subject to our standard terms.", creator="McLeod LoadMaster",
                          producer="McLeod PDF Writer 3.1"),
    "granite": HouseStyle(band=100, name_size=20, title_size=24, meta_x=155, bill_y=135, table_top=235, row_h=20, mark="circle",
                          creator="QuickBooks Online", producer="QuickBooks PDF Engine 2.4"),
    "vantage": HouseStyle(band=80, name_size=19, title_size=26, meta_x=150, bill_y=118, table_top=220, row_h=21, footer_y=34,
                          footer="Vantage Cloud Services. Questions? billing support in your admin console.", creator="Stripe Invoicing",
                          producer="Stripe PDF Service"),
    "lumen": HouseStyle(font="Times-Roman", bold="Times-Bold", band=95, name_size=21, title_size=25, meta_x=150, bill_y=130, table_top=230, row_h=20,
                        footer="Lumen Office Supply. Thank you for shopping local.", creator="Xero", producer="Xero Invoicing PDF"),
    "polaris": HouseStyle(band=85, name_size=20, title_size=26, meta_x=158, bill_y=124, table_top=228, row_h=20, mark="square",
                          creator="NetSuite", producer="NetSuite Advanced PDF/HTML Templates"),
    # What a fraudster rebuilding a vendor's invoice in a word processor produces.
    "forger": HouseStyle(creator="Microsoft Word for Microsoft 365", producer="Microsoft: Print To PDF"),
}


def _fmt(x: Decimal) -> str:
    return f"{x:,.2f}"


def render(spec: InvoiceSpec) -> bytes:
    st = STYLES.get(spec.style or "", HouseStyle())
    F, B = st.font, st.bold
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=st.pagesize)
    c.setTitle(f"Invoice {spec.number}")
    c.setAuthor(spec.vendor_name)
    c.setCreator(st.creator)
    c.setProducer(st.producer)
    w, h = st.pagesize
    accent = colors.Color(*spec.accent)

    head = st.band or 80
    name_x = 40 + (34 if st.mark != "none" else 0)
    if st.band:
        c.setFillColor(accent)
        c.rect(0, h - st.band, w, st.band, stroke=0, fill=1)
        ink = colors.white
    else:
        c.setStrokeColor(accent)
        c.setLineWidth(2)
        c.line(40, h - head, w - 40, h - head)
        ink = accent
    if st.mark == "square":
        c.setFillColor(ink)
        c.rect(40, h - head / 2 - 14, 24, 24, stroke=0, fill=1)
    elif st.mark == "circle":
        c.setFillColor(ink)
        c.circle(52, h - head / 2 - 2, 12, stroke=0, fill=1)
    c.setFillColor(ink)
    c.setFont(B, st.name_size)
    c.drawString(name_x, h - head / 2 - 5, spec.vendor_name)
    c.setFont(F, 9)
    for i, ln in enumerate(spec.vendor_address.split("\n")):
        c.drawString(name_x, h - head / 2 - 21 - i * 11, ln)
    c.setFont(B, st.title_size)
    c.drawRightString(w - 40, h - head / 2 - 10, "INVOICE")

    c.setFillColor(colors.black)
    y = h - st.bill_y
    c.setFont(B, 9)
    c.drawString(40, y, "BILL TO")
    c.setFont(F, 9)
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
        c.setFont(B, 9)
        c.drawRightString(w - st.meta_x, y - i * 13, k)
        c.setFont(F, 9)
        c.drawString(w - st.meta_x + 10, y - i * 13, v)

    y = h - st.table_top
    c.setFillColor(colors.Color(0.94, 0.95, 0.97))
    c.rect(40, y - 6, w - 80, 20, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont(B, 9)
    cols = [45, 120, w - 232, w - 162, w - 45]
    c.drawString(cols[0], y, "Item")
    c.drawString(cols[1], y, "Description")
    c.drawRightString(cols[2] + 30, y, "Qty")
    c.drawRightString(cols[3] + 40, y, "Unit Price")
    c.drawRightString(cols[4], y, "Amount")
    c.setFont(F, 9)
    for ln in spec.lines:
        y -= st.row_h
        c.drawString(cols[0], y, ln.sku)
        c.drawString(cols[1], y, ln.description[:48])
        c.drawRightString(cols[2] + 30, y, f"{ln.quantity.normalize():f}")
        c.drawRightString(cols[3] + 40, y, _fmt(ln.unit_price))
        c.drawRightString(cols[4], y, _fmt(ln.amount))
        c.setStrokeColor(colors.Color(0.88, 0.88, 0.9))
        c.setLineWidth(1)
        c.line(40, y - 6, w - 40, y - 6)

    y -= 30
    rows = [("Subtotal", spec.subtotal), (f"Sales tax ({(spec.tax_rate * 100).normalize():f}%)", spec.tax)]
    for k, v in rows:
        c.setFont(F, 9)
        c.drawRightString(cols[3] + 40, y, k)
        c.drawRightString(cols[4], y, _fmt(v))
        y -= 15
    c.setFillColor(accent)
    c.rect(cols[3] - 60, y - 8, w - 40 - (cols[3] - 60), 22, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont(B, 11)
    c.drawRightString(cols[3] + 40, y, f"Total Due ({spec.currency})")
    c.drawRightString(cols[4], y, _fmt(spec.total))
    c.setFillColor(colors.black)

    y -= 50
    c.setFont(B, 9)
    c.drawString(40, y, "REMIT PAYMENT TO")
    c.setFont(F, 9)
    remit = [f"Bank: {spec.bank_name}", f"Account No.: {spec.account}", f"Routing (ABA): {spec.routing}", f"Questions: {spec.vendor_email}"]
    for i, ln in enumerate(remit):
        c.drawString(40, y - 13 - i * 12, ln)

    if spec.note:
        ny = y - 80
        c.setFillColor(colors.Color(1, 0.97, 0.88))
        c.rect(40, ny - 30, w - 80, 40, stroke=0, fill=1)
        c.setFillColor(colors.Color(0.45, 0.3, 0))
        c.setFont(B, 9)
        c.drawString(50, ny - 2, "PLEASE NOTE")
        c.setFont(F, 9)
        c.drawString(50, ny - 16, spec.note[:110])
        c.setFillColor(colors.black)

    c.setFont(F, 8)
    c.setFillColor(colors.grey)
    footer = f"{st.footer} {spec.vendor_name}" if spec.style in (None, "forger") or spec.style not in STYLES else st.footer
    c.drawCentredString(w / 2, st.footer_y, footer)

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
