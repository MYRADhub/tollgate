"use client";

import Link from "next/link";
import { useState } from "react";
import { Bot, CheckCircle2, Clock3, Hourglass, Sparkles, UserCheck } from "lucide-react";
import { Briefing as B, PEOPLE, ROLE_LABEL, Role, ago, api, canApprove, clockLabel, compactMoney, money, useActor, useData } from "@/lib/api";
import { useFeedback } from "./Feedback";
import { Button, Card, Flag, cx } from "./ui";

const KIND_TONE: Record<string, string> = {
  quarantine: "bg-rose-50 text-rose-700",
  bank_change: "bg-amber-50 text-amber-800",
  approval: "bg-indigo-50 text-indigo-700",
  credit: "bg-emerald-50 text-emerald-800",
  review: "bg-slate-100 text-slate-700",
};

function Metric({ label, value, sub, title }: { label: string; value: string; sub?: string; title?: string }) {
  return (
    <div className="min-w-0" title={title}>
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="text-2xl font-semibold tabular-nums text-slate-900">{value}</div>
      {sub && <div className="truncate text-[11.5px] text-slate-500">{sub}</div>}
    </div>
  );
}

function QuickApprove({ id, role, reload }: { id: number; role: Role; reload: () => void }) {
  const { actor, setActor } = useActor();
  const fb = useFeedback();
  const [busy, setBusy] = useState(false);
  if (!canApprove(actor.role, role)) {
    const p = PEOPLE.find((x) => canApprove(x.role, role)) || PEOPLE[PEOPLE.length - 1];
    return (
      <Button size="sm" onClick={() => setActor(p)}>
        Act as {p.user} ({ROLE_LABEL[p.role]})
      </Button>
    );
  }
  const go = async () => {
    setBusy(true);
    try {
      await api(`/api/approvals/${id}/decide`, { method: "POST", json: { ...actor, decision: "approved" } });
      fb.toast("success", "Approved", "The agent schedules the payment and sends remittance advice.");
      reload();
    } catch (e) {
      fb.toast("error", "Could not approve", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button size="sm" variant="good" onClick={go} disabled={busy}>
      Approve as {actor.user}
    </Button>
  );
}

export function Briefing() {
  const { data: b, reload } = useData<B>("/api/briefing");
  if (!b || b.invoices === 0) return null;
  const w = b.work;
  const workBits = [
    w.lookups && `${w.lookups} lookups`,
    w.questions && `${w.questions} questions to colleagues`,
    w.emails && `${w.emails} vendor emails`,
    w.reminders && `${w.reminders} approval reminders`,
    w.fixes && `${w.fixes} PO fixes`,
  ].filter(Boolean) as string[];
  const workTotal = (w.lookups || 0) + (w.questions || 0) + (w.emails || 0) + (w.reminders || 0) + (w.fixes || 0);
  const exc = b.exceptions;
  return (
    <section className="space-y-3" data-testid="briefing">
      <Card
        title={
          <span className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-indigo-600" /> While you were away
            {b.since && <span className="font-normal text-slate-500">since {clockLabel(b.since)}</span>}
          </span>
        }
      >
        <p className="mb-3 text-[13.5px] leading-relaxed text-slate-700">
          The agent took {b.invoices} invoice{b.invoices === 1 ? "" : "s"}. <b>{b.touchless}</b> {b.touchless === 1 ? "was" : "were"} settled without anyone in AP touching them
          {exc.total > 0 && (
            <>
              , and it cleared <b>{exc.resolved_by_agent} of {exc.total}</b> exceptions on its own by asking the people who knew
            </>
          )}
          .{" "}
          {b.needs_you.length > 0 ? (
            <>
              <b>{b.needs_you.length}</b> decision{b.needs_you.length === 1 ? " needs" : "s need"} you, each with its recommendation.
            </>
          ) : (
            "Nothing needs you."
          )}
        </p>
        <div className="grid grid-cols-2 gap-4 border-t border-slate-100 pt-3 md:grid-cols-5">
          <Metric label="Settled untouched" value={`${b.touchless} of ${b.decided}`} sub={`${Math.round(b.touchless_rate * 100)}% touchless`} />
          <Metric label="Exceptions it cleared" value={`${exc.resolved_by_agent} of ${exc.total}`} sub={exc.in_progress ? `${exc.in_progress} still in progress` : exc.median_hours !== null ? `median ${exc.median_hours}h to clear` : undefined} />
          <Metric label="AP time saved" value={`~${b.time_saved.hours}h`} sub={`${b.time_saved.minutes_per_exception} min per exception`} title={`Estimate. Assumes ${b.time_saved.assumption}.`} />
          <Metric label="Work done for you" value={String(workTotal)} sub={workBits.slice(0, 2).join(", ")} title={workBits.join(", ")} />
          <Metric label="Human touches" value={String(b.human_touches)} sub="approvals and decisions by people" />
        </div>
      </Card>

      <div className="grid gap-3 lg:grid-cols-3">
        <Card title={<span className="flex items-center gap-1.5"><UserCheck className="h-4 w-4 text-indigo-600" /> Needs you ({b.needs_you.length})</span>} pad={false}>
          {b.needs_you.length === 0 ? (
            <p className="px-4 py-3 text-[13px] text-slate-500">Nothing. The agent has everything else in hand.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {b.needs_you.map((n) => (
                <li key={`${n.kind}-${n.invoice_id || n.credit_id}`} className="space-y-1.5 px-4 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className={cx("rounded px-1.5 py-0.5 text-[11px] font-medium", KIND_TONE[n.kind])}>{n.title}</span>
                    {n.waiting_since && <span className="text-[11px] text-slate-400">{ago(n.waiting_since)}</span>}
                  </div>
                  <div className="text-[13px] font-medium text-slate-900">
                    {n.vendor ? `${n.vendor} · ` : ""}
                    <span className="font-mono">{n.number}</span> · {money(n.total)}
                  </div>
                  <div className="rounded-md bg-indigo-50/60 px-2.5 py-1.5 text-[12.5px] leading-snug text-slate-800">
                    <Bot className="mr-1 inline h-3.5 w-3.5 text-indigo-600" />
                    {n.recommendation}
                  </div>
                  <div className="flex flex-wrap gap-1.5 pt-0.5">
                    {n.kind === "approval" && n.approval_id && n.required_role && <QuickApprove id={n.approval_id} role={n.required_role} reload={reload} />}
                    {n.invoice_id ? (
                      <Link href={`/invoices/${n.invoice_id}`}>
                        <Button size="sm" variant="ghost">
                          Open
                        </Button>
                      </Link>
                    ) : (
                      <Link href="/statements">
                        <Button size="sm" variant="ghost">
                          Review on Statements
                        </Button>
                      </Link>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title={<span className="flex items-center gap-1.5"><Hourglass className="h-4 w-4 text-violet-600" /> Agent is working ({b.working.length})</span>} pad={false}>
          {b.working.length === 0 ? (
            <p className="px-4 py-3 text-[13px] text-slate-500">No open exceptions.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {b.working.map((x) => (
                <li key={x.invoice_id} className="space-y-1 px-4 py-3">
                  <Link href={`/invoices/${x.invoice_id}`} className="text-[13px] font-medium text-slate-900 hover:text-indigo-700">
                    {x.vendor} · <span className="font-mono">{x.number}</span>
                  </Link>
                  <div className="flex flex-wrap gap-1">
                    {x.exceptions.map((c) => (
                      <Flag key={c} code={c} />
                    ))}
                  </div>
                  <div className="text-[12.5px] text-slate-700">
                    Waiting on {x.waiting_on}
                    {x.eta && <span className="text-slate-500"> (goods due {clockLabel(x.eta)})</span>}
                  </div>
                  {x.what && <div className="line-clamp-2 text-[12px] text-slate-500">{x.what}</div>}
                  {x.next && x.next_at && (
                    <div className="flex items-center gap-1 text-[11.5px] text-violet-700">
                      <Clock3 className="h-3 w-3" /> Agent {x.next} {clockLabel(x.next_at)}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
          {b.working.length > 0 && (
            <p className="border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">Use Fast-forward a day (top right) to see what happens next.</p>
          )}
        </Card>

        <Card title={<span className="flex items-center gap-1.5"><CheckCircle2 className="h-4 w-4 text-emerald-600" /> Exceptions cleared ({b.resolved.length})</span>} pad={false}>
          {b.resolved.length === 0 ? (
            <p className="px-4 py-3 text-[13px] text-slate-500">None yet. The agent is asking around; answers come back within a minute.</p>
          ) : (
            <ul className="max-h-[420px] divide-y divide-slate-100 overflow-y-auto">
              {b.resolved.map((r) => (
                <li key={r.invoice_id} className="space-y-1 px-4 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <Link href={`/invoices/${r.invoice_id}`} className="text-[13px] font-medium text-slate-900 hover:text-indigo-700">
                      {r.vendor} · <span className="font-mono">{r.number}</span>
                    </Link>
                    <span className={cx("shrink-0 text-[11px] font-medium", r.status === "rejected" ? "text-zinc-500" : "text-emerald-700")}>
                      {r.status === "rejected" ? "Rejected" : `Paying ${compactMoney(r.total)}`}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {r.exceptions.map((c) => (
                      <Flag key={c} code={c} />
                    ))}
                  </div>
                  <div className="line-clamp-3 text-[12px] leading-snug text-slate-600">{r.summary}</div>
                  <div className="text-[11px] text-slate-400">
                    {r.by_agent ? `${r.steps} agent steps, no person involved` : `with ${r.people.join(", ")}`}
                    {r.hours >= 1 ? `, ${r.hours}h` : ""}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </section>
  );
}
