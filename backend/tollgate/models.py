from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Money = Numeric(14, 2)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class InvoiceStatus(str, enum.Enum):
    received = "received"
    extracting = "extracting"
    checking = "checking"
    deciding = "deciding"
    awaiting_vendor = "awaiting_vendor"
    awaiting_approval = "awaiting_approval"
    on_hold = "on_hold"
    scheduled = "scheduled"
    paid = "paid"
    rejected = "rejected"
    superseded = "superseded"
    failed = "failed"


class Severity(str, enum.Enum):
    info = "info"
    warn = "warn"
    block = "block"
    recover = "recover"  # money the vendor owes us under its contract; deducted, not blocking


class Role(str, enum.Enum):
    clerk = "clerk"
    controller = "controller"
    cfo = "cfo"


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), index=True)
    tax_id: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    bank_name: Mapped[str | None] = mapped_column(String(120))
    bank_account: Mapped[str | None] = mapped_column(String(64))
    bank_routing: Mapped[str | None] = mapped_column(String(32))
    bank_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"))
    department: Mapped[str] = mapped_column(String(80))
    budget_owner_name: Mapped[str] = mapped_column(String(120))
    budget_owner_email: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(20), default="open")
    issued_on: Mapped[date] = mapped_column(Date)
    vendor: Mapped[Vendor] = relationship()
    lines: Mapped[list[POLine]] = relationship(back_populates="po", cascade="all, delete-orphan")
    receipts: Mapped[list[GoodsReceipt]] = relationship(back_populates="po", cascade="all, delete-orphan")


class POLine(Base):
    __tablename__ = "po_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id"))
    sku: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(Money)
    po: Mapped[PurchaseOrder] = relationship(back_populates="lines")


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    po_id: Mapped[str] = mapped_column(ForeignKey("purchase_orders.id"))
    received_on: Mapped[date] = mapped_column(Date)
    received_by: Mapped[str] = mapped_column(String(120))
    po: Mapped[PurchaseOrder] = relationship(back_populates="receipts")
    lines: Mapped[list[ReceiptLine]] = relationship(cascade="all, delete-orphan")


class ReceiptLine(Base):
    __tablename__ = "receipt_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    receipt_id: Mapped[str] = mapped_column(ForeignKey("goods_receipts.id"))
    sku: Mapped[str] = mapped_column(String(60))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=new_id)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), default=InvoiceStatus.received, index=True)
    source: Mapped[str] = mapped_column(String(20), default="upload")
    source_ref: Mapped[str | None] = mapped_column(String(300))
    file_key: Mapped[str] = mapped_column(String(300))
    file_name: Mapped[str] = mapped_column(String(300))
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id"))

    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"))
    vendor_name_raw: Mapped[str | None] = mapped_column(String(200))
    number: Mapped[str | None] = mapped_column(String(80), index=True)
    po_number: Mapped[str | None] = mapped_column(String(80))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(String(3))
    subtotal: Mapped[Decimal | None] = mapped_column(Money)
    tax: Mapped[Decimal | None] = mapped_column(Money)
    total: Mapped[Decimal | None] = mapped_column(Money)
    remit_bank_name: Mapped[str | None] = mapped_column(String(120))
    remit_account: Mapped[str | None] = mapped_column(String(64))
    remit_routing: Mapped[str | None] = mapped_column(String(32))

    extraction: Mapped[dict | None] = mapped_column(JSON)
    raw_text: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    agent_state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    vendor: Mapped[Vendor | None] = relationship()
    lines: Mapped[list[InvoiceLine]] = relationship(cascade="all, delete-orphan", order_by="InvoiceLine.position")
    findings: Mapped[list[Finding]] = relationship(cascade="all, delete-orphan", order_by="Finding.id")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"))
    position: Mapped[int] = mapped_column(Integer)
    sku: Mapped[str | None] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit_price: Mapped[Decimal] = mapped_column(Money)
    amount: Mapped[Decimal] = mapped_column(Money)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    severity: Mapped[Severity] = mapped_column(Enum(Severity))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    amount_at_risk: Mapped[Decimal | None] = mapped_column(Money)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    bank_change_id: Mapped[int | None] = mapped_column(ForeignKey("bank_changes.id"))
    kind: Mapped[str] = mapped_column(String(30))  # payment | bank_change | override
    required_role: Mapped[Role] = mapped_column(Enum(Role))
    reason: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String(120), default="agent")
    decision: Mapped[str | None] = mapped_column(String(20))  # approved | rejected
    decided_by: Mapped[str | None] = mapped_column(String(120))
    decided_role: Mapped[Role | None] = mapped_column(Enum(Role))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BankChange(Base):
    """A requested change to a vendor's remit-to bank account.

    Never applied by the agent. Requires two distinct human approvers, one of
    whom must record an out-of-band callback to a number already on file.
    """

    __tablename__ = "bank_changes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"))
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id"))
    old_account: Mapped[str | None] = mapped_column(String(64))
    new_account: Mapped[str] = mapped_column(String(64))
    new_routing: Mapped[str | None] = mapped_column(String(32))
    new_bank_name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    callback_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    vendor: Mapped[Vendor] = relationship()


