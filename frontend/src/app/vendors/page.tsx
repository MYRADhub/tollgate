"use client";

import { useData, money } from "@/lib/api";
import { Card, Empty, Mono, cx } from "@/components/ui";

type V = { id: string; name: string; email: string; tax_id: string; bank_name: string; bank_account: string; bank_verified_at: string | null; payment_terms_days: number; status: string; invoices: number; exceptions: number };
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
