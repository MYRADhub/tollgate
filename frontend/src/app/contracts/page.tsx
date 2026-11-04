"use client";

import { ReactNode, useState } from "react";
import { Bot, CheckCircle2, Plus, Quote, ScrollText, XCircle } from "lucide-react";
import { api, ROLE_LABEL, useActor, useData } from "@/lib/api";
import { Button, Card, Empty, cx } from "@/components/ui";

type Term = { id: number; kind: string; params: Record<string, unknown>; quote: string; summary: string; status: string; source: string; reviewed_by: string | null };
type Contract = {
  id: number;
  vendor_id: string;
  vendor: string;
  title: string;
  effective_date: string | null;
  text: string;
  terms: Term[];
  metrics: { period: string; metric: string; value: number; source: string }[];
};
type Vendor = { id: string; name: string };

const KIND: Record<string, string> = {
  sla_credit: "Service credit",
  volume_price: "Volume price",
  price_cap: "Price cap",
  early_pay_discount: "Early-payment discount",
};

function Highlighted({ text, quotes }: { text: string; quotes: string[] }) {
  const marks: [number, number][] = [];
  for (const q of quotes) {
    const i = text.indexOf(q);
    if (i >= 0) marks.push([i, i + q.length]);
  }
  marks.sort((a, b) => a[0] - b[0]);
  const parts: ReactNode[] = [];
  let at = 0;
  marks.forEach(([a, b], k) => {
    if (a < at) return;
    parts.push(text.slice(at, a));
    parts.push(
      <mark key={k} className="rounded bg-amber-100 px-0.5 text-slate-900">
        {text.slice(a, b)}
      </mark>,
    );
    at = b;
  });
  parts.push(text.slice(at));
  return <pre className="max-h-[420px] overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-4 font-sans text-[12.5px] leading-relaxed text-slate-700 ring-1 ring-slate-200">{parts}</pre>;
}

