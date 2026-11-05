"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, ChevronDown, ChevronUp, Compass, Inbox } from "lucide-react";
import { InvoiceRow, api, useData, useSeen } from "@/lib/api";
import { useFeedback } from "./Feedback";
import { Button, cx } from "./ui";

type Runs = { runs: { status: string }[] };
type Statements = { statements: unknown[] };

export function Tour({ rows, onLoaded }: { rows: InvoiceRow[] | null; onLoaded: () => void }) {
  const fb = useFeedback();
  const seen = useSeen();
  const { data: runs } = useData<Runs>("/api/payment-runs");
  const { data: statements } = useData<Statements>("/api/statements");
  const [open, setOpen] = useState(true);
  const [busy, setBusy] = useState(false);
  const by = (n: string) => rows?.find((r) => r.number === n);
  const link = (n: string) => (by(n) ? `/invoices/${by(n)!.id}` : null);

  const load = async () => {
    setBusy(true);
    try {
      await api("/api/demo/inbox", { method: "POST", json: null });
      fb.toast("info", "Twelve invoices are in the AP inbox", "Watch the briefing: the batch takes under a minute, and the agent starts asking colleagues about the exceptions.");
      onLoaded();
    } catch (e) {
      fb.toast("error", "Could not load the inbox", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const steps = [
    { title: "Send this week's invoices to the agent", hint: "Twelve invoices from seven vendors, each a different case.", done: (rows?.length || 0) > 0, href: null as string | null, action: true },
    { title: "Watch it clear exceptions by asking around", hint: "GE-5570 has no PO number: it finds the PO, Marcus confirms, it pays. Takes about a minute.", done: by("GE-5570")?.status === "scheduled" && seen.has("GE-5570"), href: link("GE-5570") },
    { title: "Fast-forward a day", hint: "Top right. GE-5561's backordered breakers arrive overnight and the agent pays it.", done: by("GE-5561")?.status === "scheduled", href: link("GE-5561") },
    { title: "See money it recovered under a contract", hint: "Polaris had an outage; the SLA clause makes it owe $975.", done: seen.has("PNS-55120"), href: link("PNS-55120") },
    { title: "Find the instruction hidden for the AI", hint: "White, 1.5pt text in the PDF. Open the Document tab.", done: seen.has("BIS-2090"), href: link("BIS-2090") },
    { title: "Approve a payment as the controller", hint: "Ostara owes $1,416 back; the critic checked the figure.", done: by("OC-7720")?.status === "scheduled", href: link("OC-7720") },
    { title: "Play the vendor who overbilled", hint: "Reply with a corrected invoice and watch it get paid.", done: by("BIS-2077")?.status === "superseded", href: link("BIS-2077") },
    { title: "Reconcile the vendors' statements", hint: "Brightline's own statement does not list BIS-2090. Claim Kestrel's $320 credit.", done: (statements?.statements.length || 0) > 0, href: (rows?.length || 0) > 0 ? "/statements" : null },
    { title: "Approve the payment run", hint: "It took the discount worth 149% a year.", done: !!runs?.runs.some((r) => r.status === "approved"), href: "/payments" },
  ];
  const doneCount = steps.filter((s) => s.done).length;
  const next = steps.findIndex((s) => !s.done);

  return (
    <section className="rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-white shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <button onClick={() => setOpen((x) => !x)} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <Compass className="h-5 w-5 text-indigo-600" />
        <div className="flex-1">
          <div className="text-sm font-semibold text-slate-900">Guided demo: nine things to try</div>
          <div className="text-xs text-slate-500">
            {doneCount === steps.length ? "All done. Reset the demo to start again." : `${doneCount} of ${steps.length} done. About seven minutes.`}
          </div>
        </div>
        <div className="hidden h-1.5 w-40 overflow-hidden rounded-full bg-indigo-100 sm:block">
          <div className="h-full rounded-full bg-indigo-500 transition-all" style={{ width: `${(doneCount / steps.length) * 100}%` }} />
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
      </button>
      {open && (
        <ol className="grid gap-2 px-4 pb-4 md:grid-cols-2 xl:grid-cols-3">
          {steps.map((s, i) => {
            const isNext = i === next;
            const body = (
              <div
                className={cx(
                  "flex h-full gap-2.5 rounded-lg p-3 ring-1 transition",
                  s.done ? "bg-white/60 ring-slate-200" : isNext ? "bg-white ring-2 ring-indigo-400 shadow-sm" : "bg-white ring-slate-200",
                  !s.done && s.href && "hover:ring-indigo-300",
                )}
              >
                <span
                  className={cx(
                    "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold",
                    s.done ? "bg-emerald-500 text-white" : isNext ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-500",
                  )}
                >
                  {s.done ? <Check className="h-3 w-3" /> : i + 1}
                </span>
                <div className="min-w-0">
                  <div className={cx("text-[13px] font-medium", s.done ? "text-slate-500 line-through decoration-slate-300" : "text-slate-900")}>{s.title}</div>
                  <div className="text-xs text-slate-500">{s.hint}</div>
                  {s.action && !s.done && (
                    <Button size="sm" variant="primary" className="mt-2" onClick={load} disabled={busy}>
                      <Inbox className="h-3.5 w-3.5" /> {busy ? "Sending..." : "Load the demo inbox"}
                    </Button>
                  )}
                  {!s.href && !s.action && !s.done && <div className="mt-1 text-[11px] text-slate-400">Load the inbox first</div>}
                </div>
              </div>
            );
            return (
              <li key={s.title}>
                {s.href && !s.action ? (
                  <Link href={s.href} className="block h-full">
                    {body}
                  </Link>
                ) : (
                  body
                )}
              </li>
            );
          })}
        </ol>
      )}
      {open && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 pb-3 text-xs text-slate-500">
          <span>Also try:</span>
          <Link href="/inquiries" className="text-indigo-600 hover:underline">
            emailing AP as a vendor
          </Link>
          <Link href="/lab" className="text-indigo-600 hover:underline">
            the attack lab, with your own PDF
          </Link>
          <Link href="/contracts" className="text-indigo-600 hover:underline">
            pasting a new contract
          </Link>
          <Link href="/audit" className="text-indigo-600 hover:underline">
            verifying the audit chain
          </Link>
        </div>
      )}
    </section>
  );
}
