"use client";

import Link from "next/link";
import { useState } from "react";
import { Download, Landmark, RefreshCw } from "lucide-react";
import { api, money, useActor, useData } from "@/lib/api";
import { Button, Card, Empty, Mono, Stat, cx } from "@/components/ui";
import { useFeedback } from "@/components/Feedback";
import { canApprove, personFor } from "@/lib/api";

type Item = { payment_id: number; invoice_id: string; number: string; vendor: string; decision: "pay" | "defer"; amount: string; discount: string; pay: string; due: string; reason: string };
type Run = {
  id: number;
  run_date: string;
  status: string;
  cash_before: number;
  cash_floor: number;
  total: number;
  discounts: number;
  plan: { items: Item[]; cash_after: string; horizon: string };
  proposed_by: string;
  approved_by: string | null;
};
type Payments = { cash: number; floor: number; horizon_days: number; runs: Run[] };
type Payment = { id: number; gross: number | null; deductions: number; discount: number; amount: number; scheduled_for: string; status: string; invoice_id: string; vendor: string; number: string; run_id: number | null; pay_to_account: string };

function RunCard({ run, reload }: { run: Run; reload: () => void }) {
  const { actor, setActor } = useActor();
  const fb = useFeedback();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const approve = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api(`/api/payment-runs/${run.id}/approve`, { method: "POST", json: actor });
      fb.toast("success", `Run ${run.id} approved`, "Payments are released; the bank file is ready to download.");
      reload();
    } catch (e) {
      const msg = (e as Error).message;
      if (/out of date|no proposed run/.test(msg)) {
        fb.toast("info", "The run changed while you were looking", "New payments were scheduled, so the agent re-planned. Review the updated run.");
        reload();
      } else {
        setErr(msg);
        fb.toast("error", "Could not approve the run", msg);
      }
    } finally {
      setBusy(false);
    }
  };
  const pay = run.plan.items.filter((i) => i.decision === "pay");
  const defer = run.plan.items.filter((i) => i.decision === "defer");
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Landmark className="h-4 w-4 text-slate-500" /> Payment run {run.id} · {run.run_date}
          <span className={cx("rounded-full px-2 py-0.5 text-[11px] font-medium ring-1", run.status === "approved" ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-indigo-50 text-indigo-700 ring-indigo-200")}>
            {run.status === "approved" ? `approved by ${run.approved_by}` : "proposed by the agent"}
          </span>
        </span>
      }
      action={
        run.status === "approved" ? (
          <a href={`/api/payment-runs/${run.id}/bank-file`} className="inline-flex items-center gap-1.5 rounded-lg bg-white px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50">
            <Download className="h-3.5 w-3.5" /> Bank file (CSV)
          </a>
        ) : canApprove(actor.role, "controller") ? (
          <Button size="sm" variant="good" onClick={approve} disabled={busy}>
            Approve run as {actor.user}
          </Button>
        ) : (
          <Button size="sm" onClick={() => setActor(personFor("controller"))}>
            Act as {personFor("controller").user} (Controller) to approve
          </Button>
        )
      }
      pad={false}
    >
      <div className="grid grid-cols-2 gap-px border-b border-slate-100 bg-slate-100 md:grid-cols-4">
        {[
          ["Cash before", money(run.cash_before)],
          ["Paid in this run", money(run.total)],
          ["Discounts captured", money(run.discounts)],
          ["Cash after (floor " + money(run.cash_floor) + ")", money(Number(run.plan.cash_after))],
        ].map(([k, v]) => (
          <div key={k} className="bg-white px-4 py-2.5">
            <div className="text-[11px] uppercase tracking-wide text-slate-500">{k}</div>
            <div className="text-lg font-semibold tabular-nums">{v}</div>
          </div>
        ))}
      </div>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-500">
            <th className="px-4 py-2 font-medium">Invoice</th>
            <th className="px-2 py-2 font-medium">Decision</th>
            <th className="px-2 py-2 text-right font-medium">Net owed</th>
            <th className="px-2 py-2 text-right font-medium">Discount</th>
            <th className="px-2 py-2 text-right font-medium">Pay now</th>
            <th className="px-4 py-2 font-medium">Why</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {[...pay, ...defer].map((i) => (
            <tr key={i.payment_id} className={cx(i.decision === "defer" && "text-slate-500")}>
              <td className="px-4 py-2">
                <Link href={`/invoices/${i.invoice_id}`} className="font-medium hover:underline">
                  {i.vendor}
                </Link>
                <div><Mono className="text-slate-500">{i.number}</Mono></div>
              </td>
              <td className="px-2 py-2">
                <span className={cx("rounded px-1.5 py-0.5 text-[11px] font-medium", i.decision === "pay" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600")}>
                  {i.decision === "pay" ? "pay now" : "later"}
                </span>
              </td>
              <td className="px-2 py-2 text-right tabular-nums">{money(Number(i.amount))}</td>
              <td className="px-2 py-2 text-right tabular-nums text-emerald-700">{Number(i.discount) ? `-${money(Number(i.discount))}` : ""}</td>
              <td className="px-2 py-2 text-right font-medium tabular-nums">{i.decision === "pay" ? money(Number(i.pay)) : ""}</td>
              <td className="px-4 py-2 text-xs">{i.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {err && <div className="border-t border-rose-100 bg-rose-50 px-4 py-2 text-xs text-rose-700">{err}</div>}
    </Card>
  );
}

export default function PaymentsPage() {
  const { data, reload } = useData<Payments>("/api/payment-runs");
  const { data: payments } = useData<Payment[]>("/api/payments");
  const { actor } = useActor();
  const [busy, setBusy] = useState(false);
  const fb = useFeedback();
  const replan = async () => {
    setBusy(true);
    try {
      const r = await api<{ id: number | null }>("/api/payment-runs/plan", { method: "POST", json: actor });
      fb.toast("success", r.id ? `Run ${r.id} planned` : "Nothing to pay", r.id ? "Review it below." : "No approved invoices are waiting.");
      reload();
    } finally {
      setBusy(false);
    }
  };
  const released = (payments || []).filter((p) => p.status === "released");
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Payment runs</h1>
          <p className="max-w-3xl text-sm text-slate-500">
            When to pay is a decision too. The agent pays everything due in the next {data?.horizon_days ?? 7} days, then spends cash above the floor on early-payment discounts, best annual return first, and keeps the rest in the bank until it is due. The controller approves the run.
          </p>
        </div>
        <Button onClick={replan} disabled={busy}>
          <RefreshCw className="h-4 w-4" /> Plan a run now
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Operating cash" value={data ? money(data.cash) : "-"} />
        <Stat label="Cash floor" value={data ? money(data.floor) : "-"} sub="never paid below" />
        <Stat label="Contract deductions" value={money((payments || []).reduce((a, p) => a + Number(p.deductions || 0), 0))} sub="kept, with remittance advice" tone="brand" />
        <Stat label="Discounts captured" value={money((payments || []).reduce((a, p) => a + Number(p.discount || 0), 0))} sub="by paying early" tone="good" />
      </div>
      {!data ? <Empty>Loading...</Empty> : data.runs.length === 0 ? <Empty>No payments waiting. Runs are planned as invoices clear.</Empty> : data.runs.map((r) => <RunCard key={r.id} run={r} reload={reload} />)}
      {released.length > 0 && (
        <Card title="Released payments" pad={false}>
          <table className="w-full text-[13px]">
            <tbody className="divide-y divide-slate-50">
              {released.map((p) => (
                <tr key={p.id}>
                  <td className="px-4 py-2">{p.vendor} <Mono className="text-slate-500">{p.number}</Mono></td>
                  <td className="px-2 py-2 text-right tabular-nums text-slate-500">{money(p.gross)}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-sky-700">{p.deductions ? `-${money(p.deductions)}` : ""}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-emerald-700">{p.discount ? `-${money(p.discount)}` : ""}</td>
                  <td className="px-2 py-2 text-right font-medium tabular-nums">{money(p.amount)}</td>
                  <td className="px-4 py-2 text-right text-xs text-slate-500">run {p.run_id} · {p.scheduled_for} · to <Mono>•••• {p.pay_to_account.replace(/\s/g, "").slice(-4)}</Mono></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