function TermRow({ t, reload }: { t: Term; reload: () => void }) {
  const { actor } = useActor();
  const [err, setErr] = useState<string | null>(null);
  const decide = async (decision: string) => {
    setErr(null);
    try {
      await api(`/api/terms/${t.id}/decide`, { method: "POST", json: { ...actor, decision } });
      reload();
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  return (
    <li className={cx("rounded-lg p-3 ring-1", t.status === "proposed" ? "bg-amber-50/60 ring-amber-200" : t.status === "rejected" ? "bg-slate-50 opacity-60 ring-slate-200" : "bg-white ring-slate-200")}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-slate-900 px-1.5 py-0.5 text-[11px] font-medium text-white">{KIND[t.kind] || t.kind}</span>
        <span className="text-[13px] font-medium text-slate-900">{t.summary}</span>
        <span className="ml-auto flex items-center gap-1 text-[11px] text-slate-500">
          {t.status === "approved" && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />}
          {t.status === "rejected" && <XCircle className="h-3.5 w-3.5 text-rose-600" />}
          {t.status === "proposed" ? "awaiting review" : `${t.status} by ${t.reviewed_by}`}
        </span>
      </div>
      <p className="mt-1.5 flex gap-1.5 text-[12.5px] italic leading-relaxed text-slate-600">
        <Quote className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
        {t.quote}
      </p>
      <div className="mt-1 text-[11px] text-slate-400">{t.source === "reviewed" ? "extracted and reviewed" : `proposed by ${t.source}; quote verified word for word in the contract`}</div>
      {t.status === "proposed" && (
        <div className="mt-2 flex items-center gap-2">
          <Button size="sm" variant="good" onClick={() => decide("approved")}>
            Approve as {actor.user}
          </Button>
          <Button size="sm" variant="danger" onClick={() => decide("rejected")}>
            Reject
          </Button>
          <span className="text-[11px] text-slate-500">controller or CFO</span>
        </div>
      )}
      {err && <div className="mt-2 rounded bg-rose-50 px-2 py-1 text-xs text-rose-700">{err}</div>}
    </li>
  );
}

function ContractCard({ c, reload }: { c: Contract; reload: () => void }) {
  const { actor } = useActor();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const reread = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<{ found: number; added: number; rejected: string[] }>(`/api/contracts/${c.id}/extract`, { method: "POST", json: actor });
      setMsg(`The model found ${r.found} term(s); ${r.added} new for review${r.rejected.length ? `; ${r.rejected.length} discarded (${r.rejected.join("; ")})` : ""}.`);
      reload();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <ScrollText className="h-4 w-4 text-slate-500" /> {c.vendor} · <span className="font-normal text-slate-600">{c.title}</span>
        </span>
      }
      action={
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={() => setOpen((x) => !x)}>
            {open ? "Hide contract" : "Show contract"}
          </Button>
          <Button size="sm" onClick={reread} disabled={busy}>
            <Bot className="h-3.5 w-3.5" /> {busy ? "Reading..." : "Read again with AI"}
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        {c.terms.length === 0 ? (
          <div className="text-[13px] text-slate-500">No terms that change what we pay.</div>
        ) : (
          <ul className="space-y-2">
            {c.terms.map((t) => (
              <TermRow key={t.id} t={t} reload={reload} />
            ))}
          </ul>
        )}
        {c.metrics.length > 0 && (
          <div className="rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Measured service levels (our monitoring)</div>
            {c.metrics.map((m) => (
              <div key={m.period} className="flex justify-between gap-3 text-[12.5px]">
                <span>
                  {m.period} availability <b className={cx(m.value < 99.95 ? "text-rose-700" : "text-slate-800")}>{m.value}%</b>
                </span>
                <span className="text-right text-slate-500">{m.source}</span>
              </div>
            ))}
          </div>
        )}
        {msg && <div className="rounded bg-indigo-50 px-3 py-2 text-xs text-indigo-800">{msg}</div>}
        {open && <Highlighted text={c.text} quotes={c.terms.filter((t) => t.status !== "rejected").map((t) => t.quote)} />}
      </div>
    </Card>
  );
}

function AddContract({ reload }: { reload: () => void }) {
  const { actor } = useActor();
  const { data: vendors } = useData<Vendor[]>("/api/vendors");
  const [vendor, setVendor] = useState("");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<{ found: number; added: number; rejected: string[] }>("/api/contracts", { method: "POST", json: { ...actor, vendor_id: vendor, title, text } });
      setMsg(`Read it: ${r.found} term(s) found and waiting for review below.`);
      setText("");
      setTitle("");
      reload();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="Add a contract">
      <div className="space-y-2">
        <div className="flex flex-wrap gap-2">
          <select value={vendor} onChange={(e) => setVendor(e.target.value)} className="rounded-md border border-slate-300 px-2 py-1.5 text-sm">
            <option value="">Vendor...</option>
            {vendors?.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title, e.g. Master Services Agreement" className="min-w-[260px] flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
        </div>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} placeholder="Paste the contract text. The model proposes the terms that change what you pay, each with its exact clause; you approve them." className="w-full rounded-md border border-slate-300 px-2 py-1.5 font-mono text-xs" />
        <div className="flex items-center gap-3">
          <Button variant="primary" onClick={submit} disabled={busy || !vendor || text.length < 200}>
            <Plus className="h-4 w-4" /> {busy ? "Reading the contract..." : "Read with AI"}
          </Button>
          {msg && <span className="text-xs text-slate-600">{msg}</span>}
        </div>
      </div>
    </Card>
  );
}

export default function ContractsPage() {
  const { data, reload } = useData<Contract[]>("/api/contracts");
  const { actor } = useActor();
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Contracts</h1>
        <p className="max-w-3xl text-sm text-slate-500">
          What each vendor agreed to. A model reads every contract once and proposes the terms that change what we pay, quoting the clause; a quote that is not in the contract word for word is thrown out. A controller approves the terms, and from then on code applies them to every invoice. You are acting as {actor.user} ({ROLE_LABEL[actor.role]}).
        </p>
      </div>
      {!data ? <Empty>Loading...</Empty> : <div className="grid gap-4 xl:grid-cols-2">{data.map((c) => <ContractCard key={c.id} c={c} reload={reload} />)}</div>}
      <AddContract reload={reload} />
    </div>
  );
}
