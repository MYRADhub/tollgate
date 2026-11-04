"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { Bot, FileUp, HandCoins, Mail, RotateCcw, Scale, ShieldAlert, User } from "lucide-react";
import { AuditEvent, InvoiceRow, Stats, ago, api, compactMoney, money, useData, useLive } from "@/lib/api";
import { useFeedback } from "@/components/Feedback";
import { Tour } from "@/components/Tour";
import { Button, Card, Empty, Flag, Stat, StatusPill, cx } from "@/components/ui";

const FILTERS: { key: string; label: string; statuses?: string[] }[] = [
  { key: "all", label: "All" },
  { key: "attention", label: "Needs a person", statuses: ["on_hold", "awaiting_approval"] },
  { key: "vendor", label: "Waiting on vendor", statuses: ["awaiting_vendor"] },
  { key: "paid", label: "Scheduled", statuses: ["scheduled", "paid"] },
  { key: "rejected", label: "Rejected", statuses: ["rejected", "superseded"] },
];

function Flags({ r }: { r: InvoiceRow }) {
  if (!r.flags.length && !r.recover.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {r.flags.map((c) => (
        <Flag key={c} code={c} />
      ))}
      {r.recover.map((c) => (
        <Flag key={c} code={c} severity="recover" />
      ))}
    </div>
  );
}

