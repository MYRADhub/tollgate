"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { FileUp, FlaskConical, ShieldCheck, ShieldX, Swords } from "lucide-react";
import { InvoiceRow, ago, api, money, useData } from "@/lib/api";
import { Button, Card, Empty, Flag, StatusPill, cx } from "@/components/ui";
import { useFeedback } from "@/components/Feedback";

type Template = { key: string; name: string; technique: string; description: string; expected: string; editable: string | null; default_text: string | null };
type Attempt = { group: string; template: string; name: string; technique: string; outcome: "caught" | "missed" | "pending"; created_at: string; invoices: (InvoiceRow & { outcome: string; checks: string[] })[] };
type Evals = {
  available: boolean;
  ran_at?: string;
  runs_per_case?: number;
  passed?: number;
  total?: number;
  models?: Record<string, string>;
  suites?: Record<string, { case: string; name?: string; runs: number; passed: number; controls_fired?: Record<string, number> }[]>;
};

const SUITE: Record<string, string> = { attacks: "Attacks stopped before payment", inbox: "Demo inbox outcomes", contracts: "Contract terms read correctly", critic: "Critic verdicts" };

function Launch({ t, onDone }: { t: Template; onDone: () => void }) {
  const fb = useFeedback();
  const [text, setText] = useState(t.default_text || "");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api("/api/lab/attack", { method: "POST", json: { template: t.key, text: t.editable ? text : undefined } });
      fb.toast("info", `${t.name}: sent`, "It is going through the same pipeline as real mail. Watch the attempts list.");
      onDone();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[13.5px] font-semibold text-slate-900">{t.name}</div>
          <div className="text-[11px] uppercase tracking-wide text-rose-700">{t.technique}</div>
        </div>
        <Button size="sm" variant="primary" onClick={go} disabled={busy}>
          <Swords className="h-3.5 w-3.5" /> {busy ? "Sending..." : "Launch"}
        </Button>
      </div>
      <p className="text-[12.5px] leading-relaxed text-slate-600">{t.description}</p>
      {t.editable && (
        <>
          {editing ? (
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} className="rounded-md border border-slate-300 px-2 py-1.5 font-mono text-[11.5px]" />
          ) : (
            <button onClick={() => setEditing(true)} className="self-start text-xs text-indigo-600 hover:underline">
              Write your own wording
            </button>
          )}
        </>
      )}
      {err && <div className="rounded bg-rose-50 px-2 py-1 text-xs text-rose-700">{err}</div>}
    </div>
  );
}

function Scorecard({ e }: { e: Evals }) {
  if (!e.available || !e.suites) return null;
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-600" /> Evaluation on the real Vultr models: {e.passed}/{e.total} passed
        </span>
      }
      action={<span className="text-[11px] text-slate-500">{e.runs_per_case} runs per case · {e.ran_at && new Date(e.ran_at).toLocaleString()}</span>}
    >
      <div className="grid gap-4 lg:grid-cols-2">
        {Object.entries(e.suites).map(([k, cases]) => {
          const p = cases.reduce((a, c) => a + c.passed, 0);
          const t = cases.reduce((a, c) => a + c.runs, 0);
          return (
            <div key={k} className="rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200">
              <div className="mb-1.5 flex justify-between text-[13px] font-medium">
                <span>{SUITE[k] || k}</span>
                <span className={cx("tabular-nums", p === t ? "text-emerald-700" : "text-amber-700")}>
                  {p}/{t}
                </span>
              </div>
              <ul className="space-y-0.5">
                {cases.map((c) => (
                  <li key={c.case} className="flex justify-between gap-3 text-[12px] text-slate-600">
                    <span className="truncate">{c.name || c.case}</span>
                    <span className="tabular-nums">
                      {c.passed}/{c.runs}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
      {e.models && <div className="mt-3 text-[11px] text-slate-500">Models: {Object.entries(e.models).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>}
    </Card>
  );
}

export default function LabPage() {
  const fb = useFeedback();
  const { data: templates } = useData<Template[]>("/api/lab/templates");
  const { data: attempts, reload } = useData<Attempt[]>("/api/lab/attempts");
  const { data: evals } = useData<Evals>("/api/lab/evals");
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const caught = attempts?.filter((a) => a.outcome === "caught").length ?? 0;
  const missed = attempts?.filter((a) => a.outcome === "missed").length ?? 0;
  const upload = async (f: FileList | null) => {
    if (!f?.length) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", f[0]);
      await api("/api/lab/upload", { method: "POST", body: fd });
      fb.toast("info", "Your PDF is in", "Watch the attempts list.");
      reload();
    } catch (e) {
      fb.toast("error", "Upload failed", (e as Error).message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
            <FlaskConical className="h-5 w-5 text-rose-600" /> Try to fool Tollgate
          </h1>
          <p className="max-w-3xl text-sm text-slate-500">
            Launch a real attack, or upload your own invoice PDF, and watch it go through exactly the same reading, controls, agent and policy guard as real mail. Lab invoices never send email, never join a payment run, and never count on the dashboard. If one gets scheduled for payment, it shows here as a miss.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right text-sm">
            <span className="font-semibold text-emerald-700">{caught} caught</span> · <span className={cx("font-semibold", missed ? "text-rose-700" : "text-slate-500")}>{missed} missed</span>
          </div>
          <input ref={fileRef} type="file" accept="application/pdf" hidden onChange={(e) => upload(e.target.files)} />
          <Button onClick={() => fileRef.current?.click()} disabled={uploading}>
            <FileUp className="h-4 w-4" /> {uploading ? "Uploading..." : "Upload your own attack"}
          </Button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{templates?.map((t) => <Launch key={t.key} t={t} onDone={reload} />)}</div>

      <Card title="Attempts" pad={false}>
        {!attempts ? (
          <Empty>Loading...</Empty>
        ) : attempts.length === 0 ? (
          <Empty>No attempts yet. Launch one above.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {attempts.map((a) => (
              <li key={a.group} className="flex flex-wrap items-start gap-3 px-4 py-3">
                <div className="mt-0.5">
                  {a.outcome === "caught" ? <ShieldCheck className="h-5 w-5 text-emerald-600" /> : a.outcome === "missed" ? <ShieldX className="h-5 w-5 text-rose-600" /> : <FlaskConical className="h-5 w-5 animate-pulse text-violet-500" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-[13.5px] font-medium">
                    {a.name}
                    <span className={cx("rounded px-1.5 py-0.5 text-[11px]", a.outcome === "caught" ? "bg-emerald-50 text-emerald-700" : a.outcome === "missed" ? "bg-rose-50 text-rose-700" : "bg-violet-50 text-violet-700")}>
                      {a.outcome === "pending" ? "reading..." : a.outcome}
                    </span>
                    <span className="text-[11px] font-normal text-slate-400">{ago(a.created_at)}</span>
                  </div>
                  {a.invoices.map((i) => (
                    <Link key={i.id} href={`/invoices/${i.id}`} className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-600 hover:text-slate-900">
                      <span className="font-mono">{i.number || i.file_name}</span>
                      <span>{money(i.total)}</span>
                      <StatusPill status={i.status} />
                      {i.checks.map((c) => (
                        <Flag key={c} code={c} />
                      ))}
                    </Link>
                  ))}
                  {a.invoices[0]?.summary && <p className="mt-1 line-clamp-2 text-xs text-slate-500">{a.invoices[a.invoices.length - 1].summary}</p>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {evals && <Scorecard e={evals} />}
    </div>
  );
}
