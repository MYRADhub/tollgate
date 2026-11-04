"use client";

import Link from "next/link";
import { useState } from "react";
import { Hash, ShieldCheck, ShieldX } from "lucide-react";
import { api, useData } from "@/lib/api";
import { Button, Card, Empty, Mono, cx } from "@/components/ui";

type Ev = { id: number; actor: string; kind: string; summary: string; invoice_id: string | null; created_at: string; hash: string; prev_hash: string };
type Verify = { ok: boolean; broken_at: number | null; events: number; head: string | null };

export default function AuditPage() {
  const { data } = useData<Ev[]>("/api/audit?limit=500");
  const [v, setV] = useState<Verify | null>(null);
  const [checking, setChecking] = useState(false);
  const verify = async () => {
    setChecking(true);
    try {
      setV(await api<Verify>("/api/audit/verify"));
    } finally {
      setChecking(false);
    }
  };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Audit trail</h1>
          <p className="text-sm text-slate-500">Every read, check, plan, policy denial, email and human decision. Each entry&apos;s hash covers the one before it, so an edit anywhere breaks the chain.</p>
        </div>
        <Button variant="primary" onClick={verify} disabled={checking}>
          <Hash className="h-4 w-4" /> Verify chain
        </Button>
      </div>
      {v && (
        <div className={cx("flex items-center gap-2 rounded-xl p-3 text-sm ring-1", v.ok ? "bg-emerald-50 text-emerald-800 ring-emerald-200" : "bg-rose-50 text-rose-800 ring-rose-200")}>
          {v.ok ? <ShieldCheck className="h-4 w-4" /> : <ShieldX className="h-4 w-4" />}
          {v.ok ? `All ${v.events} events verified. Head ${v.head?.slice(0, 16)}...` : `Chain broken at event ${v.broken_at}.`}
        </div>
      )}
      <Card pad={false}>
        {!data ? <Empty>Loading...</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-2 font-medium">#</th>
                  <th className="px-2 py-2 font-medium">When</th>
                  <th className="px-2 py-2 font-medium">Who</th>
                  <th className="px-2 py-2 font-medium">What</th>
                  <th className="px-4 py-2 font-medium">Hash</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {data.map((e) => (
                  <tr key={e.id} className="align-top">
                    <td className="px-4 py-1.5 tabular-nums text-slate-400">{e.id}</td>
                    <td className="whitespace-nowrap px-2 py-1.5 text-slate-500">{new Date(e.created_at).toLocaleTimeString()}</td>
                    <td className={cx("whitespace-nowrap px-2 py-1.5", e.actor === "policy" ? "font-medium text-rose-700" : "text-slate-600")}>{e.actor}</td>
                    <td className="px-2 py-1.5 text-slate-800">
                      {e.invoice_id ? <Link className="hover:underline" href={`/invoices/${e.invoice_id}`}>{e.summary}</Link> : e.summary}
                    </td>
                    <td className="px-4 py-1.5"><Mono className="text-slate-400">{e.hash.slice(0, 12)}</Mono></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
