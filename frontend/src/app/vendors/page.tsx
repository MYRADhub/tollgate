"use client";

import Link from "next/link";
import { useState } from "react";
import { api, useData, money } from "@/lib/api";
import { useFeedback } from "@/components/Feedback";
import { Fingerprint } from "lucide-react";
import { Button, Card, Empty, Mono, cx } from "@/components/ui";

function BillingSwitch() {
  const fb = useFeedback();
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<Record<number, string>>({});
  const send = async (step: number) => {
    setBusy(true);
    try {
      const r = await api<{ id: string; number: string }>(`/api/demo/billing-switch/${step}`, { method: "POST" });
      setSent((x) => ({ ...x, [step]: r.id }));
      fb.toast("info", `Polaris sent ${r.number}`, step === 1 ? "Open it: the fingerprint will not recognise the new layout." : "If a controller confirmed the first one, this one should pass.");
    } catch (e) {
      fb.toast("error", "Could not send", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mx-4 mb-4 mt-3 rounded-lg bg-indigo-50/60 p-3 text-[12.5px] text-slate-700 ring-1 ring-indigo-100">
      <div className="font-medium text-slate-900">Try it: the model learns from your team</div>
      <p className="mt-0.5">
        Vendors do change billing systems. Polaris has just moved from NetSuite to Zuora, so its next invoice looks nothing like the last forty. The model holds it. A controller calls Polaris on the
        number on file, confirms it, and clears the finding: the model learns the new layout as a second one, and Polaris&apos;s next invoice passes. Every other layout is still checked against the usual one.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => send(1)} disabled={busy}>1. Polaris sends its first Zuora invoice</Button>
        {sent[1] && <Link href={`/invoices/${sent[1]}`} className="text-indigo-600 hover:underline">open it, then clear the finding as Rosa Kim</Link>}
        <Button size="sm" onClick={() => send(2)} disabled={busy}>2. Polaris sends the next one</Button>
        {sent[2] && <Link href={`/invoices/${sent[2]}`} className="text-indigo-600 hover:underline">open it</Link>}
      </div>
    </div>
  );
}

type Learned = { label: string; confirmed: { by: string; invoice: string; at: string }[] };
type FP = { learned_layouts?: Learned[]; trained_on: number; holdout_genuine: number; false_alarms: number; caught: number; forged_total: number; producer: string; fonts: string; forgeries: Record<string, { caught: number; of: number }> };
type V = { id: string; name: string; email: string; tax_id: string; bank_name: string; bank_account: string; bank_verified_at: string | null; payment_terms_days: number; status: string; invoices: number; exceptions: number; fingerprint: FP | null };
type PO = { number: string; vendor: string; department: string; budget_owner_name: string; status: string; issued_on: string; total: number; lines: { sku: string; description: string; quantity: number; unit_price: number; received: number }[] };

export default function VendorsPage() {
  const { data: vendors } = useData<V[]>("/api/vendors");
  const { data: pos } = useData<PO[]>("/api/purchase-orders");
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Vendors and purchase orders</h1>
        <p className="text-sm text-slate-500">The system of record the agent checks every invoice against. Bank accounts here change only through a callback and two approvers.</p>
      </div>
      <Card title="Vendor master" pad={false}>
        {!vendors ? <Empty>Loading...</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-2 font-medium">Vendor</th>
                  <th className="px-2 py-2 font-medium">Contact on file</th>
                  <th className="px-2 py-2 font-medium">Verified bank account</th>
                  <th className="px-2 py-2 font-medium">Terms</th>
                  <th className="px-4 py-2 text-right font-medium">Invoices / exceptions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {vendors.map((v) => (
                  <tr key={v.id}>
                    <td className="px-4 py-2"><div className="font-medium">{v.name}</div><Mono className="text-slate-500">{v.tax_id}</Mono></td>
                    <td className="px-2 py-2 text-slate-600">{v.email}</td>
                    <td className="px-2 py-2"><Mono>{v.bank_account}</Mono><div className="text-[11px] text-slate-500">{v.bank_name} · verified {v.bank_verified_at ? new Date(v.bank_verified_at).toLocaleDateString() : "never"}</div></td>
                    <td className="px-2 py-2">net {v.payment_terms_days}</td>
                    <td className="px-4 py-2 text-right tabular-nums">{v.invoices} / <span className={cx(v.exceptions ? "text-rose-700" : "text-slate-500")}>{v.exceptions}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {vendors && vendors.some((v) => v.fingerprint) && (
        <Card title={<span className="flex items-center gap-1.5"><Fingerprint className="h-4 w-4 text-indigo-600" /> Document fingerprints: Tollgate&apos;s own model</span>} pad={false}>
          <p className="px-4 pt-3 text-[12.5px] leading-relaxed text-slate-600">
            One model per vendor, trained on that vendor&apos;s past invoices. It learns how their billing system makes a PDF: the software, the fonts, where every label sits,
            the line spacing. An invoice rebuilt in a word processor, made from someone else&apos;s template, or edited to change a number does not match, even when every field is right.
            Tested on held-out invoices the model never saw and on forgeries of four kinds. In this demo each vendor&apos;s archive is generated; in production it is the vendor&apos;s real invoice history.
          </p>
          <div className="overflow-x-auto">
            <table className="mt-2 w-full text-[12.5px]">
              <thead>
                <tr className="border-y border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-2 font-medium">Vendor</th>
                  <th className="px-2 py-2 font-medium">Their billing system</th>
                  <th className="px-2 py-2 font-medium">Fonts</th>
                  <th className="px-2 py-2 text-right font-medium">Trained on</th>
                  <th className="px-2 py-2 text-right font-medium">False alarms</th>
                  <th className="px-2 py-2 text-right font-medium">Forgeries caught</th>
                  <th className="px-4 py-2 font-medium">Learned from your team</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {vendors.filter((v) => v.fingerprint).map((v) => {
                  const f = v.fingerprint!;
                  return (
                    <tr key={v.id}>
                      <td className="px-4 py-1.5 font-medium">{v.name}</td>
                      <td className="px-2 py-1.5 text-slate-600">{f.producer}</td>
                      <td className="px-2 py-1.5 text-slate-600">{f.fonts.replace(/\+/g, ", ")}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{f.trained_on} invoices</td>
                      <td className={cx("px-2 py-1.5 text-right tabular-nums", f.false_alarms ? "text-rose-700" : "text-emerald-700")}>{f.false_alarms} of {f.holdout_genuine}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums" title={Object.entries(f.forgeries).map(([k, x]) => `${k}: ${x.caught}/${x.of}`).join("\n")}>
                        {f.caught} of {f.forged_total}
                      </td>
                      <td className="px-4 py-1.5 text-slate-600">
                        {f.learned_layouts?.length
                          ? f.learned_layouts.map((l) => `${l.label}, confirmed by ${[...new Set(l.confirmed.map((c) => c.by))].join(", ")} (${l.confirmed.map((c) => c.invoice).join(", ")})`).join("; ")
                          : <span className="text-slate-400">nothing yet</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <BillingSwitch />
        </Card>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {pos?.map((p) => (
          <Card key={p.number} title={<span><Mono>{p.number}</Mono> · {p.vendor}</span>} action={<span className="text-xs text-slate-500">{p.department} · {p.budget_owner_name}</span>} pad={false}>
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-1.5 font-medium">Item</th>
                  <th className="px-2 py-1.5 text-right font-medium">Ordered</th>
                  <th className="px-2 py-1.5 text-right font-medium">Received</th>
                  <th className="px-4 py-1.5 text-right font-medium">Unit price</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {p.lines.map((l) => (
                  <tr key={l.sku}>
                    <td className="px-4 py-1.5">{l.description} <Mono className="text-slate-400">{l.sku}</Mono></td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{l.quantity}</td>
                    <td className={cx("px-2 py-1.5 text-right tabular-nums", l.received < l.quantity && "font-medium text-amber-700")}>{l.received}</td>
                    <td className="px-4 py-1.5 text-right tabular-nums">{money(l.unit_price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="border-t border-slate-100 px-4 py-1.5 text-right text-xs text-slate-500">PO total {money(p.total)}</div>
          </Card>
        ))}
      </div>
    </div>
  );
}
