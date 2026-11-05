"""The briefing: what the agent did while nobody was watching, what it is still
working on, and the few decisions that need a person, each with the agent's
recommendation. Every number here is counted from the ledger and the audit
trail; the one estimate (time saved) carries its assumption with it."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import clock
from .config import get_settings
from .models import (
    Approval,
    AuditEvent,
    BankChange,
    ColleagueQuestion,
    CriticReview,
    Invoice,
    InvoiceStatus,
    Job,
    Payment,
    VendorCredit,
)

MACHINE = {"agent", "controls", "policy", "system", "critic", "attack lab", "upload", "Receiving dock"}
DONE = (InvoiceStatus.scheduled, InvoiceStatus.paid, InvoiceStatus.rejected)
WORKING = ("colleague", "receipt", "agent")
WORK_KINDS = {
    "action:email_vendor": "emails",
    "action:email_budget_owner": "emails",
    "action:ask_colleague": "questions",
    "approval_reminder": "reminders",
    "tool": "lookups",
    "action:attach_po": "fixes",
    "action:accept_charge": "fixes",
    "action:schedule_payment": "payments",
    "action:reject": "rejections",
}


def is_human(ev: AuditEvent) -> bool:
    if ev.kind in ("received", "seed"):
        return False
    a = ev.actor or ""
    return not (a in MACHINE or a.startswith(("email:", "colleague:")))


def _iso(dt: datetime | None) -> str | None:
    return clock.aware(dt).isoformat() if dt else None


def _chains(invs: list[Invoice]) -> list[list[Invoice]]:
    by_id = {i.id: i for i in invs}
    nxt = {i.supersedes_id: i for i in invs if i.supersedes_id}
    roots = [i for i in invs if not i.supersedes_id or i.supersedes_id not in by_id]
    out = []
    for r in roots:
        chain = [r]
        while chain[-1].id in nxt:
            chain.append(nxt[chain[-1].id])
        out.append(chain)
    return out


def _money(x) -> str:
    return f"${Decimal(str(x or 0)):,.2f}"


def _recommend(s: Session, inv: Invoice, kind: str) -> str:
    from .agent import deductions

    codes = {f.code for f in inv.findings if not f.resolved}
    if kind == "approval":
        rv = s.execute(select(CriticReview).where(CriticReview.invoice_id == inv.id).order_by(CriticReview.id.desc())).scalars().first()
        ded = deductions(inv)
        net = (inv.total or Decimal(0)) - ded
        rec = f"Approve: every control passes. Pay {_money(net)}" + (f" after the {_money(ded)} the contract entitles us to" if ded else "") + "."
        if rv is not None and rv.verdict in ("concerns", "disagree"):
            rec = f"Read the critic first ({rv.verdict}): {rv.summary[:200]}"
        return rec
    if kind == "quarantine":
        why = "Reject it: the document carries instructions written for the AI"
        if "DOC_FINGERPRINT" in codes:
            why += ", the PDF was not produced by the vendor's billing system"
        if "NOT_ON_VENDOR_STATEMENT" in codes:
            why += ", and the vendor's own statement does not list it"
        if "BANK_MISMATCH" in codes:
            why += ". It also asks for payment to an unverified account"
        return why + "."
    if kind == "bank_change":
        v = inv.vendor
        return (f"Call {v.name if v else 'the vendor'} on the number already on file, not one on the invoice. Approve only if they confirm the new account; "
                "until then the payment stays on the verified account.")
    return (inv.agent_state or {}).get("recommendation") or (inv.agent_state or {}).get("hold_reason") or "Review the findings."


def build(s: Session) -> dict:
    cfg = get_settings()
    invs = list(s.execute(select(Invoice).where(Invoice.source.not_in(["history", "lab"])).order_by(Invoice.created_at)).scalars())
    ids = [i.id for i in invs]
    events: dict[str, list[AuditEvent]] = defaultdict(list)
    if ids:
        for e in s.execute(select(AuditEvent).where(AuditEvent.invoice_id.in_(ids)).order_by(AuditEvent.id)).scalars():
            events[e.invoice_id].append(e)
    work: dict[str, int] = defaultdict(int)
    for evs in events.values():
        for e in evs:
            k = WORK_KINDS.get(e.kind)
            if k:
                work[k] += 1

    pending_approvals = list(s.execute(select(Approval).where(Approval.decision.is_(None), Approval.invoice_id.in_(ids))).scalars()) if ids else []
    jobs: dict[str, list[Job]] = defaultdict(list)
    if ids:
        for j in s.execute(select(Job).where(Job.status == "queued", Job.invoice_id.in_(ids)).order_by(Job.run_after)).scalars():
            jobs[j.invoice_id].append(j)

    resolved, working, needs_you = [], [], []
    touchless = decided = human_touches = 0
    hours: list[float] = []
    for chain in _chains(invs):
        final = chain[-1]
        evs = [e for i in chain for e in events.get(i.id, [])]
        humans = [e for e in evs if is_human(e)]
        human_touches += len(humans)
        exceptions = sorted({c for i in chain for c in (i.agent_state or {}).get("exceptions", [])})
        v = final.vendor
        base = {"invoice_id": final.id, "number": final.number, "vendor": v.name if v else final.vendor_name_raw, "total": float(final.total or 0),
                "exceptions": exceptions}
        if final.status in DONE:
            decided += 1
            if not humans:
                touchless += 1
            if exceptions:
                start, end = clock.aware(chain[0].created_at), clock.aware(evs[-1].created_at) if evs else clock.aware(final.created_at)
                h = max((end - start).total_seconds() / 3600, 0)
                steps = sum(1 for e in evs if e.kind in WORK_KINDS)
                item = {**base, "status": final.status.value, "summary": final.summary, "steps": steps, "hours": round(h, 1),
                        "by_agent": not humans, "people": sorted({e.actor for e in humans})}
                resolved.append(item)
                if not humans:
                    hours.append(h)
            continue
        waiting = (final.agent_state or {}).get("waiting_for")
        if final.status == InvoiceStatus.awaiting_vendor or (final.status == InvoiceStatus.on_hold and waiting in WORKING):
            qs = [q for q in s.execute(select(ColleagueQuestion).where(ColleagueQuestion.invoice_id == final.id).order_by(ColleagueQuestion.id)).scalars()
                  if q.topic != "approval"]
            last_q = qs[-1] if qs else None
            if final.status == InvoiceStatus.awaiting_vendor:
                on = f"{v.name if v else 'the vendor'} (vendor)"
            elif last_q is not None:
                on = last_q.person_name
            else:
                on = "the agent"
            nxt = next((j for j in jobs.get(final.id, []) if j.kind in ("followup", "check_in", "colleague_reply", "decide", "recheck")), None)
            label = {"followup": "follows up with the vendor", "check_in": "checks the receipt again", "colleague_reply": "expects an answer",
                     "decide": "re-plans", "recheck": "re-checks"}
            eta = last_q.eta if (final.status != InvoiceStatus.awaiting_vendor and last_q is not None and last_q.answer == "later") else None
            working.append({**base, "waiting_on": on, "what": (final.agent_state or {}).get("hold_reason") or final.summary,
                            "eta": _iso(eta), "next": label[nxt.kind] if nxt else None, "next_at": _iso(nxt.run_after) if nxt else None})
            continue
        if final.status in (InvoiceStatus.on_hold, InvoiceStatus.awaiting_approval):
            codes = {f.code for f in final.findings if not f.resolved}
            pa = [a for a in pending_approvals if a.invoice_id == final.id]
            bc = s.execute(select(BankChange).where(BankChange.invoice_id == final.id, BankChange.status == "pending")).scalar_one_or_none()
            if "PROMPT_INJECTION" in codes:
                kind, title = "quarantine", "Decide on a quarantined invoice"
            elif bc is not None:
                kind, title = "bank_change", "Verify a bank account change"
            elif any(a.kind == "payment" for a in pa):
                kind, title = "approval", "Approve a payment"
            else:
                kind, title = "review", "Review an exception the agent handed over"
            pay_ap = next((a for a in pa if a.kind == "payment"), None)
            needs_you.append({**base, "kind": kind, "title": title, "recommendation": _recommend(s, final, kind),
                              "why": (pay_ap.reason if pay_ap else (final.agent_state or {}).get("hold_reason")) or final.summary,
                              "approval_id": pay_ap.id if pay_ap else None, "required_role": pay_ap.required_role.value if pay_ap else None,
                              "waiting_since": _iso((pay_ap.created_at if pay_ap else (evs[-1].created_at if evs else final.created_at)))})

    credits = list(s.execute(select(VendorCredit).where(VendorCredit.status == "open")).scalars())
    for c in credits:
        needs_you.append({"invoice_id": None, "number": c.reference, "vendor": None, "total": float(c.amount), "exceptions": [], "kind": "credit",
                          "title": "Claim a credit the vendor owes us", "recommendation": f"Claim it: {_money(c.amount)} comes off the vendor's next payment.",
                          "why": c.description, "approval_id": None, "required_role": "controller", "waiting_since": _iso(c.created_at), "credit_id": c.id})

    by_agent = [r for r in resolved if r["by_agent"]]
    exceptions_total = len(resolved) + len(working) + len([n for n in needs_you if n["exceptions"]])
    recovered = sum((p.deductions or Decimal(0)) + (p.discount or Decimal(0)) for p in s.execute(select(Payment).where(Payment.invoice_id.in_(ids))).scalars()) if ids else 0
    first = clock.aware(invs[0].created_at) if invs else None
    return {
        "now": clock.now().isoformat(),
        "clock_offset_hours": round(clock.offset_s() / 3600, 2),
        "since": first.isoformat() if first else None,
        "invoices": len(_chains(invs)),
        "decided": decided,
        "touchless": touchless,
        "touchless_rate": touchless / decided if decided else 0,
        "human_touches": human_touches,
        "exceptions": {"total": exceptions_total, "resolved_by_agent": len(by_agent), "resolved_with_help": len(resolved) - len(by_agent),
                       "in_progress": len(working), "median_hours": round(median(hours), 1) if hours else None},
        "work": dict(work),
        "recovered": float(recovered),
        "time_saved": {"hours": round(len(by_agent) * cfg.minutes_per_exception / 60, 1), "minutes_per_exception": cfg.minutes_per_exception,
                       "assumption": f"{cfg.minutes_per_exception:g} minutes of AP time per exception, the low end of the 15-45 minutes commonly cited"},
        "resolved": sorted(resolved, key=lambda r: (not r["by_agent"], r["number"] or "")),
        "working": working,
        "needs_you": needs_you,
    }
