"use client";

import { useState } from "react";
import { Bot, CheckCircle2, MailQuestion, Send, ShieldAlert, ShieldCheck, ShieldX } from "lucide-react";
import { ago, api, useData } from "@/lib/api";
import { Button, Card, Empty, cx } from "@/components/ui";
import { useFeedback } from "@/components/Feedback";

type Preset = { key: string; label: string; who: string; sender: string; subject: string; body: string };
type InvoiceFact = { invoice: string; amount: string; currency: string; status: string; pay_date?: string; paid_on?: string; pay_amount?: string; deductions?: { reason: string; amount: string }[] };
type Inquiry = {
  id: number;
  sender: string;
  subject: string;
  vendor: string | null;
  match: string;
  match_note: string;
  intent: string;
  asked_about: string[];
  facts: { invoices: InvoiceFact[]; not_on_your_account: string[] } | null;
  flags: string[];
  reply_source: string | null;
  draft_problems: string[];
  outcome: string;
  created_at: string;
  question: string;
  reply: { subject: string; body: string; status: string; recipient: string } | null;
};

const MATCH: Record<string, { label: string; tone: string; icon: typeof ShieldCheck }> = {
  address: { label: "Registered address", tone: "bg-emerald-50 text-emerald-700 ring-emerald-200", icon: ShieldCheck },
  domain: { label: "Vendor's company domain", tone: "bg-emerald-50 text-emerald-700 ring-emerald-200", icon: ShieldCheck },
  lookalike: { label: "Lookalike domain", tone: "bg-rose-50 text-rose-700 ring-rose-200", icon: ShieldX },
  auth_failed: { label: "Failed sender authentication", tone: "bg-rose-50 text-rose-700 ring-rose-200", icon: ShieldX },
  unknown: { label: "Unknown sender", tone: "bg-slate-100 text-slate-600 ring-slate-200", icon: ShieldAlert },
};

const FLAG: Record<string, string> = {
  impersonation: "Impersonation attempt",
  bank_change_request: "Bank change refused",
  asked_about_other_invoices: "Asked about invoices that are not theirs",
  ai_instructions: "Instructions for the AI ignored",
};

const INTENT: Record<string, string> = {
  payment_status: "Payment status",
  deduction_question: "Why was the payment lower?",
  bank_change: "Bank details change",
  other: "Other",
};