class EmailMessage(Base):
    __tablename__ = "emails"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str | None] = mapped_column(ForeignKey("invoices.id"), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # out | in
    sender: Mapped[str] = mapped_column(String(200))
    recipient: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(String(300), unique=True)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent | simulated | received | failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), unique=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"))
    gross: Mapped[Decimal | None] = mapped_column(Money)  # invoice total
    deductions: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))  # contract recoveries
    discount: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))  # early-payment discount taken
    amount: Mapped[Decimal] = mapped_column(Money)  # what actually leaves the bank
    due_date: Mapped[date | None] = mapped_column(Date)
    discount_deadline: Mapped[date | None] = mapped_column(Date)
    discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("payment_runs.id"))
    currency: Mapped[str] = mapped_column(String(3))
    pay_to_account: Mapped[str] = mapped_column(String(64))
    pay_to_routing: Mapped[str | None] = mapped_column(String(32))
    scheduled_for: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    """Append-only, hash-chained log of everything the agent and humans did."""

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str | None] = mapped_column(String(12), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(40))
    invoice_id: Mapped[str | None] = mapped_column(String(12), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MailCursor(Base):
    __tablename__ = "mail_cursor"
    __table_args__ = (UniqueConstraint("mailbox"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mailbox: Mapped[str] = mapped_column(String(200))
    last_uid: Mapped[int] = mapped_column(Integer, default=0)


class InferenceSpend(Base):
    """Running total of model usage, checked before every call."""

    __tablename__ = "inference_spend"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model: Mapped[str] = mapped_column(String(80), unique=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))


class InvoiceCost(Base):
    """Model usage charged to one invoice. No foreign key: usage is flushed
    after the job's transaction, and the invoice may have been reset since."""

    __tablename__ = "invoice_costs"
    invoice_id: Mapped[str] = mapped_column(String(12), primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    effective_date: Mapped[date | None] = mapped_column(Date)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    vendor: Mapped[Vendor] = relationship()
    terms: Mapped[list[ContractTerm]] = relationship(back_populates="contract", cascade="all, delete-orphan", order_by="ContractTerm.id")


class ContractTerm(Base):
    """One machine-checkable term, extracted from a contract with its exact clause.

    The model proposes terms; a person approves them; code applies approved
    terms to every invoice."""

    __tablename__ = "contract_terms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # sla_credit | volume_price | price_cap | early_pay_discount
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    quote: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed | approved | rejected
    source: Mapped[str] = mapped_column(String(40), default="model")
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    contract: Mapped[Contract] = relationship(back_populates="terms")


class ServiceMetric(Base):
    """Measured service levels (from our own monitoring), used for SLA credits."""

    __tablename__ = "service_metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    metric: Mapped[str] = mapped_column(String(40))
    value: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    source: Mapped[str] = mapped_column(String(200))


class CriticReview(Base):
    __tablename__ = "critic_reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), index=True)
    proposal: Mapped[dict] = mapped_column(JSON, default=dict)
    verdict: Mapped[str] = mapped_column(String(20))  # agree | concerns | disagree | unavailable
    summary: Mapped[str] = mapped_column(Text)
    points: Mapped[list] = mapped_column(JSON, default=list)
    independent_amount: Mapped[Decimal | None] = mapped_column(Money)
    model: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentRun(Base):
    __tablename__ = "payment_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed | approved | rejected
    cash_before: Mapped[Decimal] = mapped_column(Money)
    cash_floor: Mapped[Decimal] = mapped_column(Money)
    total: Mapped[Decimal] = mapped_column(Money)
    discounts: Mapped[Decimal] = mapped_column(Money)
    plan: Mapped[dict] = mapped_column(JSON, default=dict)
    proposed_by: Mapped[str] = mapped_column(String(120), default="agent")
    approved_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
