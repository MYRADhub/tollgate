"""Tamper-evident audit log: each event's hash covers the previous event's hash."""

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditEvent, utcnow

GENESIS = "0" * 64


def _ts(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=dt.microsecond).isoformat()


def _default(o):
    if isinstance(o, (Decimal,)):
        return str(o)
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


def _digest(prev_hash: str, invoice_id: str | None, actor: str, kind: str, summary: str, detail: dict, ts: str) -> str:
    payload = json.dumps(
        {"prev": prev_hash, "invoice": invoice_id, "actor": actor, "kind": kind, "summary": summary, "detail": detail, "ts": ts},
        sort_keys=True,
        default=_default,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def record(
    s: Session, *, actor: str, kind: str, summary: str, invoice_id: str | None = None, detail: dict | None = None
) -> AuditEvent:
    detail = json.loads(json.dumps(detail or {}, default=_default))
    last = s.execute(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1).with_for_update()).scalar_one_or_none()
    prev = last.hash if last else GENESIS
    ts = utcnow()
    ev = AuditEvent(
        invoice_id=invoice_id,
        actor=actor,
        kind=kind,
        summary=summary,
        detail=detail,
        prev_hash=prev,
        created_at=ts,
        hash=_digest(prev, invoice_id, actor, kind, summary, detail, _ts(ts)),
    )
    s.add(ev)
    s.flush()
    from . import events

    events.publish({"type": "audit", "invoice_id": invoice_id, "kind": kind, "summary": summary, "actor": actor})
    return ev


def verify_chain(s: Session) -> tuple[bool, int | None]:
    """Recompute every hash. Returns (ok, id of first broken event)."""
    prev = GENESIS
    for ev in s.execute(select(AuditEvent).order_by(AuditEvent.id)).scalars():
        if ev.prev_hash != prev or _digest(prev, ev.invoice_id, ev.actor, ev.kind, ev.summary, ev.detail, _ts(ev.created_at)) != ev.hash:
            return False, ev.id
        prev = ev.hash
    return True, None
