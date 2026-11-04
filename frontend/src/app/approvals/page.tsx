"use client";

import Link from "next/link";
import { Landmark, ShieldCheck } from "lucide-react";
import { Approval, ROLE_LABEL, money, useActor, useData } from "@/lib/api";
import { BankChangeReview, PaymentApproval } from "@/components/ApprovalControls";
import { Card, Empty, Flag } from "@/components/ui";

type Group = { key: string; kind: "payment" | "bank_change"; items: Approval[] };

function group(rows: Approval[]): Group[] {
  const out = new Map<string, Group>();
  for (const a of rows) {
    const key = a.kind === "bank_change" ? `bc-${a.bank_change_id}` : `p-${a.id}`;
    const g = out.get(key) || { key, kind: a.kind, items: [] };
    g.items.push(a);
    out.set(key, g);
  }
  return [...out.values()].map((g) => ({ ...g, items: g.items.sort((x, y) => x.id - y.id) }));
}

function InvoiceLine({ a }: { a: Approval }) {
  const inv = a.invoice;
  if (!inv) return null;
  return (
    <Link href={`/invoices/${inv.id}`} className="inline-flex flex-wrap items-center gap-2 text-xs text-indigo-700 hover:underline">
      <span className="font-mono">
        {inv.number} · {inv.po_number}
      </span>
      {inv.flags.map((c) => (
        <Flag key={c} code={c} />
      ))}
      {inv.recover.map((c) => (
        <Flag key={c} code={c} severity="recover" />
      ))}
    </Link>
  );
}

export default function ApprovalsPage() {
  const { data, reload } = useData<Approval[]>("/api/approvals?pending=false");
  const { actor } = useActor();
  const groups = group(data || []);
  const open = groups.filter((g) => g.items.some((a) => !a.decision) && !g.items.some((a) => a.decision === "rejected" && g.kind === "bank_change"));
  const done = groups.filter((g) => !open.includes(g)).slice(0, 8);
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Approvals</h1>
        <p className="text-sm text-slate-500">
          Only what the agent could not settle on its own. You are acting as <b>{actor.user}</b> ({ROLE_LABEL[actor.role]}); each card tells you who can decide it.
        </p>
      </div>
      <Card pad={false} title={`Waiting for a person (${open.length})`}>
        {!data ? (
          <Empty>Loading...</Empty>
        ) : open.length === 0 ? (
          <Empty>Nothing waiting for a person. Load the demo inbox from the Invoices page to see some.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {open.map((g) => {
              const a = g.items[0];
              const inv = a.invoice;
              return (
                <li key={g.key} className="space-y-2 px-4 py-4">
                  <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                    {g.kind === "bank_change" ? <Landmark className="h-4 w-4 text-rose-600" /> : <ShieldCheck className="h-4 w-4 text-indigo-600" />}
                    {g.kind === "bank_change" ? `Bank change for ${a.bank_change?.vendor}` : `Pay ${inv?.vendor_name} ${money(inv && inv.recover_amount ? inv.total! - inv.recover_amount : inv?.total)}`}
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-normal text-slate-600">
                      {g.kind === "bank_change" ? "callback + two people" : `needs ${ROLE_LABEL[a.required_role]}`}
                    </span>
                    {g.kind === "payment" && inv && inv.recover_amount > 0 && (
                      <span className="text-xs font-normal text-sky-700">
                        invoice {money(inv.total)} less {money(inv.recover_amount)} owed under contract
                      </span>
                    )}
                  </div>
                  <InvoiceLine a={a} />
                  <div className="max-w-3xl">
                    {g.kind === "bank_change" && a.bank_change ? (
                      <BankChangeReview approvals={g.items} change={a.bank_change} onDone={reload} />
                    ) : (
                      <PaymentApproval a={a} onDone={reload} />
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
      {done.length > 0 && (
        <Card pad={false} title="Recently decided">
          <ul className="divide-y divide-slate-50">
            {done.map((g) => {
              const a = g.items[g.items.length - 1];
              return (
                <li key={g.key} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-[13px]">
                  <span>
                    {g.kind === "bank_change" ? `Bank change, ${a.bank_change?.vendor}` : `Payment, ${a.invoice?.vendor_name} ${money(a.invoice?.total)}`}
                  </span>
                  <span className="text-xs text-slate-500">
                    {g.items.map((x) => `${x.decision} by ${x.decided_by}`).join(" · ")}
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>
      )}
    </div>
  );
}
