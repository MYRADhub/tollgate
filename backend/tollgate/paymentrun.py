"""Payment runs: when to pay each approved invoice.

Pays everything due within the run horizon, then spends what is left above
the cash floor on early-payment discounts, best annualised return first.
Deterministic; the controller approves the run before money moves.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import audit
from .config import get_settings
from .models import Invoice, Payment, PaymentRun, utcnow

CENT = Decimal("0.01")


def _m(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Candidate:
    payment_id: int
    invoice_id: str
    number: str
    vendor: str
    amount: Decimal  # net of contract deductions
    due: date
    discount_pct: Decimal | None
    discount_deadline: date | None

    def discount_if_paid(self, on: date) -> Decimal:
        if self.discount_pct and self.discount_deadline and on <= self.discount_deadline:
            return _m(self.amount * self.discount_pct / 100)
        return Decimal(0)

    def annualised_return(self) -> float:
        """What paying early earns, as an annual rate (2/10 net 30 is about 37%)."""
        if not (self.discount_pct and self.discount_deadline):
            return 0.0
        days = max((self.due - self.discount_deadline).days, 1)
        p = float(self.discount_pct) / 100
        return p / (1 - p) * 365 / days


def cash_position(s: Session) -> Decimal:
    cfg = get_settings()
    released = s.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.run_id.is_not(None), Payment.status == "released")
    ).scalar_one()
    return _m(Decimal(str(cfg.cash_balance_usd)) - Decimal(str(released or 0)))


def plan(candidates: list[Candidate], today: date, cash: Decimal, floor: Decimal, horizon_days: int) -> dict:
    available = cash - floor
    horizon = today + timedelta(days=horizon_days)
    items, spent, discounts = [], Decimal(0), Decimal(0)

    def take(c: Candidate, reason: str) -> bool:
        nonlocal spent, discounts
        disc = c.discount_if_paid(today)
        cost = c.amount - disc
        if spent + cost > available:
            return False
        spent += cost
        discounts += disc
        items.append({"payment_id": c.payment_id, "invoice_id": c.invoice_id, "number": c.number, "vendor": c.vendor,
                      "decision": "pay", "amount": str(c.amount), "discount": str(disc), "pay": str(cost), "due": c.due.isoformat(), "reason": reason})
        return True

    def defer(c: Candidate, reason: str) -> None:
        items.append({"payment_id": c.payment_id, "invoice_id": c.invoice_id, "number": c.number, "vendor": c.vendor,
                      "decision": "defer", "amount": str(c.amount), "discount": "0", "pay": "0", "due": c.due.isoformat(), "reason": reason})

    due_now = sorted([c for c in candidates if c.due <= horizon], key=lambda c: c.due)
    later = [c for c in candidates if c.due > horizon]
    early = sorted([c for c in later if c.discount_if_paid(today) > 0], key=lambda c: -c.annualised_return())
    rest = [c for c in later if c.discount_if_paid(today) == 0]

    for c in due_now:
        if not take(c, f"due {c.due}" + (f"; {c.discount_pct}% discount still available" if c.discount_if_paid(today) else "")):
            defer(c, f"due {c.due} but paying it would breach the {floor:,.0f} cash floor: needs treasury")
    for c in early:
        rate = c.annualised_return() * 100
        if not take(c, f"early: {c.discount_pct}% discount until {c.discount_deadline}, worth {rate:.0f}% a year annualised"):
            defer(c, f"discount worth {rate:.0f}% a year, but cash above the floor is committed to invoices that are due")
    for c in rest:
        defer(c, f"not due until {c.due}; no early-payment discount, so cash stays in the bank")

    return {
        "items": items,
        "cash_before": str(cash),
        "floor": str(floor),
        "pay_total": str(_m(spent)),
        "discounts": str(_m(discounts)),
        "cash_after": str(_m(cash - spent)),
        "horizon": horizon.isoformat(),
    }


def candidates(s: Session) -> list[Candidate]:
    out = []
    rows = s.execute(select(Payment, Invoice).join(Invoice, Invoice.id == Payment.invoice_id).where(Payment.status == "scheduled", Payment.run_id.is_(None), Invoice.source != "lab"))
    for p, inv in rows:
        out.append(Candidate(p.id, inv.id, inv.number or inv.id, inv.vendor.name if inv.vendor else "?", p.amount,
                             p.due_date or p.scheduled_for, p.discount_pct, p.discount_deadline))
    return out


def propose(s: Session, actor: str = "agent", today: date | None = None) -> PaymentRun | None:
    cfg = get_settings()
    today = today or date.today()
    for old in s.execute(select(PaymentRun).where(PaymentRun.status == "proposed")).scalars():
        s.delete(old)
    s.flush()
    cands = candidates(s)
    if not cands:
        return None
    cash = cash_position(s)
    floor = Decimal(str(cfg.cash_floor_usd))
    p = plan(cands, today, cash, floor, cfg.run_horizon_days)
    run = PaymentRun(run_date=today, status="proposed", cash_before=cash, cash_floor=floor, total=Decimal(p["pay_total"]),
                     discounts=Decimal(p["discounts"]), plan=p, proposed_by=actor)
    s.add(run)
    s.flush()
    n = sum(1 for i in p["items"] if i["decision"] == "pay")
    audit.record(s, actor=actor, kind="run_proposed",
                 summary=f"Proposed payment run {run.id}: pay {n} of {len(cands)} invoices, {_m(p['pay_total']):,.2f}, "
                         f"capturing {_m(p['discounts']):,.2f} in early-payment discounts; cash stays above {floor:,.0f}")
    return run


def approve(s: Session, run_id: int, user: str, role: str) -> PaymentRun:
    from .api_actions import ActionError

    if role not in ("controller", "cfo"):
        raise ActionError("payment runs are approved by the controller or CFO")
    run = s.get(PaymentRun, run_id)
    if run is None or run.status != "proposed":
        raise ActionError("no proposed run with that id")
    for item in run.plan["items"]:
        if item["decision"] != "pay":
            continue
        p = s.get(Payment, item["payment_id"])
        if p is None or p.status != "scheduled" or p.run_id is not None:
            raise ActionError("the run is out of date; plan it again")
        p.discount = Decimal(item["discount"])
        p.amount = _m(p.amount - p.discount)
        p.scheduled_for = run.run_date
        p.run_id = run.id
        p.status = "released"
        inv = s.get(Invoice, p.invoice_id)
        audit.record(s, actor=f"{user} ({role})", kind="payment_released", invoice_id=p.invoice_id,
                     summary=f"Released {p.amount:,.2f} to {inv.vendor.name if inv and inv.vendor else 'vendor'} in run {run.id}"
                             + (f", taking a {p.discount:,.2f} early-payment discount" if p.discount else ""))
    run.status, run.approved_by, run.approved_at = "approved", f"{user} ({role})", utcnow()
    audit.record(s, actor=f"{user} ({role})", kind="run_approved",
                 summary=f"{user} approved payment run {run.id}: {run.total:,.2f} out, {run.discounts:,.2f} saved in discounts")
    return run


def bank_file(s: Session, run_id: int) -> str:
    """A CSV payment batch for upload to the bank's portal."""
    run = s.get(PaymentRun, run_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["batch_id", "payment_id", "payee", "account_number", "routing_number", "amount", "currency", "value_date", "reference"])
    for p in s.execute(select(Payment).where(Payment.run_id == run_id).order_by(Payment.id)).scalars():
        inv = s.get(Invoice, p.invoice_id)
        w.writerow([f"TG-RUN-{run.id}", p.id, inv.vendor.name, p.pay_to_account.replace(" ", ""), p.pay_to_routing or "",
                    f"{p.amount:.2f}", p.currency, run.run_date.isoformat(), f"INV {inv.number}"])
    return buf.getvalue()