function ActivityFeed() {
  const { last } = useLive();
  const { data } = useData<AuditEvent[]>("/api/audit?limit=40&scope=main");
  const merged = [...last.filter((e) => !e.lab), ...(data || [])]
    .filter((e, i, arr) => arr.findIndex((x) => x.id === e.id) === i)
    .sort((a, b) => b.id - a.id)
    .slice(0, 40);
  const icon = (e: AuditEvent) => {
    if (e.actor === "policy" || e.kind === "injection_detected") return <ShieldAlert className="h-3.5 w-3.5 text-rose-600" />;
    if (e.actor === "critic") return <Scale className="h-3.5 w-3.5 text-amber-600" />;
    if (e.kind === "checked" && /recovery/.test(e.summary)) return <HandCoins className="h-3.5 w-3.5 text-sky-600" />;
    if (e.actor === "agent" || e.actor === "controls") return <Bot className="h-3.5 w-3.5 text-indigo-600" />;
    if (e.actor.startsWith("email:")) return <Mail className="h-3.5 w-3.5 text-amber-600" />;
    return <User className="h-3.5 w-3.5 text-slate-500" />;
  };
  return (
    <Card
      title="Agent activity"
      action={
        <span className="flex items-center gap-1.5 text-[11px] text-emerald-600">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
          live
        </span>
      }
      pad={false}
    >
      <ol className="max-h-[640px] divide-y divide-slate-50 overflow-y-auto">
        {merged.length === 0 && <Empty>Quiet. The agent is watching the AP inbox.</Empty>}
        {merged.map((e) => {
          const inner = (
            <>
              <div className="mt-0.5">{icon(e)}</div>
              <div className="min-w-0 flex-1">
                {e.number && (
                  <div className="truncate text-[11px] font-medium text-slate-500">
                    {e.vendor} · <span className="font-mono">{e.number}</span>
                  </div>
                )}
                <div className={cx("line-clamp-3 text-[12.5px] leading-snug", e.actor === "policy" ? "font-medium text-rose-700" : "text-slate-700")}>{e.summary}</div>
                <div className="text-[11px] text-slate-400">
                  {e.actor} · {ago(e.created_at)}
                </div>
              </div>
            </>
          );
          return (
            <li key={e.id}>
              {e.invoice_id ? (
                <Link href={`/invoices/${e.invoice_id}`} className="flex gap-2.5 px-4 py-2 hover:bg-slate-50">
                  {inner}
                </Link>
              ) : (
                <div className="flex gap-2.5 px-4 py-2">{inner}</div>
              )}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

export default function InvoicesPage() {
  const fb = useFeedback();
  const [filter, setFilter] = useState("all");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const f = FILTERS.find((x) => x.key === filter)!;
  const { data: rows, reload } = useData<InvoiceRow[]>(`/api/invoices${f.statuses ? `?status=${f.statuses.join(",")}` : ""}`);
  const { data: all, reload: reloadAll } = useData<InvoiceRow[]>("/api/invoices");
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
      fb.toast("success", `${files.length} invoice${files.length > 1 ? "s" : ""} received`, "The agent is reading it now.");
      reload();
    } catch (e) {
      fb.toast("error", "Upload failed", (e as Error).message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const reset = async () => {
    const ok = await fb.confirm({
      title: "Reset the demo company?",
      body: "Clears every invoice, email, approval, payment run and lab attempt, and restores the vendors, POs and contracts.",
      confirmLabel: "Reset",
      danger: true,
    });
    if (!ok) return;
    await api("/api/demo/reset", { method: "POST" });
    try {
      localStorage.removeItem("tollgate.seen");
    } catch {}
    location.reload();
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">The AP agent that pays for itself</h1>
          <p className="max-w-3xl text-sm text-slate-500">
            Tollgate reads every vendor invoice, checks it against POs, receipts, the vendor master and the vendor&apos;s contract, claims what you are owed, and works each exception until it is safe to pay.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={reset}>
            <RotateCcw className="h-3.5 w-3.5" /> Reset demo
          </Button>
          <input ref={fileRef} type="file" accept="application/pdf" multiple hidden onChange={(e) => upload(e.target.files)} />
          <Button onClick={() => fileRef.current?.click()} disabled={uploading}>
            <FileUp className="h-4 w-4" /> {uploading ? "Uploading..." : "Upload invoice PDF"}
          </Button>
        </div>
      </div>

      <Tour
        rows={all}
        onLoaded={() => {
          reload();
          reloadAll();
        }}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat
          label="Recovered for you"
          value={stats ? compactMoney(stats.recovered + stats.discounts) : "-"}
          sub={stats ? `${money(stats.recovered)} under contracts · ${money(stats.discounts)} discounts` : undefined}
          tone="brand"
        />
        <Stat label="Wrong payments stopped" value={stats ? compactMoney(stats.prevented) : "-"} sub={stats ? `${stats.caught.length} invoices held or rejected` : undefined} tone="bad" />
        <Stat label="Paid with no human touch" value={stats ? `${stats.touchless} of ${stats.decided}` : "-"} sub="invoices decided" />
        <Stat label="Scheduled to pay" value={stats ? compactMoney(stats.scheduled_total) : "-"} sub="to verified accounts only" tone="good" />
        <Stat
          label="Waiting on a person"
          value={stats?.pending_approvals ?? "-"}
          sub={
            <Link href="/approvals" className="text-indigo-600 hover:underline">
              Open approvals
            </Link>
          }
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_380px]">
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
            <div className="space-y-2 p-4">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-100" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <Empty>
              {filter === "all" ? (
                <>
                  No invoices yet. Use <b>Load the demo inbox</b> in the guided demo above, or upload a PDF.
                </>
              ) : (
                "Nothing here right now."
              )}
            </Empty>
          ) : (
            <>
              <table className="hidden w-full text-sm md:table">
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
                      <td className="max-w-[230px] px-4 py-2.5">
                        <Link href={`/invoices/${r.id}`} className="block">
                          <div className="truncate font-medium text-slate-900 group-hover:text-indigo-700">{r.vendor_name || r.file_name}</div>
                          <div className="truncate font-mono text-[11px] text-slate-500">
                            {r.number || "reading..."} {r.po_number && <>· {r.po_number}</>}
                          </div>
                        </Link>
                      </td>
                      <td className="whitespace-nowrap px-2 py-2.5 text-right tabular-nums">
                        {money(r.total, r.currency || "USD")}
                        {r.recover_amount > 0 && <div className="text-[11px] text-sky-700">-{money(r.recover_amount)} owed</div>}
                      </td>
                      <td className="px-2 py-2.5">
                        <StatusPill status={r.status} />
                      </td>
                      <td className="max-w-[420px] px-2 py-2.5">
                        <Flags r={r} />
                        <div className="mt-1 line-clamp-2 text-xs text-slate-500">{r.summary}</div>
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right text-xs text-slate-500">{ago(r.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ul className="divide-y divide-slate-100 md:hidden">
                {rows.map((r) => (
                  <li key={r.id}>
                    <Link href={`/invoices/${r.id}`} className="block space-y-1.5 px-4 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate font-medium text-slate-900">{r.vendor_name || r.file_name}</div>
                          <div className="font-mono text-[11px] text-slate-500">{r.number}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-sm tabular-nums">{money(r.total, r.currency || "USD")}</div>
                          <StatusPill status={r.status} />
                        </div>
                      </div>
                      <Flags r={r} />
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
        <ActivityFeed />
      </div>
    </div>
  );
}
