"""Background worker: runs queued jobs and polls the AP mailbox.

Runs as its own process on the Vultr VM (`python -m tollgate.worker`), so the
agent keeps working, following up and reacting to replies with nobody's
browser open."""

from __future__ import annotations

import logging
import signal
import time

from sqlalchemy import select, update

from . import agent, mailer, paymentrun, pipeline
from .config import get_settings
from .db import init_db, session_scope
from .llm import attribute, flush_spend
from .models import Invoice, Job, utcnow

log = logging.getLogger("tollgate.worker")
_stop = False


def run_job(job_id: int) -> None:
    with session_scope() as s:
        invoice_id = s.get(Job, job_id).invoice_id
    with attribute(invoice_id):
        _run_job(job_id)


def _run_job(job_id: int) -> None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        inv = s.get(Invoice, job.invoice_id) if job.invoice_id else None
        if job.kind == "process":
            pipeline.process(s, job.invoice_id)
        elif job.kind == "recheck":
            pipeline.recheck(s, job.invoice_id, job.payload.get("reason", "re-check"))
        elif job.kind == "decide" and inv is not None:
            agent.decide(s, inv, trigger=job.payload.get("trigger", "update"), extra=job.payload.get("extra"))
        elif job.kind == "vendor_reply" and inv is not None:
            mailer.handle_vendor_reply(s, inv, int(job.payload["email_id"]))
        elif job.kind == "followup" and inv is not None:
            agent.followup(s, inv)
        elif job.kind == "apply_credit":
            from . import statements

            statements.apply_credit(s, int(job.payload["credit_id"]))
        elif job.kind == "statement":
            from . import statements

            statements.process(s, int(job.payload["statement_id"]))
        elif job.kind == "inquiry":
            from . import inquiry

            inquiry.handle(s, int(job.payload["email_id"]), job.payload.get("headers"), simulate=bool(job.payload.get("simulate")))
        elif job.kind == "plan_run":
            from sqlalchemy import select as _select

            newer = s.execute(_select(Job.id).where(Job.kind == "plan_run", Job.status == "queued", Job.id > job.id)).first()
            if newer is None:  # several invoices scheduled together: plan once, after the last
                paymentrun.propose(s)


def run_due_jobs(limit: int = 10) -> int:
    with session_scope() as s:
        ids = list(
            s.execute(
                select(Job.id).where(Job.status == "queued", Job.run_after <= utcnow()).order_by(Job.run_after, Job.id).limit(limit)
            ).scalars()
        )
    n = 0
    for jid in ids:
        with session_scope() as s:
            claimed = s.execute(update(Job).where(Job.id == jid, Job.status == "queued").values(status="running", attempts=Job.attempts + 1)).rowcount
        if not claimed:
            continue
        try:
            run_job(jid)
            status, err = "done", None
        except Exception as e:
            log.exception("job %s failed", jid)
            status, err = "failed", f"{type(e).__name__}: {e}"
            with session_scope() as s:
                job = s.get(Job, jid)
                if job.invoice_id:
                    inv = s.get(Invoice, job.invoice_id)
                    if inv is not None and inv.status.value in ("extracting", "checking", "deciding"):
                        from .models import InvoiceStatus

                        inv.status = InvoiceStatus.on_hold
                        inv.agent_state = {**(inv.agent_state or {}), "waiting_for": "person", "hold_reason": f"Processing error: {err[:200]}"}
                    from . import audit

                    audit.record(s, actor="system", kind="error", invoice_id=job.invoice_id, summary=f"{job.kind} failed: {err[:300]}")
        with session_scope() as s:
            s.execute(update(Job).where(Job.id == jid).values(status=status, last_error=err))
        try:
            flush_spend()
        except Exception:
            log.exception("could not record inference spend")
        n += 1
    return n


def drain(max_rounds: int = 50) -> None:
    """Run jobs until none are due (used by tests and the demo seeder)."""
    for _ in range(max_rounds):
        if run_due_jobs() == 0:
            return


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    init_db()
    cfg = get_settings()

    def _sig(*_):
        global _stop
        _stop = True

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    last_poll = 0.0
    log.info("worker started (mail %s)", "on" if cfg.mail_enabled else "off")
    while not _stop:
        did = run_due_jobs()
        if time.monotonic() - last_poll >= cfg.mail_poll_interval_s:
            last_poll = time.monotonic()
            try:
                with session_scope() as s:
                    n = mailer.poll_inbox(s)
                if n:
                    log.info("mailbox: %d new message(s)", n)
            except Exception:
                log.exception("mail poll failed")
        if not did:
            time.sleep(1.0)


if __name__ == "__main__":
    main()