function Composer({ onSent }: { onSent: () => void }) {
  const fb = useFeedback();
  const { data: presets } = useData<Preset[]>("/api/demo/inquiry-presets");
  const [key, setKey] = useState<string | null>(null);
  const [msg, setMsg] = useState({ sender: "", subject: "", body: "" });
  const [busy, setBusy] = useState(false);
  const pick = (p: Preset) => {
    setKey(p.key);
    setMsg({ sender: p.sender, subject: p.subject, body: p.body });
  };
  const send = async () => {
    setBusy(true);
    try {
      await api("/api/demo/inquiry", { method: "POST", json: msg });
      fb.toast("info", "Question sent to the AP inbox", "The agent is checking who sent it and what they may be told.");
      onSent();
    } catch (e) {
      fb.toast("error", "Could not send", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const field = "w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-[13px] focus:border-indigo-400 focus:outline-none";
  return (
    <Card title="Play a vendor: email the AP inbox">
      <div className="mb-3 flex flex-wrap gap-1.5">
        {presets?.map((p) => (
          <button
            key={p.key}
            onClick={() => pick(p)}
            className={cx("rounded-full px-2.5 py-1 text-xs font-medium ring-1", key === p.key ? "bg-slate-900 text-white ring-slate-900" : "bg-white text-slate-700 ring-slate-300 hover:bg-slate-50")}
          >
            {p.label}
          </button>
        ))}
      </div>
      {key && <div className="mb-2 text-[11px] text-slate-500">From: {presets?.find((p) => p.key === key)?.who}</div>}
      <div className="space-y-2">
        <input aria-label="From" placeholder="From (email address)" value={msg.sender} onChange={(e) => setMsg({ ...msg, sender: e.target.value })} className={field} />
        <input aria-label="Subject" placeholder="Subject" value={msg.subject} onChange={(e) => setMsg({ ...msg, subject: e.target.value })} className={field} />
        <textarea aria-label="Message" placeholder="Message" rows={5} value={msg.body} onChange={(e) => setMsg({ ...msg, body: e.target.value })} className={cx(field, "font-mono text-[12px]")} />
      </div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="text-[11px] text-slate-500">Edit anything. Try your own wording, or a sender that is almost right.</span>
        <Button variant="primary" onClick={send} disabled={busy || !msg.sender || !msg.body}>
          <Send className="h-3.5 w-3.5" /> {busy ? "Sending..." : "Send"}
        </Button>
      </div>
    </Card>
  );
}

function InquiryCard({ q }: { q: Inquiry }) {
  const m = MATCH[q.match] || MATCH.unknown;
  const Icon = m.icon;
  const [facts, setFacts] = useState(false);
  return (
    <li className="space-y-3 px-4 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13.5px] font-semibold text-slate-900">{q.vendor || q.sender}</span>
        <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1", m.tone)} title={q.match_note}>
          <Icon className="h-3 w-3" /> {m.label}
        </span>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">{INTENT[q.intent] || q.intent}</span>
        {q.flags.map((f) => (
          <span key={f} className="rounded bg-rose-50 px-1.5 py-0.5 text-[11px] font-medium text-rose-700">
            {FLAG[f] || f}
          </span>
        ))}
        <span className="ml-auto text-[11px] text-slate-400">{ago(q.created_at)}</span>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200">
          <div className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">
            From {q.sender}: {q.subject}
          </div>
          <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-slate-700">{q.question}</p>
          {q.match_note && <div className="mt-2 text-[11px] text-slate-500">Sender check: {q.match_note}</div>}
        </div>
        <div className="rounded-lg bg-white p-3 ring-1 ring-indigo-200">
          <div className="mb-1 flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-indigo-700">
            <Bot className="h-3 w-3" /> {q.reply ? `Reply (${q.reply.status})` : "No reply"}
          </div>
          {q.reply ? (
            <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-slate-800">{q.reply.body}</p>
          ) : (
            <p className="text-[12.5px] text-slate-500">{q.outcome}</p>
          )}
          {q.reply && (
            <div className="mt-2 text-[11px] text-slate-500">
              {q.reply_source === "model" ? (
                <span className="inline-flex items-center gap-1 text-emerald-700">
                  <CheckCircle2 className="h-3 w-3" /> Worded by the model; every amount, date and reference checked against the ledger
                </span>
              ) : q.draft_problems.length ? (
                <span className="text-amber-700">Model draft rejected ({q.draft_problems.join("; ")}), so the reply was built from the ledger directly</span>
              ) : q.vendor ? (
                "Built from the ledger directly"
              ) : (
                "Fixed reply: nothing about any account is shared with an unverified sender"
              )}
            </div>
          )}
        </div>
      </div>
      {q.facts && (
        <div>
          <button onClick={() => setFacts(!facts)} className="text-xs text-indigo-600 hover:underline">
            {facts ? "Hide" : "Show"} what the agent was allowed to say
          </button>
          {facts && (
            <ul className="mt-1.5 space-y-1 text-[12px] text-slate-600">
              {q.facts.invoices.map((f) => (
                <li key={f.invoice}>
                  <span className="font-mono">{f.invoice}</span>: {f.status}
                  {f.pay_date && `, pay on ${f.pay_date}`}
                  {f.paid_on && `, paid ${f.paid_on}`}
                  {f.pay_amount && `, ${f.currency} ${f.pay_amount}`}
                  {f.deductions?.map((d) => ` · deducted ${d.amount} (${d.reason})`)}
                </li>
              ))}
              {q.facts.not_on_your_account.map((n) => (
                <li key={n}>
                  <span className="font-mono">{n}</span>: not on this vendor&apos;s account, so treated as unknown
                </li>
              ))}
              {!q.facts.invoices.length && !q.facts.not_on_your_account.length && <li>No invoice data (the request did not need any).</li>}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

export default function InquiriesPage() {
  const { data, reload } = useData<{ pending: number; items: Inquiry[] }>("/api/inquiries");
  const { data: cfg } = useData<{ mail: boolean; mailbox: string | null }>("/api/config");
  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <MailQuestion className="h-5 w-5 text-indigo-600" /> Vendor questions
        </h1>
        <p className="max-w-3xl text-sm text-slate-500">
          Suppliers email AP to ask when they will be paid and why a payment was lower than the invoice. Tollgate answers from the ledger, with guard rails written in code: it only
          answers the vendor&apos;s registered address or company domain, only about that vendor&apos;s own invoices, never changes bank details by email, and checks every amount,
          date and reference in the model&apos;s wording before anything is sent.
          {cfg?.mail && cfg.mailbox ? " The AP inbox is live: real emails are answered the same way." : ""}
        </p>
      </div>
      <Composer onSent={reload} />
      <Card
        title="Questions and replies"
        action={data && data.pending > 0 ? <span className="animate-pulse text-[11px] text-violet-600">answering {data.pending}...</span> : undefined}
        pad={false}
      >
        {!data ? (
          <Empty>Loading...</Empty>
        ) : data.items.length === 0 ? (
          <Empty>No questions yet. Pick one above and send it. Load the demo inbox first so there are invoices to ask about.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.items.map((q) => (
              <InquiryCard key={q.id} q={q} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
