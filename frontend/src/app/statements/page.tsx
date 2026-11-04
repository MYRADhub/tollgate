"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { CheckCircle2, FileSpreadsheet, FileUp, Mail, Scale } from "lucide-react";
import { api, canApprove, money, personFor, useActor, useData } from "@/lib/api";
import { Button, Card, Empty, Mono, cx } from "@/components/ui";
import { useFeedback } from "@/components/Feedback";

type Item = {
  kind: string;
  reference: string;
  statement_amount: string | null;
  our_amount: string | null;
  invoice_id: string | null;
  effect: string;
  text: string;
  credit_id?: number | null;
  credit_status?: string;
};
type StatementRow = {
  id: number;
  vendor: string | null;
  vendor_name_raw: string | null;
  file_name: string;
  statement_date: string | null;
  status: string;
  extraction: { method?: string; adds_up?: boolean; lines?: { grounded: boolean }[] } | null;
  result: { vendor_balance: string; our_balance: string; difference: string; explained: string; unexplained: string; items: Item[]; emailed?: string } | null;
};
type Data = { statements: StatementRow[]; pending: number };
type Demo = { index: number; title: string; expectation: string };

const KIND: Record<string, { label: string; tone: string }> = {
  matched: { label: "Agrees", tone: "bg-slate-100 text-slate-600" },
  missing: { label: "Never received", tone: "bg-amber-50 text-amber-800" },
  unapplied_payment: { label: "Paid; they did not apply it", tone: "bg-sky-50 text-sky-800" },
  disputed: { label: "We do not owe this", tone: "bg-slate-100 text-slate-700" },
  corrected: { label: "Replaced by a corrected invoice", tone: "bg-slate-100 text-slate-700" },
  amount_differs: { label: "Amount differs", tone: "bg-amber-50 text-amber-800" },
  credit: { label: "Credit owed to us", tone: "bg-emerald-50 text-emerald-800" },
  not_on_statement: { label: "Not on their statement", tone: "bg-rose-50 text-rose-700" },
  unknown_payment: { label: "Payment we did not make", tone: "bg-rose-50 text-rose-700" },
};
const ORDER = ["not_on_statement", "credit", "missing", "unapplied_payment", "amount_differs", "disputed", "corrected", "unknown_payment", "matched"];

function signed(n: number) {
  return n === 0 ? money(0) : `${n > 0 ? "+" : "-"}${money(Math.abs(n))}`;
}

