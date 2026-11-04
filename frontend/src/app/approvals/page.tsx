"use client";

import Link from "next/link";
import { useState } from "react";
import { Landmark, ShieldCheck } from "lucide-react";
import { Approval, ROLE_LABEL, api, money, useActor, useData } from "@/lib/api";
import { Button, Card, Empty, Flag, Mono } from "@/components/ui";

function Item({ a, reload }: { a: Approval; reload: () => void }) {
  const { actor } = useActor();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [callback, setCallback] = useState("");
  const decide = async (decision: "approved" | "rejected") => {
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/approvals/${a.id}/decide`, { method: "POST", json: { ...actor, decision, callback_note: callback || undefined } });
      reload();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const inv = a.invoice;
  return (
    <li className="px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm font-medium">
            {a.kind === "bank_change" ? <Landmark className="h-4 w-4 text-rose-600" /> : <ShieldCheck className="h-4 w-4 text-indigo-600" />}
            {a.kind === "bank_change" ? `Bank change: ${a.bank_change?.vendor}` : `Pay ${inv?.vendor_name} ${money(inv?.total)}`}
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-normal text-slate-600">needs {ROLE_LABEL[a.required_role]}</span>
          </div>
          <p className="mt-1 text-[13px] text-slate-600">{a.reason}</p>
          {inv && (
            <Link href={`/invoices/${inv.id}`} className="mt-1 inline-flex items-center gap-2 font-mono text-[11px] text-indigo-600 hover:underline">
              {inv.number} · {inv.po_number}
              {inv.flags.map((c) => (
                <Flag key={c} code={c} />
              ))}
            </Link>
          )}
          {a.bank_change && (
            <div className="mt-2 flex flex-wrap gap-4 text-xs">
              <span>
                On file <Mono>{a.bank_change.old_account}</Mono>
              </span>
              <span className="text-rose-700">
                Requested <Mono>{a.bank_change.new_account}</Mono> ({a.bank_change.new_bank_name})
              </span>
              {a.other_approvers && a.other_approvers.length > 0 && <span className="text-slate-500">Already approved by {a.other_approvers.join(", ")}</span>}
            </div>
          )}
          {a.kind === "bank_change" && !a.bank_change?.callback_note && (
            <input
              value={callback}
              onChange={(e) => setCallback(e.target.value)}
              placeholder="Callback record: number dialled from the vendor master, who confirmed"
              className="mt-2 w-full max-w-xl rounded-md border border-slate-300 px-2 py-1.5 text-xs"
            />
          )}
          {err && <div className="mt-2 rounded bg-rose-50 px-2 py-1 text-xs text-rose-700">{err}</div>}
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="good" disabled={busy} onClick={() => decide("approved")}>
            Approve as {actor.user}
          </Button>
          <Button size="sm" variant="danger" disabled={busy} onClick={() => decide("rejected")}>
            Reject
          </Button>
        </div>
      </div>
    </li>
  );
}

export default function ApprovalsPage() {
  const { data, reload } = useData<Approval[]>("/api/approvals");
  const { actor } = useActor();
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Approvals</h1>
        <p className="text-sm text-slate-500">
          Only what the agent could not settle on its own. You are acting as <b>{actor.user}</b> ({ROLE_LABEL[actor.role]}); switch people in the sidebar.
        </p>
      </div>
      <Card pad={false}>
        {!data ? <Empty>Loading...</Empty> : data.length === 0 ? <Empty>Nothing waiting for a person.</Empty> : <ul className="divide-y divide-slate-100">{data.map((a) => <Item key={a.id} a={a} reload={reload} />)}</ul>}
      </Card>
    </div>
  );
}
