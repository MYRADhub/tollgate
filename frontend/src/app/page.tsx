"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { Bot, FileUp, Inbox, Mail, RotateCcw, ShieldAlert, User } from "lucide-react";
import { InvoiceRow, Stats, ago, api, compactMoney, money, useData, useLive } from "@/lib/api";
import { Button, Card, Empty, Flag, Stat, StatusPill, cx } from "@/components/ui";

type DemoItem = { index: number; file_name: string; title: string; expectation: string };

const FILTERS: { key: string; label: string; statuses?: string[] }[] = [
  { key: "all", label: "All" },
  { key: "attention", label: "Needs a person", statuses: ["on_hold", "awaiting_approval"] },
  { key: "vendor", label: "Waiting on vendor", statuses: ["awaiting_vendor"] },
  { key: "paid", label: "Scheduled", statuses: ["scheduled", "paid"] },
  { key: "rejected", label: "Rejected", statuses: ["rejected", "superseded"] },
];

function DemoInbox({ onClose }: { onClose: () => void }) {
  const { data } = useData<DemoItem[]>("/api/demo/inbox");
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const send = async (indexes: number[] | null) => {
    setBusy(true);
    try {
      await api("/api/demo/inbox", { method: "POST", json: indexes });
      onClose();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Mail className="h-4 w-4 text-slate-500" /> This week&apos;s AP inbox (demo vendors)
        </span>
      }
      action={
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={onClose}>
            Close
          </Button>
          <Button size="sm" disabled={busy || picked.size === 0} onClick={() => send([...picked])}>
            Send selected
          </Button>
          <Button size="sm" variant="primary" disabled={busy} onClick={() => send(null)}>
            Send all {data?.length ?? ""} to Tollgate
          </Button>
        </div>
      }
      pad={false}
    >
      <ul className="divide-y divide-slate-100">
        {data?.map((d) => (
          <li key={d.index} className="flex items-start gap-3 px-4 py-2.5">
            <input
              type="checkbox"
              className="mt-1"
              checked={picked.has(d.index)}
              onChange={(e) => {
                const n = new Set(picked);
                if (e.target.checked) n.add(d.index);
                else n.delete(d.index);
                setPicked(n);
              }}
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-800">
                {d.title}
                <a className="font-mono text-[11px] font-normal text-indigo-600 hover:underline" href={`/api/demo/inbox/${d.index}/file`}>
                  {d.file_name}
                </a>
              </div>
              <div className="text-xs text-slate-500">{d.expectation}</div>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function ActivityFeed() {
  const { last } = useLive();
  const { data } = useData<{ id: number; actor: string; kind: string; summary: string; invoice_id: string | null; created_at: string }[]>("/api/audit?limit=40");
  const merged = [...last, ...(data || [])].filter((e, i, arr) => arr.findIndex((x) => x.id === e.id) === i).sort((a, b) => b.id - a.id).slice(0, 40);
  const icon = (actor: string, kind: string) => {
    if (actor === "policy") return <ShieldAlert className="h-3.5 w-3.5 text-rose-600" />;
    if (kind === "injection_detected") return <ShieldAlert className="h-3.5 w-3.5 text-rose-600" />;
    if (actor === "agent" || actor === "controls") return <Bot className="h-3.5 w-3.5 text-indigo-600" />;
    if (actor.startsWith("email:")) return <Mail className="h-3.5 w-3.5 text-amber-600" />;
    return <User className="h-3.5 w-3.5 text-slate-500" />;
  };
  return (
    <Card title="Agent activity" action={<span className="flex items-center gap-1.5 text-[11px] text-emerald-600"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />live</span>} pad={false}>
      <ol className="max-h-[560px] divide-y divide-slate-50 overflow-y-auto">
        {merged.length === 0 && <Empty>No activity yet.</Empty>}
        {merged.map((e) => (
          <li key={e.id} className="flex gap-2.5 px-4 py-2">
            <div className="mt-0.5">{icon(e.actor, e.kind)}</div>
            <div className="min-w-0 flex-1">
              <div className={cx("text-[12.5px] leading-snug", e.actor === "policy" ? "font-medium text-rose-700" : "text-slate-700")}>
                {e.invoice_id ? (
                  <Link href={`/invoices/${e.invoice_id}`} className="hover:underline">
                    {e.summary}
                  </Link>
                ) : (
                  e.summary
                )}
              </div>
              <div className="text-[11px] text-slate-400">
                {e.actor} · {ago(e.created_at)}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export default function InvoicesPage() {
  const [filter, setFilter] = useState("all");
  const [showDemo, setShowDemo] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const f = FILTERS.find((x) => x.key === filter)!;
  const { data: rows } = useData<InvoiceRow[]>(`/api/invoices${f.statuses ? `?status=${f.statuses.join(",")}` : ""}`);
  const { data: stats } = useData<Stats>("/api/stats");

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", file);
        await api("/api/invoices", { method: "POST", body: fd });
      }
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const reset = async () => {
    if (!confirm("Reset the demo company? All invoices, emails and approvals are cleared.")) return;
    await api("/api/demo/reset", { method: "POST" });
    location.reload();
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Every invoice earns its payment</h1>
          <p className="text-sm text-slate-500">Tollgate reads each invoice, checks it against POs, receipts and the vendor master, and works the exceptions until it is safe to pay.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={reset}>
            <RotateCcw className="h-3.5 w-3.5" /> Reset demo
          </Button>
          <input ref={fileRef} type="file" accept="application/pdf" multiple hidden onChange={(e) => upload(e.target.files)} />
          <Button onClick={() => fileRef.current?.click()} disabled={uploading}>
            <FileUp className="h-4 w-4" /> {uploading ? "Uploading..." : "Upload invoice PDF"}
          </Button>
          <Button variant="primary" onClick={() => setShowDemo((x) => !x)}>
            <Inbox className="h-4 w-4" /> Demo inbox
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Stat label="Invoices processed" value={stats?.decided ?? "-"} sub={stats ? `${stats.invoices} received${stats.queue ? `, ${stats.queue} in progress` : ""}` : undefined} />
        <Stat label="Paid with no human touch" value={stats ? `${Math.round(stats.touchless_rate * 100)}%` : "-"} sub={stats ? `${stats.touchless} clean invoices` : undefined} tone="brand" />
        <Stat label="Wrong payments stopped" value={stats ? compactMoney(stats.prevented) : "-"} sub={stats ? `${stats.caught.length} invoices held or rejected` : undefined} tone="bad" />
        <Stat label="Recovered under contracts" value={stats ? compactMoney(stats.recovered + stats.discounts) : "-"} sub={stats ? `${money(stats.recovered)} owed back · ${money(stats.discounts)} discounts` : undefined} tone="brand" />
        <Stat label="Scheduled to pay" value={stats ? compactMoney(stats.scheduled_total) : "-"} sub="to verified accounts only" tone="good" />
        <Stat label="Waiting on a person" value={stats?.pending_approvals ?? "-"} sub="approvals pending" />
      </div>

      {showDemo && <DemoInbox onClose={() => setShowDemo(false)} />}

      <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
        <Card
          pad={false}
          title={
            <div className="flex flex-wrap gap-1">
              {FILTERS.map((x) => (
                <button
                  key={x.key}
                  onClick={() => setFilter(x.key)}
                  className={cx("rounded-md px-2 py-1 text-xs font-medium", filter === x.key ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100")}
                >
                  {x.label}
                </button>
              ))}
            </div>
          }
        >
          {!rows ? (
            <Empty>Loading...</Empty>
          ) : rows.length === 0 ? (
            <Empty>
              No invoices yet. Open the <b>Demo inbox</b> to send this week&apos;s vendor invoices, or upload a PDF.
            </Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-500">
                    <th className="px-4 py-2 font-medium">Vendor / invoice</th>
                    <th className="px-2 py-2 text-right font-medium">Amount</th>
                    <th className="px-2 py-2 font-medium">Status</th>
                    <th className="px-2 py-2 font-medium">What the agent found</th>
                    <th className="px-4 py-2 text-right font-medium">Received</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {rows.map((r) => (
                    <tr key={r.id} className={cx("group align-top hover:bg-slate-50/80", r.status === "superseded" && "opacity-60")}>
                      <td className="px-4 py-2.5">
                        <Link href={`/invoices/${r.id}`} className="block">
                          <div className="font-medium text-slate-900 group-hover:text-indigo-700">{r.vendor_name || r.file_name}</div>
                          <div className="font-mono text-[11px] text-slate-500">
                            {r.number || "reading..."} {r.po_number && <>· {r.po_number}</>}
                          </div>
                        </Link>
                      </td>
                      <td className="px-2 py-2.5 text-right tabular-nums">{money(r.total, r.currency || "USD")}</td>
                      <td className="px-2 py-2.5">
                        <StatusPill status={r.status} />
                      </td>
                      <td className="max-w-[420px] px-2 py-2.5">
                        {(r.flags.length > 0 || r.recover.length > 0) && (
                          <div className="mb-1 flex flex-wrap gap-1">
                            {r.flags.map((c) => (
                              <Flag key={c} code={c} />
                            ))}
                            {r.recover.map((c) => (
                              <Flag key={c} code={c} severity="recover" />
                            ))}
                          </div>
                        )}
                        <div className="line-clamp-2 text-xs text-slate-500">{r.summary}</div>
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right text-xs text-slate-500">{ago(r.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <ActivityFeed />
      </div>
    </div>
  );
}