function CreditButtons({ item, reload }: { item: Item; reload: () => void }) {
  const { actor, setActor } = useActor();
  const fb = useFeedback();
  const [busy, setBusy] = useState(false);
  if (item.credit_status !== "open" || !item.credit_id) return null;
  if (!canApprove(actor.role, "controller")) {
    const p = personFor("controller");
    return (
      <Button size="sm" onClick={() => setActor(p)}>
        Act as {p.user} (Controller) to claim
      </Button>
    );
  }
  const decide = async (approve: boolean) => {
    setBusy(true);
    try {
      const r = await api<{ status: string; applied_invoice_number: string | null }>(`/api/credits/${item.credit_id}/decide`, { method: "POST", json: { ...actor, approve } });
      fb.toast(
        "success",
        approve ? `Credit ${item.reference} claimed` : `Credit ${item.reference} declined`,
        r.status === "applied" ? `Deducted from the scheduled payment for ${r.applied_invoice_number}; remittance advice sent.` : approve ? "It comes off the vendor's next invoice." : undefined,
      );
      reload();
    } catch (e) {
      fb.toast("error", "Could not decide", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex gap-1.5">
      <Button size="sm" variant="good" onClick={() => decide(true)} disabled={busy}>
        Claim as {actor.user}
      </Button>
      <Button size="sm" variant="ghost" onClick={() => decide(false)} disabled={busy}>
        Decline
      </Button>
    </div>
  );
}

function StatementCard({ st, reload }: { st: StatementRow; reload: () => void }) {
  const r = st.result;
  const title = (
    <span className="flex flex-wrap items-center gap-2">
      <FileSpreadsheet className="h-4 w-4 text-slate-500" /> {st.vendor || st.vendor_name_raw || st.file_name}
      {st.statement_date && <span className="font-normal text-slate-500">statement of {st.statement_date}</span>}
      {st.extraction?.method && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-normal text-slate-600">read by {st.extraction.method === "vision" ? "the vision model" : "the text layer"}</span>}
    </span>
  );
  const action = (
    <a href={`/api/statements/${st.id}/file`} target="_blank" rel="noreferrer" className="text-xs text-indigo-600 hover:underline">
      View PDF
    </a>
  );
  if (st.status !== "reconciled" || !r) {
    return (
      <Card title={title} action={action}>
        <p className="text-sm text-slate-600">
          {st.status === "unmatched_vendor"
            ? `${st.vendor_name_raw || "The sender"} is not in the vendor master, so nothing was reconciled and nothing was sent.`
            : st.status === "failed"
              ? "Could not read this statement."
              : "Reading the statement..."}
        </p>
      </Card>
    );
  }
  const items = [...r.items].sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind));
  const ungrounded = (st.extraction?.lines || []).filter((l) => !l.grounded).length;
  return (
    <Card title={title} action={action} pad={false}>
      <div className="grid grid-cols-2 gap-px border-b border-slate-100 bg-slate-100 md:grid-cols-4">
        {[
          ["They say we owe", money(Number(r.vendor_balance))],
          ["Our books say", money(Number(r.our_balance))],
          ["Difference", signed(Number(r.difference))],
          ["Unexplained", money(Number(r.unexplained))],
        ].map(([k, v]) => (
          <div key={k} className="bg-white px-4 py-2.5">
            <div className="text-[11px] uppercase tracking-wide text-slate-500">{k}</div>
            <div className={cx("text-lg font-semibold tabular-nums", k === "Unexplained" && Number(r.unexplained) === 0 && "text-emerald-700")}>{v}</div>
          </div>
        ))}
      </div>
      {Number(r.unexplained) === 0 && (
        <div className="flex items-center gap-1.5 border-b border-slate-100 px-4 py-2 text-xs text-emerald-700">
          <CheckCircle2 className="h-3.5 w-3.5" /> Every cent of the difference is explained below.
          {st.extraction?.adds_up === false && <span className="text-amber-700"> Their statement&apos;s own total does not add up.</span>}
          {ungrounded > 0 && <span className="text-amber-700"> {ungrounded} line(s) could not be found in the file&apos;s text.</span>}
        </div>
      )}
      <ul className="divide-y divide-slate-50">
        {items.map((x, i) => {
          const k = KIND[x.kind] || KIND.matched;
          return (
            <li key={`${x.reference}-${i}`} className={cx("grid gap-2 px-4 py-2.5 md:grid-cols-[180px_1fr_auto] md:items-start", x.kind === "matched" && "text-slate-500")}>
              <div>
                {x.invoice_id ? (
                  <Link href={`/invoices/${x.invoice_id}`} className="font-mono text-[12.5px] font-medium hover:underline">
                    {x.reference}
                  </Link>
                ) : (
                  <Mono className="font-medium">{x.reference}</Mono>
                )}
                <div className="mt-0.5">
                  <span className={cx("rounded px-1.5 py-0.5 text-[11px] font-medium", k.tone)}>{k.label}</span>
                </div>
              </div>
              <div className="text-[12.5px] leading-snug">
                {x.text}
                <div className="mt-0.5 text-[11px] text-slate-400">
                  {x.statement_amount !== null && <>theirs {money(Number(x.statement_amount))}</>}
                  {x.our_amount !== null && <> · ours {money(Number(x.our_amount))}</>}
                  {Number(x.effect) !== 0 && <> · explains {signed(Number(x.effect))}</>}
                </div>
              </div>
              <div className="md:text-right">
                <CreditButtons item={x} reload={reload} />
              </div>
            </li>
          );
        })}
      </ul>
      {r.emailed && (
        <div className="flex items-center gap-1.5 border-t border-slate-100 px-4 py-2 text-[11px] text-slate-500">
          <Mail className="h-3 w-3" /> Sent {r.emailed} the requests and explanations above (missing copies, payments to apply, invoices to confirm).
        </div>
      )}
    </Card>
  );
}

export default function StatementsPage() {
  const fb = useFeedback();
  const { data, reload } = useData<Data>("/api/statements");
  const { data: demos } = useData<Demo[]>("/api/demo/statements");
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const loadDemo = async () => {
    setBusy(true);
    try {
      await api("/api/demo/statements", { method: "POST", json: null });
      fb.toast("info", "Two vendor statements arrived", "The agent is reading them and reconciling against the ledger.");
      reload();
    } catch (e) {
      fb.toast("error", "Could not load", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const upload = async (f: FileList | null) => {
    if (!f?.length) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f[0]);
      await api("/api/statements", { method: "POST", body: fd });
      fb.toast("info", "Statement received", "Reconciling now.");
      reload();
    } catch (e) {
      fb.toast("error", "Upload failed", (e as Error).message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
            <Scale className="h-5 w-5 text-indigo-600" /> Vendor statements
          </h1>
          <p className="max-w-3xl text-sm text-slate-500">
            A vendor&apos;s statement is their view of what we owe. Tollgate reads it, matches every line against the ledger and explains the gap to the cent: invoices we never
            received, payments they never applied, credits we never took, and invoices in our books that the vendor itself does not list. A statement line is never paid on its own.
          </p>
        </div>
        <div className="flex gap-2">
          <input ref={fileRef} type="file" accept="application/pdf" hidden onChange={(e) => upload(e.target.files)} />
          <Button onClick={() => fileRef.current?.click()} disabled={busy}>
            <FileUp className="h-4 w-4" /> Upload a statement
          </Button>
          <Button variant="primary" onClick={loadDemo} disabled={busy}>
            Load demo statements
          </Button>
        </div>
      </div>
      {data && data.pending > 0 && <div className="animate-pulse text-sm text-violet-700">Reconciling {data.pending} statement(s)...</div>}
      {!data ? (
        <Empty>Loading...</Empty>
      ) : data.statements.length === 0 ? (
        <Card title="No statements yet">
          <p className="mb-3 text-sm text-slate-600">Load the demo inbox first, so there are invoices to reconcile against. Then load these:</p>
          <ul className="space-y-2">
            {demos?.map((d) => (
              <li key={d.index} className="text-[13px]">
                <a href={`/api/demo/statements/${d.index}/file`} target="_blank" rel="noreferrer" className="font-medium text-indigo-600 hover:underline">
                  {d.title}
                </a>
                <div className="text-slate-500">{d.expectation}</div>
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        data.statements.map((st) => <StatementCard key={st.id} st={st} reload={reload} />)
      )}
    </div>
  );
}
